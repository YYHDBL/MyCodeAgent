"""HistoryManager tests."""

import unittest
from unittest.mock import patch

from runtime.history import HistoryManager, Message


class TestHistoryManager(unittest.TestCase):
    def test_append_user_and_assistant(self):
        hm = HistoryManager()
        hm.append_user("hello")
        hm.append_assistant("hi")
        self.assertEqual(hm.get_message_count(), 2)
        self.assertEqual(hm.get_rounds_count(), 1)

    def test_append_tool_calls_truncator(self):
        hm = HistoryManager()
        with patch("runtime.observation_store.truncate_observation", return_value="TRUNCATED") as mock_truncate:
            msg = hm.append_tool("LS", "{\"status\":\"success\"}")
        mock_truncate.assert_called_once()
        self.assertEqual(msg.role, "tool")
        self.assertEqual(msg.content, "TRUNCATED")
        self.assertEqual(msg.metadata.get("tool_name"), "LS")

    def test_append_tool_skips_truncation_when_observation_already_budgeted(self):
        hm = HistoryManager()

        with patch("runtime.observation_store.truncate_observation", return_value="TRUNCATED") as mock_truncate:
            msg = hm.append_tool(
                "Read",
                '{"status":"partial"}',
                metadata={"tool_call_id": "call_1", "budgeted": True},
                project_root=".",
            )

        self.assertEqual(msg.content, '{"status":"partial"}')
        mock_truncate.assert_not_called()

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

if __name__ == "__main__":
    unittest.main()
