"""Trace Logger - 记录 Agent 完整执行轨迹

遵循《TraceLogging设计文档.md》，记录完整 ReAct 推理过程。

职责：
- 记录单个会话的所有事件到 JSONL 文件
- 生成 session_summary
- 线程安全的文件写入
"""

import html
import json
import logging
import os
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.context_engine.trace_sanitizer import TraceSanitizer
from core.env import load_env

load_env()

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
        self._html_filepath: Optional[Path] = None
        self._html_handle = None
        self._current_step = None
        self._current_run = None
        self._timeline_started = False
        self._system_messages_logged = False
        self._html_step_open = False
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

            # HTML 人类可读审计文件
            html_filename = f"trace-{self.session_id}.html"
            self._html_filepath = self.trace_dir / html_filename
            self._html_handle = open(self._html_filepath, "a", encoding="utf-8")
            self._write_html_header()
            
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
            if self._html_handle:
                self._close_step_block()
                self._write_html_footer()
                self._html_handle.close()
                self._html_handle = None
            
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
            if self._html_handle:
                self._write_html_event(event_obj)
    
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

    def _write_html_header(self):
        if not self._html_handle:
            return
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        title = f"Trace Session: {self.session_id}"
        self._html_handle.write("""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
""")
        self._html_handle.write(f"  <title>{html.escape(title)}</title>\n")
        self._html_handle.write("""  <style>
    :root { color-scheme: light; }
    body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px; color: #111; }
    header { margin-bottom: 20px; }
    h1 { font-size: 20px; margin: 0 0 6px; }
    h2 { font-size: 16px; margin: 18px 0 8px; }
    h3 { font-size: 14px; margin: 12px 0 6px; }
    .meta { color: #555; font-size: 12px; }
    .block { border: 1px solid #e4e4e7; border-radius: 8px; padding: 10px 12px; margin: 8px 0; background: #fafafa; }
    .timeline { margin-top: 18px; }
    details { border: 1px solid #e4e4e7; border-radius: 8px; padding: 8px 12px; margin: 10px 0; background: #fff; }
    summary { cursor: pointer; font-weight: 600; }
    pre { background: #0f172a; color: #f8fafc; padding: 10px 12px; border-radius: 8px; overflow-x: auto; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
    .tag { display: inline-block; padding: 2px 6px; border-radius: 999px; font-size: 11px; background: #e2e8f0; color: #334155; }
  </style>
</head>
<body>
""")
        self._html_handle.write(f"<header><h1>{html.escape(title)}</h1><div class=\"meta\">Started: {html.escape(now)}</div></header>\n")
        self._html_handle.write("<main>\n")
        self._html_handle.flush()

    def _truncate(self, text: str, limit: int = 300) -> str:
        if text is None:
            return ""
        s = str(text)
        if len(s) <= limit:
            return s
        return s[:limit] + "...(truncated)"

    def _write_html_footer(self):
        if not self._html_handle:
            return
        if self._timeline_started:
            self._html_handle.write("</section>\n")
        self._html_handle.write("</main>\n</body>\n</html>\n")
        self._html_handle.flush()

    def _ensure_timeline_header(self):
        if not self._html_handle:
            return
        if not self._timeline_started:
            self._html_handle.write("<section class=\"timeline\"><h2>Timeline</h2>\n")
            self._timeline_started = True

    def _close_step_block(self):
        if self._html_handle and self._html_step_open:
            self._html_handle.write("</details>\n")
            self._html_step_open = False

    def _escape_html(self, text: str) -> str:
        return html.escape(text or "")

    def _write_html_event(self, event_obj: Dict[str, Any]):
        if not self._html_handle:
            return
        event = event_obj.get("event")
        step = event_obj.get("step", 0)
        payload = event_obj.get("payload", {}) or {}
        ts = event_obj.get("ts", "")

        lines = []

        if event == "system_messages":
            messages = payload.get("messages", []) or []
            lines.append("<section class=\"block\"><h2>System Messages (logged once)</h2>")
            if not messages:
                lines.append("<div class=\"meta\">No system messages</div>")
            else:
                for idx, msg in enumerate(messages, 1):
                    role = msg.get("role", "system")
                    content = msg.get("content", "")
                    lines.append(f"<h3>System Message {idx}</h3>")
                    lines.append(f"<div class=\"meta\">Role: {self._escape_html(role)}</div>")
                    lines.append("<pre><code>")
                    lines.append(self._escape_html(content))
                    lines.append("</code></pre>")
            lines.append("</section>")
            if lines:
                self._html_handle.write("".join(lines) + "\n")
                self._html_handle.flush()
            return

        if event == "run_start":
            run_id = payload.get("run_id")
            user_text = payload.get("input", "")
            processed = payload.get("processed")
            self._current_run = run_id
            self._current_step = None
            self._close_step_block()
            lines.append(f"<section class=\"block\"><h2>Run {self._escape_html(str(run_id))}</h2>")
            if ts:
                lines.append(f"<div class=\"meta\">Start: {self._escape_html(ts)}</div>")
            if user_text:
                lines.append("<h3>🧑 User Input</h3>")
                lines.append("<pre><code>")
                lines.append(self._escape_html(user_text))
                lines.append("</code></pre>")
            if processed and processed != user_text:
                lines.append("<div class=\"meta\">Processed (with @file expansion):</div>")
                lines.append("<pre><code>")
                lines.append(self._escape_html(processed))
                lines.append("</code></pre>")
            lines.append("</section>")
            if lines:
                self._html_handle.write("".join(lines) + "\n")
                self._html_handle.flush()
            return

        if event == "run_end":
            run_id = payload.get("run_id")
            final = payload.get("final", "")
            self._close_step_block()
            lines.append("<section class=\"block\">")
            lines.append(f"<h3>✅ Run End (run={self._escape_html(str(run_id))})</h3>")
            if ts:
                lines.append(f"<div class=\"meta\">End: {self._escape_html(ts)}</div>")
            if final:
                lines.append("<pre><code>")
                lines.append(self._escape_html(final))
                lines.append("</code></pre>")
            lines.append("</section>")
            if lines:
                self._html_handle.write("".join(lines) + "\n")
                self._html_handle.flush()
            return

        self._ensure_timeline_header()

        if step and step != self._current_step:
            self._close_step_block()
            self._current_step = step
            lines.append(f"<details><summary>Step {step}</summary>")
            self._html_step_open = True

        if event == "user_input":
            lines.append("<div class=\"block\"><h3>🧑 User Input</h3>")
            lines.append(f"<pre><code>{self._escape_html(payload.get('text', ''))}</code></pre>")
            processed = payload.get('processed')
            if processed and processed != payload.get('text'):
                lines.append("<div class=\"meta\">Processed (with @file expansion):</div>")
                lines.append(f"<pre><code>{self._escape_html(processed)}</code></pre>")
            lines.append("</div>")

        elif event == "history_compression_triggered":
            lines.append("<div class=\"block\"><h3>📦 History Compression Triggered</h3>")
            lines.append(f"<div class=\"meta\">Estimated tokens: {payload.get('estimated_tokens', 0)}</div>")
            lines.append(f"<div class=\"meta\">Threshold: {payload.get('threshold', 0)}</div>")
            lines.append(f"<div class=\"meta\">Current messages: {payload.get('message_count', 0)}</div>")
            lines.append("</div>")

        elif event == "history_compression_plan":
            lines.append("<div class=\"block\"><h3>🧭 History Compression Plan</h3>")
            lines.append(f"<div class=\"meta\">Rounds: {payload.get('rounds_count', 0)}</div>")
            lines.append(f"<div class=\"meta\">Min retain rounds: {payload.get('min_retain_rounds', 0)}</div>")
            lines.append(f"<div class=\"meta\">Retain start round: {payload.get('retain_start_round')}</div>")
            lines.append(f"<div class=\"meta\">Retain start idx: {payload.get('retain_start_idx')}</div>")
            lines.append(f"<div class=\"meta\">Messages before: {payload.get('messages_before')}</div>")
            lines.append("</div>")

        elif event == "history_compression_messages":
            lines.append("<div class=\"block\"><h3>📄 History Compression Messages</h3>")
            lines.append(f"<div class=\"meta\">Messages to compress: {payload.get('messages_to_compress', 0)}</div>")
            lines.append(f"<div class=\"meta\">Existing summaries: {payload.get('existing_summaries', 0)}</div>")
            lines.append("</div>")

        elif event == "history_compression_summary":
            lines.append("<div class=\"block\"><h3>📝 History Compression Summary</h3>")
            lines.append(f"<div class=\"meta\">Summary generated: {payload.get('summary_generated', False)}</div>")
            lines.append(f"<div class=\"meta\">Summary length: {payload.get('summary_len', 0)}</div>")
            summary_text = payload.get("summary_text", "")
            if summary_text:
                lines.append("<div class=\"meta\">Summary (full):</div>")
                lines.append("<pre><code>")
                lines.append(self._escape_html(summary_text))
                lines.append("</code></pre>")
            lines.append("</div>")

        elif event == "history_compression_rebuilt":
            lines.append("<div class=\"block\"><h3>🧱 History Compression Rebuilt</h3>")
            lines.append(f"<div class=\"meta\">Messages after: {payload.get('messages_after', 0)}</div>")
            lines.append("</div>")

        elif event == "history_compression_context":
            lines.append("<div class=\"block\"><h3>🧩 History Compression Context (post)</h3>")
            lines.append(f"<div class=\"meta\">Message count: {payload.get('message_count', 0)}</div>")
            messages = payload.get("messages", []) or []
            for idx, msg in enumerate(messages, 1):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                lines.append(f"<h3>Message {idx} ({self._escape_html(role)})</h3>")
                lines.append("<pre><code>")
                lines.append(self._escape_html(content))
                lines.append("</code></pre>")
            lines.append("</div>")

        elif event == "history_compression_final_context":
            lines.append("<div class=\"block\"><h3>🧩 Final Context After Compression (system + history)</h3>")
            lines.append(f"<div class=\"meta\">Message count: {payload.get('message_count', 0)}</div>")
            messages = payload.get("messages", []) or []
            for idx, msg in enumerate(messages, 1):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                lines.append(f"<h3>Message {idx} ({self._escape_html(role)})</h3>")
                lines.append("<pre><code>")
                lines.append(self._escape_html(content))
                lines.append("</code></pre>")
            lines.append("</div>")

        elif event == "history_compression_skipped":
            lines.append("<div class=\"block\"><h3>⏭️ History Compression Skipped</h3>")
            reason = payload.get("reason", "unknown")
            lines.append(f"<div class=\"meta\">Reason: {self._escape_html(str(reason))}</div>")
            lines.append(f"<div class=\"meta\">Rounds: {payload.get('rounds_count', 0)}</div>")
            lines.append(f"<div class=\"meta\">Min retain rounds: {payload.get('min_retain_rounds', 0)}</div>")
            lines.append("</div>")

        elif event == "history_compression_completed":
            lines.append("<div class=\"block\"><h3>✅ History Compression Completed</h3>")
            lines.append(f"<div class=\"meta\">Rounds before: {payload.get('rounds_before', 0)}</div>")
            lines.append(f"<div class=\"meta\">Rounds after: {payload.get('rounds_after', 0)}</div>")
            lines.append(f"<div class=\"meta\">Messages compressed: {payload.get('messages_compressed', 0)}</div>")
            if payload.get('summary_generated'):
                lines.append("<div class=\"meta\">Summary generated: Yes</div>")
            else:
                lines.append("<div class=\"meta\">Summary generated: No (fallback to truncation)</div>")
            lines.append("</div>")

        elif event == "message_written":
            role = payload.get('role', 'unknown')
            content = payload.get('content', '')
            metadata = payload.get('metadata', {})
            
            if role == "user":
                lines.append("<div class=\"block\"><h3>💬 Message Written: User</h3>")
                lines.append(f"<pre><code>{self._escape_html(self._truncate(content, 500))}</code></pre></div>")
            elif role == "assistant":
                lines.append("<div class=\"block\"><h3>🤖 Message Written: Assistant</h3>")
                action_type = metadata.get('action_type', 'unknown')
                lines.append(f"<div class=\"meta\">Type: {self._escape_html(str(action_type))}</div>")
                lines.append(f"<pre><code>{self._escape_html(self._truncate(content, 500))}</code></pre></div>")
            elif role == "tool":
                tool_name = metadata.get('tool_name', 'unknown')
                lines.append(f"<div class=\"block\"><h3>🔧 Message Written: Tool ({self._escape_html(str(tool_name))})</h3>")
                lines.append(f"<pre><code>{self._escape_html(self._truncate(content, 300))}</code></pre></div>")
            elif role == "system":
                lines.append("<div class=\"block\"><h3>🧩 Message Written: System</h3>")
                lines.append(f"<pre><code>{self._escape_html(self._truncate(content, 500))}</code></pre></div>")
            elif role == "summary":
                lines.append("<div class=\"block\"><h3>📝 Message Written: Summary</h3>")
                lines.append(f"<pre><code>{self._escape_html(self._truncate(content, 500))}</code></pre></div>")

        elif event == "model_output":
            raw = payload.get("raw", "")
            usage = payload.get("usage")
            tool_calls = payload.get("tool_calls") or []
            lines.append("<div class=\"block\"><h3>🧠 Model Output</h3>")
            if usage:
                lines.append(f"<div class=\"meta\">Tokens: {usage.get('prompt_tokens', 0)} → {usage.get('completion_tokens', 0)} = {usage.get('total_tokens', 0)}</div>")
            if tool_calls:
                lines.append("<div class=\"meta\">Tool calls:</div>")
                try:
                    calls_text = json.dumps(tool_calls, ensure_ascii=False)
                except Exception:
                    calls_text = str(tool_calls)
                lines.append("<pre><code>")
                lines.append(self._escape_html(self._truncate(calls_text, 800)))
                lines.append("</code></pre>")
            if raw:
                lines.append("<div class=\"meta\">Content (truncated):</div>")
                lines.append("<pre><code>")
                lines.append(self._escape_html(self._truncate(raw, 600)))
                lines.append("</code></pre>")
            raw_response = payload.get("raw_response")
            include_raw = os.environ.get("TRACE_HTML_INCLUDE_RAW_RESPONSE")
            if include_raw is None:
                include_raw = os.environ.get("TRACE_MD_INCLUDE_RAW_RESPONSE", "false")
            if raw_response is not None and str(include_raw).lower() == "true":
                try:
                    raw_text = json.dumps(raw_response, ensure_ascii=False, indent=2)
                except Exception:
                    raw_text = str(raw_response)
                lines.append("<div class=\"meta\">Raw response (JSON):</div>")
                lines.append("<pre><code>")
                lines.append(self._escape_html(raw_text))
                lines.append("</code></pre>")
            lines.append("</div>")

        elif event == "parsed_action":
            thought = payload.get("thought", "")
            action = payload.get("action", "")
            args = payload.get("args")
            lines.append("<div class=\"block\"><h3>🧠 Parsed Action</h3>")
            if thought:
                lines.append("<div class=\"meta\">Thought:</div>")
                lines.append("<pre><code>")
                lines.append(self._escape_html(thought))
                lines.append("</code></pre>")
            if action:
                lines.append("<div class=\"meta\">Action:</div>")
                lines.append("<pre><code>")
                lines.append(self._escape_html(action))
                lines.append("</code></pre>")
            if args is not None:
                try:
                    args_text = json.dumps(args, ensure_ascii=False)
                except Exception:
                    args_text = str(args)
                lines.append("<div class=\"meta\">Args:</div>")
                lines.append("<pre><code>")
                lines.append(self._escape_html(args_text))
                lines.append("</code></pre>")
            lines.append("</div>")

        elif event == "tool_call":
            tool = payload.get("tool", "")
            args = payload.get("args", {})
            try:
                args_text = json.dumps(args, ensure_ascii=False)
            except Exception:
                args_text = str(args)
            lines.append("<div class=\"block\"><h3>🛠️ Tool Call</h3>")
            lines.append("<pre><code>")
            lines.append(self._escape_html(f"{tool} {args_text}"))
            lines.append("</code></pre></div>")

        elif event == "tool_result":
            tool = payload.get("tool", "")
            result = payload.get("result", {})
            status = result.get("status")
            text = result.get("text", "")
            data = result.get("data", None)
            lines.append("<div class=\"block\"><h3>👁️ Observation</h3>")
            lines.append(f"<div class=\"meta\">Tool: {self._escape_html(tool)}</div>")
            if status:
                lines.append(f"<div class=\"meta\">Status: {self._escape_html(str(status))}</div>")
            if text:
                lines.append("<div class=\"meta\">Text:</div>")
                lines.append("<pre><code>")
                lines.append(self._escape_html(text))
                lines.append("</code></pre>")
            if data is not None:
                try:
                    data_text = json.dumps(data, ensure_ascii=False)
                except Exception:
                    data_text = str(data)
                data_text = self._truncate(data_text, 300)
                lines.append("<div class=\"meta\">Data (truncated):</div>")
                lines.append("<pre><code>")
                lines.append(self._escape_html(data_text))
                lines.append("</code></pre>")
            lines.append("</div>")

        elif event == "error":
            lines.append("<div class=\"block\"><h3>❌ Error</h3>")
            try:
                err_text = json.dumps(payload, ensure_ascii=False)
            except Exception:
                err_text = str(payload)
            lines.append("<pre><code>")
            lines.append(self._escape_html(err_text))
            lines.append("</code></pre></div>")

        elif event == "finish":
            lines.append("<div class=\"block\"><h3>✅ Finish</h3>")
            final = payload.get("final", "")
            lines.append("<pre><code>")
            lines.append(self._escape_html(final))
            lines.append("</code></pre></div>")

        elif event == "session_summary":
            lines.append("<div class=\"block\"><h3>📊 Session Summary</h3>")
            try:
                summary_text = json.dumps(payload, ensure_ascii=False, indent=2)
            except Exception:
                summary_text = str(payload)
            lines.append("<pre><code>")
            lines.append(self._escape_html(summary_text))
            lines.append("</code></pre></div>")

        if lines:
            self._html_handle.write("".join(lines) + "\n")
            self._html_handle.flush()
    
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
