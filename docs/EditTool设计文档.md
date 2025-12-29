# 单次编辑工具设计文档（EditTool Standardized）

版本：1.0.0  
协议标准：Standard Envelope v1.0（详见 `docs/通用工具响应协议.md`）

## 1. 概述

EditTool 是 Code Agent 的“单点替换”编辑工具，用于在**已存在**文件中，将一段**唯一的旧片段**替换为新片段。它不依赖行号，完全基于上下文锚点匹配，并遵循统一响应协议。

核心特性：
- **唯一锚点替换**：`old_string` 必须在文件中唯一出现
- **格式无感**：自动处理 CRLF/LF 差异，避免平台换行导致匹配失败
- **乐观锁（框架兜底）**：基于 `expected_mtime_ms + expected_size_bytes` 防止覆盖用户修改（由框架从 Read 结果自动注入）
- **沙箱安全**：路径必须在 project_root 内
- **统一协议**：输出标准信封结构，便于 Agent 解析

> 注：新文件创建请使用 `Write` 工具；Edit 仅支持已有文件。

---

## 2. 接口规范

### 2.1 工具定义
- Internal Class Name: `EditTool`
- Python Module: `tools/builtin/edit_file.py`
- Agent Exposed Name: **`Edit`**

### 2.2 输入参数（JSON Schema）

```json
{
  "name": "Edit",
  "description": "Replace a single unique text segment in an existing file.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Path to the file (relative to project root, POSIX style). Required."
      },
      "old_string": {
        "type": "string",
        "description": "Exact text snippet to replace. MUST be unique. Include 2-5 lines of surrounding context. Do NOT include line numbers or escape newlines."
      },
      "new_string": {
        "type": "string",
        "description": "Replacement text. Ensure it fits syntactically in context."
      },
      "expected_mtime_ms": {
        "type": "integer",
        "description": "File mtime in ms from Read (stats.file_mtime_ms). Framework auto-injects when available.",
        "default": null
      },
      "expected_size_bytes": {
        "type": "integer",
        "description": "File size in bytes from Read (stats.file_size_bytes). Framework auto-injects when available.",
        "default": null
      },
      "dry_run": {
        "type": "boolean",
        "description": "If true, compute diff but do not write to disk.",
        "default": false
      }
    },
    "required": ["path", "old_string", "new_string"]
  }
}
```

---

## 3. 输出结构（标准信封）

顶层字段：`status`, `data`, `text`, `stats`, `context`（error 时额外 `error`）。

### 3.1 data 字段
- `applied` (boolean): 是否写入落盘（dry_run 时为 false）
- `diff_preview` (string): Unified Diff 预览
- `diff_truncated` (boolean): diff 是否被截断
- `replacements` (int): 实际替换次数（应为 1）

### 3.2 stats 字段
- `time_ms` (int)
- `bytes_written` (int)
- `lines_added` (int) ※若 diff 截断，仅统计预览范围
- `lines_removed` (int) ※若 diff 截断，仅统计预览范围

### 3.3 context 字段
- `cwd` (string)
- `params_input` (object)
- `path_resolved` (string)

---

## 4. 状态判定

- **success**：写入成功 + diff 未截断 + 非 dry_run
- **partial**：dry_run 或 diff_truncated
- **error**：路径非法 / 读写失败 / 锚点不唯一 / 乐观锁冲突等

---

## 5. 错误码映射（建议）

| 场景 | error.code | 说明 |
|---|---|---|
| 文件不存在 | NOT_FOUND | 目标文件必须存在（Edit 不创建） |
| 沙箱越权 | ACCESS_DENIED | 路径不在 project_root 内 |
| 目标是目录 | IS_DIRECTORY | 必须是文件 |
| old_string 为空 | INVALID_PARAM | 必须提供唯一锚点 |
| old_string 未匹配 | INVALID_PARAM | 提示重新 Read、检查缩进 | 
| old_string 匹配多处 | INVALID_PARAM | 提示增加上下文 | 
| 读写权限不足 | PERMISSION_DENIED | OS 级权限错误 |
| IO 错误 | EXECUTION_ERROR | 其它 I/O 错误 |
| 文件已被修改 | CONFLICT | 乐观锁冲突 |

---

## 6. 核心流程（MVP）

1. **参数校验**：path/old_string/new_string 必填且为字符串
2. **路径解析 + 沙箱校验**：禁止绝对路径，必须在 project_root 内
3. **存在性检查**：文件必须存在；否则 NOT_FOUND
4. **乐观锁校验（框架兜底）**：若文件存在，校验 `expected_mtime_ms` / `expected_size_bytes`（由框架自动注入）
5. **二进制检测**：包含 `\x00` 视为 BINARY_FILE
6. **换行探测**：统计 `\r\n` vs `\n`，记录原始行尾
7. **归一化匹配**：将内容/old/new 全部转为 `\n`，执行精确匹配
   - 匹配 0 次 → INVALID_PARAM（提示重新 Read）
   - 匹配 >1 → INVALID_PARAM（提示增加上下文）
8. **替换**：只替换第一次匹配结果
9. **还原换行**：如原始为 CRLF，整体恢复
10. **写入 + diff**：原子写入 + diff 预览（截断保护）

---

## 7. 提示词建议（放入 tools prompt）

```
Tool: Edit
Purpose: Replace a single, unique snippet in an existing file.

Rules:
- You MUST read the file immediately before editing.
- old_string must be an EXACT copy from Read output (no line numbers, no escaped \n).
- old_string must be unique; include 2-5 lines of surrounding context.
- Framework auto-injects expected_mtime_ms and expected_size_bytes after Read.
- If you get CONFLICT, re-read the file and re-apply changes.
```

---

## 8. 测试建议（MVP）

- 成功替换（唯一匹配）
- old_string 不存在 → INVALID_PARAM
- old_string 多处匹配 → INVALID_PARAM
- CRLF 文件替换后行尾不变
- dry_run 返回 partial 且不落盘
- CONFLICT（mtime/size 不匹配）
