# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MyCodeAgent is a learning/experimental ReAct code agent project for practicing: tool protocols, context engineering, skill systems, and subagent mechanisms.

## Development Commands

### Installation
```bash
pip install -r requirements.txt
```

### Running the Agent
```bash
# Interactive CLI with default settings
python scripts/chat_test_agent.py

# Custom provider/model
python scripts/chat_test_agent.py --provider zhipu --model GLM-4.7 --api-key YOUR_KEY --base-url https://open.bigmodel.cn/api/coding/paas/v4

# Debug mode (show raw LLM responses)
python scripts/chat_test_agent.py --show-raw
```

### Testing
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_read_tool.py -v
```

### Evaluation
```bash
# Run evaluation suites
python eval/run_eval.py --suite base
python eval/run_eval.py --suite long_horizon
python eval/run_eval.py --suite all
```

## Architecture

### Core Components
- **`core/agent.py`**: Abstract `Agent` base class
- **`core/llm.py`**: `HelloAgentsLLM` wrapper for LLM providers
- **`core/message.py`**: `Message` data model
- **`core/config.py`**: Configuration from environment variables
- **`agents/codeAgent.py`**: Main `CodeAgent` implementation with ReAct loop

### Context Engineering (Message List Mode)
The agent uses a **Message List** accumulation pattern:
- **L1**: System prompt + tool descriptions (`prompts/agents_prompts/L1_system_prompt.py`)
- **L2**: CODE_LAW.md (if present)
- **L3**: History messages from `HistoryManager` (user/assistant/tool/summary)
- **L4**: Current user input (appended to history)

Key files:
- **`core/context_engine/context_builder.py`**: Builds message lists for LLM calls
- **`core/context_engine/history_manager.py`**: Manages conversation history with compression
- **`core/context_engine/observation_truncator.py`**: Truncates large tool outputs
- **`core/context_engine/summary_compressor.py`**: Summarizes history when context window exceeded
- **`core/context_engine/trace_logger.py`**: Logs execution traces to `eval/traces/`

### Tool System
All tools follow the **Universal Tool Response Protocol** (see `docs/通用工具响应协议.md`):

Required response fields:
- `status`: `"success"` | `"partial"` | `"error"`
- `data`: Core payload (object)
- `text`: Natural language summary for LLM
- `error`: Structured error (only when `status="error"`)
- `stats`: Runtime metrics (must include `time_ms`)
- `context`: Execution context (must include `cwd`, `params_input`)

**`tools/registry.py`**: Central tool registry with optimistic lock auto-injection for Write/Edit tools.

### Built-in Tools
Located in `tools/builtin/`:
- **list_files.py** (LS): Directory listing with pagination
- **search_files_by_name.py** (Glob): Glob pattern matching with dual circuit-breakers
- **search_code.py** (Grep): Regex content search with ripgrep priority
- **read_file.py** (Read): File reading with line limits
- **write_file.py** (Write): File writing with optimistic lock
- **edit_file.py** (Edit): Single-point editing
- **edit_file_multi.py** (MultiEdit): Multi-point editing
- **todo_write.py** (TodoWrite): Task list management
- **skill.py** (Skill): Loads skills from `skills/**/SKILL.md`
- **task.py** (Task): Subagent delegation (general/explore/plan/summary)
- **bash.py** (Bash): Shell command execution

### Skills
Skills are stored in `skills/<skill-name>/SKILL.md` with frontmatter:
```markdown
---
name: code-review
description: Review code quality and risks
---
# Code Review
...
$ARGUMENTS
```

### MCP Integration
Register MCP tools via `mcp_servers.json`:
```json
{
  "mcpServers": {
    "myServer": {
      "transport": "http",
      "url": "http://localhost:8000"
    }
  }
}
```

## Key Environment Variables

### Context/History
- `CONTEXT_WINDOW` (default: 10000)
- `COMPRESSION_THRESHOLD` (default: 0.8)
- `MIN_RETAIN_ROUNDS` (default: 10)
- `SUMMARY_TIMEOUT` (default: 120s)

### Tool Output Truncation
- `TOOL_OUTPUT_MAX_LINES` (default: 2000)
- `TOOL_OUTPUT_MAX_BYTES` (default: 51200)
- `TOOL_OUTPUT_TRUNCATE_DIRECTION` (head|tail)
- `TOOL_OUTPUT_DIR` (default: tool-output)

### Skills
- `SKILLS_REFRESH_ON_CALL` (default: true)
- `SKILLS_PROMPT_CHAR_BUDGET` (default: 12000)

### Subagent
- `SUBAGENT_MAX_STEPS` (default: 15)
- `LIGHT_LLM_MODEL_ID` / `LIGHT_LLM_API_KEY` / `LIGHT_LLM_BASE_URL`

## Important Conventions

### Tool Development
- All tools must inherit from `tools/base.py:Tool`
- Use repo-absolute imports (e.g., `from core.llm import HelloAgentsLLM`)
- Follow Universal Tool Response Protocol strictly
- Tool prompts live in `prompts/tools_prompts/*.py`

### Testing
- Tests use pytest style in `tests/`
- Keep tests deterministic and offline
- For quick validation, use `scripts/chat_test_agent.py --show-raw`

### When Modifying Code
1. Read existing patterns first (e.g., check neighboring files for imports)
2. Use existing libraries/frameworks—never assume availability
3. Follow security best practices (never log/commit secrets)
4. Update corresponding tool prompt if behavior changes


