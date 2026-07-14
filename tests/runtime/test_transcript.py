import json
from pathlib import Path

def _configure_runtime_host(agent, recorder) -> None:
    """Give partial hosts the stable dependencies a real CodeAgent owns."""

    from runtime.events import TranscriptRuntimeEventSink
    from runtime.session_memory import SessionMemoryManager

    agent.runtime_event_sink = TranscriptRuntimeEventSink(recorder)
    agent.session_memory_manager = SessionMemoryManager(on_update=lambda _memory: None)
    agent._active_transcript_run_id = None
    agent._turn_cancelled = False
    agent._run_id = 0


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


def test_transcript_session_id_is_unique_when_tracing_is_disabled():
    from runtime.transcript import resolve_transcript_session_id

    first = resolve_transcript_session_id("disabled")
    second = resolve_transcript_session_id("disabled")

    assert first.startswith("session-")
    assert second.startswith("session-")
    assert first != second
    assert resolve_transcript_session_id("trace-session-1") == "trace-session-1"


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


def test_transcript_store_can_append_after_trailing_partial_record(tmp_path: Path):
    from runtime.transcript import TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_message(run_id="run-1", step=0, role="user", content="before crash")
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"event_id":"broken"')
        handle.flush()

    store.append_message(run_id="run-1", step=1, role="assistant", content="after resume")
    events = store.read_events()

    assert [event.payload["content"] for event in events] == [
        "before crash",
        "after resume",
    ]


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
    assert any("Read" in item.text for item in resume.session_memory.completed_work)


def test_resume_loader_marks_started_but_unfinished_mutation_tool_uncertain(tmp_path: Path):
    from runtime.transcript import ResumeLoader, TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_tool_lifecycle(
        run_id="run-1",
        step=3,
        tool_name="Edit",
        tool_call_id="call-2",
        status="requested",
        payload={"args": {"path": "notes.txt", "content": "draft"}},
    )
    store.append_tool_lifecycle(
        run_id="run-1",
        step=3,
        tool_name="Edit",
        tool_call_id="call-2",
        status="started",
        payload={"args": {"path": "notes.txt", "content": "draft"}},
    )

    resume = ResumeLoader(store).load(run_id="run-1")

    assert resume.pending_tool_calls == []
    assert len(resume.uncertain_actions) == 1
    assert resume.uncertain_actions[0].tool_name == "Edit"
    assert resume.uncertain_actions[0].tool_call_id == "call-2"
    assert resume.uncertain_actions[0].replay_allowed is False
    assert not any("call-2" in item.text for item in resume.session_memory.completed_work)
    assert any("call-2" in item.text for item in resume.session_memory.todo_items)


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


def test_resume_loader_restores_all_session_runs_but_keeps_requested_run_semantics(tmp_path: Path):
    from runtime.transcript import ResumeLoader, TranscriptStore

    store = TranscriptStore(tmp_path / "transcript.jsonl", session_id="session-1")
    store.append_message(run_id="run-1", step=0, role="user", content="first question")
    store.append_message(run_id="run-1", step=1, role="assistant", content="first answer")
    store.append_message(run_id="run-2", step=0, role="user", content="second question")
    store.append_message(run_id="run-2", step=1, role="assistant", content="second answer")

    loader = ResumeLoader(store)
    resumed_session = loader.load_session()
    requested_run = loader.load(run_id="run-2")

    assert [message["content"] for message in resumed_session.history_messages] == [
        "first question",
        "first answer",
        "second question",
        "second answer",
    ]
    assert resumed_session.run_id == "run-2"
    assert [message["content"] for message in requested_run.history_messages] == ["second question", "second answer"]


