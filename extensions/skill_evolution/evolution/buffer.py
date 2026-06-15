"""异常轨迹缓存 — 按 Skill 分区，persistent_run_id 去重，JSONL 存储。

达到阈值后触发 Batch Review。
"""

from __future__ import annotations

import json
from pathlib import Path

from extensions.skill_evolution.types import EvolutionStateRecord, RolloutRecord


class _BufferEntry:
    __slots__ = ("consumed", "rollout")

    def __init__(self, consumed: bool, rollout: RolloutRecord):
        self.consumed = consumed
        self.rollout = rollout


class AbnormalTrajectoryBuffer:
    def __init__(self, buffer_dir: Path):
        self._buffer_dir = Path(buffer_dir)

    def _buffer_path(self, skill_name: str) -> Path:
        return self._buffer_dir / skill_name / ".evolution" / "buffer.jsonl"

    def _read_entries(self, skill_name: str) -> list[_BufferEntry]:
        path = self._buffer_path(skill_name)
        if not path.exists():
            return []
        entries: list[_BufferEntry] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                entry = _BufferEntry(
                    consumed=obj.get("consumed", False),
                    rollout=RolloutRecord(**obj["rollout"]),
                )
                entries.append(entry)
            except (json.JSONDecodeError, TypeError):
                continue
        return entries

    def _write_entries(self, skill_name: str, entries: list[_BufferEntry]):
        path = self._buffer_path(skill_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for e in entries:
                obj = {
                    "consumed": e.consumed,
                    "rollout": {
                        "persistent_run_id": e.rollout.persistent_run_id,
                        "attributing_skill": e.rollout.attributing_skill,
                        "task_success": e.rollout.task_success,
                        "hard_error": e.rollout.hard_error,
                        "error_signatures": e.rollout.error_signatures,
                        "summary": e.rollout.summary,
                    },
                }
                fh.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def append(self, rollout: RolloutRecord):
        skill_name = rollout.attributing_skill
        if not skill_name:
            return
        entries = self._read_entries(skill_name)
        existing_ids = {e.rollout.persistent_run_id for e in entries}
        if rollout.persistent_run_id in existing_ids:
            return
        entries.append(_BufferEntry(consumed=False, rollout=rollout))
        self._write_entries(skill_name, entries)

    def get_batch(self, skill_name: str) -> list[RolloutRecord]:
        return [e.rollout for e in self._read_entries(skill_name) if not e.consumed]

    def should_review(self, skill_name: str, min_traces: int = 3, min_runs: int = 2) -> bool:
        active = [e for e in self._read_entries(skill_name) if not e.consumed]
        if len(active) < min_traces:
            return False
        distinct_runs = len({e.rollout.persistent_run_id for e in active})
        return distinct_runs >= min_runs

    def count_distinct_runs(self, skill_name: str) -> int:
        active = [e for e in self._read_entries(skill_name) if not e.consumed]
        return len({e.rollout.persistent_run_id for e in active})

    def mark_consumed(self, skill_name: str, run_ids: list[str]):
        if not run_ids:
            return
        entries = self._read_entries(skill_name)
        id_set = set(run_ids)
        changed = False
        for e in entries:
            if e.rollout.persistent_run_id in id_set and not e.consumed:
                e.consumed = True
                changed = True
        if changed:
            self._write_entries(skill_name, entries)

    def clear(self, skill_name: str):
        path = self._buffer_path(skill_name)
        if path.exists():
            path.unlink(missing_ok=True)


__all__ = ["AbnormalTrajectoryBuffer"]
