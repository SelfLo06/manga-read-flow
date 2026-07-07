# Data Model Detailed Design v0.1

## 1. Design goals

This design supports the MVP local manga translation and basic typesetting workflow described by the SRS and HLD. The model is optimized for project isolation, restart recovery, partial retry, result versioning, artifact traceability, export safety, and implementation readiness with SQLite plus a local filesystem workspace.

Key decisions:

- Use `app.db` for global registry/settings and one `project.db` per Project for all Project-owned content, workflow, quality, artifact, glossary, task, and export data.
- Store image and large payload bytes on the filesystem only. SQLite stores artifact metadata.
- Keep OCR and translation results immutable and versioned.
- Use active pointer fields as the P0 source of truth for current OCR/translation and page image outputs. Do not use independent active flags.
- Persist every `WorkflowAttempt`, `WorkflowDecision`, `ToolRunLog`, `QualityIssue`, and relevant `ProcessingArtifact` needed to explain recovery and export gates.
- Keep Provider Adapters free of database access, artifact lifecycle decisions, retry/fallback/skip/block decisions, and QualityIssue creation.

## 2. Source documents

Read and synthesized:

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

Resolved source tension:

- SRS lists `project_config` as a candidate data block. Final design maps this to `Project` defaults, global provider config references, `ProcessingProfile` templates, and immutable per-task `ProcessingProfileSnapshot` records. No separate P0 `ProjectConfig` table is introduced.

## 3. app.db/project.db split

`app.db` stores global application data:

| Entity/data | Responsibility |
| --- | --- |
| `Project` | Project registry, display metadata, workspace/project.db path, default languages, default profile reference, lifecycle status, soft delete/trash metadata. |
| `ProviderConfig` | Provider identity, capability metadata, model defaults, license/capability notes, and secret references only. API keys are not stored here as raw values and are never stored in `project.db`. |
| `ProcessingProfile` | Built-in and user-editable workflow policy templates. |
| `GlobalSetting` | Workspace root, UI/application preferences, and non-secret defaults. |
| `schema_migrations` | app.db migration ledger. |

Each `project.db` stores Project-owned data:

| Entity/data | Responsibility |
| --- | --- |
| `ProjectMetadata` | Local mirror of `project_id`, project schema version, and workspace identity for integrity checks. |
| Content hierarchy | `Batch`, `Page`, `TextBlock`. |
| Result history | `OCRResult`, `TranslationResult`. |
| Glossary | `GlossaryTerm`, `GlossaryVersion`. |
| Workflow state | `ProcessingTask`, `ProcessingProfileSnapshot`, `WorkflowAttempt`, `WorkflowDecision`, `WorkflowDecisionIssue`. |
| Quality and tools | `QualityIssue`, `ToolRunLog`. |
| Files | `ProcessingArtifact`. |
| Export | `ExportRecord`, optional `ExportIssueSnapshot` or structured issue snapshot artifact. |
| `schema_migrations` | project.db migration ledger. |

Rules:

- No cross-database foreign keys.
- Same-database foreign keys are used inside `project.db` where feasible.
- `project_id` is still stored on project-owned rows as an isolation guard.
- Project open verifies `app.db.projects.project_id` matches `project.db.project_metadata.project_id`.
- Artifact paths are project-relative. `app.db` resolves the project workspace root.

## 4. Full entity list

P0 domain and workflow entities:

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

P1/P2 candidate entities:

- `GeometryRevision`
- `PageTranslationContext`
- `ExportIssueSnapshot`
- `ArtifactRetentionPolicy`
- `TermCandidate`
- `ContextPack`
- `TaskSummaryIndex`

## 5. P0 / P1 / P2 entity classification

| Priority | Entity/capability | Decision |
| --- | --- | --- |
| P0 | Project, Batch, Page, TextBlock | Required ownership spine. Page belongs to Batch; Batch belongs to Project; TextBlock belongs to Page. |
| P0 | OCRResult, TranslationResult | Immutable versioned results. User edits create new versions. |
| P0 | Active pointers | `TextBlock.active_ocr_result_id`, `TextBlock.active_translation_result_id`, `Page.original_artifact_id`, `Page.active_cleaned_artifact_id`, and `Page.active_typeset_artifact_id`. |
| P0 | GlossaryTerm, GlossaryVersion | Project-local glossary and version boundary for translation provenance. |
| P0 | ProcessingTask, WorkflowAttempt, WorkflowDecision | Durable workflow execution, retry/fallback/skip/block rationale, and recovery support. |
| P0 | QualityIssue | Discovered/root stage attribution, severity, blocking flag, status, export gate source. |
| P0 | ProcessingArtifact | Metadata for original images, masks, crops, raw payloads, cleaned/typeset/export artifacts, debug bundles. |
| P0 | ToolRunLog | Sanitized external/local tool invocation trace. |
| P0 | ExportRecord | Successful, warning, and rejected export attempt metadata. |
| P0 | ProcessingProfile and ProcessingProfileSnapshot | Mutable app-level templates plus immutable per-run policy snapshots. |
| P1 | GeometryRevision | Manual geometry history. P0 keeps geometry fields directly on TextBlock. |
| P1 | TermCandidate | Automated or quick-add glossary suggestions. |
| P1 | Export manifest detail | ZIP manifest artifact is supported by ExportRecord but detailed manifest schema is P1. |
| P1 | Cost/token rollups | Optional fields on ToolRunLog or summaries. |
| P1 | Forced/incomplete export | Advanced flow only; normal export blocks unresolved blocking issues. |
| P2 | Multi-page ContextPack | MVP uses Page-level context. |
| P2 | Advanced artifact lineage graph | Not needed for MVP recovery. |

