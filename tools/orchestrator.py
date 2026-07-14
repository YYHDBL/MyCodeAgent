"""Tool call orchestration boundary for the agent runtime."""

from __future__ import annotations

import os
import traceback as tb
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol

from core.llm import parse_tool_input
from tools.base import ErrorCode, ToolResult, ToolStatus, serialize_tool_result, tool_result_payload
from tools.observation_store import force_truncate_result, truncate_result


class RuntimeEventEmitter(Protocol):
    """Neutral callback implemented by the runtime host, not by tools."""

    def emit_runtime_event(
        self,
        *,
        run_id: str,
        step: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> None: ...

@dataclass(frozen=True)
class ToolObservation:
    tool_name: str
    tool_call_id: str
    result: ToolResult
    raw_result: ToolResult | None = None
    metadata: dict[str, Any] | None = None
    observation: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation", serialize_tool_result(self.result))


@dataclass(frozen=True)
class ToolResultBudget:
    max_tool_bytes: int
    max_message_bytes: int


@dataclass(frozen=True)
class ToolCallPlan:
    call: dict[str, Any]
    tool_name: str
    tool_call_id: str
    parsed_input: dict[str, Any]
    parse_error: Exception | None
    concurrency_safe: bool


@dataclass(frozen=True)
class ToolBatch:
    concurrency_safe: bool
    calls: list[ToolCallPlan]


class ToolOrchestrator:
    """Execute model tool calls while preserving model order."""

    SAFE_TOOL_NAMES = {"Read", "Grep", "Glob"}
    UNSAFE_TOOL_NAMES = {"Edit", "Bash", "Task", "Skill", "TodoWrite"}

    def __init__(self, host: Any):
        self.host = host

    def _get_transcript_run_id(self) -> str:
        run_id = getattr(self.host, "_active_transcript_run_id", None)
        if run_id is not None:
            return str(run_id)
        return f"run-{getattr(self.host, '_run_id', 0)}"

    def _emit_tool_lifecycle(
        self,
        *,
        step: int,
        tool_name: str,
        tool_call_id: str,
        status: str,
        payload: dict[str, Any] | None = None,
        trace_logger=None,
    ) -> None:
        event_payload = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "status": status,
            "payload": payload or {},
        }
        emit_runtime_event = getattr(self.host, "emit_runtime_event", None)
        if callable(emit_runtime_event):
            emit_runtime_event(
                run_id=self._get_transcript_run_id(),
                step=step,
                event_type="tool_lifecycle",
                payload=event_payload,
            )
            return
        self._log_tool_lifecycle(trace_logger, step=step, payload=event_payload)

    @staticmethod
    def _log_tool_lifecycle(trace_logger, *, step: int, payload: dict[str, Any]) -> None:
        """Keep direct tool-unit callers traceable without a runtime host."""

        if trace_logger is None:
            return
        lifecycle_payload = payload["payload"]
        if payload["status"] == "requested":
            trace_logger.log_event(
                "tool_call",
                {
                    "tool": payload["tool_name"],
                    "args": lifecycle_payload.get("args") or {},
                    "tool_call_id": payload["tool_call_id"],
                },
                step=step,
            )
        elif payload["status"] in {"completed", "failed"} and "result" in lifecycle_payload:
            trace_logger.log_event(
                "tool_result",
                {
                    "tool": payload["tool_name"],
                    "result": lifecycle_payload["result"],
                },
                step=step,
            )
        trace_logger.log_event("tool_lifecycle", payload, step=step)

    def run(
        self,
        tool_calls: list[dict[str, Any]],
        *,
        step: int,
        trace_logger,
    ) -> list[ToolObservation]:
        plans = self.plan_tool_calls(tool_calls)
        batches = self.partition_tool_calls(plans)
        self._log_plan(trace_logger, step, batches)

        observations: list[ToolObservation] = []
        for batch_index, batch in enumerate(batches):
            self._log_batch_start(trace_logger, step, batch_index, batch)
            batch_observations = (
                self._run_batch_concurrently(batch, step=step, trace_logger=trace_logger)
                if batch.concurrency_safe
                else self._run_batch_serially(batch, step=step, trace_logger=trace_logger)
            )
            self._log_batch_end(trace_logger, step, batch_index, batch, batch_observations)
            observations.extend(batch_observations)

        observations = [self._normalize_empty_result(obs) for obs in observations]
        observations = [self._apply_observation_limit(obs) for obs in observations]
        return self._apply_result_budget(observations, step=step, trace_logger=trace_logger)

    def run_serial(
        self,
        tool_calls: list[dict[str, Any]],
        *,
        step: int,
        trace_logger,
    ) -> list[ToolObservation]:
        plans = self.plan_tool_calls(tool_calls)
        observations = self._run_batch_serially(
            ToolBatch(concurrency_safe=False, calls=plans),
            step=step,
            trace_logger=trace_logger,
        )
        return observations

    def plan_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[ToolCallPlan]:
        plans: list[ToolCallPlan] = []
        for call in tool_calls:
            tool_name = call.get("name") or "unknown_tool"
            tool_call_id = call.get("id") or f"call_{uuid.uuid4().hex}"
            raw_args = call.get("arguments") or {}
            parsed_input, parse_error = parse_tool_input(raw_args)
            plans.append(
                ToolCallPlan(
                    call=call,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    parsed_input=parsed_input if isinstance(parsed_input, dict) else {},
                    parse_error=parse_error,
                    concurrency_safe=self.is_concurrency_safe(tool_name, parse_error),
                )
            )
        return plans

    def is_concurrency_safe(self, tool_name: str, parse_error: Exception | None) -> bool:
        if parse_error is not None:
            return False
        if tool_name in self.SAFE_TOOL_NAMES:
            return True
        if tool_name in self.UNSAFE_TOOL_NAMES:
            return False
        return False

    def partition_tool_calls(self, plans: list[ToolCallPlan]) -> list[ToolBatch]:
        batches: list[ToolBatch] = []
        for plan in plans:
            if (
                batches
                and plan.concurrency_safe
                and batches[-1].concurrency_safe
            ):
                batches[-1].calls.append(plan)
                continue
            batches.append(ToolBatch(concurrency_safe=plan.concurrency_safe, calls=[plan]))
        return batches

    def _run_batch_serially(
        self,
        batch: ToolBatch,
        *,
        step: int,
        trace_logger,
    ) -> list[ToolObservation]:
        observations: list[ToolObservation] = []
        for plan in batch.calls:
            observations.append(self._execute_plan(plan, step=step, trace_logger=trace_logger))
        return observations

    def _run_batch_concurrently(
        self,
        batch: ToolBatch,
        *,
        step: int,
        trace_logger,
    ) -> list[ToolObservation]:
        observations: dict[int, ToolObservation] = {}
        max_workers = min(len(batch.calls), self._get_max_concurrency())
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                offset: executor.submit(self._execute_plan, plan, step=step, trace_logger=trace_logger)
                for offset, plan in enumerate(batch.calls)
            }
            for offset, future in futures.items():
                observations[offset] = future.result()
        return [observations[idx] for idx in range(len(batch.calls))]

    def _execute_plan(self, plan: ToolCallPlan, *, step: int, trace_logger) -> ToolObservation:
        self._emit_tool_lifecycle(
            step=step,
            tool_name=plan.tool_name,
            tool_call_id=plan.tool_call_id,
            status="requested",
            payload={"args": plan.parsed_input},
            trace_logger=trace_logger,
        )
        if plan.parse_error is not None:
            result = self._parse_error_result(plan.parse_error)
            self._log_parse_error(trace_logger, step, plan.tool_name, plan.tool_call_id, plan.parse_error)
            self._emit_tool_lifecycle(
                step=step,
                tool_name=plan.tool_name,
                tool_call_id=plan.tool_call_id,
                status="failed",
                payload={"error": str(plan.parse_error), "args": plan.parsed_input},
                trace_logger=trace_logger,
            )
        else:
            result = self._execute_one(
                plan.tool_name,
                plan.parsed_input,
                plan.tool_call_id,
                trace_logger,
                step,
            )

        return ToolObservation(
            tool_name=plan.tool_name,
            tool_call_id=plan.tool_call_id,
            result=result,
        )

    def _execute_one(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_call_id: str,
        trace_logger,
        step: int,
    ) -> ToolResult:
        host = self.host
        self._emit_tool_lifecycle(
            step=step,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            status="started",
            payload={"args": tool_input},
            trace_logger=trace_logger,
        )
        try:
            if hasattr(host, "tool_executor") and host.tool_executor is not None:
                result = host.tool_executor.execute(
                    tool_name,
                    tool_input,
                    trace_logger=trace_logger,
                    step=step,
                )
            else:
                result = host._execute_tool(tool_name, tool_input)
            if not isinstance(result, ToolResult):
                raise TypeError(f"Tool '{tool_name}' returned unsupported result type.")
            lifecycle_status, lifecycle_payload = self._tool_lifecycle_result_payload(result)
            self._emit_tool_lifecycle(
                step=step,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                status=lifecycle_status,
                payload=lifecycle_payload,
                trace_logger=trace_logger,
            )
            return result
        except Exception as exc:
            error_result = ToolResult(
                status=ToolStatus.ERROR,
                data={},
                text=str(exc),
                error_code=ErrorCode.EXECUTION_ERROR,
                error_message=str(exc),
                stats={"time_ms": 0},
                context={"cwd": ".", "params_input": tool_input},
            )
            trace_logger.log_event(
                "error",
                {
                    "stage": "tool_execution",
                    "error_code": "EXECUTION_ERROR",
                    "message": str(exc),
                    "tool": tool_name,
                    "traceback": tb.format_exc(),
                },
                step=step,
            )
            self._emit_tool_lifecycle(
                step=step,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                status="failed",
                payload={"error": str(exc), "args": tool_input},
                trace_logger=trace_logger,
            )
            return error_result

    def _tool_lifecycle_result_payload(self, result: ToolResult) -> tuple[str, dict[str, Any]]:
        lifecycle_status = "failed" if result.status is ToolStatus.ERROR else "completed"
        return lifecycle_status, {"result": tool_result_payload(result)}

    def _parse_error_result(self, parse_err: Exception) -> ToolResult:
        message = f"Tool arguments parse error: {parse_err}"
        return ToolResult(
            status=ToolStatus.ERROR,
            data={},
            text=message,
            error_code=ErrorCode.INVALID_PARAM,
            error_message=message,
            stats={"time_ms": 0},
            context={"cwd": ".", "params_input": {}},
        )

    def _log_parse_error(
        self,
        trace_logger,
        step: int,
        tool_name: str,
        tool_call_id: str,
        parse_err: Exception,
    ) -> None:
        trace_logger.log_event(
            "error",
            {
                "stage": "tool_call_parse",
                "error_code": "INVALID_PARAM",
                "message": str(parse_err),
                "tool": tool_name,
                "tool_call_id": tool_call_id,
            },
            step=step,
        )

    def _get_max_concurrency(self) -> int:
        raw_value = os.getenv("MYCODEAGENT_MAX_TOOL_CONCURRENCY", "4")
        try:
            return max(1, int(raw_value))
        except ValueError:
            return 4

    def _get_result_budget(self) -> ToolResultBudget:
        def _read_env(name: str, default: int) -> int:
            try:
                return max(1, int(os.getenv(name, str(default))))
            except ValueError:
                return default

        return ToolResultBudget(
            max_tool_bytes=_read_env("MYCODEAGENT_MAX_TOOL_RESULT_BYTES", 50000),
            max_message_bytes=_read_env("MYCODEAGENT_MAX_TOOL_MESSAGE_BYTES", 200000),
        )

    @staticmethod
    def _result_bytes(result: ToolResult) -> int:
        return len(serialize_tool_result(result).encode("utf-8"))

    def _apply_result_budget(
        self,
        observations: list[ToolObservation],
        *,
        step: int,
        trace_logger,
    ) -> list[ToolObservation]:
        budget = self._get_result_budget()
        trace_logger.log_event(
            "tool_result_budget_start",
            {
                "tool_count": len(observations),
                "max_tool_bytes": budget.max_tool_bytes,
                "max_message_bytes": budget.max_message_bytes,
            },
            step=step,
        )
        budgeted: list[ToolObservation] = []
        replaced_count = 0
        raw_total_bytes = 0
        visible_total_bytes = 0

        for obs in observations:
            raw_result = obs.raw_result if obs.raw_result is not None else obs.result
            raw_bytes = self._result_bytes(raw_result)
            raw_total_bytes += raw_bytes
            next_obs = obs
            if raw_bytes > budget.max_tool_bytes:
                compressed = force_truncate_result(
                    obs.tool_name,
                    raw_result,
                    self.host.project_root,
                )
                visible_bytes = self._result_bytes(compressed)
                metadata = {
                    **(obs.metadata or {}),
                    "budgeted": True,
                    "replaced": True,
                    "reason": "single_tool_budget",
                    "raw_bytes": raw_bytes,
                    "visible_bytes": visible_bytes,
                }
                full_output_path = compressed.data.get("truncation", {}).get("full_output_path")
                if full_output_path:
                    metadata["full_output_path"] = full_output_path
                next_obs = ToolObservation(
                    tool_name=obs.tool_name,
                    tool_call_id=obs.tool_call_id,
                    result=compressed,
                    raw_result=raw_result,
                    metadata=metadata,
                )
                replaced_count += 1
                trace_logger.log_event(
                    "tool_result_budget_item",
                    {
                        "tool_call_id": obs.tool_call_id,
                        "reason": "single_tool_budget",
                        "replaced": True,
                        "raw_bytes": raw_bytes,
                        "visible_bytes": visible_bytes,
                    },
                    step=step,
                )
            budgeted.append(next_obs)
            visible_total_bytes += self._result_bytes(next_obs.result)

        if visible_total_bytes > budget.max_message_bytes:
            indexed = list(enumerate(budgeted))
            indexed.sort(key=lambda item: self._result_bytes(item[1].result), reverse=True)
            for idx, obs in indexed:
                if visible_total_bytes <= budget.max_message_bytes:
                    break
                if (obs.metadata or {}).get("replaced") is True:
                    continue
                source_result = obs.raw_result if obs.raw_result is not None else obs.result
                previous_visible = self._result_bytes(obs.result)
                compressed = force_truncate_result(
                    obs.tool_name,
                    source_result,
                    self.host.project_root,
                )
                visible_bytes = self._result_bytes(compressed)
                metadata = {
                    **(obs.metadata or {}),
                    "budgeted": True,
                    "replaced": True,
                    "reason": "aggregate_message_budget",
                    "raw_bytes": self._result_bytes(source_result),
                    "visible_bytes": visible_bytes,
                }
                full_output_path = compressed.data.get("truncation", {}).get("full_output_path")
                if full_output_path:
                    metadata["full_output_path"] = full_output_path
                budgeted[idx] = ToolObservation(
                    tool_name=obs.tool_name,
                    tool_call_id=obs.tool_call_id,
                    result=compressed,
                    raw_result=source_result,
                    metadata=metadata,
                )
                visible_total_bytes = visible_total_bytes - previous_visible + visible_bytes
                replaced_count += 1
                trace_logger.log_event(
                    "tool_result_budget_item",
                    {
                        "tool_call_id": obs.tool_call_id,
                        "reason": "aggregate_message_budget",
                        "replaced": True,
                        "raw_bytes": self._result_bytes(source_result),
                        "visible_bytes": visible_bytes,
                    },
                    step=step,
                )

        trace_logger.log_event(
            "tool_result_budget_end",
            {
                "tool_count": len(observations),
                "max_tool_bytes": budget.max_tool_bytes,
                "max_message_bytes": budget.max_message_bytes,
                "raw_total_bytes": raw_total_bytes,
                "visible_total_bytes": visible_total_bytes,
                "replaced_count": replaced_count,
            },
            step=step,
        )
        return budgeted

    def _normalize_empty_result(self, obs: ToolObservation) -> ToolObservation:
        if not self._is_empty_result(obs.result):
            return obs

        metadata = {**(obs.metadata or {}), "budgeted": True, "reason": "empty_result", "replaced": False}
        return ToolObservation(
            tool_name=obs.tool_name,
            tool_call_id=obs.tool_call_id,
            result=ToolResult(
                status=ToolStatus.SUCCESS,
                data={},
                text=f"{obs.tool_name} completed with no output.",
                stats={"time_ms": 0},
                context={"cwd": ".", "params_input": {}},
            ),
            raw_result=obs.result,
            metadata=metadata,
        )

    def _apply_observation_limit(self, obs: ToolObservation) -> ToolObservation:
        truncated = truncate_result(
            obs.tool_name,
            obs.result,
            getattr(self.host, "project_root", None),
        )
        if truncated is obs.result:
            return obs

        raw_result = obs.raw_result if obs.raw_result is not None else obs.result
        return ToolObservation(
            tool_name=obs.tool_name,
            tool_call_id=obs.tool_call_id,
            result=truncated,
            raw_result=raw_result,
            metadata={
                **(obs.metadata or {}),
                "reason": "observation_limit",
                "raw_bytes": self._result_bytes(raw_result),
                "visible_bytes": self._result_bytes(truncated),
            },
        )

    @staticmethod
    def _is_empty_result(result: ToolResult) -> bool:
        return (
            result.status is not ToolStatus.ERROR
            and not result.text.strip()
            and not result.data
        )

    def _log_plan(self, trace_logger, step: int, batches: list[ToolBatch]) -> None:
        trace_logger.log_event(
            "tool_orchestration_plan",
            {
                "batch_count": len(batches),
                "batches": [
                    {
                        "concurrency_safe": batch.concurrency_safe,
                        "tool_names": [plan.tool_name for plan in batch.calls],
                    }
                    for batch in batches
                ],
            },
            step=step,
        )

    def _log_batch_start(self, trace_logger, step: int, batch_index: int, batch: ToolBatch) -> None:
        trace_logger.log_event(
            "tool_batch_start",
            {
                "batch_index": batch_index,
                "concurrency_safe": batch.concurrency_safe,
                "tool_count": len(batch.calls),
                "tool_names": [plan.tool_name for plan in batch.calls],
            },
            step=step,
        )

    def _log_batch_end(
        self,
        trace_logger,
        step: int,
        batch_index: int,
        batch: ToolBatch,
        observations: list[ToolObservation],
    ) -> None:
        trace_logger.log_event(
            "tool_batch_end",
            {
                "batch_index": batch_index,
                "concurrency_safe": batch.concurrency_safe,
                "tool_count": len(batch.calls),
                "completed_count": len(observations),
            },
            step=step,
        )
