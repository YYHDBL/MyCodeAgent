"""Read 工具提示词

提供给 LLM 的工具描述，遵循《通用工具响应协议》。
"""

read_prompt = """
Tool name: Read
Tool description:
Reads a file from the local filesystem with line numbers. Optimized for code editing.
Follows the Universal Tool Response Protocol (顶层字段仅: status/data/text/error/stats/context).

Usage
- Use Read to view file content with line numbers for editing context.
- Each line is prefixed with line number in format: "   1 | content"
- Supports pagination via start_line and limit parameters.
- Do NOT use bash cat/less/head/tail; use this tool for consistent output.

Parameters (JSON object)
- path (string, required)
  Path to the file (relative to project root).
- start_line (integer, optional, default 1)
  The line number to start reading from (1-based).
- limit (integer, optional, default 500, max 2000)
  The maximum number of lines to read.

Response Structure
- status: "success" | "partial" | "error"
  - "success": file read completely (reached EOF)
  - "partial": truncated (more lines available) or encoding fallback used
  - "error": file not found, access denied, binary file, or invalid parameters
- data.content: string
  File content with line numbers (format: "%4d | %s\\n" per line).
- data.truncated: boolean
  true if results were truncated (use start_line to paginate).
- data.fallback_encoding: string (optional)
  Present when encoding fallback was used (e.g., "replace").
- text: Human-readable summary with pagination hints.
- stats: {time_ms, lines_read, chars_read, total_lines, file_size_bytes, encoding}
- context: {cwd, params_input, path_resolved}
- error: {code, message} (only when status="error")

Examples
1) Read a file from the beginning

Read[{"path": "src/main.py"}]

2) Read with pagination (lines 101-200)

Read[{"path": "src/main.py", "start_line": 101, "limit": 100}]

3) Read a specific range

Read[{"path": "config.yaml", "start_line": 50, "limit": 20}]

Error Handling
- NOT_FOUND: File does not exist.
- ACCESS_DENIED: Path is outside project root.
- IS_DIRECTORY: Path is a directory (use LS instead).
- BINARY_FILE: File appears to be binary.
- INVALID_PARAM: start_line exceeds file length, or limit out of range.
  (Note: empty file only allows start_line=1.)
"""
