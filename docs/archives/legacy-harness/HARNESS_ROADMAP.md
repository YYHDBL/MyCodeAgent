# MyCodeAgent Harness Roadmap

## 1. 项目目标

MyCodeAgent 是一个用于学习和展示 Agent Harness Engineering 的项目，不以复刻 Claude Code 或建设企业级 Agent 平台为目标。

项目最终需要证明五件事：

1. 能把模型调用组织成可解释、可恢复的 Agent Loop。
2. 能安全、确定地调度工具，而不是让模型直接操作环境。
3. 能把完整历史、长期存储和模型当前视图区分开。
4. 能判断任务是否真正完成，并在失败后有限恢复。
5. 能通过受限子 Agent 展示上下文隔离、能力裁剪和独立验证。

所有后续功能都应服务于这五个目标。不能增强核心论述、无法形成可验证设计、只提升产品体验的功能，不进入主路线。

## 2. 路线启动时的基线

本路线启动时已经完成三项核心骨架：

- Agent Loop 显式状态、转移原因和终止原因。
- ToolOrchestrator 的安全批次、顺序保持和结果预算。
- ContextEngine 的完整历史、非破坏性 compact checkpoint 和读时投影。

当时的主要缺口不在工具数量，而在后三层：

- 完成判定仍由模型单方面决定。
- API 与模型失败恢复路径不完整。
- 权限只具备简单工具级判断。
- Trace 可以记录过程，但还不能系统评价 Harness 效果。
- Session 是快照，不是可持续恢复的事件记录。
- 子 Agent 使用独立的简化循环，没有复用主运行时。

## 3. 总体实施顺序

```text
Phase 0  基线冻结与架构清理
   ↓
Phase 1  Prompt Assembly 与缓存稳定性
   ↓
Phase 2  Completion Gate 与验证协议
   ↓
Phase 3  Model Recovery 与有限韧性
   ↓
Phase 4  Permission Core 与信任边界
   ↓
Phase 5  Eval Harness 收口与可观测性
   ↓
Phase 6A Transcript 与 Resume
   ↓
Phase 6B Session Memory
   ↓
Phase 7  Subagent Runtime 与受限多 Agent
   ↓
Phase 8  Long-term Memory 最小闭环
   ↓
Phase 9  求职材料与架构收口
```

完成 Phase 0-6B 后，单 Agent Harness Core 基本完成。Phase 7-8 用于展示多 Agent 和长期记忆能力，但不能反过来破坏单 Agent 核心。

### 里程碑

- **Milestone A：可信单 Agent**。完成 Phase 0-2，解决架构边界、提示词稳定性和可靠结束问题。
- **Milestone B：可恢复单 Agent**。完成 Phase 3-5，补齐恢复、权限和评估闭环。
- **Milestone C：可持续长任务**。完成 Phase 6A-6B，具备 transcript、resume 和 session memory。
- **Milestone D：受限扩展能力**。完成 Phase 7-8，用统一运行时承载子 Agent 和长期记忆。
- **Milestone E：求职交付**。完成 Phase 9，形成演示、数据和完整技术叙述。

每个 Milestone 完成后都应暂停增加功能，先检查架构、测试、Trace 和文档是否能够共同证明目标已经达成。

## 4. Phase 0：基线冻结与架构清理

状态：已完成基线冻结与架构清理实现，当前主运行时边界、核心 Trace 事件协议和 mock 基线场景已固定；真实模型场景保持独立人工回归。

### 目标

明确现有三层骨架的稳定边界，为后续功能提供唯一扩展点，避免继续在 `runtime/loop.py` 中堆积条件分支。

### 范围

- 固化 Agent Loop、ToolOrchestrator、ContextEngine 的职责与不变量。
- 清理文档与实际代码之间的差异。
- 标记实验性 Teams 与主运行时的边界。
- 固定 Trace 事件协议，避免后续阶段随意改变核心事件语义。
- 建立 5-8 个端到端基线场景，记录当前步骤数、工具调用、上下文消耗和终止原因。
- 将 mock LLM 的确定性机制测试与真实模型的行为评估分开。

