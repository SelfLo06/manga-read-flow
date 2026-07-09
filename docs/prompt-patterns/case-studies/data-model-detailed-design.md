# 数据模型详细设计案例研究

本文保留 Data Model prompt-pattern，作为一次成功详细设计协作的案例研究。

它不是之后每个设计任务的默认模板。使用它来理解 Data Model 轮次中哪些做法有效，然后在较小设计领域中缩小可复用模式的规模。

来源案例：

- `docs/prompt-patterns/data-model-detailed-design-template.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/data-model/final/schema-outline.md`
- `docs/design/data-model/final/state-data-impact.md`
- `docs/design/data-model/final/open-questions.md`

## 案例流程

Data Model 轮次使用了以下协作流程：

```text
GOAL
-> HARNESS
-> proposal agents
-> cross-review
-> limited revision loop
-> synthesizer
-> harness validation
-> ADR / open questions
```

重点不是让一个 agent 立刻写出最终答案。重点是暴露设计差异，用架构不变量和场景审查这些差异，然后综合成一个一致基线。

## 保留下来的有用想法

### 带角色偏置的 Proposal Agents

Data Model 任务使用了带不同偏置的 proposal agents：

- Domain model
- Persistence
- Workflow state
- Artifact and quality
- API / ORM readiness

每份 proposal 都必须阅读相同权威输入，但从不同风险面切入问题。这降低了单一视角掩盖重要冲突的概率。

### P0 / P1 / P2 分类

每份 proposal 都必须将实体和行为分为 MVP 关键范围、近期范围和延后范围。

这有助于防止数据模型对 MVP-0 恢复来说过薄，或为了未来 P1 / P2 功能而过宽。

### 强不变量

prompts 反复强调不可违反的架构规则：

- No image BLOBs in SQLite.
- Original images are never overwritten.
- Provider adapters do not access the database.
- Provider adapters do not own artifact lifecycle.
- Provider adapters do not decide retry, fallback, skip, warning, or block.
- ArtifactService owns official artifact lifecycle.
- Repository / DAO is the SQLite boundary.
- API keys and secrets are not stored in project databases or logs.

这些不是可选偏好，而是从 SRS 和 HLD 继承下来的设计 guard。

### 对 HARNESS 场景进行验证

HARNESS 要求 proposals 和最终 synthesis 解释以下场景：

- OCR edit
- Translation edit
- Provider refusal
- Cleaning skip
- Typesetting overflow
- Crash recovery
- Export blocking
- Idempotent rerun

最终 Data Model 设计必须证明数据层能够通过 entities、active pointers、attempts、decisions、issues、artifacts 和 dependency hashes 解释这些场景。

### Cross-Review 重点

Cross-review 不是润色 prose 的步骤。它查找：

- proposals 之间的冲突；
- 缺失实体；
- 缺失关系；
- 过度设计；
- 设计不足；
- 被违反的不变量；
- HARNESS 场景未被支持；
- 重复事实来源风险；
- recovery 和 export gate 缺口；
- 阻塞问题与非阻塞问题。

这让 review 成为工程过滤器，而不只是第二意见。

### 有限 Revision Loop

流程允许有限 revision loop，而不是无休止争论。

revision 仅针对 blocking issues，必须保留 open questions，且不允许 proposal agents 直接编辑最终设计文件。如果达到限制后仍有 blockers，流程应停止并报告 unresolved decision。

### Synthesizer 作为决策者

Synthesizer 不是机械合并 proposal 文本。

它必须选择一个一致设计、拒绝备选方案、解决冲突、产出最终文档，并为重要决策创建 ADR。这就是最终 Data Model 结果能成为基线，而不是拼贴 proposal 包的原因。

### Validation Agent 与 Synthesizer 分离

最终 validation step 独立于 synthesis。

这避免 synthesizer 自证自己的设计。Validation 检查最终设计是否满足不变量、回放 HARNESS 场景，并将剩余缺口识别为 open questions 或 implementation validation needs。

## Data-Model 专属部分

不要盲目复制到每个设计任务：

- 精确的五个 proposal roles 是 Data-Model-specific。
- 必需实体列表是 Data-Model-specific。
- Schema outline、ERD、active pointer rules、migration concerns 和 data placement 并非每个设计领域都需要。
- 对基础架构来说，重量级 proposal / review / synthesis 流程是合理的；但对窄实现决策来说太重。
- Data Model 需要深入的 persistence 和 recovery 分析；UI flow、API endpoint、export manifest 或 testing strategy 可能需要不同 roles 和不同 harness scenarios。

## 可在其他地方复用的经验

- 先明确 GOAL 和 HARNESS，再请求 proposals。
- 只有存在多个真实风险面时，才使用 role-biased agents。
- 尽早明确 P0 / P1 / P2 scope。
- 当违反规则会破坏设计时，在任务 prompt 中重复 hard invariants。
- 让每份 proposal 都针对 HARNESS 验证，而不仅描述偏好的设计。
- Review 要关注冲突、缺失概念和未支持场景。
- 限制 revision loops，避免设计变成无休止争论。
- 让 synthesis 做决策，而不是拼接文档。
- 将 validation 与 synthesis 分开运行。
- 将重大权衡转为 ADR，将未解决的非阻塞问题转为 open questions。

## 本案例研究不应变成什么

本案例研究不应变成新的重量级框架、自定义 agent runtime 或每个任务的强制流程。

未来 prompt-patterns 应保持轻量，只在真实任务需要时填充内容。
