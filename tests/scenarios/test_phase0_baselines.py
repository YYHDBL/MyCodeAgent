from runtime.loop import RuntimeRunner

from tests.scenarios.phase0_baselines import (
    AlwaysEmptyScenarioHost,
    AlwaysToolScenarioHost,
    CompletionGateBlockedScenarioHost,
    CompressingScenarioHost,
    EmptyThenFinalScenarioHost,
    PermissionDeniedScenarioHost,
    ToolFailureScenarioHost,
    ToolThenFinalScenarioHost,
    run_phase0_mock_scenarios,
    summarize_trace,
)


def test_phase0_mock_baselines_cover_expected_runtime_paths():
    cases = [
        ("normal_complete", ToolThenFinalScenarioHost(tool_name="Read", final_text="tool done"), "tool done", "completed"),
        ("read_only_search", ToolThenFinalScenarioHost(), "tool done", "completed"),
        ("file_edit", ToolThenFinalScenarioHost(tool_name="Write"), "tool done", "completed"),
        ("tool_failure", ToolFailureScenarioHost(), "tool done", "completed"),
        ("permission_deny", PermissionDeniedScenarioHost(), "tool done", "completed"),
        ("context_compaction", CompressingScenarioHost(), "runner final answer", "completed"),
        ("empty_response_recovery", EmptyThenFinalScenarioHost(), "after retry", "completed"),
        ("completion_gate_block", CompletionGateBlockedScenarioHost(), "抱歉，我无法在限定步数内完成这个任务。", "completion_gate_blocked"),
        ("max_steps", AlwaysToolScenarioHost(), "抱歉，我无法在限定步数内完成这个任务。", "max_steps"),
        ("empty_response_failed", AlwaysEmptyScenarioHost(), "抱歉，我无法在限定步数内完成这个任务。", "empty_response_failed"),
    ]

    for name, host, expected_text, expected_terminal in cases:
        result = RuntimeRunner(host).run(name, show_raw=False)

        assert result == expected_text
        summary = summarize_trace(host.trace_logger.events)
        assert summary["terminal_reason"] == expected_terminal
        assert summary["step_count"] >= 1
        assert summary["tool_call_count"] >= 0
        assert "failure_stage" in summary
        assert "model_call_count" in summary


def test_phase0_mock_baseline_batch_runner_returns_json_summary(tmp_path):
    output_path = tmp_path / "phase0-summary.json"

    report = run_phase0_mock_scenarios(output_path=output_path)

    assert output_path.exists()
    assert report["scenario_count"] >= 6
    assert report["scenarios"]
    by_name = {item["scenario_name"]: item for item in report["scenarios"]}
    assert {"normal_complete", "tool_call", "completion_gate_block", "model_recovery", "permission_deny", "context_compaction"} <= set(by_name)
    assert by_name["permission_deny"]["metrics"]["permission_denied_count"] >= 1
    assert by_name["completion_gate_block"]["metrics"]["failure_stage"] == "completion_gate"
    assert by_name["model_recovery"]["metrics"]["model_recovery_count"] >= 1
    assert by_name["context_compaction"]["metrics"]["context_compaction_count"] >= 1