## 6. Entity responsibility table

| Entity | Responsibility | Owns / does not own |
| --- | --- | --- |
| Project | Registry and lifecycle boundary for one manga workflow project. | Owns project discovery and workspace location in app.db. Does not own page/result rows directly. |
| ProviderConfig | Provider metadata, capability/license notes, and secret references. | Does not store raw API keys in project.db or logs. |
| ProcessingProfile | Editable template for retry budgets, quality strictness, fallback, warning export, and retention. | Does not explain historical runs after edits; snapshots do. |
| ProjectMetadata | Integrity marker inside project.db. | Verifies project.db belongs to the app registry entry. |
| Batch | Upload/processing group and Page ordering scope. | Owns Pages. Does not own glossary. |
| Page | One manga image, page order, summary state, and active page artifacts. | Owns TextBlocks and page output pointers. Original image is immutable. |
| TextBlock | Detected text region, geometry, reading order, skip/manual state, phase statuses, active OCR/translation pointers. | Owns OCRResult and TranslationResult histories. |
| OCRResult | Immutable OCR output version for one TextBlock. | Does not decide active selection; TextBlock pointer does. |
| TranslationResult | Immutable translation output version for one TextBlock from page-level context. | Links to source OCR version/hash and glossary version. |
| GlossaryTerm | Mutable current Project glossary term. | Project-scoped only. |
| GlossaryVersion | Immutable glossary state identity. | Version/hash always recorded by TranslationResult. |
| ProcessingTask | Durable user/system requested work item. | Tracks task state and selected profile snapshot. Does not store raw payloads. |
| ProcessingProfileSnapshot | Immutable serialized policy used by a task/export/attempt. | Historical source for warning export and retry decisions. |
| WorkflowAttempt | One bounded attempt for a stage/target. | Metadata always persists, even if payload artifacts are cleaned. |
| WorkflowDecision | WorkflowLoopEngine rationale for continue/retry/fallback/skip/warning/block/finish. | Links to QualityIssues through `WorkflowDecisionIssue`. |
| WorkflowDecisionIssue | Relation between decisions and issues. | Avoids issue-id lists becoming the source of truth. |
| QualityIssue | Quality/refusal/export issue with discovered/root attribution. | Export gate source. Does not itself advance workflow. |
| ProcessingArtifact | File metadata source of truth: path, hash, type, scope, retention, storage state. | ArtifactService-only registration/lifecycle. |
| ToolRunLog | Sanitized tool/provider invocation trace. | Logs metadata and artifact refs, not secrets. |
| ExportRecord | Export precheck and output history. | Records success, warning-allowed, or blocked export attempts. |

## 7. Relationship table

| Relationship | Cardinality | Notes |
| --- | --- | --- |
| Project -> Batch | 1 to many | By `project_id` inside one project.db; no cross-db FK from app.db. |
| Batch -> Page | 1 to many | `Page.page_index` unique among active Pages in a Batch. |
| Page -> TextBlock | 1 to many | Detection creates TextBlock. |
| TextBlock -> OCRResult | 1 to many | Immutable version history. |
| TextBlock -> TranslationResult | 1 to many | Immutable version history. |
| TextBlock -> active OCRResult | many to 0/1 | Pointer only. Active OCR must belong to same TextBlock. |
| TextBlock -> active TranslationResult | many to 0/1 | Pointer only. Active translation must belong to same TextBlock. |
| TranslationResult -> OCRResult | many to 1 | `source_ocr_result_id` plus `source_text_hash` are required. |
| TranslationResult -> GlossaryVersion | many to 1 | Required even for empty glossary through an initial version. |
| Page -> ProcessingArtifact | many to 0/1 per pointer | Original, active cleaned, active typeset. |
| OCRResult -> ProcessingArtifact | many to optional artifacts | Input crop and raw OCR output when retained. |
| WorkflowAttempt -> ToolRunLog | 1 to zero/many | Cache reuse attempts may have no provider call. |
| WorkflowAttempt -> ProcessingArtifact | 1 to zero/many | Raw request/response/debug/attempt artifacts. |
| WorkflowAttempt -> TranslationResult | 1 to many for page translation | One page attempt can create many TextBlock TranslationResults. |
| WorkflowDecision -> QualityIssue | many to many | Normalized by `WorkflowDecisionIssue`. |
| QualityIssue -> target | many to one polymorphic target | Always includes `project_id`; common scopes include `batch_id`, `page_id`, `text_block_id`. |
| ExportRecord -> ProcessingArtifact | many to optional output/manifest/snapshot artifacts | Blocked exports may have no output artifact. |
| ProcessingTask -> ProcessingProfileSnapshot | many to 1 | Snapshot is immutable and local to project.db. |

