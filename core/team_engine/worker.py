"""Thread worker for persistent teammate execution."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional


class TeammateWorker(threading.Thread):
    def __init__(
        self,
        team_name: str,
        teammate_name: str,
        poll_fn: Callable[[], bool],
        poll_interval_s: float = 0.2,
        idle_timeout_s: float = 120.0,
    ):
        super().__init__(
            name=f"TeamWorker[{team_name}:{teammate_name}]",
            daemon=True,
        )
        self.team_name = team_name
        self.teammate_name = teammate_name
        self._poll_fn = poll_fn
        self.poll_interval_s = max(0.01, float(poll_interval_s))
        self.idle_timeout_s = max(0.01, float(idle_timeout_s))
        self.stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self.state = "starting"
        now = time.time()
        self.last_heartbeat = now
        self.last_active = now
        self.last_error: Optional[str] = None

    def stop(self) -> None:
        with self._state_lock:
            self.state = "stopping"
        self.stop_event.set()

    def wait_stopped(self, timeout: float = 2.0) -> bool:
        self.join(timeout=timeout)
        return not self.is_alive()

    def run(self) -> None:
        with self._state_lock:
            self.state = "active"
        self.last_active = time.time()

        while not self.stop_event.is_set():
            now = time.time()
            self.last_heartbeat = now
            processed = False
            try:
                processed = bool(self._poll_fn())
            except Exception as exc:  # pragma: no cover - defensive
                self.last_error = str(exc)

            if processed:
                self.last_active = now
                with self._state_lock:
                    self.state = "active"
            else:
                idle_for = now - self.last_active
                if idle_for >= self.idle_timeout_s:
                    break
                with self._state_lock:
                    self.state = "idle"

            time.sleep(self.poll_interval_s)

        with self._state_lock:
            self.state = "stopped"

