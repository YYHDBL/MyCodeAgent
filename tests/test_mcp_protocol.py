"""MCP 协议层最小测试

验证 MCP 错误处理的四类分类和 error.type 映射。

运行方式：
    python -m pytest tests/test_mcp_protocol.py -v
"""

import json
import time
import unittest

from tools.base import ErrorCode
from tools.mcp.protocol import (
    to_protocol_error,
    to_protocol_invalid_param,
    to_protocol_result,
    _error_type_mapping,
)


class MockMCPResult:
    """Mock MCP tool result"""

    def __init__(self, content=None, is_error=False, structured=None):
        self.content = content or []
        self.isError = is_error
        self.structuredContent = structured


class MockTextContent:
    """Mock text content item"""

    def __init__(self, text):
        self.text = text


class TestMCPErrorTypeMapping(unittest.TestCase):
    """测试错误类型映射（四类分类）"""

    def test_param_error_mapping(self):
        """测试参数错误映射"""
        self.assertEqual(
            _error_type_mapping(ErrorCode.MCP_PARAM_ERROR), "param_error"
        )
        self.assertEqual(_error_type_mapping(ErrorCode.INVALID_PARAM), "param_error")

    def test_parse_error_mapping(self):
        """测试解析错误映射"""
        self.assertEqual(
            _error_type_mapping(ErrorCode.MCP_PARSE_ERROR), "parse_error"
        )

    def test_network_error_mapping(self):
        """测试网络错误映射"""
        self.assertEqual(
            _error_type_mapping(ErrorCode.MCP_NETWORK_ERROR), "network_error"
        )
        self.assertEqual(_error_type_mapping(ErrorCode.MCP_TIMEOUT), "network_error")

    def test_execution_error_mapping(self):
        """测试执行错误映射"""
        self.assertEqual(
            _error_type_mapping(ErrorCode.MCP_EXECUTION_ERROR), "execution_error"
        )
        self.assertEqual(
            _error_type_mapping(ErrorCode.MCP_NOT_FOUND), "execution_error"
        )
        self.assertEqual(_error_type_mapping(ErrorCode.INTERNAL_ERROR), "execution_error")


class TestMCPProtocolError(unittest.TestCase):
    """测试 MCP 协议错误响应"""

    def test_error_response_structure(self):
        """测试错误响应包含所有必需字段"""
        start_time = time.monotonic()
        response_str = to_protocol_error(
            message="Test error message",
            params_input={"param1": "value1"},
            tool_name="test_tool",
            start_time=start_time,
            error_code=ErrorCode.MCP_EXECUTION_ERROR,
        )

        response = json.loads(response_str)

        # 验证顶层字段
        self.assertEqual(response["status"], "error")
        self.assertIn("data", response)
        self.assertIn("error", response)
        self.assertIn("stats", response)
        self.assertIn("context", response)

        # 验证 error 字段结构
        error = response["error"]
        self.assertIn("code", error)
        self.assertIn("message", error)
        self.assertIn("type", error)

    def test_error_code_and_type_mapping(self):
        """测试 error.code 和 error.type 的正确映射"""
        test_cases = [
            (ErrorCode.MCP_PARAM_ERROR, "param_error"),
            (ErrorCode.MCP_PARSE_ERROR, "parse_error"),
            (ErrorCode.MCP_NETWORK_ERROR, "network_error"),
            (ErrorCode.MCP_TIMEOUT, "network_error"),
            (ErrorCode.MCP_EXECUTION_ERROR, "execution_error"),
            (ErrorCode.MCP_NOT_FOUND, "execution_error"),
        ]

        start_time = time.monotonic()
        for error_code, expected_type in test_cases:
            with self.subTest(error_code=error_code, expected_type=expected_type):
                response_str = to_protocol_error(
                    message="Test error",
                    params_input={},
                    tool_name="test_tool",
                    start_time=start_time,
                    error_code=error_code,
                )

                response = json.loads(response_str)
                self.assertEqual(response["error"]["code"], error_code.value)
                self.assertEqual(response["error"]["type"], expected_type)

    def test_invalid_param_error(self):
        """测试参数无效错误"""
        start_time = time.monotonic()
        response_str = to_protocol_invalid_param(
            message="Missing required param: url",
            params_input={"url": ""},
            tool_name="fetch",
            start_time=start_time,
        )

        response = json.loads(response_str)

        self.assertEqual(response["error"]["code"], "MCP_PARAM_ERROR")
        self.assertEqual(response["error"]["type"], "param_error")
        self.assertEqual(response["error"]["message"], "Missing required param: url")

    def test_network_error_code(self):
        """测试网络错误码"""
        start_time = time.monotonic()
        response_str = to_protocol_error(
            message="Connection refused",
            params_input={},
            tool_name="test_tool",
            start_time=start_time,
            error_code=ErrorCode.MCP_NETWORK_ERROR,
        )

        response = json.loads(response_str)
        self.assertEqual(response["error"]["code"], "MCP_NETWORK_ERROR")
        self.assertEqual(response["error"]["type"], "network_error")

    def test_timeout_error_code(self):
        """测试超时错误码"""
        start_time = time.monotonic()
        response_str = to_protocol_error(
            message="Tool call timeout after 30s",
            params_input={},
            tool_name="test_tool",
            start_time=start_time,
            error_code=ErrorCode.MCP_TIMEOUT,
        )

        response = json.loads(response_str)
        self.assertEqual(response["error"]["code"], "MCP_TIMEOUT")
        self.assertEqual(response["error"]["type"], "network_error")

    def test_not_found_error_code(self):
        """测试工具不存在错误码"""
        start_time = time.monotonic()
        response_str = to_protocol_error(
            message="Tool 'nonexistent' not found on server",
            params_input={},
            tool_name="nonexistent",
            start_time=start_time,
            error_code=ErrorCode.MCP_NOT_FOUND,
        )

        response = json.loads(response_str)
        self.assertEqual(response["error"]["code"], "MCP_NOT_FOUND")
        self.assertEqual(response["error"]["type"], "execution_error")


class TestMCPProtocolResult(unittest.TestCase):
    """测试 MCP 协议成功响应"""

    def test_success_response(self):
        """测试成功响应"""
        start_time = time.monotonic()
        result = MockMCPResult(
            content=[MockTextContent("Hello, World!")],
            is_error=False,
            structured={"data": "value"},
        )

        response_str = to_protocol_result(
            result,
            params_input={"param1": "value1"},
            tool_name="test_tool",
            start_time=start_time,
        )

        response = json.loads(response_str)

        self.assertEqual(response["status"], "success")
        self.assertIn("data", response)
        self.assertIn("stats", response)
        self.assertIn("context", response)
        self.assertNotIn("error", response)

    def test_error_response_from_mcp_result(self):
        """测试从 MCP 错误结果转换为协议错误"""
        start_time = time.monotonic()
        result = MockMCPResult(
            content=[MockTextContent("Tool execution failed")],
            is_error=True,
        )

        response_str = to_protocol_result(
            result,
            params_input={},
            tool_name="test_tool",
            start_time=start_time,
        )

        response = json.loads(response_str)

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"]["code"], "MCP_EXECUTION_ERROR")
        self.assertEqual(response["error"]["type"], "execution_error")


if __name__ == "__main__":
    unittest.main()
