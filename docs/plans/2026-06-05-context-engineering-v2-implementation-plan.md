# Context Engineering v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move context budgeting and compaction out of `HistoryManager`, delete the legacy context facade, and make compaction a non-destructive read-time projection through `ContextEngine`.

**Architecture:** `HistoryManager` becomes an append-only runtime log. `runtime/context/` owns round segmentation, token estimation, compaction decisions, compact checkpoints, model-view projection, and message normalization. Compaction no longer rewrites history; it stores a `CompactCheckpoint` and `ProjectionBuilder` projects the active model view from full history plus the checkpoint.

**Tech Stack:** Python dataclasses, existing `Config`, existing `runtime.summary.create_summary_generator`, pytest.

---

## Scope

v2 is the cleanup and ownership-transfer version. After v2, there should not be a legacy `ContextManager` wrapper and the main context responsibilities should not live in `HistoryManager`.

v2 includes:
- Delete `runtime/context_provider.py`.
- Remove `HistoryManager.to_messages()`, `HistoryManager.should_compress()`, `HistoryManager.compact()`, `HistoryManager.estimate_context_tokens()`, and `HistoryManager.estimate_total_tokens()`.
- Add `RoundSegmenter` under `runtime/context/`.
- Add `ContextBudgetPolicy` under `runtime/context/`.
- Add `CompactStore` and `CompactCheckpoint` under `runtime/context/`.
- Add `ContextCompactor` under `runtime/context/`.
- Make `ProjectionBuilder` support compact checkpoint projection.
- Make `ContextEngine` own usage accounting, compact decisions, compaction execution, and model-view construction.
- Update `RuntimeRunner` so compression checks go through `host.context_engine`.

v2 does not include:
- Multi-checkpoint collapse chains.
- Tool-result microcompact beyond existing ToolOrchestrator v3 budgeting.
- Post-compact file restore.
- Prompt cache pinning.
- Streaming context updates.

The important v2 boundary:

```text
HistoryManager = durable runtime log
ContextEngine = model context runtime
ProjectionBuilder = read-time view builder
CompactStore = compressed view state
```

---

## Target Structure

Create:
- `runtime/context/rounds.py`: identifies user-started conversation rounds from `Message` list.
- `runtime/context/budget.py`: estimates context usage and decides whether compaction is needed.
- `runtime/context/compact_store.py`: stores active compact checkpoint without mutating history.
- `runtime/context/compact.py`: creates compact checkpoints from full history.
- `tests/runtime/test_context_budget.py`: budget and trigger tests.
- `tests/runtime/test_context_compaction.py`: non-destructive compaction and projection tests.

Modify:
- `runtime/context/model_view.py`: add optional compact checkpoint metadata.
- `runtime/context/projection.py`: apply compact checkpoints during projection.
- `runtime/context/engine.py`: own usage accounting and compaction lifecycle.
- `runtime/context/__init__.py`: export new context components.
- `runtime/history.py`: remove context serialization and compaction responsibilities.
- `runtime/host.py`: pass `Config` and `summary_generator` into `ContextEngine`; initialize plain `HistoryManager`.
- `runtime/loop.py`: replace `history_manager.should_compress()/compact()/update_last_usage()` with `context_engine` calls.
- `tests/runtime/test_runner.py`: update fake host/history for new context flow.
- `tests/runtime/test_context.py`: remove `ContextManager` import and assert direct `ContextEngine` usage.
- `tests/test_history_manager.py`: keep append/history tests only; move compact tests to context tests.
- `tests/test_context_engineering.py`: update old context compression tests to the new `ContextEngine`/`ContextCompactor` APIs.
- `tests/experimental/test_team_runtime_injection.py`: replace `hm.to_messages()` with `ContextEngine`.

Delete:
- `runtime/context_provider.py`.

---

## Design Contract

### 1. HistoryManager Contract

After v2, `HistoryManager` must only own:
- append user/assistant/tool/summary messages
- get messages
- serialize/load messages for session persistence
- count messages and rounds
- clear history

`HistoryManager` must not own:
- model API serialization
- compression threshold decisions
- summary generation
- compaction mutation
- model-view construction

### 2. ContextEngine Contract

`ContextEngine` must expose:

```python
class ContextEngine:
    def record_usage(self, total_tokens: int | None) -> None: ...

    def should_compact(self, *, history_manager: Any, pending_input: str) -> bool: ...

    def compact_if_needed(
        self,
        *,
        history_manager: Any,
        pending_input: str,
        step: int = 0,
        trace_logger: Any = None,
    ) -> dict[str, Any]: ...

    def build_model_view(
        self,
        *,
        history_manager: Any,
        pending_input: str = "",
        step: int = 0,
        trace_logger: Any = None,
    ) -> ModelView: ...
```

### 3. Non-Destructive Compact Contract

Compaction must not modify `HistoryManager._messages`.

Instead:

```text
full history:
  user1 assistant1 tool1 ... user9 assistant9

compact checkpoint:
  summary = "..."
  retain_start_idx = index of recent retained region

model projection:
  system messages
  summary message
  full history from retain_start_idx onward
```

### 4. Failure Policy

If summary generation fails or there are not enough rounds:
- do not mutate history
- do not create a checkpoint
- return `{"compacted": False, "reason": "..."}`
- emit trace event

