"""ContextBuilder tests."""

import time
import unittest

from core.context_engine.context_builder import ContextBuilder
from tests.utils.test_helpers import create_temp_project


class DummyToolRegistry:
    def get_all_tools(self):
        return []


class TestContextBuilder(unittest.TestCase):
    def _make_project(self, structure):
        return create_temp_project(structure)

    def test_build_messages_with_history(self):
        structure = {
            "prompts/agents_prompts/L1_system_prompt.py": "system_prompt = 'L1 {tools}'",
            "prompts/tools_prompts/ls_prompt.py": "ls_prompt = 'LS tool'",
            "CODE_LAW.md": "Rule A",
        }
        with self._make_project(structure) as project:
            builder = ContextBuilder(tool_registry=DummyToolRegistry(), project_root=str(project.root))
            history = [{"role": "user", "content": "hi"}]
            messages = builder.build_messages(history)
            self.assertEqual(messages[0]["role"], "system")
            self.assertEqual(messages[1]["role"], "system")
            self.assertEqual(messages[2]["role"], "user")

    def test_system_prompt_override(self):
        structure = {
            "prompts/tools_prompts/ls_prompt.py": "ls_prompt = 'LS tool'",
        }
        with self._make_project(structure) as project:
            builder = ContextBuilder(
                tool_registry=DummyToolRegistry(),
                project_root=str(project.root),
                system_prompt_override="OVERRIDE {tools}",
            )
            messages = builder.get_system_messages()
            self.assertIn("OVERRIDE", messages[0]["content"])
            self.assertIn("LS tool", messages[0]["content"])

    def test_code_law_lowercase_name(self):
        structure = {
            "prompts/agents_prompts/L1_system_prompt.py": "system_prompt = 'L1'",
            "code_law.md": "lowercase rule",
        }
        with self._make_project(structure) as project:
            builder = ContextBuilder(tool_registry=DummyToolRegistry(), project_root=str(project.root))
            messages = builder.get_system_messages()
            self.assertEqual(len(messages), 2)
            self.assertIn("lowercase rule", messages[1]["content"])

    def test_code_law_cache_refresh(self):
        structure = {
            "prompts/agents_prompts/L1_system_prompt.py": "system_prompt = 'L1'",
            "CODE_LAW.md": "Rule A",
        }
        with self._make_project(structure) as project:
            builder = ContextBuilder(tool_registry=DummyToolRegistry(), project_root=str(project.root))
            messages1 = builder.get_system_messages()
            self.assertIn("Rule A", messages1[1]["content"])
            time.sleep(0.01)
            project.path("CODE_LAW.md").write_text("Rule B", encoding="utf-8")
            # Cache is reused until invalidated explicitly
            messages2 = builder.get_system_messages()
            self.assertIn("Rule A", messages2[1]["content"])
            builder.set_mcp_tools_prompt("invalidate")
            messages3 = builder.get_system_messages()
            self.assertIn("Rule B", messages3[1]["content"])

    def test_tool_prompts_sorted_and_skip_private(self):
        structure = {
            "prompts/agents_prompts/L1_system_prompt.py": "system_prompt = 'L1 {tools}'",
            "prompts/tools_prompts/a_prompt.py": "a_prompt = 'A'",
            "prompts/tools_prompts/b_prompt.py": "b_prompt = 'B'",
            "prompts/tools_prompts/__init__.py": "ignored_prompt = 'X'",
        }
        with self._make_project(structure) as project:
            builder = ContextBuilder(tool_registry=DummyToolRegistry(), project_root=str(project.root))
            messages = builder.get_system_messages()
            content = messages[0]["content"]
            self.assertIn("A", content)
            self.assertIn("B", content)
            self.assertNotIn("X", content)
            self.assertLess(content.find("A"), content.find("B"))

    def test_missing_tool_prompts_dir(self):
        structure = {
            "prompts/agents_prompts/L1_system_prompt.py": "system_prompt = 'L1 {tools}'",
        }
        with self._make_project(structure) as project:
            builder = ContextBuilder(tool_registry=DummyToolRegistry(), project_root=str(project.root))
            messages = builder.get_system_messages()
            self.assertIn("L1", messages[0]["content"])
            self.assertNotIn("Available Tools", messages[0]["content"])

    def test_mcp_tools_prompt_injection(self):
        structure = {
            "prompts/agents_prompts/L1_system_prompt.py": "system_prompt = 'L1'",
        }
        with self._make_project(structure) as project:
            builder = ContextBuilder(tool_registry=DummyToolRegistry(), project_root=str(project.root))
            builder.set_mcp_tools_prompt("MCP tool list")
            messages = builder.get_system_messages()
            self.assertIn("# MCP Tools", messages[0]["content"])
            self.assertIn("MCP tool list", messages[0]["content"])

    def test_skills_prompt_injection(self):
        structure = {
            "prompts/agents_prompts/L1_system_prompt.py": "system_prompt = 'L1 {tools}'",
            "prompts/tools_prompts/skill_prompt.py": "skill_prompt = 'Skills: {{available_skills}}'",
        }
        with self._make_project(structure) as project:
            builder = ContextBuilder(tool_registry=DummyToolRegistry(), project_root=str(project.root))
            builder.set_skills_prompt("SkillA, SkillB")
            messages = builder.get_system_messages()
            self.assertIn("SkillA, SkillB", messages[0]["content"])

    def test_cache_invalidated_on_set_skills_prompt(self):
        structure = {
            "prompts/agents_prompts/L1_system_prompt.py": "system_prompt = 'L1 {tools}'",
            "prompts/tools_prompts/skill_prompt.py": "skill_prompt = 'Skills: {{available_skills}}'",
        }
        with self._make_project(structure) as project:
            builder = ContextBuilder(tool_registry=DummyToolRegistry(), project_root=str(project.root))
            messages1 = builder.get_system_messages()
            self.assertNotIn("SkillA", messages1[0]["content"])
            builder.set_skills_prompt("SkillA")
            messages2 = builder.get_system_messages()
            self.assertIn("SkillA", messages2[0]["content"])


if __name__ == "__main__":
    unittest.main()