def test_resume_adds_paired_uncertain_tool_observation_for_interrupted_started_call(tmp_path: Path):
    from runtime.context.normalizer import MessageNormalizer
    from runtime.history import HistoryManager
    from runtime.transcript import ResumeLoader, TranscriptStore

    store = TranscriptStore(tmp_path / "transcript.jsonl", session_id="session-1")
    store.append_message(
        run_id="run-1",
        step=1,
        role="assistant",
        content="",
        metadata={
            "action_type": "tool_call",
            "tool_calls": [{"id": "call-edit", "name": "Edit", "arguments": {"path": "notes.txt"}}],
        },
    )
    store.append_tool_lifecycle(
        run_id="run-1",
        step=1,
        tool_name="Edit",
        tool_call_id="call-edit",
        status="requested",
        payload={"args": {"path": "notes.txt"}},
    )
    store.append_tool_lifecycle(
        run_id="run-1",
        step=1,
        tool_name="Edit",
        tool_call_id="call-edit",
        status="started",
        payload={"args": {"path": "notes.txt"}},
    )
    store.append_terminal(run_id="run-1", step=1, reason="interrupted", details={"cancelled": True})

    resume = ResumeLoader(store).load_session()
    history = HistoryManager()
    history.load_messages(resume.history_messages)
    model_messages = MessageNormalizer().normalize(history.get_messages())

    assert [message["role"] for message in model_messages] == ["assistant", "tool"]
    assert model_messages[0]["tool_calls"][0]["id"] == "call-edit"
    assert model_messages[1]["tool_call_id"] == "call-edit"
    assert json.loads(model_messages[1]["content"])["error"]["code"] == "INTERRUPTED_UNCERTAIN"
    assert [action.tool_call_id for action in resume.uncertain_actions] == ["call-edit"]


def test_resume_pairs_completed_and_uncertain_calls_when_interrupt_prevents_tool_messages(tmp_path: Path):
    from runtime.context.normalizer import MessageNormalizer
    from runtime.history import HistoryManager
    from runtime.transcript import ResumeLoader, TranscriptStore

    store = TranscriptStore(tmp_path / "transcript.jsonl", session_id="session-1")
    store.append_message(
        run_id="run-1",
        step=1,
        role="assistant",
        content="",
        metadata={
            "action_type": "tool_call",
            "tool_calls": [
                {"id": "call-read", "name": "Read", "arguments": {"path": "README.md"}},
                {"id": "call-edit", "name": "Edit", "arguments": {"path": "notes.txt"}},
            ],
        },
    )
    for call_id, tool_name in (("call-read", "Read"), ("call-edit", "Edit")):
        store.append_tool_lifecycle(
            run_id="run-1",
            step=1,
            tool_name=tool_name,
            tool_call_id=call_id,
            status="requested",
            payload={"args": {}},
        )
        store.append_tool_lifecycle(
            run_id="run-1",
            step=1,
            tool_name=tool_name,
            tool_call_id=call_id,
            status="started",
            payload={"args": {}},
        )
    store.append_tool_lifecycle(
        run_id="run-1",
        step=1,
        tool_name="Read",
        tool_call_id="call-read",
        status="completed",
        payload={"result": {"status": "success", "data": {"content": "done"}}},
    )
    store.append_terminal(run_id="run-1", step=1, reason="interrupted", details={"cancelled": True})

    resume = ResumeLoader(store).load_session()
    history = HistoryManager()
    history.load_messages(resume.history_messages)
    model_messages = MessageNormalizer().normalize(history.get_messages())

    assert [message["tool_call_id"] for message in model_messages[1:]] == ["call-read", "call-edit"]
    assert json.loads(model_messages[1]["content"])["status"] == "success"
    assert json.loads(model_messages[2]["content"])["error"]["code"] == "INTERRUPTED_UNCERTAIN"
    assert [action.tool_call_id for action in resume.uncertain_actions] == ["call-edit"]


