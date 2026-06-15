# Skill Evolution 受控演进框架 — 实现设计文档

**文档版本：** V1.2  
**最后修订：** 2026-06-15  
**说明：** 本文档已拆分为 11 份可执行粒度文档，位于 `docs/skill_evolution/` 下。本文档保留为总索引。

---

## 分文档索引

| 编号 | 文件 | 内容 |
|------|------|------|
| 00 | [`_00_OVERVIEW.md`](skill_evolution/_00_OVERVIEW.md) | 总览、项目结构、状态机、简化策略 |
| 01 | [`_01_TYPES_AND_CONFIG.md`](skill_evolution/_01_TYPES_AND_CONFIG.md) | 所有 Enum、dataclass、EvolutionConfig |
| 02 | [`_02_CORE_UTILS.md`](skill_evolution/_02_CORE_UTILS.md) | Patcher、Store、SkillLoader overlay 扩展 |
| 03 | [`_03_ADAPTER_AND_ROUTER.md`](skill_evolution/_03_ADAPTER_AND_ROUTER.md) | Adapter、FeedbackRouter、TraceLogger 缓冲 |
| 04 | [`_04_HOTFIX_PIPELINE.md`](skill_evolution/_04_HOTFIX_PIPELINE.md) | HotfixGenerator + LLM 终判 |
| 05 | [`_05_EVOLUTION_BUFFER.md`](skill_evolution/_05_EVOLUTION_BUFFER.md) | AbnormalTrajectoryBuffer |
| 06 | [`_06_REVIEW_AGENT.md`](skill_evolution/_06_REVIEW_AGENT.md) | BatchReviewAgent + System Prompt |
| 07 | [`_07_PROPOSAL_AND_OBSERVER.md`](skill_evolution/_07_PROPOSAL_AND_OBSERVER.md) | ProposalManager + CandidateObserver |
| 08 | [`_08_STATE_MACHINE.md`](skill_evolution/_08_STATE_MACHINE.md) | SkillEvolutionManager + 跨重启恢复 |
| 09 | [`_09_INTEGRATION_POINTS.md`](skill_evolution/_09_INTEGRATION_POINTS.md) | 10 个现有文件修改详情 |
| 10 | [`_10_MOCK_SKILL_AND_TESTS.md`](skill_evolution/_10_MOCK_SKILL_AND_TESTS.md) | Mock Skill + 60 个测试用例清单 |

---

以下是原始完整文档（保留供索引）。  
**适用项目：** MyCodeAgent  
**核心思想：** 基于《通用 Agent Skill 受控演进框架 TRD》，针对 MyCodeAgent 做适配性实现

---

## 1. 概述

将 Skill 更新从"单轮即时自修改"改造成两条不同可信度的路径：

```
用户明确纠错或长期要求
→ FeedbackRouter 初筛（长期关键词）
→ HotfixGenerator LLM 终判（过滤一次性指令）
→ 立即局部更新
→ 新 Stable Skill（不经过观察期）
→ 写入 memory/skill_evolution/active/ overlay，不污染源码 skills/

Agent 观察到失败或异常
→ Abnormal Trajectory Buffer（按 run_id 去重）
→ Batch Review
→ Agent-Inferred Proposal
→ Candidate Skill（overlay 版本）
→ 后续相关任务观察（至少 3 次命中目标 Skill 的 PASS）
→ 晋升或回滚
```

核心原则：
- 用户明确指令是命令，但需 LLM 二次鉴权（区分一次性指令和长期规则）
- Agent 自主推断是假设，需要观察验证
- 正常成功默认不触发修改
- 一次只处理一个主要问题
- 所有修改可追踪、可回滚
- 进化产物写入 `memory/skill_evolution/active/`，源码 `skills/` 永不修改
- 实验性功能，通过 CLI 参数 `--skill-evolution` 开关控制

---

## 2. 项目结构

```
extensions/skill_evolution/                  # 【新建】
├── __init__.py                              # 公开 API
├── types.py                                 # 核心数据类型
├── config.py                                # EvolutionConfig
├── adapter.py                               # Trace → Rollout 适配器
├── patcher.py                               # Markdown 段落级补丁
├── store.py                                 # Skill 版本快照存储（读写 overlay）
├── feedback_router.py                       # 路由：关键词初筛 → HOTFIX / ABNORMAL / NORMAL
├── hotfix/
│   ├── __init__.py
│   └── generator.py                         # User-Directed Hotfix 生成器（LLM 终判）
├── evolution/
│   ├── __init__.py
│   ├── buffer.py                            # 异常轨迹缓存（按 run_id 去重）
│   ├── review_agent.py                      # Batch Review Agent
│   ├── proposal_manager.py                  # Proposal 生命周期管理
│   └── observer.py                          # Candidate 观察器（相关任务计数）
├── state_machine.py                         # 主状态机
└── templates/
    ├── __init__.py
    └── review_prompt.py                     # Review Agent Prompt 模板

skills/                                      # 源码资产，git tracked，永不修改
└── code-review/
    └── SKILL.md                             # 【新建】mock skill 用于测试

memory/skill_evolution/                      # runtime 产物，gitignored
├── state.json                               # 全局 EvolutionState
└── active/
    └── code-review/
        ├── SKILL.md                         # overlay 版本（进化产物）
        └── .evolution/
            ├── versions/    (v1.md, v2.md, ...)
            ├── proposals/   (HF-*.json, P-*.json)
            ├── rejected.jsonl
            ├── buffer.jsonl
            └── metrics.jsonl

tests/extensions/
└── test_skill_evolution.py                  # 【新建】单元测试
```

### 修改的现有文件

| 文件 | 改动 |
|------|------|
| `core/config.py` | + `enable_skill_evolution` 字段 |
| `app/cli.py` | + `--skill-evolution` CLI 参数 |
| `app/bootstrap.py` | 传递 `enable_skill_evolution` 到 agent |
| `runtime/host.py` | + `_skill_evolution_manager` 属性 + `_on_run_finished()` 钩子 |
| `runtime/factory.py` | 初始化 `SkillEvolutionManager` + 设置 SkillLoader overlay |
| `runtime/loop.py` | 任务结束后调用 `_on_run_finished()` + `_prepare_run` 中清空事件缓冲 |
| `extensions/tracing/protocol.py` | + `EVOLUTION_TRACE_EVENTS` dict（独立于 CORE_TRACE_EVENTS）|
| `extensions/tracing/logger.py` | + `_current_run_events` 内存缓冲 + `get_current_run_events()` / `clear_current_run_events()` |
| `extensions/skills/loader.py` | + `set_overlay_dir()` 方法，扫描时优先读取 overlay |

---

## 3. 模块详细设计

### 3.1 types.py — 核心数据类型

| 类型 | 说明 | 取值 |
|------|------|------|
| `EvolutionState` | 系统状态 | STABLE / EVALUATING / COOLDOWN / PAUSED |
| `ProposalStatus` | Proposal 生命周期 | PROPOSED / STAGED / EVALUATING / ACCEPTED / REJECTED / SUPERSEDED |
| `ProposalType` | Proposal 来源 | USER_DIRECTED_HOTFIX / AGENT_INFERRED |
| `SkillState` | 版本状态 | STABLE / CANDIDATE / ROLLED_BACK / SUPERSEDED / ARCHIVED |
| `FeedbackRoute` | 路由结果 | USER_HOTFIX / ABNORMAL_ROLLOUT / NORMAL_ROLLOUT |
| `BatchReviewDecision` | Review 决策 | NO_UPDATE / KEEP_COLLECTING / PROPOSE_PATCH |
| `ObservationResult` | 观察结果 | PASS / TARGET_ERROR / HARD_FAILURE / HUMAN_INTERVENTION / IRRELEVANT |

