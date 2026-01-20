# MyCodeAgent - Project Overview

## Project Goal

MyCodeAgent is a code agent framework focused on **tool protocols**, **context engineering**, **subagent mechanisms**, and **observability**. The vision is to make both "what an agent can do" and "why an agent can do it" traceable, verifiable, and extensible. It serves as a learning and experimental platform for function calling, tool protocols, and agent systems (from `README.md`).

## Core Modules

| Directory | Purpose |
|-----------|---------|
| `agents/` | Main agent implementations (`agents/codeAgent.py` - ReAct-based code assistant) |
| `core/` | Core runtime, context engineering, LLM integration (`core/agent.py` base class) |
| `core/context_engine/` | History management, compression, trace logging |
| `core/skills/` | Skill loading mechanism |
| `tools/` | Tool system and registry (`tools/registry.py`) |
| `tools/builtin/` | 12 built-in tools (LS, Glob, Grep, Read, Write, Edit, MultiEdit, Bash, TodoWrite, Skill, Task, AskUser) |
| `tools/mcp/` | MCP server loader for external tool integration |
| `prompts/` | System prompts and tool prompts |
| `skills/` | Skill definitions (`skills/<skill-name>/SKILL.md`) |
| `docs/` | Comprehensive design documentation |
| `scripts/` | CLI entry points (`scripts/chat_test_agent.py`) |
| `memory/` | Trace/session output storage |
| `tool-output/` | Long output persistence directory |

## Key Features

- **Function Calling Tool Protocol**: Native OpenAI function calling without Action text parsing
- **Unified Tool Response Protocol**: Standardized `status/data/text/stats/context/error` envelope (defined in `docs/通用工具响应协议.md`)
- **12 Built-in Tools**: LS, Glob, Grep, Read, Write, Edit, MultiEdit, Bash, TodoWrite, Skill, Task, AskUser
- **Context Engineering**: Three-layer injection (L1: system+tools, L2: CODE_LAW.md, L3: history) with history compression (designed in `docs/上下文工程设计文档.md`)
- **Tool Output Truncation**: Automatic truncation at 2000 lines/50KB with disk persistence to `tool-output/`
- **Circuit Breaker**: Auto-disable tools after consecutive failures (`tools/circuit_breaker.py`)
- **Trace Logging**: Dual-track JSONL + HTML logging with sanitization (`docs/TraceLogging设计文档.md`)
- **Session Persistence**: `/save` and `/load` commands for session management
- **MCP Extension**: External tools via `mcp_servers.json` configuration
- **Enhanced CLI UI**: Tool call tree visualization, token statistics, progress display
- **Skills System**: Loadable skill packages with SKILL.md format and `$ARGUMENTS` substitution (`docs/skillTool设计文档.md`)
- **Task Subagents**: Read-only subagents for focused delegation with model selection (main/light) (`docs/task(subagent)设计文档.md`)

## Technical Stack

- **Language**: Python 3.x
- **Core Libraries**:
  - `openai>=1.0.0` - LLM API client
  - `pydantic>=1.10.0` - Data validation
  - `mcp>=1.0.0` - MCP protocol support
  - `anyio>=3.0.0` - Async I/O
  - `python-dotenv>=1.0.0` - Environment variables
  - `rich>=13.0.0` - Terminal formatting
  - `prompt_toolkit>=3.0.0` - Interactive CLI
  - `pytest>=7.0.0` - Testing framework

## Architecture Overview

### Multi-Layer Context Design
1. **L1 System Layer**: System Prompt + tool descriptions (stable)
2. **L2 Project Rules Layer**: `CODE_LAW.md` (optional, not in history)
3. **L3 Session History Layer**: User/assistant/tool messages + system summaries

### ReAct Loop with Message List Mode
- ReAct循环构建 `messages = system(L1/L2) + history(user/assistant/tool)` (from `agents/codeAgent.py`)
- 每步同步写入 assistant/tool 消息到 history
- HistoryManager manages rounds, compression, and summary generation

### Tool Response Protocol
All tools return standardized envelope with:
- `status`: "success" | "partial" | "error"
- `data`: Tool-specific payload (e.g., entries, paths, matches)
- `text`: Human-readable summary for LLM
- `stats`: Time and execution metrics
- `context`: cwd, params_input, path_resolved
- `error`: {code, message} when status="error"

### Trace Logging System
- Events: system_messages, run_start/end, user_input, model_output, tool_call, tool_result, error, finish, session_summary
- Dual output: JSONL for processing + HTML for audit
- Sanitization enabled by default for API keys/tokens
- Full tool results recorded per protocol

## Competitive Analysis

| Feature | MyCodeAgent | Claude Code | Codex CLI/Cursor AI |
|---------|-------------|-------------|---------------------|
| **Tool Protocol** | ✅ Standardized envelope | Proprietary | Varies by implementation |
| **Context Engineering** | ✅ 3-layer injection + compression | Limited details | Basic context management |
| **History Compression** | ✅ LLM-based summaries | Not documented | Typically not present |
| **Trace Logging** | ✅ JSONL + HTML with sanitization | Internal logs | Varies |
| **Skills System** | ✅ Markdown-based SKILL.md | Workspaces/Artifacts | Custom prompts |
| **Subagent Delegation** | ✅ Task tool with model selection | Projects | Tab-based multi-file |
| **MCP Extension** | ✅ Native support | Limited | Varies |
| **Tool Output Truncation** | ✅ Configurable with persistence | Automatic | Not specified |
| **Observability** | ✅ High (trace + stats + CLI UI) | Medium | Varies |
| **Open Source** | ✅ MIT License | ❌ Proprietary | Mixed (Cursor open, others not) |
| **Extensibility** | ✅ High (tool registry, MCP) | Medium | Medium |

### Unique Aspects

1. **Standardized Tool Protocol**: Strict `status/data/text/stats/context/error` envelope ensures consistency across all tools (from `docs/通用工具响应协议.md`)

2. **Advanced Context Engineering**: Three-layer injection with LLM-based history compression, @file forcing, and mtime tracking (from `docs/上下文工程设计文档.md`)

3. **Skills System**: In-project skill packages with YAML frontmatter and `$ARGUMENTS` substitution (from `docs/skillTool设计文档.md`)

4. **Subagent Delegation**: Read-only subagents with tool filtering and dual-model selection (main/light) (from `docs/task(subagent)设计文档.md`)

5. **Dual-Track Observability**: JSONL for programmatic analysis + HTML for human audit with built-in sanitization (from `docs/TraceLogging设计文档.md`)

6. **Protocol-First Design**: All design documents specify exact protocols, making behaviors traceable and verifiable

7. **Circuit Breaker**: Lightweight protection against cascading tool failures (`tools/circuit_breaker.py`)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run interactive CLI
python scripts/chat_test_agent.py

# Specify provider and model
python scripts/chat_test_agent.py --provider zhipu --model GLM-4.7

# Enable raw output debugging
python scripts/chat_test_agent.py --show-raw

# Run tests
python -m pytest tests/ -v
```

## Key Design Documents

- `docs/通用工具响应协议.md` - Standardized tool response envelope
- `docs/上下文工程设计文档.md` - Multi-layer context and history compression
- `docs/工具输出截断设计文档.md` - Tool output truncation strategy
- `docs/TraceLogging设计文档.md` - Trace logging and observability
- `docs/skillTool设计文档.md` - Skills system architecture
- `docs/task(subagent)设计文档.md` - Subagent delegation mechanism
- `CODE_LAW.md` - Repository guidelines and conventions
