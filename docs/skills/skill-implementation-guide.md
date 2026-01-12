# Kode Skill 系统实现详解

## 目录

1. [概述](#概述)
2. [架构设计](#架构设计)
3. [核心概念](#核心概念)
4. [Skill 定义格式](#skill-定义格式)
5. [核心模块实现](#核心模块实现)
6. [Skill Marketplace](#skill-marketplace)
7. [插件系统](#插件系统)
8. [完整示例](#完整示例)

---

## 概述

### 什么是 Skill

Skill（技能）是 Kode 中的**可复用 AI 能力单元**，本质上是一个**预定义的提示模板**，可以被 AI 主动调用以完成特定任务。

### Skill 的价值

| 特性 | 说明 |
|------|------|
| **AI 可调用** | AI 通过 `Skill` 工具主动调用相关技能 |
| **可组合** | 技能可以调用其他技能 |
| **参数化** | 支持动态参数注入 |
| **工具限制** | 可限制技能使用的工具范围 |
| **模型选择** | 可为技能指定专用模型 |
| **MCP 集成** | 技能包可包含 MCP 服务器配置 |

### 能力矩阵

| 能力 | 状态 | 说明 |
|------|------|------|
| **本地技能** | ✅ | 从本地目录加载 `.md` 技能文件 |
| **技能市场** | ✅ | 从 GitHub/Git/URL 安装技能包 |
| **插件包** | ✅ | 完整的插件系统，包含技能/命令/MCP |
| **作用域** | ✅ | user/project/local 三级作用域 |
| **启用/禁用** | ✅ | 可临时禁用技能而不删除 |
| **命名空间** | ✅ | 支持插件前缀命名空间 |

---

## 架构设计

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Kode Application                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                       AI 对话层                                   │    │
│  │                                                                   │    │
│  │  用户请求 → AI 分析 → 调用 Skill 工具 → 执行技能 → 返回结果        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↑                                       │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      SkillTool (工具层)                          │    │
│  │  (src/tools/ai/SkillTool/SkillTool.tsx)                          │    │
│  │                                                                   │    │
│  │  - validateInput()    → 验证技能名称                             │    │
│  │  - call()             → 执行技能调用                             │    │
│  │  - prompt()           → 生成可用技能列表                         │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↑                                       │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Commands 层 (命令注册)                        │    │
│  │  (src/commands/index.ts)                                         │    │
│  │                                                                   │    │
│  │  - getCommands()       → 获取所有命令                            │    │
│  │  - getCommand()        → 获取单个命令                            │    │
│  │  - hasCommand()        → 检查命令是否存在                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↑                                       │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                CustomCommands 层 (技能加载)                      │    │
│  │  (src/services/customCommands.ts)                               │    │
│  │                                                                   │    │
│  │  - loadCustomCommands()  → 加载所有技能                         │    │
│  │  - parseFrontmatter()     → 解析 Markdown frontmatter           │    │
│  │  - executeBashCommands()  → 执行嵌入的 Bash 命令                │    │
│  │  - resolveFileReferences() → 解析文件引用                       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↑                                       │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                   技能来源层 (多源加载)                          │    │
│  │                                                                   │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │    │
│  │  │ 本地目录    │  │ 技能市场    │  │ 插件包      │              │    │
│  │  │ .kode/      │  │ Marketplace │  │ Plugin Pack │              │    │
│  │  │ skills/     │  │ GitHub/URL  │  │ .kode-plugin│              │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘              │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

### 目录结构

```
src/
├── tools/ai/SkillTool/          # Skill 工具实现
│   ├── SkillTool.tsx            # 工具主逻辑
│   └── prompt.ts                # 提示模板
│
├── services/
│   ├── customCommands.ts        # 自定义命令/技能加载
│   └── plugins/
│       ├── skillMarketplace.ts  # 技能市场管理
│       ├── pluginRuntime.ts     # 插件运行时
│       └── customCommands.ts    # 插件命令处理
│
├── commands/
│   ├── index.ts                 # 命令注册中心
│   └── plugin.ts                # /plugin 命令实现
│
└── utils/session/
    └── sessionPlugins.ts        # 会话插件状态
```

---

## 核心概念

### 1. Skill 类型

```typescript
// src/services/customCommands.ts

type CustomCommandWithScope = {
  type: 'prompt'              // 必须是 prompt 类型
  name: string                // 技能名称
  description: string         // 技能描述
  isEnabled: boolean          // 是否启用
  isHidden: boolean           // 是否隐藏（技能默认隐藏）
  aliases?: string[]          // 别名
  progressMessage: string     // 进度消息

  // 技能特有属性
  isSkill?: boolean           // 标识为技能
  whenToUse?: string          // 使用场景说明
  argumentHint?: string       // 参数提示
  allowedTools?: string[]     // 允许使用的工具
  model?: string              // 指定模型
  maxThinkingTokens?: number  // 最大思考 token

  // 执行函数
  getPromptForCommand(args: string): Promise<MessageParam[]>
  userFacingName(): string
}
```

### 2. 技能来源优先级

```
1. 插件命令 (Session Plugins)
   ↓
2. 项目命令 (.kode/commands/)
   ↓
3. 用户命令 (~/.config/kode/commands/)
   ↓
4. 项目技能目录 (.kode/skills/)
   ↓
5. 用户技能目录 (~/.config/kode/skills/)
   ↓
6. 兼容 Claude 目录 (.claude/)
```

### 3. 技能命名规则

```typescript
// 技能目录命名规则（严格模式）
const validateName = (skillName: string): boolean => {
  if (skillName.length < 1 || skillName.length > 64) return false
  return /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(skillName)
}

// 有效示例: "pdf", "git-commit", "code-review-2"
// 无效示例: "PDF", "git_commit", "MySkill"
```

### 4. 作用域类型

```typescript
type PluginScope = 'user' | 'project' | 'local'

// user    → ~/.config/kode/      (全局，所有项目共享)
// project → .kode/               (当前项目)
// local   → 同 project
```

---

## Skill 定义格式

### 基本格式

技能文件使用 **Markdown + YAML Frontmatter** 格式：

```markdown
---
description: "处理 PDF 文档，提取文本和图片"
when_to_use: "当用户需要处理 PDF 文件时使用"
allowed-tools: ["Read", "Bash"]
model: "sonnet"
max-thinking-tokens: 20000
version: "1.0.0"
---

# PDF 处理技能

这是一个用于处理 PDF 文档的技能。

## 功能

- 提取 PDF 文本内容
- 提取 PDF 中的图片
- 分析 PDF 结构

## 使用方法

直接提供 PDF 文件路径即可。

ARGUMENTS 将被替换为用户提供的参数。
```

### Frontmatter 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `description` | string | 推荐 | 技能描述 |
| `when_to_use` | string | 推荐 | 使用场景说明 |
| `allowed-tools` | string[] | 可选 | 限制使用的工具 |
| `model` | string | 可选 | 指定模型 (haiku/sonnet/opus/quick/task/main) |
| `max-thinking-tokens` | number | 可选 | 最大思考 token 数 |
| `argument-hint` | string | 可选 | 参数提示文本 |
| `version` | string | 可选 | 技能版本 |
| `disable-model-invocation` | boolean | 可选 | 禁止 AI 调用 |

### 技能目录结构

```
# 方式 1: 单文件技能
.kode/
└── commands/
    └── pdf.md                    # 直接定义命令

# 方式 2: 技能目录（推荐）
.kode/
└── skills/
    └── pdf/                      # 技能目录（命名需符合规则）
        └── SKILL.md              # 技能定义文件

# 方式 3: 插件包
plugins/
└── my-plugin/
    └── .kode-plugin/
        ├── plugin.json           # 插件清单
        ├── skills/               # 技能目录
        │   └── pdf/
        │       └── SKILL.md
        └── commands/             # 命令目录
        └── .mcp.json             # MCP 配置
```

---

## 核心模块实现

### 1. SkillTool 工具实现

```typescript
// src/tools/ai/SkillTool/SkillTool.tsx

import { z } from 'zod'
import type { Message } from '@query'

const inputSchema = z.strictObject({
  skill: z.string().describe('The skill name (no arguments)'),
  args: z.string().optional().describe('Optional arguments for the skill'),
})

export const SkillTool = {
  name: 'Skill',

  // 生成 AI 可见的技能列表
  async prompt() {
    const all = await loadCustomCommands()

    // 过滤出技能类型
    const skills = all.filter(cmd =>
      cmd.type === 'prompt' &&
      cmd.disableModelInvocation !== true &&
      (cmd.hasUserSpecifiedDescription || cmd.whenToUse)
    )

    // Token 预算控制
    const budget = Number(process.env.SLASH_COMMAND_TOOL_CHAR_BUDGET) || 15000
    const limited: CustomCommandWithScope[] = []
    let used = 0

    for (const skill of skills) {
      const block = formatSkillBlock(skill)
      used += block.length + 1
      if (used > budget) break
      limited.push(skill)
    }

    const availableSkills = limited.map(formatSkillBlock).join('\n')

    return `Execute a skill within the main conversation

<skills_instructions>
When users ask you to perform tasks, check if any of the available skills below can help.

How to invoke:
- Use this tool with the skill name and optional arguments
- Examples:
  - skill: "pdf" - invoke the pdf skill
  - skill: "commit", args: "-m 'Fix bug'" - invoke with arguments

Important:
- When a skill is relevant, you must invoke this tool IMMEDIATELY
- NEVER just announce a skill without calling this tool
- Only use skills listed in <available_skills> below
</skills_instructions>

<available_skills>
${availableSkills}
</available_skills>`
  },

  // 验证输入
  async validateInput({ skill }: Input, context) {
    const raw = skill.trim()
    if (!raw) {
      return { result: false, message: `Invalid skill format: ${skill}` }
    }

    const skillName = raw.startsWith('/') ? raw.slice(1) : raw
    const commands = context?.options?.commands ?? (await getCommands())
    const cmd = findCommand(skillName, commands)

    if (!cmd) {
      return {
        result: false,
        message: `Unknown skill: ${skillName}`,
      }
    }

    if (cmd.type !== 'prompt') {
      return {
        result: false,
        message: `Skill ${skillName} is not a prompt-based skill`,
      }
    }

    return { result: true }
  },

  // 执行技能调用
  async *call({ skill, args }: Input, context) {
    const skillName = skill.trim().startsWith('/') ? skill.slice(1) : skill
    const commands = context.options?.commands ?? (await getCommands())
    const cmd = findCommand(skillName, commands)

    // 获取技能提示
    const prompt = await cmd.getPromptForCommand(args ?? '')

    // 构建消息
    const expandedMessages: Message[] = prompt.map(msg => {
      const userMessage = createUserMessage(
        typeof msg.content === 'string' ? msg.content : /* ... */
      )
      userMessage.options = {
        isCustomCommand: true,
        commandName: cmd.userFacingName(),
      }
      return userMessage
    })

    // 获取技能配置
    const allowedTools = cmd.allowedTools ?? []
    const model = normalizeCommandModelName(cmd.model)

    yield {
      type: 'result',
      data: {
        success: true,
        commandName: skillName,
        allowedTools: allowedTools.length > 0 ? allowedTools : undefined,
        model,
      },
      newMessages: expandedMessages,
      contextModifier: {
        modifyContext(ctx) {
          // 应用工具限制和模型选择
          if (allowedTools.length > 0) {
            ctx.options.commandAllowedTools = [
              ...(ctx.options.commandAllowedTools || []),
              ...allowedTools,
            ]
          }
          if (model) {
            ctx.options.model = model
          }
          return ctx
        },
      },
    }
  },
}
```

### 2. 自定义命令加载器

```typescript
// src/services/customCommands.ts

import { memoize } from 'lodash-es'
import matter from 'gray-matter'
import yaml from 'js-yaml'

// 解析 Frontmatter
export function parseFrontmatter(content: string): {
  frontmatter: CustomCommandFrontmatter
  content: string
} {
  const yamlSchema = (yaml as any).JSON_SCHEMA
  const parsed = matter(content, {
    engines: {
      yaml: {
        parse: (input: string) =>
          yaml.load(input, yamlSchema ? { schema: yamlSchema } : undefined) ?? {},
      },
    },
  })
  return {
    frontmatter: (parsed.data ?? {}) as CustomCommandFrontmatter,
    content: parsed.content ?? '',
  }
}

// 创建技能命令对象
function createPromptCommandFromFile(
  record: CommandFileRecord,
): CustomCommandWithScope | null {
  const isSkill = isSkillMarkdownFile(record.filePath)
  const name = nameForCommandFile(record.filePath, record.baseDir)

  const descriptionText =
    record.frontmatter.description ??
    extractDescriptionFromMarkdown(record.content, 'Skill')

  const allowedTools = parseAllowedTools(record.frontmatter['allowed-tools'])
  const maxThinkingTokens = parseMaxThinkingTokens(record.frontmatter)
  const model = record.frontmatter.model === 'inherit'
    ? undefined
    : record.frontmatter.model

  return {
    type: 'prompt',
    name,
    description: `${descriptionText} (${sourceLabel(record.source)})`,
    isEnabled: true,
    isHidden: isSkill,  // 技能默认隐藏
    isSkill,
    whenToUse: record.frontmatter.when_to_use,
    allowedTools,
    maxThinkingTokens,
    model,
    hasUserSpecifiedDescription: !!record.frontmatter.description,
    source: record.source,
    scope: record.scope,
    filePath: record.filePath,

    userFacingName() {
      return name
    },

    async getPromptForCommand(args: string): Promise<MessageParam[]> {
      let prompt = record.content

      // 技能自动添加基础目录信息
      if (isSkill) {
        const skillBaseDir = dirname(record.filePath)
        prompt = `Base directory for this skill: ${skillBaseDir}\n\n${prompt}`
      }

      // 替换参数
      const trimmedArgs = args.trim()
      if (trimmedArgs) {
        if (prompt.includes('$ARGUMENTS')) {
          prompt = prompt.replaceAll('$ARGUMENTS', trimmedArgs)
        } else {
          prompt = `${prompt}\n\nARGUMENTS: ${trimmedArgs}`
        }
      }

      return [{ role: 'user', content: prompt }]
    },
  }
}

// 加载所有自定义命令/技能
export const loadCustomCommands = memoize(
  async (): Promise<CustomCommandWithScope[]> => {
    const cwd = getCwd()
    const userKodeBaseDir = getUserKodeBaseDir()

    // 定义多个来源目录
    const sources = [
      // 项目级
      { dir: join(cwd, '.kode', 'commands'), source: 'localSettings', scope: 'project' },
      { dir: join(cwd, '.kode', 'skills'), source: 'localSettings', scope: 'project' },
      { dir: join(cwd, '.claude', 'commands'), source: 'localSettings', scope: 'project' },
      { dir: join(cwd, '.claude', 'skills'), source: 'localSettings', scope: 'project' },
      // 用户级
      { dir: join(userKodeBaseDir, 'commands'), source: 'userSettings', scope: 'user' },
      { dir: join(userKodeBaseDir, 'skills'), source: 'userSettings', scope: 'user' },
      { dir: join(homedir(), '.claude', 'commands'), source: 'userSettings', scope: 'user' },
      { dir: join(homedir(), '.claude', 'skills'), source: 'userSettings', scope: 'user' },
    ]

    const allCommands: CustomCommandWithScope[] = []

    for (const { dir, source, scope } of sources) {
      // 加载命令文件
      const commandFiles = loadCommandMarkdownFilesFromBaseDir(dir, source, scope)
      for (const file of commandFiles) {
        const cmd = createPromptCommandFromFile(file)
        if (cmd) allCommands.push(cmd)
      }

      // 加载技能目录
      const skillCommands = loadSkillDirectoryCommandsFromBaseDir(dir, source, scope)
      allCommands.push(...skillCommands)
    }

    // 加载插件命令
    const sessionPlugins = getSessionPlugins()
    for (const plugin of sessionPlugins) {
      for (const commandsDir of plugin.commandsDirs) {
        allCommands.push(...loadPluginCommandsFromDir({
          pluginName: plugin.name,
          commandsDir,
        }))
      }
      for (const skillsDir of plugin.skillsDirs) {
        allCommands.push(...loadPluginSkillDirectoryCommandsFromBaseDir({
          pluginName: plugin.name,
          skillsDir,
        }))
      }
    }

    // 去重
    const seen = new Set<string>()
    const unique: CustomCommandWithScope[] = []
    for (const cmd of allCommands) {
      const key = cmd.userFacingName()
      if (seen.has(key)) continue
      seen.add(key)
      unique.push(cmd)
    }

    return unique.filter(cmd => cmd.isEnabled)
  },
)
```

### 3. 技能目录加载

```typescript
// src/services/customCommands.ts

function loadSkillDirectoryCommandsFromBaseDir(
  skillsDir: string,
  source: CommandSource,
  scope: 'user' | 'project',
): CustomCommandWithScope[] {
  if (!existsSync(skillsDir)) return []

  const out: CustomCommandWithScope[] = []
  const entries = readdirSync(skillsDir, { withFileTypes: true })

  // 验证技能名称
  const validateName = (skillName: string): boolean => {
    if (skillName.length < 1 || skillName.length > 64) return false
    return /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(skillName)
  }

  for (const entry of entries) {
    if (!entry.isDirectory() && !entry.isSymbolicLink()) continue

    const skillDir = join(skillsDir, entry.name)

    // 查找技能文件
    const skillFileCandidates = [
      join(skillDir, 'SKILL.md'),
      join(skillDir, 'skill.md'),
    ]
    const skillFile = skillFileCandidates.find(p => existsSync(p))
    if (!skillFile) continue

    try {
      const raw = readFileSync(skillFile, 'utf8')
      const { frontmatter, content } = parseFrontmatter(raw)

      const dirName = entry.name
      const declaredName = frontmatter.name?.trim()

      // 验证名称一致性
      if (declaredName && declaredName !== dirName) {
        if (strictMode) continue
        debugLogger.warn('CUSTOM_COMMAND_SKILL_NAME_MISMATCH', {
          dirName,
          declaredName,
          skillFile,
        })
      }

      // 验证目录名格式
      if (!validateName(dirName)) {
        if (strictMode) continue
        debugLogger.warn('CUSTOM_COMMAND_SKILL_DIR_INVALID', { dirName })
      }

      out.push({
        type: 'prompt',
        name: dirName,
        description: `${frontmatter.description ?? extractDescriptionFromMarkdown(content, 'Skill')} (${sourceLabel(source)})`,
        isEnabled: true,
        isHidden: true,  // 技能默认隐藏
        isSkill: true,
        whenToUse: frontmatter.when_to_use,
        allowedTools: parseAllowedTools(frontmatter['allowed-tools']),
        maxThinkingTokens: parseMaxThinkingTokens(frontmatter),
        model: frontmatter.model === 'inherit' ? undefined : frontmatter.model,
        filePath: skillFile,
        source,
        scope,

        userFacingName() {
          return declaredName || dirName
        },

        async getPromptForCommand(args: string): Promise<MessageParam[]> {
          let prompt = `Base directory for this skill: ${skillDir}\n\n${content}`
          const trimmedArgs = args.trim()
          if (trimmedArgs) {
            if (prompt.includes('$ARGUMENTS')) {
              prompt = prompt.replaceAll('$ARGUMENTS', trimmedArgs)
            } else {
              prompt = `${prompt}\n\nARGUMENTS: ${trimmedArgs}`
            }
          }
          return [{ role: 'user', content: prompt }]
        },
      })
    } catch (error) {
      logError(error)
    }
  }

  return out
}
```

### 4. Bash 命令执行

```typescript
// src/services/customCommands.ts

import { execFile } from 'child_process'
import { promisify } from 'util'

const execFileAsync = promisify(execFile)

export async function executeBashCommands(content: string): Promise<string> {
  const bashCommandRegex = /!\`([^`]+)\`/g
  const matches = [...content.matchAll(bashCommandRegex)]

  if (matches.length === 0) {
    return content
  }

  let result = content

  for (const match of matches) {
    const fullMatch = match[0]
    const command = match[1].trim()

    try {
      const parts = command.split(/\s+/)
      const cmd = parts[0]
      const args = parts.slice(1)

      const { stdout, stderr } = await execFileAsync(cmd, args, {
        timeout: 5000,
        encoding: 'utf8',
        cwd: getCwd(),
      })

      const output = stdout.trim() || stderr.trim() || '(no output)'
      result = result.replace(fullMatch, output)
    } catch (error) {
      logError(error)
      result = result.replace(fullMatch, `(error executing: ${command})`)
    }
  }

  return result
}
```

### 5. 文件引用解析

```typescript
// src/services/customCommands.ts

export async function resolveFileReferences(content: string): Promise<string> {
  const fileRefRegex = /@([a-zA-Z0-9/._-]+(?:\.[a-zA-Z0-9]+)?)/g
  const matches = [...content.matchAll(fileRefRegex)]

  if (matches.length === 0) {
    return content
  }

  let result = content

  for (const match of matches) {
    const fullMatch = match[0]
    const filePath = match[1]

    // 跳过 agent 文件引用
    if (filePath.startsWith('agent-')) {
      continue
    }

    try {
      const fullPath = join(getCwd(), filePath)

      if (existsSync(fullPath)) {
        const fileContent = readFileSync(fullPath, { encoding: 'utf-8' })

        const formattedContent = `\n\n## File: ${filePath}\n\`\`\`\n${fileContent}\n\`\`\`\n`
        result = result.replace(fullMatch, formattedContent)
      } else {
        result = result.replace(fullMatch, `(file not found: ${filePath})`)
      }
    } catch (error) {
      logError(error)
      result = result.replace(fullMatch, `(error reading: ${filePath})`)
    }
  }

  return result
}
```

---

## Skill Marketplace

### Marketplace 配置格式

```json
{
  "name": "My Skills Marketplace",
  "description": "A collection of useful skills",
  "owner": {
    "name": "Your Name",
    "email": "your@email.com"
  },
  "plugins": [
    {
      "name": "pdf-tools",
      "description": "PDF processing tools",
      "source": "./skills/pdf-tools",
      "skills": ["pdf-reader", "pdf-writer"],
      "commands": ["extract-text"]
    }
  ]
}
```

### Marketplace 管理功能

```typescript
// src/services/plugins/skillMarketplace.ts

// 添加市场
export async function addMarketplace(
  sourceInput: string,
): Promise<{ name: string }> {
  // 支持的源格式:
  // - github:owner/repo
  // - git:https://github.com/owner/repo.git
  // - url:https://example.com/marketplace.json
  // - file:/path/to/marketplace.json
  // - dir:/path/to/marketplace

  const source = parseMarketplaceSourceInput(sourceInput)

  // 下载并缓存
  await cacheMarketplaceToTempDir(source, tempDir)

  // 读取清单
  const manifest = readMarketplaceFromDirectory(tempDir)
  const marketplaceName = manifest.name

  // 保存配置
  config[marketplaceName] = {
    source,
    installLocation,
    lastUpdated: new Date().toISOString(),
  }
  saveKnownMarketplaces(config)

  return { name: marketplaceName }
}

// 安装技能插件
export function installSkillPlugin(
  pluginInput: string,
  options?: { scope?: PluginScope; force?: boolean },
): {
  pluginSpec: string
  installedSkills: string[]
  installedCommands: string[]
} {
  // 解析插件规格: plugin@marketplace
  const { plugin, marketplace, pluginSpec } = resolvePluginForInstall(pluginInput)

  // 获取市场清单
  const { manifest, rootDir } = getMarketplaceManifest(marketplace)

  // 查找插件条目
  const entry = manifest.plugins.find(p => p.name === plugin)

  // 判断类型
  const pluginManifestPath = join(rootDir, entry.source, '.kode-plugin', 'plugin.json')

  if (existsSync(pluginManifestPath)) {
    // Plugin Pack: 完整插件包
    return installPluginPack(entry, rootDir, scope)
  } else {
    // Skill Pack: 纯技能包
    return installSkillPack(entry, rootDir, scope)
  }
}

// 启用/禁用技能
export function enableSkillPlugin(pluginInput: string, options?: { scope?: PluginScope })
export function disableSkillPlugin(pluginInput: string, options?: { scope?: PluginScope })

// 卸载技能
export function uninstallSkillPlugin(pluginInput: string, options?: { scope?: PluginScope })

// 刷新市场
export async function refreshMarketplaceAsync(name: string)
export async function refreshAllMarketplacesAsync(onProgress?: (message: string) => void)
```

### 支持的源类型

| 源类型 | 格式 | 示例 |
|-------|------|------|
| `github` | `github:owner/repo[@ref][#path]` | `github:example/skills@main` |
| `git` | `git:url[@ref][#path]` | `git:https://github.com/example/skills.git` |
| `url` | `url:https://...` | `url:https://example.com/marketplace.json` |
| `file` | `file:/path/to/file` | `file:~/marketplace.json` |
| `dir` | `dir:/path/to/dir` | `dir:~/.local/skills` |

---

## 插件系统

### Plugin Pack 结构

```
my-plugin/
├── .kode-plugin/
│   ├── plugin.json           # 插件清单（必需）
│   └── marketplace.json      # 可选，如果是市场的一部分
├── skills/                   # 技能目录
│   ├── skill1/
│   │   └── SKILL.md
│   └── skill2/
│       └── SKILL.md
├── commands/                 # 命令目录
│   ├── command1.md
│   └── command2.md
├── agents/                   # 代理目录
│   └── agent1.md
├── output-styles/            # 输出样式
│   └── style1.json
├── hooks/
│   └── hooks.json            # 钩子配置
└── .mcp.json                 # MCP 服务器配置
```

### plugin.json 格式

```json
{
  "name": "my-plugin",
  "description": "My awesome plugin",
  "version": "1.0.0",
  "skills": ["./skills/*"],
  "commands": ["./commands/*"],
  "agents": ["./agents/*"],
  "outputStyles": ["./output-styles/*"],
  "hooks": "./hooks/hooks.json",
  "mcpServers": "./.mcp.json"
}
```

### 插件加载器

```typescript
// src/services/plugins/pluginRuntime.ts

export async function configureSessionPlugins(args: {
  pluginDirs: string[]
  baseDir?: string
}): Promise<{ plugins: SessionPlugin[]; errors: string[] }> {
  const baseDir = args.baseDir ?? getCwd()

  // 支持通配符和 ~ 展开
  const dirs = await expandPluginDirInputs(args.pluginDirs, baseDir)

  const plugins: SessionPlugin[] = []
  const errors: string[] = []

  for (const dir of dirs) {
    try {
      plugins.push(loadPluginFromDir(dir))
    } catch (err) {
      errors.push(err instanceof Error ? err.message : String(err))
    }
  }

  // 更新会话状态
  setSessionPlugins(plugins)

  // 重新加载命令、MCP 工具等
  reloadCustomCommands()
  getCommands.cache.clear?.()
  ;(getClients as any).cache?.clear?.()
  ;(getMCPTools as any).cache?.clear?.()
  clearOutputStyleCache()

  return { plugins, errors }
}

function loadPluginFromDir(rootDir: string): SessionPlugin {
  const manifestPath = join(rootDir, '.kode-plugin', 'plugin.json')
  const manifestRaw = readFileSync(manifestPath, 'utf8')
  const manifestJson = JSON.parse(manifestRaw)

  const name = manifestJson.name

  return {
    name,
    rootDir,
    manifestPath,
    manifest: manifestJson,
    commandsDirs: [
      ...listIfDir(join(rootDir, 'commands')),
      ...resolveManifestPaths(rootDir, manifestJson.commands).dirs,
    ],
    skillsDirs: [
      ...listIfDir(join(rootDir, 'skills')),
      ...resolveManifestPaths(rootDir, manifestJson.skills).dirs,
    ],
    agentsDirs: [
      ...listIfDir(join(rootDir, 'agents')),
      ...resolveManifestPaths(rootDir, manifestJson.agents).dirs,
    ],
    hooksFiles: [
      ...fileIfExists(join(rootDir, 'hooks', 'hooks.json')),
      ...resolveManifestPaths(rootDir, manifestJson.hooks).files,
    ],
    outputStylesDirs: [
      ...listIfDir(join(rootDir, 'output-styles')),
      ...resolveManifestPaths(rootDir, manifestJson.outputStyles).dirs,
    ],
    mcpConfigFiles: [
      ...fileIfExists(join(rootDir, '.mcp.json')),
      ...resolveManifestPaths(rootDir, manifestJson.mcpServers).files,
    ],
  }
}
```

---

## 完整示例

### 示例 1: 简单的 Git 技能

```markdown
---
description: "Git 版本控制操作"
when_to_use: "当用户需要执行 git 操作如提交、推送、拉取时使用"
allowed-tools: ["Bash"]
argument-hint: "<操作> [参数...]"
---

# Git 技能

帮助你执行常见的 Git 操作。

## 支持的操作

- `status` - 查看状态
- `commit <message>` - 提交更改
- `push` - 推送到远程
- `pull` - 拉取更新
- `log` - 查看提交历史

请使用 `git <操作>` 的格式执行请求的操作。
```

### 示例 2: 带参数的代码审查技能

```markdown
---
description: "审查代码并提供改进建议"
when_to_use: "当用户要求审查代码或改进代码质量时使用"
allowed-tools: ["Read", "Grep", "Bash"]
max-thinking-tokens: 10000
---

# Code Review

这是一位经验丰富的代码审查专家。

## 审查要点

1. **代码质量** - 可读性、可维护性
2. **安全性** - 潜在的安全漏洞
3. **性能** - 性能优化建议
4. **最佳实践** - 语言和框架的最佳实践

## 使用方法

提供文件路径或代码片段，我将提供详细的审查意见。

ARGUMENTS 将被替换为你要审查的文件或代码。
```

### 示例 3: 带文件引用的技能

```markdown
---
description: "根据项目规范生成代码"
allowed-tools: ["Read", "Write", "Edit"]
---

# 代码生成器

根据 @docs/coding-standards.md 中的规范生成代码。

## 规范要点

@docs/coding-standards.md

## 当前项目结构

!`tree -L 2 -I 'node_modules|.git'`

请根据上述规范和项目结构生成符合要求的代码。
```

### 示例 4: Plugin Pack

```
my-dev-tools/
├── .kode-plugin/
│   └── plugin.json
├── skills/
│   ├── git/
│   │   └── SKILL.md
│   ├── docker/
│   │   └── SKILL.md
│   └── testing/
│       └── SKILL.md
├── commands/
│   └── setup.md
└── .mcp.json
```

**plugin.json**:
```json
{
  "name": "dev-tools",
  "description": "Development utilities",
  "version": "1.0.0",
  "skills": ["./skills/*"],
  "commands": ["./commands/*"],
  "mcpServers": "./.mcp.json"
}
```

**.mcp.json**:
```json
{
  "mcpServers": {
    "github": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"]
    }
  }
}
```

---

## 总结

### Skill 系统特点

| 特点 | 说明 |
|------|------|
| **简单定义** | Markdown + YAML Frontmatter |
| **多源加载** | 本地目录、技能市场、插件包 |
| **灵活配置** | 工具限制、模型选择、token 控制 |
| **作用域管理** | user/project/local 三级 |
| **命名空间** | 插件前缀避免冲突 |
| **MCP 集成** | 技能包可包含 MCP 服务器 |

### 最佳实践

1. **技能命名**：使用小写字母和连字符，如 `code-review`
2. **描述完整**：提供清晰的 `description` 和 `when_to_use`
3. **限制工具**：使用 `allowed-tools` 提高安全性和效率
4. **版本管理**：使用版本号跟踪技能变更
5. **参数提示**：提供 `argument-hint` 帮助用户使用
