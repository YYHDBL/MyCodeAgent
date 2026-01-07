"""Context builder for ReAct prompt assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import runpy
from typing import List, Optional

from tools.registry import ToolRegistry


DEFAULT_REACT_TEMPLATE = """# L1: System Static Layer
{system_prompt}

{code_law}

## 任务背景
{context}

## 当前问题
Question: {question}

## 执行历史（Action/Observation）
{history}

现在开始："""


@dataclass
class ContextBuilder:
    """Builds the full prompt for the ReAct loop."""

    tool_registry: ToolRegistry
    project_root: str
    system_prompt_override: Optional[str] = None
    template: str = DEFAULT_REACT_TEMPLATE
    _cached_code_law: str = field(default="", init=False)
    _cached_code_law_mtime: Optional[float] = field(default=None, init=False)

    def build(self, question: str, context_prompt: str, scratchpad: List[str]) -> str:
        system_prompt = self._load_system_prompt()
        tools_prompt = self._load_tool_prompts()
        if tools_prompt:
            if "{tools}" in system_prompt:
                system_prompt = system_prompt.replace("{tools}", tools_prompt)
            else:
                system_prompt = f"{system_prompt}\n\n# Tools Prompts\n{tools_prompt}"
        code_law = self._load_code_law()
        code_law_block = f"## CODE_LAW\n{code_law}" if code_law else ""
        history_str = "\n".join(scratchpad) if scratchpad else "(empty)"
        return self.template.format(
            system_prompt=system_prompt.strip(),
            code_law=code_law_block.strip(),
            context=context_prompt,
            question=question,
            history=history_str,
        )

    def _load_system_prompt(self) -> str:
        if self.system_prompt_override:
            return self.system_prompt_override
        prompt_path = Path(self.project_root) / "prompts" / "agents_prompts" / "L1_system_prompt.py"
        if not prompt_path.exists():
            return ""
        data = runpy.run_path(str(prompt_path))
        prompt = data.get("system_prompt", "")
        return prompt if isinstance(prompt, str) else ""

    def _load_tool_prompts(self) -> str:
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
                    prompts.append(value.strip())
        return "\n\n".join(p for p in prompts if p)

    def _load_code_law(self) -> str:
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
