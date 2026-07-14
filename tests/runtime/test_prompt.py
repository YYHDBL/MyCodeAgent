from runtime.prompt_builder import ContextBuilder


def test_runtime_prompt_builder_module_exposes_context_builder():
    from runtime.prompt_builder import ContextBuilder as CanonicalContextBuilder

    assert CanonicalContextBuilder is ContextBuilder


class _DummyToolRegistry:
    def get_disabled_tools(self):
        return []


def test_context_builder_injects_skill_prompt_and_runtime_blocks(tmp_path):
    agents_dir = tmp_path / "prompts" / "agents_prompts"
    tools_dir = tmp_path / "prompts" / "tools_prompts"
    agents_dir.mkdir(parents=True)
    tools_dir.mkdir(parents=True)

    (agents_dir / "L1_system_prompt.py").write_text('system_prompt = "base\\n{tools}"', encoding="utf-8")
    (tools_dir / "tooling.py").write_text(
        'example_prompt = "Skills: {{available_skills}}"',
        encoding="utf-8",
    )

    builder = ContextBuilder(
        tool_registry=_DummyToolRegistry(),
        project_root=str(tmp_path),
        skills_prompt="skill-a",
    )
    builder.set_runtime_system_blocks(["runtime block"])

    messages = builder.get_system_messages()

    assert "skill-a" in "\n".join(message["content"] for message in messages)
    assert messages[-1]["content"] == "runtime block"


def test_context_builder_exposes_prompt_assembly_fingerprints(tmp_path):
    agents_dir = tmp_path / "prompts" / "agents_prompts"
    tools_dir = tmp_path / "prompts" / "tools_prompts"
    agents_dir.mkdir(parents=True)
    tools_dir.mkdir(parents=True)

    (agents_dir / "L1_system_prompt.py").write_text('system_prompt = "base\\n{tools}"', encoding="utf-8")
    (tools_dir / "tooling.py").write_text('example_prompt = "Tool contract"', encoding="utf-8")

    builder = ContextBuilder(tool_registry=_DummyToolRegistry(), project_root=str(tmp_path))
    assembly = builder.get_prompt_assembly()

    assert assembly.constitution_fingerprint
    assert assembly.tool_contracts_fingerprint
    assert assembly.system_fingerprint
    assert assembly.stable_messages == builder.get_system_messages()
