# Harness Task Breakdown

本文档把 `docs/HARNESS_ROADMAP.md` 拆成可执行子任务。它不是代码级实施计划，不包含完整代码；每个任务应能独立交给一个 agent 执行，并在完成后通过测试、Trace 或文档验收。

## 执行原则

- 每个任务只改一个清晰边界，不跨阶段偷做后续功能。
- 每个任务完成后都要更新相关测试或 Trace 断言。
- 每个 Phase 完成后先暂停，检查架构、测试、文档和演示是否能证明该阶段目标。
- 不为模仿 Claude Code 增加复杂度；只实现能支撑学习和展示的 harness 能力。
- `experimental/teams/` 在 Phase 7 前保持实验边界，不进入主运行时。

## Phase 0：基线冻结与架构清理

执行备注（2026-06-08）：

- `RuntimeRunner` 维持唯一正式单 Agent loop；`CodeAgent._react_loop()` 仅为兼容委托。
- `TaskTool` 与 `experimental/teams/` 只做实验边界标记，未纳入主运行时。
- 核心 Trace 协议冻结在 `docs/HARNESS_TRACE_PROTOCOL.md` 与 `extensions/tracing/protocol.py`。
- 基线场景固定在 `tests/scenarios/`；真实模型场景不进入默认 `pytest`。

### P0-T1：确认主运行时边界

**目标**：确认单 Agent 正式入口只有 `RuntimeRunner`，避免后续继续在多个循环里扩散逻辑。

**范围**：
- 梳理 `runtime/loop.py`、`runtime/host.py`、`tools/builtin/task.py`、`experimental/teams/` 的调用关系。
- 在文档中标明哪些是正式运行时，哪些是实验或兼容路径。
- 不删除现有实验功能。

**输出**：
- 更新 `docs/HARNESS.md` 或补充架构说明。
- 一张主运行时调用链。

**验收**：
- 能说明主 Agent 从用户输入到终止只经过一个正式 loop。
- 后续 Phase 能明确应改 `RuntimeRunner` 还是扩展模块。

### P0-T2：冻结 Trace 核心事件协议

**目标**：确定后续评估依赖的最小 Trace 事件集合。

**范围**：
- 定义核心事件：`run_start`、`context_build`、`model_output`、`state_transition`、`tool_call`、`tool_result`、`terminal`、`run_end`。
- 记录每类事件必须包含的字段。
- 不做完整 observability 平台。

**输出**：
- 新增或更新 Trace 协议文档。
- 对现有 `TraceLogger` 行为做测试覆盖。

**验收**：
- 后续阶段新增事件不能破坏核心事件字段。
- 一次运行可以从 Trace 复盘状态转移和终止原因。

### P0-T3：建立基线场景集

**目标**：准备 5-8 个可重复运行的 harness 场景，作为后续改造对照。

**范围**：
- 场景覆盖：只读搜索、文件修改、工具失败、上下文压缩、空响应恢复、最大步数终止。
- mock LLM 场景和真实模型场景分开。
- 暂不覆盖子 Agent。

**输出**：
- `tests/scenarios/` 或等价目录下的场景说明与测试入口。
- 基线指标：步数、工具数、上下文投影模式、终止原因。

**验收**：
- 场景能重复运行。
- 每个场景有明确预期，而不是只看“没有报错”。

### P0-T4：清理路线文档一致性

**目标**：让 README、HARNESS、ROADMAP 和任务拆分表达一致。

**范围**：
- 确认已完成能力、暂不实现能力、后续阶段顺序。
- 清理过期文档引用。

**输出**：
- 文档更新。

**验收**：
- 新 agent 阅读 README、HARNESS、ROADMAP、TASK_BREAKDOWN 后不会得到互相冲突的路线。

## Phase 1：Prompt Assembly 与缓存稳定性

执行备注（2026-06-08）：

- `ContextBuilder` 保留运行时 facade，但内部已按 `Constitution / Tool Contracts / Project Rules / Runtime Signals` 分层。
- `Runtime Signals` 仍通过 system messages 进入当前模型接口，但不进入稳定 `system_fingerprint`。
- `CODE_LAW.md` 改为按内容感知刷新，不再依赖“存在性”或外部手动失效。
- OpenAI tools schema 已稳定排序，并可输出 fingerprint 供 Trace 与 session 对比。

