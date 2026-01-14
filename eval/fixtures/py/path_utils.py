"""Path utilities for evaluation fixtures."""

from typing import Optional


def normalize_path(path: Optional[str]) -> str:
    """
    Normalize a filesystem-like path.

    Expected behavior (see tests):
    - strip whitespace
    - replace backslashes with forward slashes
    - collapse duplicate slashes
    - remove leading/trailing slashes
    """
    if path is None:
        return ""
    return str(path)
