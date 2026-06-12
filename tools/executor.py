"""Tool execution boundary separated from registry/schema concerns."""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .base import ErrorCode, ToolStatus
from .context import ToolExecutionContext
from .permissions import PermissionAction


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

    def execute(self, name: str, input_text: Any, *, trace_logger=None, step: int = 0) -> str:
        parameters = self.registry.prepare_parameters(input_text)

        permission_payload = self._decide_permission(name, parameters, trace_logger=trace_logger, step=step)
        if permission_payload is not None:
            return json.dumps(permission_payload, ensure_ascii=False, indent=2)

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
        if name == "Memory" and trace_logger is not None:
            self._log_long_term_memory_event(result_payload, trace_logger=trace_logger, step=step)

        return json.dumps(result_payload, ensure_ascii=False, indent=2)

    def _decide_permission(self, name: str, parameters: dict[str, Any], *, trace_logger=None, step: int = 0):
        decider = self.context.permission_decider
        if decider is not None:
            decision = decider(name, parameters, self.context.permission_context)
            effective_action = decision.action
            if effective_action is PermissionAction.ASK and self.context.permission_context.ask_policy == "deny":
                effective_action = PermissionAction.DENY
            if trace_logger:
                trace_logger.log_event(
                    "permission_decision",
                    decision.as_trace_payload(
                        tool_name=name,
                        effective_action=effective_action.value,
                    ),
                    step=step,
                )
            if effective_action is not PermissionAction.ALLOW:
                return self._permission_denied_payload(name, parameters, decision, effective_action)
            return None

        if not self.context.permission_checker(name):
            return {
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
        return None

    def _permission_denied_payload(self, name: str, parameters: dict[str, Any], decision, effective_action):
        rendered_action = "denied" if effective_action is PermissionAction.DENY else "requires confirmation"
        return {
            "status": ToolStatus.ERROR.value,
            "data": {},
            "text": f"Tool '{name}' {rendered_action} by permission core.",
            "error": {
                "code": ErrorCode.PERMISSION_DENIED.value,
                "message": f"Tool '{name}' {rendered_action} by permission core.",
                "details": {
                    "permission": {
                        **decision.as_trace_payload(tool_name=name),
                        "effective_action": effective_action.value,
                    }
                },
            },
            "stats": {"time_ms": 0},
            "context": {
                "cwd": ".",
                "params_input": parameters,
                "runtime_mode": self.context.permission_context.runtime_mode,
            },
        }

    @staticmethod
    def _log_long_term_memory_event(result_payload: dict[str, Any], *, trace_logger, step: int) -> None:
        if not isinstance(result_payload, dict):
            return
        data = result_payload.get("data")
        if not isinstance(data, dict):
            return
        state = data.get("state")
        if not isinstance(state, dict):
            return
        usage = state.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        event_name = (
            "long_term_memory_write"
            if result_payload.get("status") != ToolStatus.ERROR.value
            else "long_term_memory_rejected"
        )
        trace_logger.log_event(
            event_name,
            {
                "action": data.get("action"),
                "target": data.get("target"),
                "entry_count": usage.get("entry_count", 0),
                "usage_chars": usage.get("chars", 0),
                "limit_chars": usage.get("limit", 0),
                "reason": data.get("reason"),
            },
            step=step,
        )
