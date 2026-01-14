"""GrepTool tests."""

import os
import unittest
from unittest.mock import patch

from tools.builtin.search_code import GrepTool
from tools.base import ErrorCode
from tests.utils.protocol_validator import ProtocolValidator
from tests.utils.test_helpers import create_temp_project, parse_response


class TestGrepTool(unittest.TestCase):
    def _validate(self, response_str: str, expected_status: str = None) -> dict:
        result = ProtocolValidator.validate(response_str, tool_type="grep")
        if not result.passed:
            error_msg = "\n" + "=" * 60 + "\n"
            error_msg += "Grep protocol validation failed\n"
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

    def test_success_case_insensitive_default(self):
        with create_temp_project({"a.txt": "Hello world"}) as project:
            tool = GrepTool(project_root=project.root)
            with patch("tools.builtin.search_code.shutil.which", return_value=None):
                response = tool.run({"pattern": "hello", "include": "*.txt"})
            parsed = self._validate(response, "partial")
            self.assertGreaterEqual(len(parsed["data"]["matches"]), 1)
            self.assertTrue(parsed["data"].get("fallback_used"))

    def test_case_sensitive(self):
        with create_temp_project({"a.txt": "Hello world"}) as project:
            tool = GrepTool(project_root=project.root)
            with patch("tools.builtin.search_code.shutil.which", return_value=None):
                response = tool.run({"pattern": "hello", "include": "*.txt", "case_sensitive": True})
            parsed = self._validate(response, "partial")
            self.assertEqual(parsed["data"]["matches"], [])

    def test_include_glob_filter(self):
        structure = {"a.py": "class A:", "b.txt": "class B:"}
        with create_temp_project(structure) as project:
            tool = GrepTool(project_root=project.root)
            with patch("tools.builtin.search_code.shutil.which", return_value=None):
                response = tool.run({"pattern": "class", "include": "*.py"})
            parsed = self._validate(response, "partial")
            files = {m["file"] for m in parsed["data"]["matches"]}
            self.assertIn("a.py", files)
            self.assertNotIn("b.txt", files)

    def test_regex_pattern(self):
        with create_temp_project() as project:
            tool = GrepTool(project_root=project.root)
            with patch("tools.builtin.search_code.shutil.which", return_value=None):
                response = tool.run({"pattern": r"class\s+MyClass", "include": "*.py"})
            parsed = self._validate(response, "partial")
            self.assertGreaterEqual(len(parsed["data"]["matches"]), 1)

    def test_sorted_by_mtime_desc(self):
        structure = {"old.txt": "needle", "new.txt": "needle"}
        with create_temp_project(structure) as project:
            old_path = project.path("old.txt")
            new_path = project.path("new.txt")
            os.utime(old_path, (1, 1))
            os.utime(new_path, None)
            tool = GrepTool(project_root=project.root)
            with patch("tools.builtin.search_code.shutil.which", return_value=None):
                response = tool.run({"pattern": "needle", "include": "*.txt"})
            parsed = self._validate(response, "partial")
            matches = parsed["data"]["matches"]
            if matches:
                self.assertEqual(matches[0]["file"], "new.txt")

    def test_partial_truncated_max_results(self):
        lines = "\n".join(["hit" for _ in range(10)])
        with create_temp_project({"many.txt": lines}) as project:
            tool = GrepTool(project_root=project.root)
            tool.MAX_RESULTS = 2
            with patch("tools.builtin.search_code.shutil.which", return_value=None):
                response = tool.run({"pattern": "hit", "include": "*.txt"})
            parsed = self._validate(response, "partial")
            self.assertTrue(parsed["data"].get("truncated"))
            self.assertEqual(len(parsed["data"]["matches"]), 2)

    def test_fallback_rg_not_found(self):
        with create_temp_project({"a.txt": "match"}) as project:
            tool = GrepTool(project_root=project.root)
            with patch("tools.builtin.search_code.shutil.which", return_value=None):
                response = tool.run({"pattern": "match", "include": "*.txt"})
            parsed = self._validate(response, "partial")
            self.assertTrue(parsed["data"].get("fallback_used"))
            self.assertEqual(parsed["data"].get("fallback_reason"), "rg_not_found")

    def test_fallback_rg_failed(self):
        with create_temp_project({"a.txt": "match"}) as project:
            tool = GrepTool(project_root=project.root)
            with patch("tools.builtin.search_code.shutil.which", return_value="rg"), \
                 patch.object(GrepTool, "_run_rg", side_effect=RuntimeError("rg failed")):
                response = tool.run({"pattern": "match", "include": "*.txt"})
            parsed = self._validate(response, "partial")
            self.assertTrue(parsed["data"].get("fallback_used"))
            self.assertEqual(parsed["data"].get("fallback_reason"), "rg_failed")

    def test_error_missing_pattern(self):
        with create_temp_project() as project:
            tool = GrepTool(project_root=project.root)
            response = tool.run({"pattern": ""})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.INVALID_PARAM.value)

    def test_error_invalid_regex(self):
        with create_temp_project({"a.txt": "text"}) as project:
            tool = GrepTool(project_root=project.root)
            with patch("tools.builtin.search_code.shutil.which", return_value=None):
                response = tool.run({"pattern": "(", "include": "*.txt"})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.INVALID_PARAM.value)

    def test_error_include_not_string(self):
        with create_temp_project() as project:
            tool = GrepTool(project_root=project.root)
            response = tool.run({"pattern": "x", "include": 123})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.INVALID_PARAM.value)

    def test_error_case_sensitive_not_bool(self):
        with create_temp_project() as project:
            tool = GrepTool(project_root=project.root)
            response = tool.run({"pattern": "x", "case_sensitive": "yes"})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.INVALID_PARAM.value)

    def test_error_not_found(self):
        with create_temp_project() as project:
            tool = GrepTool(project_root=project.root)
            response = tool.run({"pattern": "x", "path": "missing"})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.NOT_FOUND.value)

    def test_error_not_directory(self):
        with create_temp_project({"a.txt": "x"}) as project:
            tool = GrepTool(project_root=project.root)
            response = tool.run({"pattern": "x", "path": "a.txt"})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.INVALID_PARAM.value)

    def test_error_access_denied(self):
        with create_temp_project() as project:
            tool = GrepTool(project_root=project.root)
            response = tool.run({"pattern": "x", "path": str(project.root.parent)})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.ACCESS_DENIED.value)

    def test_error_timeout_no_results(self):
        with create_temp_project({"a.txt": "x"}) as project:
            tool = GrepTool(project_root=project.root)
            with patch("tools.builtin.search_code.shutil.which", return_value=None), \
                 patch.object(GrepTool, "_run_python_search", return_value=([], "timeout")):
                response = tool.run({"pattern": "nomatch", "include": "*.txt"})
            parsed = self._validate(response, "error")
            self.assertEqual(parsed["error"]["code"], ErrorCode.TIMEOUT.value)


if __name__ == "__main__":
    unittest.main()
