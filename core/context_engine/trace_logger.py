"""Trace Logger - 记录 Agent 完整执行轨迹

遵循《TraceLogging设计文档.md》，记录完整 ReAct 推理过程。

职责：
- 记录单个会话的所有事件到 JSONL 文件
- 生成 session_summary
- 线程安全的文件写入
"""

import json
import logging
import os
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.context_engine.trace_sanitizer import TraceSanitizer

logger = logging.getLogger(__name__)


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
        self._current_run = None
        self._timeline_started = False
        self._system_messages_logged = False
        self._md_step_open = False
        self._sanitizer = TraceSanitizer(
            enable=os.environ.get("TRACE_SANITIZE", "true").lower() == "true"
        )
        
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
            logger.warning("TraceLogger init failed: %s", e)
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
            safe_payload = self._sanitizer.sanitize(payload)
            # 构建事件对象
            event_obj = {
                "ts": datetime.utcnow().isoformat() + "Z",
                "session_id": self.session_id,
                "step": step,
                "event": event,
                "payload": safe_payload,
            }
            
            # 写入文件
            self._write_line(event_obj)
            
            # 更新统计
            self._update_stats(event, payload, step)
            
        except Exception as e:
            logger.warning("TraceLogger log_event failed: %s", e)

    def log_system_messages(self, messages: list[dict[str, Any]]):
        """
        记录 system messages（仅一次）
        
        Args:
            messages: system messages 列表
        """
        if not self.enabled:
            return
        if self._system_messages_logged:
            return
        self._system_messages_logged = True
        self.log_event("system_messages", {"messages": messages}, step=0)
    
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
                self._close_step_block()
                self._md_handle.close()
                self._md_handle = None
            
            logger.info("Trace saved to %s", self._filepath)
            
        except Exception as e:
            logger.warning("TraceLogger finalize failed: %s", e)
    
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

    def _ensure_timeline_header(self):
        if not self._md_handle:
            return
        if not self._timeline_started:
            self._md_handle.write("\n## Timeline\n\n")
            self._timeline_started = True

    def _close_step_block(self):
        if self._md_handle and self._md_step_open:
            self._md_handle.write("\n</details>\n")
            self._md_step_open = False

    def _write_md_event(self, event_obj: Dict[str, Any]):
        if not self._md_handle:
            return
        event = event_obj.get("event")
        step = event_obj.get("step", 0)
        payload = event_obj.get("payload", {}) or {}
        ts = event_obj.get("ts", "")

        lines = []

        if event == "system_messages":
            messages = payload.get("messages", []) or []
            lines.append("## System Messages (logged once)\n")
            if not messages:
                lines.append("_No system messages_\n")
            else:
                for idx, msg in enumerate(messages, 1):
                    role = msg.get("role", "system")
                    content = msg.get("content", "")
                    lines.append(f"### System Message {idx}\n")
                    lines.append(f"Role: `{role}`\n\n")
                    lines.append("```text\n")
                    lines.append(f"{content}\n")
                    lines.append("```\n")
            if lines:
                self._md_handle.write("".join(lines))
                self._md_handle.flush()
            return

        if event == "run_start":
            run_id = payload.get("run_id")
            user_text = payload.get("input", "")
            processed = payload.get("processed")
            self._current_run = run_id
            self._current_step = None
            self._close_step_block()
            lines.append(f"\n## Run {run_id}\n")
            if ts:
                lines.append(f"*Start: {ts}*\n\n")
            if user_text:
                lines.append("### 🧑 User Input\n")
                lines.append("```text\n")
                lines.append(f"{user_text}\n")
                lines.append("```\n")
            if processed and processed != user_text:
                lines.append("\n*Processed (with @file expansion):*\n")
                lines.append("```text\n")
                lines.append(f"{processed}\n")
                lines.append("```\n")
            if lines:
                self._md_handle.write("".join(lines))
                self._md_handle.flush()
            return

        if event == "run_end":
            run_id = payload.get("run_id")
            final = payload.get("final", "")
            self._close_step_block()
            lines.append(f"\n### ✅ Run End (run={run_id})\n")
            if ts:
                lines.append(f"*End: {ts}*\n\n")
            if final:
                lines.append("```text\n")
                lines.append(f"{final}\n")
                lines.append("```\n")
            if lines:
                self._md_handle.write("".join(lines))
                self._md_handle.flush()
            return

        self._ensure_timeline_header()

        if step and step != self._current_step:
            self._close_step_block()
            self._current_step = step
            lines.append(f"\n<details>\n<summary>Step {step}</summary>\n\n")
            self._md_step_open = True

        if event == "user_input":
            lines.append("#### 🧑 User Input\n")
            lines.append(f"{payload.get('text', '')}\n")
            processed = payload.get('processed')
            if processed and processed != payload.get('text'):
                lines.append("\n*Processed (with @file expansion):*\n")
                lines.append(f"```\n{processed}\n```\n")

        elif event == "history_compression_triggered":
            lines.append("#### 📦 History Compression Triggered\n")
            lines.append(f"- Estimated tokens: {payload.get('estimated_tokens', 0)}\n")
            lines.append(f"- Threshold: {payload.get('threshold', 0)}\n")
            lines.append(f"- Current messages: {payload.get('message_count', 0)}\n\n")

        elif event == "history_compression_plan":
            lines.append("#### 🧭 History Compression Plan\n")
            lines.append(f"- Rounds: {payload.get('rounds_count', 0)}\n")
            lines.append(f"- Min retain rounds: {payload.get('min_retain_rounds', 0)}\n")
            lines.append(f"- Retain start round: {payload.get('retain_start_round')}\n")
            lines.append(f"- Retain start idx: {payload.get('retain_start_idx')}\n")
            lines.append(f"- Messages before: {payload.get('messages_before')}\n\n")

        elif event == "history_compression_messages":
            lines.append("#### 📄 History Compression Messages\n")
            lines.append(f"- Messages to compress: {payload.get('messages_to_compress', 0)}\n")
            lines.append(f"- Existing summaries: {payload.get('existing_summaries', 0)}\n\n")

        elif event == "history_compression_summary":
            lines.append("#### 📝 History Compression Summary\n")
            lines.append(f"- Summary generated: {payload.get('summary_generated', False)}\n")
            lines.append(f"- Summary length: {payload.get('summary_len', 0)}\n\n")
            summary_text = payload.get("summary_text", "")
            if summary_text:
                lines.append("Summary (full):\n")
                lines.append("```text\n")
                lines.append(f"{summary_text}\n")
                lines.append("```\n")

        elif event == "history_compression_rebuilt":
            lines.append("#### 🧱 History Compression Rebuilt\n")
            lines.append(f"- Messages after: {payload.get('messages_after', 0)}\n\n")

        elif event == "history_compression_context":
            lines.append("#### 🧩 History Compression Context (post)\n")
            lines.append(f"- Message count: {payload.get('message_count', 0)}\n\n")
            messages = payload.get("messages", []) or []
            for idx, msg in enumerate(messages, 1):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                lines.append(f"##### Message {idx} ({role})\n")
                lines.append("```text\n")
                lines.append(f"{content}\n")
                lines.append("```\n")

        elif event == "history_compression_final_context":
            lines.append("#### 🧩 Final Context After Compression (system + history)\n")
            lines.append(f"- Message count: {payload.get('message_count', 0)}\n\n")
            messages = payload.get("messages", []) or []
            for idx, msg in enumerate(messages, 1):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                lines.append(f"##### Message {idx} ({role})\n")
                lines.append("```text\n")
                lines.append(f"{content}\n")
                lines.append("```\n")

        elif event == "history_compression_skipped":
            lines.append("#### ⏭️ History Compression Skipped\n")
            reason = payload.get("reason", "unknown")
            lines.append(f"- Reason: {reason}\n")
            lines.append(f"- Rounds: {payload.get('rounds_count', 0)}\n")
            lines.append(f"- Min retain rounds: {payload.get('min_retain_rounds', 0)}\n\n")

        elif event == "history_compression_completed":
            lines.append("#### ✅ History Compression Completed\n")
            lines.append(f"- Rounds before: {payload.get('rounds_before', 0)}\n")
            lines.append(f"- Rounds after: {payload.get('rounds_after', 0)}\n")
            lines.append(f"- Messages compressed: {payload.get('messages_compressed', 0)}\n")
            if payload.get('summary_generated'):
                lines.append(f"- Summary generated: Yes\n\n")
            else:
                lines.append(f"- Summary generated: No (fallback to truncation)\n\n")

        elif event == "message_written":
            role = payload.get('role', 'unknown')
            content = payload.get('content', '')
            metadata = payload.get('metadata', {})
            
            if role == "user":
                lines.append("#### 💬 Message Written: User\n")
                lines.append(f"```\n{self._truncate(content, 500)}\n```\n")
            elif role == "assistant":
                lines.append("#### 🤖 Message Written: Assistant\n")
                action_type = metadata.get('action_type', 'unknown')
                lines.append(f"Type: `{action_type}`\n\n")
                lines.append(f"```\n{self._truncate(content, 500)}\n```\n")
            elif role == "tool":
                tool_name = metadata.get('tool_name', 'unknown')
                lines.append(f"#### 🔧 Message Written: Tool ({tool_name})\n")
                lines.append(f"```json\n{self._truncate(content, 300)}\n```\n")
            elif role == "system":
                lines.append("#### 🧩 Message Written: System\n")
                lines.append(f"```\n{self._truncate(content, 500)}\n```\n")
            elif role == "summary":
                lines.append("#### 📝 Message Written: Summary\n")
                lines.append(f"```\n{self._truncate(content, 500)}\n```\n")

        elif event == "model_output":
            raw = payload.get("raw", "")
            usage = payload.get("usage")
            tool_calls = payload.get("tool_calls") or []
            lines.append("#### 🧠 Model Output\n")
            if usage:
                lines.append(f"*Tokens: {usage.get('prompt_tokens', 0)} → {usage.get('completion_tokens', 0)} = {usage.get('total_tokens', 0)}*\n\n")
            if tool_calls:
                lines.append("Tool calls:\n")
                try:
                    calls_text = json.dumps(tool_calls, ensure_ascii=False)
                except Exception:
                    calls_text = str(tool_calls)
                lines.append("```json\n")
                lines.append(f"{self._truncate(calls_text, 800)}\n")
                lines.append("```\n")
            if raw:
                lines.append("Content (truncated):\n")
                lines.append("```text\n")
                lines.append(f"{self._truncate(raw, 600)}\n")
                lines.append("```\n")
            raw_response = payload.get("raw_response")
            if raw_response is not None and os.environ.get("TRACE_MD_INCLUDE_RAW_RESPONSE", "false").lower() == "true":
                try:
                    raw_text = json.dumps(raw_response, ensure_ascii=False, indent=2)
                except Exception:
                    raw_text = str(raw_response)
                lines.append("Raw response (JSON):\n")
                lines.append("```json\n")
                lines.append(f"{raw_text}\n")
                lines.append("```\n")

        elif event == "parsed_action":
            thought = payload.get("thought", "")
            action = payload.get("action", "")
            args = payload.get("args")
            if thought:
                lines.append("#### 💭 Thought\n")
                lines.append("```text\n")
                lines.append(f"{thought}\n")
                lines.append("```\n")
            if action:
                lines.append("#### ⚡ Action\n")
                lines.append("```text\n")
                lines.append(f"{action}\n")
                lines.append("```\n")
            if args is not None:
                try:
                    args_text = json.dumps(args, ensure_ascii=False)
                except Exception:
                    args_text = str(args)
                lines.append("#### 📋 Args\n")
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
            lines.append("#### 🛠️ Tool Call\n")
            lines.append("```text\n")
            lines.append(f"{tool} {args_text}\n")
            lines.append("```\n")

        elif event == "tool_result":
            tool = payload.get("tool", "")
            result = payload.get("result", {})
            status = result.get("status")
            text = result.get("text", "")
            data = result.get("data", None)
            lines.append("#### 👁️ Observation\n")
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
            lines.append("#### ❌ Error\n")
            try:
                err_text = json.dumps(payload, ensure_ascii=False)
            except Exception:
                err_text = str(payload)
            lines.append("```json\n")
            lines.append(f"{err_text}\n")
            lines.append("```\n")

        elif event == "finish":
            lines.append("#### ✅ Finish\n")
            final = payload.get("final", "")
            lines.append("```text\n")
            lines.append(f"{final}\n")
            lines.append("```\n")

        elif event == "session_summary":
            lines.append("#### 📊 Session Summary\n")
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
