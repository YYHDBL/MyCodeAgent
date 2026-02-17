"""Tests for Task tool MVP implementation."""

import pytest
import json
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import tools.builtin.task as task_module

from tools.builtin.task import (
    TaskTool,
    SubagentRunner,
    DENIED_TOOLS,
    ALLOWED_TOOLS,
    VALID_SUBAGENT_TYPES,
    VALID_MODELS,
    _get_subagent_prompt,
    _create_light_llm,
)
from tools.registry import ToolRegistry
from tools.base import ErrorCode


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_llm():
    """Create a mock LLM."""
    llm = Mock()
    llm.invoke_raw = Mock(return_value={"choices": [{"message": {"content": "Final Answer: Test result"}}]})
    return llm


def make_raw_response(content: str = "", tool_calls: list | None = None):
    message: dict = {"content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}]}


@pytest.fixture
def mock_tool_registry():
    """Create a mock tool registry with basic tools."""
    registry = ToolRegistry()
    
    # Create mock tools
    for tool_name in ["LS", "Glob", "Grep", "Read", "TodoWrite"]:
        mock_tool = Mock()
        mock_tool.name = tool_name
        mock_tool.run = Mock(return_value='{"status": "success", "data": {}, "text": "ok"}')
        registry.register_tool(mock_tool)
    
    # Also add some denied tools to verify filtering
    for tool_name in ["Task", "Write", "Edit", "Bash"]:
        mock_tool = Mock()
        mock_tool.name = tool_name
        mock_tool.run = Mock(return_value='{"status": "success", "data": {}}')
        registry.register_tool(mock_tool)
    
    return registry


@pytest.fixture
def task_tool(mock_llm, mock_tool_registry, tmp_path):
    """Create a TaskTool instance for testing."""
    return TaskTool(
        project_root=tmp_path,
        main_llm=mock_llm,
        tool_registry=mock_tool_registry,
    )


# =============================================================================
# Test Constants
# =============================================================================

class TestConstants:
    """Test that constants are correctly defined."""
    
    def test_denied_tools(self):
        """Verify denied tools list."""
        assert "Task" in DENIED_TOOLS
        assert "Write" in DENIED_TOOLS
        assert "Edit" in DENIED_TOOLS
        assert "MultiEdit" in DENIED_TOOLS
        assert "Bash" in DENIED_TOOLS
        assert "Read" not in DENIED_TOOLS
    
    def test_allowed_tools(self):
        """Verify allowed tools list."""
        assert "LS" in ALLOWED_TOOLS
        assert "Glob" in ALLOWED_TOOLS
        assert "Grep" in ALLOWED_TOOLS
        assert "Read" in ALLOWED_TOOLS
        assert "TodoWrite" in ALLOWED_TOOLS
        assert "Task" not in ALLOWED_TOOLS
        assert "Write" not in ALLOWED_TOOLS
    
    def test_valid_subagent_types(self):
        """Verify valid subagent types."""
        assert "general" in VALID_SUBAGENT_TYPES
        assert "explore" in VALID_SUBAGENT_TYPES
        assert "summary" in VALID_SUBAGENT_TYPES
        assert "plan" in VALID_SUBAGENT_TYPES
        assert len(VALID_SUBAGENT_TYPES) == 4
    
    def test_valid_models(self):
        """Verify valid model choices."""
        assert "main" in VALID_MODELS
        assert "light" in VALID_MODELS
        assert len(VALID_MODELS) == 2


# =============================================================================
# Test Subagent Prompts
# =============================================================================

class TestSubagentPrompts:
    """Test subagent prompt retrieval."""
    
    def test_general_prompt(self):
        """Test general prompt retrieval."""
        prompt = _get_subagent_prompt("general")
        assert "general-purpose subagent" in prompt
        assert "Read-only" in prompt
    
    def test_explore_prompt(self):
        """Test explore prompt retrieval."""
        prompt = _get_subagent_prompt("explore")
        assert "file search specialist" in prompt.lower() or "explore" in prompt.lower()
    
    def test_plan_prompt(self):
        """Test plan prompt retrieval."""
        prompt = _get_subagent_prompt("plan")
        assert "planning" in prompt.lower() or "plan" in prompt.lower()
    
    def test_summary_prompt(self):
        """Test summary prompt retrieval (may use fallback)."""
        prompt = _get_subagent_prompt("summary")
        assert "summar" in prompt.lower()
    
    def test_unknown_type_fallback(self):
        """Test that unknown type falls back to general."""
        prompt = _get_subagent_prompt("unknown")
        assert "general-purpose" in prompt.lower()


# =============================================================================
# Test Task Tool Parameters
# =============================================================================

class TestTaskToolParameters:
    """Test TaskTool parameter definition."""
    
    def test_get_parameters(self, task_tool):
        """Test parameter definition."""
        params = task_tool.get_parameters()
        param_names = [p.name for p in params]
        
        assert "description" in param_names
        assert "prompt" in param_names
        assert "subagent_type" in param_names
        assert "model" in param_names
        assert "mode" in param_names
        assert "team_name" in param_names
        assert "teammate_name" in param_names
    
    def test_required_parameters(self, task_tool):
        """Test required parameter flags."""
        params = task_tool.get_parameters()
        param_dict = {p.name: p for p in params}
        
        assert param_dict["description"].required is True
        assert param_dict["prompt"].required is True
        assert param_dict["subagent_type"].required is True
        assert param_dict["model"].required is False


# =============================================================================
# Test Task Tool Validation
# =============================================================================

class TestTaskToolValidation:
    """Test input validation."""
    
    def test_missing_description(self, task_tool):
        """Test error when description is missing."""
        result = task_tool.run({
            "prompt": "Test prompt",
            "subagent_type": "general"
        })
        data = json.loads(result)
        
        assert data["status"] == "error"
        assert data["error"]["code"] == ErrorCode.INVALID_PARAM.value
        assert "description" in data["error"]["message"]
    
    def test_empty_description(self, task_tool):
        """Test error when description is empty."""
        result = task_tool.run({
            "description": "  ",
            "prompt": "Test prompt",
            "subagent_type": "general"
        })
        data = json.loads(result)
        
        assert data["status"] == "error"
        assert data["error"]["code"] == ErrorCode.INVALID_PARAM.value
    
    def test_missing_prompt(self, task_tool):
        """Test error when prompt is missing."""
        result = task_tool.run({
            "description": "Test task",
            "subagent_type": "general"
        })
        data = json.loads(result)
        
        assert data["status"] == "error"
        assert data["error"]["code"] == ErrorCode.INVALID_PARAM.value
        assert "prompt" in data["error"]["message"]
    
    def test_invalid_subagent_type(self, task_tool):
        """Test error when subagent_type is invalid."""
        result = task_tool.run({
            "description": "Test task",
            "prompt": "Test prompt",
            "subagent_type": "invalid_type"
        })
        data = json.loads(result)
        
        assert data["status"] == "error"
        assert data["error"]["code"] == ErrorCode.INVALID_PARAM.value
        assert "invalid_type" in data["error"]["message"]
    
    def test_invalid_model_defaults_to_light(self, task_tool, mock_llm):
        """Test that invalid model defaults to light."""
        mock_llm.invoke_raw.return_value = make_raw_response(content="Final Answer: Done")
        
        result = task_tool.run({
            "description": "Test task",
            "prompt": "Test prompt",
            "subagent_type": "general",
            "model": "invalid_model"
        })
        data = json.loads(result)
        
        # Should succeed with default model
        assert data["status"] == "success"

    def test_persistent_mode_requires_team_fields(self, task_tool):
        result = task_tool.run({
            "description": "d",
            "prompt": "p",
            "subagent_type": "general",
            "mode": "persistent",
        })
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["error"]["code"] == ErrorCode.INVALID_PARAM.value


# =============================================================================
# Test Tool Filtering
# =============================================================================

class TestToolFiltering:
    """Test subagent tool filtering."""
    
    def test_filtered_registry_excludes_denied(self, task_tool):
        """Test that filtered registry excludes denied tools."""
        filtered = task_tool._create_filtered_registry()
        
        for tool_name in DENIED_TOOLS:
            assert filtered.get_tool(tool_name) is None
    
    def test_filtered_registry_includes_allowed(self, task_tool):
        """Test that filtered registry includes allowed tools."""
        filtered = task_tool._create_filtered_registry()
        
        # At least some allowed tools should be present
        allowed_present = [
            filtered.get_tool(name) is not None
            for name in ALLOWED_TOOLS
        ]
        assert any(allowed_present)


# =============================================================================
# Test SubagentRunner
# =============================================================================

class TestSubagentRunner:
    """Test SubagentRunner execution."""
    
    def test_runner_basic_execution(self, mock_llm, mock_tool_registry, tmp_path):
        """Test basic subagent execution."""
        mock_llm.invoke_raw.return_value = make_raw_response(content="Final Answer: Test complete")
        
        runner = SubagentRunner(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            system_prompt="You are a test agent.",
            project_root=tmp_path,
            max_steps=5,
        )
        
        result, tool_usage = runner.run("Test task")
        
        assert "Test complete" in result
        assert mock_llm.invoke_raw.called
    
    def test_runner_tool_call_parsing(self, mock_llm, mock_tool_registry, tmp_path):
        """Test that runner parses tool calls correctly."""
        # First call returns a tool use, second returns final answer
        mock_llm.invoke_raw.side_effect = [
            make_raw_response(tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "Read", "arguments": {"path": "test.txt"}},
            }]),
            make_raw_response(content="Final Answer: Content was read successfully"),
        ]
        
        runner = SubagentRunner(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            system_prompt="Test agent",
            project_root=tmp_path,
            max_steps=5,
        )
        
        result, tool_usage = runner.run("Read test.txt")
        
        assert "Read" in tool_usage
        assert tool_usage["Read"] == 1
    
    def test_runner_denied_tool_blocked(self, mock_llm, mock_tool_registry, tmp_path):
        """Test that runner blocks denied tools."""
        mock_llm.invoke_raw.side_effect = [
            make_raw_response(tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "Task", "arguments": {"description": "nested", "prompt": "test"}},
            }]),
            make_raw_response(content="Final Answer: Blocked"),
        ]
        
        runner = SubagentRunner(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            system_prompt="Test agent",
            project_root=tmp_path,
            max_steps=5,
        )
        
        result, tool_usage = runner.run("Try to call Task")
        
        # Task should not be in tool_usage
        assert "Task" not in tool_usage
    
    def test_runner_max_steps(self, mock_llm, mock_tool_registry, tmp_path):
        """Test that runner respects max_steps limit."""
        # Always return a tool call, never finish
        mock_llm.invoke_raw.return_value = make_raw_response(tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {"name": "Read", "arguments": {"path": "test.txt"}},
        }])
        
        runner = SubagentRunner(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            system_prompt="Test agent",
            project_root=tmp_path,
            max_steps=3,
        )
        
        result, tool_usage = runner.run("Infinite loop task")
        
        assert "maximum steps" in result.lower()
        # Should have called Read at most max_steps times
        assert tool_usage.get("Read", 0) <= 3