### P1-T1：引入 Prompt Assembly 分层模型

**目标**：把稳定宪法、工具契约、项目规则和运行时信号拆成明确生命周期。

**范围**：
- 设计 `Constitution`、`Tool Contracts`、`Project Rules`、`Runtime Signals` 四类输入。
- 明确哪些内容可以缓存，哪些只能动态注入。
- 不接入真实 prompt cache。

**输出**：
- Prompt Assembly 设计文档。
- 对应的数据结构或构建入口。

**验收**：
- 不再把动态 Teams、恢复提示、验证反馈混入稳定系统提示词。
- 能输出每层内容的 hash 或 fingerprint。

### P1-T2：修正 CODE_LAW 变化检测

**目标**：确保项目规则内容变化时，系统提示词缓存正确失效。

**范围**：
- 修正只检查 CODE_LAW 是否存在、不检查内容变化的问题。
- 增加 mtime/hash 断言。

**输出**：
- `ContextBuilder` 或新的 Prompt Assembly 测试。

**验收**：
- CODE_LAW 内容变化后 system fingerprint 变化。
- CODE_LAW 未变化时连续构建 fingerprint 稳定。

### P1-T3：稳定 Skills/MCP/Disabled Tools 注入

**目标**：只在实际变化时更新动态能力说明，避免每轮无意义清空稳定前缀。

**范围**：
- Skills prompt、MCP prompt、disabled tools 分别计算 fingerprint。
- 没变化时不重建稳定 prompt。
- Runtime Signals 使用动态消息或模型视图附加层。

**输出**：
- Prompt 稳定性测试。
- Trace 中记录变化来源。

**验收**：
- 连续两轮无配置变化时 system/tool fingerprint 不变。
- Skills 文件未变化时不会导致 system cache 重建。

### P1-T4：稳定工具 Schema 构建

**目标**：工具集合不变时工具 schema 保持稳定，便于后续缓存和 Trace 对比。

**范围**：
- 为工具 schema 增加排序、hash 和变化原因记录。
- 不重写工具注册系统。

**输出**：
- 工具 schema fingerprint。
- schema 稳定性测试。

**验收**：
- 同一工具集合多次构建 hash 一致。
- 工具增删或描述变化时能解释变化来源。

## Phase 2：Completion Gate 与验证协议

执行备注（2026-06-08）：

- `RuntimeRunner` final 分支已先产出 `CompletionCandidate`，再交给 `runtime/completion.py` 判定。
- `CompletionRequirements` 当前只处理显式验证要求、可选 `UNVERIFIED` 和最新 `TodoWrite` 未完成项。
- `VerificationEvidence` 当前只从实际工具执行中提取，模型文本自述不算证据。
- 验证后发生 `Write` / `Edit` / `MultiEdit` 会使旧证据失效。
- Gate 阻塞通过 `STOP_HOOK_BLOCKING` 转移进入下一轮，超过上限后以 `completion_gate_blocked` 终止。
- verifier 接口已预留，默认仍是确定性实现，不启动第二个 Agent。

### P2-T1：定义完成候选协议

**目标**：模型 final response 先变成完成候选，而不是直接 terminal。

**范围**：
- 定义 `CompletionCandidate`，包含 final text、step、response meta、最近工具状态。
- RuntimeRunner final 分支接入候选对象。

**输出**：
- 完成候选数据结构。
- final 分支测试。

**验收**：
- 没有工具调用不再直接等价于完成。
- Trace 能记录 final candidate。

### P2-T2：定义 CompletionRequirements

**目标**：让运行时知道本轮任务完成前必须满足什么。

**范围**：
- 支持最小要求：是否需要验证、是否允许 unverifiable、是否存在必须完成 Todo、是否存在用户显式约束。
- 初版可由输入预处理、Todo 状态和运行时显式记录生成。
- 不做复杂自然语言需求抽取。

**输出**：
- `CompletionRequirements` 数据结构。
- 基础生成逻辑。

**验收**：
- 用户明确要求“运行测试”时，requirements 能表达需要验证。
- 无明确验证要求的简单问答不会被过度阻塞。

### P2-T3：定义 VerificationEvidence

**目标**：用实际工具调用证据支撑完成判定，而不是相信模型自述。

**范围**：
- 记录验证命令、工具名、结果状态、产生 step、关联 requirement。
- 支持 evidence 失效标记，例如验证后又发生文件修改。

