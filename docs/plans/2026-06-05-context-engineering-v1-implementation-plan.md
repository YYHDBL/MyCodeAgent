# Context Engineering v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new context subsystem that separates full runtime history from the model-facing view, and route the main agent loop through `ContextEngine`.

**Architecture:** `HistoryManager` remains the append-only runtime log for v1. A new `runtime/context/` package owns projection, message normalization, and `ModelView` construction. `RuntimeRunner` asks `ContextEngine` for the current model view and sends that view to the LLM, instead of directly calling `HistoryManager.to_messages()`.

**Tech Stack:** Python dataclasses, existing `HistoryManager`, existing `ContextBuilder`, pytest.

---

## Scope

v1 builds the new skeleton and moves the main model-context path onto it.

v1 includes:
- A new `runtime/context/` package.
- `ModelView` as the explicit object representing "what the model sees".
- Non-mutating projection from full history to model history.
- Message normalization extracted from `HistoryManager.to_messages()`.
- Runtime tracing for `model_view_build`.
- Tests proving full history is not mutated when building model context.

v1 does not include:
- Auto compact.
- Context collapse store.
- Summary checkpoint generation.
- Post-compact restore.
- Microcompact.
- Prompt-cache replacement policy.
- Deleting legacy context code.

Compatibility rule for v1:
- `HistoryManager.to_messages()` may remain for old tests and non-main callers.
- `RuntimeRunner` must not use `HistoryManager.to_messages()` to build the model request.
- v2 will remove or demote legacy context responsibilities after the new path is stable.

---

## Target Structure

Create:
- `runtime/context/__init__.py`: public exports.
- `runtime/context/model_view.py`: `ModelView` dataclass and stats.
- `runtime/context/normalizer.py`: converts `runtime.history.Message` to OpenAI-compatible message dicts.
- `runtime/context/projection.py`: non-mutating projection from full history to active history.
- `runtime/context/engine.py`: orchestrates system messages, projection, normalization, and tracing stats.
- `tests/runtime/test_context_engine.py`: unit tests for the new context subsystem.

Modify:
- `runtime/host.py`: initialize `self.context_engine` after `self.context_builder`.
- `runtime/loop.py`: use `host.context_engine.build_model_view(...)` for model requests.
- `tests/runtime/test_runner.py`: update fake host to expose `context_engine` or verify runner uses the new event.
- `runtime/history.py`: optionally make `to_messages()` delegate to `MessageNormalizer` for compatibility.

Do not modify in v1:
- Tool orchestration behavior.
- Tool result budgeting.
- Session persistence format.
- Existing compact algorithm, except for removing main-loop dependency on its serialized output.

---

## Design Contract

The v1 flow must become:

```text
RuntimeRunner
  -> HistoryManager append/read full runtime messages
  -> ContextEngine.build_model_view(...)
  -> ProjectionBuilder.project(...)
  -> MessageNormalizer.normalize(...)
  -> ContextBuilder.get_system_messages()
  -> ModelView.messages
  -> LLM.invoke_raw(ModelView.messages, ...)
```

`ModelView` is the boundary object. Anything sent to the model should be traceable through a `ModelView`.

```python
@dataclass(frozen=True)
class ModelView:
    messages: list[dict[str, Any]]
    system_message_count: int
    history_message_count: int
    source_message_count: int
    estimated_chars: int
    projection_mode: str = "full_history"
    warnings: tuple[str, ...] = ()
```

v1 projection is intentionally simple:

```text
full history in
same full history out
no mutation
stats recorded
```

The important learning goal is the harness boundary, not compression sophistication.

---

## Task 1: Add ModelView

**Files:**
- Create: `runtime/context/__init__.py`
- Create: `runtime/context/model_view.py`
- Test: `tests/runtime/test_context_engine.py`

- [ ] **Step 1: Write the failing ModelView test**

Add this test file:

