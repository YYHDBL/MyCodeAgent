"""Tool call orchestration boundary for the agent runtime."""

from __future__ import annotations

import json
import traceback as tb
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolObservation:
    tool_name: str
    tool_call_id: str
    observation: str


class ToolOrchestrator:
    """Execute model tool calls while preserving model order."""

    def __init__(self, host: Any):
        self.host = host

    def run_serial(
        self,
        tool_calls: list[dict[str, Any]],
        *,
        step: int,
        trace_logger,
    ) -> list[ToolObservation]:
        observations: list[ToolObservation] = []
        host = self.host

        for call in tool_calls:
            tool_name = call.get("name") or "unknown_tool"
            tool_call_id = call.get("id") or f"call_{uuid.uuid4().hex}"
            raw_args = call.get("arguments") or {}
            tool_input, parse_err = host._ensure_json_input(raw_args)
            if parse_err:
                error_result = {
                    "status": "error",
                    "error": {
                        "code": "INVALID_PARAM",
                        "message": f"Tool arguments parse error: {parse_err}",
                    },
                    "data": {},
                }
                observation = json.dumps(error_result, ensure_ascii=False)
                trace_logger.log_event(
                    "error",
                    {
                        "stage": "tool_call_parse",
                        "error_code": "INVALID_PARAM",
                        "message": str(parse_err),
                        "tool": tool_name,
                        "tool_call_id": tool_call_id,
                    },
                    step=step,
                )
            else:
                trace_logger.log_event(
                    "tool_call",
                    {"tool": tool_name, "args": tool_input, "tool_call_id": tool_call_id},
                    step=step,
                )
                try:
                    if hasattr(host, "tool_executor") and host.tool_executor is not None:
                        observation = host.tool_executor.execute(tool_name, tool_input)
                    else:
                        observation = host._execute_tool(tool_name, tool_input)
                    try:
                        result_obj = json.loads(observation)
                        trace_logger.log_event(
                            "tool_result",
                            {"tool": tool_name, "result": result_obj},
                            step=step,
                        )
                    except json.JSONDecodeError:
                        trace_logger.log_event(
                            "tool_result",
                            {"tool": tool_name, "result": {"text": observation}},
                            step=step,
                        )
                except Exception as exc:
                    error_result = {
                        "status": "error",
                        "error": {"code": "EXECUTION_ERROR", "message": str(exc)},
                        "data": {},
                    }
                    observation = json.dumps(error_result, ensure_ascii=False)
                    trace_logger.log_event(
                        "error",
                        {
                            "stage": "tool_execution",
                            "error_code": "EXECUTION_ERROR",
                            "message": str(exc),
                            "tool": tool_name,
                            "traceback": tb.format_exc(),
                        },
                        step=step,
                    )

            observations.append(
                ToolObservation(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    observation=observation,
                )
            )

        return observations
