"""Smoke test for MCP weather server."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "scripts" / "mcp_weather_server.py")],
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"Tools: {[t.name for t in tools.tools]}")
            result = await session.call_tool("get_weather", {"city": "Beijing"})
            print("Result:")
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
