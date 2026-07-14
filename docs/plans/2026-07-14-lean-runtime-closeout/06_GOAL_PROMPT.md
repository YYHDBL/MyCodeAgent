# GPT-5.5 Goal Prompt

Run Codex/GPT-5.5 from this worktree:

```bash
cd /Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712
```

Then paste the following prompt:

```text
/goal 将 MyCodeAgent 的 lean-runtime-20260712 分支完成到“release-ready、但尚未自动集成”的状态。持续执行，直到 docs/plans/2026-07-14-lean-runtime-closeout/05_ACCEPTANCE_CRITERIA.md 中所有验收项都有本轮新鲜、可复现的通过证据，并完成 FINAL_REPORT.md 与 INTEGRATION_HANDOFF.md。不要因为某个子任务完成就提前结束。

唯一允许修改的实现工作区是：
/Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712

禁止修改、stash、reset、checkout、commit、覆盖或删除原工作区：
/Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent
该工作区有六处用户自己的未提交修改，其中多处与 lean 分支删除的 Skill Evolution 文件冲突。最终只生成安全的集成交接文档，不执行 merge、rebase、push，也不替用户决定这些修改的去留。

开始前必须按顺序完整阅读：
1. docs/plans/2026-07-14-lean-runtime-closeout/00_START_HERE.md
2. docs/plans/2026-07-14-lean-runtime-closeout/01_GOAL.md
3. docs/plans/2026-07-14-lean-runtime-closeout/02_MILESTONES.md
4. docs/plans/2026-07-14-lean-runtime-closeout/03_TASK_GRAPH.md
5. docs/plans/2026-07-14-lean-runtime-closeout/04_EXECUTION_PROTOCOL.md
6. docs/plans/2026-07-14-lean-runtime-closeout/05_ACCEPTANCE_CRITERIA.md
7. docs/plans/2026-07-14-lean-runtime-closeout-design.md
8. docs/plans/2026-07-14-lean-runtime-closeout/MASTER_IMPLEMENTATION_PLAN.md
9. 原计划 docs/plans/2026-07-12-lean-runtime/ 下的 00_START_HERE.md、01_GOAL.md、02_TARGET_ARCHITECTURE.md、DECISIONS.md、PROGRESS.md、FINAL_REPORT.md。

然后严格按 docs/plans/2026-07-14-lean-runtime-closeout/tasks/ 下 R0-01 到 R5-01 的依赖顺序执行。一个 task 文件是一个 agent 的最大范围；每个任务单独提交。只有 03_TASK_GRAPH.md 明确列出的任务可以在独立 worktree 中并行，集成顺序也必须按该文件执行。主 Goal agent 负责检查每个子 agent 的 diff、重新运行任务门禁、更新 PROGRESS.md 和 DECISIONS.md，不能只相信子 agent 的完成声明。

执行原则：
- 行为修改必须先写失败回归，再做最小实现，再跑 GREEN 和完整回归。
- 遇到异常测试失败先做系统化根因诊断，不得靠放宽断言、跳过测试或增加全局 ignore 通过。
- 首先修复 --enable-verification-agent 启动 NameError，并增加从 build_runtime 进入的无网络回归测试。
- Ruff 必须重新执行 F821、E722、F401、F541、F841；稳定产品包必须通过 E402。不得保留这些规则的全局忽略。
- JSONL 是唯一 trace 产物。保留并证明现有 session_summary 的 steps、tools_used、token totals；不要恢复 HTML renderer、extensions/tracing/protocol.py 或 runtime/evals.py。
- 从 core/llm.py 的 provider 配置分支、dotenv 重复加载、request/retry 重复，以及 runtime/subagents.py 的无调用 response adapter 中减重。provider 元数据应是数据表，不要增加 provider 框架或新依赖。
- 不要为了行数删除 transcript recovery、JSONL、Task、Skills、MCP、completion gate、安全校验、七工具契约或有效测试。
- scripts/check_release_metrics.py 使用用户批准的 15,000 行阈值；禁止修改 source roots、排除规则和七工具上限，禁止用重新分类代码制造通过。
- RuntimeRunner 的 650 行是已有记录的建议目标，不要为了行数拆出第二个 loop 或单调用者 stage 抽象。
- 每完成一个任务，记录 RED/GREEN/回归命令、精确结果、LOC/工具/依赖变化和 commit SHA。每个 milestone 后跑完整门禁。

最终停止条件：
1. enable_verification_agent=True 的运行时装配成功，默认仍不创建 verifier；
2. uv run pytest -q、场景测试、MCP 可选测试全部通过；
3. 普通 Ruff、关键 F/E 规则、稳定包 E402 全部通过；
4. uv lock --check 通过；
5. 新临时 venv 安装后，在无关 Git 仓库运行 mycodeagent --help，3 秒内 exit 0；
6. scripts/check_release_metrics.py exit 0，稳定生产 Python ≤15,000，工具正好是 Bash/Edit/Glob/Grep/Read/Task/TodoWrite，核心依赖 ≤5；
7. Teams 和 Skill Evolution 在稳定源中无引用；
8. JSONL session_summary 契约通过，文档准确区分保留 metrics 与删除 evaluator；
9. 原工作区六处用户修改的 status 与 R0 hash 前后一致；
10. FINAL_REPORT.md 对每个 acceptance ID 给出本轮命令和结果，状态只能写“RELEASE-READY BRANCH — NOT YET INTEGRATED”；
11. INTEGRATION_HANDOFF.md 写清 base/head、所有 closeout commits、预期冲突、用户可选处理方案及集成后复验命令；
12. lean-runtime-20260712 工作区最终 clean；不 merge、不 push。

如果 R3 重构后指标仍失败，不允许继续随机删代码。先记录精确超额和差异，只能在已经批准的 core/llm.py、runtime/subagents.py 或严格 lint 暴露的死代码范围内提出一个新的、行为保持的窄任务，经主 Goal agent 对照 01_GOAL.md 审核后再执行。任何必须牺牲上述保留能力才能通过的情况都要标记为真实 blocker，而不是伪造完成。
```
