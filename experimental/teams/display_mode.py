"""Display mode resolver for teammate runtime."""

import os
import shutil
from typing import Optional, Tuple

VALID_TEAMMATE_MODES = {"auto", "in-process", "tmux"}


def resolve_teammate_mode(requested_mode: Optional[str]) -> Tuple[str, Optional[str]]:
    """Resolve requested teammate mode to runtime mode with optional warning."""
    mode = (requested_mode or "auto").strip().lower()
    if mode not in VALID_TEAMMATE_MODES:
        return "in-process", f"Invalid teammate_mode={requested_mode!r}; fallback to in-process"

    if mode == "in-process":
        return "in-process", None

    tmux_available = shutil.which("tmux") is not None
    if mode == "tmux":
        if tmux_available:
            return "tmux", None
        return "in-process", "Requested teammate_mode=tmux but tmux is unavailable; fallback to in-process"

    # auto: only use tmux when already inside a tmux session.
    if os.getenv("TMUX") and tmux_available:
        return "tmux", None
    return "in-process", None

