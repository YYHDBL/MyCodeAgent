"""Skills extension surface."""

from extensions.skills.loader import SkillLoader, SkillMeta
from extensions.skills.prompt import format_skills_for_prompt

__all__ = ["SkillLoader", "SkillMeta", "format_skills_for_prompt"]
