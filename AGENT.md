# MyCodeAgent Agent Guide

Last updated: 2026-06-06

## Project Goal

MyCodeAgent is a learning-oriented Python code-agent harness. Keep the default single-agent runtime small while preserving the important harness boundaries: explicit loop state, controlled tool execution, and model-facing context projection.

Do not turn this repository into an enterprise platform. Prefer a clear implementation that demonstrates the design principle.

## Canonical Runtime

```text
main.py
  -> app.cli
  -> app.bootstrap
  -> runtime.host.CodeAgent
  -> runtime.loop.RuntimeRunner
```

There is one canonical single-agent loop: `runtime/loop.py`.

## Runtime Responsibilities

- `runtime/host.py`: dependency wiring and host adapters
- `runtime/loop.py`: loop stages and state transitions
- `runtime/state.py`: `LoopState`, transition reasons, terminal reasons
- `runtime/history.py`: complete runtime message log only
- `runtime/context/`: context budget, compact checkpoint, projection, normalization, and `ModelView`
- `runtime/prompt_builder.py`: stable system prompt construction
- `runtime/input_preprocess.py`: user input and `@file` preprocessing
- `runtime/observation_store.py`: large tool-output persistence and truncation
- `runtime/session.py`: session snapshot persistence
- `runtime/summary.py`: summary generation helper used by context compaction

Do not move context decisions back into `HistoryManager`. It must not own token budgets, model-message serialization, or destructive compaction.

## Tool Responsibilities

- `tools/executor.py`: one validated tool execution lifecycle
- `tools/orchestrator.py`: tool planning, safe batching, ordered observations, and result budgets
- `tools/registry.py`: tool registration and read/write metadata
- `tools/builtin/`: concrete tools

Concurrency is opt-in. Only explicitly safe read-only calls may run concurrently. Unknown or side-effecting tools stay serial.

Tool output is a context resource. Preserve full oversized output on disk and send the model a bounded view.

## Context Invariants

- Full history remains available in `HistoryManager`.
- `ContextEngine.build_model_view()` is the model request boundary.
- Compact creates a checkpoint; it does not delete old history.
- `ProjectionBuilder` applies the checkpoint at read time.
- Clearing history or loading a session must reset context checkpoint and usage state.
- A current checkpoint must not be regenerated for unchanged history.

## Optional Systems

- `extensions/mcp/`: MCP integration
- `extensions/skills/`: local skill discovery
- `extensions/tracing/`: trace logging and sanitization
- `experimental/teams/`: opt-in multi-agent runtime

Experimental team code must not become a dependency of the default runtime path.

## Editing Rules

- Preserve the canonical boundaries above.
- Avoid compatibility wrappers and duplicate runtime centers.
- Add tests beside the owning subsystem.
- Do not add broad abstractions for hypothetical future features.
- Keep trace events and transition reasons when adding recovery paths.
- Never make context compaction destructive.

## Verification

Run the full suite before completion:

```bash
.venv/bin/python -m pytest -q
```

Useful focused suites:

```bash
.venv/bin/python -m pytest tests/runtime tests/tools -q
.venv/bin/python -m pytest tests/extensions -q
.venv/bin/python -m pytest tests/experimental -q
```

Current harness design: `docs/HARNESS.md`.
