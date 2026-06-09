import json


def _jsonl_event(name, step, payload, *, session_id="s-1"):
    return {
        "ts": "2026-06-09T00:00:00Z",
        "session_id": session_id,
        "step": step,
        "event": name,
        "payload": payload,
    }


def test_summarize_trace_events_exposes_metrics_schema():
    from runtime.evals import summarize_trace_events

    events = [
        ("run_start", 0, {"run_id": 7, "input": "fix bug", "processed": "fix bug"}),
        (
            "prompt_assembly",
            1,
            {
                "constitution_fingerprint": "constitution-1",
                "tool_contracts_fingerprint": "tools-1",
                "project_rules_fingerprint": "rules-1",
                "runtime_signals_fingerprint": "signals-1",
                "system_fingerprint": "prompt-1",
            },
        ),
        ("tool_schema", 1, {"fingerprint": "schema-1", "tool_count": 3, "changed": False}),
        (
            "model_output",
            1,
            {
                "raw": "",
                "usage": {"total_tokens": 10},
                "meta": {},
                "tool_calls": [{"id": "call_1", "name": "Read", "arguments": {"path": "README.md"}}],
            },
        ),
        ("tool_call", 1, {"tool": "Read", "args": {"path": "README.md"}, "tool_call_id": "call_1"}),
        ("tool_result", 1, {"tool": "Read", "result": {"status": "success", "data": {}}}),
        ("context_compaction_completed", 1, {"checkpoint_id": "cp-1"}),
        (
            "model_output",
            2,
            {
                "raw": "done",
                "usage": {"total_tokens": 20},
                "meta": {},
                "tool_calls": [],
            },
        ),
        (
            "completion_gate_verdict",
            2,
            {"verdict": "fail", "reasons": ["missing_verification_evidence:tests"], "blocking_feedback": "run tests"},
        ),
        (
            "permission_decision",
            2,
            {
                "tool_name": "Write",
                "risk": "high",
                "action": "deny",
                "effective_action": "deny",
                "reason": "readonly_subagent blocks writes",
                "policy_source": "permission_core",
                "input_summary": 'Write({"path":"a.txt"})',
            },
        ),
        (
            "tool_result",
            2,
            {
                "tool": "Write",
                "result": {"status": "error", "error": {"code": "PERMISSION_DENIED", "message": "blocked"}},
            },
        ),
        ("model_recovery_attempted", 2, {"kind": "empty_response", "retry_count": 1, "retry_limit": 1}),
        ("state_transition", 2, {"reason": "stop_hook_blocking", "message_count": 4, "details": {}}),
        ("terminal", 2, {"reason": "completion_gate_blocked", "details": {}}),
    ]

    summary = summarize_trace_events(events)

    assert summary["run_id"] == 7
    assert summary["terminal_reason"] == "completion_gate_blocked"
    assert summary["step_count"] == 2
    assert summary["model_call_count"] == 2
    assert summary["tool_call_count"] == 1
    assert summary["tool_error_count"] == 1
    assert summary["permission_denied_count"] == 1
    assert summary["completion_gate_block_count"] == 1
    assert summary["model_recovery_count"] == 1
    assert summary["context_compaction_count"] == 1
    assert summary["prompt_fingerprint"] == "prompt-1"
    assert summary["tool_schema_fingerprint"] == "schema-1"
    assert summary["total_tokens"] == 30
    assert summary["failure_stage"] == "completion_gate"


def test_summarize_trace_jsonl_file_matches_event_summary(tmp_path):
    from runtime.evals import summarize_trace_events, summarize_trace_file

    event_tuples = [
        ("run_start", 0, {"run_id": 9, "input": "hello", "processed": "hello"}),
        ("model_output", 1, {"raw": "answer", "usage": {"total_tokens": 12}, "meta": {}, "tool_calls": []}),
        ("terminal", 1, {"reason": "completed", "details": {}}),
    ]
    jsonl_path = tmp_path / "trace.jsonl"
    jsonl_path.write_text(
        "\n".join(
            json.dumps(_jsonl_event(name, step, payload), ensure_ascii=False)
            for name, step, payload in event_tuples
        )
        + "\n",
        encoding="utf-8",
    )

    from_events = summarize_trace_events(event_tuples)
    from_file = summarize_trace_file(jsonl_path)

    assert from_file["run_id"] == from_events["run_id"] == 9
    assert from_file["model_call_count"] == from_events["model_call_count"] == 1
    assert from_file["total_tokens"] == from_events["total_tokens"] == 12


def test_classify_failure_stage_distinguishes_context_model_tool_permission_and_unknown():
    from runtime.evals import classify_failure_stage

    assert classify_failure_stage(
        terminal_reason="model_error",
        permission_denied_count=0,
        tool_error_count=0,
        completion_gate_block_count=0,
        event_flags={"prompt_too_long": True},
    ) == "context"
    assert classify_failure_stage(
        terminal_reason="empty_response_failed",
        permission_denied_count=0,
        tool_error_count=0,
        completion_gate_block_count=0,
        event_flags={},
    ) == "model"
    assert classify_failure_stage(
        terminal_reason="tool_error_unrecoverable",
        permission_denied_count=0,
        tool_error_count=1,
        completion_gate_block_count=0,
        event_flags={},
    ) == "tool"
    assert classify_failure_stage(
        terminal_reason="tool_error_unrecoverable",
        permission_denied_count=1,
        tool_error_count=1,
        completion_gate_block_count=0,
        event_flags={},
    ) == "permission"
    assert classify_failure_stage(
        terminal_reason="completion_gate_blocked",
        permission_denied_count=0,
        tool_error_count=0,
        completion_gate_block_count=2,
        event_flags={},
    ) == "completion_gate"
    assert classify_failure_stage(
        terminal_reason="max_steps",
        permission_denied_count=0,
        tool_error_count=0,
        completion_gate_block_count=0,
        event_flags={},
    ) == "max_steps"
    assert classify_failure_stage(
        terminal_reason="completed",
        permission_denied_count=0,
        tool_error_count=0,
        completion_gate_block_count=0,
        event_flags={},
    ) == "unknown"
