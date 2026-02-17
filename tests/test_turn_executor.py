import json
from unittest.mock import Mock

from core.team_engine.turn_executor import TurnExecutor
from tools.registry import ToolRegistry


def _raw(content="", tool_calls=None):
    message = {"content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}]}


def test_turn_executor_returns_final_answer_without_tool_calls(tmp_path):
    llm = Mock()
    llm.invoke_raw.return_value = _raw(content="Final Answer: done")
    executor = TurnExecutor(
        llm=llm,
        tool_registry=ToolRegistry(),
        project_root=tmp_path,
        denied_tools={"Task"},
    )
    messages = [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}]

    result = executor.execute_turn(messages, tool_usage={})
    assert result["done"] is True
    assert "done" in result["final_result"]


def test_turn_executor_blocks_denied_task_tool(tmp_path):
    llm = Mock()
    llm.invoke_raw.return_value = _raw(
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {"name": "Task", "arguments": json.dumps({"description": "nested"})},
        }]
    )
    executor = TurnExecutor(
        llm=llm,
        tool_registry=ToolRegistry(),
        project_root=tmp_path,
        denied_tools={"Task"},
    )
    messages = [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}]

    result = executor.execute_turn(messages, tool_usage={})
    assert result["done"] is False
    assert any(m.get("role") == "tool" for m in result["messages"])
    tool_msg = [m for m in result["messages"] if m.get("role") == "tool"][-1]
    assert "not allowed" in tool_msg["content"]
