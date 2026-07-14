"""Stable-product boundaries for removed research systems."""

from __future__ import annotations

from pathlib import Path


STABLE_PACKAGE_DIRECTORIES = ("app", "core", "runtime", "tools", "extensions", "prompts")
FORBIDDEN_SKILL_EVOLUTION_SYMBOLS = (
    "skill_evolution",
    "enable_skill_evolution",
    "--skill-evolution",
    "SKILL_EVOLUTION",
    "_skill_evolution_manager",
    "set_overlay_dir",
    "_overlay_dir",
    "EVOLUTION_TRACE_EVENTS",
)


def test_stable_packages_do_not_reference_removed_skill_evolution_research() -> None:
    project_root = Path(__file__).resolve().parents[1]
    occurrences: list[str] = []

    for directory in STABLE_PACKAGE_DIRECTORIES:
        for path in (project_root / directory).rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            for symbol in FORBIDDEN_SKILL_EVOLUTION_SYMBOLS:
                if symbol in content:
                    occurrences.append(f"{path.relative_to(project_root)}: {symbol}")

    assert not occurrences, "Removed Skill Evolution references remain:\n" + "\n".join(occurrences)
