# 产品路线 M0–M3

仓库重构是工程治理任务，不是新的产品里程碑，也不改变任何算法门禁。

| 里程碑 | 定义 | 当前状态 |
| --- | --- | --- |
| M0 — Architecture Proof | 用 FakeProvider 证明 Repository/UoW、ArtifactService、Provider Adapter、Workflow Loop、QualityIssue、active pointer、幂等/恢复与 export readiness 等核心机制 | 已关闭；不是产品 MVP，不证明真实工具质量或用户可用性 |
| M1 — Single-Page Visual Closure | 首个且唯一的产品 MVP：可信 OCR/译文、BubbleInstance 或等价关联、Cleaning/Check、Typesetting/Check、最小单页 Web 预览、人工修改、局部返工、单图导出 | 当前主线；未完成，真实产品链尚未逐边接通 |
| M2 — Semantic Quality Closure | Detection/OCR、reading order、Page/必要多页翻译上下文、术语/称谓/代词/口吻一致性、semantic review、编辑后的 stale propagation 与局部重翻/重检/重嵌 | M1 后续；未开始产品闭环 |
| M3 — Scale & Personal Product | Batch、模型复用/缓存、性能资源预算、暂停取消恢复、页面失败隔离、retry/fallback/refusal、完整 Web、ZIP/manifest、设置备份日志和本地交付 | M2 后续；未开始产品闭环 |
| Post-MVP | 英文、竖排、复杂背景/艺术字、专业级排版等明确后置能力 | 不进入 M1 |

## 当前 M1 门禁

### Gate 1 — Single-page input and real upstream evidence

- 用户可操作的单页输入和 immutable Import；
- real Detection 与 real OCR 进入正式 Provider、Check、Workflow acceptance 和 accepted/current 路径；
- 允许必要人工复核，但不得静默传递漏检、空 OCR 或明显坏结果。

### Gate 2 — Shared semantic/visual handoff

- production Grouping 消费 exact accepted Detection/OCR binding；
- current/stale 语义通过正式入口和 UoW 保持；
- Translation 与 Physical Boundary 均消费正式 accepted/current Grouping 输入，而非测试或实验快照。

### Gate 3 — Two product branches and merge

- page-level real Translation 形成 accepted/current 结果；
- Physical Boundary → VisualContract → Cleaning 形成正式 accepted cleaned artifact；
- accepted Translation + accepted Cleaning 进入 real Typesetting 和 actual-glyph Check。

### Gate 4 — User closure

- 提供单页 preview、OCR/译文人工编辑、stale 与局部返工；
- actual single-image Export 生成用户可访问文件；
- re-export 只消费当前 accepted、non-stale、hash-valid 结果。

以上门禁均未因信息架构重构而通过。

## 里程碑边界与裁决

M1 不要求提前完成系统性 OCR benchmark、跨页语义一致性、复杂 fallback、Batch、资源预算或复杂恢复产品化；这些仍属于 M2/M3。但 M1 至少要求真实本地 Provider 可运行、质量问题可发现、结果可人工修正，并且普通正文不会被静默遗漏。不能以 M2 负责系统性质量为由，在 M1 中继续使用 FakeProvider 或无检查的冻结输入冒充产品能力。

拒绝把 M1、M2、M3 统称为多个产品 MVP，也拒绝将 M0 的后端机制闭环描述为用户可用产品。Physical Boundary 与 Cleaning 的既有门禁仍有效，但必须在真实上游边关闭后进入同一产品链，而不是作为脱离产品入口的独立主线无限推进。

风险是未来能力被提前写成已实现、单样本证据被泛化，或为追求里程碑名称而重写稳定架构。每个里程碑必须由真实验收证据关闭。M1 冻结样本规模和最小 UI 交互仍待专门设计。
