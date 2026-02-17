from core.team_engine.manager import TeamManager


class DummyTmuxOrchestrator:
    def __init__(self):
        self.calls = []

    def ensure_session(self, team_name: str):
        self.calls.append(("ensure_session", team_name))

    def ensure_teammate_window(self, team_name: str, teammate_name: str):
        self.calls.append(("ensure_teammate_window", team_name, teammate_name))

    def cleanup_session(self, team_name: str):
        self.calls.append(("cleanup_session", team_name))


def test_tmux_mode_orchestrates_team_lifecycle(tmp_path):
    orchestrator = DummyTmuxOrchestrator()
    manager = TeamManager(
        project_root=tmp_path,
        teammate_runtime_mode="tmux",
        tmux_orchestrator=orchestrator,
    )

    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev1")
    manager.delete_team("demo")

    assert ("ensure_session", "demo") in orchestrator.calls
    assert ("ensure_teammate_window", "demo", "dev1") in orchestrator.calls
    assert ("cleanup_session", "demo") in orchestrator.calls


def test_in_process_mode_does_not_call_tmux_orchestrator(tmp_path):
    orchestrator = DummyTmuxOrchestrator()
    manager = TeamManager(
        project_root=tmp_path,
        teammate_runtime_mode="in-process",
        tmux_orchestrator=orchestrator,
    )

    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev1")

    assert orchestrator.calls == []
