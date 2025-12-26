Tool name: Glob
Tool description: Find files using glob-like patterns.
IMPORTANT:
- `pattern` is ALWAYS relative to `path` (the search root). Do NOT include project root in the pattern.
- Use '**/*' ONLY when the user explicitly asks to include subdirectories / recursive / whole project.

Examples:
- '*.md' with path='.' : Markdown files in the current directory only.
- '**/*.ts' with path='src' : All .ts files under src recursively.
- 'test_*.py' with path='core' : Matching files in core directory only.
