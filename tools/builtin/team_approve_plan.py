"""TeamApprovePlan tool."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.team_engine.manager import TeamManager, TeamManagerError
from prompts.tools_prompts.team_approve_plan_prompt import team_approve_plan_prompt
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


class TeamApprovePlanTool(Tool):
    def __init__(
        self,
        name: str = "TeamApprovePlan",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
        team_manager: Optional[TeamManager] = None,
    ):
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        super().__init__(
            name=name,
            description=team_approve_plan_prompt,
            project_root=project_root,
            working_dir=working_dir if working_dir else project_root,
        )
        if team_manager is None:
            raise ValueError("team_manager is required")
        self._team_manager = team_manager

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="team_name", type="string", description="Team name", required=True),
            ToolParameter(name="request_id", type="string", description="Approval request id", required=True),
            ToolParameter(name="approved", type="boolean", description="Approve or reject", required=True),
            ToolParameter(name="feedback", type="string", description="Optional feedback", required=False),
            ToolParameter(name="from_member", type="string", description="Sender member name", required=False, default="lead"),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        start_time = time.monotonic()
        params_input = dict(parameters)
        team_name = parameters.get("team_name")
        request_id = parameters.get("request_id")
        approved = parameters.get("approved")
        feedback = parameters.get("feedback", "")
        from_member = parameters.get("from_member", "lead")

        if not isinstance(team_name, str) or not team_name.strip():
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'team_name' is required and must be a non-empty string.",
                params_input=params_input,
            )
        if not isinstance(request_id, str) or not request_id.strip():
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'request_id' is required and must be a non-empty string.",
                params_input=params_input,
            )
        if not isinstance(approved, bool):
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'approved' is required and must be a boolean.",
                params_input=params_input,
            )
        if feedback is not None and not isinstance(feedback, str):
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'feedback' must be a string when provided.",
                params_input=params_input,
            )
        if from_member is not None and not isinstance(from_member, str):
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'from_member' must be a string when provided.",
                params_input=params_input,
            )

        try:
            result = self._team_manager.respond_plan_approval(
                team_name=team_name,
                request_id=request_id,
                approved=approved,
                feedback=feedback or "",
                from_member=(from_member or "lead"),
            )
            return self.create_success_response(
                data=result,
                text=f"Plan approval response sent for request '{request_id}'.",
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
                message=f"TeamApprovePlan failed: {exc}",
                params_input=params_input,
                time_ms=int((time.monotonic() - start_time) * 1000),
            )
