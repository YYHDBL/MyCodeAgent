# 四、把"自由命令"拆成"可控工具"：我的工具体系重构实录

前面踩完 Terminal Tool 的坑，我才意识到：问题不是"工具不够多"，而是**工具不够可控**。

当时读到一篇解读 Claude Code 的文章，讲工具分层，说"高频动作更需要确定性"。这一下把我点醒了。

我的问题，恰恰是把所有能力塞进了一个"无限自由"的 Terminal Tool。低频场景确实灵活，但在高频动作上反而成了**噪音制造机**。

是时候重新设计了。

---

## 1、重构目标：每一步都有结构化证据

我给自己定了一条核心原则：

> **工具化的核心不是"更多工具"，而是"每一步都有结构化证据"。**

这意味着：统一协议、可预测的搜索链路、可回滚的编辑链路，以及最后兜底的 Bash。

按"频率"和"确定性"重新分类：

| 频率 | 确定性 | 工具 | 设计目标 |
|-----|--------|------|---------|
| 高频 | 强 | LS / Glob / Grep / Read | 原子化、标准化、沙箱 |
| 中频 | 中等 | Write / Edit / MultiEdit | 安全、可确认、乐观锁 |
| 低频 | 弱 | Bash | 兜底、受控、禁网络 |

说白了，不是为了多造轮子，而是让**每一步都可观察、可判断、可纠错**。

---

## 2、先把协议统一：所有工具说同一种"语言"

在 Hello-Agent 里，工具返回的内容偏自由文本，模型还得去"理解"每个工具的输出结构。

我现在做的是**标准化信封（Standard Envelope）**：`status / data / text / stats / context` 六件套。

这不是为了写得好看，而是为了"让模型能无脑判定"。

标准结构长这样：

```json
{
  "status": "partial",
  "data": {
    "paths": ["core/llm.py", "agents/codeAgent.py"],
    "truncated": true,
    "aborted_reason": "time_limit"
  },
  "text": "Found 2 files matching '**/*.py' in 'core'\n(Scanned 12000 items in 2010ms)\n[Partial: Search timed out (>2s).]",
  "stats": {"time_ms": 2010, "matched": 2, "visited": 12000},
  "context": {"cwd": ".", "params_input": {"pattern": "**/*.py", "path": "core"}}
}
```

有了这个结构，模型不用猜"这是成功还是失败"，直接根据 `status` 和 `data` 做下一步动作。

> 把"工具输出"从"杂乱文本"升级成"可推理信号"——这是质变。

---

## 3、ToolRegistry：工具体系的"中枢神经"

工具不是零散的功能块，而是一个统一调度系统。这个统一入口就是 `tools/registry.py`。

它做了三件关键的事：

### Schema 汇总：把工具"变成函数"

每个 Tool 的参数定义统一转换成 JSON Schema，通过 `get_openai_tools()` 一次性汇总给模型。

**模型不再"自由拼字符串"，而是被 schema 约束在合法参数里。**

### 乐观锁自动注入：Write/Edit 不再裸奔

只要你 Read 过文件，ToolRegistry 就会缓存 `file_mtime_ms` 和 `file_size_bytes`，后续的 Write / Edit / MultiEdit 会自动注入这两个参数：

```python
if name in {"Write", "Edit", "MultiEdit"}:
    parameters = self._inject_optimistic_lock_params(name, parameters)
```

这一步看起来很小，但它把"读前约束"变成了硬约束：

> **不 Read 就不能改，Read 过再改也有冲突检测。**

### 熔断器：工具连续失败会被暂时禁用

`tools/circuit_breaker.py` 默认是 **3 次失败熔断、300 秒恢复**。工具一旦进入 open 状态，ToolRegistry 直接返回结构化错误，防止模型在坏工具上死循环。

---

## 4、搜索链路可控化：从"一条大命令"到"原子动作"

V0 里模型可能写一条命令干完所有事：

```bash
rg -n "TargetFunc" src/ | grep "class Foo" | sed -n '1,120p'
```

看着挺酷，但失败时你只看到一个"空结果"，根本不知道哪步挂了。

重构后的目标很明确：**拆成原子工具，每次只做一件事，结果必须结构化。**

我把"找"这件事拆成四个原子动作：

- **LS**：列目录（分页 + 过滤 + 沙箱）
- **Glob**：按名字找文件（双熔断：访问数 + 时间）
- **Grep**：按内容找片段（rg 优先，失败回退 Python）
- **Read**：带行号读取（分页 + 二进制熔断）

### Glob：把"找文件"变成确定动作

高频动作，约束得很死：

- `pattern` 永远相对 `path`，不让模型猜"从哪搜"
- 双熔断：最大 20000 条目、最多 2 秒
- `**` 才能跨目录，`*` 不跨
- 返回相对路径，方便后续 Read/Edit 直接接

