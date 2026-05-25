"""Tool execution boundary separated from registry/schema concerns."""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .base import ErrorCode, ToolStatus
from .context import ToolExecutionContext


class ToolExecutor:
    """Execute registered tools with permission checks and result packaging."""

    def __init__(
        self,
        registry,
        permission_checker: Optional[Callable[[str], bool]] = None,
        context: Optional[ToolExecutionContext] = None,
    ):
        self.registry = registry
        self.context = context or ToolExecutionContext(
            permission_checker=permission_checker or (lambda _name: True)
        )

    def execute(self, name: str, input_text: Any) -> str:
        parameters = self.registry.prepare_parameters(input_text)

        if not self.context.permission_checker(name):
            payload = {
                "status": ToolStatus.ERROR.value,
                "data": {},
                "text": f"Tool '{name}' is not allowed in the current mode.",
                "error": {
                    "code": ErrorCode.PERMISSION_DENIED.value,
                    "message": f"Tool '{name}' is not allowed in the current mode.",
                },
                "stats": {"time_ms": 0},
                "context": {"cwd": ".", "params_input": parameters},
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)

        if name in {"Write", "Edit", "MultiEdit"}:
            parameters = self.registry.inject_optimistic_lock_params(name, parameters)

        if not self.registry.is_available(name):
            return self.registry.create_circuit_open_response(name, parameters)

        result_payload = None
        tool = self.registry.get_tool(name)
        func = self.registry.get_function(name) if tool is None else None

        if tool is not None:
            try:
                result = tool.run(parameters)
                result_payload = self.registry.normalize_result(name, result, parameters)
            except Exception as exc:
                result_payload = self.registry.create_internal_error_payload(
                    name=name,
                    message=f"执行工具 '{name}' 时发生异常: {str(exc)}",
                    params_input=parameters,
                )
        elif func is not None:
            try:
                raw_input = input_text if not isinstance(input_text, dict) else input_text.get("input", input_text)
                result = func(raw_input)
                result_payload = self.registry.normalize_result(name, result, parameters)
            except Exception as exc:
                result_payload = self.registry.create_internal_error_payload(
                    name=name,
                    message=f"执行工具 '{name}' 时发生异常: {str(exc)}",
                    params_input=parameters,
                )
        else:
            result_payload = self.registry.create_internal_error_payload(
                name=name,
                message=f"未找到名为 '{name}' 的工具。",
                params_input={},
            )

        self.registry.record_execution_result(name, result_payload)
        if name == "Read":
            self.registry.cache_read_result(result_payload, parameters)

        return json.dumps(result_payload, ensure_ascii=False, indent=2)
