"""Internal tool-result contract and model-boundary serialization."""

from __future__ import annotations

import json

from tools.base import Tool, ToolParameter
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry


class _Echo(Tool):
    def __init__(self) -> None:
        super().__init__(name="Echo", description="test echo")

    def get_parameters(self) -> list[ToolParameter]:
        return []

    def run(self, parameters):
        return self.success_result(
            data={"value": parameters["value"]},
            text=parameters["value"],
            params_input=parameters,
            time_ms=1,
        )


def test_executor_keeps_a_typed_result_until_the_model_boundary() -> None:
    from tools.base import ToolResult, serialize_tool_result

    registry = ToolRegistry()
    registry.register_tool(_Echo())

    result = ToolExecutor(registry).execute("Echo", {"value": "hello"})

    assert isinstance(result, ToolResult)
    assert result.data == {"value": "hello"}
    assert json.loads(serialize_tool_result(result)) == {
        "status": "success",
        "data": {"value": "hello"},
        "text": "hello",
        "stats": {"time_ms": 1},
        "context": {"cwd": ".", "params_input": {"value": "hello"}},
    }


def test_result_budget_truncates_the_typed_result_without_reparsing_json(tmp_path) -> None:
    from tools.base import ToolResult, ToolStatus, serialize_tool_result
    from tools.observation_store import force_truncate_result

    result = ToolResult(
        status=ToolStatus.SUCCESS,
        text="large result",
        data={"content": "x" * 1000},
        stats={"time_ms": 1},
        context={"cwd": ".", "params_input": {}},
    )

    truncated = force_truncate_result("Read", result, str(tmp_path), max_preview_bytes=120)

    assert isinstance(truncated, ToolResult)
    assert truncated.status is ToolStatus.PARTIAL
    assert truncated.data["truncated"] is True
    assert json.loads(serialize_tool_result(truncated))["data"]["truncation"]["full_output_path"]
