import argparse
import json
import os
import sys
import time
import re
from pathlib import Path
from typing import Optional, Any

# Ensure project root is on sys.path when running as a script
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.env import load_env

load_env()

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.style import Style
    from rich.text import Text
    from rich.theme import Theme
    from rich.rule import Rule
    from rich.syntax import Syntax
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style as PromptStyle
    from prompt_toolkit.formatted_text import HTML
except ImportError:
    print("Please install required packages: pip install rich prompt_toolkit")
    sys.exit(1)

from core.llm import HelloAgentsLLM
from agents.codeAgent import CodeAgent
from tools.registry import ToolRegistry
from prompts.agents_prompts.init_prompt import CODE_LAW_GENERATION_PROMPT
from core.config import Config
from core.team_engine.cli_commands import (
    DELEGATE_USAGE,
    TEAM_MSG_USAGE,
    parse_delegate_command,
    parse_team_message_command,
)
from utils.ui_components import EnhancedUI, ToolCallTree

# Geeky Theme
custom_theme = Theme({
    "info": "bright_cyan",
    "warning": "bright_yellow",
    "error": "bold bright_red",
    "user": "bold bright_green",
    "agent": "bold bright_blue",
    "banner": "bold bright_blue",
    "thinking": "italic bright_magenta",
    "action": "bold bright_cyan",
    "observation": "dim",
})

console = Console(theme=custom_theme)

