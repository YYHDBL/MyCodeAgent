glob_prompt = """
Tool name: Glob
Tool description:
Finds files by name using glob patterns (e.g. **/*.ts).
Matches paths relative to the search root (path) and returns file paths only.
Common noisy directories (e.g. .git, node_modules, dist, build) are skipped by default.

Usage
- Use Glob to find files by name or pattern (not file contents).
- pattern is glob, not regex:
  - *.md -> current directory only
  - **/*.md -> recursive
  - src/**/*.test.ts -> recursive under src/
- path is the search root, relative to project root:
  - "." -> whole project
  - "src" -> only ./src
- include_hidden controls dotfiles/dirs; include_ignored controls ignored dirs (use sparingly).

Parameters (JSON object)
- pattern (string, required)
  Glob pattern relative to the search root (path).
- path (string, optional, default ".")
  Directory to start the search from, relative to project root.
- limit (integer, optional, default 50, range 1-200)
  Max number of matches to return.
- include_hidden (boolean, optional, default false)
  Include dotfiles/dot-directories.
- include_ignored (boolean, optional, default false)
  Traverse ignored directories (node_modules, dist, build, etc.).

Examples
1) List all Markdown files in the project

Glob[{"pattern": "**/*.md", "path": "."}]

2) Only list top-level TypeScript files under src/

Glob[{"pattern": "*.ts", "path": "src"}]

3) Include hidden files

Glob[{"pattern": "**/*.json", "path": ".", "include_hidden": true}]
"""