核心 dataclass：

```python
@dataclass
class RolloutRecord:
    """从 Trace 聚合的任务执行摘要"""
    trace_id: str
    persistent_run_id: str        # f"{session_id}:{run_id}"，跨进程持久去重
    input_fingerprint: str        # SHA256(processed_input)[:12]
    skills_invoked: list[str]     # 本 run 中调用的 Skill 名称列表
    attributing_skill: str | None # 本次 run 归属的 Skill（仅当恰好调用 1 个 Skill 时）
    skill_version: str            # 归属 Skill 的版本
    task_success: bool
    hard_error: bool              # model_error / tool_error_unrecoverable / token_budget
    human_intervention: bool      # AskUser 工具被调用且用户给了响应
    user_feedback_text: str | None = None
    is_explicit_correction: bool = False
    is_long_term_instruction: bool = False
    error_signatures: list[str] = field(default_factory=list)
    summary: str = ""

@dataclass
class EvolutionStateRecord:
    """per-Skill 持久化的演化状态，跨重启恢复"""
    skill_id: str
    state: str                    # STABLE / EVALUATING / COOLDOWN / PAUSED
    active_proposal_id: str | None
    lkg_version: str              # last known good version
    current_version: str          # 当前 overlay 版本
    observer_relevant_pass_count: int = 0
    observer_total_relevant_count: int = 0
    cooldown_tasks_remaining: int = 0
    consecutive_rejections: int = 0
    overlay_active: bool = False

@dataclass
class PatchOp:
    """局部补丁操作"""
    patch_type: str          # replace | insert_after | append
    target_section: str      # Markdown 标题文本
    old_text: str = ""       # replace 时需要
    new_text: str = ""       # 新内容

@dataclass
class Proposal:
    """Skill 修改提案"""
    proposal_id: str
    proposal_type: ProposalType
    target_skill: str
    base_version: str
    source_trace_ids: list[str]
    problem: str
    reason: str
    target_section: str
    patch: PatchOp
    expected_behavior: str
    error_signature: str       # 标识目标问题的 key
    risk_level: str = "medium"
    status: ProposalStatus = ProposalStatus.PROPOSED
    user_instruction: Optional[str] = None   # Hotfix 时填写
    rejection_reason: Optional[str] = None
    failure_trace_ids: list[str] = field(default_factory=list)

@dataclass
class SkillVersionMeta:
    skill_id: str
    version: str                     # v1, v2, v3-candidate, v3
    parent_version: Optional[str]
    state: SkillState
    proposal_id: Optional[str] = None
    source_type: Optional[str] = None

@dataclass
class ReviewResult:
    decision: BatchReviewDecision
    proposal: Optional[Proposal] = None
    reasoning: str = ""
```

---

### 3.2 config.py — 配置

```python
@dataclass
class EvolutionConfig:
    enabled: bool = False

    # Batch Review 阈值（相比 TRD 降低，加速实验触发）
    minimum_abnormal_traces: int = 3          # TRD: 5
    minimum_distinct_runs: int = 2            # 最少不同 run_id 数量（原 TRD 的 distinct_tasks）
    max_proposals_per_batch: int = 1

    # Candidate 观察（相比 TRD 缩短，加速验证）
    minimum_relevant_tasks: int = 3           # 至少 N 个相关任务 PASS 才晋升
    max_observation_tasks: int = 15           # 最多等 N 个任务，超限降级晋升
    lock_during_evaluation: bool = True

    # 冷却期
    tasks_after_accept: int = 3              # TRD: 10
    tasks_after_reject: int = 3              # TRD: 10

    # 拒绝限制
    max_consecutive_rejections: int = 2
    recent_rejected_proposals_in_prompt: int = 5

    # Patch 约束
    max_sections: int = 2
    allow_full_rewrite: bool = False

    # 存储
    rollout_retention_days: int = 30
    version_retention_count: int = 20
```

### 3.3 adapter.py — Trace → Rollout 适配器

**职责：** 将 TraceLogger 的内存事件缓冲转换为 `RolloutRecord`。**Skill 归属规则：一个 run 恰好调用 1 个 Skill → 归属该 Skill；0 个或 ≥2 个 → 不归属，跳过演进。**

**输入来源：** `TraceLogger._current_run_events`

核心函数：

| 函数 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `trace_events_to_rollout(events, session_id, run_id, processed_input)` | `list[dict]` | `RolloutRecord` | 聚合事件 |
| `classify_outcome(rollout)` | `RolloutRecord` | `str` | SUCCESS / FAILURE / HARD_ERROR / HUMAN_INTERVENTION |
| `extract_skills_invoked(events)` | `list[dict]` | `list[str]` | 从 tool_call 事件提取 Skill 名称 |
| `resolve_attribution(skills_invoked)` | `list[str]` | `str \| None` | 恰好 1 个 → 返回名称；否则 → None |
| `detect_user_feedback(events)` | `list[dict]` | `dict` | 提取用户纠正消息 |
| `detect_error_signature(rollout, proposal)` | `RolloutRecord + Proposal` | `bool` | 检查目标错误是否复现 |

**Skill 归属规则：**

```
skills_invoked = [] → attributing_skill = None → NORMAL_ROLLOUT（不触发演进）
skills_invoked = ["code-review"] → attributing_skill = "code-review"
skills_invoked = ["code-review", "testing"] → attributing_skill = None → NORMAL_ROLLOUT（歧义，不归属）
```

**Rollout 聚合逻辑修正：**
- `persistent_run_id` = `f"{session_id}:{run_id}"` — 跨进程唯一，用于 buffer 去重
- `skills_invoked`：遍历 `tool_call` 事件中 `tool == "Skill"` 且 args 含 name 参数
- `terminal.reason in {"completed", "completed_unverified"}` → task_success = True
- `terminal.reason in {"model_error", "tool_error_unrecoverable", "token_budget"}` → hard_error = True
- `human_intervention`：通过 `tool_call(tool == "AskUser")` + 对应的 `tool_result` 中用户给出了非空回复来检测（**不是** user 消息，AskUser 的回答在 tool_result 中）
- **不使用 `session_summary`**：该事件仅在 `TraceLogger.finalize()` 时产生（会话结束时），不是每个 run 都有。直接从 `terminal` + 事件流聚合

### 3.3.1 TraceLogger 内存缓冲变更

为支持 `_on_run_finished()` 获取当前 run 事件，在 `TraceLogger` 中新增三个轻量级成员：

```python
# extensions/tracing/logger.py — TraceLogger 内部新增

class TraceLogger:
    def __init__(self, ...):
        ...
        self._current_run_events: list[dict] = []   # ← 新增：per-run 内存缓冲

    def log_event(self, event, payload, step=0):
        ...
        if self.enabled:
            ...
            event_obj = {"ts": ..., "session_id": ..., "step": step, "event": event, "payload": safe_payload}
            self._current_run_events.append(event_obj)  # ← 新增：写入缓冲
            ...

    def get_current_run_events(self) -> list[dict]:
        """返回当前 run 的事件副本，供 Skill Evolution 使用"""
        return list(self._current_run_events)

    def clear_current_run_events(self):
        """新 run 开始前清空缓冲"""
        self._current_run_events.clear()
```

