from demo.harness_portfolio import DEMO_NAMES, run_all_demos, run_demo


def _event_names(report):
    return [event["event"] for event in report["trace"]]


def test_portfolio_demo_catalog_covers_four_core_modules():
    assert DEMO_NAMES == (
        "agent-loop",
        "tool-harness",
        "context-engineering",
        "memory-subagent",
    )


def test_agent_loop_demo_shows_completion_gate_blocking_early_finish():
    report = run_demo("agent-loop")

    assert report["demo"] == "agent-loop"
    assert report["summary"]["terminal_reason"] == "completion_gate_blocked"
    assert report["summary"]["completion_gate_block_count"] == 2
    assert "completion_candidate" in _event_names(report)
    assert "completion_gate_verdict" in _event_names(report)


def test_tool_harness_demo_shows_batching_order_and_permission_denial():
    report = run_demo("tool-harness")

    assert report["summary"]["observation_order"] == [
        "read-slow",
        "grep-fast",
        "write-denied",
    ]
    assert report["summary"]["permission_denied_count"] == 1
    assert "tool_orchestration_plan" in _event_names(report)
    assert "permission_decision" in _event_names(report)


def test_context_demo_keeps_full_history_and_projects_compact_model_view():
    report = run_demo("context-engineering")

    assert report["summary"]["source_message_count"] == 6
    assert report["summary"]["history_message_count"] < 6
    assert report["summary"]["projection_mode"] == "compact_checkpoint"
    assert report["summary"]["history_preserved"] is True
    assert "context_compaction_completed" in _event_names(report)
    assert "model_view_build" in _event_names(report)


def test_memory_subagent_demo_shows_resume_memory_injection_and_child_isolation():
    report = run_demo("memory-subagent")

    assert report["summary"]["uncertain_action_count"] == 1
    assert report["summary"]["uncertain_replay_allowed"] is False
    assert report["summary"]["session_memory_injected"] is True
    assert report["summary"]["long_term_memory_injected"] is True
    assert report["summary"]["subagent_status"] == "completed"
    assert "model_view_build" in _event_names(report)
    assert "subagent_requested" in _event_names(report)
    assert "subagent_completed" in _event_names(report)


def test_all_portfolio_demos_return_one_report_per_module():
    reports = run_all_demos()

    assert [report["demo"] for report in reports] == list(DEMO_NAMES)
