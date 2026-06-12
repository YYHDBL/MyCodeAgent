# Phase 8 Long-term Memory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a minimal, reliable long-term memory loop with project/user separation, frozen snapshots, safe file-backed mutation, and a single explicit `Memory` tool.

**Architecture:** Introduce a new `runtime/memory/` package that owns parsing, safety policy, usage accounting, atomic persistence, and model-view rendering. `CodeAgent` and formal subagents keep existing transcript/session-memory flows unchanged; main-agent startup loads a frozen long-term memory snapshot once per session, `ContextEngine` injects it as an independent dynamic layer, and `MemoryTool` mutates only the live store on disk.

**Tech Stack:** Python stdlib (`pathlib`, `tempfile`, `os.replace`, optional `fcntl/msvcrt` locking), existing `Tool`, `ToolRegistry`, `ContextEngine`, `Config`, tracing, and pytest.

---

### Task 1: Add failing tests for long-term memory store parsing and mutation

**Files:**
- Create: `tests/runtime/test_long_term_memory_store.py`
- Reference: `runtime/session_memory.py`
- Reference: `runtime/transcript.py`

**Step 1: Write the failing tests**

Cover:
- `MEMORY.md` / `USER.md` parse and serialize with `\n§\n`
- `load`, `list`, `add`, `replace`, `remove`, `usage`
- duplicate rejection
- unique substring requirement
- ambiguous replace/remove rejection
- over-budget rejection without changing old file
- prompt-injection / invisible-unicode / empty-entry rejection
- frozen snapshot separation between loaded snapshot and live state

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/runtime/test_long_term_memory_store.py -q`
Expected: FAIL because `runtime.memory.store` and related APIs do not exist.

**Step 3: Write minimal implementation**

Create:
- `runtime/memory/__init__.py`
- `runtime/memory/store.py`
- `runtime/memory/policy.py`
- `runtime/memory/model_view.py`

Implement:
- `LongTermMemoryStore`
- bounded entry-list file format
- project/user scope separation
- frozen snapshot capture at load/new-session time
- live mutation APIs
- safe refusal paths with usage metadata

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/runtime/test_long_term_memory_store.py -q`
Expected: PASS

### Task 2: Add failing tests for reliable persistence and concurrency

**Files:**
- Modify: `tests/runtime/test_long_term_memory_store.py`
- Reference: `../hermes-agent/tools/memory_tool.py`

**Step 1: Write the failing tests**

Cover:
- temp file + atomic replace behavior
- write failure preserves old file
- concurrent write drift does not silently overwrite
- live reload before mutation

**Step 2: Run targeted tests to verify failures**

Run: `.venv/bin/python -m pytest tests/runtime/test_long_term_memory_store.py -q`
Expected: FAIL on persistence/concurrency assertions.

**Step 3: Write minimal implementation**

Implement:
- lock file context manager
- read-under-lock before mutation
- same-directory temp file write
- `flush` + `fsync`
- `os.replace`
- drift / conflict detection

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/runtime/test_long_term_memory_store.py -q`
Expected: PASS

### Task 3: Add failing tests for model-view snapshot injection

**Files:**
- Modify: `tests/runtime/test_context_engine.py`
- Modify: `runtime/context/model_view.py`
- Modify: `runtime/context/engine.py`

**Step 1: Write the failing tests**

Cover:
- long-term memory injected without mutating history
- injected payload contains target/source/usage
- frozen snapshot remains unchanged after live writes
- `ModelView` tracks long-term-memory counts/chars
- long-term memory does not change prompt assembly stable fingerprint

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/runtime/test_context_engine.py tests/runtime/test_prompt.py tests/runtime/test_prompt_assembly_trace.py -q`
Expected: FAIL due to missing long-term-memory view support.

**Step 3: Write minimal implementation**