This is intentionally safer than the old behavior where compaction could drop old messages without a summary.

---

## Task 1: Add RoundSegmenter

**Files:**
- Create: `runtime/context/rounds.py`
- Modify: `runtime/context/__init__.py`
- Test: `tests/runtime/test_context_compaction.py`

- [ ] **Step 1: Write failing round segmentation tests**

Create `tests/runtime/test_context_compaction.py`:

```python
from runtime.context import RoundSegmenter
from runtime.history import Message


def test_round_segmenter_identifies_user_started_rounds():
    messages = [
        Message("old summary", "summary"),
        Message("q1", "user"),
        Message("a1", "assistant"),
        Message("q2", "user"),
        Message("a2", "assistant"),
    ]

    rounds = RoundSegmenter().identify(messages)

    assert [(r.start_idx, r.end_idx) for r in rounds] == [(1, 2), (3, 4)]


def test_round_segmenter_handles_consecutive_users():
    messages = [
        Message("q1", "user"),
        Message("q2", "user"),
        Message("a2", "assistant"),
    ]

    rounds = RoundSegmenter().identify(messages)

    assert [(r.start_idx, r.end_idx) for r in rounds] == [(0, 0), (1, 2)]
```

- [ ] **Step 2: Run the new tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/runtime/test_context_compaction.py::test_round_segmenter_identifies_user_started_rounds tests/runtime/test_context_compaction.py::test_round_segmenter_handles_consecutive_users -q
```

Expected:

```text
ImportError: cannot import name 'RoundSegmenter'
```

- [ ] **Step 3: Implement RoundSegmenter**

Create `runtime/context/rounds.py`:

```python
"""Conversation round segmentation for context planning."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.history import Message


@dataclass(frozen=True)
class HistoryRound:
    start_idx: int
    end_idx: int


class RoundSegmenter:
    """Identifies rounds that start at user messages."""

    def identify(self, messages: list[Message]) -> list[HistoryRound]:
        rounds: list[HistoryRound] = []
        current_start: int | None = None
        for idx, msg in enumerate(messages or []):
            if msg.role == "user":
                if current_start is not None:
                    rounds.append(HistoryRound(current_start, idx - 1))
                current_start = idx
        if current_start is not None:
            rounds.append(HistoryRound(current_start, len(messages) - 1))
        return rounds
```

Update `runtime/context/__init__.py`:

```python
from runtime.context.rounds import HistoryRound, RoundSegmenter
```

And add them to `__all__`.

- [ ] **Step 4: Run round tests**

Run:

```bash
.venv/bin/python -m pytest tests/runtime/test_context_compaction.py::test_round_segmenter_identifies_user_started_rounds tests/runtime/test_context_compaction.py::test_round_segmenter_handles_consecutive_users -q
```

Expected:

```text
2 passed
```

---

## Task 2: Add ContextBudgetPolicy

**Files:**
- Create: `runtime/context/budget.py`
- Modify: `runtime/context/__init__.py`
- Test: `tests/runtime/test_context_budget.py`

- [ ] **Step 1: Write failing budget tests**

Create `tests/runtime/test_context_budget.py`:

```python
from core.config import Config
from runtime.context import ContextBudgetPolicy
from runtime.history import HistoryManager


def test_context_budget_policy_requires_minimum_messages():
    policy = ContextBudgetPolicy(Config(context_window=1000, compression_threshold=0.1))
    history = HistoryManager()
    history.append_user("q")
    history.append_assistant("a")

    decision = policy.should_compact(
        messages=history.get_messages(),
        pending_input="input",
        last_usage_tokens=900,
    )

    assert decision.should_compact is False
    assert decision.reason == "messages_not_enough"


def test_context_budget_policy_triggers_from_usage_estimate():
    policy = ContextBudgetPolicy(Config(context_window=1000, compression_threshold=0.8))
    history = HistoryManager()
    history.append_user("q1")
    history.append_assistant("a1")
    history.append_user("q2")

    decision = policy.should_compact(
        messages=history.get_messages(),
        pending_input="more",
        last_usage_tokens=810,
    )

    assert decision.should_compact is True
    assert decision.reason == "threshold_exceeded"
    assert decision.threshold == 800


def test_context_budget_policy_estimates_message_content_and_tool_calls():
    policy = ContextBudgetPolicy(Config(context_window=1000, compression_threshold=0.8))
    history = HistoryManager()
    history.append_user("q" * 900)
    history.append_assistant(
        "",
        metadata={
            "action_type": "tool_call",
            "tool_calls": [{"id": "call_1", "name": "Read", "arguments": {"path": "a.py"}}],
        },
    )
    history.append_user("next")

    decision = policy.should_compact(
        messages=history.get_messages(),
        pending_input="more",
        last_usage_tokens=0,
    )

    assert decision.estimated_tokens > 0
```

- [ ] **Step 2: Run budget tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/runtime/test_context_budget.py -q
```

Expected:

```text
ImportError: cannot import name 'ContextBudgetPolicy'
```

- [ ] **Step 3: Implement ContextBudgetPolicy**

Create `runtime/context/budget.py`:

```python
"""Context budget estimation and compaction decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass

from core.config import Config
from runtime.history import Message


