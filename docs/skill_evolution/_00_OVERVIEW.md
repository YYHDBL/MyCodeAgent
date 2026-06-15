# Skill Evolution — 总览

**版本：** V1.2  
**状态：** 实验性，`--skill-evolution` 开关控制  
**依赖：** 现有 Skill 系统 (`extensions/skills/`) + TraceLogger (`extensions/tracing/`)

---

## 1. 核心理念

将 Skill 更新从"单轮即时自修改"改造成**两条不同可信度的路径**：

```
用户明确纠错或长期要求
→ FeedbackRouter 关键词初筛
→ HotfixGenerator LLM 终判（拒绝一次性指令）
→ 立即局部更新
→ 写入 overlay，不污染源码 skills/

Agent 观察到失败或异常
→ AbnormalTrajectoryBuffer（按 Skill 分区，按 persistent_run_id 去重）
→ BatchReviewAgent（LLM 批量分析）
→ Agent-Inferred Proposal
→ Candidate Skill（overlay 版本）
→ CandidateObserver（仅相关任务参与裁决）
→ 晋升或回滚（无关任务不参与）
```

**核心原则：**
- 用户明确指令是命令，但需 LLM 二次鉴权
- Agent 自主推断是假设，需要观察验证
- 正常成功不触发修改
- 一次只处理一个主要问题
- 所有修改可追踪、可回滚
- **进化产物写入 `memory/skill_evolution/active/`，源码 `skills/` 永不修改**

---

## 2. 项目结构

```
extensions/skill_evolution/           # 【新建】核心逻辑
├── types.py                          # 数据类型
├── config.py                         # EvolutionConfig
├── adapter.py                        # Trace → Rollout
├── patcher.py                        # Markdown 补丁器
├── validator.py                      # Proposal 校验
├── store.py                          # 版本存储（只写 overlay）
├── feedback_router.py                # 路由
├── hotfix/generator.py               # Hotfix（LLM 终判）
├── evolution/buffer.py               # 异常缓存
├── evolution/review_agent.py         # Batch Review
├── evolution/proposal_manager.py     # Proposal 管理
├── evolution/observer.py             # Candidate 观察
├── state_machine.py                  # 主状态机
└── templates/review_prompt.py        # Review Prompt

memory/skill_evolution/               # 【运行时产物，gitignored】
├── state.json                        # 全局状态（跨重启恢复）
└── active/<skill_name>/
    ├── SKILL.md                      # overlay 版本
    └── .evolution/                   # 演化元数据

skills/<skill_name>/SKILL.md          # 【源码资产，git tracked，永不修改】
```

---

## 3. 修改的现有文件（10 个）

| 文件 | 改动量 | 要点 |
|------|--------|------|
| `core/config.py` | +5 行 | `enable_skill_evolution` |
| `app/cli.py` | +3 行 | `--skill-evolution` |
| `app/bootstrap.py` | +6 行 | CLI > env var 优先级 |
| `runtime/host.py` | +30 行 | `_on_run_finished(processed_input)`, try/except 隔离 |
| `runtime/factory.py` | +18 行 | init SkillEvolutionManager + load_state() |
| `runtime/loop.py` | +10 行 | clear buffer + 传递 processed_input |
| `extensions/tracing/protocol.py` | +5 行 | `EVOLUTION_TRACE_EVENTS` dict |
| `extensions/tracing/logger.py` | +15 行 | `_current_run_events` 缓冲 |
| `extensions/tracing/__init__.py` | +5 行 | `NullTraceLogger` 兼容接口 |
| `extensions/skills/loader.py` | +20 行 | `set_overlay_dir()` |

---

## 4. 状态机

```
                           ┌─────────────────────┐
                           │       STABLE        │
                           └──────────┬──────────┘
                                      │
               ┌──────────────────────┴──────────────────────┐
               │                                             │
    Keyword Match + LLM Confirm                       Buffer Ready
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
                                                             STABLE (Cooldown / PAUSED)
```

---

## 5. 简化策略（相比 TRD V1）

| 维度 | TRD | 本方案 |
|------|-----|--------|
| 异常阈值 | 5 traces, 3 tasks | 3 traces, 2 runs |
| 观察窗口 | 15 任意任务 | 3 相关 PASS，最多 15 相关 |
| 冷却期 | 10 tasks | 3 tasks |
| 配置 | YAML | Python dataclass + 环境变量 |
| 去重 | task_id 语义 | persistent_run_id |
| 文件锁 | mutex | threading.Lock |
| 语义去重 | 向量 db | 文本指纹 |
| Hotfix | 关键词直接写入 | 两层过滤 (初筛+LLM) |
| 写入目标 | 源码 skills/ | memory/ overlay |
| 状态管理 | 全局 | per-Skill 独立 |
| 跨重启 | 无 | state.json 原子保存 |
| CORE_TRACE | 新增事件 | 独立 EVOLUTION_TRACE_EVENTS |
| NullTraceLogger | 不支持 | 兼容接口 |
| Review LLM | 无隔离 | try/except 隔离 |
