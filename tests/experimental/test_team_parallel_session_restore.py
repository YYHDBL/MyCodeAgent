from core.team_engine.manager import TeamManager
from core.team_engine.protocol import WORK_ITEM_STATUS_QUEUED, WORK_ITEM_STATUS_RUNNING
from core.session_store import build_session_snapshot, load_session_snapshot, save_session_snapshot


def test_restore_requeues_running_work_items(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}, {"name": "dev1"}])

    dispatch = manager.fanout_work(
        "demo",
        tasks=[{"owner": "dev1", "title": "impl", "instruction": "do impl"}],
    )
    work_id = dispatch["work_items"][0]["work_id"]

    manager.store.update_work_item_status("demo", work_id=work_id, status=WORK_ITEM_STATUS_RUNNING)

    # Keep this test deterministic: verify requeue behavior without starting workers.
    manager._start_worker = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    manager.import_state(manager.export_state())

    items = manager.store.list_work_items("demo", owner="dev1")
    assert len(items) == 1
    assert items[0]["work_id"] == work_id
    assert items[0]["status"] == WORK_ITEM_STATUS_QUEUED
    assert items[0].get("started_at") in (None, "")


def test_snapshot_includes_parallel_work_index(tmp_path):
    snapshot = build_session_snapshot(
        system_messages=[],
        history_messages=[],
        tool_schema=[],
        project_root=str(tmp_path),
        teams_snapshot={"work_items": {"demo": {"queued": 1, "running": 0}}},
    )
    assert snapshot["parallel_work_index"]["demo"]["queued"] == 1

    path = tmp_path / "session.json"
    save_session_snapshot(path, {"version": 1, "system_messages": [], "history_messages": []})
    loaded = load_session_snapshot(path)
    assert loaded["parallel_work_index"] == {}
