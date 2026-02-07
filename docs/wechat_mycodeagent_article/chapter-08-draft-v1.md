# 八、扩展期：MCP / Task / Todo 让 Agent 更“像团队”

有一次我让 Agent 做一个任务：**“调研 MCP 协议，然后给我一个可落地的示例工具方案。”**

结果它先是疯狂搜索，把主线上下文刷爆了；
好不容易整理出结论，开始写代码时又忘了前面调研的关键点；
写到一半卡住，我问它进度，它自己也说不清“现在做到哪了”。

那一刻我意识到：**单个模型跑长流程，就像让一个人同时当老师、学生和班长——全搞砸。**

于是我补上了扩展能力这一层：**MCP / Task / Todo**。

这章讲的不是“多了几个功能”，而是**把长流程拆成“可控协作”**。

---

## 1、MCP：把外部能力“注册进来”

长流程的第一步通常是调研。我不想让模型胡乱搜索，于是把“外部检索”变成可控工具。

MCP 的设计像一个“工具插槽”：
- `mcp_servers.json` 描述外部服务
- `tools/mcp/config.py` 加载配置
- `tools/mcp/loader.py` 连接并注册工具
- 注册后进入 `ToolRegistry`，成为标准工具

注册入口在 `agents/codeAgent.py`：
```python
clients, tools_meta = register_mcp_servers(self.tool_registry, self.project_root)
self._mcp_clients = clients
self._mcp_tools_prompt = format_mcp_tools_prompt(tools_meta)
```

这一步很关键：**不仅把 MCP 工具注册进来，还把工具描述注入提示词**，模型才知道“外部工具怎么用”。

MCP 的返回也被统一封装成通用响应协议（`status/data/text/stats/context/error`），
错误码直接用 `MCP_TIMEOUT / MCP_NETWORK_ERROR / MCP_PARSE_ERROR`，不再是“模糊失败”。

在 `tools/mcp/protocol.py` 里就是标准信封：
```python
return {
  "status": "error",
  "error": {"code": "MCP_TIMEOUT", "message": "..."},
  "stats": {"time_ms": ...},
  "context": {"params_input": ..., "mcp_tool": tool_name}
}
```

**外部能力不是野生的，而是被协议化后再接入。**

---

## 1.5、为什么一定要扩展？（对比表）

```
┌──────────────────┬──────────────────────────────┬─────────────────────────────────┐
│ 问题场景         │ 不用扩展能力的后果           │ 用了扩展能力的效果              │
├──────────────────┼──────────────────────────────┼─────────────────────────────────┤
│ 需要外部资料     │ 模型胡乱搜索，结果不可控     │ MCP 标准化接入，结果结构化      │
├──────────────────┼──────────────────────────────┼─────────────────────────────────┤
│ 调研任务打断主线 │ 上下文被污染，主任务忘了干啥 │ Task 子代理隔离会话，不污染主线 │
├──────────────────┼──────────────────────────────┼─────────────────────────────────┤
│ 长流程中途偏航   │ “做到哪了”都不知道           │ Todo 地图随时知道进度和待办     │
└──────────────────┴──────────────────────────────┴─────────────────────────────────┘
```

这张表背后的核心思想只有一句话：**扩展不是堆能力，而是让每个环节“可控”。**

---

## 2、Task 子代理：把调研任务拆出去

调研如果全由主 Agent 做，主线会被打断、上下文被污染。

于是我在 Task 工具里做了一个极简“子代理系统”：
- 独立会话（隔离消息）
- 受限工具集（只读为主）
- 指定子代理类型 + 模型路由（main / light）

Task 的输入很简单：
```json
{
  "description": "调研外部资料并总结",
  "prompt": "请梳理 XXX 的关键点并给出实现建议",
  "subagent_type": "explore",
  "model": "light"
}
```

子代理类型来自 `docs/task(subagent)设计文档.md`：
- general / explore / summary / plan

工具限制也很硬：
- deny：`Task, Write, Edit, MultiEdit, Bash`
- allow：`LS, Glob, Grep, Read, TodoWrite`

