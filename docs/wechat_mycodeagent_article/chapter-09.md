# 九、Skills：把经验变成可复用的 SOP

有个问题困扰了我很久。

同样是让 Agent 做代码审查，有的能一眼看出"这个改动会打破那边的抽象"，有的却只能发现"第 5 行缩进不对"。**差距在哪？**

后来我明白了：不是工具不够多，是 Agent "有手没脑"——它会用 Read 读代码、用 Grep 搜引用，但**不知道什么才算"审查好"**。

就像给新手程序员开了所有系统的权限，却没给操作手册。MCP 解决的是"能不能连上"，但"连上之后怎么干"，需要另一层封装。

这就是 Skills。

---

## 1、说白了，Skills 是什么？

**把个人经验写成 SOP，让 Agent 按需调用。**

你有没有这种崩溃经历？每次让 Agent 写技术博客，都要重复念叨：
- "开头要抓人，别写'随着XX的发展'"
- "技术点要有证据，给数字、给代码路径"
- "结尾要升华，别干巴巴总结"

明明教过一百遍，下次还得再说。大概是职业病吧，我受够了这种重复劳动。

Skills 就是来解决这个的。把这套经验写成 `SKILL.md`，塞进 `skills/tech-blog-writing/`：

```markdown
---
name: tech-blog-writing
description: 撰写技术分享博客，包含开头、技术点、结尾的标准流程
---

# 技术博客写作 SOP

## 1. 开头（黄金3秒）
用痛点或故事引入，别写"随着XX的发展"。

## 2. 技术内容
- 先讲"为什么"，再讲"是什么"  
- 用具体数字、代码路径当"证据锚点"

## 3. 结尾
升华到认知层面，给读者一个行动建议。

$ARGUMENTS
```

注意最后的 `$ARGUMENTS`，这是参数占位符。调用时传参：
```json
{"name": "tech-blog-writing", "args": "主题是MCP协议"}
```

`$ARGUMENTS` 就被替换成"主题是MCP协议"。**一套 SOP，多处复用**，不用为每个主题写一个新技能。

---

## 2、渐进式披露：省 Token 的秘诀

你可能会问：为什么不直接把这套 SOP 写进系统提示？每次都用呗。

问题在这：**技能多了，全部塞进系统提示，上下文立马爆炸。**

假设你有 20 个技能，每个 2000 字，那就是 4 万字。模型还没开始干活，Token 先烧掉一堆。

Skills 的核心设计是**渐进式披露（Progressive Disclosure）**：

| 层级 | 内容 | 加载时机 | Token 消耗 |
|-----|------|---------|-----------|
| 第一层 | 元数据（name/description） | 启动时 | 约 100/技能 |
| 第二层 | 技能正文（完整 SOP） | 命中时 | 1000-5000 |
| 第三层 | 附加资源（脚本/模板） | 按需 | 看情况 |

**只有 name 和 description 常驻系统提示**，正文命中才读。

社区有个真实案例：
- MCP 方式：连一个数据库 MCP，所有表结构全塞上下文 → **16000 Token**
- Skills 方式：只在系统提示放 "mysql-analysis: 分析员工数据库的技能" → **100 Token**

真正需要时再加载详细指令。**Token 省 90% 以上。**

代码在 `core/skills/skill_loader.py`：
```python
def format_skills_for_prompt(self, char_budget: int) -> str:
    lines = []
    for skill in skills:
        line = f"- {skill.name}: {skill.description}"
        if used + len(line) > char_budget:  # 严格控制预算
            break
        lines.append(line)
    return "\n".join(lines)
```

`agents/codeAgent.py` 启动时扫描技能，生成列表注入 L1 系统提示。模型看到的是：
```
Available Skills:
- tech-blog-writing: 撰写技术分享博客...
- code-review: 执行代码审查...
```

判断需要时，调用 Skill Tool 完整加载：
```python
content = f"Base directory for this skill: {base_dir}\n\n{expanded}"
```

