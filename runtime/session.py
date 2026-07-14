"""One-way import support for snapshots written by pre-transcript releases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_legacy_session_snapshot(path: str | Path) -> dict[str, Any]:
    """Read a former JSON session snapshot for one-time transcript migration.

    New runtime sessions never call this function: JSONL transcript facts are the
    only durable recovery source.  Keeping the parser here makes the migration
    boundary explicit without retaining a second persistence API.
    """

    snapshot_path = Path(path)
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid legacy session snapshot: {snapshot_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid legacy session snapshot: {snapshot_path}")
    messages = payload.get("history_messages") or []
    if not isinstance(messages, list):
        raise ValueError(f"Invalid legacy session history: {snapshot_path}")
    return payload


__all__ = ["load_legacy_session_snapshot"]
