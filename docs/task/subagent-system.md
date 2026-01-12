# OpenCode Subagent 系统设计文档

## 目录

1. [系统概述](#系统概述)
2. [核心概念](#核心概念)
3. [Task 工具详解](#task-工具详解)
4. [Agent 系统](#agent-系统)
5. [权限隔离](#权限隔离)
6. [会话管理](#会话管理)
7. [事件总线](#事件总线)
8. [完整工作流](#完整工作流)

---

## 系统概述

OpenCode 的 Subagent 系统是一个分层任务执行架构，允许主代理（Primary Agent）将复杂任务委托给专门的子代理（Subagent）执行。每个子代理在独立的会话中运行，具有独立的权限规则和工具访问能力。

### 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户会话 (User Session)                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                     Primary Agent (build/plan)                 │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │  │
│  │  │   Read      │  │   Edit      │  │      Task Tool      │   │  │
│  │  └─────────────┘  └─────────────┘  └──────────┬──────────┘   │  │
│  │                                              │                │  │
│  └──────────────────────────────────────────────┼────────────────┘  │
│                                                 │                   │
│                              ┌──────────────────┼──────────────────┐│
│                              │                  │                  ││
│                              ▼                  ▼                  ││
│  ┌───────────────────┐ ┌──────────────────┐ ┌──────────────────┐ │
│  │  Subagent Session │ │  Subagent Session│ │  Subagent Session│ │
│  │       #1          │ │       #2         │ │       #3         │ │
│  ├───────────────────┤ ├──────────────────┤ ├──────────────────┤ │
│  │ Agent: general    │ │ Agent: explore   │ │ Agent: custom    │ │
│  │ Tools: [受限]     │ │ Tools: [只读]    │ │ Tools: [自定义]  │ │
│  │ Status: running   │ │ Status: done     │ │ Status: error    │ │
│  └───────────────────┘ └──────────────────┘ └──────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         事件总线 (Event Bus)                     │
│  • session.created     • session.updated                        │
│  • message.created     • message.part.updated                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心概念

### 1. Agent（代理）

Agent 是具有特定能力和权限规则的执行实体。每个 Agent 包含：

```python
@dataclass
class AgentInfo:
    """代理配置信息"""
    name: str                      # 代理唯一标识符
    mode: Literal["primary", "subagent", "all"]  # 代理模式
    description: Optional[str]     # 功能描述
    native: bool                   # 是否为内置代理
    hidden: bool                   # 是否在列表中隐藏

    # 权限配置
    permission: Dict[str, Any]     # 权限规则集

    # AI 模型配置
    model: Optional[ModelConfig]   # 覆盖默认模型
    temperature: Optional[float]   # 温度参数
    top_p: Optional[float]         # Top-p 采样

    # 自定义配置
    prompt: Optional[str]          # 自定义系统提示词
    options: Dict[str, Any]        # 额外选项
    steps: Optional[int]           # 最大执行步骤


@dataclass
class ModelConfig:
    """AI 模型配置"""
    provider_id: str    # 提供商 ID (如 "anthropic")
    model_id: str       # 模型 ID (如 "claude-opus-4-5")
```

### 2. Session（会话）

Session 是 Agent 执行的上下文环境，包含消息历史、权限配置等：

```python
@dataclass
class SessionInfo:
    """会话信息"""
    id: str                        # 会话唯一 ID
    project_id: str                # 所属项目 ID
    directory: str                 # 工作目录
    parent_id: Optional[str]       # 父会话 ID（子会话时存在）

    title: str                     # 会话标题
    version: str                   # 版本号

    # 时间戳
    time: SessionTime
    permission: Optional[Dict]     # 会话级权限覆盖

    # 变更摘要
    summary: Optional[Summary]
    revert: Optional[RevertInfo]


@dataclass
class SessionTime:
    created: int      # 创建时间戳
    updated: int      # 更新时间戳
    compacting: Optional[int]  # 压缩开始时间
    archived: Optional[int]    # 归档时间
```

### 3. Message（消息）

Message 是 Session 中的通信单元：

```python
@dataclass
class MessageInfo:
    """消息信息"""
    id: str
    session_id: str
    role: Literal["user", "assistant", "system"]
    model_id: str
    provider_id: str
    created: int

    # AI 使用统计
    usage: Optional[UsageStats]


@dataclass
class UsageStats:
    """AI 使用统计"""
    prompt_tokens: int
    completion_tokens: int

    # 输入/输出详情
    input_tokens: Dict[str, int]    # {cache, read, tools}
    output_tokens: Dict[str, int]   # {cache, read, tools}
    total_price: Decimal
```

---

## Task 工具详解

Task 工具是 Primary Agent 调用 Subagent 的桥梁。

### 参数定义

```python
class TaskParams(BaseModel):
    """Task 工具参数"""
    description: str = Field(
        description="任务的简短描述（3-5 个词）"
    )
    prompt: str = Field(
        description="给 subagent 的详细任务指令"
    )
    subagent_type: str = Field(
        description="要使用的 subagent 类型名称"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="现有 Task 会话 ID，用于继续执行"
    )
    command: Optional[str] = Field(
        default=None,
        description="触发此任务的命令"
    )
```

### 执行流程

```python
async def execute_task(
    params: TaskParams,
    context: ToolContext
) -> TaskResult:
    """
    Task 工具执行流程

    步骤 1: 权限检查
    步骤 2: 获取/创建子会话
    步骤 3: 设置进度监听
    步骤 4: 执行 Subagent
    步骤 5: 收集结果
    """

    # ============================================================
    # 步骤 1: 权限检查
    # ============================================================
    if not context.extra.get("bypassAgentCheck"):
        await context.ask(PermissionRequest(
            permission="task",
            patterns=[params.subagent_type],
            always=["*"],
            metadata={
                "description": params.description,
                "subagent_type": params.subagent_type,
            }
        ))

    # ============================================================
    # 步骤 2: 获取/创建子会话
    # ============================================================
    agent = await Agent.get(params.subagent_type)
    if agent is None:
        raise ValueError(f"Unknown agent: {params.subagent_type}")

    # 尝试恢复现有会话或创建新会话
    session = await get_or_create_session(params, context, agent)

    # ============================================================
    # 步骤 3: 设置进度监听
    # ============================================================
    parts_tracker = {}  # 追踪工具调用状态
    unsubscribe = setup_progress_listener(session, context, parts_tracker)

    try:
        # ============================================================
        # 步骤 4: 执行 Subagent
        # ============================================================
        result = await run_subagent(session, agent, params, context)

        # ============================================================
        # 步骤 5: 收集并返回结果
        # ============================================================
        return await format_result(result, session, parts_tracker)

    finally:
        unsubscribe()  # 清理监听器


async def get_or_create_session(
    params: TaskParams,
    context: ToolContext,
    agent: AgentInfo
) -> SessionInfo:
    """获取现有会话或创建新子会话"""

    # 尝试恢复现有会话
    if params.session_id:
        existing = await Session.get(params.session_id)
        if existing:
            return existing

    # 创建新的子会话
    config = await Config.get()

    return await Session.create(
        parent_id=context.session_id,  # 父子关系
        title=f"{params.description} (@{agent.name} subagent)",
        permission=build_subagent_permissions(agent, config)
    )


def build_subagent_permissions(
    agent: AgentInfo,
    config: Config
) -> List[PermissionRule]:
    """
    构建 Subagent 权限规则

    核心原则：防止递归调用
    """
    base_permissions = [
        # 禁止 TodoWrite（防止与主代理冲突）
        PermissionRule(
            permission="todowrite",
            pattern="*",
            action="deny"
        ),
        PermissionRule(
            permission="todoread",
            pattern="*",
            action="deny"
        ),
        # 禁止递归调用 Task（防止无限嵌套）
        PermissionRule(
            permission="task",
            pattern="*",
            action="deny"
        ),
    ]

    # 添加实验性工具权限
    experimental_tools = config.experimental.get("primary_tools", [])
    for tool in experimental_tools:
        base_permissions.append(PermissionRule(
            pattern="*",
            action="allow",
            permission=tool
        ))

    # 合并 Agent 自身权限
    return PermissionNext.merge(
        agent.permission,
        base_permissions
    )


def setup_progress_listener(
    session: SessionInfo,
    context: ToolContext,
    parts_tracker: Dict
) -> Callable:
    """
    设置进度监听器

    通过事件总线实时接收 Subagent 的工具调用状态
    """

    def on_part_updated(event):
        """消息片段更新事件处理"""
        part = event.properties.part

        # 只关心当前会话的工具调用
        if part.session_id != session.id:
            return
        if part.type != "tool":
            return

        # 更新追踪状态
        parts_tracker[part.id] = {
            "id": part.id,
            "tool": part.tool,
            "state": {
                "status": part.state.status,
                "title": part.state.title if part.state.status == "completed" else None
            }
        }

        # 更新元数据（向上级汇报进度）
        context.metadata(
            title=context.current_description,
            metadata={
                "summary": list(parts_tracker.values()),
                "session_id": session.id
            }
        )

    # 订阅事件
    unsubscribe = Bus.subscribe(
        MessageV2.Event.PartUpdated,
        on_part_updated
    )

    return unsubscribe


async def run_subagent(
    session: SessionInfo,
    agent: AgentInfo,
    params: TaskParams,
    context: ToolContext
) -> PromptResult:
    """
    运行 Subagent

    在独立的会话上下文中执行 AI 代理
    """

    # 解析提示词（支持 @-syntax 和文件引用）
    prompt_parts = await SessionPrompt.resolve_prompt_parts(
        params.prompt
    )

    # 确定模型配置
    parent_message = await MessageV2.get(
        session_id=context.session_id,
        message_id=context.message_id
    )

    model = agent.model or ModelConfig(
        model_id=parent_message.model_id,
        provider_id=parent_message.provider_id
    )

    # 设置取消处理
    def cancel():
        SessionPrompt.cancel(session.id)

    context.abort.add_listener("abort", cancel)

    try:
        # 执行提示
        result = await SessionPrompt.prompt(
            message_id=Identifier.ascending("message"),
            session_id=session.id,
            model={
                "model_id": model.model_id,
                "provider_id": model.provider_id
            },
            agent=agent.name,
            tools={
                "todowrite": False,
                "todoread": False,
                "task": False,  # 确保不传递 Task 工具
            },
            parts=prompt_parts
        )

        return result

    finally:
        context.abort.remove_listener("abort", cancel)


async def format_result(
    result: PromptResult,
    session: SessionInfo,
    parts_tracker: Dict
) -> TaskResult:
    """
    格式化并返回结果

    收集所有工具调用摘要和最终文本输出
    """

    # 获取会话中的所有消息
    messages = await Session.messages(session_id=session.id)

    # 提取所有工具调用摘要
    summary = []
    for msg in messages:
        if msg.role == "assistant":
            for part in msg.parts:
                if part.type == "tool":
                    summary.append({
                        "id": part.id,
                        "tool": part.tool,
                        "state": {
                            "status": part.state.status,
                            "title": part.state.title if part.state.status == "completed" else None
                        }
                    })

    # 获取最终文本
    text = result.parts[-1].text if result.parts else ""

    # 构建输出（包含元数据）
    output = f"""{text}

<task_metadata>
session_id: {session.id}
</task_metadata>"""

    return TaskResult(
        title=params.description,
        output=output,
        metadata={
            "summary": summary,
            "session_id": session.id
        }
    )
```

---

## Agent 系统

### 内置 Agent

```python
# Agent 状态管理
class AgentState:
    """
    Agent 配置状态（单例模式）
    """
    _instance: Optional['AgentState'] = None

    def __init__(self):
        self.agents: Dict[str, AgentInfo] = {}

        # 加载内置 Agent
        self._load_builtin_agents()

        # 加载用户自定义 Agent
        await self._load_user_agents()

    def _load_builtin_agents(self):
        """加载内置 Agent 配置"""

        # 默认权限规则
        default_permissions = {
            "*": "allow",
            "doom_loop": "ask",
            "external_directory": {
                "*": "ask",
                Truncate.DIR: "allow"  # 允许读取截断的输出
            },
            "question": "deny",
            "read": {
                "*": "allow",
                "*.env": "deny",
                "*.env.*": "deny",
                "*.env.example": "allow"
            }
        }

        # ============================================================
        # BUILD AGENT - 主开发代理
        # ============================================================
        self.agents["build"] = AgentInfo(
            name="build",
            mode="primary",
            native=True,
            permission=PermissionNext.merge(
                default_permissions,
                {"question": "allow"}  # 允许询问用户
            ),
            options={}
        )

        # ============================================================
        # PLAN AGENT - 规划代理（只读）
        # ============================================================
        self.agents["plan"] = AgentInfo(
            name="plan",
            mode="primary",
            native=True,
            permission=PermissionNext.merge(
                default_permissions,
                {
                    "question": "allow",
                    "edit": {
                        "*": "deny",
                        ".opencode/plan/*.md": "allow"  # 只允许编辑计划文件
                    }
                }
            ),
            options={}
        )

        # ============================================================
        # GENERAL SUBAGENT - 通用子代理
        # ============================================================
        self.agents["general"] = AgentInfo(
            name="general",
            mode="subagent",
            native=True,
            description=(
                "General-purpose agent for researching complex questions "
                "and executing multi-step tasks. Use this agent to execute "
                "multiple units of work in parallel."
            ),
            permission=PermissionNext.merge(
                default_permissions,
                {
                    "todowrite": "deny",  # 不管理 Todo
                    "todoread": "deny"
                }
            ),
            options={}
        )

        # ============================================================
        # EXPLORE SUBAGENT - 代码探索专家
        # ============================================================
        self.agents["explore"] = AgentInfo(
            name="explore",
            mode="subagent",
            native=True,
            description=(
                "Fast agent specialized for exploring codebases. Use this "
                "when you need to quickly find files by patterns, search code "
                "for keywords, or answer questions about the codebase."
            ),
            permission={
                # 白名单模式：默认拒绝
                "*": "deny",
                "grep": "allow",
                "glob": "allow",
                "list": "allow",
                "bash": "allow",
                "webfetch": "allow",
                "websearch": "allow",
                "codesearch": "allow",
                "read": "allow",
                "external_directory": {
                    Truncate.DIR: "allow"
                }
            },
            prompt=PROMPT_EXPLORE,  # 专用提示词
            options={}
        )

        # ============================================================
        # INTERNAL AGENTS - 系统内部使用
        # ============================================================
        self.agents["compaction"] = AgentInfo(
            name="compaction",
            mode="primary",
            native=True,
            hidden=True,  # 不对用户可见
            prompt=PROMPT_COMPACTION,
            permission={"*": "deny"}
        )

        self.agents["title"] = AgentInfo(
            name="title",
            mode="primary",
            native=True,
            hidden=True,
            temperature=0.5,
            permission={"*": "deny"},
            prompt=PROMPT_TITLE
        )

        self.agents["summary"] = AgentInfo(
            name="summary",
            mode="primary",
            native=True,
            hidden=True,
            permission={"*": "deny"},
            prompt=PROMPT_SUMMARY
        )

    async def _load_user_agents(self):
        """从配置文件加载用户自定义 Agent"""
        config = await Config.get()

        for name, agent_config in config.get("agent", {}).items():
            if agent_config.get("disable"):
                continue

            # 更新或创建 Agent
            self.agents[name] = self._create_user_agent(name, agent_config)
```

### Agent 生命周期

```python
class Agent:
    """Agent 管理器"""

    @staticmethod
    async def get(name: str) -> Optional[AgentInfo]:
        """获取指定 Agent"""
        state = await AgentState.get_instance()
        return state.agents.get(name)

    @staticmethod
    async def list() -> List[AgentInfo]:
        """列出所有可用 Agent（排除 primary）"""
        state = await AgentState.get_instance()
        config = await Config.get()

        agents = [
            agent for agent in state.agents.values()
            if agent.mode != "primary"
        ]

        # 按配置的默认 Agent 排序
        default = config.get("default_agent", "build")
        return sorted(
            agents,
            key=lambda a: a.name == default,
            reverse=True
        )

    @staticmethod
    async def default_agent() -> str:
        """获取默认 Agent 名称"""
        state = await AgentState.get_instance()
        return next(iter(state.agents.keys()))

    @staticmethod
    async def generate(
        description: str,
        model: Optional[ModelConfig] = None
    ) -> AgentGeneration:
        """
        使用 AI 生成新 Agent 配置

        根据用户描述自动创建合适的 Agent 配置
        """
        config = await Config.get()
        default_model = model or await Provider.default_model()
        language = await Provider.get_language(default_model)

        existing = await Agent.list()

        result = await generate_object(
            temperature=0.3,
            messages=[
                *build_system_prompt(default_model.provider_id),
                PROMPT_GENERATE,
                {
                    "role": "user",
                    "content": f"""Create an agent configuration based on this request: "{description}"

IMPORTANT: The following identifiers already exist and must NOT be used:
{", ".join(a.name for a in existing)}

Return ONLY the JSON object, no other text, do not wrap in backticks"""
                }
            ],
            model=language,
            schema={
                "identifier": str,
                "whenToUse": str,
                "systemPrompt": str
            }
        )

        return result.object
```

---

## 权限隔离

### 权限规则系统

```python
@dataclass
class PermissionRule:
    """权限规则"""
    permission: str        # 权限名称（工具名或类别）
    pattern: Union[str, Dict[str, Any]]  # 匹配模式
    action: Literal["allow", "deny", "ask"]  # 操作


class PermissionNext:
    """权限评估系统"""

    @staticmethod
    def evaluate(
        permission: str,
        pattern: str,
        ruleset: Dict[str, Any]
    ) -> PermissionResult:
        """
        评估权限请求

        返回是否允许操作
        """
        # 1. 精确匹配
        if permission in ruleset:
            rule = ruleset[permission]
            return PermissionNext._match_pattern(rule, pattern)

        # 2. 通配符匹配
        if "*" in ruleset:
            rule = ruleset["*"]
            return PermissionNext._match_pattern(rule, pattern)

        # 3. 默认拒绝
        return PermissionResult(action="deny")

    @staticmethod
    def _match_pattern(
        rule: Union[str, Dict],
        pattern: str
    ) -> PermissionResult:
        """匹配模式规则"""
        if isinstance(rule, str):
            return PermissionResult(action=rule)

        if isinstance(rule, dict):
            # 检查精确匹配
            if pattern in rule:
                return PermissionResult(action=rule[pattern])

            # 检查通配符
            if "*" in rule:
                return PermissionResult(action=rule["*"])

            # 递归检查子模式（用于 external_directory 等）
            for key, value in rule.items():
                if pattern.startswith(key):
                    return PermissionNext._match_pattern(value, pattern)

        return PermissionResult(action="deny")

    @staticmethod
    def merge(*rulesets: Dict) -> Dict:
        """
        合并多个权限规则集

        后续规则会覆盖前面的规则
        """
        result = {}
        for ruleset in rulesets:
            result = deep_merge(result, ruleset)
        return result
```

### 权限层级

```
┌─────────────────────────────────────────────────────────────────┐
│                        权限优先级                                │
├─────────────────────────────────────────────────────────────────┤
│  1. Subagent Session 权限（最高优先级）                          │
│     └─ 显式拒绝: todowrite, todoread, task                      │
│                                                                 │
│  2. Agent 权限                                                   │
│     └─ explore: 白名单模式（只允许特定工具）                     │
│     └─ general: 禁止 todo 工具                                  │
│                                                                 │
│  3. 用户配置权限                                                 │
│     └─ opencode.jsonc 中的 permission 配置                      │
│                                                                 │
│  4. 默认权限（最低优先级）                                       │
│     └─ 大部分工具允许, .env 文件拒绝, question 默认拒绝          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 会话管理

### 会话创建

```python
class Session:
    """会话管理器"""

    @staticmethod
    async def create(
        parent_id: Optional[str] = None,
        title: Optional[str] = None,
        permission: Optional[Dict] = None
    ) -> SessionInfo:
        """
        创建新会话

        Args:
            parent_id: 父会话 ID（创建子会话时使用）
            title: 会话标题
            permission: 会话级权限覆盖
        """
        session_id = Identifier.create("session", prefix=True)

        # 确定标题
        if title is None:
            title = create_default_title(is_child=(parent_id is not None))

        # 确定项目
        project_id = Project.current_id()
        directory = Project.current_directory()

        # 创建会话信息
        info = SessionInfo(
            id=session_id,
            project_id=project_id,
            directory=directory,
            parent_id=parent_id,
            title=title,
            version=Version.get(),
            time=SessionTime(
                created=Date.now(),
                updated=Date.now()
            ),
            permission=permission
        )

        # 持久化
        await Storage.save(f"session/{session_id}/info.json", info)

        # 发布事件
        await Bus.publish(Session.Event.Created, {"info": info})

        return info

    @staticmethod
    async def get(session_id: str) -> Optional[SessionInfo]:
        """获取会话信息"""
        data = await Storage.load(f"session/{session_id}/info.json")
        if data is None:
            return None
        return SessionInfo.model_validate(data)

    @staticmethod
    async def messages(session_id: str) -> List[MessageInfo]:
        """获取会话的所有消息"""
        message_files = await Storage.list(f"session/{session_id}/message/")
        messages = []

        for file in message_files:
            msg = await MessageV2.get(session_id, file.name)
            if msg:
                messages.append(msg)

        return sorted(messages, key=lambda m: m.created)
```

### 会话关系

```python
@dataclass
class SessionTree:
    """会话树结构"""

    @staticmethod
    async def get_children(session_id: str) -> List[SessionInfo]:
        """获取子会话列表"""
        all_sessions = await Session.list_all()
        return [
            s for s in all_sessions
            if s.parent_id == session_id
        ]

    @staticmethod
    async def get_root(session_id: str) -> SessionInfo:
        """获取根会话"""
        current = await Session.get(session_id)
        while current and current.parent_id:
            current = await Session.get(current.parent_id)
        return current

    @staticmethod
    async def get_depth(session_id: str) -> int:
        """获取会话深度（嵌套层级）"""
        depth = 0
        current = await Session.get(session_id)
        while current and current.parent_id:
            depth += 1
            current = await Session.get(current.parent_id)
        return depth
```

---

## 事件总线

### 事件定义

```python
class BusEvent:
    """类型安全的事件定义"""

    @staticmethod
    def define(
        event_type: str,
        properties_schema: Schema
    ) -> EventDefinition:
        """定义新事件类型"""
        return EventDefinition(
            type=event_type,
            properties=properties_schema
        )


# 消息相关事件
MessageV2.Event.Created = BusEvent.define(
    "message.created",
    z.object({"info": MessageInfo.schema()})
)

MessageV2.Event.PartUpdated = BusEvent.define(
    "message.part.updated",
    z.object({
        "part": z.object({
            "id": z.string(),
            "session_id": z.string(),
            "message_id": z.string(),
            "type": z.literal["text", "tool", "image"],
            "tool": z.string().optional(),
            "state": z.object({
                "status": z.literal["pending", "running", "completed", "failed"],
                "title": z.string().optional()
            })
        })
    })
)

# 会话相关事件
Session.Event.Created = BusEvent.define(
    "session.created",
    z.object({"info": SessionInfo.schema()})
)

Session.Event.Updated = BusEvent.define(
    "session.updated",
    z.object({
        "id": z.string(),
        "changes": z.object({
            "title": z.string().optional(),
            "summary": z.any().optional()
        }).optional()
    })
)
```

### 事件订阅

```python
class Bus:
    """事件总线"""

    _subscriptions: Dict[str, List[Callable]] = defaultdict(list)

    @staticmethod
    async def publish(
        event_def: EventDefinition,
        properties: Any
    ) -> None:
        """
        发布事件

        所有订阅者都会异步接收此事件
        """
        payload = {
            "type": event_def.type,
            "properties": properties
        }

        pending = []
        for key in [event_def.type, "*"]:  # 也发给通配符订阅者
            for callback in Bus._subscriptions[key]:
                pending.append(callback(payload))

        await Promise.all(pending)

    @staticmethod
    def subscribe(
        event_def: EventDefinition,
        callback: Callable[[Event], None]
    ) -> Callable[[], None]:
        """
        订阅事件

        返回取消订阅函数
        """
        Bus._subscriptions[event_def.type].append(callback)

        def unsubscribe():
            callbacks = Bus._subscriptions[event_def.type]
            if callback in callbacks:
                callbacks.remove(callback)

        return unsubscribe

    @staticmethod
    def subscribe_all(
        callback: Callable[[Event], None]
    ) -> Callable[[], None]:
        """订阅所有事件"""
        Bus._subscriptions["*"].append(callback)

        def unsubscribe():
            if callback in Bus._subscriptions["*"]:
                Bus._subscriptions["*"].remove(callback)

        return unsubscribe
```

---

## 完整工作流

### 场景：用户请求"重构这个模块"

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户交互                                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  1. Primary Agent (build) 接收任务                                  │
│                                                                     │
│  "我需要重构 src/auth/ 目录下的认证模块"                             │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2. Primary Agent 决定使用 explore subagent 了解代码结构            │
│                                                                     │
│  Task Tool 调用:                                                    │
│  {                                                                  │
│    "description": "探索认证模块结构",                               │
│    "prompt": "探索 src/auth/ 目录，了解认证模块的组件结构和依赖关系", │
│    "subagent_type": "explore"                                      │
│  }                                                                  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  3. Task 工具执行                                                    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 3.1 权限检查: task → explore = allow                       │   │
│  │ 3.2 创建子会话: session_abc (parent=main)                  │   │
│  │ 3.3 设置事件监听                                            │   │
│  │ 3.4 运行 explore agent                                      │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  4. Explore Subagent 执行                                           │
│                                                                     │
│  独立会话: session_abc                                              │
│  权限: {read: allow, grep: allow, glob: allow, ...}                │
│                                                                     │
│  工具调用序列:                                                       │
│  ├─ Glob("src/auth/**/*.ts")  → 找到 8 个文件                      │
│  ├─ Read("src/auth/index.ts")  → 了解入口                          │
│  ├─ Grep("class.*Auth", "src/auth/")  → 查找类定义                 │
│  └─ 生成分析报告                                                    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  5. 事件驱动进度更新                                                 │
│                                                                     │
│  每个工具调用触发:                                                   │
│                                                                     │
│  Bus.publish(MessageV2.Event.PartUpdated, {                        │
│    "part": {                                                        │
│      "id": "tool_1",                                                │
│      "session_id": "session_abc",                                   │
│      "message_id": "msg_xyz",                                       │
│      "type": "tool",                                                │
│      "tool": "glob",                                                │
│      "state": {"status": "completed", "title": "List auth files"}  │
│    }                                                                │
│  })                                                                 │
│                                                                     │
│  Primary Agent 的 Task 工具接收事件并更新 metadata:                 │
│  metadata.summary = [                                               │
│    {"id": "tool_1", "tool": "glob", "state": "completed"},        │
│    {"id": "tool_2", "tool": "read", "state": "running"},          │
│    ...                                                              │
│  ]                                                                  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  6. Explore 完成，返回结果                                          │
│                                                                     │
│  output: """                                                        │
│    认证模块结构分析:                                                │
│    - src/auth/index.ts: 导出 AuthManager, LoginHandler            │
│    - src/auth/providers/: OAuth, JWT, Basic 认证提供者             │
│    - src/auth/middleware.ts: Express 中间件                        │
│    - src/auth/types.ts: TypeScript 类型定义                        │
│    - src/auth/utils.ts: 密码哈希、token 生成工具                   │
│                                                                     │
│    主要依赖: jsonwebtoken, bcrypt, express                         │
│                                                                     │
│    <task_metadata>                                                  │
│    session_id: session_abc                                         │
│    </task_metadata>                                                │
│  """                                                                │
│                                                                     │
│  metadata.summary = [所有工具调用摘要]                              │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  7. Primary Agent 分析结果并继续                                    │
│                                                                     │
│  基于 explore 的分析，Primary Agent:                                │
│  1. 读取具体文件了解实现细节                                        │
│  2. 设计重构方案                                                    │
│  3. 使用 general subagent 并行执行重构任务                          │
│     ├─ Task("重构类型定义", subagent="general")                    │
│     ├─ Task("重构认证提供者", subagent="general")                  │
│     └─ Task("更新中间件", subagent="general")                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  8. 并行 Subagent 执行                                              │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │  General #1  │  │  General #2  │  │  General #3  │             │
│  │  重构类型    │  │  重构提供者  │  │  更新中间件  │             │
│  │  Status: ✓   │  │  Status: ✓   │  │  Status: ✓   │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
│                                                                     │
│  三个子任务完全独立，并行执行                                        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  9. 汇总结果                                                        │
│                                                                     │
│  Primary Agent 收集所有 subagent 结果:                              │
│  - General #1: 更新了 types.ts, 添加了新接口                        │
│  - General #2: 重构了 providers/ 目录结构                           │
│  - General #3: 简化了 middleware.ts                                │
│                                                                     │
│  向用户报告完成情况                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 关键设计要点

1. **会话隔离**: 每个 subagent 在独立会话中运行，避免状态污染
2. **权限限制**: Subagent 默认禁止递归调用 Task，防止无限嵌套
3. **事件驱动**: 通过事件总线实时追踪进度，无需轮询
4. **并行执行**: 多个 subagent 可以同时执行不同任务
5. **可恢复性**: 通过 session_id 可以恢复未完成的 subagent 任务

---

## 附录

### A. Agent 配置示例

```json
{
  "agent": {
    "code-reviewer": {
      "name": "Code Reviewer",
      "description": "Reviews code for best practices and potential issues",
      "mode": "subagent",
      "model": {
        "provider_id": "anthropic",
        "model_id": "claude-opus-4-5"
      },
      "temperature": 0.3,
      "permission": {
        "*": "deny",
        "read": "allow",
        "grep": "allow"
      },
      "prompt": "You are a code reviewer. Focus on: correctness, performance, security, and maintainability."
    }
  }
}
```

### B. Task 工具提示词模板

```
Launch a specialized subagent to handle a complex, multi-step task.

Available subagents:
{agents}

Parameters:
- description: A short (3-5 words) description of the task
- prompt: The detailed task for the agent to perform
- subagent_type: The type of specialized agent to use
- session_id: (Optional) Existing Task session to continue

Use this tool when:
1. The task requires multiple steps that can be executed independently
2. You need specialized capabilities (e.g., code exploration)
3. You want to parallelize work across multiple agents
```

### C. 数据模型总结

```python
# 核心数据关系
Session (1) ──┳── (*) Message (1) ── (*) Part
              │
              └── (1) parent ──→ Session

Message.Part 可以是:
- TextPart: {type: "text", text: str}
- ToolPart: {type: "tool", tool: str, state: ToolState}
- ImagePart: {type: "image", ...}

ToolState:
- pending: 工具已排队，等待执行
- running: 工具正在执行
- completed: 工具执行成功
- failed: 工具执行失败
```
