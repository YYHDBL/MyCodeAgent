"""Prompt contract for the sole file-mutation tool."""

edit_prompt = """Edit: atomically create one text file or apply ordered replacements to one existing text file.

Use exactly one input mode:

- To create a new file, send `path` and `create_content`. Parent directories are created as needed. The same mode fully replaces an existing file after Read supplies its snapshot lock.
- To change an existing file, Read it first, then send `path` and a non-empty `edits` array. Each item has a unique `old_string` and its `new_string`. Every anchor is matched against the original content; overlapping anchors are rejected. The framework injects the Read snapshot lock.

Safety guarantees

- Paths must stay beneath the selected project root.
- Existing files are checked for binary content and snapshot conflicts.
- All validated replacements are applied in memory and committed by one atomic write, preserving the file's predominant newline style.
- `dry_run=true` returns a diff and never changes the file.

On `CONFLICT`, Read the file again and retry with fresh anchors.
"""
