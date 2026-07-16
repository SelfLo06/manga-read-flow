# 数据模型详细设计 v0.1

## 1. 设计目标

本设计支撑 SRS 与 HLD 描述的 MVP 本地漫画翻译与基础嵌字工作流。模型针对 Project 隔离、重启恢复、局部重试、结果版本化、artifact 可追踪性、导出安全，以及基于 SQLite + 本地文件系统 workspace 的实现就绪性进行优化。

关键决策：

- 使用 `app.db` 保存全局注册表 / 设置，并为每个 Project 使用一个 `project.db` 保存所有 Project-owned content、workflow、quality、artifact、glossary、task 和 export 数据。
- 图片与大型 payload bytes 只存放在文件系统。SQLite 只保存 artifact metadata。
- OCR 与 translation results 保持不可变并版本化。
- 使用 active pointer fields 作为 P0 当前 OCR / translation 与 page image outputs 的事实来源。不要使用独立 active flags。
- 持久化每个 `WorkflowAttempt`、`WorkflowDecision`、`ToolRunLog`、`QualityIssue`，以及解释恢复和 export gates 所需的相关 `ProcessingArtifact`。
- Provider Adapters 不得访问数据库、决定 artifact lifecycle、决定 retry / fallback / skip / block，也不得创建 QualityIssue。

## 2. 来源文档

