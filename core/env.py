"""Environment loader helper to ensure .env is applied early."""

import os
from typing import Optional


_ENV_LOADED = False


def load_env() -> None:
    """Load .env once if available (no override)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    try:
        from dotenv import load_dotenv, find_dotenv
        dotenv_path = find_dotenv(usecwd=True)
        if dotenv_path:
            load_dotenv(dotenv_path, override=False)
        else:
            load_dotenv(override=False)
    except Exception:
        # Fail silently: rely on system environment if dotenv is missing.
        pass
    _ENV_LOADED = True


def getenv(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get env var after ensuring .env is loaded."""
    load_env()
    return os.getenv(key, default)
