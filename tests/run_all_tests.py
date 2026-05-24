#!/usr/bin/env python3
"""Run the default harness-core verification suite."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_TESTS = [
    "tests/test_context_builder.py",
    "tests/test_context_engineering.py",
    "tests/test_protocol_compliance.py",
    "tests/test_bash_tool.py",
    "tests/test_read_tool.py",
    "tests/test_write_tool.py",
    "tests/test_edit_tool.py",
    "tests/test_todo_write_tool.py",
    "tests/test_app_bootstrap.py",
    "tests/runtime/test_runner.py",
    "tests/runtime/test_context.py",
    "tests/runtime/test_prompt.py",
    "tests/runtime/test_session.py",
    "tests/tools/test_executor.py",
    "tests/extensions",
]

QUICK_TESTS = [
    "tests/test_protocol_compliance.py",
    "tests/test_app_bootstrap.py",
    "tests/runtime/test_runner.py",
    "tests/tools/test_executor.py",
]

def build_pytest_command(verbose: bool, quiet: bool, quick: bool) -> list[str]:
    cmd = [sys.executable, "-m", "pytest"]
    cmd.extend(QUICK_TESTS if quick else DEFAULT_TESTS)
    if quiet:
        cmd.append("-q")
    elif verbose:
        cmd.append("-vv")
    else:
        cmd.append("-q")
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the default harness-core test suite")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose pytest output")
    parser.add_argument("-q", "--quiet", action="store_true", help="quiet pytest output")
    parser.add_argument("--quick", action="store_true", help="run a smaller smoke suite")
    args = parser.parse_args()

    cmd = build_pytest_command(args.verbose, args.quiet, args.quick)
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
