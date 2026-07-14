grep_prompt = """
Tool name: Grep
Tool description:
Searches text-file contents using regular expressions in deterministic path and line order.
Prefers rg (ripgrep) when available and falls back to a Python implementation.
Follows the Universal Tool Response Protocol (顶层字段仅: status/data/text/error/stats/context).

Usage
- ALWAYS use Grep for searching inside file contents.
- Do NOT call shell grep/rg; this tool is sandboxed to the project root.
- pattern is regex; glob is an optional file filter.
- path is a directory relative to the project root.
- Common noisy directories (.git, node_modules, dist, build, __pycache__, .venv) are ignored automatically.

Parameters (JSON object)
- pattern (string, required)
  Regex pattern to search in file contents. Examples: "class\\s+User", "TODO", "def\\s+\\w+".
- path (string, optional, default ".")
  Directory to search in, relative to project root.
- glob (string, optional)
  Glob pattern to filter which files are searched. Examples: "*.ts", "src/**/*.py", "**/*.md".
- case_sensitive (boolean, optional, default false)
  false -> case-insensitive (default)
  true  -> case-sensitive
- limit (integer, optional, default 100, range 1-200)
  Max number of matching lines to return.

Response Structure
- status: "success" | "partial" | "error"
  - "success": search completed normally
  - "partial": results were truncated by the match/line budget, or Python fallback was used
  - "error": invalid input or a search-root error
- data.matches: Array<{file: string, line: number, text: string}>
  List of matches with file path, line number, and matched text.
- data.truncated: boolean
  true if results were truncated by the requested match limit or the per-line text budget.
- data.truncation_reasons: Array<"match_limit"|"line_length"> (optional)
  Present when data.truncated is true.
  Returned matching-line text is capped at 2,000 characters.
- data.fallback_used: boolean (optional)
  true if Python fallback was used instead of ripgrep.
- data.fallback_reason: "rg_not_found" | "rg_failed" | "rg_unsupported_pattern" (optional)
  Reason for using Python fallback.
- text: Human-readable summary with match list.
- stats: {time_ms, searched_files, matched_lines}
- context: {cwd, params_input, path_resolved}
- error: {code, message} (only when status="error")

Error Codes
- NOT_FOUND: search root does not exist.
- ACCESS_DENIED: path outside project root (sandbox violation).
- INVALID_PARAM: invalid regex or parameters.
- INTERNAL_ERROR: unexpected failure.

Examples
1) Find TODO comments in all TypeScript files

{"pattern": "TODO", "glob": "**/*.ts"}

2) List all class definitions under src/

{"pattern": "class\\s+\\w+", "path": "src"}

3) Case-sensitive search for the word "Password" in TS files

{"pattern": "Password", "path": ".", "glob": "src/**/*.ts", "case_sensitive": true}

4) Limit results to the first 3 deterministic matches

{"pattern": "class ", "path": ".", "limit": 3}
"""
