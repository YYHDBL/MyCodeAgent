"""
OpenCode Skills 功能分析文档
==============================

目录结构
--------
1. 概述
2. 核心数据结构
3. Skills 加载机制 (TypeScript -> Python)
4. Skills 执行流程 (TypeScript -> Python)
5. 权限系统集成
6. 文件存储格式
7. 时序图

1. 概述
-------
Skills 是 OpenCode 中用于扩展 AI Agent 能力的插件系统。它允许用户通过 Markdown
文件定义可重用的工作流程和专业知识，AI Agent 可以在适当的时候调用这些技能。

核心特点:
- 基于 Markdown 文件的简单定义格式
- 支持项目级和全局技能目录
- 与权限系统深度集成
- 作为 Tool 系统的一部分实现
- 懒加载机制，按需扫描

2. 核心数据结构
--------------
"""

from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum


class PermissionAction(Enum):
    """权限操作类型"""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass
class SkillInfo:
    """技能信息结构 (对应 TypeScript: Skill.Info)"""
    name: str           # 技能唯一标识符
    description: str    # 技能描述
    location: str       # 技能文件绝对路径


@dataclass
class PermissionRule:
    """权限规则 (对应 TypeScript: PermissionNext.Rule)"""
    permission: str     # 权限类型 (如 "skill", "edit", "bash")
    pattern: str        # 匹配模式 (支持通配符)
    action: PermissionAction  # 操作类型


@dataclass
class FrontmatterData:
    """Markdown 前置元数据"""
    name: str
    description: str


@dataclass
class ParsedMarkdown:
    """解析后的 Markdown 文件"""
    data: FrontmatterData
    content: str  # 前置元数据之后的内容


"""
3. Skills 加载机制 (TypeScript -> Python)
========================================

原文件: packages/opencode/src/skill/skill.ts

核心流程:
1. 扫描多个目录查找 SKILL.md 文件
2. 解析 Markdown 前置元数据
3. 验证必需字段
4. 构建技能索引
"""

import os
import glob
import re
from pathlib import Path
from typing import Callable, Awaitable
from functools import wraps


