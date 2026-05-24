from core.team_engine.protocol import (
    EVENT_TYPES,
    EVENT_WORK_ITEM_ASSIGNED,
    EVENT_WORK_ITEM_COMPLETED,
    WORK_ITEM_STATUS_FAILED,
    WORK_ITEM_STATUS_QUEUED,
    WORK_ITEM_STATUS_RUNNING,
    WORK_ITEM_STATUS_SUCCEEDED,
)


def test_parallel_work_item_status_constants():
    assert WORK_ITEM_STATUS_QUEUED == "queued"
    assert WORK_ITEM_STATUS_RUNNING == "running"
    assert WORK_ITEM_STATUS_SUCCEEDED == "succeeded"
    assert WORK_ITEM_STATUS_FAILED == "failed"


def test_message_types_include_work_item():
    assert EVENT_WORK_ITEM_ASSIGNED in EVENT_TYPES
    assert EVENT_WORK_ITEM_COMPLETED in EVENT_TYPES
