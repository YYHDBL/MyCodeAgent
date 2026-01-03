# TodoWrite 工具设计文档（MVP / 声明式覆盖）
版本：1.0.0  
协议标准：Standard Envelope v1.0（详见 `docs/通用工具响应协议.md`）

## 1. 概述
TodoWrite 是面向 Code Agent 的**任务列表管理工具**，用于在复杂任务中保持目标一致性、降低偏航风险，并通过“末尾复述（recap）”把当前目标压缩到上下文尾部，提高模型短期注意力命中率。

核心目标：
- **决策留给模型**：拆解/调整/取消任务由模型决定。
- **低心智负担**：模型只提交“当前完整列表”，不做 diff 或 id 维护。
- **工具兜底**：参数校验、统计、recap 生成与持久化由工具完成。
- **展示分离**：`data` 面向模型（结构化），`text` 面向用户（简洁 UI 展示）。

## 2. 角色与职责边界
### 2.1 模型负责
- 任务拆解、优先级与取消决策
- 更新任务状态（pending / in_progress / completed / cancelled）
- 在需要时重新规划并提交完整列表
  - 必须提供 `summary`（总体任务概述）

### 2.2 工具负责
- 参数校验（任务数量/长度/状态）
- 生成**简短 recap**
- 生成**用户可见的任务清单文本**（`text` 字段）
- 在任务**整体完成**时写入 `memory/todos/todoList-YYYYMMDD-HHMMSS.md`

## 3. 接口规范
### 3.1 工具定义
- Internal Class Name: `TodoWriteTool`（待实现）
- Python Module: `tools/builtin/todo_write.py`（规划路径）
- Agent Exposed Name: **`TodoWrite`**

### 3.2 输入参数（声明式覆盖）
**说明**：模型提交“当前完整 todo 列表”。工具以此**覆盖**旧列表，并在整体完成时写入日志。

```json
{
  "name": "TodoWrite",
  "description": "Overwrite the todo list with the current complete list. Framework persists and returns the updated list and recap.",
  "parameters": {
    "type": "object",
    "properties": {
      "summary": {
        "type": "string",
        "description": "Overall task summary (required by the model)."
      },
      "todos": {
        "type": "array",
        "description": "The full todo list (overwrites existing list).",
        "items": {
          "type": "object",
          "properties": {
            "content": {
              "type": "string",
              "description": "Todo text."
            },
            "status": {
              "type": "string",
              "enum": ["pending", "in_progress", "completed", "cancelled"],
              "description": "Todo status."
            },
            "id": {
              "type": "string",
              "description": "Optional todo id (framework may assign/reuse)."
            }
          },
          "required": ["content", "status"],
          "additionalProperties": false
        }
      }
    },
    "required": ["summary", "todos"]
  }
}
```

> 约束：
> - 子任务数量上限：10
> - 子任务描述长度上限：60 字
> - 列表中**最多一个** `in_progress`（允许 0 或 1）

## 4. 数据模型
TodoItem 最小字段集（MVP）：
```json
{
  "id": "todo_123",
  "content": "修复 multi_edit 重叠检测",
  "status": "in_progress"
}
```

- `id` 由工具生成，模型不必提供；**传入的 id 会被忽略**。
- MVP 阶段每次更新生成新 id（不做复用）。

## 5. 输出结构（标准信封）
TodoWrite 必须遵循通用工具响应协议，顶层仅允许：
`status`, `data`, `text`, `stats`, `context`（错误时包含 `error`）。

### 5.1 data 字段（模型侧）
- `todos` (array): 当前完整 todo 列表（已更新）
- `recap` (string): **简短复述**，用于放入上下文末尾
- `summary` (string): 总体任务概述（回显）

