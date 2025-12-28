"""通用工具响应协议验证器

遵循《通用工具响应协议》，提供可复用的协议合规性验证函数。

验证规则清单：
- V001-V012: 结构验证（必需字段、类型、禁止自定义顶层字段）
- S001-S008: 状态语义验证（error字段、截断、回退）
- T001-T004: text内容验证（非空、长度、说明）
- D001-D007: 工具特定字段验证（entries/paths/matches）

使用方式：
    from tests.utils.protocol_validator import ProtocolValidator
    
    result = ProtocolValidator.validate(response_json_string)
    if not result.passed:
        for error in result.errors:
            print(error)
"""

import json
import sys
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """验证结果"""
    passed: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def add_error(self, rule_id: str, message: str):
        """添加错误"""
        self.passed = False
        self.errors.append(f"[{rule_id}] {message}")
    
    def add_warning(self, rule_id: str, message: str):
        """添加警告（不影响 passed 状态）"""
        self.warnings.append(f"[{rule_id}] {message}")
    
    def __str__(self) -> str:
        """格式化输出"""
        lines = []
        if self.passed:
            lines.append("✅ 协议验证通过")
        else:
            lines.append("❌ 协议验证失败")
        
        if self.errors:
            lines.append("\n错误:")
            for error in self.errors:
                lines.append(f"  {error}")
        
        if self.warnings:
            lines.append("\n警告:")
            for warning in self.warnings:
                lines.append(f"  ⚠️  {warning}")
        
        return "\n".join(lines)


