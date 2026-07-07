# 1. Scope

This proposal covers the artifact and quality traceability slice of the data model for the local manga translation workflow.

Primary focus:

- `ProcessingArtifact`
- `QualityIssue`
- `ToolRunLog`
- provider refusal records
- failed payload retention
- debug artifacts
- file cleanup
- export blocking
- artifact lifecycle ownership

The proposal also explicitly discusses every required entity so the artifact and quality decisions fit the full data model:

| Entity | Artifact-quality relevance |
| --- | --- |
| `Project` | Isolation boundary for project data, project.db, artifacts, soft delete, trash, and export policy defaults. |
| `Batch` | Processing and export grouping; aggregate quality state and export readiness. |
| `Page` | Original image owner, page-stage state owner, page artifact anchor, and page-level quality aggregation target. |
| `TextBlock` | Fine-grained processing target for OCR, translation, cleaning, typesetting, refusal, skip, and warning issues. |
| `OCRResult` | Versioned text result linked to OCR input/output artifacts and active pointer. |
| `TranslationResult` | Versioned translation linked to page-level provider attempts, glossary version, quality checks, and active pointer. |
| `GlossaryTerm` | Project-local term source for quality checks such as `translation_term_mismatch`. |
| `GlossaryVersion` | Immutable version marker recorded by `TranslationResult` and used in translation cache keys. |
| `ProcessingTask` | User-started/background execution unit that groups attempts, decisions, logs, and recovery state. |
| `WorkflowAttempt` | Workflow loop attempt metadata; always persisted even if large payload artifacts are cleaned. |
| `WorkflowDecision` | Persisted decision made by `WorkflowLoopEngine` after quality checks and attempt outcomes. |
| `QualityIssue` | Persisted quality/refusal/export-blocking issue with discovered stage and root-stage attribution. |
| `ProcessingArtifact` | Metadata record for every managed filesystem artifact; SQLite stores metadata only, never image blobs. |
| `ToolRunLog` | External tool/provider call trace; records standardized status/error and links to artifacts when retained. |
| `ExportRecord` | Export attempt/result metadata, including blocked and forced/incomplete export decisions. |
| `ProcessingProfile` | Policy source for retry budgets, warning export, debug artifact retention, and successful payload retention. |

Out of scope:

- SQL DDL, ORM classes, API schema, frontend UI, prompts, provider integrations, and migration scripts.
- Professional scanlation-grade artifact types beyond MVP needs.
- Multi-user permissions and cloud deployment.

# 2. Role Bias

This proposal intentionally biases toward auditability and recovery over minimum table count.

Decisions:

- Keep tool call trace (`ToolRunLog`), workflow loop trace (`WorkflowAttempt` / `WorkflowDecision`), quality findings (`QualityIssue`), and file metadata (`ProcessingArtifact`) separate.
- Represent provider refusal as a first-class `QualityIssue` plus standardized `ToolRunLog` and `WorkflowAttempt` metadata, not as an opaque exception string.
- Persist failed attempt artifacts by default because they are required to diagnose invalid JSON, provider refusals, and partial failures.
- Allow successful large raw payload artifacts to be cleaned by retention policy while preserving enough metadata to explain recovery and cache behavior.
- Treat export blocking as a data query over unresolved blocking `QualityIssue` records, with `ProcessingProfile` deciding whether warnings may export.

Rationale:

- The HLD assigns different responsibilities to `ArtifactService`, `QualityCheckService`, and `WorkflowLoopEngine`; the data model should preserve those boundaries.
- Restart recovery cannot depend only on page status. It needs active result pointers, artifact metadata, attempt metadata, decisions, and stage statuses.
- Provider adapters must not own persistence, artifact lifecycle, fallback, skip, or block behavior.

# 3. Assumptions

- `app.db` stores global application metadata, project registry, global/provider configuration references, and global/default `ProcessingProfile` definitions.
- Each Project has its own `project.db` and workspace directory under `workspace/projects/{project_id}/`.
- Project-local data, including artifacts metadata, quality issues, tool logs, attempts, decisions, exports, glossary, and results, lives in the Project's `project.db`.
- File paths stored in `ProcessingArtifact` are project-relative paths, not arbitrary absolute paths. The project workspace root is resolved by app-level project metadata.
- SQLite stores artifact metadata and small structured fields only. Image blobs and large provider payloads live in the filesystem.
- Provider adapters may create temporary files, but only `ArtifactService` can move/register a file as a managed `ProcessingArtifact`.
- `QualityCheckService` creates or updates `QualityIssue` records. `WorkflowLoopEngine` uses those issues plus `ProcessingProfile` to create `WorkflowDecision` records.
- `WorkflowAttempt` metadata is always persisted before or at the same transaction boundary as the corresponding decision/result state change.
- Debug artifacts may contain sensitive local content, OCR text, translations, prompts, and provider responses; they must be explicitly marked.

# 4. Proposed entities

| Entity | Responsibility | Lifecycle owner |
| --- | --- | --- |
| `Project` | Global project record; identifies project.db and workspace path; tracks soft delete/trash state. | Application Service / Repository |
| `Batch` | Upload/processing group; owns ordered `Page` collection and aggregate status. | Application Service / WorkflowService |
| `Page` | Single image unit; owns original image artifact reference, stage status, active page artifacts, and quality summary. | Application Service / WorkflowService |
| `TextBlock` | Detected text region; owns geometry, skip state, per-stage statuses, active OCR/translation pointers. | Detection stage / Review use cases |
| `OCRResult` | Immutable OCR output version for one `TextBlock`; may be tool-generated or user-edited. | OCR stage / Review use cases |
| `TranslationResult` | Immutable translation output version for one `TextBlock`; records glossary and context provenance. | Translation stage / Review use cases |
| `GlossaryTerm` | Project-local term entry. | Glossary use cases |
| `GlossaryVersion` | Immutable project glossary snapshot/hash version. | Glossary use cases |
| `ProcessingTask` | Background task created by UI/API for processing/retry/export. | WorkflowService / TaskRunner |
| `WorkflowAttempt` | One bounded attempt within a workflow stage or loop. | WorkflowLoopEngine |
| `WorkflowDecision` | Persisted reasoned decision after an attempt/check. | WorkflowLoopEngine |
| `QualityIssue` | Quality/refusal/blocking/warning finding, attributed to discovered/root stages and target. | QualityCheckService |
| `ProcessingArtifact` | Managed filesystem artifact metadata with path, hash, type, retention, ownership, and cleanup state. | ArtifactService |
| `ToolRunLog` | External provider/tool invocation trace. | StageExecutor through Repository |
| `ExportRecord` | Export request/result/block record and output artifact references. | Export use case / WorkflowLoopEngine |
| `ProcessingProfile` | Policy for retries, export warning behavior, retention, debug artifact behavior, and provider fallback. | ConfigService |

