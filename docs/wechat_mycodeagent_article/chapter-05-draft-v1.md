# 第5章：字符串 ReAct 解析不稳定——从“格式约束”走向“协议调用”

第4章把工具体系拆出来之后，我以为问题已经解决了一大半。工具更可控了、粒度更清晰了，
但真正运行起来还是会“偶发翻车”。

翻车的根源并不在工具，而在**工具是怎么被调用的**。

那时候我沿用的是 Hello-Agent 的 ReAct 方式：模型输出 Thought/Action 字符串，
框架用正则去解析。工具看似变精细了，但调用协议依旧是“自由文本”。
只要模型多说一句、少一个符号，链路就断。

---

## 01｜旧版 ReAct：全靠“字符串纪律”

Hello-Agent 的 ReAct Prompt 其实写得很严格，要求模型必须输出 Thought 和 Action 两行，
格式清晰到近乎“军规”：

```text
Thought: <你的思考（简短）>
Action: <以下二选一>
- tool_name[tool_input]
- Finish[最终回答]
```

（来自 `docs/wechat_mycodeagent_article/HelloCodeAgentCli/code_agent/prompts/react.md`）

表面上是强约束，但本质还是**字符串协定**。
模型只要多写一句解释、或者把 Action 放在段落后面，解析就开始抖。

我后来翻 ReAct 解析代码时，才意识到它有多脆：

```python
m = re.search(
    r"(?:\*\*)?(Thought|思考)(?:\*\*)?\s*[:：]\s*(.*?)\n"
    r"(?:\*\*)?(Action|行动)(?:\*\*)?\s*[:：]\s*(.*)\s*$",
    t,
    flags=re.DOTALL,
)
```

（来自 `docs/wechat_mycodeagent_article/HelloCodeAgentCli/agents/react_agent.py`）

这个正则本身已经很“照顾模型”了：
兼容了中英文、全角冒号、Markdown 加粗。但如果模型输出是：

```
Thought: ...
Action: Grep[{...}]
Observation: ...
Thought: ...
Action: Read[...]
```

就会把后面的 Thought/Action 全部吞进第一个 Action，导致工具参数乱飞。
所以它又加了一层“截断补丁”：

```python
if action_raw:
    stop_patterns = ["\nThought:", "\n思考:", "\nAction:", "\n行动:", "\nObservation:", ...]
    ...
    action_raw = action_raw[:earliest_stop].strip()
```

这个逻辑很聪明，但它恰恰暴露了一个事实：
**我们不是在做协议调用，而是在“修作文”。**

---

## 02｜容错补丁越来越多，但稳定性依旧不可控

当模型的 Action 输入是 JSON 时，麻烦会更大。因为模型一旦输出了 `}]`、
或者多了个括号，工具就直接报错。

所以旧版 ToolRegistry 又不得不写了一堆 JSON 容错：

```python
# 1b 常见模型输出尾部多了一个 ']' 的容错
if obj is None and raw.startswith("{") and raw.endswith("}]"):
    obj = _try_json(raw[:-1].strip())

# 1c 模型输出为数组包裹一个对象
if obj is None and raw.startswith("[") and raw.endswith("]"):
    arr = _try_json(raw)
    if isinstance(arr, list) and len(arr) == 1 and isinstance(arr[0], dict):
        obj = arr[0]

# 1e 正则兜底：提取首个完整 JSON 对象
if obj is None and "{" in raw and "}" in raw:
    ...
```

（来自 `docs/wechat_mycodeagent_article/HelloCodeAgentCli/tools/registry.py`）

我把它叫作“救火式解析”。它可以提高成功率，但它解决不了根本问题：
**输入漂移永远存在，只是暂时被容错遮住了。**

当工具越多、调用越频繁，这种漂移就会被放大——
你看起来是“偶发错误”，实际上是“协议层在流血”。

---

## 03｜调研后的结论：把“文本解析问题”变成“结构化协议问题”

后来我去系统读了一遍主流 Code Agent 的实现方式，
发现大家几乎都在做同一件事：

**把 ReAct 的 Action 从“字符串协议”升级为 Function Calling。**

这不是“把格式写得更严”，而是**彻底换了通信方式**：
模型不再输出 `tool_name[...]`，而是输出结构化 `tool_calls`，
框架再把结果和 `tool_call_id` 精确绑定。

这件事在我自己的设计文档里也有一句硬结论：

> “统一 function calling，避免 Action 文本解析与 tool_call_id 缺失。”

（`docs/上下文工程设计文档.md`）

所以我开始把整条链路换成 function calling。

---

## 04｜改造三件套：工具 Schema → tool_calls → tool_call_id

### 1）工具 Schema：参数被强约束

我在 `tools/registry.py` 里加了 `get_openai_tools()`：
每个 Tool 的参数从 `ToolParameter` 自动转成 JSON Schema。

```python
tools.append({
  "type": "function",
  "function": {
    "name": tool.name,
    "description": tool.description or "",
    "parameters": self._parameters_to_schema(params),
  },
})
```

这一步的意义是：**模型只能在 schema 里填值，而不是自由拼字符串。**

### 2）tool_calls：模型输出变结构化

在 `agents/codeAgent.py` 的 ReAct 循环里，我直接用 `invoke_raw(..., tools=...)`：

```python
raw_response = self.llm.invoke_raw(messages, tools=tools_schema, tool_choice=tool_choice)
...
tool_calls = self._extract_tool_calls(raw_response)
```

不再去解析 Action 字符串，直接抽取 `tool_calls`。
这一步把“文本解析”变成了“结构读取”。

### 3）tool_call_id：调用和结果强绑定

这是最关键的一环：
每个 tool_call 都有 id，我会确保它存在，写入 assistant 消息后再执行工具。
然后把工具结果用相同 id 回填到 tool message 里。

```python
if not call.get("id"):
    call["id"] = f"call_{uuid.uuid4().hex}"
...
self.history_manager.append_tool(
    tool_name=tool_name,
    raw_result=observation,
    metadata={"step": step, "tool_call_id": tool_call_id},
)
```

历史序列化的时候也会严格保留 `tool_calls` / `tool_call_id`：

```python
assistant_msg["tool_calls"] = [{
  "id": call_id,
  "type": "function",
  "function": {"name": name, "arguments": args_str},
}]

messages.append({
  "role": "tool",
  "tool_call_id": tool_call_id,
  "content": msg.content,
})
```

（来自 `core/context_engine/history_manager.py`）

这意味着：**每一次工具调用都能精确对应结果，链路不会再断。**

---

## 05｜从“修格式”到“修协议”，ReAct 才真正稳定

我在旧版里为了“能跑”，写了大量容错补丁；
现在我把问题上升到协议层，反而把补丁砍掉了。

这次改造带来的变化非常直观：

- 模型不再纠结 Thought/Action 格式；
- 工具调用失败的来源更清晰（参数错误 vs 工具执行错误）；
- History 里每条 Observation 都有对应的 tool_call_id，可回放、可追踪；
- 上下文拼装变简单了，ContextBuilder 只负责拼消息列表，不再拼 scratchpad。

一句话总结：

**ReAct 的稳定性，不是靠“写更严的提示词”，而是靠“让模型说人话→说协议话”。**

---

接下来我做的，是在这个稳定的 function calling 之上，继续解决“长上下文腐烂”的问题。
第6章讲上下文工程与历史压缩，才是另一场硬仗。
