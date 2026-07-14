"""Small shared path rules for the stable discovery tools."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path

from tools.workspace import FileWorkspace, WorkspaceError


DEFAULT_IGNORED_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".idea",
        ".vscode",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "target",
        "venv",
    }
)
DEFAULT_RESULT_LIMIT = 100
MAX_RESULT_LIMIT = 200


def resolve_search_directory(workspace: FileWorkspace, requested: str) -> tuple[Path, str]:
    """Resolve an existing project-confined directory for a search."""
    target = workspace.resolve(requested)
    relative = workspace.relative(target)
    if not target.exists():
        raise WorkspaceError("not_found", f"Search path '{requested}' does not exist.")
    if not target.is_dir():
        raise WorkspaceError("not_directory", f"Search path '{requested}' is not a directory.")
    return target, relative


def visible_name(name: str, *, include_hidden: bool, include_ignored: bool) -> bool:
    """Whether an entry is included under the two discovery policies."""
    if not include_hidden and name.startswith("."):
        return False
    return include_ignored or name not in DEFAULT_IGNORED_NAMES


def iter_files(
    root: Path, *, include_hidden: bool = False, include_ignored: bool = False
) -> Iterator[Path]:
    """Yield ordinary files below ``root`` in deterministic path order."""
    for directory, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(directory)
        directories[:] = [
            name
            for name in sorted(directories)
            if visible_name(
                name, include_hidden=include_hidden, include_ignored=include_ignored
            )
            and not (current / name).is_symlink()
        ]
        for name in sorted(filenames):
            candidate = current / name
            if (
                visible_name(name, include_hidden=include_hidden, include_ignored=include_ignored)
                and not candidate.is_symlink()
            ):
                yield candidate


def path_matches(path: str, pattern: str) -> bool:
    """Match a relative POSIX path without letting ``*`` cross a directory."""
    pattern = pattern.replace("\\", "/").lstrip("/")
    while pattern.startswith("./"):
        pattern = pattern[2:]
    expression: list[str] = ["^"]
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*" and index + 1 < len(pattern) and pattern[index + 1] == "*":
            if index + 2 < len(pattern) and pattern[index + 2] == "/":
                expression.append("(?:.*/)?")
                index += 3
                continue
            expression.append(".*")
            index += 2
            continue
        if char == "*":
            expression.append("[^/]*")
        elif char == "?":
            expression.append("[^/]")
        elif char == "[":
            closing = pattern.find("]", index + 1)
            if closing != -1:
                contents = pattern[index + 1 : closing]
                expression.append("[" + ("^" if contents.startswith("!") else "") + re.escape(contents.lstrip("!")) + "]")
                index = closing
            else:
                expression.append(re.escape(char))
        else:
            expression.append(re.escape(char))
        index += 1
    expression.append("$")
    return re.match("".join(expression), path) is not None
