# 文件读取工具设计文档（ReadTool Standardized）
版本：2.0.0（Protocol Alignment）
协议标准：Standard Envelope v1.0（详见 `docs/通用工具响应协议.md`）

## 1. 概述
ReadTool 是 Code Agent 获取代码上下文的核心工具，提供带行号的文本读取能力，并严格遵循统一工具响应协议。

核心特性：
- 编辑导向：输出带行号（1-based）便于 Edit 定位
- 防御性读取：内置分页截断与二进制熔断
- 标准化响应：统一 `status/data/text/stats/context` 结构

## 2. 接口规范
### 2.1 工具定义
- Internal Class Name: `ReadTool`（Python 类名）
- Python Module: `tools/builtin/read_file.py`（实现文件）
- Agent Exposed Name: **`Read`**（注册到 ToolRegistry 时的名称）

### 2.2 输入参数（JSON Schema）
```json
{
  "name": "Read",
  "description": "Reads a file from the local filesystem with line numbers. Optimized for code editing.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Path to the file (relative to project root). Required."
      },
      "start_line": {
        "type": "integer",
        "description": "The line number to start reading from (1-based). Default is 1.",
        "default": 1
      },
      "limit": {
        "type": "integer",
        "description": "The maximum number of lines to read. Default is 500. Hard limit is 2000.",
        "default": 500
      }
    },
    "required": ["path"]
  }
}
```

### 2.3 输出结构（标准信封）
严格遵循《通用工具响应协议》，顶层字段只允许：
`status`, `data`, `text`, `stats`, `context`（且仅当 `status="error"` 时出现 `error` 字段）。

#### 2.3.1 data 字段定义
- `content` (string): 核心载荷，逐行带行号前缀
  - 格式固定为 `"%4d | %s\n"`
  - 每行强制包含换行符（包括最后一行）
- `truncated` (boolean): 是否触发分页截断
- `fallback_encoding` (string, optional): 仅当编码降级时出现（如 `"replace"`）

#### 2.3.2 context 字段定义
- `cwd` (string): **必填**，工具执行时的工作目录，相对于 project root。大多数情况下为 `"."`
- `params_input` (object): **必填**，调用时传入的原始参数（原样保存）
- `path_resolved` (string): 解析后的规范化相对路径（POSIX 风格，允许 resolve symlink）

#### 2.3.2.1 stats 字段补充说明
- `time_ms` (int): 执行耗时（毫秒）
- `lines_read` (int): 读取的行数
- `chars_read` (int): 读取的字符数
- `total_lines` (int): 文件总行数
- `file_size_bytes` (int): 文件大小（字节）
- `file_mtime_ms` (int): 文件 mtime（毫秒）
- `encoding` (string): 实际使用的编码

#### 2.3.3 成功/截断示例
```json
{
  "status": "partial",
  "data": {
    "content": "   1 | import os\n   2 | import json\n   3 | \n",
    "truncated": true
  },
  "text": "Read 500 lines from 'src/utils.py' (Lines 1-500).\n(Took 12ms)\n[Truncated: Showing first 500 of 1523 lines. Use start_line=501 to continue.]",
  "stats": {
    "time_ms": 12,
    "lines_read": 500,
    "chars_read": 12050,
    "total_lines": 1523,
    "file_size_bytes": 45200,
    "file_mtime_ms": 1735212345000,
    "encoding": "utf-8"
  },
  "context": {
    "cwd": ".",
    "params_input": {"path": "src/utils.py", "limit": 500},
    "path_resolved": "src/utils.py"
  }
}
```

## 3. 状态机与逻辑判定
### 3.1 status = "success"
- 文件存在且可读（文本）
- 未触发截断
- 无编码降级
- 覆盖到 EOF

### 3.2 status = "partial"
- 触发截断（`data.truncated=true`）
- 或发生编码降级（`data.fallback_encoding` 存在）

### 3.3 status = "error"
- 路径不存在 / 越权 / 非文件
- 二进制文件
- 参数非法（如 `start_line` 超出文件长度）

## 4. 错误处理规范
错误必须映射到标准错误码，并返回结构化 `error` 对象。

| 场景 | error.code | error.message / text 建议 |
| --- | --- | --- |
| 文件不存在 | NOT_FOUND | "File '{path}' does not exist." |
| 越权访问 | ACCESS_DENIED | "Access denied. Path must be within project root." |
| 路径是目录 | IS_DIRECTORY | "Path '{path}' is a directory. Use LS to explore it." |
| 二进制文件 | BINARY_FILE | "File '{path}' appears to be binary." |
| 参数错误 | INVALID_PARAM | "Invalid start_line/limit..." |

### 4.1 ErrorCode 枚举扩展
为支持 Read 工具的错误场景，需要在 `tools/base.py` 的 `ErrorCode` 枚举中扩展：

```python
class ErrorCode(str, Enum):
    # ... 现有错误码 ...
    IS_DIRECTORY = "IS_DIRECTORY"     # 路径是目录而非文件
    BINARY_FILE = "BINARY_FILE"       # 文件是二进制格式
```

这两个错误码也可供其他文件操作工具复用（如未来的 Write/Edit 工具）。

## 5. 关键逻辑细节
### 5.1 start_line 边界行为
- 若 `start_line` > 文件总行数：**返回 error（INVALID_PARAM）**
  - text 明确提示：文件总行数与合法范围
- 空文件时：`start_line` 只能为 1；若 `start_line > 1`，返回 `INVALID_PARAM`

### 5.2 limit 上限
- `limit` 必须在 1–2000 范围内
- 超出直接报 `INVALID_PARAM`，不静默截断

### 5.3 编码策略
- 默认 `utf-8` 严格读取
- 失败则回退：`utf-8` + `errors="replace"`
- 回退时 `status="partial"`，并写入 `data.fallback_encoding="replace"`

### 5.4 二进制检测
- 读取前 8KB
- 若包含 `\x00` → 直接判定二进制并返回 `BINARY_FILE`

### 5.5 路径规范化
- `context.path_resolved` 为规范化后的相对路径（POSIX）
- 允许 resolve symlink，但仍需保证在 project root 内

## 6. text 字段规范
格式统一为：
```
Read N lines from '{path}' (Lines a-b).
(Took Xms)
[Truncated: Showing first N of M lines. Use start_line=K to continue.]
```

- 成功时不含 Truncated 行
- partial 时必须给出下一页起始行

## 7. 空文件处理
- status: `success`
- data.content: ""
- text: "Read 0 lines from '{path}' (file is empty)."
- stats: `lines_read=0`, `total_lines=0`
