# 五、从"修作文"到"走协议"：我为什么放弃字符串 ReAct

工具体系改造完成后，我以为问题已经解决了一大半。

工具更可控了、返回协议也统一了，但真正跑起来还是会"偶发翻车"。

翻车的根源不在工具，而在**工具是怎么被调用的**。

那时候我沿用的是 Hello-Agent 的 ReAct：模型输出 Thought/Action 字符串，框架用正则解析。工具变精细了，但调用协议还是"自由文本"——只要模型多说一句、少一个符号，链路就断。

---

## 1、旧版 ReAct：全靠"字符串纪律"

Hello-Agent 的 ReAct Prompt 写得很死，要求模型必须输出 Thought 和 Action 两行：

```text
Thought: <你的思考（简短）>
Action: <以下二选一>
- tool_name[tool_input]
- Finish[最终回答]
```

表面上是强约束，本质还是**字符串协定**。模型多写一句解释、或者把 Action 放错位置，解析就开始抖。

看看解析代码才知道它有多脆：

```python
m = re.search(
    r"(?:\*\*)?(Thought|思考)(?:\*\*)?\s*[:：]\s*(.*?)\n"
    r"(?:\*\*)?(Action|行动)(?:\*\*)?\s*[:：]\s*(.*)\s*$",
    t,
    flags=re.DOTALL,
)
```

这个正则已经很"照顾模型"了：兼容中英文、全角冒号、Markdown 加粗。但如果模型输出是多轮 Thought/Action，就会把后面的全部吞进第一个 Action，导致参数乱飞。

于是又加"截断补丁"：

```python
stop_patterns = ["\nThought:", "\n思考:", "\nAction:", "\n行动:", ...]
action_raw = action_raw[:earliest_stop].strip()
```

这个逻辑挺聪明，但它暴露了一个事实：**我们不是在做协议调用，而是在"修作文"。**

---

## 2、救火式解析：补丁越打越多，问题还在

当 Action 输入是 JSON 时，麻烦更大。模型一旦输出了 `}]`、或者多了个括号，工具就直接报错。

旧版 ToolRegistry 里堆了一堆 JSON 容错：

```python
# 常见模型输出尾部多了一个 ']' 的容错
if obj is None and raw.startswith("{") and raw.endswith("}]"):
    obj = _try_json(raw[:-1].strip())

# 模型输出为数组包裹一个对象
if obj is None and raw.startswith("[") and raw.endswith("]"):
    arr = _try_json(raw)
    if isinstance(arr, list) and len(arr) == 1:
        obj = arr[0]

# 正则兜底：提取首个完整 JSON 对象
if obj is None and "{" in raw and "}" in raw:
    ...
```

我把它叫作**"救火式解析"**。它能提高成功率，但解决不了根本问题：

> **输入漂移永远存在，只是被容错暂时遮住了。**

工具越多、调用越频繁，这种漂移就越明显。看起来是"偶发错误"，实际上是**协议层在流血**。

---

## 3、调研后的顿悟：文本解析 → 结构化协议

后来系统读了一遍主流 Code Agent 的实现，发现大家几乎都在做同一件事：

**把 ReAct 的 Action 从"字符串协议"升级为 Function Calling。**

讲真，这不是"把格式写得更严"，而是**彻底换了通信方式**——模型不再输出 `tool_name[...]`，而是输出结构化 `tool_calls`，框架再把结果和 `tool_call_id` 精确绑定。

我自己的设计文档里也有一句硬结论：

> "统一 function calling，避免 Action 文本解析与 tool_call_id 缺失。"

于是开干，把整条链路换成 function calling。

---

## 4、改造三件套：Schema → tool_calls → tool_call_id

### Schema：参数被强约束

在 `tools/registry.py` 里加了 `get_openai_tools()`，每个 Tool 的参数自动转成 JSON Schema：

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

**说白了，模型只能在 schema 里填值，而不是自由拼字符串。**

### tool_calls：模型输出变结构化

在 `agents/codeAgent.py` 里直接用 `invoke_raw(..., tools=...)`：

```python
raw_response = self.llm.invoke_raw(messages, tools=tools_schema)
tool_calls = self._extract_tool_calls(raw_response)
```

不再解析 Action 字符串，直接抽取 `tool_calls`。把"文本解析"变成"结构读取"。

### tool_call_id：调用和结果强绑定

最关键的一环：每个 tool_call 都有 id，写入 assistant 消息后再执行工具，结果用相同 id 回填。

```python
if not call.get("id"):
    call["id"] = f"call_{uuid.uuid4().hex}"

self.history_manager.append_tool(
    tool_name=tool_name,
    raw_result=observation,
    metadata={"step": step, "tool_call_id": tool_call_id},
)
```

历史序列化时严格保留 `tool_calls` / `tool_call_id`：

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

**每一次工具调用都能精确对应结果，链路不会再断。**

---

## 5、写在最后

旧版为了"能跑"，写了大量容错补丁；现在把问题上升到协议层，反而把补丁砍掉了。

改造带来的变化很直观：

- 模型不再纠结 Thought/Action 格式
- 工具调用失败的来源更清晰（参数错误 vs 执行错误）
- History 里每条 Observation 都有 tool_call_id，可回放、可追踪
- 上下文拼装变简单了，ContextBuilder 只负责拼消息列表

**说白了，ReAct 的稳定性不是靠"写更严的提示词"，而是靠"让模型说协议话"。**

---

**下一章**：在稳定的 function calling 之上，继续解决"长上下文腐烂"的问题。
