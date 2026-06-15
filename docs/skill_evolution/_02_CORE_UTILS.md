# Skill Evolution — 基础工具层

**文件：** `extensions/skill_evolution/patcher.py`, `extensions/skill_evolution/validator.py`, `extensions/skill_evolution/store.py`, `extensions/skills/loader.py` (改动)

---

## 1. patcher.py — Markdown 段落级补丁器

### 1.1 接口

```python
def apply_patch(content: str, patch: PatchOp) -> str | None:
    """对 Markdown 内容应用补丁。失败返回 None。"""

def locate_section(content: str, heading: str) -> tuple[int, int] | None:
    """定位标题对应的段落区间 (start_line, end_line)，返回 None 表示未找到。"""

def replace_text(content: str, old: str, new: str) -> str | None:
    """在全文范围内精确匹配 old_text 并替换为 new_text。"""

def insert_after_section(content: str, heading: str, new_text: str) -> str | None:
    """在目标标题对应的整个段落之后插入 new_text。"""

def append_to_end(content: str, new_text: str) -> str:
    """追加到文件末尾，确保前后有空行分隔。"""
```

### 1.2 行为约定

- 段落边界：以 `# `、`## `、`### ` 开头的行视为标题。下一个同级或上级标题前的内容属于该段落。
- `replace`：在目标段落内精确匹配 `old_text`（含原始缩进），替换为 `new_text`。全文中 `old_text` 应唯一匹配。
- `insert_after`：在目标段落最后一个非空行之后插入，保留 2 个空行分隔。
- `append`：在文件末尾追加，自动添加空行分隔。
- 所有操作失败返回 `None`（标题不存在、old_text 不匹配等），调用方负责处理。

---

## 2. validator.py — Proposal 校验

**文件：** `extensions/skill_evolution/validator.py`

### 2.1 接口

```python
def validate_proposal(proposal: Proposal, skill_content: str) -> bool:
    """校验 Proposal 是否可应用。返回 False 表示不可应用，应跳过。"""
```

### 2.2 校验规则

```python
def validate_proposal(proposal: Proposal, skill_content: str) -> bool:
    # 1. patch_type 必须是合法值
    if proposal.patch.patch_type not in ("replace", "insert_after", "append"):
        return False

    # 2. target_section 必须存在于 skill_content 中（append 除外）
    if proposal.patch.patch_type != "append":
        if locate_section(skill_content, proposal.patch.target_section) is None:
            return False

    # 3. replace 时 old_text 必须在目标段落中存在
    if proposal.patch.patch_type == "replace":
        if not proposal.patch.old_text:
            return False
        section_range = locate_section(skill_content, proposal.patch.target_section)
        if section_range:
            section_text = "\n".join(skill_content.splitlines()[section_range[0]:section_range[1]])
            if proposal.patch.old_text not in section_text:
                return False

    # 4. new_text 不能为空
    if not proposal.patch.new_text:
        return False

    return True
```

---

## 3. store.py — Skill 版本存储

### 3.1 路径约定

```
源码:       skills/<skill_name>/SKILL.md       (git tracked, 只读)
overlay:    memory/skill_evolution/active/<skill_name>/SKILL.md
版本目录:   memory/skill_evolution/active/<skill_name>/.evolution/versions/
Proposal:   memory/skill_evolution/active/<skill_name>/.evolution/proposals/
```

### 3.2 接口

