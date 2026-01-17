"""RefactorSuggest tests."""

import unittest
from pathlib import Path
from dataclasses import dataclass

from tests.utils.test_helpers import create_temp_project, parse_response
from tests.utils.protocol_validator import ProtocolValidator


# 简化的协议验证器（用于验证响应格式）
class ProtocolValidator:
    @staticmethod
    def validate(response_str: str, tool_type: str = "refactor"):
        """验证响应格式"""
        try:
            parsed = parse_response(response_str)
            errors = []
            warnings = []
            
            # 检查必需字段（error 状态不需要 data）
            status = parsed.get("status", "")
            required_fields = ["status", "text", "stats", "context"]
            if status != "error":
                required_fields.insert(1, "data")
            
            for field in required_fields:
                if field not in parsed:
                    errors.append(f"缺少必需字段: {field}")
            
            # 检查 data 字段（仅在非 error 状态时）
            if status != "error" and "data" in parsed:
                data = parsed["data"]
                if not isinstance(data, dict):
                    errors.append("data 字段必须是对象")
                else:
                    if "issues" not in data:
                        errors.append("data.issues 字段缺失")
                    if "summary" not in data:
                        errors.append("data.summary 字段缺失")
                    if "analyzed_files" not in data:
                        errors.append("data.analyzed_files 字段缺失")
            
            return ValidationResult(not errors, errors, warnings)
        except Exception as e:
            return ValidationResult(False, [f"JSON 解析失败: {e}"], warnings=[])


@dataclass
class ValidationResult:
    passed: bool
    errors: list
    warnings: list


