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

## Parameters
- `path` (string, required): Relative path to the file. POSIX style (use `/`), no absolute paths.
- `content` (string, required): The FULL content to write to the file.
- `dry_run` (boolean, optional): If true, only compute diff without writing. Default: false.

## Best Practices
1. **Read Before Write**: Always use Read tool first to understand the current content before modifying existing files.
2. **Check Diff**: Review the returned `diff_preview` to verify your changes are correct.
3. **Handle Truncation**: If `diff_truncated=true`, use Read to verify the full content.
4. **Use Dry Run**: For risky changes, use `dry_run=true` first to preview.

## Output
Returns a standard envelope with:
- `data.applied`: Whether the file was actually written (false if dry_run)
- `data.operation`: "create" or "update"
- `data.diff_preview`: Unified diff showing changes
- `data.diff_truncated`: Whether diff was truncated (large changes)
- `stats.lines_added/lines_removed`: Line change statistics (if diff truncated, counts are for preview only)
- `text`: Human-readable summary

## Error Codes
- `INVALID_PARAM`: Missing path/content, or absolute path used
- `ACCESS_DENIED`: Path outside project root (sandbox violation)
- `PERMISSION_DENIED`: OS-level permission error (EACCES)
- `EXECUTION_ERROR`: Other I/O or execution errors (e.g., disk full)
- `IS_DIRECTORY`: Target path is a directory

## Examples

### Create a new file
```json
{
  "path": "src/utils/helper.py",
  "content": "def greet(name):\\n    return f'Hello, {name}!'\\n"
}
```

### Update existing file with dry run
```json
{
  "path": "README.md",
  "content": "# Updated Title\\n\\nNew content here.\\n",
  "dry_run": true
}
```

## Important Notes
- This tool does NOT support partial edits or patches. Always provide full content.
- For editing specific sections of a file, first Read the file, modify the content in your response, then Write the complete modified content.
- Empty content (`""`) is allowed - this creates an empty file.
"""
