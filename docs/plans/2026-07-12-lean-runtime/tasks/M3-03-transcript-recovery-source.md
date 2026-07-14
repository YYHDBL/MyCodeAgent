# M3-03 Transcript as Recovery Source Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development`.

**Goal:** Make transcript events the sole durable session recovery truth and remove duplicate session snapshot persistence.

**Architecture:** Reconstruct runtime/session state from append-only transcript facts and derive model/session summaries without another persisted message copy.

**Tech Stack:** Python, JSONL, pathlib, pytest.

**Dependencies:** M3-02.

**Files:**

- Modify: `runtime/transcript.py`
- Modify: `runtime/session.py`
- Modify: `runtime/session_memory.py`
- Modify: `runtime/host.py`
- Modify: `app/cli.py`
- Modify: `tests/runtime/test_transcript.py`
- Modify: `tests/runtime/test_session.py`
- Modify: `tests/runtime/test_session_memory.py`
- Modify: `tests/scenarios/test_phase7_subagents.py` only if restore setup changes

## Migration Contract

- New sessions persist and resume from transcript only.
- Existing snapshot files may be read during one migration window, converted to transcript events, and never written again.
- Session memory remains a derived model-view aid, not a competing source of truth.
- Completed tools are not replayed; started-only side effects are reported as uncertain.
- Compact checkpoint state is recoverable without persisting a second full message copy.

## Steps

1. Add transcript-only reconstruction tests for normal, compacted, interrupted, and uncertain-action sessions.
2. Add a legacy snapshot import test if preserving existing local sessions is inexpensive; otherwise write a decision and explicit migration warning.
3. Route CLI `/save`, `/load`, `--resume`, and auto-save behavior through transcript session operations.
4. Stop writing session snapshots and remove snapshot-only host state.
5. Delete dead snapshot helpers/classes/tests after migration coverage passes.
6. Verify session memory derivation is idempotent across resume.
7. Run persistence, context, completion, CLI lifecycle, and scenario suites.

## Acceptance

- A clean run produces no new `session-latest.json` snapshot.
- Resume parity and uncertain-action semantics are deterministic.
- Commit: `refactor(M3-03): use transcript as session truth`.
