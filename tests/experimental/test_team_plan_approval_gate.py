import time

from core.team_engine.manager import TeamManager


def test_plan_required_teammate_waits_for_approval(tmp_path):
    manager = TeamManager(project_root=tmp_path, work_executor=lambda item: {"result": "done"})
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate(
        "demo",
        "dev1",
        tool_policy={"allowlist": [], "denylist": ["Task"], "require_plan_approval": True},
    )
    task = manager.create_board_task("demo", subject="Refactor auth", description="refactor")
    task_id = task["id"]

    pending_req = None
    for _ in range(60):
        approvals = manager.list_plan_approvals("demo", status="pending")
        if approvals:
            pending_req = approvals[0]
            break
        time.sleep(0.03)

    assert pending_req is not None
    assert pending_req["task_id"] == task_id
    assert pending_req["teammate"] == "dev1"

    # Before approval, task should not complete and no work item should finish.
    snapshot = manager.collect_work("demo")
    assert snapshot["counts"]["succeeded"] == 0
    board = manager.get_board_task("demo", task_id)
    assert board["status"] == "in_progress"


def test_plan_approval_response_unblocks_execution(tmp_path):
    manager = TeamManager(project_root=tmp_path, work_executor=lambda item: {"result": "done"})
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate(
        "demo",
        "dev1",
        tool_policy={"allowlist": [], "denylist": ["Task"], "require_plan_approval": True},
    )
    task = manager.create_board_task("demo", subject="Refactor auth", description="refactor")
    task_id = task["id"]

    request_id = ""
    for _ in range(60):
        approvals = manager.list_plan_approvals("demo", status="pending")
        if approvals:
            request_id = approvals[0]["request_id"]
            break
        time.sleep(0.03)
    assert request_id

    manager.send_message(
        "demo",
        "lead",
        "dev1",
        "approved",
        message_type="plan_approval_response",
        request_id=request_id,
        approved=True,
        feedback="go ahead",
    )

    done = False
    for _ in range(80):
        board = manager.get_board_task("demo", task_id)
        if board["status"] == "completed":
            done = True
            break
        time.sleep(0.03)
    assert done