已阅读并综合：

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/design/data-model/GOAL.md`
- `docs/design/data-model/HARNESS.md`
- `docs/design/data-model/proposals/01-domain-model-agent.md`
- `docs/design/data-model/proposals/02-persistence-agent.md`
- `docs/design/data-model/proposals/03-workflow-state-agent.md`
- `docs/design/data-model/proposals/04-artifact-quality-agent.md`
- `docs/design/data-model/proposals/05-api-orm-readiness-agent.md`
- `docs/design/data-model/reviews/00-preflight.md`
- `docs/design/data-model/reviews/01-cross-review.md`

已解决的来源张力：

- SRS 将 `project_config` 列为候选数据块。最终设计将其映射为 `Project` defaults、全局 provider config references、`ProcessingProfile` templates，以及不可变的每任务 `ProcessingProfileSnapshot` records。不引入独立 P0 `ProjectConfig` table。

## 3. app.db / project.db 拆分

`app.db` 保存全局应用数据：

| Entity / data | Responsibility |
| --- | --- |
| `Project` | Project registry、display metadata、workspace / project.db path、default languages、default profile reference、lifecycle status、soft delete / trash metadata。 |
| `ProviderConfig` | Provider identity、capability metadata、model defaults、license / capability notes，以及 secret references only。API keys 不以 raw values 存放于此，也绝不存入 `project.db`。 |
| `ProcessingProfile` | 内置和用户可编辑的 workflow policy templates。 |
| `GlobalSetting` | Workspace root、UI / application preferences 与 non-secret defaults。 |
| `schema_migrations` | app.db migration ledger。 |

每个 `project.db` 保存 Project-owned 数据：

| Entity / data | Responsibility |
| --- | --- |
| `ProjectMetadata` | `project_id`、project schema version 和 workspace identity 的本地镜像，用于完整性检查。 |
| Content hierarchy | `Batch`、`Page`、`TextBlock`。 |
| Result history | `OCRResult`、`TranslationResult`。 |
| Glossary | `GlossaryTerm`、`GlossaryVersion`。 |
| Workflow state | `ProcessingTask`、`ProcessingProfileSnapshot`、`WorkflowAttempt`、`WorkflowDecision`、`WorkflowDecisionIssue`。 |
| Quality and tools | `QualityIssue`、`ToolRunLog`。 |
| Files | `ProcessingArtifact`。 |
| Export | `ExportRecord`，可选 `ExportIssueSnapshot` 或结构化 issue snapshot artifact。 |
| `schema_migrations` | project.db migration ledger。 |

规则：

- 不使用跨数据库 foreign keys。
- 在可行时，`project.db` 内部使用同库 foreign keys。
- `project_id` 仍存储在 project-owned rows 上，作为隔离 guard。
- 打开 Project 时验证 `app.db.projects.project_id` 与 `project.db.project_metadata.project_id` 匹配。
- Artifact paths 使用 project-relative。`app.db` 负责解析 project workspace root。

## 4. 完整实体列表

P0 domain 与 workflow entities：

- `Project`
- `ProviderConfig`
- `ProcessingProfile`
- `ProjectMetadata`
- `Batch`
- `Page`
- `TextBlock`
- `OCRResult`
- `TranslationResult`
- `GlossaryTerm`
- `GlossaryVersion`
- `ProcessingTask`
- `ProcessingProfileSnapshot`
- `WorkflowAttempt`
- `WorkflowDecision`
- `WorkflowDecisionIssue`
- `QualityIssue`
- `ProcessingArtifact`
- `ToolRunLog`
- `ExportRecord`

P1 / P2 candidate entities：

- `GeometryRevision`
- `PageTranslationContext`
- `ExportIssueSnapshot`
- `ArtifactRetentionPolicy`
- `TermCandidate`
- `ContextPack`
- `TaskSummaryIndex`

## 5. P0 / P1 / P2 实体分类

| Priority | Entity / capability | Decision |
| --- | --- | --- |
| P0 | Project、Batch、Page、TextBlock | 必需 ownership spine。Page 属于 Batch；Batch 属于 Project；TextBlock 属于 Page。 |
| P0 | OCRResult、TranslationResult | 不可变版本化结果。用户编辑创建新版本。 |
| P0 | Active pointers | `TextBlock.active_ocr_result_id`、`TextBlock.active_translation_result_id`、`Page.original_artifact_id`、`Page.active_cleaned_artifact_id` 和 `Page.active_typeset_artifact_id`。 |
| P0 | GlossaryTerm、GlossaryVersion | Project-local glossary，以及 translation provenance 的版本边界。 |
| P0 | ProcessingTask、WorkflowAttempt、WorkflowDecision | 持久化 workflow execution、retry / fallback / skip / block 理由，以及 recovery support。 |
| P0 | QualityIssue | Discovered / root stage attribution、severity、blocking flag、status、export gate source。 |
| P0 | ProcessingArtifact | 原图、masks、crops、raw payloads、cleaned / typeset / export artifacts、debug bundles 的 metadata。 |
| P0 | ToolRunLog | 脱敏后的 external / local tool invocation trace。 |
| P0 | ExportRecord | 成功、带 warning 和被拒绝 export attempt metadata。 |
| P0 | ProcessingProfile and ProcessingProfileSnapshot | 可变 app-level templates 加不可变 per-run policy snapshots。 |
| P1 | GeometryRevision | 手动 geometry history。P0 直接在 TextBlock 上保留 geometry fields。 |
| P1 | TermCandidate | 自动或 quick-add glossary suggestions。 |
| P1 | Export manifest detail | ZIP manifest artifact 由 ExportRecord 支持，但详细 manifest schema 属于 P1。 |
| P1 | Cost / token rollups | ToolRunLog 或 summaries 上的可选字段。 |
| P1 | Forced / incomplete export | 仅高级流程；正常 export 阻塞 unresolved blocking issues。 |
| P2 | Multi-page ContextPack | MVP 使用 Page-level context。 |
| P2 | Advanced artifact lineage graph | MVP recovery 不需要。 |

## 6. 实体职责表

| Entity | Responsibility | Owns / does not own |
| --- | --- | --- |
| Project | 一个漫画 workflow project 的 registry 和 lifecycle boundary。 | 在 app.db 中拥有 project discovery 和 workspace location。不直接拥有 page / result rows。 |
| ProviderConfig | Provider metadata、capability / license notes 和 secret references。 | 不在 project.db 或 logs 中存储 raw API keys。 |
| ProcessingProfile | retry budgets、quality strictness、fallback、warning export 和 retention 的可编辑模板。 | edits 之后不解释历史 runs；snapshots 负责解释历史。 |
| ProjectMetadata | project.db 内的完整性标记。 | 验证 project.db 属于 app registry entry。 |
| Batch | 上传 / 处理分组和 Page ordering scope。 | 拥有 Pages。不拥有 glossary。 |
| Page | 一张漫画图片、页面顺序、摘要状态和 active page artifacts。 | 拥有 TextBlocks 和 page output pointers。Original image 不可变。 |
| TextBlock | 检测到的文本区域、geometry、reading order、skip / manual state、phase statuses、active OCR / translation pointers。 | 拥有 OCRResult 和 TranslationResult histories。 |
| OCRResult | 单个 TextBlock 的不可变 OCR output version。 | 不决定 active selection；TextBlock pointer 决定。 |
| TranslationResult | 基于 page-level context 的单个 TextBlock 不可变 translation output version。 | 链接 source OCR version / hash 和 glossary version。 |
| GlossaryTerm | Mutable current Project glossary term。 | 仅 Project-scoped。 |
| GlossaryVersion | 不可变 glossary state identity。 | TranslationResult 始终记录 version / hash。 |
| ProcessingTask | 持久化的 user / system requested work item。 | 跟踪 task state 和所选 profile snapshot。不存储 raw payloads。 |
| ProcessingProfileSnapshot | task / export / attempt 使用的不可变 serialized policy。 | warning export 和 retry decisions 的历史来源。 |
| WorkflowAttempt | 一个 stage / target 的一次有界 attempt。 | metadata 始终持久化，即使 payload artifacts 被清理。 |
| WorkflowDecision | WorkflowLoopEngine 对 continue / retry / fallback / skip / warning / block / finish 的理由。 | 通过 `WorkflowDecisionIssue` 链接 QualityIssues。 |
| WorkflowDecisionIssue | decisions 与 issues 之间的关系。 | 避免 issue-id lists 成为事实来源。 |
| QualityIssue | 带 discovered / root attribution 的 quality / refusal / export issue。 | Export gate source。不自行推进 workflow。 |
| ProcessingArtifact | 文件 metadata 事实来源：path、hash、type、scope、retention、storage state。 | 只由 ArtifactService registration / lifecycle 管理。 |
| ToolRunLog | 脱敏后的 tool / provider invocation trace。 | 记录 metadata 和 artifact refs，不记录 secrets。 |
| ExportRecord | Export precheck 和 output history。 | 记录 success、warning-allowed 或 blocked export attempts。 |

## 7. 关系表

| Relationship | Cardinality | Notes |
| --- | --- | --- |
| Project -> Batch | 1 to many | 通过一个 project.db 内的 `project_id`；没有来自 app.db 的跨库 FK。 |
| Batch -> Page | 1 to many | `Page.page_index` 在一个 Batch 的 active Pages 中唯一。 |
| Page -> TextBlock | 1 to many | Detection 创建 TextBlock。 |
| TextBlock -> OCRResult | 1 to many | 不可变版本历史。 |
| TextBlock -> TranslationResult | 1 to many | 不可变版本历史。 |
| TextBlock -> active OCRResult | many to 0 / 1 | 仅 pointer。Active OCR 必须属于同一 TextBlock。 |
| TextBlock -> active TranslationResult | many to 0 / 1 | 仅 pointer。Active translation 必须属于同一 TextBlock。 |
| TranslationResult -> OCRResult | many to 1 | 必需 `source_ocr_result_id` 加 `source_text_hash`。 |
| TranslationResult -> GlossaryVersion | many to 1 | 即使是空 glossary，也必须通过 initial version 记录。 |
| Page -> ProcessingArtifact | many to 0 / 1 per pointer | Original、active cleaned、active typeset。 |
| OCRResult -> ProcessingArtifact | many to optional artifacts | 保留时包含 input crop 和 raw OCR output。 |
| WorkflowAttempt -> ToolRunLog | 1 to zero / many | Cache reuse attempts 可能没有 provider call。 |
| WorkflowAttempt -> ProcessingArtifact | 1 to zero / many | Raw request / response / debug / attempt artifacts。 |
| WorkflowAttempt -> TranslationResult | 1 to many for page translation | 一个 page attempt 可以创建多个 TextBlock TranslationResults。 |
| WorkflowDecision -> QualityIssue | many to many | 由 `WorkflowDecisionIssue` 规范化。 |
| QualityIssue -> target | many to one polymorphic target | 始终包含 `project_id`；常见 scopes 包括 `batch_id`、`page_id`、`text_block_id`。 |
| ExportRecord -> ProcessingArtifact | many to optional output / manifest / snapshot artifacts | Blocked exports 可能没有 output artifact。 |
| ProcessingTask -> ProcessingProfileSnapshot | many to 1 | Snapshot 不可变，并且 local to project.db。 |

## 8. 各实体关键字段

这是 implementation-ready 的字段分组，不是 SQL DDL。

| Entity | Key field groups |
| --- | --- |
| Project | `project_id`、`name`、`workspace_project_path`、`project_db_path`、`default_source_language`、`default_target_language`、`default_processing_profile_id`、`status`、`deleted_at`、`trash_path`、timestamps。 |
| ProviderConfig | `provider_config_id`、`provider_name`、`provider_type`、`capabilities`、`license_note`、`default_model_id`、`secret_ref`、`enabled`、timestamps。 |
| ProcessingProfile | `profile_id`、`name`、`version`、`scope`、`is_builtin`、provider refs、retry budgets、quality strictness、fallback policy、warning export policy、retention / debug policy、timestamps。 |
| ProjectMetadata | `project_id`、`project_schema_version`、`workspace_identity`、`created_at`、`last_opened_at`。 |
| Batch | `batch_id`、`project_id`、`name`、`source_language`、`target_language`、`page_count`、`status`、`quality_summary`、`last_processed_at`、`deleted_at`、timestamps。 |
| Page | `page_id`、`project_id`、`batch_id`、`page_index`、`original_filename`、`original_artifact_id`、`active_cleaned_artifact_id`、`active_typeset_artifact_id`、`status`、`translation_context_hash`、`translation_context_stale`、`has_stale_blocks`、`quality_flags`、`deleted_at`、timestamps。 |
| TextBlock | `text_block_id`、`project_id`、`batch_id`、`page_id`、`reading_order`、bbox fields、`polygon_json`、`geometry_revision`、`geometry_hash`、`source_direction`、`detection_provider`、`detection_confidence`、`active_mask_artifact_id`、`active_ocr_result_id`、`active_translation_result_id`、`locked_translation_result_id`、stage statuses、skip / manual fields、`deleted_at`、timestamps。 |
| OCRResult | `ocr_result_id`、`project_id`、`text_block_id`、`version_number`、`parent_ocr_result_id`、`source_type`、`source_text`、`source_text_hash`、confidence / quality、provider / model / tool metadata、`input_artifact_id`、`raw_output_artifact_id`、`input_hash`、`config_hash`、`geometry_hash`、`workflow_attempt_id`、`tool_run_id`、`is_user_edited`、timestamps。 |
| TranslationResult | `translation_result_id`、`project_id`、`text_block_id`、`version_number`、`parent_translation_result_id`、`source_type`、`source_ocr_result_id`、`source_text_hash`、`translation_text`、`translation_text_hash`、provider / model / prompt metadata、`glossary_version_id`、`glossary_version_number`、`glossary_terms_hash`、`context_hash`、`generation_config_hash`、`page_translation_group_key`、`used_terms_json`、confidence / quality、`needs_review`、`error_code`、`workflow_attempt_id`、`tool_run_id`、`is_user_edited`、timestamps。 |
| GlossaryTerm | `term_id`、`project_id`、`source_text`、`target_text`、`term_type`、`reading`、`aliases_json`、`case_sensitive`、`priority`、`status`、`created_from_text_block_id`、`created_by_user`、`note`、`deleted_at`、timestamps。 |
| GlossaryVersion | `glossary_version_id`、`project_id`、`version_number`、`terms_hash`、`term_count`、optional `snapshot_artifact_id`、`created_reason`、`created_at`。 |
| ProcessingTask | `task_id`、`project_id`、`target_type`、`target_id`、common scope ids、`task_type`、`requested_stages`、`resume_policy`、`status`、`current_stage`、progress summary、`profile_snapshot_id`、`idempotency_key`、pause / cancel fields、`heartbeat_at`、`started_at`、`finished_at`、timestamps。 |
| ProcessingProfileSnapshot | `profile_snapshot_id`、`project_id`、`source_profile_id`、`source_profile_version`、`snapshot_schema_version`、`settings_json`、`settings_hash`、`created_at`。 |
| WorkflowAttempt | `attempt_id`、`project_id`、`task_id`、common scope ids、`stage`、`target_type`、`target_id`、`attempt_number`、provider / model / tool metadata、`input_hash`、`config_hash`、`context_hash`、`profile_snapshot_id`、`profile_hash`、`status`、`error_code`、sanitized message、retry budget fields、artifact refs、timestamps。 |
| WorkflowDecision | `decision_id`、`project_id`、`task_id`、`attempt_id`、common scope ids、`stage`、`target_type`、`target_id`、`decision_type`、`reason_code`、`rationale_summary`、`next_stage`、`fallback_provider`、retry budget fields、`profile_snapshot_id`、`created_at`。 |
| WorkflowDecisionIssue | `decision_id`、`quality_issue_id`、`relation_type`、`created_at`。 |
| QualityIssue | `quality_issue_id`、`project_id`、common scope ids、`target_type`、`target_id`、`discovered_stage`、`root_stage`、`issue_type`、`error_code`、`severity`、`is_blocking`、`status`、message / suggested action fields、related attempt / tool / artifact refs、`input_hash`、`config_hash`、`applies_to_result_id`、resolution fields、timestamps。 |
| ProcessingArtifact | `artifact_id`、`project_id`、common scope ids、`owner_type`、`owner_id`、`artifact_type`、`source_stage`、`relative_path`、`file_hash`、`hash_algorithm`、`byte_size`、`mime_type`、dimensions、`workflow_attempt_id`、`tool_run_id`、`retention_class`、`storage_state`、debug / sensitive flags、cleanup fields、timestamps。 |
| ToolRunLog | `tool_run_id`、`project_id`、`task_id`、`attempt_id`、common scope ids、`stage`、`tool_name`、`tool_version`、`provider_name`、`model_id`、artifact refs、`input_hash`、`config_hash`、`status`、`error_code`、`error_class`、`is_provider_refusal`、sanitized message、optional usage / cost、timings。 |
| ExportRecord | `export_id`、`project_id`、`target_type`、`target_id`、common scope ids、`export_type`、`format`、`profile_snapshot_id`、`profile_hash`、`status`、precheck status、issue counts / hash、`allowed_with_warnings`、output / manifest / snapshot artifact refs、rejected reason、timestamps。 |

## 9. 索引与唯一性建议

建议唯一性：

- `Project.project_id` 在 app.db 中唯一。
- Active `Project.workspace_project_path` 在 app.db 中唯一。
- `Batch.batch_id` 在 project.db 中唯一。
- Active `Page(batch_id, page_index)` 唯一。
- 分配 reading order 后，Active `TextBlock(page_id, reading_order)` 唯一。
- `OCRResult(text_block_id, version_number)` 唯一。
- `TranslationResult(text_block_id, version_number)` 唯一。
- `GlossaryVersion(project_id, version_number)` 唯一。
- `ProcessingProfileSnapshot(settings_hash)` 可在每个 Project 内唯一，以复用相同 snapshots。
- `WorkflowAttempt(task_id, stage, target_type, target_id, attempt_number)` 唯一。
- 当 storage state 为 `present` 或 `moved_to_trash` 时，active artifact path `ProcessingArtifact(project_id, relative_path)` 唯一。

建议索引：

- Project listing：`Project(status, updated_at)`。
- Batch progress：`Batch(project_id, status)`。
- Page order / progress：`Page(batch_id, page_index)`、`Page(batch_id, status)`。
- TextBlock recovery：`TextBlock(page_id, detection_status)`、`TextBlock(page_id, ocr_status)`、`TextBlock(page_id, translation_status)`、`TextBlock(page_id, cleaning_status)`、`TextBlock(page_id, typesetting_status)`。
- Result histories：`OCRResult(text_block_id, created_at)`、`TranslationResult(text_block_id, created_at)`。
- OCR cache：`OCRResult(text_block_id, input_hash, config_hash, provider, model_id, tool_version)`。
- Translation cache：`TranslationResult(source_text_hash, context_hash, glossary_version_id, provider, model_id, prompt_template_version, generation_config_hash)`。
- Glossary lookup：`GlossaryTerm(project_id, source_text, status)`。
- Recovery：`ProcessingTask(project_id, status, heartbeat_at)`、`WorkflowAttempt(task_id, stage, status)`。
- Export gate：`QualityIssue(project_id, is_blocking, status)`，加 batch / page / textblock 的 scope indexes。
- Artifact cleanup：`ProcessingArtifact(project_id, retention_class, storage_state, cleanup_eligible_at)`。
- Artifact lookup：`ProcessingArtifact(project_id, artifact_type)`、`ProcessingArtifact(file_hash, artifact_type)`。
- Tool diagnostics：`ToolRunLog(attempt_id)`、`ToolRunLog(project_id, stage, status, started_at)`。
- Export history：`ExportRecord(project_id, target_type, target_id, created_at)`。

## 10. 版本化规则

OCR：

- 每个 provider OCR output 创建一个 `OCRResult`，除非幂等性复用了已有 result。
- 每次用户 OCR edit 都创建新的 `OCRResult`，并设置 `source_type = user_edit`。
- 既有 OCR 文本永不覆盖。
- 无效 OCR provider output 可以创建 ToolRunLog、WorkflowAttempt、QualityIssue、WorkflowDecision 和 failed artifacts，而不创建 OCRResult。

Translation：

- Page-level translation attempts 创建零个或多个 `TranslationResult` rows，每个有效返回的 TextBlock output 一个。
- 每次用户 translation edit 都创建新的 `TranslationResult`，并设置 `source_type = user_edit`。
- `TranslationResult.source_ocr_result_id` 与 `source_text_hash` 都是必需字段。
- `TranslationResult.glossary_version_id`、`glossary_version_number` 和 `glossary_terms_hash` 都是必需字段。
- 既有 translation text 永不覆盖。

Glossary：

- 对 active glossary terms 的任何语义性 create / edit / delete / status change 都创建新的 `GlossaryVersion`。
- 如果 normalized `terms_hash` 未变化，no-op saves 可以复用现有 version。
- `snapshot_artifact_id` 是可选 P0，但建议用于 strict / debug reproducibility。

Geometry：

- P0 将 bbox、polygon、source direction、`geometry_revision` 和 `geometry_hash` 存储在 TextBlock 上。
- Geometry changes 增加 revision / hash，并将依赖 stages 标记为 stale。
- 当需要手动 geometry edit history 时，`GeometryRevision` 属于 P1。

Workflow：

- Attempts 和 decisions 是 append-only。
- Retry 创建新的 WorkflowAttempt 和 WorkflowDecision。
- Result rows 是 domain state；WorkflowAttempt 是 audit / provenance，不是 result owner。

## 11. Active pointer 规则

P0 active source of truth：

- `TextBlock.active_ocr_result_id`
- `TextBlock.active_translation_result_id`
- `TextBlock.locked_translation_result_id`
- `Page.original_artifact_id`
- `Page.active_cleaned_artifact_id`
- `Page.active_typeset_artifact_id`

规则：

- P0 中 OCRResult 或 TranslationResult 不使用独立 `is_active` flags。
- Active OCR / translation targets 必须属于同一 TextBlock。
- 新 provider results 只有在 QualityCheckService output 和 WorkflowLoopEngine decision 后才变为 active。
- 用户编辑会创建新的 result version，并立即选中它。
- Locked translation 由 `TextBlock.locked_translation_result_id` 表示。除非用户明确 override，自动 workflow 不得替换它。
- Active 表示被 UI / downstream context 选中。Export-effective 表示被选中、fresh、dependency hashes 匹配，并且没有 unresolved blocking issue 适用。
- 下游 stale state 不清除 active pointers；UI 需要旧的 selected data 供 review。
- Active pointer updates 应与 new result creation、stale propagation 和相关 WorkflowDecision 原子提交。

被拒绝的备选方案：

- Result rows 上的 active flags。拒绝原因：会产生重复 active source of truth 和 multi-active 冲突风险。
- 从最新 timestamp 推导 active result。拒绝原因：locked 或手动选择的旧结果也可能有效。

## 12. stale 传播规则

| Trigger | Required data impact |
| --- | --- |
| OCR edit | 创建 OCRResult；更新 active OCR pointer；将 translation、translation_check 和 typesetting 标记为 stale；将 review 设为 needs_review；将 Page translation context stale 和 has_stale_blocks 置位。 |
| Translation edit | 创建 TranslationResult；更新 active translation pointer；将 typesetting 标记为 stale；将 review 设为 needs_review，并设置 Page has_stale_blocks。 |
| Geometry / mask edit | 更新 geometry revision / hash 和 mask artifact；将 cleaning 和 typesetting 标记为 stale；如果 crop input 变化，则将 OCR 标记为 stale。 |
| Reading order edit | 将 Page translation context 标记为 stale；active translations 保持 selected，但对检查而言变为 page-context-stale。 |
| Glossary edit | 创建 GlossaryVersion；旧 TranslationResults 保留旧 version；strict profiles 对受影响 translations 创建 warnings / needs_review；default profile 可仅对 used-term intersections warning。 |
| Provider config / profile change | 既有 results 保持 historical；新 tasks 使用新 profile snapshot 和 config hashes；将新 config 应用到现有 scope 会将受影响 stages 标记为 stale。 |
| TextBlock skipped | Downstream stages 变为 skipped；Page 可进入 ready_for_export_with_warnings，而不是纯 ready_for_export。 |
| TextBlock unskipped | 根据可用上游 active results，将相关 stages 重置为 pending 或 stale。 |
| QualityIssue resolved | Export gate 根据 unresolved blocking issue query 重新计算。 |

Issue statuses：

- `open`：未解决，并被 export gate 计入。
- `resolved`：通过 rerun、edit、user action 或 explicit resolution 修复。
- `accepted_warning`：warning 被接受用于 export；仍可见且不计为 blocking。
- `stale`：不再适用于 active inputs / results。
- `superseded`：被更新 issue 替代。

Unresolved blocking issue 定义：

- `is_blocking = true`
- `status = open`
- target falls within export scope

## 13. Artifact 生命周期

ArtifactService 拥有 path generation、safe writes、hashing、registration、retention、cleanup、trash moves、missing-file checks 和 restore validation。

Provider Adapters 可以使用临时文件，但不能写 official workspace paths 或登记 artifact records。

必需 artifact states：

| State | Meaning |
| --- | --- |
| `present` | 文件存在于已登记的 project-relative path。 |
| `metadata_only_cleaned` | 文件 bytes 已由 retention policy 清理；metadata、hashes、provenance 和 workflow refs 保留。 |
| `moved_to_trash` | 文件已移动到 project / project-local trash，用于 soft delete。 |
| `missing` | 预期存在文件，但找不到或 hash validation 失败。 |
| `deleted` | 文件已在确认或 retention cleanup 后永久删除。 |

必需 retention classes：

| Class | Default |
| --- | --- |
| `permanent_original` | 保留到 Project / Page 永久删除。 |
| `active_result` | 当被 active page / textblock / export pointers 引用时保留。 |
| `failed_attempt_payload` | 默认保留。 |
| `successful_payload` | 可依据 profile policy 清理。 |
| `debug` | 仅当 debug profile / policy 启用时保留。 |
| `cache_rebuildable` | 如果可重建，宽限期后可清理。 |
| `export_output` | 保留到 export deletion 或 Project deletion。 |
| `trash_pending_delete` | soft delete 后 permanent purge 前移动 / 标记。 |

Safety flags：

- `is_debug`
- `may_contain_original_image`
- `may_contain_ocr_text`
- `may_contain_translation`
- `may_contain_provider_response`
- `contains_secret_redacted`

规则：

- SQLite 中不存 image BLOBs。
- Original images 永不覆盖。
- Domain rows 存 artifact IDs，而不是 authoritative paths。
- Failed raw LLM JSON responses 和 provider refusal evidence 默认保留。
- Successful raw request / response payloads 可变为 `metadata_only_cleaned`。
- Cleanup 不得移除 active original、active cleaned、active typeset、active mask、export output 或 retained failed artifacts。

## 14. WorkflowAttempt 与 WorkflowDecision 模型

`ProcessingTask` 是持久化 user / system command。`WorkflowAttempt` 是对某个 stage / target 的一次有界执行尝试。`WorkflowDecision` 是 WorkflowLoopEngine 在 attempt output、quality checks、retry budget、profile policy 和当前 state 之后给出的理由。

Stage vocabulary：

- `import`
- `detection`
- `ocr`
- `translation`
- `translation_check`
- `cleaning`
- `typesetting`
- `export`
- `artifact_cleanup`

Attempt statuses：

- `planned`
- `running`
- `succeeded`
- `failed`
- `refused`
- `cancelled`
- `skipped`
- `reused_cached`
- `interrupted`
- `abandoned_after_crash`

Decision types：

- `continue`
- `reuse_cached_result`
- `retry_same_stage`
- `fallback_provider`
- `retry_upstream_stage`
- `skip_target`
- `mark_warning`
- `block`
- `finish_ready_for_export`
- `finish_ready_for_export_with_warnings`
- `pause_for_user`
- `cancel`

Transaction boundary guidance：

- 在 external provider call 前持久化 task / attempt start。
- Provider call 期间不持有 write transaction。
- Provider 返回后，通过 ArtifactService 登记 artifacts，并持久化 ToolRunLog / attempt outcome。
- 在一个 transaction 中创建 result rows、创建 / 更新 QualityIssues、创建 WorkflowDecision、在接受时更新 active pointers，并更新 stage statuses。
- 如果 crash 发生在 file write 和 artifact registration 之间，recovery 扫描 temp / attempt directories 中的 orphan files，并根据 retention policy 登记或清理。

## 15. QualityIssue 模型

QualityCheckService 拥有 issue creation、severity、blocking flag、discovered stage、root-stage attribution 和 suggested action。WorkflowLoopEngine 消费 issues，但不执行 quality detection。

必需字段：

- target：`target_type`、`target_id`，以及 common scope ids。
- attribution：`discovered_stage`、`root_stage`。
- classification：`issue_type`、`error_code`。
- severity：`info`、`warning`、`error`、`blocking`。
- gate：`is_blocking`。
- status：`open`、`resolved`、`accepted_warning`、`stale`、`superseded`。
- provenance：related attempt、tool run、artifact、result、input / config hashes。

Provider refusal：

- `ToolRunLog.status = refused` 或 failed 且 `is_provider_refusal = true`。
- `WorkflowAttempt.status = refused`。
- `QualityIssue.issue_type = provider_refusal` 或 stage-specific code，例如 `translation_provider_refused`。
- `QualityIssue.discovered_stage = translation`，用于 translation refusal。
- `QualityIssue.root_stage = provider_policy`。
- `WorkflowDecision` 记录 fallback、warning、skip、manual path 或 block。

Export gate：

- 正常 export 拒绝 scope 内任何 open blocking issue。
- Warning export 只有在 active `ProcessingProfileSnapshot.allow_warning_export` 允许时才可执行。
- Accepted warnings 保持可见，并记录在 ExportRecord snapshots 上。

## 16. ToolRunLog 模型

`ToolRunLog` 记录每次 external 或 local tool / provider invocation：

- stage、target scope、attempt id。
- tool / provider / model identity 与 versions。
- input / config / context hashes。
- 保留时的 input / output / raw request / raw response artifact ids。
- status、error_code、error_class、`is_provider_refusal`。
- sanitized error / user messages。
- timing 与可选 token / cost estimates。
- sanitization version。

规则：

- 不记录 API keys、tokens、credentials、secret headers 或 raw authorization values。
- Raw payloads 如果保留，是带 retention / safety flags 的 ProcessingArtifacts。
- 当 cache 复用或不需要 provider call 时，WorkflowAttempt 可以有零个 ToolRunLogs。
- Page-level translation attempt 通常有一个 page-scoped ToolRunLog，并通过共享 attempt / tool run 链接多个 TranslationResults。

## 17. Export 模型

正常 export 流程：

1. Export use case 创建或规划一个 `ExportRecord`。
2. ExportCheck 查询目标 scope 内 unresolved blocking QualityIssues。
3. 如果存在 blockers，`ExportRecord.status = blocked` 并记录 blocker counts / hash / snapshot。不创建正常 output artifact。
4. 如果只存在 warnings，仅当 `ProcessingProfileSnapshot` 允许 warning export 时继续。
5. 成功 export 创建 output artifacts 和可选 manifest artifact。

Export statuses：

- `planned`
- `succeeded`
- `blocked`
- `failed`
- `cancelled`
- `succeeded_with_warnings`

字段：

- target scope：Page 或 Batch。
- export type / format。
- profile snapshot / hash。
- precheck status。
- blocking 和 warning issue counts。
- issue snapshot hash 与可选 issue snapshot artifact。
- output / manifest artifact ids。
- rejected reason。

P1 forced / incomplete export：

- 延后到后续详细设计。
- 如果引入，绝不能与 normal export 混淆，且必须存储显式 `is_forced_export` 或 `is_incomplete_export`，并附带 blocking issue summary。

## 18. ProcessingProfile 模型

`ProcessingProfile` templates 位于 app.db。不可变 execution snapshots 位于 project.db，形式为 `ProcessingProfileSnapshot`。

设计级表示：

- `ProcessingProfile` app.db row：可编辑模板，包含 `profile_id`、`name`、`version`、provider references、retry budgets、strictness、fallback policy、warning export policy、retention policy 和 debug policy。
- `ProcessingProfileSnapshot` project.db row：task / export / attempt 使用的不可变 serialized policy，包含 `source_profile_id`、`source_profile_version`、`snapshot_schema_version`、`settings_json` 和 `settings_hash`。

规则：

- Task、WorkflowAttempt、WorkflowDecision 和 ExportRecord 引用相关 snapshot 或 hash。
- Global template edits 永不改写历史 workflow meaning。
- Provider secret values 不复制进 snapshots。Snapshots 只包含 provider config references 和 sanitized provider identity。
- Warning export decisions 使用有效 snapshot，而不是当前 mutable template。

被拒绝的备选方案：

- 在 tasks 上只存 mutable `profile_id`。拒绝原因：profile edits 后，历史 retry / export behavior 会改变。
- 存储独立 P0 ProjectConfig table。拒绝原因：SRS `project_config` 已由 Project defaults、profile templates、provider config references 和 snapshots 满足。

## 19. Soft delete 规则

Project：

- Soft delete 更新 app.db Project status / deleted_at / trash_path。
- 在确保没有 task running 后，将 Project workspace 移动到 trash 或标记为 trash-pending。
- project.db 在永久删除前保持可恢复。
- 永久删除需要确认，并移除 project.db 和 project workspace。

Batch / Page / TextBlock：

- Soft delete 设置 `deleted_at`，并在正常 processing / export 中隐藏 records。
- Child records 保留用于 traceability，直到永久 project cleanup。
- Associated artifacts 变为 trash-eligible，除非受 active references、retention class 或 export history 保护。

Glossary：

- Delete 改变 term status / deleted_at，并创建 GlossaryVersion。
- Old TranslationResults 保留其 glossary version。

Artifacts：

- Soft delete 可将 files 移动到 trash，并将 artifact storage state 设为 `moved_to_trash`。
- Restore 校验 path / hash，并在可行时恢复 files。
- Missing trash files 标记为 `missing`，并报告为 restore risk。

Exports：

- ExportRecord 在 output cleanup 后仍保留；linked artifact state 解释 output 是否仍 present。

## 20. Migration strategy

规则：

- 在 app.db 和每个 project.db 中维护独立 `schema_migrations`。
- app.db Project row 记录 last known project_db schema compatibility。
- Project open flow：读取 app.db、定位 project.db、验证 ProjectMetadata、锁定 project.db、运行 project-local migrations，然后启用 editing / processing。
- Migrations 应可按 Project 恢复。
- Artifact paths 相对于 Project root 存储，以支持 workspace moves。
- enum-like values 使用 stable strings，并通过新增值演进，而不是重写 audit history。
- JSON fields 在结构可演进时必须携带 schema / version markers。
- migrations 不得重写 OCR / translation result text。如果需要语义修正，创建新的 result version 或 migration note。

Backfill guidance：

- Legacy path fields 转为 ProcessingArtifact rows 加 active artifact pointers。
- Legacy active flags 如存在，迁移为 owner pointers，并将冲突记录为 QualityIssues。
- Missing glossary versions 创建 initial / unknown GlossaryVersion，并将受影响 TranslationResults 标记为 review。
- Migration 后缺失 artifact files 应变为 `storage_state = missing`，而不是删除 workflow records。

## 21. 幂等性策略

WorkflowLoopEngine 和 repositories 拥有 cache / reuse decisions。Provider Adapters 不拥有。

Stage keys：

| Stage | Key inputs |
| --- | --- |
| Import | File hash、size、normalized metadata、user-intended Page identity。跨 Projects 允许重复 filenames。 |
| Detection | Original artifact hash、provider / model / tool version、detection config hash、profile thresholds。 |
| OCR | Geometry hash、crop / input hash、provider / model / tool version、OCR config hash、source language。 |
| Page translation | Ordered active OCR result ids / hashes、reading order、context hash、glossary version / terms hash、provider / model、prompt template version、generation config hash、target language。 |
| Single-block translation | Target TextBlock id 加 full page context hash 和 active OCR / source hash。 |
| Cleaning | Base image hash、mask hash、geometry hash、cleaning provider / mode / tool version、config hash。 |
| Typesetting | Active cleaned artifact hash、active TranslationResult id / hash、geometry hash、font / layout config hash、typesetter version。 |
| Export | Active typeset artifact hashes、page order hash、export config hash、issue snapshot hash、warning export policy hash。 |

Reuse rules：

- Reuse 创建 `WorkflowAttempt.status = reused_cached` 或 `WorkflowDecision.decision_type = reuse_cached_result`。
- Reuse 仍必须 reconcile active pointers 和 stage statuses。
- Failed attempts 和 provider refusals 不是 successful cache hits，但它们计入 retry budget，并可能导致 fallback / block decisions。
- User force-rerun 创建新的 idempotency key，或显式绕过 reuse。

## 22. 场景回放

| Scenario | Replay result |
| --- | --- |
| Create Project, upload one Page, process successfully, export | Project registered in app.db；Batch / Page / TextBlock / results / artifacts / workflow records in project.db；确认无 open blocking issues 后 export succeeds。 |
| Crash after OCR before translation | Running task / attempt 变为 interrupted；OCRResult、active OCR pointer、artifacts 和 stage status 允许从 translation 继续，无需 OCR rerun。 |
| OCR edit | 新 OCRResult active pointer；translation / check / typesetting stale；page context stale；old OCR remains。 |
| Translation edit | 新 TranslationResult active pointer；typesetting stale；old translation remains。 |
| Provider refusal | Persist ToolRunLog、WorkflowAttempt、QualityIssue、WorkflowDecision，以及可用时的 failed evidence artifact；profile controls fallback / manual / block。 |
| Cleaning skip | TextBlock cleaning_status skipped；warning QualityIssue；如果 profile allows，Page can export with warnings。 |
| Typesetting overflow | Preview artifact retained；QualityIssue `typeset_overflow`；export depends on severity / profile。 |
| Glossary edit after translation | 新 GlossaryVersion；old TranslationResult keeps old version / hash；按 policy 产生 stale warnings。 |
| Failed LLM JSON | Failed raw response artifact 默认保留；attempt / log / issue / decision 解释 retry / fallback / block。 |
| Successful payload cleanup | Raw payload artifact 变为 `metadata_only_cleaned`；attempt / log / result metadata remains。 |
| Project soft delete and restore | app.db 标记 deleted / trash；project.db / files 保持可恢复；restore validates artifact states。 |
| Same filename in two Projects | 独立 workspace / project.db / project_id scope 防止冲突。 |
| Export with unresolved blocking issue | ExportRecord blocked / rejected；no normal output artifact。 |
| Warning-only export | 使用 ProcessingProfileSnapshot warning policy，并记录 warning issue snapshot。 |
| Unchanged TextBlock rerun | 复用 existing result / artifact；workflow records cache reuse 并避免重复 provider call。 |

## 23. ADR 清单

- `docs/design/data-model/adr/0001-app-db-project-db-split.md`
- `docs/design/data-model/adr/0002-active-result-pointers.md`
- `docs/design/data-model/adr/0003-artifact-metadata-lifecycle.md`
- `docs/design/data-model/adr/0004-page-translation-textblock-results.md`
- `docs/design/data-model/adr/0005-workflow-recovery-source-of-truth.md`
- `docs/design/data-model/adr/0006-processing-profile-snapshots.md`
- `docs/design/data-model/adr/0007-quality-issue-export-gate.md`
- `docs/design/data-model/adr/0008-provider-refusal-handling.md`
- `docs/design/data-model/adr/0009-soft-delete-trash.md`
- `docs/design/data-model/adr/0010-glossary-version-reproducibility.md`

## 24. 未决问题

非阻塞 open questions：

- 精确 enum spellings，以及它们由 lookup tables 还是 application constants 校验。
- 精确 ID format：UUIDv7、ULID、integer plus public id 或其他稳定方案。
- successful payloads、debug bundles、rebuildable crops 和 replaced preview artifacts 的精确 retention TTLs。
- warning export 除 profile policy 外，是否需要 per-export user acknowledgement。
- cleanup failures 在不影响 export / recovery 时，是否应创建 user-facing QualityIssues，还是只记录 maintenance-only records。
- strict / debug profile 下是否默认保留完整 GlossaryVersion snapshots。
- `WorkflowDecisionIssue` 是否从 MVP 起实现，还是 first spike 只用 structured issue snapshot artifact 即可。最终设计建议使用 relation。

已解决的 cross-review blockers：

- Active pointers 是 P0 source of truth；拒绝 independent active flags。
- Normal export 阻塞 open blocking QualityIssues；warning export 遵循 ProcessingProfileSnapshot。
- Provider refusal 作为 ToolRunLog + WorkflowAttempt + QualityIssue + WorkflowDecision 持久化。
- SRS `project_config` 映射为 Project defaults + ProcessingProfile + provider config references / snapshots。
- Artifact states 包括 `present`、`metadata_only_cleaned`、`moved_to_trash`、`missing` 和 `deleted`。
- Page-level translation partial output 为 valid blocks 创建有效 TranslationResults，并为 missing / invalid blocks 创建 QualityIssues。
- ProcessingProfile templates 位于 app.db，不可变 snapshots 位于 project.db。
- Crash recovery vocabulary 使用 `interrupted`、`recovering` 和 `abandoned_after_crash`。
- TranslationResult 链接 `source_ocr_result_id` 和 `source_text_hash`。
- TextBlock geometry fields 在 P0 保留在 TextBlock 上；`GeometryRevision` 是 P1。

## 25. 被拒绝的备选方案

| Alternative | Rejection rationale |
| --- | --- |
| Single global SQLite database | Project isolation 较弱，corruption / deletion blast radius 更大，backup / restore 更困难。 |
| Image BLOBs in SQLite | 违反强不变量，并损害 cleanup / preview 性能。 |
| Direct image paths on Page / Result as source of truth | ArtifactService 必须拥有 path / hash / retention / storage state。 |
| Mutable latest OCR / translation fields only | 违反 versioning 和 user edit traceability。 |
| Active flags on result rows | 产生重复 source of truth 和 multi-active 风险。 |
| Provider adapters write artifacts / logs / issues | 违反架构边界。 |
| Page-level TranslationResult blob | 阻塞 TextBlock-level edit / lock / retry / typeset。 |
| Workflow state reconstructed only from logs | UI / recovery / export 需要显式 current state 和 active pointers。 |
| Hard delete on user delete | 破坏 restore 和 traceability。 |
| Mutable profile references only | profile edits 后历史 decisions 无法解释。 |
| Cache translation by source text only | 忽略 context、glossary、prompt、model、config 和 language。 |

## 26. 风险与缓解

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Active pointer / status drift | Export 可能使用 stale outputs。 | Atomic updates、export-effective checks、recovery reconciliation。 |
| Artifact filesystem drift | Previews / export / recovery 可能失败。 | Artifact states、hash validation、ArtifactService-only lifecycle、missing-file repair path。 |
| Workflow table growth | 大型 projects 带 retry / debug data 时可能增长。 | Retention classes 和 successful raw payload bytes cleanup。 |
| Sensitive debug artifacts | 本地内容或 provider payload 泄露。 | Explicit flags、redaction、no secrets、debug policy warnings 和 TTLs。 |
| Page-level translation partial outputs | 有效 block translations 可能丢失，或 invalid blocks 被隐藏。 | 在一个 page attempt 下持久化 valid block results，并为 missing / invalid blocks 创建 issues。 |
| Generic target references | Referential integrity gaps。 | 存储 common scope ids，并在 repositories 中校验 target existence。 |
| Profile snapshot JSON evolution | 旧 runs 可能不可读。 | Snapshot schema version 和 compatibility readers。 |
| Soft delete / file trash drift | Restore 可能失败。 | 记录 trash path / state，restore 时校验，标记 missing 而不是删除 metadata。 |
| Over-strict glossary stale propagation | warnings 过多。 | 默认使用 used-term impact policy；strict profile 可扩大检查范围。 |

## 27. 延后到后续详细设计阶段的决策

- 精确 SQL DDL、constraints、partial indexes、ORM mappings 和 migrations。
- 精确 API schemas、DTOs、route layout 和 repository method names。
- 精确 enum taxonomies：stages、statuses、issue types、decision types、artifact types 和 error codes。
- 精确 artifact directory layout、temp file naming 和 cleanup scheduler behavior。
- 精确 fast / balanced / strict profile defaults。
- 精确 provider capability / license schema 和 OS secret store integration。
- 精确 QualityCheckService rule taxonomy 和 user-facing message catalog。
- 精确 WorkflowLoopEngine state machine 和 retry budget arithmetic。
- 精确 export manifest schema。
- 精确 P1 forced / incomplete export semantics。
- 精确 P1 GeometryRevision schema。
