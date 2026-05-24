import json
import time

from core.team_engine.manager import TeamManager
from tools.builtin.team_approve_plan import TeamApprovePlanTool
from tools.builtin.team_approvals import TeamApprovalsTool


def test_team_approvals_and_approve_plan_flow(tmp_path):
    manager = TeamManager(project_root=tmp_path, work_executor=lambda item: {"result": "done"})
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate(
        "demo",
        "dev1",
        tool_policy={"allowlist": [], "denylist": ["Task"], "require_plan_approval": True},
    )
    task = manager.create_board_task("demo", subject="Refactor auth", description="refactor")
    task_id = task["id"]

    list_tool = TeamApprovalsTool(project_root=tmp_path, team_manager=manager)
    approve_tool = TeamApprovePlanTool(project_root=tmp_path, team_manager=manager)

    request_id = ""
    for _ in range(60):
        listed = json.loads(list_tool.run({"team_name": "demo", "status": "pending"}))
        assert listed["status"] == "success"
        items = listed["data"]["items"]
        if items:
            request_id = items[0]["request_id"]
            break
        time.sleep(0.03)
    assert request_id

    approved = json.loads(
        approve_tool.run(
            {
                "team_name": "demo",
                "request_id": request_id,
                "approved": True,
                "feedback": "looks good",
            }
        )
    )
    assert approved["status"] == "success"
    assert approved["data"]["request_id"] == request_id

    done = False
    for _ in range(80):
        row = manager.get_board_task("demo", task_id)
        if row["status"] == "completed":
            done = True
            break
        time.sleep(0.03)
    assert done


def test_team_approve_plan_requires_request_id(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    tool = TeamApprovePlanTool(project_root=tmp_path, team_manager=manager)

    result = json.loads(tool.run({"team_name": "demo", "request_id": "", "approved": True}))
    assert result["status"] == "error"
    assert result["error"]["code"] == "INVALID_PARAM"
