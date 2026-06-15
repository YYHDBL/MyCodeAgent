# Skill Evolution — Adapter 与路由层

**文件：** `extensions/skill_evolution/adapter.py`, `extensions/skill_evolution/feedback_router.py`  
**依赖改动：** `extensions/tracing/logger.py`, `extensions/tracing/__init__.py`

---

## 1. TraceLogger 内存缓冲扩展

### 1.1 TraceLogger 新增成员

```python
# extensions/tracing/logger.py

class TraceLogger:
    def __init__(self, ...):
        ...
        self._current_run_events: list[dict] = []   # per-run 内存缓冲

    def log_event(self, event, payload, step=0):
        ...
        if self.enabled:
            event_obj = {"ts": ..., "session_id": ..., "step": step, "event": event, "payload": safe_payload}
            self._current_run_events.append(event_obj)  # ← 新增
            ...

    def get_current_run_events(self) -> list[dict]:
        return list(self._current_run_events)         # 返回副本

    def clear_current_run_events(self):
        self._current_run_events.clear()
```

### 1.2 NullTraceLogger 兼容

```python
# extensions/tracing/__init__.py

class NullTraceLogger:
    # ... 已有成员保持不变 ...

    def get_current_run_events(self) -> list[dict]:
        return []                          # tracing 关闭时返回空列表

    def clear_current_run_events(self):
        pass                              # no-op
```

### 1.3 生命周期

```
loop._prepare_run()  → trace_logger.clear_current_run_events()
loop._react_loop()   → trace_logger.log_event() × N  (自动累积)
loop._finish_run()   →
host._on_run_finished(processed_input) → trace_logger.get_current_run_events() → SkillEvolutionManager
```

空列表时 adapter 将生成 `attributing_skill = None` 的 RolloutRecord，整个 Evolution 流程跳过（不崩溃）。

---

## 2. adapter.py — Trace → Rollout 适配器

### 2.1 接口

```python
def trace_events_to_rollout(
    events: list[dict],
    session_id: str,
    run_id: int,
    processed_input: str,
) -> RolloutRecord:
    """从 trace 内存事件缓冲聚合为 RolloutRecord。"""

def extract_skills_invoked(events: list[dict]) -> list[str]:
    """从 tool_call 事件提取 Skill 名称，去重排序。"""

def resolve_attribution(skills_invoked: list[str]) -> str | None:
    """恰好 1 个 → 返回名称；0 或 ≥2 → 返回 None。"""

def detect_user_feedback(events: list[dict]) -> dict:
    """检测用户纠正消息，返回 {is_long_term, is_explicit_correction, raw_text}。"""

def detect_error_signature(rollout: RolloutRecord, proposal: Proposal) -> bool:
    """检查 Proposal 目标错误是否在本次 run 中复现。V1 简化：检查 rollout.error_signatures 是否包含 proposal.error_signature。"""
```

### 2.2 聚合逻辑（每条对应一个 trace 事件）

| RolloutRecord 字段 | 来源 |
|-------------------|------|
| `persistent_run_id` | `f"{session_id}:{run_id}"` |
| `input_fingerprint` | `SHA256(processed_input)[:12]` |
| `skills_invoked` | `tool_call` 中 `tool == "Skill"`，收集 args.name |
| `attributing_skill` | `resolve_attribution(skills_invoked)` |
| `task_success` | `terminal.reason in {"completed", "completed_unverified"}` |
| `hard_error` | `terminal.reason in {"model_error", "tool_error_unrecoverable", "token_budget"}` |
| `human_intervention` | 检查到 `tool_call(tool=="AskUser")` 且对应 `tool_result` 中用户给了非空回复 |
| `user_feedback_text` | `detect_user_feedback()` |
| `is_long_term_instruction` | 用户消息含长期关键词（"以后都"等）|
| `is_explicit_correction` | 用户消息含纠正关键词（"不对"等）|

**关键修正：**
- **不使用 `session_summary`** — 该事件仅在 `TraceLogger.finalize()` 时产生，不是每个 run 都有。
- **`human_intervention` 不依赖 user 消息** — AskUser 的回答在 `tool_result` 中，不是独立 user 事件。
- **Skill 归属：** 0 个 Skill → attribution=None → 跳过演进；≥2 个 Skill → attribution=None → 跳过（歧义）。

### 2.3 关键词列表

```python
LONG_TERM_KEYWORDS = [
    "以后都", "下次遇到", "以后先做", "以后要", "以后再",
    "后续都", "每次都要", "从今往后", "一直要",
]
CORRECTION_KEYWORDS = [
    "不对", "错误", "不要用", "别再", "改正", "修复", "纠正",
    "应该是", "正确做法", "问题在于",
]
```

---

## 3. feedback_router.py — 反馈路由

```python
class FeedbackRouter:
    def route(self, rollout: RolloutRecord) -> FeedbackRoute
```

### 3.1 路由逻辑（初筛，允许假阳性）

```
rollout.is_long_term_instruction == True
  → USER_HOTFIX_CANDIDATE   # 称 "CANDIDATE"，因为 LLM 终判可能拒绝

rollout.attributing_skill is None
  → NORMAL_ROLLOUT          # 无归属 Skill，不触发任何演化

rollout.task_success == False 或 rollout.hard_error 或 rollout.human_intervention
  → ABNORMAL_ROLLOUT

否则
  → NORMAL_ROLLOUT
```

### 3.2 要点

- FeedbackRouter **只做初筛**，允许假阳性通过（用户说"以后都这么做吧"作为一次性确认）。真正的语义判断在 HotfixGenerator 的 LLM 终判中完成。
- `attributing_skill == None` 是早期短路——无归属的任务直接走 NORMAL_ROLLOUT，不进入 buffer。
