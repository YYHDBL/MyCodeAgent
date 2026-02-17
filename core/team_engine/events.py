"""Team event objects."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Event:
    id: str
    ts: float
    team: str
    type: str
    payload: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "team": self.team,
            "type": self.type,
            "payload": self.payload,
        }

    @classmethod
    def create(cls, team: str, event_type: str, payload: Dict[str, Any]) -> "Event":
        return cls(
            id=f"evt_{uuid.uuid4().hex}",
            ts=time.time(),
            team=team,
            type=event_type,
            payload=payload,
        )

