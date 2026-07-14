"""Current product documentation and UI must expose only current tool names."""

from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_TOOL_PATTERN = re.compile(
    r"\b(?:Write|MultiEdit|WriteTool|MultiEditTool)\b|"
    r"(?:write_file|edit_file_multi|write_prompt|multi_edit_prompt)",
)


def _active_docs():
    docs = PROJECT_ROOT / "docs"
    excluded = {docs / "plans", docs / "research-archive.md", docs / "archives"}
    for path in docs.rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".json"}:
            continue
        if any(parent in path.parents or path == parent for parent in excluded):
            continue
        yield path


def test_active_docs_and_ui_do_not_advertise_removed_file_mutation_tools():
    paths = [*(_active_docs()), PROJECT_ROOT / "demo" / "README.md"]
    paths.extend((PROJECT_ROOT / directory).rglob("*.py") for directory in ("app", "utils"))
    source_paths = []
    for path in paths:
        if isinstance(path, Path):
            source_paths.append(path)
        else:
            source_paths.extend(path)

    leaks = [
        f"{path.relative_to(PROJECT_ROOT)}: {match.group(0)}"
        for path in source_paths
        for match in LEGACY_TOOL_PATTERN.finditer(path.read_text(encoding="utf-8"))
    ]

    assert not leaks, "Removed file-mutation surface remains:\n" + "\n".join(leaks)
    assert not (PROJECT_ROOT / "docs" / "WriteTool设计文档.md").exists()
    assert not (PROJECT_ROOT / "docs" / "MultiEditTool设计文档.md").exists()
