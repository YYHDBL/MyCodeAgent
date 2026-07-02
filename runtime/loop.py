"""Runtime runner for the canonical single-agent turn loop."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from runtime.completion import (
    CompletionGateVerdict,
    DeterministicCompletionVerifier,
    build_completion_candidate,
    collect_verification_evidence,
    infer_completion_requirements,
)
from runtime.input_preprocess import preprocess_input
from runtime.model_errors import ModelErrorKind, classify_model_error
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
        self._record_transcript_state_transition(
            from_state=state.transition.reason.value if state.transition else None,
            to_state=reason.value,
            reason=reason.value,
            step=step if step is not None else next_state.step,
            details=payload_details,
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
        self._record_transcript_terminal(reason=reason.value, step=step, details=details)

    def _get_transcript_recorder(self):
        return getattr(self.host, "transcript_recorder", None)

    def _get_transcript_run_id(self) -> str:
        run_id = getattr(self.host, "_active_transcript_run_id", None)
        if run_id is not None:
            return str(run_id)
        fallback = getattr(self.host, "_run_id", 0)
        return f"run-{fallback}"

    def _record_transcript_message(
        self,
        *,
        role: str,
        content: str,
        step: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        recorder = self._get_transcript_recorder()
        if recorder is None:
            return
        recorder.record_message(
            run_id=self._get_transcript_run_id(),
            step=step,
            role=role,
            content=content,
            metadata=metadata or {},
        )

    def _record_transcript_state_transition(
        self,
        *,
        from_state: str | None,
        to_state: str,
        reason: str,
        step: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        recorder = self._get_transcript_recorder()
        if recorder is None:
            return
        recorder.record_state_transition(
            run_id=self._get_transcript_run_id(),
            step=step,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            details=details or {},
        )

    def _record_transcript_checkpoint(self, *, step: int, checkpoint_id: str, payload: dict[str, Any]) -> None:
        recorder = self._get_transcript_recorder()
        if recorder is None:
            return
        recorder.record_checkpoint(
            run_id=self._get_transcript_run_id(),
            step=step,
            checkpoint_id=checkpoint_id,
            payload=payload,
        )

    def _record_active_transcript_checkpoint(self, *, step: int) -> None:
        compact_store = getattr(getattr(self.host, "context_engine", None), "compact_store", None)
        checkpoint = getattr(compact_store, "active_checkpoint", None)
        if checkpoint is None:
            return
        self._record_transcript_checkpoint(
            step=step,
            checkpoint_id=checkpoint.id,
            payload={
                "summary": checkpoint.summary,
                "source_message_count": checkpoint.source_message_count,
                "retain_start_idx": checkpoint.retain_start_idx,
                "messages_compacted": checkpoint.messages_compacted,
                "created_at": checkpoint.created_at,
                "metadata": dict(checkpoint.metadata),
            },
        )

    def _record_transcript_terminal(self, *, reason: str, step: int, details: dict[str, Any]) -> None:
        recorder = self._get_transcript_recorder()
        if recorder is None:
            return
        recorder.record_terminal(
            run_id=self._get_transcript_run_id(),
            step=step,
            reason=reason,
            details=details,
        )

    def _trace_model_request_state(
        self,
        trace_logger,
        *,
        tools_schema: list[dict[str, Any]],
        step: int,
    ) -> None:
        host = self.host
        if hasattr(host.context_builder, "get_prompt_assembly"):
            prompt_assembly = host.context_builder.get_prompt_assembly()
            previous_prompt_fingerprints = getattr(host, "_last_prompt_fingerprints", {})
            current_prompt_fingerprints = {
                "constitution": prompt_assembly.constitution_fingerprint,
                "tool_contracts": prompt_assembly.tool_contracts_fingerprint,
                "project_rules": prompt_assembly.project_rules_fingerprint,
                "runtime_signals": prompt_assembly.runtime_signals_fingerprint,
            }
            changed_layers = [
                layer
                for layer, value in current_prompt_fingerprints.items()
                if previous_prompt_fingerprints.get(layer) not in (None, value)
            ]
            trace_logger.log_event(
                "prompt_assembly",
                {
                    "constitution_fingerprint": prompt_assembly.constitution_fingerprint,
                    "tool_contracts_fingerprint": prompt_assembly.tool_contracts_fingerprint,
                    "project_rules_fingerprint": prompt_assembly.project_rules_fingerprint,
                    "runtime_signals_fingerprint": prompt_assembly.runtime_signals_fingerprint,
                    "system_fingerprint": prompt_assembly.system_fingerprint,
                    "stable_message_count": len(prompt_assembly.stable_messages),
                    "runtime_signal_count": len(prompt_assembly.runtime_signal_messages),
                    "changed_layers": changed_layers,
                },
                step=step,
            )
            host._last_prompt_fingerprints = current_prompt_fingerprints

        tool_schema_payload = json.dumps(
            tools_schema,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        tool_schema_fingerprint = hashlib.sha256(
            tool_schema_payload.encode("utf-8")
        ).hexdigest()
        previous_tool_schema_fingerprint = getattr(host, "_last_tool_schema_fingerprint", None)
        trace_logger.log_event(
            "tool_schema",
            {
                "fingerprint": tool_schema_fingerprint,
                "tool_count": len(tools_schema),
                "changed": previous_tool_schema_fingerprint not in (
                    None,
                    tool_schema_fingerprint,
                ),
            },
            step=step,
        )
        host._last_tool_schema_fingerprint = tool_schema_fingerprint

    def _append_user_message(self, content: str, metadata: dict[str, Any] | None = None) -> None:
        append_user = self.host.history_manager.append_user
        if metadata is None:
            append_user(content)
            return
        try:
            append_user(content, metadata=metadata)
        except TypeError:
            append_user(content)

    def _get_completion_verifier(self):
        verifier = getattr(self.host, "completion_verifier", None)
        if verifier is not None:
            return verifier
        verifier = DeterministicCompletionVerifier()
        self.host.completion_verifier = verifier
        return verifier

    def _get_model_recovery_limit(self, kind: ModelErrorKind) -> int:
        host = self.host
        if kind is ModelErrorKind.EMPTY_RESPONSE:
            return int(getattr(host, "empty_response_retry_limit", 1) or 1)
        if kind is ModelErrorKind.PROMPT_TOO_LONG:
            return 1
        if kind is ModelErrorKind.MAX_OUTPUT:
            return int(getattr(host, "max_output_recovery_limit", 0) or 0)
        return 0

    def _increment_model_recovery_count(self, state: LoopState, kind: ModelErrorKind) -> dict[str, int]:
        counts = dict(state.model_recovery_counts)
        counts[kind.value] = counts.get(kind.value, 0) + 1
        return counts

    def _trace_model_error_classified(
        self,
        trace_logger,
        *,
        step: int,
        stage: str,
        kind: ModelErrorKind,
        retry_count: int,
        retry_limit: int,
        message: str,
        finish_reason: str | None = None,
    ) -> None:
        trace_logger.log_event(
            "model_error_classified",
            {
                "stage": stage,
                "kind": kind.value,
                "retry_count": retry_count,
                "retry_limit": retry_limit,
                "message": message,
                "finish_reason": finish_reason,
            },
            step=step,
        )

    def _trace_model_recovery_attempted(
        self,
        trace_logger,
        *,
        step: int,
        kind: ModelErrorKind,
        retry_count: int,
        retry_limit: int,
        action: str,
    ) -> None:
        trace_logger.log_event(
            "model_recovery_attempted",
            {
                "kind": kind.value,
                "retry_count": retry_count,
                "retry_limit": retry_limit,
                "action": action,
            },
            step=step,
        )

    def _trace_model_recovery_failed(
        self,
        trace_logger,
        *,
        step: int,
        kind: ModelErrorKind,
        retry_count: int,
        retry_limit: int,
        reason: str,
    ) -> None:
        trace_logger.log_event(
            "model_recovery_failed",
            {
                "kind": kind.value,
                "retry_count": retry_count,
                "retry_limit": retry_limit,
                "reason": reason,
            },
            step=step,
        )

    def run(self, input_text: str, **kwargs) -> str:
        show_raw = kwargs.pop("show_raw", False)
        processed_input, trace_logger, run_id = self._prepare_run(input_text, show_raw)
        raw_input = processed_input
        response_text = ""
        try:
            response_text = self._react_loop(
                pending_input=processed_input,
                show_raw=show_raw,
                trace_logger=trace_logger,
            )
        finally:
            self._finish_run(trace_logger, run_id, response_text)
            host = self.host
            if hasattr(host, "_on_run_finished"):
                host._on_run_finished(processed_input=raw_input)
        return response_text

    def _prepare_run(self, input_text: str, show_raw: bool) -> tuple[str, Any, int]:
        """Refresh dynamic inputs and record the start of a user run."""
        host = self.host
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
        if hasattr(trace_logger, "clear_current_run_events"):
            trace_logger.clear_current_run_events()
        host._run_id += 1
        run_id = host._run_id
        host._active_transcript_run_id = f"run-{run_id}"
        host._log_system_messages_if_needed(trace_logger)
        trace_logger.log_event(
            "run_start",
            {"run_id": run_id, "input": input_text, "processed": processed_input},
            step=0,
        )
        self._append_user_message(processed_input)
        self._record_transcript_message(role="user", content=processed_input, step=0, metadata={})
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
        return processed_input, trace_logger, run_id

    def _finish_run(self, trace_logger, run_id: int, response_text: str) -> None:
        """Record run completion and release run-scoped state."""
        host = self.host
        trace_logger.log_event(
            "run_end",
            {"run_id": run_id, "final": response_text},
            step=0,
        )
        host._active_transcript_run_id = None
        if host.console_progress:
            host._console("✅ Agent 已完成")
        host.logger.debug("response=%s", response_text)
        host.logger.info(
            "history_size=%d, rounds=%d",
            host.history_manager.get_message_count(),
            host.history_manager.get_rounds_count(),
        )

    def _react_loop(self, pending_input: str, show_raw: bool, trace_logger) -> str:
        host = self.host
        tool_choice = "auto"
        completion_retry_limit = int(getattr(host, "completion_gate_retry_limit", 2) or 2)
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
            state, tools_schema, messages = self._prepare_step_context(
                state=state,
                pending_input=pending_input,
                step=step,
                trace_logger=trace_logger,
            )
            base_messages = messages

            response_text = ""
            tool_calls: list[dict[str, Any]] = []
            reasoning_content = None
            response_meta: dict[str, Any] = {}

            while True:
                try:
                    raw_response = host.llm.invoke_raw(messages, tools=tools_schema, tool_choice=tool_choice)
                except Exception as exc:
                    classification = classify_model_error(error=exc)
                    retry_count = state.model_recovery_counts.get(classification.kind.value, 0)
                    retry_limit = self._get_model_recovery_limit(classification.kind)
                    self._trace_model_error_classified(
                        trace_logger,
                        step=step,
                        stage="model_invoke",
                        kind=classification.kind,
                        retry_count=retry_count,
                        retry_limit=retry_limit,
                        message=classification.message,
                        finish_reason=classification.finish_reason,
                    )

                    if (
                        classification.kind is ModelErrorKind.PROMPT_TOO_LONG
                        and retry_count < retry_limit
                        and hasattr(host.context_engine, "reactive_compact")
                    ):
                        next_retry_count = retry_count + 1
                        recovery_counts = self._increment_model_recovery_count(state, classification.kind)
                        self._trace_model_recovery_attempted(
                            trace_logger,
                            step=step,
                            kind=classification.kind,
                            retry_count=next_retry_count,
                            retry_limit=retry_limit,
                            action="reactive_compact",
                        )
                        compact_info = host.context_engine.reactive_compact(
                            history_manager=host.history_manager,
                            pending_input=pending_input,
                            step=step,
                            trace_logger=trace_logger,
                        )
                        if compact_info.get("compacted"):
                            self._record_active_transcript_checkpoint(step=step)
                            state = self._transition(
                                state,
                                TransitionReason.MODEL_RECOVERY_RETRY,
                                trace_logger,
                                step=step,
                                model_recovery_counts=recovery_counts,
                                compact_attempted=True,
                                last_model_error_kind=classification.kind.value,
                                last_model_error_stage="model_invoke",
                                last_error=classification.message,
                                details={
                                    "error_kind": classification.kind.value,
                                    "retry_count": next_retry_count,
                                    "retry_limit": retry_limit,
                                    "action": "reactive_compact",
                                    "checkpoint_id": compact_info.get("checkpoint_id"),
                                },
                            )
                            model_view = host.context_engine.build_model_view(
                                history_manager=host.history_manager,
                                pending_input=pending_input,
                                step=step,
                                trace_logger=trace_logger,
                            )
                            messages = model_view.messages
                            base_messages = messages
                            state = state.update(messages=messages)
                            trace_logger.log_event(
                                "context_build",
                                {
                                    "message_count": len(messages),
                                    "history_count": model_view.history_message_count,
                                    "source_message_count": model_view.source_message_count,
                                    "projection_mode": model_view.projection_mode,
                                },
                                step=step,
                            )
                            continue

                        self._trace_model_recovery_failed(
                            trace_logger,
                            step=step,
                            kind=classification.kind,
                            retry_count=next_retry_count,
                            retry_limit=retry_limit,
                            reason=str(compact_info.get("reason") or "reactive_compact_failed"),
                        )
                        state = self._transition(
                            state,
                            TransitionReason.MODEL_RECOVERY_FAILED,
                            trace_logger,
                            step=step,
                            model_recovery_counts=recovery_counts,
                            compact_attempted=True,
                            last_model_error_kind=classification.kind.value,
                            last_model_error_stage="model_invoke",
                            last_error=classification.message,
                            details={
                                "error_kind": classification.kind.value,
                                "retry_count": next_retry_count,
                                "retry_limit": retry_limit,
                                "action": "reactive_compact",
                                "reason": compact_info.get("reason"),
                            },
                        )
                    else:
                        self._trace_model_recovery_failed(
                            trace_logger,
                            step=step,
                            kind=classification.kind,
                            retry_count=retry_count,
                            retry_limit=retry_limit,
                            reason="non_recoverable" if retry_limit == 0 else "retry_exhausted",
                        )
                        state = self._transition(
                            state,
                            TransitionReason.MODEL_RECOVERY_FAILED,
                            trace_logger,
                            step=step,
                            last_model_error_kind=classification.kind.value,
                            last_model_error_stage="model_invoke",
                            last_error=classification.message,
                            details={
                                "error_kind": classification.kind.value,
                                "retry_count": retry_count,
                                "retry_limit": retry_limit,
                            },
                        )

                    self._terminal(
                        TerminalReason.MODEL_ERROR,
                        trace_logger,
                        step=step,
                        error_kind=classification.kind.value,
                        message=classification.message,
                        retry_count=retry_count,
                        retry_limit=retry_limit,
                    )
                    return "抱歉，我无法在限定步数内完成这个任务。"

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
                    host.context_engine.record_usage(usage["total_tokens"])
                    max_total_tokens = int(getattr(host, "max_total_tokens", 0) or 0)
                    if max_total_tokens and host.context_engine.total_usage_tokens > max_total_tokens:
                        state = self._transition(
                            state,
                            TransitionReason.TOKEN_BUDGET_EXCEEDED,
                            trace_logger,
                            step=step,
                            details={
                                "total_tokens": host.context_engine.total_usage_tokens,
                                "token_budget": max_total_tokens,
                            },
                        )
                        self._terminal(
                            TerminalReason.TOKEN_BUDGET,
                            trace_logger,
                            step=step,
                            total_tokens=host.context_engine.total_usage_tokens,
                            token_budget=max_total_tokens,
                        )
                        return "抱歉，我无法在限定预算内完成这个任务。"

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

                classification = None
                candidate_error = classify_model_error(
                    response_text=response_text,
                    tool_calls=tool_calls,
                    response_meta=response_meta,
                )
                if candidate_error.kind in {ModelErrorKind.EMPTY_RESPONSE, ModelErrorKind.MAX_OUTPUT}:
                    classification = candidate_error

                if classification is None:
                    break

                retry_count = state.model_recovery_counts.get(classification.kind.value, 0)
                retry_limit = self._get_model_recovery_limit(classification.kind)
                self._trace_model_error_classified(
                    trace_logger,
                    step=step,
                    stage="model_response",
                    kind=classification.kind,
                    retry_count=retry_count,
                    retry_limit=retry_limit,
                    message=classification.message,
                    finish_reason=classification.finish_reason,
                )

                if classification.kind is ModelErrorKind.EMPTY_RESPONSE and retry_count < retry_limit:
                    next_retry_count = retry_count + 1
                    recovery_counts = self._increment_model_recovery_count(state, classification.kind)
                    hint = "上次 content 为空且未返回 tool_calls，请在 content 中回复最终答案，或使用工具调用。"
                    messages = base_messages + [{"role": "user", "content": hint}]
                    self._trace_model_recovery_attempted(
                        trace_logger,
                        step=step,
                        kind=classification.kind,
                        retry_count=next_retry_count,
                        retry_limit=retry_limit,
                        action="retry_with_hint",
                    )
                    state = self._transition(
                        state,
                        TransitionReason.MODEL_EMPTY_RETRY,
                        trace_logger,
                        step=step,
                        model_recovery_counts=recovery_counts,
                        last_model_error_kind=classification.kind.value,
                        last_model_error_stage="model_response",
                        last_error=classification.message,
                        last_response_meta=response_meta,
                        details={
                            "error_kind": classification.kind.value,
                            "finish_reason": response_meta.get("finish_reason"),
                            "retry_count": next_retry_count,
                            "retry_limit": retry_limit,
                        },
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

                self._trace_model_recovery_failed(
                    trace_logger,
                    step=step,
                    kind=classification.kind,
                    retry_count=retry_count,
                    retry_limit=retry_limit,
                    reason="retry_exhausted" if retry_limit else "non_recoverable",
                )
                transition_reason = (
                    TransitionReason.MODEL_EMPTY_FAILED
                    if classification.kind is ModelErrorKind.EMPTY_RESPONSE
                    else TransitionReason.MODEL_RECOVERY_FAILED
                )
                state_changes: dict[str, Any] = {
                    "last_response_meta": response_meta,
                    "last_model_error_kind": classification.kind.value,
                    "last_model_error_stage": "model_response",
                    "last_error": classification.message,
                }
                if classification.kind is ModelErrorKind.MAX_OUTPUT:
                    state_changes["max_output_recovery_count"] = state.max_output_recovery_count + 1
                state = self._transition(
                    state,
                    transition_reason,
                    trace_logger,
                    step=step,
                    details={
                        "error_kind": classification.kind.value,
                        "finish_reason": response_meta.get("finish_reason"),
                        "retry_count": retry_count,
                        "retry_limit": retry_limit,
                    },
                    **state_changes,
                )
                terminal_reason = (
                    TerminalReason.EMPTY_RESPONSE_FAILED
                    if classification.kind is ModelErrorKind.EMPTY_RESPONSE
                    else TerminalReason.MODEL_ERROR
                )
                self._terminal(
                    terminal_reason,
                    trace_logger,
                    step=step,
                    error_kind=classification.kind.value,
                    finish_reason=response_meta.get("finish_reason"),
                    retry_count=retry_count,
                    retry_limit=retry_limit,
                )
                if classification.kind is ModelErrorKind.EMPTY_RESPONSE:
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
                self._record_transcript_message(
                    role="assistant",
                    content=assistant_content,
                    step=step,
                    metadata={
                        "action_type": "tool_call",
                        "tool_calls": tool_calls,
                    },
                )
                host._log_message_write(
                    trace_logger,
                    "assistant",
                    assistant_content,
                    {"action_type": "tool_call", "tool_calls": tool_calls},
                    step,
                )
                if getattr(host, "tool_orchestrator", None) is None:
                    raise RuntimeError("Runtime host must provide a ToolOrchestrator instance")
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
                for obs in observations:
                    obs_metadata = getattr(obs, "metadata", None) or {}
                    host.history_manager.append_tool(
                        tool_name=obs.tool_name,
                        raw_result=obs.observation,
                        metadata={
                            "step": step,
                            "tool_call_id": obs.tool_call_id,
                            **obs_metadata,
                        },
                        project_root=host.project_root,
                    )
                    self._record_transcript_message(
                        role="tool",
                        content=obs.observation,
                        step=step,
                        metadata={
                            "tool_name": obs.tool_name,
                            "tool_call_id": obs.tool_call_id,
                            **obs_metadata,
                        },
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
            candidate = build_completion_candidate(
                final_text=final_text,
                step=step,
                response_meta=response_meta,
                history_messages=host.history_manager.get_messages(),
            )
            trace_logger.log_event(
                "completion_candidate",
                candidate.to_trace_payload(),
                step=step,
            )

            requirements = infer_completion_requirements(
                user_input=pending_input,
                history_messages=host.history_manager.get_messages(),
            )
            trace_logger.log_event(
                "completion_requirements",
                requirements.to_trace_payload(),
                step=step,
            )

            evidence = collect_verification_evidence(host.history_manager.get_messages())
            for item in evidence:
                trace_logger.log_event("verification_evidence", item.to_trace_payload(), step=step)

            verdict = self._get_completion_verifier().evaluate(
                candidate,
                requirements,
                evidence,
                host.history_manager.get_messages(),
            )
            trace_logger.log_event(
                "completion_gate_verdict",
                verdict.to_trace_payload(),
                step=step,
            )

            if verdict.verdict in {CompletionGateVerdict.PASS, CompletionGateVerdict.UNVERIFIED}:
                action_type = "final" if verdict.verdict is CompletionGateVerdict.PASS else "final_unverified"
                host.history_manager.append_assistant(
                    content=final_text,
                    metadata={"step": step, "action_type": action_type},
                    reasoning_content=reasoning_content,
                )
                self._record_transcript_message(
                    role="assistant",
                    content=final_text,
                    step=step,
                    metadata={"action_type": action_type},
                )
                host._log_message_write(
                    trace_logger,
                    "assistant",
                    final_text,
                    {"action_type": action_type},
                    step,
                )
                state = self._transition(
                    state,
                    TransitionReason.MODEL_RETURNED_FINAL,
                    trace_logger,
                    step=step,
                    last_response_meta={
                        "final_length": len(final_text),
                        "completion_verdict": verdict.verdict.value,
                    },
                    details={
                        "final_length": len(final_text),
                        "completion_verdict": verdict.verdict.value,
                    },
                )
                terminal_reason = (
                    TerminalReason.COMPLETED
                    if verdict.verdict is CompletionGateVerdict.PASS
                    else TerminalReason.COMPLETED_UNVERIFIED
                )
                self._terminal(
                    terminal_reason,
                    trace_logger,
                    step=step,
                    final_length=len(final_text),
                    completion_verdict=verdict.verdict.value,
                )
                trace_logger.log_event(
                    "finish",
                    {"final": final_text, "completion_verdict": verdict.verdict.value},
                    step=step,
                )
                return final_text

            host.history_manager.append_assistant(
                content=final_text,
                metadata={"step": step, "action_type": "final_candidate"},
                reasoning_content=reasoning_content,
            )
            self._record_transcript_message(
                role="assistant",
                content=final_text,
                step=step,
                metadata={"action_type": "final_candidate"},
            )
            host._log_message_write(
                trace_logger,
                "assistant",
                final_text,
                {"action_type": "final_candidate"},
                step,
            )
            block_count = state.completion_block_count + 1
            feedback = verdict.blocking_feedback or "Completion blocked by runtime gate."
            self._append_user_message(
                feedback,
                metadata={"step": step, "source": "completion_gate"},
            )
            self._record_transcript_message(
                role="user",
                content=feedback,
                step=step,
                metadata={"source": "completion_gate"},
            )
            host._log_message_write(
                trace_logger,
                "user",
                feedback,
                {"source": "completion_gate"},
                step,
            )
            state = self._transition(
                state,
                TransitionReason.STOP_HOOK_BLOCKING,
                trace_logger,
                step=step,
                completion_block_count=block_count,
                stop_hook_active=True,
                details={
                    "completion_verdict": verdict.verdict.value,
                    "reasons": list(verdict.reasons),
                    "retry_count": block_count,
                    "retry_limit": completion_retry_limit,
                },
            )
            if block_count >= completion_retry_limit:
                self._terminal(
                    TerminalReason.COMPLETION_GATE_BLOCKED,
                    trace_logger,
                    step=step,
                    completion_verdict=verdict.verdict.value,
                    reasons=list(verdict.reasons),
                    retry_count=block_count,
                    retry_limit=completion_retry_limit,
                )
                return "抱歉，我无法在限定步数内完成这个任务。"
            continue

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

    def _prepare_step_context(
        self,
        *,
        state: LoopState,
        pending_input: str,
        step: int,
        trace_logger,
    ) -> tuple[LoopState, list[dict[str, Any]], list[dict[str, Any]]]:
        """Refresh runtime signals, compact history, and build the model view."""
        host = self.host
        tools_schema = host._get_openai_tools_for_current_mode()
        if (
            host.enable_agent_teams
            and host.team_manager
            and hasattr(host.context_builder, "set_runtime_system_blocks")
        ):
            events = host.team_manager.drain_events()
            runtime_state = host.team_manager.export_state()
            runtime_blocks = host._format_runtime_system_blocks(
                events,
                runtime_state=runtime_state,
            )
            host.context_builder.set_runtime_system_blocks(runtime_blocks)

        self._trace_model_request_state(
            trace_logger,
            tools_schema=tools_schema,
            step=step,
        )
        if host.console_verbose:
            host._console(f"\n--- Step {step}/{host.max_steps} ---")
        elif host.console_progress:
            host._console(f"… Step {step}/{host.max_steps}")
        elif host.logger.isEnabledFor(10):
            host.logger.debug("Step %d/%d", step, host.max_steps)

        compact_info = host.context_engine.compact_if_needed(
            history_manager=host.history_manager,
            pending_input=pending_input,
            step=step,
            trace_logger=trace_logger,
        )
        if compact_info.get("compacted"):
            self._record_active_transcript_checkpoint(step=step)
            state = self._transition(
                state,
                TransitionReason.CONTEXT_COMPACTED,
                trace_logger,
                step=step,
                compact_attempted=True,
                details={
                    "checkpoint_id": compact_info.get("checkpoint_id"),
                    "messages_compacted": compact_info.get("messages_compacted"),
                    "retain_start_idx": compact_info.get("retain_start_idx"),
                },
            )
            final_context = host.context_engine.build_model_view(
                history_manager=host.history_manager,
                pending_input=pending_input,
                step=step,
                trace_logger=trace_logger,
            ).messages
            trace_logger.log_event(
                "history_compression_final_context",
                {"message_count": len(final_context), "messages": final_context},
                step=step,
            )
            if host.console_verbose:
                host._console("\n📦 触发历史压缩...")
                host._console(
                    "✅ 压缩完成，当前轮次数: %d"
                    % host.history_manager.get_rounds_count()
                )
                host._print_context_preview(final_context)
            elif host.logger.isEnabledFor(10):
                host.logger.debug("触发历史压缩")
                host.logger.debug(
                    "压缩完成，当前轮次数: %d",
                    host.history_manager.get_rounds_count(),
                )
                host._print_context_preview(final_context)

        model_view = host.context_engine.build_model_view(
            history_manager=host.history_manager,
            pending_input=pending_input,
            step=step,
            trace_logger=trace_logger,
        )
        messages = model_view.messages
        state = state.update(step=step, messages=messages)
        trace_logger.log_event(
            "context_build",
            {
                "message_count": len(messages),
                "history_count": model_view.history_message_count,
                "source_message_count": model_view.source_message_count,
                "projection_mode": model_view.projection_mode,
            },
            step=step,
        )
        return state, tools_schema, messages
