"""Source function for translation to TypeScript."""

import re
from typing import List


def to_kebab(value: str, stopwords: List[str] | None = None) -> str:
    """Convert a string to kebab-case and drop optional stopwords."""
    if stopwords is None:
        stopwords = []
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", " ", value)
    parts = [p.lower() for p in cleaned.strip().split() if p]
    parts = [p for p in parts if p not in stopwords]
    return "-".join(parts)