## 8. Key fields per entity

This is implementation-ready field grouping, not SQL DDL.

| Entity | Key field groups |
| --- | --- |
| Project | `project_id`, `name`, `workspace_project_path`, `project_db_path`, `default_source_language`, `default_target_language`, `default_processing_profile_id`, `status`, `deleted_at`, `trash_path`, timestamps. |
| ProviderConfig | `provider_config_id`, `provider_name`, `provider_type`, `capabilities`, `license_note`, `default_model_id`, `secret_ref`, `enabled`, timestamps. |
| ProcessingProfile | `profile_id`, `name`, `version`, `scope`, `is_builtin`, provider refs, retry budgets, quality strictness, fallback policy, warning export policy, retention/debug policy, timestamps. |
| ProjectMetadata | `project_id`, `project_schema_version`, `workspace_identity`, `created_at`, `last_opened_at`. |
| Batch | `batch_id`, `project_id`, `name`, `source_language`, `target_language`, `page_count`, `status`, `quality_summary`, `last_processed_at`, `deleted_at`, timestamps. |
| Page | `page_id`, `project_id`, `batch_id`, `page_index`, `original_filename`, `original_artifact_id`, `active_cleaned_artifact_id`, `active_typeset_artifact_id`, `status`, `translation_context_hash`, `translation_context_stale`, `has_stale_blocks`, `quality_flags`, `deleted_at`, timestamps. |
| TextBlock | `text_block_id`, `project_id`, `batch_id`, `page_id`, `reading_order`, bbox fields, `polygon_json`, `geometry_revision`, `geometry_hash`, `source_direction`, `detection_provider`, `detection_confidence`, `active_mask_artifact_id`, `active_ocr_result_id`, `active_translation_result_id`, `locked_translation_result_id`, stage statuses, skip/manual fields, `deleted_at`, timestamps. |
| OCRResult | `ocr_result_id`, `project_id`, `text_block_id`, `version_number`, `parent_ocr_result_id`, `source_type`, `source_text`, `source_text_hash`, confidence/quality, provider/model/tool metadata, `input_artifact_id`, `raw_output_artifact_id`, `input_hash`, `config_hash`, `geometry_hash`, `workflow_attempt_id`, `tool_run_id`, `is_user_edited`, timestamps. |
| TranslationResult | `translation_result_id`, `project_id`, `text_block_id`, `version_number`, `parent_translation_result_id`, `source_type`, `source_ocr_result_id`, `source_text_hash`, `translation_text`, `translation_text_hash`, provider/model/prompt metadata, `glossary_version_id`, `glossary_version_number`, `glossary_terms_hash`, `context_hash`, `generation_config_hash`, `page_translation_group_key`, `used_terms_json`, confidence/quality, `needs_review`, `error_code`, `workflow_attempt_id`, `tool_run_id`, `is_user_edited`, timestamps. |
| GlossaryTerm | `term_id`, `project_id`, `source_text`, `target_text`, `term_type`, `reading`, `aliases_json`, `case_sensitive`, `priority`, `status`, `created_from_text_block_id`, `created_by_user`, `note`, `deleted_at`, timestamps. |
| GlossaryVersion | `glossary_version_id`, `project_id`, `version_number`, `terms_hash`, `term_count`, optional `snapshot_artifact_id`, `created_reason`, `created_at`. |
| ProcessingTask | `task_id`, `project_id`, `target_type`, `target_id`, common scope ids, `task_type`, `requested_stages`, `resume_policy`, `status`, `current_stage`, progress summary, `profile_snapshot_id`, `idempotency_key`, pause/cancel fields, `heartbeat_at`, `started_at`, `finished_at`, timestamps. |
| ProcessingProfileSnapshot | `profile_snapshot_id`, `project_id`, `source_profile_id`, `source_profile_version`, `snapshot_schema_version`, `settings_json`, `settings_hash`, `created_at`. |
| WorkflowAttempt | `attempt_id`, `project_id`, `task_id`, common scope ids, `stage`, `target_type`, `target_id`, `attempt_number`, provider/model/tool metadata, `input_hash`, `config_hash`, `context_hash`, `profile_snapshot_id`, `profile_hash`, `status`, `error_code`, sanitized message, retry budget fields, artifact refs, timestamps. |
| WorkflowDecision | `decision_id`, `project_id`, `task_id`, `attempt_id`, common scope ids, `stage`, `target_type`, `target_id`, `decision_type`, `reason_code`, `rationale_summary`, `next_stage`, `fallback_provider`, retry budget fields, `profile_snapshot_id`, `created_at`. |
| WorkflowDecisionIssue | `decision_id`, `quality_issue_id`, `relation_type`, `created_at`. |
| QualityIssue | `quality_issue_id`, `project_id`, common scope ids, `target_type`, `target_id`, `discovered_stage`, `root_stage`, `issue_type`, `error_code`, `severity`, `is_blocking`, `status`, message/suggested action fields, related attempt/tool/artifact refs, `input_hash`, `config_hash`, `applies_to_result_id`, resolution fields, timestamps. |
| ProcessingArtifact | `artifact_id`, `project_id`, common scope ids, `owner_type`, `owner_id`, `artifact_type`, `source_stage`, `relative_path`, `file_hash`, `hash_algorithm`, `byte_size`, `mime_type`, dimensions, `workflow_attempt_id`, `tool_run_id`, `retention_class`, `storage_state`, debug/sensitive flags, cleanup fields, timestamps. |
| ToolRunLog | `tool_run_id`, `project_id`, `task_id`, `attempt_id`, common scope ids, `stage`, `tool_name`, `tool_version`, `provider_name`, `model_id`, artifact refs, `input_hash`, `config_hash`, `status`, `error_code`, `error_class`, `is_provider_refusal`, sanitized message, optional usage/cost, timings. |
| ExportRecord | `export_id`, `project_id`, `target_type`, `target_id`, common scope ids, `export_type`, `format`, `profile_snapshot_id`, `profile_hash`, `status`, precheck status, issue counts/hash, `allowed_with_warnings`, output/manifest/snapshot artifact refs, rejected reason, timestamps. |

