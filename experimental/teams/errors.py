"""Shared errors for team engine services."""

from __future__ import annotations


class TeamEngineError(Exception):
    """Typed error carrying a stable code for manager-level mapping."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code or "INTERNAL_ERROR")
        self.message = str(message or "")

