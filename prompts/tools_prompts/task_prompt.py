"""Task tool prompt."""

task_prompt = """
Tool name: Task
Tool description:
Launches an isolated, read-only Explore Agent and returns a bounded structured result.

When to use Task
- When repository exploration would add noisy search history to the main context.
- When you need a focused codebase scan with findings and file evidence.

Capability boundary
- The only supported subagent_type is "explore".
- Explore can use only Glob, Grep, and Read.
- Explore cannot use Bash, Edit, or Task.
- Task does not provide persistent, parallel, background, plan, summary, or general agents.

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
  Must be "explore".
- model (string, optional)
  Choose "main" or "light". The main agent decides based on task complexity.

Usage notes
1) Only one Task call is supported at a time (single tool call).
2) The parent receives only ExploreResult, not child history or raw session memory.
3) Your prompt should be detailed and specify exactly what to return.
4) Explore cannot call Task recursively.

Example
{"description": "Explore auth flow", "prompt": "Find key files and summarize auth flow. Return file paths and purpose.", "subagent_type": "explore", "model": "light"}
"""
