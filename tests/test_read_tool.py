"""ReadTool 单元测试

遵循《通用工具响应协议 v1.2.0》规范，全面测试 Read 工具的各项功能。

运行方式：
    python -m pytest tests/test_read_tool.py -v
    python -m unittest tests.test_read_tool -v
"""

import unittest
from pathlib import Path
from tools.builtin.read_file import ReadTool
from tools.base import ErrorCode
from tests.utils.protocol_validator import ProtocolValidator
from tests.utils.test_helpers import create_temp_project, parse_response


class TestReadTool(unittest.TestCase):
    """ReadTool 单元测试套件

    覆盖场景：
    1. Success（成功）：正常读取、空文件、分页读取
    2. Partial（部分成功）：内容截断、编码回退
    3. Error（错误）：NOT_FOUND、ACCESS_DENIED、INVALID_PARAM、IS_DIRECTORY、BINARY_FILE
    4. 沙箱安全：路径遍历攻击防护
    """

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _validate_and_assert(self, response_str: str, expected_status: str = None,
                            tool_type: str = "read") -> dict:
        """验证协议合规性并返回解析结果"""
        result = ProtocolValidator.validate(response_str, tool_type=tool_type)

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

    # ========================================================================
    # Success 场景测试
    # ========================================================================

    def test_success_read_normal_file(self):
        """Success: 正常读取完整文件"""
        with create_temp_project() as project:
            project.create_file("test.txt", "line1\nline2\nline3\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "test.txt"})

            parsed = self._validate_and_assert(response, "success")

            # 验证必需字段
            self.assertIn("content", parsed["data"])
            self.assertIn("stats", parsed)
            self.assertIn("context", parsed)
            self.assertIn("cwd", parsed["context"])
            self.assertIn("params_input", parsed["context"])
            self.assertIn("time_ms", parsed["stats"])

            # 验证内容格式（带行号）
            content = parsed["data"]["content"]
            self.assertIn("1 | line1", content)
            self.assertIn("2 | line2", content)
            self.assertIn("3 | line3", content)

            # 验证截断标志
            self.assertFalse(parsed["data"].get("truncated", False))

    def test_success_read_empty_file(self):
        """Success: 读取空文件"""
        with create_temp_project() as project:
            project.create_file("empty.txt", "")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "empty.txt"})

            parsed = self._validate_and_assert(response, "success")

            self.assertEqual(parsed["data"]["content"], "")
            self.assertEqual(parsed["stats"]["lines_read"], 0)
            self.assertFalse(parsed["data"].get("truncated", False))

    def test_success_read_with_line_numbers(self):
        """Success: 验证行号格式正确"""
        with create_temp_project() as project:
            content = "first line\nsecond line\nthird line\n"
            project.create_file("numbered.txt", content)

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "numbered.txt"})

            parsed = self._validate_and_assert(response, "success")

            # 验证行号格式：4位数字，右对齐
            lines = parsed["data"]["content"].split("\n")
            self.assertTrue(lines[0].startswith("   1 |"))
            self.assertTrue(lines[1].startswith("   2 |"))
            self.assertTrue(lines[2].startswith("   3 |"))

    def test_success_pagination_middle_of_file(self):
        """Success: 分页读取文件中间内容"""
        with create_temp_project() as project:
            lines = [f"line {i}" for i in range(1, 101)]
            project.create_file("long.txt", "\n".join(lines) + "\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "long.txt", "start_line": 10, "limit": 5})

            parsed = self._validate_and_assert(response, "partial")

            content = parsed["data"]["content"]
            # 应从第10行开始，读5行（10-14）
            self.assertIn("10 | line 10", content)
            self.assertIn("14 | line 14", content)
            self.assertNotIn("9 |", content)
            self.assertNotIn("15 |", content)

    def test_success_read_to_end_no_truncation(self):
        """Success: 读取到文件末尾，无截断"""
        with create_temp_project() as project:
            lines = [f"line {i}" for i in range(1, 11)]
            project.create_file("ten.txt", "\n".join(lines) + "\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "ten.txt", "start_line": 8, "limit": 100})

            parsed = self._validate_and_assert(response, "success")

            # 读到末尾，不应截断
            self.assertFalse(parsed["data"].get("truncated", False))
            self.assertEqual(parsed["stats"]["lines_read"], 3)

    def test_success_default_parameters(self):
        """Success: 使用默认参数"""
        with create_temp_project() as project:
            project.create_file("default.txt", "content\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "default.txt"})

            parsed = self._validate_and_assert(response, "success")

            # 验证传入的参数被记录（默认值未显式传入时不记录）
            params = parsed["context"]["params_input"]
            self.assertEqual(params["path"], "default.txt")
            # start_line 和 limit 未显式传入，不在 params_input 中

    def test_success_context_path_resolved(self):
        """Success: 验证 context.path_resolved 字段"""
        with create_temp_project() as project:
            project.create_file("subdir/test.txt", "content\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "subdir/test.txt"})

            parsed = self._validate_and_assert(response, "success")

            self.assertIn("path_resolved", parsed["context"])
            self.assertEqual(parsed["context"]["path_resolved"], "subdir/test.txt")

    # ========================================================================
    # Partial 场景测试
    # ========================================================================

    def test_partial_content_truncated(self):
        """Partial: 内容被截断（limit 小于总行数）"""
        with create_temp_project() as project:
            lines = [f"line {i}" for i in range(1, 101)]
            project.create_file("truncate.txt", "\n".join(lines) + "\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "truncate.txt", "limit": 10})

            parsed = self._validate_and_assert(response, "partial")

            # 验证截断标志
            self.assertTrue(parsed["data"].get("truncated", False))

            # 验证 text 包含截断说明
            text = parsed["text"]
            self.assertIn("Truncated", text)
            self.assertIn("start_line=", text)

            # 验证实际读取行数
            self.assertEqual(parsed["stats"]["lines_read"], 10)

    def test_partial_encoding_fallback(self):
        """Partial: 编码回退（UTF-8 解码失败，使用 errors='replace'）"""
        with create_temp_project() as project:
            # 创建包含无效 UTF-8 序列的文件
            invalid_utf8_path = project.path("invalid_utf8.txt")
            with open(invalid_utf8_path, "wb") as f:
                f.write(b"valid text\n")
                f.write(b"\xff\xfe")  # 无效的 UTF-8 序列
                f.write(b"more text\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "invalid_utf8.txt"})

            parsed = self._validate_and_assert(response, "partial")

            # 验证回退标志
            self.assertIn("fallback_encoding", parsed["data"])
            self.assertEqual(parsed["data"]["fallback_encoding"], "replace")

            # 验证 text 包含编码警告
            text = parsed["text"]
            self.assertIn("encoding", text.lower())

            # 验证 stats 中的编码信息
            self.assertIn("encoding", parsed["stats"])
            self.assertEqual(parsed["stats"]["encoding"], "utf-8 (replace)")

    def test_partial_both_truncated_and_fallback(self):
        """Partial: 同时触发截断和编码回退"""
        with create_temp_project() as project:
            lines = [f"line {i}" for i in range(1, 101)]
            content = "\n".join(lines) + "\n"

            # 添加无效 UTF-8
            invalid_utf8_path = project.path("both.txt")
            with open(invalid_utf8_path, "wb") as f:
                f.write(content.encode("utf-8"))
                f.write(b"\xff\xfe")  # 添加无效字节
                f.write(b"\nextra line\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "both.txt", "limit": 10})

            parsed = self._validate_and_assert(response, "partial")

            # 应同时有截断和回退标志
            self.assertTrue(parsed["data"].get("truncated", False))
            self.assertIn("fallback_encoding", parsed["data"])

    # ========================================================================
    # Error - NOT_FOUND 场景测试
    # ========================================================================

    def test_error_not_found_nonexistent_file(self):
        """Error: NOT_FOUND - 文件不存在"""
        with create_temp_project() as project:
            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "nonexistent.txt"})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "NOT_FOUND")
            self.assertIn("nonexistent.txt", parsed["error"]["message"])
            self.assertIn("does not exist", parsed["error"]["message"].lower())

    def test_error_invalid_param_empty_path(self):
        """Error: INVALID_PARAM - 空路径"""
        with create_temp_project() as project:
            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": ""})

            # 空路径被视为 INVALID_PARAM
            parsed = self._validate_and_assert(response, "error")
            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    # ========================================================================
    # Error - ACCESS_DENIED 场景测试
    # ========================================================================

    def test_error_access_denied_path_traversal(self):
        """Error: ACCESS_DENIED - 路径遍历攻击 ../../"""
        with create_temp_project() as project:
            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "../../../etc/passwd"})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "ACCESS_DENIED")
            self.assertIn("outside project root", parsed["error"]["message"].lower())

    def test_error_access_denied_absolute_path_outside(self):
        """Error: ACCESS_DENIED - 绝对路径在项目根外"""
        with create_temp_project() as project:
            tool = ReadTool(project_root=project.root)
            # 尝试读取系统文件
            response = tool.run({"path": "/etc/passwd"})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "ACCESS_DENIED")

    def test_error_access_denied_symlink_outside(self):
        """Error: ACCESS_DENIED - 符号链接指向项目外"""
        with create_temp_project() as project:
            # 创建符号链接（如果系统支持）
            try:
                link_path = project.path("link_to_outside")
                outside_path = project.root.parent / "outside.txt"
                outside_path.write_text("outside content")

                link_path.symlink_to(outside_path)

                tool = ReadTool(project_root=project.root)
                response = tool.run({"path": "link_to_outside"})

                parsed = self._validate_and_assert(response, "error")
                self.assertEqual(parsed["error"]["code"], "ACCESS_DENIED")
            except OSError:
                # 符号链接创建失败（可能不支持或权限问题），跳过测试
                self.skipTest("符号链接创建失败")

    # ========================================================================
    # Error - INVALID_PARAM 场景测试
    # ========================================================================

    def test_error_invalid_param_missing_path(self):
        """Error: INVALID_PARAM - 缺少 path 参数"""
        with create_temp_project() as project:
            tool = ReadTool(project_root=project.root)
            response = tool.run({})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("path", parsed["error"]["message"].lower())
            self.assertIn("required", parsed["error"]["message"].lower())

    def test_error_invalid_param_start_line_zero(self):
        """Error: INVALID_PARAM - start_line 为 0"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "test.txt", "start_line": 0})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("start_line", parsed["error"]["message"])

    def test_error_invalid_param_start_line_negative(self):
        """Error: INVALID_PARAM - start_line 为负数"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "test.txt", "start_line": -1})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_error_invalid_param_start_line_not_integer(self):
        """Error: INVALID_PARAM - start_line 不是整数"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "test.txt", "start_line": "abc"})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_error_invalid_param_limit_zero(self):
        """Error: INVALID_PARAM - limit 为 0"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "test.txt", "limit": 0})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("limit", parsed["error"]["message"])

    def test_error_invalid_param_limit_negative(self):
        """Error: INVALID_PARAM - limit 为负数"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "test.txt", "limit": -1})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_error_invalid_param_limit_exceeds_max(self):
        """Error: INVALID_PARAM - limit 超过最大值 2000"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "test.txt", "limit": 2001})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("2000", parsed["error"]["message"])

    def test_error_invalid_param_limit_not_integer(self):
        """Error: INVALID_PARAM - limit 不是整数"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "test.txt", "limit": "ten"})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")

    def test_error_invalid_param_start_line_exceeds_file_length(self):
        """Error: INVALID_PARAM - start_line 超出文件行数"""
        with create_temp_project() as project:
            project.create_file("short.txt", "line1\nline2\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "short.txt", "start_line": 100})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("start_line", parsed["error"]["message"].lower())
            self.assertIn("exceeds", parsed["error"]["message"].lower())

    def test_error_invalid_param_start_line_exceeds_empty_file(self):
        """Error: INVALID_PARAM - start_line > 1 但文件为空"""
        with create_temp_project() as project:
            project.create_file("empty.txt", "")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "empty.txt", "start_line": 2})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("empty", parsed["error"]["message"].lower())

    # ========================================================================
    # Error - IS_DIRECTORY 场景测试
    # ========================================================================

    def test_error_is_directory(self):
        """Error: IS_DIRECTORY - 路径是目录"""
        with create_temp_project() as project:
            project.create_dir("src")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "src"})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "IS_DIRECTORY")
            self.assertIn("directory", parsed["error"]["message"].lower())
            self.assertIn("Use LS", parsed["error"]["message"])

    # ========================================================================
    # Error - BINARY_FILE 场景测试
    # ========================================================================

    def test_error_binary_file_with_null_byte(self):
        """Error: BINARY_FILE - 文件包含 null byte"""
        with create_temp_project() as project:
            binary_path = project.path("binary.bin")
            binary_path.write_bytes(b"\x00\x01\x02\x03\x04\x05")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "binary.bin"})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "BINARY_FILE")
            self.assertIn("binary", parsed["error"]["message"].lower())

    def test_error_binary_file_at_start(self):
        """Error: BINARY_FILE - null byte 在文件开头"""
        with create_temp_project() as project:
            binary_path = project.path("early_null.bin")
            binary_path.write_bytes(b"\x00some text")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "early_null.bin"})

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "BINARY_FILE")

    def test_success_text_file_without_null_byte(self):
        """Success: 普通文本文件不误判为二进制"""
        with create_temp_project() as project:
            project.create_file("text.txt", "Normal text file\nwith multiple lines\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "text.txt"})

            parsed = self._validate_and_assert(response, "success")

            self.assertIn("content", parsed["data"])

    # ========================================================================
    # 协议字段完整性测试
    # ========================================================================

    def test_protocol_all_required_fields_present(self):
        """Protocol: 验证所有必需字段存在"""
        with create_temp_project() as project:
            project.create_file("protocol_test.txt", "test content\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "protocol_test.txt"})

            parsed = parse_response(response)

            # 验证顶层字段
            required_top_level = {"status", "data", "text", "stats", "context"}
            self.assertEqual(set(parsed.keys()), required_top_level)

            # 验证 context 字段
            self.assertIn("cwd", parsed["context"])
            self.assertIn("params_input", parsed["context"])

            # 验证 stats 字段
            self.assertIn("time_ms", parsed["stats"])

    def test_protocol_no_extra_top_level_fields(self):
        """Protocol: 验证没有禁止的顶层自定义字段"""
        with create_temp_project() as project:
            project.create_file("extra_test.txt", "test\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "extra_test.txt"})

            parsed = parse_response(response)
            allowed_fields = {"status", "data", "text", "stats", "context"}
            actual_fields = set(parsed.keys())

            # success 状态不应有 error 字段
            self.assertEqual(actual_fields, allowed_fields)

    def test_protocol_error_response_structure(self):
        """Protocol: 验证错误响应结构正确"""
        with create_temp_project() as project:
            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "nonexistent.txt"})

            parsed = parse_response(response)

            # error 状态必须有 error 字段
            self.assertIn("error", parsed)
            self.assertIn("code", parsed["error"])
            self.assertIn("message", parsed["error"])

            # error 状态的 data 应为空对象
            self.assertEqual(parsed["data"], {})

    def test_protocol_context_preserves_input_params(self):
        """Protocol: 验证 context.params_input 保留原始输入"""
        with create_temp_project() as project:
            project.create_file("params.txt", "content\n")

            tool = ReadTool(project_root=project.root)
            input_params = {"path": "params.txt", "start_line": 5, "limit": 10}
            response = tool.run(input_params)

            parsed = parse_response(response)
            params_input = parsed["context"]["params_input"]

            # 验证原始参数被保留
            self.assertEqual(params_input["path"], "params.txt")
            self.assertEqual(params_input["start_line"], 5)
            self.assertEqual(params_input["limit"], 10)

    # ========================================================================
    # 边界条件测试
    # ========================================================================

    def test_boundary_limit_max_value(self):
        """Boundary: limit 等于最大值 2000"""
        with create_temp_project() as project:
            lines = [f"line {i}" for i in range(1, 2001)]
            project.create_file("max_limit.txt", "\n".join(lines))

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "max_limit.txt", "limit": 2000})

            parsed = self._validate_and_assert(response, "success")
            self.assertEqual(parsed["stats"]["lines_read"], 2000)

    def test_boundary_limit_min_value(self):
        """Boundary: limit 等于最小值 1"""
        with create_temp_project() as project:
            project.create_file("min_limit.txt", "line1\nline2\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "min_limit.txt", "limit": 1})

            parsed = self._validate_and_assert(response, "partial")
            self.assertEqual(parsed["stats"]["lines_read"], 1)

    def test_boundary_start_line_min_value(self):
        """Boundary: start_line 等于最小值 1"""
        with create_temp_project() as project:
            project.create_file("start1.txt", "line1\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "start1.txt", "start_line": 1})

            parsed = self._validate_and_assert(response, "success")
            self.assertIn("1 |", parsed["data"]["content"])

    def test_boundary_file_with_very_long_lines(self):
        """Boundary: 文件包含非常长的行"""
        with create_temp_project() as project:
            long_line = "a" * 10000
            project.create_file("long_line.txt", long_line + "\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "long_line.txt"})

            parsed = self._validate_and_assert(response, "success")
            self.assertIn("a" * 1000, parsed["data"]["content"])  # 验证至少包含部分内容

    def test_boundary_file_with_crlf_line_endings(self):
        """Boundary: 文件使用 CRLF 行尾"""
        with create_temp_project() as project:
            content = "line1\r\nline2\r\nline3\r\n"
            project.create_file("crlf.txt", content)

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "crlf.txt"})

            parsed = self._validate_and_assert(response, "success")

            # 验证行号格式统一
            content = parsed["data"]["content"]
            self.assertIn("1 | line1", content)
            self.assertIn("2 | line2", content)

    # ========================================================================
    # 特殊路径测试
    # ========================================================================

    def test_special_path_with_dot_slash(self):
        """Special: 路径以 ./ 开头"""
        with create_temp_project() as project:
            project.create_file("test.txt", "content\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "./test.txt"})

            parsed = self._validate_and_assert(response, "success")
            self.assertIn("content", parsed["data"]["content"])

    def test_special_path_with_nested_directories(self):
        """Special: 嵌套目录路径"""
        with create_temp_project() as project:
            project.create_file("a/b/c/d/file.txt", "deep content\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "a/b/c/d/file.txt"})

            parsed = self._validate_and_assert(response, "success")
            self.assertIn("deep content", parsed["data"]["content"])

    def test_special_path_relative_navigation_within_project(self):
        """Special: 项目内相对路径导航"""
        with create_temp_project() as project:
            project.create_dir("subdir")
            project.create_file("subdir/file.txt", "content\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "subdir/../subdir/file.txt"})

            parsed = self._validate_and_assert(response, "success")
            self.assertIn("content", parsed["data"]["content"])

    # ========================================================================
    # 性能与统计测试
    # ========================================================================

    def test_stats_time_ms_is_reasonable(self):
        """Stats: time_ms 应为合理数值"""
        with create_temp_project() as project:
            project.create_file("timer.txt", "x\n" * 100)

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "timer.txt"})

            parsed = parse_response(response)
            time_ms = parsed["stats"]["time_ms"]

            self.assertIsInstance(time_ms, (int, float))
            self.assertGreaterEqual(time_ms, 0)
            self.assertLess(time_ms, 10000)  # 不应超过 10 秒

    def test_stats_contains_line_and_char_counts(self):
        """Stats: 验证行数和字符数统计"""
        with create_temp_project() as project:
            content = "line1\nline2\nline3\n"
            project.create_file("stats.txt", content)

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "stats.txt"})

            parsed = parse_response(response)

            self.assertIn("lines_read", parsed["stats"])
            self.assertIn("chars_read", parsed["stats"])
            self.assertEqual(parsed["stats"]["lines_read"], 3)

    def test_stats_contains_file_size(self):
        """Stats: 验证文件大小统计"""
        with create_temp_project() as project:
            content = "test content"
            project.create_file("size.txt", content)

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "size.txt"})

            parsed = parse_response(response)

            self.assertIn("file_size_bytes", parsed["stats"])
            self.assertGreater(parsed["stats"]["file_size_bytes"], 0)

    def test_stats_contains_encoding_info(self):
        """Stats: 验证编码信息"""
        with create_temp_project() as project:
            project.create_file("encoding.txt", "content\n")

            tool = ReadTool(project_root=project.root)
            response = tool.run({"path": "encoding.txt"})

            parsed = parse_response(response)

            self.assertIn("encoding", parsed["stats"])
            self.assertEqual(parsed["stats"]["encoding"], "utf-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
