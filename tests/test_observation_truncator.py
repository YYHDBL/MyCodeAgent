"""工具输出截断器测试

测试 ObservationTruncator 的统一截断策略。
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_engine.observation_truncator import (
    ObservationTruncator,
    truncate_observation,
    _get_max_lines,
    _get_max_bytes,
)


class TestObservationTruncatorBasic:
    """基础截断功能测试"""
    
    def test_small_output_not_truncated(self, tmp_path):
        """小于阈值的输出不被截断"""
        result = {
            "status": "success",
            "data": {"message": "hello"},
            "text": "ok"
        }
        raw = json.dumps(result)
        
        truncator = ObservationTruncator(str(tmp_path))
        output = truncator.truncate("Test", raw)
        
        parsed = json.loads(output)
        assert parsed["status"] == "success"
        assert "truncated" not in parsed.get("data", {})
    
    def test_large_output_truncated_by_lines(self, tmp_path):
        """超过行数限制时触发截断"""
        # 创建超过 2000 行的输出
        lines = [f"line {i}" for i in range(3000)]
        content = "\n".join(lines)
        result = {
            "status": "success",
            "data": {"content": content},
            "text": "large output"
        }
        raw = json.dumps(result)
        
        truncator = ObservationTruncator(str(tmp_path))
        output = truncator.truncate("Read", raw)
        
        parsed = json.loads(output)
        assert parsed["status"] == "partial"
        assert parsed["data"].get("truncated") is True
        assert "preview" in parsed["data"]
        assert "truncation" in parsed["data"]
        assert parsed["data"]["truncation"]["original_lines"] > 2000
    
    def test_large_output_truncated_by_bytes(self, tmp_path):
        """超过字节数限制时触发截断"""
        # 创建超过 50KB 的输出
        content = "x" * (60 * 1024)  # 60KB
        result = {
            "status": "success",
            "data": {"content": content},
            "text": "large output"
        }
        raw = json.dumps(result)
        
        truncator = ObservationTruncator(str(tmp_path))
        output = truncator.truncate("Bash", raw)
        
        parsed = json.loads(output)
        assert parsed["status"] == "partial"
        assert parsed["data"].get("truncated") is True
        assert "preview" in parsed["data"]
        assert parsed["data"]["truncation"]["original_bytes"] > 50 * 1024
    
    def test_skip_truncation_when_marked(self, tmp_path):
        """跳过标记生效"""
        content = "x" * (60 * 1024)  # 60KB
        result = {
            "status": "success",
            "data": {"content": content},
            "context": {"truncation_skip": True}
        }
        raw = json.dumps(result)
        
        truncator = ObservationTruncator(str(tmp_path))
        output = truncator.truncate("Read", raw)
        
        # 应该原样返回
        assert output == raw


class TestObservationTruncatorFileSave:
    """落盘保存测试"""
    
    def test_full_output_saved_to_file(self, tmp_path):
        """完整输出被保存到文件"""
        lines = [f"line {i}" for i in range(3000)]
        content = "\n".join(lines)
        result = {
            "status": "success",
            "data": {"content": content},
        }
        raw = json.dumps(result)
        
        truncator = ObservationTruncator(str(tmp_path))
        output = truncator.truncate("Read", raw)
        
        parsed = json.loads(output)
        
        # 检查文件路径
        assert "full_output_path" in parsed["data"]["truncation"]
        output_path = tmp_path / parsed["data"]["truncation"]["full_output_path"]
        assert output_path.exists()
        
        # 检查文件内容
        saved_content = output_path.read_text()
        saved_result = json.loads(saved_content)
        assert len(saved_result["data"]["content"]) == len(content)
    
    def test_output_dir_created(self, tmp_path):
        """输出目录被自动创建"""
        output_dir = tmp_path / "tool-output"
        assert not output_dir.exists()
        
        lines = [f"line {i}" for i in range(3000)]
        result = {
            "status": "success",
            "data": {"content": "\n".join(lines)},
        }
        raw = json.dumps(result)
        
        truncator = ObservationTruncator(str(tmp_path))
        truncator.truncate("Test", raw)
        
        assert output_dir.exists()


class TestObservationTruncatorDirection:
    """截断方向测试"""
    
    def test_head_direction_keeps_first_lines(self, tmp_path):
        """head 方向保留前 N 行"""
        lines = [f"line_{i}" for i in range(100)]
        result = {
            "status": "success",
            "data": {"content": "\n".join(lines)},
        }
        raw = json.dumps(result)
        
        with patch.dict(os.environ, {"TOOL_OUTPUT_MAX_LINES": "10"}):
            truncator = ObservationTruncator(str(tmp_path))
            output = truncator.truncate("Test", raw)
        
        parsed = json.loads(output)
        assert parsed["data"]["truncation"]["direction"] == "head"
        assert parsed["data"]["truncation"]["kept_lines"] <= 10
    
    def test_tail_direction_keeps_last_lines(self, tmp_path):
        """tail 方向保留后 N 行"""
        lines = [f"line_{i}" for i in range(100)]
        result = {
            "status": "success",
            "data": {"content": "\n".join(lines)},
        }
        raw = json.dumps(result)
        
        with patch.dict(os.environ, {
            "TOOL_OUTPUT_MAX_LINES": "10",
            "TOOL_OUTPUT_TRUNCATE_DIRECTION": "tail"
        }):
            truncator = ObservationTruncator(str(tmp_path))
            output = truncator.truncate("Test", raw)
        
        parsed = json.loads(output)
        assert parsed["data"]["truncation"]["direction"] == "tail"


class TestObservationTruncatorHint:
    """智能提示测试"""
    
    def test_hint_contains_file_path(self, tmp_path):
        """提示包含文件路径"""
        lines = [f"line {i}" for i in range(3000)]
        result = {
            "status": "success",
            "data": {"content": "\n".join(lines)},
        }
        raw = json.dumps(result)
        
        truncator = ObservationTruncator(str(tmp_path))
        output = truncator.truncate("Read", raw)
        
        parsed = json.loads(output)
        assert "tool-output" in parsed["text"]
        assert "完整内容见" in parsed["text"] or "Full" in parsed["text"]


class TestObservationTruncatorConfig:
    """配置测试"""
    
    def test_env_config_max_lines(self, tmp_path):
        """环境变量配置 MAX_LINES"""
        with patch.dict(os.environ, {"TOOL_OUTPUT_MAX_LINES": "100"}):
            assert _get_max_lines() == 100
    
    def test_env_config_max_bytes(self, tmp_path):
        """环境变量配置 MAX_BYTES"""
        with patch.dict(os.environ, {"TOOL_OUTPUT_MAX_BYTES": "10240"}):
            assert _get_max_bytes() == 10240
    
    def test_default_config(self):
        """默认配置值"""
        # 确保没有环境变量干扰
        with patch.dict(os.environ, {}, clear=True):
            # 重新导入以获取默认值
            from core.context_engine.observation_truncator import (
                _get_max_lines, _get_max_bytes
            )
            # 使用默认值断言（考虑可能已设置的环境变量）
            assert _get_max_lines() >= 100  # 至少 100
            assert _get_max_bytes() >= 10000  # 至少 10KB


class TestObservationTruncatorEdgeCases:
    """边界情况测试"""
    
    def test_invalid_json_returned_as_is(self, tmp_path):
        """无效 JSON 原样返回"""
        raw = "not valid json {"
        
        truncator = ObservationTruncator(str(tmp_path))
        output = truncator.truncate("Test", raw)
        
        assert output == raw
    
    def test_empty_data_handled(self, tmp_path):
        """空 data 处理"""
        result = {
            "status": "success",
            "data": {},
        }
        raw = json.dumps(result)
        
        truncator = ObservationTruncator(str(tmp_path))
        output = truncator.truncate("Test", raw)
        
        parsed = json.loads(output)
        assert parsed["status"] == "success"
    
    def test_error_status_preserved(self, tmp_path):
        """错误状态被保留"""
        lines = [f"line {i}" for i in range(3000)]
        result = {
            "status": "error",
            "data": {"content": "\n".join(lines)},
            "error": {"code": "TEST_ERROR", "message": "test"}
        }
        raw = json.dumps(result)
        
        truncator = ObservationTruncator(str(tmp_path))
        output = truncator.truncate("Test", raw)
        
        parsed = json.loads(output)
        assert parsed["status"] == "error"


class TestConvenienceFunction:
    """便捷函数测试"""
    
    def test_truncate_observation_function(self, tmp_path):
        """truncate_observation 便捷函数"""
        result = {
            "status": "success",
            "data": {"message": "test"},
        }
        raw = json.dumps(result)
        
        output = truncate_observation("Test", raw, str(tmp_path))
        
        parsed = json.loads(output)
        assert parsed["status"] == "success"


class TestBackwardCompatibility:
    """向后兼容性测试"""
    
    def test_compress_tool_result_import(self):
        """旧的 compress_tool_result 导入仍可用"""
        from core.context_engine.tool_result_compressor import compress_tool_result
        
        result = {
            "status": "success",
            "data": {"message": "test"},
        }
        raw = json.dumps(result)
        
        output = compress_tool_result("Test", raw)
        
        parsed = json.loads(output)
        assert parsed["status"] == "success"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
