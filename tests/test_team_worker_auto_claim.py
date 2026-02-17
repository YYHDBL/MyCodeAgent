import time

from core.team_engine.manager import TeamManager


def test_worker_auto_claims_and_completes_board_task(tmp_path):
    manager = TeamManager(project_root=tmp_path, work_executor=lambda item: {"result": f"ok:{item.get('work_id')}"})
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev1")

    task = manager.create_board_task("demo", subject="Analyze modules", description="inspect code")
    task_id = task["id"]

    done = False
    latest = None
    for _ in range(80):
        latest = manager.get_board_task("demo", task_id)
        if latest["status"] == "completed":
            done = True
            break
        time.sleep(0.03)

    assert done
    assert latest["owner"] == "dev1"


def test_worker_wakes_up_to_claim_new_board_task(tmp_path):
    manager = TeamManager(project_root=tmp_path, work_executor=lambda item: {"result": "done"})
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev1")

    # Let worker run through idle poll cycles, then push a new task.
    time.sleep(0.12)
    task = manager.create_board_task("demo", subject="Late task", description="late")
    task_id = task["id"]

    done = False
    for _ in range(80):
        row = manager.get_board_task("demo", task_id)
        if row["status"] == "completed":
            done = True
            break
        time.sleep(0.03)
    assert done
