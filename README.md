# MyCodeAgent

MyCodeAgent is a local-first, single-agent Python coding harness. It supplies
the reliable machinery around an OpenAI-compatible model: one controlled loop,
project-confined tools, permission decisions, bounded context, append-only
transcripts, and JSONL traces. It is meant to be installed once and run inside
an unrelated repository.

## Install

Python 3.10+ and [uv](https://docs.astral.sh/uv/) are supported.

```bash
uv sync --locked --extra dev
uv run mycodeagent --help
```

For a regular editable install, use `python -m pip install -e ".[dev]"`.
`pyproject.toml` is the dependency authority; the requirements files are
generated compatibility exports.

Configure an OpenAI-compatible provider in `.env` or pass CLI overrides:

```env
LLM_PROVIDER=openai
LLM_MODEL_ID=your-model
LLM_API_KEY=your-key
```

## Use

Start an interactive session in the repository you want to work on:

```bash
cd /path/to/project
mycodeagent
```

The invocation directory is the default project root. Use `--cwd` when the
target is elsewhere:

```bash
mycodeagent --cwd /path/to/project -p "inspect the test failure"
mycodeagent --cwd /path/to/project -p "summarize the repository" --json
```

`-p` runs one turn and exits. `--json` writes one machine-readable outcome to
standard output. Interactive sessions provide `/sessions`, `/resume [id]`,
and `/status`; transcripts under the selected project are the resume source.
Use Ctrl-C to cancel an active turn safely, then resume it if needed.

## Permissions and boundaries

The default schema contains seven tools: `Bash`, `Edit`, `Glob`, `Grep`,
`Read`, `Task`, and `TodoWrite`. `Edit` is the only file-mutation tool. File
paths are confined to the selected project; writes use read snapshots and
atomic replacement. Permission policy controls tool requests, but it is not
an operating-system sandbox—run the harness only where its process account is
appropriate.

The runner is `RuntimeRunner`. It records lifecycle facts once through the
event boundary; the transcript is recovery truth, and the model receives a
bounded derived view rather than a second persistent session snapshot.

## Optional extensions and lean startup

The normal startup path creates no MCP child process and no verification
subagent. It uses lightweight JSONL tracing: each trace ends with a
`session_summary` row containing steps, `tools_used`, and accumulated token
totals. It does not produce HTML reports or expose a generic trace-evaluation
API. Local Skills are loaded only when the selected project actually contains
`skills/**/SKILL.md`.

MCP is intentionally absent from the core installation. Install and enable it
only when required:

```bash
uv sync --locked --extra dev --extra mcp
mycodeagent --enable-mcp
```

The equivalent compatibility commands are:

```bash
uv sync --extra dev --extra mcp
python -m pip install -e ".[dev,mcp]"
```

The standalone extra is `mycodeagent[mcp]`.

`--enable-verification-agent` is also an explicit opt-in; when enabled, it
constructs the completion verifier without changing default startup. Removed
research systems and optional project-memory experiments are not product
features; their historical implementations remain discoverable through the
[research archive](docs/research-archive.md).

## Verify

```bash
uv run ruff check .
uv run ruff check . --select E722,F401,F541,F821,F841
uv run ruff check app core runtime tools extensions prompts utils --select E402
uv run pytest -q
uv run pytest -q tests/extensions/test_mcp_extension.py tests/test_core_without_mcp.py tests/test_mcp_protocol.py
uv run python scripts/check_release_metrics.py
```

The metrics command remains enforcing with a `≤15,000` stable-source cap and
returns nonzero when exceeded. The current 14,095-line release tree passes this
policy with bounded headroom; the seven-tool and dependency caps are unchanged.
See [closeout C-008](docs/plans/2026-07-14-lean-runtime-closeout/DECISIONS.md#c-008-raise-the-stable-production-budget-to-15000-lines).

Credentialed provider probes are deliberately excluded from the deterministic
suite. Run them only with explicit credentials and
`RUN_CREDENTIALLED_EVALS=1 uv run pytest -q -m credentialed`.

For the current execution flow and invariants, read
[docs/HARNESS.md](docs/HARNESS.md). Dated plans, previous design notes, and
demo snapshots are in [the historical archive](docs/archives/README.md).

## Non-goals

MyCodeAgent is not an enterprise platform, multi-agent team framework,
self-modifying skill laboratory, IDE, web dashboard, remote-worker system, or
OS-grade sandbox.
