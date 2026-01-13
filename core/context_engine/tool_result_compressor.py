"""工具结果压缩器（已弃用）

本模块已被 observation_truncator.py 替换。
保留此文件是为了向后兼容。

新代码请使用：
    from core.context_engine.observation_truncator import truncate_observation
"""

# 导入新模块以保持兼容性
from .observation_truncator import (
    truncate_observation as compress_tool_result,
    ObservationTruncator as ToolResultCompressor,
    get_truncator as tool_result_compressor,
)

# 废弃警告
import warnings

def _deprecated_compress(tool_name: str, raw_result: str) -> str:
    """已弃用的压缩函数"""
    warnings.warn(
        "compress_tool_result is deprecated, use truncate_observation instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return compress_tool_result(tool_name, raw_result)


__all__ = ["compress_tool_result", "ToolResultCompressor", "tool_result_compressor"]
