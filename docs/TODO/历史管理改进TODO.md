# 历史管理改进 TODO

## 背景
当前 ReAct 设计中，scratchpad 每轮清空，导致模型不记得上一轮的工具调用结果。详见 `ReAct历史管理设计分析.md`

---

## TODO 列表

### P0: 工具摘要层（核心功能）

- [ ] 设计 `ToolSummary` 数据结构
  - 工具名称、操作目标、摘要信息、时间戳
- [ ] 实现 `ToolSummaryManager` 类
  - 记录每个工具操作的摘要
  - 支持查询最近 N 轮的工具操作
- [ ] 修改 ReActEngine
  - 在工具调用后生成摘要
  - 在构建 prompt 时注入摘要信息

**相关文件**：
- `core/message.py` - 新增 ToolSummary 消息类型
- `agentEngines/ReActEngine.py` - 集成摘要管理

---

### P1: 智能历史注入

- [ ] 实现 `build_context_summary()` 方法
  - 从工具摘要中生成可读的上下文描述
- [ ] 修改 prompt 模板
  - 添加 `{recent_operations}` 占位符
- [ ] 配置化
  - 可配置保留最近 N 轮的摘要（默认 5 轮）

**相关文件**：
- `agentEngines/ReActEngine.py`
- `prompts/tools_prompts/react_prompt.py`

---

### P2: 按需详情恢复

- [ ] 实现 `ToolHistory` 类
  - 完整存储工具调用结果（带索引）
- [ ] 添加智能恢复机制
  - 检测用户问询是否需要历史详情
  - 自动注入相关的历史工具结果
- [ ] LRU 缓存
  - 限制内存使用，自动淘汰旧记录

**相关文件**：
- 新增 `core/tool_history.py`
- `agentEngines/ReActEngine.py`

---

### P3: 自动压缩（长期优化）

- [ ] 实现对话摘要算法
  - 基于 LLM 的智能摘要
  - 或基于规则的关键信息提取
- [ ] 分层存储
  - 热数据：上下文中的摘要
  - 温数据：最近几轮的完整记录
  - 冷数据：压缩后的历史
- [ ] 上下文窗口监控
  - 接近限制时触发压缩

**相关文件**：
- 新增 `core/context_manager.py`

---

## 设计草图

```python
# 工具摘要结构
@dataclass
class ToolSummary:
    tool_name: str          # "Read", "Edit", "Grep" 等
    target: str             # 操作目标（文件路径、搜索词等）
    summary: str            # 人类可读的摘要
    timestamp: float        # 时间戳
    full_result: Optional[str] = None  # 完整结果（可选保留）

# 摘要管理器
class ToolSummaryManager:
    def __init__(self, max_summaries: int = 20):
        self.summaries: deque[ToolSummary] = deque(maxlen=max_summaries)

    def add(self, tool_name: str, target: str, result: str):
        # 生成摘要并存储
        pass

    def get_recent(self, n: int = 5) -> List[ToolSummary]:
        # 获取最近 N 条摘要
        pass

    def format_for_prompt(self) -> str:
        # 格式化为 prompt 可用的文本
        pass
```

---

## 参考资料

- [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Cursor Shadow Workspace](https://cursor.com/blog/shadow-workspace)
- [AutoGPT Memory System](https://mem0.ai/blog/memory-in-agents-what-why-and-how)
