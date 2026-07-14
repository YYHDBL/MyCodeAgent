# [已归档] Harness Execution Protocol

> **归档说明**：开发执行协议，所有 Phase 均已完成，不再需要。保留供参考。

本文档规定 agent 如何执行 `docs/HARNESS_TASK_BREAKDOWN.md`。路线图回答“做什么”，任务拆分回答“拆成哪些任务”，本协议回答“如何安全执行”。

## 1. 执行粒度

- 默认一次只执行一个 Phase。
- 不允许在未完成当前 Phase 验收前提前实现后续 Phase。
- 如果某个 Phase 过大，可以拆成多个子 goal，但必须保持任务顺序。
- 每个 Phase 完成后暂停，等待 review 或明确继续指令。

推荐顺序：

```text
Goal 1: Phase 0
Goal 2: Phase 1
Goal 3: Phase 2
Review: Batch A
Goal 4: Phase 3
Goal 5: Phase 4
Goal 6: Phase 5
Review: Batch B
Goal 7: Phase 6A
Goal 8: Phase 6B
Review: Harness Core Done
Goal 9: Phase 7
Goal 10: Phase 8
Review: Extension Done
Goal 11: Phase 9
```

## 2. 每个 Phase 的固定流程

每个 Phase 都必须按以下流程执行：

1. 阅读 `docs/HARNESS_ROADMAP.md`、`docs/HARNESS_TASK_BREAKDOWN.md` 和本协议中对应阶段。
2. 检查当前代码状态、相关模块和已有测试。
3. 写一份简短 Phase 实施计划，明确本阶段要改哪些边界。
4. 逐个执行该 Phase 下的子任务。
5. 每个子任务完成后补充测试、Trace 断言或文档验收。
6. Phase 完成后运行相关测试。
7. Phase 完成后运行全量测试。
8. 更新受影响文档。
9. 总结验收结果、剩余风险和下一阶段建议。
10. 提交 commit。

## 3. 不允许的行为

- 不允许为了通过测试删除、弱化或跳过测试。
- 不允许在当前 Phase 中实现后续 Phase 的功能。
- 不允许把临时兼容代码包装成长期架构。
- 不允许让 `runtime/loop.py` 继续堆积无边界的隐式布尔状态。
- 不允许把动态运行时信息混入稳定系统提示词。
- 不允许把 Session Memory、Transcript 和 Model View 混成同一份 messages 数组。
- 不允许把 Bash 正则分类描述成安全沙箱。
- 不重新引入已归档的多 Agent 研究运行时。
- 不允许为了快速完成而牺牲 Trace 可解释性。

## 4. 测试要求

每个 Phase 至少满足：

- 新增或修改的核心行为有单元测试。
- 影响 RuntimeRunner、ToolExecutor、ContextEngine 或 Session 的改动有集成测试。
- 涉及 Trace 的改动必须断言关键事件字段。
- 涉及错误恢复的改动必须测试成功恢复和超过上限失败两种路径。
- 涉及权限的改动必须测试 allow、deny 和无法判断的默认关闭路径。
- 涉及 resume 的改动必须测试 completed 和 uncertain 两种工具状态。

Phase 完成前必须运行：

```bash
.venv/bin/python -m pytest -q
```

如果全量测试无法运行，必须说明原因、已经运行的替代测试和剩余风险。

## 5. Trace 与验收要求

每个核心机制不只要“能跑”，还要能从 Trace 解释：

- 当前处于哪个 step。
- 为什么进入下一轮。
- 为什么最终结束。
- 工具为什么被允许、拒绝或预算压缩。
- Completion Gate 为什么通过或阻塞。
- Recovery 为什么触发、重试几次、为什么停止。
- Context 为什么 compact，模型看到的是 full history 还是 projection。

如果 Trace 不能解释某个新机制，视为该机制没有完成。

## 6. 文档要求

每个 Phase 完成后至少检查：

- `docs/HARNESS.md` 是否需要更新当前有效架构。
- `docs/HARNESS_ROADMAP.md` 是否需要标记阶段状态。
- `docs/HARNESS_TASK_BREAKDOWN.md` 是否需要补充实际执行中的取舍。
- `README.md` 是否受用户可见能力影响。

文档不能写成完成清单堆砌，必须说明边界和不变量。

## 7. Commit 规则

每个 Phase 完成后提交一个或多个 commit。

建议格式：

```bash
git add <changed-files>
git commit -m "feat(harness): complete phase N <short name>"
```

如果 Phase 只改文档：

```bash
git commit -m "docs(harness): add phase N execution plan"
```

提交前必须确认：

- `git diff --check` 通过。
- 测试结果已记录在最终总结里。
- 没有无关文件被误提交。

## 8. Goal 使用建议

不要创建一个覆盖所有 Phase 的巨大 goal。每个 goal 应该只覆盖一个 Phase，最多覆盖一个 Batch。

推荐 goal 结构：

```text
目标：完成 docs/HARNESS_TASK_BREAKDOWN.md 中的 Phase X。

约束：
- 严格遵守 docs/HARNESS_EXECUTION_PROTOCOL.md。
- 只执行 Phase X，不实现后续 Phase。
- 每个子任务都要有测试、Trace 断言或文档验收。
- Phase 完成后运行全量测试。
- 更新受影响文档。
- 提交 commit。
- 最后总结完成项、测试结果、剩余风险和下一阶段建议。
```

如果 goal 执行中发现任务拆分不合理，应先更新任务拆分文档并说明原因，而不是继续硬做。
