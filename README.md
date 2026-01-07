# MyCodeAgent

基于 ReAct（Reasoning + Acting）架构的 AI 智能体框架，用于自动化代码分析和编程任务。

## 特性

- **ReAct 推理引擎**：Thought → Action → Observation 循环，智能决策和执行
- **统一工具协议**：所有工具遵循标准响应协议，输出结构一致
- **多 LLM 支持**：支持 OpenAI、DeepSeek、Qwen、智谱 AI 等
- **沙箱安全**：文件操作严格限制在项目根目录内
- **完整测试**：提供单元测试和协议合规性验证

## 快速开始

### 安装

```bash
# 克隆项目
git clone <repository-url>
cd MyCodeAgent

# 安装依赖
pip install -r requirements.txt
```

### 配置

创建 `.env` 文件或设置环境变量：

```bash
# OpenAI（默认）
export OPENAI_API_KEY="your-api-key"

# DeepSeek
export DEEPSEEK_API_KEY="your-api-key"

# 智谱 AI
export GLM_API_KEY="your-api-key"

# 自定义 API 地址
export LLM_BASE_URL="https://your-api-endpoint"
```

### 运行

```bash
# 运行代码智能体
python scripts/chat_test_agent.py --show-raw

# 指定提供商和模型
python scripts/chat_test_agent.py --provider zhipu --model GLM-4.7
```

## 架构

```
MyCodeAgent
├── core/              # 基础层
│   ├── agent.py       # Agent 基类
│   ├── llm.py         # HelloAgentsLLM 统一接口
│   ├── message.py     # 消息系统
│   └── config.py      # 配置管理
├── agents/            # 智能体层
│   └── codeAgent.py   # 代码智能体
├── agentEngines/      # 推理引擎层（已合并到 CodeAgent）
├── tools/             # 工具层
│   ├── registry.py    # 工具注册中心
│   └── builtin/       # 内置工具
│       ├── list_files.py         → LS（目录列表）
│       ├── search_files_by_name.py → Glob（文件搜索）
│       ├── search_code.py        → Grep（代码搜索）
│       ├── read_file.py          → Read（文件读取）
│       └── write_file.py         → Write（文件写入）
└── prompts/           # 提示词
    └── tools_prompts/ # 工具描述
```

## 内置工具

| 工具 | 功能 |
|------|------|
| **LS** | 列出目录内容，支持递归和限制条目数 |
| **Glob** | 按通配符模式搜索文件 |
| **Grep** | 在代码中搜索文本或正则表达式 |
| **Read** | 读取文件内容，支持行范围和限制 |
| **Write** | 写入或覆盖文件，支持 diff 预览和 dry-run |

所有工具响应遵循 [通用工具响应协议](docs/通用工具响应协议.md)。

## 开发

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行单个工具测试
python -m pytest tests/test_write_tool.py -v
python -m pytest tests/test_read_tool.py -v

# 协议合规性测试
python -m pytest tests/test_protocol_compliance.py -v
```

### 添加新工具

1. 继承 `tools.base.Tool` 基类
2. 实现 `run()` 方法，返回标准响应格式
3. 在 `tools.registry.ToolRegistry` 中注册
4. 在 `prompts/tools_prompts/` 添加工具描述

示例：

```python
from tools.base import Tool, ToolStatus, ErrorCode

class MyTool(Tool):
    def run(self, parameters: dict) -> str:
        # 参数校验
        if not parameters.get("required_param"):
            return self.create_error_response(
                error_code=ErrorCode.INVALID_PARAM,
                message="required_param is missing",
                params_input=parameters,
            )

        # 执行逻辑
        result = self._do_work(parameters)

        # 返回响应
        return self.create_success_response(
            data={"result": result},
            text=f"操作成功: {result}",
            params_input=parameters,
        )
```

### 工具响应协议

所有工具必须返回以下结构：

```json
{
  "status": "success" | "partial" | "error",
  "data": { ... },
  "text": "人类可读摘要",
  "stats": { "time_ms": 100, ... },
  "context": {
    "cwd": ".",
    "params_input": { ... }
  },
  "error": { "code": "...", "message": "..." }
}
```

详细规范见 [docs/通用工具响应协议.md](docs/通用工具响应协议.md)。

## 项目结构

- `AGENTS.md` - 项目指南和编码规范
- `CLAUDE.md` - Claude Code 工作指南
- `docs/` - 详细设计文档
  - `通用工具响应协议.md` - 工具响应协议规范
  - `WriteTool设计文档.md` - Write 工具设计
  - `ReAct历史管理设计分析.md` - ReAct 历史管理分析
- `tests/` - 测试套件

## 许可证

[待添加]