```python
from runtime.context import ModelView


def test_model_view_tracks_counts_and_estimated_chars():
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hello"},
    ]

    view = ModelView(
        messages=messages,
        system_message_count=1,
        history_message_count=1,
        source_message_count=1,
        estimated_chars=11,
        projection_mode="full_history",
    )

    assert view.messages == messages
    assert view.system_message_count == 1
    assert view.history_message_count == 1
    assert view.source_message_count == 1
    assert view.estimated_chars == 11
    assert view.projection_mode == "full_history"
    assert view.warnings == ()
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
pytest tests/runtime/test_context_engine.py::test_model_view_tracks_counts_and_estimated_chars -q
```

Expected:

```text
ModuleNotFoundError: No module named 'runtime.context'
```

- [ ] **Step 3: Implement ModelView**

Create `runtime/context/model_view.py`:

```python
"""Model-facing context view types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelView:
    """The exact message view prepared for one model request."""

    messages: list[dict[str, Any]]
    system_message_count: int
    history_message_count: int
    source_message_count: int
    estimated_chars: int
    projection_mode: str = "full_history"
    warnings: tuple[str, ...] = field(default_factory=tuple)
```

Create `runtime/context/__init__.py`:

```python
"""Context engineering subsystem."""

from runtime.context.model_view import ModelView

__all__ = ["ModelView"]
```

- [ ] **Step 4: Run the test and verify it passes**

Run:

```bash
pytest tests/runtime/test_context_engine.py::test_model_view_tracks_counts_and_estimated_chars -q
```

Expected:

```text
1 passed
```

---

## Task 2: Add Non-Mutating Projection

**Files:**
- Create: `runtime/context/projection.py`
- Modify: `runtime/context/__init__.py`
- Test: `tests/runtime/test_context_engine.py`

- [ ] **Step 1: Add failing projection tests**

Append:

```python
from runtime.context import ProjectionBuilder
from runtime.history import HistoryManager


def test_projection_returns_copy_without_mutating_history():
    history = HistoryManager()
    history.append_user("q1")
    history.append_assistant("a1")

    before = history.get_messages()
    projected = ProjectionBuilder().project(before)

    assert projected.messages == before
    assert projected.messages is not before
    assert history.get_message_count() == 2
    assert projected.source_message_count == 2
    assert projected.projection_mode == "full_history"


def test_projection_warnings_default_to_empty_tuple():
    projected = ProjectionBuilder().project([])

    assert projected.messages == []
    assert projected.warnings == ()
```

- [ ] **Step 2: Run the projection tests and verify they fail**

Run:

```bash
pytest tests/runtime/test_context_engine.py::test_projection_returns_copy_without_mutating_history tests/runtime/test_context_engine.py::test_projection_warnings_default_to_empty_tuple -q
```

Expected:

```text
ImportError: cannot import name 'ProjectionBuilder'
```

- [ ] **Step 3: Implement ProjectionBuilder**

Create `runtime/context/projection.py`:

```python
"""Read-time history projection."""

from __future__ import annotations

from dataclasses import dataclass, field

from runtime.history import Message


@dataclass(frozen=True)
class ProjectionResult:
    messages: list[Message]
    source_message_count: int
    projection_mode: str = "full_history"
    warnings: tuple[str, ...] = field(default_factory=tuple)


class ProjectionBuilder:
    """Builds the active history view without mutating the runtime log."""

    def project(self, source_messages: list[Message]) -> ProjectionResult:
        copied = list(source_messages or [])
        return ProjectionResult(
            messages=copied,
            source_message_count=len(source_messages or []),
            projection_mode="full_history",
            warnings=(),
        )
```

Update `runtime/context/__init__.py`:

```python
"""Context engineering subsystem."""

from runtime.context.model_view import ModelView
from runtime.context.projection import ProjectionBuilder, ProjectionResult

__all__ = ["ModelView", "ProjectionBuilder", "ProjectionResult"]
```

- [ ] **Step 4: Run projection tests**

Run:

