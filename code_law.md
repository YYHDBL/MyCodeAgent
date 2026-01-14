# Repository Guidelines

## Project Structure & Module Organization

```
MyCodeAgent/
├── agents/          # Agent implementations
├── core/            # Core ReAct loop and tool protocols
├── docs/            # Design documentation
├── eval/            # Evaluation scripts
├── memory/          # Memory and context management
├── prompts/         # System prompts and templates
├── scripts/         # Entry points (chat_test_agent.py)
├── skills/          # Skill definitions (SKILL.md per skill)
├── tests/           # Test suite
├── tools/           # Built-in tools (LS, Glob, Grep, etc.)
├── utils/           # Utility functions
└── tool-output/     # Truncated tool outputs cache
```

## Build, Test, and Development Commands

- **Install dependencies**: `pip install -r requirements.txt`
- **Run interactive CLI**: `python scripts/chat_test_agent.py`
- **Run with custom model**: `python scripts/chat_test_agent.py --provider <provider> --model <model> --api-key <key> --base-url <url>`
- **Run tests**: `python -m pytest tests/ -v`
- **Debug raw responses**: `python scripts/chat_test_agent.py --show-raw`

## Coding Style & Naming Conventions

- **Language**: Python 3.x
- **Dependencies**: openai>=1.0.0, pydantic>=1.10.0, mcp>=1.0.0, anyio>=3.0.0, rich>=13.0.0
- **Key patterns**:
  - Tool responses follow Universal Tool Response Protocol (status/data/text/stats/context)
  - Skills use `skills/<skill-name>/SKILL.md` format with frontmatter (name, description)
  - Environment variables for configuration (CONTEXT_WINDOW, TOOL_OUTPUT_MAX_LINES, etc.)

## Testing Guidelines

- **Framework**: pytest
- **Test location**: `tests/` directory
- **Run tests**: `python -m pytest tests/ -v`
- **Coverage**: Test tool protocols, agent loops, and context management
- **Naming**: Use descriptive test names following `test_<functionality>_<scenario>` pattern

## Skills & Subagent Guidelines

- **Skills**: Place in `skills/<name>/SKILL.md` with frontmatter; use `$ARGUMENTS` placeholder for dynamic content
- **Task subagents**: Use `general` for execution, `explore` for codebase scanning, `plan` for implementation steps, `summary` for compression
- **MCP tools**: Register in `mcp_servers.json` at project root

## Architecture Notes

- **ReAct pattern**: Thought → Action → Observation loop
- **Context engineering**: Layered injection, history compression, @file references force Read
- **Tool isolation**: Subagents have restricted toolsets (read-only/limited)
