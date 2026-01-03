LS_prompt = """
Tool name: LS
Tool description:
Lists files and directories in a target directory. Safe and sandboxed to the project root.
Supports pagination, hidden toggle, and ignore globs.
Follows the Universal Tool Response Protocol (顶层字段仅: status/data/text/error/stats/context).

Usage
- Use LS to explore directory structure or see what is inside a folder.
- Do NOT use bash ls/find/dir; use this tool for consistent, safe output.
- Results are paginated with offset/limit.

Parameters (JSON object)
- path (string, optional, default ".")
  Directory path relative to project root (or absolute within root).
- offset (integer, optional, default 0)
  Pagination start index (>= 0).
- limit (integer, optional, default 100, range 1-200)
  Max entries to return.
- include_hidden (boolean, optional, default false)
  Include dotfiles/dot-directories (e.g. .git, .vscode).
- ignore (array, optional)
  Glob patterns to ignore (basename or relative path). Common noisy dirs are ignored by default.

Response Structure
- status: "success" | "partial" | "error"
  - "success": all entries returned within limit
  - "partial": results truncated (more entries available, use offset to paginate)
  - "error": path not found, access denied, or invalid parameters
- data.entries: Array<{path: string, type: "file"|"dir"|"link"}>
  List of entries with relative paths and types.
- data.truncated: boolean
  true if results were truncated (status will be "partial").
- text: Human-readable summary with entry list.
- stats: {time_ms, total_entries, dirs, files, links, returned}
- context: {cwd, params_input, path_resolved}
- error: {code, message} (only when status="error")

Error Codes
- NOT_FOUND: path does not exist.
- ACCESS_DENIED: path outside project root (sandbox violation).
- INVALID_PARAM: invalid path/offset/limit/include_hidden.
- INTERNAL_ERROR: unexpected failure.

Examples
1) List project root (first page)
LS[{"path": ".", "limit": 50}]

2) List src/ (default ignores)
LS[{"path": "src", "offset": 0, "limit": 100}]

3) List logs/ but ignore .log files
LS[{"path": "logs", "limit": 100, "ignore": ["*.log"]}]

4) Include hidden directories
LS[{"path": ".", "include_hidden": true, "limit": 100}]
"""
