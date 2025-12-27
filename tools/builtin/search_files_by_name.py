"""全局文件搜索工具 (search_files_by_name / Glob)

遵循《通用工具响应协议》，返回标准化结构。
"""

import fnmatch
import os
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from prompts.tools_prompts.glob_prompt import glob_prompt
from ..base import Tool, ToolParameter, ToolStatus, ErrorCode


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
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        
        # 调用基类初始化（注入 project_root）
        super().__init__(
            name=name,
            description=glob_prompt,
            project_root=project_root,
        )
        
        # 保持向后兼容的内部变量
        self._root = self._project_root

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
            JSON 格式的响应字符串（遵循《通用工具响应协议》）
        """
        start_time = time.monotonic()
        
        # 保存原始参数用于 context.params_input
        params_input = dict(parameters)
        
        pattern = parameters.get("pattern")
        if not pattern:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Missing required parameter 'pattern'.",
                params_input=params_input,
            )

        path = parameters.get("path", ".")
        limit = parameters.get("limit", 50)
        include_hidden = parameters.get("include_hidden", False)
        include_ignored = parameters.get("include_ignored", False)

        if not isinstance(limit, int) or limit < 1 or limit > 200:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="limit must be an integer between 1 and 200.",
                params_input=params_input,
            )

        # 路径解析与沙箱校验
        try:
            input_path = Path(path)
            if input_path.is_absolute():
                root = input_path.resolve()
            else:
                root = (self._root / input_path).resolve()

            # 沙箱安全检查
            root.relative_to(self._root)
        except ValueError:
            return self.create_error_response(
                error_code=ErrorCode.ACCESS_DENIED,
                message="Access denied. Path must be within project root.",
                params_input=params_input,
            )
        except OSError as e:
            return self.create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Search failed ({e}).",
                params_input=params_input,
            )

        # 计算解析后的相对路径
        rel_root = str(root.relative_to(self._root)) or "."

        if not root.exists():
            return self.create_error_response(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Search root '{path}' does not exist.",
                params_input=params_input,
                path_resolved=rel_root,
            )
        if not root.is_dir():
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message=f"Search root '{path}' is not a directory.",
                params_input=params_input,
                path_resolved=rel_root,
            )

        # 初始化搜索统计信息
        visited_count = 0
        matches: List[str] = []
        truncated = False
        aborted_reason: Optional[str] = None

        # 统一使用 POSIX 风格 pattern
        pattern_normalized = pattern.replace("\\", "/").strip()

        try:
            # 使用 os.walk 遍历目录树
            for current_root, dirs, files in os.walk(root, topdown=True):
                # 确定性排序
                dirs.sort()
                files.sort()

                # 剪枝
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
            time_ms = int((time.monotonic() - start_time) * 1000)
            return self.create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Search failed ({e}).",
                params_input=params_input,
                path_resolved=rel_root,
                time_ms=time_ms,
            )

        # 计算搜索耗时
        time_ms = int((time.monotonic() - start_time) * 1000)

        # 构建响应
        return self._format_response(
            matches=matches,
            rel_root=rel_root,
            pattern_normalized=pattern_normalized,
            visited_count=visited_count,
            time_ms=time_ms,
            truncated=truncated,
            aborted_reason=aborted_reason,
            limit=limit,
            params_input=params_input,
        )

    def _should_abort(self, start_time: float, visited_count: int) -> bool:
        """检查是否应该中止搜索"""
        if visited_count > self.MAX_VISITED_ENTRIES:
            return True
        elapsed_ms = (time.monotonic() - start_time) * 1000
        if elapsed_ms > self.MAX_DURATION_MS:
            return True
        return False

    def _abort_reason(self, start_time: float, visited_count: int) -> Optional[str]:
        """获取中止搜索的原因"""
        if visited_count > self.MAX_VISITED_ENTRIES:
            return "count_limit"
        elapsed_ms = (time.monotonic() - start_time) * 1000
        if elapsed_ms > self.MAX_DURATION_MS:
            return "time_limit"
        return None

    def _match_pattern(self, rel_posix: str, pattern_normalized: str) -> bool:
        """
        使用 fnmatch 进行锚定匹配，避免 PurePosixPath.match 的后缀匹配问题。
        
        问题：PurePosixPath.match('agents/*.py') 会匹配 'site-packages/agents/foo.py'，
        因为 match() 是后缀匹配。改用 fnmatch 确保 'agents/*.py' 只匹配顶层 agents 目录。
        
        注意：fnmatch 中 * 和 ? 默认匹配 /，所以需要将 * 转换为 [!/]*、? 转换为 [!/] 来避免跨目录匹配。
        只有 ** 才应该匹配跨目录。
        """
        cleaned_pattern = self._strip_relative_prefix(pattern_normalized)
        
        # 将 pattern 转换为不跨目录匹配的形式
        # * 不应匹配 /，只有 ** 才匹配任意层级
        converted_pattern = self._convert_glob_to_fnmatch(cleaned_pattern)
        
        # 使用 fnmatch 进行完整路径匹配（非后缀匹配）
        if fnmatch.fnmatch(rel_posix, converted_pattern):
            return True
        
        # 兼容 **/ 可匹配 0 层目录
        if cleaned_pattern.startswith("**/"):
            zero_layer_pattern = cleaned_pattern[3:]  # 移除 **/
            converted_zero = self._convert_glob_to_fnmatch(zero_layer_pattern)
            if fnmatch.fnmatch(rel_posix, converted_zero):
                return True
        
        return False

    def _convert_glob_to_fnmatch(self, pattern: str) -> str:
        """
        将 glob 模式转换为 fnmatch 兼容模式，确保单个 * 不匹配 /。
        
        转换规则：
        - ** → * （fnmatch 的 * 可匹配任意字符包括 /）
        - 单独的 * → [^/]* （不匹配 /）
        
        例如：
        - **/*.py → */*.py （匹配 src/main.py, a/b/c.py）
        - *.py → [^/]*.py （只匹配 main.py，不匹配 src/main.py）
        - agents/*.py → agents/[!/]*.py
        - a?b.txt → a[!/]b.txt
        """
        result = []
        i = 0
        n = len(pattern)
        
        while i < n:
            if pattern[i] == '*':
                # 检查是否是 **
                if i + 1 < n and pattern[i + 1] == '*':
                    # ** 转换为 *（fnmatch 的 * 匹配任意字符包括 /）
                    result.append('*')
                    i += 2  # 跳过两个 *
                    continue
                else:
                    # 单个 * 转换为 [!/]*
                    result.append('[!/]*')
            elif pattern[i] == '?':
                # 单个 ? 转换为 [!/]
                result.append('[!/]')
            else:
                result.append(pattern[i])
            i += 1
        
        return ''.join(result)

    def _strip_relative_prefix(self, pattern: str) -> str:
        """移除开头的 ./ 或 / 前缀"""
        cleaned = pattern
        while cleaned.startswith("./"):
            cleaned = cleaned[2:]
        while cleaned.startswith("/"):
            cleaned = cleaned[1:]
        return cleaned

    def get_parameters(self) -> List[ToolParameter]:
        """获取工具参数定义"""
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

    def _format_response(
        self,
        matches: List[str],
        rel_root: str,
        pattern_normalized: str,
        visited_count: int,
        time_ms: int,
        truncated: bool,
        aborted_reason: Optional[str],
        limit: int,
        params_input: Dict[str, Any],
    ) -> str:
        """
        构建标准化响应（遵循《通用工具响应协议》）
        
        顶层字段仅包含：status, data, text, stats, context
        
        状态判定逻辑：
        - 有结果 + 截断/熔断 → status="partial"
        - 无结果 + 熔断 → status="error" + error.code="TIMEOUT" 或 "INTERNAL_ERROR"
        - 其他成功 → status="success"
        """
        has_results = len(matches) > 0
        is_partial = truncated or (aborted_reason is not None and has_results)
        is_error_timeout = aborted_reason is not None and not has_results
        
        # 构建 data.paths（字符串数组）
        data = {
            "paths": matches,
            "truncated": truncated,
        }
        
        # 如果有熔断原因，添加到 data 中
        if aborted_reason:
            data["aborted_reason"] = aborted_reason
        
        # 构建 text（人类可读摘要）
        lines = []
        if has_results:
            lines.append(f"Found {len(matches)} files matching '{pattern_normalized}' in '{rel_root}'")
        else:
            lines.append(f"No files found matching '{pattern_normalized}' in '{rel_root}'")
        
        lines.append(f"(Scanned {visited_count} items in {time_ms}ms)")
        
        # 添加状态说明
        if truncated:
            lines.append(f"[Truncated: Showing first {limit} matches. Narrow pattern or increase limit.]")
        elif aborted_reason == "count_limit":
            if has_results:
                lines.append("[Partial: Search stopped early (scanned too many items). Use a more specific 'path'.]")
            else:
                lines.append("[Error: Search aborted (scanned too many items without results). Use a more specific 'path'.]")
        elif aborted_reason == "time_limit":
            if has_results:
                lines.append("[Partial: Search timed out (>2s). Results are incomplete.]")
            else:
                lines.append("[Error: Search timed out (>2s) without finding results. Try a more specific path.]")
        
        if has_results:
            lines.append("")
            lines.extend(matches)
        
        text = "\n".join(lines)
        
        # 构建 extra_stats
        extra_stats = {
            "matched": len(matches),
            "visited": visited_count,
        }
        
        # 构建 extra_context
        extra_context = {
            "pattern_normalized": pattern_normalized,
        }
        
        # 根据状态选择响应类型
        if is_error_timeout:
            # 无结果且被熔断 → error
            error_code = ErrorCode.TIMEOUT if aborted_reason == "time_limit" else ErrorCode.INTERNAL_ERROR
            return self.create_error_response(
                error_code=error_code,
                message=text,
                params_input=params_input,
                time_ms=time_ms,
                path_resolved=rel_root,
                extra_context=extra_context,
            )
        elif is_partial:
            # 有结果但截断或熔断 → partial
            return self.create_partial_response(
                data=data,
                text=text,
                params_input=params_input,
                time_ms=time_ms,
                extra_stats=extra_stats,
                path_resolved=rel_root,
                extra_context=extra_context,
            )
        else:
            # 正常完成 → success
            return self.create_success_response(
                data=data,
                text=text,
                params_input=params_input,
                time_ms=time_ms,
                extra_stats=extra_stats,
                path_resolved=rel_root,
                extra_context=extra_context,
            )
