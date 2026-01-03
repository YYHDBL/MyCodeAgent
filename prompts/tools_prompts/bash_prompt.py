bash_prompt = """
Tool name: Bash
Tool description:
Execute a shell command within the project sandbox. Supports command chaining (&&, ||, ;) and limited cd inside the project root.
Follows the Universal Tool Response Protocol (顶层字段仅: status/data/text/error/stats/context).

Usage
- Use Bash for build/test/run commands or system utilities that are not covered by other tools.
- Do NOT use shell commands for listing/searching/reading files:
  - Use LS for listing, Read for file contents, Grep for content search, Glob for filename search.
- Avoid interactive commands (vim/nano/top/htop/ssh/git rebase -i, etc.) — they are blocked.
- Prefer the `directory` parameter over `cd`. If you must use `cd`, it must stay within the project root.

Parameters (JSON object)
- command (string, required)
  The shell command to execute. Command chaining is allowed.
- directory (string, optional, default ".")
  Working directory relative to project root.
- timeout_ms (integer, optional, default 120000, max 600000)
  Command timeout in milliseconds.

Safety Notes (MVP)
- Commands are sandboxed to the project root; paths outside are denied.
- Blocked high-risk patterns include: sudo/su/doas, mkfs/fdisk/dd, rm -rf /, remote-script exec (curl|bash, wget|bash).
- Network tools like curl/wget are blocked by default in MVP (can be enabled via BASH_ALLOW_NETWORK=true).

Response Structure
- status: "success" | "partial" | "error"
  - "success": exit_code == 0 and not truncated
  - "partial": exit_code != 0, truncated output, or timeout with partial output
  - "error": invalid params, blocked command, path denied, or timeout with no output
- data: {stdout, stderr, exit_code, signal, truncated, command, directory}
- stats: {time_ms, stdout_bytes, stderr_bytes}
- context: {cwd, params_input, directory_resolved}

Examples
1) Run tests in the project root
Bash[{"command": "pytest tests"}]

2) Run a command in a subdirectory
Bash[{"command": "npm test", "directory": "frontend"}]

3) Chain commands (allowed)
Bash[{"command": "python -m pip --version && python -V"}]
"""
