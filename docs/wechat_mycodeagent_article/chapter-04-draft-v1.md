# 第4章：工具体系重构——从“能跑命令”到“可控工具”

前面踩完 Terminal Tool 的坑，我才意识到：问题不是“工具不够多”，而是**工具不够可控**。
要把一个 Code Agent 变成工程里能用的东西，核心不是功能堆叠，而是每一步都能被**结构化验证**。

于是我把这一章的目标定得非常明确：

**工具化的核心不是“更多工具”，而是“每一步都有结构化证据”。**

这意味着：统一协议、可预测的搜索链路、可回滚的编辑链路，以及最后兜底的 Bash。

---

## 01｜先把协议统一：所有工具都必须说同一种“语言”

在 Hello-Agent 里，工具返回的内容偏自由文本，
模型还得去“理解”每个工具的输出结构，这会带来不确定性。

我现在做的是**标准化信封（Standard Envelope）**：
`status / data / text / stats / context` 六件套。
这不是为了写得好看，而是为了“让模型能无脑判定”。

一个最完整的标准信封示例如下（摘取核心结构）：

```json
{
  "status": "partial",
  "data": {
    "paths": ["core/llm.py", "agents/codeAgent.py"],
    "truncated": true,
    "aborted_reason": "time_limit"
  },
  "text": "Found 2 files matching '**/*.py' in 'core'\n(Scanned 12000 items in 2010ms)\n[Partial: Search timed out (>2s). Results are incomplete.]",
  "stats": {"time_ms": 2010, "matched": 2, "visited": 12000},
  "context": {"cwd": ".", "params_input": {"pattern": "**/*.py", "path": "core"}, "path_resolved": "core"}
}
```

有了这个结构，模型不用猜“这是成功还是失败”，
也不需要重新理解输出格式，直接根据 `status` 和 `data` 做下一步动作。

这套协议在 `docs/通用工具响应协议.md` 里定了明确标准，
也是后面一切“可控工具”的基础。

---

## 02｜ToolRegistry 是工具体系的“中枢神经”

工具不是零散的功能块，而是一个统一调度系统。
这个统一入口就是 `tools/registry.py`。

它做了三件非常关键的事情：

### 1）Schema 汇总：把工具“变成函数”

每个 Tool 的参数定义统一转换成 JSON Schema，
通过 `get_openai_tools()` 一次性汇总给模型。

模型不再“自由拼字符串”，而是被 schema 约束在合法参数里。

### 2）乐观锁自动注入：Write/Edit/MultiEdit 不再裸奔

只要你 Read 过文件，ToolRegistry 就会缓存 `file_mtime_ms` 和 `file_size_bytes`，
后续的 Write / Edit / MultiEdit 会自动注入这两个参数：

```python
if name in {"Write", "Edit", "MultiEdit"}:
    parameters = self._inject_optimistic_lock_params(name, parameters)
```

这一步看起来很小，但它把“读前约束”变成了硬约束：
**不 Read 就不能改，Read 过再改也有冲突检测。**

### 3）熔断器：工具连续失败会被暂时禁用

`tools/circuit_breaker.py` 默认是 **3 次失败熔断、300 秒恢复**。
工具一旦进入 open 状态，ToolRegistry 直接返回结构化错误，
防止模型在坏工具上死循环。

> 这就是“体系”的意义：不是工具堆在一起，而是有节制、有自愈。

---

## 03｜搜索链路可控化：LS / Glob / Grep / Read

这一段是我最重视的，因为 80% 的 Code Agent 行为都在“找”。
我把它拆成四个原子动作：

- **LS**：列目录（分页 + 过滤 + 沙箱）
- **Glob**：按名字找文件（双熔断：访问数 + 时间）
- **Grep**：按内容找片段（rg 优先，失败回退 Python）
- **Read**：带行号读取（分页 + 二进制熔断）

这四个工具有几个共同的“可控点”：

- **路径强制在 project_root 内**（沙箱边界）
- **分页与截断**（`limit/offset` 或 `limit/start_line`）
- **结果可复现**（排序一致，Glob 走确定性遍历）
- **partial 可感知**（`data.truncated` / `aborted_reason` 明确提示）

比如 Glob 的“双熔断”就写死在设计文档里：

- `MAX_VISITED_ENTRIES = 20000`
- `MAX_DURATION_MS = 2000`

