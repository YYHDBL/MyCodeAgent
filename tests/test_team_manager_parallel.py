from core.team_engine.manager import TeamManager
from core.team_engine.protocol import EVENT_WORK_ITEM_ASSIGNED


def test_fanout_creates_work_items_and_assign_events(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev1")
    manager.spawn_teammate("demo", "dev2")

    result = manager.fanout_work(
        "demo",
        tasks=[
            {"owner": "dev1", "title": "impl", "instruction": "do impl"},
            {"owner": "dev2", "title": "test", "instruction": "do test"},
        ],
    )
    assert len(result["work_items"]) == 2
    events = manager.drain_events("demo")
    assigned = [e for e in events if e["type"] == EVENT_WORK_ITEM_ASSIGNED]
    assert len(assigned) == 2


def test_collect_work_returns_done_and_pending(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev1")

    result = manager.fanout_work(
        "demo",
        tasks=[
            {"owner": "dev1", "title": "impl", "instruction": "do impl"},
        ],
    )
    work_id = result["work_items"][0]["work_id"]
    manager.store.update_work_item_status("demo", work_id, "running")
    grouped = manager.collect_work("demo")

    assert grouped["counts"]["running"] >= 1
    assert grouped["total"] >= 1