# Python 实现的技能加载器
class SkillLoader:
    """技能加载器 - Python 实现"""

    # 技能文件匹配模式
    OPENCODE_SKILL_PATTERN = "{skill,skills}/**/SKILL.md"
    CLAUDE_SKILL_PATTERN = "skills/**/SKILL.md"

    def __init__(self, project_dir: str, worktree_dir: Optional[str] = None):
        self.project_dir = Path(project_dir)
        self.worktree_dir = Path(worktree_dir) if worktree_dir else self.project_dir
        self._skills_cache: Dict[str, SkillInfo] = None

    def parse_markdown(self, file_path: str) -> Optional[ParsedMarkdown]:
        """
        解析 Markdown 文件 (gray-matter equivalent)
        对应: ConfigMarkdown.parse()
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 解析 YAML 前置元数据
            frontmatter_pattern = r'^---\n(.*?)\n---\n(.*)$'
            match = re.match(frontmatter_pattern, content, re.DOTALL)

            if not match:
                return None

            frontmatter_text, body_content = match.groups()

            # 简单解析 YAML (生产环境应使用 yaml 库)
            data = self._parse_simple_yaml(frontmatter_text)

            return ParsedMarkdown(
                data=FrontmatterData(
                    name=data.get('name', ''),
                    description=data.get('description', '')
                ),
                content=body_content.strip()
            )
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return None

    def _parse_simple_yaml(self, yaml_text: str) -> dict:
        """简单的 YAML 解析器"""
        result = {}
        for line in yaml_text.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                result[key.strip()] = value.strip().strip('"\'')
        return result

    def find_claude_dirs(self) -> list[Path]:
        """
        查找 .claude 目录
        对应: Filesystem.up({ targets: [".claude"], ... })
        """
        claude_dirs = []

        # 向上遍历查找 .claude 目录
        current = self.project_dir
        while current != self.worktree_dir.parent and current != current.parent:
            claude_path = current / '.claude'
            if claude_path.exists():
                claude_dirs.append(claude_path)
            current = current.parent

        # 添加全局 ~/.claude 目录
        global_claude = Path.home() / '.claude'
        if global_claude.exists():
            claude_dirs.append(global_claude)

        return claude_dirs

    def find_opencode_dirs(self) -> list[Path]:
        """查找 .opencode 配置目录"""
        opencode_dirs = []

        # 查找项目级配置目录
        current = self.project_dir
        while current != self.worktree_dir.parent and current != current.parent:
            for subdir in ['skill', 'skills']:
                opencode_path = current / '.opencode' / subdir
                if opencode_path.exists():
                    opencode_dirs.append(opencode_path)
            current = current.parent

        return opencode_dirs

    def scan_skills(self, disable_claude_skills: bool = False) -> Dict[str, SkillInfo]:
        """
        扫描所有技能目录
        对应: Skill.state() 函数
        """
        skills: Dict[str, SkillInfo] = {}

        def add_skill(file_path: str) -> None:
            parsed = self.parse_markdown(file_path)
            if not parsed:
                return

            # 验证必需字段
            if not parsed.data.name or not parsed.data.description:
                return

            # 检查重复名称
            if parsed.data.name in skills:
                print(f"Warning: duplicate skill name '{parsed.data.name}'")
                print(f"  Existing: {skills[parsed.data.name].location}")
                print(f"  Duplicate: {file_path}")

            skills[parsed.data.name] = SkillInfo(
                name=parsed.data.name,
                description=parsed.data.description,
                location=file_path
            )

        # 扫描 .claude/skills/ 目录
        if not disable_claude_skills:
            for claude_dir in self.find_claude_dirs():
                skills_dir = claude_dir / 'skills'
                if skills_dir.exists():
                    for skill_path in skills_dir.rglob('SKILL.md'):
                        add_skill(str(skill_path))

        # 扫描 .opencode/skill/ 目录
        for opencode_dir in self.find_opencode_dirs():
            for skill_path in opencode_dir.rglob('SKILL.md'):
                add_skill(str(skill_path))

        self._skills_cache = skills
        return skills

    def get_skill(self, name: str) -> Optional[SkillInfo]:
        """获取指定技能"""
        if self._skills_cache is None:
            self.scan_skills()
        return self._skills_cache.get(name)

    def all_skills(self) -> list[SkillInfo]:
        """获取所有技能"""
        if self._skills_cache is None:
            self.scan_skills()
        return list(self._skills_cache.values())


"""
4. Skills 执行流程 (TypeScript -> Python)
========================================

原文件: packages/opencode/src/tool/skill.ts

Skill 被实现为一个特殊的 Tool，执行流程如下:
1. 获取所有可用技能
2. 根据当前 Agent 的权限过滤技能
3. 生成包含可用技能列表的工具描述
4. 当 AI 调用时，验证技能存在性并请求权限
5. 加载并返回技能内容
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, TypeVar, Generic


T = TypeVar('T')


@dataclass
class ToolContext:
    """工具调用上下文"""
    agent: Optional['Agent'] = None
    session_id: Optional[str] = None


@dataclass
class ToolResult:
    """工具执行结果"""
    title: str
    output: str
    metadata: dict[str, Any]


@dataclass
class Agent:
    """Agent 信息"""
    permission: list[PermissionRule]  # Agent 的权限规则集


def wildcard_match(pattern: str, text: str) -> bool:
    """
    通配符匹配
    对应: Wildcard.match()
    支持 * 和 ? 通配符
    """
    import fnmatch
    return fnmatch.fnmatch(text, pattern)


def evaluate_permission(
    permission_type: str,
    pattern: str,
    ruleset: list[PermissionRule]
) -> PermissionRule:
    """
    评估权限规则
    对应: PermissionNext.evaluate()

    返回最后一个匹配的规则 (后定义的规则优先)
    """
    matching_rules = [
        rule for rule in ruleset
        if wildcard_match(rule.permission, permission_type) and
           wildcard_match(rule.pattern, pattern)
    ]

    if matching_rules:
        return matching_rules[-1]  # 返回最后匹配的规则

    # 默认规则: 询问用户
    return PermissionRule(
        permission=permission_type,
        pattern="*",
        action=PermissionAction.ASK
    )


