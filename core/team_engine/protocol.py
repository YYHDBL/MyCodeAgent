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

