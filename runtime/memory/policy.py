"""Safety checks for long-term memory entries."""

from __future__ import annotations

import re


_THREAT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"ignore\s+(?:(?:all|any)\s+)?(?:previous|above|prior)\s+instructions",
            re.IGNORECASE,
        ),
        "prompt injection",
    ),
    (re.compile(r"disregard\s+(?:your|all|any)\s+(?:instructions|rules|guidelines)", re.IGNORECASE), "instruction bypass"),
    (re.compile(r"system\s+prompt\s+override", re.IGNORECASE), "system prompt override"),
    (re.compile(r"you\s+are\s+now\s+", re.IGNORECASE), "role hijack"),
    (
        re.compile(
            r"(?:curl|wget)\s+[^\n]*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)",
            re.IGNORECASE,
        ),
        "secret exfiltration",
    ),
    (
        re.compile(
            r"cat\s+[^\n]*(?:\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc)",
            re.IGNORECASE,
        ),
        "secret file access",
    ),
)

_INVISIBLE_UNICODE = {
    "\u200b",
    "\u200c",
    "\u200d",
    "\u2060",
    "\ufeff",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
}


def validate_memory_entry(content: str, *, max_entry_chars: int) -> tuple[str | None, str | None]:
    """Return (reason, message) when content must be rejected."""

    normalized = str(content or "").strip()
    if not normalized:
        return "empty_content", "Memory entry content cannot be empty."

    if len(normalized) > max_entry_chars:
        return (
            "entry_too_long",
            f"Memory entry exceeds the single-entry limit of {max_entry_chars} characters.",
        )

    for char in _INVISIBLE_UNICODE:
        if char in normalized:
            return (
                "security_rejected",
                f"Memory entry contains invisible unicode control U+{ord(char):04X}.",
            )

    for pattern, label in _THREAT_PATTERNS:
        if pattern.search(normalized):
            return (
                "security_rejected",
                f"Memory entry matched blocked pattern: {label}.",
            )

    return None, None


__all__ = ["validate_memory_entry"]
