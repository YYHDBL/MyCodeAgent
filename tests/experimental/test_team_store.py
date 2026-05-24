import json
import os
import threading
import time
from pathlib import Path

import pytest

from core.team_engine.protocol import TEAM_CONFIG_VERSION
from core.team_engine.store import TeamStore


def test_create_team_writes_versioned_config(tmp_path: Path):
    store = TeamStore(project_root=tmp_path)
    store.create_team("demo", members=[{"name": "lead"}])

    cfg = store.read_team("demo")
    assert cfg["version"] == TEAM_CONFIG_VERSION
    assert cfg["members"][0]["name"] == "lead"
    assert cfg["members"][0]["role"]
    assert isinstance(cfg["members"][0]["tool_policy"], dict)


def test_lock_is_exclusive_under_threads(tmp_path: Path):
    store = TeamStore(project_root=tmp_path)
    lock_dir = tmp_path / ".teams" / "lock-test.lock"
    start = threading.Event()
    gate = threading.Barrier(2)
    in_critical = 0
    max_in_critical = 0
    guard = threading.Lock()

    def worker():
        nonlocal in_critical, max_in_critical
        gate.wait()
        start.wait()
        with store.lock(lock_dir, timeout_s=2.0):
            with guard:
                in_critical += 1
                max_in_critical = max(max_in_critical, in_critical)
            time.sleep(0.05)
            with guard:
                in_critical -= 1

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    start.set()
    t1.join()
    t2.join()

    assert max_in_critical == 1


def test_stale_lock_is_reclaimed(tmp_path: Path):
    store = TeamStore(project_root=tmp_path, lock_stale_s=0.2)
    lock_dir = tmp_path / ".teams" / "stale.lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    stale_ts = time.time() - 30
    os.utime(lock_dir, (stale_ts, stale_ts))

    with store.lock(lock_dir, timeout_s=1.0):
        assert lock_dir.exists()

    assert not lock_dir.exists()


def test_append_inbox_message_is_valid_jsonl(tmp_path: Path):
    store = TeamStore(project_root=tmp_path)
    store.create_team("demo", members=[{"name": "lead"}, {"name": "dev-1"}])

    threads = []
    for i in range(20):
        t = threading.Thread(
            target=lambda idx=i: store.append_inbox_message(
                "demo",
                "dev-1",
                {"message_id": f"m-{idx}", "text": f"hello-{idx}"},
            )
        )
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    inbox = tmp_path / ".teams" / "demo" / "dev-1_inbox.jsonl"
    rows = [json.loads(line) for line in inbox.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 20
    assert all("message_id" in row for row in rows)
