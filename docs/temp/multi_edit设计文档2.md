 批量编辑工具设计文档（MultiEditTool Standardized）
版本：1.0.0
协议标准：Standard Envelope v1.0
1. 概述
MultiEdit 工具允许 Agent 在一次操作中对同一个文件执行多处不同的修改。
核心价值：
原子性 (Atomicity)：所有编辑视为一个事务。要么全部成功，要么全部不执行。避免文件处于“改了一半”的中间坏状态。
一致性上下文 (Context Consistency)：Agent 基于同一个文件版本生成所有修改，无需预测“修改A后文件长什么样”。
冲突检测 (Collision Detection)：自动检测多个编辑请求是否修改了同一行或重叠区域，防止逻辑冲突。
适用场景：重构（Refactoring）、清理无用引用（Unused Imports）、批量修改变量名等。
2. 接口规范
2.1 工具定义
Agent Exposed Name: BatchEdit (或 MultiEdit)
2.2 输入参数（JSON Schema）
JSON

{
  "name": "BatchEdit",
  "description": "Apply multiple distinct edits to a single file atomically.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Path to the file (relative to project root). Required."
      },
      "edits": {
        "type": "array",
        "description": "List of edit operations to apply sequentially.",
        "minItems": 1,
        "items": {
          "type": "object",
          "properties": {
            "old_string": {
              "type": "string",
              "description": "Exact text snippet to replace. Must be unique in the original file content."
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
        "description": "Optimistic lock: File mtime from last Read.",
        "default": null
      },
      "dry_run": {
        "type": "boolean",
        "description": "If true, returns the combined diff without writing.",
        "default": false
      }
    },
    "required": ["path", "edits"]
  }
}
3. 输出结构（标准信封）
3.1 data 字段
applied (boolean): 是否落盘。
diff_preview (string): 包含所有修改的合并 Unified Diff。
replacements_count (int): 成功执行的替换总数。
collisions (array): 若发生冲突，返回冲突的编辑项索引（可选）。
3.2 示例响应
JSON

{
  "status": "success",
  "data": {
    "applied": true,
    "replacements_count": 3,
    "diff_preview": "@@ -10,2 +10,2 @@\n- var a = 1;\n+ const a = 1;\n@@ -45,1 +45,1 @@\n- function foo() {\n+ export function foo() {"
  },
  "text": "Successfully applied 3 edits to 'src/utils.ts'.",
  "stats": { "time_ms": 12 }
}
4. 核心流程与冲突算法
这是 MultiEdit 最复杂也是最关键的部分。
4.1 预处理
校验：路径合法性、存在性、乐观锁（expected_mtime_ms）校验同 SingleEdit。
读取：一次性读取文件内容到内存 rawContent。
归一化：探测换行符，将内容转为 LF 模式的 searchContent。
4.2 匹配与定位 (Mapping Phase)
遍历 edits 数组，为每个 edit 计算在原文件中的绝对位置区间 [start, end)。
对于第 i 个 edit：
在 searchContent 中查找 old_string。
唯一性检查：必须匹配且仅匹配一次。
记录：{ index: i, start: number, end: number, new_content: string }
4.3 冲突检测 (Collision Detection)
在应用任何修改前，必须确保所有 edit 的操作区间互不重叠。
将所有匹配记录按 start 从小到大排序。
遍历排序后的列表，检查：
current.start < previous.end ?
如果为真，说明 Edit A 的修改范围覆盖了 Edit B 的锚点。
动作：抛出 COLLISION_ERROR，告知 Agent 第 X 个和第 Y 个修改冲突。
4.4 原子应用 (Atomic Application)
倒序替换法：为了防止替换导致的索引偏移，必须从文件末尾向前应用修改（或者使用基于偏移量的构建器）。
例如：先应用位置在 1000 的修改，再应用位置在 50 的修改。这样修改位置 1000 时，位置 50 的索引不会变。
内存构建：在内存中生成 finalContent。
4.5 写入与收尾
格式还原：将 finalContent 的换行符还原为原文件格式。
写入：fs.writeFileSync。
生成 Diff：对比 rawContent 和 finalContent 生成预览。
5. 错误码扩展
在 SingleEdit 基础上增加：
错误码说明建议COLLISION_DETECTED多个 edit 修改了重叠的区域建议分步修改或合并逻辑PARTIAL_MATCH_FAIL数组中某一个 edit 未找到匹配整个批次均不执行，提示修正该项DUPLICATE_EDITSedits 数组包含完全相同的操作提示去重6. 系统提示词 (System Prompt)
Markdown

Tool: BatchEdit
Purpose: Apply multiple changes to ONE file in a single atomic operation.

Best Practices:- Use this instead of multiple `Edit` calls when refactoring a file.- All `old_string`s are matched against the ORIGINAL file content. Do not try to predict how the file changes after the first edit.- Ensure edits do not overlap (e.g., do not edit a function and also delete the class containing it).- If any edit in the list fails to match, the ENTIRE operation fails. Verify all anchors.