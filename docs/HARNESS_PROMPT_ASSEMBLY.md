# Harness Prompt Assembly

本文档描述 Phase 1 之后的 Prompt Assembly 边界。目标不是接入真实 prompt cache，而是把稳定控制面和动态运行时信号分开，并为后续缓存、Trace 与评估提供稳定指纹。

## 四层生命周期

```text
Constitution
  -> Agent 稳定行为原则

Tool Contracts
  -> 本地工具提示
  -> Skills 注入
  -> MCP 能力说明
  -> disabled tools 提示

Project Rules
  -> CODE_LAW.md

Runtime Signals
  -> teams runtime block
  -> 恢复提示
  -> 验证反馈
  -> 其他逐轮变化信号
```

前 3 层属于稳定层。`Runtime Signals` 属于动态层。

## 当前实现边界

- `runtime/prompt_builder.py`
  - `ContextBuilder` 仍是运行时入口，但内部已经按 Prompt Assembly 分层。
  - `get_prompt_assembly()` 返回四层消息和各层 fingerprint。
  - `get_system_messages()` 返回 `stable_messages + runtime_signal_messages`，供当前 LLM 接口继续使用。

- `runtime/loop.py`
  - 每次 run 记录 `prompt_assembly` Trace 事件。
  - 事件包含各层 fingerprint，以及相对上一次 run 的 `changed_layers`。

- `tools/registry.py`
  - OpenAI tools schema 统一按工具名稳定排序。
  - 当前模式下的 schema 可输出稳定 fingerprint。

## 指纹规则

- `constitution_fingerprint`
  - 仅反映 L1 宪法内容。
  - 不包含工具说明、MCP、Skills 或 runtime blocks。

- `tool_contracts_fingerprint`
  - 反映本地工具提示、Skills 注入、MCP 说明、disabled tools 列表。
  - 这些内容任一变化，工具契约层指纹都会变化。

- `project_rules_fingerprint`
  - 反映 `CODE_LAW.md` 内容。
  - 不是只看文件存在与否，也不是只看 mtime。

- `runtime_signals_fingerprint`
  - 只反映逐轮动态 block。
  - 变化不会污染 `system_fingerprint`。

- `system_fingerprint`
  - 由 `Constitution + Tool Contracts + Project Rules` 三层组合得到。
  - 稳定层不变时必须保持稳定。

## 不变量

- Runtime Signals 不能进入稳定 system fingerprint。
- 相同 Skills/MCP/disabled tools 内容不能导致稳定层重复失效。
- 相同工具集合必须生成相同 schema 顺序和 fingerprint。
- `CODE_LAW.md` 内容变化必须改变 project/system fingerprint。
- Trace 必须能解释 prompt 变化落在哪一层，而不只是“system prompt 变了”。

## 非目标

- 不接入真实 prompt cache。
- 不做 feature flag 或 A/B 平台。
- 不为不同模型维护复杂兼容矩阵。
