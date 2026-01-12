"""工具结果压缩器

根据《上下文工程方案》A3 规则，将工具返回结果压缩后写入 history。

压缩原则（C1）：
- 保留字段：status, data（按规则压缩）, error（完整保留）
- 丢弃字段：text, stats, context

压缩策略（A3）：
| 工具 | 历史写入压缩策略 |
|---|---|
| LS | 目录 + 统计 + 前 N 项（N=10） |
| Glob | pattern + 命中数 + 前 N 项（N=10） |
| Grep | 摘要 + 前 N 条匹配行（N=5） |
| Read | 保留片段内容（带行号），上限 500 行 |
| Edit/MultiEdit | 变更摘要（文件 + 变更区间 + 关键片段） |
| Write | 变更摘要（文件 + 新增/覆盖 + 片段前 20-50 行） |
| Bash | 摘要 + stderr 尾部 20 行，stdout 仅摘要 |
| TodoWrite | 仅保留 recap |
"""

import json
from typing import Any, Dict, Optional


# 压缩配置常量
LS_MAX_ENTRIES = 10
GLOB_MAX_PATHS = 10
GREP_MAX_MATCHES = 5
READ_MAX_LINES = 500
WRITE_PREVIEW_LINES = 50
BASH_STDERR_TAIL_LINES = 20
BASH_STDOUT_SUMMARY_CHARS = 200


