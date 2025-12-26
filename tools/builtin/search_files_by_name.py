"""全局文件搜索工具 (search_files_by_name / Glob)"""

import os
import time
import json
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional

from ..base import Tool, ToolParameter


class SearchFilesByNameTool(Tool):
    """使用 glob 模式搜索文件（安全、可控、可复现）"""

    # 总是忽略的目录/文件列表
    ALWAYS_IGNORE = {
        ".git",          # Git 版本控制目录
        ".hg",           # Mercurial 版本控制目录
        ".svn",          # Subversion 版本控制目录
        "__pycache__",   # Python 字节码缓存
        "node_modules",  # Node.js 依赖目录
        "target",        # Java/Scala 构建输出目录
        "build",         # 通用构建输出目录
        "dist",          # 分发目录
        ".idea",         # JetBrains IDE 配置目录
        ".vscode",       # VS Code 配置目录
        ".DS_Store",     # macOS 系统文件
        "venv",          # Python 虚拟环境
        ".venv",         # Python 虚拟环境（另一种命名）
        ".mypy_cache",   # mypy 类型检查缓存
        ".pytest_cache", # pytest 测试缓存
        ".ruff_cache",   # ruff linter 缓存
        ".tox",          # tox 测试环境目录
        ".cache",        # 通用缓存目录
        "site-packages", # Python 包目录
    }

    # 最大访问条目数（防止搜索过大）
    MAX_VISITED_ENTRIES = 20_000

    # 最大搜索时间（毫秒）
    MAX_DURATION_MS = 2_000

    def __init__(self, name: str = "Glob", project_root: Optional[Path] = None):
        """
        初始化文件搜索工具

        Args:
            name: 工具名称，默认为 "Glob"
            project_root: 项目根目录，用于沙箱限制
        """
        description = (
            "Find files using glob patterns (e.g., 'src/**/*.ts'). "
            "Matches against relative paths from the search root (path). Returns files only."
        )
        super().__init__(name=name, description=description)
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        self._root = Path(project_root).resolve()

    def run(self, parameters: Dict[str, Any]) -> str:
        """
        执行文件搜索操作

        Args:
            parameters: 包含以下键的字典：
                - pattern: glob 模式（必需）
                - path: 搜索起始目录（默认为 '.'）
                - limit: 最大返回结果数（默认为 50）
                - include_hidden: 是否包含隐藏文件（默认为 False）
                - include_ignored: 是否遍历忽略的目录（默认为 False）

        Returns:
            格式化的搜索结果字符串
        """
        pattern = parameters.get("pattern")
        if not pattern:
            return self._error_response("Error: Missing required parameter 'pattern'.")

        path = parameters.get("path", ".")
        limit = parameters.get("limit", 50)
        include_hidden = parameters.get("include_hidden", False)
        include_ignored = parameters.get("include_ignored", False)

        if not isinstance(limit, int) or limit < 1 or limit > 200:
            return self._error_response("Error: limit must be an integer between 1 and 200.")

        # 路径解析与沙箱校验
        try:
            input_path = Path(path)
            if input_path.is_absolute():
                # 绝对路径直接解析
                root = input_path.resolve()
            else:
                # 相对路径基于项目根目录
                root = (self._root / input_path).resolve()

            # 沙箱安全检查：确保路径在项目根目录内
            root.relative_to(self._root)
        except ValueError:
            return self._error_response("Error: Access denied. Path must be within project root.")
        except OSError as e:
            return self._error_response(f"Error: Search failed ({e}).")

        if not root.exists():
            return self._error_response(f"Error: Search root '{path}' does not exist.")
        if not root.is_dir():
            return self._error_response(f"Error: Search root '{path}' is not a directory.")

        # 初始化搜索统计信息
        start_time = time.monotonic()
        visited_count = 0
        matches = []
        truncated = False
        aborted_reason = None

        # 统一使用 POSIX 风格 pattern（纯字符串规范化）
        pattern_normalized = pattern.replace("\\", "/").strip()

        try:
            # 使用 os.walk 遍历目录树
            for current_root, dirs, files in os.walk(root, topdown=True):
                # 确定性排序（确保结果可复现）
                dirs.sort()
                files.sort()

                # 剪枝（原地修改 dirs 列表，避免遍历不需要的目录）
                if not include_ignored:
                    dirs[:] = [d for d in dirs if d not in self.ALWAYS_IGNORE]
                if not include_hidden:
                    dirs[:] = [d for d in dirs if not d.startswith(".")]

                # 计入目录访问
                visited_count += 1
                if self._should_abort(start_time, visited_count):
                    aborted_reason = self._abort_reason(start_time, visited_count)
                    break

                # 遍历当前目录的文件
                for filename in files:
                    visited_count += 1
                    if self._should_abort(start_time, visited_count):
                        aborted_reason = self._abort_reason(start_time, visited_count)
                        break

                    # 跳过隐藏文件
                    if not include_hidden and filename.startswith("."):
                        continue

                    # 匹配基准：相对于搜索起点 root
                    rel_match_path = Path(current_root).resolve().relative_to(root) / filename
                    rel_match_posix = rel_match_path.as_posix()


                    # 展示路径：相对于项目根目录
                    rel_display_path = Path(current_root).resolve().relative_to(self._root) / filename
                    rel_display_posix = rel_display_path.as_posix()

                    # 检查文件是否匹配 glob 模式
                    if self._match_pattern(rel_match_posix, pattern_normalized):
                        matches.append(rel_display_posix)
                        if len(matches) >= limit:
                            truncated = True
                            break

                # 如果已达到限制或需要中止，停止搜索
                if aborted_reason or truncated:
                    break
        except Exception as e:
            return self._error_response(f"Error: Search failed ({e}).")

        # 计算搜索耗时
        time_ms = int((time.monotonic() - start_time) * 1000)

        rel_root = str(root.relative_to(self._root)) or "."

        if not matches:
            text = f"No files found matching '{pattern_normalized}'."
            return self._format_response(
                matches=[],
                rel_root=rel_root,
                pattern_normalized=pattern_normalized,
                visited_count=visited_count,
                time_ms=time_ms,
                truncated=False,
                aborted_reason=aborted_reason,
                text_override=text,
            )

        return self._format_response(
            matches=matches,
            rel_root=rel_root,
            pattern_normalized=pattern_normalized,
            visited_count=visited_count,
            time_ms=time_ms,
            truncated=truncated,
            aborted_reason=aborted_reason,
            limit=limit,
        )

    def _should_abort(self, start_time: float, visited_count: int) -> bool:
        """
        检查是否应该中止搜索

        Args:
            start_time: 搜索开始时间（time.monotonic() 返回值）
            visited_count: 已访问的条目数量

        Returns:
            如果超过最大访问数或最大时间则返回 True，否则返回 False
        """
        if visited_count > self.MAX_VISITED_ENTRIES:
            return True
        elapsed_ms = (time.monotonic() - start_time) * 1000
        if elapsed_ms > self.MAX_DURATION_MS:
            return True
        return False

    def _abort_reason(self, start_time: float, visited_count: int) -> Optional[str]:
        """
        获取中止搜索的原因

        Args:
            start_time: 搜索开始时间
            visited_count: 已访问的条目数量

        Returns:
            返回 "count_limit" 或 "time_limit"，如果不需要中止则返回 None
        """
        if visited_count > self.MAX_VISITED_ENTRIES:
            return "count_limit"
        elapsed_ms = (time.monotonic() - start_time) * 1000
        if elapsed_ms > self.MAX_DURATION_MS:
            return "time_limit"
        return None

    def _match_pattern(self, rel_posix: str, pattern_normalized: str) -> bool:
        """
        使用相对路径进行匹配，补充 **/ 零层目录兼容。

        Args:
            rel_posix: 相对于搜索起点的 POSIX 风格路径
            pattern_normalized: 规范化后的 glob 模式

        Returns:
            如果路径匹配模式则返回 True，否则返回 False
        """
        cleaned_pattern = self._strip_relative_prefix(pattern_normalized)
        path_obj = PurePosixPath(rel_posix)

        # 1) 正常匹配
        if path_obj.match(cleaned_pattern):
            return True

        # 2) 兼容 **/ 可匹配 0 层目录
        if cleaned_pattern.startswith("**/"):
            if path_obj.match(cleaned_pattern[3:]):
                return True

        return False

    def _strip_relative_prefix(self, pattern: str) -> str:
        """
        仅移除开头的 ./ 或 /，避免 lstrip 的字符集误用

        Args:
            pattern: 原始 glob 模式

        Returns:
            移除前缀后的模式字符串
        """
        cleaned = pattern
        while cleaned.startswith("./"):
            cleaned = cleaned[2:]
        while cleaned.startswith("/"):
            cleaned = cleaned[1:]
        return cleaned

    # NOTE: We keep matching minimal and only add **/ zero-depth fallback.

    def _format_response(
        self,
        matches: list[str],
        rel_root: str,
        pattern_normalized: str,
        visited_count: int,
        time_ms: int,
        truncated: bool,
        aborted_reason: Optional[str],
        limit: Optional[int] = None,
        text_override: Optional[str] = None,
    ) -> str:
        """同时返回结构化数据与可读文本"""
        lines = []
        lines.append(f"Search Pattern: {pattern_normalized} (in '{rel_root}')")
        lines.append(
            f"[Stats: Found {len(matches)} matches. Scanned {visited_count} items in {time_ms}ms.]"
        )
        if text_override:
            lines.append("")
            lines.append(text_override)
        else:
            lines.append("")
            lines.extend(matches)

        footer_warning = None
        if truncated:
            footer_warning = (
                f"[Warning: Showing first {limit} matches only. Narrow pattern or increase limit.]"
            )
        elif aborted_reason == "count_limit":
            footer_warning = (
                "[Warning: Search stopped early (scanned too many items). "
                "Results are incomplete. Use a more specific 'path'.]"
            )
        elif aborted_reason == "time_limit":
            footer_warning = (
                "[Warning: Search timed out (>2s). Results are incomplete. "
                "Try excluding ignored directories.]"
            )

        if footer_warning:
            lines.append("")
            lines.append(footer_warning)

        payload = {
            "matches": matches,
            "context": {
                "root_resolved": rel_root,
                "pattern_normalized": pattern_normalized,
            },
            "stats": {
                "matched": len(matches),
                "visited": visited_count,
                "time_ms": time_ms,
            },
            "flags": {
                "truncated": bool(truncated),
                "aborted_reason": aborted_reason,
            },
            "text": "\n".join(lines),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _error_response(self, message: str) -> str:
        payload = {
            "error": message,
            "matches": [],
            "context": {},
            "stats": {},
            "flags": {},
            "text": message,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def get_parameters(self):
        """
        获取工具参数定义

        Returns:
            ToolParameter 对象列表，描述工具支持的参数
        """
        return [
            ToolParameter(
                name="pattern",
                type="string",
                description="Glob pattern relative to the search root (path), e.g. '**/*.js'",
                required=True,
            ),
            ToolParameter(
                name="path",
                type="string",
                description="Directory to start search from (relative to project root)",
                required=False,
                default=".",
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="Max matches to return (1-200)",
                required=False,
                default=50,
            ),
            ToolParameter(
                name="include_hidden",
                type="boolean",
                description="If true, include hidden files and directories",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="include_ignored",
                type="boolean",
                description="If true, traverse ignored directories (node_modules, dist, etc.)",
                required=False,
                default=False,
            ),
        ]