示例：
```json
{
  "status": "success",
  "data": {
    "todos": [
      {"id": "t1", "content": "修复重叠检测", "status": "in_progress"},
      {"id": "t2", "content": "更新文档", "status": "pending"},
      {"id": "t3", "content": "性能优化脚本", "status": "cancelled"}
    ],
    "recap": "[1/3] In progress: 修复重叠检测. Pending: 更新文档. Cancelled: 性能优化脚本.",
    "summary": "修复 multi_edit 重叠检测并完善文档"
  },
  "text": "Updated todos: 1 in_progress, 1 pending, 1 cancelled.",
  "stats": {
    "total": 3,
    "pending": 1,
    "in_progress": 1,
    "completed": 0,
    "cancelled": 1
  },
  "context": {
    "cwd": ".",
    "params_input": {
      "todos": [{"content": "修复重叠检测", "status": "in_progress"}]
    }
  }
}
```

## 6. Recap 生成规范（核心）
recap 由工具自动生成，目标是“**短、明确、可复述**”。

建议格式：
- 仅列出：
  - `in_progress`（1 条）
  - `pending`（最多 3 条）
  - `cancelled`（最多 2 条）
- `completed` 通常不复述
- 总长度建议 < 300 字

示例：
```
[1/5] In progress: 修复重叠检测.
Pending: 更新文档; 修复测试.
Cancelled: 性能优化脚本.
```

> 进度指示格式：`[done/total]`，其中 `done = completed + cancelled`（如 `[1/5]`）。

## 7. 最简 UI 规范（用户侧展示）
工具在 `text` 字段中输出简洁任务清单，供用户查看；模型应以 `data` 为准：
```
--- TODO UPDATE ---
[▶] 修复重叠检测
[ ] 更新文档
[~] 性能优化脚本
-------------------
```

## 8. 错误处理规范
### 8.1 错误码建议
- `INVALID_PARAM`: 参数缺失、状态非法
- `INTERNAL_ERROR`: 意外异常

### 8.2 典型错误
- 同时出现多个 `in_progress` → `INVALID_PARAM`

## 9. 行为准则（提示词约束）
建议在提示词中强调（结合 Claude / Gemini / Kode 的优点，适配本项目）：
- **使用时机**：仅当任务≥3步或用户明确要求进度跟踪时使用；简单问答不使用。
- **状态规范**：`pending` / `in_progress` / `completed` / `cancelled`；同一时刻最多一个 `in_progress`。
- **更新时机**：开始一个子任务前先标 `in_progress`，完成后立即标 `completed`；不需要的任务标 `cancelled`。
- **提交方式**：始终提交**完整列表（声明式覆盖）**，不要做增量补丁。
- **任务描述**：内容要短且可执行，避免过度抽象。
- **稳定性**：列表可动态调整，但每次调整都要更新 TodoWrite。

可用于系统提示词的简版片段：
```
Tool: TodoWrite
Use this tool only for multi-step tasks. Maintain a single in_progress item.
Always submit the full current list. Mark completed immediately, cancelled if no longer needed.
Always provide a concise overall summary in `summary`.
```

## 10. 持久化约定
**MVP 使用 Markdown 写入“完成日志”**（由工具写入）：  
- 位置：`memory/todos/todoList-YYYYMMDD-HHMMSS.md`（**会话内复用同一个文件**）  
- **仅在整体任务完成时写入**（非完成状态不写）  
- 用 Markdown 任务列表与删除线表达已取消任务  
- 同一会话内多次完成任务时，**追加写入新的任务块**到同一文件  

**写入时机**：
- TodoWrite 成功返回后，若 `todos` 全部为 `completed` 或 `cancelled` → 写入  
- 其它情况下不写入持久化记录  

**文件内任务块标题格式**：
- `# task{递增id}-YYYYMMDD-HHMMSS`  
- 递增 id 为会话内计数

示例（写入完成日志）：
```
# task3-20250102-174233

总任务概述：修复 multi_edit 重叠检测并完善文档与测试

[3/4] Completed: 完成的任务.
- 修复 multi_edit 重叠检测逻辑
- 更新 multi_edit 文档
- 运行相关测试

[1/4] Cancelled: 取消的任务.
- ~~性能优化脚本~~
```
