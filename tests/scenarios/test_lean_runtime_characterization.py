import json

from runtime.loop import RuntimeRunner
from runtime.transcript import ResumeLoader
from tools.context import ToolExecutionContext
from tools.executor import ToolExecutor
from tools.permissions import PermissionContext, RiskClassifier
from tools.registry import ToolRegistry
from tools.base import ToolResult, ToolStatus
from tools.base import serialize_tool_result

from tests.scenarios.phase0_baselines import (
    CountingEditScenarioHost,
    CompressingScenarioHost,
    FinalOnlyScenarioHost,
    PermissionDeniedScenarioHost,
    StaleEvidenceScenarioHost,
    TranscriptAwareContinuationScenarioHost,
    ToolThenFinalScenarioHost,
    VerifiedEditScenarioHost,
    attach_transcript,
)


def _event_names(host):
    return [name for name, _step, _payload in host.trace_logger.events]


def _events(host, name):
    return [payload for event_name, _step, payload in host.trace_logger.events if event_name == name]


def test_one_user_turn_reaches_final_completion_terminal():
    host = FinalOnlyScenarioHost()

    result = RuntimeRunner(host).run("summarize the repository", show_raw=False)

    assert result == "runner final answer"
    assert [message["role"] for message in host.history_manager.messages] == ["user", "assistant"]
    assert _events(host, "terminal")[-1]["reason"] == "completed"
    assert "tool_call" not in _event_names(host)


def test_authorized_tool_execution_records_an_observation_before_final():
    host = ToolThenFinalScenarioHost(tool_name="Read", final_text="read complete")
    registry = ToolRegistry()
    executed_inputs = []

    def read_fixture(parameters):
        executed_inputs.append(parameters)
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={"path": parameters["path"]},
            text="fixture read",
            stats={"time_ms": 1},
            context={"cwd": ".", "params_input": parameters},
        )

    registry.register_function("Read", "deterministic read fixture", read_fixture)
    host.tool_executor = ToolExecutor(
        registry,
        context=ToolExecutionContext(
            permission_context=PermissionContext(runtime_mode="main_agent"),
            permission_decider=RiskClassifier().classify,
            project_root=host.project_root,
        ),
    )

    result = RuntimeRunner(host).run("read the project", show_raw=False)

    assert result == "read complete"
    assert executed_inputs == [{"path": "."}]
    names = _event_names(host)
    assert names.index("tool_call") < names.index("permission_decision") < names.index("tool_result")
    tool_message = next(message for message in host.history_manager.messages if message["role"] == "tool")
    observation = json.loads(tool_message["content"])
    assert observation["status"] == "success"
    assert observation["context"]["params_input"] == {"path": "."}
    assert _events(host, "terminal")[-1]["reason"] == "completed"


def test_permission_rejection_is_a_normal_tool_observation():
    host = PermissionDeniedScenarioHost()

    result = RuntimeRunner(host).run("attempt a write", show_raw=False)

    assert result == "tool done"
    tool_message = next(message for message in host.history_manager.messages if message["role"] == "tool")
    observation = json.loads(tool_message["content"])
    assert observation["status"] == "error"
    assert observation["error"]["code"] == "PERMISSION_DENIED"
    assert _events(host, "permission_decision")[-1]["effective_action"] == "deny"
    assert _events(host, "terminal")[-1]["reason"] == "completed"


def test_context_threshold_creates_checkpoint_without_deleting_source_history():
    host = CompressingScenarioHost()
    original_history = [(message["role"], message["content"]) for message in host.history_manager.messages]

    result = RuntimeRunner(host).run("continue the task", show_raw=False)

    assert result == "runner final answer"
    checkpoint = host.context_engine.compact_store.active_checkpoint
    assert checkpoint is not None
    assert checkpoint.source_message_count == len(original_history) + 1
    current_history = [(message["role"], message["content"]) for message in host.history_manager.messages]
    assert current_history[: len(original_history)] == original_history
    assert "compact_checkpoint" in [item["projection_mode"] for item in _events(host, "context_build")]


