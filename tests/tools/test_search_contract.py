"""Contracts for the two stable discovery tools: Glob and Grep."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.builtin.glob import GlobTool
from tools.builtin.search_code import GrepTool, _UnsupportedRipgrepPattern
from tools.base import serialize_tool_result


def _response(tool, parameters: dict) -> dict:
    return json.loads(serialize_tool_result(tool.run(parameters)))


@pytest.fixture
def search_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "nested").mkdir()
    (tmp_path / "build").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "README.md").write_text("project overview\n", encoding="utf-8")
    (tmp_path / "src" / "app.py").write_text("TODO: implement\nvalue = 1\n", encoding="utf-8")
    (tmp_path / "src" / "nested" / "worker.py").write_text(
        "todo: nested\n", encoding="utf-8"
    )
    (tmp_path / "build" / "generated.py").write_text("TODO: generated\n", encoding="utf-8")
    (tmp_path / ".hidden" / "secret.py").write_text("TODO: secret\n", encoding="utf-8")
    (tmp_path / "binary.bin").write_bytes(b"text\x00not-source")
    return tmp_path


def test_glob_lists_a_directory_in_deterministic_order(search_project: Path) -> None:
    response = _response(GlobTool(project_root=search_project), {"path": "."})

    assert response["status"] == "success"
    assert response["data"]["paths"] == ["README.md", "binary.bin", "src"]


def test_glob_recursively_matches_files_and_excludes_hidden_and_ignored(
    search_project: Path,
) -> None:
    response = _response(
        GlobTool(project_root=search_project), {"path": ".", "pattern": "**/*.py"}
    )

    assert response["status"] == "success"
    assert response["data"]["paths"] == ["src/app.py", "src/nested/worker.py"]


def test_glob_can_include_hidden_and_ignored_paths(search_project: Path) -> None:
    response = _response(
        GlobTool(project_root=search_project),
        {
            "path": ".",
            "pattern": "**/*.py",
            "include_hidden": True,
            "include_ignored": True,
        },
    )

    assert response["data"]["paths"] == [
        ".hidden/secret.py",
        "build/generated.py",
        "src/app.py",
        "src/nested/worker.py",
    ]


def test_glob_marks_limited_results_partial(search_project: Path) -> None:
    response = _response(
        GlobTool(project_root=search_project),
        {"path": ".", "pattern": "**/*.py", "limit": 1},
    )

    assert response["status"] == "partial"
    assert response["data"] == {"paths": ["src/app.py"], "truncated": True}


def test_glob_rejects_workspace_escape(search_project: Path) -> None:
    response = _response(GlobTool(project_root=search_project), {"path": "../"})

    assert response["status"] == "error"
    assert response["error"]["code"] == "ACCESS_DENIED"


def test_grep_matches_content_with_a_glob_filter(search_project: Path) -> None:
    response = _response(
        GrepTool(project_root=search_project),
        {"pattern": "todo", "glob": "src/**/*.py"},
    )

    assert response["status"] == "success"
    assert response["data"]["matches"] == [
        {"file": "src/app.py", "line": 1, "text": "TODO: implement"},
        {"file": "src/nested/worker.py", "line": 1, "text": "todo: nested"},
    ]


def test_grep_skips_binary_files(search_project: Path) -> None:
    response = _response(GrepTool(project_root=search_project), {"pattern": "text"})

    assert response["status"] == "success"
    assert response["data"]["matches"] == []


def test_grep_python_fallback_succeeds_when_results_are_complete(
    search_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tools.builtin.search_code.shutil.which", lambda _: None)

    response = _response(GrepTool(project_root=search_project), {"pattern": "TODO"})

    assert response["status"] == "success"
    assert response["data"]["fallback_used"] is True
    assert response["data"]["fallback_reason"] == "rg_not_found"


def test_grep_bounds_one_long_matching_line_with_partial_metadata(tmp_path: Path) -> None:
    (tmp_path / "long.txt").write_text("needle " + "x" * 10_000 + "\n", encoding="utf-8")

    response = _response(GrepTool(project_root=tmp_path), {"pattern": "needle"})

    assert response["status"] == "partial"
    assert response["data"]["truncated"] is True
    assert response["data"]["truncation_reasons"] == ["line_length"]
    assert len(response["data"]["matches"][0]["text"]) <= GrepTool.max_line_chars


def test_grep_falls_back_when_rg_rejects_a_python_valid_regex(
    search_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject_pattern(*_args, **_kwargs):
        raise _UnsupportedRipgrepPattern("unsupported")

    monkeypatch.setattr("tools.builtin.search_code.shutil.which", lambda _: "/usr/bin/rg")
    monkeypatch.setattr(GrepTool, "_rg_matches", reject_pattern)

    response = _response(GrepTool(project_root=search_project), {"pattern": "TODO(?=:)"})

    assert response["status"] == "success"
    assert response["data"]["matches"] == [
        {"file": "src/app.py", "line": 1, "text": "TODO: implement"},
        {"file": "src/nested/worker.py", "line": 1, "text": "todo: nested"},
    ]
    assert response["data"]["fallback_reason"] == "rg_unsupported_pattern"


def test_grep_rejects_invalid_regular_expression(search_project: Path) -> None:
    response = _response(GrepTool(project_root=search_project), {"pattern": "["})

    assert response["status"] == "error"
    assert response["error"]["code"] == "INVALID_PARAM"


def test_grep_marks_limited_results_partial_in_deterministic_order(search_project: Path) -> None:
    response = _response(
        GrepTool(project_root=search_project), {"pattern": "todo", "limit": 1}
    )

    assert response["status"] == "partial"
    assert response["data"]["matches"] == [
        {"file": "src/app.py", "line": 1, "text": "TODO: implement"}
    ]
    assert response["data"]["truncated"] is True