class ToolResultCompressor:
    """工具结果压缩器，用于将完整的工具返回压缩后写入 history。"""

    def compress(self, tool_name: str, raw_result: str) -> str:
        """
        压缩工具返回结果。

        Args:
            tool_name: 工具名称（如 "LS", "Grep", "Read" 等）
            raw_result: 工具返回的原始 JSON 字符串

        Returns:
            压缩后的 JSON 字符串
        """
        try:
            result = json.loads(raw_result)
        except json.JSONDecodeError:
            # 无法解析为 JSON，原样返回（保守策略）
            return raw_result

        # 提取需要保留的字段
        compressed = self._extract_base_fields(result)

        # 根据工具类型压缩 data 字段
        # 注意：data 必须始终存在（即使为空对象），遵循协议规范
        data = result.get("data", {})
        if data is None:
            data = {}
        compressor_method = self._get_compressor(tool_name)
        compressed["data"] = compressor_method(data, result)

        return json.dumps(compressed, ensure_ascii=False, separators=(",", ":"))

    def _extract_base_fields(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """提取基础字段（status, error），丢弃 text/stats/context。"""
        compressed = {
            "status": result.get("status", "success"),
        }

        # error 字段完整保留（仅在 status="error" 时存在）
        if result.get("status") == "error" and "error" in result:
            compressed["error"] = result["error"]

        return compressed

    def _get_compressor(self, tool_name: str):
        """根据工具名称获取对应的 data 压缩方法。"""
        compressors = {
            "LS": self._compress_ls,
            "Glob": self._compress_glob,
            "Grep": self._compress_grep,
            "Read": self._compress_read,
            "Edit": self._compress_edit,
            "MultiEdit": self._compress_multi_edit,
            "Write": self._compress_write,
            "Bash": self._compress_bash,
            "TodoWrite": self._compress_todo_write,
        }
        return compressors.get(tool_name, self._compress_default)

    def _compress_ls(self, data: Dict[str, Any], full_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        LS 压缩：目录 + 统计 + 前 N 项
        
        保留：
        - path: 列出的目录路径（从 context.path_resolved 获取）
        - entries: 前 10 项
        - truncated: 是否截断
        - total_count: 从 stats.total_entries 获取真实总数
        """
        entries = data.get("entries", [])
        
        # 从 stats 获取真实总数（优先），否则用 entries 长度
        stats = full_result.get("stats", {})
        total_count = stats.get("total_entries", len(entries))
        
        # 从 context 获取路径信息
        context = full_result.get("context", {})
        path_resolved = context.get("path_resolved", "")
        
        compressed = {
            "path": path_resolved,
            "entries": entries[:LS_MAX_ENTRIES],
            "truncated": data.get("truncated", False) or len(entries) > LS_MAX_ENTRIES,
            "total_count": total_count,
        }
        
        return compressed

    def _compress_glob(self, data: Dict[str, Any], full_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Glob 压缩：pattern + 命中数 + 前 N 项
        
        保留：
        - pattern: 搜索模式（从 context.params_input 获取）
        - paths: 前 10 项
        - truncated: 是否截断
        - total_matched: 从 stats.matched 获取，或用 paths 长度
        """
        paths = data.get("paths", [])
        
        # 从 stats 获取匹配数（优先），否则用 paths 长度
        stats = full_result.get("stats", {})
        total_matched = stats.get("matched", len(paths))
        
        # 从 context 获取搜索模式
        context = full_result.get("context", {})
        params_input = context.get("params_input", {})
        pattern = params_input.get("pattern", "")
        
        compressed = {
            "pattern": pattern,
            "paths": paths[:GLOB_MAX_PATHS],
            "truncated": data.get("truncated", False) or len(paths) > GLOB_MAX_PATHS,
            "total_matched": total_matched,
        }
        
        # 保留 aborted_reason 如果有
        if "aborted_reason" in data:
            compressed["aborted_reason"] = data["aborted_reason"]
        
        return compressed

    def _compress_grep(self, data: Dict[str, Any], full_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Grep 压缩：pattern + 摘要 + 前 N 条匹配行（N=5）
        
        保留：
        - pattern: 搜索模式（从 context.params_input 获取）
        - matches: 前 5 条（含 file:line:text）
        - truncated: 是否截断
        - total_matches: 从 stats.matched_lines 获取，或用 matches 长度
        """
        matches = data.get("matches", [])
        
        # 从 stats 获取匹配行数（优先），否则用 matches 长度
        stats = full_result.get("stats", {})
        total_matches = stats.get("matched_lines", len(matches))
        
        # 从 context 获取搜索模式
        context = full_result.get("context", {})
        params_input = context.get("params_input", {})
        pattern = params_input.get("pattern", "")
        
        compressed = {
            "pattern": pattern,
            "matches": matches[:GREP_MAX_MATCHES],
            "truncated": data.get("truncated", False) or len(matches) > GREP_MAX_MATCHES,
            "total_matches": total_matches,
        }
        
        # 保留 fallback 信息
        if data.get("fallback_used"):
            compressed["fallback_used"] = True
        
        return compressed

    def _compress_read(self, data: Dict[str, Any], full_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Read 压缩：保留路径、mtime、片段内容（带行号），上限 500 行
        
        保留：
        - path: 文件路径（从 context.path_resolved 获取）
        - file_mtime_ms: 文件修改时间（从 stats 获取，用于外部修改检测）
        - modified_externally: 是否被外部修改（C4 mtime 追踪）
        - content: 文件内容（截断到 500 行）
        - truncated: 是否截断
        """
        content = data.get("content", "")
        
        # 计算行数
        lines = content.split("\n") if content else []
        line_count = len(lines)
        
        # 从 context 获取路径
        context = full_result.get("context", {})
        path_resolved = context.get("path_resolved", "")
        
        # 从 stats 获取 mtime
        stats = full_result.get("stats", {})
        file_mtime_ms = stats.get("file_mtime_ms")
        
        compressed = {
            "path": path_resolved,
            "content": content,  # 保留完整内容（Read 已经限制了行数）
            "truncated": data.get("truncated", False),
        }
        
        # 如果内容超长，截断到 500 行（额外保护）
        if line_count > READ_MAX_LINES:
            truncated_content = "\n".join(lines[:READ_MAX_LINES])
            compressed["content"] = truncated_content
            compressed["truncated"] = True
        
        # 保留 mtime（用于后续读取时检测外部修改）
        if file_mtime_ms is not None:
            compressed["file_mtime_ms"] = file_mtime_ms
        
        # 保留 modified_externally（C4 外部修改提示）
        if data.get("modified_externally"):
            compressed["modified_externally"] = True
        
        # 保留 fallback_encoding 信息
        if "fallback_encoding" in data:
            compressed["fallback_encoding"] = data["fallback_encoding"]
        
        return compressed

    def _compress_edit(self, data: Dict[str, Any], full_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Edit 压缩：变更摘要（文件 + 变更区间 + 关键片段）
        
        保留：
        - path: 编辑的文件路径
        - applied: 是否已应用
        - replacements: 替换次数
        - diff_summary: diff 的前 10 行（关键变更片段）
        """
        # 从 context 获取路径
        context = full_result.get("context", {})
        path_resolved = context.get("path_resolved", "")
        
        compressed = {
            "path": path_resolved,
            "applied": data.get("applied", False),
            "replacements": data.get("replacements", 0),
        }
        
        # 保留 diff_preview 的前 10 行作为摘要（A3 要求保留关键片段）
        diff_preview = data.get("diff_preview", "")
        if diff_preview:
            diff_lines = diff_preview.split("\n")
            compressed["diff_summary"] = "\n".join(diff_lines[:10])
            if len(diff_lines) > 10:
                compressed["diff_truncated"] = True
        
        if data.get("dry_run"):
            compressed["dry_run"] = True
        
        return compressed

    def _compress_multi_edit(self, data: Dict[str, Any], full_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        MultiEdit 压缩：变更摘要
        
        保留：
        - path: 编辑的文件路径
        - applied: 是否已应用
        - replacements: 替换次数
        - diff_summary: diff 的前 10 行
        """
        # 从 context 获取路径
        context = full_result.get("context", {})
        path_resolved = context.get("path_resolved", "")
        
        compressed = {
            "path": path_resolved,
            "applied": data.get("applied", False),
            "replacements": data.get("replacements", 0),
        }
        
        # 保留 diff_preview 的前 10 行作为摘要
        diff_preview = data.get("diff_preview", "")
        if diff_preview:
            diff_lines = diff_preview.split("\n")
            compressed["diff_summary"] = "\n".join(diff_lines[:10])
            if len(diff_lines) > 10:
                compressed["diff_truncated"] = True
        
        if data.get("dry_run"):
            compressed["dry_run"] = True
        
        # 保留 failed_edits 信息（如果有部分失败）
        if "failed_edits" in data:
            compressed["failed_edits"] = data["failed_edits"]
        
        return compressed

    def _compress_write(self, data: Dict[str, Any], full_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Write 压缩：变更摘要（文件 + 新增/覆盖 + 片段前 50 行）
        
        保留：
        - path: 写入的文件路径
        - applied: 是否已应用
        - operation: create/update
        - content_summary: 写入内容的前 50 行
        """
        # 从 context 获取路径
        context = full_result.get("context", {})
        path_resolved = context.get("path_resolved", "")
        
        compressed = {
            "path": path_resolved,
            "applied": data.get("applied", False),
            "operation": data.get("operation", "unknown"),
        }
        
        # 保留 diff_preview 的前 10 行作为摘要
        diff_preview = data.get("diff_preview", "")
        if diff_preview:
            diff_lines = diff_preview.split("\n")
            compressed["diff_summary"] = "\n".join(diff_lines[:10])
            if len(diff_lines) > 10:
                compressed["diff_truncated"] = True
        
        if data.get("dry_run"):
            compressed["dry_run"] = True
        
        return compressed

    def _compress_bash(self, data: Dict[str, Any], full_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Bash 压缩：摘要 + stderr 尾部 20 行，stdout 仅摘要
        
        保留：
        - exit_code
        - command
        - stdout_summary: stdout 前 200 字符
        - stderr_tail: stderr 尾部 20 行
        """
        stdout = data.get("stdout", "")
        stderr = data.get("stderr", "")
        
        compressed = {
            "exit_code": data.get("exit_code"),
            "command": data.get("command", ""),
        }
        
        # stdout 仅保留摘要（前 200 字符）
        if stdout:
            if len(stdout) > BASH_STDOUT_SUMMARY_CHARS:
                compressed["stdout_summary"] = stdout[:BASH_STDOUT_SUMMARY_CHARS] + "..."
            else:
                compressed["stdout_summary"] = stdout
        
        # stderr 保留尾部 20 行
        if stderr:
            stderr_lines = stderr.split("\n")
            if len(stderr_lines) > BASH_STDERR_TAIL_LINES:
                compressed["stderr_tail"] = "\n".join(stderr_lines[-BASH_STDERR_TAIL_LINES:])
                compressed["stderr_truncated"] = True
            else:
                compressed["stderr_tail"] = stderr
        
        # 保留 signal 信息
        if data.get("signal"):
            compressed["signal"] = data["signal"]
        
        return compressed

    def _compress_todo_write(self, data: Dict[str, Any], full_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        TodoWrite 压缩：仅保留 recap
        
        丢弃完整的 todos 列表，只保留简短的 recap 摘要。
        """
        compressed = {
            "recap": data.get("recap", ""),
        }
        
        return compressed

    def _compress_default(self, data: Dict[str, Any], full_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        默认压缩策略：保留 data 原样（针对未知工具）
        
        作为兜底策略，确保不会丢失关键信息。
        如果 data 过大（>1000 字符），则截断。
        """
        data_str = json.dumps(data, ensure_ascii=False)
        if len(data_str) > 1000:
            # 截断策略：保留前 1000 字符对应的 JSON 结构
            # 简单处理：直接返回截断标记
            return {
                "truncated": True,
                "original_size": len(data_str),
            }
        return data


# 单例实例，供外部使用
tool_result_compressor = ToolResultCompressor()


def compress_tool_result(tool_name: str, raw_result: str) -> str:
    """
    压缩工具返回结果的便捷函数。

    Args:
        tool_name: 工具名称
        raw_result: 原始 JSON 结果字符串

    Returns:
        压缩后的 JSON 字符串
    """
    return tool_result_compressor.compress(tool_name, raw_result)
