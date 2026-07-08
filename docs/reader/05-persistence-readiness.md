# Phase 2D Persistence Readiness：真实设计结果

本文给项目维护者看，解释 persistence readiness 阶段最终决定了数据库访问、事务、恢复和幂等怎么实现。

## 源文件

- [../design/persistence/final/persistence-readiness-dd-v0.1.md](../design/persistence/final/persistence-readiness-dd-v0.1.md)
- [../design/persistence/final/repository-contract-minimal.md](../design/persistence/final/repository-contract-minimal.md)
- [../design/persistence/final/unit-of-work-and-transactions.md](../design/persistence/final/unit-of-work-and-transactions.md)
- [../design/persistence/final/migration-strategy-minimal.md](../design/persistence/final/migration-strategy-minimal.md)
- [../design/persistence/final/fakeprovider-persistence-readiness.md](../design/persistence/final/fakeprovider-persistence-readiness.md)

## Repository / DAO 是唯一 SQLite 入口

上层不能拿到：

- SQL string；
- ORM session；
- DB cursor；
- query builder；
- table-shaped row dict；
- generic `Repository<T>`。

上层只能通过有名字的 repository operation 读写。

底层意义：

- WorkflowLoopEngine 不依赖 SQL。
- StageExecutor 不会变成半个 persistence layer。
- Provider Adapter 永远拿不到数据库能力。

## Repository group 已经划分

MVP-0 最小 repository 分组：

| Repository group | DB | 负责 |
| --- | --- | --- |
| ProjectCatalogRepository | app.db | Project registry、workspace/project.db path、生命周期。 |
| AppConfigRepository | app.db | 非 secret 设置、provider/profile 模板或骨架。 |
| ProjectIdentityRepository | project.db | ProjectMetadata、schema compatibility、open verification。 |
| ContentStateRepository | project.db | Batch、Page、TextBlock、active pointers、stage statuses。 |
| ResultVersionRepository | project.db | OCRResult / TranslationResult 版本、reuse lookup。 |
| GlossaryRepository | project.db | GlossaryVersion、可选 GlossaryTerm。 |
| WorkflowExecutionRepository | project.db | ProcessingTask、ProfileSnapshot、Attempt、Decision、DecisionIssue。 |
| QualityIssueRepository | project.db | issue draft persistence、lifecycle、blocker/warning query。 |
| ArtifactMetadataRepository | project.db | ProcessingArtifact metadata 和 storage_state。 |
| ReadinessQueryRepository | project.db | export readiness 所需 active output、blocker、warning、freshness 查询。 |

## Project open gate 已经固定

Project repository 不能随便打开。

打开流程：

1. 读 app.db 中 Project registry。
2. 解析 project.db path。
3. 打开 project.db。
4. 校验 `project_metadata.project_id` 与 app registry 一致。
5. 校验 app/project migration ledger。
6. 通过后才暴露 Project repository contracts。

如果 identity mismatch、schema mismatch、checksum mismatch、project.db missing：

```text
Project 进入 repair-only
不暴露 workflow mutation repository
```

底层意义：

- 不会把一个 Project 的数据库错当成另一个 Project。
- 不会因为 project.db 丢失就静默创建一个新库覆盖历史。

## Unit of Work 类型已经固定

MVP-0 有这些事务边界：

| UoW | 作用 |
| --- | --- |
| App lifecycle UoW | 初始化/迁移 app.db，创建 Project registry。 |
| Project lifecycle UoW | 初始化/迁移 project.db，写 ProjectMetadata。 |
| Import UoW | 创建 Batch/Page import state，选择 original artifact pointer。 |
| Attempt reservation UoW | claim stage work，创建 running WorkflowAttempt。 |
| Tool evidence UoW | 写 ToolRunLog 和窄 attempt evidence。 |
| Artifact metadata UoW | ArtifactService 注册/更新 ProcessingArtifact。 |
| Acceptance UoW | 一次性提交 accepted result、active pointer、issue、decision、status。 |
| User edit UoW | 用户编辑创建新版本、更新 active pointer、传播 stale。 |
| Recovery repair UoW | 标记 interrupted/recovering、写恢复决策。 |