Grep 也有硬限制：`MAX_RESULTS=100`，超时 2s。
Read 默认只读 500 行，上限 2000 行。

这些限制不是“怕慢”，而是为了保证工具输出**可预测、可复盘**。

---

## 04｜编辑链路可控化：Read → Edit/MultiEdit → Write

工具体系最重要的一条闭环，其实是编辑链路。
我把它设计成“读前约束 + 可预览 + 可回滚”的最小闭环：

### 1）Read：给编辑提供“可定位证据”
Read 的输出带行号，且只读指定范围：

```json
{"path": "agents/codeAgent.py", "start_line": 1, "limit": 120}
```

它返回 `file_mtime_ms` / `file_size_bytes`，
这两个字段会被 ToolRegistry 缓存，作为后续乐观锁。

### 2）Edit / MultiEdit：锚点替换 + diff 预览
Edit 是“单点替换”，MultiEdit 是“同一文件多点原子替换”。
两者都要求 `old_string` 在原文件中唯一匹配，
并支持 `dry_run=true` 只预览 diff：

```json
{
  "path": "core/llm.py",
  "old_string": "def invoke_raw(self, messages: list[dict[str, str]], **kwargs):",
  "new_string": "def invoke_raw(self, messages: list[dict[str, str]], **kwargs) -> Any:",
  "dry_run": true
}
```

MultiEdit 则强调**一次读，多处改，一次写**，
并且会检测编辑区间是否重叠，避免互相覆盖。

### 3）Write：全量覆盖 + diff 预览
Write 只做一件事：**写完整内容**。
它会返回 diff 预览，支持 dry_run，并且要求已有文件必须 Read 过。

这套链路真正做到了一件事：
**编辑变成“可验证动作”，而不是“赌命写文件”。**

---

## 05｜Bash 降级为兜底：能用但不滥用

Bash 不是被删掉，而是被降级。
它变成了“没有工具能解决时的最后手段”。

关键的硬约束（来自 `docs/BashTool设计文档.md`）：

- **禁止读/搜/列命令**：`ls / cat / head / tail / grep / find / rg`
- **禁止交互命令**：vim、nano、top、ssh 等
- **禁止网络（默认）**：curl/wget 被禁，需要显式开 `BASH_ALLOW_NETWORK=true`
- **黑名单**：rm -rf /、sudo/su、mkfs/fdisk 等危险命令
- **超时与统一截断**：输出过大直接截断，写入 tool-output

这样 Bash 就不会成为“绕过工具体系的后门”。
它仍然存在，但必须付出明确的成本与风险。

---

## 06｜统一截断 + 落盘：工具体系的安全阀

再可控的工具，也会有“输出太大”的时刻。
所以我加了统一截断与落盘机制：

- 超过 `MAX_LINES=2000` 或 `MAX_BYTES=50KB` → 截断
- 完整结果落盘到 `tool-output/`
- 返回结构中明确 `full_output_path`

这一招看似是“节流”，但实际是**安全阀**：
既不让上下文爆炸，又保留了完整证据可回查。

---

## 07｜提示词集成：让模型“用得对”

工具可控只是第一步，还得让模型知道**何时用、怎么用**。

我把所有工具的使用规则写进了：

- `prompts/agents_prompts/L1_system_prompt.py`
- `prompts/tools_prompts/` 下的各工具说明

L1 里明确要求：
- 禁止 Thought/Action 文本
- 必须用 Function Calling
- 每次只调用一个工具

工具 prompt 则进一步细化：
例如 Read 要求分页、Edit 要求 Read 前置，Bash 明确禁用 ls/cat/grep 等。

**工具体系 + 提示词约束**，才是真正的可控闭环。

---

## 小结：工具体系不是清单，而是一条“可复盘链路”

这一章我真正解决的是：

- 工具返回统一协议，模型能稳定理解
- 搜索链路可控：LS/Glob/Grep/Read 有分页/熔断/沙箱
- 编辑链路可控：Read → Edit/MultiEdit → Write + 乐观锁
- Bash 只做兜底：强约束 + 禁网络 + 截断保护
- ToolRegistry 作为中枢：schema 汇总 + 熔断 + 乐观锁注入

**工具越多不重要，重要的是每一步都有结构化证据。**

下一章，我会讲另一个“让人崩溃”的问题：
ReAct 字符串解析不稳定，以及为什么必须切换 Function Calling。
