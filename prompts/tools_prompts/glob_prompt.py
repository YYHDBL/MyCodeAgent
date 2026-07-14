glob_prompt = """
Tool name: Glob
Tool description:
Lists one directory when pattern is omitted, or recursively finds files by glob pattern.
Matches paths relative to the search root (path) and returns project-relative paths.
Common noisy directories (e.g. .git, node_modules, dist, build) are skipped by default.
Follows the Universal Tool Response Protocol (顶层字段仅: status/data/text/error/stats/context).

Usage
- Use Glob to list a directory or find files by name or pattern (not file contents).
- pattern is glob, not regex:
  - *.md -> current directory only
  - **/*.md -> recursive
  - src/**/*.test.ts -> recursive under src/
- path is the search root, relative to project root:
  - "." -> whole project
  - "src" -> only ./src
- include_hidden controls dotfiles/dirs; include_ignored controls ignored dirs (use sparingly).

Parameters (JSON object)
- path (string, optional, default ".")
  Directory to start the search from, relative to project root.
- pattern (string, optional)
  Glob pattern relative to the search root (path). Omit it to list the directory.
- limit (integer, optional, default 100, range 1-200)
  Max number of matches to return.
- include_hidden (boolean, optional, default false)
  Include dotfiles/dot-directories.
- include_ignored (boolean, optional, default false)
  Traverse ignored directories (node_modules, dist, build, etc.).

Response Structure
- status: "success" | "partial" | "error"
  - "success": search completed, all matches returned
  - "partial": results were truncated by limit
  - "error": invalid input or a search-root error
- data.paths: string[]
  List of matching file paths (relative to project root).
- data.truncated: boolean
  true if results were truncated by limit.
- text: Human-readable summary with match list.
- stats: {time_ms, matched, visited}
- context: {cwd, params_input, path_resolved}
- error: {code, message} (only when status="error")

Error Codes
- NOT_FOUND: search root does not exist.
- ACCESS_DENIED: path outside project root (sandbox violation).
- INVALID_PARAM: invalid pattern/path/limit.
- INTERNAL_ERROR: unexpected failure.

Examples
1) List the project root

{"path": "."}

2) List all Markdown files in the project

{"pattern": "**/*.md", "path": "."}

3) Only list top-level TypeScript files under src/

{"pattern": "*.ts", "path": "src"}

4) Include hidden files

{"pattern": "**/*.json", "path": ".", "include_hidden": true}
"""
