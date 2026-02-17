"""SendMessage tool."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.team_engine.manager import TeamManager, TeamManagerError
from prompts.tools_prompts.send_message_prompt import send_message_prompt
from ..base import ErrorCode, Tool, ToolParameter


def _map_error_code(code: str) -> ErrorCode:
    if code == "INVALID_PARAM":
        return ErrorCode.INVALID_PARAM
    if code == "NOT_FOUND":
        return ErrorCode.NOT_FOUND
    if code == "TIMEOUT":
        return ErrorCode.TIMEOUT
    return ErrorCode.INTERNAL_ERROR


class SendMessageTool(Tool):
    def __init__(
        self,
        name: str = "SendMessage",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
        team_manager: Optional[TeamManager] = None,
    ):
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        super().__init__(
            name=name,
            description=send_message_prompt,
            project_root=project_root,
            working_dir=working_dir if working_dir else project_root,
        )
        if team_manager is None:
            raise ValueError("team_manager is required")
        self._team_manager = team_manager

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="team_name", type="string", description="Team name", required=True),
            ToolParameter(name="from_member", type="string", description="Sender member name", required=True),
            ToolParameter(name="to_member", type="string", description="Receiver member name", required=True),
            ToolParameter(name="text", type="string", description="Message text", required=True),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        start_time = time.monotonic()
        params_input = dict(parameters)
        team_name = parameters.get("team_name")
        from_member = parameters.get("from_member")
        to_member = parameters.get("to_member")
        text = parameters.get("text")

        for field_name, value in (
            ("team_name", team_name),
            ("from_member", from_member),
            ("to_member", to_member),
            ("text", text),
        ):
            if not isinstance(value, str) or not value.strip():
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message=f"Parameter '{field_name}' is required and must be a non-empty string.",
                    params_input=params_input,
                )

        try:
            sent = self._team_manager.send_message(team_name, from_member, to_member, text)
            return self.create_success_response(
                data={
                    "message_id": sent.get("message_id"),
                    "status": sent.get("status"),
                    "team_name": team_name,
                    "from_member": from_member,
                    "to_member": to_member,
                },
                text=f"Message sent to '{to_member}' ({sent.get('status')}).",
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
                message=f"SendMessage failed: {exc}",
                params_input=params_input,
                time_ms=int((time.monotonic() - start_time) * 1000),
            )

