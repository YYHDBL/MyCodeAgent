# MyCodeAgent

A production‑ready ReAct agent framework for code analysis and autonomous software tasks.

```
 __  __       ____          _      ___                 _
|  \/  |_   _/ ___|___   __| | ___|_ _|_ __ ___   __ _| |
| |\/| | | | | |   / _ \ / _` |/ _ \| || '_ ` _ \ / _` | |
| |  | | |_| | |__| (_) | (_| |  __/| || | | | | | (_| | |
|_|  |_|\__, |\____\___/ \__,_|\___|___|_| |_| |_|\__,_|_|
        |___/
```

## Why this exists
MyCodeAgent turns a codebase into an executable workspace: reasoning + tools + safety.
It is built for long‑running, tool‑rich sessions with strict protocol guarantees.

## Highlights
- ReAct loop with Thought → Action → Observation
- Unified tool response protocol (schema‑stable, agent‑friendly)
- Tool result compression + history summary to control context growth
- Multi‑provider LLM support (OpenAI/DeepSeek/Qwen/Zhipu/Kimi/ModelScope/Ollama/vLLM/local)
- Sandbox‑safe file ops and command execution
- Deterministic, offline‑friendly tests

## Architecture at a glance
```
core/      = base agent, LLM client, messages, config, history, context
agents/    = concrete agents (CodeAgent)
tools/     = registry + protocol helpers
tools/builtin/ = LS/Glob/Grep/Read/Write/Edit/MultiEdit/TodoWrite/Bash
prompts/   = agent/tool prompts
scripts/   = entrypoints
```

## Built‑in tools
| Tool | Purpose | Notes |
|------|---------|------|
| LS | List directories | pagination, ignore rules |
| Glob | Find files by pattern | deterministic ordering |
| Grep | Search code | regex + rg fallback |
| Read | Read files | paging + line numbers |
| Write | Create/overwrite | diff preview + optimistic lock |
| Edit | Single replacement | unique anchor required |
| MultiEdit | Batch edits | atomic multi‑replace |
| TodoWrite | Task list | recap + persistence |
| Bash | Shell command | sandbox + safety rules |

All tools return a unified response envelope. See `docs/通用工具响应协议.md`.

## Quickstart
### Install
```bash
pip install -r requirements.txt
```

### Configure
```bash
# OpenAI
export OPENAI_API_KEY="your-api-key"

# Other providers
export DEEPSEEK_API_KEY="your-api-key"
export GLM_API_KEY="your-api-key"
export LLM_BASE_URL="https://your-api-endpoint"
```

### Run
```bash
python scripts/chat_test_agent.py --show-raw

# Explicit provider/model
python scripts/chat_test_agent.py --provider zhipu --model GLM-4.7
```

## Tool protocol (contract)
Every tool returns:
```json
{
  "status": "success" | "partial" | "error",
  "data": { ... },
  "text": "human-readable summary",
  "stats": { "time_ms": 123, ... },
  "context": {
    "cwd": ".",
    "params_input": { ... }
  },
  "error": { "code": "...", "message": "..." }
}
```

## Development
### Tests
```bash
python -m pytest tests/ -v
python -m pytest tests/test_write_tool.py -v
python -m pytest tests/test_read_tool.py -v
python -m pytest tests/test_protocol_compliance.py -v
```

### Add a new tool
1) Inherit `tools.base.Tool`
2) Implement `run()` and `get_parameters()`
3) Register in `tools/registry.py`
4) Add prompt in `prompts/tools_prompts/`

## Project rules
- `CODE_LAW.md` is auto‑injected into system context (L2)
- When tool behavior changes, update prompts in `prompts/tools_prompts/`

## License
TBD