```bash
pytest tests/runtime/test_context_engine.py::test_projection_returns_copy_without_mutating_history tests/runtime/test_context_engine.py::test_projection_warnings_default_to_empty_tuple -q
```

Expected:

```text
2 passed
```

---

## Task 3: Extract MessageNormalizer

**Files:**
- Create: `runtime/context/normalizer.py`
- Modify: `runtime/context/__init__.py`
- Optional modify: `runtime/history.py`
- Test: `tests/runtime/test_context_engine.py`

- [ ] **Step 1: Add failing normalizer tests**

Append:

```python
import json

from runtime.context import MessageNormalizer
from runtime.history import Message


def test_normalizer_serializes_tool_call_assistant_message():
    normalizer = MessageNormalizer()
    msg = Message(
        content="",
        role="assistant",
        metadata={
            "action_type": "tool_call",
            "tool_calls": [
                {"id": "call_1", "name": "Read", "arguments": {"file_path": "a.py"}}
            ],
        },
    )

    messages = normalizer.normalize([msg])

    assert messages == [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "Read",
                        "arguments": json.dumps({"file_path": "a.py"}, ensure_ascii=False),
                    },
                }
            ],
        }
    ]


def test_normalizer_serializes_tool_result_with_call_id():
    normalizer = MessageNormalizer()
    msg = Message(
        content='{"status":"success"}',
        role="tool",
        metadata={"tool_name": "Read", "tool_call_id": "call_1"},
    )

    messages = normalizer.normalize([msg])

    assert messages == [
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": '{"status":"success"}',
        }
    ]


def test_normalizer_falls_back_tool_without_call_id_to_user_observation():
    normalizer = MessageNormalizer()
    msg = Message(
        content='{"status":"success"}',
        role="tool",
        metadata={"tool_name": "Read"},
    )

    messages = normalizer.normalize([msg])

    assert messages == [
        {
            "role": "user",
            "content": 'Observation (Read): {"status":"success"}',
        }
    ]


def test_normalizer_converts_summary_to_system_message():
    normalizer = MessageNormalizer()
    msg = Message(content="old facts", role="summary")

    messages = normalizer.normalize([msg])

    assert messages == [{"role": "system", "content": "## Summary\nold facts"}]
```

- [ ] **Step 2: Run normalizer tests and verify they fail**

Run:

```bash
pytest tests/runtime/test_context_engine.py::test_normalizer_serializes_tool_call_assistant_message tests/runtime/test_context_engine.py::test_normalizer_serializes_tool_result_with_call_id tests/runtime/test_context_engine.py::test_normalizer_falls_back_tool_without_call_id_to_user_observation tests/runtime/test_context_engine.py::test_normalizer_converts_summary_to_system_message -q
```

Expected:

```text
ImportError: cannot import name 'MessageNormalizer'
```

- [ ] **Step 3: Implement MessageNormalizer**

Create `runtime/context/normalizer.py`:

