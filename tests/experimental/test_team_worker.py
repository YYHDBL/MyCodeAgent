import time

from core.team_engine.manager import TeamManager
from core.team_engine.worker import TeammateWorker


def test_worker_does_not_exit_when_running_normally():
    worker = TeammateWorker(
        team_name="demo",
        teammate_name="dev",
        poll_fn=lambda: False,
        poll_interval_s=0.02,
        idle_timeout_s=1.0,
    )
    worker.start()
    time.sleep(0.12)
    assert worker.is_alive()
    worker.stop()
    worker.join(timeout=1.0)
    assert not worker.is_alive()


def test_worker_exits_after_idle_timeout():
    worker = TeammateWorker(
        team_name="demo",
        teammate_name="dev",
        poll_fn=lambda: False,
        poll_interval_s=0.02,
        idle_timeout_s=0.05,
    )
    worker.start()
    worker.join(timeout=1.0)
    assert not worker.is_alive()


def test_team_delete_stops_worker(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev")
    assert manager.has_worker("demo", "dev")

    manager.delete_team("demo")
    assert not manager.has_worker("demo", "dev")
