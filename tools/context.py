"""Tool execution context shared by runtime and executor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .permissions import PermissionContext, PermissionDecision


@dataclass
class ToolExecutionContext:
    """Runtime state needed at the tool execution boundary."""

    permission_checker: Callable[[str], bool] = lambda _name: True
    permission_decider: Optional[
        Callable[[str, dict[str, Any], PermissionContext], PermissionDecision]
    ] = None
    permission_context: PermissionContext = PermissionContext()
    project_root: Optional[str] = None

    @property
    def root_path(self) -> Optional[Path]:
        return Path(self.project_root) if self.project_root else None


__all__ = ["ToolExecutionContext"]
