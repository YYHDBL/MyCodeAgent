"""Convert MCP tool results to the Universal Tool Response Protocol."""

from __future__ import annotations

import json
import time
from typing import Any

from tools.base import ToolStatus, ErrorCode


def _extract_text_blocks(result: Any) -> list[str]:
    texts: list[str] = []
    contents = getattr(result, "content", None) or []
    for item in contents:
        text = None
        if hasattr(item, "text"):
            text = getattr(item, "text")
        elif isinstance(item, dict):
            text = item.get("text")
        if text:
            texts.append(str(text))
            continue
        resource = None
        if hasattr(item, "resource"):
            resource = getattr(item, "resource")
        elif isinstance(item, dict):
            resource = item.get("resource")
        if resource is not None:
            res_text = None
            if hasattr(resource, "text"):
                res_text = getattr(resource, "text")
            elif isinstance(resource, dict):
                res_text = resource.get("text")
            if res_text:
                texts.append(str(res_text))
    return texts


def _describe_content_item(item: Any) -> str | None:
    mime_type = None
    data = None
    if hasattr(item, "mimeType"):
        mime_type = getattr(item, "mimeType")
        data = getattr(item, "data", None)
    elif isinstance(item, dict):
        mime_type = item.get("mimeType") or item.get("mime_type")
        data = item.get("data")
    if mime_type:
        size = None
        try:
            size = len(data) if data is not None else None
        except Exception:
            size = None
        if size is not None:
            return f"[binary content {mime_type}, {size} bytes]"
        return f"[binary content {mime_type}]"

    resource = None
    if hasattr(item, "resource"):
        resource = getattr(item, "resource")
    elif isinstance(item, dict):
        resource = item.get("resource")
    if resource is not None:
        uri = None
        if hasattr(resource, "uri"):
            uri = getattr(resource, "uri")
        elif isinstance(resource, dict):
            uri = resource.get("uri")
        if uri:
            return f"[resource {uri}]"
        return "[resource content]"

    if isinstance(item, dict):
        kind = item.get("type")
        if kind:
            return f"[{kind} content]"
    return None


def _summarize_non_text(result: Any) -> list[str]:
    contents = getattr(result, "content", None) or []
    summaries: list[str] = []
    for item in contents:
        summary = _describe_content_item(item)
        if summary:
            summaries.append(summary)
    return summaries


def _get_structured_content(result: Any) -> Any:
    if hasattr(result, "structuredContent"):
        return getattr(result, "structuredContent")
    if hasattr(result, "structured_content"):
        return getattr(result, "structured_content")
    if isinstance(result, dict):
        return result.get("structuredContent") or result.get("structured_content")
    return None


def to_protocol_success(
    result: Any,
    params_input: dict[str, Any],
    tool_name: str,
    start_time: float,
) -> str:
    structured = _get_structured_content(result)
    text_blocks = _extract_text_blocks(result)
    if text_blocks:
        text = "\n".join(text_blocks)
    else:
        summaries = _summarize_non_text(result)
        text = "\n".join(summaries) if summaries else ""

    data = {
        "structured": structured,
        "text": text,
    }

    time_ms = int((time.monotonic() - start_time) * 1000)

    return json.dumps(
        {
            "status": ToolStatus.SUCCESS.value,
            "data": data,
            "text": text,
            "stats": {"time_ms": time_ms},
            "context": {
                "cwd": ".",
                "params_input": params_input,
                "mcp_tool": tool_name,
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def to_protocol_error(
    message: str,
    params_input: dict[str, Any],
    tool_name: str,
    start_time: float,
) -> str:
    if not message:
        message = "MCP execution error"
    time_ms = int((time.monotonic() - start_time) * 1000)
    return json.dumps(
        {
            "status": ToolStatus.ERROR.value,
            "data": {},
            "text": message,
            "error": {
                "code": ErrorCode.EXECUTION_ERROR.value,
                "message": message,
            },
            "stats": {"time_ms": time_ms},
            "context": {
                "cwd": ".",
                "params_input": params_input,
                "mcp_tool": tool_name,
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def to_protocol_invalid_param(
    message: str,
    params_input: dict[str, Any],
    tool_name: str,
    start_time: float,
) -> str:
    if not message:
        message = "Invalid parameters"
    time_ms = int((time.monotonic() - start_time) * 1000)
    return json.dumps(
        {
            "status": ToolStatus.ERROR.value,
            "data": {},
            "text": message,
            "error": {
                "code": ErrorCode.INVALID_PARAM.value,
                "message": message,
            },
            "stats": {"time_ms": time_ms},
            "context": {
                "cwd": ".",
                "params_input": params_input,
                "mcp_tool": tool_name,
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def to_protocol_result(
    result: Any,
    params_input: dict[str, Any],
    tool_name: str,
    start_time: float,
) -> str:
    is_error = False
    if hasattr(result, "isError"):
        is_error = bool(getattr(result, "isError"))
    elif isinstance(result, dict):
        is_error = bool(result.get("isError"))

    if not is_error:
        return to_protocol_success(result, params_input, tool_name, start_time)

    text_blocks = _extract_text_blocks(result)
    message = "\n".join(text_blocks) if text_blocks else "MCP tool returned error"
    return to_protocol_error(message, params_input, tool_name, start_time)
