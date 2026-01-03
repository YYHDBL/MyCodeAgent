import argparse
import json
import os
import readline
import sys

# Ensure project root is on sys.path when running as a script
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.llm import HelloAgentsLLM
from agents.testAgent import TestAgent
from agents.codeAgent import CodeAgent
from tools.registry import ToolRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat with TestAgent")
    parser.add_argument("--name", default="test", help="agent name")
    parser.add_argument("--agent", choices=["test", "code"], default="code", help="which agent to run")
    parser.add_argument("--system", default=None, help="system prompt")
    parser.add_argument("--provider", default="zhipu", help="llm provider")
    parser.add_argument("--model", default="GLM-4.7", help="model name")
    parser.add_argument("--api-key", default=None, help="api key")
    parser.add_argument("--base-url", default=None, help="base url")
    parser.add_argument("--temperature", type=float, default=0.7, help="temperature")
    parser.add_argument("--show-raw", action="store_true", help="print raw response structure")
    parser.add_argument("--react", dest="use_react", action="store_true", default=True, help="use ReAct engine")
    parser.add_argument("--no-react", dest="use_react", action="store_false", help="disable ReAct engine")
    args = parser.parse_args()

    llm = HelloAgentsLLM(
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        provider=args.provider,
        temperature=args.temperature,
    )
    tool_registry = ToolRegistry()
   

    if args.agent == "code":
        agent = CodeAgent(
            name=args.name,
            llm=llm,
            tool_registry=tool_registry,
            project_root=PROJECT_ROOT,
        )
    else:
        agent = TestAgent(
            name=args.name,
            llm=llm,
            system_prompt=args.system,
            tool_registry=tool_registry,
            project_root=PROJECT_ROOT,
        )

    print("Type 'exit' to quit.")
    while True:
        try:
            user_input = input("you> ").strip()
        except EOFError:
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q"}:
            break

        if args.agent == "code":
            response = agent.run(user_input, show_raw=args.show_raw)
        else:
            response = agent.run(
                user_input,
                use_llm=True,
                use_react=args.use_react,
                show_raw=args.show_raw,
            )
        print("\n=== assistant ===")
        print(response)
        print("====================")

        if args.show_raw and hasattr(agent, "last_response_raw") and agent.last_response_raw is not None:
            print()
            print("----- raw response -----")
            print(json.dumps(agent.last_response_raw, ensure_ascii=False, indent=2))
            print("------------------------")


if __name__ == "__main__":
    main()
