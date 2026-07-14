"""Register MCP servers and tools in ToolRegistry."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from extensions.mcp.config import load_mcp_servers, connect_mode
from extensions.mcp.errors import MCP_EXTRA_ERROR, MCPExtraRequiredError
from extensions.mcp.prompt import format_mcp_tools_prompt

if TYPE_CHECKING:
    from extensions.mcp.client import MCPClient

logger = logging.getLogger(__name__)

def _load_mcp_runtime() -> tuple[type[Any], type[Any], Any]:
    """Load the MCP SDK boundary only after the user explicitly enables MCP."""
    try:
        from extensions.mcp.adapter import register_mcp_tools
        from extensions.mcp.client import MCPClient, MCPClientConfig
    except ImportError as exc:
        raise MCPExtraRequiredError(MCP_EXTRA_ERROR) from exc
    return MCPClient, MCPClientConfig, register_mcp_tools


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


def _build_client_config(project_root: str, spec: dict[str, Any], client_config_class: type[Any]) -> Any:
    transport = spec.get("transport")
    url = spec.get("url") or spec.get("endpoint")
    command = spec.get("command")
    args = spec.get("args") or []
    env = spec.get("env") or {}

    if transport == "http" or url:
        if not url:
            raise ValueError("MCP server config requires url for http transport")
        return client_config_class(transport="http", url=url, env=env)

    if command in {"uvx", "uv"}:
        env = _default_uv_env(project_root, env)

    if not command:
        raise ValueError("MCP server config requires command for stdio transport")
    expanded_args = [os.path.expandvars(str(arg)) for arg in args]
    return client_config_class(transport="stdio", command=command, args=expanded_args, env=env)


def register_mcp_servers(tool_registry, project_root: str) -> tuple[list[MCPClient], list[dict[str, object | None]]]:
    MCPClient, MCPClientConfig, register_mcp_tools = _load_mcp_runtime()
    servers = load_mcp_servers(project_root)
    mode = connect_mode()
    if not servers or mode == "disabled":
        return [], []

    clients: list[MCPClient] = []
    registered_tools: list[dict[str, object | None]] = []

    for server_name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        config = _build_client_config(project_root, spec, MCPClientConfig)
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


__all__ = ["MCPExtraRequiredError", "format_mcp_tools_prompt", "register_mcp_servers"]
