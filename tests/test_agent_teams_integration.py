import json
import time

from core.team_engine.manager import TeamManager
from tools.builtin.send_message import SendMessageTool
from tools.builtin.team_create import TeamCreateTool
from tools.builtin.team_delete import TeamDeleteTool
from tools.builtin.team_status import TeamStatusTool


def test_end_to_end_team_message_flow(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    team_create = TeamCreateTool(project_root=tmp_path, team_manager=manager)
    send = SendMessageTool(project_root=tmp_path, team_manager=manager)
    status = TeamStatusTool(project_root=tmp_path, team_manager=manager)
    delete = TeamDeleteTool(project_root=tmp_path, team_manager=manager)

    created = json.loads(team_create.run({"team_name": "demo", "members": [{"name": "lead"}]}))
    assert created["status"] == "success"
    manager.spawn_teammate("demo", "dev")

    sent = json.loads(
        send.run(
            {
                "team_name": "demo",
                "from_member": "lead",
                "to_member": "dev",
                "text": "ping",
                "summary": "ping dev",
            }
        )
    )
    assert sent["status"] == "success"
    assert sent["data"]["status"] in {"pending", "delivered", "processed"}

    processed = False
    for _ in range(30):
        payload = json.loads(status.run({"team_name": "demo"}))
        processed_count = payload["data"]["message_counts"]["processed"]
        if processed_count >= 1:
            processed = True
            break
        time.sleep(0.03)
    assert processed

    deleted = json.loads(delete.run({"team_name": "demo"}))
    assert deleted["status"] == "success"


def test_restore_after_snapshot_does_not_duplicate_worker(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev")
    snapshot = manager.export_state()

    manager.import_state(snapshot)
    manager.import_state(snapshot)
    assert manager.has_worker("demo", "dev")
    assert len([key for key in manager._workers if key == ("demo", "dev")]) == 1
