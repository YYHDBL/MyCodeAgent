from argparse import Namespace


def test_root_entrypoint_delegates_to_app_cli():
    import app.cli
    import main

    assert main.main is app.cli.main


def test_bootstrap_defaults_to_codeagent_runtime_host():
    import app.bootstrap
    from runtime.agent_host import CodeAgent

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
        teammate_mode=None,
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