调用很简单：

```json
{
  "pattern": "**/*context*.py",
  "path": "core",
  "limit": 50
}
```

返回标准化路径列表，下一步 Read 就很稳。

### Grep：把"找符号"变成可推理的证据

两条核心规矩：

1. 优先 `rg`，失败时回退到 Python 搜索（必须标明 fallback）
2. 输出固定为 `file/line/text`，按 mtime 排序

返回长这样：

```json
{
  "status": "partial",
  "data": {
    "matches": [
      {"file": "core/agent.py", "line": 42, "text": "class Agent(ABC):"}
    ],
    "truncated": true,
    "fallback_used": true,
    "fallback_reason": "rg_not_found"
  }
}
```

**讲真，模型不需要理解"输出是什么意思"，只需要判断"下一步读哪一行"。**

这些工具有几个共同的"可控点"：

- **路径强制在 project_root 内**（沙箱边界）
- **分页与截断**（`limit/offset` 或 `limit/start_line`）
- **结果可复现**（排序一致，Glob 走确定性遍历）
- **partial 可感知**（`data.truncated` / `aborted_reason` 明确提示）

---

## 5、编辑链路可控化：Read → Edit/MultiEdit → Write

工具体系最重要的一条闭环，其实是编辑链路。我把它设计成"读前约束 + 可预览 + 可回滚"的最小闭环：

### Read：给编辑提供"可定位证据"

Read 的输出带行号，且只读指定范围：

```json
{"path": "agents/codeAgent.py", "start_line": 1, "limit": 120}
```

它返回 `file_mtime_ms` / `file_size_bytes`，这两个字段会被 ToolRegistry 缓存，作为后续乐观锁。

### Edit / MultiEdit：锚点替换 + diff 预览

Edit 是"单点替换"，MultiEdit 是"同一文件多点原子替换"。两者都要求 `old_string` 在原文件中唯一匹配，并支持 `dry_run=true` 只预览 diff：

```json
{
  "path": "core/llm.py",
  "old_string": "def invoke_raw(self, messages: list[dict[str, str]], **kwargs):",
  "new_string": "def invoke_raw(self, messages: list[dict[str, str]], **kwargs) -> Any:",
  "dry_run": true
}
```

MultiEdit 则强调**一次读，多处改，一次写**，并且会检测编辑区间是否重叠，避免互相覆盖。

### Write：全量覆盖 + diff 预览

Write 只做一件事：**写完整内容**。它会返回 diff 预览，支持 dry_run，并且要求已有文件必须 Read 过。

这套链路真正做到了一件事：

> **编辑变成"可验证动作"，而不是"赌命写文件"。**

---

## 6、Bash 从"默认"变成"兜底"

Bash 不是被删掉，而是被降级。它变成了"没有工具能解决时的最后手段"。

关键的硬约束（来自 `docs/BashTool设计文档.md`）：

- **禁止读/搜/列命令**：`ls / cat / head / tail / grep / find / rg`
- **禁止交互命令**：vim、nano、top、ssh 等
- **禁止网络（默认）**：curl/wget 被禁，需要显式开 `BASH_ALLOW_NETWORK=true`
- **黑名单**：rm -rf /、sudo/su、mkfs/fdisk 等危险命令
- **超时与统一截断**：输出过大直接截断，写入 tool-output

这样 Bash 就不会成为"绕过工具体系的后门"。它仍然存在，但必须付出明确的成本与风险。

---

## 7、统一截断 + 落盘：工具体系的安全阀

再可控的工具，也会有"输出太大"的时刻。所以我加了统一截断与落盘机制：

- 超过 `MAX_LINES=2000` 或 `MAX_BYTES=50KB` → 截断
- 完整结果落盘到 `tool-output/`
- 返回结构中明确 `full_output_path`

这一招看似是"节流"，但实际是**安全阀**：既不让上下文爆炸，又保留了完整证据可回查。

---

## 8、写在最后

我后来越来越明白一件事：

> **Code Agent 的"聪明"，不是模型聪明，而是工具设计够不够可控。**

这一章真正解决的是：

- 工具返回统一协议，模型能稳定理解
- 搜索链路可控：LS/Glob/Grep/Read 有分页/熔断/沙箱
- 编辑链路可控：Read → Edit/MultiEdit → Write + 乐观锁
- Bash 只做兜底：强约束 + 禁网络 + 截断保护
- ToolRegistry 作为中枢：schema 汇总 + 熔断 + 乐观锁注入

**工具越多不重要，重要的是每一步都有结构化证据。**

把高频动作拆成原子工具，统一返回协议，让模型用结构化信号做决策——这套改造才真正让我从"能跑"走向"能稳"。

---

**下一章**：字符串 ReAct 解析为啥不靠谱，以及我为什么转向 Function Calling。
