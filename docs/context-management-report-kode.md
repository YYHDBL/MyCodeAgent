# Kode-cli 上下文管理系统技术报告

**版本**: v2.0.2
**日期**: 2025-01-05
**作者**: Claude Code

---

## 目录

1. [概述](#1-概述)
2. [核心概念](#2-核心概念)
3. [消息类型定义](#3-消息类型定义)
4. [Token 计数与管理](#4-token-计数与管理)
5. [上下文压缩机制](#5-上下文压缩机制)
6. [消息保留策略](#6-消息保留策略)
7. [项目上下文系统](#7-项目上下文系统)
8. [系统提示集成](#8-系统提示集成)
9. [配置选项](#9-配置选项)
10. [架构图](#10-架构图)
11. [最佳实践](#11-最佳实践)

---

## 1. 概述

Kode-cli 的上下文管理系统是一个多层次、智能化的对话状态管理框架，旨在解决大型语言模型（LLM）应用中的核心挑战：**如何在有限的上下文窗口内保持对话连贯性和项目感知能力**。

### 1.1 设计目标

- **透明性**: 用户可清晰了解当前上下文使用情况
- **连续性**: 长对话中保持上下文的连贯性
- **智能化**: 自动识别和保留重要信息
- **可配置**: 支持多种压缩和保留策略
- **高效性**: 最小化 token 消耗，最大化信息密度

### 1.2 核心文件结构

```
src/
├── app/
│   ├── query.ts                    # 消息类型定义
│   ├── messages.ts                 # 消息状态管理
│   └── history.ts                  # 历史记录管理
├── utils/
│   ├── session/
│   │   ├── autoCompactCore.ts      # 自动压缩核心逻辑
│   │   ├── autoCompactThreshold.ts # 压缩阈值计算
│   │   ├── messageContextManager.ts # 消息上下文管理器
│   │   └── fileRecoveryCore.ts     # 文件恢复机制
│   ├── model/
│   │   └── tokens.ts               # Token 计数工具
│   └── messages/
│       └── core.ts                 # 消息归一化处理
├── services/
│   ├── context/
│   │   └── kodeContext.ts          # 项目上下文管理器
│   └── system/
│       └── systemPrompt.ts         # 系统提示格式化
└── core/
    └── permissions/                # 权限系统集成
```

---

## 2. 核心概念

### 2.1 上下文窗口 (Context Window)

上下文窗口是指 LLM 在单次对话中能够处理的最大 token 数量。不同模型有不同的限制：

| 模型系列 | 典型上下文长度 |
|---------|--------------|
| GPT-4o | 128,000 |
| Claude 3.5 Sonnet | 200,000 |
| GPT-4.1 | 1,000,000 |
| 本地模型 | 可变 (8,000 - 128,000) |

### 2.2 Token 统计

Kode-cli 使用 API 返回的 `usage` 字段进行精确 token 计数：

```typescript
interface TokenUsage {
  input_tokens: number              // 输入 token 数
  output_tokens: number             // 输出 token 数
  cache_creation_input_tokens?: number  // 缓存创建 token
  cache_read_input_tokens?: number      // 缓存读取 token
}
```

总 token 计算公式：
```
total_tokens = input_tokens + output_tokens + cache_creation_input_tokens + cache_read_input_tokens
```

### 2.3 压缩阈值

系统默认在上下文使用达到 **90%** 时触发自动压缩：

```typescript
export const AUTO_COMPACT_THRESHOLD_RATIO = 0.9
```

这个阈值平衡了两个需求：
- 足够高的阈值（90%）确保最大化利用上下文
- 保留 10% 缓冲区避免突发超限

---

## 3. 消息类型定义

### 3.1 消息类型层次结构

```typescript
// 基础消息类型
export type Message = UserMessage | AssistantMessage | ProgressMessage

// 用户消息
export type UserMessage = {
  message: MessageParam
  type: 'user'
  uuid: UUID
  toolUseResult?: FullToolUseResult
  options?: {
    isKodingRequest?: boolean
    kodingContext?: string
    isCustomCommand?: boolean
    commandName?: string
    commandArgs?: string
  }
}

// 助手消息
export type AssistantMessage = {
  costUSD: number
  durationMs: number
  message: APIAssistantMessage
  type: 'assistant'
  uuid: UUID
  isApiErrorMessage?: boolean
  responseId?: string
}

// 进度消息（流式处理中的中间状态）
export type ProgressMessage = {
  content: AssistantMessage
  normalizedMessages: NormalizedMessage[]
  siblingToolUseIDs: Set<string>
  tools: Tool[]
  toolUseID: string
  type: 'progress'
  uuid: UUID
}
```

### 3.2 消息状态管理

使用 React Hooks 模式管理消息状态：

```typescript
// src/app/messages.ts
let getMessages: () => Message[] = () => []
let setMessages: React.Dispatch<React.SetStateAction<Message[]>> = () => {}

export function registerMessageHooks(
  getter: () => Message[],
  setter: React.Dispatch<React.SetStateAction<Message[]>>,
) {
  getMessages = getter
  setMessages = setter
}
```

### 3.3 消息归一化

在发送到 API 前，消息会被归一化处理：

```typescript
export function normalizeMessagesForAPI(
  messages: Message[],
): (UserMessage | AssistantMessage)[] {
  const result: (UserMessage | AssistantMessage)[] = []

  for (const message of messages) {
    // 过滤进度消息
    if (message.type === 'progress') continue

    // 过滤合成错误消息
    if (isSyntheticApiErrorMessage(message)) continue

    // 合并连续的用户消息
    if (prev?.type === 'user' && message.type === 'user') {
      result[result.indexOf(prev)] = mergeUserMessages(prev, message)
    } else {
      result.push(message)
      prev = message
    }
  }

  return result
}
```

---

## 4. Token 计数与管理

### 4.1 精确计数实现

`src/utils/model/tokens.ts` 实现了基于 API 返回的精确计数：

```typescript
export function countTokens(messages: Message[]): number {
  // 从最新消息开始倒序查找
  let i = messages.length - 1
  while (i >= 0) {
    const message = messages[i]

    // 只统计包含 usage 字段的助手消息
    if (
      message?.type === 'assistant' &&
      'usage' in message.message &&
      !(SYNTHETIC_ASSISTANT_MESSAGES.has(message.message.content[0]?.text))
    ) {
      const { usage } = message.message
      return (
        usage.input_tokens +
        (usage.cache_creation_input_tokens ?? 0) +
        (usage.cache_read_input_tokens ?? 0) +
        usage.output_tokens
      )
    }
    i--
  }

  return 0
}
```

### 4.2 缓存 Token 统计

支持 Prompt Caching 的独立统计：

```typescript
export function countCachedTokens(messages: Message[]): number {
  let i = messages.length - 1
  while (i >= 0) {
    const message = messages[i]
    if (message?.type === 'assistant' && 'usage' in message.message) {
      const { usage } = message.message
      return (
        (usage.cache_creation_input_tokens ?? 0) +
        (usage.cache_read_input_tokens ?? 0)
      )
    }
    i--
  }
  return 0
}
```

### 4.3 阈值计算

```typescript
export function calculateAutoCompactThresholds(
  tokenCount: number,
  contextLimit: number,
  ratio: number = AUTO_COMPACT_THRESHOLD_RATIO,
): {
  isAboveAutoCompactThreshold: boolean
  percentUsed: number
  tokensRemaining: number
  contextLimit: number
  autoCompactThreshold: number
  ratio: number
} {
  const safeContextLimit =
    Number.isFinite(contextLimit) && contextLimit > 0 ? contextLimit : 1
  const autoCompactThreshold = safeContextLimit * ratio

  return {
    isAboveAutoCompactThreshold: tokenCount >= autoCompactThreshold,
    percentUsed: Math.round((tokenCount / safeContextLimit) * 100),
    tokensRemaining: Math.max(0, autoCompactThreshold - tokenCount),
    contextLimit: safeContextLimit,
    autoCompactThreshold,
    ratio,
  }
}
```

---

## 5. 上下文压缩机制

### 5.1 自动压缩流程

```
┌─────────────────────┐
│  每次消息处理后      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  countTokens()      │ ◄── 精确统计当前 token
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  calculateThresholds│ ◄── 计算是否需要压缩
└──────────┬──────────┘
           │
           ▼
      ┌────────┴────────┐
      │                 │
      ▼                 ▼
  token < 90%      token >= 90%
      │                 │
      │                 ▼
      │         ┌───────────────────┐
      │         │  executeAutoCompact│
      │         └─────────┬─────────┘
      │                   │
      │                   ▼
      │         ┌──────────────────────┐
      │         │  1. 选择压缩模型       │
      │         │  2. 生成对话摘要      │
      │         │  3. 恢复关键文件      │
      │         │  4. 清理缓存          │
      │         └──────────┬───────────┘
      │                      │
      └──────────────────────┘
```

### 5.2 压缩提示模板

系统使用结构化的提示来生成高质量的对话摘要：

```typescript
const COMPRESSION_PROMPT = `Please provide a comprehensive summary of our conversation structured as follows:

## Technical Context
Development environment, tools, frameworks, and configurations in use. Programming languages, libraries, and technical constraints. File structure, directory organization, and project architecture.

## Project Overview
Main project goals, features, and scope. Key components, modules, and their relationships. Data models, APIs, and integration patterns.

## Code Changes
Files created, modified, or analyzed during our conversation. Specific code implementations, functions, and algorithms added. Configuration changes and structural modifications.

## Debugging & Issues
Problems encountered and their root causes. Solutions implemented and their effectiveness. Error messages, logs, and diagnostic information.

## Current Status
What we just completed successfully. Current state of the codebase and any ongoing work. Test results, validation steps, and verification performed.

## Pending Tasks
Immediate next steps and priorities. Planned features, improvements, and refactoring. Known issues, technical debt, and areas needing attention.

## User Preferences
Coding style, formatting, and organizational preferences. Communication patterns and feedback style. Tool choices and workflow preferences.

## Key Decisions
Important technical decisions made and their rationale. Alternative approaches considered and why they were rejected. Trade-offs accepted and their implications.

Focus on information essential for continuing the conversation effectively, including specific details about code, files, errors, and plans.`
```

### 5.3 压缩模型选择策略

系统智能选择压缩模型：

```typescript
// 1. 首选: compact 模型指针
const compactResolution = modelManager.resolveModelWithInfo('compact')

// 2. 检查压缩模型是否有足够容量
const compactBudget = Math.floor(
  compactResolution.profile.contextLength * 0.9
)

if (tokenCount > compactBudget) {
  // 3. 回退: 使用 main 模型
  compressionModelPointer = 'main'
}

// 4. 最终压缩消息
const compactedMessages = [
  createUserMessage(`Context compressed using ${compressionModelPointer}`),
  summaryResponse,  // AI 生成的摘要
  ...recoveredFiles // 恢复的关键文件
]
```

### 5.4 文件恢复机制

压缩后会自动恢复最近修改的文件：

```typescript
const recoveredFiles = await selectAndReadFiles()

if (recoveredFiles.length > 0) {
  for (const file of recoveredFiles) {
    const contentWithLines = addLineNumbers({
      content: file.content,
      startLine: 1,
    })
    const recoveryMessage = createUserMessage(
      `**Recovered File: ${file.path}**\n\n\`\`\`\n${contentWithLines}\n\`\`\`\n\n` +
      `*Automatically recovered (${file.tokens} tokens)${file.truncated ? ' [truncated]' : ''}*`
    )
    compactedMessages.push(recoveryMessage)
  }
}
```

---

## 6. 消息保留策略

### 6.1 策略类型

`MessageContextManager` 支持四种保留策略：

```typescript
export interface MessageRetentionStrategy {
  type:
    | 'preserve_recent'        // 保留最近消息
    | 'preserve_important'     // 保留重要消息
    | 'smart_compression'      // 智能压缩
    | 'auto_compact'           // 自动压缩
  maxTokens: number
  preserveCount?: number
  importanceThreshold?: number
}
```

### 6.2 策略详解

#### 6.2.1 Preserve Recent（激进策略）

保留最近的 N 条消息：

```typescript
private preserveRecentMessages(
  messages: Message[],
  strategy: MessageRetentionStrategy,
): MessageTruncationResult {
  const preserveCount =
    strategy.preserveCount || this.estimateMessageCount(strategy.maxTokens)
  const truncatedMessages = messages.slice(-preserveCount)
  const removedCount = messages.length - truncatedMessages.length

  return {
    truncatedMessages,
    removedCount,
    preservedTokens: countTokens(truncatedMessages),
    strategy: `Preserved last ${preserveCount} messages`,
  }
}
```

#### 6.2.2 Preserve Important（平衡策略）

保留重要消息 + 最近消息：

```typescript
private preserveImportantMessages(
  messages: Message[],
  strategy: MessageRetentionStrategy,
): MessageTruncationResult {
  const importantMessages: Message[] = []
  const recentMessages: Message[] = []

  // 保留最近 5 条
  const recentCount = Math.min(5, messages.length)
  recentMessages.push(...messages.slice(-recentCount))

  // 识别重要消息
  for (let i = 0; i < messages.length - recentCount; i++) {
    const message = messages[i]
    if (this.isImportantMessage(message)) {
      importantMessages.push(message)
    }
  }

  return {
    truncatedMessages: [...importantMessages, ...recentMessages],
    removedCount,
    preservedTokens: countTokens(truncatedMessages),
    strategy: `Preserved ${importantMessages.length} important + ${recentCount} recent`,
  }
}
```

**重要消息识别**：

```typescript
private isImportantMessage(message: Message): boolean {
  if (message.type === 'user') return true

  if (message.type === 'assistant') {
    const textContent = /* 提取文本内容 */.toLowerCase()

    return (
      textContent.includes('error') ||
      textContent.includes('failed') ||
      textContent.includes('warning') ||
      textContent.includes('critical') ||
      textContent.includes('issue')
    )
  }

  return false
}
```

#### 6.2.3 Smart Compression（保守策略）

创建对话摘要 + 保留最近消息：

```typescript
private async smartCompressionStrategy(
  messages: Message[],
  strategy: MessageRetentionStrategy,
): Promise<MessageTruncationResult> {
  const recentCount = Math.min(10, Math.floor(messages.length * 0.3))
  const recentMessages = messages.slice(-recentCount)
  const olderMessages = messages.slice(0, -recentCount)

  // 生成摘要
  const summary = this.createMessagesSummary(olderMessages)

  // 创建摘要消息
  const summaryMessage: Message = {
    type: 'assistant',
    message: {
      role: 'assistant',
      content: [{
        type: 'text',
        text: `[CONVERSATION SUMMARY - ${olderMessages.length} messages compressed]\n\n${summary}\n\n[END SUMMARY - Recent context follows...]`,
      }],
    },
    costUSD: 0,
    durationMs: 0,
    uuid: crypto.randomUUID(),
  }

  return {
    truncatedMessages: [summaryMessage, ...recentMessages],
    removedCount: olderMessages.length,
    preservedTokens: countTokens([summaryMessage, ...recentMessages]),
    strategy: `Compressed ${olderMessages.length} messages + preserved ${recentCount} recent`,
  }
}
```

**摘要生成**：

```typescript
private createMessagesSummary(messages: Message[]): string {
  const userMessages = messages.filter(m => m.type === 'user').length
  const assistantMessages = messages.filter(m => m.type === 'assistant').length
  const toolUses = /* 统计工具调用 */

  // 主题识别
  const topics: string[] = []
  messages.forEach(msg => {
    if (msg.type === 'user') {
      const text = /* 提取文本 */
      if (text.includes('error') || text.includes('bug')) topics.push('debugging')
      if (text.includes('implement') || text.includes('create')) topics.push('implementation')
      if (text.includes('explain')) topics.push('explanation')
      if (text.includes('fix')) topics.push('problem-solving')
    }
  })

  return `Previous conversation included ${userMessages} user messages and ${assistantMessages} assistant responses, with ${toolUses} tool invocations. Key topics: ${uniqueTopics.join(', ') || 'general discussion'}.`
}
```

### 6.3 策略选择

```typescript
export function createRetentionStrategy(
  targetContextLength: number,
  currentTokens: number,
  userPreference: 'aggressive' | 'balanced' | 'conservative' = 'balanced',
): MessageRetentionStrategy {
  const maxTokens = Math.floor(targetContextLength * 0.7)

  switch (userPreference) {
    case 'aggressive':
      return {
        type: 'preserve_recent',
        maxTokens,
        preserveCount: Math.max(3, Math.floor(maxTokens / 200)),
      }
    case 'conservative':
      return {
        type: 'smart_compression',
        maxTokens,
      }
    case 'balanced':
    default:
      return {
        type: 'preserve_important',
        maxTokens,
        preserveCount: Math.max(5, Math.floor(maxTokens / 150)),
      }
  }
}
```

---

## 7. 项目上下文系统

### 7.1 KodeContextManager

使用单例模式管理项目文档上下文：

```typescript
class KodeContextManager {
  private static instance: KodeContextManager
  private projectDocsCache = ''
  private cacheInitialized = false
  private initPromise: Promise<void> | null = null

  static getInstance(): KodeContextManager {
    if (!KodeContextManager.instance) {
      KodeContextManager.instance = new KodeContextManager()
    }
    return KodeContextManager.instance
  }

  private async initialize(): Promise<void> {
    if (this.initPromise) return this.initPromise

    this.initPromise = (async () => {
      try {
        const projectDocs = await getProjectDocs()
        this.projectDocsCache = projectDocs || ''
        this.cacheInitialized = true
      } catch (error) {
        logError(error)
        this.projectDocsCache = ''
        this.cacheInitialized = true
      }
    })()

    return this.initPromise
  }

  public getKodeContext(): string {
    if (!this.cacheInitialized) {
      this.initialize().catch(error => logError(error))
      return ''
    }
    return this.projectDocsCache
  }

  public async refreshCache(): Promise<void> {
    this.cacheInitialized = false
    this.initPromise = null
    await this.initialize()
  }
}
```

### 7.2 启动时初始化

```typescript
// 在非测试环境下，启动时自动初始化缓存
if (process.env.NODE_ENV !== 'test') {
  setTimeout(() => {
    refreshKodeContext().catch(() => {})
  }, 0)
}
```

---

## 8. 系统提示集成

### 8.1 格式化系统提示

```typescript
export function formatSystemPromptWithContext(
  systemPrompt: string[],
  context: { [k: string]: string },
  agentId?: string,
  skipContextReminders = false,
): { systemPrompt: string[]; reminders: string } {
  const enhancedPrompt = [...systemPrompt]

  // 1. 添加 GPT-5 持久化提示
  if (isGPT5Model(modelProfile.modelName)) {
    const persistencePrompts = [
      '\n# Agent Persistence for Long-Running Coding Tasks',
      'You are working on a coding project that may involve multiple steps and iterations...',
    ]
    enhancedPrompt.push(...persistencePrompts)
  }

  // 2. 添加项目上下文
  if (hasContext) {
    const kodeContext = generateKodeContext()
    if (kodeContext) {
      enhancedPrompt.push('\n---\n# 项目上下文\n')
      enhancedPrompt.push(kodeContext)
      enhancedPrompt.push('\n---\n')
    }

    // 3. 添加具体上下文
    enhancedPrompt.push(
      ...Object.entries(filteredContext).map(
        ([key, value]) => `<context name="${key}">${value}</context>`,
      ),
    )
  }

  return { systemPrompt: enhancedPrompt, reminders }
}
```

---

## 9. 配置选项

### 9.1 模型指针

系统使用模型指针来为不同用途配置默认模型：

```typescript
interface ModelPointers {
  main: string        // 主对话模型
  task: string        // 子代理任务模型
  reasoning: string   // 推理模型
  quick: string       // 快速 NLP 任务模型
  compact: string     // 压缩/总结模型
}
```

### 9.2 上下文相关配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `AUTO_COMPACT_THRESHOLD_RATIO` | number | 0.9 | 触发自动压缩的 token 比例 |
| `MAX_HISTORY_ITEMS` | number | 100 | 最大历史记录条数 |
| `userPreference` | string | 'balanced' | 消息保留策略偏好 |

---

## 10. 架构图

### 10.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         Kode-cli UI                              │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Message Store                               │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐    │
│  │   UserMsg   │  │ AssistantMsg │  │   ProgressMsg       │    │
│  └─────────────┘  └──────────────┘  └─────────────────────┘    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Context Manager                                │
│  ┌─────────────────┐  ┌──────────────────┐                     │
│  │ Token Counter   │  │ Threshold Calc   │                     │
│  └─────────────────┘  └──────────────────┘                     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
                ▼                         ▼
        ┌───────────────┐         ┌───────────────┐
        │ Below 90%     │         │ Above 90%     │
        │ Continue      │         │ Auto Compact  │
        └───────────────┘         └───────┬───────┘
                                           │
                                           ▼
                                ┌───────────────────────────┐
                                │  Compression Service      │
                                │  ┌─────────────────────┐  │
                                │  │ Select Model        │  │
                                │  │ Generate Summary    │  │
                                │  │ Recover Files       │  │
                                │  │ Clear Cache         │  │
                                │  └─────────────────────┘  │
                                └───────────┬───────────────┘
                                            │
                                            ▼
                                ┌───────────────────────────┐
                                │  Compacted Messages       │
                                │  ┌─────────────────────┐  │
                                │  │ Summary             │  │
                                │  │ Recovered Files     │  │
                                │  │ Recent Messages     │  │
                                │  └─────────────────────┘  │
                                └───────────────────────────┘
```

### 10.2 数据流

```
用户输入
    │
    ▼
┌─────────────┐
│ createUser  │ ─────► UserMessage
│  Message    │
└─────┬───────┘
      │
      ▼
┌─────────────────────────────┐
│ normalizeMessagesForAPI     │
│  - 过滤 progress 消息        │
│  - 合并连续用户消息          │
│  - 过滤合成错误消息          │
└───────┬─────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│ checkAutoCompact            │
│  - countTokens()            │◄─────┐
│  - calculateThresholds()    │      │
└───────┬─────────────────────┘      │
        │                           │
        │ 是否需要压缩?              │
        ▼                           │
   ┌────────┴────────┐              │
   │ No              │ Yes          │
   ▼                 ▼              │
┌─────────┐   ┌─────────────┐        │
│ 发送到  │   │ 压缩上下文   │        │
│  LLM    │   │ 重建消息数组 │        │
└────┬────┘   └──────┬──────┘        │
     │              │               │
     └──────────────┴───────────────┘
                    │
                    ▼
            ┌───────────────┐
            │ queryLLM()    │
            └───────┬───────┘
                    │
                    ▼
            ┌───────────────┐
            │AssistantMessage│
            │  + usage      │
            └───────┬───────┘
                    │
                    ▼
            ┌───────────────┐
            │添加到消息历史  │
            └───────────────┘
```

---

## 11. 最佳实践

### 11.1 开发建议

1. **压缩模型配置**
   - 为 `compact` 指针配置高上下文容量的模型
   - 确保压缩模型具有良好的总结能力

2. **上下文监控**
   - 定期检查 `percentUsed` 指标
   - 在接近阈值时主动触发压缩

3. **缓存利用**
   - 利用 Prompt Caching 减少重复 token 消耗
   - 项目上下文使用单例缓存模式

### 11.2 性能优化

1. **Token 预算分配**
   ```
   系统提示: ~5-10%
   项目上下文: ~10-15%
   对话历史: ~60-70%
   输出空间: ~15-20%
   ```

2. **消息合并**
   - 连续的用户消息会被自动合并
   - 减少消息结构开销

3. **异步初始化**
   - 项目上下文在后台异步加载
   - 不阻塞启动流程

### 11.3 故障处理

1. **压缩失败降级**
   ```typescript
   try {
     const compactedMessages = await executeAutoCompact(messages, toolUseContext)
     return { messages: compactedMessages, wasCompacted: true }
   } catch (error) {
     logError(error)
     return { messages, wasCompacted: false }
   }
   ```

2. **模型切换**
   - `compact` 模型不可用时自动回退到 `main`
   - 上下文过长时智能选择合适模型

---

## 附录

### A. 关键常量

```typescript
// 自动压缩阈值比例
export const AUTO_COMPACT_THRESHOLD_RATIO = 0.9

// 最大历史记录数
const MAX_HISTORY_ITEMS = 100

// 平均每条消息 token 数（估算）
const avgTokensPerMessage = 150

// 消息保留数量
const PRESERVE_RECENT_COUNT = Math.max(3, Math.floor(maxTokens / 200))
const PRESERVE_IMPORTANT_COUNT = Math.max(5, Math.floor(maxTokens / 150))
```

### B. 相关文件索引

| 文件 | 功能 |
|------|------|
| `src/app/query.ts` | 消息类型定义 |
| `src/app/messages.ts` | 消息状态管理 |
| `src/utils/model/tokens.ts` | Token 计数 |
| `src/utils/session/autoCompactCore.ts` | 自动压缩核心 |
| `src/utils/session/autoCompactThreshold.ts` | 阈值计算 |
| `src/utils/session/messageContextManager.ts` | 消息上下文管理器 |
| `src/services/context/kodeContext.ts` | 项目上下文管理 |
| `src/services/system/systemPrompt.ts` | 系统提示格式化 |

### C. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v2.0.2 | 2025-01-05 | Node.js 运行时兼容性和架构重构 |
| v2.0.0 | 2024 | 智能上下文管理系统 |
| v1.x | 2024 | 基础上下文管理 |

---

**文档结束**