```python
"""Convert runtime history messages into model API messages."""

from __future__ import annotations

import json
import logging
from typing import Any

from runtime.history import Message

logger = logging.getLogger(__name__)


class MessageNormalizer:
    """Serializes runtime messages into OpenAI-compatible dictionaries."""

    def normalize(self, messages: list[Message]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for msg in messages or []:
            normalized.extend(self._normalize_one(msg))
        return normalized

    def _normalize_one(self, msg: Message) -> list[dict[str, Any]]:
        if msg.role == "user":
            return [{"role": "user", "content": msg.content}]
        if msg.role == "assistant":
            return [self._assistant_message(msg)]
        if msg.role == "tool":
            return [self._tool_message(msg)]
        if msg.role == "summary":
            return [{"role": "system", "content": f"## Summary\n{msg.content}"}]
        return []

    def _assistant_message(self, msg: Message) -> dict[str, Any]:
        metadata = msg.metadata or {}
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": msg.content,
        }

        reasoning_content = metadata.get("reasoning_content")
        if reasoning_content:
            assistant_msg["reasoning_content"] = reasoning_content

        if metadata.get("action_type") == "tool_call":
            tool_calls = metadata.get("tool_calls")
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    self._tool_call_dict(call) for call in tool_calls
                ]
            else:
                legacy_call = self._legacy_tool_call(metadata)
                if legacy_call:
                    assistant_msg["tool_calls"] = [legacy_call]
                else:
                    logger.warning("Strict tool mode active but missing tool_calls")

        return assistant_msg

    def _tool_call_dict(self, call: dict[str, Any]) -> dict[str, Any]:
        name = call.get("name") or "unknown_tool"
        arguments = call.get("arguments") or {}
        args_str = arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)
        return {
            "id": call.get("id"),
            "type": "function",
            "function": {
                "name": name,
                "arguments": args_str,
            },
        }

    def _legacy_tool_call(self, metadata: dict[str, Any]) -> dict[str, Any] | None:
        tool_name = metadata.get("tool_name")
        tool_call_id = metadata.get("tool_call_id")
        if not tool_name or not tool_call_id:
            return None
        return {
            "id": tool_call_id,
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(metadata.get("tool_args") or {}, ensure_ascii=False),
            },
        }

    def _tool_message(self, msg: Message) -> dict[str, Any]:
        metadata = msg.metadata or {}
        tool_call_id = metadata.get("tool_call_id")
        if tool_call_id:
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": msg.content,
            }
        tool_name = metadata.get("tool_name", "unknown")
        return {
            "role": "user",
            "content": f"Observation ({tool_name}): {msg.content}",
        }
```

Update `runtime/context/__init__.py`:

```python
"""Context engineering subsystem."""

from runtime.context.model_view import ModelView
from runtime.context.normalizer import MessageNormalizer
from runtime.context.projection import ProjectionBuilder, ProjectionResult

__all__ = [
    "MessageNormalizer",
    "ModelView",
    "ProjectionBuilder",
    "ProjectionResult",
]
```

- [ ] **Step 4: Optionally delegate HistoryManager.to_messages()**

This keeps legacy callers consistent with the new normalizer.

In `runtime/history.py`, replace the body of `to_messages()` with:

```python
from runtime.context.normalizer import MessageNormalizer

return MessageNormalizer().normalize(self._messages)
```

If this creates an import cycle in local execution, do not delegate yet. Keep `HistoryManager.to_messages()` unchanged for v1 and record this as a v2 cleanup item in the commit message body.

- [ ] **Step 5: Run normalizer tests**

Run:

```bash
pytest tests/runtime/test_context_engine.py -q
```

Expected:

```text
7 passed
```

---

## Task 4: Add ContextEngine

**Files:**
- Create: `runtime/context/engine.py`
- Modify: `runtime/context/__init__.py`
- Test: `tests/runtime/test_context_engine.py`

- [ ] **Step 1: Add failing ContextEngine tests**

Append:

```python
from runtime.context import ContextEngine


class _FakeContextBuilder:
    def get_system_messages(self):
        return [{"role": "system", "content": "system prompt"}]


class _FakeTraceLogger:
    def __init__(self):
        self.events = []

    def log_event(self, name, payload, step=0):
        self.events.append((name, step, payload))


def test_context_engine_builds_model_view_with_system_and_history():
    history = HistoryManager()
    history.append_user("hello")
    engine = ContextEngine(context_builder=_FakeContextBuilder())

    view = engine.build_model_view(history_manager=history, pending_input="hello", step=3)

    assert view.messages == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "hello"},
    ]
    assert view.system_message_count == 1
    assert view.history_message_count == 1
    assert view.source_message_count == 1
    assert view.estimated_chars > 0


def test_context_engine_emits_model_view_build_trace():
    history = HistoryManager()
    history.append_user("hello")
    trace = _FakeTraceLogger()
    engine = ContextEngine(context_builder=_FakeContextBuilder())

    engine.build_model_view(
        history_manager=history,
        pending_input="hello",
        step=5,
        trace_logger=trace,
    )

    assert trace.events
    name, step, payload = trace.events[-1]
    assert name == "model_view_build"
    assert step == 5
    assert payload["system_message_count"] == 1
    assert payload["history_message_count"] == 1
    assert payload["source_message_count"] == 1
    assert payload["projection_mode"] == "full_history"
```

