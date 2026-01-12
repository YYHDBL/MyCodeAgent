"""Skill system tests."""

from core.skills.skill_loader import SkillLoader
from tools.builtin.skill import SkillTool
from tests.utils.test_helpers import parse_response


def test_skill_loader_scans_skills(temp_project):
    temp_project.create_file(
        "skills/code-review/SKILL.md",
        """---
name: code-review
description: Review code quality
---
# Code Review
""",
    )

    loader = SkillLoader(str(temp_project.root))
    skills = loader.scan()

    assert len(skills) == 1
    assert skills[0].name == "code-review"
    assert skills[0].description == "Review code quality"


def test_skill_loader_skips_invalid_frontmatter(temp_project):
    temp_project.create_file(
        "skills/bad/SKILL.md",
        """# Missing frontmatter
content
""",
    )

    loader = SkillLoader(str(temp_project.root))
    skills = loader.scan()

    assert skills == []


def test_skill_tool_loads_and_expands_arguments(temp_project):
    temp_project.create_file(
        "skills/code-review/SKILL.md",
        """---
name: code-review
description: Review code quality
---
# Code Review

Check this file:

$ARGUMENTS
""",
    )

    loader = SkillLoader(str(temp_project.root))
    loader.scan()

    tool = SkillTool(project_root=temp_project.root, skill_loader=loader)
    response = tool.run({"name": "code-review", "args": "src/main.py"})
    parsed = parse_response(response)

    assert parsed["status"] == "success"
    data = parsed["data"]
    assert data["name"] == "code-review"
    assert "Base directory for this skill" in data["content"]
    assert "src/main.py" in data["content"]
