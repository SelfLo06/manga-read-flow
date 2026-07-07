## 1. Scope

This proposal covers persistence design for the data model detailed design loop, with emphasis on:

- `app.db` vs per-project `project.db` placement.
- Indexes and uniqueness constraints.
- Migration readiness and schema evolution.
- Soft delete, trash, retention, and restore behavior.
- Project isolation.
- Avoiding cross-database foreign keys.

This proposal is design-only. It does not define SQL DDL, ORM models, API handlers, migrations, provider integrations, prompts, or frontend behavior.

Primary decisions:

- Use `app.db` as the global registry and local application configuration database.
- Use one `project.db` per Project for all Project-owned workflow, glossary, result, artifact, quality, task, and export records.
- Do not use cross-database foreign keys between `app.db` and `project.db`.
- Store image and large payload bytes in the filesystem only, referenced by `ProcessingArtifact`.
- Keep workflow recovery state in `project.db`, not in volatile task memory.
- Treat soft delete as metadata state first, with filesystem trash movement coordinated by `ArtifactService`.

## 2. Role Bias

As Persistence Agent, I bias toward:

- Durable recovery over minimal table count.
- Explicit indexes and uniqueness rules over implicit application assumptions.
- Per-project isolation over globally normalized convenience.
- Migration-safe schema evolution over early schema cleverness.
- Queryable metadata over opaque JSON when the field affects recovery, filtering, export blocking, or idempotency.
- JSON metadata only for bounded, provider-specific, or fast-changing details that are not first-class workflow predicates.

This bias rejects:

- A single global database for all Project workflow data.
- Foreign keys across attached SQLite databases.
- Storing large binary images in SQLite.
- Provider-owned persistence.
- Relying only on `Page.status` for restart recovery.

## 3. Assumptions

- `docs/SRS-v1.0.md` and `docs/HLD.md` are authoritative and aligned for this scope.
- HLD storage split is accepted: `app.db` stores global data; `project.db` stores Project-owned data.
- A Project has exactly one active `project.db` path at a time, recorded by `app.db.projects`.
- A Project workspace directory contains `project.db`, original images, intermediate artifacts, exports, and trash.
- SQLite migrations are managed separately for `app.db` and each `project.db`.
- IDs are application-generated stable IDs, preferably UUID/ULID style, so records can be created without relying on cross-database integer sequences.
- Timestamps are stored in a consistent UTC representation.
- API keys and secrets live in local config or an OS secret store, not in `project.db`, `ToolRunLog`, or artifact examples.
- The MVP may use one process and one local user, but the schema should not make later worker separation impossible.

## 4. Proposed entities

| Entity | Placement | Responsibility | Persistence notes |
| --- | --- | --- | --- |
| Project | `app.db` | Global Project registry, display metadata, workspace path, soft-delete entry point. | No Project workflow data lives here. Records the path to `project.db`; does not FK into it. |
| Batch | `project.db` | Upload/processing unit inside one Project. | Belongs to exactly one Project and owns Page ordering scope. |
| Page | `project.db` | One source image page inside a Batch. | References original, cleaned, typeset, and export artifacts by artifact IDs or active pointers. |
| TextBlock | `project.db` | Detected text region and per-stage state anchor. | Stores geometry, reading order, skip flags, active OCR/translation pointers, and stage statuses. |
| OCRResult | `project.db` | Immutable OCR output version for one TextBlock. | User OCR edits create new versions. Never overwrite old source text. |
| TranslationResult | `project.db` | Immutable translation output version for one TextBlock. | Records source hash, context hash, prompt/config identifiers, and glossary version. |
| GlossaryTerm | `project.db` | Project-local glossary entry. | Soft-delete or inactive status preferred over physical delete during normal use. |
| GlossaryVersion | `project.db` | Snapshot identity for a glossary state. | Used by TranslationResult for historical traceability. |
| ProcessingTask | `project.db` | Durable background task state for WorkflowService/TaskRunner. | Restart recovery reads this plus granular stage state. |
| WorkflowAttempt | `project.db` | One bounded attempt of a stage/action in the Workflow Loop. | Metadata always persisted, even when payload artifacts are cleaned. |
| WorkflowDecision | `project.db` | WorkflowLoopEngine decision record and rationale. | Persisted after quality checks and attempt outcomes. |
| QualityIssue | `project.db` | Quality finding with discovered/root stage attribution. | Export checks unresolved blocking issues from here. |
| ProcessingArtifact | `project.db` | Metadata for filesystem artifacts. | Records path, hash, type, ownership, retention, and cleanup state. |
| ToolRunLog | `project.db` | External tool/provider run log. | Sanitized; no secrets; linked to attempts and artifacts where applicable. |
| ExportRecord | `project.db` | Export operation and output metadata. | Records export eligibility, warnings/blockers snapshot, and output artifacts. |
| ProcessingProfile | `app.db` and optional project copy in `project.db` | Workflow policy template and per-run policy snapshot. | Global definitions live in `app.db`; immutable task snapshot or project override lives in `project.db`. |

Decision:

- Put all required entities except global `Project` and global `ProcessingProfile` definitions in `project.db`.

Rationale:

- Project data must be isolated and restorable independently.
- Restart recovery requires Page/TextBlock/result/task/attempt/artifact state to be in the same local database.
- SQLite cannot enforce reliable foreign keys across separate database files, so cross-file relationships should be represented by stable IDs and verified by repository code.

