import threading

from core.team_engine.manager import TeamManager


def test_team_task_claim_is_atomic_under_threads(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}] + [{"name": f"dev{i}"} for i in range(8)])

    for idx in range(5):
        manager.create_board_task("demo", subject=f"task-{idx}")

    claimed_ids = []
    lock = threading.Lock()

    def _claim(owner: str) -> None:
        item = manager.claim_next_board_task("demo", owner=owner)
        if not item:
            return
        with lock:
            claimed_ids.append(item["id"])

    threads = [threading.Thread(target=_claim, args=(f"dev{i}",)) for i in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=1.0)

    assert len(claimed_ids) == 5
    assert len(set(claimed_ids)) == 5

    tasks = manager.list_board_tasks("demo")
    in_progress = [task for task in tasks if task["status"] == "in_progress"]
    assert len(in_progress) == 5
