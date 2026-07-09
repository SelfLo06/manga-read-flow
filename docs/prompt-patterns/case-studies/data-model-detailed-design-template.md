# Data Model Prompt Pattern v0.1

## 1. 总体方法

我们采用的是：

```text
GOAL.md
→ HARNESS.md
→ proposal agents
→ cross-review agent
→ limited revision loop
→ synthesizer agent
→ harness validation
→ ADR / open questions
```

这和项目规划里定义的设计阶段 AI / Codex 协作流程一致：设计阶段不是让一个 agent 直接写最终文档，而是先定义目标与验证标准，再让多个 proposal agent 独立提出方案，之后 cross-review、synthesis、validation、ADR 化。

核心目的不是“让 Codex 一次写对”，而是：

```text
用多视角 proposal 暴露设计差异
用 cross-review 找冲突、遗漏和过度设计
用 synthesis 收敛成唯一基线
用 HARNESS 验证设计是否支撑关键场景
用 ADR 记录关键取舍
```

---

# 2. 分层提示词结构

## 2.1 全局层：AGENTS.md / 项目全局提示词

作用：固定长期规则。

内容重点：

```text
项目定位
软件工程原则
AI 协作原则
架构边界
禁止事项
Git / commit / push 规则
设计任务与实现任务的区别
```

这一层不应该塞数据模型细节。它只固定不变量，例如：

```text
Provider Adapter 不访问数据库
ArtifactService 统一管理 artifact
Repository / DAO 统一访问 SQLite
原图永不覆盖
不写规避第三方 Provider 策略的逻辑
```

这些不变量来自 HLD，HLD 已明确 Provider Adapter、ArtifactService、Repository / DAO、WorkflowLoopEngine、QualityCheckService 的职责边界。

---

## 2.2 任务目标层：GOAL.md

作用：定义本轮设计到底要完成什么。

Data Model 的 GOAL 应该限定：

```text
本轮只做数据模型详细设计
不写代码
不写 SQL DDL
不写 ORM
不写 migration
不设计完整 API
不实现前端
```

GOAL 还要定义产物：

```text
final/data-model-dd-v0.1.md
final/schema-outline.md
final/state-data-impact.md
final/open-questions.md
final/erd.mmd
adr/*.md
```

Data Model 最终确实产出了完整设计、schema outline、state-data-impact、open questions 和 ADR 列表；最终文档也记录了它综合读取了 SRS、HLD、GOAL、HARNESS、五份 proposal 和 review 文件。

---

## 2.3 验证层：HARNESS.md

作用：不是描述“怎么写”，而是定义“什么算通过”。

Data Model HARNESS 重点验证：

```text
hard invariants
scenario replay
required entities
ownership boundary
recovery support
artifact lifecycle
export gate
idempotency
scope control
```

这一步很关键。没有 HARNESS，Codex 很容易输出“看起来完整”的数据模型，但无法证明它支撑：

```text
OCR edit
translation edit
provider refusal
cleaning skip
typesetting overflow
crash recovery
export blocking
```

最终的 `state-data-impact.md` 就是典型 harness 结果：它逐个说明这些关键状态变化如何落到数据层。

---

# 3. Proposal Agent 设计

## 3.1 为什么用五个 proposal agents

Data Model 是高风险核心设计，不适合单 agent 直接定稿。我们拆成五个视角：

```text
1. Domain Model Agent
2. Persistence Agent
3. Workflow-State Agent
4. Artifact-Quality Agent
5. API / ORM Readiness Agent
```

每个 agent 独立读取 SRS、HLD、GOAL、HARNESS，不读取其他 proposal。这样可以减少互相污染。

## 3.2 五个 agent 的关注点

```text
Domain Model Agent
关注实体职责、聚合边界、版本化、active result、glossary、stale 关系。

Persistence Agent
关注 app.db / project.db、索引、唯一性、migration、soft delete、Project 隔离。

Workflow-State Agent
关注 ProcessingTask、WorkflowAttempt、WorkflowDecision、状态恢复、幂等、stale 传播。

Artifact-Quality Agent
关注 ProcessingArtifact、QualityIssue、ToolRunLog、provider refusal、failed payload、export gate。

API / ORM Readiness Agent
关注 SQLAlchemy / Pydantic / FastAPI 后续映射可行性，但不设计完整 API / ORM。
```

这五个角色基本覆盖了数据模型的主要风险面：领域建模、持久化、workflow、artifact / quality、实现映射。

---

# 4. Proposal 文件结构

每个 proposal 要求相同结构，便于 cross-review。

推荐保留这个结构：

```text
1. 范围
2. 角色偏置
3. 假设
4. 提议实体
5. P0 / P1 / P2 分类
6. app.db 与 project.db 放置
7. 关键字段
8. 关系
9. 版本化规则
10. Active pointer 规则
11. 状态与 stale 规则
12. Artifact 关系
13. 幂等性与 cache keys
14. 删除与 retention policy
15. Migration 关注点
16. 风险
17. 被拒绝的备选方案
18. 有意留到后续轮次的决策
19. 对 HARNESS.md 中所有场景的验证
20. 未决问题
```

