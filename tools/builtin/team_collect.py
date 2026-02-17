"""TeamCollect tool."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.team_engine.manager import TeamManager, TeamManagerError
from prompts.tools_prompts.team_collect_prompt import team_collect_prompt
from ..base import ErrorCode, Tool, ToolParameter


def _map_error_code(code: str) -> ErrorCode:
    if code == "INVALID_PARAM":
        return ErrorCode.INVALID_PARAM
    if code == "NOT_FOUND":
        return ErrorCode.NOT_FOUND
    if code == "TIMEOUT":
        return ErrorCode.TIMEOUT
    return ErrorCode.INTERNAL_ERROR


class TeamCollectTool(Tool):
    def __init__(
        self,
        name: str = "TeamCollect",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
        team_manager: Optional[TeamManager] = None,
    ):
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        super().__init__(
            name=name,
            description=team_collect_prompt,
            project_root=project_root,
            working_dir=working_dir if working_dir else project_root,
        )
        if team_manager is None:
            raise ValueError("team_manager is required")
        self._team_manager = team_manager

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="team_name", type="string", description="Team name", required=True),
            ToolParameter(name="work_ids", type="array", description="Optional work item id list", required=False),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        start_time = time.monotonic()
        params_input = dict(parameters)
        team_name = parameters.get("team_name")
        work_ids = parameters.get("work_ids")
        if not isinstance(team_name, str) or not team_name.strip():
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'team_name' is required and must be a non-empty string.",
                params_input=params_input,
            )
        if work_ids is not None and not isinstance(work_ids, list):
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'work_ids' must be a list when provided.",
                params_input=params_input,
            )
        try:
            result = self._team_manager.collect_work(team_name=team_name, work_ids=work_ids)
            counts = result.get("counts", {})
            text = (
                f"Collected {result.get('total', 0)} work items: "
                f"queued={counts.get('queued', 0)}, "
                f"running={counts.get('running', 0)}, "
                f"succeeded={counts.get('succeeded', 0)}, "
                f"failed={counts.get('failed', 0)}."
            )
            return self.create_success_response(
                data=result,
                text=text,
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
                message=f"TeamCollect failed: {exc}",
                params_input=params_input,
                time_ms=int((time.monotonic() - start_time) * 1000),
            )
