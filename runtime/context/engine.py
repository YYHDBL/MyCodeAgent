"""Context model-view construction."""

from __future__ import annotations

from typing import Any

from core.config import Config
from runtime.context.budget import ContextBudgetPolicy
from runtime.context.compact import ContextCompactor
from runtime.context.compact_store import CompactStore
from runtime.context.model_view import ModelView
from runtime.context.normalizer import MessageNormalizer
from runtime.context.projection import ProjectionBuilder


class ContextEngine:
    """Builds the exact model-facing context for a loop iteration."""

    def __init__(
        self,
        context_builder: Any,
        *,
        config: Config | None = None,
        summary_generator: Any = None,
        compact_store: CompactStore | None = None,
        budget_policy: ContextBudgetPolicy | None = None,
        compactor: ContextCompactor | None = None,
        projection_builder: ProjectionBuilder | None = None,
        normalizer: MessageNormalizer | None = None,
    ):
        self.context_builder = context_builder
        self.config = config or Config.from_env()
        self.compact_store = compact_store or CompactStore()
        self.budget_policy = budget_policy or ContextBudgetPolicy(self.config)
        self.compactor = compactor or ContextCompactor(
            config=self.config,
            compact_store=self.compact_store,
            summary_generator=summary_generator,
        )
        self.projection_builder = projection_builder or ProjectionBuilder(self.compact_store)
        self.normalizer = normalizer or MessageNormalizer()
        self.last_usage_tokens = 0
        self.total_usage_tokens = 0

    def record_usage(self, total_tokens: int | None) -> None:
        if total_tokens is None:
            return
        self.last_usage_tokens = int(total_tokens)
        self.total_usage_tokens += int(total_tokens)

    def reset(self) -> None:
        """Reset session-scoped context state."""
        self.compact_store.clear()
        self.last_usage_tokens = 0
        self.total_usage_tokens = 0

    def should_compact(self, *, history_manager: Any, pending_input: str) -> bool:
        source_messages = history_manager.get_messages()
        checkpoint = self.compact_store.active_checkpoint
        if checkpoint and checkpoint.source_message_count == len(source_messages):
            return False
        projection = self.projection_builder.project(source_messages)
        decision = self.budget_policy.should_compact(
            messages=projection.messages,
            pending_input=pending_input,
            last_usage_tokens=self.last_usage_tokens,
        )
        return decision.should_compact

    def compact_if_needed(
        self,
        *,
        history_manager: Any,
        pending_input: str,
        step: int = 0,
        trace_logger: Any = None,
    ) -> dict[str, Any]:
        source_messages = history_manager.get_messages()
        checkpoint = self.compact_store.active_checkpoint
        if checkpoint and checkpoint.source_message_count == len(source_messages):
            return {
                "compacted": False,
                "reason": "checkpoint_current",
                "checkpoint_id": checkpoint.id,
            }

        projection = self.projection_builder.project(source_messages)
        decision = self.budget_policy.should_compact(
            messages=projection.messages,
            pending_input=pending_input,
            last_usage_tokens=self.last_usage_tokens,
        )
        if trace_logger:
            trace_logger.log_event(
                "context_compaction_decision",
                {
                    "should_compact": decision.should_compact,
                    "reason": decision.reason,
                    "estimated_tokens": decision.estimated_tokens,
                    "threshold": decision.threshold,
                    "message_count": decision.message_count,
                },
                step=step,
            )
        if not decision.should_compact:
            return {
                "compacted": False,
                "reason": decision.reason,
                "estimated_tokens": decision.estimated_tokens,
                "threshold": decision.threshold,
            }
        info = self.compactor.compact(source_messages)
        if trace_logger:
            event_name = (
                "context_compaction_completed"
                if info.get("compacted")
                else "context_compaction_skipped"
            )
            trace_logger.log_event(event_name, info, step=step)
        return info

    def build_model_view(
        self,
        *,
        history_manager: Any,
        pending_input: str = "",
        step: int = 0,
        trace_logger: Any = None,
    ) -> ModelView:
        source_messages = history_manager.get_messages()
        projection = self.projection_builder.project(source_messages)
        history_messages = self.normalizer.normalize(projection.messages)
        system_messages = self.context_builder.get_system_messages()
        messages = list(system_messages) + list(history_messages)

        estimated_chars = len(pending_input or "")
        for message in messages:
            estimated_chars += len(str(message.get("content", "")))

        view = ModelView(
            messages=messages,
            system_message_count=len(system_messages),
            history_message_count=len(history_messages),
            source_message_count=projection.source_message_count,
            estimated_chars=estimated_chars,
            projection_mode=projection.projection_mode,
            compact_checkpoint_id=projection.compact_checkpoint_id,
            warnings=projection.warnings,
        )

        if trace_logger:
            trace_logger.log_event(
                "model_view_build",
                {
                    "message_count": view.message_count,
                    "system_message_count": view.system_message_count,
                    "history_message_count": view.history_message_count,
                    "source_message_count": view.source_message_count,
                    "estimated_chars": view.estimated_chars,
                    "projection_mode": view.projection_mode,
                    "compact_checkpoint_id": view.compact_checkpoint_id,
                    "warnings": list(view.warnings),
                },
                step=step,
            )

        return view
