#!/usr/bin/env python3
"""Check the published lean-runtime release budgets without test dependencies."""

from __future__ import annotations

import sys
from pathlib import Path
from subprocess import run


ROOT = Path(__file__).resolve().parents[1]
STABLE_SOURCE_ROOTS = ("app", "core", "runtime", "tools", "extensions")
MAX_STABLE_PRODUCTION_LINES = 15_000
MAX_STABLE_TOOLS = 7


def python_lines() -> int:
    """Use the M0 baseline definition: stable source excluding removed research."""

    paths = run(
        [
            "rg",
            "--files",
            *STABLE_SOURCE_ROOTS,
            "-g",
            "*.py",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return sum(
        len((ROOT / path).read_text(encoding="utf-8").splitlines())
        for path in paths
        if not path.startswith("extensions/skill_evolution/")
    )


def stable_tool_names() -> list[str]:
    """Build the default schema without model credentials or optional integrations."""

    from core.config import Config
    from runtime.host import CodeAgent
    from tools.registry import ToolRegistry

    class FakeLLM:
        provider = "test"
        model = "test"

    agent = CodeAgent(
        name="release-metrics",
        llm=FakeLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(ROOT),
        config=Config(
            enable_mcp=False,
            enable_skills=False,
            enable_tracing=False,
            enable_verification_agent=False,
        ),
    )
    try:
        return sorted(schema["function"]["name"] for schema in agent.tool_registry.get_openai_tools())
    finally:
        agent.close()


def main() -> int:
    lines = python_lines()
    tools = stable_tool_names()
    print(f"stable_production_python_lines={lines}")
    print(f"stable_tool_count={len(tools)}")
    print(f"stable_tools={', '.join(tools)}")

    errors = []
    if lines > MAX_STABLE_PRODUCTION_LINES:
        errors.append(
            f"stable production Python exceeds {MAX_STABLE_PRODUCTION_LINES}: {lines}"
        )
    if len(tools) > MAX_STABLE_TOOLS:
        errors.append(f"stable tool count exceeds {MAX_STABLE_TOOLS}: {len(tools)}")
    if errors:
        print("release metric failure: " + "; ".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
