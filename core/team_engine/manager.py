"""Team orchestration manager for AgentTeams MVP."""

from __future__ import annotations

import uuid
import os
import threading
import time
from pathlib import Path
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

from .events import Event
from .protocol import (
    EVENT_MESSAGE_ACK,
    EVENT_MESSAGE_SENT,
    EVENT_PLAN_APPROVAL_RESPONSE,
    EVENT_SHUTDOWN_REQUEST,
    EVENT_SHUTDOWN_RESPONSE,
    EVENT_WORK_ITEM_ASSIGNED,
    EVENT_WORK_ITEM_COMPLETED,
    EVENT_WORK_ITEM_FAILED,
    EVENT_WORK_ITEM_STARTED,
    MESSAGE_TYPES,
    MESSAGE_TYPE_BROADCAST,
    MESSAGE_TYPE_MESSAGE,
    MESSAGE_TYPE_PLAN_APPROVAL_RESPONSE,
    MESSAGE_TYPE_SHUTDOWN_REQUEST,
    MESSAGE_TYPE_SHUTDOWN_RESPONSE,
    TASK_STATUS_CANCELED,
    TASK_STATUS_COMPLETED,
    MESSAGE_STATUS_DELIVERED,
    MESSAGE_STATUS_PENDING,
    MESSAGE_STATUS_PROCESSED,
    WORK_ITEM_STATUS_FAILED,
    WORK_ITEM_STATUS_QUEUED,
    WORK_ITEM_STATUS_RUNNING,
    WORK_ITEM_STATUS_SUCCEEDED,
    WORK_ITEM_STATUSES,
    normalize_member,
    sanitize_name,
)
from .store import TeamStore
from .task_board_store import TaskBoardStore
from .worker import TeammateWorker
from .turn_executor import TurnExecutor
from tools.registry import ToolRegistry


