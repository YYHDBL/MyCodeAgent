"""最小可用测试 Agent"""

from typing import Any, Optional

from core.agent import Agent
from core.message import Message
from core.llm import HelloAgentsLLM
from core.config import Config
from utils import setup_logger
from tools.registry import ToolRegistry

from tools.builtin.list_files import ListFilesTool
from tools.builtin.search_files_by_name import SearchFilesByNameTool
from tools.builtin.search_code import GrepTool
from agentEngines.ReActEngine import ReActEngine


class TestAgent(Agent):
    """最简单的测试 Agent，用于验证日志与输出"""

    def __init__(
        self,
        name: str,
        llm: HelloAgentsLLM,
        system_prompt: Optional[str] = None,
        config: Optional[Config] = None,
        tool_registry: Optional[ToolRegistry] = None,
        project_root: Optional[str] = None,
        logger=None,
    ):
        super().__init__(name=name, llm=llm, system_prompt=system_prompt, config=config)
        self.logger = logger or setup_logger(
            name=f"agent.{self.name}",
            level=self.config.log_level,
        )
        self.last_response_raw: Optional[Any] = None
        self.tool_registry = tool_registry or ToolRegistry()
        self.project_root = project_root
        # 给 TestAgent 注册计算器工具
        self.tool_registry.register_tool(
            ListFilesTool(project_root=self.project_root, working_dir=self.project_root)
        )
        self.tool_registry.register_tool(SearchFilesByNameTool(project_root=self.project_root))
        self.tool_registry.register_tool(GrepTool(project_root=self.project_root))
        # 以 ReActEngine 作为核心
        self.engine = ReActEngine(
            llm=self.llm,
            tool_registry=self.tool_registry,
            max_steps=8,
            verbose=True,
        )

    def run(self, input_text: str, **kwargs) -> str:
        use_llm = kwargs.pop("use_llm", False)
        use_react = kwargs.pop("use_react", True)
        show_raw = kwargs.pop("show_raw", False)

        self.logger.info("TestAgent start")
        self.logger.info("input_text=%s", input_text)

        response_text = None

        if use_react:
            history_lines = "\n".join(
                f"{m.role}: {m.content}" for m in self.get_history()
            ) or "(empty)"
            context_parts = []
            if self.system_prompt:
                context_parts.append(self.system_prompt)
            context_parts.append(f"[Chat History]\n{history_lines}")
            context_prompt = "\n\n".join(context_parts)

            self.engine.capture_raw = show_raw
            response_text = self.engine.run(
                question=input_text,
                context_prompt=context_prompt,
            )
            self.last_response_raw = self.engine.last_response_raw
        elif use_llm:
            user_message = Message(content=input_text, role="user")
            messages = []
            if self.system_prompt:
                messages.append({"role": "system", "content": self.system_prompt})
            messages.extend([m.to_dict() for m in self.get_history()])
            messages.append(user_message.to_dict())

            if show_raw:
                raw_response = self.llm.invoke_raw(messages, **kwargs)
                self.last_response_raw = (
                    raw_response.model_dump()
                    if hasattr(raw_response, "model_dump")
                    else raw_response
                )
                try:
                    response_text = raw_response.choices[0].message.content
                except Exception:
                    response_text = str(raw_response)
            else:
                self.last_response_raw = None
                response_text = self.llm.invoke(messages, **kwargs)
        else:
            self.last_response_raw = None
            response_text = f"TestAgent({self.name}) received: {input_text}"

        user_message = Message(content=input_text, role="user")
        self.add_message(user_message)
        assistant_message = Message(content=response_text, role="assistant")
        self.add_message(assistant_message)

        # Avoid duplicating full assistant output in stdout; keep detailed content at DEBUG.
        self.logger.debug("response=%s", response_text)
        self.logger.info("history_size=%d", len(self.get_history()))
        return response_text
