"""The sole atomic text-file mutation tool."""

from __future__ import annotations

import difflib
import time
from pathlib import Path
from typing import Any, Optional

from prompts.tools_prompts.edit_prompt import edit_prompt
from tools.base import ErrorCode, Tool, ToolParameter, ToolResult
from tools.workspace import FileWorkspace, WorkspaceError


class EditTool(Tool):
    """Create one file or atomically apply independent, uniquely anchored edits."""

    MAX_DIFF_LINES = 100
    MAX_DIFF_BYTES = 10_240

    def __init__(
        self,
        name: str = "Edit",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
    ) -> None:
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        super().__init__(
            name=name,
            description=edit_prompt,
            project_root=project_root,
            working_dir=working_dir or project_root,
        )
        self._workspace = FileWorkspace(self._project_root)

    def run(self, parameters: dict[str, Any]) -> ToolResult:
        started = time.monotonic()
        params_input = dict(parameters)
        path = parameters.get("path")
        edits = parameters.get("edits")
        create_content = parameters.get("create_content")
        dry_run = parameters.get("dry_run", False)

        validation = self._validate(path, edits, create_content, dry_run, params_input)
        if validation is not None:
            return validation
        try:
            target = self._workspace.resolve(path)
        except WorkspaceError as error:
            return self._workspace_error_response(error, path, params_input)
        rel_path = self._workspace.relative(target)

        if create_content is not None:
            return self._create(
                path, rel_path, create_content, dry_run, params_input, started
            )
        return self._edit(path, rel_path, edits, dry_run, params_input, started)

    def _validate(
        self,
        path: Any,
        edits: Any,
        create_content: Any,
        dry_run: Any,
        params_input: dict[str, Any],
    ) -> Optional[str]:
        if not isinstance(path, str) or not path:
            return self._error(ErrorCode.INVALID_PARAM, "Parameter 'path' must be a non-empty string.", params_input)
        has_edits = edits is not None
        has_create = create_content is not None
        if has_edits == has_create:
            return self._error(
                ErrorCode.INVALID_PARAM,
                "Provide exactly one of non-empty 'edits' or 'create_content'.",
                params_input,
            )
        if has_create and not isinstance(create_content, str):
            return self._error(ErrorCode.INVALID_PARAM, "Parameter 'create_content' must be a string.", params_input)
        if has_edits:
            if not isinstance(edits, list) or not edits:
                return self._error(ErrorCode.INVALID_PARAM, "Parameter 'edits' must be a non-empty array.", params_input)
            for index, edit in enumerate(edits):
                if not isinstance(edit, dict):
                    return self._error(ErrorCode.INVALID_PARAM, f"Edit at index {index} must be an object.", params_input)
                old = edit.get("old_string")
                new = edit.get("new_string")
                if not isinstance(old, str) or not old:
                    return self._error(
                        ErrorCode.INVALID_PARAM,
                        f"Edit at index {index}: 'old_string' must be a non-empty string.",
                        params_input,
                    )
                if not isinstance(new, str):
                    return self._error(
                        ErrorCode.INVALID_PARAM,
                        f"Edit at index {index}: 'new_string' must be a string.",
                        params_input,
                    )
        if not isinstance(dry_run, bool):
            return self._error(ErrorCode.INVALID_PARAM, "Parameter 'dry_run' must be a boolean.", params_input)
        return None

    def _create(
        self,
        path: str,
        rel_path: str,
        content: str,
        dry_run: bool,
        params_input: dict[str, Any],
        started: float,
    ) -> ToolResult:
        try:
            initial = self._workspace.inspect(path)
        except WorkspaceError as error:
            if error.kind != "not_found":
                return self._workspace_error_response(error, path, params_input, path_resolved=rel_path)
            return self._finish(
                path=path,
                rel_path=rel_path,
                old_content="",
                new_content=content,
                replacements=0,
                operation="create",
                dry_run=dry_run,
                params_input=params_input,
                started=started,
                snapshot=None,
            )
        lock_error = self._validate_lock(params_input, rel_path)
        if lock_error is not None:
            return lock_error
        if (
            initial.mtime_ms != params_input["expected_mtime_ms"]
            or initial.size != params_input["expected_size_bytes"]
        ):
            return self._error(
                ErrorCode.CONFLICT,
                "File has been modified since you read it. Please Read the file again.",
                params_input,
                path_resolved=rel_path,
            )
        try:
            old_content, _encoding, _fallback, snapshot = self._workspace.read_text(path)
        except WorkspaceError as error:
            return self._workspace_error_response(error, path, params_input, path_resolved=rel_path)
        return self._finish(
            path=path,
            rel_path=rel_path,
            old_content=old_content,
            new_content=content,
            replacements=1,
            operation="replace",
            dry_run=dry_run,
            params_input=params_input,
            started=started,
            snapshot=snapshot,
        )

    def _edit(
        self,
        path: str,
        rel_path: str,
        edits: list[dict[str, str]],
        dry_run: bool,
        params_input: dict[str, Any],
        started: float,
    ) -> ToolResult:
        lock_error = self._validate_lock(params_input, rel_path)
        if lock_error is not None:
            return lock_error
        try:
            initial = self._workspace.inspect(path)
        except WorkspaceError as error:
            return self._workspace_error_response(error, path, params_input, path_resolved=rel_path)
        expected_mtime = params_input.get("expected_mtime_ms")
        expected_size = params_input.get("expected_size_bytes")
        if initial.mtime_ms != expected_mtime or initial.size != expected_size:
            return self._error(
                ErrorCode.CONFLICT,
                "File has been modified since you read it. Please Read the file again.",
                params_input,
                path_resolved=rel_path,
            )
        try:
            old_content, _encoding, _fallback, snapshot = self._workspace.read_text(path)
        except WorkspaceError as error:
            return self._workspace_error_response(error, path, params_input, path_resolved=rel_path)
        new_content, error = self._apply_edits(old_content, edits, params_input, rel_path)
        if error is not None:
            return error
        return self._finish(
            path=path,
            rel_path=rel_path,
            old_content=old_content,
            new_content=new_content,
            replacements=len(edits),
            operation="edit",
            dry_run=dry_run,
            params_input=params_input,
            started=started,
            snapshot=snapshot,
        )

    def _validate_lock(self, params_input: dict[str, Any], rel_path: str) -> Optional[str]:
        mtime = params_input.get("expected_mtime_ms")
        size = params_input.get("expected_size_bytes")
        if mtime is None and size is None:
            return self._error(
                ErrorCode.INVALID_PARAM,
                "You must Read the file before editing it.",
                params_input,
                path_resolved=rel_path,
            )
        if mtime is None or size is None:
            return self._error(
                ErrorCode.INVALID_PARAM,
                "Both expected_mtime_ms and expected_size_bytes must be provided together.",
                params_input,
                path_resolved=rel_path,
            )
        if not isinstance(mtime, int) or not isinstance(size, int):
            return self._error(
                ErrorCode.INVALID_PARAM,
                "expected_mtime_ms and expected_size_bytes must be integers.",
                params_input,
                path_resolved=rel_path,
            )
        return None

    def _apply_edits(
        self,
        old_content: str,
        edits: list[dict[str, str]],
        params_input: dict[str, Any],
        rel_path: str,
    ) -> tuple[str, Optional[str]]:
        use_crlf = old_content.count("\r\n") > old_content.count("\n") - old_content.count("\r\n")
        normalized = old_content.replace("\r\n", "\n")
        regions: list[tuple[int, int, int, str]] = []
        for index, edit in enumerate(edits):
            old = edit["old_string"].replace("\r\n", "\n")
            new = edit["new_string"].replace("\r\n", "\n")
            count = normalized.count(old)
            if count != 1:
                noun = "not found" if count == 0 else f"matches {count} times"
                return old_content, self._error(
                    ErrorCode.INVALID_PARAM,
                    f"Edit at index {index}: old_string {noun}; it must be unique.",
                    params_input,
                    path_resolved=rel_path,
                    data={"failed_index": index},
                )
            start = normalized.find(old)
            regions.append((start, start + len(old), index, new))
        for previous, following in zip(sorted(regions), sorted(regions)[1:]):
            if following[0] < previous[1]:
                return old_content, self._error(
                    ErrorCode.INVALID_PARAM,
                    f"Edits at indexes {previous[2]} and {following[2]} overlap.",
                    params_input,
                    path_resolved=rel_path,
                )
        for start, end, _index, new in reversed(sorted(regions)):
            normalized = normalized[:start] + new + normalized[end:]
        return (normalized.replace("\n", "\r\n") if use_crlf else normalized), None

    def _finish(
        self,
        *,
        path: str,
        rel_path: str,
        old_content: str,
        new_content: str,
        replacements: int,
        operation: str,
        dry_run: bool,
        params_input: dict[str, Any],
        started: float,
        snapshot: Any,
    ) -> ToolResult:
        diff = self._compute_diff(old_content, new_content, rel_path)
        applied = False
        try:
            if not dry_run:
                if snapshot is None:
                    bytes_written = self._workspace.atomic_create(path, new_content)
                else:
                    bytes_written = self._workspace.atomic_write(path, new_content, expected=snapshot)
                applied = True
            else:
                bytes_written = len(new_content.encode("utf-8"))
        except WorkspaceError as error:
            return self._workspace_error_response(error, path, params_input, path_resolved=rel_path)
        except PermissionError:
            return self._error(ErrorCode.PERMISSION_DENIED, "Permission denied writing to file.", params_input, path_resolved=rel_path)
        except OSError as error:
            return self._error(ErrorCode.EXECUTION_ERROR, f"Disk full or IO error: {error}", params_input, path_resolved=rel_path)
        data = {
            "applied": applied,
            "operation": operation,
            "replacements": replacements,
            "diff_preview": diff["preview"],
            "diff_truncated": diff["truncated"],
        }
        if dry_run:
            data["dry_run"] = True
        stats = {
            "bytes_written": bytes_written,
            "original_size": len(old_content.encode("utf-8")),
            "new_size": len(new_content.encode("utf-8")),
            "lines_added": diff["lines_added"],
            "lines_removed": diff["lines_removed"],
        }
        text = (
            f"[Dry Run] Would {operation} '{rel_path}' (+{diff['lines_added']}/-{diff['lines_removed']} lines)."
            if dry_run
            else f"{operation.capitalize()}d '{rel_path}' (+{diff['lines_added']}/-{diff['lines_removed']} lines, {bytes_written} bytes)."
        )
        if diff["truncated"]:
            text += "\n(Diff preview truncated. Use Read to verify full content.)"
        response = self.partial_result if dry_run or diff["truncated"] else self.success_result
        return response(
            data=data,
            text=text,
            params_input=params_input,
            time_ms=int((time.monotonic() - started) * 1000),
            extra_stats=stats,
            path_resolved=rel_path,
        )

    def _workspace_error_response(
        self,
        error: WorkspaceError,
        path: str,
        params_input: dict[str, Any],
        *,
        path_resolved: Optional[str] = None,
    ) -> ToolResult:
        code = {
            "not_found": ErrorCode.NOT_FOUND,
            "directory": ErrorCode.IS_DIRECTORY,
            "binary": ErrorCode.BINARY_FILE,
            "not_regular": ErrorCode.INVALID_PARAM,
            "absolute": ErrorCode.INVALID_PARAM,
            "invalid_path": ErrorCode.INVALID_PARAM,
            "outside": ErrorCode.ACCESS_DENIED,
            "conflict": ErrorCode.CONFLICT,
        }.get(error.kind, ErrorCode.EXECUTION_ERROR)
        messages = {
            "not_found": f"File '{path}' does not exist. Use create_content to create it.",
            "directory": f"Path '{path}' is a directory, not a file.",
            "binary": f"File '{path}' appears to be binary. Cannot edit binary files.",
            "not_regular": f"Path '{path}' is not a regular file.",
            "absolute": "Absolute path not allowed. Use relative path.",
            "outside": "Path must be within project root.",
            "conflict": "File has been modified since it was read. Please Read the file again.",
        }
        return self._error(code, messages.get(error.kind, str(error)), params_input, path_resolved=path_resolved)

    def _error(
        self,
        code: ErrorCode,
        message: str,
        params_input: dict[str, Any],
        *,
        path_resolved: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> ToolResult:
        return self.error_result(
            error_code=code,
            message=message,
            params_input=params_input,
            data=data,
            path_resolved=path_resolved,
        )

    def _compute_diff(self, old_content: str, new_content: str, path: str) -> dict[str, Any]:
        preview: list[str] = []
        preview_bytes = 0
        truncated = False
        added = removed = 0
        for line in difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="\n",
        ):
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
            display = line[0] + line[1:].lstrip() if line[:1] in {"+", "-"} and not line.startswith(("+++", "---")) else line
            size = len(display.encode("utf-8"))
            if len(preview) >= self.MAX_DIFF_LINES or preview_bytes + size > self.MAX_DIFF_BYTES:
                truncated = True
                break
            preview.append(display)
            preview_bytes += size
        if truncated:
            preview.append("... (truncated)")
        return {"preview": "\n".join(preview), "truncated": truncated, "lines_added": added, "lines_removed": removed}

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="path", type="string", description="Path relative to project root.", required=True),
            ToolParameter(name="edits", type="array", description="Ordered unique replacements; use exactly one of edits or create_content.", required=False),
            ToolParameter(name="create_content", type="string", description="Content for a new file; use exactly one of edits or create_content.", required=False),
            ToolParameter(name="expected_mtime_ms", type="integer", description="Read snapshot mtime, automatically injected after Read.", required=False),
            ToolParameter(name="expected_size_bytes", type="integer", description="Read snapshot size, automatically injected after Read.", required=False),
            ToolParameter(name="dry_run", type="boolean", description="Preview without writing. Defaults to false.", required=False, default=False),
        ]