## 9. Index and uniqueness recommendations

Recommended uniqueness:

- `Project.project_id` unique in app.db.
- Active `Project.workspace_project_path` unique in app.db.
- `Batch.batch_id` unique in project.db.
- Active `Page(batch_id, page_index)` unique.
- Active `TextBlock(page_id, reading_order)` unique when reading order is assigned.
- `OCRResult(text_block_id, version_number)` unique.
- `TranslationResult(text_block_id, version_number)` unique.
- `GlossaryVersion(project_id, version_number)` unique.
- `ProcessingProfileSnapshot(settings_hash)` may be unique per Project to reuse identical snapshots.
- `WorkflowAttempt(task_id, stage, target_type, target_id, attempt_number)` unique.
- Active artifact path `ProcessingArtifact(project_id, relative_path)` unique while storage state is `present` or `moved_to_trash`.

Recommended indexes:

- Project listing: `Project(status, updated_at)`.
- Batch progress: `Batch(project_id, status)`.
- Page order/progress: `Page(batch_id, page_index)`, `Page(batch_id, status)`.
- TextBlock recovery: `TextBlock(page_id, detection_status)`, `TextBlock(page_id, ocr_status)`, `TextBlock(page_id, translation_status)`, `TextBlock(page_id, cleaning_status)`, `TextBlock(page_id, typesetting_status)`.
- Result histories: `OCRResult(text_block_id, created_at)`, `TranslationResult(text_block_id, created_at)`.
- OCR cache: `OCRResult(text_block_id, input_hash, config_hash, provider, model_id, tool_version)`.
- Translation cache: `TranslationResult(source_text_hash, context_hash, glossary_version_id, provider, model_id, prompt_template_version, generation_config_hash)`.
- Glossary lookup: `GlossaryTerm(project_id, source_text, status)`.
- Recovery: `ProcessingTask(project_id, status, heartbeat_at)`, `WorkflowAttempt(task_id, stage, status)`.
- Export gate: `QualityIssue(project_id, is_blocking, status)`, plus scope indexes for batch/page/textblock.
- Artifact cleanup: `ProcessingArtifact(project_id, retention_class, storage_state, cleanup_eligible_at)`.
- Artifact lookup: `ProcessingArtifact(project_id, artifact_type)`, `ProcessingArtifact(file_hash, artifact_type)`.
- Tool diagnostics: `ToolRunLog(attempt_id)`, `ToolRunLog(project_id, stage, status, started_at)`.
- Export history: `ExportRecord(project_id, target_type, target_id, created_at)`.

## 10. Versioning rules

OCR:

- Every provider OCR output creates an `OCRResult` unless an existing result is reused by idempotency.
- Every user OCR edit creates a new `OCRResult` with `source_type = user_edit`.
- Existing OCR text is never overwritten.
- Invalid OCR provider output may create ToolRunLog, WorkflowAttempt, QualityIssue, WorkflowDecision, and failed artifacts without creating OCRResult.

Translation:

- Page-level translation attempts create zero or more `TranslationResult` rows, one per valid returned TextBlock output.
- Every user translation edit creates a new `TranslationResult` with `source_type = user_edit`.
- `TranslationResult.source_ocr_result_id` and `source_text_hash` are both required.
- `TranslationResult.glossary_version_id`, `glossary_version_number`, and `glossary_terms_hash` are required.
- Existing translation text is never overwritten.

Glossary:

- Any semantic create/edit/delete/status change to active glossary terms creates a new `GlossaryVersion`.
- No-op saves may reuse the existing version if the normalized `terms_hash` is unchanged.
- `snapshot_artifact_id` is optional P0 but recommended for strict/debug reproducibility.

Geometry:

- P0 stores bbox, polygon, source direction, `geometry_revision`, and `geometry_hash` on TextBlock.
- Geometry changes increment revision/hash and mark dependent stages stale.
- `GeometryRevision` is P1 when manual geometry edit history is needed.

Workflow:

