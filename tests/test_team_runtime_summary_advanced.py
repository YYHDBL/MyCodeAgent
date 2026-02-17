import time

from agents.codeAgent import CodeAgent
from core.team_engine.manager import TeamManager


def test_runtime_block_includes_idle_approvals_and_blocked_tasks():
    events = [
        {
            "team": "demo",
            "type": "message_sent",
            "payload": {"message_id": "m1", "status": "delivered"},
        },
        {
            "team": "demo",
            "type": "message_sent",
            "payload": {"message_id": "m1", "status": "delivered"},
        },
    ]
    runtime_state = {
        "teams": {
            "demo": {
                "last_error": "",
                "active_teammates": ["dev3"],
                "idle_teammates": ["dev1", "dev2"],
            }
        },
        "work_items": {
            "demo": {
                "queued": 1,
                "running": 0,
                "succeeded": 2,
                "failed": 0,
                "canceled": 0,
            }
        },
        "approvals": {
            "demo": {"pending": 2, "approved": 1, "rejected": 0}
        },
        "task_board": {
            "demo": {"blocked": 3, "pending": 4, "in_progress": 1, "total": 6}
        },
    }

    blocks = CodeAgent._format_runtime_system_blocks(events=events, runtime_state=runtime_state, max_lines=20)

    assert blocks
    block = blocks[0]
    assert "demo teammates active=1 idle=2" in block
    assert "demo approvals pending=2 approved=1 rejected=0" in block
    assert "demo tasks blocked=3 pending=4 in_progress=1" in block
    # duplicate events should be compacted
    assert block.count("message=m1 status=delivered") == 1


def test_export_state_contains_task_board_and_worker_state(tmp_path):
    manager = TeamManager(project_root=tmp_path, work_executor=lambda item: {"result": "done"})
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate(
        "demo",
        "dev1",
        tool_policy={"allowlist": [], "denylist": ["Task"], "require_plan_approval": True},
    )

    root = manager.create_board_task("demo", subject="Root", description="root")
    manager.create_board_task("demo", subject="Child", description="child", blocked_by=[root["id"]])

    pending_req = False
    for _ in range(60):
        if manager.list_plan_approvals("demo", status="pending"):
            pending_req = True
            break
        time.sleep(0.03)
    assert pending_req

    state = manager.export_state()

    demo_team = state["teams"]["demo"]
    assert "active_teammates" in demo_team
    assert "idle_teammates" in demo_team

    assert state["approvals"]["demo"]["pending"] >= 1
    assert state["task_board"]["demo"]["blocked"] >= 1
