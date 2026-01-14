"""ListFilesTool (LS) tests.

Covers pagination, filtering, sandbox checks, and protocol compliance.
"""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.builtin.list_files import ListFilesTool
from tools.base import ErrorCode
from tests.utils.protocol_validator import ProtocolValidator
from tests.utils.test_helpers import create_temp_project, parse_response


class TestListFilesTool(unittest.TestCase):
    """ListFilesTool unit tests."""

    def _validate(self, response_str: str, expected_status: str = None) -> dict:
        result = ProtocolValidator.validate(response_str, tool_type="ls")
        if not result.passed:
            error_msg = "\n" + "=" * 60 + "\n"
            error_msg += "LS protocol validation failed\n"
            error_msg += "=" * 60 + "\n"
            for error in result.errors:
                error_msg += f"  {error}\n"
            if result.warnings:
                error_msg += "\nWarnings:\n"
                for warning in result.warnings:
                    error_msg += f"  {warning}\n"
            self.fail(error_msg)
        parsed = parse_response(response_str)
        if expected_status:
            self.assertEqual(parsed["status"], expected_status)
        return parsed

    def test_success_list_current_dir(self):
        with create_temp_project() as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": "."})
            parsed = self._validate(response, "success")
            self.assertIsInstance(parsed["data"]["entries"], list)
            self.assertGreaterEqual(len(parsed["data"]["entries"]), 1)

    def test_success_list_nested_dir(self):
        with create_temp_project() as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": "src"})
            parsed = self._validate(response, "success")
            self.assertEqual(parsed["context"].get("path_resolved"), "src")
            self.assertGreaterEqual(len(parsed["data"]["entries"]), 1)

    def test_success_empty_directory(self):
        with create_temp_project({"empty/": None}) as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": "empty"})
            parsed = self._validate(response, "success")
            self.assertEqual(parsed["data"]["entries"], [])
            self.assertEqual(parsed["stats"].get("total_entries"), 0)

    def test_default_ignore_and_hidden(self):
        structure = {
            "src/": None,
            "node_modules/ignored.js": "console.log('x')",
            ".hidden_file.txt": "secret",
            "README.md": "readme",
        }
        with create_temp_project(structure) as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": "."})
            parsed = self._validate(response, "success")
            paths = [entry["path"] for entry in parsed["data"]["entries"]]
            self.assertNotIn("node_modules", paths)
            self.assertNotIn(".hidden_file.txt", paths)
            self.assertIn("README.md", paths)

    def test_include_hidden_includes_default_ignored(self):
        structure = {
            "node_modules/ignored.js": "console.log('x')",
            ".hidden_file.txt": "secret",
            "README.md": "readme",
        }
        with create_temp_project(structure) as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": ".", "include_hidden": True})
            parsed = self._validate(response, "success")
            paths = [entry["path"] for entry in parsed["data"]["entries"]]
            self.assertIn("node_modules", paths)
            self.assertIn(".hidden_file.txt", paths)

    def test_custom_ignore_pattern(self):
        structure = {
            "README.md": "readme",
            "docs/": None,
            "docs/guide.md": "guide",
        }
        with create_temp_project(structure) as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": ".", "ignore": ["README.md"]})
            parsed = self._validate(response, "success")
            paths = [entry["path"] for entry in parsed["data"]["entries"]]
            self.assertNotIn("README.md", paths)
            self.assertIn("docs", paths)

    def test_sorting_dirs_before_files(self):
        structure = {
            "b_dir/": None,
            "a_dir/": None,
            "b.txt": "b",
            "a.txt": "a",
        }
        with create_temp_project(structure) as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": "."})
            parsed = self._validate(response, "success")
            paths = [entry["path"] for entry in parsed["data"]["entries"]]
            self.assertEqual(paths[:2], ["a_dir", "b_dir"])
            self.assertEqual(paths[2:], ["a.txt", "b.txt"])

    def test_symlink_entry(self):
        structure = {"src/": None, "src/main.py": "print('x')"}
        with create_temp_project(structure) as project:
            link_path = project.path("link_to_src")
            try:
                os.symlink(project.path("src"), link_path)
            except OSError:
                self.skipTest("Symlink not supported in this environment")
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": "."})
            parsed = self._validate(response, "success")
            entry = next((e for e in parsed["data"]["entries"] if e["path"] == "link_to_src"), None)
            self.assertIsNotNone(entry)
            self.assertEqual(entry["type"], "link")

    def test_pagination_limit_truncation(self):
        structure = {"a.txt": "a", "b.txt": "b", "c.txt": "c"}
        with create_temp_project(structure) as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": ".", "limit": 1})
            parsed = self._validate(response, "partial")
            self.assertTrue(parsed["data"].get("truncated"))
            self.assertEqual(len(parsed["data"]["entries"]), 1)
            self.assertIn("Use offset=", parsed["text"])

    def test_pagination_offset(self):
        structure = {"a.txt": "a", "b.txt": "b"}
        with create_temp_project(structure) as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": ".", "offset": 1})
            parsed = self._validate(response, "success")
            self.assertEqual(len(parsed["data"]["entries"]), 1)

    def test_offset_exceeds_total_returns_empty(self):
        structure = {"a.txt": "a"}
        with create_temp_project(structure) as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": ".", "offset": 10})
            parsed = self._validate(response, "success")
            self.assertEqual(parsed["data"]["entries"], [])

    def test_error_not_found(self):
        with create_temp_project() as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": "missing"})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.NOT_FOUND.value)

    def test_error_is_file(self):
        with create_temp_project() as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": "README.md"})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.INVALID_PARAM.value)

    def test_error_invalid_offset(self):
        with create_temp_project() as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": ".", "offset": -1})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.INVALID_PARAM.value)

    def test_error_invalid_limit(self):
        with create_temp_project() as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": ".", "limit": 0})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.INVALID_PARAM.value)

            response = tool.run({"path": ".", "limit": 201})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.INVALID_PARAM.value)

    def test_error_ignore_not_list(self):
        with create_temp_project() as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": ".", "ignore": "README.md"})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.INVALID_PARAM.value)

    def test_access_denied_traversal(self):
        with create_temp_project() as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": "../"})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.ACCESS_DENIED.value)

    def test_access_denied_absolute_outside(self):
        with create_temp_project() as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": str(project.root.parent)})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.ACCESS_DENIED.value)

    def test_permission_denied_from_os(self):
        with create_temp_project() as project:
            tool = ListFilesTool(project_root=project.root)
            with patch.object(ListFilesTool, "_list_items", side_effect=PermissionError):
                response = tool.run({"path": "."})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.ACCESS_DENIED.value)


if __name__ == "__main__":
    unittest.main()
