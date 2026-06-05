"""Context engineering subsystem."""

from runtime.context.engine import ContextEngine
from runtime.context.model_view import ModelView
from runtime.context.normalizer import MessageNormalizer
from runtime.context.projection import ProjectionBuilder, ProjectionResult

__all__ = [
    "ContextEngine",
    "MessageNormalizer",
    "ModelView",
    "ProjectionBuilder",
    "ProjectionResult",
]