def test_resume_keeps_persisted_tool_observations_before_synthetic_interrupted_ones(tmp_path: Path):
    from runtime.context.normalizer import MessageNormalizer
    from runtime.history import HistoryManager
    from runtime.transcript import ResumeLoader, TranscriptStore

    store = TranscriptStore(tmp_path / "transcript.jsonl", session_id="session-1")
    store.append_message(
        run_id="run-1",
        step=1,
        role="assistant",
        content="",
        metadata={
            "action_type": "tool_call",
            "tool_calls": [
                {"id": "call-one", "name": "Read", "arguments": {}},
                {"id": "call-two", "name": "Edit", "arguments": {}},
            ],
        },
    )
    store.append_message(
        run_id="run-1",
        step=1,
        role="tool",
        content='{"status":"success"}',
        metadata={"tool_name": "Read", "tool_call_id": "call-one"},
    )
    store.append_tool_lifecycle(
        run_id="run-1", step=1, tool_name="Edit", tool_call_id="call-two", status="requested", payload={}
    )
    store.append_tool_lifecycle(
        run_id="run-1", step=1, tool_name="Edit", tool_call_id="call-two", status="started", payload={}
    )

    resume = ResumeLoader(store).load_session()
    history = HistoryManager()
    history.load_messages(resume.history_messages)
    model_messages = MessageNormalizer().normalize(history.get_messages())

    assert [message["tool_call_id"] for message in model_messages[1:]] == ["call-one", "call-two"]
    assert [action.tool_call_id for action in resume.uncertain_actions] == ["call-two"]


def test_resume_scopes_duplicate_tool_call_ids_to_their_run(tmp_path: Path):
    from runtime.context.normalizer import MessageNormalizer
    from runtime.history import HistoryManager
    from runtime.transcript import ResumeLoader, TranscriptStore

    store = TranscriptStore(tmp_path / "transcript.jsonl", session_id="session-1")
    for run_id in ("run-1", "run-2"):
        store.append_message(
            run_id=run_id,
            step=1,
            role="assistant",
            content="",
            metadata={"action_type": "tool_call", "tool_calls": [{"id": "call-shared", "name": "Edit", "arguments": {}}]},
        )
        store.append_tool_lifecycle(
            run_id=run_id, step=1, tool_name="Edit", tool_call_id="call-shared", status="requested", payload={}
        )
        store.append_tool_lifecycle(
            run_id=run_id, step=1, tool_name="Edit", tool_call_id="call-shared", status="started", payload={}
        )
        if run_id == "run-1":
            store.append_tool_lifecycle(
                run_id=run_id,
                step=1,
                tool_name="Edit",
                tool_call_id="call-shared",
                status="completed",
                payload={"result": {"status": "success"}},
            )
            store.append_message(
                run_id=run_id,
                step=1,
                role="tool",
                content='{"status":"success"}',
                metadata={"tool_name": "Edit", "tool_call_id": "call-shared"},
            )

    resume = ResumeLoader(store).load_session()
    history = HistoryManager()
    history.load_messages(resume.history_messages)
    model_messages = MessageNormalizer().normalize(history.get_messages())

    assert [message["role"] for message in model_messages] == ["assistant", "tool", "assistant", "tool"]
    assert json.loads(model_messages[-1]["content"])["error"]["code"] == "INTERRUPTED_UNCERTAIN"
    assert [action.tool_call_id for action in resume.uncertain_actions] == ["call-shared"]


def test_transcript_store_lists_and_resolves_sessions_by_recent_transcript(tmp_path: Path):
    from runtime.transcript import TranscriptStore

    transcripts = tmp_path / "memory" / "transcripts"
    old = TranscriptStore(transcripts / "transcript-session-old.jsonl", session_id="session-old")
    old.append_message(run_id="run-1", step=0, role="user", content="old")
    current = TranscriptStore(transcripts / "transcript-session-current.jsonl", session_id="session-current")
    current.append_message(run_id="run-3", step=0, role="user", content="current")

    sessions = TranscriptStore.list_sessions(transcripts)

    assert {session.session_id for session in sessions} == {"session-old", "session-current"}
    assert TranscriptStore.resolve_session(transcripts, "session-current").latest_run_id == "run-3"
    assert TranscriptStore.resolve_session(transcripts).session_id in {"session-old", "session-current"}


