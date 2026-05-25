from runtime.host import CodeAgent
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


def test_skills_extension_scans_project_skills_for_prompt(tmp_path):
    from extensions.skills import SkillLoader
    from extensions.skills.prompt import format_skills_for_prompt

    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo description\n---\nBody\n",
        encoding="utf-8",
    )

    loader = SkillLoader(str(tmp_path))
    skills = loader.scan()

    assert [skill.name for skill in skills] == ["demo-skill"]
    assert "- demo-skill: demo description" in format_skills_for_prompt(skills, 1000)


def test_skills_extension_exports_loader_and_prompt_surfaces():
    from extensions.skills import SkillLoader, format_skills_for_prompt
    from extensions.skills.loader import SkillLoader as LoaderClass
    from extensions.skills.prompt import format_skills_for_prompt as prompt_format

    assert SkillLoader is LoaderClass
    assert format_skills_for_prompt is prompt_format
