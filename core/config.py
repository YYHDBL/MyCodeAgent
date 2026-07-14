"""配置管理"""

import os
from typing import Any, Dict, Optional
from pydantic import BaseModel

from core.env import load_env

load_env()


_TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def _env_flag(name: str, default: bool) -> bool:
    """Read a canonical boolean environment value without compatibility aliases."""

    return os.getenv(name, str(default)).strip().lower() in _TRUE_VALUES


class Config(BaseModel):
    """HelloAgents配置类"""
    
    # LLM配置
    default_model: str = "gpt-3.5-turbo"
    default_provider: str = "openai"
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    
    # 系统配置
    debug: bool = False
    log_level: str = "INFO"
    show_react_steps: bool = True
    show_progress: bool = True
    
    # 历史记录配置
    max_history_length: int = 100

    # 上下文工程配置（E5）
    context_window: int = 128000  # 默认 128K tokens
    compression_threshold: float = 0.8  # 触发压缩的阈值比例
    min_retain_rounds: int = 10  # 最少保留的轮次数
    summary_timeout: int = 120  # Summary 生成超时（秒）
    session_memory_char_budget: int = 4000
    enable_verification_agent: bool = False

    # Optional capabilities.  These values are the sole runtime defaults; the
    # bootstrap applies explicit CLI opt-ins to this object before construction.
    enable_mcp: bool = False
    enable_skills: bool = True
    skills_refresh_on_call: bool = False
    enable_tracing: bool = True
    
    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量创建配置"""
        return cls(
            debug=_env_flag("DEBUG", False),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            show_react_steps=_env_flag("SHOW_REACT_STEPS", True),
            show_progress=_env_flag("SHOW_PROGRESS", True),
            temperature=float(os.getenv("TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("MAX_TOKENS")) if os.getenv("MAX_TOKENS") else None,
            context_window=int(os.getenv("CONTEXT_WINDOW", "128000")),
            compression_threshold=float(os.getenv("COMPRESSION_THRESHOLD", "0.8")),
            min_retain_rounds=int(os.getenv("MIN_RETAIN_ROUNDS", "10")),
            summary_timeout=int(os.getenv("SUMMARY_TIMEOUT", "120")),
            session_memory_char_budget=int(os.getenv("SESSION_MEMORY_CHAR_BUDGET", "4000")),
            enable_verification_agent=_env_flag("ENABLE_VERIFICATION_AGENT", False),
            enable_mcp=_env_flag("ENABLE_MCP", False),
            enable_skills=_env_flag("ENABLE_SKILLS", True),
            skills_refresh_on_call=_env_flag("SKILLS_REFRESH_ON_CALL", False),
            enable_tracing=_env_flag("ENABLE_TRACING", True),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump()
