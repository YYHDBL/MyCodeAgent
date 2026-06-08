"""Model error classification for runtime recovery paths."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ModelErrorKind(str, Enum):
    EMPTY_RESPONSE = "empty_response"
    API_ERROR = "api_error"
    PROMPT_TOO_LONG = "prompt_too_long"
    MAX_OUTPUT = "max_output"
    UNKNOWN_MODEL_ERROR = "unknown_model_error"


@dataclass(frozen=True)
class ModelErrorClassification:
    kind: ModelErrorKind
    recoverable: bool
    message: str = ""
    finish_reason: str | None = None


def classify_model_error(
    *,
    response_text: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    response_meta: dict[str, Any] | None = None,
    error: Exception | None = None,
) -> ModelErrorClassification:
    meta = response_meta or {}
    finish_reason = _normalize_text(meta.get("finish_reason"))
    content = (response_text or "").strip()
    calls = tool_calls or []

    if error is not None:
        message = _normalize_text(str(error))
        if _looks_like_prompt_too_long(message):
            return ModelErrorClassification(
                kind=ModelErrorKind.PROMPT_TOO_LONG,
                recoverable=True,
                message=message,
                finish_reason=finish_reason,
            )
        if isinstance(error, RuntimeError):
            return ModelErrorClassification(
                kind=ModelErrorKind.API_ERROR,
                recoverable=False,
                message=message,
                finish_reason=finish_reason,
            )
        return ModelErrorClassification(
            kind=ModelErrorKind.UNKNOWN_MODEL_ERROR,
            recoverable=False,
            message=message,
            finish_reason=finish_reason,
        )

    if finish_reason in {"length", "max_output", "max_tokens"}:
        return ModelErrorClassification(
            kind=ModelErrorKind.MAX_OUTPUT,
            recoverable=True,
            message="Model output hit length limit.",
            finish_reason=finish_reason,
        )

    if not calls and not content:
        return ModelErrorClassification(
            kind=ModelErrorKind.EMPTY_RESPONSE,
            recoverable=True,
            message="Model returned no content and no tool calls.",
            finish_reason=finish_reason,
        )

    return ModelErrorClassification(
        kind=ModelErrorKind.UNKNOWN_MODEL_ERROR,
        recoverable=False,
        message="No model error classified.",
        finish_reason=finish_reason,
    )


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _looks_like_prompt_too_long(message: str) -> bool:
    patterns = (
        "prompt too long",
        "context length",
        "context window",
        "too many tokens",
        "maximum context length",
        "request too large",
    )
    return any(pattern in message for pattern in patterns)


__all__ = ["ModelErrorClassification", "ModelErrorKind", "classify_model_error"]
