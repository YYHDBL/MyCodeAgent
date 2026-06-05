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
    raw_observation: str | None = None
    metadata: dict[str, Any] | None = None


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

        observations = [self._normalize_empty_result(obs) for obs in observations]
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

    def _byte_len(self, text: str) -> int:
        return len((text or "").encode("utf-8"))

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
            raw_text = obs.raw_observation if obs.raw_observation is not None else obs.observation
            raw_bytes = self._byte_len(raw_text)
            raw_total_bytes += raw_bytes
            next_obs = obs
            if raw_bytes > budget.max_tool_bytes:
                from runtime.observation_store import force_truncate_observation

                compressed = force_truncate_observation(
                    obs.tool_name,
                    raw_text,
                    self.host.project_root,
                )
                visible_bytes = self._byte_len(compressed)
                metadata = {
                    **(obs.metadata or {}),
                    "budgeted": True,
                    "replaced": True,
                    "reason": "single_tool_budget",
                    "raw_bytes": raw_bytes,
                    "visible_bytes": visible_bytes,
                }
                try:
                    parsed = json.loads(compressed)
                    full_output_path = (
                        parsed.get("data", {})
                        .get("truncation", {})
                        .get("full_output_path")
                    )
                    if full_output_path:
                        metadata["full_output_path"] = full_output_path
                except json.JSONDecodeError:
                    pass
                next_obs = ToolObservation(
                    tool_name=obs.tool_name,
                    tool_call_id=obs.tool_call_id,
                    observation=compressed,
                    raw_observation=raw_text,
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
            visible_total_bytes += self._byte_len(next_obs.observation)

        if visible_total_bytes > budget.max_message_bytes:
            indexed = list(enumerate(budgeted))
            indexed.sort(key=lambda item: self._byte_len(item[1].observation), reverse=True)
            for idx, obs in indexed:
                if visible_total_bytes <= budget.max_message_bytes:
                    break
                if (obs.metadata or {}).get("replaced") is True:
                    continue
                from runtime.observation_store import force_truncate_observation

                source_text = obs.raw_observation if obs.raw_observation is not None else obs.observation
                previous_visible = self._byte_len(obs.observation)
                compressed = force_truncate_observation(
                    obs.tool_name,
                    source_text,
                    self.host.project_root,
                )
                visible_bytes = self._byte_len(compressed)
                metadata = {
                    **(obs.metadata or {}),
                    "budgeted": True,
                    "replaced": True,
                    "reason": "aggregate_message_budget",
                    "raw_bytes": self._byte_len(source_text),
                    "visible_bytes": visible_bytes,
                }
                try:
                    parsed = json.loads(compressed)
                    full_output_path = (
                        parsed.get("data", {})
                        .get("truncation", {})
                        .get("full_output_path")
                    )
                    if full_output_path:
                        metadata["full_output_path"] = full_output_path
                except json.JSONDecodeError:
                    pass
                budgeted[idx] = ToolObservation(
                    tool_name=obs.tool_name,
                    tool_call_id=obs.tool_call_id,
                    observation=compressed,
                    raw_observation=source_text,
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
                        "raw_bytes": self._byte_len(source_text),
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
        if not self._is_empty_observation(obs.observation):
            return obs

        payload = {
            "status": "success",
            "data": {},
            "text": f"{obs.tool_name} completed with no output.",
        }
        metadata = {**(obs.metadata or {}), "budgeted": True, "reason": "empty_result", "replaced": False}
        return ToolObservation(
            tool_name=obs.tool_name,
            tool_call_id=obs.tool_call_id,
            observation=json.dumps(payload, ensure_ascii=False),
            raw_observation=obs.observation,
            metadata=metadata,
        )

    def _is_empty_observation(self, text: str) -> bool:
        if not text or not str(text).strip():
            return True
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return False
        if not isinstance(parsed, dict):
            return False
        if parsed.get("error"):
            return False
        payload_text = parsed.get("text")
        payload_data = parsed.get("data")
        if isinstance(payload_text, str) and payload_text.strip():
            return False
        if payload_data:
            return False
        return True

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
