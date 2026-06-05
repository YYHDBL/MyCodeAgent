# Agent Loop State v1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a lightweight Agent Loop state layer to `MyCodeAgent` so each loop continuation and terminal path records an explicit reason without changing runtime behavior.

**Architecture:** Keep the existing `RuntimeRunner` loop shape. Add `runtime/state.py` with small dataclasses/enums, then instrument the existing compact, empty-response, tool, final-answer, and max-steps paths with state transitions. This is a learning-oriented harness improvement, not a full Claude Code clone.

**Tech Stack:** Python 3, dataclasses, enum, pytest, existing `RuntimeRunner`, existing trace logger.

---

## Constraints

Do not broaden the scope.

- Do not rewrite `_react_loop()` into a new architecture.
- Do not change `RuntimeRunner.run()` return type.
- Do not change tool execution order.
- Do not add tool concurrency.
- Do not implement Stop Hook, fallback, Context Collapse, or token budget continuation.
- Do not modify `HistoryManager.compact()` behavior.
- Do not touch unrelated tracing files unless a test proves it is necessary.

The only runtime behavior change should be additional state objects and trace events.

## Existing Reference Points

Read these before editing:

- `runtime/loop.py`
- `tests/runtime/test_runner.py`
- `docs/plans/2026-06-05-agent-loop-state-v1-design.md`
- `free-code/src/query.ts`, especially its `State` and `transition.reason` usage

Current important locations:

- `runtime/loop.py:96`: `_react_loop()`
- `runtime/loop.py:119`: proactive compaction
- `runtime/loop.py:192`: model call and empty-response retry
- `runtime/loop.py:270`: tool call handling
- `runtime/loop.py:387`: final answer
- `runtime/loop.py:403`: max-steps fallback

## Acceptance Criteria

All criteria must pass:

- `runtime/state.py` exists and exports `LoopState`, `Transition`, `TransitionReason`, and `TerminalReason`.
- `RuntimeRunner` creates a `LoopState` during `_react_loop()`.
- Trace logger receives `state_transition` events for final answer, tool execution, empty response retry, and max steps.
- Existing behavior stays the same: final answers, tool calls, empty-response retry, compaction, and max steps still work as before.
- `pytest tests/runtime/test_runner.py -q` passes.
- Full test suite passes with the project venv if available: `.venv/bin/pytest -q`.

## Task 1: Add Runtime State Types

**Files:**

- Create: `runtime/state.py`
- Test: `tests/runtime/test_runner.py`

**Step 1: Write failing import test**

Append a test to `tests/runtime/test_runner.py`:

```python
def test_runtime_state_types_are_importable():
    from runtime.state import LoopState, TerminalReason, Transition, TransitionReason

    transition = Transition(reason=TransitionReason.USER_INPUT, details={"input": "hello"})
    state = LoopState(messages=[], step=1, turn_count=1, tool_choice="auto", transition=transition)

    assert state.transition.reason is TransitionReason.USER_INPUT
    assert state.transition.details == {"input": "hello"}
    assert TerminalReason.COMPLETED.value == "completed"
```

**Step 2: Run test and verify it fails**

Run:

```bash
pytest tests/runtime/test_runner.py::test_runtime_state_types_are_importable -q
```

Expected: fails with `ModuleNotFoundError: No module named 'runtime.state'`.

**Step 3: Create `runtime/state.py`**

Add:

```python
"""Lightweight loop state for the runtime agent harness."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any


class TransitionReason(str, Enum):
    USER_INPUT = "user_input"
    CONTEXT_COMPACTED = "context_compacted"
    MODEL_EMPTY_RETRY = "model_empty_retry"
    MODEL_EMPTY_FAILED = "model_empty_failed"
    MODEL_RETURNED_TOOL_CALLS = "model_returned_tool_calls"
    TOOLS_EXECUTED = "tools_executed"
    MODEL_RETURNED_FINAL = "model_returned_final"
    STOP_HOOK_BLOCKING = "stop_hook_blocking"
    MAX_STEPS_EXCEEDED = "max_steps_exceeded"
    UNRECOVERABLE_ERROR = "unrecoverable_error"


class TerminalReason(str, Enum):
    COMPLETED = "completed"
    EMPTY_RESPONSE_FAILED = "empty_response_failed"
    MAX_STEPS = "max_steps"
    TOOL_ERROR_UNRECOVERABLE = "tool_error_unrecoverable"
    USER_ABORT = "user_abort"
    MODEL_ERROR = "model_error"


@dataclass(frozen=True)
class Transition:
    reason: TransitionReason
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LoopState:
    messages: list[dict[str, Any]]
    step: int
    turn_count: int
    tool_choice: str
    transition: Transition | None = None
    compact_attempted: bool = False
    empty_response_retry_used: bool = False
    max_output_recovery_count: int = 0
    stop_hook_active: bool = False
    last_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    last_response_meta: dict[str, Any] = field(default_factory=dict)
    last_error: str | None = None

    def next(self, reason: TransitionReason, **changes: Any) -> "LoopState":
        details = changes.pop("details", {})
        return replace(self, transition=Transition(reason=reason, details=details), **changes)
```

**Step 4: Run test and verify it passes**

Run:

```bash
pytest tests/runtime/test_runner.py::test_runtime_state_types_are_importable -q
```

Expected: pass.

## Task 2: Add Transition Logging Helper

**Files:**

- Modify: `runtime/loop.py`
- Test: `tests/runtime/test_runner.py`

**Step 1: Write failing helper-level behavior test**

Append:

```python
def test_runtime_runner_transition_logs_state_event():
    from runtime.loop import RuntimeRunner
    from runtime.state import LoopState, TransitionReason

    host = _FakeHost()
    runner = RuntimeRunner(host)
    state = LoopState(messages=[], step=1, turn_count=1, tool_choice="auto")

    next_state = runner._transition(
        state,
        TransitionReason.MODEL_RETURNED_FINAL,
        host.trace_logger,
        step=1,
        final_length=12,
    )

    assert next_state.transition.reason is TransitionReason.MODEL_RETURNED_FINAL
    assert next_state.transition.details == {"final_length": 12}
    assert ("state_transition", 1, {
        "step": 1,
        "turn_count": 1,
        "reason": "model_returned_final",
        "details": {"final_length": 12},
    }) in host.trace_logger.events
```

**Step 2: Run test and verify it fails**

Run:

```bash
pytest tests/runtime/test_runner.py::test_runtime_runner_transition_logs_state_event -q
```

Expected: fails because `_transition` does not exist.

**Step 3: Modify `runtime/loop.py` imports**

Add imports near the top:

```python
from runtime.state import LoopState, TerminalReason, TransitionReason
```

`TerminalReason` may initially be unused until Task 5. If lint complains, import it later instead.

**Step 4: Add `_transition()` to `RuntimeRunner`**

Inside `RuntimeRunner`, after `__init__`, add:

```python
    def _transition(
        self,
        state: LoopState,
        reason: TransitionReason,
        trace_logger,
        *,
        step: int | None = None,
        **details: Any,
    ) -> LoopState:
        next_state = state.next(reason, details=details)
        if trace_logger:
            trace_logger.log_event(
                "state_transition",
                {
                    "step": next_state.step,
                    "turn_count": next_state.turn_count,
                    "reason": reason.value,
                    "details": details,
                },
                step=step if step is not None else next_state.step,
            )
        return next_state
```

**Step 5: Run test and verify it passes**

Run:

```bash
pytest tests/runtime/test_runner.py::test_runtime_runner_transition_logs_state_event -q
```

Expected: pass.

## Task 3: Initialize LoopState in `_react_loop()`

**Files:**

- Modify: `runtime/loop.py`
- Test: `tests/runtime/test_runner.py`

**Step 1: Write failing integration test**

Append:

```python
def test_runtime_runner_emits_user_input_transition():
    from runtime.loop import RuntimeRunner

    host = _FakeHost()
    runner = RuntimeRunner(host)

    runner.run("hello world", show_raw=False)

    transitions = [event for event in host.trace_logger.events if event[0] == "state_transition"]
    assert any(event[2]["reason"] == "user_input" for event in transitions)
```