### 不做

- 不重写现有三层。
- 不引入工作流框架或图执行框架。
- 不处理纯 UI 和 CLI 体验。

### 验收

- 主 Agent 只有一个正式循环入口。
- 三个核心模块的职责可以通过架构图解释。
- 后续功能能够明确归属到某一层，而不是新增全局状态。
- 基线场景可以重复运行，并保留改造前的 Trace 和指标。

### 面试价值

能够说明项目从普通 ReAct Loop 演进为 Harness Runtime 的过程，以及为什么状态、工具和上下文必须分层。

## 5. Phase 1：Prompt Assembly 与缓存稳定性

状态：已完成 Prompt Assembly 分层、`CODE_LAW.md` 内容感知刷新、Skills/MCP/disabled tools 稳定指纹，以及工具 schema 稳定 fingerprint；未接入真实 prompt cache。

### 目标

建立明确的提示词控制面，使稳定指令、工具能力、项目规则和动态运行时信息拥有不同生命周期。

### 核心设计

提示词分为四类：

```text
Constitution       稳定的 Agent 行为原则
Tool Contracts     跟随具体工具的使用约束
Project Rules      CODE_LAW 等项目级指令
Runtime Signals    当前步骤、恢复提示、验证反馈等动态信息
```

稳定层在会话内保持不可变；动态信号通过独立消息进入模型视图，不反复重建稳定前缀。Prompt Assembly 应成为集中入口，同时记录 system、tools 和 project rules 的指纹。

### 范围

- 修正 CODE_LAW 内容变化与缓存失效关系。
- Skills、MCP 和临时禁用工具只在实际变化时更新。
- 工具 Schema 在工具集合不变时保持稳定。
- 动态 Teams/恢复/验证通知不进入稳定宪法。
- 使用 hash 解释提示词或工具列表为何发生变化。

### 不做

- 不建设 Claude Code 级 Prompt Cache 遥测系统。
- 不做 Feature Flag 和 A/B 测试平台。
- 不为每个模型维护复杂兼容矩阵。

### 验收

- 连续两轮无配置变化时，稳定提示词和工具 Schema 指纹一致。
- 任一动态信息变化不会隐式污染稳定层。
- 能从 Trace 中解释一次提示词变化的来源。

### 面试价值

可以讲清“提示词是控制面”“稳定宪法与运行时信号分离”以及缓存约束如何反过来影响架构。

## 6. Phase 2：Completion Gate 与验证协议

状态：已完成 `CompletionCandidate / CompletionRequirements / VerificationEvidence / DeterministicCompletionVerifier` 接入；final response 不再直接 terminal，当前默认不启动独立 Verification Agent。

### 目标

把“模型说完成了”改造成“运行时允许任务完成”，建立项目最重要的可靠结束机制。

### 核心设计

模型产生 final response 后，先生成完成候选，再经过 Completion Gate：

```text
model final candidate
  → completion requirements
  → deterministic checks
  → verification evidence
  → optional verifier
  → pass / block / unable-to-verify
  → terminal or continue
```

`CompletionRequirements` 描述本次任务允许完成前必须满足的条件，例如是否要求测试、是否允许无法验证、是否存在必须完成的 Todo。`VerificationEvidence` 记录由哪次工具调用、命令结果或状态检查证明某项要求已经满足，并标记证据是否仍然有效。

确定性检查只负责代码可以可靠判断的事实，例如未完成 Todo、要求的验证没有有效证据、存在阻塞状态。该阶段先定义统一验证协议和扩展接口；真正独立运行的 Verification Agent 在 Phase 7 接入，避免当前阶段提前引入第二套 Agent Runtime。

### 范围

