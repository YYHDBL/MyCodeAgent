# ToolOrchestrator v1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract tool-call handling from `RuntimeRunner._react_loop()` into a lightweight `ToolOrchestrator` while preserving current serial execution behavior.

**Architecture:** Keep `RuntimeRunner` responsible for the agent loop and state transitions. Add `tools/orchestrator.py` as the boundary that turns model `tool_calls` into ordered tool observations. v1 is deliberately serial and behavior-preserving; batching, concurrency, result budgeting, and hooks belong to later versions.

**Tech Stack:** Python 3, dataclasses, pytest, existing `ToolExecutor`, existing `ToolRegistry`, existing runtime trace logger.

---

## Scope

This is a harness-boundary refactor, not a feature expansion.

v1 should make one thing true:

```text
runtime/loop.py no longer owns per-tool execution details.
```

It should not make tools faster or smarter yet. The value is architectural: the agent loop asks for tool execution; the orchestrator performs the controlled lifecycle and returns ordered results.

## Non-Goals

Do not implement these in v1:

- tool concurrency
- `partition_tool_calls()`
- read-only classification
- Bash read-only detection
- PreToolUse / PostToolUse hooks
- permission modes beyond the existing permission checker
- tool result budget / large result persistence
- streaming tool execution
- sibling cancellation
- tombstone or streaming event protocol changes

If a change requires redesigning tool APIs, it is out of scope for v1.

## Current Reference Points

Read before editing:

- `runtime/loop.py`
- `tools/executor.py`
- `tools/registry.py`
- `tests/runtime/test_runner.py`
- `tests/tools/test_executor.py`
- `free-code/src/services/tools/toolOrchestration.ts`
- `free-code/src/services/tools/toolExecution.ts`

Important current behavior:

- `runtime/loop.py` parses tool arguments with `host._ensure_json_input()`.
- If parsing fails, it creates an `INVALID_PARAM` tool result.
- If execution throws, it creates an `EXECUTION_ERROR` tool result.
- It appends every tool result to history with the original `tool_call_id`.
- It logs `tool_call`, `tool_result`, and `error` trace events.
- It executes tools serially in model-returned order.

v1 must preserve all of that.

## Target Shape

Add:

```text
tools/orchestrator.py
```

Expose:

```python
@dataclass
class ToolObservation:
    tool_name: str
    tool_call_id: str
    observation: str


class ToolOrchestrator:
    def __init__(self, host: Any):
        self.host = host

    def run_serial(self, tool_calls: list[dict[str, Any]], *, step: int, trace_logger) -> list[ToolObservation]:
        ...
```

`RuntimeRunner` should then do:

```python
observations = host.tool_orchestrator.run_serial(tool_calls, step=step, trace_logger=trace_logger)
for obs in observations:
    host.history_manager.append_tool(...)
    host._log_message_write(...)
```

The loop still owns history writes in v1. That keeps the boundary smaller and avoids changing message semantics.

## Task 1: Add ToolOrchestrator Skeleton

**Files:**

- Create: `tools/orchestrator.py`
- Test: `tests/tools/test_orchestrator.py`

**Step 1: Write failing import test**

Create `tests/tools/test_orchestrator.py`:

```python
from tools.orchestrator import ToolObservation, ToolOrchestrator


def test_tool_orchestrator_exports_v1_types():
    assert ToolOrchestrator.__name__ == "ToolOrchestrator"

    obs = ToolObservation(
        tool_name="Echo",
        tool_call_id="call_1",
        observation='{"status": "success"}',
    )

    assert obs.tool_name == "Echo"
    assert obs.tool_call_id == "call_1"
    assert obs.observation == '{"status": "success"}'
```

