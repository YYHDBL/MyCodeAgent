# Repository Guidelines

## Project Structure & Module Organization

```
agents/          - Main agent implementations (e.g., CodeAgent)
core/            - Core runtime, context engineering, LLM integration
  ├── context_engine/  - History management, compression, trace logging
  └── skills/         - Skill loading mechanism
tools/           - Tool system and registry
  ├── builtin/       - Built-in tools (LS, Glob, Grep, Read, Write, Edit, etc.)
  └── mcp/           - MCP server loader
prompts/         - System and tool prompts
tests/           - Test suite (pytest-based)
scripts/         - CLI entry points
skills/          - Skill definitions (SKILL.md per skill)
docs/            - Design documentation
memory/          - Trace/session output (local)
tool-output/     - Long output persistence
```

## Build, Test, and Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run interactive CLI
python scripts/chat_test_agent.py

# Run with specific provider/model
python scripts/chat_test_agent.py --provider zhipu --model GLM-4.7

# Enable raw output for debugging
python scripts/chat_test_agent.py --show-raw

# Run tests
python -m pytest tests/ -v
```

## Coding Style & Naming Conventions

- **Language**: Python 3.x
- **Indentation**: 4 spaces (PEP 8)
- **Naming**: 
  - Classes: `PascalCase` (e.g., `CodeAgent`, `ListFilesTool`)
  - Functions/variables: `snake_case` (e.g., `run_agent`, `project_root`)
  - Constants: `UPPER_SNAKE_CASE` (e.g., `CONTEXT_WINDOW`)
- **Docstrings**: Use triple quotes for class/function documentation
- **Type hints**: Required for function parameters and returns

## Testing Guidelines

- **Framework**: pytest
- **Fixtures**: Shared fixtures in `tests/conftest.py`
- **Test naming**: `test_<module>_<feature>.py` (e.g., `test_read_tool.py`)
- **Test functions**: `def test_<scenario>(...)`
- **Temp projects**: Use `temp_project` fixture for sandboxed testing
- **Run specific tests**: `python -m pytest tests/test_read_tool.py -v`

## Commit & Pull Request Guidelines

- **Commit messages**: Use conventional commits
  - `feat:` - New features
  - `docs:` - Documentation updates
  - `fix:` - Bug fixes
  - Example: `feat: function calling + mvp enhancements`
- **Pull requests**: Include clear descriptions, link related issues, add tests for new features

## MCP Tools Integration

Configure external MCP tools in `mcp_servers.json`:
```json
{
  "mcpServers": {
    "tool-name": {
      "command": "npx",
      "args": ["-y", "some-mcp-server"]
    }
  }
}
```

## Skills Directory Convention

```
skills/<skill-name>/SKILL.md
```

SKILL.md format:
```markdown
---
name: skill-name
description: Skill description
---
# Skill Title

Instructions here...
$ARGUMENTS
```

## Environment Variables

Key variables (see README.md for full list):
- `CONTEXT_WINDOW` - Default 128000
- `TOOL_OUTPUT_MAX_LINES` - Default 2000
- `TRACE_ENABLED` - Default true
- `SUBAGENT_MAX_STEPS` - Default 15
