"""File-based task board store for AgentTeams."""

from __future__ import annotations

import json
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from .protocol import (
    TASK_STATUSES,
    TASK_STATUS_CANCELED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_PENDING,
    sanitize_name,
)


class TaskBoardStore:
    def __init__(
        self,
        project_root: str | Path,
        task_store_dir: str = ".tasks",
        lock_timeout_s: float = 3.0,
        lock_stale_s: float = 30.0,
        lock_retry_interval_s: float = 0.01,
    ):
        self.project_root = Path(project_root).resolve()
        self.task_store_dir = task_store_dir
        self.lock_timeout_s = max(0.1, float(lock_timeout_s))
        self.lock_stale_s = max(0.1, float(lock_stale_s))
        self.lock_retry_interval_s = max(0.001, float(lock_retry_interval_s))
        self.tasks_root = (self.project_root / self.task_store_dir).resolve()
        self.tasks_root.mkdir(parents=True, exist_ok=True)

    def _team_dir(self, team_name: str) -> Path:
        return self.tasks_root / sanitize_name(team_name)

    def _meta_path(self, team_name: str) -> Path:
        return self._team_dir(team_name) / "_meta.json"

    def _task_path(self, team_name: str, task_id: str) -> Path:
        return self._team_dir(team_name) / f"task_{task_id}.json"

    def _lock_path(self, team_name: str) -> Path:
        return self._team_dir(team_name) / ".board.lock"

    def _ensure_team_dir(self, team_name: str) -> Path:
        path = self._team_dir(team_name)
        path.mkdir(parents=True, exist_ok=True)
        return path

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

    def _load_meta(self, team_name: str) -> Dict[str, Any]:
        path = self._meta_path(team_name)
        if not path.exists():
            return {"next_id": 1}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_meta(self, team_name: str, payload: Dict[str, Any]) -> None:
        self._meta_path(team_name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _iter_task_paths(self, team_name: str) -> List[Path]:
        team_dir = self._team_dir(team_name)
        if not team_dir.exists():
            return []
        items = list(team_dir.glob("task_*.json"))
        return sorted(items, key=lambda p: p.stem.removeprefix("task_"))

    @staticmethod
    def _read_task(path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_task(path: Path, task: Dict[str, Any]) -> None:
        path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_task(
        self,
        team_name: str,
        subject: str,
        description: str = "",
        owner: str = "",
        blocked_by: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError("subject is required")

        self._ensure_team_dir(normalized_team)
        board_lock = self._lock_path(normalized_team)
        with self.lock(board_lock):
            meta = self._load_meta(normalized_team)
            task_id = str(int(meta.get("next_id", 1)))
            meta["next_id"] = int(task_id) + 1
            self._save_meta(normalized_team, meta)

            blockers = []
            for value in blocked_by or []:
                blocker_id = str(value)
                blocker_path = self._task_path(normalized_team, blocker_id)
                if not blocker_path.exists():
                    raise FileNotFoundError(f"blocker task not found: {blocker_id}")
                blockers.append(blocker_id)

            now = time.time()
            task = {
                "id": task_id,
                "team_name": normalized_team,
                "subject": subject.strip(),
                "description": str(description or ""),
                "status": TASK_STATUS_PENDING,
                "owner": sanitize_name(owner) if str(owner or "").strip() else "",
                "blocked_by": blockers,
                "blocks": [],
                "created_at": now,
                "updated_at": now,
                "claimed_at": None,
                "completed_at": None,
            }
            task_path = self._task_path(normalized_team, task_id)
            self._write_task(task_path, task)

            # Link reverse dependencies.
            for blocker_id in blockers:
                blocker_path = self._task_path(normalized_team, blocker_id)
                blocker = self._read_task(blocker_path)
                if task_id not in blocker.get("blocks", []):
                    blocker.setdefault("blocks", []).append(task_id)
                    blocker["updated_at"] = now
                    self._write_task(blocker_path, blocker)
            return task

    def list_tasks(self, team_name: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_team = sanitize_name(team_name)
        tasks: List[Dict[str, Any]] = []
        for path in self._iter_task_paths(normalized_team):
            row = self._read_task(path)
            if status and row.get("status") != status:
                continue
            tasks.append(row)
        return tasks

    def get_task(self, team_name: str, task_id: str) -> Dict[str, Any]:
        normalized_team = sanitize_name(team_name)
        path = self._task_path(normalized_team, str(task_id))
        if not path.exists():
            raise FileNotFoundError(f"task not found: {task_id}")
        return self._read_task(path)

    def update_task(
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
        tid = str(task_id)
        self._ensure_team_dir(normalized_team)
        board_lock = self._lock_path(normalized_team)
        with self.lock(board_lock):
            path = self._task_path(normalized_team, tid)
            if not path.exists():
                raise FileNotFoundError(f"task not found: {tid}")
            task = self._read_task(path)
            now = time.time()

            if status is not None:
                if status not in TASK_STATUSES:
                    raise ValueError(f"invalid task status: {status}")
                task["status"] = status
                if status == TASK_STATUS_IN_PROGRESS and not task.get("claimed_at"):
                    task["claimed_at"] = now
                if status in {TASK_STATUS_COMPLETED, TASK_STATUS_CANCELED}:
                    task["completed_at"] = now
            if owner is not None:
                owner_text = str(owner).strip()
                task["owner"] = sanitize_name(owner_text) if owner_text else ""
            if subject is not None:
                text = str(subject).strip()
                if not text:
                    raise ValueError("subject cannot be empty")
                task["subject"] = text
            if description is not None:
                task["description"] = str(description)

            if add_blocked_by:
                for value in add_blocked_by:
                    blocker_id = str(value)
                    blocker_path = self._task_path(normalized_team, blocker_id)
                    if not blocker_path.exists():
                        raise FileNotFoundError(f"blocker task not found: {blocker_id}")
                    if blocker_id not in task["blocked_by"]:
                        task["blocked_by"].append(blocker_id)
                    blocker = self._read_task(blocker_path)
                    if tid not in blocker.get("blocks", []):
                        blocker.setdefault("blocks", []).append(tid)
                        blocker["updated_at"] = now
                        self._write_task(blocker_path, blocker)

            if add_blocks:
                for value in add_blocks:
                    blocked_id = str(value)
                    blocked_path = self._task_path(normalized_team, blocked_id)
                    if not blocked_path.exists():
                        raise FileNotFoundError(f"blocked task not found: {blocked_id}")
                    if blocked_id not in task["blocks"]:
                        task["blocks"].append(blocked_id)
                    blocked_task = self._read_task(blocked_path)
                    if tid not in blocked_task.get("blocked_by", []):
                        blocked_task.setdefault("blocked_by", []).append(tid)
                        blocked_task["updated_at"] = now
                        self._write_task(blocked_path, blocked_task)

            task["updated_at"] = now
            self._write_task(path, task)

            if task.get("status") == TASK_STATUS_COMPLETED:
                self._clear_dependency_locked(normalized_team, tid)
                task = self._read_task(path)
            return task

    def claim_next_task(self, team_name: str, owner: str) -> Optional[Dict[str, Any]]:
        normalized_team = sanitize_name(team_name)
        owner_name = sanitize_name(owner)
        self._ensure_team_dir(normalized_team)
        board_lock = self._lock_path(normalized_team)
        with self.lock(board_lock):
            for path in self._iter_task_paths(normalized_team):
                task = self._read_task(path)
                if task.get("status") != TASK_STATUS_PENDING:
                    continue
                if task.get("owner"):
                    continue
                if task.get("blocked_by"):
                    continue
                now = time.time()
                task["status"] = TASK_STATUS_IN_PROGRESS
                task["owner"] = owner_name
                task["claimed_at"] = now
                task["updated_at"] = now
                self._write_task(path, task)
                return task
        return None

    def _clear_dependency_locked(self, team_name: str, completed_task_id: str) -> None:
        now = time.time()
        for path in self._iter_task_paths(team_name):
            row = self._read_task(path)
            blocked_by = list(row.get("blocked_by") or [])
            if completed_task_id in blocked_by:
                row["blocked_by"] = [x for x in blocked_by if x != completed_task_id]
                row["updated_at"] = now
                self._write_task(path, row)
