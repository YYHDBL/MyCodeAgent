"""Worker lifecycle supervision."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from .protocol import sanitize_name
from .worker import TeammateWorker


class WorkerSupervisor:
    """Manages teammate worker lifecycle and active set."""

    def __init__(self, worker_factory: Optional[Callable[..., Any]] = None):
        self._worker_factory = worker_factory or TeammateWorker
        self._workers: Dict[Tuple[str, str], Any] = {}

    @property
    def workers(self) -> Dict[Tuple[str, str], Any]:
        return self._workers

    def start_worker(
        self,
        team_name: str,
        teammate_name: str,
        poll_fn: Callable[[], bool],
        poll_interval_s: float = 0.02,
        idle_timeout_s: float = 60.0,
    ) -> Any:
        team = sanitize_name(team_name)
        teammate = sanitize_name(teammate_name)
        key = (team, teammate)
        existing = self._workers.get(key)
        if existing and existing.is_alive():
            return existing
        worker = self._worker_factory(
            team_name=team,
            teammate_name=teammate,
            poll_fn=poll_fn,
            poll_interval_s=poll_interval_s,
            idle_timeout_s=idle_timeout_s,
        )
        worker.start()
        self._workers[key] = worker
        return worker

    def has_worker(self, team_name: str, teammate_name: str) -> bool:
        key = (sanitize_name(team_name), sanitize_name(teammate_name))
        worker = self._workers.get(key)
        return bool(worker and worker.is_alive())

    def request_stop(self, team_name: str, teammate_name: str) -> None:
        key = (sanitize_name(team_name), sanitize_name(teammate_name))
        worker = self._workers.get(key)
        if worker and hasattr(worker, "stop"):
            worker.stop()

    def active_workers(self, team_name: str) -> list[str]:
        team = sanitize_name(team_name)
        active: list[str] = []
        for (w_team, member), worker in self._workers.items():
            if w_team != team:
                continue
            if worker and worker.is_alive():
                active.append(member)
        return sorted(active)

    def stop_team(self, team_name: str, join_timeout_s: float = 2.0) -> None:
        team = sanitize_name(team_name)
        for (w_team, member), worker in list(self._workers.items()):
            if w_team != team:
                continue
            try:
                if hasattr(worker, "stop"):
                    worker.stop()
                if hasattr(worker, "join"):
                    worker.join(timeout=join_timeout_s)
            finally:
                self._workers.pop((w_team, member), None)

