import json
import time

from core.team_engine.manager import TeamManager
from tools.builtin.team_collect import TeamCollectTool
from tools.builtin.team_create import TeamCreateTool
from tools.builtin.team_delete import TeamDeleteTool
from tools.builtin.team_fanout import TeamFanoutTool


def test_parallel_end_to_end_flow(tmp_path):
    def work_executor(item):
        time.sleep(0.5)
        return {"result": f"done:{item.get('owner')}"}

    manager = TeamManager(project_root=tmp_path, work_executor=work_executor)
    team_create = TeamCreateTool(project_root=tmp_path, team_manager=manager)
    team_fanout = TeamFanoutTool(project_root=tmp_path, team_manager=manager)
    team_collect = TeamCollectTool(project_root=tmp_path, team_manager=manager)
    team_delete = TeamDeleteTool(project_root=tmp_path, team_manager=manager)

    created = json.loads(team_create.run({"team_name": "demo", "members": [{"name": "lead"}]}))
    assert created["status"] == "success"

    manager.spawn_teammate("demo", "dev1")
    manager.spawn_teammate("demo", "dev2")

    start = time.monotonic()
    dispatched = json.loads(
        team_fanout.run(
            {
                "team_name": "demo",
                "tasks": [
                    {"owner": "dev1", "title": "impl", "instruction": "implement"},
                    {"owner": "dev2", "title": "test", "instruction": "test"},
                ],
            }
        )
    )
    assert dispatched["status"] == "success"

    work_ids = [item["work_id"] for item in dispatched["data"]["work_items"]]
    done = False
    payload = {}
    for _ in range(50):
        payload = json.loads(team_collect.run({"team_name": "demo", "work_ids": work_ids}))
        if payload["data"]["counts"].get("succeeded") == 2:
            done = True
            break
        time.sleep(0.05)

    elapsed = time.monotonic() - start
    assert done
    assert elapsed < 0.9

    succeeded = payload["data"]["groups"]["succeeded"]
    assert len(succeeded) == 2
    assert all(str(item.get("result", "")).startswith("done:") for item in succeeded)

    deleted = json.loads(team_delete.run({"team_name": "demo"}))
    assert deleted["status"] == "success"