class TeamManagerError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class TeamManager:
    def __init__(
        self,
        project_root: str,
        team_store_dir: str = ".teams",
        task_store_dir: str = ".tasks",
        store: Optional[TeamStore] = None,
        llm: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
        work_executor: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        max_llm_concurrency: Optional[int] = None,
    ):
        self.store = store or TeamStore(
            project_root=project_root,
            team_store_dir=team_store_dir,
            task_store_dir=task_store_dir,
        )
        self.task_board = TaskBoardStore(
            project_root=project_root,
            task_store_dir=task_store_dir,
        )
        self.project_root = project_root
        self.llm = llm
        self.tool_registry = tool_registry
        self.work_executor = work_executor
        self._workers: Dict[tuple[str, str], Any] = {}
        self._events: Dict[str, List[Event]] = defaultdict(list)
        self._message_status: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        self._recent_errors: Dict[str, str] = {}
        self._processed_by_member: Dict[tuple[str, str], set[str]] = defaultdict(set)
        max_parallel = max_llm_concurrency or int(os.getenv("TEAM_LLM_MAX_CONCURRENCY", "4"))
        self._llm_semaphore = threading.Semaphore(max(1, max_parallel))

    def create_team(self, team_name: str, members: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        normalized_members = [normalize_member(m) for m in (members or [{"name": "lead"}])]
        member_names = [m["name"] for m in normalized_members]
        if len(member_names) != len(set(member_names)):
            raise TeamManagerError("INVALID_PARAM", "duplicate member names are not allowed")
        try:
            cfg = self.store.create_team(normalized_team, members=normalized_members)
        except FileExistsError as exc:
            raise TeamManagerError("CONFLICT", str(exc)) from exc
        return cfg

    def delete_team(self, team_name: str) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        self._read_team_or_raise(normalized_team)
        self._emit(normalized_team, EVENT_SHUTDOWN_REQUEST, {"team_name": normalized_team})
        for (team, member), worker in list(self._workers.items()):
            if team != normalized_team:
                continue
            try:
                if hasattr(worker, "stop"):
                    worker.stop()
                if hasattr(worker, "join"):
                    worker.join(timeout=2.0)
            finally:
                self._workers.pop((team, member), None)
        self.store.delete_team(normalized_team)
        self._message_status.pop(normalized_team, None)
        self._recent_errors.pop(normalized_team, None)
        for key in list(self._processed_by_member.keys()):
            if key[0] == normalized_team:
                self._processed_by_member.pop(key, None)
        return {"team_name": normalized_team, "deleted": True}

    def spawn_teammate(
        self,
        team_name: str,
        teammate_name: str,
        role: str = "developer",
        tool_policy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        teammate = normalize_member(
            {
                "name": teammate_name,
                "role": role,
                "tool_policy": tool_policy or {"allowlist": [], "denylist": ["Task"]},
            }
        )
        cfg = self._read_team_or_raise(normalized_team)
        names = {m["name"] for m in cfg.get("members", [])}
        if teammate["name"] in names:
            raise TeamManagerError("INVALID_PARAM", f"duplicate teammate name: {teammate['name']}")
        cfg["members"] = list(cfg.get("members", [])) + [teammate]
        self.store.update_team(normalized_team, cfg)
        self._start_worker(normalized_team, teammate["name"])
        return teammate

    def send_message(
        self,
        team_name: str,
        from_member: str,
        to_member: str,
        text: str,
        message_type: str = MESSAGE_TYPE_MESSAGE,
        summary: str = "",
        request_id: str = "",
    ) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        sender = sanitize_name(from_member)
        message_kind = str(message_type or MESSAGE_TYPE_MESSAGE).strip().lower()
        summary_text = str(summary or "").strip()
        request_ref = str(request_id or "").strip()
        if not text or not str(text).strip():
            raise TeamManagerError("INVALID_PARAM", "text is required")
        if message_kind not in MESSAGE_TYPES:
            raise TeamManagerError("INVALID_PARAM", f"unsupported message type: {message_kind}")
        if message_kind == MESSAGE_TYPE_BROADCAST and not summary_text:
            raise TeamManagerError("INVALID_PARAM", "summary is required when message type is broadcast")
        if message_kind in {MESSAGE_TYPE_SHUTDOWN_RESPONSE, MESSAGE_TYPE_PLAN_APPROVAL_RESPONSE} and not request_ref:
            raise TeamManagerError("INVALID_PARAM", f"request_id is required when message type is {message_kind}")
        if message_kind == MESSAGE_TYPE_SHUTDOWN_REQUEST and not request_ref:
            request_ref = f"req_{uuid.uuid4().hex[:10]}"

        cfg = self._read_team_or_raise(normalized_team)
        members = {m["name"] for m in cfg.get("members", [])}
        if sender not in members:
            raise TeamManagerError("NOT_FOUND", f"member not found: {sender}")
        recipients: List[str]
        if message_kind == MESSAGE_TYPE_BROADCAST:
            recipients = sorted(name for name in members if name != sender)
            if not recipients:
                raise TeamManagerError("INVALID_PARAM", "broadcast requires at least one recipient")
        else:
            recipient = sanitize_name(to_member)
            if recipient not in members:
                raise TeamManagerError("NOT_FOUND", f"member not found: {sender}->{recipient}")
            recipients = [recipient]

        message_ids: List[str] = []
        for recipient in recipients:
            message_id = f"msg_{uuid.uuid4().hex}"
            pending = {
                "message_id": message_id,
                "team_name": normalized_team,
                "from": sender,
                "to": recipient,
                "text": str(text),
                "type": message_kind,
                "summary": summary_text,
                "request_id": request_ref,
                "status": MESSAGE_STATUS_PENDING,
            }
            self._message_status[normalized_team][message_id] = dict(pending)
            delivered = dict(pending)
            delivered["status"] = MESSAGE_STATUS_DELIVERED
            self.store.append_inbox_message(normalized_team, recipient, delivered)
            self._message_status[normalized_team][message_id] = delivered
            event_type = EVENT_MESSAGE_SENT
            if message_kind == MESSAGE_TYPE_SHUTDOWN_REQUEST:
                event_type = EVENT_SHUTDOWN_REQUEST
            elif message_kind == MESSAGE_TYPE_SHUTDOWN_RESPONSE:
                event_type = EVENT_SHUTDOWN_RESPONSE
            elif message_kind == MESSAGE_TYPE_PLAN_APPROVAL_RESPONSE:
                event_type = EVENT_PLAN_APPROVAL_RESPONSE
            self._emit(
                normalized_team,
                event_type,
                {
                    "message_id": message_id,
                    "from": sender,
                    "to": recipient,
                    "type": message_kind,
                    "status": MESSAGE_STATUS_DELIVERED,
                    "request_id": request_ref,
                },
            )
            message_ids.append(message_id)

        result: Dict[str, Any] = {
            "message_id": message_ids[0],
            "message_ids": message_ids,
            "status": MESSAGE_STATUS_DELIVERED,
            "type": message_kind,
            "request_id": request_ref,
            "summary": summary_text,
        }
        if message_kind == MESSAGE_TYPE_BROADCAST:
            result["recipient_count"] = len(recipients)
        return result

    def mark_message_processed(self, team_name: str, message_id: str, processed_by: str) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        statuses = self._message_status.get(normalized_team, {})
        if message_id not in statuses:
            raise TeamManagerError("NOT_FOUND", f"message not found: {message_id}")
        state = dict(statuses[message_id])
        state["status"] = MESSAGE_STATUS_PROCESSED
        state["processed_by"] = sanitize_name(processed_by)
        statuses[message_id] = state
        self._emit(
            normalized_team,
            EVENT_MESSAGE_ACK,
            {"message_id": message_id, "status": MESSAGE_STATUS_PROCESSED, "processed_by": state["processed_by"]},
        )
        return state

    def get_status(self, team_name: str) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        cfg = self._read_team_or_raise(normalized_team)
        statuses = self._message_status.get(normalized_team, {})
        counts = {
            MESSAGE_STATUS_PENDING: 0,
            MESSAGE_STATUS_DELIVERED: 0,
            MESSAGE_STATUS_PROCESSED: 0,
        }
        for value in statuses.values():
            status = value.get("status")
            if status in counts:
                counts[status] += 1
        recent_messages = list(statuses.values())[-20:]
        return {
            "team_name": normalized_team,
            "members": cfg.get("members", []),
            "message_counts": counts,
            "recent_messages": recent_messages,
            "last_error": self._recent_errors.get(normalized_team),
        }

    def create_board_task(
        self,
        team_name: str,
        subject: str,
        description: str = "",
        owner: str = "",
        blocked_by: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        self._read_team_or_raise(normalized_team)
        try:
            return self.task_board.create_task(
                normalized_team,
                subject=subject,
                description=description,
                owner=owner,
                blocked_by=blocked_by or [],
            )
        except FileNotFoundError as exc:
            raise TeamManagerError("NOT_FOUND", str(exc)) from exc
        except ValueError as exc:
            raise TeamManagerError("INVALID_PARAM", str(exc)) from exc

    def get_board_task(self, team_name: str, task_id: str) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        self._read_team_or_raise(normalized_team)
        try:
            return self.task_board.get_task(normalized_team, str(task_id))
        except FileNotFoundError as exc:
            raise TeamManagerError("NOT_FOUND", str(exc)) from exc

    def list_board_tasks(self, team_name: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_team = sanitize_name(team_name)
        self._read_team_or_raise(normalized_team)
        return self.task_board.list_tasks(normalized_team, status=status)

    def update_board_task(
        self,
        team_name: str,
        task_id: str,
        status: Optional[str] = None,
        owner: Optional[str] = None,
        subject: Optional[str] = None,
        description: Optional[str] = None,
        add_blocked_by: Optional[List[str]] = None,
        add_blocks: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        self._read_team_or_raise(normalized_team)
        try:
            return self.task_board.update_task(
                normalized_team,
                task_id=str(task_id),
                status=status,
                owner=owner,
                subject=subject,
                description=description,
                add_blocked_by=add_blocked_by or [],
                add_blocks=add_blocks or [],
            )
        except FileNotFoundError as exc:
            raise TeamManagerError("NOT_FOUND", str(exc)) from exc
        except ValueError as exc:
            raise TeamManagerError("INVALID_PARAM", str(exc)) from exc

    def claim_next_board_task(self, team_name: str, owner: str) -> Optional[Dict[str, Any]]:
        normalized_team = sanitize_name(team_name)
        self._read_team_or_raise(normalized_team)
        try:
            return self.task_board.claim_next_task(normalized_team, owner=owner)
        except ValueError as exc:
            raise TeamManagerError("INVALID_PARAM", str(exc)) from exc

    def drain_events(self, team_name: Optional[str] = None) -> List[Dict[str, Any]]:
        if team_name is not None:
            normalized_team = sanitize_name(team_name)
            items = self._events.get(normalized_team, [])
            self._events[normalized_team] = []
            return [event.as_dict() for event in items]

        drained: List[Dict[str, Any]] = []
        for key in list(self._events.keys()):
            items = self._events.get(key, [])
            self._events[key] = []
            drained.extend(event.as_dict() for event in items)
        return drained

    def fanout_work(self, team_name: str, tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        cfg = self._read_team_or_raise(normalized_team)
        members = {m["name"] for m in cfg.get("members", [])}
        if not isinstance(tasks, list) or not tasks:
            raise TeamManagerError("INVALID_PARAM", "tasks must be a non-empty list")

        created: List[Dict[str, Any]] = []
        for idx, task in enumerate(tasks):
            if not isinstance(task, dict):
                raise TeamManagerError("INVALID_PARAM", f"task at index {idx} must be an object")
            owner = task.get("owner")
            title = task.get("title")
            instruction = task.get("instruction")
            if not isinstance(owner, str) or not owner.strip():
                raise TeamManagerError("INVALID_PARAM", f"task[{idx}].owner is required")
            owner_name = sanitize_name(owner)
            if owner_name not in members:
                raise TeamManagerError("NOT_FOUND", f"owner not in team: {owner_name}")
            if owner_name == "lead":
                raise TeamManagerError("INVALID_PARAM", "owner cannot be lead for fanout work")
            if not isinstance(title, str) or not title.strip():
                raise TeamManagerError("INVALID_PARAM", f"task[{idx}].title is required")
            if not isinstance(instruction, str) or not instruction.strip():
                raise TeamManagerError("INVALID_PARAM", f"task[{idx}].instruction is required")
            payload = task.get("payload")
            item = self.store.create_work_item(
                normalized_team,
                owner=owner_name,
                title=title,
                instruction=instruction,
                payload=payload if isinstance(payload, dict) else None,
            )
            created.append(item)
            self._emit(
                normalized_team,
                EVENT_WORK_ITEM_ASSIGNED,
                {"work_id": item["work_id"], "owner": owner_name, "status": item["status"]},
            )

        return {
            "dispatch_id": f"dispatch_{uuid.uuid4().hex}",
            "team_name": normalized_team,
            "work_items": created,
        }

    def collect_work(self, team_name: str, work_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        self._read_team_or_raise(normalized_team)
        items = self.store.list_work_items(normalized_team)
        if work_ids:
            wanted = {str(x) for x in work_ids}
            items = [item for item in items if item.get("work_id") in wanted]

        counts = {status: 0 for status in WORK_ITEM_STATUSES}
        groups: Dict[str, List[Dict[str, Any]]] = {status: [] for status in WORK_ITEM_STATUSES}
        for item in items:
            status = str(item.get("status") or "")
            if status not in counts:
                continue
            counts[status] += 1
            groups[status].append(item)

        return {
            "team_name": normalized_team,
            "total": len(items),
            "counts": counts,
            "groups": groups,
        }

    def retry_failed_work(self, team_name: str, work_id: str) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        self._read_team_or_raise(normalized_team)
        try:
            item = self.store.update_work_item_status(
                normalized_team,
                work_id=work_id,
                status=WORK_ITEM_STATUS_QUEUED,
            )
        except FileNotFoundError as exc:
            raise TeamManagerError("NOT_FOUND", str(exc)) from exc
        self._emit(
            normalized_team,
            EVENT_WORK_ITEM_ASSIGNED,
            {"work_id": work_id, "owner": item.get("owner"), "status": WORK_ITEM_STATUS_QUEUED},
        )
        return item

    def has_worker(self, team_name: str, teammate_name: str) -> bool:
        key = (sanitize_name(team_name), sanitize_name(teammate_name))
        worker = self._workers.get(key)
        return bool(worker and worker.is_alive())

    def export_state(self) -> Dict[str, Any]:
        teams = self.store.list_teams()
        return {
            "teams": {name: self.get_status(name) for name in teams},
            "work_items": {
                name: self.collect_work(name).get("counts", {})
                for name in teams
            },
        }

    def import_state(self, state: Optional[Dict[str, Any]]) -> None:
        snapshot = state or {}
        names = set(self.store.list_teams())
        snapshot_teams = snapshot.get("teams")
        if isinstance(snapshot_teams, dict):
            names.update(snapshot_teams.keys())
        for team_name in sorted(names):
            try:
                cfg = self.store.read_team(team_name)
            except FileNotFoundError:
                continue
            self.store.requeue_running_work_items(team_name)
            for member in cfg.get("members", []):
                name = str(member.get("name") or "")
                if not name or name == "lead":
                    continue
                self._start_worker(team_name, name)

    def _read_team_or_raise(self, team_name: str) -> Dict[str, Any]:
        try:
            return self.store.read_team(team_name)
        except FileNotFoundError as exc:
            raise TeamManagerError("NOT_FOUND", f"team not found: {team_name}") from exc

    def _emit(self, team_name: str, event_type: str, payload: Dict[str, Any]) -> None:
        self._events[team_name].append(Event.create(team=team_name, event_type=event_type, payload=payload))

    def _start_worker(self, team_name: str, teammate_name: str) -> None:
        key = (team_name, teammate_name)
        existing = self._workers.get(key)
        if existing and existing.is_alive():
            return
        worker = TeammateWorker(
            team_name=team_name,
            teammate_name=teammate_name,
            poll_fn=lambda: self._process_member_inbox(team_name, teammate_name),
            poll_interval_s=0.02,
            idle_timeout_s=60.0,
        )
        worker.start()
        self._workers[key] = worker

    def _process_member_inbox(self, team_name: str, teammate_name: str) -> bool:
        processed_ids = self._processed_by_member[(team_name, teammate_name)]
        rows = self.store.read_inbox_messages(team_name, teammate_name)
        did_work = False
        for row in rows:
            message_id = str(row.get("message_id") or "")
            if not message_id or message_id in processed_ids:
                continue
            status = str(row.get("status") or "")
            if status not in {MESSAGE_STATUS_PENDING, MESSAGE_STATUS_DELIVERED}:
                continue
            self.mark_message_processed(team_name, message_id, processed_by=teammate_name)
            processed_ids.add(message_id)
            did_work = True
        did_work = self._process_next_work_item(team_name, teammate_name) or did_work
        if not did_work:
            did_work = self._claim_board_task_to_work_item(team_name, teammate_name) or did_work
        return did_work

    def _process_next_work_item(self, team_name: str, teammate_name: str) -> bool:
        queued = self.store.list_work_items(team_name, owner=teammate_name, status=WORK_ITEM_STATUS_QUEUED)
        if not queued:
            return False
        item = queued[0]
        work_id = str(item.get("work_id"))
        try:
            running_item = self.store.update_work_item_status(
                team_name,
                work_id=work_id,
                status=WORK_ITEM_STATUS_RUNNING,
            )
        except FileNotFoundError:
            return False
        self._emit(
            team_name,
            EVENT_WORK_ITEM_STARTED,
            {"work_id": work_id, "owner": teammate_name, "status": WORK_ITEM_STATUS_RUNNING},
        )

        try:
            with self._llm_semaphore:
                execution = self._execute_work_item(team_name, teammate_name, running_item)
            result = execution.get("result")
            updated = self.store.update_work_item_status(
                team_name,
                work_id=work_id,
                status=WORK_ITEM_STATUS_SUCCEEDED,
                result=result,
            )
            payload = running_item.get("payload") if isinstance(running_item.get("payload"), dict) else {}
            board_task_id = str(payload.get("board_task_id") or "").strip()
            if board_task_id:
                try:
                    self.update_board_task(
                        team_name,
                        task_id=board_task_id,
                        status=TASK_STATUS_COMPLETED,
                        owner=teammate_name,
                    )
                except TeamManagerError:
                    pass
            self._emit(
                team_name,
                EVENT_WORK_ITEM_COMPLETED,
                {"work_id": work_id, "owner": teammate_name, "status": WORK_ITEM_STATUS_SUCCEEDED},
            )
            _ = updated
        except Exception as exc:
            self.store.update_work_item_status(
                team_name,
                work_id=work_id,
                status=WORK_ITEM_STATUS_FAILED,
                error={"message": str(exc)},
            )
            payload = running_item.get("payload") if isinstance(running_item.get("payload"), dict) else {}
            board_task_id = str(payload.get("board_task_id") or "").strip()
            if board_task_id:
                try:
                    self.update_board_task(
                        team_name,
                        task_id=board_task_id,
                        status=TASK_STATUS_CANCELED,
                        owner=teammate_name,
                    )
                except TeamManagerError:
                    pass
            self._recent_errors[team_name] = str(exc)
            self._emit(
                team_name,
                EVENT_WORK_ITEM_FAILED,
                {"work_id": work_id, "owner": teammate_name, "status": WORK_ITEM_STATUS_FAILED},
            )
        return True

    def _claim_board_task_to_work_item(self, team_name: str, teammate_name: str) -> bool:
        claimed = self.claim_next_board_task(team_name, owner=teammate_name)
        if not claimed:
            return False
        task_id = str(claimed.get("id"))
        subject = str(claimed.get("subject") or f"task-{task_id}")
        description = str(claimed.get("description") or "").strip()
        instruction = description or subject
        item = self.store.create_work_item(
            team_name,
            owner=teammate_name,
            title=subject,
            instruction=instruction,
            payload={"board_task_id": task_id},
        )
        self._emit(
            team_name,
            EVENT_WORK_ITEM_ASSIGNED,
            {"work_id": item["work_id"], "owner": teammate_name, "status": item["status"]},
        )
        return True

    def _execute_work_item(self, team_name: str, teammate_name: str, work_item: Dict[str, Any]) -> Dict[str, Any]:
        if self.work_executor:
            payload = self.work_executor(dict(work_item))
            if isinstance(payload, dict):
                return payload
            return {"result": payload}
        if self.llm is None or self.tool_registry is None:
            # Fallback behavior when no executor is wired yet.
            return {
                "result": f"[{team_name}/{teammate_name}] completed: {work_item.get('title', '')}",
            }

        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                return self._run_turn_executor_work(team_name, teammate_name, work_item)
            except Exception as exc:  # pragma: no cover - defensive
                last_error = exc
                message = str(exc).lower()
                retryable = "rate limit" in message or "429" in message or "timeout" in message
                if not retryable or attempt >= 2:
                    break
                time.sleep(0.2 * (2 ** attempt))
        raise RuntimeError(str(last_error) if last_error else "work item execution failed")

    def _run_turn_executor_work(self, team_name: str, teammate_name: str, work_item: Dict[str, Any]) -> Dict[str, Any]:
        registry, denied_tools = self._build_teammate_registry(team_name, teammate_name)
        executor = TurnExecutor(
            llm=self.llm,
            tool_registry=registry,
            project_root=Path(self.project_root),
            denied_tools=denied_tools,
        )
        instruction = str(work_item.get("instruction") or "")
        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a teammate worker. Complete the assigned work item. "
                    "Task recursion is forbidden."
                ),
            },
            {"role": "user", "content": instruction},
        ]
        tool_usage: Dict[str, int] = {}
        last_tool_msg = ""
        max_steps = int(os.getenv("TEAM_WORKER_MAX_STEPS", "8"))
        for _ in range(max(1, max_steps)):
            turn = executor.execute_turn(messages, tool_usage=tool_usage)
            messages = turn["messages"]
            tool_messages = [m for m in messages if m.get("role") == "tool"]
            if tool_messages:
                last_tool_msg = str(tool_messages[-1].get("content", ""))
            if turn["done"]:
                final_result = str(turn.get("final_result") or "").strip()
                if final_result:
                    return {"result": final_result, "tool_usage": tool_usage}
                break
        if last_tool_msg:
            return {"result": last_tool_msg, "tool_usage": tool_usage}
        return {"result": "", "tool_usage": tool_usage}

    def _build_teammate_registry(self, team_name: str, teammate_name: str) -> tuple[ToolRegistry, set[str]]:
        cfg = self._read_team_or_raise(team_name)
        teammate = None
        for member in cfg.get("members", []):
            if str(member.get("name") or "") == teammate_name:
                teammate = member
                break
        policy = (teammate or {}).get("tool_policy") if isinstance(teammate, dict) else {}
        if not isinstance(policy, dict):
            policy = {}
        allowlist = policy.get("allowlist")
        denylist = policy.get("denylist")
        allowset = {str(x) for x in allowlist} if isinstance(allowlist, list) else set()
        denyset = {str(x) for x in denylist} if isinstance(denylist, list) else set()
        denyset.add("Task")

        filtered = ToolRegistry()
        for tool in self.tool_registry.get_all_tools():
            name = tool.name
            if name in denyset:
                continue
            if allowset and name not in allowset:
                continue
            filtered.register_tool(tool)
        return filtered, denyset
