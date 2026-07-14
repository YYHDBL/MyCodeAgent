"""Smoke tests for the installable MyCodeAgent distribution."""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_project_metadata_declares_the_mycodeagent_console_script() -> None:
    """The package metadata is the source of truth for the public CLI."""

    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as project_file:
        metadata = tomllib.load(project_file)

    project = metadata["project"]
    assert project["name"] == "mycodeagent"
    assert project["scripts"] == {"mycodeagent": "app.cli:main"}
    assert project["requires-python"] == ">=3.10"
    assert "dependencies" in project
    assert "tomli>=2.0.0; python_version < '3.11'" in project["optional-dependencies"]["dev"]


def test_setuptools_discovers_only_supported_runtime_packages() -> None:
    """The installed wheel excludes the removed experimental namespace."""

    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as project_file:
        metadata = tomllib.load(project_file)

    include = metadata["tool"]["setuptools"]["packages"]["find"]["include"]
    assert {"app*", "runtime*", "tools*", "prompts*"}.issubset(include)
    assert "experimental*" not in include
    assert not (REPOSITORY_ROOT / "experimental" / "__init__.py").exists()


def test_compatibility_exports_and_install_docs_keep_mcp_optional() -> None:
    """Generated core/dev exports must not silently reinstall the MCP extra."""

    core_export = (REPOSITORY_ROOT / "requirements.txt").read_text(encoding="utf-8")
    dev_export = (REPOSITORY_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    env_example = (REPOSITORY_ROOT / ".env.example").read_text(encoding="utf-8")

    for export in (core_export, dev_export):
        assert "mcp==" not in export
        assert "anyio==" not in export
        assert "# via mcp" not in export

    assert "MCP remains a core dependency" not in readme
    assert "mycodeagent[mcp]" in readme
    assert "uv sync --extra dev --extra mcp" in readme
    assert 'python -m pip install -e ".[dev,mcp]"' in readme
    assert "ENABLE_AGENT_TEAMS" not in env_example