**Step 2: Run test and verify it fails**

Run:

```bash
pytest tests/runtime/test_runner.py::test_runtime_runner_emits_user_input_transition -q
```

Expected: fails because no `user_input` state transition is logged.

**Step 3: Initialize state at `_react_loop()` entry**

At the start of `_react_loop()`, after `tool_choice = "auto"`, add:

```python
        state = LoopState(
            messages=[],
            step=1,
            turn_count=1,
            tool_choice=tool_choice,
        )
        state = self._transition(
            state,
            TransitionReason.USER_INPUT,
            trace_logger,
            step=0,
            pending_input_len=len(pending_input or ""),
        )
```

**Step 4: Run test and verify it passes**

Run:

```bash
pytest tests/runtime/test_runner.py::test_runtime_runner_emits_user_input_transition -q
```

Expected: pass.

## Task 4: Record Compact, Empty-Response, Tool, and Final Transitions

**Files:**

- Modify: `runtime/loop.py`
- Modify: `tests/runtime/test_runner.py`

**Step 1: Add transition assertion to existing final-answer test**

In `test_runtime_runner_executes_turn_loop_and_returns_final_answer`, add:

```python
    transitions = [event for event in host.trace_logger.events if event[0] == "state_transition"]
    assert any(event[2]["reason"] == "model_returned_final" for event in transitions)
```

Run:

```bash
pytest tests/runtime/test_runner.py::test_runtime_runner_executes_turn_loop_and_returns_final_answer -q
```

Expected: fails until final transition is added.

**Step 2: Add final-answer transition**

Before `trace_logger.log_event("finish", ...)` in final answer path, add:

```python
            state = state.next(
                TransitionReason.MODEL_RETURNED_FINAL,
                step=step,
                turn_count=state.turn_count,
                details={"final_length": len(final_text)},
            )
            state = self._transition(
                state,
                TransitionReason.MODEL_RETURNED_FINAL,
                trace_logger,
                step=step,
                final_length=len(final_text),
            )
```

Important: if this double-sets transition awkwardly, use only `_transition()`. Keep the code simple:

```python
            state = self._transition(
                state,
                TransitionReason.MODEL_RETURNED_FINAL,
                trace_logger,
                step=step,
                final_length=len(final_text),
            )
```

**Step 3: Run final-answer test**

Run:

```bash
pytest tests/runtime/test_runner.py::test_runtime_runner_executes_turn_loop_and_returns_final_answer -q
```

Expected: pass.

**Step 4: Add empty-response retry test**

Create a fake host variant in `tests/runtime/test_runner.py`:

```python
class _EmptyThenFinalHost(_FakeHost):
    def __init__(self):
        super().__init__()
        self.responses = [
            {"choices": [{"message": {"content": ""}}]},
            {"choices": [{"message": {"content": "after retry"}}]},
        ]

        class _FakeLLM:
            def __init__(self, outer):
                self.outer = outer

            def invoke_raw(self, messages, tools=None, tool_choice=None):
                self.outer.llm_calls.append(
                    {"messages": messages, "tools": tools, "tool_choice": tool_choice}
                )
                return self.outer.responses.pop(0)

        self.llm = _FakeLLM(self)
```

Append test:

```python
def test_runtime_runner_emits_empty_response_retry_transition():
    from runtime.loop import RuntimeRunner

    host = _EmptyThenFinalHost()
    runner = RuntimeRunner(host)

    result = runner.run("hello world", show_raw=False)

    assert result == "after retry"
    transitions = [event for event in host.trace_logger.events if event[0] == "state_transition"]
    assert any(event[2]["reason"] == "model_empty_retry" for event in transitions)
```

Run:

```bash
pytest tests/runtime/test_runner.py::test_runtime_runner_emits_empty_response_retry_transition -q
```

Expected: fails until transition is added.

**Step 5: Add empty-response retry transition**

Inside the `if not empty_retry_used:` branch, before `continue`, add:

```python
                    state = self._transition(
                        state,
                        TransitionReason.MODEL_EMPTY_RETRY,
                        trace_logger,
                        step=step,
                        finish_reason=response_meta.get("finish_reason"),
                    )
```

