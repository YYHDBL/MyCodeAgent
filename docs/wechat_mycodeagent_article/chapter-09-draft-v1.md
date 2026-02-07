# 九、Skills：把经验变成可复用的 SOP

有个问题困扰了我很久：为什么有些 Agent 能干出漂亮的活，有些却像个"有手没脑"的笨蛋？

举个例子。我让 Agent 做代码审查，它倒是能一行一行看，但只能发现"这行少了空格"这种表面问题。至于"这段代码违反了项目规范""这个改动会影响那个模块"——它完全看不出来。

**不是它不会用工具，而是它不知道怎么才算"审查好"。**

后来我明白了：MCP 解决的是"能不能连上"，但"连上之后怎么干"，需要另一层封装。这就是 Skills 要解决的问题。

---

## 1、Skills 到底是什么？

简单说，**Skills 是把个人经验固化为可调用 SOP 的机制**。

你有没有这种经历？每次让 Agent 写技术博客，都要重复教它"开头要抓人、技术点要有证据、结尾要有洞察"。明明说过一百遍，下次还是得再说一遍。

Skills 就是来解决这个痛点的。你把这套经验写成 `SKILL.md`，放到 `skills/tech-blog-writing/` 目录下，以后 Agent 就能像查手册一样调用它。

文件结构很简单：
```
skills/
  tech-blog-writing/
    SKILL.md
```

`SKILL.md` 内容长这样：
```markdown
---
name: tech-blog-writing
description: 撰写技术分享博客，包含开头、技术点、结尾的标准流程
---

# 技术博客写作 SOP

## 1. 开头（黄金3秒）
用痛点或故事引入，避免"随着XX的发展"。

## 2. 技术内容
- 先讲"为什么"，再讲"是什么"
- 用具体数字、代码路径、阈值当"证据锚点"

## 3. 结尾
升华到认知层面，给出行动建议。

$ARGUMENTS
```

看到最后的 `$ARGUMENTS` 了吗？这是技能调用的参数占位符。调用时可以传参：
```json
{"name": "tech-blog-writing", "args": "主题是MCP协议"}
```

然后 `$ARGUMENTS` 会被替换成"主题是MCP协议"。**一套 SOP，多处复用。**

---

## 2、渐进式披露：解决上下文爆炸的秘诀

你可能想问：为什么不直接把这套 SOP 写进系统提示？每次都用不就行了？

问题在这儿：**技能多了之后，全部塞进系统提示，上下文立马爆炸。**

假设你有 20 个技能，每个技能 2000 字，那就是 4 万字。模型还没开始干活，Token 已经烧掉一堆了。

Skills 的核心设计是**渐进式披露（Progressive Disclosure）**：

| 层级 | 内容 | 时机 | Token消耗 |
|-----|------|------|----------|
| 第一层 | 元数据（name/description） | 启动时加载 | 约100/技能 |
| 第二层 | 技能正文（完整SOP） | 命中时加载 | 1000-5000 |
| 第三层 | 附加资源（脚本/模板） | 按需加载 | 看情况 |

**只有 name 和 description 常驻系统提示**，正文只有命中时才读取。

举个例子对比：
- MCP 方式：连接一个数据库 MCP，所有表结构、API 定义全塞进上下文 → **16000 Token**
- Skills 方式：只在系统提示放 "mysql-analysis: 分析员工数据库的技能" → **100 Token**

等到真的需要分析数据库时，才加载详细指令和表结构。**90% 以上的 Token 省下来了。**

代码实现在 `core/skills/skill_loader.py`：
```python
def format_skills_for_prompt(self, char_budget: int) -> str:
    # 只列出 name: description，严格控制预算
    lines = []
    for skill in skills:
        line = f"- {skill.name}: {skill.description}"
        if used + len(line) > char_budget:
            break
        lines.append(line)
    return "\n".join(lines)
```

在 `agents/codeAgent.py` 里，启动时扫描技能，生成技能列表注入 L1 系统提示。模型看到的是：
```
Available Skills:
- tech-blog-writing: 撰写技术分享博客...
- code-review: 执行代码审查...
- test-case-design: 设计测试用例...
```

当模型判断需要某个技能时，调用 Skill Tool，才会完整加载：
```python
# tools/builtin/skill.py
content = f"Base directory for this skill: {base_dir}\n\n{expanded}"
return {
    "data": {"name": skill.name, "base_dir": base_dir, "content": content},
    "text": f"Loaded skill '{skill.name}'."
}
```

---

## 3、关键机制：$ARGUMENTS 与 base_dir

Skills 有两个关键机制，让它从"静态文档"变成"动态 SOP"。

### $ARGUMENTS：参数化复用

