"""Message routing service for AgentTeams."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any, Callable, Dict, List, Set

from .errors import TeamEngineError
from .protocol import (
    EVENT_MESSAGE_ACK,
    EVENT_MESSAGE_SENT,
    EVENT_PLAN_APPROVAL_RESPONSE,
    EVENT_SHUTDOWN_REQUEST,
    EVENT_SHUTDOWN_RESPONSE,
    MESSAGE_TYPES,
    MESSAGE_TYPE_BROADCAST,
    MESSAGE_TYPE_MESSAGE,
    MESSAGE_TYPE_PLAN_APPROVAL_RESPONSE,
    MESSAGE_TYPE_SHUTDOWN_REQUEST,
    MESSAGE_TYPE_SHUTDOWN_RESPONSE,
    MESSAGE_STATUS_DELIVERED,
    MESSAGE_STATUS_PENDING,
    MESSAGE_STATUS_PROCESSED,
    sanitize_name,
)


class MessageRouter:
    """Owns send/ack protocol state and inbox delivery."""

    def __init__(self, store: Any, emit_fn: Callable[[str, str, Dict[str, Any]], None]):
        self._store = store
        self._emit = emit_fn
        self._message_status: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)

    @property
    def message_status(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        return self._message_status

    def clear_team(self, team_name: str) -> None:
        self._message_status.pop(team_name, None)

    def send_message(
        self,
        *,
        team_name: str,
        members: Set[str],
        from_member: str,
        to_member: str,
        text: str,
        message_type: str = MESSAGE_TYPE_MESSAGE,
        summary: str = "",
        request_id: str = "",
        approved: Any = None,
        feedback: str = "",
    ) -> Dict[str, Any]:
        sender = sanitize_name(from_member)
        message_kind = str(message_type or MESSAGE_TYPE_MESSAGE).strip().lower()
        summary_text = str(summary or "").strip()
        request_ref = str(request_id or "").strip()
        feedback_text = str(feedback or "").strip()
        if not text or not str(text).strip():
            raise TeamEngineError("INVALID_PARAM", "text is required")
        if message_kind not in MESSAGE_TYPES:
            raise TeamEngineError("INVALID_PARAM", f"unsupported message type: {message_kind}")
        if message_kind in {MESSAGE_TYPE_MESSAGE, MESSAGE_TYPE_BROADCAST} and not summary_text:
            raise TeamEngineError("INVALID_PARAM", "summary is required when message type is message or broadcast")
        if message_kind in {MESSAGE_TYPE_SHUTDOWN_RESPONSE, MESSAGE_TYPE_PLAN_APPROVAL_RESPONSE} and not request_ref:
            raise TeamEngineError("INVALID_PARAM", f"request_id is required when message type is {message_kind}")
        if message_kind == MESSAGE_TYPE_SHUTDOWN_REQUEST and not request_ref:
            request_ref = f"req_{uuid.uuid4().hex[:10]}"

        if sender not in members:
            raise TeamEngineError("NOT_FOUND", f"member not found: {sender}")

        recipients: List[str]
        if message_kind == MESSAGE_TYPE_BROADCAST:
            recipients = sorted(name for name in members if name != sender)
            if not recipients:
                raise TeamEngineError("INVALID_PARAM", "broadcast requires at least one recipient")
        else:
            recipient = sanitize_name(to_member)
            if recipient not in members:
                raise TeamEngineError("NOT_FOUND", f"member not found: {sender}->{recipient}")
            recipients = [recipient]

        message_ids: List[str] = []
        for recipient in recipients:
            message_id = f"msg_{uuid.uuid4().hex}"
            pending = {
                "message_id": message_id,
                "team_name": team_name,
                "from": sender,
                "to": recipient,
                "text": str(text),
                "type": message_kind,
                "summary": summary_text,
                "request_id": request_ref,
                "approved": approved if isinstance(approved, bool) else None,
                "feedback": feedback_text,
                "status": MESSAGE_STATUS_PENDING,
            }
            self._message_status[team_name][message_id] = dict(pending)
            delivered = dict(pending)
            delivered["status"] = MESSAGE_STATUS_DELIVERED
            self._store.append_inbox_message(team_name, recipient, delivered)
            self._message_status[team_name][message_id] = delivered

            event_type = EVENT_MESSAGE_SENT
            if message_kind == MESSAGE_TYPE_SHUTDOWN_REQUEST:
                event_type = EVENT_SHUTDOWN_REQUEST
            elif message_kind == MESSAGE_TYPE_SHUTDOWN_RESPONSE:
                event_type = EVENT_SHUTDOWN_RESPONSE
            elif message_kind == MESSAGE_TYPE_PLAN_APPROVAL_RESPONSE:
                event_type = EVENT_PLAN_APPROVAL_RESPONSE
            self._emit(
                team_name,
                event_type,
                {
                    "message_id": message_id,
                    "from": sender,
                    "to": recipient,
                    "type": message_kind,
                    "status": MESSAGE_STATUS_DELIVERED,
                    "request_id": request_ref,
                    "approved": approved if isinstance(approved, bool) else None,
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
            "approved": approved if isinstance(approved, bool) else None,
            "feedback": feedback_text,
        }
        if message_kind == MESSAGE_TYPE_BROADCAST:
            result["recipient_count"] = len(recipients)
        return result

    def mark_processed(self, team_name: str, message_id: str, processed_by: str) -> Dict[str, Any]:
        statuses = self._message_status.get(team_name, {})
        if message_id not in statuses:
            raise TeamEngineError("NOT_FOUND", f"message not found: {message_id}")
        state = dict(statuses[message_id])
        state["status"] = MESSAGE_STATUS_PROCESSED
        state["processed_by"] = sanitize_name(processed_by)
        statuses[message_id] = state
        self._emit(
            team_name,
            EVENT_MESSAGE_ACK,
            {"message_id": message_id, "status": MESSAGE_STATUS_PROCESSED, "processed_by": state["processed_by"]},
        )
        return state

    def team_messages(self, team_name: str) -> Dict[str, Dict[str, Any]]:
        return self._message_status.get(team_name, {})

