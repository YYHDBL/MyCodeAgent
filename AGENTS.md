# Repository Guidelines

## Project Structure & Module Organization
- `core/`: foundational types/services (Agent base, LLM wrapper, message, config, trace logger).
- `agents/`: concrete agents (`codeAgent.py`) that wire tools and ReAct.
- `agentEngines/`: (merged into `CodeAgent`).
- `tools/`: tool base + registry (protocol helpers, optimistic‑lock injection).
- `tools/builtin/`: built‑in tools (LS/Glob/Grep/Read/Write/Edit/MultiEdit/TodoWrite/Bash).
- `prompts/tools_prompts/`: tool prompts (Python string constants).
- `prompts/agents_prompts/`: agent prompts (e.g., `codeAgentPrompt.md`).
- `docs/`: design docs and handoff notes (`通用工具响应协议.md`, `DEV_HANDOFF.md`).
- `scripts/`: entry points (`scripts/chat_test_agent.py`).
- `tests/`: automated tests.
- `eval/`: evaluation suites, fixtures, and runner (`eval/run_eval.py`).

## Build, Test, and Development Commands
- Install deps: `pip install -r requirements.txt`
- Run interactive chat:
  - `python scripts/chat_test_agent.py --show-raw`
- Run eval suites:
  - `python eval/run_eval.py --suite base`
  - `python eval/run_eval.py --suite long_horizon`
  - `python eval/run_eval.py --suite all`

## Coding Style & Naming Conventions
- Python 3, 4‑space indentation.
- `snake_case` for functions/variables, `PascalCase` for classes.
- Prefer repo‑absolute imports (e.g., `from core.llm import HelloAgentsLLM`).

## Tooling & Response Protocol
- All tools must follow `docs/通用工具响应协议.md`.
- Top‑level response fields: `status`, `data`, `text`, `stats`, `context` (and `error` only on failure).
- Update the matching prompt in `prompts/tools_prompts/` when tool behavior changes.

## Testing Guidelines
- Tests live under `tests/` (pytest style). Keep them deterministic and offline.
- For quick validation, use `scripts/chat_test_agent.py` and inspect `--show-raw`.
- For evaluation, use `eval/run_eval.py`; reports are written to `eval/reports/`.

## Evaluation & Runner Notes
- Suites: `eval/tasks/base.json` and `eval/tasks/long_horizon.json` define tasks and checks.
- Fixtures live under `eval/fixtures/` (Python/TypeScript, long logs, etc).
- Provider selection: if multiple providers are configured, set `LLM_PROVIDER` or pass `--provider`.
- Optional overrides: `--model`, `--base-url`, `--api-key` map to `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`.
- Traces: the runner enables tracing and writes JSONL to `eval/traces/` for tool-usage checks.
- MCP servers: if eval appears to hang on MCP startup, set `MCP_CONNECT_MODE=disabled` (or clear MCP configs).

## Commit & Pull Request Guidelines
- No enforced convention; recommended format: `type: short summary` (e.g., `feat: add Grep tool`).
- PRs should include: summary, verification steps, and any config/env changes.

## Security & Configuration Tips
- Store keys in `.env` or environment variables; never commit secrets.
- If a key is exposed, rotate it immediately.

## Skills
A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and file path so you can open the source for full instructions when using a specific skill.
### Available skills
- skill-creator: Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Codex's capabilities with specialized knowledge, workflows, or tool integrations. (file: /Users/yyhdbl/.codex/skills/.system/skill-creator/SKILL.md)
- skill-installer: Install Codex skills into $CODEX_HOME/skills from a curated list or a GitHub repo path. Use when a user asks to list installable skills, install a curated skill, or install a skill from another repo (including private repos). (file: /Users/yyhdbl/.codex/skills/.system/skill-installer/SKILL.md)
### How to use skills
- Discovery: The list above is the skills available in this session (name + description + file path). Skill bodies live on disk at the listed paths.
- Trigger rules: If the user names a skill (with `$SkillName` or plain text) OR the task clearly matches a skill's description shown above, you must use that skill for that turn. Multiple mentions mean use them all. Do not carry skills across turns unless re-mentioned.
- Missing/blocked: If a named skill isn't in the list or the path can't be read, say so briefly and continue with the best fallback.
- How to use a skill (progressive disclosure):
  1) After deciding to use a skill, open its `SKILL.md`. Read only enough to follow the workflow.
  2) If `SKILL.md` points to extra folders such as `references/`, load only the specific files needed for the request; don't bulk-load everything.
  3) If `scripts/` exist, prefer running or patching them instead of retyping large code blocks.
  4) If `assets/` or templates exist, reuse them instead of recreating from scratch.
- Coordination and sequencing:
  - If multiple skills apply, choose the minimal set that covers the request and state the order you'll use them.
  - Announce which skill(s) you're using and why (one short line). If you skip an obvious skill, say why.
- Context hygiene:
  - Keep context small: summarize long sections instead of pasting them; only load extra files when needed.
  - Avoid deep reference-chasing: prefer opening only files directly linked from `SKILL.md` unless you're blocked.
  - When variants exist (frameworks, providers, domains), pick only the relevant reference file(s) and note that choice.
- Safety and fallback: If a skill can't be applied cleanly (missing files, unclear instructions), state the issue, pick the next-best approach, and continue.