上面例子里的 `$ARGUMENTS` 不是摆设。在 `tools/builtin/skill.py` 里：
```python
def _apply_arguments(body: str, args: str) -> str:
    if "$ARGUMENTS" in body:
        return body.replace("$ARGUMENTS", args)
    if args:
        return f"{body}\n\nARGUMENTS: {args}"
    return body
```

如果技能文件里有 `$ARGUMENTS`，就替换；如果没有但有传参，就追加到末尾。

这有什么用？**同一个技能可以应对不同场景。**

比如 `code-review` 技能，可以写：
```markdown
## 审查范围
$ARGUMENTS

## 审查清单
- 检查 SQL 注入风险
- 检查硬编码密钥
- 检查单元测试覆盖率
```

调用 `{"name": "code-review", "args": "src/auth.py"}` → 审查范围变成 `src/auth.py`。
调用 `{"name": "code-review", "args": "所有Python文件"}` → 审查范围变成 "所有Python文件"。

**一套 SOP，多处复用，不用为每个场景写一个新技能。**

### base_dir 注入：路径一致性

另一个坑是路径。技能里经常要引用项目文件，但技能文件放在 `skills/xxx/` 下，怎么知道项目根目录在哪？

`skill.py` 会自动注入：
```python
content = f"Base directory for this skill: {base_dir}\n\n{expanded}"
```

`base_dir` 是技能文件相对于项目根目录的路径。技能正文里可以用相对路径，始终基于项目根目录。

比如在 `skills/pdf-processing/SKILL.md` 里：
```markdown
调用脚本：{base_dir}/parse_pdf.py
```

Agent 拿到后知道去哪找脚本，不会迷路。

---

## 4、缓存与刷新：工程化的细节

Skills 还有一个容易被忽视但很重要的设计：**缓存策略**。

技能文件存在磁盘上，总不能每次调用都重新扫描一遍吧？但如果一直缓存，改了技能文件又无法生效。

`skill_loader.py` 的做法是 **mtime 检测**：
```python
def refresh_if_stale(self) -> List[SkillMeta]:
    current_max_mtime, current_count = self._get_skills_state()
    if current_max_mtime != self._last_scan_mtime or current_count != self._last_scan_count:
        return self.scan()
    return self.list_skills(refresh=False)
```

- 启动时扫描一次，记录所有技能文件的最大修改时间和数量
- 每次调用技能前检查：如果 mtime 变了或文件数量变了，就重新扫描
- 否则用缓存

环境变量 `SKILLS_REFRESH_ON_CALL` 控制是否开启这个行为（默认开启）。

**这个小细节让开发体验好很多：改完技能文件，下次调用就生效，不用重启 Agent。**

---

## 5、对比：用不用 Skills，差别在哪？

举个例子直观感受一下。

### 场景：写技术博客

**不用 Skills**：
```
User: 帮我写一篇关于 MCP 的技术博客
Agent: （迷茫）MCP 是什么？博客要怎么写？
[然后你得一步步教它...]
```

**用了 Skills**：
```
User: 帮我写一篇关于 MCP 的技术博客
Agent: （识别到 tech-blog-writing 技能）
       → 调用 Skill("tech-blog-writing", "MCP协议")
       → 拿到完整 SOP
       → 按 SOP 执行：开头→技术点→结尾
```

**差别不是"能不能写"，而是"知不知道该怎么写"。**

### Skills vs MCP

| 维度 | MCP | Skills |
|-----|-----|--------|
| 解决什么问题 | 能不能连上 | 连上之后怎么干 |
| 类比 | USB 接口/驱动 | 软件操作手册 |
| 上下文策略 | 急切加载（全量） | 渐进式披露（按需） |
| 内容 | 工具定义、API Schema | 领域知识、工作流程 |
| 谁来维护 | 外部服务提供方 | 项目/个人 |

**两者不是竞争关系，是互补关系。**

MCP 让你能连数据库，Skills 让你知道怎么写正确的 SQL、怎么分析结果、怎么给出业务洞察。

---

## 6、写在最后

回顾整个系列，我们从 V0 起步，一路走过工具重构、Function Calling、上下文工程、可观测性、扩展能力，终于来到 Skills。

**Skills 是给 Agent 装上了"脑子"。**

不是让它更聪明（那是模型的事），而是让它**知道该怎么用已有的能力**。把个人的工程经验、团队的规范流程，都固化成可复用的 SOP。

这套机制的价值在于：
1. **经验可迁移**：你的 review 经验可以分享给团队任何人
2. **上下文可控**：渐进式披露避免信息爆炸
3. **灵活可复用**：$ARGUMENTS 让一套 SOP 应对多种场景

**Agent 开发到最后，拼的不是模型多强，而是工程细节做得多扎实。**

---

**全文完。**

感谢阅读这个系列。如果你也在做 Agent，祝你的 Agent 既有"手"，也有"脑"。
