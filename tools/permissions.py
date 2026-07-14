"""Permission core for tool execution.

This module is an MVP policy router, not an OS sandbox. The model may propose
actions, but the harness decides whether a tool invocation is allowed to land.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from enum import Enum
from typing import Any


class PermissionAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PermissionContext:
    runtime_mode: str = "main_agent"
    ask_policy: str = "deny"


@dataclass(frozen=True)
class PermissionDecision:
    action: PermissionAction
    risk: RiskLevel
    reason: str
    policy_source: str
    input_summary: str

    def as_trace_payload(self, *, tool_name: str | None = None, effective_action: str | None = None) -> dict[str, Any]:
        payload = {
            "risk": self.risk.value,
            "action": self.action.value,
            "reason": self.reason,
            "policy_source": self.policy_source,
            "input_summary": self.input_summary,
        }
        if tool_name is not None:
            payload["tool_name"] = tool_name
        if effective_action is not None:
            payload["effective_action"] = effective_action
        return payload


class RiskClassifier:
    """Classify tool calls into permission decisions."""

    READ_ONLY_TOOLS = {"Read", "Grep", "Glob"}
    WRITE_TOOLS = {"Edit"}
    INTERNAL_STATE_TOOLS = {"TodoWrite"}
    RECURSIVE_OR_MUTATING_TOOLS = {"Bash", "Task"}
    _WRITE_PATH_KEYS = ("path", "file_path")
    _BASH_ALLOW_EXACT = {
        "pwd",
    }
    _BASH_ALLOW_PREFIXES = (
        ("sed", "-n"),
        ("git", "status"),
        ("git", "diff"),
        ("git", "log"),
    )
    _BASH_DENY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"(^|[;&|]\s*)sudo(?:\s|$)"), "sudo crosses the process privilege boundary"),
        (re.compile(r"(^|[;&|]\s*)rm(?:\s|$)"), "destructive delete command"),
        (
            re.compile(r"(^|[;&|]\s*)git\s+checkout(?:\s|$)"),
            "git checkout mutates working tree",
        ),
        (
            re.compile(r"(^|[;&|]\s*)git\s+reset(?:\s|$)"),
            "git reset mutates working tree/history",
        ),
        (
            re.compile(r"(^|[;&|]\s*)git\s+clean(?:\s|$)"),
            "git clean removes files",
        ),
        (
            re.compile(r"(^|[;&|]\s*)(?:sh|bash|zsh)\s+-c(?:\s|$)"),
            "nested shell execution bypasses command classification",
        ),
        (
            re.compile(r"(^|[;&|]\s*)(?:python|python3)\s+-c(?:\s|$)"),
            "inline Python execution bypasses command classification",
        ),
        (
            re.compile(r"\|\s*(?:sh|bash|zsh)(?:\s|$)"),
            "piping data into a shell executes unreviewed code",
        ),
        (
            re.compile(r"`|\$\("),
            "shell command substitution executes nested commands",
        ),
    )
    _BASH_ASK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"(^|[;&|]\s*)mv\b"), "mv may rewrite project files"),
        (re.compile(r"(^|[;&|]\s*)cp\b"), "cp may write new project files"),
        (re.compile(r">>?\s*\S"), "shell redirection may overwrite files"),
        (re.compile(r"\bnpm\s+install\b"), "package installation mutates the environment"),
        (re.compile(r"\bpip\s+install\b"), "package installation mutates the environment"),
        (re.compile(r"(^|[;&|]\s*)chmod\b"), "chmod mutates file permissions"),
        (re.compile(r"\bcurl\b.*\|\s*(?:sh|bash)\b"), "remote script execution requires review"),
    )

    def classify(
        self,
        tool_name: str,
        normalized_input: dict[str, Any] | None,
        context: PermissionContext | None = None,
    ) -> PermissionDecision:
        context = context or PermissionContext()
        payload = normalized_input if isinstance(normalized_input, dict) else {}
        summary = self._summarize_input(tool_name, payload)

        if tool_name in self.READ_ONLY_TOOLS:
            return PermissionDecision(
                action=PermissionAction.ALLOW,
                risk=RiskLevel.LOW,
                reason="read-only tool",
                policy_source="permission_core",
                input_summary=summary,
            )

        if tool_name in self.WRITE_TOOLS:
            decision = self._classify_write(tool_name, payload, context, summary)
            if decision is not None:
                return decision

        if tool_name in self.INTERNAL_STATE_TOOLS:
            return PermissionDecision(
                action=PermissionAction.ALLOW,
                risk=RiskLevel.LOW,
                reason="internal planning state tool",
                policy_source="permission_core",
                input_summary=summary,
            )

        if tool_name == "Bash":
            return self._classify_bash(payload, context, summary)

        if tool_name == "Task":
            if context.runtime_mode == "readonly_subagent":
                return PermissionDecision(
                    action=PermissionAction.DENY,
                    risk=RiskLevel.HIGH,
                    reason="readonly_subagent blocks recursive task execution",
                    policy_source="permission_core",
                    input_summary=summary,
                )
            return PermissionDecision(
                action=PermissionAction.ASK,
                risk=RiskLevel.HIGH,
                reason="task delegation crosses a trust boundary",
                policy_source="permission_core",
                input_summary=summary,
            )

        if tool_name == "Skill":
            return PermissionDecision(
                action=PermissionAction.ALLOW,
                risk=RiskLevel.LOW,
                reason="local skill tool",
                policy_source="permission_core",
                input_summary=summary,
            )

        return PermissionDecision(
            action=PermissionAction.DENY,
            risk=RiskLevel.UNKNOWN,
            reason=f"unknown tool '{tool_name}' fails closed",
            policy_source="permission_core",
            input_summary=summary,
        )

    def _classify_write(
        self,
        tool_name: str,
        payload: dict[str, Any],
        context: PermissionContext,
        summary: str,
    ) -> PermissionDecision | None:
        path_value = self._extract_first(payload, self._WRITE_PATH_KEYS)
        if context.runtime_mode == "readonly_subagent":
            return PermissionDecision(
                action=PermissionAction.DENY,
                risk=RiskLevel.HIGH,
                reason=f"readonly_subagent blocks {tool_name}",
                policy_source="permission_core",
                input_summary=summary,
            )
        if not isinstance(path_value, str) or not path_value.strip():
            return PermissionDecision(
                action=PermissionAction.DENY,
                risk=RiskLevel.UNKNOWN,
                reason=f"{tool_name} requires a target path",
                policy_source="permission_core",
                input_summary=summary,
            )
        return PermissionDecision(
            action=PermissionAction.ALLOW,
            risk=RiskLevel.MEDIUM,
            reason="file modification tool",
            policy_source="permission_core",
            input_summary=summary,
        )

    def _classify_bash(
        self,
        payload: dict[str, Any],
        context: PermissionContext,
        summary: str,
    ) -> PermissionDecision:
        command = payload.get("command")
        if context.runtime_mode == "readonly_subagent":
            return PermissionDecision(
                action=PermissionAction.DENY,
                risk=RiskLevel.HIGH,
                reason="readonly_subagent blocks Bash",
                policy_source="permission_core",
                input_summary=summary,
            )
        if not isinstance(command, str) or not command.strip():
            return PermissionDecision(
                action=PermissionAction.DENY,
                risk=RiskLevel.UNKNOWN,
                reason="Bash requires a non-empty command",
                policy_source="permission_core",
                input_summary=summary,
            )

        normalized = " ".join(command.strip().split())
        lowered = normalized.lower()

        for pattern, reason in self._BASH_DENY_PATTERNS:
            if pattern.search(lowered):
                return PermissionDecision(
                    action=PermissionAction.DENY,
                    risk=RiskLevel.HIGH,
                    reason=reason,
                    policy_source="permission_core",
                    input_summary=summary,
                )

        for pattern, reason in self._BASH_ASK_PATTERNS:
            if pattern.search(lowered):
                return PermissionDecision(
                    action=PermissionAction.ASK,
                    risk=RiskLevel.HIGH,
                    reason=reason,
                    policy_source="permission_core",
                    input_summary=summary,
                )

        if self._is_low_risk_bash(lowered):
            return PermissionDecision(
                action=PermissionAction.ALLOW,
                risk=RiskLevel.LOW,
                reason="low-risk read/search shell command",
                policy_source="permission_core",
                input_summary=summary,
            )

        return PermissionDecision(
            action=PermissionAction.ASK,
            risk=RiskLevel.MEDIUM,
            reason="unclassified shell command requires review in MVP policy",
            policy_source="permission_core",
            input_summary=summary,
        )

    def _is_low_risk_bash(self, command: str) -> bool:
        if re.search(r"[;&|<>]", command):
            return False
        try:
            parts = shlex.split(command)
        except ValueError:
            return False
        if not parts:
            return False
        if parts[0] in self._BASH_ALLOW_EXACT and len(parts) >= 1:
            return True
        for prefix in self._BASH_ALLOW_PREFIXES:
            if tuple(parts[: len(prefix)]) == prefix:
                return True
        return False

    def _extract_first(self, payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key in payload:
                return payload[key]
        return None

    def _summarize_input(self, tool_name: str, payload: dict[str, Any]) -> str:
        try:
            compact = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except TypeError:
            compact = repr(payload)
        if len(compact) > 240:
            compact = compact[:237] + "..."
        return f"{tool_name}({compact})"


__all__ = [
    "PermissionAction",
    "PermissionContext",
    "PermissionDecision",
    "RiskClassifier",
    "RiskLevel",
]
