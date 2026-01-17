ask_user_prompt = """
## AskUser
当需要用户提供信息才能继续时使用此工具（如缺少 API Key、路径或配置）。

参数：
- questions: 问题列表，每项包含 id/text/type/options/required

示例（参数）：
{
  "questions": [
    {"id": "api_key", "text": "请提供 API Key", "type": "text", "required": true},
    {"id": "framework", "text": "项目使用什么框架？", "type": "text"}
  ]
}
"""