这在 `tools/builtin/task.py` 里是写死的：
```python
DENIED_TOOLS = {"Task", "Write", "Edit", "MultiEdit", "Bash"}
ALLOWED_TOOLS = {"LS", "TodoWrite", "Glob", "Grep", "Read"}
```

**它确保子代理只做“调研”，不会越界修改代码。**

模型路由也很清楚：简单任务走 `light`，复杂分析走 `main`。主 Agent 把“重活”留给主模型，把“资料搬运”交给轻模型，成本和质量都有平衡。

---

## 3、TodoWrite：让执行变得“可追踪”

调研完只是输入，真正难的是“落地实现”。

为了避免长任务中途偏航，我把 Todo 作为执行层的“地基”。

TodoWrite 不是普通清单，它有几个强约束：
- **声明式覆盖**：每次提交完整列表，不做 diff
- **最多 1 个 in_progress**：避免并行混乱
- **自动 recap**：把当前关键目标压缩到上下文尾部
- **自动持久化**：任务完成后写入 `memory/todos/`

### 为什么要“最多 1 个 in_progress”？

因为我发现模型很容易“贪心”：同时标记 3 个任务 in_progress，
结果每个都做一半，最后全乱了。

**强制“一次只能做一件事”，反而让它更专注。**

### 为什么要“自动 recap”？

长流程跑到后面，模型经常会忘记“当前目标是什么”。
Recap 就像一个提醒器：
```
[1/3] In progress: 修复重叠检测. Pending: 更新文档...
```

**每次调用工具前，它都能看到这条提醒，不会跑偏。**

在 `tools/builtin/todo_write.py` 里，工具会校验数量/长度/状态并生成 recap。
`prompts/tools_prompts/todo_write_prompt.py` 还强制模型：
- 只在“>=3 步任务”时使用
- 每完成一步立即更新
- 取消任务必须显式标记

**如果说 Trace 是复盘证据，Todo 就是过程中的“路线图”。**

---

## 4、把三者串起来：一个“调研+实现”的真实链路

举个真实例子：我让 Agent 做 **“调研 MCP 协议并实现一个示例工具”**。

### Step 1：MCP 拉资料
主 Agent 调用一个 MCP 工具（例如 `mcp_web_search` 之类）：
```
Tool: mcp_web_search
Args: {"query": "MCP Model Context Protocol overview"}
```
返回结果直接进入上下文：
```
text: "MCP 是 ...，核心是 ..."
status: success
```

### Step 2：Task 拆调研
主 Agent 让子代理去本地代码里对照现有实现：
```json
{
  "description": "梳理当前 MCP 实现位置与结构",
  "prompt": "请定位 MCP 相关目录和关键文件，并给出扩展建议",
  "subagent_type": "explore",
  "model": "light"
}
```
子代理只用 `Grep/Read`，返回类似：
```
- MCP 实现在 tools/mcp/
- 入口在 tools/mcp/loader.py
- 建议扩展 adapter 的参数校验
```

### Step 3：TodoWrite 跟进落地
主 Agent 把“实现步骤”写成 Todo：
```
[ ] 1. 阅读 MCP 协议核心部分
[ ] 2. 设计示例工具接口
[ ] 3. 实现并注册示例工具
```

每完成一步，Todo 会自动更新：
```
[1/3] In progress: 设计示例工具接口. Pending: 实现并注册示例工具...
```

**全程主 Agent 只做决策，子代理做调研，Todo 管进度——像个小团队在协作。**

---

## 5、写在最后

从 V0 到现在，差别在哪？

**V0 时**：让 Agent 做长流程任务，就像让一个人同时当编剧、导演、演员——全搞砸。

**现在**：MCP 拉资料，Task 拆调研，Todo 管进度——**像个小团队在协作**。

> **扩展能力不是让 Agent 变复杂，而是让它把复杂拆成可控路径。**

---

**下一章**：Skills ——把工程知识固化成可复用的“技巧包”。