@dataclass(frozen=True)
class CompactDecision:
    should_compact: bool
    reason: str
    estimated_tokens: int
    threshold: int
    message_count: int


class ContextBudgetPolicy:
    """Decides when the active model context needs compaction."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config.from_env()

    def estimate_tokens(self, messages: list[Message], pending_input: str = "") -> int:
        total_chars = len(pending_input or "")
        for msg in messages or []:
            total_chars += len(str(msg.content or ""))
            metadata = msg.metadata or {}
            if msg.role == "assistant" and metadata.get("tool_calls"):
                try:
                    total_chars += len(json.dumps(metadata["tool_calls"], ensure_ascii=False))
                except Exception:
                    total_chars += len(str(metadata["tool_calls"]))
            if msg.role == "tool" and metadata.get("tool_name"):
                total_chars += len(str(metadata["tool_name"]))
        return total_chars // 3

    def should_compact(
        self,
        *,
        messages: list[Message],
        pending_input: str = "",
        last_usage_tokens: int = 0,
    ) -> CompactDecision:
        message_count = len(messages or [])
        threshold = int(self.config.context_window * self.config.compression_threshold)
        estimated_from_messages = self.estimate_tokens(messages, pending_input)
        estimated_from_usage = int(last_usage_tokens or 0) + len(pending_input or "") // 3
        estimated = max(estimated_from_messages, estimated_from_usage)

        if message_count < 3:
            return CompactDecision(False, "messages_not_enough", estimated, threshold, message_count)
        if estimated < threshold:
            return CompactDecision(False, "below_threshold", estimated, threshold, message_count)
        return CompactDecision(True, "threshold_exceeded", estimated, threshold, message_count)
```

Update `runtime/context/__init__.py`:

```python
from runtime.context.budget import CompactDecision, ContextBudgetPolicy
```

And add them to `__all__`.

- [ ] **Step 4: Run budget tests**

Run:

```bash
.venv/bin/python -m pytest tests/runtime/test_context_budget.py -q
```

Expected:

```text
3 passed
```

---

## Task 3: Add CompactStore and ContextCompactor

**Files:**
- Create: `runtime/context/compact_store.py`
- Create: `runtime/context/compact.py`
- Modify: `runtime/context/__init__.py`
- Test: `tests/runtime/test_context_compaction.py`

- [ ] **Step 1: Add failing compactor tests**

Append to `tests/runtime/test_context_compaction.py`:

```python
from core.config import Config
from runtime.context import CompactStore, ContextCompactor
from runtime.history import HistoryManager


def _append_round(history: HistoryManager, idx: int):
    history.append_user(f"q{idx}")
    history.append_assistant(f"a{idx}")


def test_context_compactor_creates_checkpoint_without_mutating_history():
    history = HistoryManager(config=Config(min_retain_rounds=2))
    for idx in range(5):
        _append_round(history, idx)
    before = history.get_messages()

    store = CompactStore()
    compactor = ContextCompactor(
        config=Config(min_retain_rounds=2),
        compact_store=store,
        summary_generator=lambda messages: f"summary({len(messages)})",
    )

    info = compactor.compact(history.get_messages())

    assert info["compacted"] is True
    assert history.get_messages() == before
    checkpoint = store.active_checkpoint
    assert checkpoint is not None
    assert checkpoint.summary == "summary(6)"
    assert checkpoint.retain_start_idx == 6


def test_context_compactor_skips_when_rounds_not_enough():
    history = HistoryManager(config=Config(min_retain_rounds=3))
    for idx in range(2):
        _append_round(history, idx)

    store = CompactStore()
    compactor = ContextCompactor(
        config=Config(min_retain_rounds=3),
        compact_store=store,
        summary_generator=lambda messages: "summary",
    )

    info = compactor.compact(history.get_messages())

    assert info == {
        "compacted": False,
        "reason": "rounds_not_enough",
        "rounds_count": 2,
        "min_retain_rounds": 3,
    }
    assert store.active_checkpoint is None


def test_context_compactor_skips_when_summary_unavailable():
    history = HistoryManager(config=Config(min_retain_rounds=1))
    for idx in range(3):
        _append_round(history, idx)

    store = CompactStore()
    compactor = ContextCompactor(
        config=Config(min_retain_rounds=1),
        compact_store=store,
        summary_generator=lambda messages: None,
    )

    info = compactor.compact(history.get_messages())

    assert info["compacted"] is False
    assert info["reason"] == "summary_unavailable"
    assert store.active_checkpoint is None
```

- [ ] **Step 2: Run compactor tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/runtime/test_context_compaction.py -q
```

Expected:

```text
ImportError: cannot import name 'CompactStore'
```

- [ ] **Step 3: Implement CompactStore**

Create `runtime/context/compact_store.py`:

```python
"""Compact checkpoint storage for read-time context projection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import uuid


@dataclass(frozen=True)
class CompactCheckpoint:
    id: str
    summary: str
    source_message_count: int
    retain_start_idx: int
    messages_compacted: int
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


