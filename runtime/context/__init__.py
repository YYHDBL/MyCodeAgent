"""Context engineering subsystem."""

from runtime.context.budget import CompactDecision, ContextBudgetPolicy
from runtime.context.compact import ContextCompactor
from runtime.context.compact_store import CompactCheckpoint, CompactStore
from runtime.context.engine import ContextEngine
from runtime.context.model_view import ModelView
from runtime.context.normalizer import MessageNormalizer
from runtime.context.projection import ProjectionBuilder, ProjectionResult
from runtime.context.rounds import HistoryRound, RoundSegmenter

__all__ = [
    "CompactCheckpoint",
    "CompactDecision",
    "CompactStore",
    "ContextCompactor",
    "ContextBudgetPolicy",
    "ContextEngine",
    "HistoryRound",
    "MessageNormalizer",
    "ModelView",
    "ProjectionBuilder",
    "ProjectionResult",
    "RoundSegmenter",
]
