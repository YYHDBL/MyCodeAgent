# MyCodeAgent Architecture Notes

Last updated: 2026-05-24

## Purpose

`MyCodeAgent` is a compact Python coding-agent harness. The repository now centers one canonical single-agent runtime path and keeps optional or experimental systems behind explicit directories.

The main story is:

```text
main.py -> app/ -> runtime/ -> tools/
                         -> extensions/
                         -> experimental/ (explicit opt-in only)
```

## Canonical Entrypoint

- User-facing entrypoint: `main.py`
- CLI implementation: `app/cli.py`
- Dependency wiring: `app/bootstrap.py`
- Historical launcher: `scripts/chat_test_agent.py`, kept only to forward old commands to `app.cli.main`

## Runtime Center

`runtime/` is the only runtime center:

- `runtime/agent_host.py`: default host implementation
- `runtime/runner.py`: ReAct-style single-agent loop
- `runtime/messages.py`: message model and history manager
- `runtime/context.py`: input preprocessing, observation truncation, summary helpers, context policy helpers
- `runtime/prompt.py`: system prompt and message assembly
- `runtime/session.py`: session snapshot persistence

There is no `agents/` package and no `core/context_engine` runtime tree.

## Supporting Layers

- `tools/`: tool abstraction, registry, executor, and built-in tools
- `extensions/mcp/`: optional MCP loading, client, adapter, and protocol conversion
- `extensions/skills/`: optional local skill loader
- `extensions/tracing/`: optional trace logger and sanitizer
- `experimental/teams/`: non-canonical team runtime, enabled only by explicit configuration
- `core/`: shared infrastructure only: config, environment loading, base agent abstraction, exceptions, and LLM client

## Execution Flow

1. `main.py` delegates to `app.cli.main`.
2. `app.bootstrap.build_runtime` assembles config, LLM, tool registry, and `runtime.agent_host.CodeAgent`.
3. `runtime.runner.RuntimeRunner` drives the single-agent turn loop.
4. Context and prompt construction come from `runtime.context`, `runtime.messages`, and `runtime.prompt`.
5. Tool calls go through `tools.executor.ToolExecutor` and `tools.registry.ToolRegistry`.
6. Optional MCP, skills, and tracing are loaded through `extensions/`.
7. Team runtime code is imported only when experimental team features are enabled.

## Tests

- Runtime: `tests/runtime/`
- Tool boundary: `tests/tools/` plus focused root tool tests
- Extensions: `tests/extensions/`
- Experimental teams: `tests/experimental/`

Recommended checks:

```bash
.venv/bin/pytest tests/runtime tests/tools tests/extensions -q
.venv/bin/pytest tests/experimental -q
```