class TestRefactorSuggest(unittest.TestCase):
    """RefactorSuggest 工具测试"""
    
    def setUp(self):
        """测试前准备"""
        from tests.refactor_suggest import RefactorSuggest
        self.RefactorSuggest = RefactorSuggest
    
    def _validate(self, response_str: str, expected_status: str = None) -> dict:
        """验证响应格式"""
        result = ProtocolValidator.validate(response_str)
        if not result.passed:
            error_msg = "\n" + "=" * 60 + "\n"
            error_msg += "RefactorSuggest protocol validation failed\n"
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
    
    def test_success_single_file_clean_code(self):
        """测试分析干净的单文件"""
        code = '''
def short_func(x):
    return x * 2

class SmallClass:
    def method(self):
        pass
'''
        with create_temp_project({"clean.py": code}) as project:
            tool = self.RefactorSuggest(project_root=project.root)
            response = tool.run({"paths": ["clean.py"]})
            parsed = self._validate(response, "success")
            self.assertEqual(parsed["data"]["analyzed_files"], 1)
            self.assertEqual(len(parsed["data"]["issues"]), 0)
    
    def test_success_long_function(self):
        """测试检测过长函数"""
        code = 'def long_function():\n' + '\n'.join([f'    x = {i}' for i in range(35)]) + '\n    return x'
        with create_temp_project({"long.py": code}) as project:
            tool = self.RefactorSuggest(project_root=project.root)
            response = tool.run({"paths": ["long.py"]})
            parsed = self._validate(response, "success")
            issues = parsed["data"]["issues"]
            long_func_issues = [i for i in issues if i["type"] == "long_function"]
            self.assertGreater(len(long_func_issues), 0)
            self.assertEqual(long_func_issues[0]["severity"], "medium")
    
    def test_success_high_complexity(self):
        """测试检测高复杂度函数"""
        code = '''
def complex_function(x):
    if x > 0:
        if x > 10:
            if x > 20:
                if x > 30:
                    if x > 40:
                        if x > 50:
                            if x > 60:
                                if x > 70:
                                    if x > 80:
                                        if x > 90:
                                            if x > 100:
                                                return x
                                            return x - 10
                                        return x - 20
                                    return x - 30
                                return x - 40
                            return x - 50
                        return x - 60
                    return x - 70
                return x - 80
            return x - 90
        return x - 100
    return 0
'''
        with create_temp_project({"complex.py": code}) as project:
            tool = self.RefactorSuggest(project_root=project.root)
            response = tool.run({"paths": ["complex.py"]})
            parsed = self._validate(response, "success")
            issues = parsed["data"]["issues"]
            complex_issues = [i for i in issues if i["type"] == "high_complexity"]
            self.assertGreater(len(complex_issues), 0)
    
    def test_success_too_many_parameters(self):
        """测试检测参数过多的函数"""
        code = 'def many_params(a, b, c, d, e, f):\n    return a + b + c + d + e + f'
        with create_temp_project({"params.py": code}) as project:
            tool = self.RefactorSuggest(project_root=project.root)
            response = tool.run({"paths": ["params.py"]})
            parsed = self._validate(response, "success")
            issues = parsed["data"]["issues"]
            param_issues = [i for i in issues if i["type"] == "too_many_parameters"]
            self.assertGreater(len(param_issues), 0)
    
    def test_success_long_class(self):
        """测试检测过长的类"""
        code = 'class LongClass:\n' + '\n'.join([f'    def method_{i}(self): pass' for i in range(201)])
        with create_temp_project({"long_class.py": code}) as project:
            tool = self.RefactorSuggest(project_root=project.root)
            response = tool.run({"paths": ["long_class.py"]})
            parsed = self._validate(response, "success")
            issues = parsed["data"]["issues"]
            class_issues = [i for i in issues if i["type"] == "long_class"]
            self.assertGreater(len(class_issues), 0)
    
    def test_success_multiple_files(self):
        """测试分析多个文件"""
        code1 = 'def func1(): return 1\n' * 5
        code2 = 'def func2(): return 2\n' * 5
        with create_temp_project({"file1.py": code1, "file2.py": code2}) as project:
            tool = self.RefactorSuggest(project_root=project.root)
            response = tool.run({"paths": ["file1.py", "file2.py"]})
            parsed = self._validate(response, "success")
            self.assertEqual(parsed["data"]["analyzed_files"], 2)
    
    def test_summary_statistics(self):
        """测试摘要统计"""
        code = 'def long_func():\n' + '\n'.join([f'    x = {i}' for i in range(35)]) + '\n    return x'
        with create_temp_project({"test.py": code}) as project:
            tool = self.RefactorSuggest(project_root=project.root)
            response = tool.run({"paths": ["test.py"]})
            parsed = self._validate(response, "success")
            summary = parsed["data"]["summary"]
            self.assertIn("total", summary)
            self.assertIn("high", summary)
            self.assertIn("medium", summary)
            self.assertIn("low", summary)
            self.assertIn("by_type", summary)
    
    def test_error_invalid_param_paths_not_list(self):
        """测试错误：paths 不是列表"""
        with create_temp_project() as project:
            tool = self.RefactorSuggest(project_root=project.root)
            response = tool.run({"paths": "not_a_list"})
            parsed = self._validate(response, "error")
            self.assertIn("paths 参数必须", parsed["error"]["message"])
    
    def test_error_invalid_param_paths_empty(self):
        """测试错误：paths 为空列表"""
        with create_temp_project() as project:
            tool = self.RefactorSuggest(project_root=project.root)
            response = tool.run({"paths": []})
            parsed = self._validate(response, "error")
            self.assertIn("paths 参数必须", parsed["error"]["message"])
    
    def test_error_invalid_param_missing_paths(self):
        """测试错误：缺少 paths 参数"""
        with create_temp_project() as project:
            tool = self.RefactorSuggest(project_root=project.root)
            response = tool.run({})
            parsed = self._validate(response, "error")
    
    def test_text_report_format(self):
        """测试文本报告格式"""
        code = 'def long_func():\n' + '\n'.join([f'    x = {i}' for i in range(35)]) + '\n    return x'
        with create_temp_project({"test.py": code}) as project:
            tool = self.RefactorSuggest(project_root=project.root)
            response = tool.run({"paths": ["test.py"]})
            parsed = self._validate(response, "success")
            text = parsed["text"]
            self.assertIn("代码重构分析报告", text)
            self.assertIn("已分析文件", text)
            self.assertIn("发现问题", text)
    
    def test_stats_fields(self):
        """测试统计字段"""
        code = 'def long_func():\n' + '\n'.join([f'    x = {i}' for i in range(35)]) + '\n    return x'
        with create_temp_project({"test.py": code}) as project:
            tool = self.RefactorSuggest(project_root=project.root)
            response = tool.run({"paths": ["test.py"]})
            parsed = self._validate(response, "success")
            stats = parsed["stats"]
            self.assertIn("time_ms", stats)
            self.assertIn("total_issues", stats)
            self.assertIn("high_severity", stats)
            self.assertIn("medium_severity", stats)
            self.assertIn("low_severity", stats)
    
    def test_issue_structure(self):
        """测试问题数据结构"""
        code = 'def long_func():\n' + '\n'.join([f'    x = {i}' for i in range(35)]) + '\n    return x'
        with create_temp_project({"test.py": code}) as project:
            tool = self.RefactorSuggest(project_root=project.root)
            response = tool.run({"paths": ["test.py"]})
            parsed = self._validate(response, "success")
            issues = parsed["data"]["issues"]
            if issues:
                issue = issues[0]
                required_fields = ["severity", "file", "line", "type", "description", "suggestion"]
                for field in required_fields:
                    self.assertIn(field, issue)
                self.assertIn(issue["severity"], ["high", "medium", "low"])
    
    def test_get_parameters(self):
        """测试参数定义"""
        with create_temp_project() as project:
            tool = self.RefactorSuggest(project_root=project.root)
            params = tool.get_parameters()
            self.assertEqual(len(params), 1)
            self.assertEqual(params[0].name, "paths")
            self.assertEqual(params[0].type, "array")
            self.assertTrue(params[0].required)
    
    def test_nonexistent_file(self):
        """测试分析不存在的文件"""
        with create_temp_project() as project:
            tool = self.RefactorSuggest(project_root=project.root)
            response = tool.run({"paths": ["nonexistent.py"]})
            parsed = self._validate(response, "success")
            # 应该成功但没有发现问题
            self.assertEqual(len(parsed["data"]["issues"]), 0)
            self.assertEqual(parsed["data"]["analyzed_files"], 1)


if __name__ == "__main__":
    unittest.main()
