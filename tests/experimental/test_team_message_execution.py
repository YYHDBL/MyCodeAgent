import time

from core.team_engine.manager import TeamManager


def _wait_succeeded(manager: TeamManager, team_name: str, expected: int, timeout_s: float = 3.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        snapshot = manager.collect_work(team_name)
        if int(snapshot.get("counts", {}).get("succeeded", 0) or 0) >= expected:
            return snapshot
        time.sleep(0.03)
    return manager.collect_work(team_name)


def _wait_shutdown_response(manager: TeamManager, team_name: str, request_id: str, timeout_s: float = 3.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = manager.get_status(team_name)
        recent = status.get("recent_messages", [])
        for row in recent:
            if row.get("type") == "shutdown_response" and row.get("request_id") == request_id:
                return row
        time.sleep(0.03)
    return {}


def test_message_creates_executable_work_item(tmp_path):
    manager = TeamManager(project_root=tmp_path, work_executor=lambda item: {"result": f"done:{item.get('instruction')}"})
    manager.create_team("demo", members=[{"name": "lead"}, {"name": "dev1"}])

    sent = manager.send_message(
        "demo",
        "lead",
        "dev1",
        "please run focused implementation",
        message_type="message",
        summary="impl request",
    )
    snapshot = _wait_succeeded(manager, "demo", expected=1, timeout_s=4.0)

    assert sent["status"] in {"pending", "delivered", "processed"}
    assert snapshot["counts"]["succeeded"] >= 1
    done = snapshot["groups"]["succeeded"][0]
    assert done["payload"]["source_message_id"] == sent["message_id"]
    assert done["payload"]["message_type"] == "message"


def test_broadcast_creates_work_items_for_each_teammate(tmp_path):
    manager = TeamManager(project_root=tmp_path, work_executor=lambda item: {"result": f"done:{item.get('owner')}"})
    manager.create_team("demo", members=[{"name": "lead"}, {"name": "dev1"}, {"name": "dev2"}])

    sent = manager.send_message(
        "demo",
        "lead",
        "all",
        "share your latest progress",
        message_type="broadcast",
        summary="status check",
    )
    snapshot = _wait_succeeded(manager, "demo", expected=2, timeout_s=4.0)

    assert sent["type"] == "broadcast"
    assert sent["recipient_count"] == 2
    assert snapshot["counts"]["succeeded"] >= 2
    source_ids = {row.get("payload", {}).get("source_message_id") for row in snapshot["groups"]["succeeded"]}
    assert set(sent["message_ids"]).issubset(source_ids)


def test_shutdown_request_produces_shutdown_response_with_same_request_id(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}, {"name": "dev1"}])

    sent = manager.send_message(
        "demo",
        "lead",
        "dev1",
        "please shutdown",
        message_type="shutdown_request",
        summary="shutdown",
    )
    row = _wait_shutdown_response(manager, "demo", sent["request_id"], timeout_s=4.0)

    assert sent["request_id"]
    assert row
    assert row["from"] == "dev1"
    assert row["to"] == "lead"
    assert row["request_id"] == sent["request_id"]
