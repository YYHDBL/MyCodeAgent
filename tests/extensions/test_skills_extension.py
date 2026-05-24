from agents.codeAgent import CodeAgent
from tools.registry import ToolRegistry


class _DummyLLM:
    provider = "openai"
    model = "dummy-model"


def test_codeagent_can_disable_skills_extension(tmp_path):
    agent = CodeAgent(
        name="code",
        llm=_DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        enable_skills=False,
        enable_mcp=False,
        enable_tracing=False,
    )

    assert agent._skill_loader is None
    assert "Skill" not in agent.tool_registry.list_tools()

