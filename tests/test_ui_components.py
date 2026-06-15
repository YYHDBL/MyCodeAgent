"""pytest tests for UI components."""

import io

import pytest
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from utils.ui_components import EnhancedUI, ModelBanner, TokenTracker, ToolCallTree


def _capture_console():
    """Return (console, stringio) for capturing rendered output."""
    sio = io.StringIO()
    console = Console(file=sio, force_terminal=False, width=120)
    return console, sio


def _render_to_str(renderable, console=None, sio=None) -> str:
    """Render a Rich renderable to a plain string via a StringIO console."""
    if console is None:
        console, sio = _capture_console()
    console.print(renderable)
    return sio.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def console_and_io():
    console, sio = _capture_console()
    return console, sio


@pytest.fixture
def tool_tree():
    return ToolCallTree()


@pytest.fixture
def token_tracker():
    return TokenTracker()


@pytest.fixture
def enhanced_ui():
    console, _ = _capture_console()
    return EnhancedUI(
        console=console,
        model="GLM-4.7",
        provider="zhipu",
        project_root="/fake/project",
        version="v1.0",
    )


# ---------------------------------------------------------------------------
# ModelBanner
# ---------------------------------------------------------------------------


class TestModelBanner:
    def test_create_returns_panel(self):
        panel = ModelBanner.create(
            model="GLM-4.7", provider="zhipu", project_root="/tmp/test", version="v1.0"
        )
        assert isinstance(panel, Panel)

    def test_create_contains_model_and_provider(self):
        panel = ModelBanner.create(
            model="GLM-4.7", provider="zhipu", project_root="/tmp/test", version="v1.0"
        )
        rendered = _render_to_str(panel)
        assert "GLM-4.7" in rendered
        assert "ZHIPU" in rendered
        assert "MyCodeAgent" in rendered

    def test_create_shows_workspace(self):
        panel = ModelBanner.create(
            model="GEMINI-2.0",
            provider="google",
            project_root="/home/user/my_project",
            version="v2.0",
        )
        rendered = _render_to_str(panel)
        assert "GOOGLE" in rendered
        assert "Workspace" in rendered


# ---------------------------------------------------------------------------
# ToolCallTree
# ---------------------------------------------------------------------------


class TestToolCallTree:
    def test_initial_tree_has_no_children(self, tool_tree):
        tree = tool_tree.get_tree()
        assert isinstance(tree, Tree)
        assert tree.children == []

    def test_add_tool_call_creates_child(self, tool_tree):
        tool_tree.add_tool_call("Read", "docs/README.md")
        tree = tool_tree.get_tree()
        assert len(tree.children) == 1

    def test_multiple_tool_calls(self, tool_tree):
        tool_tree.add_tool_call("Read", "a.txt")
        tool_tree.add_tool_call("Write", "b.txt")
        tool_tree.add_tool_call("Grep", "pattern")
        assert len(tool_tree.get_tree().children) == 3

    def test_tree_renders_tool_names(self, tool_tree):
        tool_tree.add_tool_call("Read", "README.md")
        tool_tree.add_tool_call("Bash", "pytest -v")
        rendered = _render_to_str(tool_tree.get_tree())
        assert "Read" in rendered
        assert "README.md" in rendered
        assert "Bash" in rendered

    def test_add_detail_writes_key_value(self, tool_tree):
        branch = tool_tree.add_tool_call("Write", "output.txt")
        tool_tree.add_detail("bytes", "1024", parent=branch)
        rendered = _render_to_str(tool_tree.get_tree())
        assert "bytes" in rendered
        assert "1024" in rendered

    def test_add_detail_defaults_to_current_branch(self, tool_tree):
        tool_tree.add_tool_call("Grep", "pattern")
        tool_tree.add_detail("matches", "5")  # no explicit parent
        rendered = _render_to_str(tool_tree.get_tree())
        assert "matches" in rendered
        assert "5" in rendered

    def test_long_values_are_truncated(self, tool_tree):
        tool_tree.add_tool_call("Read", "file.txt")
        long_val = "x" * 200
        tool_tree.add_detail("content", long_val)
        rendered = _render_to_str(tool_tree.get_tree())
        assert "..." in rendered
        assert long_val not in rendered

    def test_add_detail_without_branch_is_safe(self, tool_tree):
        """add_detail should not raise when there is no current_branch."""
        tool_tree.add_detail("key", "value")
        tree = tool_tree.get_tree()
        assert tree.children == []

    def test_get_tool_icon_returns_string(self):
        icon = ToolCallTree._get_tool_icon("Read")
        assert isinstance(icon, str)
        assert icon  # non-empty

    def test_get_tool_icon_unknown_fallback(self):
        icon = ToolCallTree._get_tool_icon("SomeUnknownTool")
        assert icon == "⚙️"


# ---------------------------------------------------------------------------
# TokenTracker
# ---------------------------------------------------------------------------


