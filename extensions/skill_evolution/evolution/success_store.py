"""per-skill 近期成功轨迹缓存 — FIFO，JSONL 存储。

写入 NORMAL_ROLLOUT 或 Hotfix 成功后调用。跨重启自然保留。
"""

from __future__ import annotations

import json
from pathlib import Path


class RecentSuccessStore:
    def __init__(self, store_path: Path, max_entries: int = 5):
        self._store_path = Path(store_path)
        self._max_entries = max_entries
        self._store_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, persistent_run_id: str, summary: str):
        ts = ""
        try:
            from datetime import datetime, UTC
            ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        except Exception:
            pass

        entry = {
            "persistent_run_id": persistent_run_id,
            "summary": summary,
            "timestamp": ts,
        }

        entries: list[dict] = []
        if self._store_path.exists():
            for line in self._store_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        entries.append(entry)
        entries = entries[-self._max_entries :]

        self._store_path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n")

    def get_recent(self, n: int) -> list[str]:
        if not self._store_path.exists():
            return []
        entries: list[dict] = []
        for line in self._store_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return [e.get("summary", "") for e in entries[-n:]]

    def clear(self):
        if self._store_path.exists():
            self._store_path.unlink(missing_ok=True)


__all__ = ["RecentSuccessStore"]
