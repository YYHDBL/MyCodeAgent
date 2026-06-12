"""Canonical runtime package."""

from runtime.history import HistoryManager, Message

__all__ = [
    "CodeAgent",
    "ContextBuilder",
    "HistoryManager",
    "Message",
    "ResumeLoader",
    "RuntimeRunner",
    "TranscriptStore",
]


def __getattr__(name: str):
    if name == "CodeAgent":
        from runtime.host import CodeAgent

        return CodeAgent
    if name == "RuntimeRunner":
        from runtime.loop import RuntimeRunner

        return RuntimeRunner
    if name == "ContextBuilder":
        from runtime.prompt_builder import ContextBuilder

        return ContextBuilder
    if name == "ResumeLoader":
        from runtime.transcript import ResumeLoader

        return ResumeLoader
    if name == "TranscriptStore":
        from runtime.transcript import TranscriptStore

        return TranscriptStore
    raise AttributeError(name)