- 定义完成候选、阻塞原因和验证结果协议。
- 定义轻量的 `CompletionRequirements`，明确本轮任务的完成条件。
- 定义 `VerificationEvidence`，将验证要求与实际工具执行证据关联。
- Completion Gate 最多允许有限次数阻塞重试。
- 阻塞反馈作为新的状态转移进入下一轮。
- 支持 `PASS`、`FAIL`、`UNVERIFIED`，不能把无法验证伪装成成功。
- 第一版只实现确定性检查、验证记录和可插拔验证接口。

### 不做

- 不做通用形式化证明。
- 不让验证 Agent 自动修改代码。
- 不实现开放式、无限自我反思循环。

### 验收

- 没有工具调用不再等同于任务完成。
- 未执行用户明确要求的验证，或验证证据已经失效时，系统不会直接标记成功。
- Completion Gate 不依赖模型在最终文本中自述“已经测试”作为验证证据。
- Completion Gate 失败不会形成无限循环。
- Trace 可以解释任务为何完成或为何继续。

### 面试价值

这是区分 Demo Agent 和生产型 Harness 的关键案例：模型负责提出完成声明，系统负责批准完成。

## 7. Phase 3：Model Recovery 与有限韧性

### 目标

让 Agent 面对常见 API、上下文和输出失败时能够恢复，同时保证每种恢复都有预算和熔断。

### 核心设计

错误按发生阶段和可恢复性分类：

```text
transport/API error
rate limit/overload
empty response
max output truncation
prompt too long
invalid tool response
unrecoverable model error
```

每类错误只允许进入合法恢复路径。恢复必须产生显式 transition reason，并有独立计数上限。

### 范围

- API 临时错误的有限重试与退避。
- `max_output_tokens` 的短指令续写。
- `prompt_too_long` 先尝试 ContextEngine reactive compact。
- 空响应保留当前单次恢复策略，并纳入统一错误分类。
- 连续恢复失败后进入明确终止状态。

### 不做

- 第一版不做跨模型 fallback。
- 不做流式 tombstone 和 StreamingToolExecutor。
- 不隐藏最终无法恢复的错误。

### 验收

- 所有自动重试都有明确上限。
- 不同阶段的错误不会进入错误的后处理流程。
- 失败恢复后消息、工具调用和历史仍保持合法配对。
- 能测试并复现每一种恢复转移。

### 面试价值

可以展示 Agent Loop 是“面向失败恢复的状态机”，并说明错误阶段语义、有限重试和 death spiral 防护。

## 8. Phase 4：Permission Core 与信任边界

### 目标

把当前基于工具名称的布尔判断升级为输入级权限决策，证明模型只能提出动作请求，Harness 才拥有最终执行权。

### 核心设计

权限决策至少包含：

```text
tool + normalized input + runtime mode
  → risk classification
  → allow / deny / ask
  → execution or explicit rejection
```

判断应结合具体输入，而不是简单规定某个工具永远安全或危险。用户明确拒绝和项目规则具有最高优先级；未知工具、解析失败和无法判断的操作默认关闭。

Permission Core 是 Harness 的策略和交互边界，不是 OS 级安全沙箱。尤其是 Bash 的命令分类只能用于风险路由和是否询问用户，不能承诺识别所有 Shell 绕过方式，也不能替代进程、网络和文件系统隔离。

### 范围

- 区分只读、文件修改、命令执行和外部访问。
- 为 Bash 建立少量明确的危险模式和只读模式。
- 权限结果和原因进入 Trace。
- 子 Agent 可以通过独立策略获得更小能力面。
- 权限拒绝作为正常工具结果返回，不破坏整个 Agent Loop。

### 不做

- 不做模型驱动的 YOLO 安全分类器。
- 不实现完整 OS 容器沙箱。
- 不设计复杂的组织级策略语言。
- 不追求识别所有可能的 Shell 绕过方式。

### 验收

- 权限判断能够访问规范化后的工具输入。
- 未知或判断失败的动作默认拒绝或询问。
- 用户显式禁止不能被其他自动规则覆盖。
- 相同动作在主 Agent 和只读子 Agent 中可以得到不同决策。

### 面试价值

