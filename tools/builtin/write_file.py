"""文件写入工具 (Write)

遵循《通用工具响应协议》，返回标准化结构。
提供全量覆盖写入能力，支持自动目录创建、Unified Diff 预览、dry_run 模式。
"""

import difflib
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from prompts.tools_prompts.write_prompt import write_prompt
from ..base import Tool, ToolParameter, ToolStatus, ErrorCode


class WriteTool(Tool):
    """文件写入工具，支持全量覆盖、自动创建目录、diff 预览、dry_run"""

    # Diff 预览的最大行数（超过此行数会截断 diff 预览）
    MAX_DIFF_LINES = 100
    
    # Diff 预览的最大字节数（10KB，超过此大小会截断 diff 预览）
    MAX_DIFF_BYTES = 10240

    def __init__(
        self,
        name: str = "Write",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
    ):
        """
        初始化文件写入工具

        Args:
            name: 工具名称，默认为 "Write"
            project_root: 项目根目录，用于沙箱限制（防止写入项目外的文件）
            working_dir: 工作目录，用于解析相对路径
        """
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        
        super().__init__(
            name=name,
            description=write_prompt,
            project_root=project_root,
            working_dir=working_dir if working_dir else project_root,
        )
        
        # 保存项目根目录，用于路径解析和沙箱检查
        self._root = self._project_root

    def run(self, parameters: Dict[str, Any]) -> str:
        """
        执行文件写入操作

        Args:
            parameters: 包含以下键的字典：
                - path: 要写入的文件路径（必填，相对路径）
                - content: 要写入的完整内容（必填）
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
        content = parameters.get("content")
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
        
        # content 必填（允许空字符串，但不允许 None）
        if content is None:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'content' is required.",
                params_input=params_input,
            )
        
        # content 类型校验
        if not isinstance(content, str):
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'content' must be a string.",
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
                error_code=ErrorCode.INTERNAL_ERROR,
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
        # 目标路径检查（是否为目录）
        # =====================================================================
        
        # 如果目标路径是目录，拒绝写入（目录需要使用其他工具处理）
        if abs_path.exists() and abs_path.is_dir():
            return self.create_error_response(
                error_code=ErrorCode.IS_DIRECTORY,
                message="Target path is a directory.",
                params_input=params_input,
                path_resolved=rel_path,
            )

        # =====================================================================
        # 乐观锁校验（在读取原文件内容之前）
        # =====================================================================
        
        expected_mtime_ms = parameters.get("expected_mtime_ms")
        expected_size_bytes = parameters.get("expected_size_bytes")
        
        if abs_path.exists():
            # 已存在文件：强制要求提供期望值（防止覆盖用户修改）
            if expected_mtime_ms is None or expected_size_bytes is None:
                return self.create_error_response(
                    error_code=ErrorCode.INVALID_PARAM,
                    message="expected_mtime_ms and expected_size_bytes are required for existing files. "
                            "Please Read the file first to get current values from stats.",
                    params_input=params_input,
                    path_resolved=rel_path,
                )
            
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

        # =====================================================================
        # 读取原文件内容（用于 diff 计算）
        # =====================================================================
        
        old_content = ""
        original_size = 0
        is_create = True  # 是否为新建文件
        
        if abs_path.exists():
            is_create = False
            try:
                # 获取原文件大小
                original_size = abs_path.stat().st_size
                # 读取原文件内容（UTF-8 编码）
                old_content = abs_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # 原文件编码问题，使用 replace 模式继续读取
                # 这样可以避免因编码问题导致写入失败
                old_content = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                time_ms = int((time.monotonic() - start_time) * 1000)
                return self.create_error_response(
                    error_code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to read original file: {e}",
                    params_input=params_input,
                    time_ms=time_ms,
                    path_resolved=rel_path,
                )

        # =====================================================================
        # Diff 计算
        # =====================================================================
        
        # 计算新旧内容的差异，生成 Unified Diff 预览
        diff_result = self._compute_diff(
            old_content=old_content,
            new_content=content,
            file_path=rel_path,
        )
        
        # 提取 diff 结果
        diff_preview = diff_result["preview"]
        diff_truncated = diff_result["truncated"]
        lines_added = diff_result["lines_added"]
        lines_removed = diff_result["lines_removed"]

        # =====================================================================
        # 自动创建父目录
        # =====================================================================
        
        parent_dir = abs_path.parent
        dir_created: Optional[str] = None
        
        # 如果父目录不存在，需要创建
        if not parent_dir.exists():
            if not dry_run:
                try:
                    # 创建父目录（包括所有中间目录）
                    parent_dir.mkdir(parents=True, exist_ok=True)
                    dir_created = str(parent_dir.relative_to(self._root))
                except OSError as e:
                    time_ms = int((time.monotonic() - start_time) * 1000)
                    return self.create_error_response(
                        error_code=ErrorCode.INTERNAL_ERROR,
                        message=f"Failed to create directory: {e}",
                        params_input=params_input,
                        time_ms=time_ms,
                        path_resolved=rel_path,
                    )
            else:
                # dry_run 模式下，记录将要创建的目录（不实际创建）
                dir_created = str(parent_dir.relative_to(self._root))

        # =====================================================================
        # 执行写入（或 dry_run 跳过）
        # =====================================================================
        
        bytes_written = 0
        new_size = 0
        applied = False
        
        if not dry_run:
            try:
                # 写入前二次校验（缩小 TOCTOU 窗口）
                if not is_create and expected_mtime_ms is not None:
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
                # 使用 PID + 时间戳确保临时文件名唯一
                import os
                temp_path = abs_path.with_suffix(f".tmp.{os.getpid()}.{int(time.time() * 1000000)}")
                temp_path.write_text(content, encoding="utf-8")
                temp_path.replace(abs_path)
                
                applied = True
                bytes_written = len(content.encode("utf-8"))
                new_size = abs_path.stat().st_size
                
            except PermissionError:
                # 权限不足
                time_ms = int((time.monotonic() - start_time) * 1000)
                return self.create_error_response(
                    error_code=ErrorCode.PERMISSION_DENIED,
                    message="Permission denied writing to file.",
                    params_input=params_input,
                    time_ms=time_ms,
                    path_resolved=rel_path,
                )
            except OSError as e:
                # 磁盘空间不足或其他 IO 错误
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
            bytes_written = len(content.encode("utf-8"))
            new_size = bytes_written

        # =====================================================================
        # 构建响应
        # =====================================================================
        
        time_ms = int((time.monotonic() - start_time) * 1000)
        
        return self._format_response(
            rel_path=rel_path,
            applied=applied,
            is_create=is_create,
            dry_run=dry_run,
            diff_preview=diff_preview,
            diff_truncated=diff_truncated,
            bytes_written=bytes_written,
            original_size=original_size,
            new_size=new_size,
            lines_added=lines_added,
            lines_removed=lines_removed,
            dir_created=dir_created,
            time_ms=time_ms,
            params_input=params_input,
            content=content,
        )

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
        # 生成 Unified Diff
        # splitlines(keepends=True) 保留行尾符，确保 diff 准确
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        # 使用 difflib 生成 unified diff 格式的差异
        diff_gen = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",  # 原文件标识
            tofile=f"b/{file_path}",    # 新文件标识
            lineterm="\n"                  # 标准换行符
        )
        
        # 流式处理 diff，避免大文件内存膨胀
        preview_lines: List[str] = []
        preview_bytes = 0
        diff_truncated = False
        lines_added = 0
        lines_removed = 0
        
        for line in diff_gen:
            # 统计增删行数（排除 header 行）
            # header 行以 +++ 或 --- 开头，不计入增删统计
            if line.startswith("+") and not line.startswith("+++"):
                lines_added += 1
            elif line.startswith("-") and not line.startswith("---"):
                lines_removed += 1
            
            # 截断检查
            if not diff_truncated:
                line_bytes = len(line.encode("utf-8"))
                # 超过行数或字节数限制时截断
                if len(preview_lines) >= self.MAX_DIFF_LINES or preview_bytes + line_bytes > self.MAX_DIFF_BYTES:
                    diff_truncated = True
                    break
                else:
                    preview_lines.append(line)
                    preview_bytes += line_bytes
        
        # 构建预览字符串
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
        is_create: bool,
        dry_run: bool,
        diff_preview: str,
        diff_truncated: bool,
        bytes_written: int,
        original_size: int,
        new_size: int,
        lines_added: int,
        lines_removed: int,
        dir_created: Optional[str],
        time_ms: int,
        params_input: Dict[str, Any],
        content: str,
    ) -> str:
        """
        构建标准化响应
        
        状态判定逻辑：
        - dry_run=true → status="partial"（预览模式，未实际写入）
        - diff_truncated=true → status="partial"（diff 被截断，需要用户验证）
        - 其他成功 → status="success"
        
        Args:
            rel_path: 相对路径
            applied: 是否已写入
            is_create: 是否为新建文件
            dry_run: 是否为 dry_run 模式
            diff_preview: diff 预览
            diff_truncated: diff 是否被截断
            bytes_written: 写入的字节数
            original_size: 原文件大小
            new_size: 新文件大小
            lines_added: 增加的行数
            lines_removed: 删除的行数
            dir_created: 创建的目录（如果有）
            time_ms: 耗时（毫秒）
            params_input: 原始输入参数
            content: 写入的内容
        
        Returns:
            JSON 格式的标准化响应字符串
        """
        # 计算内容行数和字节数
        content_lines = len(content.splitlines()) if content else 0
        content_bytes = len(content.encode("utf-8")) if content else 0
        
        # 判断操作类型
        operation = "create" if is_create else "update"
        
        # 判断是否为 partial 状态
        # partial 状态表示操作未完全完成（dry_run 或 diff 被截断）
        is_partial = dry_run or diff_truncated
        
        # 构建 data 字段（包含核心操作数据）
        data: Dict[str, Any] = {
            "applied": applied,
            "operation": operation,
            "diff_preview": diff_preview,
            "diff_truncated": diff_truncated,
        }
        
        # dry_run 模式额外标记
        if dry_run:
            data["dry_run"] = True
        
        # 构建 text 字段（人类可读的描述）
        text_parts: List[str] = []
        
        if dry_run:
            # Dry Run 模式：显示将要执行的操作
            if is_create:
                text_parts.append(f"[Dry Run] Would create '{rel_path}' (+{lines_added} lines).")
            else:
                text_parts.append(f"[Dry Run] Would update '{rel_path}' (+{lines_added}/-{lines_removed} lines).")
        else:
            # 实际写入模式：显示已执行的操作
            if is_create:
                text_parts.append(f"Created '{rel_path}' ({content_lines} lines, {content_bytes} bytes).")
            else:
                text_parts.append(f"Updated '{rel_path}' (+{lines_added}/-{lines_removed} lines, {content_bytes} bytes).")
        
        # 目录创建提示
        if dir_created:
            text_parts.append(f"(Created directory: {dir_created}/)")
        
        # Diff 截断提示
        if diff_truncated:
            text_parts.append("(Diff preview truncated. Use Read to verify full content.)")
        
        text = "\n".join(text_parts)
        
        # 构建 stats 字段（额外的统计信息）
        extra_stats: Dict[str, Any] = {
            "bytes_written": bytes_written,
            "original_size": original_size,
            "new_size": new_size,
            "lines_added": lines_added,
            "lines_removed": lines_removed,
        }
        
        # 根据状态返回不同类型的响应
        if is_partial:
            # partial 状态：操作未完全完成
            return self.create_partial_response(
                data=data,
                text=text,
                params_input=params_input,
                time_ms=time_ms,
                extra_stats=extra_stats,
                path_resolved=rel_path,
            )
        else:
            # success 状态：操作完全成功
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
        
        定义 Write 工具支持的所有参数，包括参数名称、类型、描述、是否必填等。
        这些参数会被框架用于：
        - 生成工具的 schema（供 LLM 理解）
        - 参数验证
        - 自动补全和提示
        
        Returns:
            工具参数列表，包含以下参数：
            - path: 文件路径（必填）
            - content: 文件内容（必填）
            - expected_mtime_ms: 期望的修改时间（现有文件必填）
            - expected_size_bytes: 期望的文件大小（现有文件必填）
            - dry_run: 是否为试运行模式（可选）
        """
        return [
            ToolParameter(
                name="path",
                type="string",
                description="Path to the file (relative to project root, POSIX style). Required.",
                required=True,
            ),
            ToolParameter(
                name="content",
                type="string",
                description="Full content to write to the file (entire file). Required.",
                required=True,
            ),
            ToolParameter(
                name="expected_mtime_ms",
                type="integer",
                description="File mtime in milliseconds when read (from Read response stats.file_mtime_ms). "
                           "Required for existing files to prevent conflicts.",
                required=False,
            ),
            ToolParameter(
                name="expected_size_bytes",
                type="integer",
                description="File size in bytes when read (from Read response stats.file_size_bytes). "
                           "Required for existing files to prevent conflicts.",
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
