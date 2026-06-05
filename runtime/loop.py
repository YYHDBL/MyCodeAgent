"""Runtime runner for the canonical single-agent turn loop."""

from __future__ import annotations

import uuid
from typing import Any

from runtime.input_preprocess import preprocess_input
from runtime.state import LoopState, TerminalReason, TransitionReason


class RuntimeRunner:
    """Canonical single-agent turn loop."""

    def __init__(self, host: Any):
        self.host = host

    def _transition(
        self,
        state: LoopState,
        reason: TransitionReason,
        trace_logger,
        *,
        step: int | None = None,
        details: dict[str, Any] | None = None,
        **changes: Any,
    ) -> LoopState:
        next_step = step if step is not None else state.step
        state_field_names = set(LoopState.__dataclass_fields__)
        state_changes = {key: value for key, value in changes.items() if key in state_field_names}
        detail_changes = {key: value for key, value in changes.items() if key not in state_field_names}
        payload_details = details if details is not None else detail_changes
        next_state = state.next(reason, step=next_step, details=payload_details, **state_changes)
        if trace_logger:
            trace_logger.log_event(
                "state_transition",
                {
                    "step": next_state.step,
                    "turn_count": next_state.turn_count,
                    "reason": reason.value,
                    "message_count": len(next_state.messages),
                    "details": payload_details,
                },
                step=step if step is not None else next_state.step,
            )
        return next_state

    def _terminal(
        self,
        reason: TerminalReason,
        trace_logger,
        *,
        step: int = 0,
        **details: Any,
    ) -> None:
        if trace_logger:
            trace_logger.log_event(
                "terminal",
                {"reason": reason.value, "details": details},
                step=step,
            )

    def run(self, input_text: str, **kwargs) -> str:
        host = self.host
        show_raw = kwargs.pop("show_raw", False)
        if not show_raw:
            host.last_response_raw = None

        if host.console_progress:
            host._console("⏳ Agent 正在处理，请稍候...")

        host._refresh_skills_prompt()
        host.context_builder.set_skills_prompt(host._skills_prompt)
        preprocess_result = preprocess_input(input_text)
        processed_input = preprocess_result.processed_input

        if preprocess_result.mentioned_files:
            mentioned = ", ".join(preprocess_result.mentioned_files)
            if host.console_verbose:
                host._console(f"\n📎 检测到文件引用: {mentioned}")
                if preprocess_result.truncated_count > 0:
                    host._console(f"   (另有 {preprocess_result.truncated_count} 个文件被省略)")
            elif host.logger.isEnabledFor(10):
                host.logger.debug("检测到文件引用: %s", mentioned)
                if preprocess_result.truncated_count > 0:
                    host.logger.debug("另有 %d 个文件被省略", preprocess_result.truncated_count)

        trace_logger = host.trace_logger
        host._run_id += 1
        run_id = host._run_id

        host._log_system_messages_if_needed(trace_logger)
        trace_logger.log_event(
            "run_start",
            {
                "run_id": run_id,
                "input": input_text,
                "processed": processed_input,
            },
            step=0,
        )

        host.history_manager.append_user(processed_input)
        trace_logger.log_event(
            "user_input",
            {"text": input_text, "processed": processed_input},
            step=0,
        )
        host._log_message_write(trace_logger, "user", processed_input, {}, step=0)

        if host.console_verbose:
            host._console(f"\n⚙️ Engine 启动: {input_text}")
        elif host.logger.isEnabledFor(10):
            host.logger.debug("Engine 启动: %s", input_text)

        response_text = ""
        try:
            response_text = self._react_loop(
                pending_input=processed_input,
                show_raw=show_raw,
                trace_logger=trace_logger,
            )
        finally:
            trace_logger.log_event(
                "run_end",
                {"run_id": run_id, "final": response_text if "response_text" in locals() else ""},
                step=0,
            )
        if host.console_progress:
            host._console("✅ Agent 已完成")

        host.logger.debug("response=%s", response_text)
        host.logger.info(
            "history_size=%d, rounds=%d",
            host.history_manager.get_message_count(),
            host.history_manager.get_rounds_count(),
        )
        return response_text

    def _react_loop(self, pending_input: str, show_raw: bool, trace_logger) -> str:
        host = self.host
        tool_choice = "auto"
        state = LoopState(
            messages=[],
            step=1,
            turn_count=1,
            tool_choice=tool_choice,
        )
        state = self._transition(
            state,
            TransitionReason.USER_INPUT,
            trace_logger,
            step=0,
            pending_input_len=len(pending_input or ""),
        )

        for step in range(1, host.max_steps + 1):
            tools_schema = host._get_openai_tools_for_current_mode()
            if (
                host.enable_agent_teams
                and host.team_manager
                and hasattr(host.context_builder, "set_runtime_system_blocks")
            ):
                events = host.team_manager.drain_events()
                runtime_state = host.team_manager.export_state()
                runtime_blocks = host._format_runtime_system_blocks(events, runtime_state=runtime_state)
                host.context_builder.set_runtime_system_blocks(runtime_blocks)

            if host.console_verbose:
                host._console(f"\n--- Step {step}/{host.max_steps} ---")
            elif host.console_progress:
                host._console(f"… Step {step}/{host.max_steps}")
            elif host.logger.isEnabledFor(10):
                host.logger.debug("Step %d/%d", step, host.max_steps)

            if host.history_manager.should_compress(pending_input):
                estimated_tokens = host.history_manager.estimate_context_tokens(pending_input)
                threshold = int(host.config.context_window * host.config.compression_threshold)
                trace_logger.log_event(
                    "history_compression_triggered",
                    {
                        "estimated_tokens": estimated_tokens,
                        "threshold": threshold,
                        "total_usage_tokens": host.history_manager.get_total_usage_tokens(),
                        "message_count": host.history_manager.get_message_count(),
                    },
                    step=step,
                )

                if host.console_verbose:
                    host._console("\n📦 触发历史压缩...")
                elif host.logger.isEnabledFor(10):
                    host.logger.debug("触发历史压缩")

                rounds_before = host.history_manager.get_rounds_count()
                messages_before = host.history_manager.get_message_count()

                compress_info = host.history_manager.compact(
                    on_event=lambda ev, payload: trace_logger.log_event(ev, payload, step=step),
                    return_info=True,
                )
                compressed = bool(compress_info.get("compressed"))

                if compressed:
                    rounds_after = host.history_manager.get_rounds_count()
                    messages_after = host.history_manager.get_message_count()
                    state = self._transition(
                        state,
                        TransitionReason.CONTEXT_COMPACTED,
                        trace_logger,
                        step=step,
                        compact_attempted=True,
                        details={
                            "messages_before": messages_before,
                            "messages_after": messages_after,
                        },
                    )

                    trace_logger.log_event(
                        "history_compression_completed",
                        {
                            "rounds_before": rounds_before,
                            "rounds_after": rounds_after,
                            "messages_compressed": messages_before - messages_after,
                            "summary_generated": compress_info.get("summary_generated", False),
                            "details": compress_info,
                        },
                        step=step,
                    )

                    compressed_history = host.history_manager.to_messages()
                    final_context = host.context_builder.build_messages(compressed_history)
                    trace_logger.log_event(
                        "history_compression_final_context",
                        {"message_count": len(final_context), "messages": final_context},
                        step=step,
                    )

                    if host.console_verbose:
                        host._console(f"✅ 压缩完成，当前轮次数: {rounds_after}")
                        host._print_context_preview(final_context)
                    elif host.logger.isEnabledFor(10):
                        host.logger.debug("压缩完成，当前轮次数: %d", rounds_after)
                        host._print_context_preview(final_context)

            history_messages = host.history_manager.to_messages()
            messages = host._build_messages(history_messages)
            base_messages = messages
            state = state.update(step=step, messages=messages)

            trace_logger.log_event(
                "context_build",
                {"message_count": len(messages), "history_count": len(history_messages)},
                step=step,
            )

            empty_retry_used = False
            response_text = ""
            tool_calls: list[dict[str, Any]] = []

            while True:
                raw_response = host.llm.invoke_raw(messages, tools=tools_schema, tool_choice=tool_choice)
                if show_raw:
                    host.last_response_raw = (
                        raw_response.model_dump()
                        if hasattr(raw_response, "model_dump")
                        else raw_response
                    )

                response_text = host._extract_content(raw_response) or ""
                reasoning_content = host._extract_reasoning_content(raw_response)
                usage = host._extract_usage(raw_response)
                if usage and usage.get("total_tokens") is not None:
                    host.history_manager.update_last_usage(usage["total_tokens"])

                response_meta = host._extract_response_meta(raw_response)
                tool_calls = host._extract_tool_calls(raw_response)
                raw_dump = host._extract_raw_response(raw_response)
                trace_logger.log_event(
                    "model_output",
                    {
                        "raw": response_text,
                        "usage": usage,
                        "meta": response_meta,
                        "raw_response": raw_dump,
                        "tool_calls": tool_calls,
                    },
                    step=step,
                )

                if host.console_verbose and reasoning_content:
                    display_reasoning = reasoning_content
                    if len(display_reasoning) > 1200:
                        display_reasoning = display_reasoning[:1200] + "...(truncated)"
                    host._console(f"\n🧠 Reasoning: {display_reasoning}\n")

                if tool_calls or (response_text and str(response_text).strip()):
                    break

                if not empty_retry_used:
                    empty_retry_used = True
                    hint = "上次 content 为空且未返回 tool_calls，请在 content 中回复最终答案，或使用工具调用。"
                    messages = base_messages + [{"role": "user", "content": hint}]
                    state = self._transition(
                        state,
                        TransitionReason.MODEL_EMPTY_RETRY,
                        trace_logger,
                        step=step,
                        empty_response_retry_used=True,
                        last_response_meta=response_meta,
                        details={"finish_reason": response_meta.get("finish_reason")},
                    )
                    trace_logger.log_event(
                        "empty_response_retry",
                        {
                            "finish_reason": response_meta.get("finish_reason"),
                            "content_len": response_meta.get("content_len"),
                            "reasoning_len": response_meta.get("reasoning_len"),
                            "hint": hint,
                        },
                        step=step,
                    )
                    if host.console_verbose:
                        host._console("⚠️ LLM返回空响应，追加提示后重试一次")
                    else:
                        host.logger.warning("LLM返回空响应，追加提示后重试一次")
                    continue

                if host.console_verbose:
                    host._console("❌ LLM返回空响应")
                else:
                    host.logger.error("LLM返回空响应")
                state = self._transition(
                    state,
                    TransitionReason.MODEL_EMPTY_FAILED,
                    trace_logger,
                    step=step,
                    last_response_meta=response_meta,
                    details={"finish_reason": response_meta.get("finish_reason")},
                )
                self._terminal(
                    TerminalReason.EMPTY_RESPONSE_FAILED,
                    trace_logger,
                    step=step,
                    finish_reason=response_meta.get("finish_reason"),
                )
                trace_logger.log_event(
                    "error",
                    {
                        "stage": "llm_response",
                        "error_code": "INTERNAL_ERROR",
                        "message": "Empty response",
                        "meta": response_meta,
                    },
                    step=step,
                )
                return "抱歉，我无法在限定步数内完成这个任务。"

            if not tool_calls and (not response_text or not str(response_text).strip()):
                break

            if tool_calls:
                state = self._transition(
                    state,
                    TransitionReason.MODEL_RETURNED_TOOL_CALLS,
                    trace_logger,
                    step=step,
                    last_tool_calls=tool_calls,
                    last_response_meta=response_meta,
                    details={"tool_count": len(tool_calls)},
                )
                for call in tool_calls:
                    if not call.get("id"):
                        call["id"] = f"call_{uuid.uuid4().hex}"
                assistant_content = str(response_text or "")
                host.history_manager.append_assistant(
                    content=assistant_content,
                    metadata={
                        "step": step,
                        "action_type": "tool_call",
                        "tool_calls": tool_calls,
                    },
                    reasoning_content=reasoning_content,
                )
                host._log_message_write(
                    trace_logger,
                    "assistant",
                    assistant_content,
                    {"action_type": "tool_call", "tool_calls": tool_calls},
                    step,
                )
                if getattr(host, "tool_orchestrator", None) is not None:
                    if hasattr(host.tool_orchestrator, "run"):
                        observations = host.tool_orchestrator.run(
                            tool_calls,
                            step=step,
                            trace_logger=trace_logger,
                        )
                    else:
                        observations = host.tool_orchestrator.run_serial(
                            tool_calls,
                            step=step,
                            trace_logger=trace_logger,
                        )
                else:
                    from tools.orchestrator import ToolOrchestrator

                    observations = ToolOrchestrator(host).run(
                        tool_calls,
                        step=step,
                        trace_logger=trace_logger,
                    )
                for obs in observations:
                    host.history_manager.append_tool(
                        tool_name=obs.tool_name,
                        raw_result=obs.observation,
                        metadata={"step": step, "tool_call_id": obs.tool_call_id},
                        project_root=host.project_root,
                    )
                    host._log_message_write(
                        trace_logger,
                        "tool",
                        obs.observation,
                        {"tool_name": obs.tool_name, "tool_call_id": obs.tool_call_id},
                        step,
                    )

                    if host.console_verbose:
                        display_obs = (
                            obs.observation[:300] + "..." if len(obs.observation) > 300 else obs.observation
                        )
                        host._console(f"\n👀 Observation: {display_obs}\n")
                    elif host.logger.isEnabledFor(10):
                        display_obs = (
                            obs.observation[:300] + "..." if len(obs.observation) > 300 else obs.observation
                        )
                        host.logger.debug("Observation: %s", display_obs)
                state = self._transition(
                    state,
                    TransitionReason.TOOLS_EXECUTED,
                    trace_logger,
                    step=step,
                    last_tool_calls=tool_calls,
                    details={"tool_count": len(tool_calls)},
                )
                continue

            final_text = str(response_text).strip()
            host.history_manager.append_assistant(
                content=final_text,
                metadata={"step": step, "action_type": "final"},
                reasoning_content=reasoning_content,
            )
            host._log_message_write(
                trace_logger,
                "assistant",
                final_text,
                {"action_type": "final"},
                step,
            )
            state = self._transition(
                state,
                TransitionReason.MODEL_RETURNED_FINAL,
                trace_logger,
                step=step,
                last_response_meta={"final_length": len(final_text)},
                details={"final_length": len(final_text)},
            )
            self._terminal(
                TerminalReason.COMPLETED,
                trace_logger,
                step=step,
                final_length=len(final_text),
            )
            trace_logger.log_event("finish", {"final": final_text}, step=step)
            return final_text

        state = self._transition(
            state,
            TransitionReason.MAX_STEPS_EXCEEDED,
            trace_logger,
            step=host.max_steps,
            details={"max_steps": host.max_steps},
        )
        self._terminal(
            TerminalReason.MAX_STEPS,
            trace_logger,
            step=host.max_steps,
            max_steps=host.max_steps,
        )
        return "抱歉，我无法在限定步数内完成这个任务。"