- [ ] **Step 2: Run ContextEngine tests and verify they fail**

Run:

```bash
pytest tests/runtime/test_context_engine.py::test_context_engine_builds_model_view_with_system_and_history tests/runtime/test_context_engine.py::test_context_engine_emits_model_view_build_trace -q
```

Expected:

```text
ImportError: cannot import name 'ContextEngine'
```

- [ ] **Step 3: Implement ContextEngine**

Create `runtime/context/engine.py`:

```python
"""Context model-view construction."""

from __future__ import annotations

from typing import Any

from runtime.context.model_view import ModelView
from runtime.context.normalizer import MessageNormalizer
from runtime.context.projection import ProjectionBuilder


class ContextEngine:
    """Builds the exact model-facing context for a loop iteration."""

    def __init__(
        self,
        context_builder: Any,
        projection_builder: ProjectionBuilder | None = None,
        normalizer: MessageNormalizer | None = None,
    ):
        self.context_builder = context_builder
        self.projection_builder = projection_builder or ProjectionBuilder()
        self.normalizer = normalizer or MessageNormalizer()

    def build_model_view(
        self,
        *,
        history_manager: Any,
        pending_input: str = "",
        step: int = 0,
        trace_logger: Any = None,
    ) -> ModelView:
        source_messages = history_manager.get_messages()
        projection = self.projection_builder.project(source_messages)
        history_messages = self.normalizer.normalize(projection.messages)
        system_messages = self.context_builder.get_system_messages()
        messages = list(system_messages) + list(history_messages)

        estimated_chars = len(pending_input or "")
        for message in messages:
            estimated_chars += len(str(message.get("content", "")))

        view = ModelView(
            messages=messages,
            system_message_count=len(system_messages),
            history_message_count=len(history_messages),
            source_message_count=projection.source_message_count,
            estimated_chars=estimated_chars,
            projection_mode=projection.projection_mode,
            warnings=projection.warnings,
        )

        if trace_logger:
            trace_logger.log_event(
                "model_view_build",
                {
                    "message_count": len(view.messages),
                    "system_message_count": view.system_message_count,
                    "history_message_count": view.history_message_count,
                    "source_message_count": view.source_message_count,
                    "estimated_chars": view.estimated_chars,
                    "projection_mode": view.projection_mode,
                    "warnings": list(view.warnings),
                },
                step=step,
            )

        return view
```

Update `runtime/context/__init__.py`:

```python
"""Context engineering subsystem."""

from runtime.context.engine import ContextEngine
from runtime.context.model_view import ModelView
from runtime.context.normalizer import MessageNormalizer
from runtime.context.projection import ProjectionBuilder, ProjectionResult

__all__ = [
    "ContextEngine",
    "MessageNormalizer",
    "ModelView",
    "ProjectionBuilder",
    "ProjectionResult",
]
```

- [ ] **Step 4: Run context engine tests**

Run:

```bash
pytest tests/runtime/test_context_engine.py -q
```

Expected:

```text
9 passed
```

---

## Task 5: Wire ContextEngine Into Host and Runner

**Files:**
- Modify: `runtime/host.py`
- Modify: `runtime/loop.py`
- Modify: `tests/runtime/test_runner.py`

- [ ] **Step 1: Add failing runner test**

In `tests/runtime/test_runner.py`, update `_FakeHost.__init__` after `self.context_builder = _FakeContextBuilder()`:

```python
from runtime.context import ContextEngine

self.context_engine = ContextEngine(self.context_builder)
```

