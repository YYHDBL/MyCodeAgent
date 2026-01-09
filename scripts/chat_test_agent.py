import argparse
import json
import os
import readline
import sys
from pathlib import Path

# Ensure project root is on sys.path when running as a script
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.llm import HelloAgentsLLM
from agents.codeAgent import CodeAgent
from tools.registry import ToolRegistry
from prompts.agents_prompts.init_prompt import CODE_LAW_GENERATION_PROMPT

# code_law.md 生成提示词



def check_code_law_exists(project_root: str) -> bool:
    """检查 code_law.md 是否存在"""
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

    llm = HelloAgentsLLM(
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        provider=args.provider,
        temperature=args.temperature,
    )
    tool_registry = ToolRegistry()
   

    agent = CodeAgent(
        name=args.name,
        llm=llm,
        tool_registry=tool_registry,
        project_root=PROJECT_ROOT,
        system_prompt=args.system,
    )

    # 检查 code_law.md 是否存在
    code_law_exists = check_code_law_exists(PROJECT_ROOT)
    
    # 显示欢迎信息
    print("=" * 60)
    print("Welcome to CodeAgent!")
    print("=" * 60)
    
    if not code_law_exists:
        print("\n💡 提示：首次使用建议初始化项目")
        print("   输入 'init' 让 Agent 生成 CODE_LAW.md 文件")
        print("   该文件包含项目结构、编码规范等信息，有助于 Agent 更好地理解项目")
    else:
        print("\n✅ code_law.md 已存在")
    
    print("\nType 'exit' to quit.")
    print("-" * 60)
    
    try:
        while True:
            try:
                user_input = input("\nyou> ").strip()
            except EOFError:
                print()
                break

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "q"}:
                break

            # 检测是否为初始化命令
            if "init" in user_input.lower():
                if code_law_exists:
                    print("\n⚠️  code_law.md 已存在，是否重新生成？")
                    confirm = input("输入 'yes' 确认重新生成: ").strip().lower()
                    if confirm != "yes":
                        print("已取消。")
                        continue
                
                print("\n🚀 开始生成 code_law.md...")
                print("   Agent 将探索项目结构并生成文档...")
                
                # 将生成提示词附加到用户输入
                enhanced_input = f"{CODE_LAW_GENERATION_PROMPT}\n\n请使用 LS、Glob、Grep、Read 等工具探索项目，然后使用 Write 工具生成 code_law.md 文件。"
                
                response = agent.run(enhanced_input, show_raw=args.show_raw)
                print("\n=== assistant ===")
                print(response)
                print("====================")
                
                # 检查是否成功生成
                if check_code_law_exists(PROJECT_ROOT):
                    print("\n✅ code_law.md 已成功生成！")
                    code_law_exists = True
                else:
                    print("\n⚠️  code_law.md 未能生成，请检查 Agent 输出")
            else:
                # 正常对话
                response = agent.run(user_input, show_raw=args.show_raw)
                print("\n=== assistant ===")
                print(response)
                print("====================")

            if args.show_raw and hasattr(agent, "last_response_raw") and agent.last_response_raw is not None:
                print()
                print("----- raw response -----")
                print(json.dumps(agent.last_response_raw, ensure_ascii=False, indent=2))
                print("------------------------")
    finally:
        agent.close()


if __name__ == "__main__":
    main()
