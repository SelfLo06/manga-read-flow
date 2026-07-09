# 持久化就绪性详细设计 v0.1

## 1. 设计目标

本设计定义在实现 FakeProvider single-Page backend vertical slice 之前所需的最小持久化就绪性。

目标不是重新设计数据模型。目标是通过 repository contracts、Unit of Work 边界、transaction rules 和 database lifecycle rules，使现有 data-model、workflow-state 和 execution-contract 基线可实现。

主要目标：

- 保持 `app.db + project.db` 的 Project 隔离。
- 保持 Repository / DAO 作为唯一 SQLite 访问边界。
- 使 active pointer updates、result versions、attempts、decisions、issues、tool evidence 和 artifact metadata 可恢复、可审计。
- 让 provider calls 位于 SQLite write transactions 之外。
- 使 crash recovery 和 idempotent rerun 可查询，且不依赖 `Page.status`。
- 支持 FakeProvider slice 的临时 SQLite 集成测试。
- MVP-0 持久化就绪性止步于 `ready_for_export`；实际 `ExportRecord` 和 output export 后续处理，除非之后明确加入 scope。

非目标：

- SQL DDL、ORM mappings、Alembic files、repository method signatures、API routes、frontend behavior、真实 provider integration、prompt templates、完整 export design，或 P1 / P2 features。

## 2. 来源文档

已阅读并综合：

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/HLD.md`
- `docs/PROJECT-PLAN.md`
- `docs/design/persistence/GOAL.md`
- `docs/design/persistence/HARNESS.md`
- `docs/design/persistence/PLAN.md`
- `docs/design/persistence/reviews/00-preflight.md`
- `docs/design/persistence/proposals/01-repository-boundary-agent.md`
- `docs/design/persistence/proposals/02-unit-of-work-transaction-agent.md`
- `docs/design/persistence/proposals/03-migration-db-lifecycle-agent.md`
- `docs/design/persistence/proposals/04-recovery-idempotency-agent.md`
- `docs/design/persistence/proposals/05-fakeprovider-slice-readiness-agent.md`
- `docs/design/persistence/reviews/01-cross-review.md`
- `docs/design/persistence/reviews/02-no-blocking-revision-needed.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/data-model/final/schema-outline.md`
- `docs/design/data-model/final/state-data-impact.md`
- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/workflow-state/final/state-vocabulary.md`
- `docs/design/workflow-state/final/recovery-rules.md`
- `docs/design/workflow-state/final/stale-propagation-rules.md`
- `docs/design/workflow-state/final/decision-matrix.md`
- `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`

基线决策：

- 使用 `docs/HLD.md` 加 data-model、workflow-state 和 execution-contract final 文档作为当前基线。
- `docs/HLD.md` 现在是提升后的 HLD v0.2 基线。
- execution-contract final 原本指出，在其综合时 v0.2 HLD 路径不存在；现在已协调，当前基线是提升后的 `docs/HLD.md`。

## 3. 软件工程原则应用

| Principle | Persistence application |
| --- | --- |
| Single Responsibility | Repositories 只负责 persist / query SQLite。WorkflowLoopEngine 负责决策。QualityCheckService 负责 issues 分类。ArtifactService 拥有 official files。Provider Adapters 只调用工具。 |
| Information Hiding | 调用方收到 domain / evidence DTOs 和命名 persistence operations，而不是 SQL、ORM sessions、cursors、row dictionaries 或 table-shaped APIs。 |
| High Cohesion / Low Coupling | Repository groups 跟随 workflow needs：catalog、identity、content state、results、workflow evidence、quality、artifact metadata、glossary、readiness。 |
| Dependency Inversion | WorkflowLoopEngine、ArtifactService、StageExecutor、ConfigService 和 ApplicationService 依赖 repository contracts，而不是具体 SQLite 或 ORM 细节。 |
| Interface Segregation | StageExecutor 只能使用窄接口 `StageEvidenceWriter`；MVP-0 中 QualityCheckService 不依赖 repository；Provider Adapters 不获得 persistence interface。 |
| Recoverability | Recovery queries 使用 tasks、attempts、decisions、tool logs、active pointers、dependency hashes、artifacts、issues 和 TextBlock statuses。`Page.status` 只是可修复摘要。 |
| Traceability | Attempts、decisions、decision-issue links、issue lifecycle、tool logs、artifacts、active pointer changes 和 result versions 保持可审计。 |
| Scope Control | MVP-0 不引入 generic persistence framework、event sourcing、CQRS、distributed transactions、cross-project cache 或 plugin persistence layer。 |
| Testability | 第一个 slice 必须使用临时真实 SQLite `app.db` / `project.db` 文件和临时 workspace artifacts 运行。 |

