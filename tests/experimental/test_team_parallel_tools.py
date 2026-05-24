import json

from core.team_engine.manager import TeamManager
from tools.builtin.team_collect import TeamCollectTool
from tools.builtin.team_fanout import TeamFanoutTool


def test_team_fanout_tool_protocol(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev1")
    tool = TeamFanoutTool(project_root=tmp_path, team_manager=manager)

    response = json.loads(
        tool.run(
            {
                "team_name": "demo",
                "tasks": [{"owner": "dev1", "title": "impl", "instruction": "do impl"}],
            }
        )
    )
    assert response["status"] == "success"
    assert len(response["data"]["work_items"]) == 1


def test_team_collect_tool_protocol(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev1")
    manager.fanout_work(
        "demo",
        tasks=[{"owner": "dev1", "title": "impl", "instruction": "do impl"}],
    )
    tool = TeamCollectTool(project_root=tmp_path, team_manager=manager)
    response = json.loads(tool.run({"team_name": "demo"}))

    assert response["status"] == "success"
    assert "counts" in response["data"]
