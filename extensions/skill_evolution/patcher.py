"""Markdown段落级补丁器。

定位标题边界，对 Skill Markdown 文件执行 replace / insert_after / append 等
局部修改，不涉及全文重写。
"""

from __future__ import annotations

from extensions.skill_evolution.types import PatchOp


def locate_section(content: str, heading: str) -> tuple[int, int] | None:
    """定位标题对应的段落区间 ``(start_line, end_line)``，0-based。

    段落边界规则：
    遇到下一个同级或上级标题时，当前段落结束。
    标题行的判断以 ``# `` ``## `` ``### `` 开头为依据。
    返回 ``None`` 表示标题不存在。
    """
    lines = content.splitlines()
    heading_line = "## " + heading
    found_at: int | None = None
    heading_level = 2  # 默认 ## 级别
    for i, line in enumerate(lines):
        if line.strip() == heading_line:
            found_at = i
            heading_level = _heading_depth(line)
            break
        if line.strip() == "# " + heading:
            found_at = i
            heading_level = 1
            break
        if line.strip() == "### " + heading:
            found_at = i
            heading_level = 3
            break
    if found_at is None:
        return None

    end_at = len(lines)
    for j in range(found_at + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped.startswith("#") and _heading_depth(stripped) <= heading_level:
            end_at = j
            break
    return found_at, end_at


def _heading_depth(line: str) -> int:
    st = line.strip()
    depth = 0
    for ch in st:
        if ch == "#":
            depth += 1
        else:
            break
    return depth


def replace_text(content: str, old: str, new: str) -> str | None:
    """全文精确匹配 *old* 并替换为 *new*。
    
    要求 *old* 唯一出现；返回 ``None`` 表示替换失败。
    """
    count = content.count(old)
    if count == 0:
        return None
    if count > 1:
        return None
    return content.replace(old, new, 1)


def insert_after_section(content: str, heading: str, new_text: str) -> str | None:
    """在目标标题对应段落的最后一个非空行之后插入 *new_text*，
    保留 2 个空行分隔。返回 ``None`` 表示标题未找到。
    """
    section = locate_section(content, heading)
    if section is None:
        return None
    lines = content.splitlines()
    end = section[1]
    # 跳过末尾空行，找到最后一个非空行
    while end > section[0] and lines[end - 1].strip() == "":
        end -= 1
    out = lines[:end] + [""] + new_text.strip().splitlines() + [""] + lines[section[1]:]
    return "\n".join(out)


def append_to_end(content: str, new_text: str) -> str:
    """追加到文件末尾；自动追加一个空行加内容再加空行。"""
    return content.rstrip("\n") + "\n\n" + new_text.strip() + "\n"


def apply_patch(content: str, patch: PatchOp) -> str | None:
    """根据 patch_type 分发到对应函数。失败返回 ``None``。"""
    pt = patch.patch_type
    if pt == "replace":
        return replace_text(content, patch.old_text, patch.new_text)
    if pt == "insert_after":
        return insert_after_section(content, patch.target_section, patch.new_text)
    if pt == "append":
        return append_to_end(content, patch.new_text)
    return None


__all__ = [
    "apply_patch",
    "locate_section",
    "replace_text",
    "insert_after_section",
    "append_to_end",
]
