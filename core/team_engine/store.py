"""File-based persistence for AgentTeams MVP."""

from __future__ import annotations

import json
import shutil
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .protocol import (
    TEAM_CONFIG_VERSION,
    WORK_ITEM_STATUSES,
    WORK_ITEM_STATUS_FAILED,
    WORK_ITEM_STATUS_QUEUED,
    WORK_ITEM_STATUS_RUNNING,
    WORK_ITEM_STATUS_SUCCEEDED,
    normalize_member,
    sanitize_name,
)


class TeamStore:
    def __init__(
        self,
        project_root: Path | str,
        team_store_dir: str = ".teams",
        task_store_dir: str = ".tasks",
        lock_timeout_s: float = 3.0,
        lock_stale_s: float = 30.0,
        lock_retry_interval_s: float = 0.01,
    ):
        self.project_root = Path(project_root).resolve()
        self.team_store_dir = team_store_dir
        self.task_store_dir = task_store_dir
        self.lock_timeout_s = max(0.1, float(lock_timeout_s))
        self.lock_stale_s = max(0.1, float(lock_stale_s))
        self.lock_retry_interval_s = max(0.001, float(lock_retry_interval_s))
        self.teams_root = (self.project_root / self.team_store_dir).resolve()
        self.tasks_root = (self.project_root / self.task_store_dir).resolve()
        self.teams_root.mkdir(parents=True, exist_ok=True)
        self.tasks_root.mkdir(parents=True, exist_ok=True)

    def _team_dir(self, team_name: str) -> Path:
        return self.teams_root / sanitize_name(team_name)

    def _config_path(self, team_name: str) -> Path:
        return self._team_dir(team_name) / "config.json"

    def _inbox_path(self, team_name: str, member_name: str) -> Path:
        team_dir = self._team_dir(team_name)
        member = sanitize_name(member_name)
        return team_dir / f"{member}_inbox.jsonl"

    def _work_items_dir(self, team_name: str) -> Path:
        return self._team_dir(team_name) / "work_items"

    def _work_items_path(self, team_name: str, owner: str) -> Path:
        return self._work_items_dir(team_name) / f"work_items_{sanitize_name(owner)}.jsonl"

    def _work_items_lock_path(self, team_name: str, owner: str) -> Path:
        return self._work_items_dir(team_name) / f"work_items_{sanitize_name(owner)}.lock"

    @contextmanager
    def lock(self, lock_dir: Path | str, timeout_s: Optional[float] = None):
        lock_path = Path(lock_dir)
        timeout = self.lock_timeout_s if timeout_s is None else max(0.01, float(timeout_s))
        deadline = time.monotonic() + timeout

        while True:
            try:
                lock_path.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                self._try_reclaim_stale_lock(lock_path)
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"lock timeout: {lock_path}")
                time.sleep(self.lock_retry_interval_s)
        try:
            yield
        finally:
            if lock_path.exists():
                shutil.rmtree(lock_path, ignore_errors=True)

    def _try_reclaim_stale_lock(self, lock_path: Path) -> None:
        if not lock_path.exists():
            return
        try:
            age_s = time.time() - lock_path.stat().st_mtime
        except OSError:
            return
        if age_s >= self.lock_stale_s:
            shutil.rmtree(lock_path, ignore_errors=True)

    def create_team(self, team_name: str, members: Optional[Iterable[Dict[str, Any]]] = None) -> Dict[str, Any]:
        team_dir = self._team_dir(team_name)
        if team_dir.exists():
            raise FileExistsError(f"team already exists: {team_name}")
        team_dir.mkdir(parents=True, exist_ok=False)

        normalized_members = [normalize_member(m) for m in (members or [{"name": "lead"}])]
        payload = {
            "version": TEAM_CONFIG_VERSION,
            "team_name": sanitize_name(team_name),
            "members": normalized_members,
            "created_at": time.time(),
        }
        self._config_path(team_name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return payload

    def read_team(self, team_name: str) -> Dict[str, Any]:
        return json.loads(self._config_path(team_name).read_text(encoding="utf-8"))

    def update_team(self, team_name: str, team_config: Dict[str, Any]) -> Dict[str, Any]:
        cfg = dict(team_config or {})
        members = cfg.get("members") or []
        cfg["members"] = [normalize_member(m) for m in members]
        cfg["version"] = TEAM_CONFIG_VERSION
        self._config_path(team_name).write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return cfg

    def delete_team(self, team_name: str) -> None:
        shutil.rmtree(self._team_dir(team_name), ignore_errors=True)

    def list_teams(self) -> List[str]:
        if not self.teams_root.exists():
            return []
        names: List[str] = []
        for item in self.teams_root.iterdir():
            if not item.is_dir():
                continue
            if (item / "config.json").exists():
                names.append(item.name)
        return sorted(names)

    def append_inbox_message(self, team_name: str, to_member: str, message: Dict[str, Any]) -> Dict[str, Any]:
        inbox_path = self._inbox_path(team_name, to_member)
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        lock_dir = inbox_path.with_suffix(inbox_path.suffix + ".lock")
        row = dict(message or {})
        row.setdefault("created_at", time.time())

        with self.lock(lock_dir):
            with inbox_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False))
                f.write("\n")
        return row

    def read_inbox_messages(self, team_name: str, member_name: str) -> List[Dict[str, Any]]:
        inbox_path = self._inbox_path(team_name, member_name)
        if not inbox_path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for line in inbox_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(json.loads(line))
        return rows

    def create_work_item(
        self,
        team_name: str,
        owner: str,
        title: str,
        instruction: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.read_team(team_name)
        owner_name = sanitize_name(owner)
        now = time.time()
        item = {
            "work_id": f"work_{uuid.uuid4().hex}",
            "team_name": sanitize_name(team_name),
            "owner": owner_name,
            "title": str(title),
            "instruction": str(instruction),
            "payload": payload or {},
            "status": WORK_ITEM_STATUS_QUEUED,
            "attempt": 0,
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
        }
        work_dir = self._work_items_dir(team_name)
        work_dir.mkdir(parents=True, exist_ok=True)
        path = self._work_items_path(team_name, owner_name)
        lock_path = self._work_items_lock_path(team_name, owner_name)
        with self.lock(lock_path):
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False))
                f.write("\n")
        return item

    def list_work_items(
        self,
        team_name: str,
        owner: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        work_dir = self._work_items_dir(team_name)
        if not work_dir.exists():
            return []
        files: List[Path]
        if owner:
            files = [self._work_items_path(team_name, owner)]
        else:
            files = sorted(work_dir.glob("work_items_*.jsonl"))
        items: List[Dict[str, Any]] = []
        for path in files:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if status and row.get("status") != status:
                    continue
                items.append(row)
        items.sort(key=lambda x: float(x.get("created_at") or 0))
        return items

    def update_work_item_status(
        self,
        team_name: str,
        work_id: str,
        status: str,
        result: Optional[Any] = None,
        error: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if status not in WORK_ITEM_STATUSES:
            raise ValueError(f"invalid work item status: {status}")
        work_dir = self._work_items_dir(team_name)
        if not work_dir.exists():
            raise FileNotFoundError(f"work items dir not found for team: {team_name}")

        now = time.time()
        for path in sorted(work_dir.glob("work_items_*.jsonl")):
            owner = path.stem.removeprefix("work_items_")
            lock_path = self._work_items_lock_path(team_name, owner)
            with self.lock(lock_path):
                rows = self._read_jsonl(path)
                found = False
                updated_row: Optional[Dict[str, Any]] = None
                for row in rows:
                    if row.get("work_id") != work_id:
                        continue
                    found = True
                    row["status"] = status
                    row["updated_at"] = now
                    if status == WORK_ITEM_STATUS_RUNNING:
                        row["attempt"] = int(row.get("attempt") or 0) + 1
                        row["started_at"] = now
                        row["finished_at"] = None
                        row["error"] = None
                    elif status == WORK_ITEM_STATUS_QUEUED:
                        row["started_at"] = None
                        row["finished_at"] = None
                        row["error"] = None
                        row["result"] = None
                    elif status in {WORK_ITEM_STATUS_SUCCEEDED, WORK_ITEM_STATUS_FAILED}:
                        row["finished_at"] = now
                    if result is not None:
                        row["result"] = result
                    if error is not None:
                        row["error"] = error
                    updated_row = dict(row)
                    break
                if found:
                    self._write_jsonl(path, rows)
                    return updated_row or {}
        raise FileNotFoundError(f"work item not found: {work_id}")

    def requeue_running_work_items(self, team_name: str) -> int:
        work_dir = self._work_items_dir(team_name)
        if not work_dir.exists():
            return 0
        changed = 0
        now = time.time()
        for path in sorted(work_dir.glob("work_items_*.jsonl")):
            owner = path.stem.removeprefix("work_items_")
            lock_path = self._work_items_lock_path(team_name, owner)
            with self.lock(lock_path):
                rows = self._read_jsonl(path)
                touched = False
                for row in rows:
                    if row.get("status") == WORK_ITEM_STATUS_RUNNING:
                        row["status"] = WORK_ITEM_STATUS_QUEUED
                        row["updated_at"] = now
                        row["started_at"] = None
                        touched = True
                        changed += 1
                if touched:
                    self._write_jsonl(path, rows)
        return changed

    @staticmethod
    def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(json.loads(line))
        return rows

    @staticmethod
    def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False))
                f.write("\n")
