"""Trace sanitizer for removing sensitive data from logs."""

from __future__ import annotations

import re
from typing import Any, Dict


class TraceSanitizer:
    """Sanitize payloads before writing trace logs."""

    SENSITIVE_KEYS = {
        "api_key",
        "apikey",
        "api-key",
        "secret",
        "secret_key",
        "secretkey",
        "token",
        "access_token",
        "refresh_token",
        "password",
        "passwd",
        "pwd",
        "session_id",
        "sessionid",
        "tool_call_id",
        "call_id",
        "authorization",
        "auth",
    }

    PATTERNS = [
        (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "sk-***"),
        (re.compile(r"Bearer\\s+[a-zA-Z0-9._\\-+/=]{20,}"), "Bearer ***"),
    ]

    def __init__(self, enable: bool = True):
        self.enable = bool(enable)

    def sanitize(self, data: Any) -> Any:
        if not self.enable:
            return data
        if isinstance(data, str):
            return self._sanitize_string(data)
        if isinstance(data, dict):
            return self._sanitize_dict(data)
        if isinstance(data, list):
            return [self.sanitize(item) for item in data]
        return data

    def _sanitize_string(self, text: str) -> str:
        result = text
        for pattern, repl in self.PATTERNS:
            result = pattern.sub(repl, result)
        result = re.sub(r"/Users/[^/]+", "/Users/***", result)
        result = re.sub(r"/home/[^/]+", "/home/***", result)
        return result

    def _sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in data.items():
            key_lower = str(key).lower()
            if key_lower in self.SENSITIVE_KEYS:
                result[key] = "***"
                continue
            if "path" in key_lower and isinstance(value, str):
                result[key] = self._sanitize_string(value)
                continue
            result[key] = self.sanitize(value)
        return result
