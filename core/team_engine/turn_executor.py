"""Single-turn execution kernel shared by oneshot and persistent workers."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.context_engine.observation_truncator import truncate_observation
from tools.registry import ToolRegistry


class TurnExecutor:
    def __init__(
        self,
        llm: Any,
        tool_registry: ToolRegistry,
        project_root: Path,
        denied_tools: Optional[set[str]] = None,
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.project_root = Path(project_root)
        self.denied_tools = set(denied_tools or set())
        self._tools_schema = self._get_tools_schema()

    def execute_turn(self, messages: list[dict[str, Any]], tool_usage: Dict[str, int]) -> Dict[str, Any]:
        raw_response = self.llm.invoke_raw(messages, tools=self._tools_schema, tool_choice="auto")
        response_text = self._extract_content(raw_response) or ""
        tool_calls = self._extract_tool_calls(raw_response)
        output_messages = list(messages)

        assistant_msg: Dict[str, Any] = {"role": "assistant", "content": response_text}
        if tool_calls:
            assistant_msg["tool_calls"] = []
            for call in tool_calls:
                call_id = call.get("id") or f"call_{uuid.uuid4().hex}"
                call["id"] = call_id
                arguments = call.get("arguments") or {}
                args_str = arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)
                assistant_msg["tool_calls"].append({
                    "id": call_id,
                    "type": "function",
                    "function": {"name": call.get("name"), "arguments": args_str},
                })
        output_messages.append(assistant_msg)

        if not tool_calls:
            return {
                "done": True,
                "final_result": self._extract_final_answer(response_text),
                "messages": output_messages,
            }

        for call in tool_calls:
            tool_name = call.get("name") or "unknown_tool"
            tool_call_id = call.get("id") or f"call_{uuid.uuid4().hex}"
            tool_input, parse_err = self._ensure_json_input(call.get("arguments"))
            if parse_err:
                observation = json.dumps(
                    {
                        "status": "error",
                        "error": {"code": "INVALID_PARAM", "message": f"Tool arguments parse error: {parse_err}"},
                        "data": {},
                    },
                    ensure_ascii=False,
                )
            else:
                observation = self._execute_tool(tool_name, tool_input, tool_usage)

            output_messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": observation,
            })

        return {"done": False, "final_result": None, "messages": output_messages}

    def _get_tools_schema(self) -> list[dict[str, Any]]:
        tools = self.tool_registry.get_openai_tools()
        if not self.denied_tools:
            return tools
        return [
            item for item in tools
            if item.get("function", {}).get("name") not in self.denied_tools
        ]

    def _execute_tool(self, tool_name: str, tool_input: Dict[str, Any], tool_usage: Dict[str, int]) -> str:
        if tool_name in self.denied_tools:
            return f"Error: Tool '{tool_name}' is not allowed for subagents."

        tool = self.tool_registry.get_tool(tool_name)
        if tool is None:
            return f"Error: Tool '{tool_name}' not found."

        tool_usage[tool_name] = tool_usage.get(tool_name, 0) + 1
        try:
            result = tool.run(tool_input)
            return truncate_observation(tool_name, str(result), str(self.project_root))
        except Exception as exc:
            return f"Error executing tool: {exc}"

    @staticmethod
    def _extract_content(raw_response: Any) -> Optional[str]:
        try:
            if hasattr(raw_response, "choices"):
                content = raw_response.choices[0].message.content
                if isinstance(content, list):
                    return "".join(part.get("text", "") for part in content if isinstance(part, dict))
                return content
            if isinstance(raw_response, dict) and raw_response.get("choices"):
                content = raw_response["choices"][0]["message"].get("content")
                if isinstance(content, list):
                    return "".join(part.get("text", "") for part in content if isinstance(part, dict))
                return content
        except Exception:
            return str(raw_response)
        return None

    @staticmethod
    def _extract_tool_calls(raw_response: Any) -> list[dict[str, Any]]:
        def _get_attr(obj, key: str):
            if obj is None:
                return None
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        try:
            choices = _get_attr(raw_response, "choices")
            if not choices:
                return []
            choice = choices[0]
            message = _get_attr(choice, "message")
            if not message:
                return []
            tool_calls = _get_attr(message, "tool_calls") or []
            calls: list[dict[str, Any]] = []
            if tool_calls:
                for call in tool_calls:
                    fn = _get_attr(call, "function") or {}
                    name = _get_attr(fn, "name") or _get_attr(call, "name") or "unknown_tool"
                    arguments = _get_attr(fn, "arguments") or _get_attr(call, "arguments") or {}
                    call_id = _get_attr(call, "id")
                    calls.append({"id": call_id, "name": name, "arguments": arguments})
                return calls
        except Exception:
            return []
        return []

    @staticmethod
    def _extract_final_answer(response: str) -> str:
        return (response or "").strip()

    @staticmethod
    def _ensure_json_input(raw: Any) -> Tuple[Any, Optional[str]]:
        if raw is None:
            return {}, None
        if isinstance(raw, (dict, list)):
            return raw, None
        s = str(raw).strip()
        if not s:
            return {}, None
        try:
            return json.loads(s), None
        except Exception as exc:
            return None, str(exc)

