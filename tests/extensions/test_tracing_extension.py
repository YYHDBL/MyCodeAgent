from runtime.host import CodeAgent
from tools.registry import ToolRegistry
import warnings

from extensions.tracing.logger import TraceLogger


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


def test_trace_logger_init_emits_no_datetime_deprecation_warning(tmp_path):
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        logger = TraceLogger("test-session", tmp_path, enabled=True)
        logger.finalize()

    deprecations = [w for w in captured if issubclass(w.category, DeprecationWarning)]
    assert deprecations == []