Ownership boundaries:

- `ArtifactService` owns artifact path generation, safe writes, hashing, registration, retention marking, trash moves, and cleanup.
- `Repository / DAO` owns SQLite reads/writes and transaction boundaries.
- `Provider Adapter` owns only structured tool invocation and standardized output/error return.
- `QualityCheckService` owns `QualityIssue` detection, severity, blocking flag, discovered stage, root-stage attribution, and suggested action.
- `WorkflowLoopEngine` owns retry/fallback/skip/warning/block decisions and writes `WorkflowAttempt` / `WorkflowDecision`.
- Export use case owns `ExportRecord` creation and must call ExportCheck before normal export.

# 5. P0 / P1 / P2 classification

| Entity/feature | Priority | Rationale |
| --- | --- | --- |
| `Project`, `Batch`, `Page`, `TextBlock` | P0 | Required hierarchy and isolation boundary. |
| `OCRResult`, `TranslationResult` versioning | P0 | Required for user edits, active result pointers, stale propagation, and recovery. |
| `GlossaryTerm`, `GlossaryVersion` | P0 | Required for project-local glossary and translation provenance. |
| `ProcessingTask` | P0 | Required for asynchronous processing, pause/cancel/restart recovery. |
| `WorkflowAttempt`, `WorkflowDecision` | P0 | Required by HLD loop and recovery requirements. |
| `QualityIssue` with discovered/root stage | P0 | Required by HARNESS hard invariant and export blocking. |
| `ProcessingArtifact` for original, masks, active cleaned/typeset/export, failed payloads | P0 | Required artifact metadata and no image BLOB invariant. |
| `ToolRunLog` for every external tool call | P0 | Required traceability and error diagnosis. |
| Provider refusal as structured log + attempt + issue + decision | P0 | Required compliance and fallback/block handling. |
| Failed attempt payload retention | P0 | Required default behavior. |
| Successful raw payload cleanup policy | P0 | Required configurability and default cleanup. |
| `ExportRecord` for successful and blocked export attempts | P0 | Required export traceability and blocking explanation. |
| `ProcessingProfile` retention/export-warning policy | P0 | Required WorkflowLoopEngine decisions and warning export control. |
| Debug artifact policy and explicit marking | P0 | Required safety boundary. |
| Detection visualization, OCR crop persistence beyond active/debug needs | P1 | Useful for review and diagnostics; can be policy-controlled. |
| Export manifest artifact | P1 | Listed as P1 in SRS. |
| Cost/token usage summary in logs | P1 | Useful for cloud cost prompting. |
| Advanced cleanup dry-run and artifact repair scan | P1 | Useful but not required for MVP loop. |
| Multi-page context artifact graph | P2 | Future translation improvement, not MVP. |
| Rich artifact lineage graph across derived image layers | P2 | Useful for advanced editing; avoid over-design for MVP. |

# 6. app.db vs project.db placement

| Entity | Placement | Rationale |
| --- | --- | --- |
| `Project` | `app.db` | Global registry must locate project.db and workspace; supports recent projects and soft-deleted project listing. |
| `Batch` | `project.db` | Project-isolated processing group. |
| `Page` | `project.db` | Project-isolated image/page state and artifact references. |
| `TextBlock` | `project.db` | Project-local detection geometry and per-stage state. |
| `OCRResult` | `project.db` | Project-local result versions and artifact links. |
| `TranslationResult` | `project.db` | Project-local result versions, glossary version, context provenance. |
| `GlossaryTerm` | `project.db` | Must belong to Project and not leak between projects. |
| `GlossaryVersion` | `project.db` | Project-local version/hash. |
| `ProcessingTask` | `project.db` | A task processes one Project's data; recovery should work with only project.db plus app registry. |
| `WorkflowAttempt` | `project.db` | Project-local attempt trace. |
| `WorkflowDecision` | `project.db` | Project-local workflow explanation. |
| `QualityIssue` | `project.db` | Project-local quality and export blocking state. |
| `ProcessingArtifact` | `project.db` | Project-local filesystem metadata and ownership. |
| `ToolRunLog` | `project.db` | Project-local provider/tool trace. |
| `ExportRecord` | `project.db` | Exports are project/batch/page-specific. |
| `ProcessingProfile` | `app.db` for built-in/global profiles; `project.db` snapshot or override reference for task execution | Profiles are global defaults but task behavior must be reproducible if global defaults later change. |

Decision:

- Store a profile snapshot or profile version reference on `ProcessingTask` / `WorkflowAttempt`, even if the editable `ProcessingProfile` definition lives in `app.db`.

Rationale:

- Retention, retry, and warning-export behavior must be explainable after profile edits.

Rejected alternative:

- Store only `processing_profile_id` on tasks. This is too weak because later profile edits would rewrite the apparent policy history.

# 7. Key fields

This section lists implementation-ready field concepts without SQL DDL.

## `Project`

- identity: `project_id`, `name`
- location: `workspace_project_path`, `project_db_path`
- defaults: `default_source_language`, `default_target_language`, `default_processing_profile_id`
- lifecycle: `status`, `deleted_at`, `trash_path`, `permanent_delete_after`
- timestamps: `created_at`, `updated_at`, `last_opened_at`, `last_processed_at`

## `Batch`

