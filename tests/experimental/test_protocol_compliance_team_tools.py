import json

from core.team_engine.manager import TeamManager
from tests.utils.protocol_validator import ProtocolValidator
from tools.builtin.send_message import SendMessageTool
from tools.builtin.team_create import TeamCreateTool


def test_team_create_protocol_compliance(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    tool = TeamCreateTool(project_root=tmp_path, team_manager=manager)
    response = tool.run({"team_name": "demo", "members": [{"name": "lead"}]})

    result = ProtocolValidator.validate(response)
    assert result.passed, f"protocol errors: {result.errors}"
    payload = json.loads(response)
    assert payload["status"] == "success"


def test_send_message_error_protocol_compliance(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    tool = SendMessageTool(project_root=tmp_path, team_manager=manager)
    response = tool.run({"team_name": "", "from_member": "lead", "to_member": "dev", "text": ""})

    result = ProtocolValidator.validate(response)
    assert result.passed, f"protocol errors: {result.errors}"
    payload = json.loads(response)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "INVALID_PARAM"
