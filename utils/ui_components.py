"""
Enhanced UI Components for CodeAgent
Provides rich terminal UI with model info, directory display, tool visualization, and token tracking
"""

import os
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from rich.tree import Tree
from rich.markdown import Markdown


class ThinkingTimer:
    """Real-time timer with token counter for model thinking process"""
    
    def __init__(self, console: Console):
        self.console = console
        self._start_time = None
        self._elapsed = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._running = False
        self._thread = None
        self._live = None
        
    def start(self, input_tokens: int = 0):
        """Start the timer"""
        self._start_time = time.time()
        self._elapsed = 0
        self._input_tokens = input_tokens
        self._output_tokens = 0
        self._running = True
        
    def update_output_tokens(self, tokens: int):
        """Update output token count"""
        self._output_tokens = tokens
        
    def stop(self) -> float:
        """Stop the timer and return elapsed time"""
        self._running = False
        if self._start_time:
            self._elapsed = time.time() - self._start_time
        return self._elapsed
        
    def get_display_text(self) -> Text:
        """Get the display text for the timer"""
        if self._running and self._start_time:
            elapsed = time.time() - self._start_time
        else:
            elapsed = self._elapsed
            
        text = Text()
        text.append("✻ ", style="bold yellow")
        
        if self._running:
            text.append("Calculating… ", style="bold yellow")
        else:
            text.append("Completed ", style="bold green")
            
        text.append(f"({int(elapsed)}s", style="dim")
        
        if self._input_tokens > 0:
            text.append(f" · ↑ {self._input_tokens}", style="cyan")
        if self._output_tokens > 0:
            text.append(f" · ↓ {self._output_tokens}", style="magenta")
        
        text.append(")", style="dim")
        return text


class ModelBanner:
    """Display model, provider, and directory information"""
    
    @staticmethod
    def create(
        model: str,
        provider: str,
        project_root: str,
        version: str = "v1.0"
    ) -> Panel:
        """Create a stylized banner with model info"""

        logo_lines = [
            "      /\\_/\\",
            "     ( o.o )  [MyCat]",
            "      > ^ <",
        ]

        logo = Text("\n".join(logo_lines), style="bold bright_blue")

        # Project directory (shortened if too long)
        home = Path.home()
        try:
            rel_path = Path(project_root).relative_to(home)
            dir_display = f"~/{rel_path}"
        except ValueError:
            dir_display = project_root

        info = Table.grid(padding=(0, 1))
        info.add_row(Text("MyCodeAgent", style="bold white"), Text(version, style="dim"))
        info.add_row(Text(provider.upper(), style="bold cyan"), Text(model, style="bright_white"))
        info.add_row(Text("Workspace", style="dim"), Text(dir_display, style="bold green"))

        layout = Table.grid(expand=True)
        layout.add_column(ratio=1)
        layout.add_column(ratio=2)
        layout.add_row(logo, info)

        return Panel(layout, border_style="bright_blue", padding=(1, 2))


class ToolCallTree:
    """Visualize tool calls in a tree structure"""
    
    def __init__(self):
        self.tree = Tree("🔧 Tool Calls", style="bold cyan")
        self.current_branch = None
        
    def add_tool_call(self, tool_name: str, description: str = "") -> Tree:
        """Add a tool call to the tree"""
        icon = self._get_tool_icon(tool_name)
        label = f"{icon} {tool_name}"
        if description:
            label += f" ({description})"
        
        self.current_branch = self.tree.add(label, style="cyan")
        return self.current_branch
        
    def add_detail(self, key: str, value: str, parent: Optional[Tree] = None):
        """Add detail to current or specified branch"""
        target = parent if parent else self.current_branch
        if target:
            # Truncate long values
            if len(str(value)) > 100:
                value = str(value)[:97] + "..."
            target.add(f"⎿ {key}: {value}", style="dim")
            
    def get_tree(self) -> Tree:
        """Get the complete tree"""
        return self.tree
        
    @staticmethod
    def _get_tool_icon(tool_name: str) -> str:
        """Get icon for tool type"""
        icons = {
            "Read": "📖",
            "Write": "✍️",
            "Edit": "✏️",
            "MultiEdit": "📝",
            "LS": "📁",
            "Glob": "🔍",
            "Grep": "🔎",
            "Bash": "💻",
            "Skill": "🎯",
            "TodoWrite": "📋",
        }
        for key, icon in icons.items():
            if key.lower() in tool_name.lower():
                return icon
        return "⚙️"


