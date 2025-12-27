"""协议合规性测试

验证所有工具响应是否严格遵循《通用工具响应协议》。

运行方式：
    python -m pytest tests/test_protocol_compliance.py -v
    python -m unittest tests.test_protocol_compliance -v
"""

import unittest
import json
from pathlib import Path

from tests.utils.protocol_validator import ProtocolValidator
from tests.utils.test_helpers import create_temp_project, parse_response


class TestProtocolCompliance(unittest.TestCase):
    """协议合规性测试套件"""
    
    def _validate_and_assert(self, tool_name: str, response_str: str, 
                            tool_type: str = None):
        """验证响应并断言通过"""
        result = ProtocolValidator.validate(response_str, tool_type=tool_type)
        
        if not result.passed:
            # 格式化错误信息
            error_msg = f"\n{'='*60}\n"
            error_msg += f"{tool_name} 协议验证失败\n"
            error_msg += f"{'='*60}\n"
            error_msg += "\n错误:\n"
            for error in result.errors:
                error_msg += f"  ❌ {error}\n"
            if result.warnings:
                error_msg += "\n警告:\n"
                for warning in result.warnings:
                    error_msg += f"  ⚠️  {warning}\n"
            error_msg += f"\n响应内容:\n{self._format_response(response_str)}\n"
            self.fail(error_msg)
        
        # 返回解析后的响应，供进一步验证
        return parse_response(response_str)
    
    def _format_response(self, response_str: str) -> str:
        """格式化响应用于输出"""
        try:
            parsed = json.loads(response_str)
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        except:
            return response_str[:1000] + "..." if len(response_str) > 1000 else response_str
    
    # =========================================================================
    # ListFilesTool (LS) 测试
    # =========================================================================
    
    def test_ls_success_response(self):
        """LS: 成功响应协议合规"""
        from tools.builtin.list_files import ListFilesTool
        
        with create_temp_project() as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": "."})
            
            parsed = self._validate_and_assert("LS", response, tool_type="ls")
            
            # 验证状态
            self.assertEqual(parsed["status"], "success")
            # 验证 data.entries
            self.assertIn("entries", parsed["data"])
            self.assertIsInstance(parsed["data"]["entries"], list)
    
    def test_ls_partial_truncated_response(self):
        """LS: 截断响应协议合规"""
        from tools.builtin.list_files import ListFilesTool
        
        with create_temp_project() as project:
            tool = ListFilesTool(project_root=project.root)
            # 限制返回 1 条，触发截断
            response = tool.run({"path": ".", "limit": 1})
            
            parsed = self._validate_and_assert("LS", response, tool_type="ls")
            
            # 验证截断状态
            self.assertEqual(parsed["status"], "partial")
            self.assertTrue(parsed["data"].get("truncated", False))
    
    def test_ls_error_not_found(self):
        """LS: 路径不存在错误响应协议合规"""
        from tools.builtin.list_files import ListFilesTool
        
        with create_temp_project() as project:
            tool = ListFilesTool(project_root=project.root)
            response = tool.run({"path": "nonexistent_path"})
            
            parsed = self._validate_and_assert("LS", response)
            
            # 验证错误状态
            self.assertEqual(parsed["status"], "error")
            self.assertIsNotNone(parsed.get("error"))
            self.assertEqual(parsed["error"]["code"], "NOT_FOUND")
    
    def test_ls_error_access_denied(self):
        """LS: 越权访问错误响应协议合规"""
        from tools.builtin.list_files import ListFilesTool
        
        with create_temp_project() as project:
            tool = ListFilesTool(project_root=project.root)
            # 尝试访问项目外路径
            response = tool.run({"path": "../../../etc"})
            
            parsed = self._validate_and_assert("LS", response)
            
            # 验证错误状态
            self.assertEqual(parsed["status"], "error")
            self.assertEqual(parsed["error"]["code"], "ACCESS_DENIED")
    
    # =========================================================================
    # SearchFilesByNameTool (Glob) 测试
    # =========================================================================
    
    def test_glob_success_response(self):
        """Glob: 成功响应协议合规"""
        from tools.builtin.search_files_by_name import SearchFilesByNameTool
        
        with create_temp_project() as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            # 使用 **/*.py 递归匹配所有子目录中的 .py 文件
            response = tool.run({"pattern": "**/*.py"})
            
            parsed = self._validate_and_assert("Glob", response, tool_type="glob")
            
            # 验证状态
            self.assertEqual(parsed["status"], "success")
            # 验证 data.paths
            self.assertIn("paths", parsed["data"])
            self.assertIsInstance(parsed["data"]["paths"], list)
            # 应该找到 .py 文件
            self.assertGreater(len(parsed["data"]["paths"]), 0)
    
    def test_glob_success_no_matches(self):
        """Glob: 无匹配结果响应协议合规"""
        from tools.builtin.search_files_by_name import SearchFilesByNameTool
        
        with create_temp_project() as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "*.nonexistent_extension"})
            
            parsed = self._validate_and_assert("Glob", response, tool_type="glob")
            
            # 无匹配也是 success
            self.assertEqual(parsed["status"], "success")
            self.assertEqual(parsed["data"]["paths"], [])
    
    def test_glob_partial_truncated_response(self):
        """Glob: 截断响应协议合规"""
        from tools.builtin.search_files_by_name import SearchFilesByNameTool
        
        with create_temp_project() as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            # 使用 **/* 匹配所有文件，限制返回 1 条，触发截断
            response = tool.run({"pattern": "**/*", "limit": 1})
            
            parsed = self._validate_and_assert("Glob", response, tool_type="glob")
            
            # 验证截断状态（如果找到多于 1 个文件则为 partial）
            if len(parsed["data"]["paths"]) > 0:
                self.assertEqual(parsed["status"], "partial")
                self.assertTrue(parsed["data"].get("truncated", False))
    
    def test_glob_error_access_denied(self):
        """Glob: 越权访问错误响应协议合规"""
        from tools.builtin.search_files_by_name import SearchFilesByNameTool
        
        with create_temp_project() as project:
            tool = SearchFilesByNameTool(project_root=project.root)
            response = tool.run({"pattern": "*.py", "path": "../../../"})
            
            parsed = self._validate_and_assert("Glob", response)
            
            # 验证错误状态
            self.assertEqual(parsed["status"], "error")
            self.assertEqual(parsed["error"]["code"], "ACCESS_DENIED")
    
    # =========================================================================
    # GrepTool (Grep) 测试
    # =========================================================================
    
    def test_grep_success_response(self):
        """Grep: 成功响应协议合规"""
        from tools.builtin.search_code import GrepTool
        
        with create_temp_project() as project:
            tool = GrepTool(project_root=project.root)
            response = tool.run({"pattern": "class", "include": "*.py"})
            
            parsed = self._validate_and_assert("Grep", response, tool_type="grep")
            
            # 验证状态
            self.assertIn(parsed["status"], ["success", "partial"])
            # 验证 data.matches
            self.assertIn("matches", parsed["data"])
            self.assertIsInstance(parsed["data"]["matches"], list)
    
    def test_grep_success_no_matches(self):
        """Grep: 无匹配结果响应协议合规"""
        from tools.builtin.search_code import GrepTool
        
        with create_temp_project() as project:
            tool = GrepTool(project_root=project.root)
            response = tool.run({"pattern": "xyznonexistentpattern123", "include": "*.py"})
            
            parsed = self._validate_and_assert("Grep", response, tool_type="grep")
            
            # 无匹配也是 success
            self.assertEqual(parsed["status"], "success")
            self.assertEqual(parsed["data"]["matches"], [])
    
    def test_grep_error_invalid_regex(self):
        """Grep: 正则语法错误响应协议合规"""
        from tools.builtin.search_code import GrepTool
        
        with create_temp_project() as project:
            tool = GrepTool(project_root=project.root)
            # 无效的正则表达式
            response = tool.run({"pattern": "[invalid(regex", "include": "*.py"})
            
            parsed = self._validate_and_assert("Grep", response)
            
            # 验证错误状态
            self.assertEqual(parsed["status"], "error")
            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
    
    def test_grep_error_access_denied(self):
        """Grep: 越权访问错误响应协议合规"""
        from tools.builtin.search_code import GrepTool
        
        with create_temp_project() as project:
            tool = GrepTool(project_root=project.root)
            response = tool.run({"pattern": "test", "path": "../../../"})
            
            parsed = self._validate_and_assert("Grep", response)
            
            # 验证错误状态
            self.assertEqual(parsed["status"], "error")
            self.assertEqual(parsed["error"]["code"], "ACCESS_DENIED")
    
    # =========================================================================
    # 综合测试
    # =========================================================================
    
    def test_all_tools_have_required_fields(self):
        """综合: 所有工具响应包含必需字段"""
        from tools.builtin.list_files import ListFilesTool
        from tools.builtin.search_files_by_name import SearchFilesByNameTool
        from tools.builtin.search_code import GrepTool
        
        required_fields = {"status", "data", "text", "stats", "context"}
        
        with create_temp_project() as project:
            tools_and_params = [
                (ListFilesTool(project_root=project.root), {"path": "."}),
                (SearchFilesByNameTool(project_root=project.root), {"pattern": "*.py"}),
                (GrepTool(project_root=project.root), {"pattern": "def", "include": "*.py"}),
            ]
            
            for tool, params in tools_and_params:
                response = tool.run(params)
                parsed = parse_response(response)
                
                missing = required_fields - set(parsed.keys())
                self.assertEqual(missing, set(), 
                    f"{tool.name} 响应缺少必需字段: {missing}")
    
    def test_all_tools_context_has_cwd_and_params(self):
        """综合: 所有工具 context 包含 cwd 和 params_input"""
        from tools.builtin.list_files import ListFilesTool
        from tools.builtin.search_files_by_name import SearchFilesByNameTool
        from tools.builtin.search_code import GrepTool
        
        with create_temp_project() as project:
            tools_and_params = [
                (ListFilesTool(project_root=project.root), {"path": "."}),
                (SearchFilesByNameTool(project_root=project.root), {"pattern": "*.py"}),
                (GrepTool(project_root=project.root), {"pattern": "def", "include": "*.py"}),
            ]
            
            for tool, params in tools_and_params:
                response = tool.run(params)
                parsed = parse_response(response)
                context = parsed.get("context", {})
                
                self.assertIn("cwd", context, f"{tool.name} context 缺少 cwd")
                self.assertIn("params_input", context, f"{tool.name} context 缺少 params_input")
    
    def test_all_tools_stats_has_time_ms(self):
        """综合: 所有工具 stats 包含 time_ms"""
        from tools.builtin.list_files import ListFilesTool
        from tools.builtin.search_files_by_name import SearchFilesByNameTool
        from tools.builtin.search_code import GrepTool
        
        with create_temp_project() as project:
            tools_and_params = [
                (ListFilesTool(project_root=project.root), {"path": "."}),
                (SearchFilesByNameTool(project_root=project.root), {"pattern": "*.py"}),
                (GrepTool(project_root=project.root), {"pattern": "def", "include": "*.py"}),
            ]
            
            for tool, params in tools_and_params:
                response = tool.run(params)
                parsed = parse_response(response)
                stats = parsed.get("stats", {})
                
                self.assertIn("time_ms", stats, f"{tool.name} stats 缺少 time_ms")
                self.assertIsInstance(stats["time_ms"], (int, float),
                    f"{tool.name} stats.time_ms 类型错误")


