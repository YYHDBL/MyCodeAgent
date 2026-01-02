# 多次编辑工具设计文档（MultiEditTool Standardized）

版本：1.0.0
协议标准：Standard Envelope v1.0（详见 `docs/通用工具响应协议.md`）

## 1. 概述

MultiEditTool 是 Code Agent 的“批量原子编辑”工具，用于对**同一个文件**执行一系列顺序依赖的修改。

核心特性：

* **事务原子性 (Transactional Atomicity)**：所有编辑操作要么全部成功，要么全部失败（All-or-Nothing）。绝不产生“改了一半”的损坏文件。
* **顺序执行 (Sequential Execution)**：编辑操作按数组顺序依次在内存中应用。后续的编辑必须基于前一次编辑后的结果进行匹配。
* **内存预演 (In-Memory Dry Run)**：在写入磁盘前，先在内存中完成所有匹配和替换的校验。
* **统一协议与安全**：继承 EditTool 的乐观锁、沙箱校验和标准信封输出。

> 场景：重构（Renaming）、同时修改函数声明与调用、清理多个相关的代码块。

---

## 2. 接口规范

### 2.1 工具定义

* Internal Class Name: `MultiEditTool`
* Python Module: `tools/builtin/edit_file_multi.py`
* Agent Exposed Name: **`MultiEdit`**

### 2.2 输入参数（JSON Schema）

```json
{
  "name": "MultiEdit",
  "description": "Perform multiple atomic edits to a single file sequentially.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Path to the file (relative to project root). Required."
      },
      "edits": {
        "type": "array",
        "description": "List of edits to apply in order. Each edit depends on the result of the previous one.",
        "minItems": 1,
        "items": {
          "type": "object",
          "properties": {
            "old_string": {
              "type": "string",
              "description": "Exact text to replace. Must be unique in the CURRENT state of the file."
            },
            "new_string": {
              "type": "string",
              "description": "Replacement text."
            },
            "replace_all": {
              "type": "boolean",
              "description": "If true, replace all occurrences of old_string. Use with caution.",
              "default": false
            }
          },
          "required": ["old_string", "new_string"]
        }
      },
      "expected_mtime_ms": {
        "type": "integer",
        "description": "Optimistic lock (from Read). Framework auto-injects.",
        "default": null
      },
      "dry_run": {
        "type": "boolean",
        "description": "Compute final diff without writing.",
        "default": false
      }
    },
    "required": ["path", "edits"]
  }
}

```

---

## 3. 输出结构（标准信封）

顶层字段：`status`, `data`, `text`, `stats`, `context`。

### 3.1 data 字段

* `applied` (boolean): 是否落盘
* `diff_preview` (string): 最终结果与原始文件的 Unified Diff
* `diff_truncated` (boolean)
* `replacements` (int): 成功应用的编辑总数
* `failed_index` (int | null): 如果失败，记录是第几个 edit 导致的（从 0 开始）

### 3.2 text 字段摘要规范

* **成功**：`"Successfully applied 3 edits to 'src/main.py'."`
* **失败**：`"Failed at edit #2: 'old_string' not found. No changes were made."`

---

## 4. 状态判定

* **success**：所有 Edits 校验通过 + 写入成功 + 非 dry_run
* **partial**：dry_run 或 diff_truncated
* **error**：任一 Edit 校验失败（未找到/不唯一）、IO 错误、乐观锁冲突

---

## 5. 错误码映射

| 场景 | error.code | 说明 |
| --- | --- | --- |
| 序列中某处 old_string 未找到 | EDIT_FAILED | 事务回滚，指明是第几个 edit |
| 序列中某处 old_string 不唯一 | EDIT_FAILED | 事务回滚，指明是第几个 edit |
| 编辑导致空文件（可选策略） | EMPTY_FILE_PROTECTION | 防止误删（MVP 可暂不校验） |
| IO/权限/乐观锁 | (同 EditTool) | NOT_FOUND, CONFLICT 等 |

---

## 6. 核心流程（Pipeline）

1. **基础校验**：路径合法性、文件存在性、二进制检测。
2. **乐观锁校验**：对比 `expected_mtime_ms`。
3. **加载与归一化**：
* 读取文件内容 `buffer`。
* 侦测换行符 `original_newline`。
* 将 `buffer` 转为 LF (`\n`) 格式。


4. **内存顺序执行（Transaction Loop）**：
* 创建 `current_content = buffer`。
* 遍历 `edits` 数组 (index `i`, item `edit`)：
* **匹配**：在 `current_content` 中查找 `edit.old_string` (LF 归一化后)。
* **校验**：
* Count == 0: `throw error(code="EDIT_FAILED", msg="Edit #{i+1} failed: target text not found")`
* Count > 1 且 `!replace_all`: `throw error(code="EDIT_FAILED", msg="Edit #{i+1} failed: ambiguous match")`


* **应用**：`current_content = replace(current_content, edit)`。
* **迭代**：更新 `current_content` 供下一次 edit 使用。




5. **还原换行**：如果 `original_newline` 是 CRLF，将 `current_content` 转换回 CRLF。
6. **原子写入**：
* 若 `!dry_run`，调用 `fs.writeFile(path, current_content)`。


7. **生成反馈**：
* 计算原始 `buffer` 与最终 `current_content` 的 Diff。



---

## 7. 提示词建议（放入 tools prompt）

```
Tool: MultiEdit
Purpose: Apply multiple sequential edits to the SAME file atomically.

Usage:
- Prefer this over calling Edit multiple times for the same file.
- CRITICAL: Edits are applied IN ORDER. Edit #2 sees the file AS MODIFIED by Edit #1.
  - Example: If Edit #1 renames "foo" to "bar", Edit #2 must look for "bar", not "foo".
- Atomicity: If any edit in the list fails (e.g., text not found), the ENTIRE operation fails and the file remains unchanged.
- Context: Each `old_string` must be unique in the file state at that step.

```

---

## 8. 边缘场景测试用例

1. **依赖链成功**：
* Edit 1: `A -> B`
* Edit 2: `B -> C`
* 结果：文件中 A 变成了 C。


2. **依赖链断裂（失败回滚）**：
* Edit 1: `A -> B` (成功)
* Edit 2: `X -> Y` (X 不存在)
* 结果：报错，文件保持全是 A 的状态（Edit 1 未写入）。


3. **幻觉冲突**：
* Edit 1: 删除了一段代码。
* Edit 2: 试图修改 Edit 1 刚刚删除的代码。
* 结果：Edit 2 报错 `target text not found`，整体回滚。