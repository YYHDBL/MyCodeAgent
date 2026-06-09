# Phase 6A Transcript Resume Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add append-only transcript recording and resume semantics for the harness without collapsing transcript, loop state, and model view into one messages array.

**Architecture:** Add a dedicated transcript module that owns append-only JSONL persistence, schema validation, and resume reconstruction. Integrate it through `CodeAgent`, `RuntimeRunner`, and `ToolOrchestrator` via a narrow recorder interface so trace logging remains diagnostic-only and `ContextEngine` remains the sole model-view projection layer.

**Tech Stack:** Python, pytest, JSONL persistence, existing runtime/history/context abstractions.

---

### Task 1: Lock the expected behavior with failing tests

**Files:**
- Create: `tests/runtime/test_transcript.py`
- Modify: `tests/runtime/test_runner.py`

**Step 1: Write the failing tests**

Cover:
- transcript event schema fields and allowed event types
- append-only JSONL readback
- trailing half-JSON record ignored
- completed tool lifecycle restored without re-execution
- started but incomplete mutating tool restored as uncertain
- messages and state transitions rebuild correctly
- multiple runs in one transcript stay isolated by `run_id`
- resume rebuilds history while `ContextEngine` still produces the model view
- trace logger and transcript store remain separate responsibilities

**Step 2: Run tests to verify they fail**

Run:
`pytest tests/runtime/test_transcript.py tests/runtime/test_runner.py -q`

Expected:
Failing imports and missing transcript/resume behavior.

### Task 2: Add transcript schema and store

**Files:**
- Create: `runtime/transcript.py`
- Modify: `runtime/__init__.py`

**Step 1: Write minimal production structures**

Add:
- `TranscriptEventType`
- `ToolLifecycleStatus`
- `UncertainAction`
- `ResumeState`
- `TranscriptStore`

**Step 2: Implement append/read behavior**

Requirements:
- JSONL append-only writer
- flush on every full event
- ignore final malformed trailing line
- helpers for message, state transition, tool lifecycle, checkpoint, terminal events

**Step 3: Run focused tests**

Run:
`pytest tests/runtime/test_transcript.py -q`

Expected:
New transcript tests pass or narrow remaining failures to runtime integration.

### Task 3: Centralize runtime recording and resume reconstruction

**Files:**
- Modify: `runtime/host.py`
- Modify: `runtime/loop.py`
- Modify: `tools/orchestrator.py`
- Modify: `runtime/history.py`
- Modify: `runtime/context/engine.py` only if resume helpers are needed

**Step 1: Add a narrow transcript recorder surface on the host**

Recorder responsibilities:
- persist user/assistant/tool messages
- persist loop state transitions
- persist checkpoints and terminal events
- persist tool lifecycle requested/started/completed/failed

**Step 2: Resume support**

Load transcript facts into:
- history messages
- current loop/checkpoint state
- terminal status
- uncertain/pending tool actions
- read cache or minimal runtime state only where already supported

**Step 3: Enforce uncertain action policy**

Rules:
- `completed` keeps result, no replay
- `failed` keeps failure fact
- `requested` without `started` is replannable, not auto-executed
- `started` without terminal tool status becomes uncertain
- uncertain `Write`/`Edit`/`MultiEdit`/`Bash`/`Task` cannot auto-replay

### Task 4: Verify full scope

**Files:**
- No new code expected unless tests expose defects

**Step 1: Run targeted transcript/resume tests**

Run:
`pytest tests/runtime/test_transcript.py tests/runtime/test_runner.py -q`

**Step 2: Run runtime suite**

Run:
`pytest tests/runtime -q`

**Step 3: Run Phase 0 scenarios**

Run:
`pytest tests/scenarios/test_phase0_baselines.py -q`

**Step 4: Run non-experimental full suite**

Run:
`pytest $(find tests -path 'tests/experimental' -prune -o -name 'test_*.py' -print) -q`

**Step 5: Run diff hygiene**

Run:
`git diff --check`