**为什么安全：** `TraceLogger` 已有 `_total_steps`、`_tools_used`、`_total_usage`、`_current_step`、`_current_run` 等内部状态变量。`_current_run_events` 是同模式的累积器，不改变公开 API，不修改 `CORE_TRACE_EVENTS` 协议。

### 3.4 patcher.py — Markdown 补丁器

**职责：** 对 Markdown Skill 文件执行精确的段落级修改。

核心接口：

```python
def apply_patch(content: str, patch: PatchOp) -> str | None
def locate_section(content: str, heading: str) -> tuple[int, int] | None
def replace_text(content: str, old: str, new: str) -> str | None
def insert_after_section(content: str, heading: str, new_text: str) -> str | None
def append_to_end(content: str, new_text: str) -> str
```

策略：
- 以 `## ` 或 `# ` 开头的标题作为段落边界
- `replace` 在目标段落内精确匹配 `old_text`，替换为 `new_text`
- `insert_after` 在目标段落结束位置后插入新内容
- `append` 追加到文件末尾
- 所有操作返回修改后的完整内容，失败返回 None

### 3.5 store.py — Skill 版本存储

**职责：** 管理 Skill 文件的版本快照、应用补丁、恢复旧版本。**所有写操作针对 runtime overlay（`memory/skill_evolution/active/`），永不修改源码 `skills/` 目录。**

**Overlay 机制：**

```
skills/code-review/SKILL.md                   # 源码资产，git tracked，永不被修改
memory/skill_evolution/active/
└── code-review/
    ├── SKILL.md                              # runtime 覆盖版本（进化产物）
    └── .evolution/                           # 进化元数据
        ├── versions/    (v1.md, v2.md, ...)
        ├── proposals/   (HF-*.json, P-*.json)
        ├── rejected.jsonl
        ├── buffer.jsonl
        └── metrics.jsonl
```

**SkillLoader 优先读 overlay：** `SkillLoader._iter_skill_files()` 先扫源码 `skills/` 目录，再扫 overlay `memory/skill_evolution/active/`。如果 overlay 中存在同名 skill，覆盖源码版本。

```python
class SkillLoader:
    def __init__(self, ...):
        self._overlay_dir: Path | None = None  # ← 新增

    def set_overlay_dir(self, path: Path | None):
        self._overlay_dir = path
        self._skills.clear()  # 强制重新扫描

    def _iter_skill_files(self) -> list[Path]:
        files: dict[str, Path] = {}
        # 先扫源码目录
        for path in self._skills_dir.rglob("SKILL.md"):
            key = str(path.relative_to(self._skills_dir))
            files[key] = path
        # 再扫 overlay 目录，覆盖同名 skill
        if self._overlay_dir and self._overlay_dir.exists():
            for path in self._overlay_dir.rglob("SKILL.md"):
                key = str(path.relative_to(self._overlay_dir))
                files[key] = path  # overlay 优先
        return sorted(files.values())
```

**SkillVersionStore 核心接口：**

```python
class SkillVersionStore:
    def __init__(self, source_skill_path: Path, overlay_dir: Path)
    def ensure_overlay_exists(self)               # 首次开启时，从源码复制到 overlay
    def snapshot_current(self) -> str              # → version_id，复制 overlay SKILL.md 到 .evolution/versions/
    def apply_patch(self, patch: PatchOp) -> str   # → new_version，修改 overlay SKILL.md
    def restore_version(self, version: str)         # 从 .evolution/versions/ 恢复到 overlay
    def get_current_version(self) -> str
    def get_lkg_version(self) -> str               # last known good
    def list_versions(self) -> list[SkillVersionMeta]
    def save_metadata(self, meta: SkillVersionMeta)
```

版本号格式：`v1` → `v2` → `v3-candidate` → `v3`

**回滚的语义：** 恢复 overlay 中的 SKILL.md 到快照版本（或删除 overlay 回到源码版本），不涉及 git 操作。

### 3.6 feedback_router.py — 反馈路由

```python
class FeedbackRouter:
    def route(self, rollout: RolloutRecord) -> FeedbackRoute
```

路由逻辑（两次过滤）：

```
层级 1 — 关键词初筛（FeedbackRouter，允许假阳性通过）：
  rollout.is_long_term_instruction == True → USER_HOTFIX_CANDIDATE
  rollout.task_success == False 或 hard_error 或 human_intervention → ABNORMAL_ROLLOUT
  其他 → NORMAL_ROLLOUT

层级 2 — LLM 终判（HotfixGenerator，过滤一次性指令）：
  HotfixGenerator 的 prompt 要求 LLM 区分：
    - 一次性任务要求 → 返回 {"action": "NO_HOTFIX"}
    - 可泛化的长期规则 → 返回 {"action": "APPLY_HOTFIX", "patch": {...}}
    - 无法确定 → 返回 {"action": "ASK_USER"}(V1 降级为不操作)
```

**关键词初筛逻辑（adapter.py 中实现）：**

```python
# 长期指令关键词
LONG_TERM_KEYWORDS = [
    "以后都", "下次遇到", "以后先做", "以后要", "以后再",
    "后续都", "每次都要", "从今往后", "一直要",
]
# 纠正关键词
CORRECTION_KEYWORDS = [
    "不对", "错误", "不要用", "别再", "改正", "修复", "纠正",
    "应该是", "正确做法", "问题在于",
]

def detect_user_feedback(events):
    # 信号 1：含长期关键词
    has_long_term = any(kw in text for kw in LONG_TERM_KEYWORDS)
    # 信号 2：含纠正上下文（任务是纠正之前的错误行为）
    has_correction = any(kw in text for kw in CORRECTION_KEYWORDS)
    # 初筛通过条件：长期关键词 + （纠正上下文 或 出现在 agent 动作之后）
    return has_long_term
```

> 注意：FeedbackRouter 的初筛刻意允许假阳性（比如用户说"以后都这么做吧"作为一次性确认），真正的语义判断在 HotfixGenerator 的 LLM 终判中完成。

### 3.7 hotfix/generator.py — Hotfix 生成器

**职责：** 将用户明确指令转化为局部 Skill Patch。**FeedbackRouter 只做关键词初筛，HotfixGenerator 的 LLM 做终判，可返回 NO_HOTFIX 拒绝一次性任务指令。**

```python
class HotfixGenerator:
    def __init__(self, llm)
    def generate(
        self,
        current_skill_content: str,
        user_instruction: str,
        rollout: RolloutRecord,
    ) -> Proposal | None   # 返回 None 表示 LLM 判定无需修改
```

流程：
1. 构建 prompt：当前 Skill 完整内容 + 用户原始指令 + 当前任务上下文 + 判据
2. LLM 判断指令性质，返回三类结果：
   - `{"action": "NO_HOTFIX", "reason": "..."}` → 返回 None，不更新
   - `{"action": "ASK_USER", "question": "..."}` → V1 降级为返回 None，记录日志
   - `{"action": "APPLY_HOTFIX", "patch_type": "...", "target_section": "...", ...}` → 构造 Proposal
3. 如果是 APPLY_HOTFIX，校验 PatchOp 合法性（target_section 必须存在于当前 Skill 中）
4. 构造 Proposal（proposal_type=USER_DIRECTED_HOTFIX）

约束：
- Prompt 中明确要求区分一次性任务指令和可泛化的长期规则
- Hotfix 优先局部修改，不重写整个 Skill
- 保留用户原始指令在 Proposal 的 `user_instruction` 字段
- 如果 LLM 返回的 target_section 不存在，降级为 append

### 3.8 evolution/buffer.py — 异常轨迹缓存