Rejected alternatives:

- Store Batch/Page/TextBlock globally in `app.db`: easier cross-project search, but violates isolation and makes backup/delete/migration blast radius larger.
- Store ProcessingTask in `app.db`: central queue is tempting, but restart recovery then needs cross-database joins or duplicated state. MVP can query open project databases as needed.
- Store ProcessingProfile only in `project.db`: supports portability but makes global defaults and profile management awkward. The proposed split keeps both global templates and immutable per-run snapshots.

## 5. P0 / P1 / P2 classification

| Entity or capability | Priority | Persistence stance |
| --- | --- | --- |
| Project | P0 | Required in `app.db` before any processing. |
| Batch | P0 | Required in `project.db`; even a one-page MVP uses a Batch. |
| Page | P0 | Required in `project.db`; original image artifact must be recorded. |
| TextBlock | P0 | Required in `project.db`; detection creates it. |
| OCRResult | P0 | Versioned, immutable, active pointer required. |
| TranslationResult | P0 | Versioned, immutable, active pointer required. |
| GlossaryTerm | P0 | Project-local glossary terms. |
| GlossaryVersion | P0 | Required for translation traceability. |
| ProcessingTask | P0 | Required for async processing and restart recovery. |
| WorkflowAttempt | P0 | Attempt metadata always persisted. |
| WorkflowDecision | P0 | Required to explain retry/fallback/skip/block decisions. |
| QualityIssue | P0 | Required for warnings, blocking export, and root attribution. |
| ProcessingArtifact | P0 | Required for original images, masks, results, exports, failed attempts. |
| ToolRunLog | P0 | Required for external tool traceability. |
| ExportRecord | P0 | Required for export traceability and later edits after export. |
| ProcessingProfile | P0 | Required as selected policy/snapshot for one-click workflow. |
| Manual TextBlock coordinate editing | P1 | Existing TextBlock fields support it; new versions of geometry may be P1. |
| Cost/token accounting detail | P1 | Can extend ToolRunLog or add structured counters. |
| Export manifest detail | P1 | ExportRecord can link an optional manifest artifact. |
| Multi-page translation context | P2 | TranslationResult context hash can evolve without changing ownership. |
| Advanced profile variants and provider UI | P2 | Store as profile metadata and per-task snapshots. |

Decision:

- Model every listed entity as P0-capable even if some fields remain hidden in MVP UI.

Rationale:

- The HLD requires one-click processing, quality gates, recovery, and export blocking in the first end-to-end loop.
- Omitting attempts, decisions, artifacts, or quality issues would make recovery and diagnostics unverifiable.

Rejected alternative:

- Make WorkflowDecision or ToolRunLog P1 to simplify MVP. Rejected because provider refusal, invalid JSON, retry exhaustion, and export blocking must be explainable in P0.

## 6. app.db vs project.db placement

### `app.db`

`app.db` stores global and application-level records:

- `projects`: Project registry, display name, workspace/project_db path, default language metadata for listing, lifecycle status, soft-delete marker, last opened/processed timestamps.
- `global_settings`: workspace root, UI preferences, non-secret defaults.
- `provider_configs`: provider identity, base URL aliases, model defaults, capability metadata, secret reference names only.
- `processing_profiles`: global profile templates such as fast, balanced, strict.
- `recent_projects`: optional navigation convenience, referencing `projects.project_id`.
- `schema_migrations`: app database migration ledger.

`app.db` must not store:

- Page/TextBlock/OCR/translation workflow state.
- Glossary terms for a Project.
- Artifact file metadata for Project artifacts.
- API keys or raw provider payloads.

### `project.db`

Each `project.db` stores Project-owned records:

- `project_metadata`: local copy of `project_id`, schema version, display name snapshot, project settings snapshot, and workspace identity.
- `batches`, `pages`, `text_blocks`.
- `ocr_results`, `translation_results`.
- `glossary_terms`, `glossary_versions`.
- `processing_tasks`.
- `workflow_attempts`, `workflow_decisions`.
- `quality_issues`.
- `processing_artifacts`.
- `tool_run_logs`.
- `export_records`.
- `processing_profile_snapshots` or task-level profile snapshot fields.
- `schema_migrations`.

Decision:

- Duplicate `project_id` on Project-owned rows inside `project.db`, even though each `project.db` represents one Project.

Rationale:

- It gives every row an isolation guard.
- It simplifies artifact path validation and logs.
- It makes accidental cross-project imports detectable.
- It helps future export/import, support bundles, and project database moves.

Rejected alternatives:

- Omit `project_id` from `project.db` tables because the file already scopes the data. Rejected because it weakens integrity checks and traceability.
- Attach all project databases and use cross-database joins. Rejected because it complicates migrations, locking, and foreign key semantics.

### Avoiding cross-database foreign keys

Rules:

- `app.db.projects.project_id` identifies the Project globally.
- `project.db.project_metadata.project_id` must equal the app registry value when opened.
- `project.db` tables may FK to other tables in the same `project.db`.
- `app.db` must not FK into `project.db`.
- `project.db` must not FK into `app.db`.
- References to global ProcessingProfile templates are copied into immutable snapshots for tasks and attempts.

Validation:

- On Project open, repository code verifies `app.db.projects.project_id`, `project_db_path`, and `project.db.project_metadata.project_id`.
- If mismatched, open is blocked and surfaced as a recoverable configuration/data integrity error.

## 7. Key fields

This section names implementation-ready fields without defining DDL.

### Project

Key fields:

- `project_id`
- `name`
- `workspace_project_path`
- `project_db_path`
- `default_source_language`
- `default_target_language`
- `status`
- `soft_deleted_at`
- `trash_path`
- `created_at`, `updated_at`, `last_opened_at`, `last_processed_at`

Indexes and constraints:

- Unique `project_id`.
- Unique normalized `workspace_project_path`.
- Index `status, updated_at`.
- Index `soft_deleted_at` for trash cleanup.

### Batch

Key fields:

- `batch_id`, `project_id`
- `name`
- `source_language`, `target_language`
- `status`
- `page_count`
- `processing_profile_snapshot_id`
- `created_at`, `updated_at`, `last_processed_at`
- `soft_deleted_at`

Indexes and constraints:

- Unique `batch_id`.
- Unique active batch name per Project if the UI requires human-readable uniqueness.
- Index `project_id, status`.
- Index `project_id, soft_deleted_at`.

### Page

Key fields:

- `page_id`, `project_id`, `batch_id`
- `page_index`
- `original_artifact_id`
- `active_cleaned_artifact_id`
- `active_typeset_artifact_id`
- `active_export_artifact_id`
- `status`
- `quality_flags`
- `translation_context_hash`
- `translation_context_stale`
- `has_stale_blocks`
- `error_code`, `error_message`
- `created_at`, `updated_at`, `soft_deleted_at`

Indexes and constraints:

- Unique `page_id`.
- Unique active `batch_id, page_index`.
- Index `batch_id, status`.
- Index `project_id, status`.
- Index `project_id, original_artifact_id`.

### TextBlock

Key fields:

- `text_block_id`, `project_id`, `batch_id`, `page_id`
- `reading_order`
- `bbox_x`, `bbox_y`, `bbox_width`, `bbox_height`
- `polygon_json`
- `source_direction`
- `detection_provider`, `detection_confidence`
- `mask_artifact_id`
- `active_ocr_result_id`
- `active_translation_result_id`
- `detection_status`, `ocr_status`, `translation_status`, `translation_check_status`, `cleaning_status`, `typesetting_status`, `review_status`
- `is_skipped`, `skip_reason`
- `is_manual_adjusted`
- `created_at`, `updated_at`, `soft_deleted_at`

Indexes and constraints:

- Unique `text_block_id`.
- Unique active `page_id, reading_order`.
- Index `page_id, is_skipped`.
- Index `page_id` plus stage statuses for recovery queries.
- Index `active_ocr_result_id` and `active_translation_result_id`.

### OCRResult

Key fields:

- `ocr_result_id`, `project_id`, `text_block_id`
- `version_number`
- `source_text`
- `source_text_hash`
- `ocr_confidence`
- `ocr_quality_flag`
- `provider`, `model_id`, `tool_version`
- `input_artifact_id`, `raw_output_artifact_id`
- `input_hash`, `config_hash`
- `tool_run_id`, `workflow_attempt_id`
- `is_user_edited`
- `created_at`, `created_by`

Indexes and constraints:

- Unique `ocr_result_id`.
- Unique `text_block_id, version_number`.
- Optional unique idempotency key for non-manual OCR: `text_block_id, input_hash, config_hash, provider, model_id, tool_version`.
- Index `text_block_id, created_at`.
- Index `source_text_hash`.

### TranslationResult

Key fields:

- `translation_result_id`, `project_id`, `text_block_id`
- `version_number`
- `source_ocr_result_id`
- `source_text_hash`
- `translation_text`
- `translation_text_hash`
- `provider`, `model_id`
- `prompt_template_version`
- `glossary_version_id`
- `glossary_version_number`
- `context_hash`
- `generation_config_hash`
- `used_terms_json`
- `confidence`
- `needs_review`
- `quality_flags`
- `error_code`
- `tool_run_id`, `workflow_attempt_id`
- `is_user_edited`
- `is_locked`
- `created_at`, `created_by`

Indexes and constraints:

- Unique `translation_result_id`.
- Unique `text_block_id, version_number`.
- Optional unique idempotency key for non-manual translation: `text_block_id, source_text_hash, context_hash, glossary_version_id, provider, model_id, prompt_template_version, generation_config_hash`.
- Index `glossary_version_id`.
- Index `text_block_id, is_locked`.

### GlossaryTerm

Key fields:

- `term_id`, `project_id`
- `source_text`, `target_text`
- `term_type`
- `reading`
- `aliases_json`
- `case_sensitive`
- `priority`
- `status`
- `created_from_text_block_id`
- `created_by_user`
- `note`
- `created_at`, `updated_at`, `soft_deleted_at`

Indexes and constraints:

- Unique `term_id`.
- Unique active normalized `project_id, source_text, target_text, term_type` or stricter `project_id, source_text` depending final UX.
- Index `project_id, status, priority`.
- Index `created_from_text_block_id`.

### GlossaryVersion

Key fields:

- `glossary_version_id`, `project_id`
- `version_number`
- `terms_hash`
- `term_count`
- `created_reason`
- `created_at`
- Optional `based_on_version_id`

Indexes and constraints:

