"""Session persistence utilities (scheme B: snapshot includes system messages)."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional


def _hash_json(data: Any) -> str:
    try:
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    except Exception:
        payload = str(data).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def build_session_snapshot(
    system_messages: List[Dict[str, Any]],
    history_messages: List[Dict[str, Any]],
    tool_schema: List[Dict[str, Any]],
    project_root: str,
    cwd: str = ".",
    code_law_text: Optional[str] = None,
    skills_prompt: Optional[str] = None,
    mcp_tools_prompt: Optional[str] = None,
    read_cache: Optional[Dict[str, Any]] = None,
    tool_output_dir: Optional[str] = None,
    schema_version: int = 1,
    teams_snapshot: Optional[Dict[str, Any]] = None,
    parallel_work_index: Optional[Dict[str, Any]] = None,
    team_store_dir: str = ".teams",
    task_store_dir: str = ".tasks",
) -> Dict[str, Any]:
    team_snapshot_payload = teams_snapshot or {}
    inferred_parallel_index: Dict[str, Any] = {}
    if isinstance(team_snapshot_payload, dict):
        work_items = team_snapshot_payload.get("work_items")
        if isinstance(work_items, dict):
            inferred_parallel_index = work_items
    return {
        "version": 1,
        "schema_version": int(schema_version),
        "system_messages": system_messages or [],
        "history_messages": history_messages or [],
        "tool_schema_hash": _hash_json(tool_schema or []),
        "project_root": project_root,
        "cwd": cwd,
        "code_law_hash": _hash_text(code_law_text or ""),
        "skills_prompt_hash": _hash_text(skills_prompt or ""),
        "mcp_tools_prompt_hash": _hash_text(mcp_tools_prompt or ""),
        "read_cache": read_cache or {},
        "tool_output_dir": tool_output_dir or "tool-output",
        "teams_snapshot": team_snapshot_payload,
        "parallel_work_index": parallel_work_index or inferred_parallel_index,
        "team_store_dir": team_store_dir or ".teams",
        "task_store_dir": task_store_dir or ".tasks",
    }


def save_session_snapshot(path: str | Path, snapshot: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def load_session_snapshot(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("schema_version", 1)
    payload.setdefault("teams_snapshot", {})
    payload.setdefault("parallel_work_index", {})
    payload.setdefault("team_store_dir", ".teams")
    payload.setdefault("task_store_dir", ".tasks")
    return payload
