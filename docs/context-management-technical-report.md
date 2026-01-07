# Gemini CLI 上下文管理系统技术报告

**文档版本**: 1.0
**生成日期**: 2025-01-05
**项目**: google-gemini/gemini-cli

---

## 摘要

Gemini CLI 的上下文管理系统是一个高度模块化的架构，负责管理 AI 对话中的上下文信息收集、加载和传递。该系统采用三层分层架构（全局记忆 → 环境记忆 → JIT 上下文发现），结合智能缓存和并发控制机制，为大规模代码库提供高效的上下文支持。

---

## 目录

1. [系统架构概览](#1-系统架构概览)
2. [核心组件分析](#2-核心组件分析)
3. [上下文发现机制](#3-上下文发现机制)
4. [文件过滤系统](#4-文件过滤系统)
5. [Token 管理与限制](#5-token-管理与限制)
6. [缓存策略](#6-缓存策略)
7. [数据流与交互](#7-数据流与交互)
8. [设计模式总结](#8-设计模式总结)
9. [性能优化技术](#9-性能优化技术)

---

## 1. 系统架构概览

### 1.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Gemini CLI                           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   全局记忆    │  │   环境记忆    │  │    JIT 上下文发现     │  │
│  │ Global      │  │ Environment │  │ (Just-In-Time)      │  │
│  │ Memory      │  │ Memory      │  │                     │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                     │               │
│         └────────────────┴─────────────────────┘               │
│                          │                                    │
│                  ┌───────▼────────┐                          │
│                  │ ContextManager │                          │
│                  └───────┬────────┘                          │
│                          │                                    │
│         ┌────────────────┼────────────────┐                  │
│         ▼                ▼                ▼                  │
│  ┌─────────────┐ ┌─────────────┐ ┌────────────────┐         │
│  │   Config    │ │ Workspace   │ │ FileDiscovery  │         │
│  │             │ │   Context   │ │   Service      │         │
│  └─────────────┘ └─────────────┘ └────────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 核心文件位置

| 组件 | 文件路径 |
|------|----------|
| ContextManager | `packages/core/src/services/contextManager.ts` |
| WorkspaceContext | `packages/core/src/utils/workspaceContext.ts` |
| FileDiscoveryService | `packages/core/src/services/fileDiscoveryService.ts` |
| MemoryDiscovery | `packages/core/src/utils/memoryDiscovery.ts` |
| TokenLimits | `packages/core/src/core/tokenLimits.ts` |
| ResourceRegistry | `packages/core/src/resources/resource-registry.ts` |
| PromptRegistry | `packages/core/src/prompts/prompt-registry.ts` |

---

## 2. 核心组件分析

### 2.1 ContextManager 类

**文件位置**: `packages/core/src/services/contextManager.ts`

**类定义**:
```typescript
export class ContextManager {
  private readonly loadedPaths: Set<string> = new Set();
  private readonly config: Config;
  private globalMemory: string = '';
  private environmentMemory: string = '';
}
```

**职责**:
- 管理全局记忆和环境记忆的加载
- 追踪已加载的文件路径，避免重复加载
- 提供 JIT 上下文发现接口

**关键方法**:

| 方法 | 功能 |
|------|------|
| `refresh()` | 重新加载全局和环境记忆 |
| `loadGlobalMemory()` | 加载 `~/.gemini/GEMINI.md` |
| `loadEnvironmentMemory()` | 加载工作区的 GEMINI.md 文件 |
| `discoverContext()` | JIT 加载特定路径的上下文 |
| `getGlobalMemory()` | 获取全局记忆内容 |
| `getEnvironmentMemory()` | 获取环境记忆内容 |
| `getLoadedPaths()` | 获取已加载路径集合 |

**记忆加载流程**:
```
refresh()
    │
    ├── loadGlobalMemory()
    │       └── loadGlobalMemory() → 读取 ~/.gemini/GEMINI.md
    │
    ├── loadEnvironmentMemory()
    │       ├── 加载工作区 GEMINI.md 文件（向上遍历）
    │       ├── 获取扩展上下文文件
    │       └── 合并 MCP 指令
    │
    └── emitMemoryChanged() → 发送 CoreEvent.MemoryChanged
```

### 2.2 WorkspaceContext 类

**文件位置**: `packages/core/src/utils/workspaceContext.ts`

**类定义**:
```typescript
export class WorkspaceContext {
  private directories = new Set<string>();
  private initialDirectories: Set<string>;
  private onDirectoriesChangedListeners = new Set<() => void>();
}
```

**职责**:
- 管理多个工作区目录
- 验证路径是否在工作区内
- 通知目录变更事件

**关键方法**:

| 方法 | 功能 |
|------|------|
| `addDirectory()` | 添加目录到工作区 |
| `getDirectories()` | 获取所有工作区目录 |
| `isPathWithinWorkspace()` | 验证路径是否在工作区内 |
| `onDirectoriesChanged()` | 注册目录变更监听器 |
| `setDirectories()` | 批量设置工作区目录 |

**路径验证逻辑**:
```typescript
private isPathWithinRoot(pathToCheck: string, rootDirectory: string): boolean {
  const relative = path.relative(rootDirectory, pathToCheck);
  return (
    !relative.startsWith(`..${path.sep}`) &&
    relative !== '..' &&
    !path.isAbsolute(relative)
  );
}
```

### 2.3 ResourceRegistry 类

**文件位置**: `packages/core/src/resources/resource-registry.ts`

**类定义**:
```typescript
export class ResourceRegistry {
  private resources: Map<string, MCPResource> = new Map();
}
```

**职责**:
- 跟踪从 MCP 服务器发现的资源
- 支持资源的注册、查询和清理

**关键方法**:

| 方法 | 功能 |
|------|------|
| `setResourcesForServer()` | 为特定服务器注册资源 |
| `findResourceByUri()` | 按 URI 查找资源 |
| `removeResourcesByServer()` | 清理特定服务器的资源 |
| `getAllResources()` | 获取所有注册的资源 |

**资源命名策略**:
- 使用复合键 `serverName::uri` 确保唯一性
- 自动处理命名冲突

### 2.4 PromptRegistry 类

**文件位置**: `packages/core/src/prompts/prompt-registry.ts`

**类定义**:
```typescript
export class PromptRegistry {
  private prompts: Map<string, DiscoveredMCPPrompt> = new Map();
}
```

**职责**:
- 管理从 MCP 服务器发现的提示
- 处理提示命名冲突

**关键方法**:

| 方法 | 功能 |
|------|------|
| `registerPrompt()` | 注册提示定义 |
| `getPrompt()` | 获取特定提示 |
| `getPromptsByServer()` | 获取特定服务器的所有提示 |
| `getAllPrompts()` | 获取所有提示（按名称排序） |
| `removePromptsByServer()` | 清理特定服务器的提示 |

---

## 3. 上下文发现机制

### 3.1 三级发现策略

**文件位置**: `packages/core/src/utils/memoryDiscovery.ts`

```
                    ┌─────────────────────────┐
                    │   上下文发现策略         │
                    └─────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│   全局记忆      │      │   环境记忆      │      │   JIT 记忆     │
│  (Tier 1)     │      │  (Tier 2)     │      │  (Tier 3)     │
│               │      │               │      │               │
│ ~/.gemini/    │      │ 向上遍历到      │      │ 按需加载        │
│ GEMINI.md     │      │ 项目根目录       │      │ 访问的路径       │
└───────────────┘      └───────────────┘      └───────────────┘
```

### 3.2 全局记忆 (Tier 1)

**加载函数**: `loadGlobalMemory()`

**搜索路径**:
```bash
~/.gemini/GEMINI.md
~/.gemini/CLAUDE.md
~/.gemini/AI.md
```

**特点**:
- 始终被加载
- 适用于用户级别的全局配置
- 支持多个文件名变体

### 3.3 环境记忆 (Tier 2)

**加载函数**: `loadEnvironmentMemory()`

**搜索策略**:
1. **向上遍历**: 从当前工作目录向上搜索 GEMINI.md 文件，直到项目根目录
2. **扩展上下文**: 加载已启用扩展的上下文文件
3. **MCP 指令**: 合并 MCP 服务器提供的指令

**项目根目录检测**:
```typescript
async function findProjectRoot(startDir: string): Promise<string | null> {
  let currentDir = path.resolve(startDir);
  while (true) {
    const gitPath = path.join(currentDir, '.git');
    if (await fs.lstat(gitPath).isDirectory()) {
      return currentDir;
    }
    const parentDir = path.dirname(currentDir);
    if (parentDir === currentDir) return null;
    currentDir = parentDir;
  }
}
```

### 3.4 JIT 记忆 (Tier 3)

**加载函数**: `loadJitSubdirectoryMemory()`

**触发条件**: 当 AI 需要访问特定路径时

**工作流程**:
1. 确定目标路径所在的最深信任根
2. 从目标路径向上遍历到信任根
3. 过滤掉已加载的路径
4. 加载新发现的 GEMINI.md 文件

**伪代码**:
```
对于每个访问的路径:
    找到包含该路径的最深信任根
    从该路径向上遍历到信任根
    查找所有 GEMINI.md 文件
    过滤已加载的路径
    加载新文件内容
    标记为已加载
```

### 3.5 并发控制

**文件读取并发限制**:
```typescript
const CONCURRENT_LIMIT = 20;  // 文件读取
```

**目录遍历并发限制**:
```typescript
const CONCURRENT_LIMIT = 10;  // 目录遍历
```

**目的**: 防止 EMFILE 错误（文件描述符耗尽）

---

## 4. 文件过滤系统

### 4.1 FileDiscoveryService 类

**文件位置**: `packages/core/src/services/fileDiscoveryService.ts`

**类定义**:
```typescript
export class FileDiscoveryService {
  private gitIgnoreFilter: GitIgnoreFilter | null = null;
  private geminiIgnoreFilter: GeminiIgnoreFilter | null = null;
  private combinedIgnoreFilter: GitIgnoreFilter | null = null;
  private projectRoot: string;
}
```

### 4.2 过滤器类型

| 过滤器 | 配置文件 | 用途 |
|--------|----------|------|
| GitIgnoreFilter | `.gitignore` | 遵循 Git 忽略规则 |
| GeminiIgnoreFilter | `.geminiignore` | Gemini CLI 专用忽略规则 |
| CombinedFilter | 两者合并 | 综合过滤 |

### 4.3 过滤方法

```typescript
filterFiles(filePaths: string[], options: FilterFilesOptions): string[]
```

**选项**:
```typescript
interface FilterFilesOptions {
  respectGitIgnore?: boolean;      // 默认: true
  respectGeminiIgnore?: boolean;   // 默认: true
}
```

**过滤逻辑**:
```typescript
if (respectGitIgnore && respectGeminiIgnore && combinedIgnoreFilter) {
  return !combinedIgnoreFilter.isIgnored(filePath);
}
if (respectGitIgnore && gitIgnoreFilter?.isIgnored(filePath)) {
  return false;
}
if (respectGeminiIgnore && geminiIgnoreFilter?.isIgnored(filePath)) {
  return false;
}
return true;
```

### 4.4 过滤报告

```typescript
interface FilterReport {
  filteredPaths: string[];   // 过滤后的路径列表
  ignoredCount: number;       // 被忽略的文件数量
}
```

---

## 5. Token 管理与限制

### 5.1 Token 限制配置

**文件位置**: `packages/core/src/core/tokenLimits.ts`

```typescript
export const DEFAULT_TOKEN_LIMIT = 1_048_576;

export function tokenLimit(model: Model): TokenCount {
  switch (model) {
    case 'gemini-1.5-pro':
      return 2_097_152;  // 2M tokens
    case 'gemini-1.5-flash':
    case 'gemini-2.5-pro':
    case 'gemini-2.5-flash':
    case 'gemini-2.5-flash-lite':
    case 'gemini-2.0-flash':
      return 1_048_576;  // 1M tokens
    case 'gemini-2.0-flash-preview-image-generation':
      return 32_000;     // 32K tokens (图片生成)
    default:
      return DEFAULT_TOKEN_LIMIT;
  }
}
```

### 5.2 模型支持矩阵

| 模型 | Token 限制 | 特点 |
|------|-----------|------|
| gemini-1.5-pro | 2,097,152 | 最高上下文容量 |
| gemini-2.5-pro | 1,048,576 | 当前生产版本 |
| gemini-2.5-flash | 1,048,576 | 快速响应 |
| gemini-2.0-flash-exp-imag-gen | 32,000 | 图片生成专用 |

---

## 6. 缓存策略

### 6.1 ResultCache 类

**文件位置**: `packages/core/src/utils/filesearch/result-cache.ts`

**类定义**:
```typescript
export class ResultCache {
  private readonly cache: Map<string, string[]>;
  private hits = 0;
  private misses = 0;
}
```

**功能**:
- 缓存文件搜索结果
- 基于前缀优化的查找
- 统计缓存命中率

### 6.2 LruCache 类

**文件位置**: `packages/core/src/utils/LruCache.ts`

**类定义**:
```typescript
export class LruCache<K, V> {
  private cache: Map<K, V>;
  private maxSize: number;
}
```

**功能**:
- 最近最少使用缓存策略
- 自动淘汰旧数据
- 可配置的最大容量

### 6.3 路径去重

**ContextManager 中的 Set 追踪**:
```typescript
private readonly loadedPaths: Set<string> = new Set();
```

**优势**:
- O(1) 查找复杂度
- 自动去重
- 内存高效

---

## 7. 数据流与交互

### 7.1 组件交互图

```
┌────────────────────────────────────────────────────────────────┐
│                          Config                                │
│  ┌───────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │ ContextManager│←→│Workspace     │  │ FileDiscovery       │ │
│  │               │  │Context       │  │Service              │ │
│  └───────┬───────┘  └──────┬───────┘  └─────────────────────┘ │
│          │                 │                                   │
│          ▼                 ▼                                   │
│  ┌───────────────┐  ┌──────────────┐                          │
│  │MemoryDiscovery│  │Resource      │                          │
│  │               │  │Registry      │                          │
│  └───────────────┘  └──────────────┘                          │
│          │                 │                                   │
│          ▼                 ▼                                   │
│  ┌───────────────┐  ┌──────────────┐                          │
│  │PromptRegistry │  │MCP Client    │                          │
│  │               │  │Manager       │                          │
│  └───────────────┘  └──────────────┘                          │
└────────────────────────────────────────────────────────────────┘
```

### 7.2 上下文加载流程

```
用户启动 Gemini CLI
         │
         ▼
┌─────────────────┐
│ Config 初始化    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ContextManager  │
│ .refresh()      │
└────────┬────────┘
         │
    ┌────┴─────┐
    │          │
    ▼          ▼
┌────────┐ ┌──────────┐
│加载全局  │ │加载环境   │
│记忆      │ │记忆       │
└────────┘ └──────┬───┘
                │
                ▼
         ┌──────────────┐
         │ 合并 MCP 指令 │
         └──────┬───────┘
                │
                ▼
         ┌──────────────┐
         │ 发送 Memory   │
         │ Changed 事件  │
         └──────────────┘
```

### 7.3 JIT 上下文发现流程

```
AI 访问文件/目录
         │
         ▼
┌──────────────────┐
│ discoverContext()│
└────────┬─────────┘
         │
         ▼
┌──────────────────────┐
│ 验证路径在信任根内    │
└────────┬─────────────┘
         │
         ▼
┌──────────────────────┐
│ 从路径向上遍历查找    │
│ GEMINI.md 文件       │
└────────┬─────────────┘
         │
         ▼
┌──────────────────────┐
│ 过滤已加载的路径      │
└────────┬─────────────┘
         │
         ▼
┌──────────────────────┐
│ 加载新文件内容        │
└────────┬─────────────┘
         │
         ▼
┌──────────────────────┐
│ 标记为已加载          │
└──────────────────────┘
```

---

## 8. 设计模式总结

### 8.1 分层模式 (Layered Architecture)

- **全局层**: 用户主目录的配置
- **环境层**: 工作区/项目级配置
- **JIT 层**: 按需加载的子目录配置

### 8.2 观察者模式 (Observer Pattern)

**WorkspaceContext 事件系统**:
```typescript
private onDirectoriesChangedListeners = new Set<() => void>();

onDirectoriesChanged(listener: () => void): Unsubscribe {
  this.onDirectoriesChangedListeners.add(listener);
  return () => {
    this.onDirectoriesChangedListeners.delete(listener);
  };
}

private notifyDirectoriesChanged() {
  for (const listener of [...this.onDirectoriesChangedListeners]) {
    try {
      listener();
    } catch (e) {
      debugLogger.warn(`Error in listener: ${e}`);
    }
  }
}
```

### 8.3 注册表模式 (Registry Pattern)

**ResourceRegistry** 和 **PromptRegistry**:
- 集中管理资源/提示
- 按服务器分组
- 支持动态添加/移除

### 8.4 策略模式 (Strategy Pattern)

**Token 限制策略**:
```typescript
export function tokenLimit(model: Model): TokenCount {
  switch (model) {
    case 'gemini-1.5-pro': return 2_097_152;
    case 'gemini-2.5-flash': return 1_048_576;
    // ...
  }
}
```

### 8.5 缓存模式 (Cache Pattern)

**多层缓存**:
1. ResultCache: 搜索结果缓存
2. LruCache: LRU 缓存
3. Set 去重: 已加载路径追踪

### 8.6 工厂模式 (Factory Pattern)

**过滤器创建**:
```typescript
constructor(projectRoot: string) {
  if (isGitRepository(projectRoot)) {
    this.gitIgnoreFilter = new GitIgnoreParser(projectRoot);
  }
  this.geminiIgnoreFilter = new GeminiIgnoreParser(projectRoot);

  if (this.gitIgnoreFilter) {
    const geminiPatterns = this.geminiIgnoreFilter.getPatterns();
    this.combinedIgnoreFilter = new GitIgnoreParser(
      projectRoot,
      geminiPatterns
    );
  }
}
```

---

## 9. 性能优化技术

### 9.1 并发处理

**文件读取批处理**:
```typescript
const CONCURRENT_LIMIT = 20;
for (let i = 0; i < filePaths.length; i += CONCURRENT_LIMIT) {
  const batch = filePaths.slice(i, i + CONCURRENT_LIMIT);
  const batchPromises = batch.map(async (filePath) => {
    // 处理文件
  });
  await Promise.allSettled(batchPromises);
}
```

### 9.2 路径规范化

**符号链接处理**:
```typescript
private fullyResolvedPath(pathToCheck: string): string {
  try {
    return fs.realpathSync(path.resolve(this.targetDir, pathToCheck));
  } catch (e) {
    if (isNodeError(e) && e.code === 'ENOENT' && e.path) {
      return e.path;  // 返回解析后的路径
    }
    throw e;
  }
}
```

### 9.3 早期退出优化

**项目根目录检测**:
```typescript
while (true) {
  if (currentDir === globalGeminiDir) break;  // 早期退出
  // ...
  if (currentDir === ultimateStopDir) break;
  currentDir = path.dirname(currentDir);
}
```

### 9.4 内存优化

**Set 去重**:
```typescript
private markAsLoaded(paths: string[]): void {
  for (const p of paths) {
    this.loadedPaths.add(p);  // O(1) 插入
  }
}
```

### 9.5 容错设计

**错误隔离**:
```typescript
for (const listener of [...this.onDirectoriesChangedListeners]) {
  try {
    listener();
  } catch (e) {
    // 单个监听器失败不影响其他监听器
    debugLogger.warn(`Error in listener: ${e}`);
  }
}
```

---

## 附录

### A. 关键常量定义

```typescript
// 默认 Token 限制
export const DEFAULT_TOKEN_LIMIT = 1_048_576;

// 并发限制
const FILE_READ_CONCURRENT_LIMIT = 20;
const DIR_TRAVERSAL_CONCURRENT_LIMIT = 10;

// 默认发现目录数
const DEFAULT_MAX_DIRS = 200;

// 配置目录
const GEMINI_DIR = '.gemini';
```

### B. 事件类型

```typescript
enum CoreEvent {
  MemoryChanged = 'memory-changed',
  // 其他事件...
}
```

### C. 文件名变体

```typescript
function getAllGeminiMdFilenames(): string[] {
  return ['GEMINI.md', 'CLAUDE.md', 'AI.md'];
}
```

---

## 参考资料

- [Gemini CLI 架构文档](/docs/architecture.md)
- [GEMINI.md 文档](/docs/cli/gemini-md.md)
- [上下文缓存文档](/docs/cli/token-caching.md)
- [信任文件夹文档](/docs/cli/trusted-folders.md)

---

**文档结束**
