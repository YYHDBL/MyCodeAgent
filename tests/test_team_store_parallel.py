import threading
from pathlib import Path

from core.team_engine.protocol import WORK_ITEM_STATUS_RUNNING
from core.team_engine.store import TeamStore


def test_create_and_update_work_item(tmp_path: Path):
    store = TeamStore(tmp_path)
    store.create_team("demo", members=[{"name": "lead"}])
    item = store.create_work_item("demo", owner="dev1", title="t", instruction="do x")
    updated = store.update_work_item_status("demo", item["work_id"], WORK_ITEM_STATUS_RUNNING)
    assert updated["status"] == WORK_ITEM_STATUS_RUNNING
    assert updated["work_id"] == item["work_id"]


def test_work_item_lock_is_exclusive(tmp_path: Path):
    store = TeamStore(tmp_path)
    store.create_team("demo", members=[{"name": "lead"}])
    item = store.create_work_item("demo", owner="dev1", title="t", instruction="do x")

    statuses = []
    lock = threading.Lock()

    def worker():
        updated = store.update_work_item_status("demo", item["work_id"], WORK_ITEM_STATUS_RUNNING)
        with lock:
            statuses.append(updated["status"])

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert statuses
    items = store.list_work_items("demo", owner="dev1")
    assert len([x for x in items if x["work_id"] == item["work_id"]]) == 1