**输出**：
- Evidence 记录接口。
- Bash/工具结果到 evidence 的最小映射。

**验收**：
- 模型最终文本说“测试通过”但没有工具证据时不能通过要求。
- 修改文件后，旧验证证据可被标记失效。

### P2-T4：实现确定性 Completion Gate

**目标**：完成前执行确定性检查，并返回 `PASS / FAIL / UNVERIFIED`。

**范围**：
- 检查未完成 Todo、最后工具失败、缺少验证证据、证据失效。
- Gate 阻塞时生成反馈消息进入下一轮。
- 设置阻塞重试上限。

**输出**：
- Completion Gate 模块。
- RuntimeRunner 接入。

**验收**：
- Gate block 不会无限循环。
- Trace 能说明任务为什么完成或继续。

### P2-T5：预留可插拔 verifier 接口

**目标**：为 Phase 7 的 Verification Agent 留出接口，但不提前实现独立子 Agent。

**范围**：
- 定义 verifier 输入输出协议。
- 默认 verifier 只返回 deterministic gate 结果。

**输出**：
- verifier interface。

**验收**：
- Phase 2 不引入第二套 Agent Runtime。
- Phase 7 可以在不改 Completion Gate 主流程的情况下接入 Verification Agent。

## Phase 3：Model Recovery 与有限韧性

### P3-T1：建立模型错误分类

**目标**：把空响应、API 错误、prompt too long、max output 等错误按阶段分类。

**范围**：
- 定义错误类型、发生阶段、可恢复性。
- 统一当前空响应恢复逻辑。

**输出**：
- Model error classifier。
- 错误分类测试。

**验收**：
- 不同错误不会进入错误的恢复路径。
- Trace 记录 error type 和 stage。

### P3-T2：API 临时错误有限重试

**目标**：处理 transport、rate limit、overload 等临时错误。

**范围**：
- 增加有限 retry、退避、最大次数。
- 每次 retry 记录 transition 或 retry event。
- 不做跨模型 fallback。

**输出**：
- LLM invoke wrapper 或 RuntimeRunner 调用层恢复逻辑。

**验收**：
- 临时错误可恢复。
- 超过上限后明确 terminal。

### P3-T3：max output 续写恢复

**目标**：模型输出被截断时有限续写。

**范围**：
- 识别 max output finish reason。
- 注入短硬提示：继续、不要道歉、不要回顾。
- 最多重试固定次数。

**输出**：
- max output recovery flow。

**验收**：
- 续写不会无限循环。
- 续写后的消息历史仍合法。

### P3-T4：prompt too long reactive compact

**目标**：请求过长时优先使用 ContextEngine 做 reactive compact。

**范围**：
- 识别 prompt too long。
- 调用 ContextEngine 压缩并重建 model view。
- 避免在无有效模型响应时运行 Completion Gate。

**输出**：
- reactive compact 转移。

**验收**：
- prompt too long 后不会直接失败。
- compact 失败后明确 terminal，不进入 death spiral。

### P3-T5：恢复状态与计数收口

**目标**：所有恢复路径都进入 LoopState，而不是散落布尔变量。

**范围**：
- 将 recovery count、last error、transition reason 纳入状态。
- 为恢复上限写测试。

**输出**：
- LoopState 字段更新。
- recovery trace 事件。

**验收**：
- 每个 continue 都有可解释 transition reason。
- 能测试每种恢复转移。

## Phase 4：Permission Core 与信任边界

### P4-T1：定义权限决策协议

**目标**：把 `tool_name -> bool` 升级为 `tool + input + mode -> decision`。

**范围**：
- 定义 `allow / deny / ask`。
- 记录 reason、risk level、policy source。
- 不实现完整用户交互 UI。

**输出**：
- PermissionDecision 数据结构。
- ToolExecutor 接入点。

**验收**：
- 权限判断可以访问规范化工具输入。
- 权限拒绝作为正常工具结果返回。

### P4-T2：实现基础风险分类

**目标**：区分只读、文件修改、命令执行和外部访问。

**范围**：
- Read/Grep/Glob/ListFiles 默认只读。
- Write/Edit/MultiEdit 属于文件修改。
- Bash 按输入命令做有限分类。
- 未知工具 fail closed。

