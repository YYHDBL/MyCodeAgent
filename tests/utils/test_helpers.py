"""测试辅助工具

提供测试所需的临时项目创建、响应解析等复用函数。
"""

import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class TempProject:
    """临时测试项目"""
    root: Path
    
    def __post_init__(self):
        self.root = Path(self.root)
    
    def path(self, *parts: str) -> Path:
        """获取项目内路径"""
        return self.root.joinpath(*parts)
    
    def create_file(self, rel_path: str, content: str = "") -> Path:
        """创建文件"""
        file_path = self.path(rel_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return file_path
    
    def create_dir(self, rel_path: str) -> Path:
        """创建目录"""
        dir_path = self.path(rel_path)
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path
    
    def cleanup(self):
        """清理临时目录"""
        if self.root.exists():
            shutil.rmtree(self.root)


@contextmanager
def create_temp_project(structure: Optional[Dict[str, Any]] = None):
    """
    创建临时测试项目（上下文管理器）
    
    Args:
        structure: 项目结构字典，格式如:
            {
                "src/main.py": "print('hello')",
                "src/utils.py": "def helper(): pass",
                "tests/": None,  # 空目录
                "README.md": "# Test Project"
            }
    
    Yields:
        TempProject: 临时项目对象
    
    Example:
        with create_temp_project({"src/main.py": "..."}) as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": "."})
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_project_"))
    project = TempProject(root=temp_dir)
    
    try:
        # 创建默认结构
        if structure is None:
            structure = DEFAULT_PROJECT_STRUCTURE
        
        for path, content in structure.items():
            if path.endswith("/"):
                # 目录
                project.create_dir(path.rstrip("/"))
            else:
                # 文件
                project.create_file(path, content or "")
        
        yield project
    finally:
        project.cleanup()


# 默认测试项目结构
DEFAULT_PROJECT_STRUCTURE = {
    "src/": None,
    "src/main.py": """#!/usr/bin/env python3
\"\"\"主模块\"\"\"

class MyClass:
    \"\"\"示例类\"\"\"
    
    def __init__(self, name: str):
        self.name = name
    
    def greet(self) -> str:
        return f"Hello, {self.name}!"


def main():
    obj = MyClass("World")
    print(obj.greet())


if __name__ == "__main__":
    main()
""",
    "src/utils.py": """\"\"\"工具函数\"\"\"

from typing import List, Optional


def helper(items: List[str], prefix: Optional[str] = None) -> List[str]:
    \"\"\"添加前缀\"\"\"
    if prefix:
        return [f"{prefix}{item}" for item in items]
    return items


def validate(value: str) -> bool:
    \"\"\"验证值\"\"\"
    return bool(value and value.strip())


# TODO: 添加更多工具函数
""",
    "src/config.py": """\"\"\"配置模块\"\"\"

import os

DEBUG = os.getenv("DEBUG", "false").lower() == "true"
API_KEY = os.getenv("API_KEY", "")

class Config:
    debug: bool = DEBUG
    api_key: str = API_KEY
""",
    "tests/": None,
    "tests/__init__.py": "",
    "tests/test_main.py": """import unittest
from src.main import MyClass


class TestMyClass(unittest.TestCase):
    def test_greet(self):
        obj = MyClass("Test")
        self.assertEqual(obj.greet(), "Hello, Test!")


if __name__ == "__main__":
    unittest.main()
""",
    "docs/": None,
    "docs/README.md": "# 文档\n\n这是测试项目的文档目录。",
    "README.md": """# 测试项目

这是一个用于协议合规性测试的临时项目。

## 结构

```
src/
├── main.py     # 主模块
├── utils.py    # 工具函数
└── config.py   # 配置
tests/
├── __init__.py
└── test_main.py
docs/
└── README.md
```

## 运行

```bash
python src/main.py
```
""",
    ".gitignore": """__pycache__/
*.pyc
.env
.venv/
""",
}


def parse_response(response_str: str) -> Dict[str, Any]:
    """
    解析工具响应 JSON
    
    Args:
        response_str: JSON 格式的响应字符串
        
    Returns:
        解析后的字典
        
    Raises:
        ValueError: JSON 解析失败
    """
    try:
        return json.loads(response_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"响应不是有效的 JSON: {e}")


def assert_response_status(response_str: str, expected_status: str) -> Dict[str, Any]:
    """
    断言响应状态并返回解析结果
    
    Args:
        response_str: JSON 格式的响应字符串
        expected_status: 期望的状态值 ("success", "partial", "error")
        
    Returns:
        解析后的字典
        
    Raises:
        AssertionError: 状态不匹配
    """
    parsed = parse_response(response_str)
    actual_status = parsed.get("status")
    
    if actual_status != expected_status:
        raise AssertionError(
            f"期望 status='{expected_status}'，实际 status='{actual_status}'\n"
            f"响应: {json.dumps(parsed, ensure_ascii=False, indent=2)}"
        )
    
    return parsed


def get_response_data(response_str: str) -> Dict[str, Any]:
    """提取响应中的 data 字段"""
    return parse_response(response_str).get("data", {})


def get_response_error(response_str: str) -> Optional[Dict[str, Any]]:
    """提取响应中的 error 字段"""
    return parse_response(response_str).get("error")


def format_response(response_str: str, indent: int = 2) -> str:
    """格式化响应 JSON（用于调试输出）"""
    try:
        parsed = json.loads(response_str)
        return json.dumps(parsed, ensure_ascii=False, indent=indent)
    except:
        return response_str
