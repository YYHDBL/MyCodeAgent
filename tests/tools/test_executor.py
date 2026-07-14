import json

from tools.base import ErrorCode, Tool, ToolParameter, ToolResult, ToolStatus
from tools.permissions import PermissionAction, PermissionContext, PermissionDecision, RiskLevel
from tools.registry import ToolRegistry
from tools.base import serialize_tool_result


def _payload(result):
    return json.loads(serialize_tool_result(result))


class EchoTool(Tool):
    def __init__(self):
        super().__init__(name="Echo", description="echo tool")

    def get_parameters(self):
        return [ToolParameter(name="value", type="string", description="value")]

    def run(self, parameters):
        return self.success_result(
            data={"value": parameters["value"]},
            text=parameters["value"],
            params_input=parameters,
            time_ms=1,
        )


def test_tool_executor_executes_registered_tool():
    from tools.executor import ToolExecutor

    registry = ToolRegistry()
    registry.register_tool(EchoTool())
    executor = ToolExecutor(registry)

    result = _payload(executor.execute("Echo", {"value": "hello"}))

    assert result["status"] == ToolStatus.SUCCESS.value
    assert result["data"]["value"] == "hello"


def test_tool_executor_enforces_permission_boundary_without_affecting_schema():
    from tools.executor import ToolExecutor

    registry = ToolRegistry()
    registry.register_tool(EchoTool())
    executor = ToolExecutor(registry, permission_checker=lambda name: False)

    result = _payload(executor.execute("Echo", {"value": "hello"}))
    schemas = registry.get_openai_tools()

    assert result["status"] == ToolStatus.ERROR.value
    assert result["error"]["code"] == "PERMISSION_DENIED"
    assert any(item["function"]["name"] == "Echo" for item in schemas)


def test_tool_executor_accepts_typed_registered_function_results():
    from tools.executor import ToolExecutor

    registry = ToolRegistry()
    registry.register_function(
        "Upper",
        "upper-case input",
        lambda value: ToolResult(
            status=ToolStatus.SUCCESS,
            data={"value": str(value).upper()},
            text=str(value).upper(),
            stats={"time_ms": 1},
            context={"cwd": ".", "params_input": {"input": value}},
        ),
    )
    executor = ToolExecutor(registry)

    result = _payload(executor.execute("Upper", {"input": "hello"}))
    schemas = registry.get_openai_tools()

    assert result["status"] == ToolStatus.SUCCESS.value
    assert result["data"]["value"] == "HELLO"
    assert any(item["function"]["name"] == "Upper" for item in schemas)


def test_tool_execution_context_carries_permission_checker():
    from tools.context import ToolExecutionContext
    from tools.executor import ToolExecutor

    registry = ToolRegistry()
    registry.register_tool(EchoTool())
    context = ToolExecutionContext(permission_checker=lambda name: name != "Echo")
    executor = ToolExecutor(registry, context=context)

    result = _payload(executor.execute("Echo", {"value": "hello"}))

    assert result["status"] == ToolStatus.ERROR.value
    assert result["error"]["code"] == "PERMISSION_DENIED"


def test_tool_executor_returns_permission_denied_payload_with_decision_metadata():
    from tools.context import ToolExecutionContext
    from tools.executor import ToolExecutor

    registry = ToolRegistry()
    registry.register_tool(EchoTool())
    context = ToolExecutionContext(
        permission_context=PermissionContext(runtime_mode="readonly_subagent"),
        permission_decider=lambda name, params, ctx: PermissionDecision(
            action=PermissionAction.DENY,
            risk=RiskLevel.HIGH,
            reason=f"{name} blocked for {ctx.runtime_mode}",
            policy_source="unit_test",
            input_summary=json.dumps(params, ensure_ascii=False, sort_keys=True),
        ),
    )
    executor = ToolExecutor(registry, context=context)

    result = _payload(executor.execute("Echo", {"value": "hello"}))

    assert result["status"] == ToolStatus.ERROR.value
    assert result["error"]["code"] == ErrorCode.PERMISSION_DENIED.value
    assert result["error"]["details"]["permission"]["action"] == "deny"
    assert result["error"]["details"]["permission"]["policy_source"] == "unit_test"


def test_tool_executor_keeps_runtime_allowlist_after_policy_allow():
    from tools.context import ToolExecutionContext
    from tools.executor import ToolExecutor

    registry = ToolRegistry()
    registry.register_tool(EchoTool())
    context = ToolExecutionContext(
        permission_checker=lambda _name: False,
        permission_decider=lambda name, params, ctx: PermissionDecision(
            action=PermissionAction.ALLOW,
            risk=RiskLevel.LOW,
            reason=f"{name} allowed by classifier",
            policy_source="unit_test",
            input_summary=json.dumps(params, ensure_ascii=False, sort_keys=True),
        ),
    )
    executor = ToolExecutor(registry, context=context)

    result = _payload(executor.execute("Echo", {"value": "hello"}))

    assert result["status"] == ToolStatus.ERROR.value
    assert result["error"]["code"] == ErrorCode.PERMISSION_DENIED.value