- Unique `glossary_version_id`.
- Unique `project_id, version_number`.
- Unique `project_id, terms_hash` if unchanged glossary states should reuse a version.
- Index `project_id, created_at`.

### ProcessingTask

Key fields:

- `task_id`, `project_id`
- `task_type`
- `target_type`, `target_id`
- `batch_id`, `page_id`, `text_block_id` when scoped
- `status`
- `requested_action`
- `processing_profile_snapshot_id`
- `current_stage`
- `progress_json`
- `cancel_requested_at`, `pause_requested_at`
- `started_at`, `finished_at`, `created_at`, `updated_at`
- `error_code`, `error_message`
- `idempotency_key`

Indexes and constraints:

- Unique `task_id`.
- Unique active `idempotency_key` for duplicate task suppression.
- Index `status, updated_at`.
- Index `target_type, target_id, status`.
- Index `project_id, status`.

### WorkflowAttempt

Key fields:

- `attempt_id`, `project_id`
- `task_id`
- `stage`
- `target_type`, `target_id`
- `attempt_number`
- `provider`, `model_id`, `tool_version`
- `input_hash`, `config_hash`
- `status`
- `error_code`, `error_message`
- `started_at`, `finished_at`
- `payload_artifact_id`
- `is_payload_retained`
- `retry_budget_snapshot_json`

Indexes and constraints:

- Unique `attempt_id`.
- Unique `task_id, stage, target_type, target_id, attempt_number`.
- Index `task_id, stage, status`.
- Index `target_type, target_id, stage`.

### WorkflowDecision

Key fields:

- `decision_id`, `project_id`
- `task_id`
- `attempt_id`
- `stage`
- `target_type`, `target_id`
- `decision_type`
- `rationale_code`
- `rationale_summary`
- `quality_issue_ids_json`
- `next_stage`
- `created_at`

Indexes and constraints:

- Unique `decision_id`.
- Index `task_id, created_at`.
- Index `attempt_id`.
- Index `target_type, target_id, stage`.

### QualityIssue

Key fields:

- `quality_issue_id`, `project_id`
- `batch_id`, `page_id`, `text_block_id`
- `target_type`, `target_id`
- `discovered_stage`
- `root_stage`
- `issue_type`
- `severity`
- `is_blocking`
- `status`
- `message`
- `suggested_action`
- `source_attempt_id`
- `source_tool_run_id`
- `created_at`, `resolved_at`
- `resolution_reason`

Indexes and constraints:

- Unique `quality_issue_id`.
- Index `target_type, target_id, status`.
- Index `project_id, is_blocking, status`.
- Index `page_id, severity, status`.
- Optional dedupe key for active issues: `target_type, target_id, issue_type, root_stage, discovered_stage, status`.

### ProcessingArtifact

Key fields:

- `artifact_id`, `project_id`
- `batch_id`, `page_id`, `text_block_id`
- `owner_type`, `owner_id`
- `artifact_type`
- `source_step`
- `file_path`
- `file_hash`
- `mime_type`
- `byte_size`
- `width`, `height`
- `tool_run_id`, `workflow_attempt_id`
- `retention_class`
- `is_debug`
- `is_original`
- `is_deleted`, `deleted_at`
- `cleanup_eligible_at`
- `created_at`

Indexes and constraints:

- Unique `artifact_id`.
- Unique active normalized `project_id, file_path`.
- Index `owner_type, owner_id, artifact_type`.
- Index `project_id, artifact_type`.
- Index `file_hash` for dedupe/reuse checks.
- Index `retention_class, cleanup_eligible_at`.

### ToolRunLog

Key fields:

- `tool_run_id`, `project_id`
- `task_id`, `attempt_id`
- `batch_id`, `page_id`, `text_block_id`
- `stage`
- `tool_name`, `tool_version`, `model_id`
- `input_artifact_id`, `output_artifact_id`
- `input_hash`, `config_hash`
- `status`
- `error_code`, `error_message`
- `started_at`, `finished_at`
- `cost_units_json`
- `sanitization_version`

Indexes and constraints:

- Unique `tool_run_id`.
- Index `attempt_id`.
- Index `stage, status, started_at`.
- Index `target scope fields` for UI trace pages.

### ExportRecord

Key fields:

- `export_id`, `project_id`
- `batch_id`, optional `page_id`
- `export_type`
- `status`
- `profile_policy_snapshot_json`
- `blocking_issue_count`
- `warning_issue_count`
- `was_forced`
- `manifest_artifact_id`
- `output_artifact_id`
- `started_at`, `finished_at`, `created_at`
- `error_code`, `error_message`

Indexes and constraints:

- Unique `export_id`.
- Index `batch_id, created_at`.
- Index `page_id, created_at`.
- Index `status`.

### ProcessingProfile

Key fields in `app.db` global templates:

- `profile_id`
- `name`
- `profile_type`
- `is_builtin`
- `version_number`
- `settings_json`
- `created_at`, `updated_at`
- `soft_deleted_at`

Key fields in `project.db` snapshots:

- `profile_snapshot_id`
- `source_profile_id`
- `source_profile_version`
- `name`
- `settings_json`
- `settings_hash`
- `created_at`

Indexes and constraints:

- Unique `profile_id` in `app.db`.
- Unique active global `name`.
- Unique `profile_snapshot_id` in `project.db`.
- Unique `settings_hash` may allow snapshot reuse.