## 4. 关键决策

1. `app.db` 存储全局 Project registry、non-secret app settings、app-level provider / profile templates or skeletons，以及 app schema migrations。
2. 每个 Project 有一个 `project.db`，用于 Project-owned content、workflow、quality、result versions、artifact metadata、profile snapshots 和 project schema migrations。
3. Project repositories 只有在 Project identity 和 migration readiness 被验证后才暴露。
4. MVP-0 中，Import 是 ApplicationService / import use case，不是 WorkflowLoopEngine stage。`import` stage 仍保留为后续 task-based import 的规范词汇。
5. MVP-0 止步于 `ready_for_export`。实际 `ExportRecord`、export output artifact、ZIP 和 manifest 后续处理，除非后续 implementation milestone 明确加入。
6. MVP-0 中 QualityCheckService 不访问 repository。它返回 issue drafts、lifecycle suggestions、attribution、severity 和 suggested actions。WorkflowLoopEngine 在 acceptance 中持久化它们。
7. StageExecutor 只能使用窄接口 `StageEvidenceWriter` 写入 ToolRunLog 和 attempt tool evidence。它不得接收 generic repositories、active pointer writers、issue lifecycle writers 或 decision writers。
8. Acceptance transaction 是语义提交点。它必须原子持久化 accepted result rows 或 active artifact pointer changes、active pointers、issue lifecycle changes、`WorkflowDecision`、issues 被链接时的 `WorkflowDecisionIssue` rows、retry budget after、task progress 和 stage statuses。
9. Acceptance 必须 guard expected active pointer ids、相关 dependency hashes 和 stage statuses。仅用 timestamp guard 不足够。
10. 已登记但未被 active pointers 选择的 official artifacts 只是 evidence / reuse candidates。绝不按 timestamp 选择它们。
11. 当持久化 `WorkflowDecision` 链接持久化 `QualityIssue` rows 时，`workflow_decision_issues` 是最小必需基础设施。Happy path 可以不创建 rows。
12. app-level `projects` 和 `schema_migrations` 立即需要。若存在 deterministic project-local `ProcessingProfileSnapshot` 用于 FakeProvider，app-level `provider_configs` 和 `processing_profiles` 可以是 skeletal。

## 5. app.db / project.db 边界

`app.db` 拥有：

- `projects`
- `schema_migrations`
- optional / skeletal `provider_configs`
- optional / skeletal `processing_profiles`
- optional `global_settings`

`project.db` 拥有：

- `project_metadata`
- `schema_migrations`
- `batches`
- `pages`
- `text_blocks`
- `ocr_results`
- `translation_results`
- `glossary_versions`
- optional / skeletal `glossary_terms`
- `processing_profile_snapshots`
- `processing_tasks`
- `workflow_attempts`
- `workflow_decisions`
- `workflow_decision_issues`
- `quality_issues`
- `processing_artifacts`
- `tool_run_logs`
- optional / follow-up `export_records`

规则：

- 不使用跨数据库 foreign keys。
- MVP-0 不需要跨数据库 transaction。
- `project_id` 保留在 project-owned rows 上作为隔离 guard。
- Project open 验证 `app.db.projects.project_id` 与 `project.db.project_metadata.project_id`。
- Artifact paths 使用 project-relative。
- API keys、tokens 和 raw secrets 不存储在 `project.db`、workflow logs、artifacts 或 snapshots 中。

## 6. 最小 FakeProvider 持久化范围

