"""配置管理"""

import os
from typing import Optional, Dict, Any
from pydantic import BaseModel

from core.env import load_env

load_env()

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

    # AgentTeams 配置（MVP）
    enable_agent_teams: bool = False
    agent_teams_store_dir: str = ".teams"
    agent_tasks_store_dir: str = ".tasks"
    teammate_mode: str = "auto"
    delegate_mode: bool = False
    
    # 上下文工程配置（E5）
    context_window: int = 128000  # 默认 128K tokens
    compression_threshold: float = 0.8  # 触发压缩的阈值比例
    min_retain_rounds: int = 10  # 最少保留的轮次数
    summary_timeout: int = 120  # Summary 生成超时（秒）
    session_memory_char_budget: int = 4000
    long_term_memory_enabled: bool = True
    memory_char_limit: int = 3000
    user_memory_char_limit: int = 1500
    user_memory_path: Optional[str] = None
    memory_nudge_interval: int = 0
    enable_verification_agent: bool = True
    # 工具消息序列化策略（已弃用，当前固定为 function calling 严格模式）
    tool_message_format: str = "strict"
    
    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量创建配置"""
        enable_agent_teams_raw = os.getenv("ENABLE_AGENT_TEAMS")
        if enable_agent_teams_raw is None:
            # Alternate experimental-teams env flag
            enable_agent_teams_raw = os.getenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "false")
        teammate_mode_raw = (os.getenv("TEAMMATE_MODE", "auto") or "auto").strip().lower()
        if teammate_mode_raw not in {"auto", "in-process", "tmux"}:
            teammate_mode_raw = "auto"
        delegate_mode_raw = os.getenv("TEAM_DELEGATE_MODE", "false")
        return cls(
            debug=os.getenv("DEBUG", "false").lower() == "true",
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            show_react_steps=os.getenv("SHOW_REACT_STEPS", "true").lower() == "true",
            show_progress=os.getenv("SHOW_PROGRESS", "true").lower() == "true",
            temperature=float(os.getenv("TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("MAX_TOKENS")) if os.getenv("MAX_TOKENS") else None,
            enable_agent_teams=str(enable_agent_teams_raw).lower() in {"1", "true", "yes", "y", "on"},
            agent_teams_store_dir=os.getenv("AGENT_TEAMS_STORE_DIR", ".teams"),
            agent_tasks_store_dir=os.getenv("AGENT_TASKS_STORE_DIR", ".tasks"),
            teammate_mode=teammate_mode_raw,
            delegate_mode=str(delegate_mode_raw).lower() in {"1", "true", "yes", "y", "on"},
            context_window=int(os.getenv("CONTEXT_WINDOW", "128000")),
            compression_threshold=float(os.getenv("COMPRESSION_THRESHOLD", "0.8")),
            min_retain_rounds=int(os.getenv("MIN_RETAIN_ROUNDS", "10")),
            summary_timeout=int(os.getenv("SUMMARY_TIMEOUT", "120")),
            session_memory_char_budget=int(os.getenv("SESSION_MEMORY_CHAR_BUDGET", "4000")),
            long_term_memory_enabled=os.getenv("LONG_TERM_MEMORY_ENABLED", "true").lower()
            in {"1", "true", "yes", "y", "on"},
            memory_char_limit=int(os.getenv("MEMORY_CHAR_LIMIT", "3000")),
            user_memory_char_limit=int(os.getenv("USER_MEMORY_CHAR_LIMIT", "1500")),
            user_memory_path=os.getenv("USER_MEMORY_PATH") or None,
            memory_nudge_interval=int(os.getenv("MEMORY_NUDGE_INTERVAL", "0")),
            enable_verification_agent=os.getenv("ENABLE_VERIFICATION_AGENT", "true").lower()
            in {"1", "true", "yes", "y", "on"},
            tool_message_format=os.getenv("TOOL_MESSAGE_FORMAT", "strict"),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.dict()
