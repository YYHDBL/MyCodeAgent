"""Context model-view construction."""

from __future__ import annotations

from typing import Any

from runtime.context.model_view import ModelView
from runtime.context.normalizer import MessageNormalizer
from runtime.context.projection import ProjectionBuilder


class ContextEngine:
    """Builds the exact model-facing context for a loop iteration."""

    def __init__(
        self,
        context_builder: Any,
        projection_builder: ProjectionBuilder | None = None,
        normalizer: MessageNormalizer | None = None,
    ):
        self.context_builder = context_builder
        self.projection_builder = projection_builder or ProjectionBuilder()
        self.normalizer = normalizer or MessageNormalizer()

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
                    "warnings": list(view.warnings),
                },
                step=step,
            )

        return view
