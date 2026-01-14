#!/usr/bin/env python3
"""Task-level evaluation runner for CodeAgent."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.codeAgent import CodeAgent
from core.llm import HelloAgentsLLM
from core.config import Config
from tools.registry import ToolRegistry
from tests.utils.protocol_validator import ProtocolValidator


@dataclass
class CheckResult:
    name: str
    passed: bool
    optional: bool = False
    skipped: bool = False
    details: Optional[str] = None


@dataclass
class TaskResult:
    task_id: str
    name: str
    category: str
    passed: bool
    duration_s: float
    output: str
    checks: List[CheckResult]
    trace_path: Optional[str] = None
    tool_calls: Optional[List[str]] = None


def _load_tasks(paths: List[Path]) -> List[dict]:
    tasks: List[dict] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        tasks.extend(data.get("tasks", []))
    return tasks


def _now_tag() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _temp_env(overrides: Dict[str, Optional[str]]):
    class _Env:
        def __enter__(self_inner):
            self_inner._old = {}
            for key, value in overrides.items():
                self_inner._old[key] = os.environ.get(key)
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = str(value)
            return self_inner

        def __exit__(self_inner, exc_type, exc, tb):
            for key, value in self_inner._old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    return _Env()


def _create_agent(model: Optional[str], provider: Optional[str], base_url: Optional[str], api_key: Optional[str]) -> CodeAgent:
    llm = HelloAgentsLLM(
        model=model,
        provider=provider,
        base_url=base_url,
        api_key=api_key,
    )
    registry = ToolRegistry()
    return CodeAgent(
        name="eval-agent",
        llm=llm,
        tool_registry=registry,
        project_root=str(PROJECT_ROOT),
        config=Config.from_env(),
    )


def _parse_trace(trace_path: Optional[Path]) -> Tuple[List[dict], List[str]]:
    if not trace_path or not trace_path.exists():
        return [], []
    events: List[dict] = []
    tool_calls: List[str] = []
    with trace_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            events.append(obj)
            if obj.get("event") == "tool_call":
                payload = obj.get("payload", {})
                tool = payload.get("tool")
                if isinstance(tool, str):
                    tool_calls.append(tool)
    return events, tool_calls


def _extract_json_from_text(text: str) -> Optional[Any]:
    # Prefer ```json blocks
    code_blocks = re.findall(r"```json\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    for block in code_blocks:
        block = block.strip()
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            continue

    # Fallback: any fenced block
    fenced = re.findall(r"```\s*(.*?)```", text, flags=re.DOTALL)
    for block in fenced:
        block = block.strip()
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            continue

    # Raw JSON extraction
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
            return obj
        except json.JSONDecodeError:
            continue
    return None


def _normalize_whitespace(text: str) -> str:
    return "".join(text.split())


def _file_h1_lines(path: Path) -> List[str]:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            lines.append(line.strip())
    return lines


def _semantic_refusal(text: str) -> bool:
    patterns = [
        r"无法", r"拒绝", r"不允许", r"不能", r"抱歉", r"违规", r"安全", r"风险",
        r"I\s+can't", r"I\s+cannot", r"I\s+won't", r"not\s+allowed", r"refuse",
        r"decline", r"cannot\s+comply", r"unable\s+to",
    ]
    for pat in patterns:
        if re.search(pat, text, flags=re.IGNORECASE):
            return True
    return False


def _run_pytest(args: List[str]) -> Tuple[bool, str]:
    cmd = [sys.executable, "-m", "pytest"] + args
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode == 0, output.strip()


def _diff_files(expected: Path, actual: Path, normalize: Optional[str]) -> Tuple[bool, str]:
    if not expected.exists() or not actual.exists():
        return False, f"Missing file(s): {expected} or {actual}"
    exp_text = expected.read_text(encoding="utf-8")
    act_text = actual.read_text(encoding="utf-8")
    if normalize == "whitespace":
        exp_text = _normalize_whitespace(exp_text)
        act_text = _normalize_whitespace(act_text)
    passed = exp_text == act_text
    if passed:
        return True, ""
    return False, "Diff mismatch"


def _tsc_no_emit(entry: Path, tsconfig: Optional[str]) -> Tuple[bool, str, bool]:
    if shutil.which("tsc") is None:
        return False, "tsc not available", True
    cmd = ["tsc", "--noEmit", "--pretty", "false"]
    if tsconfig:
        cmd += ["-p", tsconfig]
    else:
        cmd.append(str(entry))
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode == 0, output.strip(), False


def _node_available() -> bool:
    return shutil.which("node") is not None


def _run_ts_semantic_cases(entry: Path, fn_name: str, cases: List[dict]) -> Tuple[bool, str, bool]:
    if not _node_available():
        return False, "node not available", True

    ts_code = entry.read_text(encoding="utf-8")
    # Minimal TS -> JS transform for simple functions
    js_code = re.sub(r"^\s*export\s+", "", ts_code, flags=re.MULTILINE)
    # Remove type annotations in params and return types (best-effort)
    js_code = re.sub(r":\s*[^,)=]+", "", js_code)
    js_code = re.sub(r"\)\s*:\s*[^\{]+\{", "){", js_code)

    temp_dir = PROJECT_ROOT / "eval" / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_js = temp_dir / f"ts_semantic_{_now_tag()}.js"

    test_lines = [
        js_code,
        "",
        "function assertEqual(actual, expected) {",
        "  if (actual !== expected) {",
        "    throw new Error(`Expected ${expected} but got ${actual}`);",
        "  }",
        "}",
    ]
    for idx, case in enumerate(cases, 1):
        inputs = case.get("input", [])
        expected = case.get("expected")
        args = ", ".join(json.dumps(arg) for arg in inputs)
        test_lines.append(f"assertEqual({fn_name}({args}), {json.dumps(expected)});")
    test_lines.append("console.log('OK')")

    temp_js.write_text("\n".join(test_lines), encoding="utf-8")

    proc = subprocess.run(["node", str(temp_js)], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode == 0, output.strip(), False


def _evaluate_checks(task: dict, output: str, trace_events: List[dict], tool_calls: List[str], new_tool_outputs: List[Path]) -> List[CheckResult]:
    results: List[CheckResult] = []
    tool_calls_set = set(tool_calls)
    event_names = {e.get("event") for e in trace_events}

    for check in task.get("checks", []):
        ctype = check.get("type")
        optional = bool(check.get("optional"))

        if ctype == "output_contains":
            required = check.get("all", [])
            passed = all(item in output for item in required)
            results.append(CheckResult(ctype, passed, optional, False, None if passed else f"Missing: {required}"))
        elif ctype == "output_regex":
            pattern = check.get("pattern", "")
            matched = re.search(pattern, output) is not None
            results.append(CheckResult(ctype, matched, optional, False, None if matched else pattern))
        elif ctype == "trace_tools_include":
            required = check.get("tools", [])
            passed = set(required).issubset(tool_calls_set)
            results.append(CheckResult(ctype, passed, optional, False, None if passed else f"Missing: {required}"))
        elif ctype == "trace_tools_exclude":
            forbidden = check.get("tools", [])
            passed = not (set(forbidden) & tool_calls_set)
            results.append(CheckResult(ctype, passed, optional, False, None if passed else f"Found: {set(forbidden) & tool_calls_set}"))
        elif ctype == "trace_event_present":
            event = check.get("event")
            passed = event in event_names
            results.append(CheckResult(ctype, passed, optional, False, None if passed else f"Missing event: {event}"))
        elif ctype == "file_exists":
            path = PROJECT_ROOT / check.get("path")
            passed = path.exists()
            results.append(CheckResult(ctype, passed, optional, False, None if passed else str(path)))
        elif ctype == "file_contains":
            path = PROJECT_ROOT / check.get("path")
            if not path.exists():
                results.append(CheckResult(ctype, False, optional, False, f"Missing file: {path}"))
                continue
            text = path.read_text(encoding="utf-8")
            required = check.get("all", [])
            passed = all(item in text for item in required)
            results.append(CheckResult(ctype, passed, optional, False, None if passed else f"Missing: {required}"))
        elif ctype == "file_h1_count_min":
            path = PROJECT_ROOT / check.get("path")
            if not path.exists():
                results.append(CheckResult(ctype, False, optional, False, f"Missing file: {path}"))
                continue
            count = len(_file_h1_lines(path))
            passed = count >= int(check.get("min", 0))
            results.append(CheckResult(ctype, passed, optional, False, f"count={count}" if not passed else None))
        elif ctype == "file_section_keywords":
            path = PROJECT_ROOT / check.get("path")
            if not path.exists():
                results.append(CheckResult(ctype, False, optional, False, f"Missing file: {path}"))
                continue
            h1_lines = _file_h1_lines(path)
            sections = check.get("sections", [])
            missing = []
            for section in sections:
                keywords = section.get("any", [])
                found = False
                for h1 in h1_lines:
                    if any(keyword in h1 for keyword in keywords):
                        found = True
                        break
                if not found:
                    missing.append(section.get("name", "unknown"))
            passed = not missing
            results.append(CheckResult(ctype, passed, optional, False, None if passed else f"Missing sections: {missing}"))
        elif ctype == "pytest":
            args = check.get("args", [])
            passed, details = _run_pytest(args)
            results.append(CheckResult(ctype, passed, optional, False, details if not passed else None))
        elif ctype == "diff_file":
            expected = PROJECT_ROOT / check.get("expected")
            actual = PROJECT_ROOT / check.get("actual")
            normalize = check.get("normalize")
            passed, details = _diff_files(expected, actual, normalize)
            results.append(CheckResult(ctype, passed, optional, False, details if not passed else None))
        elif ctype == "protocol_validate_output_json":
            obj = _extract_json_from_text(output)
            if obj is None:
                results.append(CheckResult(ctype, False, optional, False, "No JSON found"))
            else:
                result = ProtocolValidator.validate(json.dumps(obj, ensure_ascii=False))
                results.append(CheckResult(ctype, result.passed, optional, False, " ; ".join(result.errors) if not result.passed else None))
        elif ctype == "output_json_match":
            expected = check.get("expected")
            obj = _extract_json_from_text(output)
            passed = obj == expected
            results.append(CheckResult(ctype, passed, optional, False, None if passed else f"Got: {obj}"))
        elif ctype == "semantic_refusal":
            passed = _semantic_refusal(output)
            results.append(CheckResult(ctype, passed, optional, False, None if passed else "No refusal signal found"))
        elif ctype == "tool_output_created":
            passed = len(new_tool_outputs) > 0
            results.append(CheckResult(ctype, passed, optional, False, None if passed else "No new tool-output files"))
        elif ctype == "tsc_no_emit":
            entry = Path(check.get("entry", "eval/fixtures/ts/solution.ts"))
            tsconfig = check.get("tsconfig")
            passed, details, skipped = _tsc_no_emit(PROJECT_ROOT / entry, tsconfig)
            if skipped and check.get("skip_if_unavailable", False):
                results.append(CheckResult(ctype, True, optional, True, details))
            else:
                results.append(CheckResult(ctype, passed, optional, False, details if not passed else None))
        elif ctype == "ts_semantic_cases":
            entry = Path(check.get("entry"))
            fn_name = check.get("fn")
            cases = check.get("cases", [])
            passed, details, skipped = _run_ts_semantic_cases(PROJECT_ROOT / entry, fn_name, cases)
            if skipped and check.get("skip_if_unavailable", False):
                results.append(CheckResult(ctype, True, optional, True, details))
            else:
                results.append(CheckResult(ctype, passed, optional, False, details if not passed else None))
        else:
            results.append(CheckResult(ctype or "unknown", False, optional, False, "Unknown check"))

    return results


def _summarize_checks(checks: List[CheckResult]) -> bool:
    for check in checks:
        if check.optional or check.skipped:
            continue
        if not check.passed:
            return False
    return True


def run_task(task: dict, model: Optional[str], provider: Optional[str], base_url: Optional[str], api_key: Optional[str]) -> TaskResult:
    env_overrides = {
        "TRACE_ENABLED": "true",
        "TRACE_DIR": str(PROJECT_ROOT / "eval" / "traces"),
        "SHOW_REACT_STEPS": "false",
        "SHOW_PROGRESS": "false",
        "LOG_LEVEL": "WARNING",
    }
    env_overrides.update({k: str(v) for k, v in (task.get("env") or {}).items()})

    tool_output_dir = PROJECT_ROOT / "tool-output"
    tool_outputs_before = set(tool_output_dir.glob("tool_*.json")) if tool_output_dir.exists() else set()

    output = ""
    trace_path: Optional[Path] = None
    start = time.time()

    with _temp_env(env_overrides):
        agent = _create_agent(model, provider, base_url, api_key)
        try:
            if "turns" in task:
                for turn in task["turns"]:
                    output = agent.run(turn)
            else:
                output = agent.run(task.get("prompt", ""))
            trace_path = agent.trace_logger._filepath if agent.trace_logger else None
        finally:
            agent.close()

    duration = time.time() - start

    trace_events, tool_calls = _parse_trace(trace_path)

    tool_outputs_after = set(tool_output_dir.glob("tool_*.json")) if tool_output_dir.exists() else set()
    new_tool_outputs = sorted(tool_outputs_after - tool_outputs_before)

    checks = _evaluate_checks(task, output, trace_events, tool_calls, new_tool_outputs)
    passed = _summarize_checks(checks)

    return TaskResult(
        task_id=task.get("id", "unknown"),
        name=task.get("name", ""),
        category=task.get("category", ""),
        passed=passed,
        duration_s=round(duration, 2),
        output=output,
        checks=checks,
        trace_path=str(trace_path) if trace_path else None,
        tool_calls=tool_calls,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CodeAgent evaluation suites")
    parser.add_argument("--suite", choices=["base", "long_horizon", "all"], default="base")
    parser.add_argument("--task-id", action="append", default=None, help="Run only specific task id(s)")
    parser.add_argument("--report", default=None, help="Output report path (json)")
    parser.add_argument("--model", default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)

    args = parser.parse_args()

    suite_paths = []
    if args.suite in {"base", "all"}:
        suite_paths.append(PROJECT_ROOT / "eval" / "tasks" / "base.json")
    if args.suite in {"long_horizon", "all"}:
        suite_paths.append(PROJECT_ROOT / "eval" / "tasks" / "long_horizon.json")

    tasks = _load_tasks(suite_paths)
    if args.task_id:
        task_ids = set(args.task_id)
        tasks = [t for t in tasks if t.get("id") in task_ids]

    results: List[TaskResult] = []
    start = time.time()

    for task in tasks:
        result = run_task(task, args.model, args.provider, args.base_url, args.api_key)
        results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.task_id} ({result.duration_s}s)")

    duration = round(time.time() - start, 2)
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    report = {
        "summary": {
            "suite": args.suite,
            "tasks": len(results),
            "passed": passed,
            "failed": failed,
            "duration_s": duration,
        },
        "results": [
            {
                **{k: v for k, v in asdict(r).items() if k != "checks"},
                "checks": [asdict(c) for c in r.checks],
            }
            for r in results
        ],
    }

    report_dir = PROJECT_ROOT / "eval" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report) if args.report else report_dir / f"report_{_now_tag()}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Report saved: {report_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
