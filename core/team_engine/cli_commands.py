"""CLI command parsing helpers for team operations."""

from __future__ import annotations

import re
from typing import Dict

TEAM_MSG_USAGE = "Usage: /team msg <team_name> <teammate_name> <summary :: message | message>"
DELEGATE_USAGE = "Usage: /delegate <on|off|status>"


def _build_summary(text: str, limit: int = 80) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized[:limit]


def parse_team_message_command(command: str, from_member: str) -> Dict[str, str]:
    raw = (command or "").strip()
    if not raw.lower().startswith("/team msg "):
        raise ValueError(TEAM_MSG_USAGE)

    if not isinstance(from_member, str) or not from_member.strip():
        raise ValueError("from_member must be a non-empty string")

    rest = raw[len("/team msg ") :].strip()
    parts = rest.split(maxsplit=2)
    if len(parts) < 3:
        raise ValueError(TEAM_MSG_USAGE)

    team_name, to_member, content = parts[0].strip(), parts[1].strip(), parts[2].strip()
    if not team_name or not to_member or not content:
        raise ValueError(TEAM_MSG_USAGE)

    summary = ""
    text = content
    if "::" in content:
        summary, text = content.split("::", 1)
        summary = summary.strip()
        text = text.strip()

    if not text:
        raise ValueError("Message text cannot be empty")

    if not summary:
        summary = _build_summary(text)
    if not summary:
        raise ValueError("Message summary cannot be empty")

    return {
        "team_name": team_name,
        "from_member": from_member.strip(),
        "to_member": to_member,
        "text": text,
        "summary": summary,
        "type": "message",
    }


def parse_delegate_command(command: str) -> Dict[str, object]:
    raw = (command or "").strip().lower()
    parts = raw.split()
    if len(parts) != 2 or parts[0] != "/delegate":
        raise ValueError(DELEGATE_USAGE)
    action = parts[1]
    if action == "status":
        return {"action": "status"}
    if action == "on":
        return {"action": "set", "enabled": True}
    if action == "off":
        return {"action": "set", "enabled": False}
    raise ValueError(DELEGATE_USAGE)
