"""Contracts for interactive session lifecycle controls."""

from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace

import pytest


class _Console:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def print(self, value, *args, **kwargs) -> None:
        self.lines.append(str(value))


class _LifecycleAgent:
    def __init__(self) -> None:
        self.status_calls = 0
        self.resume_calls: list[str | None] = []
        self.cancel_calls = 0

    def get_session_status(self):
        self.status_calls += 1
        return {
            "project_root": "/tmp/project",
            "model": "fake-model",
            "provider": "fake-provider",
            "session_id": "session-active",
            "permission_mode": "main_agent",
            "extensions": {"mcp": False, "skills": True},
            "context_usage": {"messages": 3},
        }

    def list_transcript_sessions(self):
        return [
            SimpleNamespace(session_id="session-new", latest_run_id="run-4"),
            SimpleNamespace(session_id="session-old", latest_run_id="run-1"),
        ]

    def resume_transcript(self, session_id=None):
        self.resume_calls.append(session_id)
        return SimpleNamespace(
            session_id=session_id or "session-new",
            run_id="run-4",
            uncertain_actions=[SimpleNamespace(tool_name="Edit", tool_call_id="call-7")],
        )

    def run(self, prompt: str, *, show_raw: bool = False) -> str:
        raise KeyboardInterrupt

    def cancel_active_turn(self):
        self.cancel_calls += 1
        return {"cancelled": True, "run_id": "run-4"}


def test_parser_accepts_optional_resume_session_id():
    from app.cli import build_parser

    assert build_parser().parse_args(["--resume", "session-9"]).resume == "session-9"
    assert build_parser().parse_args(["--resume"]).resume == ""


def test_lifecycle_commands_render_public_host_data(monkeypatch):
    import app.cli as cli

    output = _Console()
    monkeypatch.setattr(cli, "console", output)
    agent = _LifecycleAgent()

    assert cli.handle_lifecycle_command(agent, "/status") is True
    assert cli.handle_lifecycle_command(agent, "/sessions") is True
    assert cli.handle_lifecycle_command(agent, "/resume session-old") is True

    rendered = "\n".join(output.lines)
    assert agent.status_calls == 1
    assert agent.resume_calls == ["session-old"]
    assert "/tmp/project" in rendered
    assert "session-new" in rendered
    assert "session-old" in rendered
    assert "call-7" in rendered


def test_keyboard_interrupt_cancels_only_the_active_turn_and_returns_to_prompt(monkeypatch):
    import app.cli as cli

    output = _Console()
    monkeypatch.setattr(cli, "console", output)
    agent = _LifecycleAgent()

    outcome = cli.run_interactive_turn(agent, "make a change", show_raw=False)

    assert outcome.cancelled is True
    assert outcome.response is None
    assert agent.cancel_calls == 1
    assert "cancelled" in "\n".join(output.lines).lower()


def test_main_resumes_before_running_a_one_shot_turn(monkeypatch, capsys):
    import app.cli as cli

    class _OneShotAgent(_LifecycleAgent):
        def __init__(self) -> None:
            super().__init__()
            self.closed = False

        def run(self, prompt: str, *, show_raw: bool = False) -> str:
            return "continued"

        def close(self) -> None:
            self.closed = True

    args = Namespace(
        print_prompt="continue",
        json=False,
        show_raw=False,
        resume="session-old",
    )
    agent = _OneShotAgent()
    runtime = SimpleNamespace(agent=agent)
    monkeypatch.setattr(cli, "build_parser", lambda: SimpleNamespace(parse_args=lambda: args))
    monkeypatch.setattr(cli, "build_runtime", lambda *_args, **_kwargs: runtime)

    with pytest.raises(SystemExit) as result:
        cli.main()

    assert result.value.code == 0
    assert agent.resume_calls == ["session-old"]
    assert agent.closed is True
    assert capsys.readouterr().out == "continued\n"
