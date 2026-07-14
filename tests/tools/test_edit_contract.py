"""Public contract for the single atomic Edit file-mutation tool."""

from __future__ import annotations

import json

from runtime.host import CodeAgent
from tools import workspace as workspace_module
from tools.builtin.edit_file import EditTool
from tools.registry import ToolRegistry
from tools.base import serialize_tool_result


def _response(tool: EditTool, parameters: dict) -> dict:
    return json.loads(serialize_tool_result(tool.run(parameters)))


def _snapshot(path):
    status = path.stat()
    return {
        "expected_mtime_ms": status.st_mtime_ns // 1_000_000,
        "expected_size_bytes": status.st_size,
    }


def test_edit_creates_a_new_text_file_atomically(tmp_path):
    response = _response(
        EditTool(project_root=tmp_path),
        {"path": "notes/new.txt", "create_content": "created\n"},
    )

    assert response["status"] == "success"
    assert response["data"]["operation"] == "create"
    assert (tmp_path / "notes/new.txt").read_text(encoding="utf-8") == "created\n"
    assert not list(tmp_path.rglob(".mycodeagent-*.tmp"))


def test_edit_applies_one_unique_replacement_after_read_snapshot(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("before\n", encoding="utf-8")

    response = _response(
        EditTool(project_root=tmp_path),
        {
            "path": "notes.txt",
            "edits": [{"old_string": "before", "new_string": "after"}],
            **_snapshot(target),
        },
    )

    assert response["status"] == "success"
    assert response["data"]["operation"] == "edit"
    assert response["data"]["replacements"] == 1
    assert target.read_text(encoding="utf-8") == "after\n"


def test_edit_replaces_an_existing_empty_file_with_a_read_snapshot(tmp_path):
    target = tmp_path / "empty.txt"
    target.write_text("", encoding="utf-8")

    response = _response(
        EditTool(project_root=tmp_path),
        {"path": "empty.txt", "create_content": "replacement\n", **_snapshot(target)},
    )

    assert response["status"] == "success"
    assert response["data"]["operation"] == "replace"
    assert target.read_text(encoding="utf-8") == "replacement\n"


def test_edit_applies_ordered_non_overlapping_replacements_in_one_write(tmp_path, monkeypatch):
    target = tmp_path / "notes.txt"
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")
    writes = []
    original = workspace_module.FileWorkspace.atomic_write

    def record_write(self, *args, **kwargs):
        writes.append(args[1])
        return original(self, *args, **kwargs)

    monkeypatch.setattr(workspace_module.FileWorkspace, "atomic_write", record_write)
    response = _response(
        EditTool(project_root=tmp_path),
        {
            "path": "notes.txt",
            "edits": [
                {"old_string": "one", "new_string": "first"},
                {"old_string": "three", "new_string": "third"},
            ],
            **_snapshot(target),
        },
    )

    assert response["status"] == "success"
    assert response["data"]["replacements"] == 2
    assert writes == ["first\ntwo\nthird\n"]
    assert target.read_text(encoding="utf-8") == "first\ntwo\nthird\n"


def test_edit_rejects_overlapping_replacements_without_changing_the_file(tmp_path):
    target = tmp_path / "notes.txt"
    original = "abcdef\n"
    target.write_text(original, encoding="utf-8")

    response = _response(
        EditTool(project_root=tmp_path),
        {
            "path": "notes.txt",
            "edits": [
                {"old_string": "abc", "new_string": "A"},
                {"old_string": "bcd", "new_string": "B"},
            ],
            **_snapshot(target),
        },
    )

    assert response["status"] == "error"
    assert response["error"]["code"] == "INVALID_PARAM"
    assert "overlap" in response["error"]["message"].lower()
    assert target.read_text(encoding="utf-8") == original


def test_edit_rejects_a_duplicate_match_without_changing_the_file(tmp_path):
    target = tmp_path / "notes.txt"
    original = "repeat\nrepeat\n"
    target.write_text(original, encoding="utf-8")

    response = _response(
        EditTool(project_root=tmp_path),
        {
            "path": "notes.txt",
            "edits": [{"old_string": "repeat", "new_string": "changed"}],
            **_snapshot(target),
        },
    )

    assert response["status"] == "error"
    assert response["error"]["code"] == "INVALID_PARAM"
    assert "matches 2 times" in response["error"]["message"]
    assert target.read_text(encoding="utf-8") == original


def test_edit_dry_run_never_writes(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("before\n", encoding="utf-8")

    response = _response(
        EditTool(project_root=tmp_path),
        {
            "path": "notes.txt",
            "edits": [{"old_string": "before", "new_string": "after"}],
            "dry_run": True,
            **_snapshot(target),
        },
    )

    assert response["status"] == "partial"
    assert response["data"]["applied"] is False
    assert target.read_text(encoding="utf-8") == "before\n"


def test_edit_rejects_a_stale_snapshot_without_changing_the_file(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("before\n", encoding="utf-8")
    stale = _snapshot(target)
    target.write_text("external change\n", encoding="utf-8")

    response = _response(
        EditTool(project_root=tmp_path),
        {
            "path": "notes.txt",
            "edits": [{"old_string": "external change", "new_string": "after"}],
            **stale,
        },
    )

    assert response["status"] == "error"
    assert response["error"]["code"] == "CONFLICT"
    assert target.read_text(encoding="utf-8") == "external change\n"


def test_edit_preserves_existing_crlf_newlines(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_bytes(b"one\r\ntwo\r\n")

    response = _response(
        EditTool(project_root=tmp_path),
        {
            "path": "notes.txt",
            "edits": [{"old_string": "two", "new_string": "second"}],
            **_snapshot(target),
        },
    )

    assert response["status"] == "success"
    assert target.read_bytes() == b"one\r\nsecond\r\n"


def test_edit_keeps_the_original_file_when_atomic_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "notes.txt"
    target.write_text("before\n", encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(workspace_module.os, "replace", fail_replace)
    response = _response(
        EditTool(project_root=tmp_path),
        {
            "path": "notes.txt",
            "edits": [{"old_string": "before", "new_string": "after"}],
            **_snapshot(target),
        },
    )

    assert response["status"] == "error"
    assert target.read_text(encoding="utf-8") == "before\n"
    assert not list(tmp_path.glob(".mycodeagent-*.tmp"))


def test_edit_schema_and_default_host_register_only_edit_for_file_mutation(tmp_path):
    class DummyLLM:
        provider = "openai"
        model = "test"

    agent = CodeAgent(
        name="code",
        llm=DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        enable_tracing=False,
    )
    names = agent.tool_registry.list_tools()
    schema = next(
        item["function"]["parameters"]
        for item in agent.tool_registry.get_openai_tools()
        if item["function"]["name"] == "Edit"
    )

    assert "Edit" in names
    assert "Write" not in names
    assert "MultiEdit" not in names
    assert set(schema["properties"]) == {
        "path",
        "edits",
        "create_content",
        "expected_mtime_ms",
        "expected_size_bytes",
        "dry_run",
    }
    assert schema["required"] == ["path"]
