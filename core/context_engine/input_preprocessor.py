"""用户输入预处理器

根据《上下文工程方案》C3 实现 @file 处理功能。

核心功能：
1. 解析用户输入中的 @file 引用
2. 生成 system-reminder 提示模型读取文件
3. 自动去重、限制最多 5 个文件

正则规则（C3）：
- 匹配: @([a-zA-Z0-9/._-]+(?:\\.[a-zA-Z0-9]+)?)
- 仅支持英文路径（设计决策 E4）
"""

import re
from typing import List, Tuple
from dataclasses import dataclass


# @file 匹配正则（仅支持英文路径）
# 使用 (?<![a-zA-Z0-9]) 负向后视确保 @ 前不是字母数字（避免误触发邮件/handle）
FILE_MENTION_PATTERN = re.compile(r"(?<![a-zA-Z0-9])@([a-zA-Z0-9/._-]+(?:\.[a-zA-Z0-9]+)?)")

# 最大引用文件数
MAX_FILE_MENTIONS = 5

# system-reminder 模板
SYSTEM_REMINDER_TEMPLATE = """<system-reminder>
The user mentioned {file_list}.
You MUST read {read_instruction} with the Read tool before answering.
</system-reminder>"""


@dataclass
class PreprocessResult:
    """预处理结果"""
    processed_input: str  # 处理后的用户输入（包含 system-reminder）
    mentioned_files: List[str]  # 提及的文件路径列表（已去重）
    truncated_count: int  # 被截断的文件数（超出 MAX_FILE_MENTIONS 的部分）


def preprocess_input(user_input: str) -> PreprocessResult:
    """
    预处理用户输入，解析 @file 引用并注入 system-reminder
    
    处理流程（C3）：
    1. 正则匹配所有 @file 引用
    2. 按出现顺序去重
    3. 最多保留 5 个文件
    4. 生成 system-reminder 追加到用户输入
    
    Args:
        user_input: 原始用户输入
    
    Returns:
        PreprocessResult 包含处理后的输入和文件列表
    """
    # 匹配所有 @file 引用
    matches = FILE_MENTION_PATTERN.findall(user_input)
    
    if not matches:
        return PreprocessResult(
            processed_input=user_input,
            mentioned_files=[],
            truncated_count=0,
        )
    
    # 按出现顺序去重
    seen = set()
    unique_files: List[str] = []
    for path in matches:
        if path not in seen:
            seen.add(path)
            unique_files.append(path)
    
    # 截断超出部分
    truncated_count = max(0, len(unique_files) - MAX_FILE_MENTIONS)
    files_to_include = unique_files[:MAX_FILE_MENTIONS]
    
    # 生成 system-reminder
    reminder = _build_system_reminder(files_to_include, truncated_count)
    
    # 追加到用户输入
    processed_input = f"{user_input}\n\n{reminder}"
    
    return PreprocessResult(
        processed_input=processed_input,
        mentioned_files=files_to_include,
        truncated_count=truncated_count,
    )


def _build_system_reminder(files: List[str], truncated_count: int) -> str:
    """
    构建 system-reminder
    
    Args:
        files: 要提及的文件列表（最多 5 个）
        truncated_count: 被截断的文件数
    
    Returns:
        system-reminder 字符串
    """
    if not files:
        return ""
    
    # 构建文件列表字符串
    file_mentions = [f"@{f}" for f in files]
    if truncated_count > 0:
        file_mentions.append(f"(and {truncated_count} more…)")
    
    file_list = ", ".join(file_mentions)
    
    # 构建读取指令
    if len(files) == 1:
        read_instruction = "this file"
    else:
        read_instruction = "these files"
    
    return SYSTEM_REMINDER_TEMPLATE.format(
        file_list=file_list,
        read_instruction=read_instruction,
    )


def extract_file_mentions(user_input: str) -> List[str]:
    """
    仅提取文件引用（不做预处理）
    
    用于检查输入中是否有 @file 引用，不注入 system-reminder。
    
    Args:
        user_input: 用户输入
    
    Returns:
        去重后的文件路径列表
    """
    matches = FILE_MENTION_PATTERN.findall(user_input)
    
    seen = set()
    unique_files: List[str] = []
    for path in matches:
        if path not in seen:
            seen.add(path)
            unique_files.append(path)
    
    return unique_files