**职责：** 按 Skill 分区缓存异常 Rollout。每个 Skill 独立一个 buffer 文件。

```python
class AbnormalTrajectoryBuffer:
    def __init__(self, buffer_path: Path, config: EvolutionConfig)
    def append(self, rollout: RolloutRecord)    # 按 rollout.attributing_skill 定位 buffer
    def get_batch(self, skill_name: str) -> list[RolloutRecord]
    def should_review(self, skill_name: str) -> bool
    def count_distinct_runs(self, skill_name: str) -> int  # 按 persistent_run_id 去重
    def mark_consumed(self, skill_name: str, trace_ids: list[str])
    def clear(self, skill_name: str)
```

存储：`memory/skill_evolution/active/<skill_name>/.evolution/buffer.jsonl`

触发条件（`should_review()`）：
- `len(buffer) >= minimum_abnormal_traces`（默认 3）
- `count_distinct_runs() >= minimum_distinct_runs`（默认 2）— 基于 `persistent_run_id` 去重，跨进程唯一
- 该 Skill 的 EvolutionState 为 STABLE

**去重 key：** `persistent_run_id` = `f"{session_id}:{run_id}"`。`session_id` 来自 TraceLogger，`run_id` 来自 RuntimeRunner。重启后 session_id 不同，不会与历史任务冲突。

**Skill 归属检查：** 只有 `rollout.attributing_skill is not None` 的 Rollout 才进入 buffer。无归属 → 跳过。

### 3.9 evolution/review_agent.py — Batch Review Agent

**职责：** 使用 LLM 分析多条异常轨迹，判断是否需要对 Skill 进行修改。

```python
class BatchReviewAgent:
    def __init__(self, llm)
    def review(
        self,
        current_skill: str,
        abnormal_rollouts: list[RolloutRecord],
        success_summaries: list[str],
        rejected_proposals: list[Proposal],
    ) -> ReviewResult
```

流程：
1. 用 `templates/review_prompt.py` 的 prompt + 注入数据
2. 调用 LLM（复用主 Agent 的 LLM 配置）
3. 解析响应：
   - `NO_UPDATE` → 归档 buffer
   - `KEEP_COLLECTING` → 保留 buffer，等待更多轨迹
   - `PROPOSE_PATCH` → 解析 JSON 中的 patch 详情
4. 如果 PROPOSE_PATCH，构造 Proposal 对象（proposal_type=AGENT_INFERRED）

输入构成：
```
Current Skill（完整内容）
+ Abnormal Rollout Summaries（精简摘要，每个 rollout 一段）
+ Success Summaries（最近 2-3 条成功轨迹的简要描述）
+ Recent Rejected Proposals（最近 5 条被拒绝的 Proposal 摘要）
+ Review Constraints
```

### 3.10 evolution/proposal_manager.py — Proposal 管理

```python
class ProposalManager:
    def __init__(self, proposals_dir: Path)
    def propose(self, proposal: Proposal)           # 保存 JSON，状态 PROPOSED
    def stage(self, proposal_id: str)                # → STAGED
    def evaluate(self, proposal_id: str)             # → EVALUATING
    def accept(self, proposal_id: str)               # → ACCEPTED
    def reject(self, proposal_id: str, reason: str)  # → REJECTED，追加到 rejected.jsonl
    def supersede(self, proposal_id: str)            # → SUPERSEDED（被 Hotfix 覆盖时）
    def get_active(self) -> Proposal | None          # 当前活跃的 Proposal
    def get_recent_rejected(self, n: int) -> list[Proposal]
    def is_duplicate(self, proposal: Proposal) -> bool
```

去重策略（V1 简化）：
- 文本指纹：`(error_signature, target_section, patch_type)` 三元组
- 检查是否与最近 rejected 的 Proposal 匹配

### 3.11 evolution/observer.py — Candidate 观察器

```python
class CandidateObserver:
    def __init__(self, config: EvolutionConfig)
    def observe(self, rollout: RolloutRecord, proposal: Proposal) -> ObservationResult
    def is_observation_complete(self) -> bool
    def is_exceeded(self) -> bool               # 观察上限已到但不够相关 → EXPIRE
    def relevant_count(self) -> int
    def total_relevant_count(self) -> int
    def reset(self)
    def restore(self, relevant_pass: int, total_relevant: int)  # 跨重启恢复
```

**核心修正：无关任务不参与裁决。** 是否相关由 `proposal.target_skill in rollout.skills_invoked` 判断。

```
observe(rollout, proposal):
  1. 相关性检查（先于任何错误检查）：
     if proposal.target_skill not in rollout.skills_invoked:
       return IRRELEVANT  # 跳过，不计入 pass/fail/error

  2. 相关任务才做错误检查：
     total_relevant_count++
     if detect_error_signature(rollout, proposal) → TARGET_ERROR
     if rollout.hard_error → HARD_FAILURE
     if rollout.human_intervention → HUMAN_INTERVENTION
     return PASS (+ relevant_count++)

is_observation_complete():
  return relevant_count >= minimum_relevant_tasks(3)   # ≥3 次相关 PASS → 晋升

is_exceeded():
  return total_relevant_count >= max_observation_tasks(15)  # 够 15 次相关但不够 3 次 PASS → EXPIRE
```

**晋升 vs 过期：**

| 条件 | 结果 |
|------|------|
| ≥3 次相关 PASS | **晋升** Candidate → Stable |
| 某次相关任务出现 TARGET_ERROR | **回滚** + Proposal REJECTED |
| 某次相关任务出现 HARD_FAILURE | **回滚** + Proposal REJECTED |
| 某次相关任务出现 HUMAN_INTERVENTION | **回滚** + Proposal REJECTED |
| 累计 15 次相关任务但 <3 次 PASS | **过期回滚** 到 LKG, Proposal SUPERSEDED（不是 REJECTED — 没有证明它错了）|
| 不相关任务 | **忽略**（不计入任何计数） |

**设计理由：** 无关任务既不应让 Candidate 晋升（没有证明力），也不应导致回滚（错误可能跟这个 Candidate 完全无关），也不应触发降级晋升（对 patch 效果毫无信息量）。观察窗口只统计真正命中了目标 Skill 的任务。

### 3.12 state_machine.py — 主状态机

```python
class SkillEvolutionManager:
    def __init__(
        self,
        skill_loader: SkillLoader,
        llm,
        config: EvolutionConfig,
        overlay_dir: Path,       # memory/skill_evolution/active/
    )
    def load_state(self)                                    # 从 state.json 恢复跨重启状态
    def save_state(self)                                    # 原子写入 state.json
    def on_run_finished(self, trace_events: list[dict],
                        session_id: str, run_id: int,
                        processed_input: str)               # 主入口
    def get_skill_state(self, skill_name: str) -> EvolutionStateRecord | None
```

**per-Skill 状态：** 每个 Skill 独立维护一个 `EvolutionStateRecord`。`SkillEvolutionManager` 内部维护 `dict[str, EvolutionStateRecord]`，按键为 skill_name。全局 `state.json` 保存所有 skill 的状态。

#### 3.12.1 跨重启恢复

