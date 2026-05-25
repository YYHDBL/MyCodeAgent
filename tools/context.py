"""Tool execution context shared by runtime and executor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass
class ToolExecutionContext:
    """Runtime state needed at the tool execution boundary."""

    permission_checker: Callable[[str], bool] = lambda _name: True
    project_root: Optional[str] = None

    @property
    def root_path(self) -> Optional[Path]:
        return Path(self.project_root) if self.project_root else None


__all__ = ["ToolExecutionContext"]
