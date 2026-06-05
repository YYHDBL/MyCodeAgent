"""Convert runtime history messages into model API messages."""

from __future__ import annotations

import json
import logging
from typing import Any

from runtime.history import Message

logger = logging.getLogger(__name__)


class MessageNormalizer:
    """Serializes runtime messages into OpenAI-compatible dictionaries."""

    def normalize(self, messages: list[Message]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for msg in messages or []:
            normalized.extend(self._normalize_one(msg))
        return normalized

    def _normalize_one(self, msg: Message) -> list[dict[str, Any]]:
        if msg.role == "user":
            return [{"role": "user", "content": msg.content}]
        if msg.role == "assistant":
            return [self._assistant_message(msg)]
        if msg.role == "tool":
            return [self._tool_message(msg)]
        if msg.role == "summary":
            return [{"role": "system", "content": f"## Archived History Summary\n{msg.content}"}]
        return []

    def _assistant_message(self, msg: Message) -> dict[str, Any]:
        metadata = msg.metadata or {}
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": msg.content,
        }

        reasoning_content = metadata.get("reasoning_content")
        if reasoning_content:
            assistant_msg["reasoning_content"] = reasoning_content

        if metadata.get("action_type") == "tool_call":
            tool_calls = metadata.get("tool_calls")
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    self._tool_call_dict(call) for call in tool_calls
                ]
            else:
                legacy_call = self._legacy_tool_call(metadata)
                if legacy_call:
                    assistant_msg["tool_calls"] = [legacy_call]
                else:
                    logger.warning("Strict tool mode active but missing tool_calls")

        return assistant_msg

    def _tool_call_dict(self, call: dict[str, Any]) -> dict[str, Any]:
        name = call.get("name") or "unknown_tool"
        arguments = call.get("arguments") or {}
        args_str = arguments if isinstance(arguments, str) else json.dumps(
            arguments, ensure_ascii=False
        )
        return {
            "id": call.get("id"),
            "type": "function",
            "function": {
                "name": name,
                "arguments": args_str,
            },
        }

    def _legacy_tool_call(self, metadata: dict[str, Any]) -> dict[str, Any] | None:
        tool_name = metadata.get("tool_name")
        tool_call_id = metadata.get("tool_call_id")
        if not tool_name or not tool_call_id:
            return None
        return {
            "id": tool_call_id,
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(metadata.get("tool_args") or {}, ensure_ascii=False),
            },
        }

    def _tool_message(self, msg: Message) -> dict[str, Any]:
        metadata = msg.metadata or {}
        tool_call_id = metadata.get("tool_call_id")
        if tool_call_id:
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": msg.content,
            }

        tool_name = metadata.get("tool_name", "unknown")
        logger.warning(
            "Strict tool mode active but missing tool_call_id; using user observation fallback"
        )
        return {
            "role": "user",
            "content": f"Observation ({tool_name}): {msg.content}",
        }
