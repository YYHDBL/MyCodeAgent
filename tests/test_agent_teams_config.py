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


if __name__ == "__main__":
    unittest.main()