class CompactStore:
    """Stores the active compact checkpoint without editing history."""

    def __init__(self):
        self._active_checkpoint: CompactCheckpoint | None = None

    @property
    def active_checkpoint(self) -> CompactCheckpoint | None:
        return self._active_checkpoint

    def set_active(self, checkpoint: CompactCheckpoint) -> None:
        self._active_checkpoint = checkpoint

    def clear(self) -> None:
        self._active_checkpoint = None

    def create_checkpoint(
        self,
        *,
        summary: str,
        source_message_count: int,
        retain_start_idx: int,
        messages_compacted: int,
        metadata: dict[str, Any] | None = None,
    ) -> CompactCheckpoint:
        checkpoint = CompactCheckpoint(
            id=f"compact_{uuid.uuid4().hex}",
            summary=summary,
            source_message_count=source_message_count,
            retain_start_idx=retain_start_idx,
            messages_compacted=messages_compacted,
            created_at=datetime.now().isoformat(),
            metadata=metadata or {},
        )
        self.set_active(checkpoint)
        return checkpoint
```

- [ ] **Step 4: Implement ContextCompactor**

Create `runtime/context/compact.py`:

```python
"""Non-destructive context compaction."""

from __future__ import annotations

from typing import Any, Callable

from core.config import Config
from runtime.context.compact_store import CompactStore
from runtime.context.rounds import RoundSegmenter
from runtime.history import Message


class ContextCompactor:
    """Creates compact checkpoints while preserving full history."""

    def __init__(
        self,
        *,
        config: Config | None = None,
        compact_store: CompactStore | None = None,
        summary_generator: Callable[[list[Message]], str | None] | None = None,
        round_segmenter: RoundSegmenter | None = None,
    ):
        self.config = config or Config.from_env()
        self.compact_store = compact_store or CompactStore()
        self.summary_generator = summary_generator
        self.round_segmenter = round_segmenter or RoundSegmenter()

    def compact(self, messages: list[Message]) -> dict[str, Any]:
        source_messages = list(messages or [])
        rounds = self.round_segmenter.identify(source_messages)
        min_rounds = self.config.min_retain_rounds
        if len(rounds) <= min_rounds:
            return {
                "compacted": False,
                "reason": "rounds_not_enough",
                "rounds_count": len(rounds),
                "min_retain_rounds": min_rounds,
            }

        retain_start_round = len(rounds) - min_rounds
        retain_start_idx = rounds[retain_start_round].start_idx
        messages_to_compact = source_messages[:retain_start_idx]
        if not messages_to_compact:
            return {"compacted": False, "reason": "no_messages_to_compact"}

        if not self.summary_generator:
            return {"compacted": False, "reason": "summary_unavailable"}

        try:
            summary = self.summary_generator(messages_to_compact)
        except Exception:
            summary = None

        if summary is None:
            return {"compacted": False, "reason": "summary_unavailable"}

        checkpoint = self.compact_store.create_checkpoint(
            summary=summary,
            source_message_count=len(source_messages),
            retain_start_idx=retain_start_idx,
            messages_compacted=len(messages_to_compact),
            metadata={
                "rounds_count": len(rounds),
                "min_retain_rounds": min_rounds,
                "retain_start_round": retain_start_round,
            },
        )
        return {
            "compacted": True,
            "checkpoint_id": checkpoint.id,
            "messages_before": len(source_messages),
            "messages_compacted": len(messages_to_compact),
            "retain_start_idx": retain_start_idx,
            "summary_generated": True,
            "summary_len": len(summary),
        }
```

Update `runtime/context/__init__.py`:

```python
from runtime.context.compact import ContextCompactor
from runtime.context.compact_store import CompactCheckpoint, CompactStore
```

And add them to `__all__`.

- [ ] **Step 5: Run compactor tests**

Run:

```bash
.venv/bin/python -m pytest tests/runtime/test_context_compaction.py -q
```

Expected:

```text
5 passed
```

---

## Task 4: Make ProjectionBuilder Use Compact Checkpoints

**Files:**
- Modify: `runtime/context/model_view.py`
- Modify: `runtime/context/projection.py`
- Test: `tests/runtime/test_context_compaction.py`
- Test: `tests/runtime/test_context_engine.py`

- [ ] **Step 1: Add failing projection tests**

Append to `tests/runtime/test_context_compaction.py`:

```python
from runtime.context import ProjectionBuilder


def test_projection_uses_active_compact_checkpoint_without_mutating_source():
    history = HistoryManager()
    for idx in range(4):
        _append_round(history, idx)
    source = history.get_messages()

    store = CompactStore()
    checkpoint = store.create_checkpoint(
        summary="summary text",
        source_message_count=len(source),
        retain_start_idx=4,
        messages_compacted=4,
    )

    projected = ProjectionBuilder(compact_store=store).project(source)

    assert history.get_messages() == source
    assert projected.projection_mode == "compact_checkpoint"
    assert projected.compact_checkpoint_id == checkpoint.id
    assert projected.messages[0].role == "summary"
    assert projected.messages[0].content == "summary text"
    assert projected.messages[1:] == source[4:]
```

- [ ] **Step 2: Run projection checkpoint test and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/runtime/test_context_compaction.py::test_projection_uses_active_compact_checkpoint_without_mutating_source -q
```

Expected:

```text
TypeError: ProjectionBuilder() takes no arguments
```

- [ ] **Step 3: Extend projection types**

Update `runtime/context/projection.py`:

