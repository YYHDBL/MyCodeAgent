"""Proposal 校验器。

在校验阶段确保 Proposal 引用的 target_section 存在于当前 Skill 内容中，
old_text 可在段落内完成匹配，且 patch_type / new_text 合法。
"""

from __future__ import annotations

from extensions.skill_evolution.types import Proposal
from extensions.skill_evolution.patcher import locate_section


def validate_proposal(proposal: Proposal, skill_content: str) -> bool:
    pt = proposal.patch.patch_type
    if pt not in ("replace", "insert_after", "append"):
        return False

    if pt != "append":
        if locate_section(skill_content, proposal.patch.target_section) is None:
            return False

    if pt == "replace":
        if not proposal.patch.old_text:
            return False
        section_range = locate_section(skill_content, proposal.patch.target_section)
        if section_range is None:
            return False
        section_text = "\n".join(skill_content.splitlines()[section_range[0] : section_range[1]])
        if proposal.patch.old_text not in section_text:
            return False

    if not proposal.patch.new_text:
        return False

    return True


__all__ = ["validate_proposal"]