可以讲清纵深防御、失败关闭、渐进式自主，以及为什么权限系统必须位于模型与工具之间。

## 9. Phase 5：Eval Harness 收口与可观测性

### 目标

在 Phase 0 基线场景和 Trace 协议之上，从“测试代码是否运行”提升到“评价 Harness 是否让 Agent 工作得更可靠”，形成可重复的对比方法。

### 核心设计

保留现有 JSONL Trace，将其扩展为本地评估数据源。重点记录：

- 每轮状态转移和终止原因。
- API 调用次数、token、耗时和错误类型。
- 工具调用、工具失败、结果大小和截断情况。
- compact 次数、投影模式和上下文估算。
- Completion Gate 阻塞次数和最终验证结果。
- prompt、tools 和 project rules 指纹。

扩展 Phase 0 的固定场景集，不追求大规模 benchmark。场景应覆盖搜索、修改、验证、工具失败、上下文压缩和恢复；子 Agent 场景在 Phase 7 完成后补入。

### 范围

- 定义少量稳定的 Harness 指标。
- 扩展和版本化 Phase 0 建立的场景测试。
- 支持改造前后结果对比。
- Trace 默认本地保存并执行敏感内容清理。

### 不做

- 不接入 Datadog、OpenTelemetry Collector 或远程数据湖。
- 不建设 Web Dashboard。
- 不追求模型回答质量的单一自动评分。

### 验收

- 每个核心机制至少有一个场景可以证明其生效。
- 一次失败可以沿 Trace 定位到上下文、模型、工具或完成判定阶段。
- 后续优化能够回答“成功率、成本或步骤数是否改善”。

### 面试价值

能够说明为什么 Agent 工程不能只依赖单元测试，以及如何用轨迹和场景评估 Harness 行为。

## 10A. Phase 6A：Transcript 与 Resume

### 目标

建立长任务的事实记录和崩溃恢复基础，使运行时可以从一致边界继续工作。

### 核心设计

```text
Transcript       append-only 事实事件
Runtime State    可恢复的当前执行状态
Model View       按本轮预算投影出的消息
```

Transcript 是恢复事实源，Runtime State 记录最近一致状态，Model View 仍由 ContextEngine 在读时生成。三者不能混为一份 messages 数组。

恢复语义采用 at-least-once 事实记录，而不是承诺外部工具副作用 exactly-once。对于中断时仍处于执行中的工具调用，恢复后标记为 `uncertain`，由运行时重新检查或请求用户确认，不能假定成功，也不能直接重复执行。

### 范围

- 每条重要消息和状态转移追加写入 JSONL。
- 支持从最后一个一致检查点恢复会话。
- 保存动作采用原子写入或可检测的不完整记录。
- 工具调用记录 `requested / started / completed / failed / uncertain` 生命周期。
- 恢复时不自动重复执行状态为 `started` 或 `uncertain` 的副作用工具。

### 不做

- 不做分布式 durable execution。
- 不保证任意工具副作用自动回滚。
- 不承诺跨进程和外部系统副作用的 exactly-once。
- 不做自动跨项目知识学习。

### 验收

- 进程中断后能够恢复到可继续工作的状态。
- 已记录为 `completed` 的工具结果不会被运行时自动再次提交。
- 中断时状态不确定的副作用工具会被显式标记，不会静默重放。
- Transcript、Runtime State 和 Model View 的职责清晰可测试。

### 面试价值

可以说明 append-only transcript、检查点和恢复语义，以及为什么 Agent Resume 不能简单等同于重新加载 messages。

## 10B. Phase 6B：Session Memory

### 目标

在可靠 Transcript 和 Resume 之上建立结构化工作摘要，使长任务经过 compact 或恢复后仍能保留目标、进度和关键决策。

### 核心设计

```text
Transcript       完整事实源
Session Memory   目标、进度、决策、失败尝试、待办和验证状态
Model View       Session Memory + 按预算投影的近期历史
```

Session Memory 是可重建、可版本化的会话级派生状态，不替代 Transcript，也不直接充当永久记忆。更新必须能追溯到 Transcript 中的来源事件。