```python
"""Read-time history projection."""

from __future__ import annotations

from dataclasses import dataclass, field

from runtime.context.compact_store import CompactStore
from runtime.history import Message


@dataclass(frozen=True)
class ProjectionResult:
    messages: list[Message]
    source_message_count: int
    projection_mode: str = "full_history"
    warnings: tuple[str, ...] = field(default_factory=tuple)
    compact_checkpoint_id: str | None = None


class ProjectionBuilder:
    """Builds the active history view without mutating the runtime log."""

    def __init__(self, compact_store: CompactStore | None = None):
        self.compact_store = compact_store

    def project(self, source_messages: list[Message]) -> ProjectionResult:
        source = list(source_messages or [])
        checkpoint = self.compact_store.active_checkpoint if self.compact_store else None
        if not checkpoint:
            return ProjectionResult(
                messages=source,
                source_message_count=len(source),
                projection_mode="full_history",
                warnings=(),
            )

        retain_start_idx = min(max(checkpoint.retain_start_idx, 0), len(source))
        summary = Message(
            content=checkpoint.summary,
            role="summary",
            metadata={
                "checkpoint_id": checkpoint.id,
                "source_message_count": checkpoint.source_message_count,
                "messages_compacted": checkpoint.messages_compacted,
            },
        )
        return ProjectionResult(
            messages=[summary] + source[retain_start_idx:],
            source_message_count=len(source),
            projection_mode="compact_checkpoint",
            warnings=(),
            compact_checkpoint_id=checkpoint.id,
        )
```

Update `runtime/context/model_view.py`:

```python
compact_checkpoint_id: str | None = None
```

Add that field after `projection_mode`.

Update `runtime/context/engine.py` to pass `compact_checkpoint_id=projection.compact_checkpoint_id` into `ModelView` and include it in `model_view_build` trace payload.

- [ ] **Step 4: Run projection and context engine tests**

Run:

```bash
.venv/bin/python -m pytest tests/runtime/test_context_compaction.py tests/runtime/test_context_engine.py -q
```

Expected:

```text
all selected tests pass
```

---

## Task 5: Move Usage and Compaction Lifecycle Into ContextEngine

**Files:**
- Modify: `runtime/context/engine.py`
- Test: `tests/runtime/test_context_engine.py`

- [ ] **Step 1: Add failing ContextEngine lifecycle tests**

Append to `tests/runtime/test_context_engine.py`:

```python
from core.config import Config


def test_context_engine_records_usage_and_decides_compaction():
    history = HistoryManager()
    history.append_user("q1")
    history.append_assistant("a1")
    history.append_user("q2")
    engine = ContextEngine(
        context_builder=_FakeContextBuilder(),
        config=Config(context_window=1000, compression_threshold=0.8),
    )

    engine.record_usage(810)

    assert engine.should_compact(history_manager=history, pending_input="more") is True
    assert engine.total_usage_tokens == 810


def test_context_engine_compact_if_needed_creates_checkpoint_and_preserves_history():
    history = HistoryManager()
    for idx in range(5):
        history.append_user(f"q{idx}")
        history.append_assistant(f"a{idx}")
    before = history.get_messages()
    trace = _FakeTraceLogger()
    engine = ContextEngine(
        context_builder=_FakeContextBuilder(),
        config=Config(context_window=1000, compression_threshold=0.1, min_retain_rounds=2),
        summary_generator=lambda messages: f"summary({len(messages)})",
    )
    engine.record_usage(900)

    info = engine.compact_if_needed(
        history_manager=history,
        pending_input="more",
        step=7,
        trace_logger=trace,
    )
    view = engine.build_model_view(history_manager=history)

    assert info["compacted"] is True
    assert history.get_messages() == before
    assert view.projection_mode == "compact_checkpoint"
    assert view.messages[1]["role"] == "system"
    assert "Archived History Summary" in view.messages[1]["content"]
    assert any(event[0] == "context_compaction_completed" for event in trace.events)
```

- [ ] **Step 2: Run lifecycle tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/runtime/test_context_engine.py::test_context_engine_records_usage_and_decides_compaction tests/runtime/test_context_engine.py::test_context_engine_compact_if_needed_creates_checkpoint_and_preserves_history -q
```

Expected:

```text
TypeError: ContextEngine.__init__() got an unexpected keyword argument 'config'
```

- [ ] **Step 3: Extend ContextEngine**

Update `runtime/context/engine.py` constructor and methods:

```python
from core.config import Config
from runtime.context.budget import ContextBudgetPolicy
from runtime.context.compact import ContextCompactor
from runtime.context.compact_store import CompactStore


