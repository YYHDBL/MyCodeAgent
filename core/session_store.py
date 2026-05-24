"""Compatibility wrapper for the canonical runtime session store."""

from runtime.session import (
    SessionStore,
    build_session_snapshot,
    load_session_snapshot,
    save_session_snapshot,
)

__all__ = [
    "SessionStore",
    "build_session_snapshot",
    "load_session_snapshot",
    "save_session_snapshot",
]