**输出**：
- Risk classifier。

**验收**：
- 解析失败或未知工具不会默认允许。
- 同一工具可因输入不同得到不同风险结果。

### P4-T3：Bash 最小权限规则

**目标**：为 Bash 建立学习型 MVP 的风险路由，不承诺安全沙箱。

**范围**：
- 识别少量只读命令和少量危险模式。
- 记录分类原因。
- 明确不能识别所有 shell 绕过。

**输出**：
- Bash permission policy。
- 测试覆盖典型 allow/deny/ask。

**验收**：
- `ls`、`cat`、`git status` 可被判为低风险。
- `rm`、重定向写入、破坏性 git 操作被拒绝或询问。

### P4-T4：主 Agent 与只读子 Agent 策略分离

**目标**：同一动作在不同 agent mode 下可得到不同权限结果。

**范围**：
- 定义 runtime mode。
- 只读模式禁止写入、Bash、递归 Task。

**输出**：
- permission policy by mode。

**验收**：
- 主 Agent 可允许的写入动作，在只读子 Agent 中拒绝。

### P4-T5：权限 Trace 与测试

**目标**：权限决策可审计。

**范围**：
- Trace 记录 tool、input summary、decision、reason。
- 敏感内容清理。

**输出**：
- permission trace event。
- 权限测试集。

**验收**：
- 可以从 Trace 解释一个工具为什么被允许或拒绝。

## Phase 5：Eval Harness 收口与可观测性

### P5-T1：定义 Harness 指标

**目标**：统一衡量 harness 行为，而不是只看测试通过。

**范围**：
- 指标包括成功率、步骤数、工具数、恢复次数、Gate block 次数、上下文压缩次数、token 用量。
- 不做自动模型质量评分。

**输出**：
- metrics schema。

**验收**：
- 每次场景运行能产出指标摘要。

### P5-T2：扩展场景 runner

**目标**：让 Phase 0 场景可以批量运行和对比。

**范围**：
- 支持 mock LLM 确定性场景。
- 支持真实模型手动或可选运行。
- 输出 JSON summary。

**输出**：
- scenario runner。

**验收**：
- 改造前后可对比步骤、工具、终止原因。

### P5-T3：Trace 汇总器

**目标**：从 JSONL Trace 中提取指标和失败阶段。

**范围**：
- 解析状态转移、terminal、tool、context、recovery、gate 事件。
- 输出简洁报告。

**输出**：
- trace summary CLI 或测试工具。

**验收**：
- 一次失败能定位到 context、model、tool、permission、completion gate 中的某个阶段。

### P5-T4：评估文档与报告样例

**目标**：让评估结果可展示。

**范围**：
- 写一份典型场景报告。
- 说明指标含义和限制。

**输出**：
- `docs/evals/` 下的报告样例。

**验收**：
- 面试时能展示“为什么这个机制有效”的数据证据。

## Phase 6A：Transcript 与 Resume

### P6A-T1：定义 append-only transcript schema

**目标**：让每条重要事实事件可持久化。

**范围**：
- 事件类型包括 message、state_transition、tool_lifecycle、terminal、checkpoint。
- 每条事件包含 id、timestamp、run id、step、parent/reference。

**输出**：
- transcript schema。
- schema 测试。

**验收**：
- transcript 可以作为恢复事实源。

### P6A-T2：实现 transcript writer

**目标**：运行时每条关键事件追加写入 JSONL。

**范围**：
- 原子写入或可检测半条记录。
- 不替代 TraceLogger，Transcript 关注恢复事实，Trace 关注诊断。

**输出**：
- TranscriptStore。

**验收**：
- 进程中断时已有事件不会丢失。

### P6A-T3：工具生命周期记录

**目标**：区分 requested、started、completed、failed、uncertain。

**范围**：
- 工具执行前后写 transcript。
- 恢复时识别未完成工具。

**输出**：
- tool lifecycle events。

**验收**：
- started 但无 completed 的副作用工具恢复后标为 uncertain。
- completed 工具不会被自动再次提交。

### P6A-T4：实现 resume loader

**目标**：从 transcript 恢复到可继续工作的 Runtime State。

**范围**：
- 重建 history、read cache、context runtime state。
- 识别 uncertain actions 并注入恢复提示。

**输出**：
- Resume loader。

