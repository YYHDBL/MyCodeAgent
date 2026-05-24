"""Runtime context services and helpers.

根据《上下文工程方案》C3 实现 @file 处理功能。

核心功能：
1. 解析用户输入中的 @file 引用
2. 生成 system-reminder 提示模型读取文件
3. 自动去重、限制最多 5 个文件

正则规则（C3）：
- 匹配: @([a-zA-Z0-9/._-]+(?:\\.[a-zA-Z0-9]+)?)
- 仅支持英文路径（设计决策 E4）
"""

import concurrent.futures
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass

from core.config import Config
from core.env import load_env

load_env()


# @file 匹配正则（仅支持英文路径）
# 使用 (?<![a-zA-Z0-9]) 负向后视确保 @ 前不是字母数字（避免误触发邮件/handle）
FILE_MENTION_PATTERN = re.compile(r"(?<![a-zA-Z0-9])@([a-zA-Z0-9/._-]+(?:\.[a-zA-Z0-9]+)?)")

# 最大引用文件数
MAX_FILE_MENTIONS = 5

# system-reminder 模板
SYSTEM_REMINDER_TEMPLATE = """<system-reminder>
The user mentioned {file_list}.
You MUST read {read_instruction} with the Read tool before answering.
</system-reminder>"""


@dataclass
class PreprocessResult:
    """预处理结果"""
    processed_input: str  # 处理后的用户输入（包含 system-reminder）
    mentioned_files: List[str]  # 提及的文件路径列表（已去重）
    truncated_count: int  # 被截断的文件数（超出 MAX_FILE_MENTIONS 的部分）


def preprocess_input(user_input: str) -> PreprocessResult:
    """
    预处理用户输入，解析 @file 引用并注入 system-reminder
    
    处理流程（C3）：
    1. 正则匹配所有 @file 引用
    2. 按出现顺序去重
    3. 最多保留 5 个文件
    4. 生成 system-reminder 追加到用户输入
    
    Args:
        user_input: 原始用户输入
    
    Returns:
        PreprocessResult 包含处理后的输入和文件列表
    """
    # 匹配所有 @file 引用
    matches = FILE_MENTION_PATTERN.findall(user_input)
    
    if not matches:
        return PreprocessResult(
            processed_input=user_input,
            mentioned_files=[],
            truncated_count=0,
        )
    
    # 按出现顺序去重
    seen = set()
    unique_files: List[str] = []
    for path in matches:
        if path not in seen:
            seen.add(path)
            unique_files.append(path)
    
    # 截断超出部分
    truncated_count = max(0, len(unique_files) - MAX_FILE_MENTIONS)
    files_to_include = unique_files[:MAX_FILE_MENTIONS]
    
    # 生成 system-reminder
    reminder = _build_system_reminder(files_to_include, truncated_count)
    
    # 追加到用户输入
    processed_input = f"{user_input}\n\n{reminder}"
    
    return PreprocessResult(
        processed_input=processed_input,
        mentioned_files=files_to_include,
        truncated_count=truncated_count,
    )


def _build_system_reminder(files: List[str], truncated_count: int) -> str:
    """
    构建 system-reminder
    
    Args:
        files: 要提及的文件列表（最多 5 个）
        truncated_count: 被截断的文件数
    
    Returns:
        system-reminder 字符串
    """
    if not files:
        return ""
    
    # 构建文件列表字符串
    file_mentions = [f"@{f}" for f in files]
    if truncated_count > 0:
        file_mentions.append(f"(and {truncated_count} more…)")
    
    file_list = ", ".join(file_mentions)
    
    # 构建读取指令
    if len(files) == 1:
        read_instruction = "this file"
    else:
        read_instruction = "these files"
    
    return SYSTEM_REMINDER_TEMPLATE.format(
        file_list=file_list,
        read_instruction=read_instruction,
    )


def extract_file_mentions(user_input: str) -> List[str]:
    """
    仅提取文件引用（不做预处理）
    
    用于检查输入中是否有 @file 引用，不注入 system-reminder。
    
    Args:
        user_input: 用户输入
    
    Returns:
        去重后的文件路径列表
    """
    matches = FILE_MENTION_PATTERN.findall(user_input)
    
    seen = set()
    unique_files: List[str] = []
    for path in matches:
        if path not in seen:
            seen.add(path)
            unique_files.append(path)
    
    return unique_files
