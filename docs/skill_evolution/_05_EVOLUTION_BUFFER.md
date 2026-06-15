# Skill Evolution — 异常轨迹缓存

**文件：** `extensions/skill_evolution/evolution/buffer.py`

---

## 1. 职责

按 Skill 分区缓存异常 Rollout。每个 Skill 独立一个 buffer 文件。达到阈值后触发 Batch Review。

---

## 2. 接口

```python
class AbnormalTrajectoryBuffer:
    def __init__(self, buffer_dir: Path, config: EvolutionConfig):
        """
        buffer_dir: memory/skill_evolution/active/
        每个 Skill 的 buffer: <buffer_dir>/<skill_name>/.evolution/buffer.jsonl
        """

    def append(self, rollout: RolloutRecord):
        """追加异常 Rollout。按 persistent_run_id 去重。"""

    def get_batch(self, skill_name: str) -> list[RolloutRecord]:
        """返回 consumed=false 的所有 Rollout。"""

    def should_review(self, skill_name: str) -> bool:
        """consumed=false 的记录数 ≥3 且 distinct persistent_run_id ≥ 2 → True。"""

    def count_distinct_runs(self, skill_name: str) -> int:
        """consumed=false 的记录中，persistent_run_id 去重计数。"""

    def mark_consumed(self, skill_name: str, run_ids: list[str]):
        """将指定 persistent_run_id 的所有行标记为 consumed=true（原地重写文件）。"""

    def clear(self, skill_name: str):
        """清空 buffer 文件。"""
```

---

## 3. 存储格式

**文件：** `memory/skill_evolution/active/<skill_name>/.evolution/buffer.jsonl`

每行一条 JSON，consumed 字段内联：

```jsonl
{"consumed": false, "rollout": {"persistent_run_id": "s-abc:1", "attributing_skill": "code-review", "task_success": false, "hard_error": true, "error_signatures": ["TOOL_SELECTION_INCORRECT"], "summary": "..."}}
{"consumed": true,  "rollout": {"persistent_run_id": "s-abc:2", ...}}
{"consumed": false, "rollout": {"persistent_run_id": "s-xyz:3", ...}}
```

**消费标记方式：** `mark_consumed(run_ids)` 读取整个 buffer 文件，对 `persistent_run_id` 在列表中的行把 `consumed` 改为 `true`，原地重写。buffer 规模很小（< 10 条），重写开销可忽略。

**读取时过滤：** `get_batch()` 和 `should_review()` 只统计 `consumed == false` 的行。

---

## 4. 去重策略

- 主 key：`persistent_run_id` = `f"{session_id}:{run_id}"`
- `append()` 时检查该 key 是否已在 buffer 中存在（无论 consumed 状态）→ 如果已存在则跳过
- 重启后 session_id 不同 → 天然不与历史冲突

---

## 5. 触发条件

`should_review(skill_name)` 返回 True 当：
1. buffer 中 `consumed == false` 的行数 ≥ `config.minimum_abnormal_traces`（默认 3）
2. 这些行的 `persistent_run_id` 去重 ≥ `config.minimum_distinct_runs`（默认 2）

> state_machine 在调用 `should_review()` 之前检查 state == STABLE，确保不在 EVALUATING/COOLDOWN/PAUSED 期间触发。

---

## 6. 总览图变更

由于 consumed 标记内联在每行，不再需要单独的 sidecar 文件或 "buffer 元数据" 概念。

```
memory/skill_evolution/active/code-review/.evolution/
├── buffer.jsonl         # 每行: {"consumed": bool, "rollout": {...}}
├── successes.jsonl      # 近期成功轨迹摘要
├── rejected.jsonl       # 被拒绝的 Proposal
├── proposals/           # active + 历史 Proposal
├── versions/            # Skill 版本快照
└── (state 在上级 state.json)
```
