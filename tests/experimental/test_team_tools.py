import json

from core.team_engine.manager import TeamManager
from tools.builtin.send_message import SendMessageTool
from tools.builtin.team_create import TeamCreateTool
from tools.builtin.team_delete import TeamDeleteTool
from tools.builtin.team_status import TeamStatusTool


def test_team_create_tool_protocol(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    tool = TeamCreateTool(project_root=tmp_path, team_manager=manager)

    result = json.loads(tool.run({"team_name": "demo", "members": [{"name": "lead"}]}))
    assert result["status"] == "success"
    assert result["data"]["team_name"] == "demo"
    assert result["data"]["members"][0]["role"]
    assert isinstance(result["data"]["members"][0]["tool_policy"], dict)


def test_send_message_tool_returns_ack_status(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev")
    tool = SendMessageTool(project_root=tmp_path, team_manager=manager)

    result = json.loads(
        tool.run(
            {
                "team_name": "demo",
                "from_member": "lead",
                "to_member": "dev",
                "text": "ping",
                "summary": "ping dev",
            }
        )
    )
    assert result["status"] == "success"
    assert result["data"]["message_id"]
    assert result["data"]["status"] in {"pending", "delivered", "processed"}


def test_send_message_tool_supports_broadcast(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}, {"name": "dev1"}, {"name": "dev2"}])
    tool = SendMessageTool(project_root=tmp_path, team_manager=manager)

    result = json.loads(
        tool.run(
            {
                "team_name": "demo",
                "from_member": "lead",
                "to_member": "all",
                "text": "Heads up",
                "type": "broadcast",
                "summary": "status update",
            }
        )
    )
    assert result["status"] == "success"
    assert result["data"]["type"] == "broadcast"
    assert result["data"]["recipient_count"] == 2


def test_send_message_tool_requires_summary_for_broadcast(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}, {"name": "dev1"}])
    tool = SendMessageTool(project_root=tmp_path, team_manager=manager)

    result = json.loads(
        tool.run(
            {
                "team_name": "demo",
                "from_member": "lead",
                "to_member": "all",
                "text": "Heads up",
                "type": "broadcast",
            }
        )
    )
    assert result["status"] == "error"
    assert result["error"]["code"] == "INVALID_PARAM"


def test_team_status_tool_aggregates_message_counts(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev")
    sent = manager.send_message("demo", "lead", "dev", "ping", summary="ping dev")
    manager.mark_message_processed("demo", sent["message_id"], processed_by="dev")
    tool = TeamStatusTool(project_root=tmp_path, team_manager=manager)

    result = json.loads(tool.run({"team_name": "demo"}))
    assert result["status"] == "success"
    assert result["data"]["message_counts"]["processed"] >= 1


def test_team_delete_tool_success_and_error_shape(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    tool = TeamDeleteTool(project_root=tmp_path, team_manager=manager)

    ok = json.loads(tool.run({"team_name": "demo"}))
    assert ok["status"] == "success"

    err = json.loads(tool.run({"team_name": "missing"}))
    assert err["status"] == "error"
    assert err["error"]["code"]
    assert err["error"]["message"]
