from typing import Any, Optional

from core.agent import Agent
from core.llm import HelloAgentsLLM
from core.message import Message
from core.config import Config
from tools.registry import ToolRegistry
from tools.builtin.list_files import ListFilesTool
from tools.builtin.search_files_by_name import SearchFilesByNameTool
from tools.builtin.search_code import GrepTool
from tools.builtin.read_file import ReadTool
from tools.builtin.write_file import WriteTool
from tools.builtin.edit_file import EditTool
from tools.builtin.edit_file_multi import MultiEditTool
from utils import setup_logger
# 引入上面的 Engine
from agentEngines.ReActEngine import ReActEngine 

class CodeAgent(Agent):
    def __init__(
        self, 
        name: str, 
        llm: HelloAgentsLLM, 
        tool_registry: ToolRegistry,
        project_root: str,  # Code Agent 特有的属性
        system_prompt: Optional[str] = None,
        config: Optional[Config] = None,
        logger=None,
    ):
        super().__init__(name, llm, system_prompt=system_prompt, config=config)
        self.project_root = project_root
        self.tool_registry = tool_registry
        self.logger = logger or setup_logger(
            name=f"agent.{self.name}",
            level=self.config.log_level,
        )
        self.last_response_raw: Optional[Any] = None
        # 注册 LS/list_files 工具
        self.tool_registry.register_tool(
            ListFilesTool(project_root=self.project_root, working_dir=self.project_root)
        )
        # 注册 Glob/search_files_by_name 工具
        self.tool_registry.register_tool(SearchFilesByNameTool(project_root=self.project_root))
        # 注册 Grep 工具
        self.tool_registry.register_tool(GrepTool(project_root=self.project_root))
        # 注册 Read 工具
        self.tool_registry.register_tool(ReadTool(project_root=self.project_root))
        # 注册 Write 工具
        self.tool_registry.register_tool(WriteTool(project_root=self.project_root))
        # 注册 Edit 工具
        self.tool_registry.register_tool(EditTool(project_root=self.project_root))
        # 注册 MultiEdit 工具
        self.tool_registry.register_tool(MultiEditTool(project_root=self.project_root))
        
        # 【核心点】组合 ReActEngine
        # 我们在这里把工具给 Engine
        self.engine = ReActEngine(
            llm=llm,
            tool_registry=self.tool_registry,
            max_steps=50, # Code 任务通常需要更多步骤
            verbose=True
        )

    def run(self, input_text: str, **kwargs) -> str:
        """
        Code Agent 的入口。
       
        """
        show_raw = kwargs.pop("show_raw", False)

        # self.logger.info("CodeAgent start")
        # self.logger.info("input_text=%s", input_text)

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

        user_message = Message(content=input_text, role="user")
        self.add_message(user_message)
        assistant_message = Message(content=response_text, role="assistant")
        self.add_message(assistant_message)

        # Avoid duplicating full assistant output in stdout; keep detailed content at DEBUG.
        self.logger.debug("response=%s", response_text)
        self.logger.info("history_size=%d", len(self.get_history()))
        return response_text

   
