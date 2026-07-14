# 全局文件搜索工具设计文档（GlobTool Standardized）
版本：2.0.0（Protocol Alignment）  
协议标准：Standard Envelope v1.0（详见 `docs/通用工具响应协议.md`）

## 1. 概述
GlobTool 用于按 glob 模式搜索文件路径，支持递归、忽略目录、隐藏文件控制，并通过熔断限制避免过度扫描。

核心特性：
- 路径安全：仅允许 `project_root` 内路径
- 搜索可控：条目数与时间双重熔断
- 模式清晰：`pattern` 相对 `path`，`*`/`?` 不跨目录，`**` 才跨目录
- 标准化响应：统一 `status/data/text/stats/context` 结构

## 2. 接口规范
### 2.1 工具定义
- Internal Class Name: `SearchFilesByNameTool`
- Python Module: `tools/builtin/search_files_by_name.py`
- Agent Exposed Name: **`Glob`**

### 2.2 输入参数（JSON Schema）
```json
{
  "name": "Glob",
  "description": "Find files using glob patterns (relative to the search root).",
  "parameters": {
    "type": "object",
    "properties": {
      "pattern": {
        "type": "string",
        "description": "Glob pattern relative to the search root (path), e.g. '**/*.js'.",
        "required": true
      },
      "path": {
        "type": "string",
        "description": "Directory to start search from (relative to project root).",
        "default": "."
      },
      "limit": {
        "type": "integer",
        "description": "Max matches to return (1-200).",
        "default": 50
      },
      "include_hidden": {
        "type": "boolean",
        "description": "If true, include hidden files and directories.",
        "default": false
      },
      "include_ignored": {
        "type": "boolean",
        "description": "If true, traverse ignored directories (node_modules, dist, etc).",
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
- `paths` (array): 匹配到的文件路径（相对 `project_root`，POSIX）
- `truncated` (boolean): 是否因 `limit` 截断
- `aborted_reason` (string, optional): `"count_limit"` 或 `"time_limit"`（仅当触发熔断时出现）

### 3.2 context 字段定义
- `cwd` (string): **必填**，执行时工作目录（相对 project root）
- `params_input` (object): **必填**，原始参数
- `path_resolved` (string): 解析后的规范化相对路径（POSIX）
- `pattern_normalized` (string): 统一为 POSIX 风格后的 pattern

### 3.3 成功/截断示例
```json
{
  "status": "partial",
  "data": {
    "paths": ["src/main.py", "src/utils/io.py"],
    "truncated": true,
    "aborted_reason": "time_limit"
  },
  "text": "Found 2 files matching '**/*.py' in 'src'\n(Scanned 12000 items in 2010ms)\n[Partial: Search timed out (>2s). Results are incomplete.]\n\nsrc/main.py\nsrc/utils/io.py",
  "stats": {
    "time_ms": 2010,
    "matched": 2,
    "visited": 12000
  },
  "context": {
    "cwd": ".",
    "params_input": {"pattern": "**/*.py", "path": "src", "limit": 2},
    "path_resolved": "src",
    "pattern_normalized": "**/*.py"
  }
}
```

## 4. 状态机与逻辑判定
### 4.1 status = "success"
- 正常完成搜索
- 未触发截断与熔断

### 4.2 status = "partial"
- 触发 `limit` 截断（`data.truncated=true`）
- 或触发熔断但已有结果（`data.aborted_reason` 存在）

### 4.3 status = "error"
- 参数错误 / 路径错误 / 越权访问
- 触发熔断且没有任何结果（`error.code=TIMEOUT` 或 `INTERNAL_ERROR`）

## 5. 搜索与匹配规则
### 5.1 路径解析
- `path` 可为相对路径或绝对路径
- 相对路径基于 `project_root`
- 解析后的路径必须在 `project_root` 内，否则报 `ACCESS_DENIED`

### 5.2 遍历与熔断
使用 `os.walk(topdown=True)`：
- 目录与文件按字母序排序（保证可复现）
- `visited` 统计包含目录与文件
- 双重熔断：
  - `MAX_VISITED_ENTRIES = 20000`
  - `MAX_DURATION_MS = 2000`

### 5.3 隐藏与忽略目录
当 `include_ignored=false` 时，剪枝以下目录：
`.git`, `.hg`, `.svn`, `__pycache__`, `node_modules`, `target`, `build`, `dist`, `.idea`, `.vscode`, `.DS_Store`, `venv`, `.venv`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.tox`, `.cache`, `site-packages`

当 `include_hidden=false` 时：
- 跳过以 `.` 开头的目录
- 跳过以 `.` 开头的文件

### 5.4 glob 语义（关键）
- `pattern` 永远相对 `path`（搜索起点）
- `*` 与 `?` **不跨目录**（通过内部转换实现）
- `**` 才能跨目录
- 为兼容 `**/` 零层匹配，`**/foo` 也会匹配 `foo`

## 6. 错误处理规范
| 场景 | error.code | error.message / text 建议 |
| --- | --- | --- |
| pattern 缺失 | INVALID_PARAM | "Missing required parameter 'pattern'." |
| limit 非法 | INVALID_PARAM | "limit must be an integer between 1 and 200." |
| 路径不存在 | NOT_FOUND | "Search root '{path}' does not exist." |
| 非目录 | INVALID_PARAM | "Search root '{path}' is not a directory." |
| 越权访问 | ACCESS_DENIED | "Access denied. Path must be within project root." |
| 熔断且无结果 | TIMEOUT / INTERNAL_ERROR | text 中包含具体原因 |

## 7. text 字段规范
格式统一为：
```
Found N files matching '{pattern}' in '{path}'
(Scanned V items in Tms)
[Truncated/Partial/Error 说明...]

<paths...>
```

当没有匹配时：
```
No files found matching '{pattern}' in '{path}'
(Scanned V items in Tms)
```
