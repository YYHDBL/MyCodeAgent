"""智能文件浏览器工具 (list_files / LS)"""

import os
import fnmatch
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import Tool, ToolParameter


class ListFilesTool(Tool):
    """安全的目录浏览工具，支持分页与过滤"""

    # 默认忽略的目录/文件（非隐藏文件类）
    DEFAULT_IGNORE = {
        "node_modules",  # Node.js 依赖目录
        "target",        # Java/Scala 构建输出目录
        "build",         # 通用构建输出目录
        "dist",          # 分发目录
        "venv",          # Python 虚拟环境
        "__pycache__",   # Python 字节码缓存
        ".git",          # Git 版本控制目录
        ".hg",           # Mercurial 版本控制目录
        ".svn",          # Subversion 版本控制目录
        ".idea",         # JetBrains IDE 配置目录
        ".vscode",       # VS Code 配置目录
        ".DS_Store",     # macOS 系统文件
        ".venv",         # Python 虚拟环境（另一种命名）
    }

    def __init__(
        self,
        name: str = "LS",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
    ):
        """
        初始化文件列表工具

        Args:
            name: 工具名称，默认为 "LS"
            project_root: 项目根目录，用于沙箱限制
            working_dir: 工作目录，用于解析相对路径
        """
        description = (
            "Lists files and directories with pagination. Supports relative or absolute paths within the project. "
            "Parameters: path (default '.'), offset (>=0), limit (1-200), include_hidden (bool), ignore (glob list). "
            "Use this to explore structure; avoid huge listings by paging."
        )
        super().__init__(name=name, description=description)
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        self._root = Path(project_root).resolve()
        # 工作目录：用于解析相对路径（默认为 cwd）
        self._working_dir = Path(working_dir).resolve() if working_dir else Path.cwd().resolve()

    def run(self, parameters: Dict[str, Any]) -> str:
        """
        执行文件列表操作

        Args:
            parameters: 包含以下键的字典：
                - path: 要列出的目录路径（默认为 '.'）
                - offset: 分页起始索引（默认为 0）
                - limit: 返回的最大条目数（默认为 100）
                - include_hidden: 是否包含隐藏文件（默认为 False）
                - ignore: 要忽略的 glob 模式列表（默认为空）

        Returns:
            格式化的文件列表字符串
        """
        path = parameters.get("path", ".")
        offset = parameters.get("offset", 0)
        limit = parameters.get("limit", 100)
        include_hidden = parameters.get("include_hidden", False)
        ignore = parameters.get("ignore") or []  # 避免可变默认值问题

        # 参数校验
        if not isinstance(offset, int) or offset < 0:
            return self._error_response("Error: offset must be a non-negative integer.")
        if not isinstance(limit, int) or limit < 1 or limit > 200:
            return self._error_response("Error: limit must be an integer between 1 and 200.")
        if not isinstance(ignore, list):
            return self._error_response("Error: ignore must be a list of glob patterns.")

        # 路径解析与沙箱校验
        try:
            input_path = Path(path)
            if input_path.is_absolute():
                # 绝对路径直接解析
                target = input_path.resolve()
            else:
                # 相对路径基于 working_dir 而非 root
                target = (self._working_dir / input_path).resolve()

            # 仅允许项目根目录内路径（沙箱安全检查）
            target.relative_to(self._root)
        except ValueError:
            return self._error_response("Error: Access denied. Path must be within the project root.")
        except OSError as e:
            return self._error_response(f"Error: Invalid path - {e}")

        if not target.exists():
            return self._error_response(f"Error: Path '{path}' does not exist.")
        if not target.is_dir():
            return self._error_response(
                f"Error: '{path}' is a file, not a directory. Use 'read_file' to view its content."
            )

        # 列出目录内容
        try:
            items = self._list_items(target, include_hidden, ignore)
        except PermissionError:
            return self._error_response(f"Error: Permission denied accessing '{path}'.")
        except OSError as e:
            return self._error_response(f"Error: Failed to list directory - {e}")

        # 计算分页范围
        total = len(items)
        start = offset if offset < total else total
        end = min(offset + limit, total)
        page_items = items[start:end]

        # 计算相对路径用于显示
        rel_path = "."
        try:
            rel_path = str(target.relative_to(self._root)) or "."
        except Exception:
            rel_path = str(target)

        # 统计各类条目数量
        dirs_count = sum(1 for i in items if i["type"] == "dir")
        files_count = sum(1 for i in items if i["type"] == "file")
        links_count = sum(1 for i in items if i["type"] == "link")

        return self._format_response(
            rel_path=rel_path,
            total=total,
            dirs_count=dirs_count,
            files_count=files_count,
            links_count=links_count,
            start=start,
            end=end,
            items=page_items,
        )

    def _list_items(self, target: Path, include_hidden: bool, ignore: List[str]):
        """
        列出目录条目，应用过滤规则

        Args:
            target: 要列出的目标目录路径
            include_hidden: 是否包含隐藏文件
            ignore: 要忽略的 glob 模式列表

        Returns:
            包含文件信息的字典列表，每个字典包含 name, type, display, is_dir 键
        """
        items = []
        with os.scandir(target) as it:
            for entry in it:
                name = entry.name
                # 条目相对于 root / target 的路径（用于 ignore glob 匹配）
                try:
                    entry_rel_root = Path(entry.path).resolve().relative_to(self._root).as_posix()
                except Exception:
                    entry_rel_root = name
                entry_rel_target = Path(name).as_posix()

                # include_hidden=False 时，跳过隐藏文件和默认忽略列表
                if not include_hidden:
                    # 跳过以点开头的隐藏文件/目录
                    if name.startswith("."):
                        continue
                    # 跳过默认忽略的目录/文件
                    if name in self.DEFAULT_IGNORE:
                        continue

                # 用户自定义 ignore 模式匹配（支持相对路径和 basename）
                if ignore and self._matches_ignore(name, entry_rel_root, entry_rel_target, ignore):
                    continue

                is_symlink = entry.is_symlink()

                # 判断是否为目录：
                # 对于 symlink，需要 resolve 后判断（同时验证沙箱）
                if is_symlink:
                    is_dir = self._symlink_points_to_dir_safe(entry)
                else:
                    is_dir = entry.is_dir()

                # 确定条目类型
                if is_symlink:
                    item_type = "link"
                elif is_dir:
                    item_type = "dir"
                else:
                    item_type = "file"

                # 构建显示名称
                display_name = name
                if is_symlink:
                    display_name = f"{name}@"  # 符号链接标记
                    if is_dir:
                        display_name += "/"
                elif is_dir:
                    display_name = f"{name}/"

                # 添加符号链接目标信息
                if is_symlink:
                    display_name = f"{display_name} -> {self._format_symlink_target(entry)}"

                items.append({
                    "name": name,
                    "type": item_type,
                    "display": display_name,
                    "is_dir": is_dir,
                })

        # 排序：目录在前，文件在后，同类型按名称字母顺序排序
        items.sort(key=lambda x: (0 if x["is_dir"] else 1, x["name"].lower()))
        return items

    def _matches_ignore(self, name: str, rel_root: str, rel_target: str, patterns: List[str]) -> bool:
        """
        检查条目是否匹配任一 ignore 模式（支持相对路径和 basename）

        Args:
            name: 文件/目录名称
            rel_root: 相对于项目根目录的路径
            rel_target: 相对于目标目录的路径
            patterns: glob 模式列表

        Returns:
            如果匹配任一模式则返回 True，否则返回 False
        """
        for pattern in patterns:
            # 如果 pattern 包含路径分隔符，则按相对路径匹配
            if "/" in pattern or "\\" in pattern:
                if fnmatch.fnmatch(rel_root, pattern) or fnmatch.fnmatch(rel_target, pattern):
                    return True
                # 也支持 **/ 开头的递归模式
                if pattern.startswith("**/"):
                    if fnmatch.fnmatch(name, pattern[3:]):
                        return True
                    if fnmatch.fnmatch(rel_root, pattern[3:]) or fnmatch.fnmatch(rel_target, pattern[3:]):
                        return True
            else:
                # 仅按 basename 匹配
                if fnmatch.fnmatch(name, pattern):
                    return True
        return False

    def _symlink_points_to_dir_safe(self, entry) -> bool:
        """
        安全检查 symlink 是否指向目录（必须在沙箱内）

        Args:
            entry: 目录条目对象

        Returns:
            如果 symlink 指向目录且在沙箱内则返回 True，否则返回 False
        """
        try:
            resolved = Path(entry.path).resolve()
            # 验证在 root 内
            resolved.relative_to(self._root)
            return resolved.is_dir()
        except (ValueError, OSError):
            # 指向沙箱外或无法解析，视为非目录
            return False

    def _format_symlink_target(self, entry) -> str:
        """
        格式化 symlink 目标显示

        Args:
            entry: 目录条目对象

        Returns:
            格式化后的 symlink 目标路径字符串
        """
        try:
            real_path = Path(entry.path).resolve()
            real_path.relative_to(self._root)
            rel = os.path.relpath(real_path, start=Path(entry.path).parent)
            return rel
        except ValueError:
            return "<Outside Sandbox>"
        except OSError:
            return "<Broken Link>"
        except Exception:
            return "<Unknown>"

    def get_parameters(self):
        """
        获取工具参数定义

        Returns:
            ToolParameter 对象列表，描述工具支持的参数
        """
        return [
            ToolParameter(
                name="path",
                type="string",
                description="Directory path to list (relative to project root or absolute within it)",
                required=False,
                default=".",
            ),
            ToolParameter(
                name="offset",
                type="integer",
                description="Pagination start index (>=0)",
                required=False,
                default=0,
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="Max items to return (1-200)",
                required=False,
                default=100,
            ),
            ToolParameter(
                name="include_hidden",
                type="boolean",
                description="Whether to include hidden files (starting with '.')",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="ignore",
                type="array",
                description="Optional list of glob patterns to ignore (supports basename like '*.log' or relative path like 'dist/**')",
                required=False,
                default=None,  # 避免可变默认值
            ),
        ]

    def _format_response(
        self,
        rel_path: str,
        total: int,
        dirs_count: int,
        files_count: int,
        links_count: int,
        start: int,
        end: int,
        items: list[dict],
    ) -> str:
        lines = []
        lines.append(f"Directory: {rel_path}")
        lines.append(
            f"[Summary: {total} items (dirs={dirs_count}, files={files_count}, links={links_count}). "
            f"Showing {start}-{end}.]"
        )
        lines.append("")
        for item in items:
            lines.append(item["display"])

        remaining = total - end
        warnings = []
        if remaining > 0:
            lines.append("")
            lines.append("[Navigation]")
            lines.append(f"There are {remaining} more items.")
            lines.append(f'{self.name}[{{"path": "{rel_path}", "offset": {end}}}]')
            warnings.append("Listing truncated. Use offset/limit to view more items.")

        payload = {
            "items": [i["display"] for i in items],
            "context": {
                "root_resolved": rel_path,
            },
            "stats": {
                "total": total,
                "dirs": dirs_count,
                "files": files_count,
                "links": links_count,
                "start": start,
                "end": end,
            },
            "flags": {
                "truncated": end < total,
            },
            "warnings": warnings,
            "text": "\n".join(lines),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _error_response(self, message: str) -> str:
        payload = {
            "error": message,
            "items": [],
            "context": {},
            "stats": {},
            "flags": {},
            "text": message,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
