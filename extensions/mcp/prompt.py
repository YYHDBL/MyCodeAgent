"""Prompt formatting for MCP tools."""

from __future__ import annotations


def _format_schema(schema: object | None) -> str:
    if not isinstance(schema, dict):
        return ""
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    if not isinstance(properties, dict) or not properties:
        return ""
    parts = []
    for name, spec in properties.items():
        if not isinstance(spec, dict):
            parts.append(str(name))
            continue
        type_name = spec.get("type")
        default = spec.get("default")
        desc = (spec.get("description") or "").strip()
        required_flag = " required" if name in required else ""
        type_label = f": {type_name}" if type_name else ""
        default_label = f", default={default}" if default is not None else ""
        if desc:
            parts.append(f"{name}{type_label}{default_label}{required_flag} - {desc}")
        else:
            parts.append(f"{name}{type_label}{default_label}{required_flag}")
    return "; ".join(parts)


def format_mcp_tools_prompt(tools_meta: list[dict[str, object | None]]) -> str:
    if not tools_meta:
        return ""
    lines = []
    for item in tools_meta:
        name = item.get("name") or ""
        description = (item.get("description") or "").strip()
        schema_text = _format_schema(item.get("schema"))
        if description:
            lines.append(f"- {name}: {description}")
        else:
            lines.append(f"- {name}")
        if schema_text:
            lines.append(f"  params: {schema_text}")
    return "\n".join(lines)


__all__ = ["format_mcp_tools_prompt"]