## 8. Relationships

Relationship summary:

- `Project` has many `Batch`, but the relationship is by matching `project_id` and project database ownership, not by cross-db FK.
- `Batch` has many `Page`.
- `Page` has many `TextBlock`.
- `TextBlock` has many `OCRResult`.
- `TextBlock` has many `TranslationResult`.
- `TextBlock` points to one active `OCRResult`.
- `TextBlock` points to one active `TranslationResult`.
- `GlossaryTerm` belongs to one Project.
- `GlossaryVersion` belongs to one Project.
- `TranslationResult` references one `GlossaryVersion`.
- `ProcessingTask` targets a Batch, Page, or TextBlock.
- `WorkflowAttempt` belongs to one `ProcessingTask` and targets a Batch, Page, or TextBlock.
- `WorkflowDecision` belongs to a task and usually to an attempt.
- `QualityIssue` targets a Batch, Page, TextBlock, Export, or Task scope.
- `ProcessingArtifact` may be owned by Project, Batch, Page, TextBlock, Result, Attempt, ToolRun, or Export scope.
- `ToolRunLog` may link to a task, attempt, target scope, and input/output artifacts.
- `ExportRecord` belongs to a Batch or Page and links output artifacts.
- `ProcessingProfile` global template may produce project-local immutable snapshots for tasks and attempts.

Decision:

- Use same-database FKs inside `project.db` for core hierarchy and artifact/result links where feasible.
- Use polymorphic `target_type, target_id` for workflow/quality entities that can apply to multiple scopes.
- Keep redundant scope columns such as `batch_id`, `page_id`, and `text_block_id` on high-volume operational tables to avoid expensive joins and simplify filtering.

Rationale:

- TextBlock-level failures and retries are common. UI and recovery queries need fast filtering by Page and stage.
- QualityIssue and WorkflowDecision need to explain Page-level and TextBlock-level behavior without forcing separate tables per target type.

Rejected alternatives:

- Fully normalize all scope through target polymorphism only. Rejected because common progress and quality queries would need repeated target resolution.
- Create separate attempt/issue tables for each target type. Rejected as over-designed for MVP and harder to migrate.

## 9. Versioning rules

OCRResult:

- OCRResult is immutable after creation except for non-semantic metadata such as retention flags if needed.
- User edits create a new OCRResult with `is_user_edited = true`.
- Re-running OCR creates a new OCRResult unless an idempotent existing result is reused.
- `version_number` is monotonic per TextBlock.

TranslationResult:

- TranslationResult is immutable after creation except for non-semantic metadata such as retention flags if needed.
- User edits create a new TranslationResult with `is_user_edited = true`.
- Re-translation creates a new TranslationResult unless an idempotent existing result is reused.
- `version_number` is monotonic per TextBlock.
- Each TranslationResult records the active OCR source hash and glossary version used at creation.

GlossaryVersion:

- Glossary changes create a new GlossaryVersion when the active term set changes.
- `terms_hash` represents the normalized active glossary state.
- TranslationResult keeps the old GlossaryVersion reference even after glossary changes.

ProcessingProfile:

- Global profile edits do not mutate historical task policy.
- A task uses an immutable profile snapshot with settings hash.

Decision:

- Use immutable result records plus active pointers, not in-place result mutation.

Rationale:

- This satisfies manual-edit traceability, restart recovery, and stale downstream detection.

Rejected alternative:

- Store only latest OCR/translation text on TextBlock. Rejected because it loses history and cannot explain downstream stale results.

## 10. Active pointer rules

Active OCR:

- `TextBlock.active_ocr_result_id` selects the current effective OCRResult.
- Exactly one active OCR is selected per non-skipped TextBlock when OCR is done.
- If OCR fails and no manual source exists, active OCR may be null and OCR status remains failed or needs_review.

Active Translation:

- `TextBlock.active_translation_result_id` selects the current effective TranslationResult.
- Locked translations remain active until the user explicitly unlocks or replaces them.
- Automatic translation must not overwrite a locked active translation.

Active image artifacts:

- `Page.original_artifact_id` is set once and never replaced during normal processing.
- `Page.active_cleaned_artifact_id` points to the current cleaned image for preview and downstream typesetting.
- `Page.active_typeset_artifact_id` points to the current typeset preview/export candidate.
- `Page.active_export_artifact_id` points to the latest exported single-page artifact when applicable.

Decision:

- Prefer explicit pointer fields over `is_active` flags for active OCR/translation selection.

Rationale:

- Pointers make it impossible for two versions to be simultaneously active if database constraints are correct.
- They simplify reads for preview and downstream stages.

Rejected alternatives:

- Use only `is_active` flags on result rows. Rejected because it requires partial unique constraints and is easier to corrupt during concurrent updates.
- Derive active result from latest timestamp. Rejected because locked/manual/user-selected versions may not be the newest.

## 11. State and stale rules

State storage:

- Batch and Page have aggregate status fields for UI and coarse workflow progress.
- TextBlock stores separate stage statuses: detection, OCR, translation, translation check, cleaning, typesetting, review.
- ProcessingTask stores task-level execution state.
- WorkflowAttempt and WorkflowDecision store the detailed history behind state changes.
- QualityIssue stores unresolved warnings/errors/blockers that affect export.

Stale rules:

