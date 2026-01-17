# MyCodeAgent 增强功能实现计划

## 概述

本计划实现四个核心增强功能，按优先级排序：
1. **AskUser 工具** - 避免因缺少信息而卡住
2. **MCP 错误分级** - 帮助 LLM 理解失败原因
3. **轻量熔断机制** - 自动禁用连续失败的工具
4. **Trace 脱敏** - 保护敏感信息

---

## 1. AskUser 工具（最小版）

### 目标
当 Agent 需要用户输入时，能够暂停并询问，避免因缺少信息而结束/卡住。

### 实现方案

#### 1.1 创建工具文件
**文件**: `tools/builtin/ask_user.py`

```python
class AskUserTool(Tool):
    """向用户提问并等待回答的工具"""

    name = "AskUser"
    description = "当需要用户提供信息时使用此工具..."

    def get_parameters(self):
        return [
            ToolParameter("questions", "array", "问题列表（1-3个）", required=True),
            ToolParameter("format", "string", "single|multi", required=False, default="single"),
        ]

    def run(self, parameters):
        # 返回特殊标记，让主循环处理
        return self.create_success_response(
            data={"requires_input": True, "questions": questions},
            text="[需要用户输入]",
            ...
        )
```

#### 1.2 修改 Agent 主循环
**文件**: `agents/codeAgent.py`

在 `_react_loop` 方法中，检测 `requires_input` 标记：

```python
def _react_loop(self, ...):
    for step in range(1, self.max_steps + 1):
        # ... 现有逻辑 ...

        # 执行工具
        observation = self._execute_tool(tool_name, tool_input)

        # 解析工具响应
        result = json.loads(observation)
        if result.get("data", {}).get("requires_input"):
            # 处理用户输入
            user_answers = self._handle_user_input(result["data"])
            # 将答案作为新的 observation
            observation = json.dumps({
                "status": "success",
                "data": {"answers": user_answers},
                "text": f"用户回答: {user_answers}",
                ...
            })
```

#### 1.3 实现用户输入处理
**文件**: `agents/codeAgent.py`

```python
def _handle_user_input(self, data: Dict) -> Dict:
    """处理需要用户输入的情况"""
    questions = data.get("questions", [])
    answers = []

    for i, q in enumerate(questions):
        prompt = f"\n[Agent 问] {q}\n> "
        answer = input(prompt)
        answers.append(answer)

    return {"questions": questions, "answers": answers}
```

#### 1.4 注册工具
**文件**: `agents/codeAgent.py`

在 `_register_builtin_tools` 方法中添加：
```python
from tools.builtin.ask_user import AskUserTool
self.tool_registry.register_tool(AskUserTool(...))
```

#### 1.5 创建 Prompt
**文件**: `prompts/tools_prompts/ask_user_prompt.py`

```python
ask_user_prompt = """
## AskUser

当需要用户提供信息才能继续时使用此工具（如缺少 API Key、文件路径等）。

参数：
- questions: 问题列表（1-3个，一次性提交）
- format: "single" 单选 | "multi" 多选

示例：
Action: AskUser[{"questions": ["请提供 API Key", "项目使用什么框架？"]}]

用户回答会作为工具结果返回。
"""
```

### 关键文件
- `tools/builtin/ask_user.py` (新建)
- `agents/codeAgent.py` (修改: `_react_loop`, `_handle_user_input`, `_register_builtin_tools`)
- `prompts/tools_prompts/ask_user_prompt.py` (新建)

---

## 2. MCP 错误语义分级

### 目标
区分参数错误/解析失败/执行失败，帮助 LLM 做出正确决策。

### 实现方案

#### 2.1 扩展 ErrorCode 枚举
**文件**: `tools/base.py`

```python
class ErrorCode(str, Enum):
    # 现有错误码...
    INVALID_PARAM = "INVALID_PARAM"
    EXECUTION_ERROR = "EXECUTION_ERROR"

    # 新增 MCP 相关错误码
    MCP_PARAM_ERROR = "MCP_PARAM_ERROR"       # MCP 参数错误
    MCP_PARSE_ERROR = "MCP_PARSE_ERROR"       # MCP 响应解析失败
    MCP_EXECUTION_ERROR = "MCP_EXECUTION_ERROR"  # MCP 工具执行失败
    MCP_NETWORK_ERROR = "MCP_NETWORK_ERROR"   # MCP 网络错误
    MCP_TIMEOUT = "MCP_TIMEOUT"               # MCP 超时
    MCP_NOT_FOUND = "MCP_NOT_FOUND"           # MCP 工具不存在
```