logger = logging.getLogger(__name__)


def create_summary_generator(
    llm: "HelloAgentsLLM",  # noqa: F821
    config: Optional[Config] = None,
    verbose: bool = False,
) -> Callable[[List[Any]], Optional[str]]:
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
    
    def generate_summary(messages: List[Any]) -> Optional[str]:
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
            logger.info("生成 Summary（超时: %ss）...", timeout)
        
        # 使用 ThreadPoolExecutor 实现超时控制
        def _call_llm():
            try:
                response = llm.invoke([{"role": "user", "content": prompt}])
                return response
            except Exception as e:
                if verbose:
                    logger.warning("LLM 调用失败: %s", e)
                return None
        
        try:
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(_call_llm)
            try:
                result = future.result(timeout=timeout)
                
                if result is None:
                    return None
                
                if verbose:
                    logger.info("Summary 生成完成")
                
                return result.strip()
            except concurrent.futures.TimeoutError:
                # 超时：取消 future 并立即关闭 executor（不等待）
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                if verbose:
                    logger.warning(
                        "Summary generation timed out (%ss), keeping recent history only.",
                        timeout,
                    )
                return None
            finally:
                # 正常完成时也要关闭 executor（但这里用 wait=False 避免阻塞）
                executor.shutdown(wait=False)
        except Exception as e:
            if verbose:
                logger.warning("Summary 生成异常: %s", e)
            return None
    
    return generate_summary


def _serialize_messages_for_summary(messages: List[Any]) -> str:
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


# =============================================================================
# 配置常量（可通过环境变量覆盖）
# =============================================================================

def _get_max_lines() -> int:
    return int(os.getenv("TOOL_OUTPUT_MAX_LINES", "2000"))

def _get_max_bytes() -> int:
    return int(os.getenv("TOOL_OUTPUT_MAX_BYTES", "51200"))  # 50KB

def _get_truncate_direction() -> str:
    direction = os.getenv("TOOL_OUTPUT_TRUNCATE_DIRECTION", "head").lower().strip()
    return direction if direction in {"head", "tail", "head_tail"} else "head"

def _get_head_tail_lines() -> int:
    value = os.getenv("TOOL_OUTPUT_HEAD_TAIL_LINES", "40")
    try:
        count = int(value)
    except ValueError:
        return 40
    return max(count, 1)

def _get_output_dir() -> str:
    return os.getenv("TOOL_OUTPUT_DIR", "tool-output")

def _get_retention_days() -> int:
    return int(os.getenv("TOOL_OUTPUT_RETENTION_DAYS", "7"))


# =============================================================================
# 观测输出截断器
# =============================================================================

