"""Regression contracts for the lean single-agent startup path."""

from __future__ import annotations

import json
import builtins


def test_runtime_exposes_no_optional_project_memory_capability(tmp_path):
    """Project memory is not a hidden opt-in in the lean product surface."""

    from app.cli import build_parser
    from core.config import Config
    from runtime.host import CodeAgent
    from tools.registry import ToolRegistry

    class DummyLLM:
        provider = "openai"
        model = "test-model"

    config = Config()
    agent = CodeAgent(
        name="code",
        llm=DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        config=config,
    )

    assert "long_term_memory_enabled" not in Config.model_fields
    assert not hasattr(agent, "long_term_memory_store")
    assert "Memory" not in {
        tool["function"]["name"] for tool in agent.tool_registry.get_openai_tools()
    }
    try:
        build_parser().parse_args(["--enable-long-term-memory"])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover - makes the capability-removal contract explicit
        raise AssertionError("removed project-memory flag was accepted")

def test_config_defaults_are_the_minimal_runtime_path():
    from core.config import Config

    config = Config()

    assert config.enable_mcp is False
    assert config.enable_verification_agent is False
    assert config.enable_skills is True
    assert config.skills_refresh_on_call is False
    assert config.enable_tracing is True


def test_config_reads_only_canonical_optional_feature_environment_variables(monkeypatch):
    from core.config import Config

    monkeypatch.setenv("ENABLE_MCP", "true")
    monkeypatch.setenv("ENABLE_VERIFICATION_AGENT", "true")
    monkeypatch.setenv("ENABLE_SKILLS", "false")
    monkeypatch.setenv("SKILLS_REFRESH_ON_CALL", "true")
    monkeypatch.setenv("ENABLE_TRACING", "false")

    config = Config.from_env()

    assert config.enable_mcp is True
    assert config.enable_verification_agent is True
    assert config.enable_skills is False
    assert config.skills_refresh_on_call is True
    assert config.enable_tracing is False


def test_cli_positive_extension_flags_override_environment_once(tmp_path, monkeypatch):
    from app.bootstrap import build_runtime
    from app.cli import build_parser

    monkeypatch.setenv("ENABLE_MCP", "false")
    monkeypatch.setenv("ENABLE_VERIFICATION_AGENT", "false")

    captured = {}

    class DummyLLM:
        def __init__(self, **kwargs):
            self.model = kwargs.get("model")
            self.provider = kwargs.get("provider")

    class DummyAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    args = build_parser().parse_args(
        [
            "--enable-mcp",
            "--enable-verification-agent",
        ]
    )
    build_runtime(
        args,
        project_root=str(tmp_path),
        llm_class=DummyLLM,
        tool_registry_factory=object,
        agent_class=DummyAgent,
    )

    config = captured["config"]
    assert config.enable_mcp is True
    assert config.enable_verification_agent is True
    assert captured["enable_mcp"] is True
    assert captured["enable_skills"] is config.enable_skills
    assert captured["enable_tracing"] is config.enable_tracing


def test_default_host_startup_creates_no_optional_runtime_services(tmp_path, monkeypatch):
    from core.config import Config
    from runtime.host import CodeAgent
    from tools.registry import ToolRegistry

    class DummyLLM:
        provider = "openai"
        model = "test-model"

    def fail_mcp(self):
        raise AssertionError("MCP must not initialize on default startup")

    monkeypatch.setattr(CodeAgent, "_register_mcp_tools", fail_mcp)
    agent = CodeAgent(
        name="code",
        llm=DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        config=Config(),
    )

    assert agent.enable_mcp is False
    assert not hasattr(agent, "completion_verifier")


def test_default_host_exposes_the_bounded_seven_tool_stable_schema(tmp_path):
    from core.config import Config
    from runtime.host import CodeAgent
    from tools.registry import ToolRegistry

    class DummyLLM:
        provider = "openai"
        model = "test-model"

    agent = CodeAgent(
        name="code",
        llm=DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        config=Config(),
    )

    assert [tool["function"]["name"] for tool in agent.tool_registry.get_openai_tools()] == [
        "Bash",
        "Edit",
        "Glob",
        "Grep",
        "Read",
        "Task",
        "TodoWrite",
    ]


def test_default_host_defers_subagent_launcher_until_task_is_used(tmp_path, monkeypatch):
    from core.config import Config
    from runtime.host import CodeAgent
    from tools.registry import ToolRegistry
    import runtime.factory as runtime_factory

    class DummyLLM:
        provider = "openai"
        model = "test-model"

    def fail_launcher(*_args, **_kwargs):
        raise AssertionError("default startup must not construct a subagent launcher")

    monkeypatch.setattr(runtime_factory, "SubagentLauncher", fail_launcher)

    agent = CodeAgent(
        name="code",
        llm=DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        config=Config(),
    )

    assert agent.subagent_launcher is None
    assert agent.tool_registry.get_tool("Task") is not None


