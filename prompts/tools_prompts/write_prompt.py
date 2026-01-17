"""WriteTool 的提示词定义

该提示词用于向 LLM 描述 Write 工具的功能和使用方式。
"""

write_prompt = """Write: Create or overwrite a file with FULL content.

## Purpose
Create new files or completely replace existing file content. This tool performs **full overwrite** - you must provide the complete file content, not patches or snippets.

## Key Features
1. **Auto-Mkdir**: Parent directories are created automatically if they don't exist.
2. **Full Content Only**: Always provide the COMPLETE file content.
3. **Diff Preview**: Returns a unified diff showing your changes.
4. **Dry Run Mode**: Use `dry_run=true` to preview changes without writing.
5. **Atomic Write**: Uses temp file + rename for crash safety.
6. **Automatic Conflict Prevention**: Framework auto-injects mtime/size from prior Read (if available).

## Parameters
- `path` (string, required): Relative path to the file. POSIX style (use `/`), no absolute paths.
- `content` (string, required): The FULL content to write to the file.
- `dry_run` (boolean, optional): If true, only compute diff without writing. Default: false.

Note: `expected_mtime_ms` and `expected_size_bytes` are **automatically injected by the framework** if you have previously Read the file. You do NOT need to pass them manually.

## Conflict Prevention (Automatic)
The framework automatically handles conflict prevention:
1. When you **Read** a file, the framework caches its `file_mtime_ms` and `file_size_bytes`
2. When you **Write** to an existing file, the framework auto-injects these values
3. If the file was modified by someone else, Write returns a `CONFLICT` error
4. On `CONFLICT`: Re-read the file, re-apply your changes, and try again

**Important**: You must Read a file before Writing to it (for existing files). The framework will report INVALID_PARAM if you try to Write an existing file without a prior Read.

## Best Practices
1. **Read Before Write**: Always use Read tool first before modifying existing files.
2. **Check Diff**: Review the returned `diff_preview` to verify your changes are correct.
3. **Handle Truncation**: If `diff_truncated=true`, use Read to verify the full content.
4. **Use Dry Run**: For risky changes, use `dry_run=true` first to preview.
5. **Handle CONFLICT**: If you get a CONFLICT error, re-read and re-apply changes.

## Response Structure
- status: "success" | "partial" | "error"
  - "success": write succeeded with full diff preview
  - "partial": dry_run or diff truncated
  - "error": invalid params, path denied, or I/O error
- data.applied: Whether the file was actually written (false if dry_run)
- data.operation: "create" or "update"
- data.diff_preview: Unified diff showing changes
- data.diff_truncated: Whether diff was truncated (large changes)
- text: Human-readable summary
- stats: {time_ms, bytes_written, original_size, new_size, lines_added, lines_removed}
- context: {cwd, params_input, path_resolved}
- error: {code, message} (only when status="error")

## Error Codes
- `INVALID_PARAM`: Missing path/content, absolute path used, or writing existing file without prior Read
- `ACCESS_DENIED`: Path outside project root (sandbox violation)
- `PERMISSION_DENIED`: OS-level permission error (EACCES)
- `EXECUTION_ERROR`: Other I/O or execution errors (e.g., disk full)
- `IS_DIRECTORY`: Target path is a directory
- `CONFLICT`: File was modified since you read it (re-read and retry)

## Examples

### Create a new file (no prior Read needed)
```json
{
  "path": "src/utils/helper.py",
  "content": "def greet(name):\\n    return f'Hello, {name}!'\\n"
}
```

### Update existing file (must Read first)
Step 1: Read the file
```
{"path": "README.md"}
```

Step 2: Write with your changes (mtime/size auto-injected)
```json
{
  "path": "README.md",
  "content": "# Updated Title\\n\\nNew content here.\\n"
}
```

### Update with dry run preview
```json
{
  "path": "config.json",
  "content": "{\\"key\\": \\"new_value\\"}\\n",
  "dry_run": true
}
```

## Important Notes
- This tool does NOT support partial edits or patches. Always provide full content.
- For editing specific sections of a file, first Read the file, modify the content in your response, then Write the complete modified content.
- Empty content (`""`) is allowed - this creates an empty file.
- For NEW files, no prior Read is needed.
- For EXISTING files, you must Read first (framework auto-injects lock parameters).
"""
