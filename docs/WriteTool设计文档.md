# 文件写入工具设计文档（WriteTool Standardized）

版本：1.0.0
协议标准：Standard Envelope v1.0（详见 `docs/通用工具响应协议.md`）

## 1. 概述

WriteTool 是 Code Agent 修改/创建文件的核心工具，提供全量覆盖写入能力，并严格遵循统一工具响应协议。

核心特性：
- **全量覆盖**：将 content 完整写入目标文件（不存在则创建）
- **审计反馈**：返回 Unified Diff 预览及详细统计
- **自动目录保障**：父目录不存在时自动递归创建
- **沙箱安全**：强制限制在 PROJECT_ROOT 内
- **预演模式**：支持 dry_run，仅计算 diff 不落盘
- **读写约束（MVP）**：当前仅在提示词层要求“已有文件必须先 Read”，代码层使用乐观锁实现约束
- **乐观锁（规划）**：Write 将引入 `expected_mtime_ms` + `expected_size_bytes` 校验，防止覆盖用户修改（见 `docs/details/乐观锁设计方案.md`）

---

## 2. 接口规范

### 2.1 工具定义
- Internal Class Name: `WriteTool`（Python 类名）
- Python Module: `tools/builtin/write_file.py`（实现文件）
- Agent Exposed Name: **`Write`**（注册到 ToolRegistry 时的名称）

### 2.2 输入参数（JSON Schema）

```json
{
  "name": "Write",
  "description": "Writes a file to the local filesystem. Overwrites existing file if present. Automatically creates parent directories.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Path to the file (relative to project root, POSIX style, no absolute path). Required."
      },
      "content": {
        "type": "string",
        "description": "Full content to write to the file (entire file). Required."
      },
      "dry_run": {
        "type": "boolean",
        "description": "If true, compute diff but do not write to disk.",
        "default": false
      }
    },
    "required": ["path", "content"]
  }
}
```

### 2.3 输出结构（标准信封）

严格遵循《通用工具响应协议》，顶层字段只允许：
`status`, `data`, `text`, `stats`, `context`（且仅当 `status="error"` 时出现 `error` 字段）。

#### 2.3.1 data 字段定义

| 字段 | 类型 | 说明 |
|------|------|------|
| `applied` | boolean | 是否已落盘（dry_run=false 且成功时为 true） |
| `operation` | string | 操作类型：`"create"` 或 `"update"` |
| `diff_preview` | string | Unified Diff 预览（仅用于可读预览，非权威结果） |
| `diff_truncated` | boolean | diff 是否被截断 |

#### 2.3.2 stats 字段定义

| 字段 | 类型 | 说明 |
|------|------|------|
| `time_ms` | int | 执行耗时（毫秒） |
| `bytes_written` | int | 写入内容的字节数 |
| `original_size` | int | 原文件大小（create 时为 0） |
| `new_size` | int | 新文件大小 |
| `lines_added` | int | Diff 统计：新增行数（如 diff 被截断，仅统计预览范围内） |
| `lines_removed` | int | Diff 统计：删除行数（如 diff 被截断，仅统计预览范围内） |

#### 2.3.3 context 字段定义

| 字段 | 类型 | 说明 |
|------|------|------|
| `cwd` | string | 工作目录（相对项目根目录） |
| `params_input` | object | 调用时传入的原始参数 |
| `path_resolved` | string | 解析后的规范化相对路径 |

---

## 3. 状态机与逻辑判定

### 3.1 status = "success"

满足以下所有条件：
- `dry_run = false` 且写入成功
- diff 未被截断

### 3.2 status = "partial"

以下任一情况：
- `dry_run = true`（预演模式，未产生副作用）
- `diff_truncated = true`（diff 预览过长被截断）

### 3.3 status = "error"

| 场景 | error.code | error.message |
|------|------------|---------------|
| 路径越权（沙箱） | ACCESS_DENIED | "Path must be within project root." |
| OS 权限拒绝 | PERMISSION_DENIED | "Permission denied writing to file." |
| 目标是目录 | IS_DIRECTORY | "Target path is a directory." |
| 参数错误 | INVALID_PARAM | "Content cannot be empty." |
| IO 错误 | EXECUTION_ERROR | "Disk full or IO error." |

