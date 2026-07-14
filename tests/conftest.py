"""Pytest 配置和共享 fixtures.

Keep pytest runnable from the repository root without requiring callers to
manually export ``PYTHONPATH``.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.utils.test_helpers import create_temp_project


@pytest.fixture
def temp_project():
    """
    提供临时测试项目 fixture

    Usage:
        def test_something(temp_project):
            tool = GlobTool(project_root=temp_project.root)
            ...
    """
    with create_temp_project() as project:
        yield project