#### 2.2 修改 MCP adapter 错误处理
**文件**: `tools/mcp/adapter.py`

```python
class MCPToolAdapter:
    def run(self, parameters: Dict[str, Any]) -> str:
        start_time = time.monotonic()
        params_input = dict(parameters)

        # 1. 参数验证阶段
        try:
            invalid = self._validate_params(parameters)
            if invalid:
                return to_protocol_error(
                    error_code=ErrorCode.MCP_PARAM_ERROR,
                    message=f"参数验证失败: {invalid}",
                    params_input=params_input,
                    tool_name=self.name,
                    start_time=start_time,
                )
        except Exception as e:
            return to_protocol_error(
                error_code=ErrorCode.MCP_PARSE_ERROR,
                message=f"参数解析异常: {e}",
                params_input=params_input,
                tool_name=self.name,
                start_time=start_time,
            )

        # 2. MCP 调用阶段
        try:
            result = self._mcp_client.call_tool_sync(
                tool_name=self.mcp_tool_name,
                arguments=parameters.get("arguments", {})
            )
        except TimeoutError:
            return to_protocol_error(
                error_code=ErrorCode.MCP_TIMEOUT,
                message=f"MCP 工具调用超时",
                params_input=params_input,
                tool_name=self.name,
                start_time=start_time,
            )
        except ConnectionError:
            return to_protocol_error(
                error_code=ErrorCode.MCP_NETWORK_ERROR,
                message=f"MCP 服务器连接失败",
                params_input=params_input,
                tool_name=self.name,
                start_time=start_time,
            )
        except Exception as e:
            return to_protocol_error(
                error_code=ErrorCode.MCP_EXECUTION_ERROR,
                message=f"MCP 工具执行失败: {e}",
                params_input=params_input,
                tool_name=self.name,
                start_time=start_time,
            )

        # 3. 响应解析阶段
        try:
            return to_protocol_result(result, ...)
        except Exception as e:
            return to_protocol_error(
                error_code=ErrorCode.MCP_PARSE_ERROR,
                message=f"MCP 响应解析失败: {e}",
                params_input=params_input,
                tool_name=self.name,
                start_time=start_time,
            )
```

#### 2.3 修改 protocol.py
**文件**: `tools/mcp/protocol.py`

```python
def to_protocol_error(
    message: str,
    params_input: dict[str, Any],
    tool_name: str,
    start_time: float,
    error_code: ErrorCode = ErrorCode.MCP_EXECUTION_ERROR,
) -> str:
    """统一 MCP 错误响应格式"""
    time_ms = int((time.monotonic() - start_time) * 1000)

    # error 字段必须存在且清晰
    error = {
        "code": error_code.value,
        "message": message,
        "type": _error_type_mapping(error_code),  # param/parse/execution
    }

    return json.dumps({
        "status": "error",
        "data": {},
        "text": f"[MCP Error] {message}",
        "error": error,
        "stats": {"time_ms": time_ms},
        "context": {"cwd": ".", "params_input": params_input},
    })

def _error_type_mapping(code: ErrorCode) -> str:
    """错误码到错误类型的映射"""
    if code in (ErrorCode.MCP_PARAM_ERROR, ErrorCode.INVALID_PARAM):
        return "param_error"
    if code in (ErrorCode.MCP_PARSE_ERROR,):
        return "parse_error"
    if code in (ErrorCode.MCP_NETWORK_ERROR, ErrorCode.MCP_TIMEOUT):
        return "network_error"
    return "execution_error"
```

### 关键文件
- `tools/base.py` (修改: ErrorCode 枚举)
- `tools/mcp/adapter.py` (修改: run 方法的错误处理)
- `tools/mcp/protocol.py` (修改: to_protocol_error, 新增 _error_type_mapping)

---

## 3. 轻量熔断机制