def test_cancelling_active_transcript_run_records_terminal_and_preserves_uncertain_tool(tmp_path: Path):
    from runtime.host import CodeAgent
    from runtime.transcript import ResumeLoader, TranscriptRecorder, TranscriptStore

    store = TranscriptStore(tmp_path / "transcript.jsonl", session_id="session-1")
    recorder = TranscriptRecorder(store)
    recorder.record_tool_lifecycle(
        run_id="run-2",
        step=3,
        tool_name="Edit",
        tool_call_id="call-2",
        status="requested",
        payload={"args": {"path": "notes.txt"}},
    )
    recorder.record_tool_lifecycle(
        run_id="run-2",
        step=3,
        tool_name="Edit",
        tool_call_id="call-2",
        status="started",
        payload={"args": {"path": "notes.txt"}},
    )

    agent = CodeAgent.__new__(CodeAgent)
    agent.transcript_store = store
    agent.transcript_recorder = recorder
    _configure_runtime_host(agent, recorder)
    result = CodeAgent.cancel_active_turn(agent)
    resume = ResumeLoader(store).load(run_id="run-2")

    assert result == {"cancelled": True, "run_id": "run-2"}
    assert resume.terminal == {"reason": "interrupted", "details": {"cancelled": True}}
    assert [event.event_type.value for event in store.read_events(run_id="run-2")] == [
        "tool_lifecycle",
        "tool_lifecycle",
        "terminal",
    ]
    assert [action.tool_call_id for action in resume.uncertain_actions] == ["call-2"]


def test_cancelling_active_turn_emits_terminal_to_runtime_event_sink(tmp_path: Path):
    from runtime.host import CodeAgent
    from runtime.transcript import TranscriptRecorder, TranscriptStore

    store = TranscriptStore(tmp_path / "transcript.jsonl", session_id="session-1")
    recorder = TranscriptRecorder(store)
    recorder.record_message(run_id="run-1", step=2, role="user", content="work")
    emitted = []

    class Sink:
        def emit(self, event) -> None:
            emitted.append(event)

    agent = CodeAgent.__new__(CodeAgent)
    agent.transcript_store = store
    agent.transcript_recorder = recorder
    _configure_runtime_host(agent, recorder)
    agent.runtime_event_sink = Sink()
    agent._active_transcript_run_id = "run-1"

    assert CodeAgent.cancel_active_turn(agent) == {"cancelled": True, "run_id": "run-1"}
    assert [(event.run_id, event.step, event.type, event.payload) for event in emitted] == [
        ("run-1", 2, "terminal", {"reason": "interrupted", "details": {"cancelled": True}})
    ]


def test_cancelling_the_same_active_turn_twice_records_one_terminal(tmp_path: Path):
    from runtime.host import CodeAgent
    from runtime.transcript import TranscriptRecorder, TranscriptStore

    store = TranscriptStore(tmp_path / "transcript.jsonl", session_id="session-1")
    recorder = TranscriptRecorder(store)
    recorder.record_message(run_id="run-1", step=0, role="user", content="work")
    agent = CodeAgent.__new__(CodeAgent)
    agent.transcript_store = store
    agent.transcript_recorder = recorder
    _configure_runtime_host(agent, recorder)
    agent._active_transcript_run_id = "run-1"

    first = CodeAgent.cancel_active_turn(agent)
    second = CodeAgent.cancel_active_turn(agent)

    assert first == {"cancelled": True, "run_id": "run-1"}
    assert second == {"cancelled": False, "run_id": None}
    assert [event.event_type.value for event in store.read_events()] == ["message", "terminal"]


