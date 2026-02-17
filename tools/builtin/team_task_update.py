"""TeamTaskUpdate tool."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.team_engine.manager import TeamManager, TeamManagerError
from prompts.tools_prompts.team_task_update_prompt import team_task_update_prompt
from ..base import ErrorCode, Tool, ToolParameter


def _map_error_code(code: str) -> ErrorCode:
    if code == "INVALID_PARAM":
        return ErrorCode.INVALID_PARAM
    if code == "NOT_FOUND":
        return ErrorCode.NOT_FOUND
    if code == "TIMEOUT":
        return ErrorCode.TIMEOUT
    if code == "CONFLICT":
        return ErrorCode.CONFLICT
    return ErrorCode.INTERNAL_ERROR


class TeamTaskUpdateTool(Tool):
    def __init__(
        self,
        name: str = "TeamTaskUpdate",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
        team_manager: Optional[TeamManager] = None,
    ):
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        super().__init__(
            name=name,
            description=team_task_update_prompt,
            project_root=project_root,
            working_dir=working_dir if working_dir else project_root,
        )
        if team_manager is None:
            raise ValueError("team_manager is required")
        self._team_manager = team_manager

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="team_name", type="string", description="Team name", required=True),
            ToolParameter(name="task_id", type="string", description="Task id", required=True),
            ToolParameter(name="status", type="string", description="Task status", required=False),
            ToolParameter(name="owner", type="string", description="Task owner", required=False),
            ToolParameter(name="subject", type="string", description="Task subject", required=False),
            ToolParameter(name="description", type="string", description="Task description", required=False),
            ToolParameter(name="add_blocked_by", type="array", description="Blockers to add", required=False),
            ToolParameter(name="add_blocks", type="array", description="Blocked tasks to add", required=False),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        start_time = time.monotonic()
        params_input = dict(parameters)
        team_name = parameters.get("team_name")
        task_id = parameters.get("task_id")

        if not isinstance(team_name, str) or not team_name.strip():
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'team_name' is required and must be a non-empty string.",
                params_input=params_input,
            )
        if not isinstance(task_id, str) or not task_id.strip():
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'task_id' is required and must be a non-empty string.",
                params_input=params_input,
            )

        for field in ("status", "owner", "subject", "description"):
            if field in parameters and parameters.get(field) is not None and not isinstance(parameters.get(field), str):
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message=f"Parameter '{field}' must be a string when provided.",
                    params_input=params_input,
                )
        for field in ("add_blocked_by", "add_blocks"):
            if field in parameters and parameters.get(field) is not None and not isinstance(parameters.get(field), list):
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message=f"Parameter '{field}' must be a list when provided.",
                    params_input=params_input,
                )

        try:
            task = self._team_manager.update_board_task(
                team_name=team_name,
                task_id=task_id,
                status=parameters.get("status"),
                owner=parameters.get("owner"),
                subject=parameters.get("subject"),
                description=parameters.get("description"),
                add_blocked_by=parameters.get("add_blocked_by"),
                add_blocks=parameters.get("add_blocks"),
            )
            return self.create_success_response(
                data={"task": task},
                text=f"Task #{task.get('id')} updated.",
                params_input=params_input,
                time_ms=int((time.monotonic() - start_time) * 1000),
            )
        except TeamManagerError as exc:
            return self.create_error_response(
                error_code=_map_error_code(exc.code),
                message=exc.message,
                params_input=params_input,
                time_ms=int((time.monotonic() - start_time) * 1000),
            )
        except Exception as exc:  # pragma: no cover
            return self.create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"TeamTaskUpdate failed: {exc}",
                params_input=params_input,
                time_ms=int((time.monotonic() - start_time) * 1000),
            )
