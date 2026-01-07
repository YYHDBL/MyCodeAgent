# Trace Logging 设计文档（MVP / 全量轨迹）

版本：1.0.0  
用途：记录 Agent 完整执行轨迹（包含 CoT、工具调用、环境反馈、用户输入、token 用量），用于测试审计与回放分析。  
注意：本方案不做脱敏，仅适用于测试/内网环境。

---

## 1. 目标
- 记录完整推理轨迹：**用户输入 + 模型原始输出（含 Thought）+ 工具调用 + 工具结果 + Finish**  
- 记录 token 使用量  
- 便于后续检索、统计、回放

---

## 2. 输出文件格式
同时输出两份：
- **JSONL**：每一步一个 JSON 对象（便于流式追加与后处理）  
  路径：`memory/traces/trace-s-YYYYMMDD-HHMMSS-xxxx.jsonl`
- **Markdown（审计可读）**：面向人类审查的可视化摘要  
  路径：`memory/traces/trace-s-YYYYMMDD-HHMMSS-xxxx.md`
同一会话只写一个文件。

---

## 3. 事件类型（最小集合）
- `user_input`
- `model_output`（原始输出，含 CoT）
- `parsed_action`（解析结果）
- `tool_call`
- `tool_result`
- `error`
- `finish`
- `session_summary`（会话结束统计）

---

## 4. 标准事件结构
所有事件必须包含以下字段：
```json
{
  "ts": "2026-01-03T20:15:33.112Z",
  "session_id": "s-20260103-201533-a3f2",
  "step": 4,
  "event": "tool_call",
  "payload": {}
}
```

字段说明：
- `ts`: ISO8601 时间戳
- `session_id`: 会话唯一标识（格式：`s-YYYYMMDD-HHMMSS-{4位随机}`，由框架创建）
- `step`: ReAct 循环的 step 序号
- `event`: 事件类型
- `payload`: 事件数据体（见下）

---

## 5. 各事件 payload 规范

### 5.1 user_input
```json
{ "text": "用户原始输入" }
```

### 5.2 model_output
```json
{
  "raw": "Thought: ...\nAction: ...",
  "usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 456,
    "total_tokens": 1690
  }
}
```
说明：
- `usage` 直接取 LLM 返回值；没有就置为 `null`
- 不做脱敏

### 5.3 parsed_action
```json
{
  "thought": "...",
  "action": "Glob",
  "args": {"pattern": "**/*.py", "path": "."}
}
```

### 5.4 tool_call
```json
{ "tool": "Glob", "args": { ... } }
```

### 5.5 tool_result
```json
{
  "tool": "Glob",
  "result": {
    "status": "success",
    "data": { ... },
    "text": "Found 12 matches...",
    "stats": { ... },
    "context": { ... }
  }
}
```
说明：直接记录工具返回的完整 JSON（遵循通用工具响应协议）
Markdown 视图中会对 `result.data` 进行截断（默认 300 字符），以避免大段内容干扰审计。

### 5.6 error
```json
{
  "stage": "tool_execution",
  "error_code": "INVALID_PARAM",
  "message": "Error: ...",
  "tool": "Glob",
  "args": { ... },
  "traceback": "..."
}
```
说明：
- `error_code`: 标准错误码（与工具协议的 ErrorCode 对齐）
- `args`: 触发错误的参数（用于重现）
- `traceback`: 堆栈跟踪（测试环境可选）

### 5.7 finish
```json
{ "final": "最终回答内容" }
```

### 5.8 session_summary
```json
{
  "steps": 12,
  "tools_used": 7,
  "total_usage": {
    "prompt_tokens": 8800,
    "completion_tokens": 1900,
    "total_tokens": 10700
  }
}
```

---

## 6. 采集位置（接入点）
**最小接入点（框架层）**：
1. ReAct 循环接收用户输入后 → `user_input`
2. LLM 返回结果后 → `model_output`
3. Action 解析后 → `parsed_action`
4. Tool 执行前 → `tool_call`
5. Tool 返回后 → `tool_result`
6. 异常捕获时 → `error`
7. Finish 时 → `finish`
8. 会话结束 → `session_summary`

---

## 7. 配置开关
建议通过环境变量控制：
- `TRACE_ENABLED=true|false`（默认 false）
- `TRACE_DIR=memory/traces`（默认该路径）

