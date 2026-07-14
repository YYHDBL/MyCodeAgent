from argparse import Namespace
import json
from pathlib import Path

import pytest


def test_parser_accepts_explicit_project_root_override():
    from app.cli import build_parser

    args = build_parser().parse_args(["--cwd", "nested/project"])

    assert args.cwd == "nested/project"


def test_default_session_path_uses_selected_project_root_transcript_directory(tmp_path):
    from app.cli import _default_session_path

    target = tmp_path / "unrelated-project"
    target.mkdir()

    path = Path(_default_session_path(str(target)))

    assert path == target / "memory" / "transcripts"
    assert path.parent.is_dir()


def test_new_runtime_creates_no_session_latest_snapshot(tmp_path, monkeypatch):
    from app.bootstrap import build_runtime
    from core.config import Config

    target = tmp_path / "unrelated-project"
    target.mkdir()
    monkeypatch.chdir(target)

    class TestConfig:
        @classmethod
        def from_env(cls):
            return Config(enable_verification_agent=False)

    class DummyLLM:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]
            self.provider = kwargs["provider"]

    runtime = build_runtime(
        Namespace(cwd=str(target)),
        extension_flags={"mcp": False, "skills": False, "tracing": False},
        config_class=TestConfig,
        llm_class=DummyLLM,
    )
    try:
        assert runtime.agent.transcript_path().parent == target / "memory" / "transcripts"
        assert not (target / "memory" / "sessions" / "session-latest.json").exists()
    finally:
        runtime.agent.close()


def test_main_returns_a_nonzero_exit_for_an_invalid_project_root(monkeypatch, capsys):
    import app.cli as cli

    class InvalidRootParser:
        def parse_args(self):
            return object()

    monkeypatch.setattr(cli, "build_parser", lambda: InvalidRootParser())
    monkeypatch.setattr(
        cli,
        "build_runtime",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("Project root must be an existing directory: missing")
        ),
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2
    output = capsys.readouterr().out
    assert "Project root must be an existing directory" in output
    assert "missing" in output


def test_unrelated_project_uses_package_prompts_and_target_project_rules(tmp_path, monkeypatch):
    from app.bootstrap import build_runtime
    from app.cli import build_parser
    from core.config import Config

    invocation_root = tmp_path / "invocation-project"
    target_root = tmp_path / "target-project"
    invocation_root.mkdir()
    target_root.mkdir()
    (target_root / "code_law.md").write_text("TARGET_ONLY_RULE", encoding="utf-8")
    monkeypatch.chdir(invocation_root)

    class TestConfig:
        @classmethod
        def from_env(cls):
            return Config(enable_verification_agent=False)

    class DummyLLM:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]
            self.provider = kwargs["provider"]

    runtime = build_runtime(
        build_parser().parse_args(["--cwd", str(target_root)]),
        extension_flags={"mcp": False, "skills": False, "tracing": False},
        config_class=TestConfig,
        llm_class=DummyLLM,
    )
    assembly = runtime.agent.context_builder.get_prompt_assembly()

    assert assembly.constitution_messages
    assert assembly.tool_contract_messages
    assert assembly.project_rule_messages == [
        {"role": "system", "content": "# Project Rules (CODE_LAW)\nTARGET_ONLY_RULE"}
    ]
    assert all(
        "TARGET_ONLY_RULE" not in message["content"]
        for message in assembly.constitution_messages + assembly.tool_contract_messages
    )
    runtime.agent.close()


def test_explicit_project_root_keeps_trace_and_transcript_artifacts_under_target(tmp_path, monkeypatch):
    from app.bootstrap import build_runtime
    from core.config import Config

    invocation_root = tmp_path / "invocation-project"
    target_root = tmp_path / "target-project"
    invocation_root.mkdir()
    target_root.mkdir()
    monkeypatch.chdir(invocation_root)
    monkeypatch.delenv("TRACE_DIR", raising=False)
    monkeypatch.setenv("TRACE_ENABLED", "true")

    class TestConfig:
        @classmethod
        def from_env(cls):
            return Config(enable_verification_agent=False)

    class DummyLLM:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]
            self.provider = kwargs["provider"]

    runtime = build_runtime(
        Namespace(cwd=str(target_root)),
        extension_flags={"mcp": False, "skills": False, "tracing": True},
        config_class=TestConfig,
        llm_class=DummyLLM,
    )
    agent = runtime.agent
    agent.transcript_store.append_message(
        run_id="root-artifact-test",
        step=0,
        role="user",
        content="record target-root artifact",
    )

    trace_path = agent.trace_logger._filepath
    transcript_path = agent.transcript_store.path
    try:
        assert trace_path.is_file()
        assert trace_path.is_relative_to(target_root)
        assert transcript_path.is_file()
        assert transcript_path.is_relative_to(target_root)
        assert not (invocation_root / "memory").exists()
    finally:
        agent.close()


def test_external_artifact_directory_overrides_do_not_escape_target(tmp_path, monkeypatch):
    from app.bootstrap import build_runtime
    from core.config import Config
    from tools.base import ToolResult, ToolStatus, serialize_tool_result
    from tools.observation_store import ObservationTruncator

    invocation_root = tmp_path / "invocation-project"
    target_root = tmp_path / "target-project"
    external_root = tmp_path / "external-artifacts"
    invocation_root.mkdir()
    target_root.mkdir()
    monkeypatch.chdir(invocation_root)
    monkeypatch.setenv("TRACE_ENABLED", "true")
    monkeypatch.setenv("TRACE_DIR", str(external_root / "traces"))
    monkeypatch.setenv("TOOL_OUTPUT_DIR", str(external_root / "tool-output"))

    class TestConfig:
        @classmethod
        def from_env(cls):
            return Config(enable_verification_agent=False)

    class DummyLLM:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]
            self.provider = kwargs["provider"]

    runtime = build_runtime(
        Namespace(cwd=str(target_root)),
        extension_flags={"mcp": False, "skills": False, "tracing": True},
        config_class=TestConfig,
        llm_class=DummyLLM,
    )
    agent = runtime.agent
    try:
        output = serialize_tool_result(ObservationTruncator(project_root=runtime.project_root).force_truncate(
            "Read",
            ToolResult(
                status=ToolStatus.SUCCESS,
                data={"content": "x" * 1024},
                text="fixture",
                stats={"time_ms": 1},
                context={"cwd": ".", "params_input": {}},
            ),
        ))
        artifact = target_root / json.loads(output)["data"]["truncation"]["full_output_path"]

        assert agent.trace_logger._filepath.is_relative_to(target_root)
        assert artifact.is_file()
        assert artifact.is_relative_to(target_root)
        assert not external_root.exists()
    finally:
        agent.close()
