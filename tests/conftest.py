"""Pytest 配置和共享 fixtures

提供测试所需的共享 fixtures，支持 pytest 运行。
"""

import pytest
from pathlib import Path

from tests.utils.test_helpers import create_temp_project, TempProject


@pytest.fixture
def temp_project():
    """
    提供临时测试项目 fixture
    
    Usage:
        def test_something(temp_project):
            tool = ListFilesTool(project_root=temp_project.root)
            ...
    """
    with create_temp_project() as project:
        yield project


@pytest.fixture
def ls_tool(temp_project):
    """ListFilesTool fixture"""
    from tools.builtin.list_files import ListFilesTool
    return ListFilesTool(project_root=temp_project.root)


@pytest.fixture
def glob_tool(temp_project):
    """SearchFilesByNameTool fixture"""
    from tools.builtin.search_files_by_name import SearchFilesByNameTool
    return SearchFilesByNameTool(project_root=temp_project.root)


@pytest.fixture
def grep_tool(temp_project):
    """GrepTool fixture"""
    from tools.builtin.search_code import GrepTool
    return GrepTool(project_root=temp_project.root)