class TestTokenTracker:
    def test_initial_values_are_zero(self, token_tracker):
        assert token_tracker.total_input == 0
        assert token_tracker.total_output == 0
        assert token_tracker.total_tokens == 0
        assert token_tracker.calls == []

    def test_add_usage_accumulates(self, token_tracker):
        token_tracker.add_usage(100, 50, "Step 1")
        assert token_tracker.total_input == 100
        assert token_tracker.total_output == 50
        assert token_tracker.total_tokens == 150

    def test_add_usage_multiple_calls(self, token_tracker):
        token_tracker.add_usage(100, 50, "Call A")
        token_tracker.add_usage(200, 100, "Call B")
        token_tracker.add_usage(300, 150, "Call C")
        assert token_tracker.total_input == 600
        assert token_tracker.total_output == 300
        assert token_tracker.total_tokens == 900
        assert len(token_tracker.calls) == 3
        assert token_tracker.calls[0]["step"] == "Call A"
        assert token_tracker.calls[1]["input"] == 200
        assert token_tracker.calls[2]["total"] == 450

    def test_get_summary_returns_table(self, token_tracker):
        token_tracker.add_usage(100, 50)
        summary = token_tracker.get_summary()
        assert isinstance(summary, Table)

    def test_get_summary_contains_totals(self, token_tracker):
        token_tracker.add_usage(1000, 500)
        rendered = _render_to_str(token_tracker.get_summary())
        assert "1,000" in rendered
        assert "500" in rendered
        assert "1,500" in rendered

    def test_get_summary_text_returns_text(self, token_tracker):
        token_tracker.add_usage(100, 50)
        text = token_tracker.get_summary_text()
        rendered = _render_to_str(text)
        assert "100" in rendered
        assert "50" in rendered
        assert "150" in rendered


# ---------------------------------------------------------------------------
# EnhancedUI
# ---------------------------------------------------------------------------


class TestEnhancedUI:
    def test_show_banner_writes_to_console(self, enhanced_ui, console_and_io):
        console, sio = console_and_io
        # Swap to our captured console
        enhanced_ui.console = console
        enhanced_ui.show_banner()
        output = sio.getvalue()
        assert "GLM-4.7" in output
        assert "ZHIPU" in output

    def test_show_tool_call_records_node(self, enhanced_ui):
        enhanced_ui.show_tool_call("Read", {"path": "README.md", "lines": "1-50"})
        assert len(enhanced_ui.tool_tree.get_tree().children) == 1

    def test_show_tool_call_with_dict_description(self, enhanced_ui):
        enhanced_ui.show_tool_call("Grep", {"pattern": "TODO"})
        tree = enhanced_ui.tool_tree.get_tree()
        assert len(tree.children) == 1

    def test_show_tool_call_with_string_description(self, enhanced_ui):
        enhanced_ui.show_tool_call("Skill", "my_skill_name")
        tree = enhanced_ui.tool_tree.get_tree()
        assert len(tree.children) == 1

    def test_show_tool_tree_renders_without_error(self, enhanced_ui, console_and_io):
        console, sio = console_and_io
        enhanced_ui.console = console
        enhanced_ui.show_tool_call("Read", {"path": "a.txt"})
        enhanced_ui.show_tool_call("Write", {"path": "b.txt"})
        enhanced_ui.show_tool_tree()
        output = sio.getvalue()
        assert "Read" in output
        assert "Write" in output

    def test_show_tool_tree_empty_is_silent(self, enhanced_ui, console_and_io):
        console, sio = console_and_io
        enhanced_ui.console = console
        enhanced_ui.show_tool_tree()
        output = sio.getvalue()
        assert output == ""

    def test_add_token_usage_and_show_summary(self, enhanced_ui, console_and_io):
        console, sio = console_and_io
        enhanced_ui.console = console
        enhanced_ui.add_token_usage(1000, 500, "Step 1")
        enhanced_ui.add_token_usage(800, 400, "Step 2")
        enhanced_ui.show_token_summary()
        output = sio.getvalue()
        assert "1,800" in output   # total input
        assert "900" in output    # total output
        assert "2,700" in output  # total

    def test_show_token_summary_empty_is_silent(self, enhanced_ui, console_and_io):
        console, sio = console_and_io
        enhanced_ui.console = console
        enhanced_ui.show_token_summary()
        output = sio.getvalue()
        assert output == ""

    def test_show_detailed_token_summary(self, enhanced_ui, console_and_io):
        console, sio = console_and_io
        enhanced_ui.console = console
        enhanced_ui.add_token_usage(500, 250, "Step")
        enhanced_ui.show_detailed_token_summary()
        output = sio.getvalue()
        assert "Token Usage" in output
        assert "500" in output
        assert "250" in output

    def test_show_detailed_token_summary_empty_is_silent(
        self, enhanced_ui, console_and_io
    ):
        console, sio = console_and_io
        enhanced_ui.console = console
        enhanced_ui.show_detailed_token_summary()
        output = sio.getvalue()
        assert output == ""

    def test_start_thinking_writes_to_console(self, enhanced_ui, console_and_io):
        console, sio = console_and_io
        enhanced_ui.console = console
        enhanced_ui.start_thinking(input_tokens=200)
        output = sio.getvalue()
        assert "200" in output

    def test_stop_thinking_returns_elapsed_and_writes(self, enhanced_ui, console_and_io):
        console, sio = console_and_io
        enhanced_ui.console = console
        enhanced_ui.start_thinking(input_tokens=100)
        elapsed = enhanced_ui.stop_thinking()
        output = sio.getvalue()
        assert isinstance(elapsed, float)
        assert elapsed >= 0
        # stop_thinking writes to console
        assert len(output) > 0

    def test_update_thinking_updates_output_tokens(self, enhanced_ui):
        enhanced_ui.start_thinking(input_tokens=100)
        enhanced_ui.update_thinking(output_tokens=50)
        assert enhanced_ui.timer._output_tokens == 50
        enhanced_ui.stop_thinking()

    def test_stop_thinking_without_start_is_safe(self, enhanced_ui):
        elapsed = enhanced_ui.stop_thinking()
        assert elapsed == 0

    def test_show_team_progress_no_state_is_silent(self, enhanced_ui, console_and_io):
        console, sio = console_and_io
        enhanced_ui.console = console
        enhanced_ui.show_team_progress({})
        output = sio.getvalue()
        assert output == ""
