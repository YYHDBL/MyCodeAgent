# MyCodeAgent Project Rules

This file is injected into the model context. Keep it short, current, and
limited to repository facts and invariants that affect implementation.

## Current Structure

- `main.py` delegates to `app/cli.py`.
- `app/` owns CLI and dependency bootstrap.
- `runtime/` owns the canonical single-agent loop, completion/recovery,
  context projection, transcript/session state, memory, and subagents.
- `tools/` owns tool contracts, registry, permissions, execution,
  orchestration, and built-in tools.
- `extensions/` owns optional MCP, skills, and tracing integrations.
- `prompts/` contains agent and tool prompt text.
- `tests/` mirrors runtime, tools, extensions, scenarios, and experimental
  behavior.
- `experimental/teams/` is research code and is not part of the default
  single-agent runtime.
- `docs/` contains design and portfolio documentation.
- `demo/` contains deterministic harness demonstrations.
- `memory/` and `tool-output/` are generated runtime data.

## Commands

```bash
# Install runtime dependencies
uv pip install -r requirements.txt

# Install development and test dependencies
uv pip install -r requirements-dev.txt

# Run the interactive agent
.venv/bin/python main.py

# Run all tests
.venv/bin/python -m pytest -q

# Run deterministic demos
.venv/bin/python demo/harness_portfolio.py all
```

## Invariants

- The canonical call path is
  `main.py -> app.cli -> runtime.host.CodeAgent -> RuntimeRunner`.
- `HistoryManager` owns conversation history. The `Agent` base class must not
  maintain a second history store.
- The model proposes tool calls; `ToolExecutor` and `RiskClassifier` decide
  whether execution is allowed.
- Tool observations use the standard response envelope and are budgeted before
  entering model context.
- Full history is durable. Compaction changes the model view, not the source
  history.
- A model final answer is only a completion candidate; the runtime completion
  gate owns termination.
- Optional integrations must fail closed or degrade without breaking the
  default single-agent runtime.
- Tool orchestration and result-budget modules must not import higher-level
  `runtime` implementations.
- Pydantic v2 is the supported major version.
