"""Register MCP servers and tools in ToolRegistry."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from tools.mcp.client import MCPClient, MCPClientConfig
from tools.mcp.adapter import register_mcp_tools
from tools.mcp.config import load_mcp_servers, connect_mode

logger = logging.getLogger(__name__)


def _default_uv_env(project_root: str, env: dict[str, str] | None) -> dict[str, str]:
    merged = dict(env or {})
    root = Path(project_root)
    cache_dir = root / ".uv_cache"
    tool_dir = root / ".uv_tools"
    npm_cache = root / ".npm_cache"

    cache_dir.mkdir(parents=True, exist_ok=True)
    tool_dir.mkdir(parents=True, exist_ok=True)
    npm_cache.mkdir(parents=True, exist_ok=True)

    merged.setdefault("UV_CACHE_DIR", str(cache_dir))
    merged.setdefault("XDG_CACHE_HOME", str(cache_dir))
    merged.setdefault("UV_HOME", str(tool_dir))
    merged.setdefault("UV_TOOL_DIR", str(tool_dir))
    merged.setdefault("UV_TOOL_BIN_DIR", str(tool_dir / "bin"))

    merged.setdefault("NPM_CONFIG_CACHE", str(npm_cache))
    merged.setdefault("NPM_CONFIG_LOGLEVEL", "error")
    merged.setdefault("NPM_CONFIG_FUND", "false")
    merged.setdefault("NPM_CONFIG_AUDIT", "false")

    return merged


def _build_client_config(project_root: str, spec: dict[str, Any]) -> MCPClientConfig:
    transport = spec.get("transport")
    url = spec.get("url") or spec.get("endpoint")
    command = spec.get("command")
    args = spec.get("args") or []
    env = spec.get("env") or {}

    if transport == "http" or url:
        if not url:
            raise ValueError("MCP server config requires url for http transport")
        return MCPClientConfig(transport="http", url=url, env=env)

    if command in {"uvx", "uv"}:
        env = _default_uv_env(project_root, env)

    if not command:
        raise ValueError("MCP server config requires command for stdio transport")
    expanded_args = [os.path.expandvars(str(arg)) for arg in args]
    return MCPClientConfig(transport="stdio", command=command, args=expanded_args, env=env)


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


def register_mcp_servers(tool_registry, project_root: str) -> tuple[list[MCPClient], list[dict[str, object | None]]]:
    servers = load_mcp_servers(project_root)
    mode = connect_mode()
    if not servers or mode == "disabled":
        return [], []

    clients: list[MCPClient] = []
    registered_tools: list[dict[str, object | None]] = []

    for server_name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        config = _build_client_config(project_root, spec)
        client = MCPClient(config)
        clients.append(client)

        if mode != "startup":
            continue

        try:
            tools_meta = register_mcp_tools(tool_registry, client, namespace=server_name)
            registered_tools.extend(tools_meta)
        except Exception as exc:
            logger.warning("MCP tool registration failed for %s: %s", server_name, exc)
            continue

    return clients, registered_tools
