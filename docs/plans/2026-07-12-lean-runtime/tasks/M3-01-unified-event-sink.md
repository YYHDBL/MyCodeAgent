# M3-01 Unified Runtime Event Sink Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development`.

**Goal:** Replace subsystem-specific recording calls in the loop with one small structured event interface consumed by trace and transcript sinks.

**Architecture:** Emit each runtime fact once through a synchronous composite sink whose adapters project it into transcript and diagnostic trace formats.

**Tech Stack:** Python dataclasses/protocols, JSONL, pytest.

**Dependencies:** M2-04 and M2 milestone gate.

**Files:**

- Create: `runtime/events.py`
- Modify: `runtime/loop.py`
- Modify: `runtime/transcript.py`
- Modify: `extensions/tracing/logger.py`
- Modify: `extensions/tracing/protocol.py`
- Modify: `runtime/factory.py` or current composition owner
- Create: `tests/runtime/test_events.py`
- Modify: `tests/runtime/test_transcript.py`
- Modify: `tests/extensions/test_tracing_extension.py`

## Design Contract

- Runtime emits typed/name-stable events with `run_id`, `step`, `type`, and payload.
- A composite sink fans out to zero or more sinks in deterministic order.
- Sink failure is isolated and observable; it does not corrupt loop state.
- Transcript and diagnostic trace may store different projections, but consume the same event fact.
- No general plugin bus, async broker, event sourcing framework, or global singleton.

## Steps

1. Write tests for no-op, composite order, sink failure isolation, and transcript/trace parity for a sample turn.
2. Define the smallest event dataclass/protocol and sink interface.
3. Adapt transcript recorder and trace logger behind sinks.
4. Convert one loop stage at a time: messages, tool lifecycle, transitions, checkpoints, terminal.
5. Delete redundant `_record_transcript_*`, `_trace_*`, and notification plumbing once all call sites migrate.
6. Run event, trace, transcript, loop, eval, and scenario tests.

## Acceptance

- One logical runtime fact is emitted once by the loop.
- Existing trace event names required by evals remain stable or receive an explicit migration.
- Commit: `refactor(M3-01): unify runtime event emission`.
