"""MultiEditTool 单元测试

遵循《通用工具响应协议 v1.0》规范，全面测试 MultiEdit 工具的各项功能。

运行方式：
    python -m pytest tests/test_multi_edit_tool.py -v
    python -m unittest tests.test_multi_edit_tool -v
"""

import unittest
import time
from pathlib import Path
from tools.builtin.edit_file_multi import MultiEditTool
from tools.base import ErrorCode
from tests.utils.protocol_validator import ProtocolValidator
from tests.utils.test_helpers import create_temp_project, parse_response


class TestMultiEditTool(unittest.TestCase):
    """MultiEditTool 单元测试套件

    覆盖场景：
    1. Success（成功）：多处独立修改、倒序应用、删除操作、CRLF 处理
    2. Partial（部分成功）：dry_run 模式、diff 截断
    3. Error（错误）：INVALID_PARAM、NOT_FOUND、CONFLICT、重叠检测
    4. 沙箱安全：路径遍历攻击防护
    """

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _validate_and_assert(self, response_str: str, expected_status: str = None) -> dict:
        """验证协议合规性并返回解析结果"""
        result = ProtocolValidator.validate(response_str, tool_type="edit")

        if not result.passed:
            error_msg = "\n" + "=" * 60 + "\n"
            error_msg += "协议验证失败\n"
            error_msg += "=" * 60 + "\n"
            for error in result.errors:
                error_msg += f"  {error}\n"
            if result.warnings:
                error_msg += "\n警告:\n"
                for warning in result.warnings:
                    error_msg += f"  {warning}\n"
            self.fail(error_msg)

        parsed = parse_response(response_str)
        if expected_status:
            self.assertEqual(parsed["status"], expected_status,
                           f"期望 status='{expected_status}'，实际 '{parsed['status']}'")
        return parsed

    def _get_file_stat(self, path: Path) -> tuple:
        """获取文件的 mtime_ms 和 size_bytes"""
        stat = path.stat()
        return stat.st_mtime_ns // 1_000_000, stat.st_size

    # ========================================================================
    # Success 场景测试
    # ========================================================================

    def test_success_multiple_independent_edits(self):
        """Success: 多处独立修改成功"""
        with create_temp_project() as project:
            content = "def foo():\n    return 1\n\ndef bar():\n    return 2\n\ndef baz():\n    return 3\n"
            project.create_file("test.py", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.py"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.py",
                "edits": [
                    {"old_string": "return 1", "new_string": "return 10"},
                    {"old_string": "return 2", "new_string": "return 20"},
                    {"old_string": "return 3", "new_string": "return 30"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证替换次数
            self.assertEqual(parsed["data"]["replacements"], 3)
            self.assertTrue(parsed["data"]["applied"])

            # 验证文件实际被修改
            actual_content = project.path("test.py").read_text(encoding="utf-8")
            self.assertIn("return 10", actual_content)
            self.assertIn("return 20", actual_content)
            self.assertIn("return 30", actual_content)
            self.assertNotIn("return 1\n", actual_content)

    def test_success_reverse_order_application(self):
        """Success: 倒序应用替换（验证索引偏移问题）"""
        with create_temp_project() as project:
            content = "AAA\nBBB\nCCC\nDDD\n"
            project.create_file("test.txt", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "AAA", "new_string": "111"},  # 位置 0-3
                    {"old_string": "CCC", "new_string": "333"},  # 位置 8-11
                    {"old_string": "BBB", "new_string": "222"},  # 位置 4-7
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证所有替换都正确应用
            actual_content = project.path("test.txt").read_text(encoding="utf-8")
            self.assertEqual(actual_content, "111\n222\n333\nDDD\n")

    def test_success_delete_operations(self):
        """Success: 删除操作（new_string 为空）"""
        with create_temp_project() as project:
            content = "line1\nline2\nline3\nline4\n"
            project.create_file("test.txt", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "line2\n", "new_string": ""},
                    {"old_string": "line4\n", "new_string": ""},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            actual_content = project.path("test.txt").read_text(encoding="utf-8")
            self.assertEqual(actual_content, "line1\nline3\n")

    def test_success_multiline_edits(self):
        """Success: 多行替换"""
        with create_temp_project() as project:
            content = "class Foo:\n    def method1(self):\n        pass\n\n    def method2(self):\n        pass\n"
            project.create_file("code.py", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("code.py"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "code.py",
                "edits": [
                    {
                        "old_string": "def method1(self):\n        pass",
                        "new_string": "def method1(self):\n        return 1"
                    },
                    {
                        "old_string": "def method2(self):\n        pass",
                        "new_string": "def method2(self):\n        return 2"
                    },
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            actual_content = project.path("code.py").read_text(encoding="utf-8")
            self.assertIn("return 1", actual_content)
            self.assertIn("return 2", actual_content)

    def test_success_crlf_preserved(self):
        """Success: CRLF 换行符被保留"""
        with create_temp_project() as project:
            content = "Line 1\r\nLine 2\r\nLine 3\r\n"
            project.create_file("crlf.txt", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("crlf.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "crlf.txt",
                "edits": [
                    {"old_string": "Line 2", "new_string": "Line Two"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证换行符仍然是 CRLF
            actual_content = project.path("crlf.txt").read_bytes().decode("utf-8")
            self.assertTrue(actual_content.startswith("Line 1\r\n"))
            self.assertTrue(actual_content.endswith("Line 3\r\n"))

    def test_success_diff_contains_all_changes(self):
        """Success: diff 包含所有修改"""
        with create_temp_project() as project:
            content = "foo\nbar\nbaz\n"
            project.create_file("test.txt", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "foo", "new_string": "FOO"},
                    {"old_string": "bar", "new_string": "BAR"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            diff_preview = parsed["data"]["diff_preview"]
            self.assertIn("-foo", diff_preview)
            self.assertIn("+FOO", diff_preview)
            self.assertIn("-bar", diff_preview)
            self.assertIn("+BAR", diff_preview)

    def test_success_unicode_edits(self):
        """Success: Unicode 字符替换"""
        with create_temp_project() as project:
            content = "Hello 世界\nGoodbye 世界\n"
            project.create_file("unicode.txt", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("unicode.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "unicode.txt",
                "edits": [
                    {"old_string": "Hello 世界", "new_string": "Hi World"},
                    {"old_string": "Goodbye 世界", "new_string": "Bye World"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            actual_content = project.path("unicode.txt").read_text(encoding="utf-8")
            self.assertEqual(actual_content, "Hi World\nBye World\n")

    def test_success_single_edit(self):
        """Success: 单个编辑（边界情况）"""
        with create_temp_project() as project:
            content = "Original\n"
            project.create_file("test.txt", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "Original", "new_string": "Modified"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            self.assertEqual(parsed["data"]["replacements"], 1)

    # ========================================================================
    # Partial 场景测试
    # ========================================================================

    def test_partial_dry_run_mode(self):
        """Partial: dry_run 模式不实际写入"""
        with create_temp_project() as project:
            original_content = "Line 1\nLine 2\nLine 3\n"
            project.create_file("test.txt", original_content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "Line 1", "new_string": "First"},
                    {"old_string": "Line 3", "new_string": "Third"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
                "dry_run": True,
            })

            parsed = self._validate_and_assert(response, "partial")

            # 验证未实际写入
            self.assertFalse(parsed["data"]["applied"])
            self.assertTrue(parsed["data"]["dry_run"])
            actual_content = project.path("test.txt").read_text(encoding="utf-8")
            self.assertEqual(actual_content, original_content)

    def test_partial_dry_run_text_contains_notice(self):
        """Partial: dry_run 模式 text 包含提示"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "content", "new_string": "modified"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
                "dry_run": True,
            })

            parsed = self._validate_and_assert(response, "partial")

            text = parsed["text"]
            self.assertIn("Dry Run", text)

    # ========================================================================
    # Error 场景测试 - INVALID_PARAM
    # ========================================================================

    def test_error_invalid_param_missing_path(self):
        """Error: INVALID_PARAM - 缺少 path 参数"""
        with create_temp_project() as project:
            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "edits": [{"old_string": "test", "new_string": "modified"}],
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_error_invalid_param_empty_path(self):
        """Error: INVALID_PARAM - path 为空字符串"""
        with create_temp_project() as project:
            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "",
                "edits": [{"old_string": "test", "new_string": "modified"}],
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_error_invalid_param_missing_edits(self):
        """Error: INVALID_PARAM - 缺少 edits 参数"""
        with create_temp_project() as project:
            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("edits", parsed["error"]["message"])

    def test_error_invalid_param_edits_not_array(self):
        """Error: INVALID_PARAM - edits 不是数组"""
        with create_temp_project() as project:
            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": "not an array",
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_error_invalid_param_edits_empty(self):
        """Error: INVALID_PARAM - edits 为空数组"""
        with create_temp_project() as project:
            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [],
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_error_invalid_param_edit_not_object(self):
        """Error: INVALID_PARAM - edit 不是对象"""
        with create_temp_project() as project:
            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": ["string", "another"],  # 不是对象
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("index 0", parsed["error"]["message"])

    def test_error_invalid_param_edit_missing_old_string(self):
        """Error: INVALID_PARAM - edit 缺少 old_string"""
        with create_temp_project() as project:
            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [{"new_string": "modified"}],  # 缺少 old_string
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_error_invalid_param_edit_empty_old_string(self):
        """Error: INVALID_PARAM - old_string 为空"""
        with create_temp_project() as project:
            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [{"old_string": "", "new_string": "modified"}],
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("cannot be empty", parsed["error"]["message"])

    def test_error_invalid_param_edit_missing_new_string(self):
        """Error: INVALID_PARAM - edit 缺少 new_string"""
        with create_temp_project() as project:
            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [{"old_string": "test"}],  # 缺少 new_string
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_error_invalid_param_wrong_type_dry_run(self):
        """Error: INVALID_PARAM - dry_run 类型错误"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [{"old_string": "content", "new_string": "modified"}],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
                "dry_run": "true",  # 字符串而非布尔值
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_error_invalid_param_absolute_path(self):
        """Error: INVALID_PARAM - 绝对路径被拒绝"""
        with create_temp_project() as project:
            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "/etc/passwd",
                "edits": [{"old_string": "test", "new_string": "modified"}],
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("Absolute path", parsed["error"]["message"])

    # ========================================================================
    # Error 场景测试 - NOT_FOUND / IS_DIRECTORY
    # ========================================================================

    def test_error_not_found_file_does_not_exist(self):
        """Error: NOT_FOUND - 文件不存在"""
        with create_temp_project() as project:
            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "nonexistent.txt",
                "edits": [{"old_string": "test", "new_string": "modified"}],
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "NOT_FOUND")
            self.assertIn("does not exist", parsed["error"]["message"])

    def test_error_is_directory_target_is_directory(self):
        """Error: IS_DIRECTORY - 目标是目录"""
        with create_temp_project() as project:
            project.create_dir("mydir")

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "mydir",
                "edits": [{"old_string": "test", "new_string": "modified"}],
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "IS_DIRECTORY")

    # ========================================================================
    # Error 场景测试 - CONFLICT（乐观锁）
    # ========================================================================

    def test_error_conflict_no_read_before_edit(self):
        """Error: INVALID_PARAM - 未先 Read 就 Edit"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [{"old_string": "content", "new_string": "modified"}],
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("Read the file before", parsed["error"]["message"])

    def test_error_conflict_only_one_param_provided(self):
        """Error: INVALID_PARAM - 只提供 expected 参数中的一个"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [{"old_string": "content", "new_string": "modified"}],
                "expected_mtime_ms": 12345,  # 只提供 mtime
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_error_conflict_mtime_mismatch(self):
        """Error: CONFLICT - mtime 不匹配"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")
            time.sleep(0.01)
            project.create_file("test.txt", "modified by user\n")
            current_mtime_ms, current_size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [{"old_string": "modified", "new_string": "agent"}],
                "expected_mtime_ms": current_mtime_ms - 1000,
                "expected_size_bytes": current_size_bytes,
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "CONFLICT")

    # ========================================================================
    # Error 场景测试 - old_string 匹配问题
    # ========================================================================

    def test_error_invalid_param_old_string_not_found(self):
        """Error: INVALID_PARAM - old_string 未匹配"""
        with create_temp_project() as project:
            project.create_file("test.txt", "Hello World\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "Goodbye", "new_string": "Farewell"},  # 不存在
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("not found", parsed["error"]["message"])
            self.assertEqual(parsed["data"].get("failed_index"), 0)

    def test_error_invalid_param_old_string_multiple_matches(self):
        """Error: INVALID_PARAM - old_string 匹配多次"""
        with create_temp_project() as project:
            project.create_file("test.txt", "line 1\nline 2\nline 1\nline 3\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "line 1", "new_string": "LINE ONE"},  # 匹配两次
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("unique", parsed["error"]["message"].lower())
            self.assertEqual(parsed["data"].get("failed_index"), 0)

    def test_error_invalid_param_second_edit_not_found(self):
        """Error: INVALID_PARAM - 第二个 edit 未匹配"""
        with create_temp_project() as project:
            project.create_file("test.txt", "AAA\nBBB\nCCC\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "AAA", "new_string": "111"},  # 存在
                    {"old_string": "DDD", "new_string": "444"},  # 不存在
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertEqual(parsed["data"].get("failed_index"), 1)

    # ========================================================================
    # Error 场景测试 - 区间重叠
    # ========================================================================

    def test_error_invalid_param_overlapping_edits(self):
        """Error: INVALID_PARAM - 编辑区间重叠"""
        with create_temp_project() as project:
            project.create_file("test.txt", "AAAAABBBBBCCCC\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "AAAAB", "new_string": "11111"},  # 位置 0-5
                    {"old_string": "ABBBB", "new_string": "22222"},  # 位置 1-6，与前一个重叠
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("overlapping", parsed["error"]["message"])

    # ========================================================================
    # Error 场景测试 - BINARY_FILE
    # ========================================================================

    def test_error_binary_file(self):
        """Error: BINARY_FILE - 检测到二进制文件"""
        with create_temp_project() as project:
            binary_content = b"Hello\x00World\x00Binary"
            project.path("binary.bin").write_bytes(binary_content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("binary.bin"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "binary.bin",
                "edits": [{"old_string": "Hello", "new_string": "Hi"}],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "BINARY_FILE")

    # ========================================================================
    # 沙箱安全测试
    # ========================================================================

    def test_error_access_denied_path_traversal(self):
        """Error: ACCESS_DENIED - 路径遍历攻击"""
        with create_temp_project() as project:
            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "../../../etc/passwd",
                "edits": [{"old_string": "test", "new_string": "modified"}],
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertIn(parsed["error"]["code"], ["ACCESS_DENIED", "INVALID_PARAM"])

    # ========================================================================
    # 协议合规性测试
    # ========================================================================

    def test_protocol_success_response_structure(self):
        """协议合规性: success 响应结构正确"""
        with create_temp_project() as project:
            project.create_file("test.txt", "Hello World\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [{"old_string": "Hello", "new_string": "Hi"}],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = parse_response(response)

            # 验证顶层字段
            self.assertEqual(parsed["status"], "success")
            self.assertIn("data", parsed)
            self.assertIn("text", parsed)
            self.assertIn("stats", parsed)
            self.assertIn("context", parsed)
            self.assertNotIn("error", parsed)

            # 验证 data 字段
            self.assertIn("applied", parsed["data"])
            self.assertIn("diff_preview", parsed["data"])
            self.assertIn("diff_truncated", parsed["data"])
            self.assertIn("replacements", parsed["data"])
            self.assertIn("failed_index", parsed["data"])
            self.assertIsNone(parsed["data"]["failed_index"])

    def test_protocol_error_response_structure(self):
        """协议合规性: error 响应结构正确"""
        with create_temp_project() as project:
            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "nonexistent.txt",
                "edits": [{"old_string": "test", "new_string": "modified"}],
            })

            parsed = parse_response(response)

            self.assertEqual(parsed["status"], "error")
            self.assertIn("error", parsed)
            self.assertIn("code", parsed["error"])
            self.assertIn("message", parsed["error"])
            self.assertIn("data", parsed)

    def test_protocol_partial_response_structure(self):
        """协议合规性: partial 响应结构正确"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [{"old_string": "content", "new_string": "modified"}],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
                "dry_run": True,
            })

            parsed = parse_response(response)

            self.assertEqual(parsed["status"], "partial")
            self.assertTrue(parsed["data"]["dry_run"])

    # ========================================================================
    # failed_index 测试
    # ========================================================================

    def test_failed_index_in_data_on_match_error(self):
        """验证: old_string 未匹配时 failed_index 在 data 中"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "nonexistent", "new_string": "replacement"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = parse_response(response)

            self.assertEqual(parsed["status"], "error")
            self.assertEqual(parsed["data"]["failed_index"], 0)

    def test_failed_index_in_data_on_duplicate_match(self):
        """验证: 多次匹配时 failed_index 在 data 中"""
        with create_temp_project() as project:
            project.create_file("test.txt", "AAA\nBBB\nAAA\nCCC\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "AAA", "new_string": "111"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = parse_response(response)

            self.assertEqual(parsed["status"], "error")
            self.assertEqual(parsed["data"]["failed_index"], 0)

    def test_failed_index_in_data_on_overlap(self):
        """验证: 区间重叠时 failed_index 在 data 中"""
        with create_temp_project() as project:
            project.create_file("test.txt", "AAAAABBBBB\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "AAAAB", "new_string": "11111"},
                    {"old_string": "ABBBB", "new_string": "22222"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = parse_response(response)

            self.assertEqual(parsed["status"], "error")
            # 重叠时应该标记第二个 edit 的索引
            self.assertIn(parsed["data"]["failed_index"], [0, 1])

    # ========================================================================
    # 边界条件测试
    # ========================================================================

    def test_boundary_replace_entire_file(self):
        """边界: 替换整个文件内容"""
        with create_temp_project() as project:
            project.create_file("test.txt", "Old Content\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "Old Content\n", "new_string": "New Content\n"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            actual_content = project.path("test.txt").read_text(encoding="utf-8")
            self.assertEqual(actual_content, "New Content\n")

    def test_boundary_empty_file(self):
        """边界: 尝试编辑空文件"""
        with create_temp_project() as project:
            project.create_file("empty.txt", "")
            mtime_ms, size_bytes = self._get_file_stat(project.path("empty.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "empty.txt",
                "edits": [
                    {"old_string": "anything", "new_string": "replacement"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_boundary_single_character_edits(self):
        """边界: 单字符多处编辑"""
        with create_temp_project() as project:
            project.create_file("test.txt", "a\nb\nc\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "a", "new_string": "x"},
                    {"old_string": "b", "new_string": "y"},
                    {"old_string": "c", "new_string": "z"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            actual_content = project.path("test.txt").read_text(encoding="utf-8")
            self.assertEqual(actual_content, "x\ny\nz\n")

    def test_boundary_whitespace_edits(self):
        """边界: 空白字符替换"""
        with create_temp_project() as project:
            project.create_file("test.txt", "line1\n   \nline2\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "   \n", "new_string": "\n"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            actual_content = project.path("test.txt").read_text(encoding="utf-8")
            self.assertEqual(actual_content, "line1\n\nline2\n")

    # ========================================================================
    # stats 字段验证
    # ========================================================================

    def test_stats_fields_present(self):
        """验证: stats 字段包含正确的统计信息"""
        with create_temp_project() as project:
            project.create_file("test.txt", "Line 1\nLine 2\nLine 3\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = MultiEditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "edits": [
                    {"old_string": "Line 2", "new_string": "Line Two"},
                ],
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            stats = parsed["stats"]
            self.assertIn("time_ms", stats)
            self.assertIn("bytes_written", stats)
            self.assertIn("original_size", stats)
            self.assertIn("new_size", stats)
            self.assertIn("lines_added", stats)
            self.assertIn("lines_removed", stats)

            # 验证统计值的合理性
            self.assertGreaterEqual(stats["time_ms"], 0)
            self.assertGreater(stats["bytes_written"], 0)


if __name__ == "__main__":
    unittest.main()
