# Harness architecture

MyCodeAgent is one local coding-agent runtime, not a team framework. Its
current execution flow is:

```text
CLI → selected project root + Config → CodeAgent composition
    → RuntimeRunner → bounded ModelView → OpenAI-compatible model
    → authorize/execute tools → runtime events → transcript + JSONL trace
    → completion gate → terminal outcome or next turn
```

`RuntimeRunner` is the sole stable loop. `CodeAgent` wires its dependencies;
it does not own a second control flow. The event boundary emits lifecycle,
transition, tool, checkpoint, and terminal facts once, then the transcript and
trace sinks project those facts for their respective uses.

## Project and tool boundary

The CLI resolves the invocation directory as the project by default, or a
valid `--cwd` target when supplied. Sessions, transcripts, traces, tool output
artifacts, filesystem actions, and Bash all use that boundary.

The stable model-visible tools are `Bash`, `Edit`, `Glob`, `Grep`, `Read`,
`Task`, and `TodoWrite`. `FileWorkspace` protects `Read`, `Edit`, `Glob`, and
`Grep` from absolute, traversal, and symlink escapes. `Edit` is the sole
mutation surface: it requires a fresh Read snapshot and atomically replaces a
file only if that snapshot still matches. `Glob` lists or finds paths; `Grep`
searches content. Full oversized results are retained in an artifact and the
model receives a bounded recoverable observation.

Permission policy is an execution gate, not an OS sandbox. Unknown,
invalid, or unsafe requests fail closed. Read-only calls may be batched only
where the orchestrator has explicitly classified them safe; side-effecting
calls remain ordered.

## Context and recovery

History is complete in-process state. `ContextEngine.build_model_view()` is
the only model request boundary; checkpoints compact the view without deleting
facts. An append-only transcript is the durable recovery source for all new
sessions. Resume deterministically rebuilds derived context and session
memory. Completed tool actions are not replayed; actions that started but lack
a matching completion remain explicitly uncertain.

The completion gate evaluates the final model candidate against retained Todo
and tool-evidence facts. Recovery and completion failures have bounded,
observable terminal paths instead of unbounded reflection.

## Defaults and extensions

Normal startup has one local agent, lightweight JSONL tracing, and no MCP
client process or verification subagent. Each enabled trace ends with one
`session_summary` JSONL event containing steps, `tools_used`, and accumulated
token totals. HTML reports, the trace protocol module, and the generic
`runtime.evals` API are removed; this retained summary is not an evaluator.
Local Skills are read-only and loaded only for a project that provides
`skills/**/SKILL.md`. MCP requires the separate `mycodeagent[mcp]` installation
and explicit `--enable-mcp`. Verification is an explicit CLI opt-in and its
enabled bootstrap constructs the completion verifier. Transcript facts and
derived session memory are the complete recovery path; no separate project
memory store is shipped.

Normal lint enforces undefined-name and basic dead-code rules. Release checks
also run strict `E722,F401,F541,F821,F841` selection and `E402` against stable
packages; neither is a type-checking guarantee. The release-metric command
enforces the user-approved 15,000-line cap; the current 14,094-line tree passes
while the seven-tool and dependency caps remain unchanged. See closeout
[C-008](plans/2026-07-14-lean-runtime-closeout/DECISIONS.md#c-008-raise-the-stable-production-budget-to-15000-lines).

Removed research systems are absent from the stable tree. Their recoverable
history is named in [research-archive.md](research-archive.md).
Superseded design documents, task breakdowns, portfolio material, and demo
snapshots are labelled [historical](archives/README.md), not current API
contracts.
