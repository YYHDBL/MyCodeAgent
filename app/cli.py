"""CLI entrypoint for the canonical local chat harness."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

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

from app.bootstrap import build_runtime
from core.env import load_env
from prompts.agents_prompts.init_prompt import CODE_LAW_GENERATION_PROMPT
from runtime.host import CodeAgent
from utils.ui_components import EnhancedUI, ToolCallTree

load_env()

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

    def _execute_tool(self, tool_name: str, tool_input: Any):
        if self.ui:
            self.ui.show_tool_call(tool_name, tool_input)
            if tool_name == "Task":
                mode = ""
                if isinstance(tool_input, dict):
                    mode = str(tool_input.get("mode", "") or "").strip()
                mode_suffix = f" mode={mode}" if mode else ""
                console.print(
                    f"[bold magenta]⚡ Task Dispatch[/bold magenta] "
                    f"{tool_name}{mode_suffix}"
                )

        with console.status(f"[bold cyan]Executing {tool_name}...[/bold cyan]", spinner="dots"):
            result = super()._execute_tool(tool_name, tool_input)

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


def _default_session_path(project_root: str) -> str:
    transcripts_dir = os.path.join(project_root, "memory", "transcripts")
    os.makedirs(transcripts_dir, exist_ok=True)
    return transcripts_dir


def _maybe_save_session(agent: CodeAgent, flag: dict[str, bool], reason: str) -> None:
    if flag.get("saved"):
        return
    try:
        path = agent.transcript_path()
        console.print(f"[dim]Session is durable in transcript ({reason}): {path}[/dim]")
        flag["saved"] = True
    except Exception as exc:
        console.print(f"[bold red]✗ Session status failed:[/bold red] {exc}")


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


def _one_shot_outcome(
    agent: Any,
    response: str,
    *,
    terminal_reason: Optional[str] = None,
) -> dict[str, Any]:
    """Adapt the current trace protocol into the scriptable CLI result contract."""

    trace_logger = getattr(agent, "trace_logger", None)
    session_id = getattr(trace_logger, "session_id", None)
    if session_id is None:
        session_id = getattr(getattr(agent, "transcript_store", None), "session_id", None)

    terminal_details: dict[str, Any] = {}
    if terminal_reason is None and trace_logger and hasattr(trace_logger, "get_current_run_events"):
        for event in reversed(trace_logger.get_current_run_events()):
            if event.get("event") != "terminal":
                continue
            payload = event.get("payload") or {}
            terminal_reason = payload.get("reason")
            terminal_details = payload.get("details") or {}
            break

    terminal_reason = terminal_reason or "completed"
    status = "success" if terminal_reason in {"completed", "completed_unverified"} else "failure"
    outcome: dict[str, Any] = {
        "status": status,
        "response": response,
        "session_id": session_id,
        "terminal_reason": terminal_reason,
    }

    usage = getattr(trace_logger, "_total_usage", None)
    if isinstance(usage, dict):
        outcome["usage"] = dict(usage)
    verification = {
        key: value
        for key, value in terminal_details.items()
        if key.startswith("completion_") or key.startswith("verification")
    }
    if verification:
        outcome["verification"] = verification
    return outcome


def _write_one_shot_outcome(outcome: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(outcome, ensure_ascii=False))
    else:
        print(outcome["response"])


@dataclass(frozen=True)
class InteractiveTurnOutcome:
    response: str | None
    cancelled: bool = False


def run_interactive_turn(agent: Any, user_input: str, *, show_raw: bool) -> InteractiveTurnOutcome:
    """Run one prompt and keep an interrupt scoped to that prompt."""

    try:
        return InteractiveTurnOutcome(agent.run(user_input, show_raw=show_raw))
    except KeyboardInterrupt:
        result = agent.cancel_active_turn()
        if result.get("cancelled"):
            console.print("[warning]Turn cancelled. The session can be resumed from its transcript.[/warning]")
        else:
            console.print("[warning]Turn interrupted before runtime work started.[/warning]")
        return InteractiveTurnOutcome(None, cancelled=True)


def handle_lifecycle_command(agent: Any, user_input: str) -> bool:
    """Render transcript lifecycle commands using the host's public API."""

    command, _, argument = user_input.strip().partition(" ")
    command = command.lower()
    argument = argument.strip()
    if command == "/status":
        console.print(json.dumps(agent.get_session_status(), ensure_ascii=False, sort_keys=True))
        return True
    if command == "/sessions":
        sessions = agent.list_transcript_sessions()
        if not sessions:
            console.print("[dim]No transcript sessions found.[/dim]")
            return True
        for item in sessions:
            console.print(f"{item.session_id}  latest={item.latest_run_id or '-'}")
        return True
    if command == "/resume":
        try:
            resume = agent.resume_transcript(argument or None)
        except ValueError as exc:
            console.print(f"[bold red]✗ Resume failed:[/bold red] {exc}")
            return True
        console.print(f"[bold green]✓ Resumed transcript:[/bold green] {resume.session_id} ({resume.run_id})")
        for action in resume.uncertain_actions:
            console.print(
                f"[warning]Uncertain action: {action.tool_name} ({action.tool_call_id}); verify before retrying.[/warning]"
            )
        return True
    return False