MVP-0 必须证明：

```text
create project
-> initialize project.db
-> import one page
-> run deterministic FakeProvider workflow
-> persist evidence and active pointers
-> reach ready_for_export or a documented warning/block path
```

立即需要：

- 真实临时 `app.db` 和 `project.db`；
- Project registry 与 ProjectMetadata identity；
- 一个 Batch、一个 Page、一个或多个 TextBlocks；
- original、cleaned 和 typeset artifacts 作为 official metadata，bytes 位于 SQLite 之外的文件系统；
- 不可变 OCRResult 和 TranslationResult rows；
- active OCR、translation、cleaned 和 typeset pointers；
- translation provenance 所需的空 / 当前 GlossaryVersion；
- ProcessingProfileSnapshot；
- ProcessingTask、WorkflowAttempt、WorkflowDecision、ToolRunLog；
- QualityIssue support 和 open blocking issue query；
- 当 decisions 链接 persisted issues 时使用 `workflow_decision_issues`。

第一个 slice 中可 skeleton 或 follow-up：

- `provider_configs` 和 `processing_profiles`：skeletal app rows，或 deferred behind deterministic snapshot bootstrap；
- `glossary_terms`：可以存在但为空；
- `export_records`：follow-up，除非实际 export 明确在 scope 中；
- mask / crop / raw OCR / raw translation / quality report artifacts：除非 failure test 需要，否则为 optional modes。

## 7. 必需实体 / 表优先级

| Priority | Entity / table | Reason |
| --- | --- | --- |
| Immediate app | `projects`、`schema_migrations` | Project registry 和 app lifecycle。 |
| Immediate project identity | `project_metadata`、`schema_migrations` | Project open verification 和 independent migrations。 |
| Immediate content | `batches`、`pages`、`text_blocks` | Ownership spine、stage statuses、active pointers。 |
| Immediate results | `ocr_results`、`translation_results`、`glossary_versions` | Versioning、provenance、idempotent reuse。 |
| Immediate workflow | `processing_profile_snapshots`、`processing_tasks`、`workflow_attempts`、`workflow_decisions`、`workflow_decision_issues` | Durable execution、decisions、retry / recovery evidence。 |
| Immediate evidence | `processing_artifacts`、`tool_run_logs`、`quality_issues` | Artifact metadata、sanitized tool trace、warning / block / export gate source。 |
| Skeleton | `provider_configs`、`processing_profiles`、`glossary_terms`、`global_settings` | 保留未来形态，不要求完整 UI / config / profile behavior。 |
| Follow-up | `export_records`、export issue snapshots、manifest artifacts | 实际 export / output design 位于 readiness 之后。 |
| Deferred P1 / P2 | GeometryRevision、ContextPack、TermCandidate、TaskSummaryIndex、full ArtifactRetentionPolicy | FakeProvider MVP-0 不需要。 |

## 8. Repository 分组与模块依赖规则

详细 contracts 见 `repository-contract-minimal.md`。

Repository groups：

- ProjectCatalogRepository
- AppConfigRepository
- ProjectIdentityRepository
- ContentStateRepository
- ResultVersionRepository
- GlossaryRepository
- WorkflowExecutionRepository
- QualityIssueRepository
- ArtifactMetadataRepository
- ReadinessQueryRepository

Dependency rules：

- API handlers 调用 ApplicationService，而不是 repositories。
- Provider Adapters 不接收 repositories。
- MVP-0 中 QualityCheckService 不接收 repositories。
- ArtifactService 只能通过 ArtifactMetadataRepository 修改 `ProcessingArtifact` metadata。
- WorkflowLoopEngine 使用 repository contracts 和 ArtifactService evidence，而不是 SQL 或 ORM sessions。
- StageExecutor 只使用 Provider Adapters、ArtifactService、read-only stage context 和窄接口 `StageEvidenceWriter`。
- ConfigService 可以读取 app-level non-secret config 和 secret references；raw secrets 不得进入 Project persistence。

## 9. Unit of Work 边界

详细 sequences 见 `unit-of-work-and-transactions.md`。

