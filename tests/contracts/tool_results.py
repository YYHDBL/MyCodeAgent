"""Reusable assertions for model-facing built-in-tool contracts."""

from __future__ import annotations

from tests.utils.protocol_validator import ProtocolValidator
from tools.base import ToolResult, serialize_tool_result


def assert_model_tool_result(result: ToolResult, *, expected_status: str) -> None:
    """Prove a typed result remains a valid model envelope at serialization."""

    assert isinstance(result, ToolResult)
    payload = serialize_tool_result(result)
    validation = ProtocolValidator.validate(payload)
    assert validation.passed, validation.errors
    assert result.status.value == expected_status
