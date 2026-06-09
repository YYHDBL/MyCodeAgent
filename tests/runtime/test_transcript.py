import json
from pathlib import Path

import pytest


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            rows.append(json.loads(line))
    return rows


def test_transcript_event_schema_round_trips_required_fields(tmp_path: Path):
    from runtime.transcript import TranscriptEvent, TranscriptEventType

    event = TranscriptEvent(
        event_id="evt-1",
        timestamp="2026-06-09T10:00:00Z",
        session_id="session-1",
        run_id="run-1",
        step=2,
        event_type=TranscriptEventType.MESSAGE,
        payload={"role": "user", "content": "hello"},
        reference_id="evt-0",
        schema_version=1,
    )

    data = event.to_dict()

    assert data == {
        "event_id": "evt-1",
        "timestamp": "2026-06-09T10:00:00Z",
        "session_id": "session-1",
        "run_id": "run-1",
        "step": 2,
        "event_type": "message",
        "payload": {"role": "user", "content": "hello"},
        "reference_id": "evt-0",
        "schema_version": 1,
    }


def test_transcript_store_appends_jsonl_and_flushes_for_reload(tmp_path: Path):
    from runtime.transcript import TranscriptEventType, TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_message(
        run_id="run-1",
        step=0,
        role="user",
        content="hello",
        metadata={"source": "input"},
    )
    store.append_state_transition(
        run_id="run-1",
        step=1,
        from_state="awaiting_input",
        to_state="waiting_model",
        reason="user_input",
    )

    rows = _read_jsonl(path)

    assert [row["event_type"] for row in rows] == [
        TranscriptEventType.MESSAGE.value,
        TranscriptEventType.STATE_TRANSITION.value,
    ]
    assert rows[0]["payload"]["metadata"] == {"source": "input"}
    assert rows[1]["payload"]["to_state"] == "waiting_model"


def test_transcript_store_ignores_trailing_partial_json_record(tmp_path: Path):
    from runtime.transcript import TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_message(run_id="run-1", step=0, role="user", content="hello")

    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"event_id":"broken"')
        handle.flush()

    events = store.read_events()

    assert len(events) == 1
    assert events[0].payload["content"] == "hello"


def test_transcript_store_can_infer_session_id_from_existing_file(tmp_path: Path):
    from runtime.transcript import TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_message(run_id="run-1", step=0, role="user", content="hello")

    assert TranscriptStore.infer_session_id(path) == "session-1"


def test_resume_loader_rebuilds_messages_and_state_transitions(tmp_path: Path):
    from runtime.transcript import ResumeLoader, TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_message(run_id="run-1", step=0, role="user", content="hello")
    store.append_state_transition(
        run_id="run-1",
        step=0,
        from_state="idle",
        to_state="waiting_model",
        reason="user_input",
    )
    store.append_message(
        run_id="run-1",
        step=1,
        role="assistant",
        content="tool call",
        metadata={"action_type": "tool_call"},
    )
    store.append_checkpoint(
        run_id="run-1",
        step=1,
        checkpoint_id="ckpt-1",
        payload={"retain_start_idx": 4, "summary": "summary(4)"},
    )

    resume = ResumeLoader(store).load(run_id="run-1")

    assert [message["role"] for message in resume.history_messages] == ["user", "assistant"]
    assert resume.loop_state.transition.reason.value == "user_input"
    assert resume.checkpoint["checkpoint_id"] == "ckpt-1"


def test_resume_loader_keeps_completed_tool_results_without_reexecution(tmp_path: Path):
    from runtime.transcript import ResumeLoader, TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_tool_lifecycle(
        run_id="run-1",
        step=1,
        tool_name="Read",
        tool_call_id="call-1",
        status="requested",
        payload={"args": {"path": "README.md"}},
    )
    store.append_tool_lifecycle(
        run_id="run-1",
        step=1,
        tool_name="Read",
        tool_call_id="call-1",
        status="started",
        payload={"args": {"path": "README.md"}},
    )
    store.append_tool_lifecycle(
        run_id="run-1",
        step=1,
        tool_name="Read",
        tool_call_id="call-1",
        status="completed",
        payload={"result": {"status": "success", "data": {"path": "README.md"}}},
    )

    resume = ResumeLoader(store).load(run_id="run-1")

    assert resume.completed_tool_results["call-1"]["result"]["status"] == "success"
    assert resume.pending_tool_calls == []


def test_resume_loader_marks_started_but_unfinished_mutation_tool_uncertain(tmp_path: Path):
    from runtime.transcript import ResumeLoader, TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_tool_lifecycle(
        run_id="run-1",
        step=3,
        tool_name="Write",
        tool_call_id="call-2",
        status="requested",
        payload={"args": {"path": "notes.txt", "content": "draft"}},
    )
    store.append_tool_lifecycle(
        run_id="run-1",
        step=3,
        tool_name="Write",
        tool_call_id="call-2",
        status="started",
        payload={"args": {"path": "notes.txt", "content": "draft"}},
    )

    resume = ResumeLoader(store).load(run_id="run-1")

    assert resume.pending_tool_calls == []
    assert len(resume.uncertain_actions) == 1
    assert resume.uncertain_actions[0].tool_name == "Write"
    assert resume.uncertain_actions[0].tool_call_id == "call-2"
    assert resume.uncertain_actions[0].replay_allowed is False


def test_resume_loader_keeps_requested_but_unstarted_tool_replannable(tmp_path: Path):
    from runtime.transcript import ResumeLoader, TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_tool_lifecycle(
        run_id="run-1",
        step=2,
        tool_name="Read",
        tool_call_id="call-3",
        status="requested",
        payload={"args": {"path": "README.md"}},
    )

    resume = ResumeLoader(store).load(run_id="run-1")

    assert [item["tool_call_id"] for item in resume.pending_tool_calls] == ["call-3"]
    assert resume.uncertain_actions == []


def test_resume_loader_separates_runs_in_same_transcript_file(tmp_path: Path):
    from runtime.transcript import ResumeLoader, TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_message(run_id="run-1", step=0, role="user", content="first")
    store.append_message(run_id="run-2", step=0, role="user", content="second")

    resume = ResumeLoader(store).load(run_id="run-2")

    assert [message["content"] for message in resume.history_messages] == ["second"]


def test_resume_loader_preserves_terminal_state(tmp_path: Path):
    from runtime.transcript import ResumeLoader, TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_terminal(
        run_id="run-1",
        step=4,
        reason="completed",
        details={"final_length": 12},
    )

    resume = ResumeLoader(store).load(run_id="run-1")

    assert resume.terminal is not None
    assert resume.terminal["reason"] == "completed"


def test_trace_logger_and_transcript_store_remain_separate(tmp_path: Path):
    from extensions.tracing.logger import TraceLogger
    from runtime.transcript import TranscriptStore

    trace_dir = tmp_path / "traces"
    transcript_path = tmp_path / "transcript.jsonl"

    trace = TraceLogger(session_id="session-1", trace_dir=trace_dir, enabled=True)
    store = TranscriptStore(transcript_path, session_id="session-1")

    trace.log_event("tool_call", {"tool": "Read"}, step=1)
    store.append_message(run_id="run-1", step=0, role="user", content="hello")
    trace.finalize()

    trace_rows = _read_jsonl(next(trace_dir.glob("trace-*.jsonl")))
    transcript_rows = _read_jsonl(transcript_path)

    assert trace_rows[0]["event"] == "tool_call"
    assert transcript_rows[0]["event_type"] == "message"
    assert "event_type" not in trace_rows[0]
    assert "event" not in transcript_rows[0]
