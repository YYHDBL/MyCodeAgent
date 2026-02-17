import re
import time

from core.team_engine.manager import TeamManager
from core.team_engine.turn_executor import TurnExecutor
from tools.registry import ToolRegistry


class SleepLLM:
    def invoke_raw(self, messages, tools=None, tool_choice=None):
        user_messages = [m for m in messages if m.get("role") == "user"]
        text = user_messages[-1]["content"] if user_messages else ""
        match = re.search(r"sleep:(\d+(?:\.\d+)?)", text)
        if match:
            time.sleep(float(match.group(1)))
        return {"choices": [{"message": {"content": "done"}}]}


class TaskCallingLLM:
    def __init__(self):
        self.calls = 0

    def invoke_raw(self, messages, tools=None, tool_choice=None):
        self.calls += 1
        if self.calls == 1:
            return {
                "choices": [{
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "Task", "arguments": "{\"description\":\"nested\"}"},
                            }
                        ],
                    }
                }]
            }
        last_tool = [m for m in messages if m.get("role") == "tool"]
        observed = last_tool[-1]["content"] if last_tool else ""
        return {"choices": [{"message": {"content": f"final {observed}"}}]}


def _wait_collect(manager: TeamManager, team: str, expect: int, timeout_s: float = 3.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        collected = manager.collect_work(team)
        if collected["counts"]["succeeded"] >= expect:
            return collected
        time.sleep(0.03)
    return manager.collect_work(team)


def test_worker_uses_turn_executor_not_ack_only(tmp_path, monkeypatch):
    calls = {"count": 0}

    def spy(self, messages, tool_usage):
        calls["count"] += 1
        return {
            "done": True,
            "final_result": "ok",
            "messages": list(messages) + [{"role": "assistant", "content": "ok"}],
        }

    monkeypatch.setattr(TurnExecutor, "execute_turn", spy)
    manager = TeamManager(project_root=tmp_path, llm=SleepLLM(), tool_registry=ToolRegistry())
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev1")
    manager.fanout_work("demo", tasks=[{"owner": "dev1", "title": "impl", "instruction": "sleep:0.01"}])
    collected = _wait_collect(manager, "demo", expect=1)

    assert collected["counts"]["succeeded"] >= 1
    assert calls["count"] > 0


def test_two_workers_run_tasks_in_parallel(tmp_path):
    manager = TeamManager(project_root=tmp_path, llm=SleepLLM(), tool_registry=ToolRegistry())
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev1")
    manager.spawn_teammate("demo", "dev2")

    start = time.time()
    manager.fanout_work(
        "demo",
        tasks=[
            {"owner": "dev1", "title": "impl", "instruction": "sleep:0.30"},
            {"owner": "dev2", "title": "test", "instruction": "sleep:0.30"},
        ],
    )
    collected = _wait_collect(manager, "demo", expect=2, timeout_s=4.0)
    elapsed = time.time() - start

    assert collected["counts"]["succeeded"] >= 2
    assert elapsed < 0.55


def test_teammate_cannot_call_task_in_worker_path(tmp_path):
    manager = TeamManager(project_root=tmp_path, llm=TaskCallingLLM(), tool_registry=ToolRegistry())
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev1")

    dispatch = manager.fanout_work(
        "demo",
        tasks=[{"owner": "dev1", "title": "blocked", "instruction": "please call Task"}],
    )
    work_id = dispatch["work_items"][0]["work_id"]
    collected = _wait_collect(manager, "demo", expect=1, timeout_s=4.0)
    done = [x for x in collected["groups"]["succeeded"] if x["work_id"] == work_id]

    assert done
    assert "not allowed" in str(done[0].get("result", "")).lower()
