# Repository Guidelines

## Project Structure & Module Organization
- `core/`: foundational types/services (Agent base, LLM wrapper, message, config, trace logger).
- `agents/`: concrete agents (`codeAgent.py`) that wire tools and ReAct.
- `agentEngines/`: (merged into `CodeAgent`).
- `tools/`: tool base + registry (protocol helpers, legacy adapter, optimistic‑lock injection).
- `tools/builtin/`: built‑in tools (LS/Glob/Grep/Read/Write/Edit/MultiEdit/TodoWrite/Bash).
- `prompts/tools_prompts/`: tool prompts (Python string constants).
- `prompts/agents_prompts/`: agent prompts (e.g., `codeAgentPrompt.md`).
- `docs/`: design docs and handoff notes (`通用工具响应协议.md`, `DEV_HANDOFF.md`).
- `scripts/`: entry points (`scripts/chat_test_agent.py`).
- `tests/`: automated tests.

## Build, Test, and Development Commands
- Install deps: `pip install -r requirements.txt`
- Run interactive chat:
  - `python scripts/chat_test_agent.py --show-raw`
- Optional: disable legacy adapter with `ENABLE_LEGACY_ADAPTER=false`.

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

## Commit & Pull Request Guidelines
- No enforced convention; recommended format: `type: short summary` (e.g., `feat: add Grep tool`).
- PRs should include: summary, verification steps, and any config/env changes.

## Security & Configuration Tips
- Store keys in `.env` or environment variables; never commit secrets.
- If a key is exposed, rotate it immediately.
