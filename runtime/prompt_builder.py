"""Context builder for ReAct prompt assembly.

重构为 Message List 自然累积模式：
- 不再拼接 scratchpad，每步历史由 messages 自然累积
- L1/L2 用 role=system 放在 messages 头部
- L3 就是 messages 中的 user/assistant/tool
- L4 当前用户输入以 role=user 追加
- Todo recap 作为观察消息进入上下文（strict 时为 tool，否则为 user observation）

Messages 格式：
[
  {"role": "system", "content": "L1 系统提示 + 工具说明"},
  {"role": "system", "content": "L2: CODE_LAW.md（如有）"},
  {"role": "user", "content": "...问题..."},
  {"role": "assistant", "content": "...", "tool_calls": [...]},
  {"role": "tool", "tool_call_id": "...", "content": "{压缩后的JSON}"},
  ...
]
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
import runpy
from typing import List, Optional, Dict, Any


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _hash_json(data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PromptAssembly:
    constitution_messages: List[Dict[str, Any]]
    tool_contract_messages: List[Dict[str, Any]]
    project_rule_messages: List[Dict[str, Any]]
    stable_messages: List[Dict[str, Any]]
    runtime_signal_messages: List[Dict[str, Any]]
    all_system_messages: List[Dict[str, Any]]
    constitution_fingerprint: str
    tool_contracts_fingerprint: str
    project_rules_fingerprint: str
    runtime_signals_fingerprint: str
    system_fingerprint: str


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
    resource_root: Optional[str] = None
    system_prompt_override: Optional[str] = None
    mcp_tools_prompt: Optional[str] = None
    skills_prompt: Optional[str] = None
    tool_prompt_allowlist: Optional[frozenset[str]] = None
    _cached_code_law: str = field(default="", init=False)
    _cached_code_law_mtime: Optional[float] = field(default=None, init=False)
    _cached_code_law_hash: str = field(default="", init=False)
    _cached_assembly: Optional[PromptAssembly] = field(default=None, init=False)
    _mcp_tools_prompt: str = field(default="", init=False)
    _skills_prompt: str = field(default="", init=False)
    _runtime_system_blocks: List[str] = field(default_factory=list, init=False)

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
        assembly = self.get_prompt_assembly()
        return [dict(m) for m in assembly.all_system_messages]

    def get_prompt_assembly(self) -> PromptAssembly:
        constitution_text = self._load_system_prompt().replace("{tools}", "").strip()
        code_law = self._load_code_law()

        if self._mcp_tools_prompt == "" and self.mcp_tools_prompt:
            self._mcp_tools_prompt = self.mcp_tools_prompt
        if self._skills_prompt == "" and self.skills_prompt:
            self._skills_prompt = self.skills_prompt

        tool_contracts_text = self._load_tool_prompts().strip()
        runtime_signal_messages = self._build_runtime_signal_messages()
        runtime_signals_fingerprint = _hash_json(runtime_signal_messages)

        constitution_messages: List[Dict[str, Any]] = []
        if constitution_text:
            constitution_messages.append({"role": "system", "content": constitution_text})

        tool_contract_messages: List[Dict[str, Any]] = []
        if tool_contracts_text:
            tool_contract_messages.append(
                {
                    "role": "system",
                    "content": f"# Tool Contracts\n{tool_contracts_text}",
                }
            )

        project_rule_messages: List[Dict[str, Any]] = []
        if code_law:
            project_rule_messages.append(
                {
                    "role": "system",
                    "content": f"# Project Rules (CODE_LAW)\n{code_law}",
                }
            )

        constitution_fingerprint = _hash_json(constitution_messages)
        tool_contracts_fingerprint = _hash_json(tool_contract_messages)
        project_rules_fingerprint = _hash_json(project_rule_messages)
        system_fingerprint = _hash_json(
            {
                "constitution": constitution_fingerprint,
                "tool_contracts": tool_contracts_fingerprint,
                "project_rules": project_rules_fingerprint,
            }
        )

        if (
            self._cached_assembly is not None
            and self._cached_assembly.system_fingerprint == system_fingerprint
            and self._cached_assembly.runtime_signals_fingerprint == runtime_signals_fingerprint
        ):
            return self._cached_assembly

        stable_messages = constitution_messages + tool_contract_messages + project_rule_messages
        assembly = PromptAssembly(
            constitution_messages=constitution_messages,
            tool_contract_messages=tool_contract_messages,
            project_rule_messages=project_rule_messages,
            stable_messages=stable_messages,
            runtime_signal_messages=runtime_signal_messages,
            all_system_messages=stable_messages + runtime_signal_messages,
            constitution_fingerprint=constitution_fingerprint,
            tool_contracts_fingerprint=tool_contracts_fingerprint,
            project_rules_fingerprint=project_rules_fingerprint,
            runtime_signals_fingerprint=runtime_signals_fingerprint,
            system_fingerprint=system_fingerprint,
        )
        self._cached_assembly = assembly
        return assembly

    def _get_system_messages(self) -> List[Dict[str, Any]]:
        """获取系统消息（带缓存）"""
        return self.get_prompt_assembly().all_system_messages

    def set_mcp_tools_prompt(self, prompt: str) -> None:
        """更新 MCP 工具提示，并清空 system cache。"""
        normalized = prompt or ""
        if normalized == self._mcp_tools_prompt:
            return
        self._mcp_tools_prompt = normalized
        self._cached_assembly = None

    def set_skills_prompt(self, prompt: str) -> None:
        """更新 Skills 提示，并清空 system cache。"""
        normalized = prompt or ""
        if normalized == self._skills_prompt:
            return
        self._skills_prompt = normalized
        self._cached_assembly = None

    def set_runtime_system_blocks(self, blocks: List[str]) -> None:
        """设置 runtime 通知块（注入 system，不污染 user 轮次）。"""
        normalized = [str(block).strip() for block in (blocks or []) if str(block).strip()]
        if normalized == self._runtime_system_blocks:
            return
        self._runtime_system_blocks = normalized
        self._cached_assembly = None

    def _load_system_prompt(self) -> str:
        """加载 L1 系统 prompt"""
        if self.system_prompt_override:
            return self.system_prompt_override
        prompt_path = self._resource_root() / "prompts" / "agents_prompts" / "L1_system_prompt.py"
        if not prompt_path.exists():
            return ""
        data = runpy.run_path(str(prompt_path))
        prompt = data.get("system_prompt", "")
        return prompt if isinstance(prompt, str) else ""

    def _load_tool_prompts(self) -> str:
        """加载所有工具的 prompt"""
        prompts_dir = self._resource_root() / "prompts" / "tools_prompts"
        prompts: List[str] = []
        allowed_names = None
        if self.tool_prompt_allowlist is not None:
            allowed_names = {
                "".join(character for character in tool_name.lower() if character.isalnum())
                for tool_name in self.tool_prompt_allowlist
            }
        if prompts_dir.exists():
            for path in sorted(prompts_dir.glob("*.py")):
                if path.name.startswith("__"):
                    continue
                data = runpy.run_path(str(path))
                for name, value in data.items():
                    if name.endswith("_prompt") and isinstance(value, str):
                        if allowed_names is not None:
                            prompt_tool_name = "".join(
                                character
                                for character in name[: -len("_prompt")].lower()
                                if character.isalnum()
                            )
                            if prompt_tool_name not in allowed_names:
                                continue
                        prompt_value = value.strip()
                        if self._skills_prompt and "{{available_skills}}" in prompt_value:
                            prompt_value = prompt_value.replace("{{available_skills}}", self._skills_prompt)
                        prompts.append(prompt_value)
        if self._mcp_tools_prompt:
            prompts.append(f"## MCP Tools\n{self._mcp_tools_prompt}")
        # 追加被熔断禁用的工具提示（避免无效调用）
        disabled_tools = []
        if hasattr(self.tool_registry, "get_disabled_tools"):
            try:
                disabled_tools = self.tool_registry.get_disabled_tools()
            except Exception:
                disabled_tools = []
        if disabled_tools:
            block = ["## Disabled Tools (temporary)\n"]
            for name in sorted(disabled_tools):
                block.append(f"- {name}\n")
            prompts.append("".join(block))
        return "\n\n".join(p for p in prompts if p)

    def _resource_root(self) -> Path:
        return Path(self.resource_root or self.project_root)

    def _load_code_law(self) -> str:
        """加载 CODE_LAW.md（基于内容 hash 刷新缓存）"""
        for filename in ("code_law.md", "CODE_LAW.md"):
            code_law_path = Path(self.project_root) / filename
            if not code_law_path.exists():
                continue
            try:
                mtime = code_law_path.stat().st_mtime
                content = code_law_path.read_text(encoding="utf-8")
            except OSError:
                return ""
            content_hash = _hash_text(content)
            if (
                self._cached_code_law_mtime == mtime
                and self._cached_code_law_hash == content_hash
                and self._cached_code_law == content
            ):
                return self._cached_code_law
            self._cached_code_law = content
            self._cached_code_law_mtime = mtime
            self._cached_code_law_hash = content_hash
            self._cached_assembly = None
            return self._cached_code_law
        return ""

    def _build_runtime_signal_messages(self) -> List[Dict[str, Any]]:
        return [{"role": "system", "content": block} for block in self._runtime_system_blocks]
    