def test_second_cancel_does_not_fall_back_to_an_old_incomplete_run(tmp_path: Path):
    from runtime.host import CodeAgent
    from runtime.transcript import TranscriptRecorder, TranscriptStore

    store = TranscriptStore(tmp_path / "transcript.jsonl", session_id="session-1")
    recorder = TranscriptRecorder(store)
    recorder.record_tool_lifecycle(
        run_id="run-old", step=1, tool_name="Edit", tool_call_id="old-call", status="started", payload={}
    )
    recorder.record_message(run_id="run-new", step=0, role="user", content="current work")
    agent = CodeAgent.__new__(CodeAgent)
    agent.transcript_store = store
    agent.transcript_recorder = recorder
    _configure_runtime_host(agent, recorder)
    agent._active_transcript_run_id = "run-new"

    first = CodeAgent.cancel_active_turn(agent)
    second = CodeAgent.cancel_active_turn(agent)

    assert first == {"cancelled": True, "run_id": "run-new"}
    assert second == {"cancelled": False, "run_id": None}
    assert [event.run_id for event in store.read_events() if event.event_type.value == "terminal"] == ["run-new"]


def test_code_agent_resumes_latest_session_from_transcript_not_snapshot(tmp_path: Path):
    from runtime.host import CodeAgent
    from runtime.transcript import TranscriptStore

    project_root = tmp_path / "project"
    transcript_path = project_root / "memory" / "transcripts" / "transcript-session-7.jsonl"
    store = TranscriptStore(transcript_path, session_id="session-7")
    store.append_message(run_id="run-3", step=0, role="user", content="earlier turn")
    store.append_message(run_id="run-4", step=0, role="user", content="continue")

    class _History:
        def load_messages(self, messages):
            self.messages = messages

        def get_message_count(self):
            return len(getattr(self, "messages", []))

    class _ContextEngine:
        def reset(self):
            return None

        def set_session_memory(self, memory):
            self.memory = memory

    agent = CodeAgent.__new__(CodeAgent)
    agent.project_root = str(project_root)
    agent.transcript_store = TranscriptStore(tmp_path / "new-session.jsonl", session_id="new-session")
    agent.history_manager = _History()
    agent.context_engine = _ContextEngine()
    agent.tool_registry = None
    agent._run_id = 0
    _configure_runtime_host(agent, None)

    requested = CodeAgent.load_transcript(agent, str(transcript_path), run_id="run-4")
    resume = CodeAgent.resume_transcript(agent, "session-7")

    assert [message["content"] for message in requested.history_messages] == ["continue"]
    assert resume.session_id == "session-7"
    assert [message["content"] for message in agent.history_manager.messages] == ["earlier turn", "continue"]
    assert agent.transcript_store.path == transcript_path
    assert agent._run_id == 4


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


def test_code_agent_load_transcript_exposes_resume_state(tmp_path: Path):
    from runtime.host import CodeAgent
    from runtime.transcript import TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_tool_lifecycle(
        run_id="run-1",
        step=1,
        tool_name="Edit",
        tool_call_id="call-1",
        status="requested",
        payload={"args": {"path": "notes.txt"}},
    )
    store.append_tool_lifecycle(
        run_id="run-1",
        step=1,
        tool_name="Edit",
        tool_call_id="call-1",
        status="started",
        payload={"args": {"path": "notes.txt"}},
    )

    class _History:
        def load_messages(self, messages):
            self.messages = messages

    class _CompactStore:
        def set_active(self, checkpoint):
            self.active_checkpoint = checkpoint

    class _ContextEngine:
        def __init__(self):
            self.compact_store = _CompactStore()

        def reset(self):
            return None

    agent = CodeAgent.__new__(CodeAgent)
    agent.transcript_store = store
    agent.history_manager = _History()
    agent.context_engine = _ContextEngine()
    agent.tool_registry = None
    _configure_runtime_host(agent, None)

    resume = CodeAgent.load_transcript(agent, str(path), run_id="run-1")

    assert resume is agent.resume_state
    assert resume.uncertain_actions[0].tool_call_id == "call-1"
    assert resume.uncertain_actions[0].replay_allowed is False
    assert agent.session_memory == resume.session_memory