Implement:
- long-term-memory render helpers
- `ContextEngine.set_long_term_memory_snapshot(...)`
- `ContextEngine.reset_long_term_memory_snapshot(...)`
- model-view metadata fields and trace payload
- injection event `long_term_memory_snapshot_injected`

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/runtime/test_context_engine.py tests/runtime/test_prompt.py tests/runtime/test_prompt_assembly_trace.py -q`
Expected: PASS

### Task 4: Add failing tests for Memory tool and permission boundaries

**Files:**
- Create: `tests/tools/test_memory_tool.py`
- Modify: `tests/tools/test_permissions.py`
- Modify: `tests/tools/test_executor.py`
- Modify: `tests/runtime/test_subagents.py`
- Modify: `runtime/host.py`
- Create: `tools/builtin/memory.py`

**Step 1: Write the failing tests**

Cover:
- main agent can register/use `Memory`
- tool returns live state after add/replace/remove/list
- readonly subagent permission core denies `Memory`
- formal subagent registries do not include `Memory`
- disabled config removes or hard-disables tool

**Step 2: Run tests to verify failures**

Run: `.venv/bin/python -m pytest tests/tools/test_memory_tool.py tests/tools/test_permissions.py tests/tools/test_executor.py tests/runtime/test_subagents.py -q`
Expected: FAIL because `Memory` is not registered and not classified.

**Step 3: Write minimal implementation**

Implement:
- single builtin `MemoryTool`
- tool prompt/description with explicit save/do-not-save guidance
- permission-core classification for `Memory`
- host registration only when enabled
- delegate/readonly denial

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/tools/test_memory_tool.py tests/tools/test_permissions.py tests/tools/test_executor.py tests/runtime/test_subagents.py -q`
Expected: PASS

### Task 5: Add failing tests for host lifecycle, config, and new-session semantics

**Files:**
- Modify: `tests/runtime/test_host.py`
- Modify: `tests/runtime/test_runner.py`
- Modify: `tests/runtime/test_transcript.py`
- Modify: `core/config.py`
- Modify: `runtime/host.py`

**Step 1: Write the failing tests**

Cover:
- config fields: `long_term_memory_enabled`, `memory_char_limit`, `user_memory_char_limit`, `user_memory_path`, `memory_nudge_interval`
- host loads snapshot once at init/new-session, not every turn
- new host/session sees latest disk state
- same host live write does not alter frozen snapshot
- no automatic write from Session Memory to Long-term Memory

**Step 2: Run tests to verify failures**

Run: `.venv/bin/python -m pytest tests/runtime/test_host.py tests/runtime/test_runner.py tests/runtime/test_transcript.py -q`
Expected: FAIL because host lifecycle/config hooks are missing.

**Step 3: Write minimal implementation**

Implement:
- config/env parsing
- host-owned `long_term_memory_store`
- explicit `reset_memory_snapshot()` / `start_new_session()` style API
- optional light nudge counter or documented stub

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/runtime/test_host.py tests/runtime/test_runner.py tests/runtime/test_transcript.py -q`
Expected: PASS

### Task 6: Add failing tests for tracing and privacy

**Files:**
- Modify: `tests/test_trace_logger.py`
- Modify: `extensions/tracing/protocol.py`
- Modify: `runtime/context/engine.py`
- Modify: `runtime/host.py`

**Step 1: Write the failing tests**

Cover:
- `long_term_memory_loaded`
- `long_term_memory_write`
- `long_term_memory_rejected`
- `long_term_memory_snapshot_injected`
- payload contains counts/usage/reasons but not full memory text

**Step 2: Run tests to verify failures**

Run: `.venv/bin/python -m pytest tests/test_trace_logger.py tests/runtime/test_context_engine.py -q`
Expected: FAIL because event specs/logging are incomplete.

**Step 3: Write minimal implementation**

Implement trace event declarations and payload logging with redacted metadata only.

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_trace_logger.py tests/runtime/test_context_engine.py -q`
Expected: PASS

### Task 7: Add targeted regression coverage and documentation

**Files:**
- Modify: `tests/scenarios/test_phase0_baselines.py`
- Modify: `docs/HARNESS.md`
- Modify: `docs/HARNESS_ROADMAP.md`
- Add: `docs/HARNESS_LONG_TERM_MEMORY.md`
- Modify: `README.md` (only if needed)

**Step 1: Write/update tests**

Cover:
- Phase 0-7 no-regression expectations
- disabled config does not affect agent core

**Step 2: Run targeted regressions**

Run: `.venv/bin/python -m pytest tests/scenarios/test_phase0_baselines.py tests/runtime tests/tools tests/scenarios -q`
Expected: PASS

**Step 3: Update docs**

Document:
- four-layer boundary: Transcript / Session Memory / Long-term Memory / Model View
- MEMORY.md vs USER.md
- frozen snapshot design
- implemented vs not implemented

**Step 4: Final verification**

Run:
- `.venv/bin/python -m pytest tests/runtime/test_long_term_memory_store.py tests/tools/test_memory_tool.py -q`
- `.venv/bin/python -m pytest tests/runtime tests/tools tests/scenarios -q`
- `.venv/bin/python -m pytest -q -k 'not experimental'`
- `git diff --check`

Expected: PASS with no diff formatting errors.
