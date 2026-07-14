"""One model-envelope contract shared by every stable built-in tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.contracts.tool_results import assert_model_tool_result
from tools.builtin.bash import BashTool
from tools.builtin.edit_file import EditTool
from tools.builtin.glob import GlobTool
from tools.builtin.read_file import ReadTool
from tools.builtin.search_code import GrepTool
from tools.builtin.task import TaskTool
from tools.builtin.todo_write import TodoWriteTool


@pytest.fixture
def contract_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("class Contract:\n    pass\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    ("tool_factory", "parameters", "expected_status"),
    [
        (lambda root: GlobTool(project_root=root), {"path": ".", "pattern": "**/*.py"}, "success"),
        (lambda root: GrepTool(project_root=root), {"pattern": "Contract", "glob": "src/**/*.py"}, "success"),
        (lambda root: ReadTool(project_root=root), {"path": "src/main.py"}, "success"),
        (lambda root: EditTool(project_root=root), {"path": "notes.txt", "create_content": "created\n"}, "success"),
        (lambda root: TodoWriteTool(project_root=root), {"summary": "contract", "todos": []}, "success"),
        (lambda root: BashTool(project_root=root), {"command": "printf contract"}, "success"),
        (
            lambda root: TaskTool(project_root=root, launcher=object()),
            {"description": "inspect", "prompt": "inspect", "subagent_type": "unsupported"},
            "error",
        ),
    ],
)
def test_stable_builtin_tools_return_one_model_envelope(
    contract_project: Path,
    tool_factory,
    parameters: dict,
    expected_status: str,
) -> None:
    result = tool_factory(contract_project).run(parameters)

    assert_model_tool_result(result, expected_status=expected_status)
