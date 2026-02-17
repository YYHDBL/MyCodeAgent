from core.team_engine.manager import TeamManager


def test_completed_task_unblocks_dependents(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}, {"name": "dev1"}, {"name": "dev2"}])

    task1 = manager.create_board_task("demo", subject="Design schema")
    task2 = manager.create_board_task("demo", subject="Implement resolver", blocked_by=[task1["id"]])

    claimed = manager.claim_next_board_task("demo", owner="dev1")
    assert claimed["id"] == task1["id"]

    manager.update_board_task("demo", task_id=task1["id"], status="completed")
    resolved = manager.get_board_task("demo", task2["id"])
    assert resolved["blocked_by"] == []
