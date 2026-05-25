"""Runtime context provider facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

from runtime.input_preprocess import PreprocessResult, preprocess_input

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

__all__ = ["ContextManager"]
