"""Tool call orchestration boundary for the agent runtime."""

from __future__ import annotations

import json
import os
import traceback as tb
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolObservation:
    tool_name: str
    tool_call_id: str
    observation: str


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

    SAFE_TOOL_NAMES = {"Read", "Grep", "Glob", "ListFiles"}
    UNSAFE_TOOL_NAMES = {"Write", "Edit", "MultiEdit", "Bash", "Task", "Skill", "TodoWrite"}

    def __init__(self, host: Any):
        self.host = host

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

        return observations

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
            parsed_input, parse_error = self.host._ensure_json_input(raw_args)
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
        if plan.parse_error is not None:
            observation = self._parse_error_observation(plan.parse_error)
            self._log_parse_error(trace_logger, step, plan.tool_name, plan.tool_call_id, plan.parse_error)
        else:
            trace_logger.log_event(
                "tool_call",
                {"tool": plan.tool_name, "args": plan.parsed_input, "tool_call_id": plan.tool_call_id},
                step=step,
            )
            observation = self._execute_one(
                plan.tool_name,
                plan.parsed_input,
                trace_logger,
                step,
            )

        return ToolObservation(
            tool_name=plan.tool_name,
            tool_call_id=plan.tool_call_id,
            observation=observation,
        )

    def _execute_one(self, tool_name: str, tool_input: dict[str, Any], trace_logger, step: int) -> str:
        host = self.host
        try:
            if hasattr(host, "tool_executor") and host.tool_executor is not None:
                observation = host.tool_executor.execute(tool_name, tool_input)
            else:
                observation = host._execute_tool(tool_name, tool_input)
            self._log_tool_result(trace_logger, step, tool_name, observation)
            return observation
        except Exception as exc:
            error_result = {
                "status": "error",
                "error": {"code": "EXECUTION_ERROR", "message": str(exc)},
                "data": {},
            }
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
            return json.dumps(error_result, ensure_ascii=False)

    def _log_tool_result(self, trace_logger, step: int, tool_name: str, observation: str) -> None:
        try:
            result_obj = json.loads(observation)
            trace_logger.log_event("tool_result", {"tool": tool_name, "result": result_obj}, step=step)
        except json.JSONDecodeError:
            trace_logger.log_event(
                "tool_result",
                {"tool": tool_name, "result": {"text": observation}},
                step=step,
            )

    def _parse_error_observation(self, parse_err: Exception) -> str:
        error_result = {
            "status": "error",
            "error": {
                "code": "INVALID_PARAM",
                "message": f"Tool arguments parse error: {parse_err}",
            },
            "data": {},
        }
        return json.dumps(error_result, ensure_ascii=False)

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
