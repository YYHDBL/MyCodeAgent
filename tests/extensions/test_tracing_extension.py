from agents.codeAgent import CodeAgent
from tools.registry import ToolRegistry


class _DummyLLM:
    provider = "openai"
    model = "dummy-model"


def test_codeagent_uses_null_trace_logger_when_tracing_disabled(tmp_path):
    agent = CodeAgent(
        name="code",
        llm=_DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        enable_skills=False,
        enable_mcp=False,
        enable_tracing=False,
    )

    assert agent.trace_logger.enabled is False
