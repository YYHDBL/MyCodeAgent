"""Task tool prompt."""

task_prompt = """
Tool name: Task
Tool description:
Launches a subagent to handle complex, multi-step tasks in an isolated session.
The subagent uses a restricted toolset and returns a single final result.

When to use Task
- When the request is complex, multi-step, or benefits from focused sub-work.
- When you want a subagent to explore or summarize and return a concise report.

Subagent type guidance
- general: default for complex execution and focused sub-work.
- explore: scan the codebase, find entry points, locate relevant files.
- plan: generate implementation steps, dependencies, risks.
- summary: compress long outputs or multi-file findings.

Model guidance
- Choose "light" for simpler tasks when appropriate.
- Choose "main" for complex reasoning or when depth/accuracy is critical.
- Decide based on task complexity; do not hard-code by subagent type.

When NOT to use Task
- If you already know the exact file path to read; use Read instead.
- If you only need a quick file search; use Glob or Grep instead.
- For simple, single-step tasks that the main agent can do directly.

Parameters (JSON object)
- description (string, required)
  Short summary of the delegated task.
- prompt (string, required)
  Full, self-contained instructions for the subagent.
- subagent_type (string, required)
  Role to select a system prompt: general | explore | summary | plan.
- model (string, optional)
  Choose "main" or "light". The main agent decides based on task complexity.

Usage notes
1) Only one Task call is supported at a time (single tool call).
2) The subagent returns one final result; summarize it back to the user.
3) Your prompt should be detailed and specify exactly what to return.
4) Subagents must not call Task again.

Example
{"description": "Explore auth flow", "prompt": "Find key files and summarize auth flow. Return file paths and purpose.", "subagent_type": "explore", "model": "light"}
"""