```python
def load_state(self):
    if not (overlay_dir / "state.json").exists():
        self._states: dict[str, EvolutionStateRecord] = {}
        return
    data = json.loads((overlay_dir / "state.json").read_text())
    for skill_name, raw in data.get("skills", {}).items():
        self._states[skill_name] = EvolutionStateRecord(**raw)
    # 验证 overlay 一致性：如果 state 说 EVALUATING 但 overlay SKILL.md 不存在 → 降级为 STABLE
    for skill_name, record in self._states.items():
        if record.state == "EVALUATING" and not (overlay_dir / skill_name / "SKILL.md").exists():
            record.state = "STABLE"
            record.active_proposal_id = None

def save_state(self):
    data = {
        "version": 1,
        "updated_at": datetime.now(UTC).isoformat(),
        "skills": {name: asdict(record) for name, record in self._states.items()}
    }
    tmp_path = overlay_dir / "state.json.tmp"
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp_path.replace(overlay_dir / "state.json")  # 原子替换
```

#### 3.12.2 核心流程（`on_run_finished`）

```
1. Adapter: trace_events → RolloutRecord
   (session_id, run_id, processed_input → persistent_run_id, input_fingerprint, skills_invoked, attributing_skill)

2. 无归属 Skill → 跳过（不触发任何演进）

3. skill_name = rollout.attributing_skill
   state = self._states.get(skill_name) or default STABLE

4. FeedbackRouter.route(rollout) → FeedbackRoute

5. switch(route):
   
   case USER_HOTFIX_CANDIDATE:
     hotfix_proposal = HotfixGenerator.generate(current_skill, user_instruction, rollout)
     if hotfix_proposal is None: break          # LLM 终判拒绝
     if state.state == EVALUATING: 
       abort_candidate(skill_name)              # 恢复 LKG，标记原 Proposal SUPERSEDED
     store.ensure_overlay_exists(skill_name)
     store.snapshot_current(skill_name)
     store.apply_patch(skill_name, hotfix_proposal.patch)
     skill_loader.set_overlay_dir(overlay_dir)
     state.state = "STABLE"; state.active_proposal_id = None
     state.lkg_version = store.get_current_version(skill_name)
     state.current_version = state.lkg_version
     state.cooldown_tasks_remaining = 0
     self.save_state()
     emit trace_event("hotfix_applied")
   
   case ABNORMAL_ROLLOUT:
     buffer.append(rollout)  # 按 skill_name 写入对应 buffer
     
     if state.state == "EVALUATING":
       result = observer.observe(rollout, active_proposal)
       switch(result):
         case IRRELEVANT: break                  # 无关任务，跳过
         case PASS: 
           observer.relevant_pass_count++
           observer.total_relevant_count++
         case TARGET_ERROR | HARD_FAILURE | HUMAN_INTERVENTION:
           rollback(skill_name)                  # 恢复 LKG、Proposal REJECTED
     
     elif state.state == "STABLE" and buffer.should_review(skill_name):
       try:
         decision = review_agent.review(...)
         switch(decision):
           case NO_UPDATE:     buffer.mark_consumed(...)
           case KEEP_COLLECTING: (保留 buffer)
           case PROPOSE_PATCH:
             if validate(proposal) and not is_duplicate:
               store.ensure_overlay_exists(skill_name)
               candidate_content = patcher.apply_patch(skill_content, proposal.patch)
               store.create_candidate(skill_name, candidate_content, version)
               skill_loader.set_overlay_dir(overlay_dir)
               observer.reset()
               state.state = "EVALUATING"
               state.active_proposal_id = proposal.proposal_id
               state.current_version = version
       except Exception:
         logger.warning("Batch review failed for %s, keeping buffer", skill_name, exc_info=True)
   
   case NORMAL_ROLLOUT:
     if state.state == "EVALUATING":
       （同 ABNORMAL 分支的 observer.observe 逻辑）
     
     if state.cooldown_tasks_remaining > 0:
       state.cooldown_tasks_remaining -= 1
     self.save_state()
```

**Exception 隔离：** `on_run_finished` 整个方法体包裹在 try/except 中。如果 Skill Evolution 内部任何异常（包括 Review LLM 超时/错误），只记录 warning 日志，不污染原任务的执行结果。

```python
# runtime/host.py 中的调用
def _on_run_finished(self, processed_input: str):
    if self._skill_evolution_manager is None:
        return
    try:
        events = self.trace_logger.get_current_run_events()
        session_id = self.trace_logger.session_id
        run_id = self._run_id
        self._skill_evolution_manager.on_run_finished(
            trace_events=events,
            session_id=session_id,
            run_id=run_id,
            processed_input=processed_input,
        )
    except Exception:
        self.logger.warning("Skill Evolution on_run_finished failed", exc_info=True)
```

#### 3.12.3 回滚与晋升操作

```python
def promote(self, skill_name):
    state = self._states[skill_name]
    store.apply_candidate_as_stable(skill_name, state.current_version)
    proposal_manager.accept(state.active_proposal_id)
    state.state = "STABLE"
    state.lkg_version = state.current_version
    state.active_proposal_id = None
    state.cooldown_tasks_remaining = config.tasks_after_accept
    state.consecutive_rejections = 0
    skill_loader.set_overlay_dir(overlay_dir)
    self.save_state()

def rollback(self, skill_name, reason):
    state = self._states[skill_name]
    store.restore_version(skill_name, state.lkg_version)
    proposal_manager.reject(state.active_proposal_id, reason)
    state.state = "STABLE"
    state.current_version = state.lkg_version
    state.active_proposal_id = None
    state.cooldown_tasks_remaining = config.tasks_after_reject
    state.consecutive_rejections += 1
    if state.consecutive_rejections >= config.max_consecutive_rejections:
        state.state = "PAUSED"
    skill_loader.set_overlay_dir(overlay_dir)
    self.save_state()
```

---

## 4. 现有文件修改细节

### 4.1 `core/config.py`

```python
# 在 Config 类中新增字段
enable_skill_evolution: bool = False

# 在 from_env() 中新增一行
enable_skill_evolution=os.getenv("SKILL_EVOLUTION_ENABLED", "false").lower()
    in {"1", "true", "yes", "y", "on"},
```

### 4.2 `app/cli.py`

```python
# build_parser() 中新增
parser.add_argument(
    "--skill-evolution", action="store_true",
    help="enable controlled skill evolution (experimental)",
)
```

### 4.3 `app/bootstrap.py`

```python
# build_runtime() 的 agent_kwargs 中新增
# CLI 参数优先，环境变量 fallback
skill_evolution_enabled = (
    getattr(args, "skill_evolution", False)
    or config.enable_skill_evolution
)
agent_kwargs["enable_skill_evolution"] = skill_evolution_enabled
```

### 4.4 `runtime/host.py`

```python
# CodeAgent.__init__ 新增参数
enable_skill_evolution: bool = False

# 新增属性
self._skill_evolution_manager = None

# 新增方法（processed_input 由 RuntimeRunner 从 _prepare_run 传递）
def _on_run_finished(self, processed_input: str):
    """Called by the runtime loop after each run completes."""
    if self._skill_evolution_manager is None:
        return
    try:
        events = self.trace_logger.get_current_run_events()
        session_id = self.trace_logger.session_id
        run_id = self._run_id
        self._skill_evolution_manager.on_run_finished(
            trace_events=events,
            session_id=session_id,
            run_id=run_id,
            processed_input=processed_input,
        )
    except Exception:
        self.logger.warning("Skill Evolution on_run_finished failed", exc_info=True)
```

### 4.5 `runtime/factory.py`

在 `initialize_persistence()` 末尾新增：