```python
class SkillVersionStore:
    def __init__(self, source_skill_path: Path, overlay_dir: Path):
        """
        source_skill_path: skills/<name>/SKILL.md 的绝对路径
        overlay_dir:       memory/skill_evolution/active/ 的绝对路径
        """

    def ensure_overlay_exists(self, skill_name: str) -> Path:
        """首次开启时，复制源码 Skill 到 overlay 目录。已存在则跳过。返回 overlay SKILL.md 路径。"""

    def snapshot_current(self, skill_name: str) -> str:
        """复制 overlay SKILL.md 到 .evolution/versions/v{N}.md。返回新版本号。"""

    def apply_patch(self, skill_name: str, patch: PatchOp) -> str:
        """修改 overlay SKILL.md → snapshot → 返回新版本号。"""

    def create_candidate(self, skill_name: str, content: str, version: str):
        """将 Candidate 内容写入 overlay SKILL.md，不 snapshot（在 apply_patch 之前已 snapshot）。"""

    def apply_candidate_as_stable(self, skill_name: str, version: str):
        """将 Candidate 版本的 overlay SKILL.md 重命名为去掉 -candidate 后缀的稳定版本。"""

    def restore_version(self, skill_name: str, version: str):
        """从 .evolution/versions/v{N}.md 恢复到 overlay SKILL.md。"""

    def get_current_version(self, skill_name: str) -> str:
        """返回当前 overlay SKILL.md 对应的版本号。"""

    def read_skill(self, skill_name: str) -> str:
        """读取 overlay SKILL.md 的完整内容。如果 overlay 不存在，读取源码 SKILL.md。"""

    def get_lkg_version(self, skill_name: str) -> str:
        """返回 Last Known Good 版本号（最近一个 stable 快照）。"""

    def list_versions(self, skill_name: str) -> list[SkillVersionMeta]:
        """列出该 Skill 的所有版本（按版本号排序）。"""

    def save_metadata(self, skill_name: str, meta: SkillVersionMeta):
        """保存版本元数据到 .evolution/versions/meta.json。"""
```

### 3.3 版本号策略

```
v1              # 初始快照
v2              # 第一次 Hotfix 或晋升
v3-candidate    # Agent Proposal 创建的 Candidate
v3              # Candidate 晋升后的稳定版本
v4              # 下一次 Hotfix
...
```

整数自增，不依赖时间戳。

---

## 4. SkillLoader overlay 扩展

### 4.1 改动点

`extensions/skills/loader.py` — `SkillLoader` 新增 overlay 支持：

```python
class SkillLoader:
    def __init__(self, project_root: str, skills_dir: str = "skills"):
        ...
        self._overlay_dir: Path | None = None   # ← 新增

    def set_overlay_dir(self, path: Path | None):
        """设置 overlay 目录。设置后清除缓存，下次扫描重新加载。"""
        self._overlay_dir = path
        self._skills.clear()

    def scan(self) -> List[SkillMeta]:
        """
        扫描逻辑（改前：只扫 skills_dir）：
        1. 先扫 skills_dir/ 下的所有 SKILL.md
        2. 再扫 overlay_dir/ 下的所有 SKILL.md（如果存在）
        3. 同名 Skill 以 overlay 为准
        4. 返回合并去重后的 SkillMeta 列表
        """
        files: dict[str, Path] = {}
        # 先扫源码目录
        for path in Path(self._project_root, self._skills_dir).rglob("SKILL.md"):
            key = str(path.relative_to(Path(self._project_root, self._skills_dir)))
            files[key] = path
        # 再扫 overlay 目录，同名覆盖
        if self._overlay_dir and self._overlay_dir.exists():
            for path in self._overlay_dir.rglob("SKILL.md"):
                key = str(path.relative_to(self._overlay_dir))
                files[key] = path  # overlay 覆盖

        skills = []
        for path in sorted(files.values()):
            meta = self._parse_skill_file(path)  # 已有的 frontmatter 解析逻辑
            if meta:
                skills.append(meta)
        self._skills = skills
        return skills
```

> **注意：** 现有代码中 `scan()` 方法内联了 `rglob("SKILL.md")` 扫描逻辑，不存在独立的 `_iter_skill_files()` 方法。overlay 逻辑直接插入 `scan()` 内部，替换原有的单目录扫描为双目录合并扫描。

### 4.2 行为保证

- 未调用 `set_overlay_dir()` → 行为完全不变，只读 `skills/` 目录
- 调用后 → overlay 存在的 Skill 覆盖源码版本；overlay 不存在的 Skill 仍从源码读取
- `refresh_if_stale()` 的 mtime 检测同时考虑源码和 overlay 两个目录