- Attempts and decisions are append-only.
- Retry creates a new WorkflowAttempt and WorkflowDecision.
- Result rows are domain state; WorkflowAttempt is audit/provenance, not the result owner.

## 11. Active pointer rules

P0 active source of truth:

- `TextBlock.active_ocr_result_id`
- `TextBlock.active_translation_result_id`
- `TextBlock.locked_translation_result_id`
- `Page.original_artifact_id`
- `Page.active_cleaned_artifact_id`
- `Page.active_typeset_artifact_id`

Rules:

- No independent `is_active` flags on OCRResult or TranslationResult in P0.
- Active OCR/translation targets must belong to the same TextBlock.
- New provider results become active only after QualityCheckService output and WorkflowLoopEngine decision.
- User edits create a new result version and select it immediately.
- Locked translation is represented by `TextBlock.locked_translation_result_id`. Automatic workflow must not replace it unless user explicitly overrides.
- Active means selected for UI/downstream context. Export-effective means selected, fresh, dependency hashes match, and no unresolved blocking issue applies.
- Stale downstream state does not clear active pointers; the UI needs old selected data for review.
- Active pointer updates should commit atomically with new result creation, stale propagation, and relevant WorkflowDecision.

Rejected alternatives:

- Active flags on result rows. Rejected because they create duplicated active source of truth and multi-active conflict risk.
- Deriving active result from latest timestamp. Rejected because locked or manually selected older results are valid.

## 12. Stale propagation rules

| Trigger | Required data impact |
| --- | --- |
| OCR edit | Create OCRResult; update active OCR pointer; mark translation, translation_check, and typesetting stale; set review needs_review; set Page translation context stale and has_stale_blocks. |
| Translation edit | Create TranslationResult; update active translation pointer; mark typesetting stale; set review needs_review and Page has_stale_blocks. |
| Geometry/mask edit | Update geometry revision/hash and mask artifact; mark cleaning and typesetting stale; mark OCR stale if crop input changed. |
| Reading order edit | Mark Page translation context stale; active translations stay selected but become page-context-stale for checks. |
| Glossary edit | Create GlossaryVersion; old TranslationResults keep old version; strict profiles create warnings/needs_review for affected translations; default profile may warn only for used-term intersections. |
| Provider config/profile change | Existing results stay historical; new tasks use new profile snapshot and config hashes; applying new config to existing scope marks affected stages stale. |
| TextBlock skipped | Downstream stages become skipped; Page can become ready_for_export_with_warnings, not pure ready_for_export. |
| TextBlock unskipped | Reset relevant stages to pending or stale according to available upstream active results. |
| QualityIssue resolved | Export gate is recomputed from unresolved blocking issue query. |

Issue statuses:

- `open`: unresolved and counted by export gate.
- `resolved`: fixed by rerun, edit, user action, or explicit resolution.
- `accepted_warning`: warning accepted for export; still visible and not counted as blocking.
- `stale`: no longer applies to active inputs/results.
- `superseded`: replaced by a newer issue.

Unresolved blocking issue definition:

- `is_blocking = true`
- `status = open`
- target falls within export scope

## 13. Artifact lifecycle

ArtifactService owns path generation, safe writes, hashing, registration, retention, cleanup, trash moves, missing-file checks, and restore validation.

Provider Adapters may use temporary files but cannot write official workspace paths or register artifact records.

Required artifact states:

| State | Meaning |
| --- | --- |
| `present` | File exists at registered project-relative path. |
| `metadata_only_cleaned` | File bytes were cleaned by retention policy; metadata, hashes, provenance, and workflow refs remain. |
| `moved_to_trash` | File was moved under project/project-local trash for soft delete. |
| `missing` | File was expected but cannot be found or hash validation fails. |
| `deleted` | File was permanently deleted after confirmation or retention cleanup. |

Required retention classes:

| Class | Default |
| --- | --- |
| `permanent_original` | Keep until permanent Project/Page deletion. |
| `active_result` | Keep while referenced by active page/textblock/export pointers. |
| `failed_attempt_payload` | Keep by default. |
| `successful_payload` | Eligible for cleanup under profile policy. |
| `debug` | Retain only when debug profile/policy enables it. |
| `cache_rebuildable` | Eligible for cleanup after grace period if reconstructable. |
| `export_output` | Keep until export deletion or Project deletion. |
| `trash_pending_delete` | Moved/marked during soft delete before permanent purge. |

Safety flags:

- `is_debug`
- `may_contain_original_image`
- `may_contain_ocr_text`
- `may_contain_translation`
- `may_contain_provider_response`
- `contains_secret_redacted`

Rules:

- No image BLOBs in SQLite.
- Original images are never overwritten.
- Domain rows store artifact IDs, not authoritative paths.
- Failed raw LLM JSON responses and provider refusal evidence are retained by default.
- Successful raw request/response payloads may become `metadata_only_cleaned`.
- Cleanup must not remove active original, active cleaned, active typeset, active mask, export output, or retained failed artifacts.

## 14. WorkflowAttempt and WorkflowDecision model

