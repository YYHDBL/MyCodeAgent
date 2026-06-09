"""Lightweight eval summary helpers for harness observability."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def _iter_normalized_events(events: Iterable[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in events:
        if isinstance(item, dict):
            normalized.append(
                {
                    "session_id": item.get("session_id"),
                    "step": int(item.get("step", 0) or 0),
                    "event": item.get("event"),
                    "payload": item.get("payload", {}) or {},
                }
            )
            continue
        if isinstance(item, (list, tuple)) and len(item) == 3:
            name, step, payload = item
            normalized.append(
                {
                    "session_id": None,
                    "step": int(step or 0),
                    "event": name,
                    "payload": payload or {},
                }
            )
    return normalized


def _split_normalized_runs(events: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    runs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] | None = None

    for event in events:
        name = event.get("event")
        if name == "run_start":
            if current:
                runs.append(current)
            current = [event]
            continue
        if current is None:
            continue
        current.append(event)
        if name == "run_end":
            runs.append(current)
            current = None

    if current:
        runs.append(current)
    if runs:
        return runs
    return [events] if events else []


def classify_failure_stage(
    *,
    terminal_reason: str | None,
    permission_denied_count: int,
    tool_error_count: int,
    completion_gate_block_count: int,
    event_flags: dict[str, bool],
) -> str:
    if terminal_reason in {"completed", "completed_unverified"}:
        return "unknown"
    if terminal_reason == "completion_gate_blocked" or completion_gate_block_count > 0:
        return "completion_gate"
    if terminal_reason == "max_steps":
        return "max_steps"
    if permission_denied_count > 0 and terminal_reason in {"tool_error_unrecoverable", "model_error"}:
        return "permission"
    if event_flags.get("prompt_too_long"):
        return "context"
    if terminal_reason in {"empty_response_failed", "model_error"} or event_flags.get("model_error"):
        return "model"
    if terminal_reason == "tool_error_unrecoverable" or tool_error_count > 0 and event_flags.get("tool_execution_error"):
        return "tool"
    return "unknown"


def _summarize_normalized_events(normalized: list[dict[str, Any]]) -> dict[str, Any]:
    run_id = None
    session_id = None
    terminal_reason = None
    step_count = 0
    model_call_count = 0
    tool_call_count = 0
    tool_error_count = 0
    permission_denied_event_count = 0
    permission_denied_tool_error_count = 0
    completion_gate_block_count = 0
    model_recovery_count = 0
    context_compaction_count = 0
    prompt_fingerprint = None
    tool_schema_fingerprint = None
    total_tokens = 0
    subagent_invocation_count = 0
    child_tool_count = 0
    child_token_usage = 0
    child_failure_count = 0
    verification_verdict = None
    projection_modes: list[str] = []
    event_flags = {
        "prompt_too_long": False,
        "model_error": False,
        "tool_execution_error": False,
    }

    for event in normalized:
        name = str(event.get("event") or "")
        step = int(event.get("step", 0) or 0)
        payload = event.get("payload", {}) or {}
        session_id = session_id or event.get("session_id")
        step_count = max(step_count, step)

        if name == "run_start":
            run_id = payload.get("run_id", run_id)
        elif name == "prompt_assembly":
            prompt_fingerprint = payload.get("system_fingerprint") or prompt_fingerprint
        elif name == "tool_schema":
            tool_schema_fingerprint = payload.get("fingerprint") or tool_schema_fingerprint
        elif name == "context_build":
            projection_mode = payload.get("projection_mode")
            if projection_mode:
                projection_modes.append(str(projection_mode))
        elif name == "model_output":
            model_call_count += 1
            usage = payload.get("usage") or {}
            if usage.get("total_tokens") is not None:
                total_tokens += int(usage["total_tokens"])
        elif name == "model_error_classified":
            event_flags["model_error"] = True
            if payload.get("kind") == "prompt_too_long":
                event_flags["prompt_too_long"] = True
            if payload.get("stage") == "model_invoke":
                model_call_count += 1
        elif name == "model_recovery_attempted":
            model_recovery_count += 1
        elif name == "model_recovery_failed":
            if payload.get("kind") == "prompt_too_long":
                event_flags["prompt_too_long"] = True
        elif name == "tool_call":
            tool_call_count += 1
        elif name == "tool_result":
            result = payload.get("result") or {}
            if isinstance(result, dict) and result.get("status") == "error":
                tool_error_count += 1
                error = result.get("error") or {}
                if isinstance(error, dict) and error.get("code") == "PERMISSION_DENIED":
                    permission_denied_tool_error_count += 1
        elif name == "permission_decision":
            action = payload.get("effective_action") or payload.get("action")
            if action == "deny":
                permission_denied_event_count += 1
        elif name == "completion_gate_verdict":
            if payload.get("verdict") == "fail":
                pass
        elif name == "state_transition":
            if payload.get("reason") == "stop_hook_blocking":
                completion_gate_block_count += 1
        elif name == "context_compaction_completed":
            context_compaction_count += 1
        elif name == "error":
            if payload.get("stage") == "tool_execution":
                event_flags["tool_execution_error"] = True
        elif name == "terminal":
            terminal_reason = payload.get("reason") or terminal_reason
        elif name == "session_summary":
            total_usage = payload.get("total_usage") or {}
            if total_usage.get("total_tokens") is not None:
                total_tokens = int(total_usage["total_tokens"])
        elif name == "subagent_requested":
            subagent_invocation_count += 1
        elif name == "subagent_completed":
            tool_usage = payload.get("tool_usage") or {}
            if isinstance(tool_usage, dict):
                child_tool_count += sum(int(value or 0) for value in tool_usage.values())
            child_token_usage += int(payload.get("token_usage") or 0)
            if payload.get("profile") == "verification":
                verification_verdict = payload.get("verdict") or verification_verdict
        elif name == "subagent_failed":
            child_failure_count += 1

    permission_denied_count = (
        permission_denied_event_count
        if permission_denied_event_count > 0
        else permission_denied_tool_error_count
    )

    failure_stage = classify_failure_stage(
        terminal_reason=terminal_reason,
        permission_denied_count=permission_denied_count,
        tool_error_count=tool_error_count,
        completion_gate_block_count=completion_gate_block_count,
        event_flags=event_flags,
    )

    return {
        "run_id": run_id,
        "session_id": session_id,
        "terminal_reason": terminal_reason,
        "failure_stage": failure_stage,
        "step_count": step_count,
        "model_call_count": model_call_count,
        "tool_call_count": tool_call_count,
        "tool_error_count": tool_error_count,
        "permission_denied_count": permission_denied_count,
        "completion_gate_block_count": completion_gate_block_count,
        "model_recovery_count": model_recovery_count,
        "context_compaction_count": context_compaction_count,
        "prompt_fingerprint": prompt_fingerprint,
        "tool_schema_fingerprint": tool_schema_fingerprint,
        "total_tokens": total_tokens,
        "projection_modes": projection_modes,
        "subagent_invocation_count": subagent_invocation_count,
        "child_tool_count": child_tool_count,
        "child_token_usage": child_token_usage,
        "child_failure_count": child_failure_count,
        "verification_verdict": verification_verdict,
    }


def summarize_trace_runs(events: Iterable[Any]) -> list[dict[str, Any]]:
    normalized = _iter_normalized_events(events)
    return [
        _summarize_normalized_events(run_events)
        for run_events in _split_normalized_runs(normalized)
    ]


def summarize_trace_events(events: Iterable[Any]) -> dict[str, Any]:
    runs = summarize_trace_runs(events)
    if runs:
        return runs[-1]
    return _summarize_normalized_events([])


def _load_trace_file_events(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            events.append(json.loads(stripped))
    return events


def summarize_trace_file(path: str | Path) -> dict[str, Any]:
    return summarize_trace_events(_load_trace_file_events(path))


def summarize_trace_file_runs(path: str | Path) -> list[dict[str, Any]]:
    return summarize_trace_runs(_load_trace_file_events(path))


def summarize_trace(source: Iterable[Any] | str | Path) -> dict[str, Any]:
    if isinstance(source, (str, Path)):
        return summarize_trace_file(source)
    return summarize_trace_events(source)


__all__ = [
    "classify_failure_stage",
    "summarize_trace",
    "summarize_trace_events",
    "summarize_trace_file",
    "summarize_trace_file_runs",
    "summarize_trace_runs",
]