使用命名 Unit of Work operations，不向业务逻辑暴露 generic framework：

- app database lifecycle Unit of Work；
- project database lifecycle Unit of Work；
- import Unit of Work；
- stage attempt reservation Unit of Work；
- tool evidence Unit of Work；
- 通过 ArtifactService 执行的 artifact metadata Unit of Work；
- workflow acceptance Unit of Work；
- user edit Unit of Work；
- recovery repair Unit of Work。

任何 Unit of Work 都不得在 provider call、长时间文件生成操作、temp directory scan 或 external model / tool invocation 期间持有 write transaction。

## 10. Transaction sequences

规范 stage execution sequence：

1. 在短 transaction 中 reserve attempt。
2. 在任何 SQLite write transaction 之外调用 Provider Adapter。
3. 通过 `StageEvidenceWriter` 持久化 sanitized tool outcome。
4. 通过 ArtifactService 登记 official artifacts。这些 artifacts 是 official 但 unselected。
5. 运行 QualityCheckService。它返回 drafts 和 suggestions，而不是 database writes。
6. 运行 acceptance transaction。只有这一步选择 active results / artifacts 并推进 workflow state。

Import sequence：

1. ApplicationService 校验用户提供的本地图片和目标 Project。
2. ArtifactService 存储 / 登记 original artifact metadata。
3. Import transaction 创建 / 更新 Batch / Page，并设置 `Page.original_artifact_id`。
4. 除非 original artifact metadata 和 pointer 一起 commit，否则 Page 不视为 imported。

Recovery sequence：

1. Project open 验证 identity 和 migrations。
2. 通过 status / heartbeat 查找 stale running tasks。
3. 使用 expected status / heartbeat checks claim recovery。
4. 加载 task / page recovery bundle。
5. 需要时由 ArtifactService 校验 missing / hash state。
6. WorkflowLoopEngine 决定 reuse、retry、pause、warning 或 block。
7. 在短 transactions 中持久化 repair decision 和 state。

## 11. Acceptance transaction

Acceptance 是 current state 的语义提交点。

它必须一起提交：

- 创建时的 accepted OCRResult 或 TranslationResult rows；
- `TextBlock.active_ocr_result_id` 或 `TextBlock.active_translation_result_id`；
- 接受 image artifacts 时的 `Page.active_cleaned_artifact_id` 或 `Page.active_typeset_artifact_id`；
- TextBlock stage statuses 和 Page aggregate status changes；
- 接受 user edits 或改变上游的 results 时的 downstream stale propagation；
- 来自 QualityCheck issue drafts 的 QualityIssue creation / lifecycle updates；
- WorkflowDecision；
- 链接 persisted issues 的 WorkflowDecisionIssue rows；
- retry budget after 和 task progress / current stage；
- expected-state guard results。

Expected-state guards：

- 受影响 TextBlocks / Page 的 expected active pointer ids；
- expected dependency hashes，例如 source OCR hash、context hash、glossary hash、geometry hash、mask hash、cleaned artifact hash、translation text hashes、layout config hash；
- expected stage statuses，例如 `running`、`pending`、`stale` 或 `needs_review`；
- expected task status / current stage；
- 相关时的 expected locked translation pointer。

如果 guard 失败，acceptance aborts、reloads evidence，并由 WorkflowLoopEngine 重新决策。

## 12. Recovery query requirements

Recovery repositories 必须支持：

- 按 Project、status 和 heartbeat 查找 running-like states 中的 stale `ProcessingTask` rows；
- 使用 expected status / heartbeat guard claim stale task recovery；
- 加载 task / stage / target 的 running / incomplete attempts；
- 加载 latest decisions、tool logs、issues、artifacts、active pointers、result rows、stage statuses 和 profile snapshot；
- 在 WorkflowLoopEngine reconciliation 后，将 attempts 标记为 `interrupted`、`refused`、`failed` 或 `abandoned_after_crash`；
- 按 Page / Batch / TextBlock scope 查询 open blocking 和 warning issues；
- 当 attempts 被 abandoned 或 state 被修复时，持久化 recovery decisions 或 repair evidence。

