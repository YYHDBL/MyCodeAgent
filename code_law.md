# Repository Guidelines

## Project Structure & Module Organization

This project follows a layered architecture for AI agents built on ReAct (Reasoning + Acting) principles:

```
MyCodeAgent/
├── core/              # Foundational layer
│   ├── agent.py       # Agent base class
│   ├── llm.py         # LLM interface wrapper
│   ├── message.py     # Message system
│   ├── config.py      # Configuration management
│   └── context_engine/ # Context engineering components
├── agents/            # Agent implementations
│   └── codeAgent.py   # Main code analysis agent
├── tools/             # Tool system
│   ├── base.py        # Tool base class
│   ├── registry.py    # Tool registration
│   └── builtin/       # Built-in tools (LS, Glob, Grep, Read, Write, Edit, etc.)
├── prompts/           # Prompt templates
├── scripts/           # Entry points and utilities
├── tests/             # Test suite
└── docs/              # Design documentation
```

## Build, Test, and Development Commands

### Installation
```bash
pip install -r requirements.txt
```

### Running the Agent
```bash
# Interactive chat with raw output
python scripts/chat_test_agent.py --show-raw

# Specify provider and model
python scripts/chat_test_agent.py --provider zhipu --model GLM-4.7
```

### Testing
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific tool tests
python -m pytest tests/test_write_tool.py -v
python -m pytest tests/test_protocol_compliance.py -v
```

## Coding Style & Naming Conventions

- **Language**: Python 3 with 4-space indentation
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes
- **Imports**: Use repo-absolute imports (e.g., `from core.llm import HelloAgentsLLM`)
- **Documentation**: Include docstrings for all public classes and methods
- **Type Hints**: Use type annotations where applicable

## Tool Development Guidelines

All tools must follow the Universal Tool Response Protocol defined in `docs/通用工具响应协议.md`:

1. Inherit from `tools.base.Tool`
2. Implement `run()` method returning structured response
3. Register in `tools.registry.ToolRegistry`
4. Add tool description in `prompts/tools_prompts/`

Required response format:
```json
{
  "status": "success" | "partial" | "error",
  "data": { ... },
  "text": "Human-readable summary",
  "stats": { "time_ms": 100, ... },
  "context": { "cwd": ".", "params_input": { ... } },
  "error": { "code": "...", "message": "..." }
}
```

## Testing Guidelines

- **Framework**: pytest
- **Location**: `tests/` directory with descriptive names (e.g., `test_write_tool.py`)
- **Naming**: `test_` prefix for test functions
- **Coverage**: Maintain protocol compliance tests in `test_protocol_compliance.py`
- **Determinism**: Tests should be offline and deterministic

## Commit & Pull Request Guidelines

### Commit Messages
- Format: `type: short summary` (e.g., `feat: add Grep tool`, `fix: resolve Write tool race condition`)
- Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

### Pull Requirements
- Clear description of changes and motivation
- Verification steps for testing
- Related issues linked if applicable
- Configuration/environment changes documented

## Security & Configuration Tips

- Store API keys in `.env` files or environment variables
- Never commit secrets or API keys
- File operations are sandboxed to project root for security

## Architecture Overview

This framework implements the ReAct pattern: **Thought → Action → Observation**. Tools provide standardized interfaces for file operations, code search, and system interactions. All components communicate through a unified response protocol ensuring consistency and reliability across the agent ecosystem.
