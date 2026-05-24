"""Plan approval state service."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from .protocol import sanitize_name


class ApprovalService:
    """Tracks plan-approval lifecycle independent from manager orchestration."""

    def __init__(self):
        self._requests: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    @property
    def requests(self) -> Dict[str, Dict[str, Any]]:
        return self._requests

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    def clear_team(self, team_name: str) -> None:
        normalized_team = sanitize_name(team_name)
        with self._lock:
            for req_id in list(self._requests.keys()):
                if self._requests[req_id].get("team_name") == normalized_team:
                    self._requests.pop(req_id, None)

    def create_request(self, team_name: str, teammate: str, task_id: str, subject: str) -> Dict[str, Any]:
        now = time.time()
        request_id = f"req_{uuid.uuid4().hex[:10]}"
        entry = {
            "request_id": request_id,
            "team_name": sanitize_name(team_name),
            "teammate": sanitize_name(teammate),
            "task_id": str(task_id),
            "subject": str(subject or ""),
            "status": "pending",
            "feedback": "",
            "approved": None,
            "dispatched": False,
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._requests[request_id] = entry
        return dict(entry)

    def get_request(self, request_id: str) -> Dict[str, Any]:
        req = str(request_id or "").strip()
        with self._lock:
            row = dict(self._requests.get(req) or {})
        return row

    def list_requests(self, team_name: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_team = sanitize_name(team_name)
        with self._lock:
            rows = [dict(x) for x in self._requests.values() if x.get("team_name") == normalized_team]
        if status:
            rows = [x for x in rows if str(x.get("status") or "") == str(status)]
        rows.sort(key=lambda x: float(x.get("created_at") or 0))
        return rows

    def apply_response(self, team_name: str, teammate: str, request_id: str, approved: bool, feedback: str = "") -> bool:
        normalized_team = sanitize_name(team_name)
        normalized_teammate = sanitize_name(teammate)
        req = str(request_id or "").strip()
        with self._lock:
            row = self._requests.get(req)
            if not row:
                return False
            if row.get("team_name") != normalized_team or row.get("teammate") != normalized_teammate:
                return False
            row["status"] = "approved" if approved else "rejected"
            row["approved"] = bool(approved)
            row["feedback"] = str(feedback or "")
            row["updated_at"] = time.time()
        return True

    def claim_next_approved_request(self, team_name: str, teammate: str) -> Optional[Dict[str, Any]]:
        normalized_team = sanitize_name(team_name)
        normalized_teammate = sanitize_name(teammate)
        with self._lock:
            for row in self._requests.values():
                if row.get("team_name") != normalized_team:
                    continue
                if row.get("teammate") != normalized_teammate:
                    continue
                if row.get("status") != "approved":
                    continue
                if row.get("dispatched"):
                    continue
                row["dispatched"] = True
                row["updated_at"] = time.time()
                return dict(row)
        return None

