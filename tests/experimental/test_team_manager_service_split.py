from unittest.mock import patch

from core.team_engine.manager import TeamManager


def _prepare_manager(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev")
    return manager


def test_manager_initializes_split_services(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    assert manager.message_router is not None
    assert manager.task_board_service is not None
    assert manager.worker_supervisor is not None
    assert manager.approval_service is not None
    assert manager.execution_service is not None


def test_send_message_delegates_to_message_router(tmp_path):
    manager = _prepare_manager(tmp_path)
    fake = {
        "message_id": "msg_1",
        "message_ids": ["msg_1"],
        "status": "delivered",
        "type": "message",
        "request_id": "",
        "summary": "ping",
        "approved": None,
        "feedback": "",
    }
    with patch.object(manager.message_router, "send_message", return_value=fake) as mocked:
        result = manager.send_message("demo", "lead", "dev", "ping", summary="ping")
    assert result["message_id"] == "msg_1"
    mocked.assert_called_once()


def test_task_board_calls_delegate_to_service(tmp_path):
    manager = _prepare_manager(tmp_path)
    with patch.object(manager.task_board_service, "create_task", return_value={"id": "task_1"}) as mocked:
        created = manager.create_board_task("demo", subject="S", description="D")
    assert created["id"] == "task_1"
    mocked.assert_called_once()


def test_plan_approval_list_delegates_to_service(tmp_path):
    manager = _prepare_manager(tmp_path)
    with patch.object(manager.approval_service, "list_requests", return_value=[{"request_id": "r1"}]) as mocked:
        rows = manager.list_plan_approvals("demo")
    assert rows == [{"request_id": "r1"}]
    mocked.assert_called_once_with("demo", status=None)


def test_has_worker_delegates_to_supervisor(tmp_path):
    manager = _prepare_manager(tmp_path)
    with patch.object(manager.worker_supervisor, "has_worker", return_value=True) as mocked:
        assert manager.has_worker("demo", "dev") is True
    mocked.assert_called_once_with("demo", "dev")
