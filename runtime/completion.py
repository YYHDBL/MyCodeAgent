"""Completion gate and verification evidence for the runtime harness."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol


VERIFY_IF_POSSIBLE_PATTERNS = (
    "if possible",
    "if you can",
    "when possible",
    "如果可以",
    "尽量",
)

VERIFY_REQUIREMENT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bpytest\b", "tests"),
    (r"\brun\s+(the\s+)?tests?\b", "tests"),
    (r"\btest\s+suite\b", "tests"),
    (r"\bunit\s+tests?\b", "tests"),
    (r"\blint\b", "lint"),
    (r"\btypecheck\b", "typecheck"),
    (r"\bbuild\b", "build"),
)

VERIFY_COMMAND_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bpytest\b", "tests"),
    (r"\btest\b", "tests"),
    (r"\blint\b", "lint"),
    (r"\btypecheck\b", "typecheck"),
    (r"\bbuild\b", "build"),
)

MUTATING_TOOL_NAMES = {"Write", "Edit", "MultiEdit"}


class CompletionGateVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class CompletionCandidate:
    final_text: str
    step: int
    response_meta: dict[str, Any]
    last_tool_name: str | None = None
    last_tool_status: str | None = None

    def to_trace_payload(self) -> dict[str, Any]:
        return {
            "final_text": self.final_text,
            "final_length": len(self.final_text),
            "step": self.step,
            "response_meta": dict(self.response_meta),
            "last_tool_name": self.last_tool_name,
            "last_tool_status": self.last_tool_status,
        }


@dataclass(frozen=True)
class CompletionRequirements:
    requires_verification: bool
    verification_kinds: tuple[str, ...] = ()
    allow_unverified: bool = False
    has_incomplete_todos: bool = False
    incomplete_todos: tuple[str, ...] = ()
    explicit_user_constraints: tuple[str, ...] = ()

    def to_trace_payload(self) -> dict[str, Any]:
        return {
            "requires_verification": self.requires_verification,
            "verification_kinds": list(self.verification_kinds),
            "allow_unverified": self.allow_unverified,
            "has_incomplete_todos": self.has_incomplete_todos,
            "incomplete_todos": list(self.incomplete_todos),
            "explicit_user_constraints": list(self.explicit_user_constraints),
        }


@dataclass(frozen=True)
class VerificationEvidence:
    requirement_id: str
    tool_name: str
    command: str | None
    status: str
    step: int
    valid: bool
    invalid_reason: str | None = None

    def to_trace_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompletionGateResult:
    verdict: CompletionGateVerdict
    reasons: tuple[str, ...] = ()
    blocking_feedback: str | None = None
    passed_evidence: tuple[VerificationEvidence, ...] = ()

    def to_trace_payload(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "reasons": list(self.reasons),
            "blocking_feedback": self.blocking_feedback,
            "passed_evidence": [e.to_trace_payload() for e in self.passed_evidence],
        }


class CompletionVerifier(Protocol):
    def evaluate(
        self,
        candidate: CompletionCandidate,
        requirements: CompletionRequirements,
        evidence: list[VerificationEvidence],
        history_messages: list[Any],
    ) -> CompletionGateResult: ...


class DeterministicCompletionVerifier:
    """Phase 2 default verifier; deterministic only, no second agent."""

    def evaluate(
        self,
        candidate: CompletionCandidate,
        requirements: CompletionRequirements,
        evidence: list[VerificationEvidence],
        history_messages: list[Any],
    ) -> CompletionGateResult:
        reasons: list[str] = []
        passed_evidence: list[VerificationEvidence] = []
        pending_unverified = False

        if requirements.has_incomplete_todos:
            reasons.append("incomplete_todos")

        if requirements.requires_verification:
            for kind in requirements.verification_kinds:
                requirement_id = f"verification:{kind}"
                relevant = [item for item in evidence if item.requirement_id == requirement_id]
                valid = [item for item in relevant if item.valid and item.status == "success"]
                if valid:
                    passed_evidence.extend(valid)
                    continue
                if relevant and not valid:
                    reasons.append(f"verification_invalid:{kind}")
                    continue
                if requirements.allow_unverified:
                    pending_unverified = True
                else:
                    reasons.append(f"missing_verification_evidence:{kind}")

        if reasons:
            return CompletionGateResult(
                verdict=CompletionGateVerdict.FAIL,
                reasons=tuple(reasons),
                blocking_feedback=_build_blocking_feedback(requirements, reasons),
                passed_evidence=tuple(passed_evidence),
            )

        if pending_unverified:
            return CompletionGateResult(
                verdict=CompletionGateVerdict.UNVERIFIED,
                reasons=("verification_unverified",),
                passed_evidence=tuple(passed_evidence),
            )

        return CompletionGateResult(
            verdict=CompletionGateVerdict.PASS,
            passed_evidence=tuple(passed_evidence),
        )


def build_completion_candidate(
    *,
    final_text: str,
    step: int,
    response_meta: dict[str, Any] | None,
    history_messages: list[Any],
) -> CompletionCandidate:
    last_tool_name = None
    last_tool_status = None
    for message in reversed(history_messages):
        if getattr(message, "role", None) != "tool":
            continue
        metadata = getattr(message, "metadata", {}) or {}
        last_tool_name = metadata.get("tool_name")
        parsed = _parse_tool_payload(getattr(message, "content", ""))
        if isinstance(parsed, dict):
            last_tool_status = parsed.get("status")
        break
    return CompletionCandidate(
        final_text=final_text,
        step=step,
        response_meta=dict(response_meta or {}),
        last_tool_name=last_tool_name,
        last_tool_status=last_tool_status,
    )


def infer_completion_requirements(
    *,
    user_input: str,
    history_messages: list[Any],
) -> CompletionRequirements:
    normalized = (user_input or "").lower()
    explicit_constraints: list[str] = []
    verification_kinds: list[str] = []
    for pattern, kind in VERIFY_REQUIREMENT_PATTERNS:
        if re.search(pattern, normalized):
            if kind not in verification_kinds:
                verification_kinds.append(kind)
                explicit_constraints.append(kind)

    latest_todos = _extract_latest_todos(history_messages)
    incomplete_todos = tuple(
        item.get("content", "")
        for item in latest_todos
        if item.get("status") in {"pending", "in_progress"}
    )

    return CompletionRequirements(
        requires_verification=bool(verification_kinds),
        verification_kinds=tuple(verification_kinds),
        allow_unverified=bool(verification_kinds)
        and any(pattern in normalized for pattern in VERIFY_IF_POSSIBLE_PATTERNS),
        has_incomplete_todos=bool(incomplete_todos),
        incomplete_todos=incomplete_todos,
        explicit_user_constraints=tuple(explicit_constraints),
    )


def collect_verification_evidence(history_messages: list[Any]) -> list[VerificationEvidence]:
    evidences: list[VerificationEvidence] = []
    latest_mutation_step = 0

    for message in history_messages:
        if getattr(message, "role", None) != "tool":
            continue
        metadata = getattr(message, "metadata", {}) or {}
        tool_name = str(metadata.get("tool_name") or "")
        step = int(metadata.get("step") or 0)
        parsed = _parse_tool_payload(getattr(message, "content", ""))
        if not isinstance(parsed, dict):
            continue
        if tool_name in MUTATING_TOOL_NAMES and parsed.get("status") in {"success", "partial"}:
            latest_mutation_step = max(latest_mutation_step, step)
        if tool_name != "Bash":
            continue
        params_input = ((parsed.get("context") or {}).get("params_input") or {})
        if not isinstance(params_input, dict):
            continue
        command = params_input.get("command")
        if not isinstance(command, str):
            continue
        evidence_kind = _classify_verification_command(command)
        if evidence_kind is None:
            continue
        evidences.append(
            VerificationEvidence(
                requirement_id=f"verification:{evidence_kind}",
                tool_name=tool_name,
                command=command,
                status=str(parsed.get("status") or "unknown"),
                step=step,
                valid=str(parsed.get("status") or "") == "success",
            )
        )

    if latest_mutation_step <= 0:
        return evidences

    invalidated: list[VerificationEvidence] = []
    for evidence in evidences:
        if evidence.step < latest_mutation_step:
            invalidated.append(
                VerificationEvidence(
                    requirement_id=evidence.requirement_id,
                    tool_name=evidence.tool_name,
                    command=evidence.command,
                    status=evidence.status,
                    step=evidence.step,
                    valid=False,
                    invalid_reason=f"modified_after_verification:{latest_mutation_step}",
                )
            )
        else:
            invalidated.append(evidence)
    return invalidated


def _parse_tool_payload(raw: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _extract_latest_todos(history_messages: list[Any]) -> list[dict[str, Any]]:
    for message in reversed(history_messages):
        if getattr(message, "role", None) != "tool":
            continue
        metadata = getattr(message, "metadata", {}) or {}
        if metadata.get("tool_name") != "TodoWrite":
            continue
        parsed = _parse_tool_payload(getattr(message, "content", ""))
        if not isinstance(parsed, dict):
            continue
        data = parsed.get("data") or {}
        todos = data.get("todos") if isinstance(data, dict) else None
        if isinstance(todos, list):
            return [item for item in todos if isinstance(item, dict)]
    return []


def _classify_verification_command(command: str) -> str | None:
    normalized = command.lower()
    for pattern, kind in VERIFY_COMMAND_PATTERNS:
        if re.search(pattern, normalized):
            return kind
    return None


def _build_blocking_feedback(requirements: CompletionRequirements, reasons: list[str]) -> str:
    lines = ["<system-reminder>Completion blocked by runtime gate.</system-reminder>"]
    for reason in reasons:
        if reason == "incomplete_todos":
            if requirements.incomplete_todos:
                lines.append("Incomplete todos remain: " + "; ".join(requirements.incomplete_todos))
            else:
                lines.append("Incomplete todos remain.")
        elif reason.startswith("missing_verification_evidence:"):
            lines.append(
                f"Missing verification evidence for {reason.split(':', 1)[1]}. Run the required verification tool."
            )
        elif reason.startswith("verification_invalid:"):
            lines.append(
                f"Verification evidence for {reason.split(':', 1)[1]} is missing, failed, or stale."
            )
        else:
            lines.append(reason)
    return "\n".join(lines)


__all__ = [
    "CompletionCandidate",
    "CompletionGateResult",
    "CompletionGateVerdict",
    "CompletionRequirements",
    "CompletionVerifier",
    "DeterministicCompletionVerifier",
    "VerificationEvidence",
    "build_completion_candidate",
    "collect_verification_evidence",
    "infer_completion_requirements",
]
