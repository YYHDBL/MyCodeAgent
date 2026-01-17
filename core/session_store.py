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
) -> Dict[str, Any]:
    return {
        "version": 1,
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
    }


def save_session_snapshot(path: str | Path, snapshot: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def load_session_snapshot(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))
