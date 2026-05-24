import json

from core.session_store import build_session_snapshot, load_session_snapshot, save_session_snapshot
from core.team_engine.manager import TeamManager


def test_snapshot_includes_team_fields(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev")

    snapshot = build_session_snapshot(
        system_messages=[],
        history_messages=[],
        tool_schema=[],
        project_root=str(tmp_path),
        teams_snapshot=manager.export_state(),
        team_store_dir=".teams",
        task_store_dir=".tasks",
        schema_version=1,
    )
    assert snapshot["schema_version"] == 1
    assert "teams_snapshot" in snapshot
    assert snapshot["team_store_dir"] == ".teams"
    assert snapshot["task_store_dir"] == ".tasks"


def test_restore_does_not_spawn_duplicate_workers(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev")

    state = manager.export_state()
    manager.import_state(state)
    manager.import_state(state)
    assert manager.has_worker("demo", "dev")

    # TeamManager keeps one worker handle per (team, teammate)
    assert len([k for k in manager._workers.keys() if k == ("demo", "dev")]) == 1


def test_snapshot_backward_compatibility_defaults(tmp_path):
    path = tmp_path / "session.json"
    save_session_snapshot(path, {"version": 1, "system_messages": [], "history_messages": []})
    loaded = load_session_snapshot(path)
    assert loaded.get("teams_snapshot", {}) == {}
