"""Quick MCP fetch server smoke test."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.mcp.client import MCPClient, MCPClientConfig


async def main():
    cache_dir = ROOT / ".uv_cache"
    tool_dir = ROOT / ".uv_tools"
    npm_cache = ROOT / ".npm_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    tool_dir.mkdir(parents=True, exist_ok=True)
    npm_cache.mkdir(parents=True, exist_ok=True)
    config = MCPClientConfig(
        transport="stdio",
        command="uvx",
        args=["mcp-server-fetch"],
        env={
            "UV_CACHE_DIR": str(cache_dir),
            "XDG_CACHE_HOME": str(cache_dir),
            "UV_HOME": str(tool_dir),
            "UV_TOOL_DIR": str(tool_dir),
            "UV_TOOL_BIN_DIR": str(tool_dir / "bin"),
            "NPM_CONFIG_CACHE": str(npm_cache),
            "NPM_CONFIG_LOGLEVEL": "error",
            "NPM_CONFIG_FUND": "false",
            "NPM_CONFIG_AUDIT": "false",
        },
    )
    client = MCPClient(config)
    try:
        session = await client.connect()
        tools = await session.list_tools()
        tool_names = [t.name for t in tools.tools]
        print(f"Tools: {tool_names}")

        if "fetch" not in tool_names:
            raise RuntimeError("fetch tool not found on server")

        result = await session.call_tool("fetch", {"url": "https://example.com"})
        print("Fetch result (raw):")
        print(result)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