```python
# 初始化 Skill Evolution（实验性功能）
if getattr(host, "enable_skill_evolution", False) and host._skill_loader is not None:
    from extensions.skill_evolution.config import EvolutionConfig
    from extensions.skill_evolution.state_machine import SkillEvolutionManager

    overlay_dir = Path(host.project_root) / "memory" / "skill_evolution" / "active"
    host._skill_evolution_manager = SkillEvolutionManager(
        skill_loader=host._skill_loader,
        llm=host.llm,
        config=EvolutionConfig(enabled=True),
        overlay_dir=overlay_dir,
    )
    host._skill_evolution_manager.load_state()   # 跨重启恢复
    host._skill_loader.set_overlay_dir(overlay_dir)

# 如果 Skill Evolution 未开启，SkillLoader overlay 不设置，行为不变
```

### 4.6 `runtime/loop.py`

`_prepare_run()` 中新增清空事件缓冲：

```python
def _prepare_run(self, input_text, show_raw):
    ...
    trace_logger = host.trace_logger
    trace_logger.clear_current_run_events()  # ← 新增
    host._run_id += 1
    ...
```

`run()` 保存 `processed_input` 并传递给钩子：

```python
def run(self, input_text: str, **kwargs) -> str:
    show_raw = kwargs.pop("show_raw", False)
    processed_input, trace_logger, run_id = self._prepare_run(input_text, show_raw)
    raw_input = processed_input  # ← 保存供 finally 使用
    response_text = ""
    try:
        response_text = self._react_loop(
            pending_input=processed_input,
            show_raw=show_raw,
            trace_logger=trace_logger,
        )
    finally:
        self._finish_run(trace_logger, run_id, response_text)
        host = self.host
        if hasattr(host, "_on_run_finished"):
            host._on_run_finished(processed_input=raw_input)
```

### 4.7 `extensions/tracing/protocol.py`

```python
# 不修改 CORE_TRACE_EVENTS。仿照 SUBAGENT_TRACE_EVENTS 模式新增：

EVOLUTION_TRACE_EVENTS: dict[str, TraceEventSpec] = {
    "skill_evolution_event": TraceEventSpec(("event_type", "skill_id", "details")),
}
```

事件类型：`hotfix_applied` | `proposal_proposed` | `candidate_evaluating` | `candidate_promoted` | `candidate_rollback` | `proposal_rejected`

### 4.8 `extensions/tracing/logger.py` + NullTraceLogger 兼容

TraceLogger 新增：

```python
class TraceLogger:
    def __init__(self, ...):
        ...
        self._current_run_events: list[dict] = []   # per-run 内存缓冲

    def log_event(self, event, payload, step=0):
        ...
        if self.enabled:
            event_obj = {...}
            self._current_run_events.append(event_obj)  # 写入缓冲
            ...

    def get_current_run_events(self) -> list[dict]:
        return list(self._current_run_events)

    def clear_current_run_events(self):
        self._current_run_events.clear()
```

NullTraceLogger 兼容（不依赖 tracing）：

```python
class NullTraceLogger:
    # ... 已有成员 ...
    
    def get_current_run_events(self) -> list[dict]:
        return []                              # ← 新增，tracing 关闭时返回空列表

    def clear_current_run_events(self):
        pass                                   # ← 新增
```

**设计保证：** 即使 tracing 关闭（NullTraceLogger），Skill Evolution 也不会崩溃。`get_current_run_events()` 返回空列表，adapter 会生成一个 `attributing_skill = None` 的 RolloutRecord，整个 Evolution 流程跳过。但这是降级行为——关闭 tracing 意味着无法记录异常轨迹用于 Batch Review。推荐文档提示开启时同时要求 tracing 启用。
    host._skill_loader.set_overlay_dir(overlay_dir)
```

### 4.6 `runtime/loop.py`

`_prepare_run()` 中新增清空事件缓冲：

```python
def _prepare_run(self, input_text, show_raw):
    ...
    trace_logger = host.trace_logger
    trace_logger.clear_current_run_events()  # ← 新增：新 run 开始前清空缓冲
    host._run_id += 1
    ...
```

`run()` 方法的 `finally` 块中，`_finish_run()` 之后新增：

```python
def run(self, input_text, **kwargs):
    ...
    try:
        response_text = self._react_loop(...)
    finally:
        self._finish_run(trace_logger, run_id, response_text)
        # 通知 Skill Evolution 任务完成
        host = self.host
        if hasattr(host, "_on_run_finished"):
            host._on_run_finished()
```

### 4.7 `extensions/tracing/protocol.py`

```python
# 不修改 CORE_TRACE_EVENTS（Phase 0 frozen），仿照 SUBAGENT_TRACE_EVENTS 模式新增独立 dict：

EVOLUTION_TRACE_EVENTS: dict[str, TraceEventSpec] = {
    "skill_evolution_event": TraceEventSpec(("event_type", "skill_id", "details")),
}
```

对应 `__all__` 也导出 `EVOLUTION_TRACE_EVENTS`。

事件类型：`hotfix_applied` | `proposal_proposed` | `candidate_evaluating` | `candidate_promoted` | `candidate_rollback` | `proposal_rejected`

**为什么这样安全：**
- `CORE_TRACE_EVENTS` 完全不动，`test_trace_protocol_defines_phase0_core_events` 的断言不受影响
- `SUBAGENT_TRACE_EVENTS` 已经证明这种独立扩展模式可行
- `TraceLogger.log_event()` 不限制事件名，只负责写 JSONL

---

## 5. 状态机

```
                           ┌─────────────────────┐
                           │       STABLE        │
                           └──────────┬──────────┘
                                      │
               ┌──────────────────────┴──────────────────────┐
               │                                             │
    Keyword Match + LLM Confirm                       Buffer Ready
    (两层过滤)                                              │
               │                                             ▼
               ▼                                         REVIEWING
        APPLY_HOTFIX                             ┌─────────┼──────────┐
               │                                  │         │          │
               ▼                              NO_UPDATE  COLLECTING  PROPOSE
            STABLE                               │                    │
                                                 │                    ▼
                                                 │              EVALUATING
                                                 │    ┌─────────────┴─────────────┐
                                                 │    │  (relevance-gated obs)   │
                                                 │    │                           │
                                                 │    ▼ (≥3 relevant PASS)       ▼ (error)
                                                 │ PROMOTE                    ROLLBACK
                                                 │    │                           │
                                                 └────┴───────────────┬───────────┘
                                                                       │
                                                                       ▼
                                                              STABLE (Cooldown)
```

---

## 6. 简化策略（相比 TRD V1）

| TRD 原设计 | 本方案 | 原因 |
|-----------|--------|------|
| minimum_abnormal_traces=5 | 3 | 实验性功能，加速触发 |
| minimum_distinct_tasks=3 | 2（基于 persistent_run_id） | 降低门槛；单 Agent CLI 无 task board |
| observation_tasks=15（任意任务） | minimum_relevant_tasks=3，max=15 | 防止不相关任务误晋升 |
| cooldown_tasks=10 | 3 | 快速迭代 |
| YAML 配置文件 | Python @dataclass + 环境变量 | 复用现有 Config 模式 |
| 文件锁 mutex | `threading.Lock` | 单进程 CLI 场景 |
| 语义去重（向量数据库） | 文本指纹 (error_signature + target_section) | V1 简化 |
| 时间冷却 | 任务计数冷却 | 不引入时间维度 |
| Success Rollout 评分器 | 仅做对照参考 | V1 聚焦失败驱动 |
| Error Signature 分类系统 | 自由字符串 | 不要求完整分类 |
| Hotfix 直接写入 | 两层过滤（关键词初筛 + LLM 终判） | 防止一次性指令污染 Skill |
| 直接修改 skills/ 源码 | Runtime overlay（memory/skill_evolution/active/） | 不污染 git worktree |
| 无 Rollout 接线方案 | TraceLogger 内存缓冲 + adapter 聚合 | 现有 TraceLogger 只写磁盘，无内存缓冲 |
| 全局唯一 state | per-Skill EvolutionStateRecord | 不同 Skill 独立演进 |
| task_id 去重 | persistent_run_id (`session_id:run_id`) | 跨进程唯一 |
| 无跨重启恢复 | load_state()/save_state() 原子读写 state.json | 进程退出不丢状态 |
| 无条件观测 | 无关任务 IRRELEVANT 跳过 | 无关任务不晋升也不回滚 |
| 无异常隔离 | on_run_finished 全量 try/except | Review LLM 异常不污染主任务 |
| Hotfix 无条件写入 | LLM 返回 NO_HOTFIX/APPLY_HOTFIX/ASK_USER | 一次性指令被 LLM 拒绝 |
| 无 NullTraceLogger 兼容 | NullTraceLogger 实现兼容接口（返回空） | tracing 关闭不崩溃 |

---

## 7. 测试设计

### 7.1 mock skill

```markdown
---
name: code-review
description: Review code quality and risks
---
# Code Review

