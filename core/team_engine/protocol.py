"""Protocol constants for AgentTeams MVP."""

from __future__ import annotations

import re


TEAM_CONFIG_VERSION = 1

MESSAGE_STATUS_PENDING = "pending"
MESSAGE_STATUS_DELIVERED = "delivered"
MESSAGE_STATUS_PROCESSED = "processed"
MESSAGE_STATUSES = {
    MESSAGE_STATUS_PENDING,
    MESSAGE_STATUS_DELIVERED,
    MESSAGE_STATUS_PROCESSED,
}

EVENT_MESSAGE_ACK = "message_ack"
EVENT_MESSAGE_SENT = "message_sent"
EVENT_SHUTDOWN_REQUEST = "shutdown_request"
EVENT_WORK_ITEM_ASSIGNED = "work_item_assigned"
EVENT_WORK_ITEM_STARTED = "work_item_started"
EVENT_WORK_ITEM_COMPLETED = "work_item_completed"
EVENT_WORK_ITEM_FAILED = "work_item_failed"

EVENT_TYPES = {
    EVENT_MESSAGE_ACK,
    EVENT_MESSAGE_SENT,
    EVENT_SHUTDOWN_REQUEST,
    EVENT_WORK_ITEM_ASSIGNED,
    EVENT_WORK_ITEM_STARTED,
    EVENT_WORK_ITEM_COMPLETED,
    EVENT_WORK_ITEM_FAILED,
}

WORK_ITEM_STATUS_QUEUED = "queued"
WORK_ITEM_STATUS_RUNNING = "running"
WORK_ITEM_STATUS_SUCCEEDED = "succeeded"
WORK_ITEM_STATUS_FAILED = "failed"
WORK_ITEM_STATUS_CANCELED = "canceled"
WORK_ITEM_STATUSES = {
    WORK_ITEM_STATUS_QUEUED,
    WORK_ITEM_STATUS_RUNNING,
    WORK_ITEM_STATUS_SUCCEEDED,
    WORK_ITEM_STATUS_FAILED,
    WORK_ITEM_STATUS_CANCELED,
}

_SANITIZE_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_name(raw: str) -> str:
    value = (raw or "").strip()
    value = _SANITIZE_PATTERN.sub("-", value)
    value = value.strip("-._")
    if not value:
        raise ValueError("name is empty after sanitization")
    return value


def normalize_member(member: dict) -> dict:
    name = sanitize_name(str(member.get("name", "")))
    role = str(member.get("role") or "developer")
    tool_policy = member.get("tool_policy")
    if not isinstance(tool_policy, dict):
        tool_policy = {
            "allowlist": [],
            "denylist": ["Task"],
        }
    tool_policy.setdefault("allowlist", [])
    tool_policy.setdefault("denylist", ["Task"])
    return {
        "name": name,
        "role": role,
        "tool_policy": tool_policy,
    }


def validate_work_item_shape(item: dict) -> None:
    """Validate minimal required work-item fields."""
    if not isinstance(item, dict):
        raise ValueError("work item must be a dict")
    for key in ("work_id", "title", "instruction"):
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"work item missing required field: {key}")