**验收**：
- 中断后能恢复到可继续工作状态。
- 不静默重放副作用工具。

### P6A-T5：resume 场景测试

**目标**：证明恢复语义可用。

**范围**：
- 正常 completed 工具恢复。
- started 未完成工具恢复。
- 半条 JSONL 记录处理。

**输出**：
- resume tests。

**验收**：
- at-least-once 事实记录语义清晰，不承诺 exactly-once。

## Phase 6B：Session Memory

### P6B-T1：定义 Session Memory schema

**目标**：保存长任务关键状态。

**范围**：
- 字段包括目标、已完成工作、关键决策、失败尝试、Todo、验证状态、来源事件范围、版本。

**输出**：
- SessionMemory 数据结构。

**验收**：
- 每个字段能追溯到 transcript 来源。

### P6B-T2：Session Memory 更新策略

**目标**：从 transcript 派生和更新工作摘要。

**范围**：
- 初版可用规则提取和有限模型摘要结合。
- 摘要失败保留上一版本。

**输出**：
- memory updater。

**验收**：
- 摘要失败不破坏 transcript 和上一份 memory。

### P6B-T3：ContextEngine 注入 Session Memory

**目标**：模型视图优先看到任务状态，而不是只依赖近期历史。

**范围**：
- Session Memory 作为动态上下文进入 Model View。
- 设置预算和来源标记。

**输出**：
- model view memory projection。

**验收**：
- compact 后模型仍能看到目标、决策和失败尝试。

### P6B-T4：Session Memory 可重建性测试

**目标**：证明 Session Memory 不是唯一事实源。

**范围**：
- 从 transcript 重建或校验 memory。
- 对比版本和来源事件范围。

**输出**：
- memory rebuild tests。

**验收**：
- memory 损坏或缺失时可从 transcript 恢复到合理状态。

## Phase 7：Subagent Runtime 与受限多 Agent

执行备注（2026-06-09）：

- `RuntimeProfile`、`SubagentRequest`、`SubagentResult` 与 `SubagentLauncher`
  位于 `runtime/subagents.py`。
- Explore 与 Verification 都复用 `RuntimeRunner`，并拥有独立 history、context、
  transcript、session memory、trace 和过滤 registry。
- 正式 Task 只支持 Explore，不再支持 general/plan/summary/persistent/parallel。
- Verification 只在 deterministic gate 通过且配置启用、任务要求验证时执行。
- 正式路径不引用 `SubagentRunner` 或 `experimental.teams.TurnExecutor`。

### P7-T1：抽象 RuntimeProfile

**目标**：让主 Agent 和子 Agent 共用 RuntimeRunner，只通过配置改变能力。

**范围**：
- 定义 system prompt、tool allowlist、context source、budget、completion policy、result contract。
- 不做 Teams 和远程 worker。

**输出**：
- RuntimeProfile。

**验收**：
- 子 Agent 不需要第二套正式 ReAct loop。

### P7-T2：重构 Task 子 Agent 到统一运行时

**目标**：删除正式路径里的独立简化循环。

**范围**：
- TaskTool 使用 RuntimeProfile 启动受限运行时。
- 删除旧模式和旧 loop，不保留 legacy wrapper。

**输出**：
- TaskTool runtime integration。

**验收**：
- 不再存在独立维护的正式子 Agent loop。

### P7-T3：实现 Explore Agent

**目标**：隔离只读搜索噪音。

**范围**：
- 只允许 LS/Glob/Grep/Read 等只读工具。
- 输出结构化结论和文件证据。

**输出**：
- Explore profile。

**验收**：
- 父 Agent 只接收摘要，不继承全部探索历史。

### P7-T4：实现 Verification Agent

**目标**：独立检查主 Agent 产物。

**范围**：
- 只读能力。
- 输出 `PASS / FAIL / PARTIAL / UNVERIFIED` 和证据。
- 接入 Completion Gate verifier 接口。

**输出**：
- Verification profile。

**验收**：
- Verification Agent 无法修改代码。
- 失败不会破坏父 Agent 会话。

### P7-T5：父子 Trace 和预算

**目标**：子 Agent 成本和结果可审计。

**范围**：
- 记录 parent run id、child run id、预算、工具使用。

**输出**：
- subagent trace relation。

**验收**：
- 能从 Trace 看出子 Agent 的上下文隔离和能力裁剪。