class ContextEngine:
    def __init__(
        self,
        context_builder: Any,
        *,
        config: Config | None = None,
        summary_generator: Any = None,
        compact_store: CompactStore | None = None,
        budget_policy: ContextBudgetPolicy | None = None,
        compactor: ContextCompactor | None = None,
        projection_builder: ProjectionBuilder | None = None,
        normalizer: MessageNormalizer | None = None,
    ):
        self.context_builder = context_builder
        self.config = config or Config.from_env()
        self.compact_store = compact_store or CompactStore()
        self.budget_policy = budget_policy or ContextBudgetPolicy(self.config)
        self.compactor = compactor or ContextCompactor(
            config=self.config,
            compact_store=self.compact_store,
            summary_generator=summary_generator,
        )
        self.projection_builder = projection_builder or ProjectionBuilder(self.compact_store)
        self.normalizer = normalizer or MessageNormalizer()
        self.last_usage_tokens = 0
        self.total_usage_tokens = 0

    def record_usage(self, total_tokens: int | None) -> None:
        if total_tokens is None:
            return
        self.last_usage_tokens = int(total_tokens)
        self.total_usage_tokens += int(total_tokens)

    def should_compact(self, *, history_manager: Any, pending_input: str) -> bool:
        decision = self.budget_policy.should_compact(
            messages=history_manager.get_messages(),
            pending_input=pending_input,
            last_usage_tokens=self.last_usage_tokens,
        )
        return decision.should_compact

    def compact_if_needed(
        self,
        *,
        history_manager: Any,
        pending_input: str,
        step: int = 0,
        trace_logger: Any = None,
    ) -> dict[str, Any]:
        decision = self.budget_policy.should_compact(
            messages=history_manager.get_messages(),
            pending_input=pending_input,
            last_usage_tokens=self.last_usage_tokens,
        )
        if trace_logger:
            trace_logger.log_event(
                "context_compaction_decision",
                {
                    "should_compact": decision.should_compact,
                    "reason": decision.reason,
                    "estimated_tokens": decision.estimated_tokens,
                    "threshold": decision.threshold,
                    "message_count": decision.message_count,
                },
                step=step,
            )
        if not decision.should_compact:
            return {
                "compacted": False,
                "reason": decision.reason,
                "estimated_tokens": decision.estimated_tokens,
                "threshold": decision.threshold,
            }
        info = self.compactor.compact(history_manager.get_messages())
        if trace_logger:
            event_name = "context_compaction_completed" if info.get("compacted") else "context_compaction_skipped"
            trace_logger.log_event(event_name, info, step=step)
        return info
```

Keep `build_model_view()` but update it to use the new constructor fields.

- [ ] **Step 4: Run context engine tests**

Run:

```bash
.venv/bin/python -m pytest tests/runtime/test_context_engine.py -q
```

Expected:

```text
all selected tests pass
```

---

## Task 6: Wire RuntimeRunner and Host to ContextEngine v2

**Files:**
- Modify: `runtime/host.py`
- Modify: `runtime/loop.py`
- Modify: `tests/runtime/test_runner.py`

- [ ] **Step 1: Update fake host in runner tests**

In `tests/runtime/test_runner.py`, update `_FakeHost.__init__` context engine construction:

```python
self.context_engine = ContextEngine(
    self.context_builder,
    config=self.config,
    summary_generator=lambda messages: f"summary({len(messages)})",
)
```

Remove `_FakeHistoryManager.update_last_usage()`, `estimate_context_tokens()`, `get_total_usage_tokens()`, and `compact()` if no remaining tests need them.

- [ ] **Step 2: Update compression runner test expectations**

Replace the old `_CompressingHistoryManager` behavior with context-engine usage accounting:

```python
class _CompressingHost(_FakeHost):
    def __init__(self):
        super().__init__()
        self.config = type(
            "Config",
            (),
            {
                "context_window": 1000,
                "compression_threshold": 0.1,
                "min_retain_rounds": 1,
            },
        )()
        from runtime.context import ContextEngine

        self.context_engine = ContextEngine(
            self.context_builder,
            config=self.config,
            summary_generator=lambda messages: f"summary({len(messages)})",
        )
        self.context_engine.record_usage(900)
        self.history_manager.append_user("old q")
        self.history_manager.append_assistant("old a")
        self.history_manager.append_user("older q")
        self.history_manager.append_assistant("older a")
```

Keep `test_runtime_runner_emits_context_compacted_transition()` asserting a `context_compacted` transition.

- [ ] **Step 3: Update host construction**

In `runtime/host.py`, change:

```python
self.history_manager = HistoryManager(
    config=self.config,
    summary_generator=summary_generator,
)
```

To:

```python
self.history_manager = HistoryManager(config=self.config)
```

And change:

```python
self.context_engine = ContextEngine(self.context_builder)
```

To:

```python
self.context_engine = ContextEngine(
    self.context_builder,
    config=self.config,
    summary_generator=summary_generator,
)
```

- [ ] **Step 4: Update RuntimeRunner usage accounting**

In `runtime/loop.py`, replace:

```python
host.history_manager.update_last_usage(usage["total_tokens"])
```

With:

```python
host.context_engine.record_usage(usage["total_tokens"])
```

- [ ] **Step 5: Update RuntimeRunner compaction branch**

Replace the old branch:

```python
if host.history_manager.should_compress(pending_input):
    ...
    compress_info = host.history_manager.compact(...)
```

With:

```python
compact_info = host.context_engine.compact_if_needed(
    history_manager=host.history_manager,
    pending_input=pending_input,
    step=step,
    trace_logger=trace_logger,
)
if compact_info.get("compacted"):
    state = self._transition(
        state,
        TransitionReason.CONTEXT_COMPACTED,
        trace_logger,
        step=step,
        compact_attempted=True,
        details={
            "checkpoint_id": compact_info.get("checkpoint_id"),
            "messages_compacted": compact_info.get("messages_compacted"),
            "retain_start_idx": compact_info.get("retain_start_idx"),
        },
    )
    final_context = host.context_engine.build_model_view(
        history_manager=host.history_manager,
        pending_input=pending_input,
        step=step,
        trace_logger=trace_logger,
    ).messages
    trace_logger.log_event(
        "history_compression_final_context",
        {"message_count": len(final_context), "messages": final_context},
        step=step,
    )
