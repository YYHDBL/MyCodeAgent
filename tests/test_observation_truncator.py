"""Contracts for typed tool-result truncation."""

from __future__ import annotations

from tools.base import ToolResult, ToolStatus, serialize_tool_result
from tools.observation_store import ObservationTruncator, force_truncate_result


def _result(content: str, *, status: ToolStatus = ToolStatus.SUCCESS) -> ToolResult:
    return ToolResult(
        status=status,
        data={"content": content},
        text="tool output",
        error_code="TEST_ERROR" if status is ToolStatus.ERROR else None,
        error_message="test" if status is ToolStatus.ERROR else None,
        stats={"time_ms": 1},
        context={"cwd": ".", "params_input": {}},
    )


def test_small_typed_result_is_returned_without_serialization_round_trip(tmp_path):
    result = _result("hello")

    assert ObservationTruncator(str(tmp_path)).truncate("Read", result) is result


def test_large_typed_result_is_saved_and_replaced_with_partial_preview(tmp_path):
    result = _result("\n".join(f"line {index}" for index in range(3000)))

    truncated = ObservationTruncator(str(tmp_path)).truncate("Read", result)

    assert truncated.status is ToolStatus.PARTIAL
    assert truncated.data["truncated"] is True
    saved = tmp_path / truncated.data["truncation"]["full_output_path"]
    assert saved.exists()
    assert len(serialize_tool_result(truncated).encode()) < len(serialize_tool_result(result).encode())


def test_truncation_keeps_an_error_status_and_error_clarity(tmp_path):
    truncated = force_truncate_result("Bash", _result("x" * 1000, status=ToolStatus.ERROR), str(tmp_path), 120)

    payload = serialize_tool_result(truncated)
    assert truncated.status is ToolStatus.ERROR
    assert '"code": "TEST_ERROR"' in payload
    assert truncated.data["truncated"] is True