- identity: `batch_id`, `project_id`, `name`
- ordering/size: `page_count`
- languages: `source_language`, `target_language`
- state: `status`, `quality_summary`, `has_unresolved_blocking_issues`, `has_warnings`
- lifecycle: `deleted_at`
- timestamps: `created_at`, `updated_at`, `last_processed_at`

## `Page`

- identity: `page_id`, `project_id`, `batch_id`, `page_index`
- input: `original_artifact_id`, `original_filename`, `original_file_hash`
- active artifacts: `active_detection_artifact_id`, `active_cleaned_artifact_id`, `active_typeset_artifact_id`
- state: `status`, `quality_flags`, `translation_context_stale`, `has_stale_blocks`
- lifecycle: `deleted_at`
- timestamps: `created_at`, `updated_at`

## `TextBlock`

- identity: `text_block_id`, `project_id`, `batch_id`, `page_id`
- geometry: `bbox`, `polygon`, `mask_artifact_id`, `source_direction`, `reading_order`
- detection provenance: `detection_provider`, `detection_confidence`, `detection_artifact_id`
- active pointers: `active_ocr_result_id`, `active_translation_result_id`
- stage state: `detection_status`, `ocr_status`, `translation_status`, `translation_check_status`, `cleaning_status`, `typesetting_status`, `review_status`
- skip/review: `is_skipped`, `skip_reason`, `is_manual_adjusted`
- lifecycle: `deleted_at`
- timestamps: `created_at`, `updated_at`

## `OCRResult`

- identity: `ocr_result_id`, `text_block_id`
- content: `source_text`, `normalized_source_text_hash`
- quality: `ocr_confidence`, `ocr_quality_flag`
- provenance: `provider`, `model_id`, `tool_version`, `tool_run_id`, `workflow_attempt_id`
- artifact links: `input_artifact_id`, `raw_output_artifact_id`
- cache: `input_hash`, `config_hash`, `provider_cache_key`
- versioning: `version_number`, `is_user_edited`, `created_from_ocr_result_id`
- timestamps: `created_at`, `updated_at`

## `TranslationResult`

- identity: `translation_result_id`, `text_block_id`
- content: `source_text_hash`, `translation_text`, `used_terms`
- provenance: `provider`, `model_id`, `prompt_template_version`, `tool_run_id`, `workflow_attempt_id`
- glossary/context: `glossary_version_id`, `glossary_version_number`, `context_hash`, `page_translation_run_id`
- cache: `generation_config_hash`, `translation_cache_key`
- quality: `confidence`, `needs_review`, `quality_flags`, `error_code`
- versioning: `version_number`, `is_user_edited`, `is_locked`, `created_from_translation_result_id`
- timestamps: `created_at`, `updated_at`

## `GlossaryTerm`

- identity: `term_id`, `project_id`
- content: `source_text`, `target_text`, `term_type`, `reading`, `aliases`
- behavior: `case_sensitive`, `priority`, `status`
- provenance: `created_from_text_block_id`, `created_by_user`
- lifecycle/timestamps: `deleted_at`, `created_at`, `updated_at`

## `GlossaryVersion`

- identity: `glossary_version_id`, `project_id`, `version_number`
- snapshot: `terms_hash`, optional `snapshot_artifact_id`
- reason: `created_reason`
- timestamps: `created_at`

## `ProcessingTask`

- identity: `processing_task_id`, `project_id`, optional `batch_id`, optional `page_id`, optional `text_block_id`
- intent: `task_type`, `requested_stage`, `requested_by`
- policy: `processing_profile_id`, `processing_profile_snapshot`
- state: `status`, `current_stage`, `progress`, `pause_requested`, `cancel_requested`
- recovery: `resume_token`, `last_workflow_decision_id`, `last_attempt_id`
- timestamps: `queued_at`, `started_at`, `finished_at`, `updated_at`

## `WorkflowAttempt`

- identity: `workflow_attempt_id`, `processing_task_id`
- target: `target_type`, `target_id`, `stage`
- order: `attempt_number`, `loop_iteration`
- input/policy: `input_hash`, `config_hash`, `profile_snapshot_hash`, `provider_name`, `model_id`
- outcome: `status`, `error_code`, `error_class`, `is_provider_refusal`
- artifacts: `input_artifact_id`, `output_artifact_id`, `raw_request_artifact_id`, `raw_response_artifact_id`, `debug_bundle_artifact_id`
- timing: `started_at`, `finished_at`, `duration_ms`
- retry: `retry_budget_before`, `retry_budget_after`

## `WorkflowDecision`

- identity: `workflow_decision_id`, `processing_task_id`, `workflow_attempt_id`
- target: `target_type`, `target_id`, `stage`
- decision: `decision_type`, `reason_code`, `rationale`
- issue links: `primary_quality_issue_id`, optional `related_quality_issue_ids`
- action: `next_stage`, `fallback_provider`, `mark_status`, `requires_user_action`
- timestamps: `created_at`

## `QualityIssue`

- identity: `quality_issue_id`, `project_id`, optional `batch_id`, optional `page_id`, optional `text_block_id`
- target: `target_type`, `target_id`
- type: `issue_type`, `error_code`
- attribution: `discovered_stage`, `root_stage`
- severity: `severity`, `is_blocking`
- state: `status`, `resolution_type`, `resolved_at`, `resolved_by`
- explanation: `message`, `user_message`, `suggested_action`
- provenance: `quality_check_name`, `workflow_attempt_id`, `workflow_decision_id`, `tool_run_id`
- artifact links: `evidence_artifact_id`, optional `debug_artifact_id`
- stale handling: `input_hash`, `config_hash`, `applies_to_result_id`, `superseded_by_issue_id`
- timestamps: `created_at`, `updated_at`

Provider refusal fields are represented on `QualityIssue` as:

- `issue_type = provider_refusal` or a stage-specific issue such as `translation_provider_refused`
- `error_code` from the approved error code set
- `severity` determined by `QualityCheckService`
- `is_blocking` determined by issue semantics and `ProcessingProfile`
- `discovered_stage = translation` or relevant provider stage
- `root_stage = provider_policy` or the provider stage if the final taxonomy avoids a separate policy stage
- `tool_run_id`, `workflow_attempt_id`, and evidence artifact links when retained