class SkillTool:
    """
    Skill 工具 - Python 实现
    对应: packages/opencode/src/tool/skill.ts
    """

    def __init__(self, skill_loader: SkillLoader):
        self.skill_loader = skill_loader
        self.id = "skill"

    async def describe(self, ctx: ToolContext) -> dict:
        """
        生成工具描述，包含可用技能列表
        对应: Tool.define() 返回值的 description 部分
        """
        skills = self.skill_loader.all_skills()

        # 根据 Agent 权限过滤技能
        if ctx.agent:
            accessible_skills = [
                skill for skill in skills
                if self._is_skill_accessible(skill, ctx.agent.permission)
            ]
        else:
            accessible_skills = skills

        # 构建描述
        if len(accessible_skills) == 0:
            description = (
                "Load a skill to get detailed instructions for a specific task. "
                "No skills are currently available."
            )
        else:
            skill_list = "\n".join([
                f"  <skill>\n    <name>{s.name}</name>\n    <description>{s.description}</description>\n  </skill>"
                for s in accessible_skills
            ])
            description = (
                "Load a skill to get detailed instructions for a specific task.\n"
                "Skills provide specialized knowledge and step-by-step guidance.\n"
                "Use this when a task matches an available skill's description.\n"
                "<available_skills>\n"
                f"{skill_list}\n"
                "</available_skills>"
            )

        return {
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The skill identifier from available_skills (e.g., 'code-review' or 'category/helper')"
                    }
                },
                "required": ["name"]
            }
        }

    def _is_skill_accessible(self, skill: SkillInfo, permissions: list[PermissionRule]) -> bool:
        """检查技能是否可访问"""
        rule = evaluate_permission("skill", skill.name, permissions)
        return rule.action != PermissionAction.DENY

    async def execute(self, params: dict, ctx: ToolContext) -> ToolResult:
        """
        执行技能加载
        对应: SkillTool 的 execute 函数
        """
        skill_name = params.get("name")

        # 获取技能
        skill = self.skill_loader.get_skill(skill_name)
        if not skill:
            available = [s.name for s in self.skill_loader.all_skills()]
            raise ValueError(
                f"Skill '{skill_name}' not found. Available skills: {', '.join(available) or 'none'}"
            )

        # 请求权限 (在真实实现中会与用户交互)
        # await self._ask_permission(ctx, skill_name)

        # 加载技能内容
        parsed = self.skill_loader.parse_markdown(skill.location)
        base_dir = os.path.dirname(skill.location)

        # 格式化输出
        output = f"## Skill: {skill.name}\n\n**Base directory**: {base_dir}\n\n{parsed.content}"

        return ToolResult(
            title=f"Loaded skill: {skill.name}",
            output=output,
            metadata={
                "name": skill.name,
                "dir": base_dir
            }
        )


"""
5. 权限系统集成
--------------
"""

class PermissionSystem:
    """
    权限系统 - 简化实现
    对应: packages/opencode/src/permission/next.ts
    """

    def __init__(self):
        self.rules: list[PermissionRule] = []
        self.approved: list[PermissionRule] = []  # 用户已批准的规则

    def add_rule(self, permission: str, pattern: str, action: PermissionAction):
        """添加权限规则"""
        self.rules.append(PermissionRule(
            permission=permission,
            pattern=pattern,
            action=action
        ))

    def check(self, permission_type: str, pattern: str) -> PermissionRule:
        """检查权限"""
        # 先检查已批准的规则
        approved_rule = evaluate_permission(permission_type, pattern, self.approved)
        if approved_rule.action == PermissionAction.ALLOW:
            return approved_rule

        # 检查配置规则
        return evaluate_permission(permission_type, pattern, self.rules)

    async def ask_permission(
        self,
        permission_type: str,
        pattern: str,
        session_id: str
    ) -> bool:
        """
        请求用户权限
        对应: PermissionNext.ask()

        在真实实现中，这会通过事件总线发送请求并等待用户响应
        """
        rule = self.check(permission_type, pattern)

        if rule.action == PermissionAction.DENY:
            raise PermissionDeniedError(f"Permission denied for {permission_type}:{pattern}")

        if rule.action == PermissionAction.ALLOW:
            return True

        # ASK - 在真实实现中会等待用户响应
        # 这里简化为返回 True
        return True


class PermissionDeniedError(Exception):
    """权限被拒绝错误"""
    pass


"""
6. 文件存储格式
--------------
"""