Use this checklist when reviewing code:

1. **Security** - Check for hardcoded secrets, SQL injection
2. **Error Handling** - Verify exceptions are caught properly
3. **Naming** - Ensure clear, descriptive names
4. **Duplication** - Look for repeated logic
5. **Testing** - Confirm edge case coverage

## Review Process

1. Read the changed files using the Read tool
2. Run existing tests to verify baseline
3. Apply each checklist item
4. Report findings with file paths and line numbers

## Output Format

Provide findings as a numbered list with severity: HIGH / MEDIUM / LOW
```

### 7.2 测试用例清单

| 测试模块 | 测试用例 | 验证点 |
|---------|---------|--------|
| **Patcher** | `test_patcher_replace_exact` | 精确文本替换 |
| | `test_patcher_insert_after_section` | 在段落后插入 |
| | `test_patcher_append` | 追加到末尾 |
| | `test_patcher_section_not_found` | 段落不存在返回 None |
| | `test_patcher_multiple_headings` | 多级标题正确定位 |
| **Store** | `test_store_ensure_overlay_creates_dir` | 首次开启时从源码复制到 overlay |
| | `test_store_snapshot_and_restore` | overlay 快照保存 + 恢复 |
| | `test_store_version_naming` | v1/v2/v3-candidate 版本号递增 |
| | `test_store_apply_patch` | 补丁应用 + 版本更新（写入 overlay，不污染源码）|
| | `test_store_list_versions` | 版本列表排序 |
| | `test_store_source_skill_never_modified` | 全程不修改 `skills/` 源码文件 |
| **SkillLoader** | `test_loader_overlay_priority` | overlay 文件覆盖源码同名 skill |
| | `test_loader_no_overlay_falls_back_to_source` | 无 overlay 时正常读源码 skill |
| **FeedbackRouter** | `test_router_hotfix_long_term_keyword` | 含"以后都" → USER_HOTFIX_CANDIDATE（初筛通过）|
| | `test_router_abnormal_failure` | task_success=False → ABNORMAL |
| | `test_router_abnormal_hard_error` | hard_error=True → ABNORMAL |
| | `test_router_normal` | 正常任务 → NORMAL |
| | `test_router_no_skill_attribution` | skills_invoked=[] → 不归属 → 跳过 |
| | `test_router_multi_skill_attribution` | skills_invoked≥2 → 歧义 → 跳过 |
| **HotfixGenerator** | `test_hotfix_llm_returns_no_hotfix` | LLM 判定为一次性指令 → 返回 None |
| | `test_hotfix_llm_returns_apply` | LLM 判定为长期规则 → 返回 Proposal |
| | `test_hotfix_llm_returns_ask_user` | LLM 不确定 → 降级为 None |
| **Buffer** | `test_buffer_threshold_reached` | 达到 minimum_abnormal_traces 可触发 |
| | `test_buffer_below_threshold` | 未达阈值不触发 |
| | `test_buffer_distinct_runs` | 按 persistent_run_id 去重计数 |
| | `test_buffer_persistent_key_unique` | 重启后 session_id 不同，历史 run 不冲突 |
| | `test_buffer_mark_consumed` | 已消费标记 |
| **ProposalManager** | `test_proposal_lifecycle` | PROPOSED → STAGED → EVALUATING → ACCEPTED |
| | `test_proposal_reject` | REJECTED + 写入 rejected.jsonl |
| | `test_proposal_supersede` | Hotfix 覆盖 → SUPERSEDED |
| | `test_proposal_duplicate_same_fingerprint` | 相同 error_signature+target_section 去重 |
| | `test_proposal_duplicate_different_fingerprint` | 不同指纹不误判 |
| **Observer** | `test_observer_relevant_pass` | 命中目标 Skill + PASS → relevant_count++ |
| | `test_observer_irrelevant_passes` | 未命中目标 Skill → IRRELEVANT，不计入任何计数 |
| | `test_observer_irrelevant_no_rollback` | 无关任务出现 hard_error → 不回滚 Candidate |
| | `test_observer_promotes_after_relevant_tasks` | 累计 3 次相关 PASS → 观察完成 |
| | `test_observer_expires_after_max_no_enough_pass` | 累计 15 次相关但 <3 次 PASS → EXPIRE 回滚（非 REJECTED）|
| | `test_observer_target_error` | 相关任务目标错误 → TARGET_ERROR → 立即回滚 |
| | `test_observer_hard_failure` | 相关任务硬失败 → HARD_FAILURE → 立即回滚 |
| | `test_observer_human_intervention` | 相关任务用户接管 → HUMAN_INTERVENTION → 立即回滚 |
| | `test_observer_restore_across_restart` | `restore()` 从 state.json 恢复计数 |
| **StateMachine** | `test_hotfix_flow` | 完整流程：路由→LLM终判→overlay写入→STABLE |
| | `test_hotfix_one_time_instruction_rejected` | 一次性指令 → LLM 返回 NO_HOTFIX → Skill 不变 |
| | `test_evolution_flow` | Evolution 完整流程（mock LLM）：异常→Buffer→Review→Candidate→Observe→Promote |
| | `test_evolution_rollback_target_error` | Candidate 出现目标错误 → 回滚 + Proposal REJECTED |
| | `test_evolution_rollback_hard_failure` | Candidate 出现硬失败 → 回滚 |
| | `test_hotfix_interrupts_candidate` | 观察期间 Hotfix → Candidate SUPERSEDED |
| | `test_consecutive_rejections_pause` | 连续 2 次拒绝 → PAUSED |
| | `test_cooldown_after_promote` | 晋升后冷却期不触发新 Review |
| | `test_cooldown_after_reject` | 回滚后冷却期不触发新 Review |
| | `test_config_disabled` | enable=False 时 `on_run_finished` 是 no-op |
| | `test_cross_restart_state_recovery` | `load_state()` 从 state.json 恢复 EVALUATING 状态 |
| | `test_cross_restart_overlay_inconsistent` | overlay 文件缺失 → 降级为 STABLE |
| | `test_no_skill_attribution_skips` | skills_invoked=0 → 不归属 → `on_run_finished` 直接跳过 |
| | `test_multi_skill_attribution_skips` | skills_invoked=2 → 歧义 → 跳过 |
| | `test_per_skill_independent_state` | Skill A PAUSED 不影响 Skill B STABLE |
| | `test_review_llm_exception_isolated` | Review LLM 异常 → 日志记录，不影响原任务 |
| **NullTraceLogger** | `test_null_tracer_returns_empty_events` | tracing 关闭时 `get_current_run_events()` 返回 [] |
| | `test_null_tracer_clear_noop` | tracing 关闭时 `clear_current_run_events()` 不崩溃 |
| | `test_evolution_with_tracing_disabled` | tracing 关闭 + evolution 开启 → 降级跳过，不崩溃 |

---

## 8. 配置开关

```bash
# CLI 方式
python main.py --skill-evolution

