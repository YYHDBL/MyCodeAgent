"""Skill tool - loads skill instructions from project-local skills."""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from extensions.skills.loader import SkillLoader
from prompts.tools_prompts.skill_prompt import skill_prompt
from ..base import Tool, ToolParameter, ToolResult, ErrorCode
from core.env import load_env

load_env()


class SkillTool(Tool):
    """Load a skill by name and return its expanded content."""

    def __init__(
        self,
        name: str = "Skill",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
        skill_loader: Optional[SkillLoader] = None,
        refresh_on_call: bool = False,
    ):
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")

        super().__init__(
            name=name,
            description=skill_prompt,
            project_root=project_root,
            working_dir=working_dir if working_dir else project_root,
        )

        self._skill_loader = skill_loader or SkillLoader(str(self._project_root))
        self._refresh_on_call = bool(refresh_on_call)

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="name",
                type="string",
                description="Skill name",
                required=True,
            ),
            ToolParameter(
                name="args",
                type="string",
                description="Optional arguments for the skill",
                required=False,
                default="",
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResult:
        start_time = time.monotonic()
        params_input = dict(parameters)

        name = parameters.get("name")
        args = parameters.get("args") or ""

        if not isinstance(name, str) or not name.strip():
            return self.error_result(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'name' is required and must be a non-empty string.",
                params_input=params_input,
            )

        refresh = self._refresh_on_call
        skill_meta = self._skill_loader.get_skill(name.strip(), refresh=refresh)
        if not skill_meta and not refresh:
            skill_meta = self._skill_loader.get_skill(name.strip(), refresh=True)
        if not skill_meta:
            return self.error_result(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Skill '{name}' not found.",
                params_input=params_input,
            )

        skill_path = Path(skill_meta.path)
        try:
            rel_path = str(skill_path.relative_to(self._project_root))
        except ValueError:
            rel_path = str(skill_path)
        try:
            raw_content = skill_path.read_text(encoding="utf-8")
        except PermissionError:
            return self.error_result(
                error_code=ErrorCode.PERMISSION_DENIED,
                message=f"Permission denied reading skill '{name}'.",
                params_input=params_input,
                path_resolved=rel_path,
            )
        except OSError as exc:
            return self.error_result(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Failed to read skill '{name}': {exc}",
                params_input=params_input,
                path_resolved=rel_path,
            )

        parsed = _parse_frontmatter(raw_content)
        if not parsed:
            return self.error_result(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Skill '{name}' has invalid frontmatter.",
                params_input=params_input,
                path_resolved=rel_path,
            )

        _frontmatter, body = parsed
        expanded = _apply_arguments(body, args)
        base_dir = skill_meta.base_dir

        content = f"Base directory for this skill: {base_dir}\n\n{expanded}".strip()
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        return self.success_result(
            data={
                "name": skill_meta.name,
                "base_dir": base_dir,
                "content": content,
            },
            text=f"Loaded skill '{skill_meta.name}'.",
            params_input=params_input,
            time_ms=elapsed_ms,
            path_resolved=rel_path,
        )


def _apply_arguments(body: str, args: str) -> str:
    trimmed_args = args.strip()
    if "$ARGUMENTS" in body:
        return body.replace("$ARGUMENTS", trimmed_args)
    if trimmed_args:
        return f"{body}\n\nARGUMENTS: {trimmed_args}"
    return body


def _parse_frontmatter(content: str) -> Optional[tuple[dict[str, str], str]]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return None

    frontmatter_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1 :])
    frontmatter: dict[str, str] = {}

    for line in frontmatter_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            return None
        key, value = stripped.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip("\"'")

    return frontmatter, body

__all__ = ["SkillTool"]