class TokenTracker:
    """Track and display token consumption"""
    
    def __init__(self):
        self.total_input = 0
        self.total_output = 0
        self.total_tokens = 0
        self.calls = []
        
    def add_usage(self, input_tokens: int, output_tokens: int, step: str = ""):
        """Add token usage for a call"""
        total = input_tokens + output_tokens
        self.total_input += input_tokens
        self.total_output += output_tokens
        self.total_tokens += total
        
        self.calls.append({
            "step": step,
            "input": input_tokens,
            "output": output_tokens,
            "total": total
        })
        
    def get_summary(self) -> Table:
        """Get token usage summary table"""
        table = Table(title="📊 Token Usage", show_header=True, header_style="bold magenta")
        table.add_column("Type", style="cyan")
        table.add_column("Tokens", justify="right", style="yellow")
        
        table.add_row("Input", f"{self.total_input:,}")
        table.add_row("Output", f"{self.total_output:,}")
        table.add_row("Total", f"{self.total_tokens:,}", style="bold green")
        
        return table
        
    def get_summary_text(self) -> Text:
        """Get token usage as inline text"""
        text = Text()
        text.append("📊 ", style="bold magenta")
        text.append(f"↑{self.total_input:,}", style="cyan")
        text.append(" · ", style="dim")
        text.append(f"↓{self.total_output:,}", style="yellow")
        text.append(" · ", style="dim")
        text.append(f"Σ{self.total_tokens:,}", style="bold green")
        return text


class EnhancedUI:
    """Main enhanced UI controller"""
    
    def __init__(
        self,
        console: Console,
        model: str,
        provider: str,
        project_root: str,
        version: str = "v1.0"
    ):
        self.console = console
        self.model = model
        self.provider = provider
        self.project_root = project_root
        self.version = version
        
        self.timer = ThinkingTimer(console)
        self.tool_tree = ToolCallTree()
        self.token_tracker = TokenTracker()
        
    def show_banner(self):
        """Display the model banner"""
        banner = ModelBanner.create(
            model=self.model,
            provider=self.provider,
            project_root=self.project_root,
            version=self.version
        )
        self.console.print(banner)
        self.console.print()
        
    def start_thinking(self, input_tokens: int = 0):
        """Start the thinking timer"""
        self.timer.start(input_tokens)
        self.console.print(self.timer.get_display_text())
        
    def update_thinking(self, output_tokens: int = 0):
        """Update thinking progress"""
        self.timer.update_output_tokens(output_tokens)
        
    def stop_thinking(self) -> float:
        """Stop thinking and show final time"""
        elapsed = self.timer.stop()
        self.console.print(self.timer.get_display_text())
        return elapsed
        
    def show_tool_call(self, tool_name: str, tool_input: Any) -> Tree:
        """Display a tool call"""
        # Parse tool input to show key details
        description = ""
        details = {}
        
        if isinstance(tool_input, dict):
            if "path" in tool_input:
                description = tool_input["path"]
            elif "pattern" in tool_input:
                description = tool_input["pattern"]
            elif "command" in tool_input:
                description = tool_input["command"]
            elif "skill_name" in tool_input:
                description = tool_input["skill_name"]
                
            details = {k: v for k, v in tool_input.items() if k != description}
        elif isinstance(tool_input, str):
            description = tool_input[:50]
            
        branch = self.tool_tree.add_tool_call(tool_name, description)
        
        # Add details
        for key, value in details.items():
            if key not in ["path", "pattern", "command", "skill_name"]:  # Already shown
                self.tool_tree.add_detail(key, value, branch)
                
        return branch
        
    def show_tool_tree(self):
        """Display the complete tool call tree"""
        if self.tool_tree.tree.children:
            self.console.print(self.tool_tree.get_tree())
            self.console.print()
            
    def add_token_usage(self, input_tokens: int, output_tokens: int, step: str = ""):
        """Add token usage"""
        self.token_tracker.add_usage(input_tokens, output_tokens, step)
        
    def show_token_summary(self):
        """Display token usage summary"""
        if self.token_tracker.total_tokens > 0:
            self.console.print(self.token_tracker.get_summary_text())
            self.console.print()
            
    def show_detailed_token_summary(self):
        """Display detailed token usage table"""
        if self.token_tracker.total_tokens > 0:
            self.console.print(self.token_tracker.get_summary())
            self.console.print()
