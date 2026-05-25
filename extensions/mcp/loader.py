"""Compatibility wrapper for MCP bootstrap and prompt formatting."""

from extensions.mcp.bootstrap import register_mcp_servers
from extensions.mcp.prompt import format_mcp_tools_prompt

__all__ = ["format_mcp_tools_prompt", "register_mcp_servers"]
