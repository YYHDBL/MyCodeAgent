# M6-02 JSONL Trace and Eval Cleanup

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development`, `ponytail:ponytail-review`, and `superpowers:verification-before-completion`.

**Goal:** Retain the required JSONL trace boundary while deleting unused HTML rendering and product-side trace-summary helpers.

**Architecture:** Trace events remain JSONL facts consumed by the runtime; no HTML audit renderer, HTML configuration, trace-evaluation production API, or unused trace-protocol export remains. Scenario assertions use direct JSONL event facts or a test-local helper.

**Dependencies:** M6-01.

**Files:**

- Modify: `extensions/tracing/logger.py`, `extensions/tracing/__init__.py`, `core/config.py`, `runtime/host.py`
- Delete: `runtime/evals.py` when all production callers are removed
- Delete: `extensions/tracing/protocol.py` when all production callers are removed
- Modify/delete only corresponding tests, fixtures, demos, and current docs.

## Acceptance

- JSONL tracing remains enabled by default and trace/transcript event parity remains tested.
- No HTML trace flag, renderer, report, or opt-in compatibility layer remains.
- No dead product trace-evaluation API remains; deterministic scenarios retain equivalent event assertions.
- Commit: `refactor(M6-02): keep JSONL tracing only`.
