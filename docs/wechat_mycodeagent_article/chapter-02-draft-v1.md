# 第2章：先跑起来——我怎么基于 Hello-Agent 做出第一个 V0

学完教程以后，我没有马上去追“最优架构”。  
相反，我先给自己定了一个非常具体、可验收的目标：

用户说一句需求，Agent 能自己去仓库里找证据，给出改动方案，输出补丁，我确认后能真正落盘。

说白了，我要的不是一个会聊天的 Demo，而是一个能干活的 CLI。  
先把闭环跑通，后面才有资格谈优雅。

---

## 01｜先做闭环，不做大而全

我当时的起手动作很克制：  
**不重造基础设施，直接复用 Hello-Agent 的主干。**

核心组件就这几块：

- `ReActAgent`：负责 Thought -> Action -> Observation 的循环；
- `ToolRegistry`：负责工具注册和调用分发；
- `ContextBuilder`：负责把系统规则、会话历史、证据拼成上下文；
- `TerminalTool`：负责仓库内命令执行；
- `Message`：负责会话消息结构。

在 `HelloCodeAgentCli/code_agent/agentic/code_agent.py` 里，我就是这么组的（节选）：

```python
self.terminal_tool = TerminalTool(
    workspace=str(self.paths.repo_root),
    timeout=60,
    confirm_dangerous=True,
    default_shell_mode=True,
)
self.registry = ToolRegistry()
self.registry.register_tool(self.terminal_tool)
self.registry.register_tool(self.note_tool)
self.registry.register_tool(PlanTool(self.llm, prompt_path=str(self.paths.prompts_dir / "plan.md")))
self.registry.register_tool(self.todo_tool)

self.context_fetch_tool = ContextFetchTool(
    workspace=str(self.paths.repo_root),
    note_tool=self.note_tool,
    memory_tool=None,
    max_tokens_per_source=800,
    context_lines=5,
)
self.registry.register_tool(self.context_fetch_tool)
```

这段代码里有两个点，后来都成了转折：

第一，`default_shell_mode=True`。  
当时我的想法很直白：先把能力放开，让模型能写复杂 shell 组合，效率优先。

第二，工具不只放 `terminal`，我还把 `todo / note / plan / context_fetch` 一起带上。  
我希望它从第一天开始就能处理“连续任务”，而不是单轮问答。

现在回看，这就是一个典型取舍：  
**能力上限先拉满，控制边界后补。**

---

## 02｜我怎么定义“V0 可用”：四个动作必须全部打通

V0 阶段我不是看“回答像不像人”，而是看这四个动作能不能连续完成：

1. 能稳定进入多步 ReAct，而不是一句话就结束；  
2. 能在仓库内取证（目录、文件、符号、上下文）；  
3. 能输出补丁，不停留在“建议你改”；  
4. 改动要可控（确认、备份、失败可回滚）。

为了让第一点成立，我在 ReAct 上先做了最基础的防跑飞设置：

```python
self.react = ReActAgent(
    name="code_agent",
    llm=self.llm,
    tool_registry=self.registry,
    max_steps=20,
    custom_prompt=react_prompt,
    observation_summarizer=_summarize_observation,
    summarize_threshold_chars=1800,
)
```

`max_steps=20` + observation 摘要这组组合，当时真的救过我很多次。  
否则工具一旦输出过长，下一轮提示词很快变脏，模型就容易跑偏。

这套配置后来肯定不够，但在 V0 阶段，它足够让我把问题“做实、做透”。

---

## 03｜V0 的单轮流程：先分流，再拼上下文，再进 ReAct

我当时最在意的是：每轮都走重流程会不会太慢、太贵、太容易失控。  
所以 `run_turn` 不是“所有输入一股脑丢给 ReAct”，而是先分流，再走主流程。

核心逻辑（节选）：

```python
if self._is_chitchat(user_input):
    # 闲聊短路，直接返回
    ...

context_text = self.context_builder.build_base(
    user_query=user_input,
    conversation_history=self.history,
    system_instructions=self.system_prompt + ("\n" + multistep_hint if multistep_hint else ""),
    tool_summaries=tool_summaries if tool_summaries else None,
)

response = self.react.run(context_text, max_tokens=8000)

self.history.append(Message(content=user_input, role="user", timestamp=datetime.now()))
self.history.append(Message(content=response, role="assistant", timestamp=datetime.now()))
if len(self.history) > 50:
    self.history = self.history[-50:]
```

这段里我当时做了三件“土但有效”的事：

- 闲聊直接短路，不调用工具；
- 检测到“分步/计划”时，给模型加轻量提示，让它先用 `todo`；
- 历史只保留最近 50 条，先粗暴控住上下文规模。

你会发现，这套思路已经在往“上下文工程”靠了，只是当时还很轻量。  
后面我会把它彻底重做。

---

## 04｜我最看重的一步：补丁闭环必须真实可落地

很多 Agent 演示到“建议修改”就结束了。  
我当时明确不接受这种“嘴上会改”，所以很早就把补丁执行链路接上了。

CLI 主流程在 `HelloCodeAgentCli/code_agent/hello_code_cli.py`，核心是这几步：

```python
patch_text = _extract_patch(response)
if not patch_text:
    continue

needs_confirm = _patch_requires_confirmation(patch_text)
if needs_confirm:
    ans = input("confirm> ").strip().lower()
    if ans not in {"y", "yes"}:
        continue

res = patch_executor.apply(patch_text)
print(f"files: {', '.join(res.files_changed)}")
```

真正保证安全的是执行器 `code_agent/executors/apply_patch_executor.py`。  
它不是“直接写文件”，而是一整套硬约束：

- 路径必须在 `repo_root` 内，防路径逃逸；
- 临时文件 + `os.replace` 原子写入，避免半写；
- 自动备份到 `.helloagents/backups/<timestamp>/`；
- 限制单次修改规模（默认 `max_files=10`、`max_total_changed_lines=800`）；
- 解析/冲突失败直接中断，不做猜测性应用。

所以 V0 虽然还远没到最终形态，但它已经满足一个底线：  
**改动是可追、可控、可撤回的。**

---

## 05｜第一波正反馈和第一波问题，是同时来的

V0 刚跑起来那几天，我确实挺兴奋。  
“看结构 -> 搜代码 -> 给补丁 -> 落盘”这条链路能通，而且通得还挺顺。

但我把任务强度一拉高，问题也很快浮出来了，而且都很实在：

- 终端命令越来越长，失败时只能看到最后一步报错，很难定位中间哪一步坏了；
- ReAct 依赖字符串格式，模型偶尔多说一句、少一个标记，解析就抖；
- 上下文在长任务里开始“变脏”，噪声越来越多；
- 工具返回还是偏字符串，后续处理很难做强约束。

这时候我才真正意识到：

**V0 的价值，不是“它已经很好”，而是“它把问题暴露得足够早”。**

没有这个阶段，我后面的重构很可能就会变成拍脑袋。  
有了这个阶段，我才能拿着代码路径和复现场景去改，而不是靠感觉改。

下一章我会先拆第一个真正把我打醒的问题：  
为什么 `TerminalTool + 高自由度 shell` 在复杂任务里会从“高效”变成“失控”。