class ObservationTruncator:
    """
    工具输出截断器
    
    对所有工具的输出执行统一的截断策略：
    1. 检查输出大小（行数 + 字节数）
    2. 超过阈值时截断 + 落盘
    3. 返回包含截断信息和文件路径的结果
    """
    
    def __init__(self, project_root: Optional[str] = None):
        """
        初始化截断器
        
        Args:
            project_root: 项目根目录，用于确定落盘路径
        """
        self._project_root = Path(project_root) if project_root else Path.cwd()
        self._output_dir = self._project_root / _get_output_dir()
        
    def truncate(self, tool_name: str, raw_result: str) -> str:
        """
        对工具输出进行截断处理
        
        Args:
            tool_name: 工具名称
            raw_result: 工具返回的原始 JSON 字符串
            
        Returns:
            处理后的 JSON 字符串（可能已截断）
        """
        # 尝试解析 JSON
        parsed = None
        try:
            parsed = json.loads(raw_result)
        except json.JSONDecodeError:
            logger.warning("Failed to parse tool result as JSON; treating as plain text")

        # 检查跳过标记
        if parsed and self._should_skip(parsed):
            return raw_result

        # 使用可读文本进行尺寸判断（将 \\n 还原为真实换行）
        preview_source = self._normalize_text(raw_result)
        content_size = self._get_content_size(preview_source)
        if not self._exceeds_limits(content_size):
            return raw_result

        # 执行截断
        return self._do_truncate(tool_name, raw_result, preview_source, parsed, content_size)
    
    def _should_skip(self, result: Dict[str, Any]) -> bool:
        """检查是否应跳过截断"""
        context = result.get("context", {})
        return context.get("truncation_skip", False)
    
    def _get_content_size(self, text: str) -> Dict[str, int]:
        """获取内容大小信息"""
        lines = text.count("\n") + 1
        bytes_count = len(text.encode("utf-8"))
        return {
            "lines": lines,
            "bytes": bytes_count,
        }
    
    def _exceeds_limits(self, size: Dict[str, int]) -> bool:
        """检查是否超过限制"""
        max_lines = _get_max_lines()
        max_bytes = _get_max_bytes()
        return size["lines"] > max_lines or size["bytes"] > max_bytes
    
    def _do_truncate(
        self,
        tool_name: str,
        raw_result: str,
        preview_source: str,
        parsed_result: Optional[Dict[str, Any]],
        original_size: Dict[str, int],
    ) -> str:
        """
        执行截断操作
        
        1. 保存完整输出到文件
        2. 截断内容
        3. 构建新的响应
        """
        max_lines = _get_max_lines()
        max_bytes = _get_max_bytes()
        direction = _get_truncate_direction()
        head_tail_lines = _get_head_tail_lines()
        
        # 1. 保存完整输出
        output_path = self._save_full_output(tool_name, raw_result)
        relative_path = str(output_path.relative_to(self._project_root)) if output_path else None
        
        # 2. 截断内容（基于可读文本）
        preview_text, kept_size = self._truncate_content(
            preview_source,
            max_lines,
            max_bytes,
            direction,
            head_tail_lines,
        )
        
        # 3. 构建截断后的响应（统一结构）
        status = "success"
        error = None
        stats = {}
        context = {}
        if isinstance(parsed_result, dict):
            status = parsed_result.get("status", "success")
            error = parsed_result.get("error")
            stats = parsed_result.get("stats") or {}
            context = parsed_result.get("context") or {}

        # 截断时标记为 partial（除非原本是 error）
        if status != "error":
            status = "partial"

        truncated_result: Dict[str, Any] = {
            "status": status,
            "data": {
                "truncated": True,
                "truncation": {
                    "direction": direction,
                    "max_lines": max_lines,
                    "max_bytes": max_bytes,
                    "head_tail_lines": head_tail_lines if direction == "head_tail" else None,
                    "original_lines": original_size["lines"],
                    "original_bytes": original_size["bytes"],
                    "kept_lines": kept_size["lines"],
                    "kept_bytes": kept_size["bytes"],
                },
                "preview": preview_text,
            },
            "text": "",
            "stats": stats,
            "context": context,
        }

        if relative_path:
            truncated_result["data"]["truncation"]["full_output_path"] = relative_path

        # 保留错误字段
        if status == "error" and error:
            truncated_result["error"] = error

        # 构建提示文本
        hint = self._build_hint(tool_name, relative_path, original_size)
        truncated_result["text"] = hint
        
        # 清理过期文件（低频执行）
        self._maybe_cleanup()
        
        return json.dumps(truncated_result, ensure_ascii=False, separators=(",", ":"))
    
    def _truncate_content(
        self,
        content: str,
        max_lines: int,
        max_bytes: int,
        direction: str,
        head_tail_lines: int,
    ) -> Tuple[str, Dict[str, int]]:
        """
        按行数和字节数截断内容
        
        Returns:
            (截断后的内容, 保留的大小信息)
        """
        lines = content.split("\n")
        
        # 按行数截断
        if direction == "head_tail":
            if len(lines) > head_tail_lines * 2:
                kept_lines = (
                    lines[:head_tail_lines]
                    + ["... (truncated) ..."]
                    + lines[-head_tail_lines:]
                )
            else:
                kept_lines = lines
        elif direction == "tail":
            kept_lines = lines[-max_lines:] if len(lines) > max_lines else lines
        else:  # head
            kept_lines = lines[:max_lines] if len(lines) > max_lines else lines
        
        truncated = "\n".join(kept_lines)
        
        # 按字节数进一步截断
        encoded = truncated.encode("utf-8")
        if len(encoded) > max_bytes:
            if direction == "tail":
                # 从尾部保留
                truncated = encoded[-max_bytes:].decode("utf-8", errors="ignore")
            else:
                # 从头部保留
                truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
        
        kept_size = {
            "lines": truncated.count("\n") + 1,
            "bytes": len(truncated.encode("utf-8")),
        }
        
        return truncated, kept_size

    def _normalize_text(self, raw_result: str) -> str:
        """将 JSON 字符串中的 \\n 还原为真实换行，提升可读性"""
        return raw_result.replace("\\n", "\n")
    
    def _save_full_output(self, tool_name: str, content: str) -> Optional[Path]:
        """
        保存完整输出到文件
        
        Returns:
            保存的文件路径，失败时返回 None
        """
        try:
            # 确保输出目录存在
            self._output_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"tool_{timestamp}_{tool_name}.json"
            filepath = self._output_dir / filename
            
            # 写入文件
            filepath.write_text(content, encoding="utf-8")
            
            logger.debug("Saved full output to %s", filepath)
            return filepath
            
        except Exception as e:
            logger.warning("Failed to save full output: %s", e)
            return None
    
    def _build_hint(
        self,
        tool_name: str,
        output_path: Optional[str],
        original_size: Dict[str, int],
    ) -> str:
        """构建截断提示信息"""
        lines = original_size["lines"]
        bytes_kb = original_size["bytes"] / 1024
        
        hint = f"⚠️ 输出过大已截断 ({lines} 行, {bytes_kb:.1f}KB)"
        
        if output_path:
            hint += f"\n完整内容见: {output_path}"
            hint += "\n建议: 可用 Task 让子代理处理，或用 Read 分页读取 / Grep 搜索"
        
        return hint
    
    def _maybe_cleanup(self):
        """
        可能执行清理操作
        
        使用概率触发避免每次都检查
        """
        if random.random() > 0.1:  # 10% 概率触发
            return
        
        self._cleanup_expired_files()
    
    def _cleanup_expired_files(self):
        """清理过期的输出文件"""
        try:
            if not self._output_dir.exists():
                return
            
            retention_days = _get_retention_days()
            cutoff = datetime.now() - timedelta(days=retention_days)
            
            for filepath in self._output_dir.glob("tool_*.json"):
                try:
                    mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
                    if mtime < cutoff:
                        filepath.unlink()
                        logger.debug("Deleted expired file: %s", filepath)
                except Exception as e:
                    logger.warning("Failed to delete %s: %s", filepath, e)
                    
        except Exception as e:
            logger.warning("Cleanup failed: %s", e)


