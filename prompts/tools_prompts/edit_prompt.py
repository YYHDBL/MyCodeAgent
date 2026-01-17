"""EditTool 的提示词定义

该提示词用于向 LLM 描述 Edit 工具的功能和使用方式。
"""

edit_prompt = """Edit: Replace a single, unique text snippet in an existing file.

## Purpose
Make surgical edits to existing files by replacing one specific text segment. Unlike Write (which replaces entire file content), Edit allows precise modifications without rewriting the whole file.

## Key Features
1. **Unique Anchor Replacement**: old_string must appear exactly once in the file.
2. **Format Agnostic**: Automatically handles CRLF/LF differences.
3. **Conflict Prevention**: Framework auto-injects mtime/size from prior Read.
4. **Diff Preview**: Returns a unified diff showing your changes.
5. **Dry Run Mode**: Use `dry_run=true` to preview changes without writing.

## Parameters
- `path` (string, required): Relative path to the file. POSIX style (use `/`), no absolute paths.
- `old_string` (string, required): Exact text to replace. **MUST be unique** in the file. Copy directly from Read output.
- `new_string` (string, required): Replacement text. Can be empty to delete old_string.
- `dry_run` (boolean, optional): If true, only compute diff without writing. Default: false.

Note: `expected_mtime_ms` and `expected_size_bytes` are **automatically injected by the framework** after you Read the file. You do NOT need to pass them manually.

## Important Rules
1. **ALWAYS Read the file immediately before editing**. The framework needs fresh mtime/size.
2. **Copy old_string exactly** from Read output - no line numbers, no escaped `\\n`, preserve all whitespace.
3. **old_string must be unique**. If it matches multiple times, include 2-5 lines of surrounding context.
4. **Handle CONFLICT errors** by re-reading the file and re-applying your changes.
5. **Use Write for new files**. Edit only works on existing files.

## Response Structure
- status: "success" | "partial" | "error"
  - "success": edit applied successfully
  - "partial": dry_run or diff truncated
  - "error": invalid params, path denied, or I/O error
- data.applied: Whether the edit was actually applied (false if dry_run)
- data.diff_preview: Unified diff showing changes
- data.diff_truncated: Whether diff was truncated
- data.replacements: Number of replacements made (always 1 for successful Edit)
- text: Human-readable summary
- stats: {time_ms, lines_added, lines_removed, bytes_written}
- context: {cwd, params_input, path_resolved}
- error: {code, message} (only when status="error")

## Error Codes
- `NOT_FOUND`: File does not exist (use Write for new files)
- `INVALID_PARAM`: Missing parameters, old_string not found, or old_string matches multiple times
- `ACCESS_DENIED`: Path outside project root (sandbox violation)
- `PERMISSION_DENIED`: OS-level permission error
- `EXECUTION_ERROR`: Other I/O or execution errors
- `IS_DIRECTORY`: Target path is a directory
- `BINARY_FILE`: File appears to be binary
- `CONFLICT`: File was modified since you read it (re-read and retry)

## Examples

### Simple function rename
Step 1: Read the file
```
{"path": "src/utils.py"}
```

Step 2: Edit with exact match from Read output
```json
{
  "path": "src/utils.py",
  "old_string": "def old_function_name(x):",
  "new_string": "def new_function_name(x):"
}
```

### Multi-line replacement (include context for uniqueness)
```json
{
  "path": "src/config.py",
  "old_string": "# Database settings\\nDB_HOST = \\"localhost\\"\\nDB_PORT = 5432",
  "new_string": "# Database settings\\nDB_HOST = \\"production.db.example.com\\"\\nDB_PORT = 5432"
}
```

### Delete a block of code
```json
{
  "path": "src/main.py",
  "old_string": "# TODO: Remove this debug code\\nprint('debug info')\\n",
  "new_string": ""
}
```

### Preview changes before applying
```json
{
  "path": "src/api.py",
  "old_string": "return {'status': 'ok'}",
  "new_string": "return {'status': 'success', 'code': 200}",
  "dry_run": true
}
```

## Common Mistakes to Avoid
1. **Don't add line numbers** - Copy text exactly as shown in Read output, without the "N | " prefix.
2. **Don't escape newlines** - Use actual newlines in old_string/new_string, not `\\n`.
3. **Don't guess the content** - Always Read first to see the exact current state.
4. **Don't use Edit for new files** - Use Write instead.
5. **Don't ignore CONFLICT errors** - They mean the file changed; re-read and retry.
"""
