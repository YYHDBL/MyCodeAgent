"""AskUser tool - request user input during agent execution."""

from __future__ import annotations

import time
from typing import Any, Dict, List

from tools.base import Tool, ToolParameter, ErrorCode


class AskUserTool(Tool):
    """向用户提问并等待回答（仅主 Agent 允许交互）。"""

    name = "AskUser"
    description = "向用户提问并获取回答（仅主 Agent 允许交互）。"

    def __init__(self, project_root=None, working_dir=None, interactive: bool = True):
        super().__init__(
            name=self.name,
            description=self.description,
            project_root=project_root,
            working_dir=working_dir,
        )
        self._interactive = bool(interactive)

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="questions",
                type="array",
                description="问题列表，每项为 {id, text, type, options?, required?}",
                required=True,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        if not self._interactive:
            return self.create_error_response(
                error_code=ErrorCode.ASK_USER_UNAVAILABLE,
                message="Subagent 禁止 AskUser 交互，请在主 Agent 处理。",
                params_input=parameters,
                time_ms=0,
            )

        questions = parameters.get("questions")
        if not isinstance(questions, list) or not questions:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="questions 必须是非空列表。",
                params_input=parameters,
                time_ms=0,
            )

        start = time.monotonic()
        answers: list[dict[str, Any]] = []
        for item in questions:
            if not isinstance(item, dict):
                continue
            prompt_text = str(item.get("text", "")).strip()
            if not prompt_text:
                continue
            prompt = f"[Agent 问] {prompt_text}\n> "
            try:
                user_input = input(prompt)
            except EOFError:
                user_input = ""
            answers.append({"id": item.get("id"), "answer": user_input})

        time_ms = int((time.monotonic() - start) * 1000)
        return self.create_success_response(
            data={"answers": answers},
            text=f"用户已回答 {len(answers)} 个问题",
            params_input=parameters,
            time_ms=time_ms,
        )
