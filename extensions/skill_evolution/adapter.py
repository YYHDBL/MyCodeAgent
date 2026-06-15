"""Trace → Rollout 适配器。

从 trace 内存事件缓冲聚合为 RolloutRecord，提取 Skill 归属、错误签名、用户反馈等。
"""

from __future__ import annotations

import hashlib
from extensions.skill_evolution.types import RolloutRecord


LONG_TERM_KEYWORDS = [
    "以后都", "下次遇到", "以后先做", "以后要", "以后再",
    "后续都", "每次都要", "从今往后", "一直要",
]
CORRECTION_KEYWORDS = [
    "不对", "错误", "不要用", "别再", "改正", "修复", "纠正",
    "应该是", "正确做法", "问题在于",
]


def trace_events_to_rollout(
    events: list[dict],
    session_id: str,
    run_id: int,
    processed_input: str,
) -> RolloutRecord:
    persistent_run_id = f"{session_id}:{run_id}"
    fingerprint = hashlib.sha256(processed_input.encode()).hexdigest()[:12]
    skills = extract_skills_invoked(events)
    attributing = resolve_attribution(skills)

    task_success = True
    hard_error = False
    human_intervention = False
    for e in events:
        if e.get("event") == "terminal":
            reason = (e.get("payload") or {}).get("reason", "")
            if reason not in ("completed", "completed_unverified"):
                task_success = False

    for e in events:
        payload = e.get("payload") or {}
        if e.get("event") == "terminal":
            reason = payload.get("reason", "")
            if reason in ("model_error", "tool_error_unrecoverable", "token_budget"):
                hard_error = True
        if e.get("event") == "tool_result":
            if _is_human_intervention(e, events):
                human_intervention = True

    fb = detect_user_feedback(events)
    error_sigs = _collect_error_signatures(events)

    summary_parts: list[str] = []
    if task_success:
        summary_parts.append("success")
    if hard_error:
        summary_parts.append("hard_error")
    if human_intervention:
        summary_parts.append("human_intervention")
    if skills:
        summary_parts.append(f"skills:{','.join(skills)}")

    return RolloutRecord(
        trace_id=persistent_run_id,
        persistent_run_id=persistent_run_id,
        input_fingerprint=fingerprint,
        skills_invoked=skills,
        attributing_skill=attributing,
        skill_version="v0",
        task_success=task_success,
        hard_error=hard_error,
        human_intervention=human_intervention,
        user_feedback_text=fb.get("raw_text"),
        is_explicit_correction=fb.get("is_explicit_correction", False),
        is_long_term_instruction=fb.get("is_long_term", False),
        error_signatures=error_sigs,
        summary=" ".join(summary_parts) or "unknown",
    )


def extract_skills_invoked(events: list[dict]) -> list[str]:
    names: set[str] = set()
    for e in events:
        if e.get("event") == "tool_call":
            args = (e.get("payload") or {}).get("args", {})
            tool = (e.get("payload") or {}).get("tool", "")
            if tool == "Skill" and args.get("name"):
                names.add(args["name"])
    return sorted(names)


def resolve_attribution(skills_invoked: list[str]) -> str | None:
    if len(skills_invoked) == 1:
        return skills_invoked[0]
    return None


def detect_user_feedback(events: list[dict]) -> dict:
    raw_text: str | None = None
    is_long_term = False
    is_explicit = False

    for e in events:
        payload = e.get("payload") or {}
        if e.get("event") == "user_input":
            raw_text = (payload.get("text") or payload.get("processed") or "")
            if raw_text:
                for kw in LONG_TERM_KEYWORDS:
                    if kw in raw_text:
                        is_long_term = True
                        break
                for kw in CORRECTION_KEYWORDS:
                    if kw in raw_text:
                        is_explicit = True
                        break

    return {
        "raw_text": raw_text,
        "is_long_term": is_long_term,
        "is_explicit_correction": is_explicit,
    }


def detect_error_signature(rollout: RolloutRecord, proposal: Proposal) -> bool:
    """检查 Proposal 的目标错误是否在本次 run 中复现。"""
    from extensions.skill_evolution.types import Proposal
    return proposal.error_signature in rollout.error_signatures


# ------------------------------------------------------------------
# 内部
# ------------------------------------------------------------------

def _is_human_intervention(tool_result_event: dict, all_events: list[dict]) -> bool:
    payload = tool_result_event.get("payload") or {}
    result = payload.get("result", {})
    if isinstance(result, dict):
        tool = result.get("tool") or payload.get("tool", "")
        if tool == "AskUser":
            text = result.get("text", "")
            if text and text.strip():
                return True
    return False


def _collect_error_signatures(events: list[dict]) -> list[str]:
    sigs: list[str] = []
    for e in events:
        if e.get("event") == "error":
            payload = e.get("payload") or {}
            msg = str(payload.get("message", payload))
            sigs.append(msg[:80])
    if not sigs:
        # 从 terminal 提取
        for e in events:
            if e.get("event") == "terminal":
                reason = (e.get("payload") or {}).get("reason", "")
                if reason and reason not in ("completed", "completed_unverified"):
                    sigs.append(reason)
    return sigs


__all__ = [
    "trace_events_to_rollout",
    "extract_skills_invoked",
    "resolve_attribution",
    "detect_user_feedback",
    "detect_error_signature",
]
