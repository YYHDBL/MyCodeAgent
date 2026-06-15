# Skill Evolution — 集成点：现有文件修改汇总

**涉及文件：10 个现有文件需要修改。**

---

## 1. `core/config.py` — 新增字段

```python
class Config(BaseModel):
    # ... 已有字段保持不变 ...

    # 新增
    enable_skill_evolution: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            # ... 已有字段保持不变 ...
            enable_skill_evolution=os.getenv("SKILL_EVOLUTION_ENABLED", "false").lower()
                in {"1", "true", "yes", "y", "on"},
        )
```

---

## 2. `app/cli.py` — CLI 参数

```python
def build_parser():
    parser = argparse.ArgumentParser(...)
    # ... 已有参数 ...
    parser.add_argument(
        "--skill-evolution", action="store_true",
        help="enable controlled skill evolution (experimental)",
    )
    return parser
```

---

## 3. `app/bootstrap.py` — 优先级

```python
def build_runtime(args, ...):
    ...
    # CLI 参数优先，环境变量 fallback
    skill_evolution_enabled = (
        getattr(args, "skill_evolution", False)
        or config.enable_skill_evolution
    )
    agent_kwargs["enable_skill_evolution"] = skill_evolution_enabled
    ...
```

---

## 4. `runtime/host.py` — 钩子

```python
class CodeAgent(Agent):
    def __init__(
        self, ...,
        enable_skill_evolution: bool = False,  # ← 新增参数
        ...
    ):
        ...
        self._skill_evolution_manager = None   # ← 新增属性

    def _on_run_finished(self, processed_input: str):  # ← 新增方法
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

---

## 5. `runtime/factory.py` — 初始化

```python
class RuntimeComponentFactory:
    def initialize_persistence(self):
        # ... 已有逻辑 ...

        # 新增 — Skill Evolution 初始化
        if getattr(host, "enable_skill_evolution", False) and host._skill_loader is not None:
            from extensions.skill_evolution.config import EvolutionConfig
            from extensions.skill_evolution.state_machine import SkillEvolutionManager

            overlay_dir = Path(host.project_root) / "memory" / "skill_evolution" / "active"
            host._skill_evolution_manager = SkillEvolutionManager(
                skill_loader=host._skill_loader,
                llm=host.llm,
                config=EvolutionConfig(enabled=True),
                overlay_dir=overlay_dir,
                on_skills_changed=lambda: host._refresh_skills_prompt(),  # ← 回调
            )
            host._skill_evolution_manager.load_state()  # 跨重启恢复
            host._skill_loader.set_overlay_dir(overlay_dir)
```

> `on_skills_changed` 回调使 SkillEvolutionManager 在 patch/Candidate/promote/rollback 后通知 host 刷新 prompt，避免 state_machine 直接依赖 host。

---

## 6. `runtime/loop.py` — 接线

```python
class RuntimeRunner:
    def _prepare_run(self, input_text, show_raw):
        ...
        trace_logger = host.trace_logger
        trace_logger.clear_current_run_events()  # ← 新增：清空上轮事件
        host._run_id += 1
        ...

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
                host._on_run_finished(processed_input=raw_input)  # ← 新增
        return response_text
```

---

## 7. `extensions/tracing/protocol.py` — 新事件

```python
# 不修改 CORE_TRACE_EVENTS （Phase 0 frozen）

EVOLUTION_TRACE_EVENTS: dict[str, TraceEventSpec] = {
    "skill_evolution_event": TraceEventSpec(("event_type", "skill_id", "details")),
}

__all__ = [..., "EVOLUTION_TRACE_EVENTS"]  # 扩展导出
```

---

## 8. `extensions/tracing/logger.py` — 内存缓冲

```python
class TraceLogger:
    def __init__(self, ...):
        ...
        self._current_run_events: list[dict] = []  # 新增

    def log_event(self, event, payload, step=0):
        ...
        if self.enabled:
            event_obj = {"ts": ..., "session_id": ..., "step": step, "event": event, "payload": safe_payload}
            self._current_run_events.append(event_obj)  # 新增
            ...

    def get_current_run_events(self) -> list[dict]:   # 新增
        return list(self._current_run_events)

    def clear_current_run_events(self):               # 新增
        self._current_run_events.clear()
```

---

## 9. `extensions/tracing/__init__.py` — NullTraceLogger 兼容

```python
class NullTraceLogger:
    # ... 已有成员 ...

    def get_current_run_events(self) -> list[dict]:   # 新增
        return []

    def clear_current_run_events(self):               # 新增
        pass
```

---

## 10. `extensions/skills/loader.py` — overlay 支持

```python
class SkillLoader:
    def __init__(self, project_root: str, skills_dir: str = "skills"):
        ...
        self._overlay_dir: Path | None = None  # 新增

    def set_overlay_dir(self, path: Path | None):      # 新增
        self._overlay_dir = path
        self._skills.clear()

    def scan(self) -> List[SkillMeta]:
        """
        改动：原有的单目录 rglob 扫描改为双目录合并扫描。
        overlay 存在的同名 Skill 覆盖源码版本。
        """
        files: dict[str, Path] = {}
        for path in Path(self._project_root, self._skills_dir).rglob("SKILL.md"):
            key = str(path.relative_to(Path(self._project_root, self._skills_dir)))
            files[key] = path
        if self._overlay_dir and self._overlay_dir.exists():
            for path in self._overlay_dir.rglob("SKILL.md"):
                key = str(path.relative_to(self._overlay_dir))
                files[key] = path  # overlay 覆盖

        skills = []
        for path in sorted(files.values()):
            meta = self._parse_skill_file(path)
            if meta:
                skills.append(meta)
        self._skills = skills
        return skills
```

> overlay 逻辑直接插入现有 `scan()` 方法内部，不存在独立的 `_iter_skill_files()` 方法。

---

## 总结

| 文件 | 改动量 | 风险 |
|------|--------|------|
| `core/config.py` | +5 | 低 — 纯加字段 |
| `app/cli.py` | +3 | 低 — 纯加参数 |
| `app/bootstrap.py` | +6 | 低 — 扩展条件 |
| `runtime/host.py` | +30 | 中 — 新增 try/except 钩子 |
| `runtime/factory.py` | +18 | 中 — 新增初始化分支 |
| `runtime/loop.py` | +10 | 中 — 改动关键循环 |
| `tracing/protocol.py` | +5 | 低 — 不修改已有 dict |
| `tracing/logger.py` | +15 | 低 — 加内部字段 |
| `tracing/__init__.py` | +5 | 低 — NullTraceLogger 加方法 |
| `skills/loader.py` | +20 | 中 — 改动文件扫描逻辑 |

**所有修改在 `enable_skill_evolution=False`（默认）时不改变任何行为。**
