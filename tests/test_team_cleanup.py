import json
import time

from core.team_engine.manager import TeamManager
from tools.builtin.send_message import SendMessageTool
from tools.builtin.team_cleanup import TeamCleanupTool


def test_team_cleanup_conflicts_when_workers_active(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev1")
    tool = TeamCleanupTool(project_root=tmp_path, team_manager=manager)

    result = json.loads(tool.run({"team_name": "demo"}))
    assert result["status"] == "error"
    assert result["error"]["code"] == "CONFLICT"


def test_team_cleanup_after_shutdown_request(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev1")
    sender = SendMessageTool(project_root=tmp_path, team_manager=manager)
    cleanup = TeamCleanupTool(project_root=tmp_path, team_manager=manager)

    sent = json.loads(
        sender.run(
            {
                "team_name": "demo",
                "from_member": "lead",
                "to_member": "dev1",
                "type": "shutdown_request",
                "summary": "shutdown",
                "text": "Please stop",
            }
        )
    )
    assert sent["status"] == "success"

    stopped = False
    for _ in range(40):
        if not manager.has_worker("demo", "dev1"):
            stopped = True
            break
        time.sleep(0.03)
    assert stopped

    result = json.loads(cleanup.run({"team_name": "demo"}))
    assert result["status"] == "success"
