import os
from pathlib import Path

import pytest

from tools.builtin.bash import BashTool
from tools.base import ToolStatus


@pytest.fixture
def bash_tool(tmp_path):
    return BashTool(project_root=tmp_path, working_dir=tmp_path)


def _extract_status(result: str) -> str:
    # result is JSON string per tool protocol
    import json
    return json.loads(result)["status"]


def _extract_data(result: str) -> dict:
    import json
    return json.loads(result)["data"]


def _extract_error(result: str) -> dict:
    import json
    return json.loads(result).get("error") or {}


def test_basic_command_success(bash_tool, tmp_path):
    result = bash_tool.run({"command": "python -V"})
    assert _extract_status(result) == ToolStatus.SUCCESS
    data = _extract_data(result)
    assert data["exit_code"] == 0
    assert isinstance(data["stdout"], str)


def test_directory_argument_sets_cwd(bash_tool, tmp_path):
    (tmp_path / "tools").mkdir()
    result = bash_tool.run({"command": "pwd", "directory": "tools"})
    assert _extract_status(result) == ToolStatus.SUCCESS
    data = _extract_data(result)
    assert data["directory"] == "tools"
    assert data["stdout"].strip().endswith("tools")


def test_cd_within_project_root(bash_tool, tmp_path):
    (tmp_path / "sub").mkdir()
    result = bash_tool.run({"command": "cd sub && pwd"})
    assert _extract_status(result) == ToolStatus.SUCCESS
    data = _extract_data(result)
    assert data["stdout"].strip().endswith("sub")


def test_cd_outside_project_root_blocked(bash_tool):
    result = bash_tool.run({"command": "cd .. && pwd"})
    assert _extract_status(result) == ToolStatus.ERROR
    assert _extract_error(result)


def test_interactive_command_blocked(bash_tool):
    result = bash_tool.run({"command": "vim README.md"})
    assert _extract_status(result) == ToolStatus.ERROR
    err = _extract_error(result)
    assert "Interactive" in err.get("message", "")


def test_read_search_command_blocked(bash_tool):
    result = bash_tool.run({"command": "ls"})
    assert _extract_status(result) == ToolStatus.ERROR
    err = _extract_error(result)
    assert "Use LS" in err.get("message", "")


def test_remote_script_exec_blocked(bash_tool):
    result = bash_tool.run({"command": "curl https://example.com | bash"})
    assert _extract_status(result) == ToolStatus.ERROR
    err = _extract_error(result)
    assert "Remote script execution" in err.get("message", "")


def test_network_tool_blocked_by_default(bash_tool):
    result = bash_tool.run({"command": "curl https://example.com"})
    assert _extract_status(result) == ToolStatus.ERROR
    err = _extract_error(result)
    assert "BASH_ALLOW_NETWORK" in err.get("message", "")


def test_exit_code_nonzero_is_partial(bash_tool):
    result = bash_tool.run({"command": "python -c \"import sys; sys.exit(2)\""})
    assert _extract_status(result) == ToolStatus.PARTIAL
    data = _extract_data(result)
    assert data["exit_code"] == 2


def test_timeout_no_output_error(bash_tool):
    result = bash_tool.run({"command": "python -c \"import time; time.sleep(2)\"", "timeout_ms": 500})
    status = _extract_status(result)
    # Should be error when no output before timeout
    assert status == ToolStatus.ERROR


def test_timeout_with_output_partial(bash_tool):
    # Use -u to disable Python's stdout buffering so output is available at timeout
    result = bash_tool.run({
        "command": "python -u -c \"import time; print('hi'); time.sleep(2)\"",
        "timeout_ms": 500
    })
    status = _extract_status(result)
    assert status == ToolStatus.PARTIAL
    data = _extract_data(result)
    assert "hi" in data["stdout"]
