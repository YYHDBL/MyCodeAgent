"""配置管理"""

import os
from typing import Optional, Dict, Any
from pydantic import BaseModel

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
    
    # 历史记录配置
    max_history_length: int = 100
    
    # 上下文工程配置（E5）
    context_window: int = 10000  # 默认 10k tokens
    compression_threshold: float = 0.8  # 触发压缩的阈值比例
    min_retain_rounds: int = 10  # 最少保留的轮次数
    summary_timeout: int = 120  # Summary 生成超时（秒）
    
    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量创建配置"""
        return cls(
            debug=os.getenv("DEBUG", "false").lower() == "true",
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            temperature=float(os.getenv("TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("MAX_TOKENS")) if os.getenv("MAX_TOKENS") else None,
            context_window=int(os.getenv("CONTEXT_WINDOW", "10000")),
            compression_threshold=float(os.getenv("COMPRESSION_THRESHOLD", "0.8")),
            min_retain_rounds=int(os.getenv("MIN_RETAIN_ROUNDS", "10")),
            summary_timeout=int(os.getenv("SUMMARY_TIMEOUT", "120")),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.dict()