def run_one_shot(args: Any, runtime: Any) -> int:
    """Run one prompt through the canonical runtime and render only its final outcome."""

    agent = runtime.agent
    json_output = bool(getattr(args, "json", False))
    try:
        response = agent.run(
            args.print_prompt,
            show_raw=bool(getattr(args, "show_raw", False)),
        )
    except KeyboardInterrupt:
        cancel = getattr(agent, "cancel_active_turn", None)
        if callable(cancel):
            cancel()
        outcome = _one_shot_outcome(agent, "", terminal_reason="interrupted")
        outcome["status"] = "interrupted"
        exit_code = 130
    except Exception as exc:
        outcome = _one_shot_outcome(agent, "", terminal_reason="runtime_error")
        outcome["error"] = str(exc)
        exit_code = 1
    else:
        outcome = _one_shot_outcome(agent, response)
        exit_code = 0 if outcome["status"] == "success" else 1
    finally:
        agent.close()

    _write_one_shot_outcome(outcome, json_output=json_output)
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the MyCodeAgent local coding harness")
    parser.add_argument("--name", default="code", help="agent name")
    parser.add_argument("--system", default=None, help="system prompt")
    parser.add_argument("--provider", default=None, help="llm provider (override LLM_PROVIDER)")
    parser.add_argument("--model", default=None, help="model name (override LLM_MODEL_ID)")
    parser.add_argument("--api-key", default=None, help="api key (override LLM_API_KEY)")
    parser.add_argument("--base-url", default=None, help="base url (override LLM_BASE_URL)")
    parser.add_argument("--temperature", type=float, default=None, help="temperature (override TEMPERATURE)")
    parser.add_argument(
        "--cwd",
        default=None,
        help="target project directory (defaults to the invocation directory)",
    )
    parser.add_argument("--enable-mcp", action="store_true", help="enable optional MCP tools")
    parser.add_argument(
        "--enable-verification-agent",
        action="store_true",
        help="enable the optional verification subagent",
    )
    parser.add_argument("--show-raw", action="store_true", help="print raw response structure")
    parser.add_argument("-p", "--print", dest="print_prompt", help="run one prompt and exit")
    parser.add_argument("--json", action="store_true", help="emit one-shot outcome as JSON")
    parser.add_argument(
        "--resume",
        nargs="?",
        const="",
        default=None,
        help="resume a transcript session (latest session when no ID is supplied)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    one_shot = getattr(args, "print_prompt", None) is not None
    if getattr(args, "json", False) and not one_shot:
        parser.error("--json requires -p/--print")
    if one_shot and not args.print_prompt.strip():
        parser.error("-p/--print requires a non-empty prompt")

    try:
        runtime_kwargs: dict[str, Any] = {
            "agent_class": CodeAgent if one_shot else RichConsoleCodeAgent
        }
        if not one_shot:
            runtime_kwargs["agent_kwargs_factory"] = lambda config, llm, project_root: {
                "ui": EnhancedUI(
                    console=console,
                    model=llm.model,
                    provider=llm.provider,
                    project_root=project_root,
                    version="v1.0",
                )
            }
        runtime = build_runtime(args, **runtime_kwargs)
    except Exception as exc:
        if one_shot and getattr(args, "json", False):
            _write_one_shot_outcome(
                {
                    "status": "invalid_input",
                    "response": "",
                    "session_id": None,
                    "terminal_reason": "invalid_configuration",
                    "error": str(exc),
                },
                json_output=True,
            )
        elif one_shot:
            print(f"Failed to initialize runtime: {exc}", file=sys.stderr)
        else:
            console.print(f"[error]Failed to initialize runtime: {exc}[/error]")
        raise SystemExit(2)

    if one_shot:
        if getattr(args, "resume", None) is not None:
            try:
                runtime.agent.resume_transcript(getattr(args, "resume") or None)
            except ValueError as exc:
                if getattr(args, "json", False):
                    _write_one_shot_outcome(
                        {
                            "status": "invalid_input",
                            "response": "",
                            "session_id": None,
                            "terminal_reason": "invalid_resume",
                            "error": str(exc),
                        },
                        json_output=True,
                    )
                else:
                    print(f"Failed to resume transcript: {exc}", file=sys.stderr)
                runtime.agent.close()
                raise SystemExit(2)
        raise SystemExit(run_one_shot(args, runtime))

    agent = runtime.agent
    project_root = runtime.project_root
    enhanced_ui = agent.ui
    code_law_exists = check_code_law_exists(project_root)
    _print_banner(code_law_exists, enhanced_ui)
    _default_session_path(project_root)
    auto_save_flag = {"saved": False}

    if getattr(args, "resume", None) is not None:
        try:
            resume = agent.resume_transcript(getattr(args, "resume") or None)
        except ValueError as exc:
            console.print(f"[error]Failed to resume transcript: {exc}[/error]")
            agent.close()
            raise SystemExit(2)
        console.print(f"[bold green]✓ Resumed transcript:[/bold green] {resume.session_id} ({resume.run_id})")

    history_file = os.path.join(project_root, ".chat_history")
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
                _maybe_save_session(agent, auto_save_flag, "keyboard interrupt")
                break

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "q"}:
                console.print("\n[dim]Shutting down...[/dim]")
                _maybe_save_session(agent, auto_save_flag, "exit")
                break

            if user_input.startswith("/"):
                if handle_lifecycle_command(agent, user_input):
                    continue
                if user_input.lower() in {"/model", "/info"}:
                    enhanced_ui.show_banner()
                    enhanced_ui.show_detailed_token_summary()
                    continue
                if user_input.lower().startswith("/save"):
                    try:
                        console.print(
                            f"[bold green]✓ Session transcript is already durable:[/bold green] {agent.transcript_path()}"
                        )
                    except Exception as exc:
                        console.print(f"[bold red]✗ Save failed:[/bold red] {exc}")
                    continue
                if user_input.lower().startswith("/load"):
                    parts = user_input.split(maxsplit=1)
                    path = parts[1].strip() if len(parts) > 1 else str(agent.transcript_path())
                    if not os.path.exists(path):
                        console.print(f"[bold red]✗ Session not found:[/bold red] {path}")
                        continue
                    try:
                        agent.load_transcript(path)
                        console.print(f"[bold green]✓ Transcript loaded:[/bold green] {path}")
                    except Exception as exc:
                        console.print(f"[bold red]✗ Load failed:[/bold red] {exc}")
                    continue
                if user_input.lower() == "/help":
                    console.print(
                        Panel(
                            "[bold]Available Commands:[/bold]\n"
                            "/model, /info - Show model and usage info\n"
                            "/status - Show session and runtime status\n"
                            "/sessions - List transcript sessions\n"
                            "/resume [id] - Resume a transcript session\n"
                            "/save - Show durable transcript path\n"
                            "/load [path] - Load transcript (or import one legacy snapshot)\n"
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

                console.print("[info]Initializing Agent Protocol...[/info]")
                enhanced_input = (
                    f"{CODE_LAW_GENERATION_PROMPT}\n\n"
                    "请使用 Glob、Grep、Read 等工具探索项目，然后使用 Edit 工具创建 code_law.md 文件。"
                )
                enhanced_ui.tool_tree = ToolCallTree()
                enhanced_ui.token_tracker.calls.clear()

                start_time = time.time()
                console.print()
                turn = run_interactive_turn(agent, enhanced_input, show_raw=args.show_raw)
                if turn.cancelled:
                    continue
                response = turn.response or ""
                elapsed = time.time() - start_time

                console.print()
                enhanced_ui.show_tool_tree()
                _print_assistant_response(response)

                timing_text = Text()
                timing_text.append(f"⏱️  Completed in {elapsed:.1f}s", style="dim cyan")
                console.print(timing_text)
                enhanced_ui.show_token_summary()
                console.print()

                if check_code_law_exists(project_root):
                    console.print("[bold green]✓ code_law.md generated successfully.[/bold green]")
                    code_law_exists = True
                else:
                    console.print("[bold red]✗ Failed to generate code_law.md[/bold red]")
                continue

            enhanced_ui.tool_tree = ToolCallTree()
            enhanced_ui.token_tracker.calls.clear()

            start_time = time.time()
            console.print()
            turn = run_interactive_turn(agent, user_input, show_raw=args.show_raw)
            if turn.cancelled:
                continue
            response = turn.response or ""
            elapsed = time.time() - start_time

            console.print()
            enhanced_ui.show_tool_tree()
            _print_assistant_response(response)

            timing_text = Text()
            timing_text.append(f"⏱️  Completed in {elapsed:.1f}s", style="dim cyan")
            console.print(timing_text)
            enhanced_ui.show_token_summary()
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
        _maybe_save_session(agent, auto_save_flag, "finalize")
        agent.close()
