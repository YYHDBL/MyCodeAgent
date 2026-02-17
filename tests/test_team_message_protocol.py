import pytest

from core.team_engine.manager import TeamManager, TeamManagerError


def test_send_message_supports_broadcast(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}, {"name": "dev1"}, {"name": "dev2"}])

    sent = manager.send_message(
        "demo",
        "lead",
        "all",
        "Heads up",
        message_type="broadcast",
        summary="status update",
    )

    assert sent["status"] == "delivered"
    assert sent["type"] == "broadcast"
    assert sent["recipient_count"] == 2
    assert sent["request_id"] == ""
    assert sent["summary"] == "status update"

    inbox_dev1 = manager.store.read_inbox_messages("demo", "dev1")
    inbox_dev2 = manager.store.read_inbox_messages("demo", "dev2")
    assert len(inbox_dev1) == 1
    assert len(inbox_dev2) == 1
    assert inbox_dev1[0]["type"] == "broadcast"
    assert inbox_dev2[0]["type"] == "broadcast"


def test_send_message_requires_summary_for_broadcast(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}, {"name": "dev1"}, {"name": "dev2"}])

    with pytest.raises(TeamManagerError) as exc:
        manager.send_message(
            "demo",
            "lead",
            "all",
            "Ping",
            message_type="broadcast",
            summary="",
        )
    assert exc.value.code == "INVALID_PARAM"
    assert "summary" in exc.value.message


def test_shutdown_request_sets_request_id(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}, {"name": "dev1"}])

    sent = manager.send_message(
        "demo",
        "lead",
        "dev1",
        "Please shut down",
        message_type="shutdown_request",
        summary="shutdown now",
    )
    assert sent["type"] == "shutdown_request"
    assert sent["request_id"]

    inbox_dev1 = manager.store.read_inbox_messages("demo", "dev1")
    assert len(inbox_dev1) == 1
    assert inbox_dev1[0]["type"] == "shutdown_request"
    assert inbox_dev1[0]["request_id"] == sent["request_id"]


def test_plan_approval_response_requires_request_id(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}, {"name": "dev1"}])

    with pytest.raises(TeamManagerError) as exc:
        manager.send_message(
            "demo",
            "lead",
            "dev1",
            "approved",
            message_type="plan_approval_response",
            summary="plan approved",
        )
    assert exc.value.code == "INVALID_PARAM"
    assert "request_id" in exc.value.message
