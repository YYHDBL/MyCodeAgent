"""CLI entrypoint extracted from the legacy chat_test_agent script."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from core.env import load_env

load_env()

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style as PromptStyle
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.syntax import Syntax
    from rich.text import Text
    from rich.theme import Theme
except ImportError:
    print("Please install required packages: pip install rich prompt_toolkit")
    sys.exit(1)

from app.bootstrap import PROJECT_ROOT, build_runtime
from prompts.agents_prompts.init_prompt import CODE_LAW_GENERATION_PROMPT
from runtime.agent_host import CodeAgent
from utils.ui_components import EnhancedUI, ToolCallTree

custom_theme = Theme(
    {
        "info": "bright_cyan",
        "warning": "bright_yellow",
        "error": "bold bright_red",
        "user": "bold bright_green",
        "agent": "bold bright_blue",
        "banner": "bold bright_blue",
        "thinking": "italic bright_magenta",
        "action": "bold bright_cyan",
        "observation": "dim",
    }
)

console = Console(theme=custom_theme)


def _load_team_cli_commands():
    from experimental.teams.cli_commands import (
        DELEGATE_USAGE,
        TEAM_MSG_USAGE,
        TEAM_WATCH_USAGE,
        parse_delegate_command,
        parse_team_message_command,
        parse_team_watch_command,
    )

    return {
        "DELEGATE_USAGE": DELEGATE_USAGE,
        "TEAM_MSG_USAGE": TEAM_MSG_USAGE,
        "TEAM_WATCH_USAGE": TEAM_WATCH_USAGE,
        "parse_delegate_command": parse_delegate_command,
        "parse_team_message_command": parse_team_message_command,
        "parse_team_watch_command": parse_team_watch_command,
    }


class RichConsoleCodeAgent(CodeAgent):
    """CodeAgent with Rich-based UI hooks."""

    def __init__(self, *args, ui: Optional[EnhancedUI] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.ui = ui
        self._step_count = 0
        self._current_step_input_tokens = 0
        self._thinking_active = False

    def run(self, user_input: str, show_raw: bool = False) -> str:
        if self.ui and not self._thinking_active:
            self.ui.start_thinking()
            self._thinking_active = True

        try:
            return super().run(user_input, show_raw=show_raw)
        finally:
            if self.ui and self._thinking_active:
                self.ui.stop_thinking()
                self._thinking_active = False

                if hasattr(self, "trace_logger") and self.trace_logger:
                    usage = self.trace_logger._total_usage
                    if usage.get("total_tokens", 0) > 0:
                        self.ui.add_token_usage(
                            usage.get("prompt_tokens", 0),
                            usage.get("completion_tokens", 0),
                            "Session Total",
                        )

    def _console(self, message: str) -> None:
        msg = message.strip()

        if "Engine 启动" in msg:
            return
        if "--- Step" in msg:
            console.print(Rule(style="dim", title=msg))
            return
        if "🤔 Thought:" in message:
            content = message.split("🤔 Thought:", 1)[-1].strip()
            if content:
                console.print(
                    Panel(
                        Markdown(content),
                        title="[thinking]Thinking[/thinking]",
                        border_style="yellow",
                        title_align="left",
                    )
                )
            return
        if "🧠 Reasoning:" in message:
            content = message.split("🧠 Reasoning:", 1)[-1].strip()
            if content:
                console.print(
                    Panel(
                        Markdown(content),
                        title="[thinking]Reasoning[/thinking]",
                        border_style="magenta",
                        title_align="left",
                    )
                )
            return
        if "🎬 Action:" in message:
            content = message.split("🎬 Action:", 1)[-1].strip()
            console.print(
                Panel(
                    Text(content, style="bold cyan"),
                    title="[action]Action[/action]",
                    border_style="cyan",
                    title_align="left",
                )
            )
            return
        if "👀 Observation:" in message:
            content = message.split("👀 Observation:", 1)[-1].strip()
            if len(content) > 1000:
                content = content[:1000] + "\n... (remaining content truncated for display)"

            if content.strip().startswith("{") or content.strip().startswith("["):
                try:
                    json.loads(content)
                    renderable = Syntax(content, "json", theme="monokai", word_wrap=True)
                except Exception:
                    renderable = Text(content, style="dim")
            else:
                renderable = Text(content, style="dim")

            console.print(
                Panel(
                    renderable,
                    title="[observation]Observation[/observation]",
                    border_style="dim",
                    title_align="left",
                )
            )
            return
        if "✅ Finish" in msg:
            return
        if "⏳" in msg or "Process" in msg:
            console.print(f"[dim]{msg}[/dim]")
            return
        if "📎" in msg:
            console.print(f"[info]{msg}[/info]")
            return
        if "📦" in msg:
            console.print(f"[warning]{msg}[/warning]")
            return
        if msg:
            console.print(f"[dim]{msg}[/dim]")

    def _execute_tool(self, tool_name: str, tool_input: Any) -> str:
        if self.ui:
            self.ui.show_tool_call(tool_name, tool_input)
            if tool_name in {"Task", "TeamFanout", "TeamCollect"}:
                mode = ""
                if isinstance(tool_input, dict):
                    mode = str(tool_input.get("mode", "") or "").strip()
                mode_suffix = f" mode={mode}" if mode else ""
                console.print(
                    f"[bold magenta]⚡ Team Dispatch[/bold magenta] "
                    f"{tool_name}{mode_suffix}"
                )

        with console.status(f"[bold cyan]Executing {tool_name}...[/bold cyan]", spinner="dots"):
            result = super()._execute_tool(tool_name, tool_input)

        if self.ui and self.enable_agent_teams and self.team_manager and tool_name in {
            "Task",
            "TeamFanout",
            "TeamCollect",
        }:
            try:
                self.ui.show_team_progress(self.team_manager.export_state())
            except Exception:
                pass
        return result


def _print_banner(code_law_exists: bool, ui: Optional[EnhancedUI] = None) -> None:
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
        console.print(
            Panel(
                "⚠️  code_law.md missing. Type 'init' to generate it.",
                style="yellow",
                title="Setup Required",
            )
        )
    console.print()


def _default_session_path() -> str:
    sessions_dir = os.path.join(PROJECT_ROOT, "memory", "sessions")
    os.makedirs(sessions_dir, exist_ok=True)
    return os.path.join(sessions_dir, "session-latest.json")


def _maybe_save_session(agent: CodeAgent, path: str, flag: dict[str, bool], reason: str) -> None:
    if flag.get("saved"):
        return
    try:
        agent.save_session(path)
        console.print(f"[dim]Auto-saved session ({reason}): {path}[/dim]")
        flag["saved"] = True
    except Exception as exc:
        console.print(f"[bold red]✗ Auto-save failed:[/bold red] {exc}")


def _print_assistant_response(text: str) -> None:
    console.print(
        Panel(
            Markdown(text),
            title="[agent]Assistant[/agent]",
            border_style="blue",
            expand=False,
        )
    )


def check_code_law_exists(project_root: str) -> bool:
    return (Path(project_root) / "code_law.md").exists()


def build_parser() -> argparse.ArgumentParser:
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
    return parser


def main() -> None:
    args = build_parser().parse_args()

    try:
        runtime = build_runtime(
            args,
            project_root=PROJECT_ROOT,
            agent_class=RichConsoleCodeAgent,
            agent_kwargs_factory=lambda config, llm, project_root: {
                "ui": EnhancedUI(
                    console=console,
                    model=llm.model,
                    provider=llm.provider,
                    project_root=project_root,
                    version="v1.0",
                )
            },
        )
    except Exception as exc:
        console.print(f"[error]Failed to initialize runtime: {exc}[/error]")
        return

    agent = runtime.agent
    enhanced_ui = agent.ui
    code_law_exists = check_code_law_exists(PROJECT_ROOT)
    _print_banner(code_law_exists, enhanced_ui)
    auto_save_path = _default_session_path()
    auto_save_flag = {"saved": False}

    history_file = os.path.join(PROJECT_ROOT, ".chat_history")
    session = PromptSession(history=FileHistory(history_file))
    prompt_style = PromptStyle.from_dict(
        {
            "user": "#00ff00 bold",
            "arrow": "#0000ff",
            "host": "#00ffff",
        }
    )

    try:
        while True:
            try:
                user_input = session.prompt(
                    HTML("<user>user</user> <arrow>➜</arrow> "),
                    style=prompt_style,
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

            if user_input.startswith("/"):
                if user_input.lower() in {"/model", "/info"}:
                    enhanced_ui.show_banner()
                    enhanced_ui.show_detailed_token_summary()
                    continue
                if user_input.lower().startswith("/save"):
                    parts = user_input.split(maxsplit=1)
                    path = parts[1].strip() if len(parts) > 1 else _default_session_path()
                    try:
                        agent.save_session(path)
                        console.print(f"[bold green]✓ Session saved:[/bold green] {path}")
                    except Exception as exc:
                        console.print(f"[bold red]✗ Save failed:[/bold red] {exc}")
                    continue
                if user_input.lower().startswith("/load"):
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
                if user_input.lower().startswith("/team msg "):
                    if not agent.enable_agent_teams or agent.team_manager is None:
                        console.print("[bold red]✗ AgentTeams is disabled.[/bold red]")
                        continue
                    team_cli = _load_team_cli_commands()
                    try:
                        payload = team_cli["parse_team_message_command"](user_input, from_member=agent.name)
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
                if user_input.lower().startswith("/team watch "):
                    if not agent.enable_agent_teams or agent.team_manager is None:
                        console.print("[bold red]✗ AgentTeams is disabled.[/bold red]")
                        continue
                    team_cli = _load_team_cli_commands()
                    try:
                        cmd = team_cli["parse_team_watch_command"](user_input)
                    except ValueError as exc:
                        console.print(f"[bold red]✗ {exc}[/bold red]")
                        continue
                    team_name = str(cmd.get("team_name"))
                    rounds = int(cmd.get("rounds", 15))
                    console.print(
                        f"[bold cyan]Watching team[/bold cyan] {team_name} "
                        f"for {rounds} rounds..."
                    )
                    for i in range(rounds):
                        try:
                            snapshot = agent.team_manager.collect_work(team_name)
                            state = agent.team_manager.export_state()
                        except Exception as exc:
                            console.print(f"[bold red]✗ Team watch failed:[/bold red] {exc}")
                            break
                        counts = snapshot.get("counts", {}) if isinstance(snapshot, dict) else {}
                        queued = int(counts.get("queued", 0) or 0)
                        running = int(counts.get("running", 0) or 0)
                        succeeded = int(counts.get("succeeded", 0) or 0)
                        failed = int(counts.get("failed", 0) or 0)
                        team_state = state.get("teams", {}).get(team_name, {}) if isinstance(state, dict) else {}
                        active = len(team_state.get("active_teammates", [])) if isinstance(team_state, dict) else 0
                        idle = len(team_state.get("idle_teammates", [])) if isinstance(team_state, dict) else 0
                        console.print(
                            f"[dim][{i+1}/{rounds}] "
                            f"queued={queued} running={running} succeeded={succeeded} failed={failed} "
                            f"active={active} idle={idle}[/dim]"
                        )
                        if queued == 0 and running == 0:
                            console.print("[bold green]✓ Team watch reached steady state.[/bold green]")
                            break
                        time.sleep(1.0)
                    continue
                if user_input.lower().startswith("/delegate"):
                    if not agent.enable_agent_teams:
                        console.print("[bold red]✗ AgentTeams is disabled.[/bold red]")
                        continue
                    team_cli = _load_team_cli_commands()
                    try:
                        cmd = team_cli["parse_delegate_command"](user_input)
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
                if user_input.lower() == "/help":
                    team_help = ""
                    if agent.enable_agent_teams:
                        team_cli = _load_team_cli_commands()
                        team_help = (
                            f"{team_cli['TEAM_MSG_USAGE']}\n"
                            f"{team_cli['TEAM_WATCH_USAGE']}\n"
                            f"{team_cli['DELEGATE_USAGE']}\n"
                        )
                    console.print(
                        Panel(
                            "[bold]Available Commands:[/bold]\n"
                            "/model, /info - Show model and usage info\n"
                            "/save [path] - Save session snapshot\n"
                            "/load [path] - Load session snapshot\n"
                            f"{team_help}"
                            "/help - Show this help\n"
                            "exit, quit, q - Exit the chat\n"
                            "init - Generate code_law.md",
                            title="Help",
                            border_style="cyan",
                        )
                    )
                    continue

            if "init" in user_input.lower() and len(user_input) < 10:
                if code_law_exists:
                    console.print("\n[warning]code_law.md already exists.[/warning]")
                    confirm = session.prompt("Regenerate? (yes/no): ").strip().lower()
                    if confirm != "yes":
                        console.print("Cancelled.")
                        continue

                console.print("[info]Initiailizing Agent Protocol...[/info]")
                enhanced_input = (
                    f"{CODE_LAW_GENERATION_PROMPT}\n\n"
                    "请使用 LS、Glob、Grep、Read 等工具探索项目，然后使用 Write 工具生成 code_law.md 文件。"
                )
                enhanced_ui.tool_tree = ToolCallTree()
                enhanced_ui.token_tracker.calls.clear()

                start_time = time.time()
                console.print()
                response = agent.run(enhanced_input, show_raw=args.show_raw)
                elapsed = time.time() - start_time

                console.print()
                enhanced_ui.show_tool_tree()
                _print_assistant_response(response)

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
                continue

            enhanced_ui.tool_tree = ToolCallTree()
            enhanced_ui.token_tracker.calls.clear()

            start_time = time.time()
            console.print()
            response = agent.run(user_input, show_raw=args.show_raw)
            elapsed = time.time() - start_time

            console.print()
            enhanced_ui.show_tool_tree()
            _print_assistant_response(response)

            timing_text = Text()
            timing_text.append(f"⏱️  Completed in {elapsed:.1f}s", style="dim cyan")
            console.print(timing_text)
            enhanced_ui.show_token_summary()
            if agent.enable_agent_teams and agent.team_manager:
                try:
                    enhanced_ui.show_team_progress(agent.team_manager.export_state())
                except Exception:
                    pass
            console.print()

            if args.show_raw and hasattr(agent, "last_response_raw") and agent.last_response_raw is not None:
                console.print(
                    Panel(
                        json.dumps(agent.last_response_raw, ensure_ascii=False, indent=2),
                        title="Raw Response",
                        border_style="dim",
                    )
                )
    finally:
        _maybe_save_session(agent, auto_save_path, auto_save_flag, "finalize")
        agent.close()