## `ProcessingArtifact`

- identity: `artifact_id`, `project_id`
- ownership: optional `batch_id`, optional `page_id`, optional `text_block_id`, optional `ocr_result_id`, optional `translation_result_id`, optional `processing_task_id`, optional `workflow_attempt_id`, optional `tool_run_id`, optional `export_record_id`
- classification: `artifact_type`, `source_stage`, `media_type`, `content_category`
- location: `relative_path`, `storage_state`
- integrity: `file_hash`, `hash_algorithm`, `byte_size`
- provenance: `created_by_service`, `created_by_provider`, `source_artifact_id`, `derived_from_artifact_ids`
- retention: `retention_class`, `retention_policy`, `is_debug`, `is_failed_payload`, `is_success_payload`, `cleanup_eligible_at`, `cleaned_at`
- safety: `may_contain_original_image`, `may_contain_ocr_text`, `may_contain_translation`, `may_contain_provider_response`, `contains_secret_redacted`
- timestamps: `created_at`, `updated_at`, `deleted_at`

`artifact_type` examples:

- `original_image`
- `page_preview`
- `detection_result_json`
- `detection_overlay_image`
- `textblock_crop_image`
- `mask_image`
- `ocr_raw_output`
- `translation_raw_request`
- `translation_raw_response`
- `cleaned_image`
- `typeset_image`
- `quality_report_json`
- `attempt_payload`
- `debug_bundle`
- `export_image`
- `export_zip`
- `export_manifest`

`retention_class` examples:

- `permanent_original`
- `active_result`
- `failed_attempt_payload`
- `successful_payload`
- `debug`
- `cache_rebuildable`
- `export_output`
- `trash_pending_delete`

`storage_state` examples:

- `present`
- `moved_to_trash`
- `metadata_only_cleaned`
- `missing`
- `deleted`

## `ToolRunLog`

- identity: `tool_run_id`, `project_id`
- target: optional `batch_id`, optional `page_id`, optional `text_block_id`
- stage/tool: `stage`, `tool_name`, `tool_version`, `provider_name`, `model_id`
- invocation: `input_hash`, `config_hash`, `request_id_external`
- status: `status`, `error_code`, `error_class`, `is_provider_refusal`
- sanitized message: `error_message`, `user_message`
- usage/cost: `input_units`, `output_units`, `estimated_cost`, `rate_limit_reset_at`
- artifact links: `input_artifact_id`, `output_artifact_id`, `raw_request_artifact_id`, `raw_response_artifact_id`
- timing: `started_at`, `finished_at`, `duration_ms`

## `ExportRecord`

- identity: `export_record_id`, `project_id`, optional `batch_id`, optional `page_id`
- request: `export_type`, `requested_by`, `processing_profile_id`, `profile_snapshot`
- precheck: `precheck_status`, `blocking_issue_count`, `warning_issue_count`, `allowed_with_warnings`
- state: `status`, `error_code`, `is_forced_export`, `is_incomplete_export`
- output: `output_artifact_id`, `manifest_artifact_id`
- issue summary: `blocked_by_issue_ids`, `included_warning_issue_ids`
- timestamps: `requested_at`, `started_at`, `finished_at`

## `ProcessingProfile`

- identity: `processing_profile_id`, `name`, `version`
- loop policy: retry budgets per stage, fallback policy, skip policy, pause-on-blocking policy
- export policy: `allow_warning_export`, `allow_forced_export`, `auto_export`
- retention policy: `keep_failed_payloads`, `successful_payload_retention`, `debug_artifact_mode`, `debug_artifact_ttl_days`
- quality policy: strictness, warning thresholds, blocking issue mapping
- timestamps: `created_at`, `updated_at`

# 8. Relationships

Relationship summary:

| Source | Relationship |
| --- | --- |
| `Project` | has many `Batch`, `GlossaryTerm`, `GlossaryVersion`, `ProcessingTask`, `QualityIssue`, `ProcessingArtifact`, `ToolRunLog`, `ExportRecord`. |
| `Batch` | belongs to `Project`; has many `Page`; may have many `ProcessingTask`, `QualityIssue`, `ProcessingArtifact`, `ExportRecord`. |
| `Page` | belongs to `Batch`; has many `TextBlock`; references original and active result artifacts. |
| `TextBlock` | belongs to `Page`; has many `OCRResult`, `TranslationResult`, `QualityIssue`, and artifacts; references active OCR/translation results. |
| `OCRResult` | belongs to `TextBlock`; references input crop and raw output artifacts; may be linked to `ToolRunLog` and `WorkflowAttempt`. |
| `TranslationResult` | belongs to `TextBlock`; references `GlossaryVersion`; may be linked to `ToolRunLog` and `WorkflowAttempt`. |
| `GlossaryVersion` | belongs to `Project`; is referenced by `TranslationResult`. |
| `ProcessingTask` | belongs to `Project`; may target `Batch`, `Page`, or `TextBlock`; has many `WorkflowAttempt` and `WorkflowDecision`. |
| `WorkflowAttempt` | belongs to `ProcessingTask`; may reference `ToolRunLog`, artifacts, and later `WorkflowDecision`. |
| `WorkflowDecision` | belongs to `ProcessingTask`; usually references `WorkflowAttempt` and one or more `QualityIssue`. |
| `QualityIssue` | belongs to `Project`; targets `Project`, `Batch`, `Page`, `TextBlock`, `OCRResult`, `TranslationResult`, `WorkflowAttempt`, `ToolRunLog`, or `ExportRecord`. |
| `ProcessingArtifact` | belongs to `Project`; may be owned by a page/textblock/result/attempt/tool run/export depending on artifact type. |
| `ToolRunLog` | belongs to `Project`; may target page/textblock; may reference input/output/raw artifacts. |
| `ExportRecord` | belongs to `Project`; may target batch/page; references output artifacts and issue ids that blocked or warned. |
| `ProcessingProfile` | global or project override; tasks/attempts/export records store a snapshot or immutable version reference. |

Important relationship decisions:

- `ProcessingArtifact` has optional owner references rather than a single generic owner field only. This is ORM-friendly and supports common queries such as "all artifacts for this page" without parsing JSON.
- `QualityIssue` uses a generic target concept plus nullable concrete scope ids. The `project_id` is always present for isolation and cleanup queries.
- Page-level translation produces one `ToolRunLog` / `WorkflowAttempt` for the page call and multiple `TranslationResult` records for text blocks. The shared translation raw response artifact is linked to the page attempt/tool run, while each `TranslationResult` links back to the shared attempt.

Rejected alternative:

- Attach raw provider payload directly to `OCRResult` or `TranslationResult`. Rejected because payload retention differs from result retention and may be cleaned independently.

# 9. Versioning rules

OCR and translation:

- `OCRResult` and `TranslationResult` are immutable after creation except for metadata that does not change semantic content, such as cleanup state on linked artifacts.
- User edits create new result versions with `is_user_edited = true`.
- Tool reruns create new result versions unless the idempotency/cache lookup reuses an existing semantically identical result.
- Old results remain queryable for audit, rollback, and stale explanation.
- The active result is selected through explicit active pointer fields on `TextBlock`.

Glossary:

- Every glossary change creates a new `GlossaryVersion` or updates the current transaction into a new version before translation uses it.
- `TranslationResult` records the glossary version used at generation time.
- Old `TranslationResult` records are not rewritten when glossary changes.

Artifacts:

- Artifacts are immutable content records once registered. If a file is regenerated, create a new `ProcessingArtifact`.
- Artifact cleanup changes `storage_state`, `cleaned_at`, and retention fields; it does not rewrite the artifact identity or hash history.
- If a cleaned successful payload is later needed for debugging, metadata remains but file bytes may be unavailable; UI/API should state that the raw payload was cleaned by policy.

Quality issues:

- Quality issues may change status from `open` to `resolved`, `accepted_warning`, `superseded`, or `stale`.
- If a new result version invalidates an issue, mark the old issue `stale` or `superseded`; do not silently delete it.
- Root-stage attribution may be corrected by `QualityCheckService` if later evidence improves attribution; record `updated_at`.

Workflow:

- `WorkflowAttempt` and `WorkflowDecision` are append-only for audit.
- Retrying a stage creates a new attempt and new decision.

# 10. Active pointer rules

`TextBlock`:

- `active_ocr_result_id` points to the OCRResult used for downstream translation.
- `active_translation_result_id` points to the TranslationResult used for downstream typesetting/export.
- At most one active OCR and one active translation are selected per TextBlock.
- Locked translations remain active until the user explicitly unlocks or replaces them.

`Page`:

- `original_artifact_id` is stable and never replaced by processing.
- `active_cleaned_artifact_id` points to the page-level current cleaned image, if available.
- `active_typeset_artifact_id` points to the current preview/export candidate image.
- Page active artifacts may be stale if downstream state flags indicate stale results; active means "currently selected", not necessarily "fresh".

`Batch`:

- Export readiness derives from page/textblock states and unresolved issues, not from a single active pointer.

`ExportRecord`:

- The latest successful normal export can be queried by `status = succeeded` and target scope.
- Blocked export attempts are kept with `status = blocked` and do not create normal output artifacts.

Rejected alternative:

- Use `is_active` flags only on result rows. Rejected for MVP because explicit pointers on `TextBlock` make restart recovery and joins simpler. A database uniqueness guard may still prevent multiple active flags if flags are used for convenience.

# 11. State and stale rules

State decision:

- Keep per-stage state on `TextBlock`, aggregate state on `Page` and `Batch`, and detailed explanations in `QualityIssue`, `WorkflowAttempt`, and `WorkflowDecision`.

Stale propagation:

| Event | Required data changes |
| --- | --- |
| User edits OCR | Create new `OCRResult`; update `TextBlock.active_ocr_result_id`; set translation, translation_check, and typesetting statuses to `stale`; mark affected translation/typesetting issues `stale`; set `Page.translation_context_stale = true`. |
| User edits translation | Create new `TranslationResult`; update `TextBlock.active_translation_result_id`; set typesetting status to `stale`; mark prior typesetting issues `stale`; set `Page.has_stale_blocks = true`. |
| User changes TextBlock geometry/mask | Create or update geometry version decision in TextBlock; register new mask artifact if changed; set cleaning and typesetting statuses to `stale`; mark related cleaning/typesetting issues `stale`. |
| Glossary changes | Create new `GlossaryVersion`; do not modify old translations; mark pages or translations with old glossary as potentially stale if profile requires strict glossary freshness. |
| Successful cleanup removes raw payload | Set artifact `storage_state = metadata_only_cleaned`; do not change attempt/result state. |
| Provider refusal | `ToolRunLog.status = refused` or `failed`; `WorkflowAttempt.is_provider_refusal = true`; create `QualityIssue`; create `WorkflowDecision` for fallback/warning/skip/block. |

Quality issue status:

- `open`: unresolved and should affect readiness/export checks.
- `resolved`: fixed by new result, retry, user action, or successful downstream rerun.
- `accepted_warning`: user/profile accepts a warning for export; still visible.
- `stale`: issue no longer applies to active inputs/results.
- `superseded`: replaced by a newer issue with clearer attribution.

Export readiness:

- Normal export is blocked when any `open` unresolved `QualityIssue` with `is_blocking = true` exists in target scope.
- Warning-only export follows `ProcessingProfile.allow_warning_export`.
- Forced/incomplete export, if allowed in advanced mode, must create `ExportRecord.is_forced_export = true` or `is_incomplete_export = true` and include blocking issue summary. It is not a normal export.

# 12. Artifact relationships

Artifact ownership rules:

- Original image artifacts are owned by `Page`, retention class `permanent_original`, and are never overwritten.
- Detection result artifacts are owned by `Page`; individual masks may be owned by `TextBlock`.
- OCR crop artifacts are owned by `TextBlock` and may be cache-rebuildable unless profile/debug policy keeps them.
- OCR raw output artifacts are owned by `ToolRunLog` / `WorkflowAttempt` and optionally referenced by `OCRResult`.
- Translation raw request/response artifacts are owned by page-level `ToolRunLog` / `WorkflowAttempt`; individual `TranslationResult` rows reference the attempt rather than duplicating payload links.
- Cleaned and typeset image artifacts are owned by `Page` for page-level images and may also reference affected `TextBlock` when produced by local rerun.
- Quality report artifacts are owned by `Page` or `Batch`.
- Export artifacts are owned by `ExportRecord`.
- Debug bundles are owned by `WorkflowAttempt` or `ProcessingTask` and must be marked `is_debug = true`.

Artifact lifecycle states:

| State | Meaning |
| --- | --- |
| `present` | File exists at registered project-relative path. |
| `moved_to_trash` | File was moved under project trash by soft delete. |
| `metadata_only_cleaned` | File bytes were cleaned by retention policy; metadata remains. |
| `missing` | File expected but not found; requires repair/retry/user notice. |
| `deleted` | Permanently deleted after confirmation or retention cleanup. |

ArtifactService constraints:

- Normalize and validate all relative paths to prevent path traversal.
- Write new artifacts atomically through temporary path plus rename where feasible.
- Compute file hash after write and before registration commit.
- Never allow provider adapters to choose final workspace paths.
- Redact secrets before saving raw request/response artifacts or logs.

Rejected alternative:

- Store `cleaned_image_path`, `typeset_image_path`, and similar path fields directly on domain rows as the only source of truth. Rejected because retention, hash, debug marking, cleanup state, and artifact provenance require a dedicated metadata record. Domain rows may keep active artifact ids for fast access.

# 13. Idempotency and cache keys

General rule:

- Cache keys belong to workflow/repository lookup decisions, not provider adapters.
- A cached result can be reused only when input content, relevant context, config, provider identity, model/version, and active upstream result versions match.

Recommended keys:

| Stage | Key inputs |
| --- | --- |
| Detection | original image hash, detection provider, provider version, model id, detection config hash. |
| OCR | crop or region image hash, bbox/mask hash, OCR provider, model id, tool version, OCR config hash. |
| Page translation | ordered active OCR source text hashes for all included TextBlocks, page context hash, glossary version, provider, model id, prompt template version, generation config hash. |
| Single-block translation | target active OCR source hash, page context hash including neighboring block OCR/translations, glossary version, provider, model id, prompt template version, generation config hash. |
| Cleaning | original image hash or prior active image hash, textblock mask hash, cleaning mode/provider, config hash. |
| Typesetting | active cleaned image hash, active translation result id/hash, geometry hash, font config hash, typesetting provider/version, layout config hash. |
| Export | active typeset artifact hashes for selected pages, page order, export config hash, manifest setting. |

Idempotency behavior:

- If an identical successful result exists and is still valid, reuse it and create a `WorkflowDecision` of `continue` or `reuse_cached_result` if the final taxonomy includes it.
- Do not repeat provider calls for unchanged TextBlock/page input and config.
- Failed attempts are not reused as successful outputs, but they count toward retry budget and provide diagnostics.
- Provider refusals should not be blindly retried with the same cloud provider and same input/config unless the user or profile explicitly changes provider/policy. The decision should be fallback, manual path, warning, skip, or block.

Important indexes/uniqueness concepts:

- Unique active OCR pointer per TextBlock through pointer field.
- Unique active translation pointer per TextBlock through pointer field.
- Lookup indexes on result cache keys, `ToolRunLog(input_hash, config_hash, provider_name, model_id, status)`, and `ProcessingArtifact(file_hash, artifact_type)`.
- Scope indexes on `QualityIssue(project_id, status, is_blocking, target_type, target_id)`.
- Cleanup indexes on `ProcessingArtifact(project_id, retention_class, storage_state, cleanup_eligible_at)`.

# 14. Deletion and retention policy

Soft delete:

- Project soft delete updates `Project.status/deleted_at` in `app.db` and marks or moves the project workspace to trash according to platform-safe policy.
- Batch/Page/TextBlock soft delete marks rows `deleted_at` and marks associated artifacts `trash_pending_delete` or moves them under project trash.
- Restore clears soft-delete metadata and returns artifacts from trash when paths are still available.
- Permanent delete requires confirmation and deletes project.db plus project workspace artifacts after ensuring no task is running.

Retention:

| Artifact class | Default policy |
| --- | --- |
| Original images | Keep until permanent project/page deletion. |
| Active cleaned/typeset images | Keep while active and until replaced plus retention grace period. |
| Export outputs | Keep until export deletion/project deletion. |
| Masks | Keep by default because cleaning and review depend on them. |
| Failed attempt payloads | Keep by default. |
| Provider refusal payload evidence | Keep sanitized metadata by default; raw payload retained according to failed/debug policy. |
| Successful raw LLM/OCR payloads | Clean by default after successful processing unless debug/strict profile keeps them. |
| Debug artifacts | Keep only when explicitly enabled; use profile TTL or manual cleanup. |
| Rebuildable crops/previews | Eligible for cleanup when no active result depends on them. |

File cleanup:

- Cleanup is performed by `ArtifactService` based on `retention_class`, `cleanup_eligible_at`, `storage_state`, and active references.
- Cleanup must not delete artifacts referenced as active original/cleaned/typeset/export/mask records.
- Cleanup must leave `ProcessingArtifact` metadata and update `storage_state`.
- If cleanup fails due to filesystem errors, create a non-blocking `QualityIssue` or task error only if it affects recovery/export. Otherwise record a maintenance issue/log.

Secret safety:

- API keys are never stored in project.db, `ToolRunLog`, raw payload artifacts, or debug bundles.
- Raw request/response artifacts must be sanitized or marked as containing provider response/user content. If redaction cannot be guaranteed, profile/UI must warn before debug retention.

Rejected alternatives:

- Delete all successful artifacts immediately. Rejected because active preview/export artifacts and masks are required for review and rerun.
- Keep all raw payloads forever. Rejected because successful raw payloads can be large and sensitive; HLD allows cleanup by policy.
- Hard-delete project files on first delete action. Rejected because HLD requires soft delete/trash with restore before permanent deletion.

# 15. Migration concerns

