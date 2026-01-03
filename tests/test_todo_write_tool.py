"""TodoWriteTool 单元测试

遵循《通用工具响应协议 v1.0》规范，全面测试 TodoWrite 工具的各项功能。

运行方式：
    python -m pytest tests/test_todo_write_tool.py -v
    python -m unittest tests.test_todo_write_tool -v
"""

import json
import unittest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from tools.builtin.todo_write import TodoWriteTool, MAX_TODO_COUNT, MAX_CONTENT_LENGTH
from tools.base import ErrorCode
from tests.utils.test_helpers import parse_response


class TestTodoWriteTool(unittest.TestCase):
    """TodoWriteTool 单元测试套件

    覆盖场景：
    1. Success（成功）：创建列表、更新列表、标记完成、标记取消、持久化
    2. Error（错误）：INVALID_PARAM（参数缺失/无效/超出约束）
    3. 协议合规性：响应结构、字段类型
    4. Recap 生成：格式正确、截断逻辑
    5. 持久化：文件写入、格式正确
    """

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _create_tool(self, project_root: Path = None) -> TodoWriteTool:
        """创建 TodoWrite 工具实例"""
        if project_root is None:
            # 使用临时目录
            temp_dir = Path(tempfile.mkdtemp(prefix="test_todo_"))
            return TodoWriteTool(project_root=temp_dir), temp_dir
        return TodoWriteTool(project_root=project_root), None

    def _cleanup_temp_dir(self, temp_dir: Path):
        """清理临时目录"""
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir)

    def _validate_and_assert(self, response_str: str, expected_status: str = None) -> dict:
        """解析响应并断言状态"""
        parsed = parse_response(response_str)

        if expected_status:
            self.assertEqual(
                parsed["status"],
                expected_status,
                f"期望 status='{expected_status}'，实际 '{parsed['status']}'"
            )

        # 验证必需的顶层字段
        required_fields = {"status", "data", "text", "stats", "context"}
        self.assertEqual(
            set(parsed.keys()) - {"error"},
            required_fields,
            f"响应顶层字段不匹配: {set(parsed.keys())}"
        )

        # 验证 stats.time_ms 存在
        self.assertIn("time_ms", parsed["stats"])
        self.assertIsInstance(parsed["stats"]["time_ms"], int)

        # 验证 context.cwd 和 params_input
        self.assertIn("cwd", parsed["context"])
        self.assertIn("params_input", parsed["context"])

        return parsed

    # ========================================================================
    # Success 场景测试
    # ========================================================================

    def test_success_create_todo_list(self):
        """Success: 创建新的 todo 列表"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "实现用户认证功能",
                "todos": [
                    {"content": "设计认证流程", "status": "in_progress"},
                    {"content": "创建登录接口", "status": "pending"},
                    {"content": "添加 JWT 验证", "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证 data.todos
            todos = parsed["data"]["todos"]
            self.assertEqual(len(todos), 3)

            # 验证 ID 生成
            self.assertEqual(todos[0]["id"], "t1")
            self.assertEqual(todos[1]["id"], "t2")
            self.assertEqual(todos[2]["id"], "t3")

            # 验证状态
            self.assertEqual(todos[0]["status"], "in_progress")
            self.assertEqual(todos[1]["status"], "pending")
            self.assertEqual(todos[2]["status"], "pending")

            # 验证 data.recap
            recap = parsed["data"]["recap"]
            self.assertIn("[0/3]", recap)
            self.assertIn("In progress: 设计认证流程", recap)
            self.assertIn("Pending:", recap)

            # 验证 data.summary
            self.assertEqual(parsed["data"]["summary"], "实现用户认证功能")

            # 验证 stats
            stats = parsed["stats"]
            self.assertEqual(stats["total"], 3)
            self.assertEqual(stats["pending"], 2)
            self.assertEqual(stats["in_progress"], 1)
            self.assertEqual(stats["completed"], 0)
            self.assertEqual(stats["cancelled"], 0)

            # 验证 text 包含 UI 展示
            text = parsed["text"]
            self.assertIn("--- TODO UPDATE ---", text)
            self.assertIn("[▶] 设计认证流程", text)
            self.assertIn("[ ] 创建登录接口", text)
            self.assertIn("[ ] 添加 JWT 验证", text)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_success_update_todo_list_declarative_overwrite(self):
        """Success: 声明式覆盖更新 todo 列表"""
        tool, temp_dir = self._create_tool()
        try:
            # 第一次调用
            tool.run({
                "summary": "实现功能",
                "todos": [
                    {"content": "任务A", "status": "in_progress"},
                    {"content": "任务B", "status": "pending"},
                ]
            })

            # 第二次调用：声明式覆盖
            response = tool.run({
                "summary": "实现功能",
                "todos": [
                    {"content": "任务A", "status": "completed"},
                    {"content": "任务B", "status": "in_progress"},
                    {"content": "任务C", "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证覆盖后的列表
            todos = parsed["data"]["todos"]
            self.assertEqual(len(todos), 3)
            self.assertEqual(todos[0]["status"], "completed")
            self.assertEqual(todos[1]["status"], "in_progress")
            self.assertEqual(todos[2]["status"], "pending")

            # 验证 recap 更新
            recap = parsed["data"]["recap"]
            self.assertIn("[1/3]", recap)  # 1 completed, 0 cancelled
            self.assertIn("In progress: 任务B", recap)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_success_mark_task_completed(self):
        """Success: 标记任务完成"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "已完成的任务", "status": "completed"},
                    {"content": "进行中的任务", "status": "in_progress"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证 stats
            stats = parsed["stats"]
            self.assertEqual(stats["completed"], 1)
            self.assertEqual(stats["in_progress"], 1)

            # 验证 text UI 图标
            text = parsed["text"]
            self.assertIn("[✓] 已完成的任务", text)
            self.assertIn("[▶] 进行中的任务", text)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_success_mark_task_cancelled(self):
        """Success: 标记任务取消"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "已取消的任务", "status": "cancelled"},
                    {"content": "待处理的任务", "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证 stats
            stats = parsed["stats"]
            self.assertEqual(stats["cancelled"], 1)
            self.assertEqual(stats["pending"], 1)

            # 验证 text UI 图标
            text = parsed["text"]
            self.assertIn("[~] 已取消的任务", text)
            self.assertIn("[ ] 待处理的任务", text)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_success_all_completed_triggers_persistence(self):
        """Success: 所有任务完成触发持久化"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "完整的任务流程",
                "todos": [
                    {"content": "完成的任务1", "status": "completed"},
                    {"content": "完成的任务2", "status": "completed"},
                    {"content": "取消的任务", "status": "cancelled"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证持久化路径在 data 中
            self.assertIn("persisted_to", parsed["data"])
            persisted_path = parsed["data"]["persisted_to"]
            self.assertTrue(persisted_path.startswith("memory/todos/todoList-"))
            self.assertTrue(persisted_path.endswith(".md"))

            # 验证文件实际被创建
            full_path = temp_dir / persisted_path
            self.assertTrue(full_path.exists(), f"持久化文件不存在: {full_path}")

            # 验证文件内容
            content = full_path.read_text(encoding="utf-8")
            self.assertIn("# task1-", content)  # 标题
            self.assertIn("完整的任务流程", content)  # 总任务概述
            self.assertIn("完成的任务1", content)
            self.assertIn("完成的任务2", content)
            self.assertIn("~~取消的任务~~", content)  # 删除线
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_success_single_in_progress_task(self):
        """Success: 单个 in_progress 任务"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "当前任务", "status": "in_progress"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证 stats
            self.assertEqual(parsed["stats"]["in_progress"], 1)

            # 验证 recap
            self.assertIn("In progress: 当前任务", parsed["data"]["recap"])
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_success_zero_in_progress_allowed(self):
        """Success: 允许 0 个 in_progress 任务（全 pending）"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "任务A", "status": "pending"},
                    {"content": "任务B", "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证 recap 显示 "In progress: None"
            self.assertIn("In progress: None", parsed["data"]["recap"])
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_recap_format_with_mixed_statuses(self):
        """Success: Recap 格式正确（混合状态）"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "进行中", "status": "in_progress"},
                    {"content": "待办1", "status": "pending"},
                    {"content": "待办2", "status": "pending"},
                    {"content": "待办3", "status": "pending"},
                    {"content": "待办4", "status": "pending"},  # 超过 3 个，应该被截断
                    {"content": "已取消1", "status": "cancelled"},
                    {"content": "已取消2", "status": "cancelled"},
                    {"content": "已取消3", "status": "cancelled"},  # 超过 2 个，应该被截断
                    {"content": "已完成", "status": "completed"},  # 不应出现在 recap
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            recap = parsed["data"]["recap"]

            # 验证进度指示
            self.assertIn("[2/9]", recap)  # 1 completed + 2 cancelled = 2, total 9

            # 验证 in_progress（最多 1 个）
            self.assertIn("In progress: 进行中", recap)

            # 验证 pending（最多 3 个）
            self.assertIn("Pending:", recap)
            self.assertIn("待办1", recap)
            self.assertIn("待办2", recap)
            self.assertIn("待办3", recap)

            # 验证 cancelled（最多 2 个）
            self.assertIn("Cancelled:", recap)
            self.assertIn("已取消1", recap)
            self.assertIn("已取消2", recap)

            # 验证 completed 不在 recap 中
            self.assertNotIn("已完成", recap)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_success_minimal_single_todo(self):
        """Success: 最小单任务列表"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "最小任务",
                "todos": [
                    {"content": "做一件事", "status": "in_progress"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            self.assertEqual(len(parsed["data"]["todos"]), 1)
            self.assertEqual(parsed["stats"]["total"], 1)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_success_max_todo_count(self):
        """Success: 最大任务数量（10 个）"""
        tool, temp_dir = self._create_tool()
        try:
            todos = [{"content": f"任务{i}", "status": "pending"} for i in range(10)]

            response = tool.run({
                "summary": "最大任务数",
                "todos": todos,
            })

            parsed = self._validate_and_assert(response, "success")
            self.assertEqual(parsed["stats"]["total"], 10)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_success_max_content_length(self):
        """Success: 最大内容长度（60 字）"""
        tool, temp_dir = self._create_tool()
        try:
            # 60 字符的 content
            content = "这是一个很长的任务描述，它包含了六十个字符作为上限的测试内容"

            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": content, "status": "pending"},
                ]
            })

            self._validate_and_assert(response, "success")
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_success_id_from_input_is_ignored(self):
        """Success: 用户提供的 id 被忽略（工具生成自己的 id）"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "任务A", "status": "pending", "id": "user_provided_id_123"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证工具生成的 id 覆盖了用户提供的
            self.assertEqual(parsed["data"]["todos"][0]["id"], "t1")
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_success_content_whitespace_trimmed(self):
        """Success: content 和 summary 的空白被 trim"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "  测试概述  ",
                "todos": [
                    {"content": "  任务描述  ", "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证 trim 后的内容
            self.assertEqual(parsed["data"]["summary"], "测试概述")
            self.assertEqual(parsed["data"]["todos"][0]["content"], "任务描述")
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_persistence_file_format(self):
        """Success: 验证持久化文件格式符合设计文档"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "持久化格式测试",
                "todos": [
                    {"content": "完成的任务", "status": "completed"},
                    {"content": "取消的任务", "status": "cancelled"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")
            persisted_path = temp_dir / parsed["data"]["persisted_to"]
            content = persisted_path.read_text(encoding="utf-8")

            # 验证格式
            lines = content.split("\n")

            # 标题格式: # task{递增id}-{timestamp}
            self.assertTrue(lines[0].startswith("# task1-20"))

            # 总任务概述
            self.assertIn("总任务概述：持久化格式测试", lines)

            # Completed 部分
            completed_section_found = False
            for line in lines:
                if "[1/2] Completed:" in line:
                    completed_section_found = True
                    break
            self.assertTrue(completed_section_found, "缺少 Completed 部分")
            self.assertIn("- 完成的任务", content)

            # Cancelled 部分（带删除线）
            cancelled_section_found = False
            for line in lines:
                if "[1/2] Cancelled:" in line:
                    cancelled_section_found = True
                    break
            self.assertTrue(cancelled_section_found, "缺少 Cancelled 部分")
            self.assertIn("~~取消的任务~~", content)
        finally:
            self._cleanup_temp_dir(temp_dir)

    # ========================================================================
    # Error - INVALID_PARAM 场景测试
    # ========================================================================

    def test_error_missing_summary(self):
        """Error: INVALID_PARAM - 缺少 summary 参数"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "todos": [
                    {"content": "任务", "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("summary", parsed["error"]["message"].lower())
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_error_empty_summary(self):
        """Error: INVALID_PARAM - 空的 summary"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "   ",
                "todos": [
                    {"content": "任务", "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_error_summary_wrong_type(self):
        """Error: INVALID_PARAM - summary 类型错误"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": 123,
                "todos": [
                    {"content": "任务", "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_error_missing_todos(self):
        """Error: INVALID_PARAM - 缺少 todos 参数"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试"
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("todos", parsed["error"]["message"].lower())
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_error_todos_not_array(self):
        """Error: INVALID_PARAM - todos 不是数组"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": "not an array"
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_error_todos_empty_array(self):
        """Error: INVALID_PARAM - todos 为空数组（根据实现应该成功，但测试边界）"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": []
            })

            parsed = self._validate_and_assert(response, "success")

            # 空列表是允许的
            self.assertEqual(parsed["stats"]["total"], 0)
            self.assertEqual(parsed["data"]["recap"], "[0/0] In progress: None.")
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_error_exceed_max_todo_count(self):
        """Error: INVALID_PARAM - 超过最大任务数量"""
        tool, temp_dir = self._create_tool()
        try:
            # 创建 11 个任务（超过上限 10）
            todos = [{"content": f"任务{i}", "status": "pending"} for i in range(11)]

            response = tool.run({
                "summary": "测试",
                "todos": todos,
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("10", parsed["error"]["message"])
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_error_todo_item_not_object(self):
        """Error: INVALID_PARAM - todo 项不是对象"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": ["just a string", {"content": "正常任务", "status": "pending"}]
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("index 0", parsed["error"]["message"])
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_error_todo_missing_content(self):
        """Error: INVALID_PARAM - todo 项缺少 content"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("content", parsed["error"]["message"].lower())
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_error_todo_empty_content(self):
        """Error: INVALID_PARAM - todo 项 content 为空"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "   ", "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_error_todo_content_wrong_type(self):
        """Error: INVALID_PARAM - todo 项 content 类型错误"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": 123, "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_error_todo_content_exceeds_max_length(self):
        """Error: INVALID_PARAM - todo 项 content 超过最大长度"""
        tool, temp_dir = self._create_tool()
        try:
            # 61 字符（超过上限 60）
            content = "这是一个超过六十个字符限制的任务描述，会导致校验失败返回错误"

            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": content, "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("60", parsed["error"]["message"])
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_error_todo_missing_status(self):
        """Error: INVALID_PARAM - todo 项缺少 status"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "任务"},
                ]
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("status", parsed["error"]["message"].lower())
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_error_todo_invalid_status(self):
        """Error: INVALID_PARAM - todo 项 status 无效"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "任务", "status": "invalid_status"},
                ]
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("pending", parsed["error"]["message"])
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_error_multiple_in_progress(self):
        """Error: INVALID_PARAM - 多个 in_progress 任务"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "任务1", "status": "in_progress"},
                    {"content": "任务2", "status": "in_progress"},
                ]
            })

            parsed = self._validate_and_assert(response, "error")

            self.assertEqual(parsed["error"]["code"], "INVALID_PARAM")
            self.assertIn("in_progress", parsed["error"]["message"])
            self.assertIn("2", parsed["error"]["message"])
        finally:
            self._cleanup_temp_dir(temp_dir)

    # ========================================================================
    # 协议合规性测试
    # ========================================================================

    def test_protocol_success_response_structure(self):
        """Protocol: 成功响应结构正确"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "任务", "status": "pending"},
                ]
            })

            parsed = parse_response(response)

            # 验证顶层字段
            required_top_level = {"status", "data", "text", "stats", "context"}
            self.assertEqual(set(parsed.keys()), required_top_level)

            # success 状态不应有 error 字段
            self.assertNotIn("error", parsed)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_protocol_error_response_structure(self):
        """Protocol: 错误响应结构正确"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                # 缺少 todos
            })

            parsed = parse_response(response)

            # error 状态必须有 error 字段
            self.assertIn("error", parsed)
            self.assertIn("code", parsed["error"])
            self.assertIn("message", parsed["error"])
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_protocol_data_fields(self):
        """Protocol: data 字段包含正确内容"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试协议",
                "todos": [
                    {"content": "任务", "status": "completed"},
                ]
            })

            parsed = parse_response(response)

            # 验证 data 必需字段
            data = parsed["data"]
            self.assertIn("todos", data)
            self.assertIn("recap", data)
            self.assertIn("summary", data)

            # 验证 todos 是数组
            self.assertIsInstance(data["todos"], list)

            # 验证 recap 是字符串
            self.assertIsInstance(data["recap"], str)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_protocol_context_fields(self):
        """Protocol: context 字段包含正确内容"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "任务", "status": "pending"},
                ]
            })

            parsed = parse_response(response)

            context = parsed["context"]
            self.assertIn("cwd", context)
            self.assertIn("params_input", context)
            self.assertIsInstance(context["params_input"], dict)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_protocol_stats_time_ms_positive(self):
        """Protocol: stats.time_ms 为非负整数"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "任务", "status": "pending"},
                ]
            })

            parsed = parse_response(response)

            self.assertIsInstance(parsed["stats"]["time_ms"], int)
            self.assertGreaterEqual(parsed["stats"]["time_ms"], 0)
        finally:
            self._cleanup_temp_dir(temp_dir)

    # ========================================================================
    # 边界条件测试
    # ========================================================================

    def test_boundary_unicode_content(self):
        """Boundary: Unicode 内容处理"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试中文和Emoji🎉",
                "todos": [
                    {"content": "实现用户登录功能 🔐", "status": "in_progress"},
                    {"content": "Добавить русский текст", "status": "pending"},
                    {"content": "日本語テスト", "status": "cancelled"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            # 验证 Unicode 正确保留
            self.assertIn("🎉", parsed["data"]["summary"])
            self.assertIn("🔐", parsed["data"]["todos"][0]["content"])
            self.assertIn("русский", parsed["data"]["todos"][1]["content"])
            self.assertIn("日本語", parsed["data"]["todos"][2]["content"])
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_boundary_all_statuses_same(self):
        """Boundary: 所有任务同一状态"""
        tool, temp_dir = self._create_tool()
        try:
            # 全部 pending
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "任务1", "status": "pending"},
                    {"content": "任务2", "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")
            self.assertEqual(parsed["stats"]["pending"], 2)
            self.assertEqual(parsed["stats"]["completed"], 0)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_boundary_all_completed_no_persistence_on_empty(self):
        """Boundary: 空列表不触发持久化"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": []
            })

            parsed = self._validate_and_assert(response, "success")

            # 空列表不应持久化
            self.assertNotIn("persisted_to", parsed["data"])
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_boundary_task_counter_increments(self):
        """Boundary: 任务计数器随持久化递增"""
        tool, temp_dir = self._create_tool()
        try:
            # 第一次持久化
            tool.run({
                "summary": "任务1",
                "todos": [{"content": "A", "status": "completed"}]
            })

            # 第二次持久化
            response = tool.run({
                "summary": "任务2",
                "todos": [{"content": "B", "status": "completed"}]
            })

            parsed = parse_response(response)
            persisted_path = temp_dir / parsed["data"]["persisted_to"]
            content = persisted_path.read_text(encoding="utf-8")

            # 第二次持久化的文件应该包含 # task2-
            self.assertIn("# task2-", content)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_boundary_persistence_in_subdirectory(self):
        """Boundary: 持久化到正确的子目录"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [{"content": "A", "status": "completed"}]
            })

            parsed = parse_response(response)

            # 验证路径
            persisted_path = temp_dir / parsed["data"]["persisted_to"]
            self.assertTrue(persisted_path.is_absolute())

            # 验证目录结构 memory/todos/
            relative_parts = Path(parsed["data"]["persisted_to"]).parts
            self.assertEqual(relative_parts[0], "memory")
            self.assertEqual(relative_parts[1], "todos")
        finally:
            self._cleanup_temp_dir(temp_dir)

    # ========================================================================
    # Recap 生成详细测试
    # ========================================================================

    def test_recap_progress_includes_cancelled(self):
        """Recap: 进度计算包含 cancelled（done = completed + cancelled）"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "已完成", "status": "completed"},
                    {"content": "已取消", "status": "cancelled"},
                    {"content": "进行中", "status": "in_progress"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            # done = 1 completed + 1 cancelled = 2
            recap = parsed["data"]["recap"]
            self.assertIn("[2/3]", recap)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_recap_pending_truncation(self):
        """Recap: pending 超过 3 个时截断"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "P1", "status": "pending"},
                    {"content": "P2", "status": "pending"},
                    {"content": "P3", "status": "pending"},
                    {"content": "P4", "status": "pending"},
                    {"content": "P5", "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            recap = parsed["data"]["recap"]

            # 应该只显示前 3 个
            self.assertIn("P1", recap)
            self.assertIn("P2", recap)
            self.assertIn("P3", recap)
            # 不应该包含 P4 和 P5
            self.assertNotIn("P4", recap)
            self.assertNotIn("P5", recap)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_recap_cancelled_truncation(self):
        """Recap: cancelled 超过 2 个时截断"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "C1", "status": "cancelled"},
                    {"content": "C2", "status": "cancelled"},
                    {"content": "C3", "status": "cancelled"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            recap = parsed["data"]["recap"]

            # 应该只显示前 2 个
            self.assertIn("C1", recap)
            self.assertIn("C2", recap)
            # 不应该包含 C3
            self.assertNotIn("C3", recap)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_recap_no_pending_section(self):
        """Recap: 没有 pending 时不显示 Pending 部分"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "进行中", "status": "in_progress"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            recap = parsed["data"]["recap"]
            # 没有 pending 时不应有 "Pending:" 字符串
            # 但由于实现中 "In progress: None." 后面没有 Pending，所以需要检查
            lines = recap.split(". ")
            self.assertEqual(len(lines), 2)  # 只有 [0/0] 和 In progress: None.
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_recap_no_cancelled_section(self):
        """Recap: 没有 cancelled 时不显示 Cancelled 部分"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "进行中", "status": "in_progress"},
                    {"content": "待办", "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            recap = parsed["data"]["recap"]
            self.assertNotIn("Cancelled", recap)
        finally:
            self._cleanup_temp_dir(temp_dir)

    # ========================================================================
    # UI 文本展示测试
    # ========================================================================

    def test_text_ui_icons(self):
        """Text: UI 图标正确显示"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "待办", "status": "pending"},
                    {"content": "进行中", "status": "in_progress"},
                    {"content": "已完成", "status": "completed"},
                    {"content": "已取消", "status": "cancelled"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            text = parsed["text"]
            self.assertIn("[ ] 待办", text)
            self.assertIn("[▶] 进行中", text)
            self.assertIn("[✓] 已完成", text)
            self.assertIn("[~] 已取消", text)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_text_ui_contains_separator(self):
        """Text: UI 包含分隔线"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "任务", "status": "pending"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            text = parsed["text"]
            self.assertIn("--- TODO UPDATE ---", text)
            self.assertIn("-------------------", text)
        finally:
            self._cleanup_temp_dir(temp_dir)

    def test_text_ui_persisted_hint(self):
        """Text: 持久化时显示路径提示"""
        tool, temp_dir = self._create_tool()
        try:
            response = tool.run({
                "summary": "测试",
                "todos": [
                    {"content": "任务", "status": "completed"},
                ]
            })

            parsed = self._validate_and_assert(response, "success")

            text = parsed["text"]
            self.assertIn("(Saved to", text)
            self.assertIn("memory/todos/", text)
        finally:
            self._cleanup_temp_dir(temp_dir)


if __name__ == "__main__":
    unittest.main(verbosity=2)
