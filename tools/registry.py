"""工具注册表 - HelloAgents原生工具系统

包含迁移期适配器，用于将旧格式响应转换为《通用工具响应协议》格式。
"""

import json
import os
import logging
from typing import Optional, Any, Callable

from .base import Tool, ToolStatus, ErrorCode

# 设置日志
logger = logging.getLogger(__name__)

# 环境变量控制适配器开关（默认启用）
ENABLE_LEGACY_ADAPTER = os.environ.get("ENABLE_LEGACY_ADAPTER", "true").lower() == "true"


class ToolRegistry:
    """
    HelloAgents工具注册表

    提供工具的注册、管理和执行功能。
    支持两种工具注册方式：
    1. Tool对象注册（推荐）
    2. 函数直接注册（简便）
    
    包含迁移期适配器，用于将旧格式响应转换为协议格式。
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._functions: dict[str, dict[str, Any]] = {}


    def register_tool(self, tool: Tool):
        """
        注册Tool对象

        Args:
            tool: Tool实例
        """
        if tool.name in self._tools:
            print(f"⚠️ 警告：工具 '{tool.name}' 已存在，将被覆盖。")

        self._tools[tool.name] = tool
        print(f"✅ 工具 '{tool.name}' 已注册。")

    def register_function(self, name: str, description: str, func: Callable[[str], str]):
        """
        直接注册函数作为工具（简便方式）

        Args:
            name: 工具名称
            description: 工具描述
            func: 工具函数，接受字符串参数，返回字符串结果
        """
        if name in self._functions:
            print(f"⚠️ 警告：工具 '{name}' 已存在，将被覆盖。")

        self._functions[name] = {
            "description": description,
            "func": func
        }
        print(f"✅ 工具 '{name}' 已注册。")

    def unregister(self, name: str):
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            print(f"🗑️ 工具 '{name}' 已注销。")
        elif name in self._functions:
            del self._functions[name]
            print(f"🗑️ 工具 '{name}' 已注销。")
        else:
            print(f"⚠️ 工具 '{name}' 不存在。")

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
        result_str = ""
        
        # 优先查找Tool对象
        if name in self._tools:
            tool = self._tools[name]
            try:
                # 如果是字典，直接传入；否则包装为input
                if isinstance(input_text, dict):
                    parameters = input_text
                else:
                    parameters = {"input": input_text}
                result_str = tool.run(parameters)
            except Exception as e:
                # 工具执行异常，返回协议格式的错误响应
                return self._create_internal_error_response(
                    name=name,
                    message=f"执行工具 '{name}' 时发生异常: {str(e)}",
                    params_input=parameters if 'parameters' in dir() else {},
                )

        # 查找函数工具
        elif name in self._functions:
            func = self._functions[name]["func"]
            try:
                result_str = func(input_text)
            except Exception as e:
                return self._create_internal_error_response(
                    name=name,
                    message=f"执行工具 '{name}' 时发生异常: {str(e)}",
                    params_input={"input": input_text} if not isinstance(input_text, dict) else input_text,
                )

        else:
            return self._create_internal_error_response(
                name=name,
                message=f"未找到名为 '{name}' 的工具。",
                params_input={},
            )
        
        # 应用迁移适配器
        if ENABLE_LEGACY_ADAPTER:
            result_str = self._apply_legacy_adapter(name, result_str, input_text)
        
        return result_str
    
    def _apply_legacy_adapter(self, tool_name: str, result_str: str, params_input: Any) -> str:
        """
        迁移期适配器：将旧格式响应转换为《通用工具响应协议》格式
        
        检测逻辑：
        1. 尝试解析 JSON
        2. 检查是否有 status 字段
        3. 如果没有，转换为新格式
        4. 如果解析失败，包装为 error 响应
        
        Args:
            tool_name: 工具名称
            result_str: 工具返回的原始字符串
            params_input: 原始输入参数
            
        Returns:
            符合协议的 JSON 字符串
        """
        try:
            parsed = json.loads(result_str)
        except json.JSONDecodeError:
            # 无法解析 JSON → 包装为 error
            logger.warning(
                f"[LegacyAdapter] Tool '{tool_name}' returned invalid JSON. "
                f"Wrapping as INTERNAL_ERROR."
            )
            return self._create_internal_error_response(
                name=tool_name,
                message=f"Tool returned invalid JSON: {result_str[:100]}...",
                params_input=params_input if isinstance(params_input, dict) else {"input": params_input},
            )
        
        # 检查是否已符合协议
        if "status" in parsed:
            # 已经是新格式，直接返回
            return result_str
        
        # 旧格式检测与转换
        logger.warning(
            f"[LegacyAdapter] Tool '{tool_name}' returned legacy format. "
            f"Detected fields: {list(parsed.keys())}. Auto-converting..."
        )
        
        return self._convert_legacy_to_protocol(tool_name, parsed, params_input)
    
    def _convert_legacy_to_protocol(self, tool_name: str, parsed: dict, params_input: Any) -> str:
        """
        将旧格式响应转换为协议格式
        
        旧格式特征：
        - items / matches / error (string) / flags / warnings
        
        Args:
            tool_name: 工具名称
            parsed: 解析后的旧格式字典
            params_input: 原始输入参数
            
        Returns:
            符合协议的 JSON 字符串
        """
        # 检测是否为错误响应（旧格式：error 是字符串）
        if "error" in parsed and isinstance(parsed["error"], str):
            error_message = parsed["error"]
            # 尝试推断错误码
            error_code = ErrorCode.INTERNAL_ERROR.value
            if "not exist" in error_message.lower() or "not found" in error_message.lower():
                error_code = ErrorCode.NOT_FOUND.value
            elif "access denied" in error_message.lower() or "permission" in error_message.lower():
                error_code = ErrorCode.ACCESS_DENIED.value
            elif "invalid" in error_message.lower() or "must be" in error_message.lower():
                error_code = ErrorCode.INVALID_PARAM.value
            elif "timeout" in error_message.lower():
                error_code = ErrorCode.TIMEOUT.value
            
            return json.dumps({
                "status": ToolStatus.ERROR.value,
                "data": {},
                "text": error_message,
                "error": {
                    "code": error_code,
                    "message": error_message,
                },
                "stats": parsed.get("stats", {"time_ms": 0}),
                "context": {
                    "cwd": ".",
                    "params_input": params_input if isinstance(params_input, dict) else {"input": params_input},
                    **parsed.get("context", {}),
                },
            }, ensure_ascii=False, indent=2)
        
        # 非错误响应：构建 data
        data = {}
        
        # LS 工具：items → entries
        if "items" in parsed:
            # 旧格式的 items 是 display 字符串数组
            # 需要转换为 {path, type} 对象数组
            items = parsed["items"]
            entries = []
            for item in items:
                if isinstance(item, str):
                    # 简单推断类型
                    if item.endswith("/"):
                        entries.append({"path": item.rstrip("/"), "type": "dir"})
                    elif "@" in item:
                        entries.append({"path": item.split("@")[0], "type": "link"})
                    else:
                        entries.append({"path": item, "type": "file"})
                elif isinstance(item, dict):
                    entries.append(item)
            data["entries"] = entries
        
        # Glob 工具：matches → paths
        if "matches" in parsed and not "items" in parsed:
            matches = parsed["matches"]
            if matches and isinstance(matches[0], str):
                # Glob 的 matches 是字符串数组
                data["paths"] = matches
            else:
                # Grep 的 matches 是对象数组
                data["matches"] = matches
        
        # 截断标记
        flags = parsed.get("flags", {})
        if flags.get("truncated"):
            data["truncated"] = True
        else:
            data["truncated"] = False
        
        if flags.get("aborted_reason"):
            data["aborted_reason"] = flags["aborted_reason"]
        
        # 判断状态
        truncated = data.get("truncated", False)
        aborted = data.get("aborted_reason") is not None
        status = ToolStatus.PARTIAL.value if (truncated or aborted) else ToolStatus.SUCCESS.value
        
        # 构建响应
        response = {
            "status": status,
            "data": data,
            "text": parsed.get("text", ""),
            "stats": {
                "time_ms": parsed.get("stats", {}).get("time_ms", 0),
                **{k: v for k, v in parsed.get("stats", {}).items() if k != "time_ms"},
            },
            "context": {
                "cwd": ".",
                "params_input": params_input if isinstance(params_input, dict) else {"input": params_input},
                "path_resolved": parsed.get("context", {}).get("root_resolved", "."),
                **{k: v for k, v in parsed.get("context", {}).items() if k != "root_resolved"},
            },
        }
        
        logger.info(
            f"[LegacyAdapter] Tool '{tool_name}' converted successfully. "
            f"status={status}, data_keys={list(data.keys())}"
        )
        
        return json.dumps(response, ensure_ascii=False, indent=2)
    
    def _create_internal_error_response(self, name: str, message: str, params_input: dict) -> str:
        """创建内部错误响应（符合协议）"""
        return json.dumps({
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
        }, ensure_ascii=False, indent=2)

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

    def get_all_tools(self) -> list[Tool]:
        """获取所有Tool对象"""
        return list(self._tools.values())

    def clear(self):
        """清空所有工具"""
        self._tools.clear()
        self._functions.clear()
        print("🧹 所有工具已清空。")

# 全局工具注册表
global_registry = ToolRegistry()