Recovery 不得：

- 从 `Page.status` 推导 success；
- 按 timestamp 选择 latest result 或 artifact；
- 在没有 ArtifactService 和正常 validation 的情况下，将 temp / orphan files 转为 official artifacts；
- 未经 acceptance 就让 official unselected artifacts 变为 export-effective。

## 13. Idempotency query requirements

幂等重跑必须区分：

- task duplicate suppression key：用于创建 / 运行 tasks 的 request-level idempotency key；
- stage reuse key：OCR、translation、cleaned 和 typeset outputs 的 evidence-level key。

必需 reuse lookups：

- OCR：TextBlock、geometry / input hash、OCR config hash、provider、model、tool version、source language。
- Translation：source OCR result id、source text hash、context hash、glossary version 或 terms hash、provider、model、prompt template version、generation config hash、target language。
- Cleaning：base image hash、mask hash 或 mask set hash、geometry hashes、skip set、cleaning provider / mode / tool version、config hash。
- Typesetting：active cleaned artifact id / hash、reading order 中的 active TranslationResult ids 和 text hashes、geometry hashes、font / layout config hash、typesetter version、target language / direction policy。

Reuse 必须记录 `reused_cached` attempt 和 / 或 `reuse_cached_result` decision。没有显式 user override 时，reuse 不能替换 locked translation。

## 14. 最小 migration strategy

详细 lifecycle 见 `migration-strategy-minimal.md`。

必需：

- app.db 和每个 project.db 中独立 `schema_migrations`；
- app startup 在 Project listing / open 前 migrates / verifies app.db；
- Project creation 初始化 project.db、应用 baseline project migrations、写入 ProjectMetadata，然后在 app.db 中 register 或 finalize Project；
- Project open 在 repositories 暴露前验证 identity 和 migration readiness；
- checksum mismatch、identity mismatch、missing project.db、incompatible newer schema 或 failed migration 会阻塞 workflow mutation；
- stages、statuses、decisions、issues、artifact states 和 error codes 使用 stable string values。

后置：

- 精确 migration tool topology；
- restore / relink UX；
- backup manifest；
- downgrade strategy；
- legacy data backfills；
- 超出 “no workflow while migrating” 的 multi-process desktop locking。

## 15. 最小正确性约束与索引

本节是设计指导，不是 SQL DDL。

正确性约束：

- app.db 中 Project identity 唯一；
- app.db 中 active Project workspace path 唯一；
- 每个 project.db 有一个 ProjectMetadata identity；
- Batch 内 active Page order 唯一；
- 分配时，Page 内 active TextBlock reading order 唯一；
- OCRResult 和 TranslationResult version numbers 在每个 TextBlock 内唯一；
- active OCR / translation pointers 必须引用同一 TextBlock 的 results；
- Page active artifact pointers 必须引用同一 Project / Page scope 内的 artifacts；
- workflow attempts 按 task / stage / target / attempt number 唯一；
- decision-issue links 按 decision / issue / relation 唯一；
- 当 storage state 为 `present` 或 `moved_to_trash` 时，artifact relative paths 唯一；
- stable strings 是追加式演进；历史 audit rows 不会为了重命名旧值而重写。

最小索引类别：

- Project listing and open：project status / path / id。
- Task recovery：project、task status、heartbeat。
- Attempt recovery：task / stage / status 与 target / stage / status。
- TextBlock recovery：page 加每个 stage status。
- OCR 和 translation 的 result histories 与 reuse keys。
- Artifact lookup by owner / type、page / type、file hash / type、retention / storage state。
- QualityIssue blocker / warning queries by project、batch、page、text block、blocking flag 和 status。
- ToolRunLog by attempt 和 project / stage / status / time。
- WorkflowDecision by task / time、attempt、target / stage。

## 16. 使用临时 SQLite 的可测试性计划

首个实现应使用临时 workspace directories 和真实 SQLite files 进行测试：

