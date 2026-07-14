# Long-term Memory Design

## 1. Scope

Phase 8 only implements a minimal cross-session memory loop:

- bounded curated memory
- project/user separation
- frozen snapshot per session
- explicit Memory tool
- atomic file persistence
- lightweight safety screening

It does **not** implement a general memory platform.

## 2. Four Layers

```text
Transcript         Complete session facts and resume source
Session Memory     Current-task goal, progress, decisions, verification state
Long-term Memory   Stable cross-session facts
Model View         The bounded view shown to the model this turn
```

Rules:

- `Transcript` is the recovery source of truth.
- `Session Memory` is derived, session-scoped, and not persistent knowledge.
- `Long-term Memory` is durable but intentionally small.
- `Model View` injects long-term memory as a separate dynamic layer.

## 3. Storage Model

Files:

- `memory/long_term/MEMORY.md`
- `memory/long_term/USER.md`

Format:

```text
entry one
§
entry two
§
entry three
```

`MEMORY.md` stores project/environment constraints, architecture decisions, and tool experience.
`USER.md` stores stable user preferences, identity hints, and explicit corrections.

Each target has its own character budget. The store rejects overflow rather than truncating.

## 4. Frozen Snapshot

At `CodeAgent` startup:

1. Load `MEMORY.md` and `USER.md`.
2. Freeze a snapshot for the current session.
3. Inject that snapshot into `ContextEngine` as dynamic model-view messages.

During the session:

- `Memory` tool writes update disk immediately.
- The current frozen snapshot does not change.
- The new memory only appears after `refresh_long_term_memory_snapshot()` or a new `CodeAgent` session.

This keeps prompt-cache-sensitive stable layers unchanged and makes the memory lifecycle explicit.

## 5. Atomic persistence safety

Mutation path:

1. Acquire a separate lock file.
2. Re-read disk under lock.
3. Validate content and budgets.
4. Persist to a same-directory temporary file.
5. `flush()` + `fsync()`.
6. `os.replace()` atomically.

Failure behavior:

- old file remains intact
- temp file is cleaned up
- writes are rejected on overflow or unsafe content
- duplicate entries are rejected
- replace/remove require a unique substring match

## 6. Security Screen

Because long-term memory enters model context, writes reject:

- prompt-injection phrases
- "ignore instructions" style overrides
- obvious secret-exfiltration command text
- invisible Unicode control characters
- overlong single entries

This is a lightweight harness defense layer, not a complete prompt-security system.

## 7. Explicit Memory Tool

`Memory` supports:

- `action=add`
- `action=replace`
- `action=remove`
- `action=list`

Targets:

- `target=memory`
- `target=user`

Permission boundary:

- main agent: allowed
- explore / verification / readonly subagent: denied
- subagent tool registries do not include `Memory`

The tool returns the **live** on-disk state so the model can see what changed, while the active session still uses the frozen snapshot.

## 8. Trace

Current trace events:

- `long_term_memory_loaded`
- `long_term_memory_write`
- `long_term_memory_rejected`
- `long_term_memory_snapshot_injected`

Trace payloads record counts, limits, targets, and rejection reasons only. Full memory content is intentionally excluded.

## 9. Deliberate Non-goals

Not implemented:

- embeddings
- vector database
- automatic background memory extraction agent
- session search
- external memory provider
- knowledge graph
- automatic cross-project learning