# =============================================================================
# Test Task Tool Execution
# =============================================================================

class TestTaskToolExecution:
    """Test full TaskTool execution."""
    
    def test_successful_execution(self, task_tool, mock_llm):
        """Test successful task execution."""
        mock_llm.invoke_raw.return_value = make_raw_response(content="Final Answer: Task completed successfully")
        
        result = task_tool.run({
            "description": "Test task",
            "prompt": "Do something",
            "subagent_type": "general",
            "model": "main"
        })
        data = json.loads(result)
        
        assert data["status"] == "success"
        assert "completed" in data["data"]["status"]
        assert "Task completed successfully" in data["data"]["result"]
        assert data["data"]["subagent_type"] == "general"
    
    def test_subagent_type_case_insensitive(self, task_tool, mock_llm):
        """Test that subagent_type is case-insensitive."""
        mock_llm.invoke_raw.return_value = make_raw_response(content="Final Answer: Done")
        
        result = task_tool.run({
            "description": "Test",
            "prompt": "Test",
            "subagent_type": "EXPLORE"
        })
        data = json.loads(result)
        
        assert data["status"] == "success"
        assert data["data"]["subagent_type"] == "explore"
    
    def test_tool_summary_included(self, task_tool, mock_llm):
        """Test that tool summary is included in response."""
        mock_llm.invoke_raw.side_effect = [
            make_raw_response(tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "Grep", "arguments": {"pattern": "test"}},
            }]),
            make_raw_response(content="Final Answer: Found test"),
        ]
        
        result = task_tool.run({
            "description": "Search for test",
            "prompt": "Find test pattern",
            "subagent_type": "explore"
        })
        data = json.loads(result)
        
        assert data["status"] == "success"
        assert "tool_summary" in data["data"]

    def test_prompt_routed_as_user_message(self, task_tool, mock_llm, monkeypatch):
        """Ensure description is in system prompt and prompt is user message."""
        captured = {}

        class DummyRunner:
            def __init__(self, llm, tool_registry, system_prompt, project_root, max_steps):
                captured["system_prompt"] = system_prompt

            def run(self, task_prompt):
                captured["task_prompt"] = task_prompt
                return ("Final Answer: ok", {})

        monkeypatch.setattr(task_module, "SubagentRunner", DummyRunner)
        mock_llm.invoke_raw.return_value = make_raw_response(content="Final Answer: ok")

        result = task_tool.run({
            "description": "Short desc",
            "prompt": "Full detailed task prompt",
            "subagent_type": "general",
        })
        data = json.loads(result)

        assert data["status"] == "success"
        assert "Short desc" in captured["system_prompt"]
        assert "Full detailed task prompt" == captured["task_prompt"]

    def test_persistent_mode_spawns_teammate(self, task_tool):
        fake_manager = Mock()
        fake_manager.spawn_teammate.return_value = {
            "name": "dev",
            "role": "developer",
            "tool_policy": {"allowlist": [], "denylist": ["Task"]},
        }
        task_tool._team_manager = fake_manager

        result = task_tool.run({
            "description": "Team worker",
            "prompt": "Handle backlog",
            "subagent_type": "general",
            "mode": "persistent",
            "team_name": "demo",
            "teammate_name": "dev",
        })
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["mode"] == "persistent"
        fake_manager.spawn_teammate.assert_called_once()