---

## 8. 性能与安全
- JSONL 追加写入开销低，适合频繁记录
- **测试环境可用**，生产环境需考虑脱敏与权限控制

---

## 9. MVP 范围
本期仅实现：
- JSONL 记录
- 标准事件与 token 统计
- 会话级 summary

后续可选：
- 追加 `trace.md`（人类友好）
- 脱敏规则（API key / system prompt）
- 采样记录（降噪）

---

## 10. 实现指南（与现有架构对齐）

### 10.1 集成方式（ReAct 循环 / Agent）
- **session_id 生成位置**：建议在 `CodeAgent.run()` 中生成（会话级唯一 ID），并传入 TraceLogger。  
- **与现有 logger 关系**：TraceLogger **并存**，不替代现有 logger（日志用于运行态观察，Trace 用于审计回放）。  
- **调用位置**：在 ReAct 循环的主循环关键点调用 `trace.log_event()`。

### 10.2 LLM usage 的获取策略
当前架构中：
- `invoke_raw()` 返回原始响应（含 usage）
- `invoke()` 只返回文本（无 usage）

**MVP 方案（推荐）**：
- ReAct 循环在 trace 启用时使用 `invoke_raw()` 并从响应中提取 usage
- 理由：侵入性小，不需要修改 LLM 接口

实现示例：
```python
if trace_enabled:
    raw = self.llm.invoke_raw(messages)
    response_text = raw.choices[0].message.content
    usage = raw.usage  # 直接使用
else:
    response_text = self.llm.invoke(messages)
    usage = None
```

> 文档要求：Trace 记录优先使用 usage；若不可得则写 `null`。

### 10.3 tool_result 记录规范（完整返回）
为了与通用工具协议一致，**直接记录工具返回的完整 JSON**：
```json
{
  "tool": "Glob",
  "result": {
    "status": "success",
    "data": { ... },
    "text": "...",
    "stats": { ... },
    "context": { ... }
  }
}
```

### 10.4 error 事件增强
error 事件建议包含：
```json
{
  "stage": "tool_execution",
  "error_code": "INVALID_PARAM",
  "message": "Error: ...",
  "tool": "Glob",
  "args": { ... },
  "traceback": "..."  // 测试环境可选
}
```

### 10.5 session_summary 触发条件
满足任一即触发：
- `CodeAgent.run()` 正常返回（Finish 或 max_steps）  
- ReAct 循环捕获异常并退出  
- `Agent.run()` 结束时（推荐由 Agent 统一调用 `trace.finalize()`）

### 10.6 TraceLogger 接口设计
```python
class TraceLogger:
    """
    会话级轨迹记录器
    
    职责：
    - 记录单个会话的所有事件到 JSONL 文件
    - 生成 session_summary
    - 线程安全的文件写入
    """
    
    def __init__(self, session_id: str, trace_dir: Path, enabled: bool = True):
        """
        初始化 TraceLogger
        
        Args:
            session_id: 会话唯一标识（格式：s-YYYYMMDD-HHMMSS-{随机}）
            trace_dir: 轨迹文件目录（如 memory/traces）
            enabled: 是否启用记录（环境变量控制）
        """
        
    def log_event(self, event: str, payload: dict, step: int = 0):
        """
        记录单个事件
        
        Args:
            event: 事件类型（user_input/model_output/tool_call 等）
            payload: 事件数据体
            step: ReAct 循环的 step 序号（0 表示非步骤事件）
        """
        
    def finalize(self):
        """
        写入 session_summary 并关闭文件
        
        自动统计：
        - 总步骤数
        - 工具调用次数
        - 累计 token 用量
        """
        
    def _write_line(self, event_obj: dict):
        """内部方法：追加写入一行 JSON（加锁保证线程安全）"""
```

线程安全：使用 `threading.Lock` 保护文件写入操作。

---

## 11. 回放机制（MVP 说明）
MVP 仅保证“可回放信息完整”，**不实现自动回放**。  
回放的输入与验证建议：
- 输入：JSONL 事件流（包含工具调用与结果）
- 验证：对比工具调用顺序 + 结果一致性（人工或脚本）
- 可选：提供 mock 工具以重放工具结果