- 初始化 app.db 并验证 app migration ledger；
- 创建 Project、初始化 project.db、验证 ProjectMetadata identity；
- import one Page，并断言 original image bytes 只在文件系统中；
- 运行 happy path 到 `ready_for_export`；
- 验证 active OCR、translation、cleaned 和 typeset pointers；
- 验证 attempts、decisions、tool logs、artifacts、issues 和 profile snapshot；
- 重跑未变化 workflow 并验证可审计 reuse；
- 模拟 OCR acceptance 后 crash，并从 translation 恢复；
- 模拟 artifact registration 后、acceptance 前 crash，并验证 artifact 未被 selected；
- 模拟 provider refusal 或 invalid translation，并验证 ToolRunLog、WorkflowAttempt、QualityIssue、WorkflowDecision 和 decision-issue links；
- 将 active artifact 标记为 missing，并验证 ArtifactService 标记 metadata，而 rebuild / warn / block decision 归 WorkflowLoopEngine；
- 验证 open blocking QualityIssue 阻止 pure readiness；
- 验证 app 和 project migrations 独立追踪。

## 17. 针对 HARNESS 的场景回放

| Scenario | Result | Summary |
| --- | --- | --- |
| P01 Create Project and project database | PASS | app.db registers Project；project.db owns Project data；ProjectMetadata identity 被验证；不需要 cross-db FK。 |
| P02 Import one Page | PASS | original artifact metadata 被登记；Page 指向 original artifact id；bytes 保留在文件系统；original 永不覆盖。 |
| P03 Happy-path single Page workflow | PASS | 必需 content、result、artifact、attempt、decision、tool 和 issue data 可持久化；active pointers 选择 accepted outputs；Page 可到达 `ready_for_export`。 |
| P04 Acceptance transaction | PASS | result rows、active pointers、issue lifecycle、decision、retry budget、task progress 和 stage statuses 一起提交；provider call 位于 write transaction 之外。 |
| R01 Crash after OCR result committed | PASS | 可找到 stale task / running attempt；active OCR pointer / result 可复用；recovery 从 translation 继续。 |
| R02 Crash after provider temp file before artifact registration | PASS | temp / orphan file 不是 official；recovery 将 attempt 标记为 abandoned / interrupted，或在 policy 下 retry。 |
| R03 Crash after artifact registration before active pointer update | PASS | official artifact 仍只是 unselected evidence / reuse candidate；不会按 timestamp promotion。 |
| R04 Missing active artifact | PASS | artifact metadata 可加载；ArtifactService 标记 `missing`；WorkflowLoopEngine 决定 rebuild、warning、pause 或 block。 |
| I01 Rerun unchanged OCR | PASS | OCR reuse query 使用 full key；reuse 可审计并避免重复 provider call。 |
| I02 Rerun unchanged translation | PASS | translation reuse query 使用 source OCR / source / context / glossary / provider / model / prompt / config；locks 被尊重。 |
| I03 Rerun unchanged cleaned / typeset artifacts | PASS | 复用前要求 artifact provenance、presence 和 hash validation。 |
| Q01 Provider refusal persistence | PASS | refusal 作为 ToolRunLog、refused attempt、QualityIssue、WorkflowDecision，以及适用时的 decision-issue link 持久化；没有 bypass data。 |
| Q02 Blocking issue prevents readiness / export | PASS | open blocking issue query by scope 阻塞 normal readiness / export；warning 仍由 profile 控制。 |
| Q03 Cleaning skip warning state | PASS | skip stage / status 和 warning issue 持久化；有 unresolved skip / warning 时不允许纯 `ready_for_export`。 |
| S01 OCR edit | PASS | 新 OCRResult 加 active pointer、downstream stale statuses、page stale flags 和 issue lifecycle changes 原子完成。 |
| S02 Translation edit | PASS | 新 TranslationResult 加 active pointer、translation_check / typesetting stale 和 old typeset non-effectiveness 原子完成。 |
| M01 Initialize app.db | PASS | app migration ledger 立即存在且独立。 |
| M02 Initialize project.db | PASS | project migration ledger 与 ProjectMetadata identity 立即存在且独立。 |
| M03 Add enum value later | PASS | stable string values 追加式演进，不需要重写 historical audit rows。 |
| Boundary failure checks | PASS | 最终设计禁止 provider DB access、artifact workflow decisions、QualityCheck state advancement、SQL leakage、Page.status-only recovery、timestamp active selection、image BLOBs 和 P1 / P2 requirements。 |

