# 多次编辑工具设计文档（MultiEditTool Standardized）

版本：1.0.0  
协议标准：Standard Envelope v1.0（详见 `docs/通用工具响应协议.md`）

## 1. 概述

MultiEditTool 是 Code Agent 的“批量原子编辑”工具，用于对**同一个文件**执行多处修改并一次性落盘。它遵循统一响应协议，强调**一次 Read、多处修改、一次写入**，避免多次 Edit 导致的上下文浪费与中间态风险。

核心特性：
- **原子性**：要么全部成功写入，要么完全不改动
- **低心智负担**：所有 `old_string` 都基于**原始文件内容**匹配（无需预测前一次修改的结果）
- **冲突检测**：多处修改若命中重叠区域直接失败，避免“互相覆盖”
- **乐观锁（框架兜底）**：基于 `expected_mtime_ms + expected_size_bytes` 防止覆盖用户修改
- **统一协议**：输出标准信封结构，便于 Agent 解析

> 注：若修改存在**顺序依赖**（A→B→C 需要依次生效），请分步调用 `Edit`，或等待后续“顺序模式”扩展。

---

## 2. 接口规范

### 2.1 工具定义
- Internal Class Name: `MultiEditTool`
- Python Module: `tools/builtin/edit_file_multi.py`
- Agent Exposed Name: **`MultiEdit`**

### 2.2 输入参数（JSON Schema）

```json
{
  "name": "MultiEdit",
  "description": "Apply multiple edits to a single file atomically. All edits are matched against the original file content.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Path to the file (relative to project root, POSIX style). Required."
      },
      "edits": {
        "type": "array",
        "description": "List of edits to apply. Each old_string must be unique in the ORIGINAL file content.",
        "minItems": 1,
        "items": {
          "type": "object",
          "properties": {
            "old_string": {
              "type": "string",
              "description": "Exact text snippet to replace. Must be unique in the original file."
            },
            "new_string": {
              "type": "string",
              "description": "Replacement text."
            }
          },
          "required": ["old_string", "new_string"]
        }
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
    "required": ["path", "edits"]
  }
}
```

---

## 3. 输出结构（标准信封）

顶层字段：`status`, `data`, `text`, `stats`, `context`（error 时额外 `error`）。

### 3.1 data 字段
- `applied` (boolean): 是否写入落盘（dry_run 时为 false）
- `diff_preview` (string): Unified Diff 预览（包含所有修改）
- `diff_truncated` (boolean): diff 是否被截断
- `replacements` (int): 实际替换次数（通常等于 edits 数量）
- `failed_index` (int | null): 若失败，标记第几个 edit 失败（从 0 开始）

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

- **success**：所有 edits 匹配成功 + 写入成功 + diff 未截断 + 非 dry_run  
- **partial**：dry_run 或 diff_truncated  
- **error**：任一 edit 未匹配/不唯一/冲突、路径非法、IO 错误、乐观锁冲突等

---

## 5. 错误码映射（建议）

| 场景 | error.code | 说明 |
|---|---|---|
| 文件不存在 | NOT_FOUND | 目标文件必须存在（MultiEdit 不创建） |
| 沙箱越权 | ACCESS_DENIED | 路径不在 project_root 内 |
| 目标是目录 | IS_DIRECTORY | 必须是文件 |
| old_string 为空 | INVALID_PARAM | 必须提供唯一锚点 |
| old_string 未匹配 | INVALID_PARAM | 提示重新 Read、检查缩进 |
| old_string 匹配多处 | INVALID_PARAM | 提示增加上下文 |
| 多处修改发生重叠 | INVALID_PARAM | 提示拆分修改或减少冲突 |
| 读写权限不足 | PERMISSION_DENIED | OS 级权限错误 |
| IO 错误 | EXECUTION_ERROR | 其它 I/O 错误 |
| 文件已被修改 | CONFLICT | 乐观锁冲突 |
| 二进制文件 | BINARY_FILE | 检测到 `\\x00` |

---

## 6. 核心流程（MVP）

1. **参数校验**：path / edits 必填且为字符串，edits 非空  
2. **路径解析 + 沙箱校验**：禁止绝对路径，必须在 project_root 内  
3. **存在性检查**：文件必须存在；否则 NOT_FOUND  
4. **乐观锁校验（框架兜底）**：校验 `expected_mtime_ms` / `expected_size_bytes`  
5. **二进制检测**：包含 `\\x00` 视为 BINARY_FILE  
6. **换行探测**：统计 CRLF/LF，记录原始行尾  
7. **匹配定位（基于原文件）**：  
   - 对每个 edit，统计 `old_string` 在原内容中的匹配次数  
   - 0 次或 >1 次 → INVALID_PARAM  
   - 记录每个 edit 的 [start, end) 区间  
8. **冲突检测**：区间重叠则失败（INVALID_PARAM）  
9. **倒序应用**：按区间起点倒序替换，避免索引偏移  
10. **还原换行**：若原始为 CRLF，整体恢复  
11. **写入 + diff**：原子写入 + diff 预览（截断保护）

---

## 7. 提示词建议（放入 tools prompt）

```
Tool: MultiEdit
Purpose: Apply multiple independent edits to ONE file atomically.

Rules:
- All old_string anchors must match the ORIGINAL file content from Read.
- Do not assume previous edits have been applied.
- If edits overlap, the tool will fail with INVALID_PARAM.
- Use MultiEdit instead of calling Edit multiple times on the same file.
```

---

## 8. 边缘场景测试用例

1. **多点独立修改成功**  
   - Edit 1: 替换函数注释  
   - Edit 2: 修改常量值  
   - 结果：一次性成功，diff 包含两处修改  

2. **匹配失败回滚**  
   - Edit 1: 成功匹配  
   - Edit 2: 目标不存在  
   - 结果：整体失败，文件不变，failed_index=1  

3. **冲突检测**  
   - Edit 1: 替换某函数签名  
   - Edit 2: 替换该函数内部的一行（包含在 Edit 1 覆盖范围）  
   - 结果：INVALID_PARAM（冲突），文件不变

