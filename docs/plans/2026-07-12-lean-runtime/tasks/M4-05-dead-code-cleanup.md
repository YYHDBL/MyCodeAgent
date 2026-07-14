# M4-05 Dead Code and Compatibility Cleanup Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `ponytail:ponytail-review` and `superpowers:verification-before-completion`.

**Goal:** Delete compatibility exports, single-implementation abstractions, dead files, and stale flags left by prior milestones.

**Architecture:** Make only behavior-preserving deletions proven by call-site and test evidence; introduce no replacement layer unless a live boundary needs it.

**Tech Stack:** Python, ripgrep, Git diff, pytest.

**Dependencies:** M4-04.

**Files:**

- Delete if no callers: `runtime/observation_store.py`
- Delete if empty/unused: `utils/serialization.py`
- Modify/delete: `core/agent.py`
- Modify/delete: obsolete helpers in `runtime/factory.py`, `runtime/session.py`, `tools/observation_budget.py`
- Modify: imports/tests/docs directly affected by deletions
- Create: `docs/plans/2026-07-12-lean-runtime/CLEANUP_REPORT.md`

## Hunt List

- compatibility re-export modules;
- ABC/protocol with one implementation and no test seam value;
- factories with one product;
- wrappers that only delegate;
- flags/config fields no longer set;
- duplicate helpers for hashing, serialization, path handling, and observation truncation;
- files containing only a docstring or export alias;
- historical tests that assert removed architecture text.

## Steps

1. Use `rg` to prove call-site counts before each deletion.
2. Delete in small batches and run focused tests after each batch.
3. Do not combine semantic behavior changes with cleanup.
4. Run import smoke tests and the full core suite.
5. Record deleted lines/files and any consciously retained abstraction with its justification.

## Acceptance

- No compatibility module remains without an active migration consumer.
- Cleanup report is evidence-based and does not claim speculative savings.
- Commit: `refactor(M4-05): remove obsolete compatibility layers`.
