# MVP-1 Visual Contract v0.1 — GOAL

状态：`DESIGN_COMPLETE`
类型：详细设计，不含实现
当前产品阶段：MVP-1 高质量单页视觉闭环

## 1. 目标

为普通对白气泡和普通旁白框冻结一套可实现、可验证、可演化的视觉领域合同，使系统能够逐页回答：

1. 每个 `TextSegment` 从哪里来、最终去了哪里；
2. 它唯一属于哪个 `BubbleInstance`，或为何被明确排除；
3. Cleaning eligibility 为什么是 E1/E2/E3/E4；
4. Cleaner 被允许修改及实际修改了哪些像素；
5. Typesetter 使用了哪个实例、哪个 region revision；
6. 实际 glyph 像素落在哪里；
7. Validator 为什么通过、告警或阻塞；
8. 失败应归因到哪个 root stage，并只允许哪一次局部修正；
9. identity、关系、hash 与大型 mask 证据如何保存、恢复和复现。

设计输出必须能直接约束下一轮 bounded Spike，但不得实现产品代码、算法、migration、API、UI、Provider、测试或大规模实验。

## 2. 产品范围

### 2.1 本轮覆盖

- 单张真实漫画页；
- 普通对白气泡；
- 普通旁白框；
- 横排简体中文；
- 可信 OCR 与可信译文输入；
- `ContactBubbleCluster → 1..N BubbleInstance`；
- 同一 `BubbleInstance` 内 0..N `TextSegment` 和 0..N `LayoutSlot`；
- Cleaning eligibility、pixel text mask、protected mask、safe edit mask；
- BubbleInstance-aware typesetting region；
- actual-glyph validation；
- 一次有界局部 correction/rerun；
- 证据、QualityIssue、active result 与恢复边界。

### 2.2 明确不覆盖

- OCR 或翻译准确率优化；
- 多页上下文、Batch、吞吐与性能优化；
- 多级 Provider fallback、长 retry 链、跨页回溯；
- 正式 Web/API/UI/Provider/Workflow 实现；
- 复杂拟声词、艺术字、发布级精修；
- 自动批准 E2/E3 Cleaning；
- 任何数据库 migration 或正式 schema 修改。

## 3. 权威输入

基线：

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/PROJECT-PLAN.md`
- `docs/prompt-patterns/design/detailed-design-pattern.md`

架构：

- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`
- `docs/design/persistence/final/persistence-readiness-dd-v0.1.md`

实证：

- Detection/OCR 与 Grouping REPORT；
- Cleaning Handoff、Algorithm Lock、Design Rationale；
- Text-Seeded Container Association Goal 4–7 最终报告与 Gate；
- 40 页 E1/E2 对比最终报告；
- Typesetting 首轮 REPORT/GATE；
- Typesetting Input Contract / Validator Grounding REPORT/GATE/HARNESS；
- 本地 `data/local/typesetting-input-contract-v0.1/run-v0.4/FORM.md` 后续人工裁决。

提交版 Input Contract REPORT/GATE 仍停留在 `PENDING_HUMAN_REGION_AND_MAPPING_REVIEW`，而后续 FORM 已选择 `GO_WITH_CHANGES`，且 SRS/HLD/PROJECT-PLAN 已吸收该裁决。本设计将两者解释为“历史报告状态 + 后续人工补充证据”，不回写旧 Spike 报告。

## 4. 必须冻结的核心决策

1. Provenance 链及逐页 reconciliation；
2. cluster、BubbleInstance、TextSegment、LayoutSlot 的身份、基数和 revision；
3. 每个 `TextSegment` 唯一归属或明确 exclusion；
4. per-instance Cleaning eligibility 的可解释字段；
5. cluster/instance/boundary/text/protected/safe/typesetting/glyph mask 的严格区分；
6. Cleaner、Typesetter、Renderer、Validator 使用的具体 revision；
7. actual glyph 像素验证，不接受 bbox 或父 cluster 替代；
8. QualityIssue taxonomy、blocking/warning/review/exclusion 语义；
9. root-stage attribution 和一次局部 rerun；
10. contract-first、artifact-heavy、最小 SQLite 扩张的持久化方向；
11. migration 现在是否必要；
12. 下一轮 bounded Spike 的输入、输出与停止条件。

## 5. 不变量

- Provider Adapter 不访问数据库、不登记正式 artifact、不创建 QualityIssue、不作 workflow decision；
- ArtifactService 是正式 artifact 生命周期唯一入口；
- Repository / DAO 是 SQLite 唯一入口；
- QualityCheckService 负责质量分类和 root-stage attribution；
- WorkflowLoopEngine 负责 retry/fallback/skip/warning/block；
- 原图永不覆盖，大型像素 payload 不进入 SQLite；
- active pointer 是当前有效结果的唯一事实来源；
- recovery 依赖 active result、hash、artifact 状态和 attempt/decision，不依赖 `Page.status`；
- 正常导出阻塞 unresolved blocking QualityIssue；
- 一个领域对象或 revision 只能有一个事实来源；
- unsupported 内容可明确 skip，普通对白不得静默丢失或降为无解释 warning。

## 6. 设计完成门禁

- final 文档包含目标指定的 25 个章节；
- HARNESS 15 个场景均映射到输入、对象关系、owner、证据、issue、严重性、局部修正和验收；
- proposal 已独立生成并经过 cross-review；
- blocker 最多两轮修订后归零，否则停止并报告；
- 领域模型、revision、source of truth、artifact/persistence 和 local loop 一致；
- 没有提前侵入 MVP-2/MVP-3；
- 没有修改允许清单之外的文件；
- Markdown、路径、术语、引用、`git diff --check` 和最终 Git 状态验证通过。

## 7. 停止条件

- 权威文档出现无法调和的架构冲突；
- 两轮 blocker 修订后仍无法确定唯一 source of truth；
- 必须修改 SRS/HLD/PROJECT-PLAN 或实现代码才能继续；
- 设计只能依赖人工逐块确认才能成立；
- 无法为普通对白缺失、跨实例或 glyph 溢出定义可执行阻塞证据。