Run the empty-response test again. Expected: pass.

**Step 6: Add tool execution transition test**

Create a fake host variant:

```python
class _ToolThenFinalHost(_FakeHost):
    def __init__(self):
        super().__init__()
        self.responses = [
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "Echo",
                                        "arguments": "{\"text\": \"hi\"}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"content": "tool done"}}]},
        ]

        class _FakeLLM:
            def __init__(self, outer):
                self.outer = outer

            def invoke_raw(self, messages, tools=None, tool_choice=None):
                self.outer.llm_calls.append(
                    {"messages": messages, "tools": tools, "tool_choice": tool_choice}
                )
                return self.outer.responses.pop(0)

        self.llm = _FakeLLM(self)

    def _extract_tool_calls(self, raw_response):
        message = raw_response["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        normalized = []
        for call in calls:
            fn = call.get("function", {})
            normalized.append({
                "id": call.get("id"),
                "name": fn.get("name"),
                "arguments": fn.get("arguments"),
            })
        return normalized

    def _execute_tool(self, tool_name, tool_input):
        return "{\"status\": \"success\", \"data\": {\"echo\": \"hi\"}}"
```

Append test:

```python
def test_runtime_runner_emits_tools_executed_transition():
    from runtime.loop import RuntimeRunner

    host = _ToolThenFinalHost()
    runner = RuntimeRunner(host)

    result = runner.run("use tool", show_raw=False)

    assert result == "tool done"
    transitions = [event for event in host.trace_logger.events if event[0] == "state_transition"]
    assert any(event[2]["reason"] == "model_returned_tool_calls" for event in transitions)
    assert any(event[2]["reason"] == "tools_executed" for event in transitions)
```

Run:

```bash
pytest tests/runtime/test_runner.py::test_runtime_runner_emits_tools_executed_transition -q
```

Expected: fails until transitions are added.

**Step 7: Add tool transitions**

Immediately after tool call ids are normalized, add:

```python
                state = self._transition(
                    state,
                    TransitionReason.MODEL_RETURNED_TOOL_CALLS,
                    trace_logger,
                    step=step,
                    tool_count=len(tool_calls),
                )
```

After the `for call in tool_calls:` loop completes, before `continue`, add:

```python
                state = self._transition(
                    state,
                    TransitionReason.TOOLS_EXECUTED,
                    trace_logger,
                    step=step,
                    tool_count=len(tool_calls),
                )
```

Run the tool transition test. Expected: pass.

**Step 8: Add compact transition only if easy**

If current tests already have a compacting fake host, add a test now. If not, skip to keep v1 small.

Manual code placement:

After successful compression, near `compressed = bool(compress_info.get("compressed"))` and inside `if compressed:`, add:

```python
                    state = self._transition(
                        state,
                        TransitionReason.CONTEXT_COMPACTED,
                        trace_logger,
                        step=step,
                        messages_before=messages_before,
                        messages_after=messages_after,
                    )
                    state = state.next(
                        TransitionReason.CONTEXT_COMPACTED,
                        compact_attempted=True,
                        details=state.transition.details if state.transition else {},
                    )
```

Prefer a simpler version if possible:

```python
                    state = self._transition(
                        state,
                        TransitionReason.CONTEXT_COMPACTED,
                        trace_logger,
                        step=step,
                        messages_before=messages_before,
                        messages_after=messages_after,
                    )
                    state = state.next(
                        TransitionReason.CONTEXT_COMPACTED,
                        compact_attempted=True,
                        details={"messages_before": messages_before, "messages_after": messages_after},
                    )
```

If this looks too noisy in implementation, update `_transition()` to accept `**changes` in a later refactor. Do not over-engineer it in this task.

## Task 5: Record Terminal Reasons

**Files:**

- Modify: `runtime/loop.py`
- Modify: `tests/runtime/test_runner.py`

**Step 1: Add helper to log terminal events**

Add method to `RuntimeRunner`:

