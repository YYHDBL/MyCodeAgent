"""Skill tool prompt."""

skill_prompt = """
Tool name: Skill
Tool description:
Loads a skill (structured instructions) from the local skills directory.
Follows the Universal Tool Response Protocol (top-level fields: status/data/text/error/stats/context).

Usage
- Use Skill when a task matches a named skill or the user explicitly requests it.
- Only load skills when needed; do not pre-load all skills.

Parameters (JSON object)
- name (string, required)
  Skill identifier (e.g., "code-review").
- args (string, optional)
  Optional arguments passed to the skill.

Available Skills
{{available_skills}}

Examples
1) Load a skill

{"name": "code-review"}

2) Load with arguments

{"name": "code-review", "args": "src/main.py"}

Response Structure
- status: "success" | "partial" | "error"
- data: { name, base_dir, content }
- text: summary
- stats: {time_ms, ...}
- context: {cwd, params_input}
- error: {code, message} (only when status="error")
"""
