"""Minimal tmux orchestration for teammate display mode."""

from __future__ import annotations

import subprocess
from typing import Callable, List, Tuple

from .protocol import sanitize_name


class TmuxOrchestrator:
    """Creates/tears down tmux session windows for teammates."""

    def __init__(self, command_runner: Callable[[List[str]], Tuple[int, str]] | None = None):
        self._runner = command_runner or self._run_subprocess

    @staticmethod
    def _run_subprocess(argv: List[str]) -> Tuple[int, str]:
        proc = subprocess.run(argv, capture_output=True, text=True, check=False)
        output = proc.stdout if proc.returncode == 0 else (proc.stderr or proc.stdout)
        return proc.returncode, output or ""

    @staticmethod
    def _session_name(team_name: str) -> str:
        return f"team_{sanitize_name(team_name)}"

    def ensure_session(self, team_name: str) -> bool:
        session = self._session_name(team_name)
        rc, _ = self._runner(["tmux", "has-session", "-t", session])
        if rc == 0:
            return False
        create_rc, create_out = self._runner(["tmux", "new-session", "-d", "-s", session, "-n", "lead"])
        if create_rc != 0:
            raise RuntimeError(f"tmux new-session failed: {create_out}")
        return True

    def ensure_teammate_window(self, team_name: str, teammate_name: str) -> bool:
        session = self._session_name(team_name)
        teammate = sanitize_name(teammate_name)
        rc, out = self._runner(["tmux", "list-windows", "-t", session, "-F", "#W"])
        if rc != 0:
            self.ensure_session(team_name)
            rc, out = self._runner(["tmux", "list-windows", "-t", session, "-F", "#W"])
            if rc != 0:
                raise RuntimeError(f"tmux list-windows failed: {out}")
        windows = {line.strip() for line in str(out or "").splitlines() if line.strip()}
        if teammate in windows:
            return False
        create_rc, create_out = self._runner(["tmux", "new-window", "-t", session, "-n", teammate])
        if create_rc != 0:
            raise RuntimeError(f"tmux new-window failed: {create_out}")
        self._runner(["tmux", "select-layout", "-t", session, "tiled"])
        return True

    def cleanup_session(self, team_name: str) -> None:
        session = self._session_name(team_name)
        self._runner(["tmux", "kill-session", "-t", session])

