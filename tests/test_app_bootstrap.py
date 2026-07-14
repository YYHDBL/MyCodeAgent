from argparse import Namespace

import pytest


def test_root_entrypoint_delegates_to_app_cli():
    import app.cli
    import main

    assert main.main is app.cli.main


def test_bootstrap_defaults_to_codeagent_runtime_host():
    import app.bootstrap
    from runtime.host import CodeAgent

    assert app.bootstrap.build_runtime.__kwdefaults__["agent_class"] is CodeAgent


def test_build_runtime_constructs_dependencies(tmp_path):
    from app.bootstrap import build_runtime

    captured = {}

    class DummyLLM:
        def __init__(self, **kwargs):
            captured["llm_kwargs"] = kwargs
            self.model = kwargs["model"]
            self.provider = kwargs["provider"]

    class DummyRegistry:
        def __init__(self):
            captured["registry_created"] = True

    class DummyAgent:
        def __init__(self, **kwargs):
            captured["agent_kwargs"] = kwargs

    args = Namespace(
        name="code",
        system="system prompt",
        provider="openai",
        model="gpt-test",
        api_key="test-key",
        base_url="https://example.com/v1",
        temperature=0.25,
        show_raw=False,
    )

    runtime = build_runtime(
        args,
        project_root=str(tmp_path),
        llm_class=DummyLLM,
        tool_registry_factory=DummyRegistry,
        agent_class=DummyAgent,
    )

    assert runtime.project_root == str(tmp_path)
    assert runtime.llm.model == "gpt-test"
    assert runtime.llm.provider == "openai"
    assert runtime.config.show_react_steps is True
    assert captured["registry_created"] is True
    assert captured["llm_kwargs"]["temperature"] == 0.25
    assert captured["agent_kwargs"]["project_root"] == str(tmp_path)
    assert captured["agent_kwargs"]["system_prompt"] == "system prompt"
    assert captured["agent_kwargs"]["config"] is runtime.config
    assert captured["agent_kwargs"]["tool_registry"] is runtime.tool_registry
    assert captured["agent_kwargs"]["llm"] is runtime.llm
    assert runtime.agent is not None


def test_enabled_verification_agent_bootstraps_without_network(tmp_path):
    from app.bootstrap import build_runtime
    from core.config import Config
    from runtime.subagents import SubagentCompletionVerifier

    class EnabledConfig:
        @classmethod
        def from_env(cls):
            return Config(
                enable_verification_agent=True,
                enable_mcp=False,
                enable_skills=False,
                enable_tracing=False,
            )

    class DummyLLM:
        def __init__(self, **kwargs):
            self.model = kwargs.get("model")
            self.provider = kwargs.get("provider")

    runtime = build_runtime(
        Namespace(cwd=str(tmp_path)),
        config_class=EnabledConfig,
        llm_class=DummyLLM,
        extension_flags={"mcp": False, "skills": False, "tracing": False},
    )
    try:
        assert isinstance(runtime.agent.completion_verifier, SubagentCompletionVerifier)
    finally:
        runtime.agent.close()


def test_build_runtime_defaults_to_invocation_directory(tmp_path, monkeypatch):
    from app.bootstrap import build_runtime

    target = tmp_path / "project-a"
    target.mkdir()
    monkeypatch.chdir(target)
    captured = {}

    class DummyLLM:
        def __init__(self, **_kwargs):
            pass

    class DummyAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    runtime = build_runtime(
        Namespace(),
        llm_class=DummyLLM,
        tool_registry_factory=object,
        agent_class=DummyAgent,
    )

    assert runtime.project_root == str(target.resolve())
    assert captured["project_root"] == str(target.resolve())


@pytest.mark.parametrize("cwd_kind", ["relative", "absolute"])
def test_build_runtime_resolves_explicit_cwd_from_invocation_directory(tmp_path, monkeypatch, cwd_kind):
    from app.bootstrap import build_runtime

    invocation_root = tmp_path / "project-a"
    target = tmp_path / "project-b"
    invocation_root.mkdir()
    target.mkdir()
    monkeypatch.chdir(invocation_root)
    captured = {}

    class DummyLLM:
        def __init__(self, **_kwargs):
            pass

    class DummyAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    runtime = build_runtime(
        Namespace(cwd="../project-b" if cwd_kind == "relative" else str(target)),
        llm_class=DummyLLM,
        tool_registry_factory=object,
        agent_class=DummyAgent,
    )

    assert runtime.project_root == str(target.resolve())
    assert captured["project_root"] == str(target.resolve())


@pytest.mark.parametrize("cwd", ["missing", __file__])
def test_build_runtime_rejects_invalid_target_before_initializing_dependencies(cwd):
    from app.bootstrap import build_runtime

    initialized = []

    class DummyLLM:
        def __init__(self, **_kwargs):
            initialized.append("llm")

    class DummyRegistry:
        def __init__(self):
            initialized.append("registry")

    class DummyAgent:
        def __init__(self, **_kwargs):
            initialized.append("agent")

    with pytest.raises(ValueError, match="existing directory"):
        build_runtime(
            Namespace(cwd=cwd),
            llm_class=DummyLLM,
            tool_registry_factory=DummyRegistry,
            agent_class=DummyAgent,
        )

    assert initialized == []
