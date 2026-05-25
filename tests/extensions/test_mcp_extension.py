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
        teammate_mode=None,
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
    from extensions.mcp import format_mcp_tools_prompt

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