`ProcessingTask` is the durable user/system command. `WorkflowAttempt` is one bounded attempt to execute a stage for a target. `WorkflowDecision` is the WorkflowLoopEngine rationale after attempt output, quality checks, retry budget, profile policy, and current state.

Stage vocabulary:

- `import`
- `detection`
- `ocr`
- `translation`
- `translation_check`
- `cleaning`
- `typesetting`
- `export`
- `artifact_cleanup`

Attempt statuses:

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

Decision types:

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

Transaction boundary guidance:

- Persist task/attempt start before external provider call.
- Do not hold write transaction during provider call.
- After provider returns, register artifacts through ArtifactService and persist ToolRunLog/attempt outcome.
- In one transaction, create result rows, create/update QualityIssues, create WorkflowDecision, update active pointers when accepted, and update stage statuses.
- If crash occurs between file write and artifact registration, recovery scans temp/attempt directories for orphan files and either registers or cleans them according to retention policy.

## 15. QualityIssue model

QualityCheckService owns issue creation, severity, blocking flag, discovered stage, root-stage attribution, and suggested action. WorkflowLoopEngine consumes issues but does not perform quality detection.

Required fields:

- target: `target_type`, `target_id`, plus common scope ids.
- attribution: `discovered_stage`, `root_stage`.
- classification: `issue_type`, `error_code`.
- severity: `info`, `warning`, `error`, `blocking`.
- gate: `is_blocking`.
- status: `open`, `resolved`, `accepted_warning`, `stale`, `superseded`.
- provenance: related attempt, tool run, artifact, result, input/config hashes.

Provider refusal:

- `ToolRunLog.status = refused` or failed with `is_provider_refusal = true`.
- `WorkflowAttempt.status = refused`.
- `QualityIssue.issue_type = provider_refusal` or a stage-specific code such as `translation_provider_refused`.
- `QualityIssue.discovered_stage = translation` for translation refusal.
- `QualityIssue.root_stage = provider_policy`.
- `WorkflowDecision` records fallback, warning, skip, manual path, or block.

Export gate:

- Normal export rejects any open blocking issue in scope.
- Warning export is allowed only when the active `ProcessingProfileSnapshot.allow_warning_export` permits it.
- Accepted warnings remain visible and are recorded on ExportRecord snapshots.

## 16. ToolRunLog model

`ToolRunLog` records each external or local tool/provider invocation:

- stage, target scope, attempt id.
- tool/provider/model identity and versions.
- input/config/context hashes.
- input/output/raw request/raw response artifact ids when retained.
- status, error_code, error_class, `is_provider_refusal`.
- sanitized error/user messages.
- timing and optional token/cost estimates.
- sanitization version.

Rules:

- No API keys, tokens, credentials, secret headers, or raw authorization values.
- Raw payloads, if retained, are ProcessingArtifacts with retention/safety flags.
- A WorkflowAttempt can have zero ToolRunLogs when cache is reused or no provider call is needed.
- A page-level translation attempt usually has one page-scoped ToolRunLog and many TranslationResults linked through the shared attempt/tool run.

## 17. Export model

Normal export flow:

1. Export use case creates or plans an `ExportRecord`.
2. ExportCheck queries unresolved blocking QualityIssues in target scope.
3. If blockers exist, `ExportRecord.status = blocked` and records blocker counts/hash/snapshot. No normal output artifact is created.
4. If only warnings exist, export proceeds only if the `ProcessingProfileSnapshot` allows warning export.
5. Successful export creates output artifacts and optional manifest artifact.

Export statuses:

- `planned`
- `succeeded`
- `blocked`
- `failed`
- `cancelled`
- `succeeded_with_warnings`

Fields:

- target scope: Page or Batch.
- export type/format.
- profile snapshot/hash.
- precheck status.
- blocking and warning issue counts.
- issue snapshot hash and optional issue snapshot artifact.
- output/manifest artifact ids.
- rejected reason.

P1 forced/incomplete export:

- Deferred to later detailed design.
- If introduced, it must never be confused with normal export and must store explicit `is_forced_export` or `is_incomplete_export` plus blocking issue summary.

## 18. ProcessingProfile model

`ProcessingProfile` templates live in app.db. Immutable execution snapshots live in project.db as `ProcessingProfileSnapshot`.

Design-level representation:

- `ProcessingProfile` app.db row: editable template with `profile_id`, `name`, `version`, provider references, retry budgets, strictness, fallback policy, warning export policy, retention policy, and debug policy.
- `ProcessingProfileSnapshot` project.db row: immutable serialized policy used by a task/export/attempt with `source_profile_id`, `source_profile_version`, `snapshot_schema_version`, `settings_json`, and `settings_hash`.

Rules:

- Task, WorkflowAttempt, WorkflowDecision, and ExportRecord reference the relevant snapshot or hash.
- Global template edits never rewrite historical workflow meaning.
- Provider secret values are not copied into snapshots. Snapshots include provider config references and sanitized provider identity only.
- Warning export decisions use the effective snapshot, not the current mutable template.

Rejected alternatives:

- Store only a mutable `profile_id` on tasks. Rejected because historical retry/export behavior would change after profile edits.
- Store a separate P0 ProjectConfig table. Rejected because SRS `project_config` is satisfied by Project defaults, profile templates, provider config references, and snapshots.