其中最有价值的是这几项：

```text
Role Bias
P0 / P1 / P2 classification
Rejected alternatives
Validation against HARNESS
Open questions
```

它们能防止 proposal 变成“单向输出”，逼 agent 暴露自己的偏置、取舍、未决点和场景覆盖情况。

---

# 5. 必须显式讨论的实体

Data Model proposal 不能只泛泛说“数据库表”。每个 proposal 必须显式讨论：

```text
Project / Batch / Page / TextBlock
OCRResult
TranslationResult
GlossaryTerm / GlossaryVersion
ProcessingTask
WorkflowAttempt / WorkflowDecision
QualityIssue
ProcessingArtifact
ToolRunLog
ExportRecord
ProcessingProfile
```

最终 data model 也确实收敛出 P0 实体集，并把 Project、Batch、Page、TextBlock、OCRResult、TranslationResult、Glossary、ProcessingTask、WorkflowAttempt、WorkflowDecision、QualityIssue、ProcessingArtifact、ToolRunLog、ExportRecord、ProcessingProfile / Snapshot 都纳入 P0 / P1 / P2 分类。

---

# 6. Hard Rules 设计

Data Model 阶段的 hard rules 很重要。核心规则包括：

```text
不要实现代码。
不要创建 migrations。
不要写 SQL DDL。
不要设计完整 API。
不要修改无关文件。
proposal 轮次不要编辑 final design files。
proposal 轮次不要编辑 ADR files。
不要发明 SRS / HLD 之外的功能。
不清楚时列为 open question。
如果 SRS 和 HLD 冲突，报告冲突。
```

项目架构硬约束也要重复写进任务 prompt：

```text
Provider adapters must not own persistence.
Provider adapters must not own artifact lifecycle.
Provider adapters must not decide retry / fallback / skip / block.
Provider adapters must not create QualityIssue.
No image BLOBs in SQLite.
Original images must never be overwritten.
API keys must not be stored in project.db.
Logs and examples must not include secrets.
```

这些规则直接对应最终 Data Model 的关键决策：图片和大 payload 只进文件系统，OCR / Translation 结果不可变版本化，active pointer 是 P0 source of truth，WorkflowAttempt / Decision / ToolRunLog / QualityIssue / ProcessingArtifact 用于解释恢复和导出 gate，Provider Adapter 不接触数据库和 artifact 生命周期。

---

# 7. Cross-Review Agent 设计

Cross-review 的职责不是“润色”，而是找问题。

它应该输出：

```text
1. 每份 proposal 摘要
2. proposals 之间的冲突
3. 缺失实体
4. 缺失关系
5. 被违反的不变量
6. 未支持的场景
7. 过度设计的部分
8. 设计不足的部分
9. migration 风险
10. ORM 风险
11. artifact lifecycle 风险
12. recovery 风险
13. 重复 source-of-truth 风险
14. 推荐最终决策
15. ADR candidates
16. blocking issues
17. non-blocking issues
18. 阻塞 final synthesis 的 open questions
19. 不阻塞 final synthesis 的 open questions
```

这里最关键的是区分：

```text
blocking issue
non-blocking issue
open question that blocks synthesis
open question that does not block synthesis
```

最终 `open-questions.md` 也遵循了这个原则：阻塞性问题已经被 synthesis 解决，剩下的是 enum 拼写、ID 格式、retention TTL、warning export 确认、cleanup failure 是否用户可见等非阻塞问题。

---

# 8. Limited Revision Loop

我们没有设计无限 debate，而是限制最多两轮 revision。

规则：

```text
只修改受 blocking issue 影响的 proposal
不改 final
不改 ADR
不改无关文件
每个修改 proposal 顶部加 Revision Notes
解释修了什么、对应哪个 review issue
不能静默删除 open question
两轮后仍有 blocker 就停止并报告
```

这是范围控制关键点。数据模型这种基础设计值得 review / revision，但不能无限循环。

---

# 9. Synthesizer Agent 设计

Synthesizer 不是“把五份 proposal 拼起来”，而是要做裁决。

它必须读取：

```text
SRS
HLD
GOAL
HARNESS
all proposals
all reviews
revision notes
```

并且只允许编辑 final 和 ADR 文件。

推荐产物：

```text
final/data-model-dd-v0.1.md
final/erd.mmd
final/schema-outline.md
final/state-data-impact.md
final/open-questions.md
adr/*.md
```

最终文档结构应包括：

```text
Design goals
Source documents
app.db / project.db split
Full entity list
P0 / P1 / P2 classification
Entity responsibility table
Relationship table
Key fields
Indexes and uniqueness
Versioning rules
Active pointer rules
Stale propagation rules
Artifact lifecycle
WorkflowAttempt / WorkflowDecision
QualityIssue
ToolRunLog
ExportRecord
ProcessingProfile
Soft delete
Migration strategy
Idempotency strategy
Scenario replay
ADR list
Open questions
Rejected alternatives
Risks and mitigations
Deferred decisions
```

