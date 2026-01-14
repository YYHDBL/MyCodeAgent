"""Task tool - Launches a subagent to handle complex tasks in an isolated session.

MVP Implementation following docs/task/task_mvp_design.md:
- Synchronous execution only
- Independent subagent session
- Tool filtering (deny list)
- Two-model routing (main/light)
- Four subagent types: general, explore, summary, plan
"""

import os
import time
import logging
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.llm import HelloAgentsLLM
from core.config import Config
from core.message import Message
from tools.registry import ToolRegistry
from core.context_engine.observation_truncator import truncate_observation
from prompts.tools_prompts.task_prompt import task_prompt
from ..base import Tool, ToolParameter, ErrorCode

# Import subagent prompts
from prompts.agents_prompts.subagent_general_prompt import SUBAGENT_GENERAL_PROMPT
from prompts.agents_prompts.subagent_explore_prompt import SUBAGENT_EXPLORE_PROMPT
from prompts.agents_prompts.subagent_plan_prompt import SUBAGENT_PLAN_PROMPT

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Tool filtering: deny list (always blocked for subagents)
DENIED_TOOLS = frozenset({"Task", "Write", "Edit", "MultiEdit", "Bash"})

# Tool filtering: allow list (default tools for subagents)
ALLOWED_TOOLS = frozenset({"LS", "TodoWrite", "Glob", "Grep", "Read"})

# Valid subagent types
VALID_SUBAGENT_TYPES = frozenset({"general", "explore", "summary", "plan"})

# Model choices
VALID_MODELS = frozenset({"main", "light"})


# =============================================================================
# Subagent prompt mapping
# =============================================================================

def _get_subagent_prompt(subagent_type: str) -> str:
    """Get the system prompt for a given subagent type."""
    prompts = {
        "general": SUBAGENT_GENERAL_PROMPT,
        "explore": SUBAGENT_EXPLORE_PROMPT,
        "plan": SUBAGENT_PLAN_PROMPT,
    }
    
    # Special handling for summary (may need fallback)
    if subagent_type == "summary":
        try:
            # Try to import SUBAGENT_SUMMARY_PROMPT
            # The import structure is unusual, so we handle it carefully
            from prompts.agents_prompts.subagent_summary_prompt import SUBAGENT_SUMMARY_PROMPT
            return SUBAGENT_SUMMARY_PROMPT
        except (ImportError, AttributeError):
            # Fallback summary prompt
            return """
You are a summarization subagent. Your role is to analyze content and produce clear, structured summaries.

Rules
- STRICTLY read-only. Do NOT create, edit, or delete files.
- Do NOT use Bash.
- Do NOT call Task or attempt to spawn other agents.
- Use only the tools provided (LS, Glob, Grep, Read).
- Return file paths relative to the project root.

Guidelines
- Focus on key information and structure.
- Be concise but complete.
- Highlight important patterns and relationships.

Output
- Provide a well-organized summary.
- Use bullet points for clarity.
- Include relevant file paths when applicable.
"""
    
    return prompts.get(subagent_type, SUBAGENT_GENERAL_PROMPT)


# =============================================================================
# Light model configuration
# =============================================================================

def _create_light_llm() -> Optional[HelloAgentsLLM]:
    """
    Create a light model LLM instance from environment config.
    
    Uses LIGHT_LLM_* environment variables. If not configured,
    returns None (caller should fallback to main model).
    """
    light_model = os.getenv("LIGHT_LLM_MODEL_ID")
    light_api_key = os.getenv("LIGHT_LLM_API_KEY")
    light_base_url = os.getenv("LIGHT_LLM_BASE_URL")
    
    # If no light model configured, return None
    if not light_model:
        return None
    
    try:
        return HelloAgentsLLM(
            model=light_model,
            api_key=light_api_key,
            base_url=light_base_url,
            provider=os.getenv("LIGHT_LLM_PROVIDER", "auto"),
            temperature=float(os.getenv("LIGHT_LLM_TEMPERATURE", "0.5")),
        )
    except Exception as e:
        logger.warning("Failed to create light LLM: %s", e)
        return None


# =============================================================================
# Subagent execution
# =============================================================================

