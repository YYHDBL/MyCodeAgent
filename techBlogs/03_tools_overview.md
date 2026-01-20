# 工具系统总览：协议设计、注册机制与调用链路

如果说 ReAct 是主循环，那工具系统就是它的“行动能力”。这一章讲清楚 MyCodeAgent 的工具体系是如何被设计成可控、可追踪、可扩展的。核心依据都在仓库里：`docs/通用工具响应协议.md`、`tools/base.py`、`tools/registry.py`，以及 `tools/builtin/`。

## 1. 为什么先定“协议”
工具不是随便返回一段文本就完事了。MyCodeAgent 先把“输出结构”规定清楚：

- 所有工具返回必须满足统一信封结构
- 顶层字段固定为：`status`、`data`、`text`、`stats`、`context`（错误时可带 `error`）
- 严禁新增其他顶层字段

![通用工具响应协议](/Users/yyhdbl/Documents/agent/Nihil/MyCodeAgent/techBlogs/img/通用工具响应协议.png)

这套规范写在 `docs/通用工具响应协议.md`。它的意义很实际：

- **LLM 可以读 `text`，程序可以读 `data`**，各司其职
- `status` 统一表达成功、部分成功或失败
- `context` 记录执行环境（如 `cwd`、原始参数、解析后的路径），便于回放
- 对长输出或回退策略有明确语义（`partial` + `data.truncated`）

从工程角度讲，这是“工具可组合”的基础。没有协议，工具就只是散装脚本。

## 2. 工具的公共基类
协议不仅写在文档里，也体现在代码基类中。

`tools/base.py` 定义了 `Tool` 抽象基类，并提供了：

- `ToolStatus` 与 `ErrorCode` 的枚举
- `create_success_response / create_partial_response / create_error_response` 的响应构造方法
- 统一的路径与 `cwd` 处理逻辑

这意味着每个工具的实现都可以只关心“业务逻辑”，而由基类保证格式正确。工具输出不是“靠自觉”，而是“靠框架”。

## 3. 工具注册与执行：ToolRegistry
工具调用的中心是 `tools/registry.py`。它负责三件关键事：

1) **注册工具**：支持 Tool 类与函数两种方式（`register_tool` / `register_function`）
2) **执行工具**：统一入口 `execute_tool`，所有调用都经过它
3) **结果标准化**：无论工具返回什么，都会被转换成协议格式的 JSON

此外它还做了一个很关键但容易被忽略的事：**乐观锁注入**。

- 对 `Write/Edit/MultiEdit`，会自动注入期望的 mtime/size
- 这些元数据来自此前的 `Read` 缓存
- 用来避免“读完文件后被别人修改，却直接覆盖写入”这种隐性风险

这一层让工具系统不仅能执行动作，还能保证一定程度的安全性与一致性。

## 4. 内置工具一览
内置工具集中在 `tools/builtin/`，覆盖了编程代理最常见的一组动作：

- **文件与检索**：`ListFilesTool`（LS）、`SearchFilesByNameTool`（Glob）、`GrepTool`、`ReadTool`
- **修改类**：`WriteTool`、`EditTool`、`MultiEditTool`
- **任务管理**：`TodoWriteTool`
- **扩展与脚本**：`SkillTool`、`BashTool`
- **子代理**：`TaskTool`

这不是为了“堆工具”，而是为了把最关键的一批能力做到“稳定可用”。工具越稳定，ReAct 才越可控。

## 5. 工具是如何被模型“看见”的
工具不仅是 Python 代码，还需要在提示词中暴露给模型。MyCodeAgent 的做法是把工具提示写成独立模块，然后在构建系统消息时注入。

- 工具提示放在 `prompts/tools_prompts/`
- `ContextBuilder._load_tool_prompts()` 负责读取并拼接
- 与 L1 system prompt 合并，形成模型的“工具说明书”

这个设计有一个优点：**不绑定某个 Provider 的函数调用协议**，模型只要能读懂提示词，就能进行工具调用。对多模型环境更友好。

## 6. 从调用到观察：完整闭环
一次工具调用在代码里的路径很清晰：

1) 模型输出 `Action: ToolName[JSON]`
2) `CodeAgent._parse_tool_call()` 解析工具名与参数
3) `ToolRegistry.execute_tool()` 执行工具，返回统一协议 JSON
4) `HistoryManager.append_tool()` 写入历史，并在必要时截断
5) 下一轮 ReAct 从新的历史继续

其中“截断”会触发 `core/context_engine/observation_truncator.py`，并把完整输出落盘到 `tool-output/`。这一步虽然属于上下文工程，但对工具系统同样关键：**工具输出再大也不会把对话系统拖垮**。

## 7. 小结
工具系统的核心不是“工具数量”，而是“协议 + 注册 + 闭环”。在 MyCodeAgent 里：

- 协议负责统一输出与语义
- 基类保证工具实现不跑偏
- 注册器负责执行与一致性
- 调用链路明确、可追踪、可回放

这也是后续几章要展开的部分：单个工具如何做到可靠、编辑类工具如何防止误写、Task 子代理如何在边界内工作。

---