硬规则：

```text
任何 SQLite write transaction 都不能跨 provider call 或长文件操作
```

## Acceptance transaction 是语义提交点

只有 acceptance 事务能让结果变成当前有效。

它必须原子提交：

- OCRResult / TranslationResult 行；
- active OCR / translation pointer；
- active cleaned / typeset artifact pointer；
- TextBlock stage statuses；
- Page aggregate status；
- QualityIssue 创建/更新/resolve/supersede；
- WorkflowDecision；
- WorkflowDecisionIssue；
- retry budget after；
- task progress/current stage；
- stale propagation。

并且要有 expected-state guard：

- 当前 active pointer 是否还是预期值；
- source/context/glossary/geometry/hash 是否还是预期值；
- stage status 是否还是预期值；
- task status/current stage 是否还是预期值；
- locked translation pointer 是否被改过。

如果 guard fail：

```text
rollback
reload evidence
WorkflowLoopEngine 重新决定
```

底层意义：

- 用户编辑和后台任务并发时不会静默覆盖。
- artifact 注册成功但 acceptance 失败时，artifact 仍只是 unselected evidence。

## Import 被定义为 ApplicationService use case

MVP-0 的 import 不是 WorkflowLoopEngine stage。

流程：

1. ApplicationService 验证图片类型、路径边界、Project readiness。
2. ArtifactService 注册 original artifact。
3. Import UoW 创建 Batch/Page，并设置 `Page.original_artifact_id`。
4. Page 没有 original pointer 就不算 import 完成。

底层意义：

- 原图从第一步就受 ArtifactService 保护。
- original image 永远不覆盖。
- 后续 workflow 从已经 imported 的 Page 开始。

## Recovery query 必须加载完整证据包

恢复查询需要取：

- task status / heartbeat / current stage；
- running/incomplete attempts；
- latest decisions；
- ToolRunLogs；
- active Page/TextBlock pointers；
- active result rows 和 dependency hashes；
- original/cleaned/typeset artifact metadata；
- open blocking/warning QualityIssues；
- TextBlock stage statuses；
- Page stale flags。

恢复查询只是证据。WorkflowLoopEngine 决定下一步。

## Idempotency 已经有查询要求

系统要支持重跑不重复调用工具：

- OCR reuse lookup：TextBlock + input/config/provider/model/tool/geometry/source-language。
- Translation reuse lookup：source OCR/text + context + glossary + provider/model/prompt/config/target-language。
- Cleaning reuse lookup：base image + mask/geometry/skip set + provider/mode/config。
- Typeset reuse lookup：cleaned artifact + active translations + geometry/layout/font/typesetter。

复用也要有 auditable decision 或 attempt。

## MVP-0 立刻需要哪些表

立即需要：

- app: `projects`, `schema_migrations`
- project identity: `project_metadata`, `schema_migrations`
- content: `batches`, `pages`, `text_blocks`
- results: `ocr_results`, `translation_results`, `glossary_versions`
- workflow: `processing_profile_snapshots`, `processing_tasks`, `workflow_attempts`, `workflow_decisions`, `workflow_decision_issues`
- evidence: `processing_artifacts`, `tool_run_logs`, `quality_issues`

可骨架或后置：

- `provider_configs`
- `processing_profiles`
- `glossary_terms`
- `global_settings`
- `export_records`

## 这个阶段没有决定什么

没有决定：

- 具体 SQL DDL；
- ORM mapping；
- repository method name；
- package layout；
- exact ID format；
- exact migration tool；
- FastAPI/API/UI。

它的结果是“可以安全开始 Slice 01 实现”，不是完整 persistence 代码。
