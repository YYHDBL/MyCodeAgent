from core.team_engine.manager import TeamManager


def test_team_task_board_crud(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}, {"name": "dev1"}])

    created = manager.create_board_task(
        "demo",
        subject="Analyze auth flow",
        description="Map key modules",
    )
    assert created["id"]
    assert created["status"] == "pending"
    assert created["blocked_by"] == []
    assert created["blocks"] == []

    fetched = manager.get_board_task("demo", created["id"])
    assert fetched["subject"] == "Analyze auth flow"

    listed = manager.list_board_tasks("demo")
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]

    updated = manager.update_board_task(
        "demo",
        task_id=created["id"],
        status="in_progress",
        owner="dev1",
    )
    assert updated["status"] == "in_progress"
    assert updated["owner"] == "dev1"
