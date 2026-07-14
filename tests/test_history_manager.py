"""HistoryManager tests."""

import unittest

from runtime.history import HistoryManager, Message


class TestHistoryManager(unittest.TestCase):
    def test_append_user_and_assistant(self):
        hm = HistoryManager()
        hm.append_user("hello")
        hm.append_assistant("hi")
        self.assertEqual(hm.get_message_count(), 2)
        self.assertEqual(hm.get_rounds_count(), 1)

    def test_append_tool_keeps_the_orchestrator_observation(self):
        hm = HistoryManager()
        msg = hm.append_tool("Glob", "{\"status\":\"success\"}")
        self.assertEqual(msg.role, "tool")
        self.assertEqual(msg.content, '{"status":"success"}')
        self.assertEqual(msg.metadata.get("tool_name"), "Glob")

    def test_append_tool_keeps_budget_metadata(self):
        hm = HistoryManager()

        msg = hm.append_tool(
            "Read",
            '{"status":"partial"}',
            metadata={"tool_call_id": "call_1", "budgeted": True},
        )

        self.assertEqual(msg.content, '{"status":"partial"}')
        self.assertTrue(msg.metadata["budgeted"])

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
