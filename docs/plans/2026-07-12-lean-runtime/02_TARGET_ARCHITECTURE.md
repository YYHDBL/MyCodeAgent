# Target Architecture

## Dependency Direction

```text
CLI / application shell
        ↓
RuntimeRunner + RuntimeHost
        ↓
ModelView  ToolExecutor  CompletionGate
        ↓       ↓              ↓
Transcript  Workspace/Tools  Evidence
        ↓
JSONL events

Optional adapters: Skills, MCP
Research systems: not shipped in the stable tree
```

Dependencies point downward. Tools must not import runtime modules. Optional extensions may depend on stable interfaces, but the stable runtime must not import extension implementations until explicitly enabled.

## Intended Modules

Names may change during implementation, but each responsibility must have one owner.

| Responsibility | Target owner | Notes |
|---|---|---|
| CLI parsing and rendering | `app/cli.py` | Interactive and one-shot share one runtime builder. |
| Configuration | `core/config.py` | One typed configuration object; CLI overrides env. |
| Model transport | `core/llm.py` | OpenAI-compatible only; provider aliases are data, not branches. |
| Agent loop | `runtime/loop.py` | Orchestrates stages; does not implement persistence or tracing details. |
| Dependency wiring | `runtime/host.py` or small builder functions | Avoid a class factory with one product. |
| Context projection | `runtime/context/` | Keep non-destructive checkpoint semantics. |
| Durable recovery | `runtime/transcript.py` | Authoritative session fact stream. |
| Event emission | `runtime/events.py` | One event interface with transcript and trace sinks. |
| Tool boundary | `tools/base.py`, `tools/executor.py`, `tools/registry.py` | Typed internal result; serialize once at model boundary. |
| Filesystem primitives | `tools/workspace.py` | Path resolution, snapshots, atomic write, binary checks. |
| Optional capabilities | `extensions/skills/`, `extensions/mcp/` | Lazy, opt-in, optional dependencies. |

## Stable Runtime Flow

```text
parse request
→ resolve project root and config
→ load or create transcript
→ append user input
→ build bounded ModelView
→ call model
→ if tool calls: authorize, execute, append results, continue
→ if final: evaluate deterministic completion evidence
→ append terminal event and return
```

Every loop transition emits a small structured event. Trace files and transcript persistence consume the event; the loop does not call many subsystem-specific record methods.

## Tool Surface

Target stable tool set:

1. `Read`
2. `Edit` — create, replace, and atomic multi-edit modes
3. `Bash`
4. `Glob`
5. `Grep`
6. `Todo` — keep only if completion semantics rely on it
7. `Task` — restricted Explore/Verification only, default verification agent off

`Write`, `MultiEdit`, `ListFiles`, and `SearchFilesByName` are migration aliases only while old sessions/tests are converted. They must not remain in the final schema.

## Persistence Model

- Transcript: append-only message, tool lifecycle, checkpoint, and terminal facts.
- Compact checkpoint: summary plus retain boundary; never destroys transcript history.
- Model view: derived for a request and not separately persisted as truth.
- Session snapshots: temporary compatibility input during migration, then removed.

## Default vs Optional

| Capability | Default | Installation |
|---|---:|---|
| Single-agent runtime | on | core |
| Filesystem/shell tools | on | core |
| Deterministic completion | on | core |
| JSONL trace | on, lightweight | core |
| Skills | on only when discovered; no scan churn | core |
| Verification subagent | off | core |
| MCP | off | `mycodeagent[mcp]` |
| Teams | removed | Git history only |
| Skill Evolution | removed | Git history only |

## Complexity Budgets

Budgets are guardrails, not reasons to distort code:

- Stable production Python: at most 15,000 lines.
- `runtime/loop.py`: target at most 650 lines.
- `runtime/host.py`: target at most 500 lines.
- Core required third-party dependencies: at most five.
- Stable tools exposed to the model: at most seven.
- One current architecture document and one concise README path; historical plans are clearly marked historical.