Migration readiness decisions:

- Include `schema_migrations` in both `app.db` and each `project.db`.
- Use stable string enums for stages, artifact types, issue types, and retention classes, but keep taxonomy centralized so later migrations can normalize values.
- Store `processing_profile_snapshot` on tasks/attempts/export records as structured JSON-compatible data to preserve historical behavior across profile schema changes.
- Use nullable forward-compatible fields for optional links such as `workflow_attempt_id`, `tool_run_id`, `ocr_result_id`, and `translation_result_id`.
- Keep artifact paths project-relative so workspace moves can update app-level project location without rewriting every artifact row.
- Add `storage_state` from the start so future cleanup/repair features do not require inferring missing files.
- Preserve unknown provider metadata in controlled JSON metadata fields only where needed, but keep common query fields normalized.

Migration risks:

- Overly broad generic target fields on `QualityIssue` can become hard to enforce. Mitigate with application validation and scope ids.
- `ProcessingArtifact` can accumulate many optional foreign keys. Mitigate with clear artifact type ownership rules and indexes for common queries.
- Profile snapshots can become stale schema blobs. Mitigate with `profile_snapshot_version` and migration adapters.

# 16. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Artifact table becomes too broad | Developers may misuse it as a dumping ground. | Require `artifact_type`, `retention_class`, owner ids, and ArtifactService-only registration. |
| Raw payloads may expose sensitive content | Debug artifacts and failed payloads may contain original images, OCR text, translations, provider responses. | Explicit debug marking, redaction, profile warnings, retention TTL, no secrets in logs. |
| Provider refusal semantics may be inconsistent | Export/fallback behavior becomes unpredictable. | Standardize provider refusal fields across `ToolRunLog`, `WorkflowAttempt`, `QualityIssue`, and `WorkflowDecision`. |
| Cleanup may remove files needed for recovery | Restart or preview may break. | Protect active artifacts and masks; cleanup only by retention class and active-reference checks; preserve metadata. |
| Export blocking could become hidden UI logic | Normal export might bypass unresolved blocking issues. | Make export precheck data-driven through `QualityIssue.status/is_blocking` and `ExportRecord`. |
| Quality issues may remain open after fixes | Export may be blocked incorrectly. | Stale/supersede rules on result version changes; validation scenario coverage. |
| Too many logs/attempts for page-level translation | Storage grows quickly. | Page-level attempt links to many result rows; successful payload cleanup by policy. |
| Generic issue target is less strict than concrete FKs | Data integrity bugs possible. | Always include project/page/textblock scope ids where applicable; add application-level validation. |

# 17. Rejected alternatives

1. Single `status/error_message` fields on `Page` and `TextBlock` only.
   - Rejected because HARNESS requires persisted `WorkflowAttempt`, `WorkflowDecision`, and `QualityIssue` with root/discovered stages.

2. Provider adapters register artifacts directly.
   - Rejected because HLD states Provider Adapters must not own artifact lifecycle or database persistence.

3. Store raw image or provider payload BLOBs in SQLite.
   - Rejected because hard invariant forbids image BLOBs in SQLite and large payloads need retention cleanup independent of metadata.

4. Represent provider refusal only as `ToolRunLog.error_message`.
   - Rejected because refusal changes workflow decisions, export readiness, fallback/manual path, and user-facing quality report.

5. Delete failed attempt payloads by default.
   - Rejected because SRS/HARNESS require failed payload artifacts to be persisted by default, especially invalid LLM JSON.

6. Never delete successful raw payloads.
   - Rejected because HLD explicitly allows successful large raw payload cleanup by policy and debug artifacts may contain sensitive content.

7. Make `QualityIssue.is_blocking` purely dynamic from `issue_type`.
   - Rejected because `ProcessingProfile` can affect warning export and strictness. Store the evaluated blocking flag and profile snapshot context for audit.

8. Store all `ProcessingProfile` definitions only in `project.db`.
   - Rejected because profiles are global settings in HLD, but per-task snapshots in project.db are still needed for reproducibility.

# 18. Decisions intentionally left to later rounds

- Exact enum taxonomy for `artifact_type`, `issue_type`, `error_code`, `decision_type`, and `retention_class`.
- Whether `QualityIssue.root_stage` should include a separate `provider_policy` stage or use the provider stage plus `issue_type = provider_refusal`.
- Exact TTL values for debug artifacts, successful payloads, and replaced active artifacts.
- Whether cleanup creates `QualityIssue` records or a separate maintenance log for non-user-facing cleanup failures.
- Whether to materialize page/batch quality summaries or compute them on demand from `QualityIssue`.
- Exact ERD cardinalities for optional artifact owner fields.
- Whether `ProcessingProfile` project overrides are stored as full rows in project.db or as immutable snapshots on tasks only.
- Exact repair behavior when a registered artifact file is missing.
- Whether `ExportRecord.blocked_by_issue_ids` is stored as a join table or compact structured field.

# 19. Validation against all scenarios in HARNESS.md

