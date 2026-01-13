"""工具输出截断器（统一策略）

根据《工具输出截断设计文档》实现统一的工具输出截断策略。

本模块**完全替换**原有的 ToolResultCompressor：
- 不再为每个工具设计特化压缩
- 所有工具输出使用同一套截断规则
- 完整输出落盘保存，随时可回溯

截断规则：
- MAX_LINES = 2000 (默认)
- MAX_BYTES = 50KB (默认)
- 截断方向：head（默认，保留前 N 行）或 tail（保留后 N 行）

落盘策略：
- 目录：项目根目录下 tool-output/
- 文件名：tool_<timestamp>_<toolname>.json
- 保留 7 天，过期自动清理
"""

import json
import os
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# 配置常量（可通过环境变量覆盖）
# =============================================================================

def _get_max_lines() -> int:
    return int(os.getenv("TOOL_OUTPUT_MAX_LINES", "2000"))

def _get_max_bytes() -> int:
    return int(os.getenv("TOOL_OUTPUT_MAX_BYTES", "51200"))  # 50KB

def _get_truncate_direction() -> str:
    direction = os.getenv("TOOL_OUTPUT_TRUNCATE_DIRECTION", "head").lower().strip()
    return direction if direction in {"head", "tail"} else "head"

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
        
        # 1. 保存完整输出
        output_path = self._save_full_output(tool_name, raw_result)
        relative_path = str(output_path.relative_to(self._project_root)) if output_path else None
        
        # 2. 截断内容（基于可读文本）
        preview_text, kept_size = self._truncate_content(
            preview_source,
            max_lines, 
            max_bytes, 
            direction
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
    ) -> Tuple[str, Dict[str, int]]:
        """
        按行数和字节数截断内容
        
        Returns:
            (截断后的内容, 保留的大小信息)
        """
        lines = content.split("\n")
        
        # 按行数截断
        if direction == "tail":
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
        import random
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


# =============================================================================
# 兼容旧接口（过渡期）
# =============================================================================

def compress_tool_result(tool_name: str, raw_result: str) -> str:
    """
    兼容旧的 ToolResultCompressor 接口
    
    此函数保持旧接口兼容性，内部使用新的截断策略。
    
    Args:
        tool_name: 工具名称
        raw_result: 原始 JSON 结果字符串
        
    Returns:
        处理后的 JSON 字符串
    """
    return truncate_observation(tool_name, raw_result)