- OCR edit creates a new active OCRResult and sets translation, translation check, and typesetting state to `stale` for the TextBlock.
- OCR edit sets Page `translation_context_stale = true` and `has_stale_blocks = true`.
- Translation edit creates a new active TranslationResult and sets typesetting state to `stale` for the TextBlock.
- TextBlock geometry edit sets cleaning and typesetting state to `stale`.
- Glossary edit creates a new GlossaryVersion but does not automatically mutate old TranslationResult records.
- Reprocessing clears stale flags only for the target scope whose downstream outputs were regenerated or explicitly accepted.

Export rules:

- Normal export checks unresolved blocking QualityIssues.
- Warning export is allowed only if the effective ProcessingProfile policy allows it.
- Skipped TextBlocks create warnings, not automatic failures.

Decision:

- Recovery must read TextBlock stage status, active pointers, attempts, decisions, artifacts, and issues. It must not rely only on Page status.

Rationale:

- SRS requires partial failure isolation and avoiding repeated calls.

Rejected alternative:

- Model workflow as one Page status enum. Rejected because TextBlock-level retry and stale detection would be lossy.

## 12. Artifact relationships

Artifact ownership:

- Original image artifacts are owned by Page scope and flagged `is_original = true`.
- Detection visualizations, crops, masks, OCR raw outputs, translation raw payloads, cleaned images, typeset images, quality reports, and exports are all `ProcessingArtifact` records.
- Artifacts should record owner scope plus narrower nullable scope fields where applicable.
- Artifacts link to `ToolRunLog` and/or `WorkflowAttempt` when generated by processing.

Required artifact behavior:

- No image BLOBs in SQLite.
- Original images are immutable and never overwritten.
- Failed attempt payload artifacts are retained by default.
- Successful large raw payload artifacts are retention-policy eligible.
- Debug artifacts are explicitly marked because they may contain sensitive local content, OCR text, translations, and provider responses.
- Artifact file paths are project-relative when practical; absolute paths may be derived from validated workspace root.

Decision:

- `ProcessingArtifact` is the only durable registry for filesystem files used by workflow state.

Rationale:

- This centralizes hash, retention, cleanup, debug marking, and ownership.

Rejected alternatives:

- Store image paths directly on Page without artifact records. Rejected because it breaks retention and traceability.
- Let provider adapters write final artifact files. Rejected because ArtifactService owns lifecycle and path safety.

## 13. Idempotency and cache keys

Idempotency is enforced by WorkflowService/WorkflowLoopEngine using repository lookups and artifact hashes. Provider adapters do not decide cache reuse.

OCR cache key:

- `text_block_id`
- input crop or source artifact hash
- normalized bbox/polygon/mask hash when relevant
- provider
- model_id
- tool_version
- config_hash

Translation cache key:

- `source_text_hash`
- `context_hash`
- `glossary_version_id` or version number plus terms hash
- provider
- model_id
- prompt_template_version
- generation_config_hash
- target TextBlock identity for page-level output matching

Cleaning cache key:

- source image artifact hash
- TextBlock geometry/mask hash
- cleaning mode/provider
- config_hash
- tool_version

Typesetting cache key:

- cleaned image artifact hash
- active TranslationResult ID or translation text hash
- TextBlock geometry hash
- font/config hash
- typesetter version

ProcessingTask idempotency key:

- target scope
- requested action
- effective ProcessingProfile snapshot hash
- relevant active input hashes

Decision:

- Store cache inputs as explicit hash fields on result, attempt, tool run, or artifact records rather than only in JSON.

Rationale:

- Recovery and duplicate-call prevention must be queryable.

Rejected alternative:

- Cache solely by provider raw request JSON hash. Rejected because provider payload shape may change while semantic inputs remain the same, and it can include sensitive data.

## 14. Deletion and retention policy

Soft delete:

- Project soft delete is initiated in `app.db.projects` with `soft_deleted_at` and status such as `trashed`.
- Project workspace is moved to a trash path or marked for trash by ArtifactService.
- `project.db` remains intact during restore window.
- Restore clears trash metadata and restores workspace path mapping.
- Permanent deletion requires confirmation and removes the Project registry row plus workspace files.

Batch/Page/TextBlock delete:

- Prefer soft delete for Batch/Page/TextBlock during normal use.
- Deleted items are hidden from normal workflow queries but remain available for recovery until permanent cleanup.
- Child records are not immediately physically deleted; they remain linked for traceability.

Artifact retention:

- Original images: retain until permanent Project deletion.
- Active cleaned/typeset/export artifacts: retain while referenced.
- Failed attempt artifacts: retain by default.
- Successful large raw payload artifacts: cleanup eligible under profile/global policy.
- Debug artifacts: retain only when debug policy requires it and mark clearly.
- Cleanup marks artifact metadata before or during file deletion; missing-file validation should report stale artifact state.

ExportRecord retention:

- Export records remain after export so later edits do not erase export history.
- Export output artifacts can be deleted by user action or retention policy, but the record should show artifact cleanup state.

Decision:

- Treat delete as a workflow-visible lifecycle state, not an immediate cascade.

Rationale:

- The product requires restore, recovery, and traceability.

Rejected alternatives:

- Immediate cascade delete for Project/Batches. Rejected because accidental deletion would be hard to recover and attempts/artifacts would lose explanatory value.
- Never delete artifacts. Rejected because LLM payloads and debug artifacts can be large and sensitive.

