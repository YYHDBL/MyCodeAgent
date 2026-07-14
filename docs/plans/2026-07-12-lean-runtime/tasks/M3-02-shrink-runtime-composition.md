# M3-02 Shrink Runtime Composition Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and `ponytail:ponytail-review` on the final diff.

**Goal:** Make RuntimeRunner express the turn state machine clearly and reduce Host/composition plumbing without creating more layers.

**Architecture:** Keep orchestration in one runner, dependencies in one host, and use direct builder functions for one-time composition.

**Tech Stack:** Python, dataclasses, pytest, existing runtime/context/tool modules.

**Dependencies:** M3-01.

**Files:**

- Modify: `runtime/loop.py`
- Modify: `runtime/host.py`
- Modify or delete: `runtime/factory.py`
- Modify: `app/bootstrap.py`
- Modify: `runtime/state.py` only if transition data can be simplified safely
- Modify: `tests/runtime/test_runner.py`
- Modify: `tests/runtime/test_host.py`
- Modify: `tests/runtime/test_phase0_boundaries.py`

## Target Shape

The loop should visibly contain these stages:

```text
prepare_run → prepare_step → call_model → handle_model_result
→ execute_tools or evaluate_completion → finish_run
```

Host owns dependencies and public lifecycle operations, not duplicated loop behavior. Composition may use simple builder functions; a class factory with one product is unnecessary.

## Steps

1. Replace source-string structure tests with behavior/dependency-boundary tests.
2. Inventory every Host/Runner method and classify it as orchestration, adapter, event, or dead compatibility.
3. Move pure model-response parsing and completion calculation to existing owning modules only when multiple callers/tests justify it.
4. Convert `RuntimeComponentFactory` into narrow builder functions or inline one-time wiring in bootstrap/host.
5. Remove `getattr`-based optional probing for capabilities that are now stable interfaces.
6. Keep recovery budgets, transition reasons, and terminal reasons observable.
7. Run runtime, completion, recovery, context, transcript, subagent, and scenario tests.

## Acceptance

- `runtime/loop.py` target ≤650 lines and `runtime/host.py` target ≤500 lines, or a decision record explains a measured exception.
- No second runtime loop or speculative abstraction appears.
- Commit: `refactor(M3-02): simplify runtime composition`.
