"""Append runtime diagnostics as JSONL facts."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.env import load_env
from extensions.tracing.sanitizer import TraceSanitizer


load_env()

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class TraceLogger:
    """Record one session's diagnostic events as an append-only JSONL file."""

    def __init__(self, session_id: str, trace_dir: Path, enabled: bool = True):
        self.session_id = session_id
        self.trace_dir = Path(trace_dir)
        self.enabled = enabled
        self._current_run_events: list[dict[str, Any]] = []
        self._total_steps = 0
        self._tools_used = 0
        self._total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        self._lock = threading.Lock()
        self._filepath: Path | None = None
        self._file_handle = None
        self._system_messages_logged = False
        self._sanitizer = TraceSanitizer(
            enable=os.environ.get("TRACE_SANITIZE", "true").lower() == "true"
        )
        if self.enabled:
            self._init_file()

    def _init_file(self) -> None:
        try:
            self.trace_dir.mkdir(parents=True, exist_ok=True)
            self._filepath = self.trace_dir / f"trace-{self.session_id}.jsonl"
            self._file_handle = self._filepath.open("a", encoding="utf-8")
        except Exception as error:
            logger.warning("TraceLogger init failed: %s", error)
            self.enabled = False

    def log_event(self, event: str, payload: dict[str, Any], step: int = 0) -> None:
        """Sanitize, retain, and append one diagnostic event."""

        if not self.enabled:
            return
        try:
            event_obj = {
                "ts": _utc_now().isoformat().replace("+00:00", "Z"),
                "session_id": self.session_id,
                "step": step,
                "event": event,
                "payload": self._sanitizer.sanitize(payload),
            }
            self._current_run_events.append(event_obj)
            self._write_line(event_obj)
            self._update_stats(event, payload, step)
        except Exception as error:
            logger.warning("TraceLogger log_event failed: %s", error)

    def log_system_messages(self, messages: list[dict[str, Any]]) -> None:
        """Record initial system messages exactly once."""

        if not self.enabled or self._system_messages_logged:
            return
        self._system_messages_logged = True
        self.log_event("system_messages", {"messages": messages})

    def finalize(self) -> None:
        """Append the session summary and close the JSONL stream."""

        if not self.enabled:
            return
        try:
            self.log_event(
                "session_summary",
                {
                    "steps": self._total_steps,
                    "tools_used": self._tools_used,
                    "total_usage": self._total_usage,
                },
            )
            if self._file_handle:
                self._file_handle.close()
                self._file_handle = None
            logger.info("Trace saved to %s", self._filepath)
        except Exception as error:
            logger.warning("TraceLogger finalize failed: %s", error)

    def _write_line(self, event_obj: dict[str, Any]) -> None:
        with self._lock:
            if self._file_handle:
                self._file_handle.write(json.dumps(event_obj, ensure_ascii=False) + "\n")
                self._file_handle.flush()

    def _update_stats(self, event: str, payload: dict[str, Any], step: int) -> None:
        self._total_steps = max(self._total_steps, step)
        if event == "tool_call":
            self._tools_used += 1
        if event == "model_output" and payload.get("usage"):
            usage = payload["usage"]
            for field in self._total_usage:
                self._total_usage[field] += usage.get(field, 0)

    def get_current_run_events(self) -> list[dict[str, Any]]:
        return list(self._current_run_events)

    def clear_current_run_events(self) -> None:
        self._current_run_events.clear()

    def __enter__(self) -> "TraceLogger":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.finalize()


def create_trace_logger(
    trace_dir: str = "memory/traces",
    *,
    project_root: str | Path | None = None,
    enabled: bool = True,
) -> TraceLogger:
    """Create a JSONL logger confined to the selected project root."""

    default_dir = Path(trace_dir).expanduser()
    if project_root is not None:
        root = Path(project_root).expanduser().resolve()
        if not default_dir.is_absolute():
            default_dir = root / default_dir
        configured_dir = os.environ.get("TRACE_DIR")
        if configured_dir:
            requested_dir = Path(configured_dir).expanduser()
            if requested_dir.is_absolute():
                logger.warning("Ignoring TRACE_DIR outside selected project root")
            else:
                candidate_dir = (root / requested_dir).resolve()
                if candidate_dir.is_relative_to(root):
                    default_dir = candidate_dir
                else:
                    logger.warning("Ignoring TRACE_DIR outside selected project root")
    else:
        default_dir = Path(os.environ.get("TRACE_DIR", default_dir)).expanduser()

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_id = f"s-{timestamp}-{os.urandom(2).hex()}"
    return TraceLogger(session_id=session_id, trace_dir=default_dir, enabled=enabled)