## Phase 8：Long-term Memory 最小闭环

### P8-T1：定义 Long-term Memory schema

**目标**：保存跨会话仍有价值的结构化事实。

**范围**：
- 字段包括内容、来源、作用域、创建时间、更新时间、状态、冲突信息。

**输出**：
- memory schema。

**验收**：
- 每条记忆可解释来源并可删除。

### P8-T2：显式写入和删除

**目标**：只允许用户明确写入长期记忆。

**范围**：
- 命令或工具接口写入、查看、删除。
- 不允许模型静默写入。

**输出**：
- memory management interface。

**验收**：
- 关闭长期记忆不影响核心运行。

### P8-T3：检索与预算注入

**目标**：相关记忆进入动态上下文，而不是稳定系统提示词。

**范围**：
- 简单关键词或结构化字段检索。
- 注入预算和来源标记。

**输出**：
- memory retriever。

**验收**：
- 无关记忆不会无界进入上下文。

### P8-T4：冲突和失效规则

**目标**：长期记忆不会覆盖用户最新明确指令。

**范围**：
- 用户最新指令优先。
- 支持禁用、过期、冲突提示。

**输出**：
- memory conflict policy。

**验收**：
- 冲突时不会静默采用旧记忆。

## Phase 9：求职材料与架构收口

状态：已完成。实际输出位于 `README.md`、`docs/portfolio/`、`demo/` 和
`docs/traces/`；未新增 Agent Runtime 功能，未修改 `experimental/teams/`。

### P9-T1：总架构 README

**目标**：十分钟内让面试官理解项目价值。

**范围**：
- 一张六层 Harness 架构图。
- 当前能力、核心取舍、运行方式、测试方式。

**输出**：
- README 更新。

**验收**：
- 非项目成员能快速说出项目解决了什么问题。

### P9-T2：四个重点模块说明

**目标**：准备可深入追问的技术材料。

**范围**：
- Agent Loop。
- Tool Harness。
- Context Engineering。
- Memory/Subagent。

**输出**：
- 四份模块设计说明或整合文档。

**验收**：
- 每份说明包含不变量、失败场景、测试和 Trace 示例。

### P9-T3：演示和关键 Trace

**目标**：把功能变成可展示证据。

**范围**：
- 每个重点机制准备一个 demo。
- 每个 demo 配一条关键 Trace。

**输出**：
- demos 或 eval reports。

**验收**：
- 能现场解释每条 Trace 对应的 harness 机制。

### P9-T4：普通 ReAct 对照实验

**目标**：证明不是“普通 agent 加了很多文档”。

**范围**：
- 选择 2-3 个场景，对比普通 ReAct 与 Harness Runtime。
- 对比完成判定、恢复、上下文和工具边界。

**输出**：
- 对照实验报告。

**验收**：
- 能清楚说明普通实现在哪里失败，harness 如何修正。

### P9-T5：项目收口

**目标**：进入维护状态，不再继续堆功能。

**范围**：
- 清理无用实验文档。
- 整理测试数量、场景数量、已知限制。
- 写明不实现 Claude Code 哪些能力以及原因。

**输出**：
- 最终项目说明。

**验收**：
- 项目叙述完整：问题、分层、机制、失败恢复、测试证据、取舍。

## 建议执行批次

### Batch A：可信单 Agent

包含：P0-T1 到 P0-T4、P1-T1 到 P1-T4、P2-T1 到 P2-T5。

完成后应暂停，确认 Completion Gate 已经真正改变终止语义。

### Batch B：可恢复单 Agent

包含：P3-T1 到 P3-T5、P4-T1 到 P4-T5、P5-T1 到 P5-T4。

完成后应暂停，确认失败恢复、权限拒绝和评估指标都可从 Trace 证明。

### Batch C：可持续长任务

包含：P6A-T1 到 P6A-T5、P6B-T1 到 P6B-T4。

完成后应暂停，确认 transcript、resume、session memory 三者没有混成一份 messages 数组。

### Batch D：受限扩展能力

包含：P7-T1 到 P7-T5、P8-T1 到 P8-T4。

完成后应暂停，确认子 Agent 和长期记忆没有破坏单 Agent Core。

### Batch E：求职交付

包含：P9-T1 到 P9-T5。

完成后项目进入材料完善和缺陷修复阶段，不再以新增能力为目标。
