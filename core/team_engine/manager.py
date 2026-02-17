"""Team orchestration manager for AgentTeams MVP."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional

from .events import Event
from .protocol import (
    EVENT_MESSAGE_ACK,
    EVENT_MESSAGE_SENT,
    EVENT_SHUTDOWN_REQUEST,
    MESSAGE_STATUS_DELIVERED,
    MESSAGE_STATUS_PENDING,
    MESSAGE_STATUS_PROCESSED,
    normalize_member,
    sanitize_name,
)
from .store import TeamStore


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
    ):
        self.store = store or TeamStore(
            project_root=project_root,
            team_store_dir=team_store_dir,
            task_store_dir=task_store_dir,
        )
        self._workers: Dict[tuple[str, str], Any] = {}
        self._events: Dict[str, List[Event]] = defaultdict(list)
        self._message_status: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        self._recent_errors: Dict[str, str] = {}

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
        return teammate

    def send_message(self, team_name: str, from_member: str, to_member: str, text: str) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        sender = sanitize_name(from_member)
        recipient = sanitize_name(to_member)
        if not text or not str(text).strip():
            raise TeamManagerError("INVALID_PARAM", "text is required")

        cfg = self._read_team_or_raise(normalized_team)
        members = {m["name"] for m in cfg.get("members", [])}
        if sender not in members or recipient not in members:
            raise TeamManagerError("NOT_FOUND", f"member not found: {sender}->{recipient}")

        message_id = f"msg_{uuid.uuid4().hex}"
        pending = {
            "message_id": message_id,
            "team_name": normalized_team,
            "from": sender,
            "to": recipient,
            "text": str(text),
            "status": MESSAGE_STATUS_PENDING,
        }
        self._message_status[normalized_team][message_id] = dict(pending)
        delivered = dict(pending)
        delivered["status"] = MESSAGE_STATUS_DELIVERED
        self.store.append_inbox_message(normalized_team, recipient, delivered)
        self._message_status[normalized_team][message_id] = delivered
        self._emit(
            normalized_team,
            EVENT_MESSAGE_SENT,
            {"message_id": message_id, "from": sender, "to": recipient, "status": MESSAGE_STATUS_DELIVERED},
        )
        return {"message_id": message_id, "status": MESSAGE_STATUS_DELIVERED}

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

    def export_state(self) -> Dict[str, Any]:
        return {
            "teams": {name: self.get_status(name) for name in list(self._events.keys())},
        }

    def import_state(self, state: Optional[Dict[str, Any]]) -> None:
        # MVP keeps file store as source of truth; snapshot import is best-effort.
        _ = state or {}

    def _read_team_or_raise(self, team_name: str) -> Dict[str, Any]:
        try:
            return self.store.read_team(team_name)
        except FileNotFoundError as exc:
            raise TeamManagerError("NOT_FOUND", f"team not found: {team_name}") from exc

    def _emit(self, team_name: str, event_type: str, payload: Dict[str, Any]) -> None:
        self._events[team_name].append(Event.create(team=team_name, event_type=event_type, payload=payload))