class RichConsoleCodeAgent(CodeAgent):
    """
    Extensions of CodeAgent with Rich UI features.
    Overrides _console and _execute_tool to provide better visual feedback.
    """
    
    def __init__(self, *args, ui: Optional['EnhancedUI'] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.ui = ui
        self._step_count = 0
        self._current_step_input_tokens = 0
        self._thinking_active = False
        
    def run(self, user_input: str, show_raw: bool = False) -> str:
        """Override run to integrate with enhanced UI"""
        # Start thinking timer
        if self.ui and not self._thinking_active:
            self.ui.start_thinking()
            self._thinking_active = True
            
        try:
            result = super().run(user_input, show_raw=show_raw)
            return result
        finally:
            # Stop thinking timer
            if self.ui and self._thinking_active:
                self.ui.stop_thinking()
                self._thinking_active = False
                
                # Update token tracker from trace logger if available
                if hasattr(self, 'trace_logger') and self.trace_logger:
                    usage = self.trace_logger._total_usage
                    if usage.get("total_tokens", 0) > 0:
                        self.ui.add_token_usage(
                            usage.get("prompt_tokens", 0),
                            usage.get("completion_tokens", 0),
                            "Session Total"
                        )
        
    def _console(self, message: str) -> None:
        """Override to render messages with Rich"""
        msg = message.strip()
        
        if "Engine 启动" in msg:
             pass # Skip start message to reduce noise
        elif "--- Step" in msg:
             console.print(Rule(style="dim", title=msg))
        elif "🤔 Thought:" in message: # Match with keyword as message might have newlines
             # Extract thought content
             content = message.split("🤔 Thought:", 1)[-1].strip()
             if content:
                 md = Markdown(content)
                 console.print(Panel(md, title="[thinking]Thinking[/thinking]", border_style="yellow", title_align="left"))
        elif "🧠 Reasoning:" in message:
             content = message.split("🧠 Reasoning:", 1)[-1].strip()
             if content:
                 md = Markdown(content)
                 console.print(Panel(md, title="[thinking]Reasoning[/thinking]", border_style="magenta", title_align="left"))
        elif "🎬 Action:" in message:
             # Action is usually followed by content, let's parse it
             content = message.split("🎬 Action:", 1)[-1].strip()
             console.print(Panel(Text(content, style="bold cyan"), title="[action]Action[/action]", border_style="cyan", title_align="left"))
        elif "👀 Observation:" in message:
             content = message.split("👀 Observation:", 1)[-1].strip()
             # Truncate if too long for display, but keep enough context
             if len(content) > 1000:
                  content = content[:1000] + "\n... (remaining content truncated for display)"
             
             # Attempt to highlight code if it looks like code
             if content.strip().startswith("{") or content.strip().startswith("["):
                 try:
                     json.loads(content)
                     renderable = Syntax(content, "json", theme="monokai", word_wrap=True)
                 except:
                     renderable = Text(content, style="dim")
             else:
                 renderable = Text(content, style="dim")
                 
             console.print(Panel(renderable, title="[observation]Observation[/observation]", border_style="dim", title_align="left"))
        elif "✅ Finish" in msg:
            pass # Finish is usually followed by the final answer which is printed separately
        elif "⏳" in msg or "Process" in msg:
            # We handle status via console.status in main loop or _execute_tool, so we can ignore simple progress msgs
            # or print them dimly
            console.print(f"[dim]{msg}[/dim]")
        elif "📎" in msg:
             console.print(f"[info]{msg}[/info]")
        elif "📦" in msg:
             console.print(f"[warning]{msg}[/warning]")
        else:
             # Fallback
             if msg:
                console.print(f"[dim]{msg}[/dim]")

    def _execute_tool(self, tool_name: str, tool_input: Any) -> str:
        """Override to show tool call in UI tree and spinner during execution"""
        # Show tool call in enhanced UI
        if self.ui:
            self.ui.show_tool_call(tool_name, tool_input)
        
        with console.status(f"[bold cyan]Executing {tool_name}...[/bold cyan]", spinner="dots"):
            # artificial small delay to make the spinner visible if tool is too fast
            # time.sleep(0.1) 
            return super()._execute_tool(tool_name, tool_input)

def _env_flag(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}

def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default

def _print_banner(code_law_exists: bool, ui: Optional['EnhancedUI'] = None) -> None:
    """Print banner - use enhanced UI if available"""
    if ui:
        ui.show_banner()
    else:
        banner_text = r"""
      /\_/\
     ( o.o )  [MyCat]
      > ^ <
        """
        console.print(Text(banner_text, style="banner"))
        console.print("[dim]Developer-first Coding Agent[/dim]")
    
    console.print("[dim]Type 'exit' to quit, '/model' to see model info[/dim]")
    
    if not code_law_exists:
        console.print(Panel("⚠️  code_law.md missing. Type 'init' to generate it.", style="yellow", title="Setup Required"))
    console.print()

def _default_session_path() -> str:
    sessions_dir = os.path.join(PROJECT_ROOT, "memory", "sessions")
    os.makedirs(sessions_dir, exist_ok=True)
    return os.path.join(sessions_dir, "session-latest.json")

def _maybe_save_session(agent: CodeAgent, path: str, flag: dict, reason: str) -> None:
    if flag.get("saved"):
        return
    try:
        agent.save_session(path)
        console.print(f"[dim]Auto-saved session ({reason}): {path}[/dim]")
        flag["saved"] = True
    except Exception as exc:
        console.print(f"[bold red]✗ Auto-save failed:[/bold red] {exc}")

def _print_assistant_response(text: str) -> None:
    md = Markdown(text)
    console.print(Panel(md, title="[agent]Assistant[/agent]", border_style="blue", expand=False))

def check_code_law_exists(project_root: str) -> bool:
    """Check if code_law.md exists"""
    code_law_path = Path(project_root) / "code_law.md"
    return code_law_path.exists()

def main() -> None:
    parser = argparse.ArgumentParser(description="Chat with CodeAgent")
    parser.add_argument("--name", default="code", help="agent name")
    parser.add_argument("--system", default=None, help="system prompt")
    parser.add_argument("--provider", default=None, help="llm provider (override LLM_PROVIDER)")
    parser.add_argument("--model", default=None, help="model name (override LLM_MODEL_ID)")
    parser.add_argument("--api-key", default=None, help="api key (override LLM_API_KEY)")
    parser.add_argument("--base-url", default=None, help="base url (override LLM_BASE_URL)")
    parser.add_argument("--temperature", type=float, default=None, help="temperature (override TEMPERATURE)")
    parser.add_argument(
        "--teammate-mode",
        choices=["auto", "in-process", "tmux"],
        default=None,
        help="teammate display mode (override TEAMMATE_MODE)",
    )
    parser.add_argument("--show-raw", action="store_true", help="print raw response structure")
    args = parser.parse_args()

    # Initialize config first (used for temperature fallback)
    config = Config.from_env()
    if args.teammate_mode is not None:
        config.teammate_mode = args.teammate_mode

    # Initialize LLM
    try:
        llm = HelloAgentsLLM(
            model=args.model,
            api_key=args.api_key,
            base_url=args.base_url,
            provider=args.provider,
            temperature=args.temperature if args.temperature is not None else config.temperature,
        )
    except Exception as e:
        console.print(f"[error]Failed to initialize LLM: {e}[/error]")
        return

    tool_registry = ToolRegistry()
   
    # Ensure config has show_react_steps=True for our RichConsoleCodeAgent to receive events
    config.show_react_steps = True

    # Initialize Enhanced UI
    enhanced_ui = EnhancedUI(
        console=console,
        model=llm.model,
        provider=llm.provider,
        project_root=PROJECT_ROOT,
        version="v1.0"
    )

    agent = RichConsoleCodeAgent(
        name=args.name,
        llm=llm,
        tool_registry=tool_registry,
        project_root=PROJECT_ROOT,
        system_prompt=args.system,
        config=config,
        ui=enhanced_ui,
    )

    code_law_exists = check_code_law_exists(PROJECT_ROOT)
    _print_banner(code_law_exists, enhanced_ui)
    auto_save_path = _default_session_path()
    auto_save_flag = {"saved": False}

    # Setup history for prompt_toolkit
    history_file = os.path.join(PROJECT_ROOT, ".chat_history")
    session = PromptSession(history=FileHistory(history_file))
    
    prompt_style = PromptStyle.from_dict({
        'user': '#00ff00 bold',
        'arrow': '#0000ff',
        'host': '#00ffff',
    })

    try:
        while True:
            try:
                # Cool prompt
                user_input = session.prompt(
                    HTML('<user>user</user> <arrow>➜</arrow> '),
                    style=prompt_style
                ).strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye![/dim]")
                _maybe_save_session(agent, auto_save_path, auto_save_flag, "keyboard interrupt")
                break

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "q"}:
                console.print("\n[dim]Shutting down...[/dim]")
                _maybe_save_session(agent, auto_save_path, auto_save_flag, "exit")
                break
                
            # Handle slash commands
            if user_input.startswith("/"):
                if user_input.lower() in ["/model", "/info"]:
                    enhanced_ui.show_banner()
                    enhanced_ui.show_detailed_token_summary()
                    continue
                elif user_input.lower().startswith("/save"):
                    parts = user_input.split(maxsplit=1)
                    path = parts[1].strip() if len(parts) > 1 else _default_session_path()
                    try:
                        agent.save_session(path)
                        console.print(f"[bold green]✓ Session saved:[/bold green] {path}")
                    except Exception as exc:
                        console.print(f"[bold red]✗ Save failed:[/bold red] {exc}")
                    continue
                elif user_input.lower().startswith("/load"):
                    parts = user_input.split(maxsplit=1)
                    path = parts[1].strip() if len(parts) > 1 else _default_session_path()
                    if not os.path.exists(path):
                        console.print(f"[bold red]✗ Session not found:[/bold red] {path}")
                        continue
                    try:
                        agent.load_session(path)
                        console.print(f"[bold green]✓ Session loaded:[/bold green] {path}")
                    except Exception as exc:
                        console.print(f"[bold red]✗ Load failed:[/bold red] {exc}")
                    continue
                elif user_input.lower().startswith("/team msg "):
                    if not agent.enable_agent_teams or agent.team_manager is None:
                        console.print("[bold red]✗ AgentTeams is disabled.[/bold red]")
                        continue
                    try:
                        payload = parse_team_message_command(user_input, from_member=agent.name)
                    except ValueError as exc:
                        console.print(f"[bold red]✗ {exc}[/bold red]")
                        continue
                    try:
                        sent = agent.team_manager.send_message(
                            team_name=payload["team_name"],
                            from_member=payload["from_member"],
                            to_member=payload["to_member"],
                            text=payload["text"],
                            message_type=payload["type"],
                            summary=payload["summary"],
                        )
                        console.print(
                            "[bold green]✓ Team message sent:[/bold green] "
                            f"{payload['team_name']} -> {payload['to_member']} "
                            f"({sent.get('status', 'pending')})"
                        )
                    except Exception as exc:
                        console.print(f"[bold red]✗ Team message failed:[/bold red] {exc}")
                    continue
                elif user_input.lower().startswith("/delegate"):
                    try:
                        cmd = parse_delegate_command(user_input)
                    except ValueError as exc:
                        console.print(f"[bold red]✗ {exc}[/bold red]")
                        continue
                    if cmd.get("action") == "status":
                        console.print(
                            "[bold cyan]Delegate mode:[/bold cyan] "
                            f"{'ON' if agent.delegate_mode else 'OFF'}"
                        )
                        continue
                    enabled = bool(cmd.get("enabled"))
                    agent.set_delegate_mode(enabled)
                    console.print(
                        "[bold green]✓ Delegate mode updated:[/bold green] "
                        f"{'ON' if enabled else 'OFF'}"
                    )
                    continue
                elif user_input.lower() == "/help":
                    console.print(Panel(
                        "[bold]Available Commands:[/bold]\n"
                        "/model, /info - Show model and usage info\n"
                        "/save [path] - Save session snapshot\n"
                        "/load [path] - Load session snapshot\n"
                        f"{TEAM_MSG_USAGE}\n"
                        f"{DELEGATE_USAGE}\n"
                        "/help - Show this help\n"
                        "exit, quit, q - Exit the chat\n"
                        "init - Generate code_law.md",
                        title="Help",
                        border_style="cyan"
                    ))
                    continue

            # Init command handling
            if "init" in user_input.lower() and len(user_input) < 10:
                if code_law_exists:
                    console.print("\n[warning]code_law.md already exists.[/warning]")
                    confirm = session.prompt("Regenerate? (yes/no): ").strip().lower()
                    if confirm != "yes":
                        console.print("Cancelled.")
                        continue
                
                console.print("[info]Initiailizing Agent Protocol...[/info]")
                enhanced_input = f"{CODE_LAW_GENERATION_PROMPT}\n\n请使用 LS、Glob、Grep、Read 等工具探索项目，然后使用 Write 工具生成 code_law.md 文件。"
                
                # Reset UI state for new request
                enhanced_ui.tool_tree = ToolCallTree()
                enhanced_ui.token_tracker.calls.clear()
                
                start_time = time.time()
                console.print()
                
                response = agent.run(enhanced_input, show_raw=args.show_raw)
                
                elapsed = time.time() - start_time
                
                # Show tool tree and token summary
                console.print()
                enhanced_ui.show_tool_tree()
                _print_assistant_response(response)
                
                # Show timing and summary
                timing_text = Text()
                timing_text.append(f"⏱️  Completed in {elapsed:.1f}s", style="dim cyan")
                console.print(timing_text)
                enhanced_ui.show_token_summary()
                console.print()
                
                if check_code_law_exists(PROJECT_ROOT):
                    console.print("[bold green]✓ code_law.md generated successfully.[/bold green]")
                    code_law_exists = True
                else:
                    console.print("[bold red]✗ Failed to generate code_law.md[/bold red]")
            else:
                # Normal chat
                # Reset UI state for new request
                enhanced_ui.tool_tree = ToolCallTree()
                enhanced_ui.token_tracker.calls.clear()  # Clear previous call tracking
                
                # Show thinking with live timer
                start_time = time.time()
                console.print()
                
                response = agent.run(user_input, show_raw=args.show_raw)
                
                elapsed = time.time() - start_time
                
                # Show tool tree and response
                console.print()
                enhanced_ui.show_tool_tree()
                _print_assistant_response(response)
                
                # Show timing and token summary
                timing_text = Text()
                timing_text.append(f"⏱️  Completed in {elapsed:.1f}s", style="dim cyan")
                console.print(timing_text)
                enhanced_ui.show_token_summary()
                console.print()

            if args.show_raw and hasattr(agent, "last_response_raw") and agent.last_response_raw is not None:
                console.print(Panel(json.dumps(agent.last_response_raw, ensure_ascii=False, indent=2), title="Raw Response", border_style="dim"))
                
    finally:
        _maybe_save_session(agent, auto_save_path, auto_save_flag, "finalize")
        agent.close()

if __name__ == "__main__":
    main()