---

## 3、两个关键机制：$ARGUMENTS 与 base_dir

Skills 不只是静态文档，有两个机制让它真正可用。

### $ARGUMENTS：参数化复用

在 `tools/builtin/skill.py` 里：
```python
def _apply_arguments(body: str, args: str) -> str:
    if "$ARGUMENTS" in body:
        return body.replace("$ARGUMENTS", args)  # 占位符替换
    if args:
        return f"{body}\n\nARGUMENTS: {args}"  # 追加到末尾
    return body
```

同样一个 `code-review` 技能：
```markdown
## 审查范围
$ARGUMENTS

## 审查清单
- 检查 SQL 注入风险
- 检查硬编码密钥
```

调用 `{"name": "code-review", "args": "src/auth.py"}` → 审查 `src/auth.py`。
调用 `{"name": "code-review", "args": "所有Python文件"}` → 审查全部。

**不用为每个场景写新技能。**

### base_dir 注入：路径不迷路

技能经常要引用项目文件，但技能文件在 `skills/xxx/` 下，项目根目录在哪？

`skill.py` 自动注入：
```python
content = f"Base directory for this skill: {base_dir}\n\n{expanded}"
```

`base_dir` 是技能文件相对于项目根目录的路径。技能里写相对路径，始终基于项目根目录。

比如在 `skills/pdf-processing/SKILL.md`：
```markdown
调用脚本：{base_dir}/parse_pdf.py
```

Agent 知道去哪找，不会迷路。

---

## 4、缓存策略：开发体验的小细节

还有个容易忽视但重要的设计：**怎么刷新技能？**

总不能每次调用都重新扫描吧？但如果一直缓存，改了技能又不生效。

`skill_loader.py` 用 **mtime 检测**：
```python
def refresh_if_stale(self):
    current_max_mtime, current_count = self._get_skills_state()
    if current_max_mtime != self._last_scan_mtime:
        return self.scan()  # 有变动，重新扫描
    return self.list_skills(refresh=False)  # 用缓存
```

- 启动时扫描，记录最大修改时间和文件数
- 每次调用前检查：mtime 变了或文件数变了，就重新扫描
- 否则用缓存

环境变量 `SKILLS_REFRESH_ON_CALL` 控制开关（默认开）。

**改完技能文件，下次调用就生效，不用重启 Agent。** 讲真，这种小细节让开发体验好很多。

---

## 5、Skills vs MCP：不是竞争，是互补

最后用一张表说清关系：

| 维度 | MCP | Skills |
|-----|-----|--------|
| 解决什么 | 能不能连上 | 连上之后怎么干 |
| 类比 | USB 接口/驱动 | 软件操作手册 |
| 上下文 | 急切加载（全量） | 渐进披露（按需） |
| 内容 | 工具定义、API Schema | 领域知识、工作流程 |
| 谁维护 | 外部服务方 | 项目/个人 |

MCP 让你能连数据库，Skills 让你知道：
- 怎么写正确的 SQL
- 怎么分析结果
- 怎么给出业务洞察

**两者配合，Agent 既有"手"，也有"脑"。**

---

## 6、写在最后

回顾整个系列：V0 → 工具重构 → Function Calling → 上下文工程 → 可观测性 → 扩展能力 → Skills。

**Skills 是给 Agent 装上"脑子"。** 不是让它更聪明（那是模型的事），而是让它**知道该怎么用已有的能力**。

把个人经验、团队规范，都固化成可复用的 SOP。价值在于：
1. **经验可迁移**——你的 review 经验，团队都能用
2. **上下文可控**——渐进披露，不爆炸
3. **灵活可复用**——一套 SOP，多处场景

Agent 开发到最后，拼的不是模型多强，而是工程细节做得多扎实。

---

**全文完。**

如果你也在做 Agent，祝你的 Agent 既有"手"，也有"脑"。
