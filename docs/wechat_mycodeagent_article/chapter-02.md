# 二、先跑起来！我用 Hello-Agent 骨架搭出第一个能用的 Code Agent

有了方向，我没急着追什么"最优架构"。

先给自己定了一个很接地气的目标：**用户说一句需求，Agent 能自己去仓库里找证据，给出改动方案，输出补丁，我确认后能真正落盘。**

说白了，我要的不是一个会聊天的 Demo，而是一个**能干活的 CLI**。

Hello-Agent 的底子正好够用——ReActAgent、ToolRegistry、ContextBuilder 这些核心组件都是现成的。我的策略很简单：**先复用，再改造**。

---

## 1、起手式：先复用，再改造

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

---

## 2、V0 怎么算"能用"？我定了四条

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

为啥？工具输出一旦太长，下一步提示词就会变脏，模型很容易跑偏。这套配置后来肯定不够，但 V0 阶段，它让问题**可复现、可调试**。

---

## 3、单轮流程：土，但管用

我当时最担心：每轮都走完整流程会不会太慢、太贵、太容易失控？

所以没搞"所有输入一股脑丢给 ReAct"，而是先分流：

```python
# 闲聊直接短路，不浪费 Token
if self._is_chitchat(user_input):
    return direct_response

# 构建上下文，走主流程
context_text = self.context_builder.build_base(...)
response = self.react.run(context_text, max_tokens=8000)

# 历史只留最近 50 条，粗暴但有效
if len(self.history) > 50:
    self.history = self.history[-50:]
```

三件小事，当时觉得挺实用：

- 闲聊直接短路，省 Token；
- 检测到"分步/计划"关键词，轻量提示让模型先用 `todo`；
- 历史粗暴截断，先控住上下文规模。

你会发现，这套思路已经在往"上下文工程"靠了，只是还比较轻。后面我会彻底重做这部分。

---

## 4、最关键的一步：补丁必须能落地

很多 Agent 演示到"建议修改"就结束了。

我明确不接受这种"嘴上会改"的状态，从第一天就把补丁执行链路接上了：

```python
# 从模型回复里提取补丁
patch_text = _extract_patch(response)
if not patch_text:
    continue  # 没补丁，继续聊

# 危险操作要确认
if _patch_requires_confirmation(patch_text):
    if input("confirm> ").strip().lower() not in {"y", "yes"}:
        continue

# 执行
res = patch_executor.apply(patch_text)
```

真正保安全的是执行器，它有几条硬规矩：

- 路径必须在 `repo_root` 内，防逃逸；
- 临时文件 + 原子写入，不半写；
- 自动备份，能撤回；
- 限制单次改动规模；
- 解析失败直接中断，不瞎猜。

这让 V0 至少有个底线：**改动是可追、可控、可撤回的。**

---

## 5、兴奋和坑，一起来了

V0 刚跑起来那几天，确实挺爽。

"看结构 → 搜代码 → 给补丁 → 落盘"这条链路能通，而且通得挺顺。我看着它改完第一个文件的时候，感觉这玩意儿**真的能干活**。

但任务强度一拉高，问题很快冒头：

- 终端命令越来越长，失败时只能看到最后报错，根本不知道哪步挂了；
- ReAct 靠字符串解析，模型偶尔多说一句、少个标记，就解析失败；
- 长任务里上下文开始"变脏"，噪声越来越多；
- 工具返回都是字符串，后续处理很难做强约束。

这时候我才真正意识到：

> **V0 的价值不是"它已经很好"，而是"它把问题暴露得足够早"。**

没有这个能跑通的版本，后面的重构可能就是拍脑袋。  
有了它，我能拿着具体代码和复现场景去改，而不是靠感觉。

---

**下一章**：第一个真正把我打醒的坑——为什么让模型"自由写 shell"，会从高效变成失控。
