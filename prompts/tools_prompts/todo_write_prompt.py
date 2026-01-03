TodoWrite_prompt = """
Tool name: TodoWrite
Tool description:
Manages a task list for multi-step tasks. Overwrites the todo list with the current complete list.
Use this tool to track progress, maintain goal consistency, and reduce context drift.
Follows the Universal Tool Response Protocol (顶层字段仅: status/data/text/error/stats/context).

When to Use
- Use ONLY for multi-step tasks (>=3 steps) or when user explicitly requests progress tracking.
- Do NOT use for simple questions or single-step tasks.

Usage Guidelines
- **Declarative Overwrite**: Always submit the FULL current list. Do not use incremental patches.
- **Single in_progress**: At most ONE todo can be 'in_progress' at any time (0 is allowed).
- **Update Timing**: Mark 'in_progress' BEFORE starting a sub-task, mark 'completed' immediately after finishing.
- **Immediate Updates**: After completing any sub-task, call TodoWrite immediately to update its status. Do not wait until all tasks are finished.
- **Cancellation**: Mark 'cancelled' for tasks no longer needed (instead of deleting).
- **Concise Content**: Keep todo descriptions short and actionable (max 60 chars).
- **Summary Required**: Always provide a concise overall summary in `summary`.

Parameters (JSON object)
- summary (string, required)
  Overall task summary describing the goal.
- todos (array, required, max 10 items)
  The full todo list (overwrites existing). Each item is an object with:
    - content (string, required, max 60 chars): Task description.
    - status (string, required): One of "pending", "in_progress", "completed", "cancelled".
    - id (string, optional): Task identifier. **Do not provide**; the tool assigns ids and ignores any provided id.

Constraints
- Max 10 todo items per list.
- Max 60 characters per todo content.
- At most 1 'in_progress' item at any time.

Status Values
- pending: Not yet started.
- in_progress: Currently being worked on (max 1 allowed).
- completed: Successfully finished.
- cancelled: No longer needed.

Response Structure
- status: "success" | "error"
- data.todos: Updated todo list with tool-assigned ids (for model).
- data.recap: Short summary for context tail (improves model attention).
- data.summary: Echoed task summary.
- data.persisted_to: Path to saved file (only when all tasks completed/cancelled).
- text: Human-readable UI block (for user display).
- stats: {time_ms, total, pending, in_progress, completed, cancelled}
- context: {cwd, params_input}

Persistence
- When ALL todos are completed or cancelled, the tool automatically persists a markdown log (no model action needed).

Examples
1) Initialize todo list for a feature

TodoWrite[{"summary": "Implement user authentication", "todos": [
  {"content": "Design auth flow", "status": "in_progress"},
  {"content": "Create login endpoint", "status": "pending"},
  {"content": "Add JWT validation", "status": "pending"}
]}]

2) Mark current task done, start next

TodoWrite[{"summary": "Implement user authentication", "todos": [
  {"content": "Design auth flow", "status": "completed"},
  {"content": "Create login endpoint", "status": "in_progress"},
  {"content": "Add JWT validation", "status": "pending"}
]}]

3) Complete all tasks (triggers persistence)

TodoWrite[{"summary": "Implement user authentication", "todos": [
  {"content": "Design auth flow", "status": "completed"},
  {"content": "Create login endpoint", "status": "completed"},
  {"content": "Add JWT validation", "status": "cancelled"}
]}]
"""