### 目标
同一工具连续失败 N 次后临时禁用（本会话内），并在 Prompt 中提示。

### 实现方案

#### 3.1 创建熔断器类
**文件**: `tools/circuit_breaker.py` (新建)

```python
from dataclasses import dataclass
from typing import Optional
from enum import Enum

class CircuitState(str, Enum):
    CLOSED = "closed"      # 正常状态，允许执行
    OPEN = "open"          # 熔断状态，拒绝执行
    HALF_OPEN = "half_open"  # 半开状态，允许试探

@dataclass
class ToolFailureRecord:
    tool_name: str
    failure_count: int = 0
    last_failure_time: Optional[float] = None
    last_error: Optional[str] = None
    circuit_state: CircuitState = CircuitState.CLOSED

class CircuitBreaker:
    """轻量级工具熔断器"""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 300):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout  # 秒
        self._records: Dict[str, ToolFailureRecord] = {}

    def record_success(self, tool_name: str):
        """记录工具执行成功，重置失败计数"""
        if tool_name not in self._records:
            self._records[tool_name] = ToolFailureRecord(tool_name=tool_name)
        record = self._records[tool_name]
        record.failure_count = 0
        record.circuit_state = CircuitState.CLOSED

    def record_failure(self, tool_name: str, error: str = ""):
        """记录工具执行失败"""
        if tool_name not in self._records:
            self._records[tool_name] = ToolFailureRecord(tool_name=tool_name)

        record = self._records[tool_name]
        record.failure_count += 1
        record.last_failure_time = time.monotonic()
        record.last_error = error

        # 检查是否需要熔断
        if record.failure_count >= self.failure_threshold:
            record.circuit_state = CircuitState.OPEN

    def is_available(self, tool_name: str) -> bool:
        """检查工具是否可用"""
        if tool_name not in self._records:
            return True

        record = self._records[tool_name]

        # 如果是 OPEN 状态，检查是否可以恢复
        if record.circuit_state == CircuitState.OPEN:
            if record.last_failure_time is None:
                return True
            elapsed = time.monotonic() - record.last_failure_time
            if elapsed > self.recovery_timeout:
                record.circuit_state = CircuitState.HALF_OPEN
                return True
            return False

        return True

    def get_disabled_tools(self) -> List[str]:
        """获取当前被禁用的工具列表"""
        return [
            name for name, record in self._records.items()
            if not self.is_available(name)
        ]

    def get_status(self, tool_name: str) -> Optional[ToolFailureRecord]:
        """获取工具的熔断状态"""
        return self._records.get(tool_name)
```

#### 3.2 集成到 ToolRegistry
**文件**: `tools/registry.py`

```python
from tools.circuit_breaker import CircuitBreaker

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=int(os.getenv("CIRCUIT_FAILURE_THRESHOLD", "3")),
            recovery_timeout=int(os.getenv("CIRCUIT_RECOVERY_TIMEOUT", "300"))
        )

    def execute_tool(self, tool_name: str, input_text: str) -> str:
        # 检查熔断状态
        if not self._circuit_breaker.is_available(tool_name):
            status = self._circuit_breaker.get_status(tool_name)
            return json.dumps({
                "status": "error",
                "error": {
                    "code": "CIRCUIT_OPEN",
                    "message": f"工具 '{tool_name}' 因连续失败 {status.failure_count} 次已被临时禁用"
                },
                ...
            })

        # 执行工具
        try:
            result = self._tools[tool_name].run(parameters)
            self._circuit_breaker.record_success(tool_name)
            return result
        except Exception as e:
            self._circuit_breaker.record_failure(tool_name, str(e))
            raise

    def get_disabled_tools(self) -> List[str]:
        """获取被禁用的工具列表（用于 Prompt 生成）"""
        return self._circuit_breaker.get_disabled_tools()
```

#### 3.3 在 Prompt 中提示禁用工具
**文件**: `core/context_engine/context_builder.py`

```python
def _load_tool_prompts(self) -> str:
    """加载工具提示，包含禁用工具信息"""
    prompts = []

    # 基础工具提示
    for tool in self.tool_registry.get_all_tools():
        prompts.append(tool.description)

    # 禁用工具提示
    disabled = self.tool_registry.get_disabled_tools()
    if disabled:
        prompts.append(f"\n# 临时禁用的工具（连续失败）\n")
        for name in disabled:
            status = self.tool_registry._circuit_breaker.get_status(name)
            prompts.append(f"- {name}: {status.last_error}")

    return "\n\n".join(prompts)
```