Add this test:

```python
def test_runtime_runner_builds_model_view_through_context_engine():
    from runtime.loop import RuntimeRunner

    host = _FakeHost()
    runner = RuntimeRunner(host)

    runner.run("hello world", show_raw=False)

    assert any(event[0] == "model_view_build" for event in host.trace_logger.events)
    assert host.llm_calls[0]["messages"][0] == {"role": "system", "content": "system"}
    assert host.llm_calls[0]["messages"][1]["role"] == "user"
```

- [ ] **Step 2: Run the runner test and verify it fails**

Run:

```bash
pytest tests/runtime/test_runner.py::test_runtime_runner_builds_model_view_through_context_engine -q
```

Expected:

```text
AssertionError: assert False
```

- [ ] **Step 3: Initialize ContextEngine in host**

In `runtime/host.py`, add import near other runtime imports:

```python
from runtime.context import ContextEngine
```

After `self.context_builder = ...` is assigned in `CodeAgent.__init__`, add:

```python
self.context_engine = ContextEngine(self.context_builder)
```

Use the actual surrounding constructor style in `runtime/host.py`; do not create a second `ContextBuilder`.

- [ ] **Step 4: Route RuntimeRunner through ContextEngine**

In `runtime/loop.py`, replace this block:

```python
history_messages = host.history_manager.to_messages()
messages = host._build_messages(history_messages)
base_messages = messages
state = state.update(step=step, messages=messages)

trace_logger.log_event(
    "context_build",
    {"message_count": len(messages), "history_count": len(history_messages)},
    step=step,
)
```

With:

```python
model_view = host.context_engine.build_model_view(
    history_manager=host.history_manager,
    pending_input=pending_input,
    step=step,
    trace_logger=trace_logger,
)
messages = model_view.messages
base_messages = messages
state = state.update(step=step, messages=messages)

trace_logger.log_event(
    "context_build",
    {
        "message_count": len(messages),
        "history_count": model_view.history_message_count,
        "source_message_count": model_view.source_message_count,
        "projection_mode": model_view.projection_mode,
    },
    step=step,
)
```

In the compression logging branch, replace:

```python
compressed_history = host.history_manager.to_messages()
final_context = host.context_builder.build_messages(compressed_history)
```

With:

```python
final_context = host.context_engine.build_model_view(
    history_manager=host.history_manager,
    pending_input=pending_input,
    step=step,
    trace_logger=trace_logger,
).messages
```

- [ ] **Step 5: Run runner tests**

Run:

```bash
pytest tests/runtime/test_runner.py -q
```

Expected:

```text
all selected tests pass
```

---

## Task 6: Compatibility and Full Verification

**Files:**
- Modify only if tests require it: `tests/runtime/test_context.py`, `tests/test_history_manager.py`

- [ ] **Step 1: Run context-related tests**

Run:

```bash
pytest tests/runtime/test_context_engine.py tests/runtime/test_context.py tests/test_context_builder.py tests/test_history_manager.py tests/runtime/test_runner.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 2: If `tests/runtime/test_context.py` still expects `ContextManager`, keep it passing**

Do not delete `runtime/context_provider.py` in v1.

If needed, update `runtime/context_provider.py` so it can optionally use `ContextEngine` internally while preserving its public methods:

```python
from runtime.context import ContextEngine


class ContextManager:
    def __init__(self, history_manager, prompt_builder):
        self.history_manager = history_manager
        self.prompt_builder = prompt_builder
        self.context_engine = ContextEngine(prompt_builder)

    def build(self):
        return self.context_engine.build_model_view(
            history_manager=self.history_manager,
        ).messages

    def maybe_compact(self, pending_input: str, **kwargs):
        if not self.history_manager.should_compress(pending_input):
            return None
        return self.history_manager.compact(**kwargs)