```

Do not keep calls to `history_manager.should_compress()` or `history_manager.compact()`.

- [ ] **Step 6: Run runner tests**

Run:

```bash
.venv/bin/python -m pytest tests/runtime/test_runner.py -q
```

Expected:

```text
all selected tests pass
```

---

## Task 7: Remove Legacy Context Provider and History Context Methods

**Files:**
- Delete: `runtime/context_provider.py`
- Modify: `runtime/history.py`
- Modify: `tests/runtime/test_context.py`
- Modify: `tests/test_history_manager.py`
- Modify: `tests/test_context_engineering.py`
- Modify: `tests/experimental/test_team_runtime_injection.py`

- [ ] **Step 1: Delete `runtime/context_provider.py`**

Use `apply_patch` delete file.

- [ ] **Step 2: Update `tests/runtime/test_context.py`**

Replace its `ContextManager` test with direct `ContextEngine` usage:

```python
from runtime.context import ContextEngine
from runtime.history import HistoryManager
from runtime.prompt_builder import ContextBuilder
from runtime.session import build_session_snapshot


def test_target_runtime_modules_expose_context_services():
    from runtime.context import ContextEngine
    from runtime.host import CodeAgent
    from runtime.input_preprocess import preprocess_input
    from runtime.observation_store import truncate_observation
    from runtime.summary import create_summary_generator

    assert CodeAgent.__name__ == "CodeAgent"
    assert ContextEngine.__name__ == "ContextEngine"
    assert callable(preprocess_input)
    assert callable(create_summary_generator)
    assert callable(truncate_observation)


class _DummyToolRegistry:
    def get_disabled_tools(self):
        return []


def test_context_engine_builds_messages_from_preprocessed_history(tmp_path):
    prompts_dir = tmp_path / "prompts" / "agents_prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "L1_system_prompt.py").write_text('system_prompt = "base system"', encoding="utf-8")

    from runtime.input_preprocess import preprocess_input

    history = HistoryManager()
    builder = ContextBuilder(tool_registry=_DummyToolRegistry(), project_root=str(tmp_path))
    engine = ContextEngine(builder)

    processed = preprocess_input("check @src/main.py")
    history.append_user(processed.processed_input)

    view = engine.build_model_view(history_manager=history)

    assert view.messages[0]["role"] == "system"
    assert view.messages[-1]["role"] == "user"
    assert "@src/main.py" in view.messages[-1]["content"]
```

Keep the session snapshot test, but replace:

```python
messages = builder.build_messages(history.to_messages())
```

With:

```python
messages = ContextEngine(builder).build_model_view(history_manager=history).messages
```

- [ ] **Step 3: Remove context methods from HistoryManager**

In `runtime/history.py`, remove:
- `summary_generator` argument from `__init__`
- `self._summary_generator`
- `_last_usage_tokens`
- `_total_usage_tokens`
- `update_last_usage`
- `get_total_usage_tokens`
- `estimate_total_tokens`
- `estimate_context_tokens`
- `should_compress`
- `compact`
- `_identify_rounds`
- `to_messages`

Keep `get_rounds_count()`, but implement it through `RoundSegmenter`:

```python
def get_rounds_count(self) -> int:
    from runtime.context.rounds import RoundSegmenter

    return len(RoundSegmenter().identify(self._messages))
```

Keep `clear()` only clearing `_messages`.

- [ ] **Step 4: Update history tests**

In `tests/test_history_manager.py`, remove tests that call:
- `should_compress`
- `compact`
- `to_messages`
- `update_last_usage`

Keep tests for append/load/serialize/count behavior.

Move serialization expectations to `tests/runtime/test_context_engine.py` using `MessageNormalizer` or `ContextEngine`.

- [ ] **Step 5: Update old context engineering tests**

In `tests/test_context_engineering.py`, replace old `HistoryManager.should_compress()/compact()/to_messages()` assertions with:
- `ContextBudgetPolicy.should_compact(...)`
- `ContextCompactor.compact(...)`
- `ContextEngine.build_model_view(...)`

Concrete replacements:
- `test_should_compress_below_threshold` uses `ContextBudgetPolicy(...).should_compact(...)`.
- `test_should_compress_above_threshold` uses `ContextBudgetPolicy(...).should_compact(...)`.
- `test_compact_preserves_min_rounds` uses `ContextCompactor` and asserts `history.get_rounds_count()` is unchanged.
- `test_serialize_for_prompt` uses `MessageNormalizer().normalize(history.get_messages())`.
- `test_compact_inserts_summary_and_retains_recent_rounds` uses `ContextEngine.compact_if_needed(...)` and asserts `history.get_rounds_count()` is unchanged while `view.projection_mode == "compact_checkpoint"`.

- [ ] **Step 6: Update team runtime injection test**

In `tests/experimental/test_team_runtime_injection.py`, replace:

```python
_ = builder.build_messages(hm.to_messages())
```

With:

```python
from runtime.context import ContextEngine

