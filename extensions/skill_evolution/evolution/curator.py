"""Report-only maintenance snapshots for Skill Evolution."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from extensions.skill_evolution.evolution.buffer import AbnormalTrajectoryBuffer
from extensions.skill_evolution.types import EvolutionStateRecord


class SkillEvolutionCurator:
    def __init__(self, overlay_dir: Path):
        self._overlay_dir = Path(overlay_dir)
        self._reports_dir = self._overlay_dir / ".evolution" / "reports"

    def write_report(
        self,
        event: str,
        states: dict[str, EvolutionStateRecord],
        buffer: AbnormalTrajectoryBuffer,
        *,
        details: dict[str, Any] | None = None,
    ) -> Path:
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "event": event,
            "created_at": datetime.now().isoformat(),
            "details": details or {},
            "skills": self._build_skill_summary(states, buffer),
        }
        path = self._reports_dir / f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}-{event}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _build_skill_summary(
        self,
        states: dict[str, EvolutionStateRecord],
        buffer: AbnormalTrajectoryBuffer,
    ) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for name, state in sorted(states.items()):
            out[name] = {
                "state": state.state,
                "active_proposal_id": state.active_proposal_id,
                "lkg_version": state.lkg_version,
                "current_version": state.current_version,
                "consecutive_rejections": state.consecutive_rejections,
                "pending_abnormal_traces": len(buffer.get_batch(name)),
            }
        return out


__all__ = ["SkillEvolutionCurator"]