## 15. Migration concerns

Migration model:

- Maintain separate migration ledgers for `app.db` and each `project.db`.
- Migrations are idempotent and ordered.
- Project open should check project database schema version before use.
- Back up or checkpoint `project.db` before destructive or large migrations.
- Migrations must be able to run on many Project databases over time, including Projects not opened recently.

Schema evolution guidelines:

- Add nullable fields or new tables before making fields required.
- Backfill in explicit migration steps.
- Avoid renaming or removing fields until a compatibility window is defined.
- Keep enum-like values as controlled strings with validation at application boundaries.
- For JSON fields, include a schema/version marker when the structure may evolve.
- Do not bake provider-specific payload schemas into core result tables.

Indexes:

- Add indexes for recovery queries early: task status, stage statuses, unresolved blocking issues, artifact retention, active pages.
- Reassess write cost after MVP sample runs.
- Avoid indexes on highly variable large JSON fields.

Cross-db migrations:

- `app.db` migrations must not assume a Project database is attached.
- `project.db` migrations must not require global profile rows to exist.
- If a global profile changes shape, Project task snapshots keep their old schema version and are interpreted by compatibility code.

Decision:

- Version `app.db` and `project.db` independently.

Rationale:

- Projects may be archived, moved, restored, or opened after the app has advanced several versions.

Rejected alternative:

- One global migration version for all databases. Rejected because it makes partially migrated Project databases difficult to reason about.

## 16. Risks

- Redundant `project_id`, `batch_id`, and `page_id` fields can drift if repository code is careless.
- Polymorphic target references cannot be fully FK-enforced in SQLite without more tables.
- Explicit active pointers require careful transactional updates when creating new versions.
- Per-project databases complicate global dashboards and cross-project search.
- Artifact metadata can drift from filesystem state if file moves/deletes are not centralized through ArtifactService.
- JSON fields such as profile snapshots and used terms can become opaque if not versioned.
- Soft delete and retention policies can leave more data on disk than users expect unless UI wording is clear.
- Separate `app.db` and `project.db` migrations increase test matrix size.
- Page-level translation stores per-TextBlock results, so failed partial page outputs need precise attempt/result association.

Mitigations:

- Repository methods should validate scope consistency on write.
- Active pointer updates should occur in one transaction with result creation and stale-state changes.
- ArtifactService should be the only path for registering, moving, retaining, or deleting artifacts.
- Migration tests should include old project database fixtures.
- Periodic integrity checks should compare artifact records with filesystem existence and hashes.

## 17. Rejected alternatives

1. Single global SQLite database for all data.
   - Rationale for rejection: simpler queries, but weaker Project isolation, harder Project backup/delete/restore, larger corruption blast radius.

2. Cross-database foreign keys using attached SQLite databases.
   - Rationale for rejection: SQLite FK behavior is not a good foundation for cross-file integrity; repository-level verification is clearer.

3. Store original or generated images as BLOBs in SQLite.
   - Rationale for rejection: violates invariants and makes backup, preview, retention, and cleanup worse.

4. Store only latest OCR and translation text.
   - Rationale for rejection: violates versioning and user-edit requirements.

5. Use `is_active` flags only for current OCR/translation.
   - Rationale for rejection: easier to create multiple active rows; pointers are clearer for reads.

6. Put ProcessingTask in `app.db`.
   - Rationale for rejection: creates cross-db recovery dependencies. Project recovery should be possible from the Project workspace.

7. Let provider adapters persist artifacts or logs.
   - Rationale for rejection: violates HLD separation. Providers return outputs; ArtifactService and Repository persist them.

8. Physically delete child data immediately on user delete.
   - Rationale for rejection: conflicts with restore, traceability, and accidental delete recovery.

9. Keep all profile policy mutable by reference.
   - Rationale for rejection: historical WorkflowDecisions would become hard to explain after profile edits.

## 18. Decisions intentionally left to later rounds

- Exact ID format: UUID v4, UUID v7, ULID, or another sortable stable ID.
- Exact enum value sets for every status, issue type, artifact type, and retention class.
- Whether GlossaryTerm uniqueness is by source text only or by source text plus target/type.
- Whether TextBlock geometry versions deserve a separate versioned entity in P1.
- Whether page-level translation attempts should create a parent Page translation aggregate record in addition to per-TextBlock TranslationResult records.
- Exact retention duration defaults for successful raw payloads and debug artifacts.
- Exact migration tooling details and naming convention.
- Exact shape of `settings_json`, `progress_json`, and profile snapshots.
- Exact strategy for opening many project databases in a future global task dashboard.
- Exact integrity-check command/report format.

## 19. Validation against all scenarios in HARNESS.md