```python
    def _terminal(self, reason: TerminalReason, trace_logger, *, step: int = 0, **details: Any) -> None:
        if trace_logger:
            trace_logger.log_event(
                "terminal",
                {"reason": reason.value, "details": details},
                step=step,
            )
```

**Step 2: Add terminal completed assertion**

In `test_runtime_runner_executes_turn_loop_and_returns_final_answer`, add:

```python
    assert any(
        event[0] == "terminal" and event[2]["reason"] == "completed"
        for event in host.trace_logger.events
    )
```

Run:

```bash
pytest tests/runtime/test_runner.py::test_runtime_runner_executes_turn_loop_and_returns_final_answer -q
```

Expected: fails until terminal event is logged.

**Step 3: Log completed terminal**

Before `return final_text`, add:

```python
            self._terminal(
                TerminalReason.COMPLETED,
                trace_logger,
                step=step,
                final_length=len(final_text),
            )
```

Run final-answer test. Expected: pass.

**Step 4: Add max steps test**

Create host variant:

```python
class _AlwaysToolHost(_ToolThenFinalHost):
    def __init__(self):
        super().__init__()
        self.max_steps = 1
        self.responses = [
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "Echo",
                                        "arguments": "{\"text\": \"hi\"}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]
```

Append:

```python
def test_runtime_runner_emits_max_steps_terminal():
    from runtime.loop import RuntimeRunner

    host = _AlwaysToolHost()
    runner = RuntimeRunner(host)

    result = runner.run("loop", show_raw=False)

    assert "限定步数" in result
    assert any(
        event[0] == "terminal" and event[2]["reason"] == "max_steps"
        for event in host.trace_logger.events
    )
```

Run:

```bash
pytest tests/runtime/test_runner.py::test_runtime_runner_emits_max_steps_terminal -q
```

Expected: fails until max steps terminal is logged.

**Step 5: Log max steps transition and terminal**

Before the final fallback return at end of `_react_loop()`, add:

```python
        state = self._transition(
            state,
            TransitionReason.MAX_STEPS_EXCEEDED,
            trace_logger,
            step=host.max_steps,
            max_steps=host.max_steps,
        )
        self._terminal(
            TerminalReason.MAX_STEPS,
            trace_logger,
            step=host.max_steps,
            max_steps=host.max_steps,
        )
```

Run max steps test. Expected: pass.

## Task 6: Run Focused and Full Verification

**Files:**

- No new files.

**Step 1: Run runtime runner tests**

Run:

```bash
pytest tests/runtime/test_runner.py -q
```

Expected: all tests pass.

**Step 2: Run related runtime tests**

Run:

```bash
pytest tests/runtime -q
```

Expected: all tests pass.

**Step 3: Run full suite**

Prefer the venv if it exists:

```bash
.venv/bin/pytest -q
```

Fallback:

```bash
pytest -q
```

Expected: all tests pass.

**Step 4: Inspect diff**

Run:

```bash
git diff -- runtime/state.py runtime/loop.py tests/runtime/test_runner.py
```

Expected:

- New state dataclasses/enums.
- `_transition()` and `_terminal()` helpers.
- Transition events added around existing behavior.
- No tool execution logic rewrite.
- No context compaction rewrite.

## Task 7: Commit

**Files:**

- `runtime/state.py`
- `runtime/loop.py`
- `tests/runtime/test_runner.py`

**Step 1: Check status**

Run:

```bash
git status --short
```

Only stage files touched by this plan. Do not stage unrelated dirty files.

**Step 2: Commit**

Run:

```bash
git add runtime/state.py runtime/loop.py tests/runtime/test_runner.py
git commit -m "feat(runtime): record agent loop state transitions"
```

## Notes for the Implementing Agent

Keep this change boring.

The purpose is not to make the agent smarter today. The purpose is to make the loop observable and ready for later harness work:

- ToolOrchestrator can later use `tools_executed`.
- Stop Hook can later use `model_returned_final` as candidate completion.
- Reactive compact can later use attempt guards.
- Context projection can later use `LoopState.messages` as model view.
- Fallback can later use transition reasons to rebuild only the current turn.

If an implementation starts rewriting large chunks of `_react_loop()`, stop and simplify.

