Tool: search_code
Description:
Search file contents using regex.
- IMPORTANT: `pattern` is matched within the search root `path` (relative to project root).
- IMPORTANT: Results are sorted by file modification time (newest first).
- If results are truncated, use a more specific 'path' or add an 'include' filter.
- 'include' supports glob patterns like '*.ts' or 'src/**/*.py'.
- Do NOT call shell commands like grep or rg directly. Always use this tool for content search.

Examples:
- {"pattern": "class\\s+User", "path": "src", "include": "**/*.ts"}
- {"pattern": "TODO", "path": ".", "case_sensitive": false}
