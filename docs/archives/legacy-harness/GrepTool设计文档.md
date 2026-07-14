# 代码内容搜索工具设计文档（GrepTool Standardized）
版本：2.0.0（Protocol Alignment）  
协议标准：Standard Envelope v1.0（详见 `docs/通用工具响应协议.md`）

## 1. 概述
GrepTool 用于在文件内容中检索正则模式，优先使用 ripgrep（rg）以获得高性能，缺失或失败时回退到 Python 实现。结果按文件修改时间降序排序，优先呈现“最近活跃”的代码。

核心特性：
- 双执行路径：rg 优先，Python 回退
- 结果可读：统一 `file:line: text` 展示
- 可控安全：沙箱路径校验 + 超时保护
- 标准化响应：统一 `status/data/text/stats/context` 结构

## 2. 接口规范
### 2.1 工具定义
- Internal Class Name: `GrepTool`
- Python Module: `tools/builtin/search_code.py`
- Agent Exposed Name: **`Grep`**

### 2.2 输入参数（JSON Schema）
```json
{
  "name": "Grep",
  "description": "Search file contents using regex. Returns matches sorted by file modification time (newest first).",
  "parameters": {
    "type": "object",
    "properties": {
      "pattern": {
        "type": "string",
        "description": "Regex pattern to search (e.g. 'class\\s+User'). Required."
      },
      "path": {
        "type": "string",
        "description": "Directory to search in (relative to project root). Defaults to '.'.",
        "default": "."
      },
      "include": {
        "type": "string",
        "description": "Glob pattern to filter files (e.g. '*.ts'). Highly recommended."
      },
      "case_sensitive": {
        "type": "boolean",
        "description": "If true, search is case-sensitive. Default is false.",
        "default": false
      }
    },
    "required": ["pattern"]
  }
}
```

## 3. 输出结构（标准信封）
严格遵循《通用工具响应协议》，顶层字段仅允许：  
`status`, `data`, `text`, `stats`, `context`（且仅当 `status="error"` 时出现 `error` 字段）。

### 3.1 data 字段定义
- `matches` (array): 匹配结果列表（对象数组）
  - `file` (string): 相对 `project_root` 的路径（POSIX）
  - `line` (int): 1-based 行号
  - `text` (string): 匹配行的完整文本（去掉末尾换行）
- `truncated` (boolean): 是否因上限截断（当前固定 `MAX_RESULTS=100`）
- `fallback_used` (boolean, optional): 使用 Python 回退时为 `true`
- `fallback_reason` (string, optional): `"rg_not_found"` 或 `"rg_failed"`

### 3.2 context 字段定义
- `cwd` (string): **必填**，执行时工作目录（相对 project root）
- `params_input` (object): **必填**，原始参数
- `path_resolved` (string): 解析后的规范化相对路径（POSIX）
- `pattern` (string): 原始正则表达式
- `sorted_by` (string): 固定为 `"mtime_desc"`

### 3.3 成功/截断示例
```json
{
  "status": "partial",
  "data": {
    "matches": [
      {"file": "src/auth/User.ts", "line": 42, "text": "export class User {"}
    ],
    "truncated": true,
    "fallback_used": true,
    "fallback_reason": "rg_not_found"
  },
  "text": "Found 1 matches in 1 files for 'class\\s+User' in 'src'\n(Sorted by mtime desc. Took 85ms)\n[Truncated: Showing first 100 matches. Narrow pattern or path.]\n[Info: ripgrep not available; used slower Python fallback search.]\n\nsrc/auth/User.ts:42: export class User {",
  "stats": {
    "time_ms": 85,
    "matched_files": 1,
    "matched_lines": 1
  },
  "context": {
    "cwd": ".",
    "params_input": {"pattern": "class\\s+User", "path": "src"},
    "path_resolved": "src",
    "pattern": "class\\s+User",
    "sorted_by": "mtime_desc"
  }
}
```

## 4. 状态机与逻辑判定
### 4.1 status = "success"
- 正常完成搜索
- 未触发截断/超时
- 未使用 Python 回退

### 4.2 status = "partial"
以下任一情况成立：
- 使用了 Python 回退（`fallback_used=true`）
- 触发截断（`truncated=true` 且有结果）
- 搜索超时但已有结果（`aborted_reason="timeout"`）

### 4.3 status = "error"
- 参数错误 / 路径错误 / 越权访问
- 超时且无结果（`error.code=TIMEOUT`）

## 5. 执行与排序逻辑
### 5.1 执行策略
1. 若系统存在 `rg`，优先使用 ripgrep
2. 若 rg 缺失或失败，回退 Python 实现（`fallback_used=true`）
3. Python 回退仍受超时控制（`TIMEOUT_SEC=2.0`）

### 5.2 include 语义
- `include` 为 glob 模式，仅用于过滤文件路径
- 基于 `PurePosixPath.match`，提供 `**/` 零层兼容
- 建议使用简单模式（`*.py`、`src/**/*.ts`）

### 5.3 排序规则
- 先按文件修改时间降序（mtime desc）
- 再按文件路径与行号稳定排序

## 6. 错误处理规范
| 场景 | error.code | error.message / text 建议 |
| --- | --- | --- |
| pattern 缺失 | INVALID_PARAM | "Missing required parameter 'pattern'." |
| include 类型错误 | INVALID_PARAM | "include must be a string if provided." |
| 正则非法 | INVALID_PARAM | "Invalid regex pattern: {details}" |
| 路径不存在 | NOT_FOUND | "Search root '{path}' does not exist." |
| 非目录 | INVALID_PARAM | "Search root '{path}' is not a directory." |
| 越权访问 | ACCESS_DENIED | "Access denied. Path must be within project root." |
| 超时且无结果 | TIMEOUT | text 中明确超时原因 |

## 7. text 字段规范
格式统一为：
```
Found N matches in M files for '{pattern}' in '{path}'
(Sorted by mtime desc. Took Tms)
[Truncated/Partial/Error 说明...]

<file:line: text...>
```

当没有匹配时：
```
No matches found for '{pattern}' in '{path}'
(Sorted by mtime desc. Took Tms)
```