### 关键文件
- `tools/circuit_breaker.py` (新建)
- `tools/registry.py` (修改: 集成 CircuitBreaker)
- `core/context_engine/context_builder.py` (修改: 在 Prompt 中显示禁用工具)

### 环境变量
```bash
CIRCUIT_FAILURE_THRESHOLD=3    # 连续失败多少次后熔断
CIRCUIT_RECOVERY_TIMEOUT=300   # 恢复时间（秒）
```

---

## 4. Trace 脱敏

### 目标
对明显敏感字段做替换：API_KEY、session_id、tool_call_id、file paths。

### 实现方案

#### 4.1 创建脱敏器
**文件**: `core/context_engine/trace_sanitizer.py` (新建)

```python
import re
from typing import Any, Dict, List

class TraceSanitizer:
    """Trace 敏感信息脱敏器"""

    # 敏感字段模式
    SENSITIVE_PATTERNS = {
        # API Keys / Tokens
        r'sk-[a-zA-Z0-9]{20,}': 'sk-***',
        r'api[_-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{10,}': 'api_key:***',
        r'token["\']?\s*[:=]\s*["\']?[a-zA-Z0-9._-]{10,}': 'token:***',
        r'secret["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{10,}': 'secret:***',
        r'Bearer\s+[a-zA-Z0-9._\-+/=]{20,}': 'Bearer ***',
        r'Authorization["\']?\s*[:=]\s*["\']?[a-zA-Z0-9._\-+/=]{20,}': 'Authorization:***',

        # Session / Call IDs
        r'session["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{20,}': 'session:***',
        r'tool_call_id["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{20,}': 'tool_call_id:***',
        r'call_[a-zA-Z0-9]{10,}': 'call_***',

        # 密码
        r'password["\']?\s*[:=]\s*["\']?[^"\'\s]{4,}': 'password:***',
        r'passwd["\']?\s*[:=]\s*["\']?[^"\'\s]{4,}': 'passwd:***',
    }

    # 需要完全替换的敏感字段名
    SENSITIVE_KEYS = {
        'api_key', 'apikey', 'api-key',
        'secret', 'secret_key', 'secretkey',
        'token', 'access_token', 'refresh_token',
        'password', 'passwd', 'pwd',
        'session_id', 'sessionid', 'session',
        'tool_call_id', 'call_id',
        'authorization', 'auth',
    }

    # 需要部分脱敏的字段（保留最后4位）
    PARTIAL_MASK_KEYS = {
        'user_id', 'account_id', 'project_id',
    }

    def __init__(self, enable: bool = True):
        self.enable = enable
        # 预编译正则
        self.compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in self.SENSITIVE_PATTERNS.items()
        ]

    def sanitize(self, data: Any) -> Any:
        """脱敏处理入口"""
        if not self.enable:
            return data

        if isinstance(data, str):
            return self._sanitize_string(data)
        elif isinstance(data, dict):
            return self._sanitize_dict(data)
        elif isinstance(data, list):
            return [self.sanitize(item) for item in data]
        else:
            return data

    def _sanitize_string(self, text: str) -> str:
        """脱敏字符串"""
        result = text
        for pattern, replacement in self.compiled_patterns:
            result = pattern.sub(replacement, result)
        return result

    def _sanitize_dict(self, data: Dict) -> Dict:
        """脱敏字典"""
        result = {}
        for key, value in data.items():
            key_lower = key.lower()

            # 跳过元数据字段（这些通常不包含敏感信息）
            if key_lower in {'time_ms', 'step', 'event', 'ts'}:
                result[key] = value
                continue

            # 完全脱敏的字段
            if key_lower in self.SENSITIVE_KEYS:
                if isinstance(value, str):
                    result[key] = '***'
                elif isinstance(value, (int, float)):
                    result[key] = 0
                else:
                    result[key] = None
                continue

            # 部分脱敏的字段（保留格式）
            if key_lower in self.PARTIAL_MASK_KEYS:
                if isinstance(value, str) and len(value) > 8:
                    result[key] = value[:4] + '***' + value[-4:]
                else:
                    result[key] = '***'
                continue

            # 文件路径脱敏（保留文件名，隐藏用户路径）
            if 'path' in key_lower and isinstance(value, str):
                result[key] = self._sanitize_path(value)
                continue

            # 递归处理嵌套结构
            result[key] = self.sanitize(value)

        return result

    def _sanitize_path(self, path: str) -> str:
        """路径脱敏：保留文件名，隐藏用户路径"""
        # 替换用户主目录
        path = re.sub(r'/Users/[^/]+', '/Users/***', path)
        path = re.sub(r'/home/[^/]+', '/home/***', path)
        # 替换长路径中间部分
        parts = path.split('/')
        if len(parts) > 5:
            return '/'.join(parts[:2]) + '/.../' + '/'.join(parts[-2:])
        return path
```

