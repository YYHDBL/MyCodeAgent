"""Explicit long-term memory management tool."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from prompts.tools_prompts.memory_prompt import memory_prompt
from runtime.memory import LongTermMemoryStore
from tools.base import ErrorCode, Tool, ToolParameter


class MemoryTool(Tool):
    """Manage long-term memory entries via structured actions."""

    def __init__(
        self,
        name: str = "Memory",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
        store: Optional[LongTermMemoryStore] = None,
    ):
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        if store is None:
            raise ValueError("store must be provided by the framework")
        super().__init__(
            name=name,
            description=memory_prompt,
            project_root=project_root,
            working_dir=working_dir or project_root,
        )
        self._store = store

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="One of add, replace, remove, list.",
                required=True,
            ),
            ToolParameter(
                name="target",
                type="string",
                description="Which long-term memory scope to manage: memory or user.",
                required=True,
            ),
            ToolParameter(
                name="content",
                type="string",
                description="Entry content for add or replace.",
                required=False,
            ),
            ToolParameter(
                name="old_text",
                type="string",
                description="Unique substring for replace or remove.",
                required=False,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        started = time.monotonic()
        params_input = dict(parameters)
        action = str(parameters.get("action") or "").strip().lower()
        target = str(parameters.get("target") or "").strip().lower()
        content = parameters.get("content")
        old_text = parameters.get("old_text")

        if target not in {"memory", "user"}:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'target' must be 'memory' or 'user'.",
                params_input=params_input,
            )

        if action == "list":
            state = self._store.list(target)
            return self.create_success_response(
                data={
                    "action": "list",
                    "target": target,
                    "state": state.to_dict(),
                    "frozen_snapshot_affected": False,
                },
                text=f"Listed live long-term memory state for '{target}'.",
                params_input=params_input,
                time_ms=int((time.monotonic() - started) * 1000),
            )

        if action == "add":
            result = self._store.add(target, str(content or ""))
        elif action == "replace":
            result = self._store.replace(target, old_text=str(old_text or ""), content=str(content or ""))
        elif action == "remove":
            result = self._store.remove(target, old_text=str(old_text or ""))
        else:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'action' must be one of add, replace, remove, or list.",
                params_input=params_input,
            )

        elapsed_ms = int((time.monotonic() - started) * 1000)
        payload = {
            "action": action,
            "target": target,
            "reason": result.reason,
            "message": result.message,
            "state": result.state.to_dict(),
            "matches": list(result.matches),
            "frozen_snapshot_affected": False,
        }
        if result.success:
            return self.create_success_response(
                data=payload,
                text=result.message or f"Long-term memory {action} succeeded.",
                params_input=params_input,
                time_ms=elapsed_ms,
            )

        error_code = ErrorCode.EXECUTION_ERROR if result.reason == "write_failed" else ErrorCode.INVALID_PARAM
        return self.create_error_response(
            error_code=error_code,
            message=result.message or f"Long-term memory {action} failed.",
            params_input=params_input,
            time_ms=elapsed_ms,
            data=payload,
        )


__all__ = ["MemoryTool"]
