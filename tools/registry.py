"""工具注册表 - HelloAgents原生工具系统

包含乐观锁自动注入机制，框架自动管理 Read 元信息缓存。
"""

import json
import time
import logging
import os
from typing import Optional, Any, Callable, TypedDict

from .base import Tool, ToolStatus, ErrorCode, ToolParameter
from .circuit_breaker import CircuitBreaker
from core.env import load_env

load_env()

# 设置日志
logger = logging.getLogger(__name__)


class ReadMeta(TypedDict):
    """Read 操作的元信息（用于乐观锁自动注入）"""
    path_resolved: str        # 解析后的规范化路径（主键）
    file_mtime_ms: int        # 文件修改时间（毫秒）
    file_size_bytes: int      # 文件大小（字节）
    captured_at: float        # 缓存时间戳（用于调试/过期策略）


class ToolRegistry:
    """
    HelloAgents工具注册表

    提供工具的注册、管理和执行功能。
    支持两种工具注册方式：
    1. Tool对象注册（推荐）
    2. 函数直接注册（简便）
    
    包含乐观锁自动注入机制，自动管理 Read 元信息缓存。
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._functions: dict[str, dict[str, Any]] = {}
        # Read 元信息缓存（用于乐观锁自动注入）
        # key: path_resolved 或原始 path
        self._read_cache: dict[str, ReadMeta] = {}
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=int(os.getenv("CIRCUIT_FAILURE_THRESHOLD", "3")),
            recovery_timeout=int(os.getenv("CIRCUIT_RECOVERY_TIMEOUT", "300")),
        )


    def register_tool(self, tool: Tool):
        """
        注册Tool对象

        Args:
            tool: Tool实例
        """
        if tool.name in self._tools:
            logger.warning("工具 '%s' 已存在，将被覆盖。", tool.name)

        self._tools[tool.name] = tool
        logger.info("工具 '%s' 已注册。", tool.name)

    def register_function(self, name: str, description: str, func: Callable[[str], str]):
        """
        直接注册函数作为工具（简便方式）

        Args:
            name: 工具名称
            description: 工具描述
            func: 工具函数，接受字符串参数，返回字符串结果
        """
        if name in self._functions:
            logger.warning("工具 '%s' 已存在，将被覆盖。", name)

        self._functions[name] = {
            "description": description,
            "func": func
        }
        logger.info("工具 '%s' 已注册。", name)

    def unregister(self, name: str):
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            logger.info("工具 '%s' 已注销。", name)
        elif name in self._functions:
            del self._functions[name]
            logger.info("工具 '%s' 已注销。", name)
        else:
            logger.warning("工具 '%s' 不存在。", name)

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """
        构建 OpenAI function calling 所需的 tools 列表。

        Returns:
            list of {"type": "function", "function": {name, description, parameters}}
        """
        tools: list[dict[str, Any]] = []

        for tool in self._tools.values():
            if not self._circuit_breaker.is_available(tool.name):
                continue
            try:
                params = tool.get_parameters()
            except Exception:
                params = []
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": self._parameters_to_schema(params),
                },
            })

        for name, info in self._functions.items():
            if not self._circuit_breaker.is_available(name):
                continue
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": info.get("description", "") if isinstance(info, dict) else "",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "input": {
                                "type": "string",
                                "description": "raw input string",
                            }
                        },
                        "required": ["input"],
                        "additionalProperties": False,
                    },
                },
            })

        return tools

    @staticmethod
    def _parameters_to_schema(params: list[ToolParameter]) -> dict[str, Any]:
        """
        将 ToolParameter 列表转换为 JSON Schema。
        """
        if not isinstance(params, (list, tuple)):
            params = []
        properties: dict[str, Any] = {}
        required: list[str] = []
        for p in params or []:
            param_type = (p.type or "string").strip().lower()
            schema: dict[str, Any] = {
                "type": ToolRegistry._normalize_schema_type(param_type),
                "description": p.description or "",
            }
            if p.default is not None:
                schema["default"] = p.default
            properties[p.name] = schema
            if p.required:
                required.append(p.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    @staticmethod
    def _normalize_schema_type(param_type: str) -> str:
        """
        规范化参数类型到 JSON Schema 类型。
        """
        mapping = {
            "str": "string",
            "string": "string",
            "int": "integer",
            "integer": "integer",
            "float": "number",
            "number": "number",
            "bool": "boolean",
            "boolean": "boolean",
            "array": "array",
            "list": "array",
            "object": "object",
            "dict": "object",
        }
        return mapping.get(param_type, "string")

    def get_tool(self, name: str) -> Optional[Tool]:
        """获取Tool对象"""
        return self._tools.get(name)

    def get_function(self, name: str) -> Optional[Callable]:
        """获取工具函数"""
        func_info = self._functions.get(name)
        return func_info["func"] if func_info else None

    def execute_tool(self, name: str, input_text) -> str:
        """
        执行工具

        Args:
            name: 工具名称
            input_text: 输入参数

        Returns:
            工具执行结果（符合《通用工具响应协议》的 JSON 字符串）
        """
        result_payload: Optional[dict] = None
        
        # 准备参数
        if isinstance(input_text, dict):
            parameters = input_text.copy()  # 复制以避免修改原始参数
        else:
            parameters = {"input": input_text}
        
        # =====================================================================
        # 乐观锁自动注入：为 Write/Edit 注入 expected_mtime_ms / expected_size_bytes
        # =====================================================================
        if name in {"Write", "Edit", "MultiEdit"}:
            parameters = self._inject_optimistic_lock_params(name, parameters)
        
        # 熔断检查
        if not self._circuit_breaker.is_available(name):
            payload = {
                "status": ToolStatus.ERROR.value,
                "data": {},
                "text": f"工具 '{name}' 因连续失败被临时禁用。",
                "error": {
                    "code": ErrorCode.CIRCUIT_OPEN.value,
                    "message": f"工具 '{name}' 因连续失败被临时禁用。",
                },
                "stats": {"time_ms": 0},
                "context": {"cwd": ".", "params_input": parameters},
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)

        # 优先查找Tool对象
        if name in self._tools:
            tool = self._tools[name]
            try:
                result = tool.run(parameters)
                result_payload = self._normalize_result(name, result, parameters)
            except Exception as e:
                result_payload = self._create_internal_error_payload(
                    name=name,
                    message=f"执行工具 '{name}' 时发生异常: {str(e)}",
                    params_input=parameters,
                )

        # 查找函数工具
        elif name in self._functions:
            func = self._functions[name]["func"]
            try:
                result = func(input_text)
                result_payload = self._normalize_result(name, result, parameters)
            except Exception as e:
                result_payload = self._create_internal_error_payload(
                    name=name,
                    message=f"执行工具 '{name}' 时发生异常: {str(e)}",
                    params_input=parameters,
                )

        else:
            result_payload = self._create_internal_error_payload(
                name=name,
                message=f"未找到名为 '{name}' 的工具。",
                params_input={},
            )
        
        # 熔断记录
        if isinstance(result_payload, dict):
            status = result_payload.get("status")
            if status == ToolStatus.ERROR.value:
                err = result_payload.get("error", {}) or {}
                err_msg = err.get("message") if isinstance(err, dict) else None
                self._circuit_breaker.record_failure(name, str(err_msg or result_payload.get("text") or ""))
            else:
                self._circuit_breaker.record_success(name)
        
        # =====================================================================
        # 乐观锁缓存更新：记录 Read 结果的元信息
        # =====================================================================
        if name == "Read":
            self._cache_read_meta(result_payload, parameters)

        return json.dumps(result_payload, ensure_ascii=False, indent=2)

    def export_read_cache(self) -> dict[str, ReadMeta]:
        """导出 Read 缓存（用于会话持久）。"""
        return dict(self._read_cache)

    def import_read_cache(self, data: dict[str, ReadMeta]) -> None:
        """恢复 Read 缓存（用于会话持久）。"""
        if isinstance(data, dict):
            self._read_cache = dict(data)
    
    def _inject_optimistic_lock_params(self, tool_name: str, parameters: dict) -> dict:
        """
        为 Write/Edit 工具自动注入乐观锁参数
        
        如果参数中缺少 expected_mtime_ms / expected_size_bytes，
        尝试从 Read 缓存中查找并注入。
        
        Args:
            tool_name: 工具名称
            parameters: 原始参数
            
        Returns:
            注入后的参数（可能与原始相同）
        """
        # 如果已经提供了，不覆盖
        if "expected_mtime_ms" in parameters and "expected_size_bytes" in parameters:
            return parameters
        
        # 获取目标路径
        path = parameters.get("path")
        if not path:
            return parameters
        
        # 尝试从缓存查找（先用原始 path，再用规范化 path）
        meta = self._read_cache.get(path)
        if not meta:
            # 尝试规范化路径匹配
            # 注意：这里的规范化逻辑应与工具内部一致
            normalized_path = path.replace("\\", "/")
            if normalized_path.startswith("./"):
                normalized_path = normalized_path[2:]
            meta = self._read_cache.get(normalized_path)
        
        if meta:
            # 找到缓存，注入参数
            if "expected_mtime_ms" not in parameters:
                parameters["expected_mtime_ms"] = meta["file_mtime_ms"]
            if "expected_size_bytes" not in parameters:
                parameters["expected_size_bytes"] = meta["file_size_bytes"]
            logger.debug(
                f"[OptimisticLock] Auto-injected for {tool_name}: "
                f"mtime={meta['file_mtime_ms']}, size={meta['file_size_bytes']}, path={path}"
            )
        else:
            # 未找到缓存，让工具正常报错（提示先 Read）
            logger.debug(
                f"[OptimisticLock] No Read cache found for path '{path}'. "
                f"Tool will report INVALID_PARAM if file exists."
            )
        
        return parameters
    
    def _cache_read_meta(self, result: Any, params_input: dict) -> None:
        """
        缓存 Read 工具的元信息（用于后续 Write/Edit 的乐观锁校验）
        
        仅在 Read 成功或 partial 时缓存。
        
        Args:
            result_str: Read 工具的响应字符串
            params_input: 原始输入参数
        """
        if isinstance(result, dict):
            parsed = result
        else:
            try:
                parsed = json.loads(result)
            except json.JSONDecodeError:
                return
        
        # 仅缓存成功/partial 状态
        status = parsed.get("status")
        if status not in ("success", "partial"):
            return
        
        # 提取元信息
        stats = parsed.get("stats", {})
        context = parsed.get("context", {})
        
        file_mtime_ms = stats.get("file_mtime_ms")
        file_size_bytes = stats.get("file_size_bytes")
        path_resolved = context.get("path_resolved")
        
        # 必须同时有 mtime 和 size
        if file_mtime_ms is None or file_size_bytes is None:
            logger.warning(
                f"[OptimisticLock] Read response missing file_mtime_ms or file_size_bytes. "
                f"Skipping cache."
            )
            return
        
        # 构建缓存条目
        meta: ReadMeta = {
            "path_resolved": path_resolved or "",
            "file_mtime_ms": file_mtime_ms,
            "file_size_bytes": file_size_bytes,
            "captured_at": time.time(),
        }
        
        # 使用 path_resolved 作为主键
        if path_resolved:
            self._read_cache[path_resolved] = meta
        
        # 同时用原始 path 作为别名键（便于匹配）
        original_path = params_input.get("path")
        if original_path and original_path != path_resolved:
            self._read_cache[original_path] = meta
        
        logger.debug(
            f"[OptimisticLock] Cached Read meta: path={path_resolved}, "
            f"mtime={file_mtime_ms}, size={file_size_bytes}"
        )
    
    def clear_read_cache(self) -> None:
        """
        清空 Read 元信息缓存
        
        在需要重置乐观锁状态时调用（如新会话开始）。
        """
        self._read_cache.clear()
        logger.debug("[OptimisticLock] Read cache cleared.")
    
    def _normalize_result(self, tool_name: str, result: Any, params_input: Any) -> dict:
        if isinstance(result, dict):
            payload = result
        elif isinstance(result, str):
            try:
                payload = json.loads(result)
            except json.JSONDecodeError:
                return self._create_internal_error_payload(
                    name=tool_name,
                    message=f"Tool '{tool_name}' returned invalid JSON.",
                    params_input=params_input if isinstance(params_input, dict) else {"input": params_input},
                )
        else:
            return self._create_internal_error_payload(
                name=tool_name,
                message=f"Tool '{tool_name}' returned unsupported result type.",
                params_input=params_input if isinstance(params_input, dict) else {"input": params_input},
            )

        if not isinstance(payload, dict):
            return self._create_internal_error_payload(
                name=tool_name,
                message=f"Tool '{tool_name}' returned invalid payload.",
                params_input=params_input if isinstance(params_input, dict) else {"input": params_input},
            )

        status = payload.get("status")
        if status not in (ToolStatus.SUCCESS.value, ToolStatus.PARTIAL.value, ToolStatus.ERROR.value):
            return self._create_internal_error_payload(
                name=tool_name,
                message=f"Tool '{tool_name}' returned non-protocol response.",
                params_input=params_input if isinstance(params_input, dict) else {"input": params_input},
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            data = {}

        text = payload.get("text") or ""
        if not isinstance(text, str):
            text = str(text)

        stats = payload.get("stats")
        if not isinstance(stats, dict):
            stats = {}
        stats.setdefault("time_ms", 0)

        context = payload.get("context")
        if not isinstance(context, dict):
            context = {}
        context.setdefault("cwd", ".")
        if "params_input" not in context:
            context["params_input"] = (
                params_input if isinstance(params_input, dict) else {"input": params_input}
            )

        normalized = {
            "status": status,
            "data": data,
            "text": text,
            "stats": stats,
            "context": context,
        }

        if status == ToolStatus.ERROR.value:
            error = payload.get("error")
            if not isinstance(error, dict):
                error = {
                    "code": ErrorCode.INTERNAL_ERROR.value,
                    "message": text or "Tool execution error",
                }
            else:
                error.setdefault("code", ErrorCode.INTERNAL_ERROR.value)
                error.setdefault("message", text or "Tool execution error")
            normalized["error"] = error

        return normalized

    def _create_internal_error_payload(self, name: str, message: str, params_input: dict) -> dict:
        """创建内部错误响应 payload（符合协议）"""
        return {
            "status": ToolStatus.ERROR.value,
            "data": {},
            "text": message,
            "error": {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": message,
            },
            "stats": {"time_ms": 0},
            "context": {
                "cwd": ".",
                "params_input": params_input,
            },
        }

    def _create_internal_error_response(self, name: str, message: str, params_input: dict) -> str:
        """创建内部错误响应（符合协议）"""
        payload = self._create_internal_error_payload(name, message, params_input)
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def get_tools_description(self) -> str:
        """
        获取所有可用工具的格式化描述字符串

        Returns:
            工具描述字符串，用于构建提示词
        """
        descriptions = []

        # Tool对象描述
        for tool in self._tools.values():
            descriptions.append(f"- {tool.name}: {tool.description}")

        # 函数工具描述
        for name, info in self._functions.items():
            descriptions.append(f"- {name}: {info['description']}")

        return "\n".join(descriptions) if descriptions else "暂无可用工具"

    def list_tools(self) -> list[str]:
        """列出所有工具名称"""
        return list(self._tools.keys()) + list(self._functions.keys())

    def get_disabled_tools(self) -> list[str]:
        """获取当前被熔断禁用的工具列表。"""
        return self._circuit_breaker.get_disabled_tools()

    def get_all_tools(self) -> list[Tool]:
        """获取所有Tool对象"""
        return list(self._tools.values())

    def clear(self):
        """清空所有工具"""
        self._tools.clear()
        self._functions.clear()
        logger.info("所有工具已清空。")

# 全局工具注册表
global_registry = ToolRegistry()
