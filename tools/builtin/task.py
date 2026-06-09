"""Task tool adapter for the formal Explore subagent."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.subagents import (
    ExploreResult,
    SubagentLauncher,
    SubagentRequest,
    SubagentStatus,
)
from tools.base import ErrorCode, Tool, ToolParameter
from prompts.tools_prompts.task_prompt import task_prompt


class TaskTool(Tool):
    """Validate an Explore request and delegate execution to SubagentLauncher."""

    def __init__(
        self,
        name: str = "Task",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
        launcher: Optional[SubagentLauncher] = None,
    ):
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        if launcher is None:
            raise ValueError("launcher must be provided by the framework")
        super().__init__(
            name=name,
            description=task_prompt,
            project_root=project_root,
            working_dir=working_dir or project_root,
        )
        self._launcher = launcher

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="description",
                type="string",
                description="Short summary of the delegated search task",
                required=True,
            ),
            ToolParameter(
                name="prompt",
                type="string",
                description="Self-contained read-only exploration instructions",
                required=True,
            ),
            ToolParameter(
                name="subagent_type",
                type="string",
                description="Formal profile; only 'explore' is supported",
                required=True,
            ),
            ToolParameter(
                name="model",
                type="string",
                description="Optional model route: main or light",
                required=False,
                default="light",
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        started = time.monotonic()
        params_input = dict(parameters)
        description = parameters.get("description")
        prompt = parameters.get("prompt")
        profile = str(parameters.get("subagent_type") or "").strip().lower()
        model = str(parameters.get("model") or "light").strip().lower()
        if not isinstance(description, str) or not description.strip():
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'description' is required and must be non-empty.",
                params_input=params_input,
            )
        if not isinstance(prompt, str) or not prompt.strip():
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'prompt' is required and must be non-empty.",
                params_input=params_input,
            )
        if profile != "explore":
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'subagent_type' must be 'explore'.",
                params_input=params_input,
            )
        if model not in {"main", "light"}:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'model' must be 'main' or 'light'.",
                params_input=params_input,
            )
        launched = self._launcher.launch(
            SubagentRequest(
                profile_name="explore",
                task=f"{description.strip()}\n\n{prompt.strip()}",
                model_choice=model,
            )
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if launched.status is SubagentStatus.FAILED or not isinstance(launched.result, ExploreResult):
            return self.create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Explore subagent failed: {launched.error or launched.terminal_reason}",
                params_input=params_input,
                time_ms=elapsed_ms,
            )
        result = launched.result
        return self.create_success_response(
            data={
                "status": result.status.value,
                "profile": "explore",
                "child_session_id": launched.child_session_id,
                "child_run_id": launched.child_run_id,
                "result": result.to_dict(),
            },
            text=result.summary,
            params_input=params_input,
            time_ms=elapsed_ms,
            extra_stats={
                "tool_calls": sum(result.tool_usage.values()),
                "token_usage": launched.token_usage,
                "model": launched.model_used,
            },
        )


__all__ = ["TaskTool"]
