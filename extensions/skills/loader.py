"""Skill loader for project-local skills."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass
class SkillMeta:
    name: str
    description: str
    path: str
    base_dir: str
    mtime: float


class SkillLoader:
    """Scan and cache skills stored under project_root/skills."""

    def __init__(self, project_root: str, skills_dir: str = "skills"):
        self._project_root = Path(project_root).resolve()
        self._skills_dir = (self._project_root / skills_dir).resolve()
        self._overlay_dir: Path | None = None
        self._skills: Dict[str, SkillMeta] = {}
        self._last_scan_mtime: float = 0.0
        self._last_scan_count: int = 0

    def set_overlay_dir(self, path: Path | None):
        self._overlay_dir = path
        self._skills.clear()

    def scan(self) -> List[SkillMeta]:
        """Scan skills directory and refresh cache.

        Overlay 目录（若已设置）中存在的同名 Skill 覆盖源码版本。
        """
        files: dict[str, Path] = {}
        for path in self._iter_skill_files():
            key = str(path.relative_to(self._skills_dir))
            files[key] = path
        if self._overlay_dir and self._overlay_dir.exists():
            for path in sorted(self._overlay_dir.rglob("SKILL.md")):
                key = str(path.relative_to(self._overlay_dir))
                files[key] = path

        skills: Dict[str, SkillMeta] = {}
        max_mtime = 0.0
        count = 0

        for path in sorted(files.values()):
            count += 1
            try:
                stat = path.stat()
                max_mtime = max(max_mtime, stat.st_mtime)
            except OSError:
                continue

            parsed = self._parse_skill_file(path)
            if not parsed:
                continue

            meta = parsed
            if meta.name in skills:
                pass
            skills[meta.name] = meta

        self._skills = skills
        self._last_scan_mtime = max_mtime
        self._last_scan_count = count
        return self.list_skills(refresh=False)

    def refresh_if_stale(self) -> List[SkillMeta]:
        """Refresh cache if skill files changed."""
        if not self._skills:
            return self.scan()

        current_max_mtime, current_count = self._get_skills_state()
        if current_max_mtime != self._last_scan_mtime or current_count != self._last_scan_count:
            return self.scan()
        return self.list_skills(refresh=False)

    def list_skills(self, refresh: bool = False) -> List[SkillMeta]:
        if refresh:
            self.refresh_if_stale()
        return sorted(self._skills.values(), key=lambda s: s.name)

    def get_skill(self, name: str, refresh: bool = False) -> Optional[SkillMeta]:
        if refresh:
            self.refresh_if_stale()
        return self._skills.get(name)

    def format_skills_for_prompt(self, char_budget: int) -> str:
        from extensions.skills.prompt import format_skills_for_prompt

        return format_skills_for_prompt(self.list_skills(refresh=False), char_budget)

    def _iter_skill_files(self) -> List[Path]:
        if not self._skills_dir.exists():
            return []
        return sorted(self._skills_dir.rglob("SKILL.md"))

    def _get_skills_state(self) -> Tuple[float, int]:
        max_mtime = 0.0
        count = 0
        for path in self._iter_skill_files():
            count += 1
            try:
                stat = path.stat()
                max_mtime = max(max_mtime, stat.st_mtime)
            except OSError:
                continue
        if self._overlay_dir and self._overlay_dir.exists():
            for path in self._overlay_dir.rglob("SKILL.md"):
                count += 1
                try:
                    stat = path.stat()
                    max_mtime = max(max_mtime, stat.st_mtime)
                except OSError:
                    continue
        return max_mtime, count

    def _parse_skill_file(self, path: Path) -> Optional[SkillMeta]:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return None

        parsed = _parse_frontmatter(content)
        if not parsed:
            return None

        frontmatter, _body = parsed
        name = (frontmatter.get("name") or "").strip()
        description = (frontmatter.get("description") or "").strip()

        if not name or not description:
            return None
        if not _SKILL_NAME_PATTERN.match(name):
            return None

        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0

        try:
            base_dir = str(path.parent.relative_to(self._project_root)) or "."
        except ValueError:
            base_dir = str(path.parent)
        return SkillMeta(
            name=name,
            description=description,
            path=str(path),
            base_dir=base_dir,
            mtime=mtime,
        )


def _parse_frontmatter(content: str) -> Optional[Tuple[Dict[str, str], str]]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return None

    frontmatter_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1 :])
    frontmatter: Dict[str, str] = {}

    for line in frontmatter_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            return None
        key, value = stripped.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip("\"'")

    return frontmatter, body


__all__ = ["SkillLoader", "SkillMeta"]
