"""Optional live-provider smoke test, intentionally outside deterministic CI."""

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.credentialed


def test_configured_provider_returns_a_nonempty_completion() -> None:
    """Run only with ``-m credentialed`` and explicit credentials enabled."""

    if os.getenv("RUN_CREDENTIALLED_EVALS") != "1":
        pytest.skip("set RUN_CREDENTIALLED_EVALS=1 to permit a live provider call")
    if not os.getenv("LLM_API_KEY") or not os.getenv("LLM_BASE_URL"):
        pytest.fail("credentialed eval requires LLM_API_KEY and LLM_BASE_URL")

    from core.llm import HelloAgentsLLM, extract_response_content

    response = HelloAgentsLLM(temperature=0, max_tokens=16).invoke_raw(
        [{"role": "user", "content": "Reply with the single word: ready"}]
    )

    assert (extract_response_content(response) or "").strip()