def test_oversized_tool_output_persists_full_artifact_and_bounded_preview(tmp_path, monkeypatch):
    host = ToolThenFinalScenarioHost(tool_name="Read", final_text="large result handled")
    host.project_root = str(tmp_path)
    full_output = ToolResult(
        status=ToolStatus.SUCCESS,
        data={"content": "line\n" * 600},
        text="large fixture",
        stats={"time_ms": 1},
        context={"cwd": ".", "params_input": {}},
    )
    host._execute_tool = lambda _tool_name, _tool_input: full_output
    monkeypatch.setenv("MYCODEAGENT_MAX_TOOL_RESULT_BYTES", "200")
    monkeypatch.setenv("TOOL_OUTPUT_MAX_BYTES", "256")

    result = RuntimeRunner(host).run("read a large file", show_raw=False)

    assert result == "large result handled"
    tool_message = next(message for message in host.history_manager.messages if message["role"] == "tool")
    observation = json.loads(tool_message["content"])
    truncation = observation["data"]["truncation"]
    artifact = tmp_path / truncation["full_output_path"]
    assert observation["status"] == "partial"
    assert artifact.exists()
    assert artifact.read_text(encoding="utf-8") == serialize_tool_result(full_output)
    assert len(observation["data"]["preview"].encode("utf-8")) <= truncation["max_bytes"]
    assert len(tool_message["content"].encode("utf-8")) < len(serialize_tool_result(full_output).encode("utf-8"))


def test_transcript_records_user_assistant_tool_transition_and_terminal_facts(tmp_path):
    host = ToolThenFinalScenarioHost()
    store = attach_transcript(host, tmp_path / "transcript.jsonl")

    assert RuntimeRunner(host).run("inspect the project", show_raw=False) == "tool done"

    events = store.read_events(run_id="run-1")
    assert [event.payload["role"] for event in events if event.event_type.value == "message"] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert {event.event_type.value for event in events} >= {
        "message",
        "state_transition",
        "tool_lifecycle",
        "terminal",
    }
    transitions = [event.payload["reason"] for event in events if event.event_type.value == "state_transition"]
    assert {"user_input", "model_returned_tool_calls", "tools_executed", "model_returned_final"} <= set(transitions)
    assert [event.payload["status"] for event in events if event.event_type.value == "tool_lifecycle"] == [
        "requested",
        "started",
        "completed",
    ]
    assert events[-1].event_type.value == "terminal"
    assert events[-1].payload["reason"] == "completed"


def test_resume_does_not_replay_a_completed_side_effecting_tool(tmp_path):
    effects = {"writes": 0}
    host = CountingEditScenarioHost(effects)
    store = attach_transcript(host, tmp_path / "transcript.jsonl")

    assert RuntimeRunner(host).run("record one edit", show_raw=False) == "edit done"
    resume = ResumeLoader(store).load(run_id="run-1")
    resumed_host = TranscriptAwareContinuationScenarioHost(effects)
    resume.apply_to_host(resumed_host)

    assert (
        RuntimeRunner(resumed_host).run("continue from the transcript", show_raw=False)
        == "continued without replay"
    )

    assert effects["writes"] == 1
    assert resume.pending_tool_calls == []
    assert resume.uncertain_actions == []
    assert resume.completed_tool_results["call_1"]["result"]["status"] == "success"
    assert "tool_call" not in _event_names(resumed_host)
    assert resumed_host.continuation_decision == "final_after_completed_write"
    assert _events(resumed_host, "terminal")[-1]["reason"] == "completed"


def test_runtime_blocks_completion_when_required_test_evidence_is_missing():
    host = FinalOnlyScenarioHost()

    result = RuntimeRunner(host).run("make the change and run tests", show_raw=False)

    assert result == "抱歉，我无法在限定步数内完成这个任务。"
    assert _events(host, "terminal")[-1]["reason"] == "completion_gate_blocked"
    assert all(
        "missing_verification_evidence:tests" in payload["reasons"]
        for payload in _events(host, "completion_gate_verdict")
    )


def test_edit_followed_by_verification_can_complete_with_current_evidence():
    host = VerifiedEditScenarioHost()

    result = RuntimeRunner(host).run("make the change and run tests", show_raw=False)

    assert result == "edit and tests complete"
    assert host.effects["writes"] == 1
    assert [payload["tool"] for payload in _events(host, "tool_call")] == ["Edit", "Bash"]
    assert _events(host, "completion_gate_verdict")[-1]["verdict"] == "pass"
    assert _events(host, "terminal")[-1]["reason"] == "completed"


def test_runtime_blocks_completion_when_test_evidence_is_stale_after_mutation():
    host = StaleEvidenceScenarioHost()

    result = RuntimeRunner(host).run("make the change and run tests", show_raw=False)

    assert result == "抱歉，我无法在限定步数内完成这个任务。"
    assert _events(host, "terminal")[-1]["reason"] == "completion_gate_blocked"
    assert all(
        "verification_invalid:tests" in payload["reasons"]
        for payload in _events(host, "completion_gate_verdict")
    )