# 示例 SKILL.md 文件
EXAMPLE_SKILL_MD = """
---
name: code-review
description: Expert code review techniques and best practices for analyzing code quality
---

# Code Review Skill

This skill provides comprehensive guidance for conducting effective code reviews.

## Review Checklist

- [ ] Verify the code meets the project's style guidelines
- [ ] Check for potential security vulnerabilities
- [ ] Assess performance implications
- [ ] Validate error handling
- [ ] Ensure proper testing coverage

## Common Issues to Look For

1. **Resource leaks**: Unclosed files, connections, etc.
2. **Race conditions**: Unprotected shared state
3. **Input validation**: Missing or insufficient checks
4. **Error handling**: Swallowed exceptions, vague messages
"""


# 文件结构示例
SKILL_DIRECTORY_STRUCTURE = """
# 项目级技能
.opencode/
└── skill/
    ├── code-review/
    │   └── SKILL.md
    └── debugging/
        └── SKILL.md

# Claude 兼容技能
.claude/
└── skills/
    ├── web-dev/
    │   └── SKILL.md
    └── api-design/
        └── SKILL.md

# 全局技能
~/.claude/
└── skills/
    └── common/
        └── SKILL.md
"""


"""
7. 使用示例与时序
----------------
"""

async def example_usage():
    """完整的使用示例"""

    # 1. 初始化技能加载器
    loader = SkillLoader(project_dir="/path/to/project")

    # 2. 扫描技能
    skills = loader.scan_skills()
    print(f"Found {len(skills)} skills:")
    for skill in skills.values():
        print(f"  - {skill.name}: {skill.description}")

    # 3. 创建权限系统
    permissions = PermissionSystem()
    permissions.add_rule("skill", "*", PermissionAction.ALLOW)

    # 4. 创建 Agent
    agent = Agent(permission=permissions.rules)

    # 5. 创建技能工具
    skill_tool = SkillTool(loader)

    # 6. 获取工具描述
    ctx = ToolContext(agent=agent)
    description = await skill_tool.describe(ctx)
    print(f"\nTool description:\n{description['description']}")

    # 7. 执行技能
    result = await skill_tool.execute({"name": "code-review"}, ctx)
    print(f"\n{result.title}")
    print(f"Content: {result.output[:100]}...")


"""
8. 时序图
---------

用户请求技能
    |
    v
AI Agent 分析请求
    |
    v
Agent 调用 skill 工具
    |
    v
SkillTool.describe() -> 获取可用技能列表
    |
    v
[权限过滤] -> 根据 Agent.permission 过滤
    |
    v
AI 选择技能并调用 skill.execute(name)
    |
    v
[权限检查] -> PermissionNext.ask()
    |
    v
加载 SKILL.md 内容
    |
    v
返回格式化的技能内容
    |
    v
AI 使用技能内容执行任务
"""


# 数据流图
DATA_FLOW = """
+----------------+     +----------------+     +------------------+
|   SKILL.md     | --> |  SkillLoader   | --> |   Skills Cache   |
|  (Disk Files)  |     |  (scan/parse)  |     |  (Dict[str,Info])|
+----------------+     +----------------+     +------------------+
                                                      |
                                                      v
+----------------+     +----------------+     +------------------+
|  Permission    | <-- |  SkillTool     | <-- |   Agent Request  |
|  System        |     |  (execute)     |     |  (AI Agent)      |
+----------------+     +----------------+     +------------------+
                                                      |
                                                      v
                                             +------------------+
                                             |  Result Output   |
                                             |  (Title+Content) |
                                             +------------------+
"""


if __name__ == "__main__":
    print("=" * 60)
    print("OpenCode Skills 功能分析 - Python 实现")
    print("=" * 60)

    # 运行示例
    import asyncio
    # asyncio.run(example_usage())

    print("\n文件结构:")
    print(SKILL_DIRECTORY_STRUCTURE)

    print("\n数据流:")
    print(DATA_FLOW)

    print("\n" + "=" * 60)
    print("关键要点:")
    print("=" * 60)
    print("""
1. Skills 使用 Markdown + YAML frontmatter 定义
2. 支持多目录扫描: .opencode/skill/, .claude/skills/, ~/.claude/skills/
3. 作为 Tool 系统的一部分，与权限系统深度集成
4. 懒加载机制: 首次访问时扫描文件系统
5. 通配符匹配支持灵活的权限控制
6. 格式化输出便于 AI 理解和使用技能内容
""")
