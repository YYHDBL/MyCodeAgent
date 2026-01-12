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

# Geeky Theme
custom_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "error": "bold red",
    "user": "bold green",
    "agent": "bold blue",
    "banner": "bold cyan",
    "thinking": "italic yellow",
    "action": "bold cyan",
    "observation": "dim",
})

console = Console(theme=custom_theme)

class RichConsoleCodeAgent(CodeAgent):
    """
    Extensions of CodeAgent with Rich UI features.
    Overrides _console and _execute_tool to provide better visual feedback.
    """
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
        """Override to show spinner during actual tool execution"""
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

def _print_banner(code_law_exists: bool) -> None:
    banner_text = """
   ______          __      ___                     __ 
  / ____/___  ____/ /___  /   |____ ____  ____  / /_
 / /   / __ \/ __  / _ \/ /| / __ `/ _ \/ __ \/ __/
/ /___/ /_/ / /_/ /  __/ ___ / /_/ /  __/ / / / /_  
\____/\____/\__,_/\___/_/  |_\__, /\___/_/ /_/\__/  
                            /____/                  
    """
    console.print(Text(banner_text, style="banner"))
    console.print("[dim]Powered by Nihil CodeAgent v1.0[/dim]")
    console.print("[dim]Type 'exit' to quit[/dim]")
    
    if not code_law_exists:
        console.print(Panel("⚠️  code_law.md missing. Type 'init' to generate it.", style="yellow", title="Setup Required"))
    console.print()

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
    parser.add_argument("--provider", default="zhipu", help="llm provider")
    parser.add_argument("--model", default="GLM-4.7", help="model name")
    parser.add_argument("--api-key", default=None, help="api key")
    parser.add_argument("--base-url", default="https://open.bigmodel.cn/api/coding/paas/v4", help="base url")
    parser.add_argument("--temperature", type=float, default=0.7, help="temperature")
    parser.add_argument("--show-raw", action="store_true", help="print raw response structure")
    args = parser.parse_args()

    # Initialize LLM
    try:
        llm = HelloAgentsLLM(
            model=args.model,
            api_key=args.api_key,
            base_url=args.base_url,
            provider=args.provider,
            temperature=args.temperature,
        )
    except Exception as e:
        console.print(f"[error]Failed to initialize LLM: {e}[/error]")
        return

    tool_registry = ToolRegistry()
   
    # Ensure config has show_react_steps=True for our RichConsoleCodeAgent to receive events
    config = Config.from_env()
    config.show_react_steps = True

    agent = RichConsoleCodeAgent(
        name=args.name,
        llm=llm,
        tool_registry=tool_registry,
        project_root=PROJECT_ROOT,
        system_prompt=args.system,
        config=config,
    )

    code_law_exists = check_code_law_exists(PROJECT_ROOT)
    _print_banner(code_law_exists)

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
                break

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "q"}:
                console.print("\n[dim]Shutting down...[/dim]")
                break

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
                
                # Use a specific status for the overall process if not covered by internal steps
                # But since RichConsoleCodeAgent prints steps, we don't want a blocking status spinner covering them.
                # So we just run it.
                response = agent.run(enhanced_input, show_raw=args.show_raw)
                
                _print_assistant_response(response)
                
                if check_code_law_exists(PROJECT_ROOT):
                    console.print("[bold green]✓ code_law.md generated successfully.[/bold green]")
                    code_law_exists = True
                else:
                    console.print("[bold red]✗ Failed to generate code_law.md[/bold red]")
            else:
                # Normal chat
                # We remove the outer 'status' context manager because RichConsoleCodeAgent 
                # will manage its own output and spinners for tools.
                # Use a simple "Thinking..." indicator that is cleared once agent starts printing.
                # Since agent prints immediately "Engine Started", we can skips the outer spinner or use a transient one.
                
                console.print("[italic yellow]Agent is thinking...[/italic yellow]")
                response = agent.run(user_input, show_raw=args.show_raw)
                
                _print_assistant_response(response)

            if args.show_raw and hasattr(agent, "last_response_raw") and agent.last_response_raw is not None:
                console.print(Panel(json.dumps(agent.last_response_raw, ensure_ascii=False, indent=2), title="Raw Response", border_style="dim"))
                
    finally:
        agent.close()

if __name__ == "__main__":
    main()
