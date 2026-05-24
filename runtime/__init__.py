"""Canonical runtime package with lazy exports.

Avoid eager imports here: compatibility wrappers under ``core/`` import
``runtime.prompt`` / ``runtime.context`` / ``runtime.session`` directly, and
package-level imports would otherwise pull in ``runtime.agent_host`` too early
and recreate circular imports through the legacy entrypoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent_host import CodeAgent
    from .runner import RuntimeRunner

__all__ = ["CodeAgent", "RuntimeRunner"]


def __getattr__(name: str):
    if name == "CodeAgent":
        from .agent_host import CodeAgent

        return CodeAgent
    if name == "RuntimeRunner":
        from .runner import RuntimeRunner

        return RuntimeRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
