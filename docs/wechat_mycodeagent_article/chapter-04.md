# 四、把"自由命令"拆成"可控工具"：我的工具体系重构实录

踩完 Terminal Tool 的坑，我才意识到：问题不是"工具不够多"，而是**工具不够可控**。

当时读到一篇解读 Claude Code 的文章，讲工具分层，说"高频动作更需要确定性"。这一下把我点醒了。

我的问题，恰恰是把所有能力塞进了一个"无限自由"的 Terminal Tool。低频场景确实灵活，但在高频动作上反而成了**噪音制造机**。

是时候重新设计了。

---

## 1、重构目标：每一步都有结构化证据

核心原则：

> **工具化的核心不是"更多工具"，而是"每一步都有结构化证据"。**

按"频率"和"确定性"重新分类：

| 频率 | 确定性 | 工具 | 设计目标 |
|-----|--------|------|---------|
| 高频 | 强 | LS / Glob / Grep / Read | 原子化、标准化、沙箱 |
| 中频 | 中等 | Write / Edit / MultiEdit | 安全、可确认、乐观锁 |
| 低频 | 弱 | Bash | 兜底、受控、禁网络 |

说白了，不是为了多造轮子，而是让**每一步都可观察、可判断、可纠错**。

---

## 2、先统一协议：所有工具说同一种"语言"

Hello-Agent 里工具返回偏自由文本，模型还得"理解"每个工具的输出结构。

我现在搞的是**标准化信封（Standard Envelope）**：`status / data / text / stats / context` 五件套。

不是为了写得好看，而是让"模型能无脑判定"。

标准结构长这样：

```json
{
  "status": "partial",
  "data": {
    "paths": ["core/llm.py", "agents/codeAgent.py"],
    "truncated": true
  },
  "text": "Found 2 files matching '**/*.py' (Scanned 12000 items, timed out)",
  "stats": {"time_ms": 2010, "matched": 2},
  "context": {"cwd": ".", "params_input": {"pattern": "**/*.py"}}
}
```

模型不用猜"这是成功还是失败"，直接看 `status` 和 `data` 就知道下一步干嘛。

> 把"工具输出"从"杂乱文本"升级成"可推理信号"——这是质变。

---

## 3、ToolRegistry：工具体系的"中枢神经"

工具不是零散功能块，而是统一调度系统。入口是 `tools/registry.py`，它干三件关键的事：

### Schema 汇总：把工具"变成函数"

每个 Tool 的参数转成 JSON Schema，通过 `get_openai_tools()` 汇总给模型。

**模型不再"自由拼字符串"，而是被 schema 约束在合法参数里。**

### 乐观锁自动注入：Write/Edit 不再裸奔

Read 过的文件，ToolRegistry 会缓存 `file_mtime_ms` 和 `file_size_bytes`，后续 Write/Edit/MultiEdit 自动注入：

```python
if name in {"Write", "Edit", "MultiEdit"}:
    parameters = self._inject_optimistic_lock_params(name, parameters)
```

**不 Read 就不能改，Read 过再改也有冲突检测。**

### 熔断器：工具连续失败会被禁用

`tools/circuit_breaker.py` 默认 **3 次失败熔断、300 秒恢复**。工具进入 open 状态后，ToolRegistry 直接返回结构化错误，防止模型在坏工具上死循环。

---

## 4、搜索链路：从"一条大命令"到"原子动作"

V0 里模型可能写一条命令干完所有事：

```bash
rg -n "TargetFunc" src/ | grep "class Foo" | sed -n '1,120p'
```

看着挺酷，但失败时你只看到一个"空结果"，根本不知道哪步挂了。

重构后拆成四个原子动作：

| 工具 | 干嘛的 | 关键约束 |
|-----|--------|---------|
| LS | 列目录 | 分页 + 过滤 + 沙箱 |
| Glob | 按名字找文件 | 双熔断：条目数 + 时间 |
| Grep | 按内容找片段 | rg 优先，失败回退 Python |
| Read | 带行号读取 | 分页 + 二进制熔断 |

### Glob：把"找文件"变成确定动作

