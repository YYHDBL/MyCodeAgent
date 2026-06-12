"""Minimal protocol shared by runtime agent implementations."""

from abc import ABC, abstractmethod
from typing import Optional

from .llm import HelloAgentsLLM
from .config import Config


class Agent(ABC):
    """Identity, model, and configuration shared by concrete agents."""
    
    def __init__(
        self,
        name: str,
        llm: HelloAgentsLLM,
        system_prompt: Optional[str] = None,
        config: Optional[Config] = None
    ):
        self.name = name
        self.llm = llm
        self.system_prompt = system_prompt
        self.config = config or Config.from_env()
    
    @abstractmethod
    def run(self, input_text: str, **kwargs) -> str:
        """Run one user request."""
        raise NotImplementedError
    
    def __str__(self) -> str:
        return f"Agent(name={self.name}, provider={self.llm.provider})"
    
    def __repr__(self) -> str:
        return self.__str__()