# =============================================================================
# 单例与便捷函数
# =============================================================================

_truncator_instance: Optional[ObservationTruncator] = None


def get_truncator(project_root: Optional[str] = None) -> ObservationTruncator:
    """获取截断器单例"""
    global _truncator_instance
    if _truncator_instance is None or project_root is not None:
        _truncator_instance = ObservationTruncator(project_root)
    return _truncator_instance


def truncate_observation(
    tool_name: str,
    raw_result: str,
    project_root: Optional[str] = None,
) -> str:
    """
    截断工具输出的便捷函数
    
    Args:
        tool_name: 工具名称
        raw_result: 原始 JSON 结果字符串
        project_root: 项目根目录
        
    Returns:
        处理后的 JSON 字符串
    """
    truncator = get_truncator(project_root)
    return truncator.truncate(tool_name, raw_result)


def compress_tool_result(tool_name: str, raw_result: str) -> str:
    """
    Convenience alias for the runtime observation truncation path.
    """
    return truncate_observation(tool_name, raw_result)


@dataclass
class ContextManager:
    """Thin runtime boundary for preprocessing, prompt assembly, and compaction."""

    history_manager: Any
    prompt_builder: Any

    def preprocess_input(self, user_input: str) -> PreprocessResult:
        return preprocess_input(user_input)

    def build_messages(self) -> List[dict[str, Any]]:
        return self.prompt_builder.build_messages(self.history_manager.to_messages())

    def maybe_compact(self, pending_input: str, **kwargs) -> Any:
        if not self.history_manager.should_compress(pending_input):
            return False
        return self.history_manager.compact(**kwargs)
