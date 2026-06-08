from runtime.loop import RuntimeRunner

from tests.scenarios.phase0_baselines import (
    AlwaysEmptyScenarioHost,
    AlwaysToolScenarioHost,
    CompressingScenarioHost,
    EmptyThenFinalScenarioHost,
    ToolFailureScenarioHost,
    ToolThenFinalScenarioHost,
    summarize_trace,
)


def test_phase0_mock_baselines_cover_expected_runtime_paths():
    cases = [
        ("read_only_search", ToolThenFinalScenarioHost(), "tool done", "completed"),
        ("file_edit", ToolThenFinalScenarioHost(tool_name="Write"), "tool done", "completed"),
        ("tool_failure", ToolFailureScenarioHost(), "tool done", "completed"),
        ("context_compaction", CompressingScenarioHost(), "runner final answer", "completed"),
        ("empty_response_recovery", EmptyThenFinalScenarioHost(), "after retry", "completed"),
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
        assert summary["projection_modes"]