---

## 4. 核心行为逻辑

### 4.0 Read-before-Write 约束（MVP 策略）
- **MVP 阶段**：仅在提示词中强约束“已有文件必须先 Read”。  
- **代码层**：暂不阻止写入，但需在实现中加入 TODO，后续引入 read_timestamps 校验。

### 4.0.1 乐观锁参数（规划）
- 对已存在文件：要求传入 `expected_mtime_ms` 与 `expected_size_bytes`（从 Read 返回的 stats 中获取）
- 不匹配则返回 `CONFLICT`，提示重新 Read

### 4.1 路径与沙箱校验

```python
# 路径规范：
# - 不允许绝对路径（以 / 开头）
# - 统一 POSIX 风格（使用 / 分隔）
# - 必须在 project_root 内

# 1. 拒绝绝对路径
if Path(path).is_absolute():
    return create_error_response(
        error_code=ErrorCode.INVALID_PARAM,
        message="Absolute path not allowed. Use relative path."
    )

# 2. 解析为绝对路径
abs_path = (self._root / Path(path)).resolve()

# 3. 沙箱检查
try:
    abs_path.relative_to(self._root)
except ValueError:
    return create_error_response(
        error_code=ErrorCode.ACCESS_DENIED,
        message="Path must be within project root."
    )

# 4. 目录检查
if abs_path.is_dir():
    return create_error_response(
        error_code=ErrorCode.IS_DIRECTORY,
        message="Target path is a directory."
    )
```

### 4.2 自动目录保障

```python
# 检查父目录，不存在则创建
parent_dir = abs_path.parent
dir_created = None

if not parent_dir.exists():
    parent_dir.mkdir(parents=True, exist_ok=True)
    dir_created = str(parent_dir.relative_to(self._root))
    # 在 text 字段中提示：(Created directory: xxx)
```

### 4.3 Diff 计算

```python
# 读取原文件内容
if abs_path.exists():
    old_content = abs_path.read_text(encoding="utf-8")
else:
    old_content = ""

# 生成 Unified Diff
diff = difflib.unified_diff(
    old_content.splitlines(keepends=True),
    content.splitlines(keepends=True),
    fromfile=f"a/{path}",
    tofile=f"b/{path}",
    lineterm=""
)

# 截断逻辑（超过 100 行或 10KB）
# 注意：避免 list(diff) 造成大文件内存膨胀
preview_lines = []
preview_bytes = 0
diff_truncated = False
lines_added = 0
lines_removed = 0
total_lines = 0

for line in diff:
    total_lines += 1
    if line.startswith("+") and not line.startswith("+++"):
        lines_added += 1
    if line.startswith("-") and not line.startswith("---"):
        lines_removed += 1

    if not diff_truncated:
        next_bytes = preview_bytes + len(line)
        if len(preview_lines) >= 100 or next_bytes > 10240:
            diff_truncated = True
            break  # 截断后停止遍历，统计值为“预览范围内”
        else:
            preview_lines.append(line)
            preview_bytes = next_bytes

diff_preview = "\n".join(preview_lines)
if diff_truncated:
    diff_preview = diff_preview + "\n... (truncated)"
```

### 4.4 写入执行

```python
if dry_run:
    applied = False
else:
    # 原子写入：写临时文件 -> rename
    temp_fd, temp_path = tempfile.mkstemp(
        dir=str(abs_path.parent),
        prefix=f"{abs_path.name}.",
        suffix=".tmp"
    )
    os.close(temp_fd)
    temp_path = Path(temp_path)
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(abs_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    applied = True
```
> 编码/行尾说明（MVP）：当前仅保证 UTF-8 写入与默认行尾；保持原编码/行尾风格属于后续增强计划。

---

## 5. text 字段规范

### 5.1 成功创建（success）

```
Created 'src/utils/helper.py' (50 lines, 1234 bytes).
(Created directory: src/utils/)
```

### 5.2 成功更新（success）

```
Updated 'src/main.py' (+12/-5 lines, 2048 bytes).
```

### 5.3 Dry Run（partial）