- `pattern` 永远相对 `path`，不让模型猜"从哪搜"
- 双熔断：最大 20000 条目、最多 2 秒
- `**` 才能跨目录，`*` 不跨
- 返回相对路径，方便后续 Read/Edit 直接接

调用很简单：
```json
{"pattern": "**/*context*.py", "path": "core", "limit": 50}
```

### Grep：把"找符号"变成可推理的证据

1. 优先 `rg`，失败回退 Python（必须标明 fallback）
2. 输出固定为 `file/line/text`，按 mtime 排序

返回长这样：
```json
{
  "status": "partial",
  "data": {
    "matches": [{"file": "core/agent.py", "line": 42, "text": "class Agent:"}],
    "truncated": true,
    "fallback_used": true
  }
}
```

**讲真，模型不需要理解"输出是什么意思"，只需要判断"下一步读哪一行"。**

这些工具的共同可控点：
- 路径强制在 `project_root` 内（沙箱）
- 分页与截断（`limit/offset`）
- 结果可复现（排序一致）
- partial 可感知（`truncated` / `aborted_reason` 明确提示）

---

## 5、编辑链路：Read → Edit/MultiEdit → Write

工具体系最重要的闭环。设计成"读前约束 + 可预览 + 可回滚"：

### Read：给编辑提供"可定位证据"

带行号读取指定范围，返回 `file_mtime_ms` / `file_size_bytes` 作为乐观锁：

```json
{"path": "agents/codeAgent.py", "start_line": 1, "limit": 120}
```

### Edit / MultiEdit：锚点替换 + diff 预览

Edit 是"单点替换"，MultiEdit 是"同一文件多点原子替换"。都要求 `old_string` 唯一匹配，支持 `dry_run=true` 只预览：

```json
{
  "path": "core/llm.py",
  "old_string": "def invoke_raw(self, messages: list[dict], **kwargs):",
  "new_string": "def invoke_raw(self, messages: list[dict], **kwargs) -> Any:",
  "dry_run": true
}
```

MultiEdit 会检测编辑区间是否重叠，避免互相覆盖。

### Write：全量覆盖 + diff 预览

只写完整内容，返回 diff 预览，支持 dry_run，已有文件必须 Read 过。

> **编辑变成"可验证动作"，而不是"赌命写文件"。**

---

## 6、Bash 从"默认"变成"兜底"

Bash 没被删掉，而是被降级为"最后手段"。

硬约束：
- **禁止读/搜/列**：`ls / cat / head / grep / find / rg`
- **禁止交互**：vim、nano、top、ssh
- **禁止网络（默认）**：curl/wget 被禁，需显式开 `BASH_ALLOW_NETWORK=true`
- **黑名单**：rm -rf /、sudo/su、mkfs/fdisk
- **超时与截断**：输出过大直接截断，写入 tool-output

Bash 不会成为"绕过工具体系的后门"。它仍然存在，但必须付出明确的成本与风险。

---

## 7、统一截断 + 落盘：工具体系的安全阀

再可控的工具，也会有"输出太大"的时候。

- 超过 `MAX_LINES=2000` 或 `MAX_BYTES=50KB` → 截断
- 完整结果落盘到 `tool-output/`
- 返回结构中明确 `full_output_path`

这一招是**安全阀**：既不让上下文爆炸，又保留完整证据可回查。

---

## 8、写在最后

我后来越来越明白一件事：

> **Code Agent 的"聪明"，不是模型聪明，而是工具设计够不够可控。**

这一章真正解决的是：

- ✅ 工具返回统一协议，模型能稳定理解
- ✅ 搜索链路可控：LS/Glob/Grep/Read 有分页/熔断/沙箱
- ✅ 编辑链路可控：Read → Edit/MultiEdit → Write + 乐观锁
- ✅ Bash 只做兜底：强约束 + 禁网络 + 截断保护
- ✅ ToolRegistry 作为中枢：schema 汇总 + 熔断 + 乐观锁注入

**工具越多不重要，重要的是每一步都有结构化证据。**

这套改造才真正让我从"能跑"走向"能稳"。

---

**下一章**：字符串 ReAct 解析为啥不靠谱，以及我为什么转向 Function Calling。
