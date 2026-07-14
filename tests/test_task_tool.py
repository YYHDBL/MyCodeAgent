import json
from unittest.mock import Mock

import pytest

from runtime.subagents import ExploreResult, SubagentLaunchResult, SubagentStatus
from tools.base import ErrorCode, serialize_tool_result
from tools.builtin.task import TaskTool


@pytest.fixture
def launcher():
    return Mock()


@pytest.fixture
def task_tool(tmp_path, launcher):
    return TaskTool(project_root=tmp_path, launcher=launcher)


def test_task_parameters_only_expose_formal_explore_mode(task_tool):
    names = [item.name for item in task_tool.get_parameters()]
    assert names == ["description", "prompt", "subagent_type", "model"]


@pytest.mark.parametrize("subagent_type", ["general", "plan", "summary", "persistent", "parallel"])
def test_task_rejects_legacy_modes(task_tool, subagent_type):
    payload = json.loads(serialize_tool_result(
        task_tool.run({"description": "d", "prompt": "p", "subagent_type": subagent_type})
    ))
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.INVALID_PARAM.value


def test_task_returns_only_structured_explore_result(task_tool, launcher):
    launcher.launch.return_value = SubagentLaunchResult(
        status=SubagentStatus.COMPLETED,
        profile_name="explore",
        child_session_id="child-session",
        child_run_id="child-run",
        result=ExploreResult(
            status=SubagentStatus.COMPLETED,
            summary="summary",
            findings=("finding",),
            evidence=("runtime/loop.py:1",),
            unresolved_questions=(),
            tool_usage={"Read": 1},
            terminal_reason="completed",
        ),
        elapsed_ms=12,
    )
    payload = json.loads(serialize_tool_result(
        task_tool.run({"description": "d", "prompt": "p", "subagent_type": "explore"})
    ))
    assert payload["status"] == "success"
    assert payload["data"]["result"]["summary"] == "summary"
    assert "history" not in payload["data"]
    assert "session_memory" not in payload["data"]


def test_task_contains_child_failure(task_tool, launcher):
    launcher.launch.return_value = SubagentLaunchResult(
        status=SubagentStatus.FAILED,
        profile_name="explore",
        child_session_id="child-session",
        child_run_id="child-run",
        result=None,
        terminal_reason="runtime_error",
        error="boom",
        elapsed_ms=3,
    )
    payload = json.loads(serialize_tool_result(
        task_tool.run({"description": "d", "prompt": "p", "subagent_type": "explore"})
    ))
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.INTERNAL_ERROR.value
