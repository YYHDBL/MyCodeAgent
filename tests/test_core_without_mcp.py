"""Contracts for running the core harness without the optional MCP SDK."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import textwrap
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _blocked_mcp_environment(tmp_path: Path) -> dict[str, str]:
    """Make any accidental MCP SDK import fail deterministically in a child process."""
    (tmp_path / "mcp.py").write_text(
        "raise ImportError('MCP SDK deliberately unavailable for core-install test')\n",
        encoding="utf-8",
    )
    (tmp_path / "anyio.py").write_text(
        "raise ImportError('AnyIO deliberately unavailable for core-install test')\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(tmp_path), str(PROJECT_ROOT), environment.get("PYTHONPATH")))
    )
    return environment


def _run_without_mcp(tmp_path: Path, source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(PROJECT_ROOT),
            "--no-sync",
            "python",
            "-c",
            textwrap.dedent(source),
        ],
        cwd=tmp_path,
        env=_blocked_mcp_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )


def test_core_cli_bootstrap_starts_when_mcp_sdk_is_unavailable(tmp_path):
    result = _run_without_mcp(
        tmp_path,
        """
        from app.bootstrap import build_runtime
        from app.cli import build_parser

        class FakeLLM:
            def __init__(self, **_kwargs):
                pass

        class FakeAgent:
            def __init__(self, **kwargs):
                assert kwargs["enable_mcp"] is False

        runtime = build_runtime(
            build_parser().parse_args([]),
            project_root=".",
            llm_class=FakeLLM,
            tool_registry_factory=object,
            agent_class=FakeAgent,
        )
        assert runtime.project_root
        """,
    )

    assert result.returncode == 0, result.stderr


def test_explicit_mcp_enablement_reports_how_to_install_missing_extra(tmp_path):
    result = _run_without_mcp(
        tmp_path,
        """
        from core.config import Config
        from runtime.host import CodeAgent
        from tools.registry import ToolRegistry

        class FakeLLM:
            provider = "openai"
            model = "test"

        try:
            CodeAgent(
                name="code",
                llm=FakeLLM(),
                tool_registry=ToolRegistry(),
                project_root=".",
                config=Config(enable_mcp=True, enable_skills=False, enable_tracing=False),
            )
        except RuntimeError as exc:
            assert 'mycodeagent[mcp]' in str(exc)
        else:
            raise AssertionError('explicit MCP enablement must fail without its extra')
        """,
    )

    assert result.returncode == 0, result.stderr


def test_mcp_client_import_explains_when_the_optional_extra_is_missing(tmp_path):
    result = _run_without_mcp(
        tmp_path,
        """
        try:
            from extensions.mcp.client import MCPClient
        except RuntimeError as exc:
            assert 'mycodeagent[mcp]' in str(exc)
        else:
            raise AssertionError('the optional MCP client import must explain its missing extra')
        """,
    )

    assert result.returncode == 0, result.stderr


def test_mcp_and_anyio_are_only_packaged_in_the_mcp_extra():
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    assert all(
        not dependency.startswith(("mcp", "anyio", "openai"))
        for dependency in project["dependencies"]
    )
    assert project["optional-dependencies"]["mcp"] == ["anyio>=3.0.0", "mcp>=1.0.0"]
