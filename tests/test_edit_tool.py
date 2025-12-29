"""EditTool 单元测试

遵循《通用工具响应协议 v1.0》规范，全面测试 Edit 工具的各项功能。

运行方式：
    python -m pytest tests/test_edit_tool.py -v
    python -m unittest tests.test_edit_tool -v
"""

import unittest
import time
from pathlib import Path
from tools.builtin.edit_file import EditTool
from tools.base import ErrorCode
from tests.utils.protocol_validator import ProtocolValidator
from tests.utils.test_helpers import create_temp_project, parse_response


class TestEditTool(unittest.TestCase):
    """EditTool 单元测试套件

    覆盖场景：
    1. Success（成功）：唯一锚点替换、CRLF/LF 自动处理、删除操作
    2. Partial（部分成功）：dry_run 模式、diff 截断
    3. Error（错误）：INVALID_PARAM、NOT_FOUND、IS_DIRECTORY、CONFLICT、BINARY_FILE
    4. 沙箱安全：路径遍历攻击防护、绝对路径拒绝
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

    def test_success_simple_replacement(self):
        """Success: 简单文本替换"""
        with create_temp_project() as project:
            project.create_file("test.txt", "Hello World\nGoodbye World\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "Hello World",
                "new_string": "Hi World",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证 data 字段
            self.assertTrue(parsed["data"]["applied"])
            self.assertEqual(parsed["data"]["replacements"], 1)
            self.assertFalse(parsed["data"]["diff_truncated"])

            # 验证文件实际被修改
            actual_content = project.path("test.txt").read_text(encoding="utf-8")
            self.assertEqual(actual_content, "Hi World\nGoodbye World\n")

    def test_success_multiline_replacement(self):
        """Success: 多行文本替换"""
        with create_temp_project() as project:
            content = "def foo():\n    return 'old'\n\ndef bar():\n    pass\n"
            project.create_file("code.py", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("code.py"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "code.py",
                "old_string": "def foo():\n    return 'old'",
                "new_string": "def foo():\n    return 'new'",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证替换成功
            actual_content = project.path("code.py").read_text(encoding="utf-8")
            self.assertIn("return 'new'", actual_content)
            self.assertNotIn("return 'old'", actual_content)

    def test_success_delete_content(self):
        """Success: 删除内容（new_string 为空）"""
        with create_temp_project() as project:
            project.create_file("test.txt", "Line 1\nLine 2\nLine 3\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "Line 2\n",
                "new_string": "",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证删除成功
            actual_content = project.path("test.txt").read_text(encoding="utf-8")
            self.assertEqual(actual_content, "Line 1\nLine 3\n")

    def test_success_with_context(self):
        """Success: 带上下文的替换（更唯一）"""
        with create_temp_project() as project:
            content = "class Foo:\n    def method(self):\n        return 'old'\n\nclass Bar:\n    pass\n"
            project.create_file("code.py", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("code.py"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "code.py",
                "old_string": "class Foo:\n    def method(self):\n        return 'old'",
                "new_string": "class Foo:\n    def method(self):\n        return 'new'",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证只有 Foo 类的方法被修改
            actual_content = project.path("code.py").read_text(encoding="utf-8")
            self.assertIn("class Foo:\n    def method(self):\n        return 'new'", actual_content)

    def test_success_crlf_preserved(self):
        """Success: CRLF 换行符被保留"""
        with create_temp_project() as project:
            # 使用 CRLF 换行符
            content = "Line 1\r\nLine 2\r\nLine 3\r\n"
            project.create_file("crlf.txt", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("crlf.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "crlf.txt",
                "old_string": "Line 2",
                "new_string": "Line Two",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证换行符仍然是 CRLF
            actual_content = project.path("crlf.txt").read_bytes().decode("utf-8")
            self.assertTrue(actual_content.startswith("Line 1\r\n"))
            self.assertTrue(actual_content.endswith("Line 3\r\n"))
            self.assertIn("Line Two", actual_content)

    def test_success_mixed_line_endings(self):
        """Success: 混合换行符的处理（归一化为 LF 或保留主导格式）"""
        with create_temp_project() as project:
            # 混合但 LF 占多数
            content = "Line 1\nLine 2\r\nLine 3\nLine 4\n"
            project.create_file("mixed.txt", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("mixed.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "mixed.txt",
                "old_string": "Line 3",
                "new_string": "Line Three",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证替换成功
            actual_content = project.path("mixed.txt").read_text(encoding="utf-8")
            self.assertIn("Line Three", actual_content)

    def test_success_with_special_characters(self):
        """Success: 包含特殊字符的替换"""
        with create_temp_project() as project:
            content = "var x = 'hello'; // comment\nvar y = \"world\";\n"
            project.create_file("code.js", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("code.js"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "code.js",
                "old_string": "'hello'",
                "new_string": "'hi'",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            actual_content = project.path("code.js").read_text(encoding="utf-8")
            self.assertIn("'hi'", actual_content)
            self.assertNotIn("'hello'", actual_content)

    def test_success_unicode_replacement(self):
        """Success: Unicode 字符替换"""
        with create_temp_project() as project:
            content = "Hello 世界\nGoodbye 世界\n"
            project.create_file("unicode.txt", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("unicode.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "unicode.txt",
                "old_string": "世界",
                "new_string": "World",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            actual_content = project.path("unicode.txt").read_text(encoding="utf-8")
            self.assertIn("Hello World", actual_content)

    def test_success_diff_contains_changes(self):
        """Success: diff_preview 包含变化"""
        with create_temp_project() as project:
            project.create_file("test.py", "def foo():\n    return 1\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.py"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.py",
                "old_string": "return 1",
                "new_string": "return 2",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证 diff 包含变化
            diff_preview = parsed["data"]["diff_preview"]
            self.assertIn("-return 1", diff_preview)
            self.assertIn("+return 2", diff_preview)

    def test_success_replacement_with_tabs(self):
        """Success: 包含 tab 字符的替换"""
        with create_temp_project() as project:
            content = "def foo():\n\treturn 'old'\n"
            project.create_file("tabs.py", content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("tabs.py"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "tabs.py",
                "old_string": "\treturn 'old'",
                "new_string": "\treturn 'new'",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            actual_content = project.path("tabs.py").read_text(encoding="utf-8")
            self.assertIn("\treturn 'new'", actual_content)

    # ========================================================================
    # Partial 场景测试
    # ========================================================================

    def test_partial_dry_run_mode(self):
        """Partial: dry_run 模式不实际写入"""
        with create_temp_project() as project:
            original_content = "Original content\n"
            project.create_file("test.txt", original_content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "Original",
                "new_string": "Modified",
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

            # 验证 diff 仍然被计算
            diff_preview = parsed["data"]["diff_preview"]
            self.assertIn("-Original", diff_preview)
            self.assertIn("+Modified", diff_preview)

    def test_partial_dry_run_text_contains_notice(self):
        """Partial: dry_run 模式 text 包含提示"""
        with create_temp_project() as project:
            project.create_file("test.txt", "Hello World\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "Hello",
                "new_string": "Hi",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
                "dry_run": True,
            })

            parsed = self._validate_and_assert(response, "partial")

            # 验证 text 包含 dry_run 提示
            text = parsed["text"]
            self.assertIn("Dry Run", text)

    # ========================================================================
    # Error 场景测试 - INVALID_PARAM
    # ========================================================================

    def test_error_invalid_param_missing_path(self):
        """Error: INVALID_PARAM - 缺少 path 参数"""
        with create_temp_project() as project:
            tool = EditTool(project_root=project.root)
            response = tool.run({
                "old_string": "test",
                "new_string": "modified",
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("path", parsed["error"]["message"].lower())

    def test_error_invalid_param_empty_path(self):
        """Error: INVALID_PARAM - path 为空字符串"""
        with create_temp_project() as project:
            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "",
                "old_string": "test",
                "new_string": "modified",
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_error_invalid_param_missing_old_string(self):
        """Error: INVALID_PARAM - 缺少 old_string 参数"""
        with create_temp_project() as project:
            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "new_string": "modified",
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("old_string", parsed["error"]["message"])

    def test_error_invalid_param_empty_old_string(self):
        """Error: INVALID_PARAM - old_string 为空字符串"""
        with create_temp_project() as project:
            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "",
                "new_string": "modified",
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("cannot be empty", parsed["error"]["message"])

    def test_error_invalid_param_missing_new_string(self):
        """Error: INVALID_PARAM - 缺少 new_string 参数"""
        with create_temp_project() as project:
            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "test",
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("new_string", parsed["error"]["message"])

    def test_error_invalid_param_wrong_type_dry_run(self):
        """Error: INVALID_PARAM - dry_run 类型错误"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "content",
                "new_string": "modified",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
                "dry_run": "true",  # 字符串而非布尔值
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("dry_run", parsed["error"]["message"])

    def test_error_invalid_param_absolute_path(self):
        """Error: INVALID_PARAM - 绝对路径被拒绝"""
        with create_temp_project() as project:
            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "/etc/passwd",  # 绝对路径
                "old_string": "test",
                "new_string": "modified",
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
            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "nonexistent.txt",
                "old_string": "test",
                "new_string": "modified",
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "NOT_FOUND")
            self.assertIn("does not exist", parsed["error"]["message"])

    def test_error_is_directory_target_is_directory(self):
        """Error: IS_DIRECTORY - 目标是目录"""
        with create_temp_project() as project:
            project.create_dir("mydir")

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "mydir",
                "old_string": "test",
                "new_string": "modified",
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "IS_DIRECTORY")
            self.assertIn("directory", parsed["error"]["message"])

    # ========================================================================
    # Error 场景测试 - CONFLICT（乐观锁）
    # ========================================================================

    def test_error_conflict_no_read_before_edit(self):
        """Error: CONFLICT - 未先 Read 就 Edit（未提供 expected 值）"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "content",
                "new_string": "modified",
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("Read the file before", parsed["error"]["message"])

    def test_error_conflict_only_one_param_provided(self):
        """Error: CONFLICT - 只提供 expected 参数中的一个"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "content",
                "new_string": "modified",
                "expected_mtime_ms": 12345,  # 只提供 mtime
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_error_conflict_mtime_mismatch(self):
        """Error: CONFLICT - mtime 不匹配"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")
            # 稍等一下让时间变化
            time.sleep(0.01)
            # 模拟文件被修改
            project.create_file("test.txt", "modified by user\n")
            current_mtime_ms, current_size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "content",
                "new_string": "agent change",
                "expected_mtime_ms": current_mtime_ms - 1000,  # 错误的 mtime
                "expected_size_bytes": current_size_bytes,
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "CONFLICT")
            self.assertIn("modified since you read", parsed["error"]["message"])

    def test_error_conflict_size_mismatch(self):
        """Error: CONFLICT - size 不匹配"""
        with create_temp_project() as project:
            project.create_file("test.txt", "original content\n")
            current_mtime_ms, current_size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "original",
                "new_string": "modified",
                "expected_mtime_ms": current_mtime_ms,
                "expected_size_bytes": current_size_bytes + 100,  # 错误的 size
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "CONFLICT")

    # ========================================================================
    # Error 场景测试 - old_string 未匹配或多次匹配
    # ========================================================================

    def test_error_invalid_param_old_string_not_found(self):
        """Error: INVALID_PARAM - old_string 在文件中未找到"""
        with create_temp_project() as project:
            project.create_file("test.txt", "Hello World\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "Goodbye",  # 不存在的文本
                "new_string": "Farewell",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("not found", parsed["error"]["message"])

    def test_error_invalid_param_old_string_multiple_matches(self):
        """Error: INVALID_PARAM - old_string 匹配多次（不唯一）"""
        with create_temp_project() as project:
            project.create_file("test.txt", "line 1\nline 2\nline 1\nline 3\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "line 1",  # 出现两次
                "new_string": "line one",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("unique", parsed["error"]["message"].lower())

    # ========================================================================
    # Error 场景测试 - BINARY_FILE
    # ========================================================================

    def test_error_binary_file(self):
        """Error: BINARY_FILE - 检测到二进制文件"""
        with create_temp_project() as project:
            # 创建包含 null byte 的二进制文件
            binary_content = b"Hello\x00World\x00Binary"
            project.path("binary.bin").write_bytes(binary_content)
            mtime_ms, size_bytes = self._get_file_stat(project.path("binary.bin"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "binary.bin",
                "old_string": "Hello",
                "new_string": "Hi",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "BINARY_FILE")
            self.assertIn("binary", parsed["error"]["message"])

    # ========================================================================
    # Error 场景测试 - 沙箱安全
    # ========================================================================

    def test_error_access_denied_path_traversal(self):
        """Error: ACCESS_DENIED - 路径遍历攻击"""
        with create_temp_project() as project:
            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "../../../etc/passwd",  # 尝试路径遍历
                "old_string": "test",
                "new_string": "modified",
            })

            parsed = self._validate_and_assert(response, "error")

            # 根据实现，可能是 ACCESS_DENIED 或 INVALID_PARAM
            self.assertIn(parsed["error"]["code"], ["ACCESS_DENIED", "INVALID_PARAM"])

    def test_error_access_denied_outside_root(self):
        """Error: ACCESS_DENIED - 路径在项目根目录外"""
        with create_temp_project() as project:
            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "/tmp/outside_file.txt",  # 项目外的文件
                "old_string": "test",
                "new_string": "modified",
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

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "Hello",
                "new_string": "Hi",
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

            # 验证 stats 字段
            self.assertIn("time_ms", parsed["stats"])
            self.assertIn("bytes_written", parsed["stats"])

            # 验证 context 字段
            self.assertIn("cwd", parsed["context"])
            self.assertIn("params_input", parsed["context"])

    def test_protocol_error_response_structure(self):
        """协议合规性: error 响应结构正确"""
        with create_temp_project() as project:
            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "nonexistent.txt",
                "old_string": "test",
                "new_string": "modified",
            })

            parsed = parse_response(response)

            # 验证 error 响应结构
            self.assertEqual(parsed["status"], "error")
            self.assertIn("error", parsed)
            self.assertIn("code", parsed["error"])
            self.assertIn("message", parsed["error"])
            self.assertIn("data", parsed)
            self.assertEqual(parsed["data"], {})  # error 时 data 为空对象

    def test_protocol_partial_response_structure(self):
        """协议合规性: partial 响应结构正确"""
        with create_temp_project() as project:
            project.create_file("test.txt", "Hello World\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "Hello",
                "new_string": "Hi",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
                "dry_run": True,
            })

            parsed = parse_response(response)

            # 验证 partial 响应结构
            self.assertEqual(parsed["status"], "partial")
            self.assertIn("data", parsed)
            self.assertIn("dry_run", parsed["data"])
            self.assertNotIn("error", parsed)

    # ========================================================================
    # 边界条件测试
    # ========================================================================

    def test_boundary_replace_entire_file(self):
        """边界: 替换整个文件内容"""
        with create_temp_project() as project:
            project.create_file("test.txt", "Old Content\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "Old Content\n",
                "new_string": "New Content\n",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            actual_content = project.path("test.txt").read_text(encoding="utf-8")
            self.assertEqual(actual_content, "New Content\n")

    def test_boundary_replace_at_start(self):
        """边界: 替换文件开头的文本"""
        with create_temp_project() as project:
            project.create_file("test.txt", "Start Middle End\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "Start",
                "new_string": "Beginning",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            actual_content = project.path("test.txt").read_text(encoding="utf-8")
            self.assertEqual(actual_content, "Beginning Middle End\n")

    def test_boundary_replace_at_end(self):
        """边界: 替换文件末尾的文本"""
        with create_temp_project() as project:
            project.create_file("test.txt", "Start Middle End\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "End",
                "new_string": "Finish",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            actual_content = project.path("test.txt").read_text(encoding="utf-8")
            self.assertEqual(actual_content, "Start Middle Finish\n")

    def test_boundary_empty_file(self):
        """边界: 尝试编辑空文件（old_string 应该找不到）"""
        with create_temp_project() as project:
            project.create_file("empty.txt", "")
            mtime_ms, size_bytes = self._get_file_stat(project.path("empty.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "empty.txt",
                "old_string": "anything",
                "new_string": "replacement",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_boundary_single_character_replacement(self):
        """边界: 单字符替换"""
        with create_temp_project() as project:
            project.create_file("test.txt", "a\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "a",
                "new_string": "b",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            actual_content = project.path("test.txt").read_text(encoding="utf-8")
            self.assertEqual(actual_content, "b\n")

    def test_boundary_whitespace_only_replacement(self):
        """边界: 纯空白字符替换"""
        with create_temp_project() as project:
            project.create_file("test.txt", "line1\n   \nline2\n")
            mtime_ms, size_bytes = self._get_file_stat(project.path("test.txt"))

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "   \n",
                "new_string": "\n",
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

            tool = EditTool(project_root=project.root)
            response = tool.run({
                "path": "test.txt",
                "old_string": "Line 2",
                "new_string": "Line Two",
                "expected_mtime_ms": mtime_ms,
                "expected_size_bytes": size_bytes,
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证 stats 字段
            stats = parsed["stats"]
            self.assertIn("time_ms", stats)
            self.assertIn("bytes_written", stats)
            self.assertIn("original_size", stats)
            self.assertIn("new_size", stats)
            self.assertIn("lines_added", stats)
            self.assertIn("lines_removed", stats)

            # 验证统计值的合理性
            self.assertGreater(stats["time_ms"], 0)
            self.assertGreater(stats["bytes_written"], 0)
            self.assertGreater(stats["lines_added"], 0)
            self.assertGreater(stats["lines_removed"], 0)


if __name__ == "__main__":
    unittest.main()
