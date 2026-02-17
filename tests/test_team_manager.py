import pytest

from core.team_engine.manager import TeamManager, TeamManagerError
from core.team_engine.protocol import (
    MESSAGE_STATUS_DELIVERED,
    MESSAGE_STATUS_PROCESSED,
)


def test_send_message_pushes_event(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "observer")

    message = manager.send_message("demo", "lead", "observer", "ping")
    assert message["message_id"]
    assert message["status"] in {MESSAGE_STATUS_DELIVERED}

    events = manager.drain_events(team_name="demo")
    assert events
    assert any(event["team"] == "demo" for event in events)


def test_duplicate_member_name_returns_error(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev")

    with pytest.raises(TeamManagerError) as exc:
        manager.spawn_teammate("demo", "dev")
    assert exc.value.code == "INVALID_PARAM"


def test_message_ack_flow_to_processed(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev")

    sent = manager.send_message("demo", "lead", "dev", "do it")
    manager.mark_message_processed("demo", sent["message_id"], processed_by="dev")

    status = manager.get_status("demo")
    assert status["message_counts"][MESSAGE_STATUS_DELIVERED] == 0
    assert status["message_counts"][MESSAGE_STATUS_PROCESSED] == 1
