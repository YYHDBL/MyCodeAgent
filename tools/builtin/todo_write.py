"""任务列表管理工具 (TodoWrite)

遵循《通用工具响应协议》，返回标准化结构。
设计参考：docs/TodoWriteTool设计文档.md

核心设计：
- 决策留给模型：拆解/调整/取消任务由模型决定
- 低心智负担：模型只提交"当前完整列表"，不做 diff 或 id 维护
- 工具兜底：参数校验、统计、recap 生成与持久化由工具完成
- 展示分离：data 面向模型（结构化），text 面向用户（简洁 UI 展示）
"""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from prompts.tools_prompts.todo_write_prompt import TodoWrite_prompt
from ..base import Tool, ToolParameter, ErrorCode


# 有效的任务状态
VALID_STATUSES = {"pending", "in_progress", "completed", "cancelled"}

# 约束常量
MAX_TODO_COUNT = 10
MAX_CONTENT_LENGTH = 60


class TodoWriteTool(Tool):
    """
    任务列表管理工具，支持声明式覆盖更新
    
    职责：
    - 参数校验（任务数量/长度/状态）
    - 生成简短 recap
    - 生成用户可见的任务清单文本（text 字段）
    - 在任务整体完成时写入 memory/todos/todoList-YYYYMMDD-HHMMSS.md
    """

    def __init__(
        self,
        name: str = "TodoWrite",
        project_root: Path = None,
    ):
        """
        初始化 TodoWrite 工具

        Args:
            name: 工具名称，默认为 "TodoWrite"
            project_root: 项目根目录，用于持久化路径
        """
        super().__init__(
            name=name,
            description=TodoWrite_prompt,
            project_root=project_root,
            working_dir=project_root,
        )
        
        # 会话内任务完成计数（用于文件标题递增 id）
        self._task_counter = 0
        # 会话内持久化文件名（首次持久化时确定）
        self._session_filename = None

    def run(self, parameters: Dict[str, Any]) -> str:
        """
        执行任务列表更新（声明式覆盖）

        Args:
            parameters: 包含以下键的字典：
                - summary: 总体任务概述（必填）
                - todos: 完整任务列表（必填），每项包含 content, status, 可选 id

        Returns:
            JSON 格式的响应字符串（遵循《通用工具响应协议》）
        """
        start_time = time.monotonic()
        params_input = dict(parameters)
        
        summary = parameters.get("summary")
        todos = parameters.get("todos")

        # =========================================
        # 参数校验
        # =========================================
        
        # summary 必填且非空
        if not summary or not isinstance(summary, str) or not summary.strip():
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'summary' is required and must be a non-empty string.",
                params_input=params_input,
            )
        summary = summary.strip()
        
        # todos 必填且为数组
        if todos is None or not isinstance(todos, list):
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'todos' is required and must be an array.",
                params_input=params_input,
            )
        
        # 任务数量上限：10
        if len(todos) > MAX_TODO_COUNT:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message=f"Too many todos. Maximum allowed is {MAX_TODO_COUNT}, got {len(todos)}.",
                params_input=params_input,
            )
        
        # 校验每个 todo 项
        validated_todos = []
        in_progress_count = 0
        
        for idx, item in enumerate(todos):
            if not isinstance(item, dict):
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message=f"Todo item at index {idx} must be an object.",
                    params_input=params_input,
                )
            
            content = item.get("content")
            status = item.get("status")
            todo_id = item.get("id")
            
            # content 必填
            if not content or not isinstance(content, str) or not content.strip():
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message=f"Todo item at index {idx}: 'content' is required and must be a non-empty string.",
                    params_input=params_input,
                )
            content = content.strip()
            
            # content 长度上限：60 字
            if len(content) > MAX_CONTENT_LENGTH:
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message=f"Todo item at index {idx}: 'content' exceeds {MAX_CONTENT_LENGTH} characters (got {len(content)}).",
                    params_input=params_input,
                )
            
            # status 必填且有效
            if not status or status not in VALID_STATUSES:
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message=f"Todo item at index {idx}: 'status' must be one of {sorted(VALID_STATUSES)}.",
                    params_input=params_input,
                )
            
            # 统计 in_progress 数量
            if status == "in_progress":
                in_progress_count += 1
            
            # 生成 id（MVP 阶段每次生成新 id）
            generated_id = f"t{idx + 1}"
            
            validated_todos.append({
                "id": generated_id,
                "content": content,
                "status": status,
            })
        
        # 约束：最多一个 in_progress
        if in_progress_count > 1:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message=f"Only one todo can be 'in_progress' at a time. Found {in_progress_count}.",
                params_input=params_input,
            )
        
        # =========================================
        # 计算统计数据
        # =========================================
        stats_count = {
            "total": len(validated_todos),
            "pending": sum(1 for t in validated_todos if t["status"] == "pending"),
            "in_progress": sum(1 for t in validated_todos if t["status"] == "in_progress"),
            "completed": sum(1 for t in validated_todos if t["status"] == "completed"),
            "cancelled": sum(1 for t in validated_todos if t["status"] == "cancelled"),
        }
        
        # =========================================
        # 生成 recap
        # =========================================
        recap = self._generate_recap(validated_todos, stats_count)
        
        # =========================================
        # 判断是否全部完成，写入持久化
        # =========================================
        all_done = self._check_all_done(validated_todos)
        persisted_path = None
        
        if all_done and validated_todos:
            persisted_path = self._persist_completed_todos(
                todos=validated_todos,
                summary=summary,
                stats_count=stats_count,
            )
        
        # =========================================
        # 计算耗时并构建响应
        # =========================================
        time_ms = int((time.monotonic() - start_time) * 1000)
        
        return self._format_response(
            todos=validated_todos,
            summary=summary,
            recap=recap,
            stats_count=stats_count,
            params_input=params_input,
            time_ms=time_ms,
            persisted_path=persisted_path,
        )

    def _generate_recap(self, todos: List[Dict[str, Any]], stats: Dict[str, int]) -> str:
        """
        生成简短 recap，用于放入上下文末尾

        格式：[done/total] In progress: xxx. Pending: xxx; xxx. Cancelled: xxx.
        
        规则：
        - in_progress: 最多 1 条
        - pending: 最多 3 条
        - cancelled: 最多 2 条
        - completed: 通常不复述
        - 总长度 < 300 字
        """
        done = stats["completed"] + stats["cancelled"]
        total = stats["total"]
        
        parts = [f"[{done}/{total}]"]
        
        # In progress（最多 1 个）
        in_progress_items = [t["content"] for t in todos if t["status"] == "in_progress"]
        if in_progress_items:
            parts.append(f"In progress: {in_progress_items[0]}.")
        else:
            parts.append("In progress: None.")
        
        # Pending（最多 3 个）
        pending_items = [t["content"] for t in todos if t["status"] == "pending"][:3]
        if pending_items:
            parts.append(f"Pending: {'; '.join(pending_items)}.")
        
        # Cancelled（最多 2 个）
        cancelled_items = [t["content"] for t in todos if t["status"] == "cancelled"][:2]
        if cancelled_items:
            parts.append(f"Cancelled: {'; '.join(cancelled_items)}.")
        
        return " ".join(parts)

    def _check_all_done(self, todos: List[Dict[str, Any]]) -> bool:
        """检查是否所有任务都已完成或取消"""
        if not todos:
            return False
        return all(t["status"] in ("completed", "cancelled") for t in todos)

    def _persist_completed_todos(
        self,
        todos: List[Dict[str, Any]],
        summary: str,
        stats_count: Dict[str, int],
    ) -> str:
        """
        持久化已完成的任务列表到 Markdown 文件
        
        文件位置：memory/todos/todoList-YYYYMMDD-HHMMSS.md（会话内复用）
        文件标题：# task{递增id}-YYYYMMDD-HHMMSS
        
        Returns:
            写入的文件路径（相对路径），失败返回 None
        """
        try:
            # 递增任务计数器
            self._task_counter += 1
            
            # 生成时间戳（用于任务块标题）
            now = datetime.now()
            timestamp = now.strftime("%Y%m%d-%H%M%S")
            
            # 确定目录路径
            if self._project_root:
                base_dir = Path(self._project_root) / "memory" / "todos"
            else:
                base_dir = Path("memory") / "todos"
            
            # 创建目录（如果不存在）
            base_dir.mkdir(parents=True, exist_ok=True)
            
            # 会话内文件名（首次持久化时确定）
            if not self._session_filename:
                session_ts = timestamp
                self._session_filename = f"todoList-{session_ts}.md"
            filename = self._session_filename
            filepath = base_dir / filename
            
            # 构建文件内容
            lines = []
            
            # 标题
            lines.append(f"# task{self._task_counter}-{timestamp}")
            lines.append("")
            
            # 总任务概述
            lines.append(f"总任务概述：{summary}")
            lines.append("")
            
            # 已完成的任务
            completed_items = [t for t in todos if t["status"] == "completed"]
            if completed_items:
                lines.append(f"[{len(completed_items)}/{stats_count['total']}] Completed: 完成的任务.")
                for item in completed_items:
                    lines.append(f"- {item['content']}")
                lines.append("")
            
            # 已取消的任务
            cancelled_items = [t for t in todos if t["status"] == "cancelled"]
            if cancelled_items:
                lines.append(f"[{len(cancelled_items)}/{stats_count['total']}] Cancelled: 取消的任务.")
                for item in cancelled_items:
                    lines.append(f"- ~~{item['content']}~~")
                lines.append("")
            
            # 写入文件（会话内追加）
            content = "\n".join(lines)
            if filepath.exists():
                with filepath.open("a", encoding="utf-8") as f:
                    f.write("\n\n")
                    f.write(content)
            else:
                filepath.write_text(content, encoding="utf-8")
            
            # 返回相对路径
            return f"memory/todos/{filename}"
            
        except Exception:
            # 持久化失败不影响主流程
            return None

    def _format_response(
        self,
        todos: List[Dict[str, Any]],
        summary: str,
        recap: str,
        stats_count: Dict[str, int],
        params_input: Dict[str, Any],
        time_ms: int,
        persisted_path: str = None,
    ) -> str:
        """
        构建标准化响应（遵循《通用工具响应协议》）

        - data: 面向模型（结构化）
        - text: 面向用户（简洁 UI 展示）
        """
        # =========================================
        # 构建 data（模型侧）
        # =========================================
        data = {
            "todos": todos,
            "recap": recap,
            "summary": summary,
        }
        
        
        # =========================================
        # 构建 text（用户侧 UI 展示）
        # =========================================
        lines = []
        lines.append("--- TODO UPDATE ---")
        
        for todo in todos:
            status_icon = {
                "pending": "[ ]",
                "in_progress": "[▶]",
                "completed": "[✓]",
                "cancelled": "[~]",
            }.get(todo["status"], "[ ]")
            lines.append(f"{status_icon} {todo['content']}")
        
        lines.append("-------------------")
        
        text = "\n".join(lines)
        
        # =========================================
        # 构建 extra_stats
        # =========================================
        extra_stats = stats_count.copy()
        
        return self.create_success_response(
            data=data,
            text=text,
            params_input=params_input,
            time_ms=time_ms,
            extra_stats=extra_stats,
        )

    def get_parameters(self) -> List[ToolParameter]:
        """获取工具参数定义"""
        return [
            ToolParameter(
                name="summary",
                type="string",
                description="Overall task summary (required by the model).",
                required=True,
            ),
            ToolParameter(
                name="todos",
                type="array",
                description=(
                    "The full todo list (overwrites existing). "
                    "Each item: {content: string, status: pending|in_progress|completed|cancelled, id?: string}. "
                    f"Max {MAX_TODO_COUNT} items, each content max {MAX_CONTENT_LENGTH} chars."
                ),
                required=True,
            ),
        ]
