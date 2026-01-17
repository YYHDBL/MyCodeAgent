"""HistoryManager tests."""

import json
import unittest
from unittest.mock import patch

from core.context_engine.history_manager import HistoryManager
from core.config import Config
from core.message import Message


class TestHistoryManager(unittest.TestCase):
    def test_append_user_and_assistant(self):
        hm = HistoryManager()
        hm.append_user("hello")
        hm.append_assistant("hi")
        self.assertEqual(hm.get_message_count(), 2)
        self.assertEqual(hm.get_rounds_count(), 1)

    def test_append_tool_calls_truncator(self):
        hm = HistoryManager()
        with patch("core.context_engine.history_manager.truncate_observation", return_value="TRUNCATED") as mock_truncate:
            msg = hm.append_tool("LS", "{\"status\":\"success\"}")
        mock_truncate.assert_called_once()
        self.assertEqual(msg.role, "tool")
        self.assertEqual(msg.content, "TRUNCATED")
        self.assertEqual(msg.metadata.get("tool_name"), "LS")

    def test_append_summary(self):
        hm = HistoryManager()
        msg = hm.append_summary("summary text")
        self.assertEqual(msg.role, "summary")
        self.assertIn("generated_at", msg.metadata)

    def test_get_messages_returns_copy(self):
        hm = HistoryManager()
        hm.append_user("a")
        msgs = hm.get_messages()
        msgs.append(Message(content="b", role="user"))
        self.assertEqual(hm.get_message_count(), 1)

    def test_round_identification_with_summary(self):
        hm = HistoryManager()
        hm.append_user("q1")
        hm.append_assistant("a1")
        hm.append_summary("summary")
        hm.append_user("q2")
        self.assertEqual(hm.get_rounds_count(), 2)

    def test_round_identification_consecutive_users(self):
        hm = HistoryManager()
        hm.append_user("q1")
        hm.append_user("q2")
        self.assertEqual(hm.get_rounds_count(), 2)

    def test_should_compress_threshold(self):
        config = Config(context_window=1000, compression_threshold=0.8)
        hm = HistoryManager(config=config)
        hm.append_user("q")
        hm.append_assistant("a")
        hm.append_user("q2")
        hm.update_last_usage(800)
        self.assertTrue(hm.should_compress("more"))

    def test_should_compress_requires_min_messages(self):
        config = Config(context_window=1000, compression_threshold=0.1)
        hm = HistoryManager(config=config)
        hm.append_user("q")
        hm.append_assistant("a")
        self.assertFalse(hm.should_compress("input"))

    def _append_round(self, hm: HistoryManager, idx: int):
        hm.append_user(f"q{idx}")
        hm.append_assistant(f"a{idx}")

    def test_compact_rounds_not_enough(self):
        config = Config(min_retain_rounds=3)
        hm = HistoryManager(config=config)
        for i in range(2):
            self._append_round(hm, i)
        info = hm.compact(return_info=True)
        self.assertFalse(info.get("compressed"))
        self.assertEqual(info.get("reason"), "rounds_not_enough")

    def test_compact_with_summary(self):
        config = Config(min_retain_rounds=2)
        hm = HistoryManager(config=config, summary_generator=lambda msgs: f"summary({len(msgs)})")
        for i in range(5):
            self._append_round(hm, i)
        info = hm.compact(return_info=True)
        self.assertTrue(info.get("compressed"))
        summaries = [m for m in hm.get_messages() if m.role == "summary"]
        self.assertEqual(len(summaries), 1)
        self.assertIn("summary(", summaries[0].content)
        self.assertEqual(hm.get_rounds_count(), 2)

    def test_compact_without_summary_generator(self):
        config = Config(min_retain_rounds=1)
        hm = HistoryManager(config=config)
        for i in range(3):
            self._append_round(hm, i)
        result = hm.compact()
        self.assertTrue(result)
        summaries = [m for m in hm.get_messages() if m.role == "summary"]
        self.assertEqual(len(summaries), 0)

    def test_compact_preserves_existing_summaries(self):
        config = Config(min_retain_rounds=1)
        hm = HistoryManager(config=config, summary_generator=lambda msgs: "new summary")
        hm.append_summary("old summary")
        for i in range(3):
            self._append_round(hm, i)
        hm.compact()
        summaries = [m for m in hm.get_messages() if m.role == "summary"]
        self.assertGreaterEqual(len(summaries), 2)
        contents = [m.content for m in summaries]
        self.assertIn("old summary", contents)

    def test_compact_emits_events(self):
        config = Config(min_retain_rounds=1)
        hm = HistoryManager(config=config, summary_generator=lambda msgs: "summary")
        for i in range(3):
            self._append_round(hm, i)
        events = []

        def on_event(name, payload):
            events.append(name)

        hm.compact(on_event=on_event)
        self.assertIn("history_compression_plan", events)
        self.assertIn("history_compression_context", events)

    def test_to_messages_forces_strict_tool_format(self):
        config = Config(tool_message_format="compat")
        hm = HistoryManager(config=config)
        hm.append_user("q")
        hm.append_tool("LS", json.dumps({"status": "success"}), metadata={"tool_call_id": "call_1"})
        messages = hm.to_messages()
        self.assertEqual(messages[1]["role"], "tool")
        self.assertEqual(messages[1]["tool_call_id"], "call_1")

    def test_to_messages_strict_tool_format_missing_call_id(self):
        config = Config(tool_message_format="strict")
        hm = HistoryManager(config=config)
        hm.append_tool("LS", json.dumps({"status": "success"}))
        messages = hm.to_messages()
        self.assertEqual(messages[0]["role"], "user")
        self.assertIn("Observation (LS)", messages[0]["content"])

    def test_to_messages_strict_tool_call_metadata(self):
        config = Config(tool_message_format="strict")
        hm = HistoryManager(config=config)
        hm.append_assistant(
            "",
            metadata={
                "action_type": "tool_call",
                "tool_calls": [
                    {"id": "call_1", "name": "LS", "arguments": {"path": "."}}
                ],
            },
        )
        messages = hm.to_messages()
        self.assertEqual(messages[0]["role"], "assistant")
        self.assertIn("tool_calls", messages[0])

    def test_tool_message_format_case_insensitive(self):
        config = Config(tool_message_format="STRICT")
        hm = HistoryManager(config=config)
        hm.append_tool("LS", json.dumps({"status": "success"}), metadata={"tool_call_id": "call_1"})
        messages = hm.to_messages()
        self.assertEqual(messages[0]["role"], "tool")
        self.assertEqual(messages[0]["tool_call_id"], "call_1")


if __name__ == "__main__":
    unittest.main()