### 范围

- 保存任务目标、已完成工作、关键决策、失败方法、待办和验证状态。
- compact 和 resume 后优先恢复 Session Memory 的关键字段。
- 每次更新记录来源事件范围和版本。
- 摘要生成失败时保留上一份有效版本，不破坏 Transcript。

### 不做

- 不跨项目共享 Session Memory。
- 不允许 Session Memory 成为唯一事实来源。
- 不在本阶段自动写入 Long-term Memory。

### 验收

- compact 不会让模型遗忘任务目标、关键决策和失败尝试。
- Session Memory 可以从 Transcript 重建或校验。
- 摘要失败不会导致已经记录的事实丢失。
- Transcript、Session Memory 和 Model View 的职责清晰可测试。

### 面试价值

可以系统回答 Working Memory、Transcript、Session Memory 和 Long-term Memory 的区别，以及为什么记忆首先是数据生命周期问题。

## 11. Phase 7：Subagent Runtime 与受限多 Agent

状态：已完成。Explore 与 Verification 使用统一 `RuntimeRunner`；旧
`SubagentRunner` 和正式 Task 对 `experimental.teams.TurnExecutor` 的依赖已删除。

### 目标

使用最小多 Agent 设计展示上下文隔离、能力裁剪和独立验证，而不是构建复杂协作平台。

### 核心设计

子 Agent 不再维护第二套 ReAct Loop，而是复用主 RuntimeRunner，通过配置决定：

```text
context source
system prompt
tool allowlist
step/token budget
model choice
completion policy
result contract
```

正式支持两类子 Agent：

- Explore Agent：只读搜索，隔离探索噪音，返回带文件证据的结论。
- Verification Agent：独立检查主 Agent 产物，返回结构化 verdict。

### 范围

- 主、子 Agent 共用状态机、上下文和工具执行基础设施。
- 子 Agent 使用独立历史和更小上下文。
- 父 Agent 只接收结构化摘要，不继承全部子 Agent 过程。
- 子 Agent 默认禁止写入、Bash 和递归 Task。
- 记录父子 Trace 关系和预算使用。

### 不做

- 不继续建设 tmux、多邮箱和远程 worker。
- 不做 Coordinator Mode 和自动 DAG 规划。
- 不默认并行执行有副作用的 Agent。

### 验收

- 不再存在独立维护的第二套正式 Agent Loop。
- Explore Agent 的搜索噪音不会进入父上下文。
- Verification Agent 无法修改被验证代码。
- 子 Agent 失败不会直接破坏父 Agent 会话。
- Task 不提供 persistent/parallel 正式模式。
- Eval 可统计 child invocation、tool、token、failure 和 verification verdict。

### 面试价值

能够讨论多 Agent 的真正问题：上下文隔离、能力边界、共享状态、成本和结果合并，而不只是“启动多个模型”。

## 12. Phase 8：Long-term Memory 最小闭环

状态：已完成 MVP。实际实现采用有界 `§` 分隔条目列表、`MEMORY.md/USER.md`
分离、显式 `Memory` CRUD、frozen snapshot、原子写入与轻量安全检查。
原计划中的逐条 metadata schema、相关性检索和持久化冲突状态未进入 MVP。

### 目标

实现可控、可追溯的跨会话记忆，展示显式写入、删除、预算和注入，而不是堆叠向量数据库。

### 核心设计

Long-term Memory 只保存跨会话仍然有价值的结构化事实，例如：

- 用户明确偏好。
- 项目稳定约束。
- 已确认的架构决策。
- 可复用的失败经验。

实际 MVP 以文件路径和 target 作为来源/作用域边界，不为每个条目维护独立时间和失效字段。冻结快照进入动态上下文，而不是修改稳定系统提示词。

### 范围

- 用户显式写入和删除记忆。
- 项目级与用户级作用域。
- `add / replace / remove / list` 显式管理。
- 项目与用户文件独立预算和来源标记。
- 当前用户指令优先于注入的长期记忆。

