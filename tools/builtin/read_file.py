"""文件读取工具 (Read)

遵循《通用工具响应协议》，返回标准化结构。
提供带行号的文本读取能力，为代码编辑场景优化。
"""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from prompts.tools_prompts.read_prompt import read_prompt
from ..base import Tool, ToolParameter, ToolStatus, ErrorCode


class ReadTool(Tool):
    """文件读取工具，支持行号、分页、编码回退"""

    # 二进制检测的采样大小
    BINARY_CHECK_SIZE = 8192
    
    # limit 的硬上限
    MAX_LIMIT = 2000
    
    # 默认 limit
    DEFAULT_LIMIT = 500

    def __init__(
        self,
        name: str = "Read",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
    ):
        """
        初始化文件读取工具

        Args:
            name: 工具名称，默认为 "Read"
            project_root: 项目根目录，用于沙箱限制
            working_dir: 工作目录，用于解析相对路径
        """
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        
        super().__init__(
            name=name,
            description=read_prompt,
            project_root=project_root,
            working_dir=working_dir if working_dir else project_root,
        )
        
        self._root = self._project_root

    def run(self, parameters: Dict[str, Any]) -> str:
        """
        执行文件读取操作

        Args:
            parameters: 包含以下键的字典：
                - path: 要读取的文件路径（必填）
                - start_line: 起始行号，1-based（默认为 1）
                - limit: 读取的最大行数（默认为 500，硬上限 2000）

        Returns:
            JSON 格式的响应字符串（遵循《通用工具响应协议》）
        """
        start_time = time.monotonic()
        
        # 保存原始参数用于 context.params_input
        params_input = dict(parameters)
        
        path = parameters.get("path")
        start_line = parameters.get("start_line", 1)
        limit = parameters.get("limit", self.DEFAULT_LIMIT)

        # =====================================================================
        # 参数校验
        # =====================================================================
        
        # path 必填
        if not path:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'path' is required.",
                params_input=params_input,
            )
        
        # start_line 校验
        if not isinstance(start_line, int) or start_line < 1:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="start_line must be a positive integer (>= 1).",
                params_input=params_input,
            )
        
        # limit 校验
        if not isinstance(limit, int) or limit < 1 or limit > self.MAX_LIMIT:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message=f"limit must be an integer between 1 and {self.MAX_LIMIT}.",
                params_input=params_input,
            )

        # =====================================================================
        # 路径解析与沙箱校验
        # =====================================================================
        
        try:
            input_path = Path(path)
            if input_path.is_absolute():
                target = input_path.resolve()
            else:
                target = (self._root / input_path).resolve()

            # 沙箱安全检查
            target.relative_to(self._root)
        except ValueError:
            return self.create_error_response(
                error_code=ErrorCode.ACCESS_DENIED,
                message=f"Access denied. Path '{path}' is outside project root.",
                params_input=params_input,
            )
        except OSError as e:
            return self.create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Path resolution failed: {e}",
                params_input=params_input,
            )

        # 计算解析后的相对路径
        try:
            rel_path = str(target.relative_to(self._root))
            if not rel_path:
                rel_path = "."
        except ValueError:
            rel_path = str(target)

        # =====================================================================
        # 文件存在性与类型检查
        # =====================================================================
        
        if not target.exists():
            return self.create_error_response(
                error_code=ErrorCode.NOT_FOUND,
                message=f"File '{path}' does not exist.",
                params_input=params_input,
                path_resolved=rel_path,
            )
        
        if target.is_dir():
            return self.create_error_response(
                error_code=ErrorCode.IS_DIRECTORY,
                message=f"Path '{path}' is a directory. Use LS to explore it.",
                params_input=params_input,
                path_resolved=rel_path,
            )

        # =====================================================================
        # 二进制文件检测
        # =====================================================================
        
        try:
            file_size = target.stat().st_size
            if self._is_binary_file(target):
                return self.create_error_response(
                    error_code=ErrorCode.BINARY_FILE,
                    message=f"File '{path}' appears to be binary. Cannot read as text.",
                    params_input=params_input,
                    path_resolved=rel_path,
                )
        except OSError as e:
            return self.create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Cannot access file: {e}",
                params_input=params_input,
                path_resolved=rel_path,
            )

        # =====================================================================
        # 读取文件内容
        # =====================================================================
        
        try:
            content, total_lines, encoding_used, fallback_used = self._read_file_content(
                target, start_line, limit
            )
        except Exception as e:
            time_ms = int((time.monotonic() - start_time) * 1000)
            return self.create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Failed to read file: {e}",
                params_input=params_input,
                time_ms=time_ms,
                path_resolved=rel_path,
            )

        # =====================================================================
        # start_line 边界检查
        # =====================================================================
        if total_lines == 0 and start_line > 1:
            time_ms = int((time.monotonic() - start_time) * 1000)
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="start_line exceeds file length (file is empty). Valid start_line is 1.",
                params_input=params_input,
                time_ms=time_ms,
                path_resolved=rel_path,
                extra_context={"total_lines": total_lines},
            )
        
        if start_line > total_lines and total_lines > 0:
            time_ms = int((time.monotonic() - start_time) * 1000)
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message=f"start_line ({start_line}) exceeds file length ({total_lines} lines). "
                        f"Valid range: 1 to {total_lines}.",
                params_input=params_input,
                time_ms=time_ms,
                path_resolved=rel_path,
                extra_context={"total_lines": total_lines},
            )

        # =====================================================================
        # 构建响应
        # =====================================================================
        
        time_ms = int((time.monotonic() - start_time) * 1000)
        
        return self._format_response(
            content=content,
            rel_path=rel_path,
            start_line=start_line,
            limit=limit,
            total_lines=total_lines,
            file_size=file_size,
            encoding_used=encoding_used,
            fallback_used=fallback_used,
            time_ms=time_ms,
            params_input=params_input,
        )

    def _is_binary_file(self, path: Path) -> bool:
        """
        检测文件是否为二进制文件
        
        读取前 8KB，如果包含 null byte (\x00) 则判定为二进制。
        """
        try:
            with open(path, "rb") as f:
                chunk = f.read(self.BINARY_CHECK_SIZE)
                return b"\x00" in chunk
        except Exception:
            return False

    def _read_file_content(
        self, 
        path: Path, 
        start_line: int, 
        limit: int
    ) -> Tuple[str, int, str, bool]:
        """
        读取文件内容并添加行号
        
        Args:
            path: 文件路径
            start_line: 起始行号 (1-based)
            limit: 最大行数
        
        Returns:
            (formatted_content, total_lines, encoding_used, fallback_used)
        """
        encoding_used = "utf-8"
        fallback_used = False
        
        # 尝试 UTF-8 严格模式
        try:
            with open(path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
        except UnicodeDecodeError:
            # 回退到 UTF-8 + errors="replace"
            fallback_used = True
            encoding_used = "utf-8 (replace)"
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        
        total_lines = len(all_lines)
        
        # 空文件处理
        if total_lines == 0:
            return "", 0, encoding_used, fallback_used
        
        # 提取目标行
        start_idx = start_line - 1  # 转换为 0-based
        end_idx = min(start_idx + limit, total_lines)
        
        # 如果 start_line 超出范围，返回空内容（后续会检测并报错）
        if start_idx >= total_lines:
            return "", total_lines, encoding_used, fallback_used
        
        selected_lines = all_lines[start_idx:end_idx]
        
        # 格式化输出："%4d | %s\n"
        formatted_parts = []
        for i, line in enumerate(selected_lines, start=start_line):
            # 移除行尾的换行符，统一添加
            line_content = line.rstrip("\n\r")
            formatted_parts.append(f"{i:4d} | {line_content}\n")
        
        content = "".join(formatted_parts)
        
        return content, total_lines, encoding_used, fallback_used

    def _format_response(
        self,
        content: str,
        rel_path: str,
        start_line: int,
        limit: int,
        total_lines: int,
        file_size: int,
        encoding_used: str,
        fallback_used: bool,
        time_ms: int,
        params_input: Dict[str, Any],
    ) -> str:
        """
        构建标准化响应
        
        状态判定逻辑：
        - 触发截断 → status="partial"
        - 编码回退 → status="partial"
        - 其他 → status="success"
        """
        # 计算实际读取的行数
        if total_lines == 0:
            lines_read = 0
            end_line = 0
        else:
            start_idx = start_line - 1
            end_idx = min(start_idx + limit, total_lines)
            lines_read = end_idx - start_idx
            end_line = start_line + lines_read - 1 if lines_read > 0 else 0
        
        # 判断是否截断
        truncated = (start_line + lines_read - 1) < total_lines if lines_read > 0 else False
        
        # 判断状态
        is_partial = truncated or fallback_used
        
        # 构建 data
        data: Dict[str, Any] = {
            "content": content,
            "truncated": truncated,
        }
        if fallback_used:
            data["fallback_encoding"] = "replace"
        
        # 构建 text
        lines = []
        
        if total_lines == 0:
            lines.append(f"Read 0 lines from '{rel_path}' (file is empty).")
        else:
            lines.append(f"Read {lines_read} lines from '{rel_path}' (Lines {start_line}-{end_line}).")
        
        lines.append(f"(Took {time_ms}ms)")
        
        if truncated:
            next_start = end_line + 1
            remaining = total_lines - end_line
            lines.append(f"[Truncated: Showing {lines_read} of {total_lines} lines. "
                        f"Use start_line={next_start} to continue ({remaining} lines remaining).]")
        
        if fallback_used:
            lines.append("[Warning: Encoding issues detected. Some characters may be corrupted (using replacement).]")
        
        text = "\n".join(lines)
        
        # 构建 stats
        extra_stats = {
            "lines_read": lines_read,
            "chars_read": len(content),
            "total_lines": total_lines,
            "file_size_bytes": file_size,
            "encoding": encoding_used,
        }
        
        # 返回响应
        if is_partial:
            return self.create_partial_response(
                data=data,
                text=text,
                params_input=params_input,
                time_ms=time_ms,
                extra_stats=extra_stats,
                path_resolved=rel_path,
            )
        else:
            return self.create_success_response(
                data=data,
                text=text,
                params_input=params_input,
                time_ms=time_ms,
                extra_stats=extra_stats,
                path_resolved=rel_path,
            )

    def get_parameters(self) -> List[ToolParameter]:
        """获取工具参数定义"""
        return [
            ToolParameter(
                name="path",
                type="string",
                description="Path to the file (relative to project root). Required.",
                required=True,
            ),
            ToolParameter(
                name="start_line",
                type="integer",
                description="The line number to start reading from (1-based). Default is 1.",
                required=False,
                default=1,
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description=f"The maximum number of lines to read. Default is {self.DEFAULT_LIMIT}. "
                           f"Hard limit is {self.MAX_LIMIT}.",
                required=False,
                default=self.DEFAULT_LIMIT,
            ),
        ]
