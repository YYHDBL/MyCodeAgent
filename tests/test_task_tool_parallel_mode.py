import json
from unittest.mock import Mock

from tools.builtin.task import TaskTool
from tools.registry import ToolRegistry


def _make_task_tool(tmp_path, team_manager):
    llm = Mock()
    llm.invoke_raw = Mock(return_value={"choices": [{"message": {"content": "ok"}}]})
    registry = ToolRegistry()
    return TaskTool(
        project_root=tmp_path,
        main_llm=llm,
        tool_registry=registry,
        team_manager=team_manager,
    )


def test_task_parallel_mode_dispatches_fanout(tmp_path):
    manager = Mock()
    manager.fanout_work.return_value = {
        "dispatch_id": "dispatch_1",
        "team_name": "demo",
        "work_items": [{"work_id": "w1"}],
    }
    tool = _make_task_tool(tmp_path, manager)

    response = json.loads(
        tool.run(
            {
                "description": "parallel",
                "prompt": "dispatch",
                "subagent_type": "general",
                "mode": "parallel",
                "team_name": "demo",
                "tasks": [{"owner": "dev1", "title": "impl", "instruction": "do impl"}],
            }
        )
    )
    assert response["status"] == "success"
    assert response["data"]["mode"] == "parallel"
    manager.fanout_work.assert_called_once()


def test_task_parallel_mode_param_validation(tmp_path):
    manager = Mock()
    tool = _make_task_tool(tmp_path, manager)

    response = json.loads(
        tool.run(
            {
                "description": "parallel",
                "prompt": "dispatch",
                "subagent_type": "general",
                "mode": "parallel",
                "team_name": "demo",
            }
        )
    )
    assert response["status"] == "error"
    assert response["error"]["code"] == "INVALID_PARAM"
