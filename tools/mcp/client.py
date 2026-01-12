"""MCP client wrapper for stdio/HTTP transports."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Optional

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
import anyio


@dataclass
class MCPClientConfig:
    transport: str
    command: Optional[str] = None
    args: Optional[list[str]] = None
    url: Optional[str] = None
    env: Optional[dict[str, str]] = None


class MCPClient:
    """Async MCP client with lazy connection management."""

    def __init__(self, config: MCPClientConfig):
        self._config = config
        self._conn = None
        self._session: Optional[ClientSession] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self) -> ClientSession:
        if self._session:
            return self._session

        if self._config.transport == "stdio":
            env = None
            if self._config.env is not None:
                env = dict(os.environ)
                env.update(self._config.env)
            params = StdioServerParameters(
                command=self._config.command,
                args=self._config.args or [],
                env=env,
            )
            self._conn = stdio_client(params)
        else:
            if not self._config.url:
                raise ValueError("MCPClientConfig.url is required for http transport")
            self._conn = streamablehttp_client(self._config.url)

        try:
            read, write, *_ = await self._conn.__aenter__()
        except Exception:
            self._conn = None
            raise

        session = ClientSession(read, write)
        try:
            await session.__aenter__()
            await session.initialize()
        except Exception:
            try:
                await session.__aexit__(None, None, None)
            finally:
                self._session = None
            try:
                await self._conn.__aexit__(None, None, None)
            finally:
                self._conn = None
            raise

        self._session = session
        return self._session

    async def close(self) -> None:
        if self._session:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._conn:
            await self._conn.__aexit__(None, None, None)
            self._conn = None

    async def list_tools(self) -> Any:
        session = await self.connect()
        try:
            return await session.list_tools()
        except anyio.ClosedResourceError:
            await self.close()
            session = await self.connect()
            return await session.list_tools()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        session = await self.connect()
        try:
            return await session.call_tool(name, arguments)
        except anyio.ClosedResourceError:
            await self.close()
            session = await self.connect()
            return await session.call_tool(name, arguments)

    async def list_resources(self) -> Any:
        session = await self.connect()
        try:
            return await session.list_resources()
        except anyio.ClosedResourceError:
            await self.close()
            session = await self.connect()
            return await session.list_resources()

    async def read_resource(self, uri: Any) -> Any:
        session = await self.connect()
        try:
            return await session.read_resource(uri)
        except anyio.ClosedResourceError:
            await self.close()
            session = await self.connect()
            return await session.read_resource(uri)

    async def list_prompts(self) -> Any:
        session = await self.connect()
        try:
            return await session.list_prompts()
        except anyio.ClosedResourceError:
            await self.close()
            session = await self.connect()
            return await session.list_prompts()

    async def get_prompt(self, name: str, arguments: dict[str, Any]) -> Any:
        session = await self.connect()
        try:
            return await session.get_prompt(name, arguments=arguments)
        except anyio.ClosedResourceError:
            await self.close()
            session = await self.connect()
            return await session.get_prompt(name, arguments=arguments)

    def _run_sync(self, coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            return self._loop.run_until_complete(coro)
        raise RuntimeError("MCPClient sync methods cannot run inside an active event loop.")

    def connect_sync(self) -> ClientSession:
        return self._run_sync(self.connect())

    def call_tool_sync(self, name: str, arguments: dict[str, Any]) -> Any:
        return self._run_sync(self.call_tool(name, arguments))

    def list_tools_sync(self) -> Any:
        return self._run_sync(self.list_tools())

    def close_sync(self) -> None:
        result = self._run_sync(self.close())
        if self._loop and not self._loop.is_closed():
            self._loop.close()
        return result
