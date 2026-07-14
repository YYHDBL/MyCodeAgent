"""Focused contracts for the project-confined file workspace."""

from __future__ import annotations

import json
import os
import stat

import pytest

from tools import workspace as workspace_module
from tools.builtin.edit_file import EditTool
from tools.builtin.read_file import ReadTool
from tools.base import serialize_tool_result
from tools.workspace import FileWorkspace, WorkspaceError


@pytest.fixture
def workspace(tmp_path):
    return FileWorkspace(tmp_path)


@pytest.mark.parametrize(
    ("requested", "expected"),
    [("notes.txt", "notes.txt"), ("src/../notes.txt", "notes.txt")],
)
def test_resolve_normalizes_relative_paths_under_the_project(workspace, requested, expected):
    assert workspace.resolve(requested) == workspace.root / expected


def test_resolve_rejects_absolute_and_traversal_paths(workspace):
    with pytest.raises(WorkspaceError, match="Absolute"):
        workspace.resolve("/tmp/outside.txt")

    with pytest.raises(WorkspaceError, match="outside"):
        workspace.resolve("../outside.txt")


def test_resolve_rejects_symlink_escape(workspace, tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = workspace.root / "escape"
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    with pytest.raises(WorkspaceError, match="outside"):
        workspace.resolve("escape")


def test_resolve_converts_a_symlink_loop_to_a_workspace_error(workspace):
    first = workspace.root / "first"
    second = workspace.root / "second"
    try:
        first.symlink_to(second.name)
        second.symlink_to(first.name)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    with pytest.raises(WorkspaceError, match="Path resolution failed") as raised:
        workspace.resolve("first")

    assert raised.value.kind == "io"


@pytest.mark.parametrize(
    ("name", "make"),
    [
        ("missing.txt", lambda target: None),
        ("directory", lambda target: target.mkdir()),
        ("binary.bin", lambda target: target.write_bytes(b"text\x00data")),
    ],
)
def test_file_tool_workspace_errors_keep_the_safe_resolved_path(workspace, name, make):
    make(workspace.root / name)

    read = json.loads(serialize_tool_result(ReadTool(project_root=workspace.root).run({"path": name})))
    edit = json.loads(serialize_tool_result(
        EditTool(project_root=workspace.root).run(
                {"path": name, "edits": [{"old_string": "text", "new_string": "changed"}]}
        )
    ))

    assert read["status"] == "error"
    assert edit["status"] == "error"
    assert read["context"]["path_resolved"] == name
    assert edit["context"]["path_resolved"] == name


def test_file_tools_turn_a_symlink_loop_into_protocol_errors(workspace):
    first = workspace.root / "first"
    second = workspace.root / "second"
    try:
        first.symlink_to(second.name)
        second.symlink_to(first.name)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    read = json.loads(serialize_tool_result(ReadTool(project_root=workspace.root).run({"path": "first"})))
    edit = json.loads(serialize_tool_result(
        EditTool(project_root=workspace.root).run(
                {"path": "first", "edits": [{"old_string": "text", "new_string": "changed"}]}
        )
    ))

    assert read["status"] == "error"
    assert read["error"]["code"] == "INTERNAL_ERROR"
    assert edit["status"] == "error"
    assert edit["error"]["code"] == "EXECUTION_ERROR"


def test_inspect_rejects_a_fifo_before_opening_it(workspace, monkeypatch):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFOs are not supported on this platform")
    os.mkfifo(workspace.root / "events.pipe")

    def binary_check_must_not_run(_self, _target):
        raise AssertionError("FIFO was opened for binary detection")

    monkeypatch.setattr(FileWorkspace, "_is_binary", binary_check_must_not_run)

    with pytest.raises(WorkspaceError, match="regular file") as raised:
        workspace.inspect("events.pipe")

    assert raised.value.kind == "not_regular"


def test_file_tools_reject_a_fifo_without_opening_it(workspace, monkeypatch):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFOs are not supported on this platform")
    os.mkfifo(workspace.root / "events.pipe")

    def binary_check_must_not_run(_self, _target):
        raise AssertionError("FIFO was opened for binary detection")

    monkeypatch.setattr(FileWorkspace, "_is_binary", binary_check_must_not_run)

    read = json.loads(serialize_tool_result(ReadTool(project_root=workspace.root).run({"path": "events.pipe"})))
    edit = json.loads(serialize_tool_result(
        EditTool(project_root=workspace.root).run(
                {"path": "events.pipe", "edits": [{"old_string": "event", "new_string": "changed"}]}
        )
    ))

    assert read["status"] == "error"
    assert read["error"]["code"] == "INVALID_PARAM"
    assert edit["status"] == "error"
    assert edit["error"]["code"] == "INVALID_PARAM"


@pytest.mark.parametrize(
    ("name", "make", "message"),
    [
        ("missing.txt", lambda target: None, "does not exist"),
        ("directory", lambda target: target.mkdir(), "directory"),
        ("binary.bin", lambda target: target.write_bytes(b"text\x00data"), "binary"),
    ],
)
def test_inspect_rejects_non_text_files(workspace, name, make, message):
    target = workspace.root / name
    make(target)

    with pytest.raises(WorkspaceError, match=message):
        workspace.inspect(name)


def test_read_text_uses_utf8_replacement_fallback(workspace):
    (workspace.root / "latin1.txt").write_bytes(b"caf\xe9")

    text, encoding, fallback, _snapshot = workspace.read_text("latin1.txt")

    assert text == "caf\ufffd"
    assert encoding == "utf-8 (replace)"
    assert fallback is True


def test_atomic_write_requires_the_expected_snapshot(workspace):
    target = workspace.root / "notes.txt"
    target.write_text("before", encoding="utf-8")
    snapshot = workspace.inspect("notes.txt")
    target.write_text("external change", encoding="utf-8")

    with pytest.raises(WorkspaceError, match="modified"):
        workspace.atomic_write("notes.txt", "after", expected=snapshot)

    assert target.read_text(encoding="utf-8") == "external change"


def test_atomic_write_replaces_only_after_a_matching_snapshot(workspace):
    target = workspace.root / "notes.txt"
    target.write_text("before", encoding="utf-8")
    snapshot = workspace.inspect("notes.txt")

    written = workspace.atomic_write("notes.txt", "after", expected=snapshot)

    assert written == len(b"after")
    assert target.read_text(encoding="utf-8") == "after"
    assert not list(workspace.root.glob(".mycodeagent-*.tmp"))


def test_atomic_write_preserves_existing_file_permissions(workspace):
    target = workspace.root / "script.sh"
    target.write_text("before", encoding="utf-8")
    target.chmod(0o755)
    snapshot = workspace.inspect("script.sh")

    workspace.atomic_write("script.sh", "after", expected=snapshot)

    assert stat.S_IMODE(target.stat().st_mode) == 0o755


def test_atomic_write_failure_keeps_original_and_cleans_temporary_file(workspace, monkeypatch):
    target = workspace.root / "notes.txt"
    target.write_text("before", encoding="utf-8")
    snapshot = workspace.inspect("notes.txt")

    def fail_replace(source, destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(workspace_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        workspace.atomic_write("notes.txt", "after", expected=snapshot)

    assert target.read_text(encoding="utf-8") == "before"
    assert not list(workspace.root.glob(".mycodeagent-*.tmp"))
