import json
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("mode", ["default", "explicit"])
def test_cli_bootstrap_keeps_runtime_artifacts_in_the_selected_git_project(
    tmp_path, monkeypatch, mode
):
    from app.bootstrap import build_runtime
    from app.cli import build_parser
    from core.config import Config
    from tools.base import ToolResult, ToolStatus, serialize_tool_result
    from tools.observation_store import ObservationTruncator

    source_root = Path(__file__).resolve().parents[2]
    invocation_root = tmp_path / f"invocation-{mode}"
    target_root = invocation_root if mode == "default" else tmp_path / f"target-{mode}"
    invocation_root.mkdir()
    if target_root != invocation_root:
        target_root.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=target_root, check=True)
    monkeypatch.chdir(invocation_root)
    external_artifacts = tmp_path / f"external-{mode}"
    monkeypatch.setenv("TRACE_DIR", str(external_artifacts / "traces"))
    monkeypatch.setenv("TOOL_OUTPUT_DIR", str(external_artifacts / "tool-output"))
    monkeypatch.setenv("TRACE_ENABLED", "true")
    source_artifacts_before = {
        path.resolve()
        for directory in (source_root / "memory", source_root / "tool-output")
        if directory.exists()
        for path in directory.rglob("*")
        if path.is_file()
    }

    class ScenarioConfig:
        @classmethod
        def from_env(cls):
            return Config(enable_verification_agent=False)

    class FakeLLM:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]
            self.provider = kwargs["provider"]

    args = build_parser().parse_args([] if mode == "default" else ["--cwd", str(target_root)])
    runtime = build_runtime(
        args,
        extension_flags={"mcp": False, "skills": False, "tracing": True},
        config_class=ScenarioConfig,
        llm_class=FakeLLM,
    )
    agent = runtime.agent
    try:
        agent.transcript_store.append_message(
            run_id=f"scenario-{mode}",
            step=0,
            role="user",
            content="record target-root runtime artifacts",
        )
        output = json.loads(serialize_tool_result(
            ObservationTruncator(project_root=runtime.project_root).force_truncate(
                "Read",
                ToolResult(
                    status=ToolStatus.SUCCESS,
                    data={"content": "x" * 1024},
                    text="fixture",
                    stats={"time_ms": 1},
                    context={"cwd": ".", "params_input": {}},
                ),
            )
        ))
        artifacts = [
            agent.trace_logger._filepath,
            agent.transcript_store.path,
            target_root / output["data"]["truncation"]["full_output_path"],
        ]

        assert runtime.project_root == str(target_root.resolve())
        assert (target_root / ".git").is_dir()
        assert all(path.is_file() and path.resolve().is_relative_to(target_root) for path in artifacts)
        if mode == "explicit":
            assert not (invocation_root / "memory").exists()
        assert not external_artifacts.exists()
        source_artifacts_after = {
            path.resolve()
            for directory in (source_root / "memory", source_root / "tool-output")
            if directory.exists()
            for path in directory.rglob("*")
            if path.is_file()
        }
        assert source_artifacts_after == source_artifacts_before
    finally:
        agent.close()
