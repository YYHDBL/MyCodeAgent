"""代码内容搜索工具 (search_code / GrepTool)"""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, TypedDict

from ..base import Tool, ToolParameter


class MatchItem(TypedDict):
    """单条匹配结果结构"""
    file: str  # 相对于项目根目录的文件路径
    line: int  # 行号（从1开始）
    text: str  # 完整的行文本


class GrepTool(Tool):
    """搜索文件内容（优先使用 ripgrep，缺失则回退到 Python 实现）"""

    # 总是忽略的目录/文件列表
    ALWAYS_IGNORE = {
        ".git",          # Git 版本控制目录
        "node_modules",  # Node.js 依赖目录
        "dist",          # 分发目录
        "build",         # 构建输出目录
        "__pycache__",   # Python 字节码缓存
        ".venv",         # Python 虚拟环境
        "venv",          # Python 虚拟环境
        ".idea",         # JetBrains IDE 配置目录
        ".vscode",       # VS Code 配置目录
        ".DS_Store",     # macOS 系统文件
        ".hg",           # Mercurial 版本控制目录
        ".svn",          # Subversion 版本控制目录
        ".mypy_cache",   # mypy 类型检查缓存
        ".pytest_cache", # pytest 测试缓存
        ".ruff_cache",   # ruff linter 缓存
        ".tox",          # tox 测试环境目录
        ".cache",        # 通用缓存目录
        "site-packages", # Python 包目录
    }

    # 最大返回结果数
    MAX_RESULTS = 100

    # 搜索超时时间（秒）
    TIMEOUT_SEC = 2.0

    def __init__(self, name: str = "search_code", project_root: Optional[Path] = None):
        description = (
            "Search file contents using regex. Returns matches sorted by file modification time (newest first)."
        )
        super().__init__(name=name, description=description)
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        self._root = Path(project_root).resolve()

    def run(self, parameters: Dict[str, Any]) -> str:
        """
        执行代码搜索操作

        Args:
            parameters: 包含以下键的字典：
                - pattern: 正则表达式模式（必需）
                - path: 搜索起始目录（默认为 '.'）
                - include: 文件过滤的 glob 模式（可选）
                - case_sensitive: 是否区分大小写（默认为 False）

        Returns:
            格式化的搜索结果字符串（JSON 格式）
        """
        pattern = parameters.get("pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            return self._error_response("Error: Missing required parameter 'pattern'.")

        path = parameters.get("path", ".")
        include = parameters.get("include")
        case_sensitive = parameters.get("case_sensitive", False)

        if include is not None and not isinstance(include, str):
            return self._error_response("Error: include must be a string if provided.")
        if not isinstance(case_sensitive, bool):
            return self._error_response("Error: case_sensitive must be a boolean.")

        try:
            abs_root = self._resolve_search_root(path)
        except ValueError:
            return self._error_response("Error: Access denied. Path must be within project root.")
        except OSError as e:
            return self._error_response(f"Error: Search failed ({e}).")

        if not abs_root.exists():
            return self._error_response(f"Error: Search root '{path}' does not exist.")
        if not abs_root.is_dir():
            return self._error_response(f"Error: Search root '{path}' is not a directory.")

        start_time = time.monotonic()
        matches: List[MatchItem] = []
        aborted_reason: Optional[str] = None
        used_rg = False

        # 优先使用 ripgrep 进行搜索
        rg_available = shutil.which("rg") is not None
        if rg_available:
            try:
                matches = self._run_rg(
                    abs_root=abs_root,
                    pattern=pattern,
                    include=include,
                    case_sensitive=case_sensitive,
                )
                used_rg = True
            except subprocess.TimeoutExpired as e:
                used_rg = True
                aborted_reason = "timeout"
                output = getattr(e, "output", "") or ""
                matches = self._parse_rg_json_output(output)
            except ValueError as e:
                return self._error_response(f"Error: {e}")
            except Exception:
                aborted_reason = "rg_failed"
        else:
            aborted_reason = "rg_not_found"

        # ripgrep 不可用或失败时，使用 Python 实现
        if not used_rg:
            try:
                matches, aborted_reason = self._run_python_search(
                    abs_root=abs_root,
                    pattern=pattern,
                    include=include,
                    case_sensitive=case_sensitive,
                    start_time=start_time,
                    aborted_reason=aborted_reason,
                )
            except re.error as e:
                return self._error_response(f"Error: Invalid regex pattern ({e}).")
            except Exception as e:
                return self._error_response(f"Error: Search failed ({e}).")

        # 按文件修改时间降序排序
        self._sort_matches_by_mtime(matches)

        # 截断结果
        truncated = False
        if len(matches) > self.MAX_RESULTS:
            matches = matches[: self.MAX_RESULTS]
            truncated = True

        if aborted_reason == "timeout":
            truncated = True

        time_ms = int((time.monotonic() - start_time) * 1000)
        rel_root = str(abs_root.relative_to(self._root)) or "."

        text = self._format_text(
            matches=matches,
            pattern=pattern,
            rel_root=rel_root,
            truncated=truncated,
            aborted_reason=aborted_reason,
            time_ms=time_ms,
        )

        payload = {
            "matches": matches,
            "context": {
                "pattern": pattern,
                "root_resolved": rel_root,
                "sorted_by": "mtime_desc",
            },
            "stats": {
                "matched_files": len({m["file"] for m in matches}),
                "matched_lines": len(matches),
                "time_ms": time_ms,
            },
            "flags": {
                "truncated": bool(truncated),
                "aborted_reason": aborted_reason,
            },
            "text": text,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _resolve_search_root(self, path: str) -> Path:
        """
        解析搜索根目录路径

        Args:
            path: 用户提供的路径（相对或绝对）

        Returns:
            解析后的绝对路径

        Raises:
            ValueError: 路径不在项目根目录内
            OSError: 路径解析失败
        """
        input_path = Path(path)
        if input_path.is_absolute():
            root = input_path.resolve()
        else:
            root = (self._root / input_path).resolve()
        root.relative_to(self._root)
        return root

    def _run_rg(
        self,
        abs_root: Path,
        pattern: str,
        include: Optional[str],
        case_sensitive: bool,
    ) -> List[MatchItem]:
        """
        使用 ripgrep 执行搜索

        Args:
            abs_root: 搜索根目录的绝对路径
            pattern: 正则表达式模式
            include: 文件过滤的 glob 模式
            case_sensitive: 是否区分大小写

        Returns:
            匹配结果列表

        Raises:
            ValueError: ripgrep 命令执行失败
            RuntimeError: ripgrep 返回错误
            subprocess.TimeoutExpired: 搜索超时
        """
        rel_root = str(abs_root.relative_to(self._root)) or "."
        search_path = rel_root

        # 构建 ripgrep 命令
        cmd = [
            "rg",
            "--json",          # JSON 格式输出
            "--no-heading",    # 不显示文件名标题
            "--line-number",   # 显示行号
            "--with-filename", # 显示文件名
            "--color",
            "never",
        ]
        if not case_sensitive:
            cmd.append("-i")
        include_normalized = include.replace("\\", "/").strip() if include else None
        if include_normalized:
            cmd.extend(["--glob", include_normalized])

        # 基于 ALWAYS_IGNORE 做目录剪枝（rg 使用 glob 排除）
        root_parts = set(abs_root.relative_to(self._root).parts)
        for entry in sorted(self.ALWAYS_IGNORE):
            if entry in root_parts:
                continue
            if entry.startswith("."):
                cmd.extend(["--glob", f"!**/{entry}/**"])
                cmd.extend(["--glob", f"!**/{entry}"])
            else:
                cmd.extend(["--glob", f"!**/{entry}/**"])

        cmd.extend(["--", pattern, search_path])

        result = subprocess.run(
            cmd,
            cwd=str(self._root),
            capture_output=True,
            text=True,
            timeout=self.TIMEOUT_SEC,
        )

        if result.returncode == 2:
            err = result.stderr.strip() or "ripgrep failed"
            raise ValueError(err)
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr.strip() or "ripgrep error")

        return self._parse_rg_json_output(result.stdout)

    def _parse_rg_json_output(self, output: str) -> List[MatchItem]:
        """
        解析 ripgrep 的 JSON 输出

        Args:
            output: ripgrep 的 stdout 输出（JSONL 格式）

        Returns:
            解析后的匹配结果列表
        """
        matches: List[MatchItem] = []
        if not output:
            return matches
        for line in output.splitlines():
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "match":
                continue
            data = obj.get("data") or {}
            path_text = (data.get("path") or {}).get("text")
            line_num = data.get("line_number")
            line_text = (data.get("lines") or {}).get("text")
            if not path_text or not line_num or line_text is None:
                continue
            file_path = Path(path_text)
            if file_path.is_absolute():
                try:
                    rel_file = file_path.resolve().relative_to(self._root).as_posix()
                except Exception:
                    rel_file = file_path.as_posix()
            else:
                rel_file = file_path.as_posix()
            matches.append({
                "file": rel_file,
                "line": int(line_num),
                "text": line_text.rstrip("\n"),
            })
        return matches

    def _run_python_search(
        self,
        abs_root: Path,
        pattern: str,
        include: Optional[str],
        case_sensitive: bool,
        start_time: float,
        aborted_reason: Optional[str],
    ) -> tuple[List[MatchItem], Optional[str]]:
        """
        使用 Python 实现执行搜索（ripgrep 不可用时的回退方案）

        Args:
            abs_root: 搜索根目录的绝对路径
            pattern: 正则表达式模式
            include: 文件过滤的 glob 模式
            case_sensitive: 是否区分大小写
            start_time: 搜索开始时间
            aborted_reason: 初始中止原因

        Returns:
            (匹配结果列表, 中止原因)
        """
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags=flags)
        matches: List[MatchItem] = []
        include_normalized = include.replace("\\", "/").strip() if include else None

        for current_root, dirs, files in os.walk(abs_root, topdown=True):
            dirs.sort()
            files.sort()

            # 剪枝：跳过忽略的目录
            dirs[:] = [d for d in dirs if d not in self.ALWAYS_IGNORE]

            for filename in files:
                if filename in self.ALWAYS_IGNORE:
                    continue

                # 检查超时
                # if self._is_timed_out(start_time):
                if False:
                    return matches, "timeout"

                rel_match_path = Path(current_root).resolve().relative_to(abs_root) / filename
                rel_match_posix = rel_match_path.as_posix()

                # 应用 include 过滤
                if include_normalized and not self._match_include(rel_match_posix, include_normalized):
                    continue

                rel_display_path = Path(current_root).resolve().relative_to(self._root) / filename
                rel_display_posix = rel_display_path.as_posix()

                file_path = Path(current_root) / filename
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
                        for line_no, line in enumerate(handle, start=1):
                            if regex.search(line):
                                matches.append({
                                    "file": rel_display_posix,
                                    "line": line_no,
                                    "text": line.rstrip("\n"),
                                })
                except (OSError, UnicodeError):
                    continue

                # if self._is_timed_out(start_time):
                if False:
                    return matches, "timeout"

        return matches, aborted_reason

    def _match_include(self, rel_posix: str, include_pattern: str) -> bool:
        """
        检查文件路径是否匹配 include glob 模式

        Args:
            rel_posix: 文件的 POSIX 风格相对路径
            include_pattern: glob 模式

        Returns:
            如果匹配则返回 True，否则返回 False
        """
        cleaned = self._strip_relative_prefix(include_pattern)
        path_obj = PurePosixPath(rel_posix)
        if path_obj.match(cleaned):
            return True
        # 兼容 **/ 可匹配 0 层目录
        if cleaned.startswith("**/"):
            return path_obj.match(cleaned[3:])
        return False

    def _strip_relative_prefix(self, pattern: str) -> str:
        """
        移除 glob 模式开头的 ./ 或 / 前缀

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

    def _is_timed_out(self, start_time: float) -> bool:
        """
        检查搜索是否超时

        Args:
            start_time: 搜索开始时间（time.monotonic() 返回值）

        Returns:
            如果超过超时时间则返回 True，否则返回 False
        """
        return (time.monotonic() - start_time) > self.TIMEOUT_SEC

    def _sort_matches_by_mtime(self, matches: List[MatchItem]) -> None:
        """
        按文件修改时间降序排序匹配结果

        Args:
            matches: 匹配结果列表（原地修改）
        """
        mtime_cache: Dict[str, float] = {}

        def get_mtime(rel_path: str) -> float:
            if rel_path not in mtime_cache:
                full_path = self._root / rel_path
                try:
                    mtime_cache[rel_path] = os.stat(full_path).st_mtime
                except OSError:
                    mtime_cache[rel_path] = 0
            return mtime_cache[rel_path]

        matches.sort(key=lambda m: (-get_mtime(m["file"]), m["file"], m["line"]))

    def _format_text(
        self,
        matches: List[MatchItem],
        pattern: str,
        rel_root: str,
        truncated: bool,
        aborted_reason: Optional[str],
        time_ms: int,
    ) -> str:
        """
        格式化搜索结果为可读文本

        Args:
            matches: 匹配结果列表
            pattern: 搜索模式
            rel_root: 相对根目录
            truncated: 是否截断结果
            aborted_reason: 中止原因
            time_ms: 搜索耗时（毫秒）

        Returns:
            格式化的文本字符串
        """
        lines: List[str] = []
        lines.append(f"Search Pattern: {pattern} (in '{rel_root}')")
        lines.append(
            f"[Stats: Found {len(matches)} matches in {len({m['file'] for m in matches})} files. "
            f"Sorted by mtime desc. Took {time_ms}ms.]"
        )
        lines.append("")

        if matches:
            for item in matches:
                lines.append(f"{item['file']}:{item['line']}: {item['text']}")
        else:
            lines.append(f"No matches for '{pattern}'.")

        warning = None
        if aborted_reason == "timeout":
            warning = (
                "[Warning: Search timed out (>2s). Results are incomplete. "
                "Try narrowing the path or pattern.]"
            )
        elif truncated:
            warning = f"[Warning: Showing first {self.MAX_RESULTS} matches only. Narrow pattern or path.]"
        elif aborted_reason == "rg_not_found":
            warning = "[Info: ripgrep not available; used Python fallback search.]"
        elif aborted_reason == "rg_failed":
            warning = "[Info: ripgrep failed; used Python fallback search.]"

        if warning:
            lines.append("")
            lines.append(warning)

        return "\n".join(lines)

    def _error_response(self, message: str) -> str:
        """
        生成错误响应

        Args:
            message: 错误消息

        Returns:
            JSON 格式的错误响应字符串
        """
        payload = {
            "error": message,
            "matches": [],
            "context": {},
            "stats": {},
            "flags": {},
            "text": message,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def get_parameters(self) -> List[ToolParameter]:
        """
        获取工具参数定义

        Returns:
            ToolParameter 对象列表，描述工具支持的参数
        """
        return [
            ToolParameter(
                name="pattern",
                type="string",
                description="Regex pattern to search (e.g. 'class\\s+User'). Required.",
                required=True,
            ),
            ToolParameter(
                name="path",
                type="string",
                description="Directory to search in (relative to project root). Defaults to '.'",
                required=False,
                default=".",
            ),
            ToolParameter(
                name="include",
                type="string",
                description="Glob pattern to filter files (e.g. '*.ts'). Highly recommended.",
                required=False,
                default=None,
            ),
            ToolParameter(
                name="case_sensitive",
                type="boolean",
                description="If true, search is case-sensitive. Default is false.",
                required=False,
                default=False,
            ),
        ]
