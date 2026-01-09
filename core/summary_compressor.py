"""Summary 生成器（SummaryCompressor）

根据《上下文工程方案》C2/E2 实现 Summary 生成功能。

核心功能：
1. 接收待压缩的历史消息列表
2. 调用 LLM 生成 Summary（按 A5 模板）
3. 支持超时控制和降级策略

超时策略（E2）：
- 超时限制：120 秒
- 降级策略：超时则返回 None，由 HistoryManager 仅做硬截断
"""

import concurrent.futures
from typing import List, Optional, Callable

from .message import Message
from .config import Config


def create_summary_generator(
    llm: "HelloAgentsLLM",  # noqa: F821
    config: Optional[Config] = None,
    verbose: bool = False,
) -> Callable[[List[Message]], Optional[str]]:
    """
    创建 Summary 生成器函数
    
    返回一个可传入 HistoryManager 的回调函数，签名为：
    (messages: List[Message]) -> Optional[str]
    
    Args:
        llm: LLM 实例，用于调用模型生成 Summary
        config: 配置对象，包含 summary_timeout 等
        verbose: 是否打印调试信息
    
    Returns:
        Summary 生成器函数
    """
    cfg = config or Config()
    timeout = cfg.summary_timeout  # 默认 120 秒
    
    def generate_summary(messages: List[Message]) -> Optional[str]:
        """
        生成 Summary
        
        Args:
            messages: 待压缩的历史消息列表
        
        Returns:
            生成的 Summary 文本，超时则返回 None
        """
        if not messages:
            return None
        
        # 构建 prompt
        conversation_text = _serialize_messages_for_summary(messages)
        prompt = _build_summary_prompt(conversation_text)
        
        if verbose:
            print(f"\n📝 生成 Summary（超时: {timeout}s）...")
        
        # 使用 ThreadPoolExecutor 实现超时控制
        def _call_llm():
            try:
                response = llm.invoke([{"role": "user", "content": prompt}])
                return response
            except Exception as e:
                if verbose:
                    print(f"⚠️ LLM 调用失败: {e}")
                return None
        
        try:
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(_call_llm)
            try:
                result = future.result(timeout=timeout)
                
                if result is None:
                    return None
                
                if verbose:
                    print("✅ Summary 生成完成")
                
                return result.strip()
            except concurrent.futures.TimeoutError:
                # 超时：取消 future 并立即关闭 executor（不等待）
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                if verbose:
                    print(f"⏰ Summary generation timed out ({timeout}s), keeping recent history only.")
                return None
            finally:
                # 正常完成时也要关闭 executor（但这里用 wait=False 避免阻塞）
                executor.shutdown(wait=False)
        except Exception as e:
            if verbose:
                print(f"⚠️ Summary 生成异常: {e}")
            return None
    
    return generate_summary


def _serialize_messages_for_summary(messages: List[Message]) -> str:
    """
    将消息列表序列化为 Summary 生成的输入文本
    
    Args:
        messages: 消息列表
    
    Returns:
        序列化后的对话文本
    """
    lines = []
    for msg in messages:
        if msg.role == "user":
            lines.append(f"[User]: {msg.content}")
        elif msg.role == "assistant":
            lines.append(f"[Assistant]: {msg.content}")
        elif msg.role == "tool":
            tool_name = (msg.metadata or {}).get("tool_name", "unknown")
            # 工具消息可能很长，截取前 500 字符
            content = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
            lines.append(f"[Tool:{tool_name}]: {content}")
        elif msg.role == "summary":
            lines.append(f"[Previous Summary]: {msg.content}")
    
    return "\n\n".join(lines)


def _build_summary_prompt(conversation_text: str) -> str:
    """
    构建 Summary 生成的完整 prompt
    
    Args:
        conversation_text: 序列化后的对话文本
    
    Returns:
        完整的 prompt
    """
    # 导入 SUMMARY_PROMPT
    try:
        from prompts.agents_prompts.summary_prompt import SUMMARY_PROMPT
    except ImportError:
        # 如果导入失败，使用内置的简化版本
        SUMMARY_PROMPT = """
You are tasked with creating an ARCHIVED SESSION SUMMARY for completed work.
Focus ONLY on completed tasks. DO NOT include current in-progress tasks.

Provide a structured summary with:
- Objectives & Status
- Technical Context
- Completed Milestones  
- Key Insights & Decisions
- File System State (files modified)
"""
    
    return f"""{SUMMARY_PROMPT}

---

Here is the conversation history to summarize:

{conversation_text}

---

Now generate the summary in the specified format:"""
