from pathlib import Path

from core.agent import Agent
from core.exceptions import HelloAgentsException
from runtime.prompt_builder import ContextBuilder


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class _Registry:
    def get_disabled_tools(self):
        return []


def test_code_law_matches_the_current_repository_and_runtime_entrypoint():
    code_law = (PROJECT_ROOT / "code_law.md").read_text(encoding="utf-8")

    assert "runtime/" in code_law
    assert "extensions/" in code_law
    assert "python main.py" in code_law
    assert "agents/" not in code_law
    assert "scripts/chat_test_agent.py" not in code_law
    assert "core/context_engine/" not in code_law


def test_prompt_builder_injects_only_current_project_rules():
    builder = ContextBuilder(
        tool_registry=_Registry(),
        project_root=str(PROJECT_ROOT),
        system_prompt_override="base",
    )

    project_rules = "\n".join(
        message["content"]
        for message in builder.get_prompt_assembly().project_rule_messages
    )

    assert "runtime/" in project_rules
    assert "python main.py" in project_rules
    assert "scripts/chat_test_agent.py" not in project_rules


def test_agent_base_is_a_thin_protocol_without_duplicate_history_state():
    source = (PROJECT_ROOT / "core" / "agent.py").read_text(encoding="utf-8")

    assert "_history" not in source
    assert "runtime.history" not in source
    assert "add_message" not in Agent.__dict__
    assert "clear_history" not in Agent.__dict__
    assert "get_history" not in Agent.__dict__


def test_tool_orchestrator_has_no_runtime_layer_imports():
    source = (PROJECT_ROOT / "tools" / "orchestrator.py").read_text(encoding="utf-8")

    assert "runtime.observation_store" not in source
    assert "from tools.observation_budget import force_truncate_observation" in source


def test_runtime_host_and_loop_expose_factored_initialization_and_stages():
    host_source = (PROJECT_ROOT / "runtime" / "host.py").read_text(encoding="utf-8")
    loop_source = (PROJECT_ROOT / "runtime" / "loop.py").read_text(encoding="utf-8")

    assert "RuntimeComponentFactory" in host_source
    assert "def _initialize_runtime_components(" in host_source
    assert "def _prepare_run(" in loop_source
    assert "def _finish_run(" in loop_source
    assert "def _prepare_step_context(" in loop_source


def test_only_the_exception_type_used_by_runtime_remains():
    import core.exceptions as exceptions

    assert exceptions.__all__ == ["HelloAgentsException"]
    assert issubclass(HelloAgentsException, Exception)
    assert not hasattr(exceptions, "LLMException")
    assert not hasattr(exceptions, "AgentException")
    assert not hasattr(exceptions, "ConfigException")
    assert not hasattr(exceptions, "ToolException")


def test_runtime_and_development_requirements_are_separated():
    runtime_requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    dev_requirements = (PROJECT_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "pydantic>=2.0.0,<3.0.0" in runtime_requirements
    assert "pytest" not in runtime_requirements
    assert "-r requirements.txt" in dev_requirements
    assert "pytest>=7.0.0" in dev_requirements


def test_pydantic_v2_serialization_is_used():
    config_source = (PROJECT_ROOT / "core" / "config.py").read_text(encoding="utf-8")
    tool_source = (PROJECT_ROOT / "tools" / "base.py").read_text(encoding="utf-8")

    assert ".dict()" not in config_source
    assert ".dict()" not in tool_source
    assert "model_dump()" in config_source
    assert "model_dump()" in tool_source


def test_example_base_url_and_cli_copy_are_normalized():
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    cli_source = (PROJECT_ROOT / "app" / "cli.py").read_text(encoding="utf-8")

    assert "LLM_BASE_URL=https://api.siliconflow.cn/v1\n" in env_example
    assert "Initiailizing" not in cli_source
    assert "Initializing Agent Protocol" in cli_source
