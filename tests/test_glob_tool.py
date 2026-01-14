"""SearchFilesByNameTool (Glob) tests."""

import unittest
from unittest.mock import patch

from tools.builtin.search_files_by_name import SearchFilesByNameTool
from tools.base import ErrorCode
from tests.utils.protocol_validator import ProtocolValidator
from tests.utils.test_helpers import create_temp_project, parse_response


class TestGlobTool(unittest.TestCase):
    def _validate(self, response_str: str, expected_status: str = None) -> dict:
        result = ProtocolValidator.validate(response_str, tool_type="glob")
        if not result.passed:
            error_msg = "\n" + "=" * 60 + "\n"
            error_msg += "Glob protocol validation failed\n"
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

    def _base_structure(self):
        return {
            "root.py": "print('root')",
            "src/a.py": "print('a')",
            "src/sub/b.py": "print('b')",
            "file1.txt": "one",
            "file10.txt": "ten",
            "file9.txt": "nine",
            "file0.txt": "zero",
            "foo.py": "print('foo')",
            "node_modules/ignored.js": "console.log('x')",
            ".hidden.py": "# hidden",
        }

    def test_success_exact_match(self):
        with create_temp_project(self._base_structure()) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "root.py"})
            parsed = self._validate(response, "success")
            self.assertIn("root.py", parsed["data"]["paths"])

    def test_wildcard_single_level(self):
        with create_temp_project(self._base_structure()) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "*.py"})
            parsed = self._validate(response, "success")
            paths = parsed["data"]["paths"]
            self.assertIn("root.py", paths)
            # Current implementation allows '*' to match across directories
            self.assertIn("src/a.py", paths)

    def test_wildcard_recursive(self):
        with create_temp_project(self._base_structure()) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "**/*.py"})
            parsed = self._validate(response, "success")
            paths = parsed["data"]["paths"]
            self.assertIn("root.py", paths)
            self.assertIn("src/a.py", paths)
            self.assertIn("src/sub/b.py", paths)

    def test_extension_match(self):
        with create_temp_project(self._base_structure()) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "*.txt"})
            parsed = self._validate(response, "success")
            paths = parsed["data"]["paths"]
            self.assertIn("file1.txt", paths)
            self.assertNotIn("src/a.py", paths)

    def test_include_hidden(self):
        with create_temp_project(self._base_structure()) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "*.py", "include_hidden": True})
            parsed = self._validate(response, "success")
            self.assertIn(".hidden.py", parsed["data"]["paths"])

    def test_include_ignored(self):
        with create_temp_project(self._base_structure()) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "**/*.js", "include_ignored": True})
            parsed = self._validate(response, "success")
            self.assertIn("node_modules/ignored.js", parsed["data"]["paths"])

    def test_path_relative_search(self):
        with create_temp_project(self._base_structure()) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "*.py", "path": "src"})
            parsed = self._validate(response, "success")
            paths = parsed["data"]["paths"]
            self.assertIn("src/a.py", paths)
            self.assertNotIn("root.py", paths)

    def test_limit_truncation(self):
        with create_temp_project(self._base_structure()) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "**/*.py", "limit": 1})
            parsed = self._validate(response, "partial")
            self.assertTrue(parsed["data"].get("truncated"))
            self.assertEqual(len(parsed["data"]["paths"]), 1)

    def test_pattern_question_mark(self):
        with create_temp_project(self._base_structure()) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "file?.txt"})
            parsed = self._validate(response, "success")
            paths = parsed["data"]["paths"]
            self.assertIn("file1.txt", paths)
            self.assertNotIn("file10.txt", paths)

    def test_pattern_bracket(self):
        with create_temp_project(self._base_structure()) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "file[0-9].txt"})
            parsed = self._validate(response, "success")
            paths = parsed["data"]["paths"]
            self.assertIn("file0.txt", paths)
            self.assertIn("file9.txt", paths)
            self.assertNotIn("file10.txt", paths)

    def test_pattern_double_star_zero_layer(self):
        with create_temp_project(self._base_structure()) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "**/foo.py"})
            parsed = self._validate(response, "success")
            self.assertIn("foo.py", parsed["data"]["paths"])

    def test_pattern_dot_slash_prefix(self):
        with create_temp_project(self._base_structure()) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "./root.py"})
            parsed = self._validate(response, "success")
            self.assertIn("root.py", parsed["data"]["paths"])

    def test_circuit_count_limit_partial(self):
        with create_temp_project({"a.py": "a", "b.py": "b"}) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            tool.MAX_VISITED_ENTRIES = 2
            response = tool.run({"pattern": "*.py"})
            parsed = self._validate(response, "partial")
            self.assertEqual(parsed["data"].get("aborted_reason"), "count_limit")
            self.assertGreaterEqual(len(parsed["data"]["paths"]), 1)

    def test_circuit_timeout_no_results(self):
        with create_temp_project({"a.txt": "a"}) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            with patch.object(SearchFilesByNameTool, "_should_abort", return_value=True), \
                 patch.object(SearchFilesByNameTool, "_abort_reason", return_value="time_limit"):
                response = tool.run({"pattern": "*.py"})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.TIMEOUT.value)

    def test_error_missing_pattern(self):
        with create_temp_project() as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.INVALID_PARAM.value)

    def test_error_limit_invalid(self):
        with create_temp_project() as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "*.py", "limit": 0})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.INVALID_PARAM.value)

    def test_error_not_found(self):
        with create_temp_project() as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "*.py", "path": "missing"})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.NOT_FOUND.value)

    def test_error_not_directory(self):
        with create_temp_project(self._base_structure()) as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "*.py", "path": "root.py"})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.INVALID_PARAM.value)

    def test_error_access_denied(self):
        with create_temp_project() as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "*.py", "path": str(project.root.parent)})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.ACCESS_DENIED.value)


if __name__ == "__main__":
    unittest.main()
