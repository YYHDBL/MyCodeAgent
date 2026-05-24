"""Helpers for rendering team progress in terminal UI."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def build_team_progress_rows(runtime_state: Optional[Dict[str, Any]], team_name: Optional[str] = None) -> List[Dict[str, Any]]:
    state = runtime_state if isinstance(runtime_state, dict) else {}
    work_items = state.get("work_items") if isinstance(state.get("work_items"), dict) else {}
    teams = state.get("teams") if isinstance(state.get("teams"), dict) else {}
    approvals = state.get("approvals") if isinstance(state.get("approvals"), dict) else {}
    task_board = state.get("task_board") if isinstance(state.get("task_board"), dict) else {}

    names = sorted(work_items.keys())
    if team_name:
        names = [name for name in names if name == str(team_name)]

    rows: List[Dict[str, Any]] = []
    for name in names:
        counts = work_items.get(name) if isinstance(work_items.get(name), dict) else {}
        team_state = teams.get(name) if isinstance(teams.get(name), dict) else {}
        approval = approvals.get(name) if isinstance(approvals.get(name), dict) else {}
        board = task_board.get(name) if isinstance(task_board.get(name), dict) else {}
        active = team_state.get("active_teammates")
        idle = team_state.get("idle_teammates")
        rows.append(
            {
                "team": name,
                "queued": _as_int(counts.get("queued")),
                "running": _as_int(counts.get("running")),
                "succeeded": _as_int(counts.get("succeeded")),
                "failed": _as_int(counts.get("failed")),
                "active": len(active) if isinstance(active, list) else 0,
                "idle": len(idle) if isinstance(idle, list) else 0,
                "approvals_pending": _as_int(approval.get("pending")),
                "blocked": _as_int(board.get("blocked")),
            }
        )
    return rows

