"""Buggy math utilities for evaluation fixtures."""


def safe_divide(a: float, b: float) -> float:
    """Return a / b. Should raise ValueError when b == 0."""
    if b == 0:
        return 0
    return a / b