class TestValidatorItself(unittest.TestCase):
    """验证器自身测试"""
    
    def test_valid_success_response(self):
        """验证器: 正确识别有效的 success 响应"""
        valid_response = json.dumps({
            "status": "success",
            "data": {"items": []},
            "text": "Operation completed successfully.",
            "stats": {"time_ms": 100},
            "context": {"cwd": ".", "params_input": {}}
        })
        
        result = ProtocolValidator.validate(valid_response)
        self.assertTrue(result.passed, f"应该通过: {result}")
    
    def test_valid_partial_response(self):
        """验证器: 正确识别有效的 partial 响应"""
        valid_response = json.dumps({
            "status": "partial",
            "data": {"items": [], "truncated": True},
            "text": "Results truncated to first 100 items.",
            "stats": {"time_ms": 150},
            "context": {"cwd": ".", "params_input": {}}
        })
        
        result = ProtocolValidator.validate(valid_response)
        self.assertTrue(result.passed, f"应该通过: {result}")
    
    def test_valid_error_response(self):
        """验证器: 正确识别有效的 error 响应"""
        valid_response = json.dumps({
            "status": "error",
            "data": {},
            "text": "File not found. Check the path and try again.",
            "error": {"code": "NOT_FOUND", "message": "File not found"},
            "stats": {"time_ms": 10},
            "context": {"cwd": ".", "params_input": {"path": "missing.txt"}}
        })
        
        result = ProtocolValidator.validate(valid_response)
        self.assertTrue(result.passed, f"应该通过: {result}")
    
    def test_invalid_missing_status(self):
        """验证器: 检测缺少 status 字段"""
        invalid_response = json.dumps({
            "data": {},
            "text": "Test",
            "stats": {"time_ms": 100},
            "context": {"cwd": ".", "params_input": {}}
        })
        
        result = ProtocolValidator.validate(invalid_response)
        self.assertFalse(result.passed)
        self.assertTrue(any("V002" in e for e in result.errors))
    
    def test_invalid_wrong_status_value(self):
        """验证器: 检测无效的 status 值"""
        invalid_response = json.dumps({
            "status": "unknown",
            "data": {},
            "text": "Test",
            "stats": {"time_ms": 100},
            "context": {"cwd": ".", "params_input": {}}
        })
        
        result = ProtocolValidator.validate(invalid_response)
        self.assertFalse(result.passed)
        self.assertTrue(any("V003" in e for e in result.errors))
    
    def test_invalid_extra_top_level_field(self):
        """验证器: 检测禁止的顶层自定义字段"""
        invalid_response = json.dumps({
            "status": "success",
            "data": {},
            "text": "Test",
            "stats": {"time_ms": 100},
            "context": {"cwd": ".", "params_input": {}},
            "custom_field": "forbidden"  # 禁止的字段
        })
        
        result = ProtocolValidator.validate(invalid_response)
        self.assertFalse(result.passed)
        self.assertTrue(any("V012" in e for e in result.errors))
    
    def test_invalid_error_without_error_field(self):
        """验证器: 检测 status=error 但缺少 error 字段"""
        invalid_response = json.dumps({
            "status": "error",
            "data": {},
            "text": "Something went wrong",
            "stats": {"time_ms": 100},
            "context": {"cwd": ".", "params_input": {}}
        })
        
        result = ProtocolValidator.validate(invalid_response)
        self.assertFalse(result.passed)
        self.assertTrue(any("S002" in e for e in result.errors))
    
    def test_invalid_truncated_but_not_partial(self):
        """验证器: 检测 truncated=true 但 status 不是 partial"""
        invalid_response = json.dumps({
            "status": "success",  # 应该是 partial
            "data": {"truncated": True},
            "text": "Results",
            "stats": {"time_ms": 100},
            "context": {"cwd": ".", "params_input": {}}
        })
        
        result = ProtocolValidator.validate(invalid_response)
        self.assertFalse(result.passed)
        self.assertTrue(any("S005" in e for e in result.errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