| Scenario | Validation |
| --- | --- |
| S1: Happy path | PASS. `Project` in app.db locates project.db/workspace. `Batch` owns ordered `Page`; `Page` owns original artifact. Detection creates `TextBlock` and detection/mask artifacts. OCR creates `ToolRunLog`, `WorkflowAttempt`, `OCRResult`, artifacts. Page-level translation creates shared attempt/log and per-TextBlock `TranslationResult`. Cleaning/typesetting register new artifacts. `QualityIssue` has no unresolved blocking issue, so `ExportRecord` succeeds and references export artifact. |
| S2: Restart after OCR | PASS. `OCRResult` versions, `TextBlock.active_ocr_result_id`, stage statuses, `WorkflowAttempt`, `WorkflowDecision`, and artifact metadata survive restart. Workflow resumes translation without rerunning OCR because idempotency keys and active OCR pointers show OCR is complete. |
| S3: OCR edit | PASS. User edit creates new `OCRResult`, updates active pointer, marks translation/check/typesetting stale, marks old downstream issues stale, and sets page translation context stale. Old OCR remains for audit. |
| S4: Translation edit | PASS. User edit creates new `TranslationResult`, updates active pointer, marks typesetting stale and old typesetting issues stale. Old translation remains available. |
| S5: Provider refusal | PASS. Provider adapter returns standardized refusal. Stage records `ToolRunLog.is_provider_refusal`, `WorkflowAttempt.is_provider_refusal`, failed/refusal artifacts if retained, `QualityIssue` with discovered/root stage, and `WorkflowDecision` for fallback/warning/skip/block according to profile. No bypass behavior is modeled. |
| S6: Complex cleaning skipped | PASS. Cleaning check creates non-blocking warning `QualityIssue` such as `cleaning_complex_background`; `WorkflowDecision` marks skip/warning; TextBlock cleaning status becomes skipped; Page may become `ready_for_export_with_warnings`. |
| S7: Typeset overflow | PASS. Typesetter output preview artifact is registered even if overflow occurs. `QualityIssue` records `typeset_overflow`, severity warning or blocking by profile, discovered/root stage, and suggested action. Export follows blocking/warning policy. |
| S8: Glossary changed | PASS. Glossary edit creates a new `GlossaryVersion`; old `TranslationResult` keeps previous `glossary_version_id`. Strict profiles may mark affected translations as stale but do not rewrite old results. |
| S9: Failed raw payload | PASS. Invalid LLM JSON creates failed `ToolRunLog`, failed `WorkflowAttempt`, failed raw response artifact with `retention_class = failed_attempt_payload`, and `QualityIssue = translation_invalid_json`. Failed payloads are persisted by default. |
| S10: Project soft delete | PASS. `Project.deleted_at/status/trash_path` updates in app.db; project artifacts are moved or marked trash-pending; project.db rows remain restorable until permanent deletion confirmation. |

Additional GOAL.md scenarios:

| Scenario | Validation |
| --- | --- |
| 1. Create Project, upload one Page, process successfully, export. | PASS. Covered by S1 with export artifact and `ExportRecord`. |
| 2. App crashes after OCR but before translation; restart and continue. | PASS. Covered by S2. |
| 3. OCR result is manually edited; translation and typesetting become stale. | PASS. Covered by S3. |
| 4. Translation result is manually edited; typesetting becomes stale. | PASS. Covered by S4. |
| 5. Cloud translation provider refuses one TextBlock; fallback or manual path is recorded. | PASS. Refusal is recorded across log/attempt/issue/decision; fallback/manual/block decision is explicit. |
| 6. Cleaning fails for complex background; TextBlock is skipped with warning. | PASS. Covered by S6. |
| 7. Typesetting overflows after minimum font size; result is still previewable with warning. | PASS. Covered by S7. |
| 8. Glossary is edited after translation; old TranslationResult keeps previous glossary_version. | PASS. Covered by S8. |
| 9. A failed LLM JSON response is stored as failed attempt artifact. | PASS. Covered by S9. |
| 10. Successful LLM raw payload is cleaned under default policy but attempt metadata remains. | PASS. `WorkflowAttempt` and `ToolRunLog` remain; raw payload artifact metadata changes to `metadata_only_cleaned`. |
| 11. Project is soft-deleted and can be restored before permanent deletion. | PASS. Covered by S10. |
| 12. Two Projects contain the same page filename but remain isolated. | PASS. Each Project has separate project.db and workspace; artifact paths are project-relative under different project roots. |
| 13. Export is attempted with unresolved blocking issue and is rejected. | PASS. Export precheck queries unresolved blocking `QualityIssue`; `ExportRecord.status = blocked` records issue ids. |
| 14. Export is attempted with warning only and follows ProcessingProfile policy. | PASS. `ProcessingProfile.allow_warning_export` and snapshot determine whether `ExportRecord` succeeds or is blocked/needs review. |
| 15. User re-runs a TextBlock with unchanged input and config; cache/idempotency prevents duplicate provider call. | PASS. Stage-specific cache keys find existing active result/log/artifact; workflow records reuse/continue decision and avoids provider call. |

Hard invariants check:

- No image BLOBs in SQLite: PASS.
- Original image is immutable: PASS.
- Project data is isolated: PASS.
- Page belongs to Batch; Batch belongs to Project; TextBlock belongs to Page: PASS.
- Detection creates TextBlock: PASS.
- OCRResult and TranslationResult are versioned; user edits create new versions: PASS.
- Active OCR and active Translation are explicit: PASS.
- TranslationResult records glossary_version: PASS.
- WorkflowAttempt metadata is always persisted: PASS.
- WorkflowDecision is persisted: PASS.
- QualityIssue supports discovered_stage and root_stage: PASS.
- ProcessingArtifact records file path, hash, type, and ownership: PASS.
- Failed attempt artifacts are persisted by default: PASS.
- Successful raw payload retention is configurable: PASS.
- Provider adapters do not own persistence: PASS.
- API keys are not stored in project.db: PASS.
- Export checks unresolved blocking issues: PASS.

# 20. Open questions

1. Should provider refusal use `root_stage = provider_policy`, or should `root_stage` be constrained to workflow stages with refusal represented only by `issue_type/error_code`?
2. Should normal export with warnings require explicit user acceptance per export, or can `ProcessingProfile.allow_warning_export` be enough for MVP?
3. What default TTL should apply to debug artifacts when debug retention is enabled?
4. Should failed attempt payload retention be unlimited until project deletion, or should it have a large configurable TTL while still satisfying "persisted by default"?
5. Should `QualityIssue` resolution history be append-only, or is status mutation with timestamps enough for MVP?
6. Should cleanup failures create `QualityIssue` records visible to users, or a separate maintenance log to avoid confusing export quality reports?
7. Should project soft delete physically move the whole project directory to trash immediately, or only mark it and defer movement until app shutdown/no active tasks?
8. Should `ExportRecord` store blocked/warning issue ids through a join table for queryability, or as structured metadata for MVP simplicity?
9. Should OCR crop artifacts be kept by default for review, or treated as rebuildable unless debug/strict profile requests retention?
10. Should page-level translation raw response artifacts link to every `TranslationResult` through a join table, or is the shared `workflow_attempt_id` link sufficient?