# =============================================================================
# Test Light Model Configuration
# =============================================================================

class TestLightModelConfig:
    """Test light model configuration."""
    
    def test_light_llm_creation_no_config(self):
        """Test that None is returned when light model not configured."""
        # Ensure no light config is set
        with patch.dict(os.environ, {}, clear=True):
            llm = _create_light_llm()
            assert llm is None
    
    def test_light_llm_creation_with_config(self):
        """Test light LLM creation with config."""
        env = {
            "LIGHT_LLM_MODEL_ID": "test-model",
            "LIGHT_LLM_API_KEY": "test-key",
            "LIGHT_LLM_BASE_URL": "http://test.example.com/v1",
        }
        
        with patch.dict(os.environ, env, clear=True):
            with patch("tools.builtin.task.HelloAgentsLLM") as mock_llm_class:
                mock_llm_class.return_value = Mock()
                llm = _create_light_llm()
                
                mock_llm_class.assert_called_once()
                assert llm is not None


# =============================================================================
# Test Error Handling
# =============================================================================

class TestErrorHandling:
    """Test error handling scenarios."""
    
    def test_llm_error_handled(self, task_tool, mock_llm):
        """Test that LLM errors are handled gracefully."""
        mock_llm.invoke_raw.side_effect = Exception("LLM API Error")
        
        result = task_tool.run({
            "description": "Test task",
            "prompt": "Test",
            "subagent_type": "general"
        })
        data = json.loads(result)
        
        # Should still return a valid response structure
        assert data["status"] in ["success", "error"]
        if data["status"] == "success":
            # Error message should be in result
            assert "error" in data["data"]["result"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