class ProtocolValidator:
    """
    通用工具响应协议验证器
    
    验证工具响应是否严格遵循《通用工具响应协议》。
    """
    
    # 允许的顶层字段（严格限制，禁止自定义）
    ALLOWED_TOP_LEVEL_KEYS: Set[str] = {"status", "data", "text", "error", "stats", "context"}
    
    # 有效的 status 值
    VALID_STATUSES: Set[str] = {"success", "partial", "error"}
    
    # 标准错误码
    VALID_ERROR_CODES: Set[str] = {
        "NOT_FOUND",       # 文件/路径不存在
        "ACCESS_DENIED",   # 路径不在 project root 内
        "PERMISSION_DENIED",  # OS 权限不足
        "INVALID_PARAM",   # 参数校验失败
        "TIMEOUT",         # 工具在获取有效数据前超时
        "INTERNAL_ERROR",  # 未分类的内部异常
        "EXECUTION_ERROR", # 其它 I/O 或执行错误
        "IS_DIRECTORY",    # 路径是目录而非文件
        "BINARY_FILE",     # 文件是二进制格式
    }
    
    # 工具类别与推荐字段映射
    TOOL_DATA_FIELDS = {
        "ls": {"entries"},           # 目录探索
        "glob": {"paths"},           # 通配匹配
        "grep": {"matches"},         # 内容搜索
        "read": {"content"},         # 文件读取
        "edit": {"applied"},         # 修改类
    }
    
    @classmethod
    def validate(cls, response_str: str, tool_type: Optional[str] = None) -> ValidationResult:
        """
        验证响应是否符合协议
        
        Args:
            response_str: JSON 格式的响应字符串
            tool_type: 工具类型（可选，用于特定字段验证）
                       可选值: "ls", "glob", "grep", "read", "edit"
        
        Returns:
            ValidationResult: 验证结果
        """
        result = ValidationResult()
        
        # V001: JSON 解析
        try:
            response = json.loads(response_str)
        except json.JSONDecodeError as e:
            result.add_error("V001", f"无效的 JSON 格式: {e}")
            return result
        
        if not isinstance(response, dict):
            result.add_error("V001", f"响应必须是对象，实际类型: {type(response).__name__}")
            return result
        
        # V002-V012: 结构验证
        cls._validate_structure(response, result)
        
        # 如果结构验证失败，跳过后续验证
        if not result.passed:
            return result
        
        # S001-S008: 状态语义验证
        cls._validate_status_semantics(response, result)
        
        # T001-T004: text 内容验证
        cls._validate_text_content(response, result)
        
        # D001-D007: 工具特定字段验证（如果指定了工具类型）
        if tool_type:
            cls._validate_tool_specific(response, tool_type, result)
        
        return result
    
    @classmethod
    def validate_dict(cls, response: Dict[str, Any], tool_type: Optional[str] = None) -> ValidationResult:
        """
        验证响应字典是否符合协议
        
        Args:
            response: 响应字典
            tool_type: 工具类型（可选）
        
        Returns:
            ValidationResult: 验证结果
        """
        return cls.validate(json.dumps(response, ensure_ascii=False), tool_type)
    
    # =========================================================================
    # 结构验证 (V001-V012)
    # =========================================================================
    
    @classmethod
    def _validate_structure(cls, response: Dict, result: ValidationResult):
        """结构验证"""
        
        # V002: status 字段必须存在
        if "status" not in response:
            result.add_error("V002", "缺少必需字段 'status'")
        else:
            # V003: status 值必须是枚举之一
            if response["status"] not in cls.VALID_STATUSES:
                result.add_error("V003", f"无效的 status 值: '{response['status']}'，"
                               f"允许值: {cls.VALID_STATUSES}")
        
        # V004-V005: data 字段
        if "data" not in response:
            result.add_error("V004", "缺少必需字段 'data'")
        elif response["data"] is None:
            result.add_error("V005", "字段 'data' 不能为 null")
        elif not isinstance(response["data"], dict):
            result.add_error("V005", f"字段 'data' 必须是对象，实际类型: {type(response['data']).__name__}")
        
        # V006: text 字段
        if "text" not in response:
            result.add_error("V006", "缺少必需字段 'text'")
        elif not isinstance(response.get("text"), str):
            result.add_error("V006", f"字段 'text' 必须是字符串，实际类型: {type(response.get('text')).__name__}")
        
        # V007-V008: stats 字段
        if "stats" not in response:
            result.add_error("V007", "缺少必需字段 'stats'")
        else:
            stats = response["stats"]
            if not isinstance(stats, dict):
                result.add_error("V007", f"字段 'stats' 必须是对象，实际类型: {type(stats).__name__}")
            elif "time_ms" not in stats:
                result.add_error("V008", "缺少必需字段 'stats.time_ms'")
            elif not isinstance(stats["time_ms"], (int, float)):
                result.add_error("V008", f"字段 'stats.time_ms' 必须是数字，"
                               f"实际类型: {type(stats['time_ms']).__name__}")
        
        # V009-V011: context 字段
        if "context" not in response:
            result.add_error("V009", "缺少必需字段 'context'")
        else:
            context = response["context"]
            if not isinstance(context, dict):
                result.add_error("V009", f"字段 'context' 必须是对象，实际类型: {type(context).__name__}")
            else:
                # V010: context.cwd
                if "cwd" not in context:
                    result.add_error("V010", "缺少必需字段 'context.cwd'")
                elif not isinstance(context["cwd"], str):
                    result.add_error("V010", f"字段 'context.cwd' 必须是字符串，"
                                   f"实际类型: {type(context['cwd']).__name__}")
                
                # V011: context.params_input
                if "params_input" not in context:
                    result.add_error("V011", "缺少必需字段 'context.params_input'")
        
        # V012: 禁止顶层自定义字段
        extra_keys = set(response.keys()) - cls.ALLOWED_TOP_LEVEL_KEYS
        if extra_keys:
            result.add_error("V012", f"禁止的顶层自定义字段: {extra_keys}")
    
    # =========================================================================
    # 状态语义验证 (S001-S008)
    # =========================================================================
    
    @classmethod
    def _validate_status_semantics(cls, response: Dict, result: ValidationResult):
        """状态语义验证"""
        status = response.get("status")
        data = response.get("data", {})
        error = response.get("error")
        
        # S001: error 字段仅在 status="error" 时存在
        if status != "error" and error is not None:
            result.add_error("S001", f"status='{status}' 时不应存在 'error' 字段")
        
        # S002-S003: status="error" 时的 error 字段验证
        if status == "error":
            if error is None:
                result.add_error("S002", "status='error' 时必须包含 'error' 字段")
            elif not isinstance(error, dict):
                result.add_error("S002", f"'error' 字段必须是对象，实际类型: {type(error).__name__}")
            else:
                # 检查 error.code 和 error.message
                if "code" not in error:
                    result.add_error("S002", "'error' 对象必须包含 'code' 字段")
                elif error["code"] not in cls.VALID_ERROR_CODES:
                    result.add_error("S003", f"无效的错误码: '{error['code']}'，"
                                   f"允许值: {cls.VALID_ERROR_CODES}")
                
                if "message" not in error:
                    result.add_error("S002", "'error' 对象必须包含 'message' 字段")
            
            # S004: status="error" 时 data 应为空对象（警告级别）
            if data and data != {}:
                result.add_warning("S004", "status='error' 时 data 应为空对象 {}")
        
        # S005-S006: 截断时必须是 partial 状态
        if data.get("truncated") is True:
            if status != "partial":
                result.add_error("S005", "data.truncated=true 时 status 必须为 'partial'")
            
            # S006: 截断时 text 应说明（警告级别）
            text = response.get("text", "")
            truncate_keywords = ["truncat", "截断", "limit", "first", "partial"]
            if not any(kw.lower() in text.lower() for kw in truncate_keywords):
                result.add_warning("S006", "data.truncated=true 时 text 应说明截断情况")
        
        # S007-S008: 回退时必须是 partial 状态
        if data.get("fallback_used") is True or "fallback" in data:
            if status != "partial":
                result.add_error("S007", "使用回退策略时 status 必须为 'partial'")
            
            # S008: 回退时 text 应说明（警告级别）
            text = response.get("text", "")
            fallback_keywords = ["fallback", "回退", "降级", "slower", "python"]
            if not any(kw.lower() in text.lower() for kw in fallback_keywords):
                result.add_warning("S008", "使用回退策略时 text 应说明回退情况")
    
    # =========================================================================
    # text 内容验证 (T001-T004)
    # =========================================================================
    
    @classmethod
    def _validate_text_content(cls, response: Dict, result: ValidationResult):
        """text 内容验证"""
        text = response.get("text", "")
        status = response.get("status")
        
        # T001: text 不能为空
        if not text or not text.strip():
            result.add_error("T001", "字段 'text' 不能为空")
            return
        
        # T004: text 长度合理（警告级别）
        if len(text.strip()) < 10:
            result.add_warning("T004", f"text 过短 ({len(text.strip())} 字符)，建议至少 10 字符")
        
        # T002: partial 时应有状态说明（警告级别）
        if status == "partial":
            partial_keywords = ["partial", "truncat", "fallback", "incomplete", 
                              "部分", "截断", "回退", "不完整"]
            if not any(kw.lower() in text.lower() for kw in partial_keywords):
                result.add_warning("T002", "status='partial' 时 text 应包含状态说明")
        
        # T003: error 时应有下一步建议（警告级别）
        if status == "error":
            guidance_keywords = ["try", "check", "use", "run", "verify",
                               "尝试", "检查", "使用", "运行", "验证"]
            if not any(kw.lower() in text.lower() for kw in guidance_keywords):
                result.add_warning("T003", "status='error' 时 text 应包含下一步建议")
    
    # =========================================================================
    # 工具特定字段验证 (D001-D007)
    # =========================================================================
    
    @classmethod
    def _validate_tool_specific(cls, response: Dict, tool_type: str, result: ValidationResult):
        """工具特定字段验证"""
        data = response.get("data", {})
        status = response.get("status")
        
        # error 状态下 data 为空，跳过工具特定验证
        if status == "error":
            return
        
        tool_type = tool_type.lower()
        
        if tool_type == "ls":
            cls._validate_ls_data(data, result)
        elif tool_type == "glob":
            cls._validate_glob_data(data, result)
        elif tool_type == "grep":
            cls._validate_grep_data(data, result)
        elif tool_type == "read":
            cls._validate_read_data(data, result)
        elif tool_type == "edit":
            cls._validate_edit_data(data, result)
    
    @classmethod
    def _validate_ls_data(cls, data: Dict, result: ValidationResult):
        """验证 LS 工具 data 字段"""
        # D001: data.entries 必须是数组
        if "entries" not in data:
            result.add_error("D001", "LS 工具 data 必须包含 'entries' 字段")
            return
        
        entries = data["entries"]
        if not isinstance(entries, list):
            result.add_error("D001", f"data.entries 必须是数组，实际类型: {type(entries).__name__}")
            return
        
        # D002-D003: 验证 entries 元素结构
        valid_types = {"file", "dir", "link"}
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                result.add_error("D002", f"entries[{i}] 必须是对象")
                continue
            
            if "path" not in entry:
                result.add_error("D002", f"entries[{i}] 缺少 'path' 字段")
            
            if "type" not in entry:
                result.add_error("D002", f"entries[{i}] 缺少 'type' 字段")
            elif entry["type"] not in valid_types:
                result.add_error("D003", f"entries[{i}].type 值无效: '{entry['type']}'，"
                               f"允许值: {valid_types}")
    
    @classmethod
    def _validate_glob_data(cls, data: Dict, result: ValidationResult):
        """验证 Glob 工具 data 字段"""
        # D004: data.paths 必须是字符串数组
        if "paths" not in data:
            result.add_error("D004", "Glob 工具 data 必须包含 'paths' 字段")
            return
        
        paths = data["paths"]
        if not isinstance(paths, list):
            result.add_error("D004", f"data.paths 必须是数组，实际类型: {type(paths).__name__}")
            return
        
        for i, path in enumerate(paths):
            if not isinstance(path, str):
                result.add_error("D004", f"paths[{i}] 必须是字符串，实际类型: {type(path).__name__}")
    
    @classmethod
    def _validate_grep_data(cls, data: Dict, result: ValidationResult):
        """验证 Grep 工具 data 字段"""
        # D005: data.matches 必须是数组
        if "matches" not in data:
            result.add_error("D005", "Grep 工具 data 必须包含 'matches' 字段")
            return
        
        matches = data["matches"]
        if not isinstance(matches, list):
            result.add_error("D005", f"data.matches 必须是数组，实际类型: {type(matches).__name__}")
            return
        
        # D006-D007: 验证 matches 元素结构
        for i, match in enumerate(matches):
            if not isinstance(match, dict):
                result.add_error("D006", f"matches[{i}] 必须是对象")
                continue
            
            if "file" not in match:
                result.add_error("D006", f"matches[{i}] 缺少 'file' 字段")
            
            if "line" not in match:
                result.add_error("D006", f"matches[{i}] 缺少 'line' 字段")
            elif not isinstance(match["line"], int):
                result.add_error("D007", f"matches[{i}].line 必须是整数，"
                               f"实际类型: {type(match['line']).__name__}")
            
            if "text" not in match:
                result.add_error("D006", f"matches[{i}] 缺少 'text' 字段")
    
    @classmethod
    def _validate_read_data(cls, data: Dict, result: ValidationResult):
        """验证 Read 工具 data 字段"""
        if "content" not in data:
            result.add_error("D008", "Read 工具 data 必须包含 'content' 字段")
        elif not isinstance(data["content"], str):
            result.add_error("D008", f"data.content 必须是字符串，"
                           f"实际类型: {type(data['content']).__name__}")
    
    @classmethod
    def _validate_edit_data(cls, data: Dict, result: ValidationResult):
        """验证 Edit 工具 data 字段"""
        if "applied" not in data:
            result.add_error("D009", "Edit 工具 data 必须包含 'applied' 字段")
        elif not isinstance(data["applied"], bool):
            result.add_error("D009", f"data.applied 必须是布尔值，"
                           f"实际类型: {type(data['applied']).__name__}")


