"""Prompt formatting for project skills."""

from __future__ import annotations

from typing import Iterable

from extensions.skills.loader import SkillMeta


def format_skills_for_prompt(skills: Iterable[SkillMeta], char_budget: int) -> str:
    items = sorted(list(skills), key=lambda skill: skill.name)
    if not items:
        return "(none)"

    lines: list[str] = []
    used = 0
    for skill in items:
        line = f"- {skill.name}: {skill.description}"
        line_len = len(line) + 1
        if used + line_len > char_budget and lines:
            break
        if used + line_len > char_budget and not lines:
            break
        lines.append(line)
        used += line_len

    return "\n".join(lines) if lines else "(none)"


__all__ = ["format_skills_for_prompt"]
