"""SummaryCompressor tests."""

import concurrent.futures
import unittest
from unittest.mock import patch

from core.context_engine.summary_compressor import (
    create_summary_generator,
    _serialize_messages_for_summary,
    _build_summary_prompt,
)
from core.message import Message
from core.config import Config


class DummyLLM:
    def __init__(self, response="Summary"):
        self.response = response

    def invoke(self, messages):
        return self.response


class FailingLLM:
    def invoke(self, messages):
        raise RuntimeError("fail")


class DummyFuture:
    def __init__(self):
        self.cancelled = False

    def result(self, timeout=None):
        raise concurrent.futures.TimeoutError()

    def cancel(self):
        self.cancelled = True


class DummyExecutor:
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.future = DummyFuture()

    def submit(self, fn):
        return self.future

    def shutdown(self, wait=False, cancel_futures=False):
        self.calls.append({"wait": wait, "cancel_futures": cancel_futures})


class TestSummaryCompressor(unittest.TestCase):
    def test_create_generator(self):
        gen = create_summary_generator(DummyLLM())
        self.assertTrue(callable(gen))

    def test_generate_summary_empty_messages(self):
        gen = create_summary_generator(DummyLLM())
        self.assertIsNone(gen([]))

    def test_generate_summary_success(self):
        gen = create_summary_generator(DummyLLM(" Summary content "))
        msg = Message(content="hi", role="user")
        result = gen([msg])
        self.assertEqual(result, "Summary content")

    def test_generate_summary_llm_failure(self):
        gen = create_summary_generator(FailingLLM())
        msg = Message(content="hi", role="user")
        self.assertIsNone(gen([msg]))

    def test_timeout_handling(self):
        config = Config(summary_timeout=1)
        gen = create_summary_generator(DummyLLM(), config=config)
        msg = Message(content="hi", role="user")
        with patch("core.context_engine.summary_compressor.concurrent.futures.ThreadPoolExecutor", DummyExecutor):
            result = gen([msg])
        self.assertIsNone(result)

    def test_timeout_cancels_and_shutdown(self):
        config = Config(summary_timeout=1)
        gen = create_summary_generator(DummyLLM(), config=config)
        msg = Message(content="hi", role="user")
        executor = DummyExecutor()
        with patch("core.context_engine.summary_compressor.concurrent.futures.ThreadPoolExecutor", return_value=executor):
            result = gen([msg])
        self.assertIsNone(result)
        self.assertTrue(executor.future.cancelled)
        self.assertGreaterEqual(len(executor.calls), 1)
        self.assertTrue(any(call.get("cancel_futures") for call in executor.calls))

    def test_serialize_messages_for_summary(self):
        long_text = "x" * 600
        messages = [
            Message(content="hello", role="user"),
            Message(content="hi", role="assistant"),
            Message(content=long_text, role="tool", metadata={"tool_name": "LS"}),
            Message(content="prev", role="summary"),
        ]
        text = _serialize_messages_for_summary(messages)
        self.assertIn("[User]: hello", text)
        self.assertIn("[Assistant]: hi", text)
        self.assertIn("[Tool:LS]:", text)
        self.assertIn("[Previous Summary]: prev", text)
        self.assertIn("...", text)

    def test_build_summary_prompt_contains_conversation(self):
        conversation = "[User]: hi"
        prompt = _build_summary_prompt(conversation)
        self.assertIn(conversation, prompt)
        self.assertIn("Here is the conversation history", prompt)

    def test_build_summary_prompt_fallback_on_import_error(self):
        conversation = "[User]: hi"
        with patch("builtins.__import__", side_effect=ImportError("missing")):
            prompt = _build_summary_prompt(conversation)
        self.assertIn("ARCHIVED SESSION SUMMARY", prompt)
        self.assertIn(conversation, prompt)


if __name__ == "__main__":
    unittest.main()