# =============================================================================
# CLI 支持：直接运行验证
# =============================================================================

def main():
    """命令行入口：验证工具响应"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="验证工具响应是否符合《通用工具响应协议》",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 验证 JSON 字符串
  python -m tests.utils.protocol_validator '{"status":"success",...}'
  
  # 验证 JSON 文件
  python -m tests.utils.protocol_validator response.json --file
  
  # 指定工具类型验证
  python -m tests.utils.protocol_validator response.json --file --type ls
        """
    )
    parser.add_argument("response", help="响应 JSON 字符串或文件路径")
    parser.add_argument("--file", "-f", action="store_true", help="输入是文件路径")
    parser.add_argument("--type", "-t", choices=["ls", "glob", "grep", "read", "edit"],
                       help="工具类型（用于特定字段验证）")
    parser.add_argument("--quiet", "-q", action="store_true", help="静默模式，仅输出错误")
    
    args = parser.parse_args()
    
    # 读取响应
    if args.file:
        try:
            with open(args.response, "r", encoding="utf-8") as f:
                response_str = f.read()
        except FileNotFoundError:
            print(f"❌ 文件不存在: {args.response}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ 读取文件失败: {e}")
            sys.exit(1)
    else:
        response_str = args.response
    
    # 验证
    result = ProtocolValidator.validate(response_str, tool_type=args.type)
    
    # 输出结果
    if args.quiet:
        if not result.passed:
            for error in result.errors:
                print(error)
            sys.exit(1)
    else:
        print(result)
        
        # 美化输出响应（如果验证失败）
        if not result.passed:
            print("\n原始响应:")
            try:
                parsed = json.loads(response_str)
                print(json.dumps(parsed, ensure_ascii=False, indent=2))
            except:
                print(response_str[:500] + "..." if len(response_str) > 500 else response_str)
    
    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()
