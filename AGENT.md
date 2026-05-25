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

There is no supported `scripts/` launcher path.

## Runtime Center

`runtime/` is the only runtime center:

- `runtime/host.py`: default host implementation
- `runtime/loop.py`: ReAct-style single-agent loop
- `runtime/history.py`: message model and history manager
- `runtime/input_preprocess.py`: user input preprocessing
- `runtime/observation_store.py`: observation truncation and storage
- `runtime/summary.py`: summary generation helpers
- `runtime/context_provider.py`: context provider facade
- `runtime/prompt_builder.py`: system prompt and message assembly
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
2. `app.bootstrap.build_runtime` assembles config, LLM, tool registry, and `runtime.host.CodeAgent`.
3. `runtime.loop.RuntimeRunner` drives the single-agent turn loop.
4. Context and prompt construction come from `runtime.input_preprocess`, `runtime.history`, `runtime.prompt_builder`, `runtime.observation_store`, and `runtime.summary`.
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
