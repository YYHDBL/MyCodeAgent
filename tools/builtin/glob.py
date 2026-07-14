"""Project-confined directory listing and recursive file discovery."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from prompts.tools_prompts.glob_prompt import glob_prompt
from tools.base import ErrorCode, Tool, ToolParameter, ToolResult
from tools.workspace import FileWorkspace, WorkspaceError

from ._search_paths import (
    DEFAULT_RESULT_LIMIT,
    MAX_RESULT_LIMIT,
    iter_files,
    path_matches,
    resolve_search_directory,
    visible_name,
)


class GlobTool(Tool):
    """List one directory or find files recursively under a selected project root."""

    def __init__(self, name: str = "Glob", project_root: Path | None = None) -> None:
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        super().__init__(name=name, description=glob_prompt, project_root=project_root)
        self.workspace = FileWorkspace(self._project_root)

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("path", "string", "Directory relative to project root.", False, "."),
            ToolParameter(
                "pattern",
                "string",
                "Optional recursive glob relative to path, for example '**/*.py'.",
                False,
            ),
            ToolParameter(
                "limit", "integer", "Maximum results to return (1-200).", False, DEFAULT_RESULT_LIMIT
            ),
            ToolParameter(
                "include_hidden", "boolean", "Include dotfiles and dot-directories.", False, False
            ),
            ToolParameter(
                "include_ignored", "boolean", "Include common build and dependency directories.", False, False
            ),
        ]

    def run(self, parameters: dict[str, Any]) -> ToolResult:
        started = time.monotonic()
        params_input = dict(parameters)
        path = parameters.get("path", ".")
        pattern = parameters.get("pattern")
        limit = parameters.get("limit", DEFAULT_RESULT_LIMIT)
        include_hidden = parameters.get("include_hidden", False)
        include_ignored = parameters.get("include_ignored", False)

        if not isinstance(path, str) or (pattern is not None and not isinstance(pattern, str)):
            return self._invalid("path and pattern must be strings.", params_input)
        if pattern == "":
            return self._invalid("pattern must not be empty when supplied.", params_input)
        if type(limit) is not int or not 1 <= limit <= MAX_RESULT_LIMIT:
            return self._invalid("limit must be an integer between 1 and 200.", params_input)
        if not isinstance(include_hidden, bool) or not isinstance(include_ignored, bool):
            return self._invalid("include_hidden and include_ignored must be booleans.", params_input)

        try:
            root, rel_root = resolve_search_directory(self.workspace, path)
        except WorkspaceError as error:
            return self._workspace_error(error, params_input)

        if pattern is None:
            candidates = [
                child
                for child in sorted(root.iterdir(), key=lambda item: item.name)
                if visible_name(
                    child.name,
                    include_hidden=include_hidden,
                    include_ignored=include_ignored,
                )
                and not child.is_symlink()
            ]
        else:
            candidates = [
                candidate
                for candidate in iter_files(
                    root,
                    include_hidden=include_hidden,
                    include_ignored=include_ignored,
                )
                if path_matches(candidate.relative_to(root).as_posix(), pattern)
            ]

        paths = [self.workspace.relative(candidate) for candidate in candidates]
        truncated = len(paths) > limit
        paths = paths[:limit]
        elapsed = int((time.monotonic() - started) * 1000)
        text = f"Found {len(paths)} path(s) in '{rel_root}'."
        if truncated:
            text += " Results were truncated; narrow the path or pattern."
            return self.partial_result(
                data={"paths": paths, "truncated": True},
                text=text,
                params_input=params_input,
                time_ms=elapsed,
                extra_stats={"matched": len(paths), "visited": len(candidates)},
                path_resolved=rel_root,
            )
        return self.success_result(
            data={"paths": paths, "truncated": False},
            text=text,
            params_input=params_input,
            time_ms=elapsed,
            extra_stats={"matched": len(paths), "visited": len(candidates)},
            path_resolved=rel_root,
        )

    def _invalid(self, message: str, params_input: dict[str, Any]) -> ToolResult:
        return self.error_result(
            error_code=ErrorCode.INVALID_PARAM, message=message, params_input=params_input
        )

    def _workspace_error(self, error: WorkspaceError, params_input: dict[str, Any]) -> ToolResult:
        codes = {
            "absolute": ErrorCode.ACCESS_DENIED,
            "outside": ErrorCode.ACCESS_DENIED,
            "not_found": ErrorCode.NOT_FOUND,
            "not_directory": ErrorCode.INVALID_PARAM,
            "invalid_path": ErrorCode.INVALID_PARAM,
        }
        return self.error_result(
            error_code=codes.get(error.kind, ErrorCode.INTERNAL_ERROR),
            message=str(error),
            params_input=params_input,
        )
