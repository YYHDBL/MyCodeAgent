# Skill MVP Implementation Plan

## Goal
Implement a minimal Skill system for this repo with a dedicated Skill tool. Skills are stored in-project and loaded on demand. The system should allow the model to load a skill by name and receive its instructions.

## Scope (MVP)
- Skills live in the project under `skills/**/SKILL.md`.
- Markdown + YAML frontmatter format.
- Required frontmatter fields: `name`, `description`.
- Skill tool lists available skills (brief description) in its prompt.
- Skill tool loads `SKILL.md`, injects base directory, and applies `$ARGUMENTS`.
- No marketplace, plugins, permissions, tool whitelists, or model overrides.

## Directory Layout
```
skills/
  <skill-name>/
    SKILL.md
```

## Skill File Format
```markdown
---
name: code-review
description: Review code quality and risks
---
# Code Review

Use this checklist:
- ...

$ARGUMENTS
```

### `$ARGUMENTS` Behavior
- If `$ARGUMENTS` exists in the skill body, replace it with the `args` string passed to the Skill tool.
- If `$ARGUMENTS` is absent and `args` is non-empty, append a section:
  `ARGUMENTS: <args>`
- If `args` is empty, do nothing.

## Core Components

### 1) Skill Loader
**New file**: `core/skills/skill_loader.py`

Responsibilities:
- Scan `skills/**/SKILL.md` under the project root.
- Parse YAML frontmatter and body.
- Validate required fields.
- Cache results and allow refresh by mtime.

Data model (suggested):
```python
@dataclass
class SkillMeta:
    name: str
    description: str
    path: str
    base_dir: str
    mtime: float
```

Key APIs:
- `scan()` -> loads all skills into cache
- `list_skills()` -> returns list of `SkillMeta`
- `get_skill(name)` -> returns `SkillMeta` or None

Validation rules:
- `name` must match: `^[a-z0-9]+(?:-[a-z0-9]+)*$`
- `description` must be non-empty
- If `name` in frontmatter does not match folder name, prefer frontmatter value
- On duplicate names, keep the last discovered and log a warning

Frontmatter parsing:
- Minimal YAML parsing is acceptable (simple `key: value` lines).
- If YAML parsing fails, skip skill with a warning.

### 2) Skill Tool
**New file**: `tools/builtin/skill.py`

Tool name: `Skill`

Parameters (JSON):
- `name` (string, required): skill identifier
- `args` (string, optional): arguments string

Behavior:
1) Load skill metadata from `SkillLoader`.
2) Read the skill file.
3) Build prompt:
   - Prefix: `Base directory for this skill: <skill_base_dir>`
   - Content: skill body
   - Apply `$ARGUMENTS` behavior
4) Return tool response envelope (per `docs/通用工具响应协议.md`).

Response `data` fields (suggested):
- `name`: skill name
- `base_dir`: skill base directory
- `content`: expanded skill content

### 3) Skill Tool Prompt
**New file**: `prompts/tools_prompts/skill_prompt.py`

Contents:
- Tool description and usage
- Parameters
- Examples
- List available skills with description (truncated by budget)

Budget control:
- Env var `SKILLS_PROMPT_CHAR_BUDGET` (default 12000)
- Stop listing when budget exceeded

### 4) Tool Registration
**Modify**: `agents/codeAgent.py`

- Import `SkillTool` and register in `_register_builtin_tools()`.
- Ensure Skill tool is included in the tool registry before context building.

## Integration Notes

### Skill Discovery Trigger (Agent Prompt Rules)
Skills should be discoverable by the model at decision time. Add a Skills rules section
to the L1 system prompt (this repo uses `prompts/agents_prompts/L1_system_prompt.py`,
there is no `codeAgentPrompt.md`).

Suggested rules (to add to the system prompt):
- When user mentions a skill by name (e.g., `$code-review` or “use code-review skill”), load it with the Skill tool.
- If a task clearly matches a skill’s description, consider loading that skill.
- Only load skills when explicitly needed; do not preload all skills.

### Skill List Placement
- The Skill tool’s prompt (including the available skill list) is injected into the L1 system prompt via `ContextBuilder`.
- This keeps skills discoverable at the same level as other tools.

### Where the Skill list appears
- The Skill tool’s prompt is included in the L1 system prompt via `ContextBuilder`.
- This means the model sees available skills in the same Tools section as LS/Read/etc.

### Sandboxing
- Skill files are under project root (`skills/`), so the existing `Read` logic is safe.

### SkillLoader Cache Invalidation Strategy (MVP)
Use a simple mtime-based refresh strategy:
- Initial scan at Agent startup (SkillLoader initialized once).
- On each Skill tool call, run `refresh_if_stale()`:
  - If the skills root directory mtime is newer than last scan time, rescan.
  - Otherwise, use cached results.
This keeps behavior correct with minimal overhead.

Environment knobs (optional):
- `SKILLS_REFRESH_ON_CALL` (default true) to enable/disable per-call refresh.

### Error Handling Details
Skill tool should return protocol-compliant errors:
- Missing skill name parameter: `INVALID_PARAM`
- Unknown skill name: `NOT_FOUND`
- Skill file read failures:
  - OS permission error -> `PERMISSION_DENIED`
  - Other I/O errors -> `EXECUTION_ERROR` or `INTERNAL_ERROR`
- Frontmatter parsing failure:
  - If a skill file fails parsing during scan, skip and log warning (not listed).
  - If directly requested and parse fails at load time, return `INTERNAL_ERROR`.

### Circular References (Future)
MVP does not support skill invoking skill. If this is added later:
- Track call stack and depth.
- On detecting a cycle, return `INVALID_PARAM` with a clear message.

## Proposed Files
- `core/skills/skill_loader.py` (new)
- `tools/builtin/skill.py` (new)
- `prompts/tools_prompts/skill_prompt.py` (new)
- `agents/codeAgent.py` (modify)

## Testing Plan
- `tests/test_skills.py` (new)
  - parses frontmatter
  - validates name/description
  - scan and list skills
  - get_skill by name
- `tests/test_protocol_compliance.py` (extend)
  - Skill tool response conforms to envelope

## Rollout Steps
1) Implement `SkillLoader` and unit tests.
2) Implement `SkillTool` and unit tests.
3) Add prompt + budget control.
4) Register tool in `CodeAgent`.
5) Run tests.

## Non-Goals (MVP)
- External/global skills directory
- Plugins/marketplace
- Permission system
- Allowed-tools restriction
- Model override for skills
- Executing inline bash or resolving `@file` references inside skills