```
[Dry Run] Would create 'src/new.py' (+50 lines).
```

### 5.4 Diff 截断（partial）

```
Updated 'src/large.py' (+500/-20 lines, 15234 bytes).
(Diff preview truncated. Use Read to verify full content.)
```

---

## 6. 响应示例

### 6.1 成功创建（success）

```json
{
  "status": "success",
  "data": {
    "applied": true,
    "operation": "create",
    "diff_preview": "--- a/src/new.py\n+++ b/src/new.py\n@@ -0,0 +1,3 @@\n+def hello():\n+    print(\"world\")\n",
    "diff_truncated": false
  },
  "text": "Created 'src/new.py' (3 lines, 54 bytes).",
  "stats": {
    "time_ms": 8,
    "bytes_written": 54,
    "original_size": 0,
    "new_size": 54,
    "lines_added": 3,
    "lines_removed": 0
  },
  "context": {
    "cwd": ".",
    "params_input": {"path": "src/new.py", "content": "def hello():\n    print(\"world\")\n"},
    "path_resolved": "src/new.py"
  }
}
```

### 6.2 更新 + 目录创建（success）

```json
{
  "status": "success",
  "data": {
    "applied": true,
    "operation": "update",
    "diff_preview": "--- a/src/deep/file.py\n+++ b/src/deep/file.py\n...",
    "diff_truncated": false
  },
  "text": "Updated 'src/deep/file.py' (+5/-2 lines, 123 bytes).\n(Created directory: src/deep/)",
  "stats": {
    "time_ms": 15,
    "bytes_written": 123,
    "original_size": 89,
    "new_size": 123,
    "lines_added": 5,
    "lines_removed": 2
  },
  "context": {
    "cwd": ".",
    "params_input": {"path": "src/deep/file.py", "content": "..."},
    "path_resolved": "src/deep/file.py"
  }
}
```

### 6.3 Dry Run（partial）

```json
{
  "status": "partial",
  "data": {
    "applied": false,
    "operation": "create",
    "diff_preview": "...",
    "diff_truncated": false
  },
  "text": "[Dry Run] Would create 'src/new.py' (+50 lines).",
  "stats": {
    "time_ms": 5,
    "bytes_written": 0,
    "original_size": 0,
    "new_size": 0,
    "lines_added": 50,
    "lines_removed": 0
  },
  "context": {
    "cwd": ".",
    "params_input": {"path": "src/new.py", "content": "...", "dry_run": true},
    "path_resolved": "src/new.py"
  }
}
```

---

## 7. 给 Agent 的系统提示词

```
Tool: Write

Purpose: Create or overwrite a file with FULL content.

Key Features:
1. Auto-Mkdir: You do NOT need to create directories manually. This tool handles it.
2. Full Content: Provide the COMPLETE file content. Do not provide patches/snippets.
3. Diff Preview: The tool returns a diff preview (use Read to verify full content).
4. Dry Run: Use dry_run=true to preview changes without writing.

Best Practices:
- Read the file first to understand its current content before writing.
- Check the returned 'diff_preview' to verify your changes are correct.
- If diff is truncated, use Read to verify the full content.
- If the file already exists, you MUST use Read before Write (enforced by prompt in MVP; code-level check is TODO).
```

---

## 8. 实现文件结构

```
tools/builtin/write_file.py          # 主实现
tools/prompts/write_prompt.py        # 提示词
tests/test_write_tool.py             # 单元测试
```

---

## 附录：与参考设计的对比

| 特性 | 参考设计 | 本设计 | 说明 |
|------|---------|--------|------|
| 协议版本 | v1.2.0 | v1.0 | 与现有项目一致 |
| dry_run | ✅ | ✅ | 保留 |
| expected_original_hash | ✅ | ❌ | MVP 暂不实现 |
| 自动创建目录 | ✅ | ✅ | 保留 |
| 用户确认机制 | ❌ | ❌ | MVP 暂不实现，由框架层统一 |
| 目录创建提示 | ❌ | ✅ | 在 text 中提示 |
| 原子写入 | 建议 | ✅ | 使用 temp + rename |
| 路径规范 | 相对 | 相对/POSIX | 明确：不允许绝对路径 |