## 18. 被拒绝的备选方案

| Alternative | Reason rejected |
| --- | --- |
| Single global SQLite database | 削弱 Project isolation、backup / restore、corruption blast radius 和 delete boundary。 |
| Cross-database transaction for app / project writes | MVP-0 不需要，且与 filesystem operations 结合时脆弱。有序可恢复 lifecycle 已足够。 |
| Long write transaction around provider call | 造成 SQLite lock 和 crash recovery 问题。 |
| Provider Adapter writes database rows or artifact metadata | 违反 provider boundary，并隐藏 workflow decisions。 |
| Artifact registration selects active pointers | 绕过 quality checks 和 acceptance。 |
| QualityCheckService persists issue lifecycle or workflow state | 拆分所有权；acceptance 必须保持 decisions / issues / statuses 一致。 |
| Generic repository framework or `Repository<T>` | 泄露 table shape，并诱导 workflow modules 进行 ad hoc persistence。 |
| Page.status as recovery source of truth | 无法解释 active pointer drift、missing artifacts、abandoned attempts、stale state 或 partial acceptance。 |
| Latest timestamp selects current result / artifact | 与 active pointers、locked translations、manual edits 和 official unselected artifacts 冲突。 |
| Full export implementation before readiness | Scope creep；workflow-state 已区分 `export_check` readiness 与 export records。 |
| In-memory fake persistence for FakeProvider | 无法验证 recovery、migration、idempotency 或 repository boundaries。 |

## 19. 风险与缓解

| Risk | Mitigation |
| --- | --- |
| Active pointer / status drift | Acceptance transaction 使用 expected active pointer ids、dependency hashes 和 stage status guards。 |
| Artifact DB / filesystem drift | ArtifactService hash validation 和 `storage_state` updates；WorkflowLoopEngine 拥有 rebuild / warn / block。 |
| Official unselected artifact confusion | Unselected artifacts 只是 evidence / reuse candidates；绝不按 timestamp-selected。 |
| Repository contracts become table-shaped | 使用 use-case snapshots 和 named operations；不给 workflow modules generic query API。 |
| StageExecutor write authority expands | 限制为 `StageEvidenceWriter`；不允许 active pointer、issue lifecycle、decision 或 generic repository writes。 |
| QualityCheck persistence ownership drift | MVP-0 中使用 repository-free issue drafts；WorkflowLoopEngine 在 acceptance 中持久化。 |
| Migration / open ambiguity | Project open 在 repositories 暴露前返回明确 readiness 或 blocked states。 |
| False idempotent reuse | 复用前要求完整 dependency keys 和 artifact validation。 |
| Under-tested recovery | 将 crash-after-OCR 和 registered-but-unselected artifact tests 纳入临时 SQLite suite。 |
| Skeleton app config becomes permanent weak design | 将 provider / profile skeletons 标记为 MVP-0 only，并要求 real providers 前补充 follow-up design。 |

## 20. ADR 清单

- `docs/design/persistence/adr/0001-repository-unit-of-work-boundary.md`
- `docs/design/persistence/adr/0002-acceptance-transaction-semantic-commit.md`
- `docs/design/persistence/adr/0003-independent-app-project-migrations.md`
- `docs/design/persistence/adr/0004-recovery-from-committed-evidence.md`
- `docs/design/persistence/adr/0005-fakeprovider-mvp0-readiness-scope.md`

## 21. 未决问题与延后决策

见 `open-questions.md`。

没有任何问题阻塞 FakeProvider single-Page persistence readiness design。延后领域包括精确 DDL / ORM / migration files、method names、DTO shapes、migration tool topology、heartbeat values、restore / relink UX、export implementation、完整 provider / profile config、cleanup TTLs 和 P1 / P2 features。
