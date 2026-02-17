"""TeamTaskCreate tool."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.team_engine.manager import TeamManager, TeamManagerError
from prompts.tools_prompts.team_task_create_prompt import team_task_create_prompt
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


class TeamTaskCreateTool(Tool):
    def __init__(
        self,
        name: str = "TeamTaskCreate",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
        team_manager: Optional[TeamManager] = None,
    ):
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        super().__init__(
            name=name,
            description=team_task_create_prompt,
            project_root=project_root,
            working_dir=working_dir if working_dir else project_root,
        )
        if team_manager is None:
            raise ValueError("team_manager is required")
        self._team_manager = team_manager

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="team_name", type="string", description="Team name", required=True),
            ToolParameter(name="subject", type="string", description="Task subject", required=True),
            ToolParameter(name="description", type="string", description="Task description", required=False),
            ToolParameter(name="owner", type="string", description="Optional owner", required=False),
            ToolParameter(name="blocked_by", type="array", description="Optional blocker task ids", required=False),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        start_time = time.monotonic()
        params_input = dict(parameters)
        team_name = parameters.get("team_name")
        subject = parameters.get("subject")
        description = parameters.get("description", "")
        owner = parameters.get("owner", "")
        blocked_by = parameters.get("blocked_by", [])

        if not isinstance(team_name, str) or not team_name.strip():
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'team_name' is required and must be a non-empty string.",
                params_input=params_input,
            )
        if not isinstance(subject, str) or not subject.strip():
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'subject' is required and must be a non-empty string.",
                params_input=params_input,
            )
        if description is not None and not isinstance(description, str):
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'description' must be a string when provided.",
                params_input=params_input,
            )
        if owner is not None and not isinstance(owner, str):
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'owner' must be a string when provided.",
                params_input=params_input,
            )
        if blocked_by is not None and not isinstance(blocked_by, list):
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'blocked_by' must be a list when provided.",
                params_input=params_input,
            )

        try:
            task = self._team_manager.create_board_task(
                team_name=team_name,
                subject=subject,
                description=description or "",
                owner=owner or "",
                blocked_by=blocked_by or [],
            )
            return self.create_success_response(
                data={"task": task},
                text=f"Task #{task.get('id')} created.",
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
                message=f"TeamTaskCreate failed: {exc}",
                params_input=params_input,
                time_ms=int((time.monotonic() - start_time) * 1000),
            )
