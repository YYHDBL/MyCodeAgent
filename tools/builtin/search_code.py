"""Project-confined regular-expression content search."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, TypedDict

from prompts.tools_prompts.grep_prompt import grep_prompt
from tools.base import ErrorCode, Tool, ToolParameter, ToolResult
from tools.workspace import FileWorkspace, WorkspaceError

from ._search_paths import (
    DEFAULT_RESULT_LIMIT,
    MAX_RESULT_LIMIT,
    iter_files,
    path_matches,
    resolve_search_directory,
)


class MatchItem(TypedDict):
    file: str
    line: int
    text: str


class GrepTool(Tool):
    """Search text files with ripgrep when available and one Python fallback."""

    timeout_seconds = 2.0
    max_line_chars = 2_000
    _line_truncation_marker = "… [truncated]"

    def __init__(self, name: str = "Grep", project_root: Path | None = None) -> None:
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        super().__init__(name=name, description=grep_prompt, project_root=project_root)
        self.workspace = FileWorkspace(self._project_root)

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("pattern", "string", "Regular expression to find.", True),
            ToolParameter("path", "string", "Directory relative to project root.", False, "."),
            ToolParameter(
                "glob", "string", "Optional file glob relative to path, for example '**/*.py'.", False
            ),
            ToolParameter(
                "case_sensitive", "boolean", "Match case exactly when true.", False, False
            ),
            ToolParameter(
                "limit", "integer", "Maximum matching lines to return (1-200).", False, DEFAULT_RESULT_LIMIT
            ),
        ]

    def run(self, parameters: dict[str, Any]) -> ToolResult:
        started = time.monotonic()
        params_input = dict(parameters)
        pattern = parameters.get("pattern")
        path = parameters.get("path", ".")
        glob = parameters.get("glob")
        case_sensitive = parameters.get("case_sensitive", False)
        limit = parameters.get("limit", DEFAULT_RESULT_LIMIT)
        if not isinstance(pattern, str) or not pattern:
            return self._invalid("pattern must be a non-empty string.", params_input)
        if not isinstance(path, str) or (glob is not None and not isinstance(glob, str)):
            return self._invalid("path and glob must be strings.", params_input)
        if glob == "":
            return self._invalid("glob must not be empty when supplied.", params_input)
        if not isinstance(case_sensitive, bool):
            return self._invalid("case_sensitive must be a boolean.", params_input)
        if type(limit) is not int or not 1 <= limit <= MAX_RESULT_LIMIT:
            return self._invalid("limit must be an integer between 1 and 200.", params_input)
        try:
            compiled = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
        except re.error as error:
            return self._invalid(f"Invalid regex pattern: {error}", params_input)
        try:
            root, rel_root = resolve_search_directory(self.workspace, path)
        except WorkspaceError as error:
            return self._workspace_error(error, params_input)

        candidates = self._text_candidates(root, glob)
        fallback_reason: str | None = None
        if shutil.which("rg") is not None:
            try:
                matches = self._rg_matches(
                    root=root,
                    candidates=candidates,
                    pattern=pattern,
                    case_sensitive=case_sensitive,
                    limit=limit,
                )
            except _UnsupportedRipgrepPattern:
                fallback_reason = "rg_unsupported_pattern"
                matches = self._python_matches(candidates, compiled)
            except (OSError, subprocess.TimeoutExpired):
                fallback_reason = "rg_failed"
                matches = self._python_matches(candidates, compiled)
        else:
            fallback_reason = "rg_not_found"
            matches = self._python_matches(candidates, compiled)

        matches.sort(key=lambda item: (item["file"], item["line"], item["text"]))
        truncation_reasons: list[str] = []
        if len(matches) > limit:
            truncation_reasons.append("match_limit")
        matches = matches[:limit]
        matches, line_truncated = self._bound_line_text(matches)
        if line_truncated:
            truncation_reasons.append("line_length")
        truncated = bool(truncation_reasons)
        elapsed = int((time.monotonic() - started) * 1000)
        data: dict[str, Any] = {"matches": matches, "truncated": truncated}
        if truncation_reasons:
            data["truncation_reasons"] = truncation_reasons
        if fallback_reason is not None:
            data["fallback_used"] = True
            data["fallback_reason"] = fallback_reason
        text = f"Found {len(matches)} matching line(s) in '{rel_root}'."
        if fallback_reason is not None:
            text += " Used the Python fallback because ripgrep was unavailable or failed."
        if truncated:
            text += " Results were truncated; narrow the path, glob, pattern, or matching lines."
            return self.partial_result(
                data=data,
                text=text,
                params_input=params_input,
                time_ms=elapsed,
                extra_stats={"matched_lines": len(matches), "searched_files": len(candidates)},
                path_resolved=rel_root,
            )
        return self.success_result(
            data=data,
            text=text,
            params_input=params_input,
            time_ms=elapsed,
            extra_stats={"matched_lines": len(matches), "searched_files": len(candidates)},
            path_resolved=rel_root,
        )

    def _rg_matches(
        self,
        *,
        root: Path,
        candidates: list[Path],
        pattern: str,
        case_sensitive: bool,
        limit: int,
    ) -> list[MatchItem]:
        if not candidates:
            return []
        command = ["rg", "--json", "--line-number", "--no-heading", "--color=never"]
        if not case_sensitive:
            command.append("--ignore-case")
        command.extend(["--max-count", str(limit + 1), "-e", pattern, "--"])
        command.extend(candidate.relative_to(root).as_posix() for candidate in candidates)
        completed = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout_seconds,
        )
        if completed.returncode == 2:
            raise _UnsupportedRipgrepPattern(completed.stderr.strip() or "ripgrep rejected the pattern")
        if completed.returncode not in (0, 1):
            raise OSError(completed.stderr.strip() or "ripgrep failed")
        matches: list[MatchItem] = []
        for raw_line in completed.stdout.splitlines():
            event = json.loads(raw_line)
            if event.get("type") != "match":
                continue
            data = event["data"]
            matches.append(
                {
                    "file": self.workspace.relative(root / data["path"]["text"]),
                    "line": data["line_number"],
                    "text": data["lines"]["text"].rstrip("\r\n"),
                }
            )
        return matches

    def _bound_line_text(self, matches: list[MatchItem]) -> tuple[list[MatchItem], bool]:
        """Cap each returned line so one match cannot exhaust the tool-result budget."""
        truncated = False
        bounded: list[MatchItem] = []
        for match in matches:
            text = match["text"]
            if len(text) > self.max_line_chars:
                text = text[: self.max_line_chars - len(self._line_truncation_marker)]
                text += self._line_truncation_marker
                truncated = True
            bounded.append({**match, "text": text})
        return bounded, truncated

    def _python_matches(self, candidates: list[Path], pattern: re.Pattern[str]) -> list[MatchItem]:
        matches: list[MatchItem] = []
        for candidate in candidates:
            relative = self.workspace.relative(candidate)
            try:
                content, _, _, _ = self.workspace.read_text(relative)
            except WorkspaceError as error:
                if error.kind in {"binary", "not_regular", "not_found", "io", "conflict"}:
                    continue
                raise
            for line_number, line in enumerate(content.splitlines(), start=1):
                if pattern.search(line):
                    matches.append({"file": relative, "line": line_number, "text": line})
        return matches

    def _text_candidates(self, root: Path, glob: str | None) -> list[Path]:
        """Apply the workspace's regular-text boundary before either engine runs."""
        candidates: list[Path] = []
        for candidate in iter_files(root):
            relative_from_root = candidate.relative_to(root).as_posix()
            if glob is not None and not path_matches(relative_from_root, glob):
                continue
            try:
                self.workspace.inspect(self.workspace.relative(candidate))
            except WorkspaceError as error:
                if error.kind in {"binary", "not_regular", "not_found", "io", "conflict"}:
                    continue
                raise
            candidates.append(candidate)
        return candidates

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


class _UnsupportedRipgrepPattern(Exception):
    """A prevalidated Python pattern that ripgrep cannot execute."""
