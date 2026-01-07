"""Trace Logger - 记录 Agent 完整执行轨迹

遵循《TraceLogging设计文档.md》，记录完整 ReAct 推理过程。

职责：
- 记录单个会话的所有事件到 JSONL 文件
- 生成 session_summary
- 线程安全的文件写入
"""

import json
import os
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class TraceLogger:
    """
    会话级轨迹记录器
    
    使用方式：
    1. 创建实例：logger = TraceLogger(session_id, trace_dir)
    2. 记录事件：logger.log_event("model_output", {...})
    3. 结束会话：logger.finalize()
    """
    
    def __init__(
        self,
        session_id: str,
        trace_dir: Path,
        enabled: bool = True,
    ):
        """
        初始化 TraceLogger
        
        Args:
            session_id: 会话唯一标识（格式：s-YYYYMMDD-HHMMSS-{随机}）
            trace_dir: 轨迹文件目录（如 memory/traces）
            enabled: 是否启用记录（环境变量控制）
        """
        self.session_id = session_id
        self.trace_dir = Path(trace_dir)
        self.enabled = enabled
        
        # 统计数据（用于 session_summary）
        self._total_steps = 0
        self._tools_used = 0
        self._total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        
        # 线程锁（保证文件写入安全）
        self._lock = threading.Lock()
        
        # 文件路径
        self._filepath: Optional[Path] = None
        self._file_handle = None
        self._md_filepath: Optional[Path] = None
        self._md_handle = None
        self._current_step = None
        
        # 初始化文件
        if self.enabled:
            self._init_file()
    
    def _init_file(self):
        """初始化 JSONL 文件"""
        try:
            # 创建目录
            self.trace_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成文件名（使用 session_id，避免同秒冲突）
            # session_id 格式：s-20260103-201533-a3f2
            filename = f"trace-{self.session_id}.jsonl"
            self._filepath = self.trace_dir / filename
            
            # 打开文件（追加模式）
            self._file_handle = open(self._filepath, "a", encoding="utf-8")

            # Markdown 人类可读审计文件
            md_filename = f"trace-{self.session_id}.md"
            self._md_filepath = self.trace_dir / md_filename
            self._md_handle = open(self._md_filepath, "a", encoding="utf-8")
            self._write_md_header()
            
        except Exception as e:
            print(f"⚠️ TraceLogger init failed: {e}")
            self.enabled = False
    
    def log_event(self, event: str, payload: Dict[str, Any], step: int = 0):
        """
        记录单个事件
        
        Args:
            event: 事件类型（user_input/model_output/tool_call 等）
            payload: 事件数据体
            step: ReAct 循环的 step 序号（0 表示非步骤事件）
        """
        if not self.enabled:
            return
        
        try:
            # 构建事件对象
            event_obj = {
                "ts": datetime.utcnow().isoformat() + "Z",
                "session_id": self.session_id,
                "step": step,
                "event": event,
                "payload": payload,
            }
            
            # 写入文件
            self._write_line(event_obj)
            
            # 更新统计
            self._update_stats(event, payload, step)
            
        except Exception as e:
            print(f"⚠️ TraceLogger log_event failed: {e}")
    
    def finalize(self):
        """
        写入 session_summary 并关闭文件
        
        自动统计：
        - 总步骤数
        - 工具调用次数
        - 累计 token 用量
        """
        if not self.enabled:
            return
        
        try:
            # 写入 session_summary
            summary_payload = {
                "steps": self._total_steps,
                "tools_used": self._tools_used,
                "total_usage": self._total_usage,
            }
            
            self.log_event("session_summary", summary_payload, step=0)
            
            # 关闭文件
            if self._file_handle:
                self._file_handle.close()
                self._file_handle = None
            if self._md_handle:
                self._md_handle.close()
                self._md_handle = None
            
            print(f"✅ Trace saved to {self._filepath}")
            
        except Exception as e:
            print(f"⚠️ TraceLogger finalize failed: {e}")
    
    def _write_line(self, event_obj: Dict[str, Any]):
        """内部方法：追加写入一行 JSON（加锁保证线程安全）"""
        with self._lock:
            if self._file_handle:
                line = json.dumps(event_obj, ensure_ascii=False)
                self._file_handle.write(line + "\n")
                self._file_handle.flush()
            if self._md_handle:
                self._write_md_event(event_obj)
    
    def _update_stats(self, event: str, payload: Dict[str, Any], step: int):
        """更新统计数据"""
        # 更新步骤数
        if step > self._total_steps:
            self._total_steps = step
        
        # 更新工具调用次数
        if event == "tool_call":
            self._tools_used += 1
        
        # 更新 token 用量
        if event == "model_output" and payload.get("usage"):
            usage = payload["usage"]
            self._total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            self._total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            self._total_usage["total_tokens"] += usage.get("total_tokens", 0)

    def _write_md_header(self):
        if not self._md_handle:
            return
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        self._md_handle.write(f"# Trace Session: {self.session_id}\n")
        self._md_handle.write(f"Started: {now}\n\n")
        self._md_handle.flush()

    def _truncate(self, text: str, limit: int = 300) -> str:
        if text is None:
            return ""
        s = str(text)
        if len(s) <= limit:
            return s
        return s[:limit] + "...(truncated)"

    def _write_md_event(self, event_obj: Dict[str, Any]):
        if not self._md_handle:
            return
        event = event_obj.get("event")
        step = event_obj.get("step", 0)
        payload = event_obj.get("payload", {}) or {}

        lines = []
        if step and step != self._current_step:
            self._current_step = step
            lines.append(f"\n## Step {step}\n")

        if event == "user_input":
            lines.append("## User Input\n")
            lines.append(f"{payload.get('text', '')}\n")

        elif event == "model_output":
            raw = payload.get("raw", "")
            lines.append("### Model Output (raw)\n")
            lines.append("```text\n")
            lines.append(f"{raw}\n")
            lines.append("```\n")

        elif event == "parsed_action":
            thought = payload.get("thought", "")
            action = payload.get("action", "")
            args = payload.get("args")
            if thought:
                lines.append("### Thought\n")
                lines.append("```text\n")
                lines.append(f"{thought}\n")
                lines.append("```\n")
            if action:
                lines.append("### Action\n")
                lines.append("```text\n")
                lines.append(f"{action}\n")
                lines.append("```\n")
            if args is not None:
                try:
                    args_text = json.dumps(args, ensure_ascii=False)
                except Exception:
                    args_text = str(args)
                lines.append("### Args\n")
                lines.append("```json\n")
                lines.append(f"{args_text}\n")
                lines.append("```\n")

        elif event == "tool_call":
            tool = payload.get("tool", "")
            args = payload.get("args", {})
            try:
                args_text = json.dumps(args, ensure_ascii=False)
            except Exception:
                args_text = str(args)
            lines.append("### Tool Call\n")
            lines.append("```text\n")
            lines.append(f"{tool} {args_text}\n")
            lines.append("```\n")

        elif event == "tool_result":
            tool = payload.get("tool", "")
            result = payload.get("result", {})
            status = result.get("status")
            text = result.get("text", "")
            data = result.get("data", None)
            lines.append("### Observation\n")
            lines.append(f"Tool: {tool}\n\n")
            if status:
                lines.append(f"Status: {status}\n\n")
            if text:
                lines.append("Text:\n")
                lines.append("```text\n")
                lines.append(f"{text}\n")
                lines.append("```\n")
            if data is not None:
                try:
                    data_text = json.dumps(data, ensure_ascii=False)
                except Exception:
                    data_text = str(data)
                data_text = self._truncate(data_text, 300)
                lines.append("Data (truncated):\n")
                lines.append("```json\n")
                lines.append(f"{data_text}\n")
                lines.append("```\n")

        elif event == "error":
            lines.append("### Error\n")
            try:
                err_text = json.dumps(payload, ensure_ascii=False)
            except Exception:
                err_text = str(payload)
            lines.append("```json\n")
            lines.append(f"{err_text}\n")
            lines.append("```\n")

        elif event == "finish":
            lines.append("## Finish\n")
            final = payload.get("final", "")
            lines.append("```text\n")
            lines.append(f"{final}\n")
            lines.append("```\n")

        elif event == "session_summary":
            lines.append("## Session Summary\n")
            try:
                summary_text = json.dumps(payload, ensure_ascii=False, indent=2)
            except Exception:
                summary_text = str(payload)
            lines.append("```json\n")
            lines.append(f"{summary_text}\n")
            lines.append("```\n")

        if lines:
            self._md_handle.write("".join(lines))
            self._md_handle.flush()
    
    def __enter__(self):
        """支持 with 语句"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句（自动 finalize）"""
        self.finalize()


def create_trace_logger(trace_dir: str = "memory/traces") -> TraceLogger:
    """
    工厂函数：创建 TraceLogger 实例
    
    根据环境变量控制是否启用：
    - TRACE_ENABLED=true|false（默认 false）
    - TRACE_DIR=memory/traces（默认该路径）
    
    Args:
        trace_dir: 轨迹文件目录（可被环境变量覆盖）
    
    Returns:
        TraceLogger 实例
    """
    # 读取环境变量
    enabled = os.environ.get("TRACE_ENABLED", "true").lower() == "true"
    trace_dir_env = os.environ.get("TRACE_DIR", trace_dir)
    
    # 生成 session_id（格式：s-YYYYMMDD-HHMMSS-{4位随机}）
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    random_suffix = os.urandom(2).hex()  # 4 位十六进制
    session_id = f"s-{timestamp}-{random_suffix}"
    
    return TraceLogger(
        session_id=session_id,
        trace_dir=Path(trace_dir_env),
        enabled=enabled,
    )
