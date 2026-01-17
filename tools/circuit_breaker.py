"""Lightweight circuit breaker for tools."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ToolFailureRecord:
    tool_name: str
    failure_count: int = 0
    last_failure_time: Optional[float] = None
    last_error: Optional[str] = None
    circuit_state: CircuitState = CircuitState.CLOSED


class CircuitBreaker:
    """Per-tool failure tracker with simple open/half-open recovery."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 300):
        self.failure_threshold = max(1, int(failure_threshold))
        self.recovery_timeout = max(1, int(recovery_timeout))
        self._records: Dict[str, ToolFailureRecord] = {}

    def record_success(self, tool_name: str) -> None:
        record = self._records.get(tool_name)
        if record is None:
            self._records[tool_name] = ToolFailureRecord(tool_name=tool_name)
            return
        record.failure_count = 0
        record.last_failure_time = None
        record.last_error = None
        record.circuit_state = CircuitState.CLOSED

    def record_failure(self, tool_name: str, error: str | None = None) -> None:
        record = self._records.get(tool_name)
        if record is None:
            record = ToolFailureRecord(tool_name=tool_name)
            self._records[tool_name] = record
        record.failure_count += 1
        record.last_failure_time = time.monotonic()
        record.last_error = error or record.last_error
        if record.failure_count >= self.failure_threshold:
            record.circuit_state = CircuitState.OPEN

    def is_available(self, tool_name: str) -> bool:
        record = self._records.get(tool_name)
        if record is None:
            return True
        if record.circuit_state == CircuitState.OPEN:
            if record.last_failure_time is None:
                return False
            elapsed = time.monotonic() - record.last_failure_time
            if elapsed >= self.recovery_timeout:
                record.circuit_state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def get_disabled_tools(self) -> List[str]:
        disabled: list[str] = []
        for name in self._records:
            if not self.is_available(name):
                disabled.append(name)
        return disabled

    def get_status(self, tool_name: str) -> Optional[ToolFailureRecord]:
        return self._records.get(tool_name)
