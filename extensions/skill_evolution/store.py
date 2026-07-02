"""Skill 版本存储 — 只写 overlay，不污染源码 skills/。

路径约定::

    source:  skills/<skill_name>/SKILL.md         (git tracked, 只读)
    overlay: memory/skill_evolution/active/<skill_name>/SKILL.md
    versions:  .../<skill_name>/.evolution/versions/
    proposals: .../<skill_name>/.evolution/proposals/
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from extensions.skill_evolution.types import PatchOp, SkillVersionMeta
from extensions.skill_evolution.patcher import apply_patch


class SkillVersionStore:
    def __init__(self, source_skills_dir: Path, overlay_dir: Path):
        self._source_skills_dir = source_skills_dir.resolve()
        self._overlay_dir = overlay_dir.resolve()

    def _source_skill_path(self, skill_name: str) -> Path:
        return self._source_skills_dir / skill_name / "SKILL.md"

    def _overlay_skill_path(self, skill_name: str) -> Path:
        return self._overlay_dir / skill_name / "SKILL.md"

    def _evolution_dir(self, skill_name: str) -> Path:
        return self._overlay_dir / skill_name / ".evolution"

    def _versions_dir(self, skill_name: str) -> Path:
        return self._evolution_dir(skill_name) / "versions"

    def _proposals_dir(self, skill_name: str) -> Path:
        return self._evolution_dir(skill_name) / "proposals"

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def ensure_overlay_exists(self, skill_name: str) -> Path:
        target = self._overlay_skill_path(skill_name)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            source = self._source_skill_path(skill_name)
            if source.exists():
                shutil.copy2(source, target)
        return target

    def snapshot_current(self, skill_name: str) -> str:
        self._versions_dir(skill_name).mkdir(parents=True, exist_ok=True)
        ver = self._next_version(skill_name)
        src = self._overlay_skill_path(skill_name)
        dst = self._versions_dir(skill_name) / f"{ver}.md"
        if src.exists():
            shutil.copy2(src, dst)
        return ver

    def apply_patch(self, skill_name: str, patch: PatchOp) -> str:
        content = self.read_skill(skill_name)
        new_content = apply_patch(content, patch)
        if new_content is None:
            raise ValueError(f"Patch application failed for skill '{skill_name}'")
        ver = self._next_version(skill_name)
        ver_dir = self._versions_dir(skill_name)
        ver_dir.mkdir(parents=True, exist_ok=True)
        (ver_dir / f"{ver}.md").write_text(new_content, encoding="utf-8")
        self._overlay_skill_path(skill_name).write_text(new_content, encoding="utf-8")
        return ver

    def create_candidate(self, skill_name: str, content: str, version: str):
        self._overlay_skill_path(skill_name).write_text(content, encoding="utf-8")

    def apply_candidate_as_stable(self, skill_name: str, version: str):
        src = self._overlay_skill_path(skill_name)
        if not src.exists():
            raise FileNotFoundError(
                f"Cannot promote candidate for skill '{skill_name}': "
                f"overlay file does not exist. The candidate may have been removed externally."
            )
        ver = self._next_version(skill_name)
        self._versions_dir(skill_name).mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, self._versions_dir(skill_name) / f"{ver}.md")
        return ver

    def restore_version(self, skill_name: str, version: str):
        if version == "v0":
            source = self._source_skill_path(skill_name)
            if not source.exists():
                raise FileNotFoundError(f"Source SKILL.md not found for '{skill_name}'")
            self._overlay_skill_path(skill_name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, self._overlay_skill_path(skill_name))
            return
        src = self._versions_dir(skill_name) / f"{version}.md"
        if not src.exists():
            raise FileNotFoundError(
                f"Version '{version}' not found for skill '{skill_name}'. "
                f"Cannot restore to a version that was never snapshotted."
            )
        shutil.copy2(src, self._overlay_skill_path(skill_name))

    def get_current_version(self, skill_name: str) -> str:
        versions = self._list_version_numbers(skill_name)
        return versions[-1] if versions else "v0"

    def read_skill(self, skill_name: str) -> str:
        overlay = self._overlay_skill_path(skill_name)
        if overlay.exists():
            return overlay.read_text(encoding="utf-8")
        source = self._source_skill_path(skill_name)
        if source.exists():
            return source.read_text(encoding="utf-8")
        raise FileNotFoundError(f"No SKILL.md for '{skill_name}'")

    def get_lkg_version(self, skill_name: str) -> str:
        versions = self._list_version_numbers(skill_name)
        for v in reversed(versions):
            if not v.endswith("-candidate"):
                return v
        return "v0"

    def list_versions(self, skill_name: str) -> list[SkillVersionMeta]:
        result: list[SkillVersionMeta] = []
        ver_dir = self._versions_dir(skill_name)
        if not ver_dir.exists():
            return result
        meta_path = ver_dir / "meta.json"
        if meta_path.exists():
            data = json.loads(meta_path.read_text())
            for item in data:
                result.append(SkillVersionMeta(**item))
        return sorted(result, key=lambda m: m.version)

    def save_metadata(self, skill_name: str, meta: SkillVersionMeta):
        ver_dir = self._versions_dir(skill_name)
        ver_dir.mkdir(parents=True, exist_ok=True)
        meta_path = ver_dir / "meta.json"
        items: list[dict] = []
        if meta_path.exists():
            items = json.loads(meta_path.read_text())
        items.append({
            "skill_id": meta.skill_id,
            "version": meta.version,
            "parent_version": meta.parent_version,
            "state": meta.state.value if hasattr(meta.state, 'value') else meta.state,
            "proposal_id": meta.proposal_id,
            "source_type": meta.source_type,
        })
        meta_path.write_text(json.dumps(items, ensure_ascii=False, indent=2))

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _list_version_numbers(self, skill_name: str) -> list[str]:
        ver_dir = self._versions_dir(skill_name)
        if not ver_dir.exists():
            return []
        nums: list[str] = []
        for f in sorted(ver_dir.glob("*.md")):
            stem = f.stem
            if stem.startswith("v"):
                nums.append(stem)
        return sorted(nums, key=_parse_version_key)

    def _next_version(self, skill_name: str) -> str:
        existing = self._list_version_numbers(skill_name)
        if not existing:
            return "v1"
        last = existing[-1]
        base = last.replace("-candidate", "")
        try:
            num = int(base[1:])
        except ValueError:
            num = 0
        return f"v{num + 1}"


def _parse_version_key(v: str) -> tuple:
    v = v.replace("-candidate", "")
    try:
        num = int(v[1:])
    except (ValueError, IndexError):
        num = 0
    return (num,)


__all__ = ["SkillVersionStore"]
