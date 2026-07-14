from argparse import Namespace


def test_bootstrap_can_disable_optional_extensions(tmp_path):
    from app.bootstrap import build_runtime

    captured = {}

    class DummyLLM:
        def __init__(self, **kwargs):
            self.model = kwargs.get("model")
            self.provider = kwargs.get("provider")

    class DummyRegistry:
        pass

    class DummyAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    args = Namespace(
        name="code",
        system=None,
        provider="openai",
        model="gpt-test",
        api_key="test-key",
        base_url="https://example.com/v1",
        temperature=0.2,
        show_raw=False,
    )

    build_runtime(
        args,
        project_root=str(tmp_path),
        llm_class=DummyLLM,
        tool_registry_factory=DummyRegistry,
        agent_class=DummyAgent,
        extension_flags={"mcp": False, "skills": False, "tracing": False},
    )

    assert captured["enable_mcp"] is False
    assert captured["enable_skills"] is False
    assert captured["enable_tracing"] is False


def test_mcp_extension_formats_tools_for_runtime_prompt():
    from extensions.mcp.prompt import format_mcp_tools_prompt

    prompt = format_mcp_tools_prompt(
        [
            {
                "name": "fs_read",
                "description": "read a file",
                "schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "file path"}},
                    "required": ["path"],
                },
            }
        ]
    )

    assert "- fs_read: read a file" in prompt
    assert "path: string required - file path" in prompt


def test_mcp_extension_exports_split_bootstrap_and_prompt_surfaces():
    from extensions.mcp import format_mcp_tools_prompt, register_mcp_servers
    from extensions.mcp.bootstrap import register_mcp_servers as bootstrap_register
    from extensions.mcp.prompt import format_mcp_tools_prompt as prompt_format

    assert register_mcp_servers is bootstrap_register
    assert format_mcp_tools_prompt is prompt_format


def test_explicit_mcp_registration_loads_the_sdk_boundary_with_fakes(tmp_path, monkeypatch):
    from extensions.mcp import bootstrap

    captured = {}

    class FakeClientConfig:
        def __init__(self, **kwargs):
            captured["config"] = kwargs

    class FakeClient:
        def __init__(self, config):
            captured["client_config"] = config

    def fake_register(tool_registry, client, namespace):
        captured["registry"] = tool_registry
        captured["client"] = client
        captured["namespace"] = namespace
        return [{"name": "docs_search", "description": "Search docs", "schema": {}}]

    registry = object()
    monkeypatch.setattr(
        bootstrap,
        "_load_mcp_runtime",
        lambda: (FakeClient, FakeClientConfig, fake_register),
    )
    monkeypatch.setattr(
        bootstrap,
        "load_mcp_servers",
        lambda _project_root: {"docs": {"command": "fake-server", "args": ["--quiet"]}},
    )
    monkeypatch.setattr(bootstrap, "connect_mode", lambda: "startup")

    clients, tools = bootstrap.register_mcp_servers(registry, str(tmp_path))

    assert len(clients) == 1
    assert tools == [{"name": "docs_search", "description": "Search docs", "schema": {}}]
    assert captured["config"] == {
        "transport": "stdio",
        "command": "fake-server",
        "args": ["--quiet"],
        "env": {},
    }
    assert captured["registry"] is registry
    assert captured["client"] is clients[0]
    assert captured["namespace"] == "docs"