```

This is allowed only as v1 compatibility. Do not introduce new feature logic into `ContextManager`.

- [ ] **Step 3: Search for forbidden main-loop dependency**

Run:

```bash
rg -n "history_manager\\.to_messages\\(|_build_messages\\(" runtime/loop.py
```

Expected:

```text
no output
```

- [ ] **Step 4: Run full test suite**

Run:

```bash
pytest -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 5: Commit only context v1 files**

Run:

```bash
git status --short
git add runtime/context runtime/host.py runtime/loop.py runtime/context_provider.py tests/runtime/test_context_engine.py tests/runtime/test_runner.py tests/runtime/test_context.py tests/test_context_builder.py tests/test_history_manager.py
git diff --cached --name-only
git commit -m "feat(context): add model view context engine"
```

Before committing, verify `git diff --cached --name-only` does not include unrelated docs, tracing changes, or tool orchestrator files.

---

## Acceptance Criteria

Implementation is complete when:
- `runtime/context/` exists and owns model-view construction.
- `RuntimeRunner` builds each LLM request through `host.context_engine.build_model_view(...)`.
- `RuntimeRunner` no longer calls `host.history_manager.to_messages()` or `host._build_messages(...)` for the normal model request path.
- A `model_view_build` trace event is emitted every model step.
- Full runtime history is not mutated by building a model view.
- Existing compression may still be destructive in v1, but all post-compression model context is rebuilt through `ContextEngine`.
- Existing tests plus new context tests pass.

---

## Implementation Prompt

Use this prompt for the implementation agent:

```text
你在 /Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent 工作。

目标：按 docs/plans/2026-06-05-context-engineering-v1-implementation-plan.md 实现 Context Engineering v1。

关键取舍：
1. 这是学习型 MVP，不要做企业级大而全。
2. v1 只建立新的上下文骨架和模型视图主链路，不做 auto compact、context collapse、summary checkpoint、restore、microcompact。
3. 新逻辑必须进入 runtime/context/ 包，不要继续把上下文逻辑堆进 runtime 根目录。
4. HistoryManager 在 v1 仍然保留完整历史和 legacy to_messages()/compact() 兼容接口，但 RuntimeRunner 的正常模型请求路径不能再依赖 history_manager.to_messages()。
5. RuntimeRunner 每次请求模型前必须通过 host.context_engine.build_model_view(...) 得到 ModelView，并把 ModelView.messages 传给 LLM。
6. ModelView 是“模型实际看到的上下文”的边界对象，必须记录 message_count、system/history/source 计数、projection_mode、estimated_chars、warnings。
7. ProjectionBuilder v1 只做 full_history read-time projection，必须不修改 HistoryManager 内部消息数组。
8. MessageNormalizer 负责从 runtime.history.Message 转换成 OpenAI-compatible dict，行为要保持现有 HistoryManager.to_messages() 的核心兼容：user、assistant tool_calls、tool result、summary 都要正确。
9. 添加 model_view_build trace 事件。
10. 不要改 ToolOrchestrator、工具预算、session 格式、skills、MCP 等无关模块。

执行方式：
1. 先读实现计划。
2. 按 Task 1 到 Task 6 顺序做，每个任务先写或更新测试，再实现。
3. 使用 apply_patch 修改文件。
4. 每完成一个任务运行计划中的对应 pytest 命令。
5. 最后运行：
   pytest tests/runtime/test_context_engine.py tests/runtime/test_context.py tests/test_context_builder.py tests/test_history_manager.py tests/runtime/test_runner.py -q
   pytest -q
6. 检查：
   rg -n "history_manager\\.to_messages\\(|_build_messages\\(" runtime/loop.py
   期望无输出。
7. 提交前运行 git status --short 和 git diff --cached --name-only，确保只提交 Context Engineering v1 相关文件。

完成后汇报：
1. 修改了哪些上下文边界。
2. RuntimeRunner 的模型请求路径现在是什么。
3. 哪些 legacy 接口仍保留给 v2 清理。
4. 测试结果。
```

