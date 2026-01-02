"""多次编辑工具 (MultiEdit)

遵循《通用工具响应协议》，返回标准化结构。
提供原子性批量编辑能力，支持多处独立修改一次性落盘。
所有 old_string 基于原始文件内容匹配，支持冲突检测。
"""

import difflib
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from prompts.tools_prompts.multi_edit_prompt import multi_edit_prompt
from ..base import Tool, ToolParameter, ToolStatus, ErrorCode


class MultiEditTool(Tool):
    """多次编辑工具，支持对同一文件多处独立修改的原子性批量编辑"""

    # 二进制检测的采样大小（读取前 8KB 检测是否包含 null byte）
    BINARY_CHECK_SIZE = 8192
    
    # Diff 预览的最大行数（超过此行数会截断 diff 预览）
    MAX_DIFF_LINES = 100
    
    # Diff 预览的最大字节数（10KB，超过此大小会截断 diff 预览）
    MAX_DIFF_BYTES = 10240

    def __init__(
        self,
        name: str = "MultiEdit",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
    ):
        """
        初始化多次编辑工具

        Args:
            name: 工具名称，默认为 "MultiEdit"
            project_root: 项目根目录，用于沙箱限制（防止编辑项目外的文件）
            working_dir: 工作目录，用于解析相对路径
        """
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        
        super().__init__(
            name=name,
            description=multi_edit_prompt,
            project_root=project_root,
            working_dir=working_dir if working_dir else project_root,
        )
        
        # 保存项目根目录，用于路径解析和沙箱检查
        self._root = self._project_root

    def run(self, parameters: Dict[str, Any]) -> str:
        """
        执行多次编辑操作

        Args:
            parameters: 包含以下键的字典：
                - path: 要编辑的文件路径（必填，相对路径）
                - edits: 编辑操作列表，每项包含 old_string 和 new_string
                - expected_mtime_ms: 期望的文件修改时间（由框架自动注入）
                - expected_size_bytes: 期望的文件大小（由框架自动注入）
                - dry_run: 是否仅预览不写入（默认为 False）

        Returns:
            JSON 格式的响应字符串（遵循《通用工具响应协议》）
        """
        # 记录开始时间，用于计算耗时
        start_time = time.monotonic()
        
        # 保存原始参数用于 context.params_input
        params_input = dict(parameters)
        
        # 提取参数
        path = parameters.get("path")
        edits = parameters.get("edits")
        expected_mtime_ms = parameters.get("expected_mtime_ms")
        expected_size_bytes = parameters.get("expected_size_bytes")
        dry_run = parameters.get("dry_run", False)

        # =====================================================================
        # 参数校验
        # =====================================================================
        
        # path 必填且必须是字符串
        if not path or not isinstance(path, str):
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'path' must be a non-empty string.",
                params_input=params_input,
            )
        
        # edits 必填且必须是非空列表
        if not edits or not isinstance(edits, list):
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'edits' must be a non-empty array.",
                params_input=params_input,
            )
        
        if len(edits) == 0:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'edits' must contain at least one edit.",
                params_input=params_input,
            )
        
        # 校验每个 edit 的结构
        for i, edit in enumerate(edits):
            if not isinstance(edit, dict):
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message=f"Edit at index {i} must be an object with 'old_string' and 'new_string'.",
                    params_input=params_input,
                )
            
            old_string = edit.get("old_string")
            new_string = edit.get("new_string")
            
            if old_string is None or not isinstance(old_string, str):
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message=f"Edit at index {i}: 'old_string' must be a string.",
                    params_input=params_input,
                )
            
            if not old_string:
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message=f"Edit at index {i}: 'old_string' cannot be empty. Provide the exact text to replace.",
                    params_input=params_input,
                )
            
            if new_string is None or not isinstance(new_string, str):
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message=f"Edit at index {i}: 'new_string' must be a string (can be empty to delete).",
                    params_input=params_input,
                )
        
        # dry_run 类型校验
        if not isinstance(dry_run, bool):
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'dry_run' must be a boolean.",
                params_input=params_input,
            )

        # =====================================================================
        # 路径解析与沙箱校验
        # =====================================================================
        
        try:
            input_path = Path(path)
            
            # 1. 拒绝绝对路径（安全限制：只允许相对路径）
            if input_path.is_absolute():
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message="Absolute path not allowed. Use relative path.",
                    params_input=params_input,
                )
            
            # 2. 解析为绝对路径（基于项目根目录）
            abs_path = (self._root / input_path).resolve()
            
            # 3. 沙箱检查：确保路径在项目根目录内（防止路径遍历攻击）
            try:
                abs_path.relative_to(self._root)
            except ValueError:
                return self.create_error_response(
                    error_code=ErrorCode.ACCESS_DENIED,
                    message="Path must be within project root.",
                    params_input=params_input,
                )
            
        except OSError as e:
            return self.create_error_response(
                error_code=ErrorCode.EXECUTION_ERROR,
                message=f"Path resolution failed: {e}",
                params_input=params_input,
            )

        # 计算解析后的相对路径（用于响应和显示）
        try:
            rel_path = str(abs_path.relative_to(self._root))
            if not rel_path:
                rel_path = "."
        except ValueError:
            rel_path = str(abs_path)

        # =====================================================================
        # 文件存在性与类型检查（MultiEdit 只能编辑已存在的文件）
        # =====================================================================
        
        # 检查文件是否存在
        if not abs_path.exists():
            return self.create_error_response(
                error_code=ErrorCode.NOT_FOUND,
                message=f"File '{path}' does not exist. MultiEdit cannot create files, use Write instead.",
                params_input=params_input,
                path_resolved=rel_path,
            )
        
        # 检查是否为目录
        if abs_path.is_dir():
            return self.create_error_response(
                error_code=ErrorCode.IS_DIRECTORY,
                message=f"Path '{path}' is a directory, not a file.",
                params_input=params_input,
                path_resolved=rel_path,
            )

        # =====================================================================
        # 乐观锁校验（在读取文件内容之前）
        # =====================================================================
        
        if expected_mtime_ms is not None and expected_size_bytes is not None:
            # 校验参数类型
            if not isinstance(expected_mtime_ms, int):
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message="Parameter 'expected_mtime_ms' must be an integer.",
                    params_input=params_input,
                    path_resolved=rel_path,
                )
            if not isinstance(expected_size_bytes, int):
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message="Parameter 'expected_size_bytes' must be an integer.",
                    params_input=params_input,
                    path_resolved=rel_path,
                )
            
            # 校验文件是否被修改
            try:
                current_stat = abs_path.stat()
                current_mtime_ms = current_stat.st_mtime_ns // 1_000_000
                current_size_bytes = current_stat.st_size
                
                if current_mtime_ms != expected_mtime_ms or current_size_bytes != expected_size_bytes:
                    return self.create_error_response(
                        error_code=ErrorCode.CONFLICT,
                        message="File has been modified since you read it. "
                                f"Expected mtime={expected_mtime_ms}, size={expected_size_bytes}; "
                                f"Current mtime={current_mtime_ms}, size={current_size_bytes}. "
                                "Please Read the file again to get the latest content.",
                        params_input=params_input,
                        path_resolved=rel_path,
                    )
            except OSError as e:
                return self.create_error_response(
                    error_code=ErrorCode.EXECUTION_ERROR,
                    message=f"Failed to check file status: {e}",
                    params_input=params_input,
                    path_resolved=rel_path,
                )
        elif expected_mtime_ms is None and expected_size_bytes is None:
            # 框架未注入（未先 Read），要求先 Read
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="You must Read the file before editing it. "
                        "expected_mtime_ms and expected_size_bytes are auto-injected by framework after Read.",
                params_input=params_input,
                path_resolved=rel_path,
            )
        else:
            # 只提供了其中一个参数
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Both expected_mtime_ms and expected_size_bytes must be provided together.",
                params_input=params_input,
                path_resolved=rel_path,
            )

        # =====================================================================
        # 二进制文件检测
        # =====================================================================
        
        try:
            if self._is_binary_file(abs_path):
                return self.create_error_response(
                    error_code=ErrorCode.BINARY_FILE,
                    message=f"File '{path}' appears to be binary. Cannot edit binary files.",
                    params_input=params_input,
                    path_resolved=rel_path,
                )
        except OSError as e:
            return self.create_error_response(
                error_code=ErrorCode.EXECUTION_ERROR,
                message=f"Cannot access file: {e}",
                params_input=params_input,
                path_resolved=rel_path,
            )

        # =====================================================================
        # 读取原文件内容
        # =====================================================================
        
        try:
            # 以二进制模式读取，保留原始换行符
            raw_content = abs_path.read_bytes()
            original_size = len(raw_content)
            
            # 尝试 UTF-8 解码
            try:
                old_content = raw_content.decode("utf-8")
            except UnicodeDecodeError:
                # UTF-8 解码失败，使用 replace 模式
                old_content = raw_content.decode("utf-8", errors="replace")
                
        except OSError as e:
            time_ms = int((time.monotonic() - start_time) * 1000)
            return self.create_error_response(
                error_code=ErrorCode.EXECUTION_ERROR,
                message=f"Failed to read file: {e}",
                params_input=params_input,
                time_ms=time_ms,
                path_resolved=rel_path,
            )

        # =====================================================================
        # 换行符探测与归一化
        # =====================================================================
        
        # 探测原始换行符类型
        crlf_count = old_content.count("\r\n")
        lf_count = old_content.count("\n") - crlf_count  # 纯 LF 数量
        use_crlf = crlf_count > lf_count  # 如果 CRLF 更多，保持 CRLF
        
        # 归一化为 LF 进行匹配
        normalized_content = old_content.replace("\r\n", "\n")

        # =====================================================================
        # 匹配定位（基于原文件）
        # =====================================================================
        
        # 存储每个 edit 的匹配区间 [start, end)
        edit_regions: List[Tuple[int, int, int, str]] = []  # (start, end, edit_index, new_string)
        
        for i, edit in enumerate(edits):
            old_string = edit["old_string"]
            new_string = edit["new_string"]
            
            # 归一化换行符
            normalized_old = old_string.replace("\r\n", "\n")
            normalized_new = new_string.replace("\r\n", "\n")
            
            # 统计匹配次数
            match_count = normalized_content.count(normalized_old)
            
            if match_count == 0:
                time_ms = int((time.monotonic() - start_time) * 1000)
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message=f"Edit at index {i}: old_string not found in file. "
                            "Please Read the file again and copy the exact text to replace. "
                            "Check for whitespace, indentation, or line ending differences.",
                    params_input=params_input,
                    time_ms=time_ms,
                    path_resolved=rel_path,
                    data={"failed_index": i},
                )
            
            if match_count > 1:
                time_ms = int((time.monotonic() - start_time) * 1000)
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message=f"Edit at index {i}: old_string matches {match_count} times in file. "
                            "It must be unique. Include more surrounding context (2-5 lines) to make it unique.",
                    params_input=params_input,
                    time_ms=time_ms,
                    path_resolved=rel_path,
                    data={"failed_index": i},
                )
            
            # 记录匹配位置
            start = normalized_content.find(normalized_old)
            end = start + len(normalized_old)
            edit_regions.append((start, end, i, normalized_new))

        # =====================================================================
        # 冲突检测（区间重叠检查）
        # =====================================================================
        
        # 按起始位置排序
        sorted_regions = sorted(edit_regions, key=lambda x: x[0])
        
        for i in range(len(sorted_regions) - 1):
            current_end = sorted_regions[i][1]
            next_start = sorted_regions[i + 1][0]
            
            if current_end > next_start:
                # 区间重叠
                current_idx = sorted_regions[i][2]
                next_idx = sorted_regions[i + 1][2]
                time_ms = int((time.monotonic() - start_time) * 1000)
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message=f"Edits at index {current_idx} and {next_idx} have overlapping regions. "
                            "Please split the edits or reduce conflicts. "
                            "Overlapping edits cannot be applied atomically.",
                    params_input=params_input,
                    time_ms=time_ms,
                    path_resolved=rel_path,
                    data={"failed_index": next_idx},
                )

        # =====================================================================
        # 倒序应用替换（避免索引偏移）
        # =====================================================================
        
        new_content = normalized_content
        
        # 按起始位置倒序排列，从后往前替换
        for start, end, _, new_string in sorted(edit_regions, key=lambda x: x[0], reverse=True):
            new_content = new_content[:start] + new_string + new_content[end:]
        
        # 还原换行符（如果原文件使用 CRLF）
        if use_crlf:
            new_content = new_content.replace("\n", "\r\n")

        # =====================================================================
        # Diff 计算
        # =====================================================================
        
        diff_result = self._compute_diff(
            old_content=old_content,
            new_content=new_content,
            file_path=rel_path,
        )
        
        diff_preview = diff_result["preview"]
        diff_truncated = diff_result["truncated"]
        lines_added = diff_result["lines_added"]
        lines_removed = diff_result["lines_removed"]

        # =====================================================================
        # 执行写入（或 dry_run 跳过）
        # =====================================================================
        
        bytes_written = 0
        new_size = 0
        applied = False
        
        if not dry_run:
            try:
                # 写入前二次校验（缩小 TOCTOU 窗口）
                current_stat = abs_path.stat()
                current_mtime_ms = current_stat.st_mtime_ns // 1_000_000
                current_size_bytes = current_stat.st_size
                
                if current_mtime_ms != expected_mtime_ms or current_size_bytes != expected_size_bytes:
                    time_ms = int((time.monotonic() - start_time) * 1000)
                    return self.create_error_response(
                        error_code=ErrorCode.CONFLICT,
                        message="File has been modified since you read it (detected before write). "
                                f"Expected mtime={expected_mtime_ms}, size={expected_size_bytes}; "
                                f"Current mtime={current_mtime_ms}, size={current_size_bytes}. "
                                "Please Read the file again to get the latest content.",
                        params_input=params_input,
                        time_ms=time_ms,
                        path_resolved=rel_path,
                    )
                
                # 原子写入：先写临时文件，再 rename
                temp_path = abs_path.with_suffix(f".tmp.{os.getpid()}.{int(time.time() * 1000000)}")
                try:
                    temp_path.write_text(new_content, encoding="utf-8")
                    temp_path.replace(abs_path)
                finally:
                    if temp_path.exists():
                        temp_path.unlink()
                
                applied = True
                bytes_written = len(new_content.encode("utf-8"))
                new_size = abs_path.stat().st_size
                
            except PermissionError:
                time_ms = int((time.monotonic() - start_time) * 1000)
                return self.create_error_response(
                    error_code=ErrorCode.PERMISSION_DENIED,
                    message="Permission denied writing to file.",
                    params_input=params_input,
                    time_ms=time_ms,
                    path_resolved=rel_path,
                )
            except OSError as e:
                time_ms = int((time.monotonic() - start_time) * 1000)
                return self.create_error_response(
                    error_code=ErrorCode.EXECUTION_ERROR,
                    message=f"Disk full or IO error: {e}",
                    params_input=params_input,
                    time_ms=time_ms,
                    path_resolved=rel_path,
                )
        else:
            # dry_run 模式：计算预期大小但不写入
            bytes_written = len(new_content.encode("utf-8"))
            new_size = bytes_written

        # =====================================================================
        # 构建响应
        # =====================================================================
        
        time_ms = int((time.monotonic() - start_time) * 1000)
        
        return self._format_response(
            rel_path=rel_path,
            applied=applied,
            dry_run=dry_run,
            diff_preview=diff_preview,
            diff_truncated=diff_truncated,
            replacements=len(edits),
            bytes_written=bytes_written,
            original_size=original_size,
            new_size=new_size,
            lines_added=lines_added,
            lines_removed=lines_removed,
            time_ms=time_ms,
            params_input=params_input,
        )

    def _is_binary_file(self, path: Path) -> bool:
        """
        检测文件是否为二进制文件
        
        读取前 8KB，如果包含 null byte (\x00) 则判定为二进制。
        
        Args:
            path: 文件路径
        
        Returns:
            True 如果是二进制文件，False 如果是文本文件
        """
        try:
            with open(path, "rb") as f:
                chunk = f.read(self.BINARY_CHECK_SIZE)
                return b"\x00" in chunk
        except Exception:
            return False

    def _compute_diff(
        self,
        old_content: str,
        new_content: str,
        file_path: str,
    ) -> Dict[str, Any]:
        """
        计算 Unified Diff 并处理截断
        
        Args:
            old_content: 原文件内容
            new_content: 新文件内容
            file_path: 文件路径（用于 diff header）
        
        Returns:
            包含 preview、truncated、lines_added、lines_removed 的字典
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff_gen = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="\n"
        )
        
        preview_lines: List[str] = []
        preview_bytes = 0
        diff_truncated = False
        lines_added = 0
        lines_removed = 0
        
        for line in diff_gen:
            # 统计增删行数（排除 header 行）
            if line.startswith("+") and not line.startswith("+++"):
                lines_added += 1
            elif line.startswith("-") and not line.startswith("---"):
                lines_removed += 1
            
            # 截断检查
            if not diff_truncated:
                line_bytes = len(line.encode("utf-8"))
                if len(preview_lines) >= self.MAX_DIFF_LINES or preview_bytes + line_bytes > self.MAX_DIFF_BYTES:
                    diff_truncated = True
                    break
                else:
                    preview_lines.append(line)
                    preview_bytes += line_bytes
        
        diff_preview = "\n".join(preview_lines)
        if diff_truncated:
            diff_preview += "\n... (truncated)"
        
        return {
            "preview": diff_preview,
            "truncated": diff_truncated,
            "lines_added": lines_added,
            "lines_removed": lines_removed,
        }

    def _format_response(
        self,
        rel_path: str,
        applied: bool,
        dry_run: bool,
        diff_preview: str,
        diff_truncated: bool,
        replacements: int,
        bytes_written: int,
        original_size: int,
        new_size: int,
        lines_added: int,
        lines_removed: int,
        time_ms: int,
        params_input: Dict[str, Any],
    ) -> str:
        """
        构建标准化响应
        
        状态判定逻辑：
        - dry_run=true → status="partial"
        - diff_truncated=true → status="partial"
        - 其他成功 → status="success"
        """
        # 判断是否为 partial 状态
        is_partial = dry_run or diff_truncated
        
        # 构建 data 字段
        data: Dict[str, Any] = {
            "applied": applied,
            "diff_preview": diff_preview,
            "diff_truncated": diff_truncated,
            "replacements": replacements,
            "failed_index": None,  # 成功时为 null
        }
        
        if dry_run:
            data["dry_run"] = True
        
        # 构建 text 字段
        text_parts: List[str] = []
        
        if dry_run:
            text_parts.append(f"[Dry Run] Would apply {replacements} edits to '{rel_path}' (+{lines_added}/-{lines_removed} lines).")
        else:
            text_parts.append(f"Applied {replacements} edits to '{rel_path}' (+{lines_added}/-{lines_removed} lines, {bytes_written} bytes).")
        
        if diff_truncated:
            text_parts.append("(Diff preview truncated. Use Read to verify full content.)")
        
        text = "\n".join(text_parts)
        
        # 构建 stats 字段
        extra_stats: Dict[str, Any] = {
            "bytes_written": bytes_written,
            "original_size": original_size,
            "new_size": new_size,
            "lines_added": lines_added,
            "lines_removed": lines_removed,
        }
        
        # 根据状态返回不同类型的响应
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
        """
        获取工具参数定义
        """
        return [
            ToolParameter(
                name="path",
                type="string",
                description="Path to the file (relative to project root, POSIX style). Required.",
                required=True,
            ),
            ToolParameter(
                name="edits",
                type="array",
                description="List of edits to apply. Each edit has 'old_string' (exact text to replace, must be unique) "
                           "and 'new_string' (replacement text). All old_string values are matched against the original file.",
                required=True,
            ),
            ToolParameter(
                name="expected_mtime_ms",
                type="integer",
                description="File mtime in milliseconds (from Read response stats.file_mtime_ms). "
                           "Auto-injected by framework after Read.",
                required=False,
            ),
            ToolParameter(
                name="expected_size_bytes",
                type="integer",
                description="File size in bytes (from Read response stats.file_size_bytes). "
                           "Auto-injected by framework after Read.",
                required=False,
            ),
            ToolParameter(
                name="dry_run",
                type="boolean",
                description="If true, compute diff but do not write to disk. Default is false.",
                required=False,
                default=False,
            ),
        ]
