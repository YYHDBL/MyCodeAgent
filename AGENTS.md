# Repository Guidelines

## Project Structure & Module Organization
- `core/`: foundational types and services (e.g., `Agent`, `HelloAgentsLLM`, config, message, exceptions).
- `agents/`: concrete agents (e.g., `testAgent.py`, `codeAgent.py`).
- `agentEngines/`: reasoning/loop engines (e.g., `ReActEngine.py`).
- `tools/`: tool abstractions and registry.
- `utils/`: logging, serialization, helpers.
- `scripts/`: runnable entry points (e.g., `scripts/chat_test_agent.py`).
- `tests/`: unit tests (e.g., `tests/test_test_agent.py`).
- `prompts/`: prompt assets (if used later).

## Build, Test, and Development Commands
- Install deps: `pip install -r requirements.txt`
- Run interactive chat: `python scripts/chat_test_agent.py --show-raw`
  - Starts a multi-turn CLI chat and prints the raw model response structure.
- Run tests: `python -m unittest tests/test_test_agent.py -v`
  - Executes the basic TestAgent unit test.

## Coding Style & Naming Conventions
- Python 3 style; use 4 spaces for indentation.
- `snake_case` for functions/variables, `PascalCase` for classes.
- Prefer top-level absolute imports within the repo (e.g., `from core.llm import HelloAgentsLLM`) to avoid relative-import issues.
- Keep functions short and focused; log key steps using `utils.setup_logger`.

## Testing Guidelines
- Test framework: `unittest`.
- Name tests as `tests/test_*.py` and classes as `Test*`.
- Keep tests deterministic and avoid network calls unless explicitly required.

## Commit & Pull Request Guidelines
- Git history is empty, so no established convention yet.
- Suggested commit format: `type: short summary` (e.g., `feat: add TestAgent chat script`).
- PRs should include: a concise description, the commands used to verify changes, and any config/env vars required.

## Security & Configuration Tips
- LLM access uses environment variables (e.g., `OPENAI_API_KEY`, `LLM_BASE_URL`).
- Avoid committing secrets; prefer `.env` for local overrides.
