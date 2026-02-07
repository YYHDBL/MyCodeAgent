# 从零开始手搓 Code Agent：一个初学者的踩坑实录与学习笔记

> **写在最前**：这篇文章记录了我作为一个 Agent 开发初学者，跟着 [Datawhale](https://github.com/datawhalechina) 的 Hello-Agent 教程一步步学习和实践的过程。文中提到的很多实现方案可能并不完美，甚至可能存在更好的做法，但这些都是我真真切切踩过的坑、流过的汗。如果你也是刚开始接触 Agent 开发，希望这篇笔记能给你一些参考；如果你已经是大佬，还请不吝赐教。

---

## 01 为什么我要自己做一个 Code Agent

这两年 AI 编程助手火得一塌糊涂。

GitHub Copilot、Cursor、Claude Code、Codex……工具一个比一个强。用自然语言描述需求，它就能写代码、改 Bug、跑测试，甚至帮你排查那些以前要绞尽脑汁的线上问题。

有意思的是，Anthropic、OpenAI 这些前沿团队也在持续公开他们的 Agent 构建经验。虽然他们的模型在国内有门槛，但 Engineering Blog 我一直在追。每次读完都很上头——你会发现，真正拉开差距的不是"提示词写得多花"，而是**工程设计是否扎实**。

看了这么多，手痒了。

正好，**[Datawhale](https://github.com/datawhalechina)** 的 Hello-Agent 教程最后有一个毕业设计：用学到的知识，做一个自己的智能体应用。

我当时就想，既然日常高强度在用各种 Code Agent，不如就做一个自己的。

**说白了，自己手搓一遍，才能真正理解这些产品为什么好用，以及它们到底在工程上做对了什么。**

![1](/Users/yyhdbl/Documents/agent/Nihil/MyCodeAgent/docs/wechat_mycodeagent_article/assest/1.png)

---

## 02 先跑起来！用 Hello-Agent 骨架搭出第一个能用的 Code Agent

有了方向，我没急着追什么"最优架构"。

先给自己定了一个很接地气的目标：**用户说一句需求，Agent 能自己去仓库里找证据，给出改动方案，输出补丁，我确认后能真正落盘。**

说白了，我要的不是一个会聊天的 Demo，而是一个**能干活的 CLI**。

Hello-Agent 的底子正好够用——ReActAgent、ToolRegistry、ContextBuilder 这些核心组件都是现成的。我的策略很简单：**先复用，再改造**。

最初版本的Code Agent代码仓库：https://github.com/YYHDBL/HelloCodeAgentCli.git

### 起手式：先复用，再改造

我的动作很克制——直接复用 Hello-Agent 的主干，把最短链路先跑通。

核心组件就这几块：

| 组件 | 干嘛的 |
|-----|--------|
| ReActAgent | Thought → Action → Observation 循环 |
| ToolRegistry | 工具注册和调用分发 |
| ContextBuilder | 拼接系统规则、历史、证据 |
| TerminalTool | 仓库内执行命令 |
| Message | 会话消息结构 |

代码层面，我直接在 `code_agent.py` 里把它们攒起来：

```python
self.terminal_tool = TerminalTool(
    workspace=str(self.paths.repo_root),
    timeout=60,
    confirm_dangerous=True,
    default_shell_mode=True,  # 注意这个
)
self.registry = ToolRegistry()
self.registry.register_tool(self.terminal_tool)
```

这里有两个关键决策，后面都成了坑：

**第一，`default_shell_mode=True`。**

我当时想的是"先把能力放开"，让模型能直接写复杂 shell，效率优先。

**第二，工具堆得挺满。**

不光有 `terminal`，我还把 `todo`、`note`、`plan`、`context_fetch` 一股脑塞进去，想让它从第一天就能处理连续任务。

现在回头看，这个取舍挺典型——**能力上限先拉高，控制边界后补**。

### V0 怎么算"能用"？我定了四条

不是看"回答像不像人"，而是看这四件事能不能连续跑通：

1. **能稳定多步** —— 不是一句话就结束；
2. **能在仓库找证据** —— 目录、文件、代码片段；
3. **能给可执行的补丁** —— 不停在口头建议；
4. **改动可控** —— 能确认、能备份、能撤回。

为了防跑飞，我给 ReAct 加了最基础的保险：

```python
self.react = ReActAgent(
    name="code_agent",
    llm=self.llm,
    tool_registry=self.registry,
    max_steps=20,  # 最多跑 20 步
    observation_summarizer=_summarize_observation,
    summarize_threshold_chars=1800,
)
```

`max_steps=20` + observation 摘要，当时救了我不少次。

### V0 的边界与妥协

**它能干什么：**
- 单轮需求理解 + 多步执行
- 在仓库里自主找证据（grep、ls、cat）
- 生成 diff 并落盘

**它干不了什么：**
- 连续对话（没有持久化记忆）
- 复杂规划（没有任务分解）
- 并发或异步执行

**核心妥协：**
把 `TerminalTool` 的权限放得很大，想换取效率。结果证明，**这个妥协迟早要还**。

不过在当时，它确实让我验证了一件事：**这条路走得通。**

先复用再改造的策略走对了——最短路径验证想法，再逐步替换薄弱点。

**这套 V0 给我的最大启发是：别在第一天就想清楚所有架构，先让东西跑起来。**

但很快，我就尝到了"自由"的苦头。

---

## 03 自由是把双刃剑：我的 Terminal Tool 是怎么失控的

V0 跑通之后，我开始得意了。

Agent 能自己查文件、跑命令、输出补丁，感觉挺酷的。但没过多久，我就遇到了第一次"翻车"。

### 那个让我懵了的下午

那天我让 Agent 做一个简单任务：**"查看 demo 目录下有哪些文件，然后告诉我。"**

看起来人畜无害，对吧？

结果 Terminal Tool 返回了这么一堆：

```
$ ls -la demo/
总用量 24
drwxr-xr-x  3 user  staff   96 Jan  3 14:22 .
drwxr-xr-x  12 user  staff  384 Jan  3 14:20 ..
-rw-r--r--  1 user  staff  1234 Jan  3 14:22 test.py

$ echo "Command executed successfully"
Command executed successfully

$ echo "Files in directory: 1"
Files in directory: 1
```

这啥？！

我只是想问个目录内容，它给我返回了三行命令 + 三行输出 + 两行废话。**token 哗啦啦地烧，上下文瞬间被污染。**

更离谱的还在后面。

### 管道操作的灾难

我又试了一个稍复杂的任务：**"找出所有包含 'TODO' 的 Python 文件。"**

Agent 决定用管道：

```bash
find . -name "*.py" | xargs grep -l "TODO" 2>/dev/null | head -20
```

这命令本身没问题。但问题是，**执行过程中出错了**：

```
find: ./venv: Permission denied
xargs: grep: No such file or directory
```

错误信息被管道重定向到了 `2>/dev/null`，Agent 看到的是**空输出**。

它以为"没找到文件"，实际上只是命令执行失败了。结果它给我回复："经过全面搜索，您的代码库中没有包含 TODO 的 Python 文件。"

**我差点信了这个结论。**

直到我自己手动跑了一遍，才发现它漏掉了十几个文件。

### 输出爆炸与上下文污染

还有一次，我让 Agent 查看一个日志文件：

```bash
cat logs/debug.log
```

没想到这个日志有 **5MB**。

Agent 毫不犹豫地执行了，然后——**整个上下文被这 5MB 的日志塞满**。后面的对话它直接"失忆"，因为上下文窗口被撑爆了。

那一刻我才意识到：Terminal Tool 的自由度太高了，高到可以轻易摧毁整个会话。

### 核心问题：我给了它一把没有保险的手枪

这三个问题，本质上是同一个：**Terminal Tool 太自由了。**

- 可以随意组合命令（管道、重定向）
- 没有任何输出限制（5MB 也照单全收）
- 错误处理全靠模型自己判断（而模型经常判断错）

**我当时把"自由"当成了"能力"，却没想过"自由"也意味着"失控"。**

就像一个实习生，你给他一把万能钥匙，他能打开任何门，但也可能把档案室烧了。

### 必须拆了它

V0 的 Terminal Tool 就像一个万能瑞士军刀——功能强大，但用起来心惊胆战。

我尝试过打补丁：加输出限制、加错误解析、加危险命令检查... 但补丁越打越多，代码越来越臃肿，问题却没根治。

有一天我盯着那一堆补丁代码，突然想通了：

> **问题的根源不是 Terminal Tool 有 bug，而是"一个工具做太多事"这个设计本身就有问题。**

如果继续修修补补，我只是在给这个"万能工具"打绷带，而不是从根本上解决问题。

于是，我做了一个艰难的决定：**把 Terminal Tool 拆了。**

不是修，是拆。把它拆成一组原子化的专用工具，每个工具只做一件事，但把它做好。

这个重构花了两周，但结果证明值得——后续三个月，我再也没有因为工具失控而失眠过。

具体怎么拆的？下一章细说。

---

## 04 从"自由狂飙"到"精准可控"：我的工具体系重构实录

踩完 Terminal Tool 的坑，我坐在电脑前愣了半天。

说实话，那一刻我才真正明白：**问题根本不是"工具不够多"，而是"工具太自由了"**。

就像给一辆车装了火箭发动机，却没有方向盘——速度是有了，但你根本不知道会撞到哪。

后来读到一篇解读 Claude Code 的文章，里面讲"工具分层"的理念。有句话特别戳我：**"高频动作更需要确定性"**。

当时我就像被人敲了一闷棍。

对啊！我把所有能力都塞进一个"无限自由"的 Terminal Tool，低频场景确实灵活，但在每天重复几十次的高频动作上，它反而成了**噪音制造机**。

是时候彻底重构了。

### 01、重构目标：每一步都要有"结构化证据"

讲真，这次重构我给自己定了一个核心原则：

> **工具化的本质不是造更多轮子，而是让每一步都有结构化证据。**

什么叫"结构化证据"？说白了就是：模型每走一步，我都能清楚地知道它看到了什么、做了什么、结果怎么样。

按"使用频率"和"确定性需求"，我把工具重新分了类：

| 频率 | 确定性 | 工具 | 设计目标 |
|-----|--------|------|---------|
| 高频 | 强 | LS / Glob / Grep / Read | 原子化、标准化、沙箱 |
| 中频 | 中等 | Write / Edit / MultiEdit | 安全、可确认、乐观锁 |
| 低频 | 弱 | Bash | 兜底、受控、禁网络 |

你看，高频工具要的是**稳**，低频工具要的是**活**。

这套分类法让我少走了很多弯路。不是为了多造几个工具炫技，而是让**每一步都可观察、可判断、可纠错**。

### 02、先统一语言：让所有工具说同一种"方言"

Hello-Agent 早期的工具返回很随意，有的是纯文本，有的是 JSON，有的干脆就是命令行输出原样返回。

模型得自己去"理解"每个工具的输出结构，累不累啊？

我现在搞的是**标准化信封（Standard Envelope）**：`status / data / text / stats / context` 五件套。

来，看个真实的 Glob 工具返回：

```json
{
  "status": "partial",
  "data": {
    "files": ["src/main.py", "src/utils.py"],
    "truncated": true,
    "total": 42
  },
  "text": "找到 42 个文件，展示前 2 个",
  "stats": {"time_ms": 12, "files_scanned": 100},
  "context": {"cwd": "/project", "pattern": "*.py"}
}
```

**为什么这么设计？**

- `status`：成功/部分/失败，模型一眼就知道结果性质
- `data`：结构化数据，方便后续工具链使用
- `text`：给模型看的摘要，人话说明
- `stats`：性能指标，排查问题用
- `context`：执行上下文，便于审计

**模型再也不需要从自由文本里"猜"结果了，标准字段一查便知。**

这就好比你以前收快递，每个快递公司用的包装都不一样，你得一个个拆开来才知道里面是啥。现在我统一用顺丰的标准箱，一眼就能看出里面装的是什么、从哪发来的、有没有破损。

### 03、原子化工具设计：一个工具只干一件事

#### LS（目录浏览）

- 只干一件事：列出目录内容
- 沙箱限制：只能访问项目根目录内
- 返回结构化：文件列表 + 元数据（大小、修改时间）

#### Glob（文件搜索）

- 按模式找文件，支持 `**/*.py` 这种递归匹配
- 结果限制：最多返回 N 个，超长的自动截断并提示
- 统一返回：文件路径列表

#### Grep（代码搜索）

- 搜内容，支持正则
- 返回带行号的结果片段
- 默认限制返回数量，避免输出爆炸

#### Read（文件读取）

- 读文件内容，支持行范围
- 大文件自动截断
- 返回内容 + 文件元数据

#### Write / Edit / MultiEdit

- 写文件、单点编辑、批量编辑三分离
- 乐观锁防并发冲突
- 修改前备份，可撤回

#### Bash（受控兜底）

- 保留但严格限制
- 白名单命令
- 禁止网络、禁止交互、禁止危险操作
- 输出截断保护

你会发现，我把 Bash 放在了最后，而且加了重重限制。讲真，这玩意儿就是个"核武器"——威力大，但用不好会炸到自己。

### 04、响应协议统一：五件套信封

所有工具返回统一结构：

```json
{
  "status": "success" | "partial" | "error",
  "data": {...},
  "text": "给 LLM 阅读的摘要",
  "stats": {"time_ms": 123, ...},
  "context": {"cwd": ".", "params_input": {...}, ...}
}
```

错误处理也标准化：

```json
{
  "status": "error",
  "error": {
    "code": "NOT_FOUND" | "ACCESS_DENIED" | "TIMEOUT" | ...,
    "message": "..."
  }
}
```

**这么做有什么好处？**

模型不用猜了：
- 看到 `success` → 放心继续下一步
- 看到 `partial` → 注意 `truncated` 标记，决定要不要继续
- 看到 `error` → 看 `error.code`，判断是重试还是换策略

说白了，就是让模型从"阅读理解题"变成了"选择题"。

### 05、熔断机制：防止重复犯错

工具连续失败怎么办？让它一直试一直报错？

显然不行。我加了个熔断机制：

```python
@circuit_breaker(threshold=3, recovery=30)
def execute_tool(tool_name, params):
    ...
```

连续失败 3 次，熔断 30 秒。

这样既保护资源，也给模型一个明确的信号："兄弟，这个工具现在有问题，换个思路吧"。

**这套改造让我明白一个道理：Code Agent 的"聪明"，真不是模型有多聪明，而是工具设计够不够可控。**

从"能跑"到"能稳"，靠的不是更严的提示词，而是更清晰的工程边界。

工具可控了，但调用协议还是个大问题——字符串解析太不靠谱，是时候转向 Function Calling 了。

---

## 05 从"改作文"到"走协议"：我为什么彻底放弃字符串 ReAct

工具原子化之后，我以为万事大吉了。

结果很快被打脸。

真正的麻烦在**调用层**：我怎么让模型"调用"这些工具？

### 01、字符串 ReAct 的窘境

最初，我用的是经典 ReAct 模式——让模型输出一段文本，里面混着 Thought、Action、Observation，然后我用正则去解析。

```
Thought: 我需要先查看目录结构
Action: LS({"path": "src/"})
Observation: [...]
```

这套看起来优雅，实际用起来全是坑。我跟你说说我踩过的几个大坑。

**坑一：格式极其不稳定**

模型有时候多打一个空格，有时候少打一个冒号，有时候把 Thought 和 Action 混在一起写。

我不得不写一堆容错正则：

```python
action_pattern = r'Action:\s*(.+?)\n'
action_pattern_v2 = r'\*\*Action:\*\*\s*(.+?)\n'  # 模型加粗了
action_pattern_v3 = r'Action:\n```\n(.+?)\n```'  # 模型用了代码块
```

补丁越打越多，像个无底洞。我当时就想，这哪是在写代码，这是在考古啊。

**坑二：参数解析错误**

模型输出的 JSON 经常有问题：
- 单引号代替双引号
- 多一个逗号
- 字段名没加引号
- 中文字符没有转义

每次都要先做一轮"作文批改"，修正格式错误，才能解析。

我当时写了个 `sanitize_json()` 函数，代码量比核心逻辑还长，你敢信？

**坑三：模型会"幻觉"**

有时候模型输出的 Action 格式完全不对，或者调了一个根本不存在的工具。

我得在代码里加一堆兜底：

```python
if tool_name not in registry:
    return "工具不存在，请检查"
```

讲真，这不是在调用工具，这是在**给模型当语文老师改作文**。

我一度怀疑人生：我到底是做 AI Agent 的，还是做 NLP 数据清洗的？

### 02、转向 Function Calling

就在我快要放弃的时候，看到了 OpenAI 的 Function Calling。

眼前一亮。

原来工具调用可以标准化成协议层，而不是让模型"写作文"。

```json
{
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "LS",
        "arguments": "{\"path\": \"src/\"}"
      }
    }
  ]
}
```

**这不是响应格式的问题，而是协议层的问题。**

Function Calling 的本质是什么？
- 在 API 层面声明工具 Schema
- 模型按 Schema 返回结构化调用
- 不再是"解析文本"，而是"执行协议"

说白了，就是把"语文考试"变成了"标准化考试"。

### 03、我的 Function Calling 改造

我重新设计了工具注册和调用流程。

**工具定义标准化：**

每个工具都要实现 `get_parameters()` 方法，返回 JSON Schema：

```python
class LSTool(Tool):
    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径"}
            },
            "required": ["path"]
        }
```

**调用流程标准化：**

1. 构建消息时，把工具 Schema 按 OpenAI 格式注入
2. 模型返回 `tool_calls` 数组
3. 直接提取 `name` 和 `arguments`，无需解析
4. 执行工具，结果以 `tool` 角色消息返回
5. 继续下一轮

```python
# 模型输出 -> 直接提取
for tool_call in response.tool_calls:
    tool_name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments)
    result = registry.execute_tool(tool_name, arguments)
```

**每一次工具调用都能精确对应结果，链路再也不会断了。**

回过头看，旧版为了"能跑"写的大量容错补丁，现在都被协议层替代了。

**ReAct 的稳定性不是靠"写更严的提示词"，而是靠"让模型说协议话"**——标准格式天然可控，省去无数补丁。

有意思的是，改造完之后我删掉了几百行容错代码，项目反而更稳定了。

调用协议稳定之后，新的问题又冒出来了——长对话一多，模型开始"变笨"。

上下文工程，成了下一个要解决的大问题。

---

## 06 长对话的"失忆症"：我的上下文工程改造实录

调用协议稳定之后，新问题又来了。

当对话轮数超过 10 轮，模型开始"变笨"：
- 忘了自己说过什么
- 重复问同一个问题
- 开始"幻觉"，编造不存在的文件或代码

我一开始以为是模型能力问题，后来才发现——**上下文被污染了**。

### 01、污染源从哪来？

仔细排查后，我发现了三个主要污染源。

**污染源一：工具输出堆积**

每次工具调用返回的内容都塞进历史，10 轮对话后，上下文里塞满了：
- 各种目录列表
- 大段代码片段
- 命令执行输出
- 错误堆栈

**这些工具输出占了 Token 的大头，但真正有价值的推理信息被淹没了。**

说白了，模型被"垃圾信息"淹没了，就像你在一个堆满杂物的房间里找一把钥匙。

**污染源二：历史只增不减**

早期实现没有清理机制，对话历史只增不减。超过上下文窗口后，直接报错。

我当时还傻乎乎地给上下文窗口配得特别大，以为这样就能解决问题。

结果发现，窗口越大，模型越慢，效果反而越差。

**污染源三：@file 语法的问题**

我实现了 `@file:path` 语法，让用户可以引用文件。但早期实现直接把整个文件内容塞进上下文：

```
User: @file:src/main.py 帮我分析一下这个文件
[文件内容300行...]
```

结果就是：上下文里多了一大段代码，但用户可能只是想问"这个文件是干嘛的"。

模型看着这 300 行代码，头都大了。

### 02、我的"污染治理"策略

意识到问题后，我开始了上下文治理工程。

#### 策略一：工具输出截断与净化

不是所有工具输出都需要完整保留。

**截断策略：**
- 大输出自动截断，保留头部 + 尾部 + 省略提示
- 超出阈值的部分写入磁盘，上下文只留摘要

**净化策略：**
- 移除 ANSI 颜色代码
- 标准化换行符
- 过滤掉无意义的空白

```python
max_lines = 200
if len(lines) > max_lines:
    head = lines[:40]
    tail = lines[-40:]
    text = "\n".join(head) + "\n... [省略 {} 行] ...\n".format(len(lines) - 80) + "\n".join(tail)
```

**上下文里只留下"提醒"，而不是"垃圾"。**

#### 策略二：@file 智能引用

@file 不再直接塞内容，而是转化为系统提醒：

```
User: @file:src/main.py

System reminder: The user mentioned @src/main.py. You MUST read this file with the Read tool before answering.
```

模型看到提醒，会主动调用 Read 工具按需获取内容。

这样做有三个好处：
- 上下文不膨胀
- 模型按需读取
- 避免"假读"问题（模型以为自己读了，其实没读）

#### 策略三：历史压缩（Summary 机制）

当上下文接近阈值时，触发压缩：

1. 保留最近 N 轮完整对话（热记忆）
2. 将更早的历史压缩成 Summary（冷记忆）
3. Summary 放入系统上下文

```
[System] 历史摘要：用户之前要求重构代码，已完成工具类提取，当前在进行测试环节。
[User] 现在进度如何？
[Assistant] ...
```

**模型不会"失忆"，只是换了一种方式"记得"。**

讲真，这个设计灵感来自我自己的记忆方式——对最近的事记得很清楚，对久远的事只记得"大概发生了什么"。

#### 策略四：Token 预估与预算控制

实时监控上下文大小：

```python
def estimate_tokens(messages) -> int:
    # 简单估算：4 字符 ≈ 1 token
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return total_chars // 4
```

设置阈值，接近时触发压缩或告警。

### 03、治理效果

这一轮改造的效果很明显。

工具输出不会无限堆积了，历史能在阈值时自动收敛，Summary 把旧历史压成"稳定记忆"，@file 不再制造垃圾上下文。

**上下文不是塞得越多越好，而是要治理得清晰、可追溯。**

你会发现，模型"变笨"的问题基本消失了。它不再是那个在垃圾堆里找钥匙的可怜虫，而是一个有清晰笔记、有重点记忆的智能助手。

但治理好上下文，还有一个更大的痛点——Agent 出错时，我完全不知道它经历了什么。

可观测性，成了下一个坎。

---

## 07 Trace：Agent 的行车记录仪，出问题时能救命

工具、协议、上下文都跑顺之后，我以为可以松口气了。结果一个晴天霹雳砸下来：**Agent 出 bug 时，我完全不知道它刚才到底在干嘛。**

有回模型连着失败 3 步，最后干脆撂挑子不干了。我狂翻控制台日志，就看到一句冷冰冰的：`tool failed`

什么参数传的？上下文是啥？前面几步它咋想的？一概没有。**我只能干瞪眼瞎猜：路径写错了？权限不够？还是工具本身有 bug？**

那一刻我悟了：**没有审计轨迹的 Agent，就像没装行车记录仪的自动驾驶——撞了你只能拍大腿，连谁的责任都说不清。**

于是赶紧补上可观测性这层：Trace 轨迹 + 会话快照。

### 1、TraceLogger：给 Agent 装上"黑匣子"

我做了个会话级轨迹记录器：`TraceLogger`。

它就干一件事：**把一次会话的每一步，按顺序完整记下来。**

#### 双格式输出：机器看 + 人看

TraceLogger 同时输出两份文件，丢进 `memory/traces/` 目录：

**JSONL 格式**（给程序用）：
- 路径：`memory/traces/trace-s-20260103-201533-a3f2.jsonl`
- 每步一个 JSON 对象，方便流式追加
- 可以写脚本批量分析、统计 token 用量、抓异常模式

**HTML 格式**（给人看）：
- 路径：`memory/traces/trace-s-20260103-201533-a3f2.html`
- 浏览器直接打开，可视化展示每一步
- 支持点击展开/折叠，像在"逐帧回放"

文件名里的 `s-20260103-201533-a3f2` 是会话唯一标识（`s-YYYYMMDD-HHMMSS-随机4位`），方便按时间翻。

#### 统一事件结构

所有事件都按这个格式记：

```json
{
  "ts": "2026-01-03T20:15:33.112Z",
  "session_id": "s-20260103-201533-a3f2",
  "step": 4,
  "event": "tool_call",
  "payload": {}
}
```

字段说明：
- `ts`：ISO8601 时间戳，精确到毫秒
- `session_id`：会话唯一标识
- `step`：ReAct 循环的 step 序号
- `event`：事件类型
- `payload`：事件数据体

#### 关键事件类型

我定义了这些事件类型，覆盖 Agent 运行的完整生命周期：

| 事件类型 | 说明 | 典型 payload |
|---------|------|-------------|
| `system_messages` | 系统消息（仅一次） | L1 System Prompt + Tools |
| `run_start` / `run_end` | 会话起止 | 时间戳、配置信息 |
| `user_input` | 用户输入 | 原始输入文本 |
| `context_build` | 上下文构建完成 | 上下文 token 估算 |
| `model_output` | 模型输出 | raw 输出、tool_calls、usage |
| `tool_call` | 工具调用前 | tool_name、args、tool_call_id |
| `tool_result` | 工具返回后 | 完整工具响应 JSON |
| `error` | 错误发生 | error_code、message、traceback |
| `finish` | 正常结束 | 最终回答内容 |
| `session_summary` | 会话统计 | steps、tools_used、total_usage |

说白了，**问题不再是"有没有日志"，而是"你想看哪一步"。**

### 2、关键证据链：每一步都打点

Trace 的核心价值是"证据链"——每一步都有迹可循，调用和结果能精确对应。

#### tool_call_id：调用与结果的强绑定

Function Calling 架构下，每个 tool_call 都有唯一 ID。TraceLogger 用这个 ID 把"调用"和"结果"串成一条链：

```python
# Step 1: 记录工具调用
trace_logger.log_event(
    "tool_call",
    {
        "tool": "Read",
        "args": {"path": "core/llm.py"},
        "tool_call_id": "call_abc123xyz"  # 关键：唯一标识
    },
    step=4,
)

# 执行工具...

# Step 2: 记录工具结果，使用相同的 tool_call_id
trace_logger.log_event(
    "tool_result",
    {
        "tool": "Read",
        "tool_call_id": "call_abc123xyz",  # 与调用对应
        "result": {
            "status": "success",
            "data": {"content": "..."},
            "text": "Read 120 lines from core/llm.py"
        }
    },
    step=4,
)
```

在 HTML 可视化里，这两个事件会被渲染成一对可折叠的卡片，一眼就能看出调用和结果的对应关系。

#### model_output：记录 Token 用量

每次模型输出，Trace 都会记 usage 信息：

```json
{
  "event": "model_output",
  "payload": {
    "raw": "...",
    "tool_calls": [...],
    "usage": {
      "prompt_tokens": 3456,
      "completion_tokens": 892,
      "total_tokens": 4348
    }
  }
}
```

这解决了一个老大难问题：**"为啥突然变慢？为啥 token 暴涨？"**

打开 Trace 一看，立马定位到哪一步上下文突然膨胀了。

### 3、HTML 可视化：把轨迹变成"可读回放"

JSONL 适合程序分析，但人复盘需要"看得懂"。TraceLogger 会同步生成一份 HTML，浏览器直接打开。

#### HTML 界面结构

典型的 Trace HTML 页面长这样：

```
Session: s-20260103-201533-a3f2
Run #1 | 8 steps | Total tokens: 12,458

Step 1: user_input
  "帮我找一下 context 相关代码"

Step 2: context_build
  Estimated tokens: 2,340

Step 3: model_output [可展开]
  Tokens: 3,456 / 892 / 4,348
  Tool Calls:
    call_abc123: Grep({"pattern": "context"})
  Raw Response: [点击展开]

Step 4: tool_call (Grep)
  ID: call_abc123
  Args: {"pattern": "context", "path": "."}

Step 5: tool_result (Grep) [可展开]
  Status: partial
  Text: "Found 2156 matches (showing first 2000)"
  Result: {"matches": [...], "truncated": true}

Step 6: model_output
  ...
```

点开每一步，就能看到完整的 input / output / token / 截断提示，像在逐帧回放。

#### 脱敏保护

生产环境里，Trace 可能包含敏感信息（API Key、Token、文件路径）。`TraceSanitizer` 默认开启（`TRACE_SANITIZE=true`）：

- API Key：`sk-***` / `Bearer ***`
- 敏感字段：`api_key`、`token`、`session_id`、`tool_call_id`
- 路径脱敏：`/Users/yyhdbl/...` → `/Users/***/...`

排查问题够用，但不会把敏感信息原样写盘。

### 4、一个真实复盘案例：Trace 怎么救了我

还记得前面提到那次"连续失败 3 步"吗？

当时 Agent 连着调用 Read 失败，最后放弃了。我翻控制台只看到 `tool failed`，完全不知道发生了啥。

有了 Trace 后，同样的问题再来一次，我的排查流程完全变了：

1. 打开 HTML Trace，定位到失败的 Step 4-6
2. 发现三次 `tool_call` 都是 `Read`，但 `tool_result` 返回了 `NOT_FOUND`
3. 查看 `args.path`，发现模型传的是绝对路径 `/Users/yyhdbl/project/core/llm.py`
4. 检查 `context.cwd`，发现工具执行时的当前目录是 `/project`
5. **根因定位**：模型用了绝对路径，但工具只能在项目根目录内访问

修复方案也简单：在系统提示里加一句"不要使用绝对路径"。

**从"瞎猜"到"定位"，差别就在有没有 Trace。**

### 5、会话快照：断点续跑的秘密

除了 Trace，我还做了会话快照功能。

**为啥需要快照？**

有时候一个任务要跑几十步，中途网络断了、API 限流了、或者我想改个参数再试。没有快照，只能从头来。

**快照存啥？**

```json
{
  "session_id": "s-20260103-201533-a3f2",
  "timestamp": "2026-01-03T20:15:33Z",
  "messages": [...],
  "tool_schema_hash": "abc123",
  "read_cache": {...},
  "code_law_hash": "def456",
  "skills_hash": "ghi789",
  "mcp_hash": "jkl012"
}
```

- `messages`：完整对话历史
- `tool_schema_hash`：工具配置指纹，防止工具变更后恢复导致不一致
- `read_cache`：文件读取缓存（含 mtime、size，乐观锁用）
- 各种 hash：CODE_LAW、Skills、MCP 配置的版本指纹

**CLI 支持：**

```bash
/save [path]    # 保存会话快照
/load [path]    # 加载会话快照
```

默认保存到 `memory/sessions/session-latest.json`，自动保存和加载。

**使用场景：**
- 长任务中断后续跑
- 调试时回溯到某一步
- 对比不同参数的效果

### 6、配置与性能

**环境变量配置：**

```bash
TRACE_ENABLED=true              # 启用 Trace 记录
TRACE_DIR=memory/traces         # Trace 输出目录
TRACE_HTML_INCLUDE_RAW_RESPONSE=false  # 是否在 HTML 中包含原始响应
```

**性能考虑：**
- JSONL 追加写入，开销极低
- 默认开启脱敏，生产环境需配合权限控制
- HTML 生成在会话结束时批量处理，不影响运行时性能

讲真，**从"猜错误"到"看证据"，这一层是工程化的分水岭。** V0 时 Agent 挂了只能瞎猜，现在打开 Trace 5 分钟就能定位问题。可观测性不是锦上添花，而是复杂系统必备的"行车记录仪"。

---

## 08 扩展期：MCP / Task / Todo / Skills，让 Agent 像个小团队

有回我让 Agent 做个任务：**"调研 MCP 协议，然后给我一个可落地的示例工具方案。"**

结果它先是疯狂搜索，把主线上下文刷爆了。好不容易整理出结论，开始写代码时又忘了前面调研的关键点。写到一半卡住，我问它进度，它自己也说不清"现在做到哪了"。

那一刻我才意识到：**让单个模型跑长流程，就像让一个人同时当老师、学生和班长——全搞砸。**

于是我补上了扩展能力这层：**MCP / Task / Todo / Skills**。

### 1、MCP：把外部能力"注册进来"

MCP 的设计像一个"工具插槽"：
- `mcp_servers.json` 描述外部服务
- `tools/mcp/config.py` 加载配置
- `tools/mcp/loader.py` 连接并注册工具
- 注册后进入 `ToolRegistry`，成为标准工具

**外部能力不是野生的，而是被协议化后再接入。**

### 2、Task 子代理：把调研任务拆出去

调研如果全由主 Agent 做，主线会被打断、上下文被污染。

于是我在 Task 工具里做了个极简"子代理系统"：
- 独立会话（隔离消息）
- 受限工具集（只读为主）
- 指定子代理类型 + 模型路由（main / light）

工具限制很硬：deny `Task, Write, Edit, MultiEdit, Bash`；allow `LS, Glob, Grep, Read, TodoWrite`。

**说白了，它确保子代理只做"调研"，不会越界改代码。**

### 3、TodoWrite：让执行变得"可追踪"

TodoWrite 不是普通清单，它有几个强约束：
- **声明式覆盖**：每次提交完整列表
- **最多 1 个 in_progress**：避免并行混乱
- **自动 recap**：把当前关键目标压缩到上下文尾部
- **自动持久化**：任务完成后写入 `memory/todos/`

**如果说 Trace 是复盘证据，Todo 就是过程中的"路线图"。**

### 4、Skills：让 Agent 拥有"领域大脑"

最近 Agent Skills 的概念特别火。Claude 的 Computer Use、OpenAI 的 Canvas、还有各种 Agent Framework 都在推类似的能力。核心思想很简单：**给 Agent 装上"领域知识包"，让它不只靠"通用智力"干活。**

#### Skills 解决什么问题？

想象两个场景：
- **场景 A**：你让 Agent 审查代码，它只能发现"第 5 行缩进不对"
- **场景 B**：你让 Agent 审查代码，它能指出"这个改动打破了那边的抽象，建议先重构接口"

差距在哪？不是工具不够多，是 Agent "有手没脑"——它会用 Read 读代码、用 Grep 搜引用，但**不知道什么才算"审查好"**。

Skills 就是来解决这个的：**把个人经验写成 SOP，让 Agent 按需调用。**

#### 核心特点：渐进式披露

Skills 与 MCP 最大的区别在**上下文加载策略**：

| 维度 | MCP | Skills |
|-----|-----|--------|
| 解决什么 | 能不能连上 | 连上之后怎么干 |
| 类比 | USB 接口/驱动 | 软件操作手册 |
| 上下文策略 | 急切加载（全量） | 渐进披露（按需） |
| 典型场景 | 连接数据库、搜索引擎 | 代码审查、技术写作、UI设计 |

MCP 的问题是"急切加载"——一连接就把所有表结构、API Schema 塞进上下文，动辄上万 Token。Skills 采用**渐进式披露（Progressive Disclosure）**：

- **第一层**：启动时只加载元数据（name/description）→ 约 100 Token/技能
- **第二层**：命中时才加载完整 SOP → 1000-5000 Token
- **第三层**：附加资源（脚本/模板）按需加载

社区有个真实对比：连一个数据库 MCP 要 16000 Token，而用 Skills 方式只需 100 Token。**Token 省 90% 以上**。

#### 我的实现：从文件到工具

我的 Skills 实现分三层：

**1. 文件层：SKILL.md 规范**

每个 Skill 是一个目录，包含 `SKILL.md`：

```markdown
---
name: tech-blog-writing
description: 撰写技术分享博客的标准流程
---

# 技术博客写作 SOP

## 1. 开头（黄金3秒）
用痛点或故事引入，别写"随着XX的发展"。

## 2. 技术内容
- 先讲"为什么"，再讲"是什么"
- 用具体数字、代码路径当"证据锚点"

## 3. 结尾
升华到认知层面，给读者行动建议。

$ARGUMENTS
```

格式要求：
- YAML frontmatter 定义元数据（name, description）
- Markdown 正文写 SOP
- `$ARGUMENTS` 是参数占位符，调用时会被替换

**2. 加载层：SkillLoader**

`core/skills/skill_loader.py` 负责管理 Skills：

```python
# 扫描 skills/ 目录下所有 SKILL.md
skill_loader.scan()  

# 获取元数据列表（仅 name + description）
skill_loader.list_skills()  

# 加载完整 Skill 内容（按需）
skill_loader.get_skill("tech-blog-writing")
```

缓存策略：基于 mtime 的增量刷新，避免每次重启都重新扫描。

**3. 工具层：Skill Tool**

`tools/builtin/skill.py` 提供调用入口：

```json
// Agent 调用示例
{
  "name": "Skill",
  "arguments": {
    "name": "tech-blog-writing",
    "args": "主题是MCP协议"
  }
}
```

执行流程：
1. 校验 Skill 存在性（不存在返回 `NOT_FOUND`）
2. 读取 SKILL.md，解析 frontmatter 和正文
3. 处理 `$ARGUMENTS`：
   - 如果正文中有 `$ARGUMENTS`，替换为传入的 args
   - 如果没有但 args 非空，追加 `ARGUMENTS: <args>`
4. 返回格式化后的 SOP，注入到当前上下文

**预算控制**

为防止 Skill 列表过长挤爆上下文，设计了字符预算机制：
- 环境变量 `SKILLS_PROMPT_CHAR_BUDGET`（默认 12000 字符）
- Skill Tool 的提示词在构建时自动截断，优先保留高优先级 Skill

**与 MCP 的配合**

两者不是竞争，是互补：
- MCP 给 Agent "手"（能连外部系统）
- Skills 给 Agent "脑"（知道怎么干活）

比如做一个"数据库 Schema 分析"任务：
1. 用 MCP 连接数据库，获取表结构
2. 用 Skill 加载"数据库分析 SOP"，知道该看索引、看关系、看冗余
3. 两者结合，产出专业分析报告

**一句话总结**：MCP 解决"能不能连"，Skills 解决"连上之后怎么干"。

扩展能力不是让 Agent 变复杂，而是让它把复杂拆成可控路径。V0 时让 Agent 做长流程任务，就像让一个人同时当编剧、导演、演员——全搞砸。现在 MCP 拉资料、Task 拆调研、Todo 管进度、Skills 给经验，像个小团队在协作。

---

## 09 功能演示：看看 MyCodeAgent 能干啥

前面八章讲了那么多设计，可能有人会觉得："听起来不错，但真的能跑吗？"

这一章，我用三个**真实的测试 Prompt** 来展示 MyCodeAgent 的实际能力。这三个 Prompt 覆盖了从基础到高阶的核心场景，每个都有明确的能力考核点。

---

### Prompt 1：基础能力测试（探索 + 理解 + 小规模产出）

**给 Agent 的指令**：

> 请快速理解这个仓库是做什么的，并输出一份"项目概览"文档：
> - 简要说明目标、核心模块、主要功能
> - 引用真实文件路径作为依据
> - 输出一个结构清晰的 Markdown 文件放在 demo/ 目录下
> 
> 注意：不要编造未看到的内容；需要的话主动探索相关文件。

**Agent 的执行过程**：

1. **主动探索**：先用 `LS` 扫描项目根目录，发现 `agents/`、`core/`、`tools/`、`prompts/` 等关键目录
2. **逐层深入**：
   - 读取 `README.md` 了解项目整体定位
   - 阅读 `agents/codeAgent.py` 确认主 Agent 实现
   - 查看 `core/context_engine/` 理解上下文工程
   - 浏览 `tools/builtin/` 了解工具集
3. **信息验证**：用 `Grep` 确认关键类名和函数名，避免"幻觉"
4. **产出文档**：在 `demo/` 下生成 `project_overview.md`，包含：
   - 项目定位（面向学习的 Code Agent 框架）
   - 核心模块说明（agents/、core/、tools/）
   - 主要功能清单（ReAct 循环、Function Calling、上下文压缩、Trace 记录等）
   - 每个结论都带真实文件路径引用

**覆盖的能力点**：
- ✅ 仓库探索（主动查找入口，不依赖人工指示）
- ✅ 文件阅读与归纳（从分散代码中提取结构）
- ✅ 路径引用准确性（每个结论都有证据链）
- ✅ 文档产出能力（生成可直接使用的 Markdown）

---

### Prompt 2：中阶能力测试（跨文件一致性 + Skill + MCP）

**给 Agent 的指令**：

> 你需要分析自己的源代码，基于代码剖析的结果，创建一个面向用户的 Agent 自我介绍网页（以第一人称视角介绍自己）。
> - 请合理使用完成任务所需的所有工具，按照最优步骤执行
> - 若你具备 UI/UX 相关技能（Skill），请调用并应用
> - 网页风格可自行选择（玻璃拟态、拟物化、新拟态等均可）
> - 最终输出一个 HTML 文件，保存至 demo/ 目录下

**Agent 的执行过程**：

1. **自我剖析阶段**（调用 `Skill` 工具）：
   - 识别到需要 UI/UX 设计，调用 `ui-ux-pro-max` Skill
   - 获取设计规范：玻璃拟态风格、配色方案、字体搭配、动效指南

2. **内容规划阶段**（调用 `Read` + `Grep`）：
   - 阅读自己的源代码，提取核心能力点
   - 整理出 "我是谁、我能做什么、我的技术栈、我的特点" 四大板块

3. **竞品调研阶段**（调用 `MCP` 工具）：
   - 使用 MCP 的 fetch 工具搜索 Claude Code、Codex CLI、Cursor 等竞品
   - 对比分析后，在网页中加入差异化卖点（如"渐进式 Skill 加载"、"Trace 可观测性"）

4. **开发阶段**（调用 `Write` 工具）：
   - 按 Skill 提供的规范编写 HTML
   - 玻璃拟态卡片 + 渐变色背景 + 悬停动效
   - 第一人称口吻："你好，我是 MyCodeAgent，一个热爱学习的代码助手..."

5. **验证阶段**（调用 `Read` 工具）：
   - 重新读取生成的 HTML，检查是否有遗漏的能力点
   - 确认文件保存路径正确

**生成的网页预览**：
- 首屏大标题："你好，我是 MyCodeAgent"
- 能力卡片：工具系统、上下文工程、可观测性、扩展能力
- 技术栈展示：Python、OpenAI Function Calling、ReAct 模式
- 差异化亮点：MCP 扩展、Skills 渐进加载、Trace 回放

**覆盖的能力点**：
- ✅ Skill 触发与使用（按需加载 UI/UX 设计规范）
- ✅ MCP 扩展能力（联网搜索竞品信息）
- ✅ 跨产物一致性维护（代码 ↔ 网页内容对应）
- ✅ 设计/前端输出能力（生成可直接打开的美观网页）
- ✅ 自主规划与执行（无需人工指定每一步）

---

### Prompt 3：高阶能力测试（长上下文 + 轨迹自评 + 反思改进）

**给 Agent 的指令**：

> 请基于你刚才完成的两步任务，做一份"执行复盘与自评报告"：
> - 总结你完成任务的关键步骤与决策
> - 分析有哪些地方做得好、有哪些不足（至少各 3 条）
> - 如果系统有 trace / 日志 / 轨迹记录，请引用其中的证据来支持你的判断
> - 给出 3 条可执行的改进建议（优先考虑稳定性与一致性）

**Agent 的执行过程**：

1. **读取历史轨迹**（调用 `Read` 工具）：
   - 读取本次会话的 Trace 日志：`memory/traces/trace-s-xxx.jsonl`
   - 解析每一步的 tool_call、tool_result、token 用量、耗时

2. **关键步骤复盘**：
   - Prompt 1：先扫描目录结构再深入阅读，"先地图后细节"策略正确
   - Prompt 2：主动调用 Skill 获取设计规范，避免"凭感觉设计"
   - 使用 MCP 进行竞品对比，而非闭门造车

3. **优点分析**（引用 Trace 证据）：
   - ✅ **工具选择合理**："Prompt 1 中，我先用 LS 而非 Grep，因为还不清楚目录结构。从 Trace 可见，LS 返回后我才针对性读取关键文件。"
   - ✅ **Skill 使用及时**："Prompt 2 中，我在第 3 步就识别到需要 UI/UX Skill，而非写了一半再回头改。"
   - ✅ **上下文保持较好**："全程使用 TodoWrite 维护任务列表，即使跨多个 Prompt 也能记住主线目标。"

4. **不足分析**（引用 Trace 证据）：
   - ⚠️ **Token 用量偏高**："Prompt 2 中读取竞品网页时，MCP fetch 返回了完整 HTML（约 8000 Token），其中大部分是无效内容。应该使用更精准的搜索关键词。"
   - ⚠️ **文件读取有冗余**："Prompt 1 中读了两次 `agents/codeAgent.py`，第一次是概览，第二次是确认细节。其实可以缓存第一次的结果。"
   - ⚠️ **错误恢复不够优雅**："Prompt 2 中尝试调用一个未配置的 MCP 工具，虽然触发了熔断，但重试 3 次才放弃，浪费了时间和 Token。"

5. **改进建议**：
   - 📌 为 MCP 工具增加"内容摘要"选项，避免全量拉取大网页
   - 📌 引入 Read 工具的结果缓存，相同路径在 5 分钟内不重复读取
   - 📌 优化熔断策略，对"配置缺失"类错误直接报错，不重试

**覆盖的能力点**：
- ✅ 长上下文保持（引用前两步产物进行分析）
- ✅ 自我评估与反思能力（客观分析优缺点）
- ✅ Trace/日志系统使用与分析（从证据链得出结论）
- ✅ 可执行改进建议产出（具体、可落地，而非泛泛而谈）

---

### 从演示中看到了什么？

这三个 Prompt 跑下来，MyCodeAgent 展现了一个**工程化 Agent** 应有的特质：

| 能力层级 | 表现 |
|---------|------|
| **基础** | 会探索、会验证、会产出 |
| **中阶** | 会规划、会用 Skill、会连 MCP |
| **高阶** | 会反思、会用证据、会提改进 |

但这背后，其实是每一层工程的支撑：
- 工具原子化 → 让它"会探索"
- 通用响应协议 → 让它"会验证"
- 上下文工程 → 让它"记得住"
- Trace 可观测性 → 让它"会反思"
- Skill/MCP → 让它"有能力"

**Agent 的智能上限看模型，但可靠程度看工程。**

这也是我做完这个项目最大的体会：做 Agent 不是拼谁的提示词写得花，而是拼谁的工程化做得扎实。

---

## 写在最后：一个初学者的碎碎念

回顾整个系列：V0 → 工具重构 → Function Calling → 上下文工程 → 可观测性 → 扩展能力 → Skills。

这九篇文章，记录了我从一个 Agent 开发小白，跟着 **[Datawhale](https://github.com/datawhalechina)** 的 Hello-Agent 教程一步步摸索过来的全过程。

**首先要特别感谢 Datawhale 的开源教程。** 如果没有 Hello-Agent 这个扎实的入门项目，我可能到现在还在各种"智能体框架"的概念里打转，而不会真正动手去写一个能跑起来的 Agent。正是教程最后那个"毕业设计"的推动，让我有了这个项目，也有了这九篇学习笔记。

说实话，写完这九篇，我越发觉得自己的渺小。

Agent 开发这个领域发展太快了，我文中提到的很多方案——比如上下文压缩策略、Skills 的设计、MCP 的集成方式——可能都还有更好的做法。我只是一个初学者，在实践中踩坑、总结、记录，分享的更多是一个"小白视角"的踩坑实录，而不是什么"最佳实践"。

**如果你发现文中有错误，或者有更好的实现思路，非常欢迎在评论区指出。** 我很希望能和大家交流，也很期待能向各位大佬请教。

### 一点真心话：我们都是在给 LLM "擦屁股"

做完这个项目，我有个特别深的感触，可能听起来有点糙，但话糙理不糙：

> **Agent 开发的核心，不是让模型更自由，而是通过工程设计，把模型"不确定的能力"约束在"最小可控的范围"里。说白了，我们就是在给 LLM 擦屁股。**

为什么这么说？

你看啊，LLM 很强，能写代码、能读文档、能推理。但它就像一个特别聪明但特别不靠谱的实习生——

- 你让它去打印文件，它可能把全公司的打印机都调用一遍；
- 你让它整理会议纪要，它可能把上周的会议也掺和进来；
- 你让它写个函数，它写得贼溜，但变量命名全是 `a`、`b`、`c`，还顺带改了你没让改的文件。

**它的"强"是能力上的强，但"不靠谱"是确定性上的不靠谱。**

而我们做 Agent 工程，本质上就是在解决这个矛盾：

| 模型的天性 | 我们的工程对策 |
|-----------|--------------|
| 喜欢自由发挥 | 用 Function Calling 锁定调用格式 |
| 上下文一多就"失忆" | 用 L1/L2/L3 分层 + Summary 压缩 |
| 出错不会自查 | 用 Trace 记录每一步，让错误可追溯 |
| 长任务容易跑偏 | 用 Todo + Task 拆分，降低单步复杂度 |
| 不懂领域知识 | 用 Skills 固化 SOP，让它"有脑" |

你看这九章的内容，从工具原子化到上下文工程，从可观测性到子代理——**每一层都是在给模型"打补丁"，帮它收拾烂摊子。**

但这恰恰是最有意思的地方。

以前我觉得，AI 时代工程师的价值会下降。现在我觉得恰恰相反：**模型越强大，越需要工程能力来驾驭它。** 就像汽车引擎越来越强，但好的底盘、刹车、悬挂系统反而更重要。

**我们不是在和模型竞争，而是在和模型协作——它负责"能做什么"，我们负责"怎么让它稳定地做对"。**

所以，如果你问我做完这个项目最大的收获是什么？

不是学会了什么高大上的架构，而是想明白了一个朴素的道理：**优秀的 Agent 不是"让模型更自由"的产物，而是"把不确定性约束到最小"的结果。**

讲真，这个认知转变，可能比所有代码都值钱。

---

### 未来的打算

MyCodeAgent 还只是一个"能跑"的玩具，离真正生产可用还有很长的路要走。接下来我想继续探索的方向：

1. **更智能的 Skills 发现机制**——现在还要手动选 skill，能不能让 Agent 自己判断需要什么技能？
2. **多 Agent 协作**——Task 只是简单的子代理，能不能做更复杂的多 Agent 编排？
3. **视觉能力集成**——让 Agent 能看懂 UI、能截图分析，这是我特别想做的方向
4. **更完善的测试体系**——现在的测试还比较简陋，需要补全协议合规性和行为测试

如果你也对 Agent 开发感兴趣，或者正在学习相关技术，欢迎一起交流。我的 GitHub 仓库地址是：[https://github.com/你的用户名/MyCodeAgent](https://github.com)（欢迎 Star 和 PR！）

**Agent 开发这条路还很长，希望能和志同道合的朋友一起走下去。**

如果你也在做 Agent，祝你的 Agent 既有"手"，也有"脑"。

---

*本文完。感谢阅读，期待你的反馈和建议！*