## 19. Soft delete rules

Project:

- Soft delete updates app.db Project status/deleted_at/trash_path.
- Project workspace is moved to trash or marked trash-pending after ensuring no task is running.
- project.db remains restorable before permanent deletion.
- Permanent deletion requires confirmation and removes project.db and project workspace.

Batch/Page/TextBlock:

- Soft delete sets `deleted_at` and hides records from normal processing/export.
- Child records remain for traceability until permanent project cleanup.
- Associated artifacts become trash-eligible unless protected by active references, retention class, or export history.

Glossary:

- Delete changes term status/deleted_at and creates a GlossaryVersion.
- Old TranslationResults keep their glossary version.

Artifacts:

- Soft delete may move files to trash and set artifact storage state `moved_to_trash`.
- Restore validates path/hash and returns files when possible.
- Missing trash files are marked `missing` and reported as restore risk.

Exports:

- ExportRecord remains after output cleanup; linked artifact state explains whether output is still present.

## 20. Migration strategy

Rules:

- Maintain independent `schema_migrations` in app.db and every project.db.
- app.db Project row records last known project_db schema compatibility.
- Project open flow: read app.db, locate project.db, verify ProjectMetadata, lock project.db, run project-local migrations, then enable editing/processing.
- Migrations should be resumable per Project.
- Store artifact paths relative to Project root to support workspace moves.
- Keep enum-like values as stable strings and add values rather than rewriting audit history.
- JSON fields must carry schema/version markers when structure can evolve.
- Do not rewrite OCR/translation result text during migrations. If semantic correction is needed, create a new result version or migration note.

Backfill guidance:

- Legacy path fields become ProcessingArtifact rows plus active artifact pointers.
- Legacy active flags, if any, migrate to owner pointers and record conflicts as QualityIssues.
- Missing glossary versions create an initial/unknown GlossaryVersion and mark affected TranslationResults for review.
- Missing artifact files after migration become `storage_state = missing`, not deleted workflow records.

## 21. Idempotency strategy

WorkflowLoopEngine and repositories own cache/reuse decisions. Provider Adapters do not.

Stage keys:

| Stage | Key inputs |
| --- | --- |
| Import | File hash, size, normalized metadata, user-intended Page identity. Duplicate filenames are allowed across Projects. |
| Detection | Original artifact hash, provider/model/tool version, detection config hash, profile thresholds. |
| OCR | Geometry hash, crop/input hash, provider/model/tool version, OCR config hash, source language. |
| Page translation | Ordered active OCR result ids/hashes, reading order, context hash, glossary version/terms hash, provider/model, prompt template version, generation config hash, target language. |
| Single-block translation | Target TextBlock id plus full page context hash and active OCR/source hash. |
| Cleaning | Base image hash, mask hash, geometry hash, cleaning provider/mode/tool version, config hash. |
| Typesetting | Active cleaned artifact hash, active TranslationResult id/hash, geometry hash, font/layout config hash, typesetter version. |
| Export | Active typeset artifact hashes, page order hash, export config hash, issue snapshot hash, warning export policy hash. |

Reuse rules:

- Reuse creates `WorkflowAttempt.status = reused_cached` or `WorkflowDecision.decision_type = reuse_cached_result`.
- Reuse must still reconcile active pointers and stage statuses.
- Failed attempts and provider refusals are not successful cache hits, but they count toward retry budget and may cause fallback/block decisions.
- User force-rerun creates a new idempotency key or bypasses reuse explicitly.

## 22. Scenario replay

| Scenario | Replay result |
| --- | --- |
| Create Project, upload one Page, process successfully, export | Project registered in app.db; Batch/Page/TextBlock/results/artifacts/workflow records in project.db; export succeeds after no open blocking issues are found. |
| Crash after OCR before translation | Running task/attempt become interrupted; OCRResult, active OCR pointer, artifacts, and stage status allow translation to resume without OCR rerun. |
| OCR edit | New OCRResult active pointer; translation/check/typesetting stale; page context stale; old OCR remains. |
| Translation edit | New TranslationResult active pointer; typesetting stale; old translation remains. |
| Provider refusal | Persist ToolRunLog, WorkflowAttempt, QualityIssue, WorkflowDecision, and failed evidence artifact if available; profile controls fallback/manual/block. |
| Cleaning skip | TextBlock cleaning_status skipped; warning QualityIssue; Page can export with warnings if profile allows. |
| Typesetting overflow | Preview artifact retained; QualityIssue `typeset_overflow`; export depends on severity/profile. |
| Glossary edit after translation | New GlossaryVersion; old TranslationResult keeps old version/hash; stale warnings by policy. |
| Failed LLM JSON | Failed raw response artifact retained by default; attempt/log/issue/decision explain retry/fallback/block. |
| Successful payload cleanup | Raw payload artifact becomes `metadata_only_cleaned`; attempt/log/result metadata remains. |
| Project soft delete and restore | app.db marks deleted/trash; project.db/files remain restorable; restore validates artifact states. |
| Same filename in two Projects | Separate workspace/project.db/project_id scope prevents collisions. |
| Export with unresolved blocking issue | ExportRecord blocked/rejected; no normal output artifact. |
| Warning-only export | Uses ProcessingProfileSnapshot warning policy and records warning issue snapshot. |
| Unchanged TextBlock rerun | Existing result/artifact reused; workflow records cache reuse and avoids duplicate provider call. |

