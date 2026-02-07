"""历史记录管理器

根据《上下文工程方案》实现历史记录的管理、压缩和轮次控制。

核心职责（D2）：
1. 轮内写入：在 ReAct 每一步同步写入 assistant（Thought/Action）与 tool（截断结果）消息
2. 轮间管理：提供 append/get/compact 接口；基于 user 消息分轮
3. 截断策略：调用 ObservationTruncator；统一截断工具输出并落盘保存
4. 触发 Summary 生成并插入 summary 消息

规则要点：
- A4: 只压缩 user/assistant/tool 消息，summary 不参与压缩
- A4: tool_use/tool_result 必须成对保留，不得拆分
- A4: 保留区至少 min_retain_rounds 轮，压缩边界对齐完整轮次
- A6: 压缩触发条件：estimated_total >= 0.8 * context_window 且消息数 >= 3
"""

import json
import logging
from typing import List, Optional, Callable, Tuple, Dict, Any
from datetime import datetime

from ..message import Message
from ..config import Config
from .observation_truncator import truncate_observation


class HistoryManager:
    """
    历史记录管理器
    
    管理会话历史，支持：
    - 消息写入（区分 user/assistant/tool/summary）
    - 轮次边界识别（user 消息开启新轮）
    - 压缩触发检测
    - 历史压缩（保留最近 N 轮 + Summary）
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        summary_generator: Optional[Callable[[List[Message]], Optional[str]]] = None,
    ):
        """
        初始化历史管理器
        
        Args:
            config: 配置对象，包含 context_window、compression_threshold 等
            summary_generator: Summary 生成回调函数，接收待压缩的消息列表，返回 Summary 文本
                              如果为 None，则压缩时不生成 Summary，仅做截断
        """
        self._config = config or Config.from_env()
        self._summary_generator = summary_generator
        
        # 历史消息列表
        self._messages: List[Message] = []
        
        # 上一次 API 调用的 token 使用量（精确值）
        self._last_usage_tokens: int = 0
        # 会话累计 token 使用量
        self._total_usage_tokens: int = 0
    
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
        raw_result: str,
        metadata: Optional[dict] = None,
        project_root: Optional[str] = None,
    ) -> Message:
        """
        添加工具消息（截断后写入）
        
        Args:
            tool_name: 工具名称（如 "LS", "Grep", "Read" 等）
            raw_result: 工具返回的原始 JSON 字符串
            metadata: 可选的元数据（如 step、tool_name 等）
            project_root: 项目根目录（用于落盘路径）
        
        Returns:
            创建的 Message 对象（content 为截断后的 JSON）
        """
        # 使用 ObservationTruncator 截断工具结果
        truncated_result = truncate_observation(tool_name, raw_result, project_root)
        
        # 注意：先展开 metadata，再写 tool_name，确保 tool_name 不被覆盖
        msg = Message(
            content=truncated_result,
            role="tool",
            metadata={
                **(metadata or {}),
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
        self._last_usage_tokens = 0
        self._total_usage_tokens = 0
    
    def update_last_usage(self, total_tokens: int):
        """
        更新上一次 API 调用的 token 使用量
        
        Args:
            total_tokens: API 返回的 usage.total_tokens
        """
        if total_tokens is None:
            return
        self._last_usage_tokens = total_tokens
        self._total_usage_tokens += total_tokens

    def get_total_usage_tokens(self) -> int:
        """获取会话累计 token 使用量"""
        return self._total_usage_tokens

    def estimate_total_tokens(self, pending_input: str) -> int:
        """估算会话累计 token（累计 usage + 当前输入估算）"""
        input_estimate = len(pending_input) // 3
        return self._total_usage_tokens + input_estimate

    def estimate_context_tokens(self, pending_input: str) -> int:
        """估算当前上下文 token（历史消息 + 当前输入）"""
        total_chars = len(pending_input or "")
        for msg in self._messages:
            content = msg.content or ""
            total_chars += len(str(content))
            meta = msg.metadata or {}
            if msg.role == "assistant":
                tool_calls = meta.get("tool_calls")
                if tool_calls:
                    try:
                        total_chars += len(json.dumps(tool_calls, ensure_ascii=False))
                    except Exception:
                        total_chars += len(str(tool_calls))
            elif msg.role == "tool":
                tool_name = meta.get("tool_name")
                if tool_name:
                    total_chars += len(str(tool_name))
        return total_chars // 3
    
    # =========================================================================
    # 压缩触发检测
    # =========================================================================
    
    def should_compress(self, pending_input: str) -> bool:
        """
        检测是否应该触发压缩
        
        根据 A6 规则：
        - estimated_total = last_usage + len(user_input) // 3
        - 触发条件：estimated_total >= threshold 且消息数 >= 3
        
        Args:
            pending_input: 待发送的用户输入
        
        Returns:
            是否需要压缩
        """
        # 最低消息数要求
        if len(self._messages) < 3:
            return False
        
        # 计算预估 token 数（基于当前上下文）
        estimated_total = self.estimate_context_tokens(pending_input)
        
        # 计算阈值
        threshold = int(self._config.context_window * self._config.compression_threshold)
        
        return estimated_total >= threshold
    
    # =========================================================================
    # 历史压缩
    # =========================================================================
    
    def compact(self, on_event=None, return_info: bool = False):
        """
        执行历史压缩
        
        压缩流程：
        1. 识别轮次边界
        2. 计算保留区（最近 N 轮）
        3. 对旧消息生成 Summary（如果有 summary_generator）
        4. 删除旧消息，插入 Summary
        
        Returns:
            是否执行了压缩（False 表示消息数不足，无需压缩）
        """
        def _emit(event: str, payload: dict):
            if on_event:
                try:
                    on_event(event, payload)
                except Exception:
                    pass

        info: dict = {"compressed": False}

        # 获取轮次边界
        rounds = self._identify_rounds()
        
        # 至少需要超过 min_retain_rounds 轮才压缩
        min_rounds = self._config.min_retain_rounds
        if len(rounds) <= min_rounds:
            info.update({
                "reason": "rounds_not_enough",
                "rounds_count": len(rounds),
                "min_retain_rounds": min_rounds,
            })
            _emit("history_compression_plan", info)
            _emit("history_compression_skipped", info)
            return info if return_info else False
        
        # 计算保留区：保留最后 min_rounds 轮
        retain_start_round = len(rounds) - min_rounds
        retain_start_idx = rounds[retain_start_round][0]  # 保留区起始消息索引

        info.update({
            "rounds": rounds,
            "rounds_count": len(rounds),
            "min_retain_rounds": min_rounds,
            "retain_start_round": retain_start_round,
            "retain_start_idx": retain_start_idx,
            "messages_before": len(self._messages),
        })
        _emit("history_compression_plan", info)
        
        # 提取待压缩的消息（不包括 summary 消息）
        messages_to_compress = [
            msg for msg in self._messages[:retain_start_idx]
            if msg.role != "summary"
        ]
        
        # 提取现有的 summary 消息（保留）
        existing_summaries = [
            msg for msg in self._messages[:retain_start_idx]
            if msg.role == "summary"
        ]

        info.update({
            "messages_to_compress": len(messages_to_compress),
            "existing_summaries": len(existing_summaries),
        })
        _emit("history_compression_messages", {
            "messages_to_compress": len(messages_to_compress),
            "existing_summaries": len(existing_summaries),
        })
        
        # 如果没有需要压缩的消息，跳过
        if not messages_to_compress:
            info.update({"reason": "no_messages_to_compress"})
            _emit("history_compression_skipped", info)
            return info if return_info else False
        
        # 生成新的 Summary
        new_summary = None
        if self._summary_generator:
            try:
                new_summary = self._summary_generator(messages_to_compress)
            except Exception:
                # Summary 生成失败，使用降级策略（仅截断）
                new_summary = None

        info.update({
            "summary_generated": new_summary is not None,
            "summary_len": len(new_summary) if isinstance(new_summary, str) else 0,
            "summary_text": new_summary if isinstance(new_summary, str) else "",
        })
        _emit("history_compression_summary", {
            "summary_generated": new_summary is not None,
            "summary_len": len(new_summary) if isinstance(new_summary, str) else 0,
            "summary_text": new_summary if isinstance(new_summary, str) else "",
        })
        
        # 重建消息列表
        new_messages: List[Message] = []
        
        # 1. 保留现有的 summary 消息
        new_messages.extend(existing_summaries)
        
        # 2. 插入新生成的 Summary（如果有）
        # 注意：使用 is not None 判断，避免空字符串被当作 False 丢弃
        if new_summary is not None:
            new_messages.append(Message(
                content=new_summary,
                role="summary",
                metadata={"generated_at": datetime.now().isoformat()},
            ))
        
        # 3. 保留最近 N 轮的消息
        new_messages.extend(self._messages[retain_start_idx:])
        
        # 替换消息列表
        self._messages = new_messages

        info.update({
            "compressed": True,
            "messages_after": len(self._messages),
        })
        _emit("history_compression_rebuilt", {
            "messages_after": len(self._messages),
        })

        # 记录压缩后的上下文（HistoryManager.to_messages 格式）
        try:
            compressed_context = self.to_messages()
        except Exception:
            compressed_context = []
        _emit("history_compression_context", {
            "messages": compressed_context,
            "message_count": len(compressed_context),
        })
        
        return info if return_info else True
    
    def _identify_rounds(self) -> List[Tuple[int, int]]:
        """
        识别轮次边界
        
        一轮定义（A4）：从 user 发起到 assistant 完成回答（中间允许多次工具调用）
        
        Returns:
            轮次列表，每项为 (start_idx, end_idx)，表示该轮在 _messages 中的索引范围
        """
        rounds: List[Tuple[int, int]] = []
        current_round_start: Optional[int] = None
        
        for idx, msg in enumerate(self._messages):
            if msg.role == "user":
                # 遇到 user 消息，开启新轮
                if current_round_start is not None:
                    # 关闭上一轮（结束于上一个消息）
                    rounds.append((current_round_start, idx - 1))
                current_round_start = idx
            elif msg.role == "summary":
                # summary 消息不属于任何轮次，跳过
                continue
        
        # 处理最后一轮
        if current_round_start is not None:
            rounds.append((current_round_start, len(self._messages) - 1))
        
        return rounds
    
    # =========================================================================
    # 序列化（供 ContextBuilder 使用）
    # =========================================================================
    
    def to_messages(self) -> List[Dict[str, Any]]:
        """
        将历史消息转换为 OpenAI messages 格式
        
        Message List 模式：
        - user: {"role": "user", "content": "..."}
        - assistant: {"role": "assistant", "content": "...", "tool_calls": [...] (可选)}
        - tool: {"role": "tool", "tool_call_id": "...", "content": "..."}
        - summary: {"role": "system", "content": "## Summary\n..."}
          作为 system 消息注入
        
        Returns:
            OpenAI messages 格式的列表
        """
        logger = logging.getLogger(__name__)
        # Function-calling mode only (no compat format)
        strict_mode = True
        messages: List[Dict[str, Any]] = []
        
        for msg in self._messages:
            if msg.role == "user":
                messages.append({
                    "role": "user",
                    "content": msg.content,
                })
            elif msg.role == "assistant":
                assistant_msg: Dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content,
                }
                # 如果有 reasoning_content，添加到消息中（Kimi API 要求）
                reasoning_content = (msg.metadata or {}).get("reasoning_content")
                if reasoning_content:
                    assistant_msg["reasoning_content"] = reasoning_content
                
                if strict_mode and (msg.metadata or {}).get("action_type") == "tool_call":
                    tool_calls = (msg.metadata or {}).get("tool_calls")
                    if tool_calls:
                        try:
                            import json
                            assistant_msg["tool_calls"] = []
                            for call in tool_calls:
                                name = call.get("name") or "unknown_tool"
                                call_id = call.get("id")
                                arguments = call.get("arguments") or {}
                                args_str = arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)
                                assistant_msg["tool_calls"].append({
                                    "id": call_id,
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": args_str,
                                    },
                                })
                        except Exception as exc:
                            logger.warning("Failed to build tool_calls metadata: %s", exc)
                    else:
                        # 兼容旧结构（单 tool）
                        tool_name = (msg.metadata or {}).get("tool_name")
                        tool_call_id = (msg.metadata or {}).get("tool_call_id")
                        tool_args = (msg.metadata or {}).get("tool_args")
                        if tool_name and tool_call_id:
                            try:
                                import json
                                assistant_msg["tool_calls"] = [{
                                    "id": tool_call_id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(tool_args or {}, ensure_ascii=False),
                                    },
                                }]
                            except Exception as exc:
                                logger.warning("Failed to build tool_calls metadata: %s", exc)
                        else:
                            logger.warning("Strict tool mode active but missing tool_calls")
                messages.append(assistant_msg)
            elif msg.role == "tool":
                tool_name = (msg.metadata or {}).get("tool_name", "unknown")
                if strict_mode:
                    tool_call_id = (msg.metadata or {}).get("tool_call_id")
                    if tool_call_id:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": msg.content,
                        })
                    else:
                        logger.warning("Strict tool mode active but missing tool_call_id; falling back to compat")
                        messages.append({
                            "role": "user",
                            "content": f"Observation ({tool_name}): {msg.content}",
                        })
                else:
                    messages.append({
                        "role": "user",
                        "content": f"Observation ({tool_name}): {msg.content}",
                    })
            elif msg.role == "summary":
                # Summary 作为 system 消息注入
                messages.append({
                    "role": "system",
                    "content": f"## Archived History Summary\n{msg.content}",
                })
        
        return messages
    
    # 兼容旧接口已移除，请使用 to_messages()
    
    def get_rounds_count(self) -> int:
        """获取当前轮次数"""
        return len(self._identify_rounds())
