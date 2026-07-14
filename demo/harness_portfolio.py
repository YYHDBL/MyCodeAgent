#!/usr/bin/env python3
"""Run deterministic Harness Engineering demos without a real API key."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import Config
from runtime.context import ContextEngine
from runtime.history import HistoryManager
from runtime.loop import RuntimeRunner
from runtime.subagents import SubagentLauncher, SubagentRequest
from runtime.transcript import ResumeLoader, TranscriptStore
from tests.scenarios.phase0_baselines import CompletionGateBlockedScenarioHost
from tools.context import ToolExecutionContext
from tools.executor import ToolExecutor
from tools.orchestrator import ToolOrchestrator
from tools.permissions import PermissionContext, RiskClassifier
from tools.registry import ToolRegistry
from tools.base import ToolResult, ToolStatus


DEMO_NAMES = (
    "agent-loop",
    "tool-harness",
    "context-engineering",
    "recovery-subagent",
)


class RecordingTrace:
    def __init__(self, *, session_id: str = "phase9-demo", enabled: bool = True):
        self.events: list[tuple[str, int, dict[str, Any]]] = []
        self.session_id = session_id
        self.enabled = enabled

    def log_event(self, name: str, payload: dict[str, Any], step: int = 0) -> None:
        self.events.append((name, step, payload))

    def log_system_messages(self, messages: list[dict[str, Any]]) -> None:
        self.events.append(("system_messages", 0, {"messages": messages}))

    def finalize(self) -> None:
        return None


class DemoContextBuilder:
    def get_system_messages(self) -> list[dict[str, str]]:
        return [{"role": "system", "content": "Deterministic harness demo."}]


class ToolDemoHost:
    def __init__(self, project_root: Path):
        self.project_root = str(project_root)
        self.trace_logger = RecordingTrace(session_id="tool-harness")
        self.tool_registry = ToolRegistry()
        self.tool_registry.register_function("Read", "deterministic read", self._read)
        self.tool_registry.register_function("Grep", "deterministic grep", self._grep)
        self.tool_registry.register_function("Edit", "must be denied", self._edit)
        self.tool_executor = ToolExecutor(
            self.tool_registry,
            context=ToolExecutionContext(
                permission_context=PermissionContext(runtime_mode="readonly_subagent"),
                permission_decider=RiskClassifier().classify,
                project_root=self.project_root,
            ),
        )

    @staticmethod
    def _read(_input: Any) -> ToolResult:
        time.sleep(0.02)
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={"content": "read result"},
            text="read result",
            stats={"time_ms": 20},
            context={"cwd": ".", "params_input": {"input": _input}},
        )

    @staticmethod
    def _grep(_input: Any) -> ToolResult:
        time.sleep(0.001)
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={"content": "grep result"},
            text="grep result",
            stats={"time_ms": 1},
            context={"cwd": ".", "params_input": {"input": _input}},
        )

    @staticmethod
    def _edit(_input: Any) -> ToolResult:
        raise AssertionError("permission core must block this edit")

    @staticmethod
    def _ensure_json_input(raw_args: Any) -> tuple[dict[str, Any], Exception | None]:
        if isinstance(raw_args, dict):
            return raw_args, None
        try:
            return json.loads(raw_args), None
        except Exception as exc:
            return {}, exc


class ScriptedExploreLLM:
    def invoke_raw(self, messages, tools=None, tool_choice=None):
        content = json.dumps(
            {
                "status": "completed",
                "summary": "Child returned a bounded result without parent history.",
                "findings": ["RuntimeRunner is shared by parent and child."],
                "evidence": ["runtime/subagents.py:1"],
                "unresolved_questions": [],
            }
        )
        return {
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 12},
        }


def _trace_rows(events: list[tuple[str, int, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [
        {"event": name, "step": step, "payload": payload}
        for name, step, payload in events
    ]


def _run_agent_loop_demo() -> dict[str, Any]:
    host = CompletionGateBlockedScenarioHost()
    result = RuntimeRunner(host).run(
        "Run pytest, but the scripted model immediately claims completion.",
        show_raw=False,
    )
    events = host.trace_logger.events
    terminal = next(payload for event, _step, payload in reversed(events) if event == "terminal")
    return {
        "demo": "agent-loop",
        "purpose": "Completion is a runtime decision, not a model-side phrase.",
        "result": result,
        "summary": {
            "terminal_reason": terminal["reason"],
            "completion_gate_block_count": sum(
                1
                for event, _step, payload in events
                if event == "completion_gate_verdict" and payload.get("verdict") == "fail"
            ),
        },
        "trace": _trace_rows(events),
    }


def _run_tool_harness_demo() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mycodeagent-tool-demo-") as temp_dir:
        host = ToolDemoHost(Path(temp_dir))
        observations = ToolOrchestrator(host).run(
            [
                {
                    "id": "read-slow",
                    "name": "Read",
                    "arguments": {"input": "README.md"},
                },
                {
                    "id": "grep-fast",
                    "name": "Grep",
                    "arguments": {"input": "RuntimeRunner"},
                },
                {
                    "id": "edit-denied",
                    "name": "Edit",
                    "arguments": {"path": "blocked.txt", "create_content": "no"},
                },
            ],
            step=1,
            trace_logger=host.trace_logger,
        )
        permission_denied_count = sum(
            1
            for name, _step, payload in host.trace_logger.events
            if name == "permission_decision"
            and (payload.get("effective_action") or payload.get("action")) == "deny"
        )
        return {
            "demo": "tool-harness",
            "purpose": "The harness batches safe reads, preserves call order, and denies mutation.",
            "summary": {
                "observation_order": [item.tool_call_id for item in observations],
                "permission_denied_count": permission_denied_count,
                "batch_count": next(
                    payload["batch_count"]
                    for name, _step, payload in host.trace_logger.events
                    if name == "tool_orchestration_plan"
                ),
            },
            "observations": [
                {
                    "tool": item.tool_name,
                    "tool_call_id": item.tool_call_id,
                    "result": json.loads(item.observation),
                }
                for item in observations
            ],
            "trace": _trace_rows(host.trace_logger.events),
        }


def _run_context_demo() -> dict[str, Any]:
    history = HistoryManager()
    for question, answer in (
        ("Inspect loop ownership.", "RuntimeRunner owns the loop."),
        ("Inspect tool ordering.", "ToolOrchestrator preserves order."),
        ("Keep the latest decision.", "Use non-destructive projection."),
    ):
        history.append_user(question)
        history.append_assistant(answer)
    before = history.get_messages()
    trace = RecordingTrace(session_id="context-engineering")
    config = Config(
        context_window=1000,
        compression_threshold=0.1,
        min_retain_rounds=1,
    )
    engine = ContextEngine(
        DemoContextBuilder(),
        config=config,
        summary_generator=lambda messages: f"Archived {len(messages)} messages.",
    )
    engine.record_usage(900)
    compact = engine.compact_if_needed(
        history_manager=history,
        pending_input="Continue.",
        step=1,
        trace_logger=trace,
    )
    view = engine.build_model_view(
        history_manager=history,
        pending_input="Continue.",
        step=1,
        trace_logger=trace,
    )
    return {
        "demo": "context-engineering",
        "purpose": "Compact changes the model projection, never the full history.",
        "summary": {
            "checkpoint_id": compact.get("checkpoint_id"),
            "source_message_count": view.source_message_count,
            "history_message_count": view.history_message_count,
            "projection_mode": view.projection_mode,
            "history_preserved": history.get_messages() == before,
        },
        "model_view": view.messages,
        "trace": _trace_rows(trace.events),
    }


def _run_recovery_subagent_demo() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mycodeagent-recovery-demo-") as temp_dir:
        root = Path(temp_dir)
        transcript = TranscriptStore(root / "transcript.jsonl", session_id="portfolio-session")
        transcript.append_message(
            run_id="run-1",
            step=0,
            role="user",
            content="Preserve progress and inspect the runtime.",
        )
        transcript.append_tool_lifecycle(
            run_id="run-1",
            step=1,
            tool_name="Read",
            tool_call_id="read-1",
            status="completed",
            payload={"result": {"status": "success"}},
        )
        transcript.append_tool_lifecycle(
            run_id="run-1",
            step=2,
            tool_name="Edit",
            tool_call_id="edit-uncertain",
            status="requested",
            payload={"args": {"path": "notes.txt"}},
        )
        transcript.append_tool_lifecycle(
            run_id="run-1",
            step=2,
            tool_name="Edit",
            tool_call_id="edit-uncertain",
            status="started",
            payload={"args": {"path": "notes.txt"}},
        )
        resume = ResumeLoader(transcript).load(run_id="run-1")

        history = HistoryManager()
        history.load_messages(resume.history_messages)
        context_trace = RecordingTrace(session_id="recovery-context")
        context_engine = ContextEngine(DemoContextBuilder())
        context_engine.set_session_memory(resume.session_memory)
        view = context_engine.build_model_view(
            history_manager=history,
            pending_input="Continue safely.",
            step=3,
            trace_logger=context_trace,
        )

        parent_trace = RecordingTrace(session_id="parent-demo", enabled=False)
        scripted_llm = ScriptedExploreLLM()
        launched = SubagentLauncher(
            project_root=root,
            main_llm=scripted_llm,
            light_llm=scripted_llm,
            tool_registry=ToolRegistry(),
            parent_trace_logger=parent_trace,
            parent_history_manager=history,
            parent_context_engine=context_engine,
        ).launch(
            SubagentRequest(
                profile_name="explore",
                task="Inspect the runtime ownership boundary.",
                parent_session_id="portfolio-session",
                parent_run_id="run-1",
            )
        )

        transcript_trace = [
            (
                f"transcript_{event.event_type.value}",
                event.step,
                event.payload,
            )
            for event in transcript.read_events(run_id="run-1")
        ]
        uncertain = resume.uncertain_actions[0]
        return {
            "demo": "recovery-subagent",
            "purpose": (
                "Transcript facts rebuild Session Memory and a bounded child result "
                "enters the Model View without merging parent history."
            ),
            "summary": {
                "transcript_event_count": len(transcript_trace),
                "uncertain_action_count": len(resume.uncertain_actions),
                "uncertain_replay_allowed": uncertain.replay_allowed,
                "session_memory_injected": "session_memory" in view.dynamic_context_sources,
                "subagent_status": launched.status.value,
                "subagent_tool_allowlist": ["Glob", "Grep", "Read"],
            },
            "session_memory": resume.session_memory.to_dict(),
            "subagent_result": (
                launched.result.to_dict()
                if launched.result is not None and hasattr(launched.result, "to_dict")
                else None
            ),
            "trace": _trace_rows(
                transcript_trace + context_trace.events + parent_trace.events
            ),
        }


DEMO_RUNNERS: dict[str, Callable[[], dict[str, Any]]] = {
    "agent-loop": _run_agent_loop_demo,
    "tool-harness": _run_tool_harness_demo,
    "context-engineering": _run_context_demo,
    "recovery-subagent": _run_recovery_subagent_demo,
}


def run_demo(name: str) -> dict[str, Any]:
    try:
        runner = DEMO_RUNNERS[name]
    except KeyError as exc:
        raise ValueError(f"unknown demo: {name}") from exc
    return runner()


def run_all_demos() -> list[dict[str, Any]]:
    return [run_demo(name) for name in DEMO_NAMES]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("demo", choices=(*DEMO_NAMES, "all"))
    parser.add_argument("--output", type=Path, help="Save the JSON report to this path.")
    args = parser.parse_args(argv)

    logging.disable(logging.CRITICAL)
    report: Any = run_all_demos() if args.demo == "all" else run_demo(args.demo)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