## 23. ADR list

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

## 24. Open questions

Non-blocking open questions:

- Exact enum spellings and whether they are validated by lookup tables or application constants.
- Exact ID format: UUIDv7, ULID, integer plus public id, or another stable scheme.
- Exact retention TTLs for successful payloads, debug bundles, rebuildable crops, and replaced preview artifacts.
- Whether warning export requires per-export user acknowledgement in addition to profile policy.
- Whether cleanup failures should create user-facing QualityIssues or maintenance-only records when they do not affect export/recovery.
- Whether full GlossaryVersion snapshots should be retained by default in strict/debug profile.
- Whether `WorkflowDecisionIssue` should be implemented from MVP or whether a structured issue snapshot artifact is enough for the first spike. Final design recommends the relation.

Resolved cross-review blockers:

- Active pointers are the P0 source of truth; independent active flags are rejected.
- Normal export blocks open blocking QualityIssues; warning export follows ProcessingProfileSnapshot.
- Provider refusal is persisted as ToolRunLog + WorkflowAttempt + QualityIssue + WorkflowDecision.
- SRS `project_config` maps to Project defaults + ProcessingProfile + provider config references/snapshots.
- Artifact states include `present`, `metadata_only_cleaned`, `moved_to_trash`, `missing`, and `deleted`.
- Page-level translation partial output creates valid TranslationResults for valid blocks and QualityIssues for missing/invalid blocks.
- ProcessingProfile templates live in app.db and immutable snapshots live in project.db.
- Crash recovery vocabulary uses `interrupted`, `recovering`, and `abandoned_after_crash`.
- TranslationResult links to `source_ocr_result_id` and `source_text_hash`.
- TextBlock geometry fields remain on TextBlock for P0; `GeometryRevision` is P1.

## 25. Rejected alternatives

| Alternative | Rejection rationale |
| --- | --- |
| Single global SQLite database | Weaker Project isolation, larger corruption/deletion blast radius, harder backup/restore. |
| Image BLOBs in SQLite | Violates hard invariant and harms cleanup/preview performance. |
| Direct image paths on Page/Result as source of truth | ArtifactService must own path/hash/retention/storage state. |
| Mutable latest OCR/translation fields only | Violates versioning and user edit traceability. |
| Active flags on result rows | Creates duplicated source of truth and multi-active risk. |
| Provider adapters write artifacts/logs/issues | Violates architecture boundaries. |
| Page-level TranslationResult blob | Blocks TextBlock-level edit/lock/retry/typeset. |
| Workflow state reconstructed only from logs | UI/recovery/export need explicit current state and active pointers. |
| Hard delete on user delete | Breaks restore and traceability. |
| Mutable profile references only | Historical decisions become inexplicable after profile edits. |
| Cache translation by source text only | Ignores context, glossary, prompt, model, config, and language. |

## 26. Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Active pointer/status drift | Export could use stale outputs. | Atomic updates, export-effective checks, recovery reconciliation. |
| Artifact filesystem drift | Previews/export/recovery can fail. | Artifact states, hash validation, ArtifactService-only lifecycle, missing-file repair path. |
| Workflow table growth | Large projects with retries/debug data may grow. | Retention classes and cleanup of successful raw payload bytes. |
| Sensitive debug artifacts | Local content or provider payload exposure. | Explicit flags, redaction, no secrets, debug policy warnings and TTLs. |
| Page-level translation partial outputs | Valid block translations could be lost or invalid blocks hidden. | Persist valid block results and create issues for missing/invalid blocks under one page attempt. |
| Generic target references | Referential integrity gaps. | Store common scope ids and validate target existence in repositories. |
| Profile snapshot JSON evolution | Old runs may become unreadable. | Snapshot schema version and compatibility readers. |
| Soft delete/file trash drift | Restore can fail. | Record trash path/state, validate on restore, mark missing instead of deleting metadata. |
| Over-strict glossary stale propagation | Too many warnings. | Use default used-term impact policy; strict profile can widen checks. |

## 27. Decisions deferred to later detailed design stages

- Exact SQL DDL, constraints, partial indexes, ORM mappings, and migrations.
- Exact API schemas, DTOs, route layout, and repository method names.
- Exact enum taxonomies for stages, statuses, issue types, decision types, artifact types, and error codes.
- Exact artifact directory layout, temp file naming, and cleanup scheduler behavior.
- Exact profile defaults for fast/balanced/strict.
- Exact provider capability/license schema and OS secret store integration.
- Exact QualityCheckService rule taxonomy and user-facing message catalog.
- Exact WorkflowLoopEngine state machine and retry budget arithmetic.
- Exact export manifest schema.
- Exact P1 forced/incomplete export semantics.
- Exact P1 GeometryRevision schema.
