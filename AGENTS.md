# Repository Guidelines

## Project Structure & Module Organization
- `core/`: foundational types and services (Agent base, LLM wrapper, message, config).
- `agents/`: concrete agents (`testAgent.py`, `codeAgent.py`) wired to ReAct.
- `agentEngines/`: reasoning loop (`ReActEngine.py`).
- `tools/`: tool base + registry (includes protocol helpers and legacy adapter).
- `tools/builtin/`: built‑in tools (`list_files.py` -> LS, `search_files_by_name.py` -> Glob, `search_code.py` -> Grep).
- `prompts/tools_prompts/`: tool prompts (Python string constants) used as tool descriptions.
- `docs/`: developer docs, including `DEV_HANDOFF.md` and `通用工具响应协议.md`.
- `scripts/`: runnable entry points (e.g., `scripts/chat_test_agent.py`).

## Build, Test, and Development Commands
- Install deps: `pip install -r requirements.txt`
- Run interactive chat (choose agent):
  - `python scripts/chat_test_agent.py --agent test --show-raw`
  - `python scripts/chat_test_agent.py --agent code --show-raw`
- Protocol adapter toggle (optional): set `ENABLE_LEGACY_ADAPTER=false` to disable legacy conversion in `tools/registry.py`.

## Coding Style & Naming Conventions
- Python 3, 4‑space indentation.
- `snake_case` for functions/variables, `PascalCase` for classes.
- Prefer repo‑absolute imports (e.g., `from core.llm import HelloAgentsLLM`).
- Tool names exposed to the model are **LS**, **Glob**, **Grep**; keep Python filenames unchanged.

## Tooling & Response Protocol
- All built‑in tools must follow `docs/通用工具响应协议.md`.
- Top‑level tool response fields must be exactly: `status`, `data`, `text`, `stats`, `context` (and `error` only when `status="error"`).
- `context.cwd` and `context.params_input` are required.
- Update corresponding prompt in `prompts/tools_prompts/` whenever you change a tool’s behavior.

## Testing Guidelines
- No formal test suite is present yet. Prefer lightweight manual checks via `scripts/chat_test_agent.py`.
- If adding tests, keep them deterministic and avoid network calls.

## Commit & Pull Request Guidelines
- No established git history conventions. Suggested format: `type: short summary` (e.g., `feat: unify tool response envelope`).
- PRs should include: brief description, how you verified changes, and any required env/config.

## Security & Configuration Tips
- LLM access uses environment variables (e.g., `OPENAI_API_KEY`, `LLM_BASE_URL`).
- Do not commit secrets; use local env files for overrides.
