"""Shell 命令执行工具 (Bash)

遵循《通用工具响应协议》，返回标准化结构。
在项目根目录沙箱内执行 Shell 命令，支持命令串联与受限 cd。
"""

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from prompts.tools_prompts.bash_prompt import bash_prompt
from ..base import Tool, ToolParameter, ToolStatus, ErrorCode


class BashTool(Tool):
    """Shell 命令执行工具，支持命令串联与沙箱限制"""

    # 默认超时时间（毫秒）
    DEFAULT_TIMEOUT_MS = 120000
    
    # 最大超时时间（毫秒）
    MAX_TIMEOUT_MS = 600000

    # 交互式命令黑名单（直接拒绝）
    INTERACTIVE_COMMANDS: Set[str] = {
        "vim", "vi", "nano", "less", "more", "top", "htop",
        "watch", "tmux", "screen", "ssh", "scp", "sftp", "ftp",
    }
    
    # 破坏性系统命令黑名单
    DESTRUCTIVE_COMMANDS: Set[str] = {
        "mkfs", "fdisk", "dd", "shutdown", "reboot", "poweroff", "halt",
    }
    
    # 权限提升命令黑名单
    PRIVILEGE_COMMANDS: Set[str] = {
        "sudo", "su", "doas",
    }
    
    # 读/搜/列类 Shell 命令黑名单（应使用相应工具）
    READ_SEARCH_COMMANDS: Set[str] = {
        "ls", "cat", "head", "tail", "grep", "find", "rg",
    }

    def __init__(
        self,
        name: str = "Bash",
        project_root: Optional[Path] = None,
        working_dir: Optional[Path] = None,
    ):
        """
        初始化 Shell 命令执行工具

        Args:
            name: 工具名称，默认为 "Bash"
            project_root: 项目根目录，用于沙箱限制
            working_dir: 工作目录，用于解析相对路径
        """
        if project_root is None:
            raise ValueError("project_root must be provided by the framework")
        
        super().__init__(
            name=name,
            description=bash_prompt,
            project_root=project_root,
            working_dir=working_dir if working_dir else project_root,
        )
        
        # 保存项目根目录
        self._root = self._project_root
        
        # 是否允许网络工具（默认禁用）
        self._allow_network = os.environ.get("BASH_ALLOW_NETWORK", "false").lower() == "true"

    def run(self, parameters: Dict[str, Any]) -> str:
        """
        执行 Shell 命令

        Args:
            parameters: 包含以下键的字典：
                - command: 要执行的命令（必填）
                - directory: 工作目录（相对项目根目录，默认为 "."）
                - timeout_ms: 超时时间（毫秒，默认 120000，最大 600000）

        Returns:
            JSON 格式的响应字符串（遵循《通用工具响应协议》）
        """
        start_time = time.monotonic()
        params_input = dict(parameters)
        
        # 提取参数
        command = parameters.get("command")
        directory = parameters.get("directory", ".")
        timeout_ms = parameters.get("timeout_ms", self.DEFAULT_TIMEOUT_MS)

        # =====================================================================
        # 参数校验
        # =====================================================================
        
        # command 必填
        if not command:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Missing required parameter 'command'.",
                params_input=params_input,
            )
        
        # command 必须是字符串
        if not isinstance(command, str):
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="Parameter 'command' must be a string.",
                params_input=params_input,
            )
        
        # timeout_ms 校验
        if not isinstance(timeout_ms, int) or timeout_ms < 1 or timeout_ms > self.MAX_TIMEOUT_MS:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message=f"timeout_ms must be an integer between 1 and {self.MAX_TIMEOUT_MS}.",
                params_input=params_input,
            )

        # =====================================================================
        # 安全检查：命令黑名单
        # =====================================================================
        
        safety_result = self._check_command_safety(command)
        if safety_result is not None:
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message=safety_result,
                params_input=params_input,
            )

        # =====================================================================
        # 目录解析与沙箱校验
        # =====================================================================
        
        try:
            # 解析目录路径
            dir_path = Path(directory)
            if dir_path.is_absolute():
                target_dir = dir_path.resolve()
            else:
                target_dir = (self._root / dir_path).resolve()
            
            # 沙箱检查
            target_dir.relative_to(self._root)
            directory_resolved = str(target_dir.relative_to(self._root))
            if not directory_resolved:
                directory_resolved = "."
        except ValueError:
            return self.create_error_response(
                error_code=ErrorCode.ACCESS_DENIED,
                message="Access denied. Path must be within project root.",
                params_input=params_input,
            )
        except OSError as e:
            return self.create_error_response(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Path resolution failed: {e}",
                params_input=params_input,
            )
        
        # 检查目录是否存在
        if not target_dir.exists():
            return self.create_error_response(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Directory '{directory}' does not exist.",
                params_input=params_input,
            )
        
        # 检查是否为目录
        if not target_dir.is_dir():
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message=f"'{directory}' is not a directory.",
                params_input=params_input,
            )

        # =====================================================================
        # 检查命令中的 cd 路径
        # =====================================================================
        
        cd_check_result = self._check_cd_paths(command, target_dir)
        if cd_check_result is not None:
            return self.create_error_response(
                error_code=ErrorCode.ACCESS_DENIED,
                message=cd_check_result,
                params_input=params_input,
            )

        # =====================================================================
        # 执行命令
        # =====================================================================
        
        # 设置环境变量
        env = os.environ.copy()
        env["MYCODEAGENT"] = "1"
        
        # 转换超时时间为秒
        timeout_sec = timeout_ms / 1000.0
        
        stdout = ""
        stderr = ""
        exit_code = None
        signal_name = None
        timed_out = False
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(target_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode
        except subprocess.TimeoutExpired as e:
            timed_out = True
            stdout = e.stdout or ""
            stderr = e.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
        except PermissionError:
            time_ms = int((time.monotonic() - start_time) * 1000)
            return self.create_error_response(
                error_code=ErrorCode.PERMISSION_DENIED,
                message="Permission denied executing command.",
                params_input=params_input,
                time_ms=time_ms,
            )
        except Exception as e:
            time_ms = int((time.monotonic() - start_time) * 1000)
            return self.create_error_response(
                error_code=ErrorCode.EXECUTION_ERROR,
                message=f"Command failed: {e}",
                params_input=params_input,
                time_ms=time_ms,
            )

        # =====================================================================
        # 构建响应
        # =====================================================================
        
        time_ms = int((time.monotonic() - start_time) * 1000)
        
        # 构建 data 字段
        data: Dict[str, Any] = {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "signal": signal_name,
            "truncated": False,  # MVP 阶段不截断
            "command": command,
            "directory": directory_resolved,
        }
        
        # 构建 stats 字段
        extra_stats = {
            "stdout_bytes": len(stdout.encode("utf-8")),
            "stderr_bytes": len(stderr.encode("utf-8")),
        }
        
        # 构建 context 字段
        extra_context = {
            "directory_resolved": directory_resolved,
            "cwd": directory_resolved,
        }
        
        # 构建 text 字段
        if timed_out:
            if stdout or stderr:
                # 超时但有部分输出 -> partial
                text_lines = [
                    f"Command timed out: {command}",
                    f"(Timeout after {timeout_ms}ms)",
                ]
                if stdout:
                    text_lines.append(f"\n--- STDOUT ({len(stdout.encode('utf-8'))} bytes) ---")
                    text_lines.append(stdout[:1000] + ("..." if len(stdout) > 1000 else ""))
                if stderr:
                    text_lines.append(f"\n--- STDERR ({len(stderr.encode('utf-8'))} bytes) ---")
                    text_lines.append(stderr[:1000] + ("..." if len(stderr) > 1000 else ""))
                text = "\n".join(text_lines)
                
                return self.create_partial_response(
                    data=data,
                    text=text,
                    params_input=params_input,
                    time_ms=time_ms,
                    extra_stats=extra_stats,
                    extra_context=extra_context,
                )
            else:
                # 超时且无输出 -> error
                return self.create_error_response(
                    error_code=ErrorCode.TIMEOUT,
                    message="Command timed out with no output.",
                    params_input=params_input,
                    time_ms=time_ms,
                )
        
        # 判断状态
        if exit_code == 0:
            # 成功
            text_lines = [
                f"Command succeeded: {command}",
                f"(Exit code 0. Took {time_ms}ms)",
            ]
            if stdout:
                text_lines.append(f"\n--- STDOUT ({len(stdout.encode('utf-8'))} bytes) ---")
                text_lines.append(stdout[:2000] + ("..." if len(stdout) > 2000 else ""))
            if stderr:
                text_lines.append(f"\n--- STDERR ({len(stderr.encode('utf-8'))} bytes) ---")
                text_lines.append(stderr[:1000] + ("..." if len(stderr) > 1000 else ""))
            text = "\n".join(text_lines)
            
            return self.create_success_response(
                data=data,
                text=text,
                params_input=params_input,
                time_ms=time_ms,
                extra_stats=extra_stats,
                extra_context=extra_context,
            )
        else:
            # 非零退出码 -> partial
            text_lines = [
                f"Command failed: {command}",
                f"(Exit code {exit_code}. Took {time_ms}ms)",
            ]
            if stdout:
                text_lines.append(f"\n--- STDOUT ({len(stdout.encode('utf-8'))} bytes) ---")
                text_lines.append(stdout[:2000] + ("..." if len(stdout) > 2000 else ""))
            if stderr:
                text_lines.append(f"\n--- STDERR ({len(stderr.encode('utf-8'))} bytes) ---")
                text_lines.append(stderr[:2000] + ("..." if len(stderr) > 2000 else ""))
            text = "\n".join(text_lines)
            
            return self.create_partial_response(
                data=data,
                text=text,
                params_input=params_input,
                time_ms=time_ms,
                extra_stats=extra_stats,
                extra_context=extra_context,
            )

    def _check_command_safety(self, command: str) -> Optional[str]:
        """
        检查命令安全性
        
        Args:
            command: 要检查的命令
            
        Returns:
            如果命令不安全，返回错误消息；否则返回 None
        """
        # 提取命令中的所有"词"（简单分词）
        # 注意：这是一个简化的检查，可能无法捕获所有变体
        # Strip quoted strings to reduce false positives (e.g. echo "ls")
        command_for_scan = re.sub(r'(["\']).*?\1', ' ', command)
        words = re.findall(r'\b\w+\b', command_for_scan.lower())
        
        # 检查交互式命令
        for word in words:
            if word in self.INTERACTIVE_COMMANDS:
                return f"Command blocked by safety rules. Interactive command '{word}' is not allowed."
        
        # 检查交互式 git 命令
        if "git" in words:
            if "rebase" in words and ("-i" in command or "--interactive" in command):
                return "Command blocked by safety rules. Interactive 'git rebase -i' is not allowed."
            if "add" in words and ("-i" in command or "--interactive" in command):
                return "Command blocked by safety rules. Interactive 'git add -i' is not allowed."
        
        # 检查破坏性命令
        for word in words:
            if word in self.DESTRUCTIVE_COMMANDS:
                return f"Command blocked by safety rules. Destructive command '{word}' is not allowed."
        
        # 检查权限提升命令
        for word in words:
            if word in self.PRIVILEGE_COMMANDS:
                return f"Command blocked by safety rules. Privilege escalation command '{word}' is not allowed."
        
        # 检查危险的 rm 命令
        if "rm" in words:
            # 检查 rm -rf / 或 rm -rf /*
            if re.search(r'\brm\s+(-[rf]+\s+)*(/|/\*)\s*$', command):
                return "Command blocked by safety rules. Destructive 'rm -rf /' is not allowed."
            if re.search(r'\brm\s+.*-[rf]*\s+.*(/|/\*)', command):
                # 更宽松的检查
                if "/ " in command or "/*" in command:
                    return "Command blocked by safety rules. Destructive 'rm' on root is not allowed."
        
        # 检查远程脚本执行
        remote_exec_patterns = [
            r'\bcurl\s+.*\|\s*bash',
            r'\bwget\s+.*\|\s*bash',
            r'\bbash\s+<\s*\(\s*curl',
            r'\bbash\s+<\s*\(\s*wget',
            r'\bcurl\s+.*\|\s*sh',
            r'\bwget\s+.*\|\s*sh',
        ]
        for pattern in remote_exec_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return "Command blocked by safety rules. Remote script execution is not allowed."
        
        # 检查网络工具（默认禁用）
        if not self._allow_network:
            if "curl" in words or "wget" in words:
                return "Command blocked by safety rules. Network tools (curl/wget) are disabled. Set BASH_ALLOW_NETWORK=true to enable."
        
        # 检查读/搜/列类命令
        for word in words:
            if word in self.READ_SEARCH_COMMANDS:
                tool_suggestion = {
                    "ls": "LS",
                    "cat": "Read",
                    "head": "Read",
                    "tail": "Read",
                    "grep": "Grep",
                    "find": "Glob",
                    "rg": "Grep",
                }.get(word, "the appropriate tool")
                return f"Command blocked by safety rules. Use {tool_suggestion} instead of '{word}'."
        
        return None

    def _check_cd_paths(self, command: str, base_dir: Path) -> Optional[str]:
        """
        检查命令中的 cd 路径是否在项目根目录内
        
        Args:
            command: 要检查的命令
            base_dir: 当前工作目录
            
        Returns:
            如果 cd 路径越界，返回错误消息；否则返回 None
        """
        # 匹配 cd 命令及其目标路径
        cd_patterns = [
            r'\bcd\s+([^\s;&|]+)',  # cd path
            r'\bcd\s+"([^"]+)"',     # cd "path with spaces"
            r"\bcd\s+'([^']+)'",     # cd 'path with spaces'
        ]
        
        for pattern in cd_patterns:
            for match in re.finditer(pattern, command):
                cd_target = match.group(1)
                
                # 解析 cd 目标路径
                try:
                    if cd_target.startswith("/"):
                        # 绝对路径
                        resolved = Path(cd_target).resolve()
                    else:
                        # 相对路径（相对于当前工作目录）
                        resolved = (base_dir / cd_target).resolve()
                    
                    # 检查是否在项目根目录内
                    resolved.relative_to(self._root)
                except ValueError:
                    return f"Access denied. 'cd {cd_target}' would go outside project root."
                except OSError:
                    # 路径解析失败，继续检查其他 cd
                    pass
        
        return None

    def get_parameters(self) -> List[ToolParameter]:
        """
        获取工具参数定义
        
        Returns:
            工具参数列表
        """
        return [
            ToolParameter(
                name="command",
                type="string",
                description="The shell command to execute. Command chaining (&&, ||, ;) is allowed.",
                required=True,
            ),
            ToolParameter(
                name="directory",
                type="string",
                description="Working directory relative to project root. Defaults to '.'.",
                required=False,
                default=".",
            ),
            ToolParameter(
                name="timeout_ms",
                type="integer",
                description=f"Execution timeout in milliseconds. Default {self.DEFAULT_TIMEOUT_MS}, max {self.MAX_TIMEOUT_MS}.",
                required=False,
                default=self.DEFAULT_TIMEOUT_MS,
            ),
        ]