| Scenario | Validation |
| --- | --- |
| S1: Happy path | PASS. Project is registered in `app.db`; Batch, Page, TextBlocks, OCRResults, TranslationResults, Cleaning/Typesetting artifacts, QualityIssues, WorkflowAttempts, WorkflowDecisions, ToolRunLogs, and ExportRecord are all persisted in `project.db`. Original image remains immutable as a ProcessingArtifact. Export checks unresolved blocking issues. |
| S2: Restart after OCR | PASS. OCRResult rows, active OCR pointers, TextBlock OCR statuses, WorkflowAttempt metadata, ToolRunLogs, and artifacts remain in `project.db`. On restart, WorkflowLoopEngine sees OCR done and translation pending/stale as appropriate, so OCR is not re-run unless requested or inputs changed. |
| S3: OCR edit | PASS. User edit creates a new OCRResult version and updates `TextBlock.active_ocr_result_id` transactionally. Old OCRResult remains. Translation, translation check, and typesetting statuses become stale; Page context stale flags are set. |
| S4: Translation edit | PASS. User edit creates a new TranslationResult version and updates `TextBlock.active_translation_result_id`. Old TranslationResult remains. Typesetting status becomes stale and Page `has_stale_blocks` is set. |
| S5: Provider refusal | PASS. ToolRunLog records sanitized provider refusal metadata; WorkflowAttempt records failed/refused attempt; QualityIssue records issue type, discovered/root stage, blocking severity as applicable; WorkflowDecision records fallback, warning, skip, or block decision according to ProcessingProfile snapshot. |
| S6: Complex cleaning skipped | PASS. Cleaning issue is stored as non-blocking QualityIssue when policy allows. TextBlock cleaning status becomes skipped, Page/Batch can become `ready_for_export_with_warnings`, and WorkflowDecision records skip/mark_warning. |
| S7: Typeset overflow | PASS. Typesetting attempt artifact can be retained for preview. QualityIssue records `typeset_overflow`, discovered/root stage, severity, and suggested action. Export policy distinguishes blocking from warning according to ProcessingProfile. |
| S8: Glossary changed | PASS. GlossaryTerm edit creates or reuses a new GlossaryVersion. Existing TranslationResult keeps previous glossary_version reference. New translations use the new GlossaryVersion and cache key. |
| S9: Failed raw payload | PASS. Failed LLM JSON response is registered as a failed attempt ProcessingArtifact with retention class requiring default retention. WorkflowAttempt metadata remains even if payload retention policy changes later. |
| S10: Project soft delete | PASS. Project is marked trashed in `app.db`; workspace is moved to or marked for trash by ArtifactService; `project.db` remains intact during restore window. Permanent deletion requires explicit confirmation. |

Additional GOAL.md scenarios:

| Scenario | Validation |
| --- | --- |
| Create Project, upload one Page, process successfully, export | PASS. Covered by S1 plus ExportRecord/output artifact creation. |
| App crashes after OCR but before translation; restart and continue | PASS. Covered by S2. |
| OCR result manually edited; translation and typesetting stale | PASS. Covered by S3. |
| Translation result manually edited; typesetting stale | PASS. Covered by S4. |
| Cloud translation provider refuses one TextBlock; fallback or manual path recorded | PASS. Covered by S5. |
| Cleaning fails for complex background; TextBlock skipped with warning | PASS. Covered by S6. |
| Typesetting overflows after minimum font size; previewable with warning | PASS. Covered by S7. |
| Glossary edited after translation; old result keeps previous glossary_version | PASS. Covered by S8. |
| Failed LLM JSON response stored as failed attempt artifact | PASS. Covered by S9. |
| Successful LLM raw payload cleaned by default policy but metadata remains | PASS. WorkflowAttempt and ToolRunLog remain; successful raw payload ProcessingArtifact may be marked cleaned/deleted by retention policy. |
| Project soft-deleted and restorable before permanent deletion | PASS. Covered by S10. |
| Two Projects contain same page filename but remain isolated | PASS. Each Project has a separate workspace and `project.db`; artifact uniqueness is scoped by Project. Same filenames are allowed in different Project directories. |
| Export attempted with unresolved blocking issue and rejected | PASS. Export precheck queries unresolved blocking QualityIssue rows before creating successful ExportRecord. Rejected attempt can create a failed ExportRecord or WorkflowDecision. |
| Export attempted with warning only follows ProcessingProfile policy | PASS. ExportRecord stores policy snapshot, warning count, and whether export was allowed or rejected. |
| Re-run TextBlock with unchanged input/config avoids duplicate provider call | PASS. OCR/translation/cleaning/typesetting cache keys query existing results/artifacts before provider execution. WorkflowDecision can record reuse/continue. |

## 20. Open questions

1. Should Project soft delete move the entire workspace immediately, or only mark it trashed and move during cleanup? Immediate move improves user visibility; marking only reduces filesystem failure modes.
2. Should `ProcessingTask` records stay only in `project.db`, or should `app.db` also keep a lightweight global task index for recent activity across Projects?
3. Should active OCR/translation pointers live only on TextBlock, or should result tables also carry a derived `is_active` for easier debugging views?
4. How strict should GlossaryTerm uniqueness be for aliases, homographs, and multiple possible translations?
5. Should Geometry edits create immutable TextBlockGeometry versions in P1, or is mutating geometry with stale downstream state acceptable for MVP?
6. Should an invalid page-level translation JSON create no TranslationResult rows, or partial TranslationResult rows for successfully parsed blocks plus QualityIssue for missing/invalid blocks?
7. What are the default retention durations for successful raw LLM payloads, debug artifacts, and non-active preview images?
8. Should permanent Project deletion preserve a small tombstone in `app.db` for audit/recent-project cleanup, or remove the row entirely?
9. How should project database integrity checks be exposed: automatic on open, manual maintenance action, or both?
10. Should warning export create a distinct export type/status, or is `ExportRecord.was_forced` plus issue counts sufficient?
