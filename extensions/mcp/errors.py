"""Errors shared by the optional MCP adapter boundary."""

MCP_EXTRA_ERROR = (
    "MCP support is not installed. Install it with `pip install 'mycodeagent[mcp]'` "
    "(or `uv sync --extra mcp`) and try again."
)


class MCPExtraRequiredError(RuntimeError):
    """Raised when MCP is explicitly enabled without its optional extra."""
