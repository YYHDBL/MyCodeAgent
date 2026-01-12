# Python MCP 客户端实现详解

## 目录

1. [概述](#概述)
2. [环境准备](#环境准备)
3. [架构设计](#架构设计)
4. [核心模块实现](#核心模块实现)
5. [传输层实现](#传输层实现)
6. [工具集成](#工具集成)
7. [配置管理](#配置管理)
8. [安全机制](#安全机制)
9. [完整示例](#完整示例)

---

## 概述

### 什么是 MCP

MCP (Model Context Protocol) 是一个开放协议，用于连接 AI 应用与外部数据源和工具。本文档详细介绍如何使用 **Python** 实现 MCP 客户端。

### 官方 SDK

```bash
pip install mcp
```

官方 SDK 提供了：
- `mcp.client.stdio` - stdio 传输
- `mcp.client.websocket` - WebSocket 传输
- `mcp.client.sse` - SSE 传输
- `mcp.ClientSession` - 会话管理

### 能力矩阵

| 能力 | Python SDK 支持情况 |
|------|---------------------|
| **Tools** | ✅ 完全支持 |
| **Prompts** | ✅ 完全支持 |
| **Resources** | ✅ 完全支持 |
| **stdio 传输** | ✅ 完全支持 |
| **SSE 传输** | ✅ 完全支持 |
| **WebSocket 传输** | ✅ 完全支持 |

---

## 环境准备

### 安装依赖

```bash
# 核心依赖
pip install mcp

# 可选依赖
pip install pydantic          # 数据验证
pip install aiohttp           # HTTP/SSE 传输
pip install websockets        # WebSocket 传输
pip install python-dotenv     # 环境变量管理
```

### 项目结构

```
mcp_python_client/
├── src/
│   ├── __init__.py
│   ├── client/
│   │   ├── __init__.py
│   │   ├── mcp_client.py       # MCP 客户端封装
│   │   ├── transport.py        # 传输层抽象
│   │   └── connection.py       # 连接管理
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py             # 工具基类
│   │   └── mcp_tool_wrapper.py # MCP 工具包装器
│   ├── config/
│   │   ├── __init__.py
│   │   └── manager.py          # 配置管理
│   └── utils/
│       ├── __init__.py
│       ├── logger.py           # 日志工具
│       └── timeout.py          # 超时控制
├── config/
│   └── mcp_servers.json        # MCP 服务器配置
├── examples/
│   ├── stdio_client.py
│   ├── websocket_client.py
│   └── sse_client.py
├── tests/
│   └── test_mcp_client.py
├── pyproject.toml
└── README.md
```

---

## 架构设计

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Python MCP Client                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                        工具系统 (Tools)                          │    │
│  │  ┌───────────────────────────────────────────────────────────┐  │    │
│  │  │  Tool (ABC)                                               │  │    │
│  │  │  - name: str                                              │  │    │
│  │  │  - call(args): Coroutine[Any]                             │  │    │
│  │  │  - description: str                                       │  │    │
│  │  │  - input_schema: dict                                     │  │    │
│  │  └───────────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↑                                       │
│                                    │ 包装                                   │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    MCP 工具包装层                                │    │
│  │  (src/tools/mcp_tool_wrapper.py)                                │    │
│  │                                                                   │    │
│  │  - MCPToolWrapper       → 将 MCP 工具包装为 Tool                 │    │
│  │  - get_mcp_tools()       → 获取所有 MCP 工具                    │    │
│  │  - call_mcp_tool()       → 执行 MCP 工具调用                    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↑                                       │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      MCP 客户端层                                │    │
│  │  (src/client/mcp_client.py)                                     │    │
│  │                                                                   │    │
│  │  - MCPClient             → 客户端抽象类                          │    │
│  │  - get_clients()         → 获取所有连接的客户端                 │    │
│  │  - connect_to_server()   → 建立服务器连接                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↑                                       │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     传输层 (mcp.client)                          │    │
│  │                                                                   │    │
│  │  - stdio_client()        → stdio 传输                             │    │
│  │  - sse_client()          → SSE 传输                               │    │
│  │  - websocket_client()    → WebSocket 传输                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↑                                       │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    MCP 服务器 (外部)                             │    │
│  │  - filesystem    - postgres       - github                       │    │
│  │  - slack         - google-drive   - custom servers...            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 核心模块实现

### 1. 类型定义

```python
# src/client/types.py
from typing import Any, Dict, List, Optional, Union, Literal
from typing_extensions import TypedDict
from enum import Enum


class TransportType(str, Enum):
    """传输类型枚举"""
    STDIO = "stdio"
    SSE = "sse"
    WEBSOCKET = "websocket"


class ServerConfig(TypedDict, total=False):
    """MCP 服务器配置基类"""
    type: TransportType
    name: str


class StdioServerConfig(ServerConfig):
    """stdio 服务器配置"""
    type: Literal[TransportType.STDIO]
    command: str
    args: Optional[List[str]]
    env: Optional[Dict[str, str]]


class SSEServerConfig(ServerConfig):
    """SSE 服务器配置"""
    type: Literal[TransportType.SSE]
    url: str
    headers: Optional[Dict[str, str]]


class WebSocketServerConfig(ServerConfig):
    """WebSocket 服务器配置"""
    type: Literal[TransportType.WEBSOCKET]
    url: str
    auth_token: Optional[str]


MCPServerConfig = Union[StdioServerConfig, SSEServerConfig, WebSocketServerConfig]


class ToolCallResult(TypedDict):
    """工具调用结果"""
    success: bool
    data: Optional[Any]
    error: Optional[str]


class ConnectedClient:
    """已连接的客户端信息"""
    def __init__(
        self,
        name: str,
        session: Any,  # mcp.ClientSession
        config: MCPServerConfig,
        capabilities: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.session = session
        self.config = config
        self.capabilities = capabilities


class FailedClient:
    """连接失败的客户端信息"""
    def __init__(self, name: str, error: str):
        self.name = name
        self.error = error


WrappedClient = Union[ConnectedClient, FailedClient]
```

### 2. 传输层抽象

```python
# src/client/transport.py
import asyncio
from typing import Any, Dict, Optional, Tuple
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.websocket import websocket_client
from mcp.client.sse import sse_client

from .types import MCPServerConfig, TransportType


class TransportError(Exception):
    """传输层异常"""
    pass


async def create_transport(
    config: MCPServerConfig,
    timeout: float = 30.0
) -> Tuple[Any, Any]:
    """
    创建传输层连接

    Args:
        config: MCP 服务器配置
        timeout: 连接超时时间（秒）

    Returns:
        (read_stream, write_stream) 元组

    Raises:
        TransportError: 连接失败时抛出
    """
    transport_type = config["type"]

    try:
        if transport_type == TransportType.STDIO:
            return await _create_stdio_transport(config, timeout)
        elif transport_type == TransportType.SSE:
            return await _create_sse_transport(config, timeout)
        elif transport_type == TransportType.WEBSOCKET:
            return await _create_websocket_transport(config, timeout)
        else:
            raise TransportError(f"不支持的传输类型: {transport_type}")
    except asyncio.TimeoutError:
        raise TransportError(f"连接超时 ({timeout}s)")
    except Exception as e:
        raise TransportError(f"连接失败: {str(e)}")


async def _create_stdio_transport(
    config: MCPServerConfig,
    timeout: float
) -> Tuple[Any, Any]:
    """创建 stdio 传输"""
    # 使用 asyncio.wait_for 实现超时
    return await asyncio.wait_for(
        stdio_client(
            StdioServerParameters(
                command=config["command"],
                args=config.get("args", []),
                env=config.get("env")
            )
        ),
        timeout=timeout
    )


async def _create_sse_transport(
    config: MCPServerConfig,
    timeout: float
) -> Tuple[Any, Any]:
    """创建 SSE 传输"""
    return await asyncio.wait_for(
        sse_client(config["url"], headers=config.get("headers")),
        timeout=timeout
    )


async def _create_websocket_transport(
    config: MCPServerConfig,
    timeout: float
) -> Tuple[Any, Any]:
    """创建 WebSocket 传输"""
    url = config["url"]

    # 处理 auth_token
    if auth_token := config.get("auth_token"):
        import urllib.parse
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        query_params = urllib.parse.parse_qs(parsed.query)
        if "authToken" not in query_params:
            query_params["authToken"] = [auth_token]
            new_query = urllib.parse.urlencode(query_params, doseq=True)
            url = urlunparse(parsed._replace(query=new_query))

    return await asyncio.wait_for(
        websocket_client(url),
        timeout=timeout
    )
```

### 3. MCP 客户端封装

```python
# src/client/mcp_client.py
import asyncio
import logging
from typing import Any, Dict, List, Optional, Callable
from functools import lru_cache

from mcp import ClientSession, types
from mcp.client.stdio import StdioServerParameters

from .types import (
    MCPServerConfig,
    ConnectedClient,
    FailedClient,
    WrappedClient
)
from .transport import create_transport, TransportError


logger = logging.getLogger(__name__)


class MCPClient:
    """
    MCP 客户端管理器

    负责管理多个 MCP 服务器的连接、会话和工具调用。
    """

    def __init__(
        self,
        servers: Dict[str, MCPServerConfig],
        connection_timeout: float = 30.0,
        connection_batch_size: int = 3
    ):
        """
        初始化 MCP 客户端管理器

        Args:
            servers: 服务器配置字典，key 为服务器名称
            connection_timeout: 连接超时时间（秒）
            connection_batch_size: 批量连接时每批的数量
        """
        self.servers = servers
        self.connection_timeout = connection_timeout
        self.connection_batch_size = connection_batch_size
        self._clients: Dict[str, WrappedClient] = {}

    async def connect_all(self) -> Dict[str, WrappedClient]:
        """
        连接所有配置的服务器

        Returns:
            服务器名称到客户端的映射
        """
        server_entries = list(self.servers.items())

        # 批量连接
        results: Dict[str, WrappedClient] = {}
        for i in range(0, len(server_entries), self.connection_batch_size):
            batch = server_entries[i:i + self.connection_batch_size]
            batch_results = await asyncio.gather(
                *[self._connect_server(name, config)
                  for name, config in batch],
                return_exceptions=True
            )

            for (name, _), result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    results[name] = FailedClient(
                        name=name,
                        error=str(result)
                    )
                    logger.error(f"服务器 {name} 连接失败: {result}")
                else:
                    results[name] = result
                    logger.info(f"服务器 {name} 连接成功")

        self._clients = results
        return results

    async def _connect_server(
        self,
        name: str,
        config: MCPServerConfig
    ) -> ConnectedClient:
        """
        连接到单个 MCP 服务器

        Args:
            name: 服务器名称
            config: 服务器配置

        Returns:
            ConnectedClient 实例

        Raises:
            TransportError: 连接失败
        """
        # 创建传输层
        read, write = await create_transport(config, self.connection_timeout)

        # 创建会话
        session = ClientSession(read, write)

        try:
            # 初始化会话
            await session.initialize()

            # 获取服务器能力
            capabilities = None
            try:
                # 检查是否支持 tools
                if hasattr(session, 'list_tools'):
                    await session.list_tools()
                # 检查是否支持 resources
                if hasattr(session, 'list_resources'):
                    await session.list_resources()
                # 检查是否支持 prompts
                if hasattr(session, 'list_prompts'):
                    await session.list_prompts()

                capabilities = {
                    "tools": True,
                    "resources": True,
                    "prompts": True
                }
            except Exception as e:
                logger.warning(f"获取服务器 {name} 能力时出错: {e}")
                capabilities = None

            return ConnectedClient(
                name=name,
                session=session,
                config=config,
                capabilities=capabilities
            )

        except Exception as e:
            # 清理资源
            try:
                await session.close()
            except:
                pass
            raise TransportError(f"会话初始化失败: {str(e)}")

    def get_connected_clients(self) -> List[ConnectedClient]:
        """获取所有已连接的客户端"""
        return [
            client for client in self._clients.values()
            if isinstance(client, ConnectedClient)
        ]

    def get_client(self, name: str) -> Optional[WrappedClient]:
        """根据名称获取客户端"""
        return self._clients.get(name)

    async def close_all(self):
        """关闭所有连接"""
        for client in self._clients.values():
            if isinstance(client, ConnectedClient):
                try:
                    await client.session.close()
                except Exception as e:
                    logger.error(f"关闭客户端 {client.name} 时出错: {e}")
        self._clients.clear()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect_all()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close_all()


async def get_mcp_tools(
    client: MCPClient
) -> List[Dict[str, Any]]:
    """
    从所有已连接的 MCP 客户端获取工具列表

    Args:
        client: MCP 客户端管理器

    Returns:
        工具信息列表
    """
    tools = []

    for connected_client in client.get_connected_clients():
        try:
            tools_response = await connected_client.session.list_tools()

            for tool in tools_response.tools:
                # 标准化工具名称
                tool_name = _sanitize_mcp_name(
                    f"mcp__{connected_client.name}__{tool.name}"
                )

                tools.append({
                    "name": tool_name,
                    "original_name": tool.name,
                    "server": connected_client.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema,
                    "is_read_only": getattr(tool, 'annotations', {}) \
                        .get('readOnlyHint', False) if hasattr(tool, 'annotations') else False,
                })

        except Exception as e:
            logger.error(
                f"获取服务器 {connected_client.name} 的工具列表失败: {e}"
            )

    return tools


async def get_mcp_resources(
    client: MCPClient
) -> List[Dict[str, Any]]:
    """
    从所有已连接的 MCP 客户端获取资源列表

    Args:
        client: MCP 客户端管理器

    Returns:
        资源信息列表
    """
    resources = []

    for connected_client in client.get_connected_clients():
        try:
            resources_response = await connected_client.session.list_resources()

            for resource in resources_response.resources:
                resources.append({
                    "uri": resource.uri,
                    "name": resource.name,
                    "description": resource.description or "",
                    "mime_type": resource.mimeType,
                    "server": connected_client.name,
                })

        except Exception as e:
            logger.error(
                f"获取服务器 {connected_client.name} 的资源列表失败: {e}"
            )

    return resources


async def get_mcp_prompts(
    client: MCPClient
) -> List[Dict[str, Any]]:
    """
    从所有已连接的 MCP 客户端获取提示模板列表

    Args:
        client: MCP 客户端管理器

    Returns:
        提示模板信息列表
    """
    prompts = []

    for connected_client in client.get_connected_clients():
        try:
            prompts_response = await connected_client.session.list_prompts()

            for prompt in prompts_response.prompts:
                prompts.append({
                    "name": _sanitize_mcp_name(
                        f"mcp__{connected_client.name}__{prompt.name}"
                    ),
                    "original_name": prompt.name,
                    "server": connected_client.name,
                    "description": prompt.description or "",
                    "arguments": prompt.arguments or [],
                })

        except Exception as e:
            logger.error(
                f"获取服务器 {connected_client.name} 的提示列表失败: {e}"
            )

    return prompts


def _sanitize_mcp_name(name: str) -> str:
    """
    清理 MCP 标识符，确保只包含安全字符

    Args:
        name: 原始名称

    Returns:
        清理后的名称
    """
    import re
    # 将非字母数字、下划线、连字符的字符替换为下划线
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)
```

### 4. 工具调用执行器

```python
# src/client/executor.py
import asyncio
import logging
from typing import Any, Dict, Optional
from dataclasses import dataclass

from mcp import types

from .types import ConnectedClient
from .mcp_client import _sanitize_mcp_name


logger = logging.getLogger(__name__)


@dataclass
class ToolCallResult:
    """工具调用结果"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    is_error: bool = False
    content: Optional[list] = None


class MCPToolExecutor:
    """
    MCP 工具执行器

    负责执行 MCP 工具调用并处理结果。
    """

    def __init__(self, clients: Dict[str, ConnectedClient]):
        """
        初始化工具执行器

        Args:
            clients: 服务器名称到 ConnectedClient 的映射
        """
        self.clients = clients

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: Optional[float] = None
    ) -> ToolCallResult:
        """
        调用 MCP 工具

        Args:
            tool_name: 工具名称（格式：mcp__{server}__{tool}）
            arguments: 工具参数
            timeout: 超时时间（秒）

        Returns:
            ToolCallResult 实例
        """
        # 解析工具名称
        parts = tool_name.split('__')
        if len(parts) < 3 or parts[0] != 'mcp':
            return ToolCallResult(
                success=False,
                error=f"无效的工具名称格式: {tool_name}"
            )

        server_name = parts[1]
        original_tool_name = '__'.join(parts[2:])

        # 查找客户端
        client = self.clients.get(server_name)
        if not client:
            return ToolCallResult(
                success=False,
                error=f"未找到服务器: {server_name}"
            )

        # 执行工具调用
        try:
            if timeout:
                result = await asyncio.wait_for(
                    client.session.call_tool(original_tool_name, arguments),
                    timeout=timeout
                )
            else:
                result = await client.session.call_tool(
                    original_tool_name,
                    arguments
                )

            # 处理结果
            return self._process_tool_result(result)

        except asyncio.TimeoutError:
            return ToolCallResult(
                success=False,
                error=f"工具调用超时 ({timeout}s)"
            )
        except Exception as e:
            logger.error(f"调用工具 {tool_name} 时出错: {e}")
            return ToolCallResult(
                success=False,
                error=str(e)
            )

    def _process_tool_result(self, result: Any) -> ToolCallResult:
        """
        处理工具调用结果

        Args:
            result: MCP 工具调用原始结果

        Returns:
            处理后的 ToolCallResult
        """
        # 检查是否是错误结果
        if hasattr(result, 'isError') and result.isError:
            error_msg = ""
            if hasattr(result, 'content') and result.content:
                for item in result.content:
                    if hasattr(item, 'text'):
                        error_msg += item.text
            return ToolCallResult(
                success=False,
                error=error_msg or "工具调用返回错误",
                is_error=True
            )

        # 提取内容
        content = None
        structured_content = None
        if hasattr(result, 'content'):
            content = result.content
        if hasattr(result, 'structuredContent'):
            structured_content = result.structuredContent

        # 处理不同类型的内容
        extracted_data = []
        if content:
            for item in content:
                if isinstance(item, types.TextContent):
                    extracted_data.append({
                        "type": "text",
                        "text": item.text
                    })
                elif isinstance(item, types.ImageContent):
                    extracted_data.append({
                        "type": "image",
                        "data": item.data,
                        "mime_type": item.mimeType
                    })
                elif isinstance(item, types.ResourceContents):
                    extracted_data.append({
                        "type": "resource",
                        "uri": item.uri
                    })

        return ToolCallResult(
            success=True,
            data=structured_content or extracted_data,
            content=extracted_data
        )

    async def read_resource(
        self,
        uri: str,
        timeout: Optional[float] = None
    ) -> ToolCallResult:
        """
        读取 MCP 资源

        Args:
            uri: 资源 URI
            timeout: 超时时间（秒）

        Returns:
            ToolCallResult 实例
        """
        # 查找包含该资源的客户端
        client = None
        for c in self.clients.values():
            try:
                resources = await c.session.list_resources()
                resource_uris = [r.uri for r in resources.resources]
                if uri in resource_uris:
                    client = c
                    break
            except:
                continue

        if not client:
            return ToolCallResult(
                success=False,
                error=f"未找到资源: {uri}"
            )

        try:
            if timeout:
                result = await asyncio.wait_for(
                    client.session.read_resource(uri),
                    timeout=timeout
                )
            else:
                result = await client.session.read_resource(uri)

            # 处理结果
            contents = []
            for item in result.contents:
                if isinstance(item, types.TextContent):
                    contents.append({
                        "type": "text",
                        "text": item.text,
                        "uri": str(uri)
                    })
                elif isinstance(item, types.BlobResourceContents):
                    contents.append({
                        "type": "blob",
                        "uri": str(uri),
                        "mime_type": item.mimeType
                    })

            return ToolCallResult(
                success=True,
                data=contents,
                content=contents
            )

        except asyncio.TimeoutError:
            return ToolCallResult(
                success=False,
                error=f"读取资源超时 ({timeout}s)"
            )
        except Exception as e:
            return ToolCallResult(
                success=False,
                error=str(e)
            )

    async def get_prompt(
        self,
        prompt_name: str,
        arguments: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> ToolCallResult:
        """
        获取 MCP 提示模板

        Args:
            prompt_name: 提示名称（格式：mcp__{server}__{prompt}）
            arguments: 提示参数
            timeout: 超时时间（秒）

        Returns:
            ToolCallResult 实例
        """
        # 解析提示名称
        parts = prompt_name.split('__')
        if len(parts) < 3 or parts[0] != 'mcp':
            return ToolCallResult(
                success=False,
                error=f"无效的提示名称格式: {prompt_name}"
            )

        server_name = parts[1]
        original_prompt_name = '__'.join(parts[2:])

        # 查找客户端
        client = self.clients.get(server_name)
        if not client:
            return ToolCallResult(
                success=False,
                error=f"未找到服务器: {server_name}"
            )

        try:
            if timeout:
                result = await asyncio.wait_for(
                    client.session.get_prompt(
                        original_prompt_name,
                        arguments or {}
                    ),
                    timeout=timeout
                )
            else:
                result = await client.session.get_prompt(
                    original_prompt_name,
                    arguments or {}
                )

            # 处理结果
            messages = []
            for msg in result.messages:
                content = msg.content
                if isinstance(content, types.TextContent):
                    messages.append({
                        "role": msg.role,
                        "content": content.text
                    })
                elif isinstance(content, types.ImageContent):
                    messages.append({
                        "role": msg.role,
                        "content": {
                            "type": "image",
                            "data": content.data,
                            "mime_type": content.mimeType
                        }
                    })

            return ToolCallResult(
                success=True,
                data=messages,
                content=messages
            )

        except asyncio.TimeoutError:
            return ToolCallResult(
                success=False,
                error=f"获取提示超时 ({timeout}s)"
            )
        except Exception as e:
            return ToolCallResult(
                success=False,
                error=str(e)
            )
```

---

## 传输层实现

### 1. stdio 传输

```python
# examples/stdio_client.py
import asyncio
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


async def main():
    # 配置 stdio 服务器参数
    server_params = StdioServerParameters(
        command="npx",
        args=[
            "-y",
            "@modelcontextprotocol/server-filesystem",
            "/path/to/allowed/files"
        ],
        env=None  # 可选的环境变量
    )

    # 创建 stdio 客户端
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 初始化连接
            await session.initialize()

            # 列出可用工具
            tools = await session.list_tools()
            print(f"可用工具: {[t.name for t in tools.tools]}")

            # 调用工具
            result = await session.call_tool(
                "read_file",
                {"path": "/path/to/file.txt"}
            )

            for content in result.content:
                if hasattr(content, 'text'):
                    print(f"结果: {content.text}")


if __name__ == "__main__":
    asyncio.run(main())
```

### 2. SSE 传输

```python
# examples/sse_client.py
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client


async def main():
    # SSE 服务器 URL
    url = "https://your-sse-server.com/sse"
    headers = {
        "Authorization": "Bearer your-token"
    }

    # 创建 SSE 客户端
    async with sse_client(url, headers=headers) as (read, write):
        async with ClientSession(read, write) as session:
            # 初始化连接
            await session.initialize()

            # 列出可用工具
            tools = await session.list_tools()
            print(f"可用工具: {[t.name for t in tools.tools]}")


if __name__ == "__main__":
    asyncio.run(main())
```

### 3. WebSocket 传输

```python
# examples/websocket_client.py
import asyncio
from mcp import ClientSession
from mcp.client.websocket import websocket_client


async def main():
    # WebSocket 服务器 URL
    url = "ws://localhost:8000/mcp"

    # 创建 WebSocket 客户端
    async with websocket_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            # 初始化连接
            await session.initialize()

            # 列出可用工具
            tools = await session.list_tools()
            print(f"可用工具: {[t.name for t in tools.tools]}")

            # 调用工具
            result = await session.call_tool("add", {"a": 5, "b": 3})
            print(f"结果: {result.content}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 工具集成

### 工具基类

```python
# src/tools/base.py
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Coroutine


class Tool(ABC):
    """工具基类"""

    def __init__(self):
        self._name: str = ""
        self._description: str = ""
        self._input_schema: Dict[str, Any] = {}

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass

    @property
    def input_schema(self) -> Dict[str, Any]:
        """输入参数 JSON Schema"""
        return self._input_schema

    @abstractmethod
    async def call(self, arguments: Dict[str, Any]) -> Any:
        """
        执行工具

        Args:
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        pass

    @abstractmethod
    def is_read_only(self) -> bool:
        """是否为只读工具"""
        pass

    @abstractmethod
    def is_concurrency_safe(self) -> bool:
        """是否并发安全"""
        pass

    def needs_permission(self) -> bool:
        """是否需要用户权限"""
        return True
```

### MCP 工具包装器

```python
# src/tools/mcp_tool_wrapper.py
from typing import Any, Dict, Optional
from .base import Tool
from ..client.executor import MCPToolExecutor


class MCPToolWrapper(Tool):
    """
    MCP 工具包装器

    将 MCP 工具包装为统一的 Tool 接口。
    """

    def __init__(
        self,
        tool_name: str,
        original_name: str,
        server_name: str,
        description: str,
        input_schema: Dict[str, Any],
        is_read_only: bool,
        executor: MCPToolExecutor
    ):
        self._tool_name = tool_name
        self._original_name = original_name
        self._server_name = server_name
        self._description = description
        self._input_schema = input_schema
        self._is_read_only = is_read_only
        self._executor = executor

    @property
    def name(self) -> str:
        return self._tool_name

    @property
    def description(self) -> str:
        return self._description

    @property
    def input_schema(self) -> Dict[str, Any]:
        return self._input_schema

    def is_read_only(self) -> bool:
        return self._is_read_only

    def is_concurrency_safe(self) -> bool:
        return self._is_read_only

    async def call(self, arguments: Dict[str, Any]) -> Any:
        """执行 MCP 工具调用"""
        result = await self._executor.call_tool(
            self._tool_name,
            arguments
        )

        if not result.success:
            raise Exception(result.error or "工具调用失败")

        return result.data

    def user_facing_name(self) -> str:
        """用户友好的工具名称"""
        return f"{self._server_name} - {self._original_name} (MCP)"


class ToolFactory:
    """工具工厂"""

    @staticmethod
    def create_mcp_tools(
        executor: MCPToolExecutor,
        tools_info: list[Dict[str, Any]]
    ) -> list[Tool]:
        """
        批量创建 MCP 工具包装器

        Args:
            executor: 工具执行器
            tools_info: 工具信息列表

        Returns:
            工具列表
        """
        tools = []

        for info in tools_info:
            tool = MCPToolWrapper(
                tool_name=info["name"],
                original_name=info["original_name"],
                server_name=info["server"],
                description=info["description"],
                input_schema=info["input_schema"],
                is_read_only=info.get("is_read_only", False),
                executor=executor
            )
            tools.append(tool)

        return tools
```

---

## 配置管理

### 配置文件格式

```json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/allowed/path"],
      "env": {
        "NODE_ENV": "production"
      }
    },
    "postgres": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/db"]
    },
    "remote-sse": {
      "type": "sse",
      "url": "https://api.example.com/sse",
      "headers": {
        "Authorization": "Bearer token123"
      }
    },
    "websocket-server": {
      "type": "websocket",
      "url": "ws://localhost:8000/mcp",
      "auth_token": "optional-token"
    }
  }
}
```

### 配置管理器

```python
# src/config/manager.py
import json
import os
from typing import Dict, Optional, Any
from pathlib import Path
from dataclasses import dataclass

from ..client.types import MCPServerConfig


@dataclass
class ConfigLocations:
    """配置文件位置"""
    global_config: Path = Path.home() / ".config" / "mcp_python_client" / "config.json"
    project_config: Path = Path.cwd() / ".mcp.json"
    mcprc_config: Path = Path.cwd() / ".mcprc"


class ConfigManager:
    """MCP 配置管理器"""

    def __init__(self, locations: Optional[ConfigLocations] = None):
        self.locations = locations or ConfigLocations()
        self._cache: Dict[str, MCPServerConfig] = {}

    def load_all_configs(self) -> Dict[str, MCPServerConfig]:
        """
        加载所有配置来源

        Returns:
            合并后的服务器配置字典
        """
        configs = {}

        # 1. 加载全局配置
        if self.locations.global_config.exists():
            try:
                global_config = self._load_config_file(self.locations.global_config)
                configs.update(global_config)
            except Exception as e:
                print(f"警告: 加载全局配置失败: {e}")

        # 2. 加载项目配置
        if self.locations.project_config.exists():
            try:
                project_config = self._load_config_file(self.locations.project_config)
                configs.update(project_config)
            except Exception as e:
                print(f"警告: 加载项目配置失败: {e}")

        # 3. 加载 .mcprc 配置（需要批准）
        if self.locations.mcprc_config.exists():
            try:
                mcprc_config = self._load_config_file(self.locations.mcprc_config)
                # 只添加已批准的服务器
                approved = self._get_approved_servers()
                for name, config in mcprc_config.items():
                    if name in approved:
                        configs[name] = config
            except Exception as e:
                print(f"警告: 加载 .mcprc 配置失败: {e}")

        self._cache = configs
        return configs

    def _load_config_file(self, path: Path) -> Dict[str, MCPServerConfig]:
        """加载单个配置文件"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 支持 mcpServers 包装或直接配置
        servers = data.get("mcpServers", data)

        # 验证配置
        return self._validate_configs(servers)

    def _validate_configs(self, configs: Dict[str, Any]) -> Dict[str, MCPServerConfig]:
        """验证配置格式"""
        validated = {}

        for name, config in configs.items():
            if not isinstance(config, dict):
                raise ValueError(f"服务器 {name} 的配置必须是字典")

            transport_type = config.get("type")
            if transport_type not in ("stdio", "sse", "websocket"):
                raise ValueError(
                    f"服务器 {name} 的 type 必须是 stdio、sse 或 websocket"
                )

            validated[name] = config

        return validated

    def _get_approved_servers(self) -> set[str]:
        """获取已批准的 .mcprc 服务器列表"""
        approved_file = Path.home() / ".config" / "mcp_python_client" / "approved_mcprc.json"

        if approved_file.exists():
            try:
                with open(approved_file, "r") as f:
                    data = json.load(f)
                    return set(data.get("approved", []))
            except:
                pass

        return set()

    def add_server(
        self,
        name: str,
        config: MCPServerConfig,
        scope: str = "project"
    ):
        """
        添加服务器配置

        Args:
            name: 服务器名称
            config: 服务器配置
            scope: 配置作用域 (global/project/mcprc)
        """
        if scope == "global":
            config_file = self.locations.global_config
        elif scope == "mcprc":
            config_file = self.locations.mcprc_config
        else:
            config_file = self.locations.project_config

        # 确保目录存在
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # 加载现有配置
        existing = {}
        if config_file.exists():
            existing = self._load_config_file(config_file)

        # 添加新服务器
        existing[name] = config

        # 保存配置
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": existing}, f, indent=2)

        # 清除缓存
        self._cache.clear()

    def remove_server(self, name: str, scope: str = "project"):
        """
        移除服务器配置

        Args:
            name: 服务器名称
            scope: 配置作用域
        """
        if scope == "global":
            config_file = self.locations.global_config
        elif scope == "mcprc":
            config_file = self.locations.mcprc_config
        else:
            config_file = self.locations.project_config

        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_file}")

        # 加载现有配置
        existing = self._load_config_file(config_file)

        # 移除服务器
        if name not in existing:
            raise ValueError(f"服务器不存在: {name}")

        del existing[name]

        # 保存配置
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": existing}, f, indent=2)

        # 清除缓存
        self._cache.clear()

    def list_servers(self) -> Dict[str, MCPServerConfig]:
        """列出所有服务器配置"""
        if not self._cache:
            self.load_all_configs()
        return self._cache.copy()
```

---

## 安全机制

### 超时控制

```python
# src/utils/timeout.py
import asyncio
from typing import Optional, Coroutine, TypeVar


T = TypeVar('T')


async def with_timeout(
    coro: Coroutine[Any, Any, T],
    timeout: Optional[float],
    default: Optional[T] = None
) -> T:
    """
    为协程添加超时控制

    Args:
        coro: 要执行的协程
        timeout: 超时时间（秒），None 表示不限制
        default: 超时时的默认返回值

    Returns:
        协程执行结果或默认值

    Raises:
        asyncio.TimeoutError: 超时且未提供默认值
    """
    if timeout is None:
        return await coro

    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        if default is not None:
            return default
        raise


class TimeoutManager:
    """超时管理器"""

    def __init__(
        self,
        connection_timeout: float = 30.0,
        tool_timeout: Optional[float] = None
    ):
        self.connection_timeout = connection_timeout
        self.tool_timeout = tool_timeout

    async def run_with_connection_timeout(
        self,
        coro: Coroutine[Any, Any, T]
    ) -> T:
        """使用连接超时运行协程"""
        return await with_timeout(coro, self.connection_timeout)

    async def run_with_tool_timeout(
        self,
        coro: Coroutine[Any, Any, T]
    ) -> T:
        """使用工具超时运行协程"""
        return await with_timeout(coro, self.tool_timeout)
```

### 权限控制

```python
# src/utils/permissions.py
from enum import Enum
from typing import Set, Dict, Optional


class PermissionLevel(str, Enum):
    """权限级别"""
    SAFE = "safe"       # 安全模式，需要确认
    YOLO = "yolo"       # 自动批准所有操作


class PermissionManager:
    """权限管理器"""

    # 危险工具列表
    DANGEROUS_TOOLS: Set[str] = {
        "write_file",
        "delete_file",
        "execute_command",
        "database_write",
    }

    # 允许的 IDE MCP 工具白名单
    IDE_MCP_TOOL_ALLOWLIST: Set[str] = {
        "mcp__ide__execute_code",
        "mcp__ide__get_diagnostics",
    }

    def __init__(self, permission_level: PermissionLevel = PermissionLevel.SAFE):
        self.permission_level = permission_level
        self.approved_tools: Set[str] = set()

    def needs_permission(self, tool_name: str) -> bool:
        """
        检查工具是否需要权限

        Args:
            tool_name: 工具名称

        Returns:
            是否需要权限
        """
        # YOLO 模式下不需要权限
        if self.permission_level == PermissionLevel.YOLO:
            return False

        # 已批准的工具不需要权限
        if tool_name in self.approved_tools:
            return False

        # IDE MCP 工具检查
        if tool_name.startswith("mcp__ide__"):
            return tool_name not in self.IDE_MCP_TOOL_ALLOWLIST

        # 危险工具需要权限
        base_name = tool_name.split("__")[-1]
        return base_name in self.DANGEROUS_TOOLS

    def approve_tool(self, tool_name: str):
        """批准工具"""
        self.approved_tools.add(tool_name)

    def revoke_tool(self, tool_name: str):
        """撤销工具批准"""
        self.approved_tools.discard(tool_name)

    def is_tool_allowed(self, tool_name: str) -> bool:
        """
        检查工具是否允许执行

        Args:
            tool_name: 工具名称

        Returns:
            是否允许执行
        """
        # IDE MCP 工具白名单检查
        if tool_name.startswith("mcp__ide__"):
            return tool_name in self.IDE_MCP_TOOL_ALLOWLIST

        return True
```

---

## 完整示例

### 完整的 MCP 客户端使用示例

```python
# examples/complete_client.py
import asyncio
import logging
from pathlib import Path

from src.client.mcp_client import MCPClient, get_mcp_tools, get_mcp_resources
from src.client.executor import MCPToolExecutor
from src.tools.mcp_tool_wrapper import ToolFactory
from src.config.manager import ConfigManager
from src.utils.permissions import PermissionManager, PermissionLevel


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """完整的 MCP 客户端使用示例"""

    # 1. 加载配置
    config_manager = ConfigManager()
    servers = config_manager.load_all_configs()

    logger.info(f"加载了 {len(servers)} 个 MCP 服务器配置")

    # 2. 创建客户端
    client = MCPClient(
        servers=servers,
        connection_timeout=30.0,
        connection_batch_size=3
    )

    # 3. 连接所有服务器
    async with client:
        connected = client.get_connected_clients()
        logger.info(f"成功连接 {len(connected)} 个服务器")

        for c in connected:
            logger.info(f"  - {c.name} ({c.config['type']})")

        # 4. 获取所有工具
        tools_info = await get_mcp_tools(client)
        logger.info(f"发现 {len(tools_info)} 个工具")

        # 5. 创建工具执行器
        clients_map = {c.name: c for c in connected}
        executor = MCPToolExecutor(clients_map)

        # 6. 创建工具包装器
        tools = ToolFactory.create_mcp_tools(executor, tools_info)

        # 7. 使用工具
        permission_manager = PermissionManager(PermissionLevel.SAFE)

        for tool in tools[:3]:  # 只展示前 3 个工具
            print(f"\n工具名称: {tool.user_facing_name()}")
            print(f"描述: {tool.description}")
            print(f"只读: {tool.is_read_only()}")

            # 检查权限
            if permission_manager.needs_permission(tool.name):
                logger.info(f"工具 {tool.name} 需要权限批准")
                # 在实际应用中，这里应该请求用户确认
                permission_manager.approve_tool(tool.name)

            # 示例：调用 read_file 工具
            if "read_file" in tool.name:
                try:
                    result = await tool.call({"path": "/path/to/file.txt"})
                    print(f"调用结果: {result}")
                except Exception as e:
                    logger.error(f"工具调用失败: {e}")

        # 8. 获取资源
        resources = await get_mcp_resources(client)
        logger.info(f"发现 {len(resources)} 个资源")

        for resource in resources[:5]:  # 只展示前 5 个资源
            print(f"\n资源: {resource['name']}")
            print(f"URI: {resource['uri']}")
            print(f"描述: {resource['description']}")

            # 读取资源内容
            try:
                result = await executor.read_resource(resource['uri'])
                if result.success:
                    print(f"内容: {result.data}")
            except Exception as e:
                logger.error(f"读取资源失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())
```

### 简化的快速开始示例

```python
# examples/quickstart.py
"""
MCP Python 客户端快速开始

运行前请先安装依赖:
    pip install mcp

然后运行:
    python quickstart.py
"""

import asyncio
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


async def quickstart():
    """最简化的 MCP 客户端示例"""

    # 配置服务器（使用官方 filesystem 服务器）
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "."]
    )

    # 连接并使用
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 1. 初始化
            await session.initialize()

            # 2. 列出工具
            tools = await session.list_tools()
            print("=== 可用工具 ===")
            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description}")

            # 3. 列出资源
            resources = await session.list_resources()
            print("\n=== 可用资源 ===")
            for resource in resources.resources[:5]:
                print(f"  - {resource.uri}")

            # 4. 调用工具
            if tools.tools:
                tool_name = tools.tools[0].name
                print(f"\n=== 调用工具: {tool_name} ===")

                # 根据工具类型调用
                if "read_file" in tool_name:
                    result = await session.call_tool(
                        tool_name,
                        {"path": "quickstart.py"}
                    )
                    for content in result.content:
                        if hasattr(content, 'text'):
                            print(f"结果: {content.text[:200]}...")
                elif "list" in tool_name:
                    result = await session.call_tool(tool_name, {})
                    for content in result.content:
                        if hasattr(content, 'text'):
                            print(f"结果: {content.text}")


if __name__ == "__main__":
    print("MCP Python 客户端快速开始示例\n")
    asyncio.run(quickstart())
```

---

## 总结

### Python MCP 客户端实现要点

| 方面 | 说明 |
|------|------|
| **异步编程** | 全面使用 `asyncio` 和 `async/await` |
| **类型安全** | 使用 `typing` 和 `TypedDict` 定义类型 |
| **错误处理** | 统一的异常处理和错误传播 |
| **资源管理** | 使用异步上下文管理器确保资源释放 |
| **可扩展性** | 抽象基类和工厂模式支持扩展 |

### 与 Kode TypeScript 实现的对比

| 特性 | Kode (TypeScript) | Python SDK |
|------|-------------------|------------|
| **传输层** | 内置 4 种传输 | 内置 3 种传输 |
| **批量连接** | 支持 | 需要自己实现 |
| **超时控制** | 内置 | 需要使用 asyncio.wait_for |
| **配置管理** | 复杂的多源配置 | 需要自己实现 |
| **工具包装** | 自动转换 | 需要自己包装 |

### 下一步

1. 根据实际需求调整配置管理
2. 实现更复杂的权限控制
3. 添加重试和故障恢复机制
4. 集成到你的 AI 应用中
