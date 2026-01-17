# MyCodeAgent 增强功能实现计划（Function Calling 版本）

## 概述

本计划围绕稳定性和可用性做 4 个核心增强，按优先级排序：
1. **AskUser 工具** - 缺信息时可互动获取，避免“卡住/瞎猜”
2. **MCP 错误分级** - 明确失败类型，帮助 LLM 正确决策
3. **轻量熔断机制** - 连续失败的工具自动降级
4. **Trace 脱敏** - 保护敏感信息，降低日志泄露风险

## 前置约束（必须统一）

- **只支持 OpenAI function calling**（`tool_calls`），不再解析 Action 文本。
- **工具响应必须遵守通用响应协议**（`status/data/text/stats/context/error`）。
- **Subagent 禁止阻塞式交互**（不能 `input()`），AskUser 仅主 Agent 允许。
- **工具列表由 `ToolRegistry.get_openai_tools()` 生成**，禁用工具必须从列表里剔除。

---

## 1. AskUser 工具（最小版）

### 目标
当 Agent 缺少关键信息时，可以向用户提问并继续执行，而不是终止或乱猜。

### 实现方案

#### 1.1 新建工具
**文件**: `tools/builtin/ask_user.py`

```python
class AskUserTool(Tool):
    name = "AskUser"
    description = "向用户提问并获取回答（仅主 Agent 允许交互）。"

    def get_parameters(self):
        return [
            ToolParameter(
                "questions",
                "array",
                "问题列表，每项为 {id, text, type, options?, required?}",
                required=True,
            ),
        ]

    def run(self, parameters):
        if not self.interactive:
            return self.create_error_response(
                error_code="ASK_USER_UNAVAILABLE",
                message="Subagent 禁止 AskUser 交互，请在主 Agent 处理。",
            )

        answers = []
        for item in parameters.get("questions", []):
            prompt = f"[Agent 问] {item.get('text', '')}\n> "
            answers.append({"id": item.get("id"), "answer": input(prompt)})

        return self.create_success_response(
            data={"answers": answers},
            text=f"用户已回答 {len(answers)} 个问题",
        )
```

#### 1.2 注册工具
**文件**: `agents/codeAgent.py`

```python
from tools.builtin.ask_user import AskUserTool

self.tool_registry.register_tool(
    AskUserTool(interactive=self.interactive)
)
```

#### 1.3 Prompt 提示
**文件**: `prompts/tools_prompts/ask_user_prompt.py`

```python
ask_user_prompt = """
## AskUser
当需要用户提供信息才能继续时使用此工具（如缺 API Key、路径、配置等）。

参数：
- questions: 问题列表，每项包含 id/text/type/options/required

示例（参数）：
{
  "questions": [
    {"id": "api_key", "text": "请提供 API Key", "type": "text", "required": true},
    {"id": "framework", "text": "项目使用什么框架？", "type": "text"}
  ]
}
"""
```

### 关键文件
- `tools/builtin/ask_user.py` (新建)
- `agents/codeAgent.py` (注册工具)
- `prompts/tools_prompts/ask_user_prompt.py` (新建)

---

## 2. MCP 错误语义分级

### 目标
区分参数错误/解析失败/执行失败/网络错误，帮助 LLM 决策重试或换策略。

### 实现方案

#### 2.1 扩展 ErrorCode 枚举
**文件**: `tools/base.py`

```python
class ErrorCode(str, Enum):
    INVALID_PARAM = "INVALID_PARAM"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    MCP_PARAM_ERROR = "MCP_PARAM_ERROR"
    MCP_PARSE_ERROR = "MCP_PARSE_ERROR"
    MCP_EXECUTION_ERROR = "MCP_EXECUTION_ERROR"
    MCP_NETWORK_ERROR = "MCP_NETWORK_ERROR"
    MCP_TIMEOUT = "MCP_TIMEOUT"
    MCP_NOT_FOUND = "MCP_NOT_FOUND"
```

#### 2.2 修改 MCP adapter 错误处理
**文件**: `tools/mcp/adapter.py`

