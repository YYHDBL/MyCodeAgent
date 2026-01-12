"""上下文工程模块测试

测试内容（D7.8）：
1. ToolResultCompressor 压缩规则
2. InputPreprocessor @file 预处理
3. HistoryManager 轮次管理和压缩触发
4. ReadTool mtime 追踪
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from core.context_engine.tool_result_compressor import compress_tool_result
from core.context_engine.input_preprocessor import preprocess_input, extract_file_mentions
from core.context_engine.history_manager import HistoryManager
from core.config import Config
from agents.codeAgent import CodeAgent


class TestToolResultCompressor:
    """ToolResultCompressor 压缩规则测试"""

    def test_compress_ls_truncates_to_10_items(self):
        """LS 工具：截断到前 10 项"""
        entries = [{"path": f"file{i}.txt", "type": "file"} for i in range(20)]
        result = {
            "status": "success",
            "data": {"entries": entries},
            "stats": {"total_entries": 20, "time_ms": 50},
            "text": "Listed 20 items",
        }
        compressed = compress_tool_result("LS", json.dumps(result))
        parsed = json.loads(compressed)
        
        assert parsed["status"] == "success"
        assert len(parsed["data"]["entries"]) == 10
        assert parsed["data"]["total_count"] == 20
        assert "stats" not in parsed
        assert "text" not in parsed

    def test_compress_grep_truncates_to_5_matches(self):
        """Grep 工具：截断到前 5 个匹配"""
        matches = [{"file": f"file{i}.py", "line": i, "content": "test"} for i in range(15)]
        result = {
            "status": "success",
            "data": {"matches": matches},
            "stats": {"total_matches": 15, "files_searched": 100},
            "text": "Found 15 matches",
        }
        compressed = compress_tool_result("Grep", json.dumps(result))
        parsed = json.loads(compressed)
        
        assert parsed["status"] == "success"
        assert len(parsed["data"]["matches"]) == 5
        assert parsed["data"]["total_matches"] == 15
        assert "stats" not in parsed

    def test_compress_read_truncates_to_500_lines(self):
        """Read 工具：截断到 500 行"""
        lines = "\n".join([f"line {i}" for i in range(1000)])
        result = {
            "status": "success",
            "data": {"content": lines, "truncated": False},
            "stats": {"lines_read": 1000, "total_lines": 1000},
        }
        compressed = compress_tool_result("Read", json.dumps(result))
        parsed = json.loads(compressed)
        
        assert parsed["status"] == "success"
        # 内容应被截断
        content_lines = parsed["data"]["content"].strip().split("\n")
        assert len(content_lines) <= 500
        assert parsed["data"]["truncated"] == True

    def test_compress_edit_keeps_applied_drops_diff(self):
        """Edit 工具：保留 applied，丢弃 diff_preview"""
        result = {
            "status": "success",
            "data": {
                "applied": True,
                "diff_preview": "--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,3 @@",
            },
            "text": "Edit applied",
        }
        compressed = compress_tool_result("Edit", json.dumps(result))
        parsed = json.loads(compressed)
        
        assert parsed["status"] == "success"
        assert parsed["data"]["applied"] == True
        assert "diff_preview" not in parsed["data"]

    def test_compress_bash_summarizes_stdout(self):
        """Bash 工具：stdout 截断到 200 字符，stderr 保留最后 20 行"""
        long_stdout = "x" * 500
        stderr_lines = "\n".join([f"error line {i}" for i in range(30)])
        result = {
            "status": "success",
            "data": {
                "stdout": long_stdout,
                "stderr": stderr_lines,
                "exit_code": 0,
            },
        }
        compressed = compress_tool_result("Bash", json.dumps(result))
        parsed = json.loads(compressed)
        
        assert parsed["status"] == "success"
        assert len(parsed["data"]["stdout_summary"]) <= 203  # 200 + "..."
        stderr_result_lines = parsed["data"]["stderr_tail"].strip().split("\n")
        assert len(stderr_result_lines) <= 20

    def test_compress_preserves_error_completely(self):
        """错误响应：完整保留 error 字段"""
        result = {
            "status": "error",
            "error": {
                "code": "NOT_FOUND",
                "message": "File not found: test.py",
            },
        }
        compressed = compress_tool_result("Read", json.dumps(result))
        parsed = json.loads(compressed)
        
        assert parsed["status"] == "error"
        assert parsed["error"]["code"] == "NOT_FOUND"
        assert parsed["error"]["message"] == "File not found: test.py"

    def test_compress_always_includes_data_field(self):
        """data 字段必须始终存在"""
        result = {
            "status": "success",
            "text": "Operation completed",
        }
        compressed = compress_tool_result("Unknown", json.dumps(result))
        parsed = json.loads(compressed)
        
        assert "data" in parsed
        assert parsed["data"] == {}

    def test_compress_skill_preserves_content(self):
        """Skill 工具：保留完整 data 内容"""
        result = {
            "status": "success",
            "data": {
                "name": "ui-ux-pro-max",
                "base_dir": "skills/ui-ux-pro-max",
                "content": "x" * 2000,
            },
            "text": "Loaded skill",
        }
        compressed = compress_tool_result("Skill", json.dumps(result))
        parsed = json.loads(compressed)

        assert parsed["status"] == "success"
        assert parsed["data"]["name"] == "ui-ux-pro-max"
        assert len(parsed["data"]["content"]) == 2000


class TestInputPreprocessor:
    """InputPreprocessor @file 预处理测试"""

    def test_no_file_mentions(self):
        """无文件引用时不修改输入"""
        result = preprocess_input("Hello world")
        assert result.processed_input == "Hello world"
        assert result.mentioned_files == []
        assert result.truncated_count == 0

    def test_single_file_mention(self):
        """单个文件引用"""
        result = preprocess_input("Please read @src/main.py")
        assert result.mentioned_files == ["src/main.py"]
        assert "system-reminder" in result.processed_input
        assert "this file" in result.processed_input

    def test_multiple_files_with_dedup(self):
        """多个文件引用（去重）"""
        result = preprocess_input("Check @a.py and @b.ts and @a.py again")
        assert result.mentioned_files == ["a.py", "b.ts"]
        assert result.truncated_count == 0
        assert "these files" in result.processed_input

    def test_max_5_files_truncation(self):
        """超过 5 个文件时截断"""
        result = preprocess_input("@a @b @c @d @e @f @g")
        assert len(result.mentioned_files) == 5
        assert result.truncated_count == 2
        assert "2 more" in result.processed_input

    def test_extract_file_mentions_only(self):
        """仅提取文件引用（不注入 reminder）"""
        files = extract_file_mentions("@test.py is important")
        assert files == ["test.py"]

    def test_file_with_nested_path(self):
        """嵌套路径"""
        result = preprocess_input("Look at @src/utils/auth.ts")
        assert result.mentioned_files == ["src/utils/auth.ts"]

    def test_file_with_underscore_and_dash(self):
        """带下划线和破折号的文件名"""
        result = preprocess_input("Check @my_file-name.py")
        assert result.mentioned_files == ["my_file-name.py"]


class TestHistoryManager:
    """HistoryManager 测试"""

    def test_append_user_starts_new_round(self):
        """user 消息开启新轮"""
        hm = HistoryManager()
        hm.append_user("Hello")
        hm.append_assistant("Hi there")
        hm.append_user("Next question")
        
        assert hm.get_rounds_count() == 2
        assert hm.get_message_count() == 3


class DummyFunction:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class DummyToolCall:
    def __init__(self, function):
        self.function = function


class DummyMessage:
    def __init__(self, content=None, tool_calls=None, function_call=None, reasoning_content=None):
        self.content = content
        self.tool_calls = tool_calls
        self.function_call = function_call
        self.reasoning_content = reasoning_content


class DummyChoice:
    def __init__(self, message):
        self.message = message


class DummyRawResponse:
    def __init__(self, choices):
        self.choices = choices


class TestCodeAgentRecovery:
    """CodeAgent 空响应恢复测试"""

    def test_recover_from_tool_calls(self):
        tool_call = DummyToolCall(DummyFunction(name="Read", arguments='{"path": "a.py"}'))
        raw = DummyRawResponse([DummyChoice(DummyMessage(content=None, tool_calls=[tool_call]))])
        recovered, meta = CodeAgent._recover_empty_response(raw)

        assert recovered == 'Action: Read[{"path": "a.py"}]'
        assert meta["source"] == "tool_call"

    def test_recover_from_function_call(self):
        func_call = DummyFunction(name="Search", arguments='{"query": "test"}')
        raw = DummyRawResponse([DummyChoice(DummyMessage(content=None, function_call=func_call))])
        recovered, meta = CodeAgent._recover_empty_response(raw)

        assert recovered == 'Action: Search[{"query": "test"}]'
        assert meta["source"] == "function_call"

    def test_recover_returns_none_when_unavailable(self):
        raw = DummyRawResponse([DummyChoice(DummyMessage(content=None, tool_calls=[], function_call=None))])
        recovered, meta = CodeAgent._recover_empty_response(raw)

        assert recovered is None
        assert meta is None

    def test_recover_from_reasoning_action(self):
        reasoning = 'Thought: x\nAction: Read[{"path": "core/a.py"}]'
        raw = DummyRawResponse([DummyChoice(DummyMessage(content="", reasoning_content=reasoning))])
        recovered, meta = CodeAgent._recover_from_reasoning(raw)

        assert recovered == 'Action: Read[{"path": "core/a.py"}]'
        assert meta["source"] == "reasoning_action"

    def test_recover_from_reasoning_finish(self):
        reasoning = 'Finish[done]'
        raw = DummyRawResponse([DummyChoice(DummyMessage(content="", reasoning_content=reasoning))])
        recovered, meta = CodeAgent._recover_from_reasoning(raw)

        assert recovered == "Finish[done]"
        assert meta["source"] == "reasoning_finish"

    def test_append_tool_compresses_result(self):
        """tool 消息自动压缩"""
        hm = HistoryManager()
        entries = [{"path": f"file{i}.txt", "type": "file"} for i in range(20)]
        raw_result = json.dumps({
            "status": "success",
            "data": {"entries": entries},
            "stats": {"total_entries": 20},
        })
        
        hm.append_tool("LS", raw_result)
        
        messages = hm.get_messages()
        assert len(messages) == 1
        parsed = json.loads(messages[0].content)
        assert len(parsed["data"]["entries"]) == 10  # 压缩到 10 项

    def test_should_compress_below_threshold(self):
        """低于阈值时不触发压缩"""
        config = Config(context_window=200000, compression_threshold=0.8)
        hm = HistoryManager(config=config)
        hm.append_user("Hello")
        hm.append_assistant("Hi")
        hm.append_user("Test")
        
        # last_usage = 0，远低于阈值
        assert hm.should_compress("short input") == False

    def test_should_compress_above_threshold(self):
        """超过阈值时触发压缩"""
        config = Config(context_window=1000, compression_threshold=0.8)  # 小窗口便于测试
        hm = HistoryManager(config=config)
        hm.append_user("Hello")
        hm.append_assistant("Hi")
        hm.append_user("Test")
        hm.update_last_usage(850)  # 接近阈值
        
        # 850 + len("more input")/3 ≈ 853 > 800 (0.8 * 1000)
        assert hm.should_compress("more input") == True

    def test_compact_preserves_min_rounds(self):
        """压缩时保留最少轮次"""
        config = Config(min_retain_rounds=2)
        hm = HistoryManager(config=config)
        
        # 创建 5 轮对话
        for i in range(5):
            hm.append_user(f"Question {i}")
            hm.append_assistant(f"Answer {i}")
        
        assert hm.get_rounds_count() == 5
        
        # 执行压缩
        result = hm.compact()
        
        assert result == True
        assert hm.get_rounds_count() == 2  # 保留最后 2 轮

    def test_serialize_for_prompt(self):
        """序列化为 messages 格式"""
        hm = HistoryManager()
        hm.append_user("Hello")
        hm.append_assistant("Hi there")

        messages = hm.to_messages()

        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hi there"


class TestReadToolMtime:
    """ReadTool mtime 追踪测试"""

    def test_mtime_tracking_detects_change(self, tmp_path):
        """检测文件外部修改"""
        from tools.builtin.read_file import ReadTool
        import time
        
        # 创建测试文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("original content")
        
        tool = ReadTool(project_root=tmp_path)
        
        # 第一次读取
        result1 = tool.run({"path": "test.txt"})
        parsed1 = json.loads(result1)
        assert parsed1["status"] == "success"
        assert "modified_externally" not in parsed1.get("data", {})
        
        # 模拟外部修改（修改 mtime）
        time.sleep(0.01)  # 确保时间戳变化
        test_file.write_text("modified content")
        
        # 第二次读取
        result2 = tool.run({"path": "test.txt"})
        parsed2 = json.loads(result2)
        assert parsed2["status"] == "success"
        assert parsed2["data"].get("modified_externally") == True
        assert "was modified externally" in parsed2.get("text", "")

    def test_mtime_no_change_no_warning(self, tmp_path):
        """文件未修改时无警告"""
        from tools.builtin.read_file import ReadTool
        
        test_file = tmp_path / "stable.txt"
        test_file.write_text("stable content")
        
        tool = ReadTool(project_root=tmp_path)
        
        # 连续读取两次（不修改）
        result1 = tool.run({"path": "stable.txt"})
        result2 = tool.run({"path": "stable.txt"})
        
        parsed2 = json.loads(result2)
        # 第二次读取时 mtime 未变，不应有警告
        assert parsed2["data"].get("modified_externally") is not True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
