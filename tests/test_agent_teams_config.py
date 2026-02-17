import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.codeAgent import CodeAgent
from core.config import Config
from tools.registry import ToolRegistry


class DummyLLM:
    def invoke_raw(self, messages, tools=None, tool_choice=None):  # pragma: no cover
        raise RuntimeError("not used in this test")


class TestAgentTeamsConfig(unittest.TestCase):
    def test_agent_teams_disabled_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            cfg = Config.from_env()
            self.assertFalse(cfg.enable_agent_teams)

    def test_agent_teams_enabled_from_env(self):
        with patch.dict("os.environ", {"ENABLE_AGENT_TEAMS": "true"}, clear=True):
            cfg = Config.from_env()
            self.assertTrue(cfg.enable_agent_teams)

    def test_agent_teams_enabled_from_claude_compat_env(self):
        with patch.dict("os.environ", {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}, clear=True):
            cfg = Config.from_env()
            self.assertTrue(cfg.enable_agent_teams)

    def test_code_agent_feature_flag_and_store_dirs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = Config(enable_agent_teams=False)
            agent = CodeAgent(
                name="tester",
                llm=DummyLLM(),
                tool_registry=ToolRegistry(),
                project_root=str(Path(temp_dir)),
                config=cfg,
            )
            self.assertFalse(agent.enable_agent_teams)
            self.assertEqual(agent.team_store_dir, ".teams")
            self.assertEqual(agent.task_store_dir, ".tasks")

    def test_code_agent_registers_team_tools_when_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = Config(enable_agent_teams=True)
            registry = ToolRegistry()
            agent = CodeAgent(
                name="tester",
                llm=DummyLLM(),
                tool_registry=registry,
                project_root=str(Path(temp_dir)),
                config=cfg,
            )
            self.assertTrue(agent.enable_agent_teams)
            self.assertIsNotNone(registry.get_tool("TeamCreate"))
            self.assertIsNotNone(registry.get_tool("SendMessage"))
            self.assertIsNotNone(registry.get_tool("TeamStatus"))
            self.assertIsNotNone(registry.get_tool("TeamDelete"))


if __name__ == "__main__":
    unittest.main()
