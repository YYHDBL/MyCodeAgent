# Contributor guide

Keep MyCodeAgent a lean, local-first single-agent coding harness. The stable
runtime has one loop, `runtime.loop.RuntimeRunner`; do not introduce another
agent loop, a compatibility alias for removed systems, or a framework layer
with one caller.

## Durable boundaries

- `app/cli.py` owns user-facing parsing and rendering. Interactive and
  one-shot paths share the same runtime builder.
- `core/config.py` owns typed defaults. Explicit CLI flags override it.
- `runtime/host.py` composes dependencies; `runtime/events.py` projects each
  runtime fact to transcript and trace consumers.
- `runtime/context/` builds the bounded model view. Do not make compaction
  destructive or move context policy into history.
- `runtime/transcript.py` is durable recovery truth. New sessions do not write
  snapshots; the legacy reader is a one-way import only.
- `tools/` owns execution, permission routing, result budgeting, and the
  project-confined filesystem boundary. Tools must not import `runtime`.
- `Edit` is the only stable mutation tool. Preserve root confinement,
  read-snapshot conflict checks, atomic writes, and bounded recoverable output.

Default startup must remain single-agent and must not start MCP, a verification
subagent, or network extensions. MCP stays in `mycodeagent[mcp]`; local Skills
stay lazy and read-only. Removed research systems belong only in Git history,
not in shipped compatibility modules, prompts, flags, or docs.

## Change discipline

Add a behavior-level regression test before changing behavior. Keep the
canonical runtime flow visible, preserve transcript/trace terminal facts, and
prefer deletion over adapters when a stable concept has been removed. Do not
expand scope with IDE, web, worker, telemetry, or multi-agent features.

## Required verification

Run these commands before proposing a release:

```bash
uv run ruff check .
uv run pytest -q
uv run pytest -q tests/extensions/test_mcp_extension.py tests/test_core_without_mcp.py tests/test_mcp_protocol.py
uv run python scripts/check_release_metrics.py
uv run mycodeagent --help
```

The MCP command requires `uv sync --locked --extra dev --extra mcp`. The
release metrics command enforces the committed production-line and stable-tool
budgets. Current architecture and user behavior are documented in
`docs/HARNESS.md`; superseded material is explicitly archived under
`docs/archives/`.