# 环境变量方式
SKILL_EVOLUTION_ENABLED=true python main.py

# 默认值：false，不开启不影响现有功能

# 所有 Evolution 配置项也支持环境变量覆盖：
SKILL_EVOLUTION_ENABLED=true
SKILL_EVOLUTION_MIN_ABNORMAL_TRACES=5
SKILL_EVOLUTION_OBSERVATION_TASKS=10
SKILL_EVOLUTION_COOLDOWN_AFTER_ACCEPT=5
```

---

## 9. 可观测性

每次 Evolution 操作通过 `TraceLogger` 记录。事件名统一为 `skill_evolution_event`，payload 层包含 `event_type`、`skill_id`、`details`：

```json
{
  "ts": "2026-06-15T10:00:00Z",
  "session_id": "s-20260615-100000-a1b2",
  "step": 0,
  "event": "skill_evolution_event",
  "payload": {
    "event_type": "hotfix_applied",
    "skill_id": "code-review",
    "details": {
      "proposal_id": "HF-00001",
      "base_version": "v1",
      "new_version": "v2",
      "user_instruction": "以后执行修改前必须先读取当前状态"
    }
  }
}
```

记录的事件类型：`hotfix_applied` / `proposal_proposed` / `candidate_evaluating` / `candidate_promoted` / `candidate_rollback` / `proposal_rejected`

**注意：** trace 事件格式与现有 TraceLogger 完全一致（ts + session_id + step + event + payload），仅事件名和 payload 字段为新增。`skill_evolution_event` 不进入 `CORE_TRACE_EVENTS`，注册在独立的 `EVOLUTION_TRACE_EVENTS` dict 中。

---

## 10. 文件清单

| # | 文件 | 操作 | 估算行数 |
|---|------|------|---------|
| 1 | `skills/code-review/SKILL.md` | 新建 | 25 |
| 2 | `extensions/skill_evolution/__init__.py` | 新建 | 15 |
| 3 | `extensions/skill_evolution/types.py` | 新建 | 150 |
| 4 | `extensions/skill_evolution/config.py` | 新建 | 55 |
| 5 | `extensions/skill_evolution/adapter.py` | 新建 | 120 |
| 6 | `extensions/skill_evolution/patcher.py` | 新建 | 80 |
| 7 | `extensions/skill_evolution/store.py` | 新建 | 140 |
| 8 | `extensions/skill_evolution/feedback_router.py` | 新建 | 50 |
| 9 | `extensions/skill_evolution/hotfix/__init__.py` | 新建 | 5 |
| 10 | `extensions/skill_evolution/hotfix/generator.py` | 新建 | 90 |
| 11 | `extensions/skill_evolution/evolution/__init__.py` | 新建 | 10 |
| 12 | `extensions/skill_evolution/evolution/buffer.py` | 新建 | 80 |
| 13 | `extensions/skill_evolution/evolution/review_agent.py` | 新建 | 120 |
| 14 | `extensions/skill_evolution/evolution/proposal_manager.py` | 新建 | 80 |
| 15 | `extensions/skill_evolution/evolution/observer.py` | 新建 | 90 |
| 16 | `extensions/skill_evolution/state_machine.py` | 新建 | 180 |
| 17 | `extensions/skill_evolution/templates/__init__.py` | 新建 | 5 |
| 18 | `extensions/skill_evolution/templates/review_prompt.py` | 新建 | 60 |
| 19 | `core/config.py` | 修改 | +5 |
| 20 | `app/cli.py` | 修改 | +3 |
| 21 | `app/bootstrap.py` | 修改 | +6 |
| 22 | `runtime/host.py` | 修改 | +30 |
| 23 | `runtime/factory.py` | 修改 | +18 |
| 24 | `runtime/loop.py` | 修改 | +10 |
| 25 | `extensions/tracing/protocol.py` | 修改 | +5 |
| 26 | `extensions/tracing/logger.py` | 修改 | +15 |
| 27 | `extensions/tracing/__init__.py` | 修改 | +5（NullTraceLogger 兼容接口）|
| 28 | `extensions/skills/loader.py` | 修改 | +20 |
| 29 | `tests/extensions/test_skill_evolution.py` | 新建 | 550 |

**新建 18 个文件 | 修改 10 个文件 | 约 1400 行业务代码 + 550 行测试代码**

---

## 11. 验收标准

- [ ] `--skill-evolution` 开关默认关闭，不影响现有功能
- [ ] 环境变量和 CLI 参数都能启用（优先级：CLI > 环境变量）
- [ ] TraceLogger 提供 `_current_run_events` 内存缓冲 + `get/clear` 方法
- [ ] NullTraceLogger 实现兼容接口（tracing 关闭时不会崩溃）
- [ ] `_on_run_finished()` 全量 try/except，Evolution 内部异常不污染主任务
- [ ] `processed_input` 正确从 RuntimeRunner.run() → `_on_run_finished()` 传递
- [ ] 开启后，恰好调用 1 个 Skill 的任务 → 归属该 Skill → 进入演化流程
- [ ] 0 个或 ≥2 个 Skill 调用的任务 → 跳过演化（不归属）
- [ ] 用户说"以后都..." → 初筛通过 → LLM 终判通过 → overlay 更新
- [ ] LLM 判定为一次性指令 → 返回 NO_HOTFIX → Skill 不变
- [ ] 任务失败/异常 → 异常轨迹缓存（按 Skill 分区，按 persistent_run_id 去重）
- [ ] 缓存达到阈值 → 触发 Batch Review（try/except 隔离，异常不影响主任务）
- [ ] Review 生成 Proposal → Candidate Skill（写入 overlay）
- [ ] Candidate 执行 ≥3 次**命中目标 Skill 的 PASS** → 晋升为 Stable
- [ ] 无关任务（未命中目标 Skill）→ IRRELEVANT，既不晋升也不回滚
- [ ] 累计 15 次相关任务但 <3 次 PASS → EXPIRE 回滚（Proposal SUPERSEDED）
- [ ] 相关任务出现目标错误/硬失败/用户接管 → 立即回滚 + Proposal REJECTED
- [ ] 连续 2 次 Proposal 失败 → PAUSED
- [ ] 晋升/回滚后 → 冷却期
- [ ] 跨重启：`load_state()` 从 state.json 恢复（EVALUATING/COOLDOWN/PAUSED 状态 + observer 计数）
- [ ] 跨重启：overlay 文件与 state.json 不一致 → 降级为 STABLE
- [ ] 不同 Skill 独立状态（Skill A PAUSED 不影响 Skill B STABLE）
- [ ] 所有版本可查询、可恢复（在 overlay 目录中）
- [ ] 被拒绝的 Proposal 可阻止重复
- [ ] `skills/code-review/SKILL.md` 源码文件全程未被修改
- [ ] SkillLoader overlay 优先读取，无 overlay 回退源码
- [ ] 所有操作有 trace 事件记录（独立 `EVOLUTION_TRACE_EVENTS`，不修改 CORE_TRACE_EVENTS）
- [ ] 40+ 个单元测试通过