class SubagentRunner:
    """
    Runs a subagent with restricted toolset and isolated session.
    
    This is a simplified agent that:
    - Uses a minimal ReAct loop
    - Has restricted tool access
    - Returns a single final result
    """
    
    def __init__(
        self,
        llm: HelloAgentsLLM,
        tool_registry: ToolRegistry,
        system_prompt: str,
        project_root: Path,
        max_steps: int = 15,
        tool_message_format: str = "strict",
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.system_prompt = system_prompt
        self.project_root = project_root
        self.max_steps = max_steps
        self.messages: List[Dict[str, str]] = []
        self.tool_usage: Dict[str, int] = {}
        format_mode = (tool_message_format or "strict").lower().strip()
        self._strict_tools = format_mode in {"strict", "openai", "tool"}
        
    def run(self, task_prompt: str) -> Tuple[str, Dict[str, int]]:
        """
        Execute the subagent and return the final result.
        
        Args:
            task_prompt: The task instructions for the subagent
            
        Returns:
            Tuple of (final_result, tool_usage_summary)
        """
        # Initialize messages with system prompt
        self.messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task_prompt}
        ]
        
        # Simple ReAct loop
        for step in range(self.max_steps):
            # Get LLM response
            try:
                response = self.llm.invoke(self.messages)
            except Exception as e:
                logger.error("Subagent LLM error: %s", e)
                return f"Error: LLM call failed - {str(e)}", self.tool_usage
            
            if not response:
                return "Error: Empty response from subagent", self.tool_usage
            
            # Add assistant response to history (may be enriched with tool_calls)
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": response}
            self.messages.append(assistant_msg)
            
            # Parse for tool call or final answer
            tool_call = self._parse_tool_call(response)
            
            if tool_call is None:
                # No tool call found - this is the final answer
                # Extract the meaningful content (skip thought/action parsing)
                final_result = self._extract_final_answer(response)
                return final_result, self.tool_usage
            
            # Execute tool
            tool_name, tool_input = tool_call

            tool_call_id = f"call_{uuid.uuid4().hex}"
            if self._strict_tools:
                assistant_msg["tool_calls"] = [{
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_input, ensure_ascii=False),
                    },
                }]

            observation = self._execute_tool(tool_name, tool_input)

            # Add observation to history
            if self._strict_tools:
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": observation,
                })
            else:
                self.messages.append({
                    "role": "user",
                    "content": f"Observation ({tool_name}):\n{observation}"
                })
        
        # Max steps reached
        return "Subagent reached maximum steps without completing.", self.tool_usage
    
    def _parse_tool_call(self, response: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Parse a tool call from the response.
        
        Looks for patterns like:
        - ToolName[{...}]
        - Action: ToolName[{...}]
        """
        import re
        import json
        
        # Strip any XML-like tool_call tags the model may emit
        if response and "<tool_call" in response:
            response = re.sub(r"<tool_call>.*?</tool_call>", "", response, flags=re.DOTALL | re.IGNORECASE)
            if "<tool_call" in response:
                lines = []
                for line in response.splitlines():
                    idx = line.find("<tool_call")
                    if idx != -1:
                        line = line[:idx].rstrip()
                    lines.append(line)
                response = "\n".join(lines)

        # Pattern: ToolName[{...}] or Action: ToolName[{...}]
        pattern = r'(?:Action:\s*)?(\w+)\[(\{.*?\})\]'
        match = re.search(pattern, response, re.DOTALL)
        
        if not match:
            # Check for Finish marker
            if "Finish[" in response or response.strip().startswith("Final Answer:"):
                return None
            # No explicit tool call - check if it looks like a final answer
            if any(marker in response.lower() for marker in ["summary:", "result:", "findings:", "answer:"]):
                return None
            # Still no tool call and no final answer marker - might be done
            if len(self.messages) > 3:  # Has some history
                return None
            return None
        
        tool_name = match.group(1)
        try:
            tool_input = json.loads(match.group(2))
        except json.JSONDecodeError:
            logger.warning("Failed to parse tool input: %s", match.group(2))
            return None
        
        return tool_name, tool_input
    
    def _execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Execute a tool and return the observation."""
        # Validate tool is allowed
        if tool_name in DENIED_TOOLS:
            return f"Error: Tool '{tool_name}' is not allowed for subagents."
        
        # Get tool from registry
        tool = self.tool_registry.get_tool(tool_name)
        if tool is None:
            return f"Error: Tool '{tool_name}' not found."
        
        # Track tool usage
        self.tool_usage[tool_name] = self.tool_usage.get(tool_name, 0) + 1
        
        # Execute tool
        try:
            result = tool.run(tool_input)
            result_str = str(result)
            return truncate_observation(tool_name, result_str, str(self.project_root))
        except Exception as e:
            logger.error("Tool execution error: %s", e)
            return f"Error executing tool: {str(e)}"
    
    def _extract_final_answer(self, response: str) -> str:
        """Extract the final answer from the response."""
        # Remove common prefixes
        result = response
        
        # Remove "Thought:" sections
        if "Thought:" in result:
            parts = result.split("Thought:")
            # Take the last non-thought part
            for part in reversed(parts):
                clean = part.strip()
                if clean and not clean.startswith("I need") and not clean.startswith("Let me"):
                    result = clean
                    break
        
        # Remove "Final Answer:" prefix
        if "Final Answer:" in result:
            result = result.split("Final Answer:", 1)[1].strip()
        
        # Remove "Finish[" wrapper if present
        if "Finish[" in result:
            import re
            match = re.search(r'Finish\["(.*)"\]', result, re.DOTALL)
            if match:
                result = match.group(1)
        
        return result.strip()


# =============================================================================
# Task Tool
# =============================================================================

class TaskTool(Tool):
    """
    Task tool - Launches a subagent to handle complex tasks.
    
    Follows the MVP design in docs/task/task_mvp_design.md:
    - Synchronous execution
    - Tool filtering (deny list)
    - Two-model routing (main/light)
    - Four subagent types: general, explore, summary, plan
    """
    
    def __init__(
        self,
        name: str = "Task",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
        main_llm: Optional[HelloAgentsLLM] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        if main_llm is None:
            raise ValueError("main_llm must be provided by the framework")
        if tool_registry is None:
            raise ValueError("tool_registry must be provided by the framework")
        
        super().__init__(
            name=name,
            description=task_prompt,
            project_root=project_root,
            working_dir=working_dir if working_dir else project_root,
        )
        
        self._main_llm = main_llm
        self._light_llm: Optional[HelloAgentsLLM] = None
        self._tool_registry = tool_registry
        self._subagent_max_steps = int(os.getenv("SUBAGENT_MAX_STEPS", "15"))
        self._tool_message_format = Config.from_env().tool_message_format
    
    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="description",
                type="string",
                description="Short summary of the delegated task",
                required=True,
            ),
            ToolParameter(
                name="prompt",
                type="string",
                description="Full, self-contained instructions for the subagent",
                required=True,
            ),
            ToolParameter(
                name="subagent_type",
                type="string",
                description="Role to select a system prompt: general | explore | summary | plan",
                required=True,
            ),
            ToolParameter(
                name="model",
                type="string",
                description="Choose 'main' or 'light'. Default is 'light'.",
                required=False,
                default="light",
            ),
        ]
    
    def run(self, parameters: Dict[str, Any]) -> str:
        start_time = time.monotonic()
        params_input = dict(parameters)
        
        # Validate required parameters
        description = parameters.get("description")
        prompt = parameters.get("prompt")
        subagent_type = parameters.get("subagent_type", "general")
        model_choice = parameters.get("model", "light")
        
        # Validate description
        if not isinstance(description, str) or not description.strip():
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'description' is required and must be a non-empty string.",
                params_input=params_input,
            )
        
        # Validate prompt
        if not isinstance(prompt, str) or not prompt.strip():
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'prompt' is required and must be a non-empty string.",
                params_input=params_input,
            )
        
        # Validate subagent_type
        subagent_type = subagent_type.lower().strip()
        if subagent_type not in VALID_SUBAGENT_TYPES:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message=f"Invalid subagent_type '{subagent_type}'. Valid options: {', '.join(sorted(VALID_SUBAGENT_TYPES))}",
                params_input=params_input,
            )
        
        # Validate model choice
        model_choice = model_choice.lower().strip()
        if model_choice not in VALID_MODELS:
            model_choice = "light"  # Default to light
        
        # Select LLM
        llm = self._select_llm(model_choice)
        
        # Build subagent system prompt
        role_prompt = _get_subagent_prompt(subagent_type)
        system_prompt = f"{role_prompt}\n\n# Task\n{description}"
        
        # Create filtered tool registry for subagent
        subagent_tools = self._create_filtered_registry()
        
        # Create and run subagent
        try:
            runner = SubagentRunner(
                llm=llm,
                tool_registry=subagent_tools,
                system_prompt=system_prompt,
                project_root=self._project_root,
                max_steps=self._subagent_max_steps,
                tool_message_format=self._tool_message_format,
            )
            
            result, tool_usage = runner.run(prompt)
            
        except Exception as e:
            logger.exception("Subagent execution error")
            return self.create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Subagent execution failed: {str(e)}",
                params_input=params_input,
                time_ms=int((time.monotonic() - start_time) * 1000),
            )
        
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        
        # Build tool summary
        tool_summary = [
            {"tool": name, "count": count}
            for name, count in sorted(tool_usage.items())
        ]
        
        # Build response
        data = {
            "status": "completed",
            "result": result,
            "tool_summary": tool_summary,
            "model_used": model_choice,
            "subagent_type": subagent_type,
        }
        
        text = f"Subagent ({subagent_type}, {model_choice}) completed.\n\n{result}"
        
        return self.create_success_response(
            data=data,
            text=text,
            params_input=params_input,
            time_ms=elapsed_ms,
            extra_stats={
                "tool_calls": sum(tool_usage.values()),
                "model": model_choice,
            },
        )
    
    def _select_llm(self, model_choice: str) -> HelloAgentsLLM:
        """Select the appropriate LLM based on model choice."""
        if model_choice == "light":
            # Try to use light model
            if self._light_llm is None:
                self._light_llm = _create_light_llm()
            
            if self._light_llm is not None:
                return self._light_llm
            
            # Fallback to main if light not configured
            logger.debug("Light model not configured, using main model")
        
        return self._main_llm
    
    def _create_filtered_registry(self) -> ToolRegistry:
        """Create a tool registry with only allowed tools for subagents."""
        filtered = ToolRegistry()
        
        for tool in self._tool_registry.get_all_tools():
            tool_name = tool.name
            
            # Skip denied tools
            if tool_name in DENIED_TOOLS:
                continue
            
            # Include allowed tools
            if tool_name in ALLOWED_TOOLS:
                filtered.register_tool(tool)
        
        return filtered
