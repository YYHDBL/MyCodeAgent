grep_prompt = """
Tool name: Grep
Tool description:
Searches file contents using regular expressions. Results are sorted by file modification time (newest first).
Prefers rg (ripgrep) when available and falls back to a Python implementation.

Usage
- ALWAYS use Grep for searching inside file contents.
- Do NOT call shell grep/rg; this tool is sandboxed to the project root.
- pattern is regex; include is glob (file filter).
- path is a directory relative to the project root.
- Common noisy directories (.git, node_modules, dist, build, __pycache__, .venv) are ignored automatically.

Parameters (JSON object)
- pattern (string, required)
  Regex pattern to search in file contents. Examples: "class\\s+User", "TODO", "def\\s+\\w+".
- path (string, optional, default ".")
  Directory to search in, relative to project root.
- include (string, optional)
  Glob pattern to filter which files are searched. Examples: "*.ts", "src/**/*.py", "**/*.md".
- case_sensitive (boolean, optional, default false)
  false -> case-insensitive (default)
  true  -> case-sensitive

Examples
1) Find TODO comments in all TypeScript files

Grep[{"pattern": "TODO", "include": "**/*.ts"}]

2) List all class definitions under src/

Grep[{"pattern": "class\\s+\\w+", "path": "src"}]

3) Case-sensitive search for the word "Password" in TS files

Grep[{"pattern": "Password", "path": ".", "include": "src/**/*.ts", "case_sensitive": true}]
"""