```python
try:
    result = self._mcp_client.call_tool_sync(...)
except TimeoutError:
    return to_protocol_error(..., error_code=ErrorCode.MCP_TIMEOUT)
except ConnectionError:
    return to_protocol_error(..., error_code=ErrorCode.MCP_NETWORK_ERROR)
except Exception as e:
    return to_protocol_error(..., error_code=ErrorCode.MCP_EXECUTION_ERROR)

try:
    return to_protocol_result(result, ...)
except Exception as e:
    return to_protocol_error(..., error_code=ErrorCode.MCP_PARSE_ERROR)
```

#### 2.3 修改 protocol.py
**文件**: `tools/mcp/protocol.py`

- `to_protocol_error` 必须填充 `error.code/error.type/message`。
- 统一映射到 `param_error/parse_error/network_error/execution_error` 四类。

### 关键文件
- `tools/base.py`
- `tools/mcp/adapter.py`
- `tools/mcp/protocol.py`

---

## 3. 轻量熔断机制

### 目标
同一工具连续失败 N 次后临时禁用（本会话内），减少无效调用和 Token 浪费。

### 实现方案

#### 3.1 熔断器类
**文件**: `tools/circuit_breaker.py` (新建)

```python
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 300):
        ...

    def record_success(self, tool_name: str):
        ...

    def record_failure(self, tool_name: str, error: str = ""):
        ...

    def is_available(self, tool_name: str) -> bool:
        ...
```

#### 3.2 集成到 ToolRegistry（执行入口）
**文件**: `tools/registry.py`

- 执行工具前检查 `is_available`，若熔断则返回 `CIRCUIT_OPEN` 错误。
- 执行失败时 `record_failure`，成功时 `record_success`。

#### 3.3 集成到工具列表生成
**文件**: `tools/registry.py`

- `get_openai_tools()` 生成工具列表时过滤被禁用工具。
- 可选：在 prompt 里展示“禁用工具列表”（告知 LLM 不要调用）。

### 环境变量
```
CIRCUIT_FAILURE_THRESHOLD=3
CIRCUIT_RECOVERY_TIMEOUT=300
```

### 关键文件
- `tools/circuit_breaker.py`
- `tools/registry.py`
- `core/context_engine/context_builder.py`（可选：展示禁用工具）

---

## 4. Trace 脱敏

### 目标
对敏感字段做替换：API Key、token、session_id、tool_call_id、路径等。

### 实现方案

#### 4.1 创建脱敏器
**文件**: `core/context_engine/trace_sanitizer.py` (新建)

- 支持字符串正则替换 + dict key 层面脱敏。
- 路径脱敏：`/Users/<name>` → `/Users/***`。

#### 4.2 集成到 TraceLogger
**文件**: `core/context_engine/trace_logger.py`

- `log_event()` 写 JSONL 前先 `sanitize(payload)`。
- Markdown Trace 里不要直接暴露原始参数。

#### 4.3 环境变量
```
TRACE_SANITIZE=true
TRACE_MD_INCLUDE_RAW_RESPONSE=false
```

### 关键文件
- `core/context_engine/trace_sanitizer.py`
- `core/context_engine/trace_logger.py`

---

## 实现优先级与依赖

```
Phase 1: 基础增强
├── 1. AskUser 工具
├── 2. MCP 错误分级
└── 4. Trace 脱敏

Phase 2: 轻量熔断
└── 3. 熔断机制（与 MCP 错误分级配合效果最好）
```

---

## 测试计划（新增）

1. AskUser
   - 主 Agent 正常交互
   - Subagent 返回 ASK_USER_UNAVAILABLE

2. MCP 错误分级
   - 参数错误/解析错误/网络错误/超时/执行错误全覆盖

3. 熔断机制
   - 连续失败触发禁用
   - 恢复超时后重新放开
   - 禁用工具在工具列表中被过滤

4. Trace 脱敏
   - 常见密钥/Token/路径脱敏
   - tool_call_id 脱敏

---

## 关键文件清单

### 新建文件
- `tools/builtin/ask_user.py`
- `prompts/tools_prompts/ask_user_prompt.py`
- `tools/circuit_breaker.py`
- `core/context_engine/trace_sanitizer.py`

### 修改文件
- `agents/codeAgent.py`
- `tools/base.py`
- `tools/mcp/adapter.py`
- `tools/mcp/protocol.py`
- `tools/registry.py`
- `core/context_engine/context_builder.py`（可选）
- `core/context_engine/trace_logger.py`

---

*计划版本: v1.1*
*创建时间: 2026-01-17*
