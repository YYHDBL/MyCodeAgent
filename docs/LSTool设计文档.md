# 目录浏览工具设计文档（LSTool Standardized）
版本：2.0.0（Protocol Alignment）  
协议标准：Standard Envelope v1.0（详见 `docs/通用工具响应协议.md`）

## 1. 概述
LSTool 用于安全列出目录内容，支持分页、隐藏文件控制与忽略规则，输出严格遵循统一工具响应协议。

核心特性：
- 安全沙箱：所有路径必须位于 `project_root` 内
- 分页与过滤：`offset/limit` + `include_hidden/ignore`
- 标准化响应：统一 `status/data/text/stats/context` 结构

## 2. 接口规范
### 2.1 工具定义
- Internal Class Name: `ListFilesTool`
- Python Module: `tools/builtin/list_files.py`
- Agent Exposed Name: **`LS`**

### 2.2 输入参数（JSON Schema）
```json
{
  "name": "LS",
  "description": "List files and directories in a given path with pagination and filters.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Directory path to list (relative to project root or absolute within it).",
        "default": "."
      },
      "offset": {
        "type": "integer",
        "description": "Pagination start index (>=0).",
        "default": 0
      },
      "limit": {
        "type": "integer",
        "description": "Max items to return (1-200).",
        "default": 100
      },
      "include_hidden": {
        "type": "boolean",
        "description": "Whether to include hidden files (starting with '.').",
        "default": false
      },
      "ignore": {
        "type": "array",
        "description": "Optional list of glob patterns to ignore.",
        "default": null
      }
    },
    "required": []
  }
}
```

## 3. 输出结构（标准信封）
严格遵循《通用工具响应协议》，顶层字段仅允许：  
`status`, `data`, `text`, `stats`, `context`（且仅当 `status="error"` 时出现 `error` 字段）。

### 3.1 data 字段定义
- `entries` (array): 目录条目列表
  - `path` (string): 相对 `project_root` 的路径（POSIX 风格）
  - `type` (string): `"dir" | "file" | "link"`
- `truncated` (boolean): 是否触发分页截断

### 3.2 context 字段定义
- `cwd` (string): **必填**，执行时工作目录（相对 project root）
- `params_input` (object): **必填**，原始参数
- `path_resolved` (string): 解析后的规范化相对路径（POSIX）

### 3.3 成功/截断示例
```json
{
  "status": "partial",
  "data": {
    "entries": [
      {"path": "agents", "type": "dir"},
      {"path": "README.md", "type": "file"}
    ],
    "truncated": true
  },
  "text": "Listed 2 entries in '.'\n(Total: 120 items - 5 dirs, 112 files, 3 links)\n[Truncated: Showing 0-2 of 120. 118 more items available.]\nUse offset=2 to view next page.\n\nagents/\nREADME.md",
  "stats": {
    "time_ms": 4,
    "total_entries": 120,
    "dirs": 5,
    "files": 112,
    "links": 3,
    "returned": 2
  },
  "context": {
    "cwd": ".",
    "params_input": {"path": ".", "limit": 2},
    "path_resolved": "."
  }
}
```

## 4. 状态机与逻辑判定
### 4.1 status = "success"
- 正常列出目录内容
- 未触发分页截断

### 4.2 status = "partial"
- `offset/limit` 导致分页截断（`data.truncated=true`）

### 4.3 status = "error"
- 路径不存在 / 越权 / 非目录 / 参数非法 / 权限不足

## 5. 过滤与排序规则
### 5.1 默认忽略列表
当 `include_hidden=false` 时，以下目录会被跳过：
`.git`, `.hg`, `.svn`, `__pycache__`, `node_modules`, `target`, `build`, `dist`, `.idea`, `.vscode`, `.DS_Store`, `venv`, `.venv`

> 说明：`include_hidden=true` 会同时显示隐藏文件与默认忽略目录。

### 5.2 ignore 模式
- 支持 `fnmatch` 通配（如 `*.log`, `dist/**`）
- 若 pattern 含 `/` 或 `\\`，会同时匹配：
  - 相对 `project_root` 的路径
  - 相对当前 `target` 的路径
- 对 `**/` 前缀提供零层兼容（`**/foo` 可匹配 `foo`）

### 5.3 排序规则
- 目录优先，其次文件
- 同类型按名称字母序（不区分大小写）
- symlink 指向目录时，会被排序为目录，但 `type` 仍为 `"link"`

## 6. 安全与路径解析
- 允许相对路径与绝对路径，但必须在 `project_root` 内
- 相对路径基于 `working_dir` 解析（由框架注入）
- 目录条目路径不 `resolve()`，避免泄露 symlink 外部路径
- 若 symlink 指向目录且仍在沙箱内，会被识别为目录用于排序

## 7. 错误处理规范
| 场景 | error.code | error.message / text 建议 |
| --- | --- | --- |
| 路径不存在 | NOT_FOUND | "Path '{path}' does not exist." |
| 越权访问 | ACCESS_DENIED | "Access denied. Path must be within the project root." |
| 非目录 | INVALID_PARAM | "'{path}' is a file, not a directory. Use 'Read' tool to view its content." |
| 权限不足 | ACCESS_DENIED | "Permission denied accessing '{path}'." |
| 参数非法 | INVALID_PARAM | "offset/limit/ignore must be valid types." |
| 其他系统错误 | INTERNAL_ERROR | "Failed to list directory - {error}" |

## 8. text 字段规范
格式统一为：
```
Listed N entries in '{path}'
(Total: X items - D dirs, F files, L links)
[Truncated: Showing start-end of X. R more items available.]
Use offset=K to view next page.

<entries...>
```

目录条目展示规则：
- 目录：尾部加 `/`
- symlink：尾部加 `@`
- 文件：无后缀
