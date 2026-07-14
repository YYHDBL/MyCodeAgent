"""Runtime message and history services."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from core.config import Config

MessageRole = Literal["user", "assistant", "summary", "tool"]

class Message(BaseModel):
    """消息类"""
    
    content: str
    role: MessageRole
    timestamp: datetime = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __init__(self, content: str, role: MessageRole, **kwargs):
        super().__init__(
            content=content,
            role=role,
            timestamp=kwargs.get('timestamp', datetime.now()),
            metadata=kwargs.get('metadata', {})
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（OpenAI API格式）"""
        return {
            "role": self.role,
            "content": self.content
        }
    
    def __str__(self) -> str:
        return f"[{self.role}] {self.content}"


class HistoryManager:
    """
    历史记录管理器
    
    管理会话历史，支持：
    - 消息写入（区分 user/assistant/tool/summary）
    - 完整历史读取与持久化
    - 轮次计数
    """

    def __init__(
        self,
        config: Optional[Config] = None,
    ):
        """
        初始化历史管理器
        
        Args:
            config: 配置对象
        """
        self._config = config or Config.from_env()
        
        # 历史消息列表
        self._messages: List[Message] = []
    
    # =========================================================================
    # 公开接口
    # =========================================================================
    
    def append_user(self, content: str, metadata: Optional[dict] = None) -> Message:
        """
        添加用户消息（开启新轮）
        
        Args:
            content: 用户输入内容
            metadata: 可选的元数据
        
        Returns:
            创建的 Message 对象
        """
        msg = Message(
            content=content,
            role="user",
            metadata=metadata or {},
        )
        self._messages.append(msg)
        return msg
    
    def append_assistant(
        self,
        content: str,
        metadata: Optional[dict] = None,
        reasoning_content: Optional[str] = None,
    ) -> Message:
        """
        添加助手消息（Thought/Action 或最终回复）
        
        Args:
            content: 助手输出内容
            metadata: 可选的元数据（如 step、action_type 等）
            reasoning_content: 可选的推理内容（Kimi API 的 reasoning_content）
        
        Returns:
            创建的 Message 对象
        """
        msg = Message(
            content=content,
            role="assistant",
            metadata=metadata or {},
        )
        # 如果有 reasoning_content，存入 metadata 中
        if reasoning_content:
            msg.metadata["reasoning_content"] = reasoning_content
        self._messages.append(msg)
        return msg
    
    def append_tool(
        self,
        tool_name: str,
        observation: str,
        metadata: Optional[dict] = None,
    ) -> Message:
        """
        Add a model-ready tool observation.
        
        Args:
            tool_name: 工具名称（如 "Glob", "Grep", "Read" 等）
            observation: JSON generated once by ``ToolOrchestrator``.
            metadata: 可选的元数据（如 step、tool_name 等）
        
        Returns:
            created message
        """
        metadata = metadata or {}
        # 注意：先展开 metadata，再写 tool_name，确保 tool_name 不被覆盖
        msg = Message(
            content=observation,
            role="tool",
            metadata={
                **metadata,
                "tool_name": tool_name,
            },
        )
        self._messages.append(msg)
        return msg
    
    def append_summary(self, content: str) -> Message:
        """
        添加 Summary 消息（不参与后续压缩）
        
        Args:
            content: Summary 内容
        
        Returns:
            创建的 Message 对象
        """
        msg = Message(
            content=content,
            role="summary",
            metadata={"generated_at": datetime.now().isoformat()},
        )
        self._messages.append(msg)
        return msg
    
    def get_messages(self) -> List[Message]:
        """获取所有历史消息的副本"""
        return self._messages.copy()

    def serialize_messages(self) -> List[Dict[str, Any]]:
        """
        将历史消息序列化为可持久化结构（保留 metadata）。
        """
        items: List[Dict[str, Any]] = []
        for msg in self._messages:
            items.append({
                "role": msg.role,
                "content": msg.content,
                "metadata": (msg.metadata or {}),
            })
        return items

    def load_messages(self, items: List[Dict[str, Any]]) -> None:
        """
        从序列化结构恢复历史消息。
        """
        self._messages = []
        for item in items or []:
            role = item.get("role")
            if role not in {"user", "assistant", "tool", "summary"}:
                continue
            msg = Message(
                content=item.get("content", ""),
                role=role,
                metadata=item.get("metadata", {}) or {},
            )
            self._messages.append(msg)
    
    def get_message_count(self) -> int:
        """获取消息数量"""
        return len(self._messages)
    
    def clear(self):
        """清空历史记录"""
        self._messages.clear()
    
    def get_rounds_count(self) -> int:
        """获取当前轮次数"""
        from runtime.context.rounds import RoundSegmenter

        return len(RoundSegmenter().identify(self._messages))