#### 4.2 集成到 TraceLogger
**文件**: `core/context_engine/trace_logger.py`

```python
from core.context_engine.trace_sanitizer import TraceSanitizer

class TraceLogger:
    def __init__(self, ...):
        # 现有代码...
        self._sanitizer = TraceSanitizer(
            enable=os.getenv("TRACE_SANITIZE", "true").lower() == "true"
        )

    def log_event(self, event: str, payload: Dict[str, Any], step: int = 0):
        """记录事件（带脱敏）"""
        # 脱敏处理
        sanitized_payload = self._sanitizer.sanitize(payload)

        # 写入 JSONL
        event_obj = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "session_id": self.session_id,
            "step": step,
            "event": event,
            "payload": sanitized_payload,  # 使用脱敏后的 payload
        }

        self._write_jsonl(event_obj)
```

#### 4.3 添加环境变量控制
**文件**: `.env` 或环境变量

```bash
TRACE_SANITIZE=true   # 是否启用脱敏（默认 true）
```

### 关键文件
- `core/context_engine/trace_sanitizer.py` (新建)
- `core/context_engine/trace_logger.py` (修改: 集成 TraceSanitizer)

---

## 实现优先级和依赖关系

```
Phase 1: 基础增强（可并行）
├── 1. AskUser 工具 [2-3h]
│   └── 独立，无依赖
├── 2. MCP 错误分级 [1-2h]
│   └── 独立，无依赖
└── 4. Trace 脱敏 [1-2h]
    └── 独立，无依赖

Phase 2: 熔断机制（依赖 Phase 1）
└── 3. 轻量熔断 [2-3h]
    └── 可与 MCP 错误分级配合使用
```

## 测试计划

每个功能完成后需要添加测试：

1. **AskUser 工具**
   - 测试单问题提问
   - 测试多问题提问
   - 测试特殊字符输入

2. **MCP 错误分级**
   - 测试各类错误码返回
   - 测试错误类型映射

3. **熔断机制**
   - 测试连续失败触发熔断
   - 测试超时后恢复
   - 测试成功后重置计数

4. **Trace 脱敏**
   - 测试各类敏感模式替换
   - 测试嵌套结构脱敏
   - 测试路径脱敏

## 关键文件清单

### 新建文件
| 文件 | 功能 |
|------|------|
| `tools/builtin/ask_user.py` | AskUser 工具实现 |
| `prompts/tools_prompts/ask_user_prompt.py` | AskUser Prompt |
| `tools/circuit_breaker.py` | 熔断器实现 |
| `core/context_engine/trace_sanitizer.py` | Trace 脱敏器 |

### 修改文件
| 文件 | 修改内容 |
|------|----------|
| `tools/base.py` | 扩展 ErrorCode 枚举 |
| `tools/mcp/adapter.py` | 细化错误处理 |
| `tools/mcp/protocol.py` | 新增错误类型映射 |
| `tools/registry.py` | 集成熔断器 |
| `agents/codeAgent.py` | AskUser 处理逻辑 |
| `core/context_engine/trace_logger.py` | 集成脱敏器 |
| `core/context_engine/context_builder.py` | 显示禁用工具 |

---

*计划版本: v1.0*
*创建时间: 2025-01-16*
