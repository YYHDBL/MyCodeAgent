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
from core.message import Message
from tools.registry import ToolRegistry
from core.context_engine.observation_truncator import truncate_observation
from prompts.tools_prompts.task_prompt import task_prompt
from ..base import Tool, ToolParameter, ErrorCode
from core.env import load_env

load_env()

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
        max_steps: int = 50,
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.system_prompt = system_prompt
        self.project_root = project_root
        self.max_steps = max_steps
        self.messages: List[Dict[str, str]] = []
        self.tool_usage: Dict[str, int] = {}
        
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
        
        tools_schema = self._get_allowed_tools_schema()
        tool_choice = "auto"

        # Simple ReAct loop
        for step in range(self.max_steps):
            # Get LLM response
            try:
                raw_response = self.llm.invoke_raw(self.messages, tools=tools_schema, tool_choice=tool_choice)
            except Exception as e:
                logger.error("Subagent LLM error: %s", e)
                return f"Error: LLM call failed - {str(e)}", self.tool_usage

            response_text = self._extract_content(raw_response) or ""
            tool_calls = self._extract_tool_calls(raw_response)

            if not tool_calls and not response_text.strip():
                return "Error: Empty response from subagent", self.tool_usage

            # Add assistant response to history (with tool_calls if any)
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": response_text}
            if tool_calls:
                for call in tool_calls:
                    if not call.get("id"):
                        call["id"] = f"call_{uuid.uuid4().hex}"
                assistant_msg["tool_calls"] = []
                for call in tool_calls:
                    arguments = call.get("arguments") or {}
                    args_str = arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)
                    assistant_msg["tool_calls"].append({
                        "id": call.get("id"),
                        "type": "function",
                        "function": {"name": call.get("name"), "arguments": args_str},
                    })
            self.messages.append(assistant_msg)

            if not tool_calls:
                final_result = self._extract_final_answer(response_text)
                return final_result, self.tool_usage

            # Execute tools
            for call in tool_calls:
                tool_name = call.get("name") or "unknown_tool"
                tool_call_id = call.get("id") or f"call_{uuid.uuid4().hex}"
                tool_input, parse_err = self._ensure_json_input(call.get("arguments"))
                if parse_err:
                    observation = json.dumps({
                        "status": "error",
                        "error": {"code": "INVALID_PARAM", "message": f"Tool arguments parse error: {parse_err}"},
                        "data": {},
                    }, ensure_ascii=False)
                else:
                    observation = self._execute_tool(tool_name, tool_input)

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": observation,
                })
        
        # Max steps reached
        return "Subagent reached maximum steps without completing.", self.tool_usage
    
    def _get_allowed_tools_schema(self) -> list[dict[str, Any]]:
        tools = self.tool_registry.get_openai_tools()
        return [t for t in tools if t.get("function", {}).get("name") in ALLOWED_TOOLS]

    @staticmethod
    def _extract_content(raw_response: Any) -> Optional[str]:
        try:
            if hasattr(raw_response, "choices"):
                content = raw_response.choices[0].message.content
                if isinstance(content, list):
                    return "".join(part.get("text", "") for part in content if isinstance(part, dict))
                return content
            if isinstance(raw_response, dict) and raw_response.get("choices"):
                content = raw_response["choices"][0]["message"].get("content")
                if isinstance(content, list):
                    return "".join(part.get("text", "") for part in content if isinstance(part, dict))
                return content
        except Exception:
            return str(raw_response)

    @staticmethod
    def _extract_tool_calls(raw_response: Any) -> list[dict[str, Any]]:
        def _get_attr(obj, key: str):
            if obj is None:
                return None
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        try:
            choices = _get_attr(raw_response, "choices")
            if not choices:
                return []
            choice = choices[0]
            message = _get_attr(choice, "message")
            if not message:
                return []
            tool_calls = _get_attr(message, "tool_calls") or []
            calls: list[dict[str, Any]] = []
            if tool_calls:
                for call in tool_calls:
                    fn = _get_attr(call, "function") or {}
                    name = _get_attr(fn, "name") or _get_attr(call, "name") or "unknown_tool"
                    arguments = _get_attr(fn, "arguments") or _get_attr(call, "arguments") or {}
                    call_id = _get_attr(call, "id")
                    calls.append({"id": call_id, "name": name, "arguments": arguments})
                return calls

            function_call = _get_attr(message, "function_call")
            if function_call:
                name = _get_attr(function_call, "name") or "unknown_tool"
                arguments = _get_attr(function_call, "arguments") or {}
                return [{"id": None, "name": name, "arguments": arguments}]
        except Exception:
            return []

        return []
    
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
        return (response or "").strip()

    @staticmethod
    def _ensure_json_input(raw: Any) -> Tuple[Any, Optional[str]]:
        if raw is None:
            return {}, None
        if isinstance(raw, (dict, list)):
            return raw, None
        s = str(raw).strip()
        if not s:
            return {}, None
        try:
            return json.loads(s), None
        except Exception as e:
            return None, str(e)


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
        self._subagent_max_steps = int(os.getenv("SUBAGENT_MAX_STEPS", "50"))
    
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
