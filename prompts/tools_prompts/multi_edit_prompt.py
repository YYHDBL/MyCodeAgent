"""MultiEditTool 的提示词定义

该提示词用于向 LLM 描述 MultiEdit 工具的功能和使用方式。
"""

multi_edit_prompt = """MultiEdit: Apply multiple independent edits to ONE file atomically.

## Purpose
Make multiple surgical edits to a single file in one atomic operation. All edits are matched against the ORIGINAL file content, applied together, and written once. Use this instead of calling Edit multiple times on the same file.

## Key Features
1. **Atomic Operation**: All edits succeed together or none are applied.
2. **Original Content Matching**: All old_string anchors are matched against the original file, not intermediate states.
3. **Conflict Detection**: Overlapping edit regions are detected and rejected.
4. **Format Agnostic**: Automatically handles CRLF/LF differences.
5. **Conflict Prevention**: Framework auto-injects mtime/size from prior Read.
6. **Diff Preview**: Returns a unified diff showing all changes.
7. **Dry Run Mode**: Use `dry_run=true` to preview changes without writing.

## Parameters
- `path` (string, required): Relative path to the file. POSIX style (use `/`), no absolute paths.
- `edits` (array, required): List of edits to apply. Each edit has:
  - `old_string` (string, required): Exact text to replace. **MUST be unique** in the original file.
  - `new_string` (string, required): Replacement text. Can be empty to delete old_string.
- `dry_run` (boolean, optional): If true, only compute diff without writing. Default: false.

Note: `expected_mtime_ms` and `expected_size_bytes` are **automatically injected by the framework** after you Read the file.

## Important Rules
1. **ALWAYS Read the file immediately before editing**. The framework needs fresh mtime/size.
2. **ALL old_string values must match the ORIGINAL file content** - not intermediate states after previous edits.
3. **Each old_string must be unique** in the file. If it matches multiple times, include surrounding context.
4. **Edits MUST NOT overlap**. If two edits target the same region, split them or use separate Edit calls.
5. **Use Write for new files**. MultiEdit only works on existing files.
6. **Handle CONFLICT errors** by re-reading the file and re-applying your changes.

## Response Structure
- status: "success" | "partial" | "error"
  - "success": all edits applied successfully
  - "partial": dry_run or diff truncated
  - "error": invalid params, path denied, or I/O error
- data.applied: Whether the edits were actually applied (false if dry_run)
- data.diff_preview: Unified diff showing all changes
- data.diff_truncated: Whether diff was truncated
- data.replacements: Number of replacements made (equals number of edits on success)
- data.failed_index: Index of failed edit (null on success)
- text: Human-readable summary
- stats: {time_ms, lines_added, lines_removed, bytes_written}
- context: {cwd, params_input, path_resolved}
- error: {code, message} (only when status="error")

## Error Codes
- `NOT_FOUND`: File does not exist (MultiEdit cannot create files)
- `INVALID_PARAM`: Missing parameters, old_string not found, old_string matches multiple times, or edits overlap
- `ACCESS_DENIED`: Path outside project root (sandbox violation)
- `PERMISSION_DENIED`: OS-level permission error
- `EXECUTION_ERROR`: Other I/O or execution errors
- `IS_DIRECTORY`: Target path is a directory
- `BINARY_FILE`: File appears to be binary
- `CONFLICT`: File was modified since you read it (re-read and retry)

## Examples

### Multiple independent edits
Step 1: Read the file
```
Read[{"path": "src/config.py"}]
```

Step 2: Apply multiple edits atomically
```json
{
  "path": "src/config.py",
  "edits": [
    {
      "old_string": "DEBUG = True",
      "new_string": "DEBUG = False"
    },
    {
      "old_string": "LOG_LEVEL = \\"INFO\\"",
      "new_string": "LOG_LEVEL = \\"WARNING\\""
    },
    {
      "old_string": "MAX_RETRIES = 3",
      "new_string": "MAX_RETRIES = 5"
    }
  ]
}
```

### Refactoring multiple functions
```json
{
  "path": "src/utils.py",
  "edits": [
    {
      "old_string": "def get_user(id):",
      "new_string": "def get_user(user_id: int) -> Optional[User]:"
    },
    {
      "old_string": "def get_order(id):",
      "new_string": "def get_order(order_id: int) -> Optional[Order]:"
    }
  ]
}
```

### Preview changes before applying
```json
{
  "path": "src/api.py",
  "edits": [
    {
      "old_string": "return 200",
      "new_string": "return HTTPStatus.OK"
    },
    {
      "old_string": "return 404",
      "new_string": "return HTTPStatus.NOT_FOUND"
    }
  ],
  "dry_run": true
}
```

## Common Mistakes to Avoid
1. **Don't assume intermediate states** - All old_string values match the ORIGINAL file, not after previous edits in the list.
2. **Don't create overlapping edits** - If edit A's region overlaps with edit B's region, the tool will fail.
3. **Don't add line numbers** - Copy text exactly as shown in Read output.
4. **Don't escape newlines** - Use actual newlines in old_string/new_string.
5. **Don't guess the content** - Always Read first to see the exact current state.
6. **Don't use for sequentially dependent edits** - If edit B depends on edit A's result, use separate Edit calls.
"""
