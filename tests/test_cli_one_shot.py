"""Contract tests for scriptable one-shot CLI execution."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest


class _FakeTrace:
    session_id = "session-123"
    _total_usage = {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}

    def get_current_run_events(self):
        return [
            {
                "event": "terminal",
                "payload": {
                    "reason": "completed",
                    "details": {"completion_verdict": "pass"},
                },
            }
        ]


class _FakeAgent:
    def __init__(self):
        self.trace_logger = _FakeTrace()
        self.calls: list[tuple[str, bool]] = []
        self.closed = False

    def run(self, prompt: str, *, show_raw: bool = False) -> str:
        self.calls.append((prompt, show_raw))
        return "implemented the requested change"

    def close(self) -> None:
        self.closed = True


def _one_shot_args(*, json_output: bool = False) -> Namespace:
    return Namespace(print_prompt="implement it", json=json_output, show_raw=False)


def test_parser_accepts_one_shot_text_and_json_flags():
    from app.cli import build_parser

    args = build_parser().parse_args(["-p", "implement it", "--json"])

    assert args.print_prompt == "implement it"
    assert args.json is True


def test_one_shot_text_uses_the_supplied_runtime_and_agent_once(capsys):
    from app.cli import run_one_shot

    agent = _FakeAgent()
    runtime = SimpleNamespace(agent=agent)

    exit_code = run_one_shot(_one_shot_args(), runtime)

    assert exit_code == 0
    assert agent.calls == [("implement it", False)]
    assert agent.closed is True
    assert capsys.readouterr().out == "implemented the requested change\n"


def test_one_shot_json_writes_one_machine_readable_outcome(capsys):
    from app.cli import run_one_shot

    agent = _FakeAgent()
    runtime = SimpleNamespace(agent=agent)

    exit_code = run_one_shot(_one_shot_args(json_output=True), runtime)

    assert exit_code == 0
    assert agent.calls == [("implement it", False)]
    assert agent.closed is True
    assert json.loads(capsys.readouterr().out) == {
        "status": "success",
        "response": "implemented the requested change",
        "session_id": "session-123",
        "terminal_reason": "completed",
        "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
        "verification": {"completion_verdict": "pass"},
    }


def test_one_shot_captures_json_metadata_before_closing_the_runtime(capsys):
    from app.cli import run_one_shot

    class ClosingAgent(_FakeAgent):
        def close(self) -> None:
            self.trace_logger = None
            self.closed = True

    agent = ClosingAgent()
    runtime = SimpleNamespace(agent=agent)

    assert run_one_shot(_one_shot_args(json_output=True), runtime) == 0

    outcome = json.loads(capsys.readouterr().out)
    assert outcome["session_id"] == "session-123"
    assert outcome["usage"]["total_tokens"] == 8


def test_one_shot_maps_runtime_failure_to_exit_one_without_rich_stdout(capsys):
    from app.cli import run_one_shot

    class FailedTrace(_FakeTrace):
        def get_current_run_events(self):
            return [{"event": "terminal", "payload": {"reason": "model_error", "details": {}}}]

    agent = _FakeAgent()
    agent.trace_logger = FailedTrace()
    runtime = SimpleNamespace(agent=agent)

    exit_code = run_one_shot(_one_shot_args(json_output=True), runtime)

    assert exit_code == 1
    outcome = json.loads(capsys.readouterr().out)
    assert outcome["status"] == "failure"
    assert outcome["terminal_reason"] == "model_error"


def test_one_shot_maps_keyboard_interrupt_to_exit_130(capsys):
    from app.cli import run_one_shot

    class InterruptedAgent(_FakeAgent):
        def run(self, prompt: str, *, show_raw: bool = False) -> str:
            raise KeyboardInterrupt

    agent = InterruptedAgent()
    runtime = SimpleNamespace(agent=agent)

    exit_code = run_one_shot(_one_shot_args(json_output=True), runtime)

    assert exit_code == 130
    assert agent.closed is True
    assert json.loads(capsys.readouterr().out) == {
        "status": "interrupted",
        "response": "",
        "session_id": "session-123",
        "terminal_reason": "interrupted",
        "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
    }


def test_main_builds_the_runtime_once_then_runs_one_shot_once(monkeypatch, capsys):
    import app.cli as cli

    agent = _FakeAgent()
    runtime = SimpleNamespace(agent=agent)
    build_calls = []

    monkeypatch.setattr(cli, "build_parser", lambda: SimpleNamespace(parse_args=lambda: _one_shot_args()))
    monkeypatch.setattr(cli, "build_runtime", lambda *args, **kwargs: build_calls.append((args, kwargs)) or runtime)

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 0
    assert len(build_calls) == 1
    assert agent.calls == [("implement it", False)]
    assert capsys.readouterr().out == "implemented the requested change\n"


def test_main_returns_json_exit_two_for_invalid_one_shot_configuration(monkeypatch, capsys):
    import app.cli as cli

    args = _one_shot_args(json_output=True)
    monkeypatch.setattr(cli, "build_parser", lambda: SimpleNamespace(parse_args=lambda: args))
    monkeypatch.setattr(cli, "build_runtime", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad config")))

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "invalid_input",
        "response": "",
        "session_id": None,
        "terminal_reason": "invalid_configuration",
        "error": "bad config",
    }


def test_main_py_one_shot_json_is_clean_in_a_subprocess(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    fake_runtime_dir = tmp_path / "fake-runtime"
    fake_runtime_dir.mkdir()
    (fake_runtime_dir / "sitecustomize.py").write_text(
        """
from types import SimpleNamespace
import app.cli

class Trace:
    session_id = "subprocess-session"
    _total_usage = {"total_tokens": 13}
    def get_current_run_events(self):
        return [{"event": "terminal", "payload": {"reason": "completed", "details": {}}}]

class Agent:
    trace_logger = Trace()
    def run(self, prompt, *, show_raw=False):
        return "subprocess final answer"
    def close(self):
        self.trace_logger = None

app.cli.build_runtime = lambda *args, **kwargs: SimpleNamespace(agent=Agent())
""",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join([str(fake_runtime_dir), str(project_root)])

    completed = subprocess.run(
        [sys.executable, str(project_root / "main.py"), "-p", "task", "--json"],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == {
        "status": "success",
        "response": "subprocess final answer",
        "session_id": "subprocess-session",
        "terminal_reason": "completed",
        "usage": {"total_tokens": 13},
    }