这套结构后续可以作为其他详细设计的最终文档模板。

---

# 10. Harness Validation Agent 设计

最后单独跑 validation，而不是让 synthesizer 自证通过。

Validation report 要检查：

```text
Invariant checklist: PASS / FAIL / UNCLEAR
Scenario replay: PASS / FAIL / UNCLEAR
Missing fields
Ambiguous ownership
Duplicated source-of-truth risks
Recovery gaps
Idempotency gaps
Artifact lifecycle gaps
Export blocking gaps
Whether acceptable for MVP backend skeleton
```

这一步的作用是防止 synthesis 看起来完整，但没有真正覆盖关键场景。

---

# 11. Commit 策略

我们最后采用的是：

```text
设计文档阶段允许及时 commit
只 stage 当前目标文件
每个 proposal 可单独 commit
cross-review 单独 commit
final + ADR 一组 commit
harness validation 单独 commit
禁止 push / pull / rebase
禁止提交无关文件、缓存、日志、secret、AI runtime 文件
```

这个策略和 PROJECT-PLAN 里的 AI agent 约束一致：设计文档阶段可以及时 commit，但必须只提交目标文件，不 push，不混入实现代码。

---

# 12. Data Model 阶段的关键产出内容

最终 Data Model 不是停留在“表清单”，而是解决了这些关键问题：

```text
app.db + project.db split
Project isolation
image / large payload filesystem-only
ProcessingArtifact metadata lifecycle
OCRResult / TranslationResult immutable versioning
active pointer source of truth
ProcessingProfileSnapshot
WorkflowAttempt / WorkflowDecision
ToolRunLog
QualityIssue export gate
Provider refusal persistence
crash recovery source of truth
stale propagation
idempotency / cache keys
soft delete / trash
migration strategy
open questions
ADR list
```

其中几个最重要的设计结论：

```text
active pointer 替代 result active flag
normal export 阻塞 open blocking QualityIssue
warning export 由 ProcessingProfileSnapshot 决定
provider refusal 记录为 ToolRunLog + WorkflowAttempt + QualityIssue + WorkflowDecision
recovery 不能只依赖 Page.status
Provider Adapter 不拥有持久化、artifact 生命周期、retry / fallback / skip / block、QualityIssue 创建
```

这些结论已经在最终 Data Model 和 HLD v0.2 的同步边界中固定下来。

---

# 13. 后续设计可复用模板

后续做任何 P0 详细设计，可以复用这个模式。

## 13.1 Prompt 结构模板

```text
你是 <design-area> detailed design 的 orchestrator。

这只是一项设计文档任务。
不要实现代码。
不要创建 migrations。
不要写 production code。
不要修改无关文件。

阅读：
- AGENTS.md
- SRS
- HLD
- PROJECT-PLAN
- 相关先前详细设计
- <design-area>/GOAL.md
- <design-area>/HARNESS.md

阶段：
1. Preflight
2. Independent proposals
3. Cross-review
4. Limited revision
5. Synthesis
6. Harness validation
7. ADR / final report
```

## 13.2 Proposal agent 模板

```text
每份 proposal 必须包含：
1. Scope
2. Role Bias
3. Assumptions
4. Proposed model / interfaces / lifecycle
5. P0 / P1 / P2 classification
6. Responsibilities and ownership
7. Relationships with existing architecture
8. State / artifact / workflow impact
9. Idempotency / recovery impact
10. Failure modes
11. Risks
12. Rejected alternatives
13. Decisions left to later rounds
14. Validation against HARNESS scenarios
15. Open questions
```

## 13.3 Review 模板

```text
Review 必须查找：
- conflicts
- missing concepts
- violated architecture invariants
- unsupported scenarios
- over-designed parts
- under-designed parts
- recovery gaps
- ownership ambiguity
- duplicated source-of-truth risks
- blocking issues
- non-blocking issues
- ADR candidates
```

## 13.4 Synthesis 模板

```text
Final design 必须：
- select one coherent design
- explain rejected alternatives
- define P0 / P1 / P2 boundaries
- include scenario replay
- include risks and mitigations
- list open questions
- generate ADRs for major decisions
- remain consistent with SRS / HLD / Data Model
```

---

# 14. 对后续设计的直接建议

后续 `workflow-state` 详细设计应该几乎照搬这个流程，但 agent 角色要换成：

```text
1. State Machine Agent
2. Workflow Loop Policy Agent
3. Recovery & Idempotency Agent
4. Quality Gate Interaction Agent
5. API / Repository Readiness Agent
```

同时 HARNESS 场景要围绕：

```text
happy path
OCR edit
translation edit
provider refusal
retry budget exhausted
cleaning skip
typesetting overflow
crash after OCR
crash after artifact write before DB registration
export with blocking issue
warning export
pause / cancel / resume
idempotent rerun
```

数据模型阶段证明了一件事：**多 agent + harness + synthesis 的成本是值得的，但必须强约束范围、强制 scenario replay、强制 rejected alternatives，否则就会变成冗长文档生成。**
