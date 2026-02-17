import json
from pathlib import Path

from agents.codeAgent import CodeAgent
from core.config import Config
from tools.registry import ToolRegistry


class DummyLLM:
    def invoke_raw(self, messages, tools=None, tool_choice=None):  # pragma: no cover
        raise RuntimeError("not used")


def _tool_names(schemas):
    return {item.get("function", {}).get("name") for item in schemas if isinstance(item, dict)}


def test_delegate_mode_filters_non_coordination_tools(tmp_path):
    cfg = Config(enable_agent_teams=True, delegate_mode=True)
    agent = CodeAgent(
        name="lead",
        llm=DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(Path(tmp_path)),
        config=cfg,
    )

    names = _tool_names(agent._get_openai_tools_for_current_mode())
    assert "TeamStatus" in names
    assert "SendMessage" in names
    assert "Read" not in names
    assert "Write" not in names


def test_delegate_mode_blocks_disallowed_tool_execution(tmp_path):
    cfg = Config(enable_agent_teams=True, delegate_mode=True)
    agent = CodeAgent(
        name="lead",
        llm=DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(Path(tmp_path)),
        config=cfg,
    )

    payload = json.loads(agent._execute_tool("Read", {"file_path": "README.md"}))
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "PERMISSION_DENIED"


def test_delegate_mode_can_toggle_at_runtime(tmp_path):
    cfg = Config(enable_agent_teams=True, delegate_mode=False)
    agent = CodeAgent(
        name="lead",
        llm=DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(Path(tmp_path)),
        config=cfg,
    )

    names_before = _tool_names(agent._get_openai_tools_for_current_mode())
    assert "Read" in names_before

    agent.set_delegate_mode(True)
    names_after = _tool_names(agent._get_openai_tools_for_current_mode())
    assert "Read" not in names_after
    assert "TeamStatus" in names_after
