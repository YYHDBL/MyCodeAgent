"""上下文工程模块测试

测试内容（D7.8）：
1. 工具输出统一截断规则
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


class TestToolOutputTruncation:
    """统一截断策略测试（全工具通用）"""

    def test_small_output_not_truncated(self):
        """小输出保持原样"""
        result = {
            "status": "success",
            "data": {"message": "ok"},
        }
        raw = json.dumps(result)
        output = compress_tool_result("AnyTool", raw)
        assert output == raw

    def test_large_output_truncated(self):
        """超过阈值时触发统一截断"""
        content = "x" * (60 * 1024)  # 60KB
        result = {
            "status": "success",
            "data": {"content": content},
        }
        raw = json.dumps(result)
        output = compress_tool_result("AnyTool", raw)
        parsed = json.loads(output)

        assert parsed["status"] == "partial"
        assert parsed["data"]["truncated"] is True
        assert parsed["data"]["truncation"]["original_bytes"] > 50 * 1024
        assert "preview" in parsed["data"]

    def test_skip_truncation_flag(self):
        """context.truncation_skip 生效"""
        content = "x" * (60 * 1024)
        result = {
            "status": "success",
            "data": {"content": content},
            "context": {"truncation_skip": True},
        }
        raw = json.dumps(result)
        output = compress_tool_result("AnyTool", raw)
        assert output == raw


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
    def __init__(self, function, call_id="call_1"):
        self.function = function
        self.id = call_id


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


class TestCodeAgentToolCalls:
    """CodeAgent tool_calls 提取测试"""

    def test_extract_tool_calls(self):
        tool_call = DummyToolCall(DummyFunction(name="Read", arguments='{"path": "a.py"}'), call_id="call_1")
        raw = DummyRawResponse([DummyChoice(DummyMessage(content=None, tool_calls=[tool_call]))])
        calls = CodeAgent._extract_tool_calls(raw)

        assert calls == [{"id": "call_1", "name": "Read", "arguments": '{"path": "a.py"}'}]

    def test_extract_tool_calls_from_function_call(self):
        func_call = DummyFunction(name="Search", arguments='{"query": "test"}')
        raw = DummyRawResponse([DummyChoice(DummyMessage(content=None, function_call=func_call))])
        calls = CodeAgent._extract_tool_calls(raw)

        assert calls == [{"id": None, "name": "Search", "arguments": '{"query": "test"}'}]

    def test_append_tool_compresses_result(self):
        """tool 消息自动截断（小结果保持原样）"""
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
        assert parsed["data"]["entries"] == entries
        assert parsed["status"] == "success"

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


class TestLongHorizonCompression:
    """长程任务上下文压缩测试"""

    @staticmethod
    def _append_round(hm: HistoryManager, idx: int):
        hm.append_user(f"Question {idx}")
        hm.append_assistant(
            "",
            metadata={
                "action_type": "tool_call",
                "tool_calls": [
                    {"id": f"call_{idx}", "name": "LS", "arguments": {"path": "."}}
                ],
            },
        )
        tool_result = json.dumps({
            "status": "success",
            "data": {"entries": [{"path": f"file_{idx}.txt", "type": "file"}]},
            "stats": {"total_entries": 1},
            "context": {"cwd": "."},
        })
        hm.append_tool("LS", tool_result, metadata={"tool_call_id": f"call_{idx}"})
        hm.append_assistant(f"Answer {idx}")

    def test_compact_inserts_summary_and_retains_recent_rounds(self):
        """压缩后插入 Summary，保留最近轮次与工具对"""
        config = Config(min_retain_rounds=2, tool_message_format="strict")
        summary_generator = lambda msgs: f"summary({len(msgs)})"
        hm = HistoryManager(config=config, summary_generator=summary_generator)

        for i in range(6):
            self._append_round(hm, i)

        info = hm.compact(return_info=True)

        assert info.get("compressed") is True
        assert hm.get_rounds_count() == 2

        messages = hm.get_messages()
        summaries = [m for m in messages if m.role == "summary"]
        assert len(summaries) == 1
        assert "summary(" in summaries[0].content

        tool_msgs = [m for m in messages if m.role == "tool"]
        assert len(tool_msgs) == 2
        assert all((m.metadata or {}).get("tool_call_id") for m in tool_msgs)

        serialized = hm.to_messages()
        tool_serialized = [m for m in serialized if m.get("role") == "tool"]
        assert len(tool_serialized) == 2
        assert all(m.get("tool_call_id") for m in tool_serialized)

        summary_serialized = [
            m for m in serialized
            if m.get("role") == "system"
            and "Archived History Summary" in m.get("content", "")
        ]
        assert summary_serialized


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
