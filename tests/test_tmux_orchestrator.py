from core.team_engine.tmux_orchestrator import TmuxOrchestrator


class DummyRunner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        if self.responses:
            return self.responses.pop(0)
        return 0, ""


def test_ensure_session_creates_when_missing():
    runner = DummyRunner(
        responses=[
            (1, ""),  # has-session fail
            (0, ""),  # new-session ok
        ]
    )
    orch = TmuxOrchestrator(command_runner=runner)

    orch.ensure_session("demo")

    assert runner.calls[0][:3] == ["tmux", "has-session", "-t"]
    assert runner.calls[1][:3] == ["tmux", "new-session", "-d"]


def test_ensure_teammate_window_skips_existing_window():
    runner = DummyRunner(
        responses=[
            (0, "lead\ndev1\n"),
        ]
    )
    orch = TmuxOrchestrator(command_runner=runner)

    orch.ensure_teammate_window("demo", "dev1")

    assert len(runner.calls) == 1
    assert runner.calls[0][:3] == ["tmux", "list-windows", "-t"]


def test_cleanup_session_ignores_missing_session():
    runner = DummyRunner(
        responses=[
            (1, ""),
        ]
    )
    orch = TmuxOrchestrator(command_runner=runner)

    orch.cleanup_session("demo")

    assert runner.calls[0][:3] == ["tmux", "kill-session", "-t"]