def test_task_constructs_the_deferred_launcher_on_first_valid_delegation(tmp_path, monkeypatch):
    from core.config import Config
    from runtime.host import CodeAgent
    from runtime.subagents import ExploreResult, SubagentLaunchResult, SubagentStatus
    from tools.registry import ToolRegistry
    import runtime.factory as runtime_factory

    class DummyLLM:
        provider = "openai"
        model = "test-model"

    constructed = []

    class RecordingLauncher:
        def __init__(self, **_kwargs):
            constructed.append(self)

        def launch(self, _request):
            return SubagentLaunchResult(
                status=SubagentStatus.COMPLETED,
                profile_name="explore",
                child_session_id="child-session",
                child_run_id="child-run",
                result=ExploreResult(
                    status=SubagentStatus.COMPLETED,
                    summary="found it",
                    findings=(),
                    evidence=(),
                    unresolved_questions=(),
                    tool_usage={},
                    terminal_reason="completed",
                ),
                elapsed_ms=0,
            )

    monkeypatch.setattr(runtime_factory, "SubagentLauncher", RecordingLauncher)
    agent = CodeAgent(
        name="code",
        llm=DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        config=Config(),
    )

    assert constructed == []
    from tools.base import serialize_tool_result

    result = json.loads(serialize_tool_result(
        agent.tool_registry.get_tool("Task").run(
            {
                "description": "inspect",
                "prompt": "inspect the project",
                "subagent_type": "explore",
            }
        )
    ))

    assert result["status"] == "success"
    assert len(constructed) == 1
    assert agent.subagent_launcher is constructed[0]


def test_default_no_skill_project_avoids_skills_extension_and_skill_tool(tmp_path, monkeypatch):
    from core.config import Config
    from runtime.host import CodeAgent
    from tools.registry import ToolRegistry

    class DummyLLM:
        provider = "openai"
        model = "test-model"

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "extensions.skills":
            raise AssertionError("default startup must not import the skills extension")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    agent = CodeAgent(
        name="code",
        llm=DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        config=Config(),
    )

    assert agent._skill_loader is None
    assert agent.tool_registry.get_tool("Skill") is None


def test_project_skill_discovers_the_lazy_skills_capability(tmp_path):
    from core.config import Config
    from runtime.host import CodeAgent
    from tools.registry import ToolRegistry

    class DummyLLM:
        provider = "openai"
        model = "test-model"

    skill_file = tmp_path / "skills" / "demo" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: demo\ndescription: Demo skill\n---\nUse demo.\n",
        encoding="utf-8",
    )

    agent = CodeAgent(
        name="code",
        llm=DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        config=Config(),
    )

    assert agent._skill_loader is not None
    assert agent.tool_registry.get_tool("Skill") is not None
    assert "demo" in agent._skills_prompt


def test_skill_tool_does_not_rescan_by_default_but_allows_explicit_refresh(tmp_path):
    from extensions.skills.loader import SkillMeta
    from tools.builtin.skill import SkillTool

    skill_path = tmp_path / "skills" / "demo" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "---\nname: demo-skill\ndescription: demo\n---\nUse this skill.\n",
        encoding="utf-8",
    )

    class RecordingLoader:
        def __init__(self):
            self.refresh_values = []

        def get_skill(self, name, *, refresh=False):
            self.refresh_values.append(refresh)
            return SkillMeta(
                name=name,
                description="demo",
                path=str(skill_path),
                base_dir="skills/demo",
                mtime=0,
            )

    default_loader = RecordingLoader()
    default_tool = SkillTool(
        project_root=tmp_path,
        skill_loader=default_loader,
        refresh_on_call=False,
    )
    from tools.base import serialize_tool_result

    assert json.loads(serialize_tool_result(default_tool.run({"name": "demo-skill"})))["status"] == "success"
    assert default_loader.refresh_values == [False]

    refreshing_loader = RecordingLoader()
    refreshing_tool = SkillTool(
        project_root=tmp_path,
        skill_loader=refreshing_loader,
        refresh_on_call=True,
    )
    assert json.loads(serialize_tool_result(refreshing_tool.run({"name": "demo-skill"})))["status"] == "success"
    assert refreshing_loader.refresh_values == [True]


def test_trace_logger_writes_only_jsonl(tmp_path):
    from core.config import Config
    from extensions.tracing.logger import TraceLogger

    assert "trace_html_enabled" not in Config.model_fields

    trace = TraceLogger(session_id="jsonl", trace_dir=tmp_path)
    trace.log_event("run_start", {"run_id": 1}, step=0)
    trace.finalize()

    assert trace._filepath is not None
    assert trace._filepath.read_text(encoding="utf-8")
    assert {path.suffix for path in tmp_path.iterdir()} == {".jsonl"}