_ = ContextEngine(builder).build_model_view(history_manager=hm).messages
```

- [ ] **Step 7: Search for removed APIs**

Run:

```bash
rg -n "context_provider|ContextManager|history_manager\\.to_messages\\(|history_manager\\.should_compress\\(|history_manager\\.compact\\(|history_manager\\.update_last_usage\\(|estimate_context_tokens\\(|get_total_usage_tokens\\(" runtime tests -S
```

Expected:

```text
no output
```

`ContextCompactor.compact(...)` and `context_engine.compact_if_needed(...)` are allowed; `history_manager.compact(...)` is not.

- [ ] **Step 8: Run context and history tests**

Run:

```bash
.venv/bin/python -m pytest tests/runtime/test_context_engine.py tests/runtime/test_context_compaction.py tests/runtime/test_context_budget.py tests/runtime/test_context.py tests/test_history_manager.py tests/test_context_engineering.py tests/experimental/test_team_runtime_injection.py -q
```

Expected:

```text
all selected tests pass
```

---

## Task 8: Full Verification and Commit

**Files:**
- All changed files from Tasks 1-7.

- [ ] **Step 1: Run API-removal search**

Run:

```bash
rg -n "context_provider|ContextManager|history_manager\\.to_messages\\(|history_manager\\.should_compress\\(|history_manager\\.compact\\(|history_manager\\.update_last_usage\\(" runtime tests -S
```

Expected:

```text
no output
```

- [ ] **Step 2: Run full tests**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 3: Inspect git diff**

Run:

```bash
git diff --stat
git diff -- runtime/history.py runtime/context runtime/loop.py runtime/host.py | sed -n '1,260p'
```

Expected:
- `HistoryManager` no longer contains context compaction or model-message serialization logic.
- `runtime/context/` contains the new context runtime components.
- `RuntimeRunner` uses `ContextEngine` for usage and compaction.

- [ ] **Step 4: Commit only v2 files**

Run:

```bash
git status --short
git add runtime/context runtime/history.py runtime/host.py runtime/loop.py tests/runtime/test_context_engine.py tests/runtime/test_context_compaction.py tests/runtime/test_context_budget.py tests/runtime/test_context.py tests/runtime/test_runner.py tests/test_history_manager.py tests/test_context_engineering.py tests/experimental/test_team_runtime_injection.py
git add -u runtime/context_provider.py
git diff --cached --name-only
git commit -m "refactor(context): move compaction into context engine"
```

Before committing, verify `git diff --cached --name-only` does not include unrelated docs or tool files.

---

## Acceptance Criteria

v2 is complete when:
- `runtime/context_provider.py` is deleted.
- No runtime code imports `ContextManager`.
- `HistoryManager` no longer has `to_messages`, `should_compress`, `compact`, `estimate_context_tokens`, `estimate_total_tokens`, `update_last_usage`, or `get_total_usage_tokens`.
- `RuntimeRunner` records usage through `host.context_engine.record_usage(...)`.
- `RuntimeRunner` requests compaction through `host.context_engine.compact_if_needed(...)`.
- Compaction creates a `CompactCheckpoint` and does not mutate `HistoryManager.get_messages()`.
- `ProjectionBuilder` produces `projection_mode="compact_checkpoint"` when a checkpoint is active.
- `ModelView` exposes compact checkpoint metadata.
- Full tests pass.

---

## Implementation Prompt

Use this prompt for the implementation agent:

```text
你在 /Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent 工作。

目标：按 docs/plans/2026-06-05-context-engineering-v2-implementation-plan.md 实现 Context Engineering v2。

v2 的核心要求：
1. v2 结束后不要再保留 runtime/context_provider.py 或 ContextManager 薄 wrapper。
2. HistoryManager 只能是完整历史日志，不再负责模型消息序列化、压缩判断、压缩执行、token 估算。
3. 上下文管理职责必须收口到 runtime/context/。
4. compact 必须是非破坏性的：不得修改 HistoryManager._messages，不得删除旧消息。
5. compact 结果保存为 CompactCheckpoint，由 ProjectionBuilder 在读时投影为 summary + recent history。
6. RuntimeRunner 必须通过 host.context_engine.record_usage(...) 记录 usage，通过 host.context_engine.compact_if_needed(...) 执行压缩检查。
7. 如果 summary 生成失败或轮次不足，必须跳过 compact，不允许丢历史。
8. 删除 legacy API 后必须更新测试，不要留下 wrapper 或兼容空壳。

执行方式：
1. 先完整阅读 v2 实施计划。
2. 按 Task 1 到 Task 8 顺序执行。
3. 每个任务先写或更新测试，再实现。
4. 使用 apply_patch 修改文件。
5. 每完成一个任务运行计划中的对应测试命令。
6. 最后运行：
   rg -n "context_provider|ContextManager|history_manager\\.to_messages\\(|history_manager\\.should_compress\\(|history_manager\\.compact\\(|history_manager\\.update_last_usage\\(" runtime tests -S
   .venv/bin/python -m pytest -q
7. 提交前检查 git diff --cached --name-only，只提交 Context Engineering v2 相关文件。

完成后汇报：
1. HistoryManager 还剩哪些职责。
2. ContextEngine 现在负责哪些上下文运行时职责。
3. compact 为什么是非破坏性的。
4. 哪些 legacy API 已删除。
5. 测试结果。
```