### 不做

- 第一版不使用向量数据库。
- 不允许模型静默写入永久记忆。
- 不做自动自我改写和无限记忆合并。

### 验收

- 长期记忆可按 target 和匹配文本查看、替换或删除。
- 记忆冲突时以用户最新明确指令为准。
- 记忆不会超过各自字符预算进入上下文。
- 关闭长期记忆后不影响 Agent 核心运行。

### 面试价值

可以说明记忆系统的难点不是 embedding，而是写入策略、作用域、冲突、失效、预算和可信度。

## 13. Phase 9：求职材料与架构收口

状态：已完成。README、四个模块设计页、四个确定性 Demo、关键 Trace、
普通 ReAct 对照实验和项目边界说明已收口；项目进入维护状态。

### 目标

把项目从“代码仓库”整理成“能够被面试官快速理解并深入追问的工程案例”。

### 范围

- README 使用一张总架构图说明六层 Harness。
- 为四个重点模块分别提供设计说明：Agent Loop、Tool Harness、Context Engineering、Memory/Subagent。
- 每个重点模块准备一个可运行演示和一条关键 Trace。
- 准备与普通 ReAct Agent 的对照实验。
- 记录明确取舍：做了什么、没做什么、为什么。
- 整理核心测试数量、典型故障场景和性能数据。

### 验收

项目应能支持一套完整叙述：

1. 最初的问题是什么。
2. 普通实现为什么不够。
3. Harness 如何分层。
4. 每层有哪些关键不变量。
5. 如何处理失败和长任务。
6. 如何通过测试和 Trace 证明有效。
7. 为什么没有完整复刻 Claude Code。

## 14. 学习深度分级

### 必须深入实现

- Agent Loop 状态转移与完成判定。
- ToolOrchestrator 和工具执行边界。
- ContextEngine、预算、compact 和 read-time projection。
- Model Recovery 和有限重试。
- Transcript、Resume 和 Session Memory。

这些内容是项目的核心竞争力，必须能够从源码、测试和 Trace 三个角度讲解。

### 最小实现并深入理解

- Prompt Cache 稳定性。
- Permission Core。
- Explore Agent 与 Verification Agent。
- Long-term Memory。

这些内容需要有可运行实现，但不追求 Claude Code 的完整规模。

### 只做原理研究

- StreamingToolExecutor。
- 跨模型 fallback 状态重建。
- 完整沙箱与安全分类器。
- Coordinator、Teams、Ultraplan。
- Feature Flag 和 A/B 平台。
- 插件市场和远程遥测。

这些内容可以在面试中讨论设计和取舍，但不应消耗当前项目的主要开发时间。

## 15. 分级完成标准

### Harness Core Done

完成 Phase 0-6B 后，单 Agent Harness Core 进入维护状态：

- 单 Agent 可以在多轮工具任务中稳定运行并解释每次转移。
- 模型不能绕过 Completion Gate 自行宣布完成。
- 常见模型/API/上下文错误有有限恢复路径。
- 上下文压缩不破坏完整历史，并能保留任务关键状态。
- 会话可以持久化、恢复并继续执行。
- 所有单 Agent 核心机制均有固定场景、自动测试和可读 Trace。

### Extension Done

完成 Phase 7-8 后，扩展能力进入维护状态：

- Explore 和 Verification 两类子 Agent 复用统一运行时。
- 长期记忆具备来源、预算、冲突和删除机制。

### Portfolio Done

完成 Phase 9 后，项目达到求职交付标准：

- README 和设计文档可以在十分钟内让面试官理解项目价值。
- 每个重点机制都有可运行演示、关键 Trace 和明确取舍。

当前状态：已达到 Portfolio Done。

达到 Harness Core Done 后，不再为单 Agent 主路线随意增加功能；达到 Portfolio Done 后，项目整体不再以新增 Agent 功能为目标。后续工作只围绕缺陷修复、评估改进和材料完善。
