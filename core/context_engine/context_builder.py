"""Context builder for ReAct prompt assembly.

重构为 Message List 自然累积模式：
- 不再拼接 scratchpad，每步历史由 messages 自然累积
- L1/L2 用 role=system 放在 messages 头部
- L3 就是 messages 中的 user/assistant/tool
- L4 当前用户输入以 role=user 追加
- Todo recap 作为 tool message 自然进入上下文

Messages 格式：
[
  {"role": "system", "content": "L1 系统提示 + 工具说明"},
  {"role": "system", "content": "L2: CODE_LAW.md（如有）"},
  {"role": "user", "content": "...问题..."},
  {"role": "assistant", "content": "Thought: ...\nAction: ..."},
  {"role": "tool", "content": "{压缩后的JSON}", "tool_name": "Grep"},
  ...
]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import runpy
from typing import List, Optional, Dict, Any


@dataclass
class ContextBuilder:
    """
    构建 ReAct 循环的 messages 列表
    
    Message List 模式：
    - L1(system+tools) 作为第一个 system message
    - L2(CODE_LAW) 作为第二个 system message（如有）
    - L3(history) 由 HistoryManager 提供的 messages 列表
    - L4(user input) 已包含在 history 中
    - Todo recap 作为 tool message 自然存在于 history 中
    """

    tool_registry: "ToolRegistry"  # noqa: F821
    project_root: str
    system_prompt_override: Optional[str] = None
    mcp_tools_prompt: Optional[str] = None
    skills_prompt: Optional[str] = None
    _cached_code_law: str = field(default="", init=False)
    _cached_code_law_mtime: Optional[float] = field(default=None, init=False)
    _cached_system_messages: Optional[List[Dict[str, Any]]] = field(default=None, init=False)
    _mcp_tools_prompt: str = field(default="", init=False)
    _skills_prompt: str = field(default="", init=False)

    def build_messages(
        self,
        history_messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        构建完整的 messages 列表
        
        Args:
            history_messages: 来自 HistoryManager.to_messages() 的历史消息列表
        
        Returns:
            完整的 messages 列表，可直接传给 LLM
        """
        messages: List[Dict[str, Any]] = []
        
        # L1: System prompt + Tools（缓存）
        system_messages = self._get_system_messages()
        messages.extend(system_messages)
        
        # L3/L4: History messages（包含 user/assistant/tool/summary）
        messages.extend(history_messages)
        
        return messages

    def get_system_messages(self) -> List[Dict[str, Any]]:
        """获取 system messages（供日志记录等使用）"""
        system_messages = self._get_system_messages()
        return [dict(m) for m in system_messages]
    
    def _get_system_messages(self) -> List[Dict[str, Any]]:
        """获取系统消息（带缓存）"""
        # 检查 CODE_LAW 是否更新
        code_law = self._load_code_law()

        if self._mcp_tools_prompt == "" and self.mcp_tools_prompt:
            self._mcp_tools_prompt = self.mcp_tools_prompt
        if self._skills_prompt == "" and self.skills_prompt:
            self._skills_prompt = self.skills_prompt

        # 如果缓存有效且 CODE_LAW 未变，直接返回
        if self._cached_system_messages is not None:
            # 检查 CODE_LAW 是否需要更新
            has_code_law_msg = len(self._cached_system_messages) > 1
            if (code_law and has_code_law_msg) or (not code_law and not has_code_law_msg):
                return self._cached_system_messages
        
        # 重新构建
        messages: List[Dict[str, Any]] = []
        
        # L1: System prompt + Tools
        system_prompt = self._load_system_prompt()
        tools_prompt = self._load_tool_prompts()
        if tools_prompt:
            if "{tools}" in system_prompt:
                system_prompt = system_prompt.replace("{tools}", tools_prompt)
            else:
                system_prompt = f"{system_prompt}\n\n# Available Tools\n{tools_prompt}"

        if self._mcp_tools_prompt:
            system_prompt = f"{system_prompt}\n\n# MCP Tools\n{self._mcp_tools_prompt}"
        
        if system_prompt.strip():
            messages.append({
                "role": "system",
                "content": system_prompt.strip(),
            })
        
        # L2: CODE_LAW
        if code_law:
            messages.append({
                "role": "system",
                "content": f"# Project Rules (CODE_LAW)\n{code_law}",
            })
        
        self._cached_system_messages = messages
        return messages

    def set_mcp_tools_prompt(self, prompt: str) -> None:
        """更新 MCP 工具提示，并清空 system cache。"""
        self._mcp_tools_prompt = prompt or ""
        self._cached_system_messages = None

    def set_skills_prompt(self, prompt: str) -> None:
        """更新 Skills 提示，并清空 system cache。"""
        self._skills_prompt = prompt or ""
        self._cached_system_messages = None

    def _load_system_prompt(self) -> str:
        """加载 L1 系统 prompt"""
        if self.system_prompt_override:
            return self.system_prompt_override
        prompt_path = Path(self.project_root) / "prompts" / "agents_prompts" / "L1_system_prompt.py"
        if not prompt_path.exists():
            return ""
        data = runpy.run_path(str(prompt_path))
        prompt = data.get("system_prompt", "")
        return prompt if isinstance(prompt, str) else ""

    def _load_tool_prompts(self) -> str:
        """加载所有工具的 prompt"""
        prompts_dir = Path(self.project_root) / "prompts" / "tools_prompts"
        if not prompts_dir.exists():
            return ""
        prompts: List[str] = []
        for path in sorted(prompts_dir.glob("*.py")):
            if path.name.startswith("__"):
                continue
            data = runpy.run_path(str(path))
            for name, value in data.items():
                if name.endswith("_prompt") and isinstance(value, str):
                    prompt_value = value.strip()
                    if self._skills_prompt and "{{available_skills}}" in prompt_value:
                        prompt_value = prompt_value.replace("{{available_skills}}", self._skills_prompt)
                    prompts.append(prompt_value)
        return "\n\n".join(p for p in prompts if p)

    def _load_code_law(self) -> str:
        """加载 CODE_LAW.md（带 mtime 缓存）"""
        for filename in ("code_law.md", "CODE_LAW.md"):
            code_law_path = Path(self.project_root) / filename
            if not code_law_path.exists():
                continue
            try:
                mtime = code_law_path.stat().st_mtime
            except OSError:
                return ""
            if self._cached_code_law_mtime == mtime and self._cached_code_law:
                return self._cached_code_law
            try:
                self._cached_code_law = code_law_path.read_text(encoding="utf-8")
            except OSError:
                self._cached_code_law = ""
            self._cached_code_law_mtime = mtime
            return self._cached_code_law
        return ""
    
    # 兼容旧接口已移除，请使用 build_messages()
