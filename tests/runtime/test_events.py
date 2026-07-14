from __future__ import annotations

from dataclasses import dataclass

import pytest


def test_noop_event_sink_accepts_runtime_event():
    from runtime.events import NoopRuntimeEventSink, RuntimeEvent

    sink = NoopRuntimeEventSink()

    assert sink.emit(RuntimeEvent(run_id="run-1", step=2, type="terminal", payload={})) is None


def test_composite_event_sink_fans_out_in_order():
    from runtime.events import CompositeRuntimeEventSink, RuntimeEvent

    received: list[tuple[str, str]] = []

    @dataclass
    class Sink:
        name: str

        def emit(self, event: RuntimeEvent) -> None:
            received.append((self.name, event.type))

    sink = CompositeRuntimeEventSink((Sink("trace"), Sink("transcript")))

    sink.emit(RuntimeEvent(run_id="run-1", step=3, type="state_transition", payload={}))

    assert received == [("trace", "state_transition"), ("transcript", "state_transition")]


def test_composite_event_sink_isolates_sink_failure_and_reports_it():
    from runtime.events import CompositeRuntimeEventSink, RuntimeEvent

    received: list[str] = []
    failures: list[tuple[str, str]] = []

    class BrokenSink:
        def emit(self, event: RuntimeEvent) -> None:
            raise RuntimeError("disk unavailable")

    class RecordingSink:
        def emit(self, event: RuntimeEvent) -> None:
            received.append(event.type)

    sink = CompositeRuntimeEventSink(
        (BrokenSink(), RecordingSink()),
        on_sink_failure=lambda event, sink, error: failures.append((event.type, str(error))),
    )

    sink.emit(RuntimeEvent(run_id="run-1", step=4, type="terminal", payload={}))

    assert received == ["terminal"]
    assert failures == [("terminal", "disk unavailable")]


def test_transcript_and_trace_sinks_project_one_message_fact_consistently():
    from runtime.events import (
        CompositeRuntimeEventSink,
        RuntimeEvent,
        TraceRuntimeEventSink,
        TranscriptRuntimeEventSink,
    )

    class Trace:
        def __init__(self) -> None:
            self.events: list[tuple[str, dict, int]] = []

        def log_event(self, name: str, payload: dict, step: int = 0) -> None:
            self.events.append((name, payload, step))

    class Transcript:
        def __init__(self) -> None:
            self.messages: list[dict] = []

        def record_message(self, **payload) -> None:
            self.messages.append(payload)

    trace = Trace()
    transcript = Transcript()
    sink = CompositeRuntimeEventSink(
        (TraceRuntimeEventSink(trace), TranscriptRuntimeEventSink(transcript))
    )

    sink.emit(
        RuntimeEvent(
            run_id="run-7",
            step=2,
            type="message",
            payload={"role": "assistant", "content": "done", "metadata": {"action_type": "final"}},
        )
    )

    assert trace.events == [
        (
            "message_written",
            {"role": "assistant", "content": "done", "metadata": {"action_type": "final"}},
            2,
        )
    ]
    assert transcript.messages == [
        {
            "run_id": "run-7",
            "step": 2,
            "role": "assistant",
            "content": "done",
            "metadata": {"action_type": "final"},
        }
    ]


def test_transcript_sink_rejects_invalid_transcript_fact_without_writing():
    from runtime.events import RuntimeEvent, TranscriptRuntimeEventSink

    class Transcript:
        def record_message(self, **payload) -> None:
            pytest.fail(f"unexpected transcript write: {payload}")

    with pytest.raises(ValueError, match="message event requires"):
        TranscriptRuntimeEventSink(Transcript()).emit(
            RuntimeEvent(run_id="run-1", step=0, type="message", payload={"role": "user"})
        )


def test_tool_orchestrator_emits_lifecycle_fact_through_neutral_host_callback():
    from tools.orchestrator import ToolOrchestrator

    received = []

    class Host:
        _run_id = 4

        def emit_runtime_event(self, *, run_id, step, event_type, payload) -> None:
            received.append((run_id, step, event_type, payload))

    ToolOrchestrator(Host())._emit_tool_lifecycle(
        step=2,
        tool_name="Read",
        tool_call_id="call-1",
        status="requested",
        payload={"args": {"path": "README.md"}},
    )

    assert received == [
        (
            "run-4",
            2,
            "tool_lifecycle",
            {
                "tool_name": "Read",
                "tool_call_id": "call-1",
                "status": "requested",
                "payload": {"args": {"path": "README.md"}},
            },
        )
    ]