**Step 2: Run test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/tools/test_orchestrator.py::test_tool_orchestrator_exports_v1_types -q
```

Expected: fails because `tools.orchestrator` does not exist.

**Step 3: Implement minimal module**

Create `tools/orchestrator.py`:

```python
"""Tool call orchestration boundary for the agent runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolObservation:
    tool_name: str
    tool_call_id: str
    observation: str


class ToolOrchestrator:
    """Execute model tool calls while preserving model order."""

    def __init__(self, host: Any):
        self.host = host
```

**Step 4: Run test and verify it passes**

Run:

```bash
.venv/bin/pytest tests/tools/test_orchestrator.py::test_tool_orchestrator_exports_v1_types -q
```

Expected: pass.

## Task 2: Move One Tool Execution Lifecycle Into Orchestrator

**Files:**

- Modify: `tools/orchestrator.py`
- Test: `tests/tools/test_orchestrator.py`

**Step 1: Add fake host and success test**

Append to `tests/tools/test_orchestrator.py`:

```python
import json


class _TraceLogger:
    def __init__(self):
        self.events = []

    def log_event(self, name, payload, step=0):
        self.events.append((name, step, payload))


class _Host:
    def __init__(self):
        self.trace_logger = _TraceLogger()
        self.calls = []
        self.project_root = "."
        self.tool_executor = None

    def _ensure_json_input(self, raw_args):
        if isinstance(raw_args, dict):
            return raw_args, None
        try:
            return json.loads(raw_args), None
        except Exception as exc:
            return {}, exc

    def _execute_tool(self, tool_name, tool_input):
        self.calls.append((tool_name, tool_input))
        return json.dumps({"status": "success", "data": {"ok": True}})


def test_run_serial_executes_one_tool_and_returns_observation():
    host = _Host()
    orchestrator = ToolOrchestrator(host)

    result = orchestrator.run_serial(
        [{"id": "call_1", "name": "Echo", "arguments": '{"text": "hi"}'}],
        step=2,
        trace_logger=host.trace_logger,
    )

    assert len(result) == 1
    assert result[0].tool_name == "Echo"
    assert result[0].tool_call_id == "call_1"
    assert json.loads(result[0].observation)["status"] == "success"
    assert host.calls == [("Echo", {"text": "hi"})]
    assert any(event[0] == "tool_call" for event in host.trace_logger.events)
    assert any(event[0] == "tool_result" for event in host.trace_logger.events)
```

**Step 2: Run test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/tools/test_orchestrator.py::test_run_serial_executes_one_tool_and_returns_observation -q
```

Expected: fails because `run_serial` does not exist.

**Step 3: Implement `run_serial()` success path**

In `tools/orchestrator.py`, add imports:

```python
import json
import traceback as tb
import uuid
```

Add method:

```python
    def run_serial(
        self,
        tool_calls: list[dict[str, Any]],
        *,
        step: int,
        trace_logger,
    ) -> list[ToolObservation]:
        observations: list[ToolObservation] = []
        host = self.host

        for call in tool_calls:
            tool_name = call.get("name") or "unknown_tool"
            tool_call_id = call.get("id") or f"call_{uuid.uuid4().hex}"
            raw_args = call.get("arguments") or {}
            tool_input, parse_err = host._ensure_json_input(raw_args)

            if parse_err:
                observation = self._parse_error_observation(parse_err)
                self._log_parse_error(trace_logger, step, tool_name, tool_call_id, parse_err)
            else:
                trace_logger.log_event(
                    "tool_call",
                    {"tool": tool_name, "args": tool_input, "tool_call_id": tool_call_id},
                    step=step,
                )
                observation = self._execute_one(tool_name, tool_input, trace_logger, step)

            observations.append(
                ToolObservation(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    observation=observation,
                )
            )

        return observations
```

Add helpers:

```python
    def _execute_one(self, tool_name: str, tool_input: dict[str, Any], trace_logger, step: int) -> str:
        host = self.host
        try:
            if hasattr(host, "tool_executor") and host.tool_executor is not None:
                observation = host.tool_executor.execute(tool_name, tool_input)
            else:
                observation = host._execute_tool(tool_name, tool_input)
            self._log_tool_result(trace_logger, step, tool_name, observation)
            return observation
        except Exception as exc:
            error_result = {
                "status": "error",
                "error": {"code": "EXECUTION_ERROR", "message": str(exc)},
                "data": {},
            }
            trace_logger.log_event(
                "error",
                {
                    "stage": "tool_execution",
                    "error_code": "EXECUTION_ERROR",
                    "message": str(exc),
                    "tool": tool_name,
                    "traceback": tb.format_exc(),
                },
                step=step,
            )
            return json.dumps(error_result, ensure_ascii=False)

    def _log_tool_result(self, trace_logger, step: int, tool_name: str, observation: str) -> None:
        try:
            result_obj = json.loads(observation)
            trace_logger.log_event("tool_result", {"tool": tool_name, "result": result_obj}, step=step)
        except json.JSONDecodeError:
            trace_logger.log_event(
                "tool_result",
                {"tool": tool_name, "result": {"text": observation}},
                step=step,
            )
```

**Step 4: Run success test**

Run:

```bash
.venv/bin/pytest tests/tools/test_orchestrator.py::test_run_serial_executes_one_tool_and_returns_observation -q
```

Expected: pass.

## Task 3: Preserve Parse Error Behavior

**Files:**

- Modify: `tools/orchestrator.py`
- Test: `tests/tools/test_orchestrator.py`

**Step 1: Add parse error test**

Append:

```python
def test_run_serial_returns_invalid_param_observation_on_parse_error():
    host = _Host()
    orchestrator = ToolOrchestrator(host)

    result = orchestrator.run_serial(
        [{"id": "call_1", "name": "Echo", "arguments": "{"}],
        step=2,
        trace_logger=host.trace_logger,
    )

    payload = json.loads(result[0].observation)

    assert payload["status"] == "error"
    assert payload["error"]["code"] == "INVALID_PARAM"
    assert host.calls == []
    assert any(
        event[0] == "error" and event[2]["stage"] == "tool_call_parse"
        for event in host.trace_logger.events
    )
```

**Step 2: Run test and verify it fails if helpers are missing**

Run:

```bash
.venv/bin/pytest tests/tools/test_orchestrator.py::test_run_serial_returns_invalid_param_observation_on_parse_error -q
```

Expected: fails until parse error helpers exist.

**Step 3: Add parse error helpers**

Add:

```python
    def _parse_error_observation(self, parse_err: Exception) -> str:
        error_result = {
            "status": "error",
            "error": {
                "code": "INVALID_PARAM",
                "message": f"Tool arguments parse error: {parse_err}",
            },
            "data": {},
        }
        return json.dumps(error_result, ensure_ascii=False)

    def _log_parse_error(self, trace_logger, step: int, tool_name: str, tool_call_id: str, parse_err: Exception) -> None:
        trace_logger.log_event(
            "error",
            {
                "stage": "tool_call_parse",
                "error_code": "INVALID_PARAM",
                "message": str(parse_err),
                "tool": tool_name,
                "tool_call_id": tool_call_id,
            },
            step=step,
        )
```

**Step 4: Run parse error test**

Run:

```bash
.venv/bin/pytest tests/tools/test_orchestrator.py::test_run_serial_returns_invalid_param_observation_on_parse_error -q
```

Expected: pass.

## Task 4: Preserve Execution Exception Behavior

**Files:**

- Modify: `tests/tools/test_orchestrator.py`

**Step 1: Add exception fake and test**

Append:

```python
class _ExplodingHost(_Host):
    def _execute_tool(self, tool_name, tool_input):
        raise RuntimeError("boom")


def test_run_serial_returns_execution_error_observation_on_exception():
    host = _ExplodingHost()
    orchestrator = ToolOrchestrator(host)

    result = orchestrator.run_serial(
        [{"id": "call_1", "name": "Echo", "arguments": '{"text": "hi"}'}],
        step=2,
        trace_logger=host.trace_logger,
    )

    payload = json.loads(result[0].observation)

    assert payload["status"] == "error"
    assert payload["error"]["code"] == "EXECUTION_ERROR"
    assert payload["error"]["message"] == "boom"
    assert any(
        event[0] == "error" and event[2]["stage"] == "tool_execution"
        for event in host.trace_logger.events
    )
```

**Step 2: Run test**

Run:

```bash
.venv/bin/pytest tests/tools/test_orchestrator.py::test_run_serial_returns_execution_error_observation_on_exception -q
```

Expected: pass if Task 2 implemented `_execute_one()` correctly.

## Task 5: Wire Orchestrator Into CodeAgent Bootstrap

**Files:**

- Modify: `runtime/host.py`
- Test: `tests/runtime/test_runner.py`

**Step 1: Add host wiring test**

Append to `tests/runtime/test_runner.py`:

```python
def test_codeagent_initializes_tool_orchestrator():
    agent = CodeAgent.__new__(CodeAgent)
    assert not hasattr(agent, "tool_orchestrator")
```

This test is intentionally not useful as-is for full initialization because `CodeAgent.__init__` is heavier. Prefer a source-level assertion if existing tests use that style.

Instead, add this source assertion:

```python
def test_runtime_host_initializes_tool_orchestrator():
    source = open("runtime/host.py", encoding="utf-8").read()

    assert "from tools.orchestrator import ToolOrchestrator" in source
    assert "self.tool_orchestrator = ToolOrchestrator(self)" in source
```

**Step 2: Run test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/runtime/test_runner.py::test_runtime_host_initializes_tool_orchestrator -q
```

Expected: fails until host imports and initializes orchestrator.

**Step 3: Modify `runtime/host.py`**

Add import:

```python
from tools.orchestrator import ToolOrchestrator
```

After `self.tool_executor` is initialized, add:

```python
self.tool_orchestrator = ToolOrchestrator(self)
```

Do not remove `self.tool_executor`; the orchestrator should reuse it.

**Step 4: Run test**

Run:

```bash
.venv/bin/pytest tests/runtime/test_runner.py::test_runtime_host_initializes_tool_orchestrator -q
```

Expected: pass.

## Task 6: Replace Tool Execution Block in RuntimeRunner

**Files:**

- Modify: `runtime/loop.py`
- Test: `tests/runtime/test_runner.py`

**Step 1: Add test that runner delegates tool execution**

In `_FakeHost.__init__`, set:

```python
self.tool_orchestrator = None
```

Create fake orchestrator:

```python
class _RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def run_serial(self, tool_calls, *, step, trace_logger):
        self.calls.append((tool_calls, step))
        return [
            type(
                "Obs",
                (),
                {
                    "tool_name": "Echo",
                    "tool_call_id": "call_1",
                    "observation": "{\"status\": \"success\", \"data\": {\"echo\": \"hi\"}}",
                },
            )()
        ]
```

Append test:

```python
def test_runtime_runner_delegates_tool_execution_to_orchestrator():
    from runtime.loop import RuntimeRunner

    host = _ToolThenFinalHost()
    host.tool_orchestrator = _RecordingOrchestrator()
    runner = RuntimeRunner(host)

    result = runner.run("hello world", show_raw=False)

    assert result == "tool done"
    assert host.tool_orchestrator.calls
    assert host.history_manager.messages[-2]["role"] == "tool"
```

**Step 2: Run test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/runtime/test_runner.py::test_runtime_runner_delegates_tool_execution_to_orchestrator -q
```

Expected: fails because `RuntimeRunner` still executes tools inline.

**Step 3: Modify tool call branch in `runtime/loop.py`**

Keep this part in loop:

- normalizing missing call ids
- appending assistant tool call message
- logging assistant message
- appending returned observations to history
- `TOOLS_EXECUTED` transition

Replace the inline `for call in tool_calls:` execution body with:

```python
                if getattr(host, "tool_orchestrator", None) is not None:
                    observations = host.tool_orchestrator.run_serial(
                        tool_calls,
                        step=step,
                        trace_logger=trace_logger,
                    )
                else:
                    from tools.orchestrator import ToolOrchestrator

                    observations = ToolOrchestrator(host).run_serial(
                        tool_calls,
                        step=step,
                        trace_logger=trace_logger,
                    )

                for obs in observations:
                    host.history_manager.append_tool(
                        tool_name=obs.tool_name,
                        raw_result=obs.observation,
                        metadata={"step": step, "tool_call_id": obs.tool_call_id},
                        project_root=host.project_root,
                    )
                    host._log_message_write(
                        trace_logger,
                        "tool",
                        obs.observation,
                        {"tool_name": obs.tool_name, "tool_call_id": obs.tool_call_id},
                        step,
                    )

                    if host.console_verbose:
                        display_obs = (
                            obs.observation[:300] + "..."
                            if len(obs.observation) > 300
                            else obs.observation
                        )
                        host._console(f"\n👀 Observation: {display_obs}\n")
                    elif host.logger.isEnabledFor(10):
                        display_obs = (
                            obs.observation[:300] + "..."
                            if len(obs.observation) > 300
                            else obs.observation
                        )
                        host.logger.debug("Observation: %s", display_obs)
```

Remove now-unused imports from `runtime/loop.py` if needed:

- `json`
- `traceback as tb`

Keep `uuid`.

**Step 4: Run delegation test**

Run:

```bash
.venv/bin/pytest tests/runtime/test_runner.py::test_runtime_runner_delegates_tool_execution_to_orchestrator -q
```

Expected: pass.

## Task 7: Verify Behavior Preservation

**Files:**

- No new files.

**Step 1: Run orchestrator tests**

Run:

```bash
.venv/bin/pytest tests/tools/test_orchestrator.py -q
```

Expected: all pass.

**Step 2: Run runtime runner tests**

Run:

```bash
.venv/bin/pytest tests/runtime/test_runner.py -q
```

Expected: all pass.

**Step 3: Run existing executor tests**

Run:

```bash
.venv/bin/pytest tests/tools/test_executor.py -q
```

Expected: all pass.

**Step 4: Run full suite**

Run:

```bash
.venv/bin/pytest -q
```

Expected: all pass.

## Task 8: Inspect Diff

**Files:**

- `tools/orchestrator.py`
- `runtime/host.py`
- `runtime/loop.py`
- `tests/tools/test_orchestrator.py`
- `tests/runtime/test_runner.py`

**Step 1: Inspect scoped diff**

Run:

```bash
git diff -- tools/orchestrator.py runtime/host.py runtime/loop.py tests/tools/test_orchestrator.py tests/runtime/test_runner.py
```

Expected:

- Tool execution logic moved out of `runtime/loop.py`.
- `runtime/loop.py` still appends assistant and tool messages.
- `runtime/loop.py` still emits `TOOLS_EXECUTED`.
- `ToolOrchestrator.run_serial()` preserves serial model order.
- No concurrency logic.
- No batching logic.
- No hooks.
- No result budget.

## Task 9: Commit

**Files:**

- `tools/orchestrator.py`
- `runtime/host.py`
- `runtime/loop.py`
- `tests/tools/test_orchestrator.py`
- `tests/runtime/test_runner.py`

**Step 1: Check status**

Run:

```bash
git status --short
```

There may be unrelated dirty files. Only stage files touched by this plan.

**Step 2: Commit**

Run:

```bash
git add tools/orchestrator.py runtime/host.py runtime/loop.py tests/tools/test_orchestrator.py tests/runtime/test_runner.py
git commit -m "refactor(tools): add serial tool orchestrator"
```

## Why This Matters

This v1 refactor should produce almost no user-visible behavior change. That is intentional.

The learning value is that `MyCodeAgent` starts to match the Claude Code harness shape:

```text
Agent Loop: decides why the loop continues
ToolOrchestrator: decides how actions are executed
ToolExecutor: executes one normalized tool call
ToolRegistry: owns schemas, lookup, result normalization, read cache, circuit breaker
```

After this lands, the next ToolOrchestrator versions become clean:

- v2: `partition_tool_calls()` and read-only batch planning
- v3: result budget and large-result persistence
- v4: permission modes and tool lifecycle hooks
- v5: streaming tool executor

Do not put v2 features into v1.

