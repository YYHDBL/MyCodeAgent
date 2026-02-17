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
    EVENT_PLAN_APPROVAL_REQUESTED,
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
from .message_router import MessageRouter
from .task_board import TaskBoardService
from .approval import ApprovalService
from .supervisor import WorkerSupervisor
from .execution import ExecutionService
from .errors import TeamEngineError


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
        self._events: Dict[str, List[Event]] = defaultdict(list)
        self._recent_errors: Dict[str, str] = {}
        self._processed_by_member: Dict[tuple[str, str], set[str]] = defaultdict(set)
        max_parallel = max_llm_concurrency or int(os.getenv("TEAM_LLM_MAX_CONCURRENCY", "4"))
        self._llm_semaphore = threading.Semaphore(max(1, max_parallel))
        self.message_router = MessageRouter(store=self.store, emit_fn=self._emit)
        self.task_board_service = TaskBoardService(self.task_board)
        self.approval_service = ApprovalService()
        self.worker_supervisor = WorkerSupervisor()
        self.execution_service = ExecutionService(
            project_root=self.project_root,
            llm=self.llm,
            tool_registry=self.tool_registry,
            work_executor=self.work_executor,
            read_team_fn=self._read_team_or_raise,
            llm_semaphore=self._llm_semaphore,
        )
        # Backward-compatible aliases used by existing tests.
        self._workers = self.worker_supervisor.workers
        self._message_status = self.message_router.message_status
        self._plan_approvals = self.approval_service.requests
        self._plan_approvals_lock = self.approval_service.lock

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
        self.worker_supervisor.stop_team(normalized_team, join_timeout_s=2.0)
        self.store.delete_team(normalized_team)
        self.message_router.clear_team(normalized_team)
        self.approval_service.clear_team(normalized_team)
        self._recent_errors.pop(normalized_team, None)
        for key in list(self._processed_by_member.keys()):
            if key[0] == normalized_team:
                self._processed_by_member.pop(key, None)
        return {"team_name": normalized_team, "deleted": True}

    def cleanup_team(self, team_name: str, force: bool = False) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        self._read_team_or_raise(normalized_team)
        active_members = self.worker_supervisor.active_workers(normalized_team)
        active = [f"{normalized_team}:{member}" for member in active_members]
        if active and not force:
            raise TeamManagerError(
                "CONFLICT",
                "team cleanup blocked: active teammates still running. shutdown teammates first or use force=true.",
            )
        return self.delete_team(normalized_team)

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
        approved: Optional[bool] = None,
        feedback: str = "",
    ) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        cfg = self._read_team_or_raise(normalized_team)
        members = {m["name"] for m in cfg.get("members", [])}
        try:
            return self.message_router.send_message(
                team_name=normalized_team,
                members=members,
                from_member=from_member,
                to_member=to_member,
                text=text,
                message_type=message_type,
                summary=summary,
                request_id=request_id,
                approved=approved,
                feedback=feedback,
            )
        except TeamEngineError as exc:
            raise TeamManagerError(exc.code, exc.message) from exc

    def mark_message_processed(self, team_name: str, message_id: str, processed_by: str) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        try:
            return self.message_router.mark_processed(normalized_team, message_id, processed_by=processed_by)
        except TeamEngineError as exc:
            raise TeamManagerError(exc.code, exc.message) from exc

    def get_status(self, team_name: str) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        cfg = self._read_team_or_raise(normalized_team)
        statuses = self.message_router.team_messages(normalized_team)
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
            return self.task_board_service.create_task(
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
            return self.task_board_service.get_task(normalized_team, str(task_id))
        except FileNotFoundError as exc:
            raise TeamManagerError("NOT_FOUND", str(exc)) from exc

    def list_board_tasks(self, team_name: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_team = sanitize_name(team_name)
        self._read_team_or_raise(normalized_team)
        return self.task_board_service.list_tasks(normalized_team, status=status)

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
            return self.task_board_service.update_task(
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
            return self.task_board_service.claim_next_task(normalized_team, owner=owner)
        except ValueError as exc:
            raise TeamManagerError("INVALID_PARAM", str(exc)) from exc

    def list_plan_approvals(self, team_name: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_team = sanitize_name(team_name)
        self._read_team_or_raise(normalized_team)
        return self.approval_service.list_requests(normalized_team, status=status)

    def respond_plan_approval(
        self,
        team_name: str,
        request_id: str,
        approved: bool,
        feedback: str = "",
        from_member: str = "lead",
    ) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        self._read_team_or_raise(normalized_team)
        req = str(request_id or "").strip()
        if not req:
            raise TeamManagerError("INVALID_PARAM", "request_id is required")
        if not isinstance(approved, bool):
            raise TeamManagerError("INVALID_PARAM", "approved must be boolean")

        row = self.approval_service.get_request(req)
        if not row or row.get("team_name") != normalized_team:
            raise TeamManagerError("NOT_FOUND", f"plan approval request not found: {req}")
        if row.get("status") not in {"pending", "approved", "rejected"}:
            raise TeamManagerError("CONFLICT", f"invalid approval state: {row.get('status')}")
        teammate = str(row.get("teammate") or "").strip()
        if not teammate:
            raise TeamManagerError("INTERNAL_ERROR", f"approval request missing teammate: {req}")

        sent = self.send_message(
            normalized_team,
            from_member=from_member,
            to_member=teammate,
            text="approved" if approved else "rejected",
            message_type=MESSAGE_TYPE_PLAN_APPROVAL_RESPONSE,
            request_id=req,
            approved=approved,
            feedback=feedback or "",
            summary="plan approval",
        )
        return {
            "request_id": req,
            "team_name": normalized_team,
            "teammate": teammate,
            "approved": approved,
            "feedback": feedback or "",
            "message_id": sent.get("message_id"),
            "status": "sent",
        }

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
        return self.worker_supervisor.has_worker(team_name, teammate_name)

    def export_state(self) -> Dict[str, Any]:
        teams = self.store.list_teams()
        team_states: Dict[str, Dict[str, Any]] = {}
        work_counts: Dict[str, Dict[str, Any]] = {}
        approval_counts: Dict[str, Dict[str, Any]] = {}
        task_board_counts: Dict[str, Dict[str, Any]] = {}
        for name in teams:
            team_state = self.get_status(name)
            worker_state = self.worker_supervisor.team_state(name)
            team_state.update(worker_state)
            team_states[name] = team_state
            work_counts[name] = self.collect_work(name).get("counts", {})
            approval_counts[name] = {
                "pending": len(self.list_plan_approvals(name, status="pending")),
                "approved": len(self.list_plan_approvals(name, status="approved")),
                "rejected": len(self.list_plan_approvals(name, status="rejected")),
            }
            board_rows = self.list_board_tasks(name)
            blocked = 0
            pending = 0
            in_progress = 0
            for row in board_rows:
                status = str(row.get("status") or "")
                blocked_by = row.get("blocked_by")
                if status == "pending":
                    pending += 1
                    if isinstance(blocked_by, list) and blocked_by:
                        blocked += 1
                elif status == "in_progress":
                    in_progress += 1
            task_board_counts[name] = {
                "total": len(board_rows),
                "blocked": blocked,
                "pending": pending,
                "in_progress": in_progress,
            }
        return {
            "teams": team_states,
            "work_items": work_counts,
            "approvals": approval_counts,
            "task_board": task_board_counts,
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
        with self._plan_approvals_lock:
            self._plan_approvals = {}

    def _read_team_or_raise(self, team_name: str) -> Dict[str, Any]:
        try:
            return self.store.read_team(team_name)
        except FileNotFoundError as exc:
            raise TeamManagerError("NOT_FOUND", f"team not found: {team_name}") from exc

    def _emit(self, team_name: str, event_type: str, payload: Dict[str, Any]) -> None:
        self._events[team_name].append(Event.create(team=team_name, event_type=event_type, payload=payload))

    def _start_worker(self, team_name: str, teammate_name: str) -> None:
        self.worker_supervisor.start_worker(
            team_name=team_name,
            teammate_name=teammate_name,
            poll_fn=lambda: self._process_member_inbox(team_name, teammate_name),
            poll_interval_s=0.02,
            idle_timeout_s=60.0,
        )

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
            message_type = str(row.get("type") or MESSAGE_TYPE_MESSAGE)
            if message_type == MESSAGE_TYPE_SHUTDOWN_REQUEST:
                self._request_worker_stop(team_name, teammate_name)
            elif message_type == MESSAGE_TYPE_PLAN_APPROVAL_RESPONSE:
                self._apply_plan_approval_response(team_name, teammate_name, row)
            self.mark_message_processed(team_name, message_id, processed_by=teammate_name)
            processed_ids.add(message_id)
            did_work = True
        did_work = self._process_next_work_item(team_name, teammate_name) or did_work
        did_work = self._dispatch_approved_plan_work(team_name, teammate_name) or did_work
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
            execution = self.execution_service.execute_work_item(team_name, teammate_name, running_item)
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
        if self._teammate_requires_plan_approval(team_name, teammate_name):
            entry = self.approval_service.create_request(team_name, teammate_name, task_id, subject)
            self._emit(
                team_name,
                EVENT_PLAN_APPROVAL_REQUESTED,
                {
                    "request_id": entry["request_id"],
                    "teammate": teammate_name,
                    "task_id": task_id,
                    "status": "pending",
                },
            )
            return True
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

    def _dispatch_approved_plan_work(self, team_name: str, teammate_name: str) -> bool:
        normalized_team = sanitize_name(team_name)
        normalized_teammate = sanitize_name(teammate_name)
        candidate = self.approval_service.claim_next_approved_request(normalized_team, normalized_teammate)
        if candidate is None:
            return False
        task_id = str(candidate.get("task_id"))
        try:
            task = self.get_board_task(normalized_team, task_id)
        except TeamManagerError:
            return False
        subject = str(task.get("subject") or f"task-{task_id}")
        description = str(task.get("description") or "").strip()
        instruction = description or subject
        item = self.store.create_work_item(
            normalized_team,
            owner=normalized_teammate,
            title=subject,
            instruction=instruction,
            payload={"board_task_id": task_id, "approval_request_id": candidate.get("request_id")},
        )
        self._emit(
            normalized_team,
            EVENT_WORK_ITEM_ASSIGNED,
            {"work_id": item["work_id"], "owner": normalized_teammate, "status": item["status"]},
        )
        return True

    def _request_worker_stop(self, team_name: str, teammate_name: str) -> None:
        self.worker_supervisor.request_stop(team_name, teammate_name)

    def _teammate_requires_plan_approval(self, team_name: str, teammate_name: str) -> bool:
        member = self._get_teammate_member(team_name, teammate_name)
        policy = member.get("tool_policy") if isinstance(member, dict) else {}
        if not isinstance(policy, dict):
            return False
        return bool(policy.get("require_plan_approval", False))

    def _get_teammate_member(self, team_name: str, teammate_name: str) -> Dict[str, Any]:
        cfg = self._read_team_or_raise(team_name)
        for member in cfg.get("members", []):
            if str(member.get("name") or "") == str(teammate_name):
                return dict(member)
        return {}

    def _apply_plan_approval_response(self, team_name: str, teammate_name: str, message_row: Dict[str, Any]) -> None:
        request_id = str(message_row.get("request_id") or "").strip()
        if not request_id:
            return
        approved_raw = message_row.get("approved")
        if isinstance(approved_raw, bool):
            approved = approved_raw
        else:
            text = str(message_row.get("text") or "").lower()
            approved = "approve" in text and "reject" not in text
        feedback = str(message_row.get("feedback") or "").strip()
        self.approval_service.apply_response(team_name, teammate_name, request_id, approved, feedback)

    def _execute_work_item(self, team_name: str, teammate_name: str, work_item: Dict[str, Any]) -> Dict[str, Any]:
        return self.execution_service.execute_work_item(team_name, teammate_name, work_item)

    def _run_turn_executor_work(self, team_name: str, teammate_name: str, work_item: Dict[str, Any]) -> Dict[str, Any]:
        return self.execution_service._run_turn_executor_work(team_name, teammate_name, work_item)

    def _build_teammate_registry(self, team_name: str, teammate_name: str) -> tuple[ToolRegistry, set[str]]:
        return self.execution_service._build_teammate_registry(team_name, teammate_name)
