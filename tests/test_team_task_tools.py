import json

from core.team_engine.manager import TeamManager
from tools.builtin.team_task_create import TeamTaskCreateTool
from tools.builtin.team_task_get import TeamTaskGetTool
from tools.builtin.team_task_list import TeamTaskListTool
from tools.builtin.team_task_update import TeamTaskUpdateTool


def test_team_task_tools_crud_protocol(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}, {"name": "dev1"}])

    create_tool = TeamTaskCreateTool(project_root=tmp_path, team_manager=manager)
    get_tool = TeamTaskGetTool(project_root=tmp_path, team_manager=manager)
    update_tool = TeamTaskUpdateTool(project_root=tmp_path, team_manager=manager)
    list_tool = TeamTaskListTool(project_root=tmp_path, team_manager=manager)

    created = json.loads(
        create_tool.run(
            {
                "team_name": "demo",
                "subject": "Design schema",
                "description": "Model key entities",
            }
        )
    )
    assert created["status"] == "success"
    task_id = created["data"]["task"]["id"]

    fetched = json.loads(get_tool.run({"team_name": "demo", "task_id": task_id}))
    assert fetched["status"] == "success"
    assert fetched["data"]["task"]["subject"] == "Design schema"

    updated = json.loads(
        update_tool.run(
            {
                "team_name": "demo",
                "task_id": task_id,
                "status": "in_progress",
                "owner": "dev1",
            }
        )
    )
    assert updated["status"] == "success"
    assert updated["data"]["task"]["status"] == "in_progress"
    assert updated["data"]["task"]["owner"] == "dev1"

    listed = json.loads(list_tool.run({"team_name": "demo", "status": "in_progress"}))
    assert listed["status"] == "success"
    assert listed["data"]["total"] == 1


def test_team_task_create_tool_requires_subject(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    tool = TeamTaskCreateTool(project_root=tmp_path, team_manager=manager)

    result = json.loads(tool.run({"team_name": "demo", "subject": ""}))
    assert result["status"] == "error"
    assert result["error"]["code"] == "INVALID_PARAM"
