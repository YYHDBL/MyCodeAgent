from pathlib import Path


def test_session_memory_schema_round_trips_required_fields():
    from runtime.session_memory import (
        SESSION_MEMORY_SCHEMA_VERSION,
        SessionMemory,
        SessionMemoryItem,
        TranscriptEventRange,
    )

    memory = SessionMemory(
        schema_version=SESSION_MEMORY_SCHEMA_VERSION,
        current_goal=SessionMemoryItem(
            text="Implement session memory",
            source=TranscriptEventRange(
                start_event_id="evt-1",
                end_event_id="evt-1",
                start_step=0,
                end_step=0,
            ),
        ),
        completed_work=(
            SessionMemoryItem(
                text="Read roadmap",
                source=TranscriptEventRange(
                    start_event_id="evt-2",
                    end_event_id="evt-2",
                    start_step=1,
                    end_step=1,
                ),
            ),
        ),
        key_decisions=(),
        failed_attempts=(),
        todo_items=(),
        verification_status=(),
        source=TranscriptEventRange(
            start_event_id="evt-1",
            end_event_id="evt-2",
            start_step=0,
            end_step=1,
        ),
        version=2,
        event_count=2,
        last_event_id="evt-2",
    )

    payload = memory.to_dict()
    restored = SessionMemory.from_dict(payload)

    assert restored == memory
    assert payload["schema_version"] == SESSION_MEMORY_SCHEMA_VERSION
    assert payload["source"]["start_event_id"] == "evt-1"


def test_session_memory_rebuilds_from_transcript_events(tmp_path: Path):
    from runtime.session_memory import SessionMemoryDeriver
    from runtime.transcript import TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_message(run_id="run-1", step=0, role="user", content="Implement Phase 6B")
    store.append_tool_lifecycle(
        run_id="run-1",
        step=1,
        tool_name="Read",
        tool_call_id="call-1",
        status="completed",
        payload={"result": {"status": "success", "data": {"path": "docs/HARNESS_ROADMAP.md"}}},
    )
    store.append_state_transition(
        run_id="run-1",
        step=2,
        from_state="waiting_model",
        to_state="waiting_model",
        reason="context_compacted",
        details={"checkpoint_id": "ckpt-1"},
    )
    store.append_terminal(
        run_id="run-1",
        step=3,
        reason="completed",
        details={"completion_verdict": "pass"},
    )

    memory = SessionMemoryDeriver().rebuild(store.read_events(run_id="run-1"))

    assert memory.current_goal is not None
    assert memory.current_goal.text == "Implement Phase 6B"
    assert any("Read" in item.text for item in memory.completed_work)
    assert any("checkpoint" in item.text.lower() for item in memory.key_decisions)
    assert any("completed" in item.text.lower() for item in memory.verification_status)
    assert memory.source.start_event_id is not None
    assert memory.source.end_event_id is not None


def test_session_memory_supports_incremental_updates(tmp_path: Path):
    from runtime.session_memory import SessionMemoryDeriver
    from runtime.transcript import TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    first = store.append_message(run_id="run-1", step=0, role="user", content="Build memory")
    deriver = SessionMemoryDeriver()

    memory = deriver.update(None, [first])
    second = store.append_tool_lifecycle(
        run_id="run-1",
        step=1,
        tool_name="Read",
        tool_call_id="call-1",
        status="completed",
        payload={"result": {"status": "success"}},
    )
    updated = deriver.update(memory, [second])
    rebuilt = deriver.rebuild(store.read_events(run_id="run-1"))

    assert updated == rebuilt
    assert updated.version == memory.version + 1


def test_session_memory_summary_failure_keeps_previous_valid_version():
    from runtime.session_memory import SessionMemoryDeriver, SessionMemoryItem, TranscriptEventRange
    from runtime.transcript import TranscriptEvent, TranscriptEventType

    deriver = SessionMemoryDeriver()
    first = TranscriptEvent(
        event_id="evt-1",
        timestamp="2026-06-09T10:00:00Z",
        session_id="session-1",
        run_id="run-1",
        step=0,
        event_type=TranscriptEventType.MESSAGE,
        payload={"role": "user", "content": "Do work", "metadata": {}},
    )
    previous = deriver.rebuild([first])
    second = TranscriptEvent(
        event_id="evt-2",
        timestamp="2026-06-09T10:01:00Z",
        session_id="session-1",
        run_id="run-1",
        step=1,
        event_type=TranscriptEventType.TOOL_LIFECYCLE,
        payload={
            "tool_name": "Read",
            "tool_call_id": "call-1",
            "status": "completed",
            "result": {"status": "success"},
        },
    )

    def failing_summary(_draft, _previous, _events):
        raise RuntimeError("summary failed")

    updated = deriver.update(previous, [second], summary_refiner=failing_summary)

    assert updated == previous
    assert updated.current_goal == SessionMemoryItem(
        text="Do work",
        source=TranscriptEventRange(
            start_event_id="evt-1",
            end_event_id="evt-1",
            start_step=0,
            end_step=0,
        ),
    )


def test_session_memory_keeps_uncertain_actions_as_unresolved_risk(tmp_path: Path):
    from runtime.session_memory import SessionMemoryDeriver
    from runtime.transcript import TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_message(run_id="run-1", step=0, role="user", content="Update notes")
    store.append_tool_lifecycle(
        run_id="run-1",
        step=2,
        tool_name="Write",
        tool_call_id="call-2",
        status="requested",
        payload={"args": {"path": "notes.txt"}},
    )
    store.append_tool_lifecycle(
        run_id="run-1",
        step=2,
        tool_name="Write",
        tool_call_id="call-2",
        status="started",
        payload={"args": {"path": "notes.txt"}},
    )

    memory = SessionMemoryDeriver().rebuild(store.read_events(run_id="run-1"))

    assert not any("call-2" in item.text for item in memory.completed_work)
    assert any("call-2" in item.text for item in memory.todo_items)
    assert any("uncertain" in item.text.lower() for item in memory.verification_status)


def test_session_memory_rebuild_matches_resume_recovery(tmp_path: Path):
    from runtime.session_memory import SessionMemoryDeriver
    from runtime.transcript import ResumeLoader, TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_message(run_id="run-1", step=0, role="user", content="Implement session memory")
    store.append_tool_lifecycle(
        run_id="run-1",
        step=1,
        tool_name="Read",
        tool_call_id="call-1",
        status="completed",
        payload={"result": {"status": "success"}},
    )

    before_resume = SessionMemoryDeriver().rebuild(store.read_events(run_id="run-1"))
    resume = ResumeLoader(store).load(run_id="run-1")

    assert resume.session_memory == before_resume
