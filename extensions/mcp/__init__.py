"""MCP extension surface."""

from extensions.mcp.prompt import format_mcp_tools_prompt

__all__ = ["format_mcp_tools_prompt", "register_mcp_servers"]


def __getattr__(name: str):
    """Keep the SDK-backed bootstrap behind explicit MCP registration."""
    if name == "register_mcp_servers":
        from extensions.mcp.bootstrap import register_mcp_servers

        return register_mcp_servers
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
