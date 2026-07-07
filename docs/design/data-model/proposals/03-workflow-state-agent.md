# 1. Scope

This proposal focuses on the durable state model needed for one-click processing, restart recovery, partial retry, stale propagation, idempotency, crash recovery, and export gating.

In scope:

- ProcessingTask lifecycle and restart recovery.
- WorkflowAttempt and WorkflowDecision traceability.
- Stage status at Batch, Page, and TextBlock levels.
- Stale propagation after OCR, translation, geometry, glossary, and profile/config changes.
- Idempotency keys and cache reuse boundaries.
- Artifact, ToolRunLog, and QualityIssue relationships needed to explain recovery behavior.
- Placement across app.db and per-project project.db.
- Design-level key fields, relationships, indexes, retention, and migration concerns.

Out of scope:

- SQL DDL, ORM model code, migrations, API handlers, frontend implementation, prompts, provider integrations, and provider-specific algorithms.
- Final data model synthesis, ERD, ADR writing, or editing any final design document.

Decision: model recovery from persisted task, stage, attempt, decision, issue, artifact, and active pointer records rather than from Page status alone.

Rationale: HLD explicitly states restart recovery cannot rely only on Page status. Recovery must know what completed, what was attempted, what artifacts exist, which result version is active, and why the WorkflowLoopEngine stopped or continued.

Rejected alternative: a single coarse `status` column per Page or Batch. It is simpler, but cannot safely support TextBlock-level retry, stale propagation, or crash recovery after partially completed stages.

# 2. Role Bias

As Workflow-State Agent, I bias the design toward:

- Durable, explicit state transitions over inferred state hidden in files.
- Local recovery and partial retry over perfect global orchestration.
- Append-friendly history for attempts, decisions, issues, and result versions.
- Small current-state pointers for UI and workflow efficiency.
- Project-local workflow data to preserve Project isolation.
- Enough idempotency metadata to avoid duplicate OCR/LLM/provider calls.

Trade-off: this creates more records than a minimal CRUD model. The added records are justified only where they explain recovery, quality gates, retry, stale state, or artifact lifecycle.

# 3. Assumptions

- The system uses app.db plus one project.db per Project.
- HLD is preferred over SRS where state lists differ. For example, HLD adds `ready_for_export`, `ready_for_export_with_warnings`, `blocked`, `auto_retrying`, and `stale`; this proposal adopts those because they are needed for workflow recovery and export gates.
- ProcessingTask represents schedulable work owned by WorkflowService/TaskRunner. It is not a provider call record.
- WorkflowAttempt represents one execution attempt of a workflow stage or stage sub-step. It is always persisted, even when payload artifacts are later cleaned.
- WorkflowDecision represents the WorkflowLoopEngine's decision after evaluating attempt outcome, QualityIssue records, profile policy, retry budget, and current state.
- ToolRunLog represents each external tool/provider invocation. A WorkflowAttempt may have zero or more ToolRunLog records.
- Provider adapters return structured outputs/errors only. They do not write project.db, register artifacts, decide fallback, create QualityIssue, or update workflow state.
- ProcessingArtifact records metadata only. Image and large payload bytes remain on the filesystem.
- The MVP may run a single in-process TaskRunner, but the data model should not prevent a later worker process.
- No API key, token, secret, or raw authorization value is stored in project.db, ToolRunLog, WorkflowAttempt, or ProcessingArtifact metadata.

# 4. Proposed entities

| Entity | Responsibility | Workflow-state notes |
| --- | --- | --- |
| Project | Top-level isolation unit for one manga/workflow collection. | app.db has the Project registry and project.db path; project.db stores Project-local workflow data. Soft delete starts here. |
| Batch | Upload/processing group inside a Project. | Holds aggregate processing state and selected/default ProcessingProfile snapshot reference for a run. |
| Page | One uploaded manga image in a Batch. | Holds page order, original image artifact pointer, aggregate page status, stale flags, and active page-level output pointers. |
| TextBlock | Detected text region on a Page. | Primary unit for OCR, translation, cleaning, typesetting, skipping, stale state, and partial retry. |
| OCRResult | Immutable OCR result version for one TextBlock. | New record for provider output or user edit; active OCR pointer drives translation input. |
| TranslationResult | Immutable translation result version for one TextBlock. | Records source hash, context hash, glossary_version, prompt/config hash, lock state, and quality flags. |
| GlossaryTerm | Project-owned glossary entry. | Changes create/update GlossaryVersion and can make downstream translation/typesetting stale by policy. |
| GlossaryVersion | Immutable snapshot identity for Project glossary state. | TranslationResult records the version used; stale checks compare active glossary version with result version. |
| ProcessingTask | Durable schedulable workflow command. | Supports queued/running/paused/cancelled/completed/failed/blocked recovery and idempotent task resume. |
| WorkflowAttempt | Persisted execution attempt metadata for a stage/sub-step. | Records input/config/result hashes, stage, target, attempt number, status, budget use, and artifact/log links. |
| WorkflowDecision | Persisted WorkflowLoopEngine decision. | Records continue/retry/fallback/skip/warning/block/export decisions with rationale and issue links. |
| QualityIssue | Durable quality/export gate issue. | Stores discovered_stage, root_stage, target, severity, blocking flag, status, and suggested_action. |
| ProcessingArtifact | Filesystem artifact metadata. | Stores path, hash, type, owner target, source_step, attempt/tool log linkage, retention class, and cleanup state. |
| ToolRunLog | External tool/provider invocation log. | Records sanitized provider/tool metadata, status, error code, timings, token/cost estimates, and artifact links. |
| ExportRecord | Durable export event/result. | Records export scope, profile policy, artifact, manifest artifact, issue snapshot, and whether export had warnings. |
| ProcessingProfile | Policy bundle for workflow loop behavior. | Controls retry budgets, fallback, skip/warning/block behavior, raw payload retention, and warning export policy. |

Ownership rules:

- WorkflowService owns ProcessingTask lifecycle.
- WorkflowLoopEngine owns WorkflowAttempt, WorkflowDecision, retry/fallback/skip/block decisions, and stage progression.
- QualityCheckService owns QualityIssue detection and root-stage attribution.
- ArtifactService owns ProcessingArtifact path, hash, registration, retention, and cleanup state.
- Repository/DAO owns SQLite persistence.
- Provider adapters own only temporary execution internals and returned structured output.

# 5. P0 / P1 / P2 classification

| Classification | Entities/fields | Decision and rationale |
| --- | --- | --- |
| P0 | Project, Batch, Page, TextBlock, OCRResult, TranslationResult, GlossaryTerm, GlossaryVersion, ProcessingTask, WorkflowAttempt, WorkflowDecision, QualityIssue, ProcessingArtifact, ToolRunLog, ExportRecord, ProcessingProfile. | All are required by SRS/HLD or HARNESS hard invariants for one-click processing, recovery, versioning, artifact traceability, and export blocking. |
| P0 | TextBlock stage statuses: detection, OCR, translation, translation_check, cleaning, typesetting, review. | Required for partial retry and stale propagation without full Batch rerun. |
| P0 | Active OCR and active Translation pointers or equivalent active flags. | Required by hard invariants and user edit behavior. |
| P0 | Idempotency fields for OCR and translation. | Required to avoid duplicate provider calls and cost. |
| P0 | Failed attempt artifact retention and configurable successful raw payload retention. | Required by HARNESS and debug/audit needs. |
| P1 | Batch-level bulk retry summaries, cost rollups, richer progress rollups, failed TextBlock batch retry grouping. | Useful UX and operations features, but derivable from P0 records for MVP. |
| P1 | User-adjustable geometry versioning and explicit layout override records. | SRS marks manual geometry and layout adjustment as P1. P0 still needs stale flags when geometry changes. |
| P1 | Automatic local fallback policy selection records. | MVP may implement manual fallback; the data model should already allow `fallback_provider` WorkflowDecision. |
| P1 | Export manifest artifact and cost/token estimate rollups. | ZIP manifest is P1 in SRS but ExportRecord should allow it. |
| P2 | Multi-Page translation context identity and page-group context records. | SRS/HLD say MVP uses Page-level translation; multi-Page context is later. |
| P2 | Advanced provider orchestration, multi-model UI profiles, vertical Chinese typesetting state. | Not required for MVP workflow-state correctness. |

Decision: keep all required workflow trace entities P0 even if the MVP UI initially hides them.

Rejected alternative: defer WorkflowDecision or ToolRunLog to P1. This would fail provider refusal, retry explanation, and crash recovery scenarios.

# 6. app.db vs project.db placement

| Entity | Placement | Rationale |
| --- | --- | --- |
| Project | app.db registry; optional project-local mirror metadata in project.db | app.db must list/open Projects and know project.db/workspace path. Project-local mirror may help backup/restore but app.db owns global discovery. |
| Batch | project.db | Batch data is Project-isolated. |
| Page | project.db | Page data and artifacts are Project-isolated. |
| TextBlock | project.db | TextBlock data belongs to a Page inside one Project. |
| OCRResult | project.db | OCR versions are Project/Page/TextBlock local. |
| TranslationResult | project.db | Translation versions depend on Project glossary/context. |
| GlossaryTerm | project.db | GlossaryTerm belongs to Project and must not leak across Projects. |
| GlossaryVersion | project.db | Project-local glossary snapshot identity. |
| ProcessingTask | project.db for Project-scoped processing; app.db only for optional global recent task summary | Recovery must work when opening a Project. Project-isolated processing state belongs with the Project. |
| WorkflowAttempt | project.db | Attempts reference local targets, artifacts, issues, and tool logs. |
| WorkflowDecision | project.db | Decisions reference attempts/issues and Project-local profile snapshots. |
| QualityIssue | project.db | Issues target local Batch/Page/TextBlock/result/artifact records. |
| ProcessingArtifact | project.db | Artifact metadata references files under Project workspace. |
| ToolRunLog | project.db | Tool runs reference local attempts/artifacts. Must not store secrets. |
| ExportRecord | project.db | Export history is Project-local. Export files live under Project workspace. |
| ProcessingProfile | app.db for built-in/global/user profiles; project.db for profile snapshots used by tasks | A task must be reproducible even if the global profile changes later. |

Decision: ProcessingTask is stored in project.db, not app.db, for MVP workflow tasks.

Rationale: Project-level recovery should not depend on cross-database joins or a global queue table. A later app.db task index can cache summaries for the home screen without owning recovery.

Rejected alternative: app.db owns all tasks. This helps global scheduling but weakens Project isolation and complicates backup/restore of a Project.

# 7. Key fields

No SQL DDL is proposed here. Field names are conceptual and should be refined during final synthesis.

### Project

- `project_id`, `name`, `status`, `default_source_language`, `default_target_language`.
- `workspace_path` or project directory reference in app.db.
- `project_db_path`, `created_at`, `updated_at`, `last_opened_at`, `last_processed_at`.
- Soft delete: `deleted_at`, `trash_path`, `delete_state`.
- Optional current profile pointer: `default_processing_profile_id`.

Important constraints/indexes:

- app.db unique `project_id`.
- app.db unique active `workspace_path` or project directory path.
- Project names should not need global uniqueness.

### Batch

- `batch_id`, `project_id`, `name`, `source_language`, `target_language`, `page_count`.
- `status`, `progress_summary`, `quality_summary`, `last_processed_at`.
- `default_processing_profile_snapshot_id` or task-level profile snapshot reference.
- `created_at`, `updated_at`, `deleted_at`.

Important constraints/indexes:

- Index by `project_id`, `status`, `last_processed_at`.
- Optional uniqueness for active `(project_id, name)` only if the product wants it; not required for recovery.

### Page

- `page_id`, `project_id`, `batch_id`, `page_index`, `original_filename`.
- `original_image_artifact_id`.
- Active output pointers: `active_cleaned_artifact_id`, `active_typeset_artifact_id`, `active_export_artifact_id`.
- State: `status`, `quality_flags`, `translation_context_hash`, `translation_context_stale`, `has_stale_blocks`.
- Soft delete: `deleted_at`.
- `created_at`, `updated_at`.

Important constraints/indexes:

- Unique active `(batch_id, page_index)` for ordering.
- Index by `batch_id`, `status`.
- Same filenames are allowed in different Projects and Batches.

### TextBlock

- `text_block_id`, `project_id`, `batch_id`, `page_id`.
- Geometry: `bbox`, `polygon`, `mask_artifact_id`, `source_direction`, `reading_order`.
- Detection metadata: `detection_provider`, `detection_model_id`, `detection_confidence`, `detection_quality_flags`.
- Stage states: `detection_status`, `ocr_status`, `translation_status`, `translation_check_status`, `cleaning_status`, `typesetting_status`, `review_status`.
- Active pointers: `active_ocr_result_id`, `active_translation_result_id`, `active_cleaning_artifact_id`, `active_typesetting_artifact_id`.
- Skip/manual flags: `is_skipped`, `skip_reason`, `is_manual_adjusted`.
- Stale flags: `stale_reason`, `stale_since`, `stale_source_result_id`.
- Soft delete: `deleted_at`.

Important constraints/indexes:

- Unique active `(page_id, reading_order)` where not deleted, if reading order is enforced.
- Index by `page_id`, each stage status, and `is_skipped`.

### OCRResult

- `ocr_result_id`, `text_block_id`, `version_number`.
- `source_text`, `source_text_hash`, `ocr_confidence`, `ocr_quality_flags`.
- Provider metadata: `provider`, `model_id`, `tool_version`.
- Input/cache metadata: `input_artifact_id`, `raw_output_artifact_id`, `input_hash`, `config_hash`, `idempotency_key`.
- Provenance: `workflow_attempt_id`, `tool_run_id`, `created_by` (`provider`, `user_edit`, `import`).
- `is_user_edited`, `created_at`.

Important constraints/indexes:

- Unique `(text_block_id, version_number)`.
- Unique or lookup index on `(text_block_id, idempotency_key)` for cache reuse.
- Immutable after creation except non-semantic cleanup flags if final synthesis allows them.

### TranslationResult

- `translation_result_id`, `text_block_id`, `version_number`.
- Source identity: `source_ocr_result_id`, `source_text_hash`.
- `translation_text`, `translation_text_hash`, `used_terms`, `confidence`, `needs_review`, `quality_flags`, `error_code`.
- Provider/prompt metadata: `provider`, `model_id`, `prompt_template_version`, `generation_config_hash`.
- Context identity: `context_hash`, `glossary_version_id`, `glossary_terms_hash`, `page_translation_attempt_group_id`.
- Provenance: `workflow_attempt_id`, `tool_run_id`, `created_by`.
- User controls: `is_user_edited`, `is_locked`.
- `idempotency_key`, `created_at`.

Important constraints/indexes:

- Unique `(text_block_id, version_number)`.
- Lookup index on translation idempotency key fields.
- Must record `glossary_version_id` even if the glossary is empty.

### GlossaryTerm

- `term_id`, `project_id`, `source_text`, `target_text`, `term_type`, `reading`, `aliases`, `case_sensitive`, `priority`, `status`.
- `created_from_text_block_id`, `created_by_user`, `note`.
- `created_at`, `updated_at`, `deleted_at`.

Important constraints/indexes:

- Index by `project_id`, `source_text`, `status`.
- Do not require global uniqueness.

### GlossaryVersion

- `glossary_version_id`, `project_id`, `version_number`, `terms_hash`.
- `created_reason`, `created_from_term_id`, `created_at`.
- Optional summary counts for active/deleted terms.

Important constraints/indexes:

- Unique `(project_id, version_number)`.
- Index `(project_id, terms_hash)` for detecting no-op edits.

### ProcessingTask

- `processing_task_id`, `project_id`, `batch_id`, nullable `page_id`, nullable `text_block_id`.
- `task_type` (`batch_process`, `page_process`, `textblock_retry`, `export`, etc.).
- `requested_scope`, `requested_stages`, `resume_policy`.
- `status` (`queued`, `running`, `pausing`, `paused`, `cancel_requested`, `cancelled`, `completed`, `failed`, `blocked`).
- `current_stage`, `current_target_type`, `current_target_id`.
- `profile_snapshot_id`, `idempotency_key`.
- `created_by`, `created_at`, `started_at`, `heartbeat_at`, `finished_at`.
- `parent_task_id` for optional split/retry lineage.
- `last_workflow_decision_id`, `last_error_code`.

Important constraints/indexes:

- Index by `status`, `heartbeat_at`, `project_id`, `batch_id`.
- Unique active idempotency key for duplicate start prevention when appropriate.

### WorkflowAttempt

- `workflow_attempt_id`, `processing_task_id`, `project_id`, `batch_id`, nullable `page_id`, nullable `text_block_id`.
- `stage` (`import`, `detection`, `ocr`, `translation`, `translation_check`, `cleaning`, `typesetting`, `export`).
- `target_type`, `target_id`, `attempt_number`.
- `provider_role`, `provider_name`, `model_id`, `tool_version`.
- `input_hash`, `config_hash`, `context_hash`, `glossary_version_id`, `idempotency_key`.
- `status` (`planned`, `running`, `succeeded`, `failed`, `cancelled`, `skipped`, `reused_cached`, `stale_invalidated`).
- `started_at`, `finished_at`, `duration_ms`.
- `error_code`, `sanitized_error_message`.
- `retry_budget_before`, `retry_budget_after`.
- Artifact links or via ProcessingArtifact: `input_artifact_id`, `output_artifact_id`, `raw_request_artifact_id`, `raw_response_artifact_id`.

Important constraints/indexes:

- Unique `(processing_task_id, stage, target_type, target_id, attempt_number)`.
- Index by `(target_type, target_id, stage, status)`.
- All metadata persists even if raw payload artifacts are cleaned.

### WorkflowDecision

- `workflow_decision_id`, `processing_task_id`, `workflow_attempt_id`.
- `project_id`, `batch_id`, nullable `page_id`, nullable `text_block_id`.
- `stage`, `target_type`, `target_id`.
- `decision_type` (`continue`, `retry_same_stage`, `fallback_provider`, `retry_upstream_stage`, `skip_target`, `mark_warning`, `block`, `finish_ready_for_export`, `finish_ready_for_export_with_warnings`).
- `rationale_code`, `rationale_summary`.
- `quality_issue_ids` or join table reference.
- `next_stage`, `next_target_type`, `next_target_id`.
- `retry_budget_before`, `retry_budget_after`.
- `profile_policy_snapshot`, `created_at`.

Important constraints/indexes:

- Index by `processing_task_id`, `created_at`.
- Index by target for UI/debug trace.

### QualityIssue

- `quality_issue_id`, `project_id`, `batch_id`, nullable `page_id`, nullable `text_block_id`.
- `target_type`, `target_id`.
- `discovered_stage`, `root_stage`.
- `issue_type`, `severity` (`info`, `warning`, `error`, `blocking`), `is_blocking`.
- `status` (`open`, `accepted`, `resolved`, `superseded`, `ignored_by_policy`).
- `message_key`, `sanitized_message`, `suggested_action`.
- `workflow_attempt_id`, `workflow_decision_id`, nullable `artifact_id`.
- `created_at`, `resolved_at`, `resolved_by`.

Important constraints/indexes:

- Index unresolved blocking issues by Project/Batch/Page/TextBlock.
- Index by `root_stage` and `discovered_stage`.

### ProcessingArtifact

- `artifact_id`, `project_id`, nullable `batch_id`, nullable `page_id`, nullable `text_block_id`.
- `artifact_type` (`original_image`, `crop`, `mask`, `raw_ocr_output`, `raw_llm_request`, `raw_llm_response`, `cleaned_image`, `typeset_image`, `export_image`, `export_zip`, `quality_report`, etc.).
- `file_path`, `file_hash`, `file_size`, `mime_type`.
- `source_step`, `workflow_attempt_id`, `tool_run_id`.
- `retention_class` (`must_keep`, `failed_attempt`, `debug`, `successful_payload`, `temporary`, `export`).
- `cleanup_state` (`active`, `eligible`, `cleaned`, `missing`, `trashed`).
- `contains_sensitive_content`, `is_debug_artifact`.
- `created_at`, `cleaned_at`.

Important constraints/indexes:

- Index by owner target and artifact type.
- Unique `file_hash` is optional only within a Project; same content across Projects should remain isolated by path/metadata.

### ToolRunLog

- `tool_run_id`, `project_id`, nullable `batch_id`, nullable `page_id`, nullable `text_block_id`.
- `workflow_attempt_id`, `stage`, `tool_name`, `tool_version`, `provider_name`, `model_id`.
- `input_hash`, `config_hash`, `status`, `error_code`, `sanitized_error_message`.
- `input_artifact_id`, `output_artifact_id`.
- Optional usage metrics: `estimated_input_tokens`, `estimated_output_tokens`, `estimated_cost`.
- `started_at`, `finished_at`.

Important constraints/indexes:

- Index by `workflow_attempt_id`, target, status, started_at.
- Logs must be sanitized; no API keys, tokens, request headers with secrets, or raw credentials.

### ExportRecord

- `export_record_id`, `project_id`, nullable `batch_id`, nullable `page_id`.
- `export_scope`, `status`, `export_format`.
- `processing_profile_snapshot_id`, `warning_policy`.
- `export_artifact_id`, `manifest_artifact_id`.
- `issue_snapshot_hash`, `blocking_issue_count`, `warning_issue_count`.
- `is_forced_or_incomplete`, `created_at`, `finished_at`.

Important constraints/indexes:

- Index by Project/Batch/Page and created_at.
- Export is rejected if unresolved blocking issues exist unless a later design explicitly allows an incomplete/forced advanced export path.

### ProcessingProfile

- In app.db: `processing_profile_id`, `name`, `profile_type` (`built_in`, `user`), `settings`, `created_at`, `updated_at`.
- In project.db snapshot: `profile_snapshot_id`, source profile identity, full serialized policy, `policy_hash`, `created_at`.
- Policy fields include retry budgets, fallback allowance, warning export allowance, debug retention, successful payload retention, blocking behavior, and auto-skip rules.

Important constraints/indexes:

- app.db unique built-in profile names.
- project.db profile snapshots immutable after creation.

# 8. Relationships

Core containment:

- Project has many Batches.
- Batch belongs to Project and has many Pages.
- Page belongs to Batch and has many TextBlocks.
- TextBlock belongs to Page and has many OCRResults and TranslationResults.
- GlossaryTerm belongs to Project.
- GlossaryVersion belongs to Project.

Workflow trace:

- ProcessingTask belongs to Project and may target Batch, Page, or TextBlock.
- ProcessingTask has many WorkflowAttempts.
- WorkflowAttempt may have many ToolRunLogs, ProcessingArtifacts, QualityIssues, and WorkflowDecisions.
- WorkflowDecision belongs to a ProcessingTask and usually follows one WorkflowAttempt.
- QualityIssue targets Project, Batch, Page, TextBlock, result, or artifact through `target_type` and `target_id`, with denormalized Project/Batch/Page/TextBlock ids for efficient filtering.

Artifact trace:

- ProcessingArtifact belongs to one Project and may be scoped to Batch/Page/TextBlock.
- Page points to original, active cleaned, active typeset, and active export artifacts.
- TextBlock points to active cleaning/typesetting artifacts when block-level artifacts exist.
- OCRResult points to crop/input and raw output artifacts.
- TranslationResult points indirectly through WorkflowAttempt/ToolRunLog, with optional raw request/response artifacts on the attempt.
- ExportRecord points to export image/zip and manifest artifacts.

Profile trace:

- ProcessingTask references an immutable ProcessingProfile snapshot.
- WorkflowAttempt and WorkflowDecision may repeat relevant profile policy hashes to make debugging independent of later profile changes.

Relationship decision: use explicit typed targets plus denormalized owner ids for workflow records.

Rationale: target_type/target_id allows one attempt/issue/decision model to cover Batch, Page, TextBlock, result, and export scopes. Denormalized Project/Batch/Page/TextBlock ids keep common UI and recovery queries simple.

Rejected alternative: separate attempt/decision/issue tables for each target type. This is more strictly relational but too repetitive and makes cross-stage workflow traces harder to query.

# 9. Versioning rules

OCRResult:

- Every provider OCR output creates a new OCRResult version unless an existing matching idempotency key is reused.
- Every user OCR edit creates a new OCRResult version with `created_by = user_edit` and `is_user_edited = true`.
- Existing OCRResult rows are immutable after creation, except optional retention metadata on linked artifacts.
- OCRResult version numbers are local to one TextBlock.

TranslationResult:

- Every provider translation output creates one TranslationResult per TextBlock returned by a Page-level translation attempt.
- Every user translation edit creates a new TranslationResult version with `created_by = user_edit`.
- TranslationResult records the active OCR/source hash, context_hash, generation_config_hash, prompt_template_version, provider/model identity, and GlossaryVersion used at creation time.
- Existing TranslationResult rows are immutable after creation, except optional lock/active handling if final synthesis chooses active flags instead of pointer fields.
- TranslationResult version numbers are local to one TextBlock.

GlossaryVersion:

- Every semantic glossary change creates a new GlossaryVersion with a new version number and terms_hash.
- No-op saves may avoid creating a new version if terms_hash is unchanged.
- TranslationResult keeps the older GlossaryVersion even after glossary changes.

WorkflowAttempt and WorkflowDecision:

- Attempts and decisions are append-only audit records.
- A retry creates a new WorkflowAttempt; it does not overwrite the failed attempt.
- A later decision can supersede prior issues or stale attempts but does not delete them.

ProcessingProfile:

- app.db ProcessingProfile can be edited by the user.
- A ProcessingTask captures an immutable project.db ProcessingProfile snapshot at task creation/start.
- Workflow recovery uses the snapshot, not the mutable global profile.

Decision: results are immutable versions, while current active state is represented separately.

Rationale: immutable versions preserve traceability and support rollback/review. Separate active pointers make UI and workflow inputs unambiguous.

Rejected alternative: update OCRResult/TranslationResult rows in place. This loses user edit history and makes stale propagation unverifiable.

# 10. Active pointer rules

Required active pointers:

- TextBlock has `active_ocr_result_id`.
- TextBlock has `active_translation_result_id`.
- Page has active original, cleaned, typeset, and export artifact pointers where applicable.
- TextBlock may have active cleaning/typesetting artifact pointers for block-level rerendering.

OCR active pointer:

- After successful OCR, active OCR points to the newest accepted OCRResult unless an existing locked/user-selected OCRResult should remain active by explicit user choice.
- After user OCR edit, active OCR must point to the user-edited result.
- Changing active OCR marks translation, translation_check, cleaning if it depends on text masks, and typesetting stale according to section 11.

Translation active pointer:

- After successful translation, active translation points to the newest accepted TranslationResult unless a locked translation is active and the user did not request override.
- After user translation edit, active translation points to the user-edited result.
- Locked active translations are not overwritten by automatic retry.
- Changing active translation marks typesetting stale.

Artifact active pointers:

- Original image artifact is set at import and never replaced or overwritten.
- Active cleaned/typeset artifacts are updated only after successful stage completion or explicit user acceptance of warning output.
- Failed attempt artifacts are linked to attempts but do not become active output pointers unless the WorkflowLoopEngine explicitly marks a warning/preview artifact as usable.

Active pointer consistency:

- At most one active OCR and one active Translation per TextBlock.
- Pointer-based active state is preferred over multiple `is_active` flags.
- If final synthesis uses active flags, it must enforce equivalent uniqueness.

Decision: prefer active pointer columns on TextBlock/Page over active flags on result rows.

Rationale: pointers are simpler to reason about during recovery, avoid partial uniqueness complexities, and make the current effective result explicit from the owning object.

Rejected alternative: `is_active` boolean on each OCRResult and TranslationResult. It is workable but easier to corrupt if two rows become active.

# 11. State and stale rules

### State vocabulary

Batch aggregate status should support:

- `created`, `imported`, `queued`, `processing`, `auto_checking`, `auto_retrying`, `paused`, `cancelled`, `reviewing`, `partially_failed`, `failed`, `ready_for_export`, `ready_for_export_with_warnings`, `completed`, `exported`, `blocked`.

Page aggregate status should support:

- `uploaded`, `detecting`, `detected`, `ocr_processing`, `ocr_done`, `translating`, `translated`, `translation_checking`, `cleaning`, `cleaned`, `typesetting`, `typeset_done`, `auto_checking`, `auto_retrying`, `reviewing`, `partially_failed`, `ready_for_export`, `ready_for_export_with_warnings`, `completed_with_warnings`, `failed`, `skipped`, `exported`, `blocked`.

TextBlock stage statuses should support:

- `pending`, `running`, `done`, `failed`, `skipped`, `needs_review`, `stale`, `locked`.

TextBlock uses separate stage columns:

- `detection_status`
- `ocr_status`
- `translation_status`
- `translation_check_status`
- `cleaning_status`
- `typesetting_status`
- `review_status`

### Stage transition rules

- `pending -> running -> done` for normal completion.
- `running -> failed` when an attempt fails and no immediate retry succeeds.
- `failed -> pending` only through explicit retry/resume decision.
- `done -> stale` when upstream active input changes.
- `stale -> pending` when user or workflow requests recomputation.
- `done -> locked` applies only where lock is meaningful, mainly active translation/review state.
- `skipped` is not failure; it can contribute warning quality issues.

### Stale propagation rules

User edits active OCR:

- Create new OCRResult.
- Set TextBlock.active_ocr_result_id to the new result.
- Set TextBlock.translation_status = `stale`.
- Set TextBlock.translation_check_status = `stale`.
- Set TextBlock.typesetting_status = `stale`.
- Set TextBlock.review_status = `needs_review`.
- Set Page.translation_context_stale = true and Page.has_stale_blocks = true.
- Create or update QualityIssue with root_stage = `ocr` and discovered_stage = `review` or `translation_check` if appropriate.

User edits active translation:

- Create new TranslationResult.
- Set TextBlock.active_translation_result_id to the new result.
- Set TextBlock.typesetting_status = `stale`.
- Set TextBlock.review_status = `needs_review` until accepted or rerendered.
- Set Page.has_stale_blocks = true.

User changes TextBlock geometry/mask:

- Set TextBlock.cleaning_status = `stale`.
- Set TextBlock.typesetting_status = `stale`.
- If crop input changes, set OCR status stale only if the OCR source depends on the changed geometry/crop.
- Set Page.has_stale_blocks = true.

Glossary changes:

- Create new GlossaryVersion if terms_hash changes.
- Existing TranslationResults keep old glossary_version.
- Active translations are not automatically overwritten.
- Mark Page.translation_context_stale = true for Pages whose active TranslationResult glossary_version differs from current glossary version and whose ProcessingProfile requires glossary freshness.
- For strict profiles, create warning or needs_review QualityIssue for stale glossary translations.

ProcessingProfile/config changes:

- Existing results remain valid historical records.
- New tasks compute new config_hash/idempotency keys.
- If the user explicitly applies new config to existing work, matching downstream stage statuses become stale by scope.

Provider refusal:

- ToolRunLog.status = failed with provider refusal error code.
- WorkflowAttempt.status = failed.
- QualityIssue records `provider_refusal` or specific translation refusal type, discovered_stage and root_stage = `translation`.
- WorkflowDecision chooses fallback_provider, mark_warning, skip_target, or block according to profile.

Crash recovery:

- On startup, any ProcessingTask with `running` status and stale heartbeat becomes `paused` or `recovering` by service policy.
- Any WorkflowAttempt with `running` status and no completed ToolRunLog/artifact after crash is marked `failed` or `abandoned_after_crash` by recovery, preserving metadata.
- Completed stage statuses with valid active pointers/artifacts are not rerun.
- `running` TextBlock stage statuses are reconciled from latest attempt, active result/artifact, and issue state before resuming.

Decision: state recovery must reconcile multiple records instead of trusting a single column.

Rationale: crashes can occur after provider output, after artifact registration, after active pointer update, or after status update. Recovery needs enough evidence to determine whether to reuse, retry, or mark abandoned.

Rejected alternative: set all running stages back to pending on restart. This is safe but causes duplicate provider calls and may lose precise failure evidence.

# 12. Artifact relationships

Artifact ownership:

- Every ProcessingArtifact belongs to exactly one Project.
- Batch/Page/TextBlock ids are nullable but should be populated whenever the artifact scope is known.
- File paths are Project-workspace-relative or canonicalized under the Project workspace to prevent path traversal and Project leakage.

Required artifact links:

- Project/Page import: original image artifact with `retention_class = must_keep`.
- Detection/TextBlock: detection visualization and masks where generated; masks used for cleaning should be artifacts.
- OCRResult: input crop artifact and raw OCR output artifact where retained.
- Translation WorkflowAttempt: raw request/response artifacts according to retention policy; failed invalid JSON response must be retained.
- Cleaning: mask and cleaned image artifacts.
- Typesetting: preview/attempt artifact and active typeset image artifact.
- QualityIssue: optional quality report/visualization artifact.
- ExportRecord: exported image or ZIP artifact and optional manifest artifact.

Retention classes:

- `must_keep`: original images, active cleaned/typeset/export artifacts, required masks.
- `failed_attempt`: failed provider/tool raw payloads and debug evidence; retained by default.
- `successful_payload`: successful raw OCR/LLM payloads; retention controlled by ProcessingProfile/global setting.
- `debug`: extra artifacts retained only when debug mode is enabled.
- `temporary`: re-creatable crops/previews that can be cleaned.
- `export`: exported output retained until export deletion/project deletion.

Decision: keep failed raw payload artifacts by default, but allow successful raw payload cleanup.

Rationale: failure debugging and provider refusal evidence are important; successful LLM payloads can be large and sensitive, so default cleanup reduces storage/sensitive-data exposure while preserving attempt metadata.

Rejected alternative: keep all raw payloads forever. This is excellent for debugging but increases storage use and privacy risk.

# 13. Idempotency and cache keys

General rule:

- Idempotency keys are computed outside provider adapters by WorkflowService/WorkflowLoopEngine using normalized inputs, config, provider identity, model/tool version, profile policy, and relevant artifact hashes.
- Provider adapters do not decide cache reuse.

ProcessingTask idempotency:

- Key components: task_type, Project, scope target, requested stages, profile policy hash, resume policy, and explicit user request id if needed.
- Prevents accidental duplicate queued/running tasks for the same scope.
- Explicit user "rerun anyway" must create a new key or bypass cache according to profile.

Detection idempotency:

- Key components: original image artifact hash, detection provider, model/tool version, detection config hash, profile policy relevant to auto-skip/thresholds.

OCR idempotency:

- Key components: input crop/mask/original artifact hash, bbox/polygon geometry hash, OCR provider, model_id, tool_version, OCR config_hash, source_language.
- If the key matches an existing successful OCRResult and the user did not force rerun, reuse it and record a WorkflowAttempt with status `reused_cached` or a WorkflowDecision explaining reuse.

Translation idempotency:

- Key components: source_text_hash, Page context_hash, glossary_version_id or terms_hash, provider, model_id, prompt_template_version, generation_config_hash, target language, relevant ProcessingProfile translation policy.
- Page-level translation may produce a group key for the full request plus per-TextBlock TranslationResult keys.
- Single-block retranslation must include full Page context and target TextBlock id.

Cleaning idempotency:

- Key components: original or current base image artifact hash, mask artifact hash, cleaning provider/mode, model/tool version, cleaning config_hash, TextBlock geometry hash.

Typesetting idempotency:

- Key components: base cleaned image artifact hash, active TranslationResult id or translation_text_hash, TextBlock geometry hash, font config hash, typesetting provider/tool version, typesetting config_hash.

Export idempotency:

- Key components: active Page typeset artifact hashes, page order, export format/config, issue snapshot hash, warning export policy.

Cache lookup decision:

- Reusing cached successful output is a WorkflowLoopEngine decision, recorded as either WorkflowAttempt `reused_cached` or WorkflowDecision `continue` with cache rationale.
- Cache reuse must not silently skip state updates; stage status and active pointers must still be reconciled.

Rejected alternative: provider-level cache only. It hides reuse decisions from workflow state and cannot explain why a task did not call a provider.

# 14. Deletion and retention policy

Project deletion:

- Project uses soft delete first: app.db Project status/deleted_at is set, Project workspace is moved to trash or marked for trash.
- project.db records remain recoverable before permanent deletion.
- Permanent deletion requires explicit confirmation and removes project.db plus Project workspace artifacts.

Batch/Page/TextBlock deletion:

- Prefer soft delete for Batch, Page, and TextBlock records.
- Deleted TextBlocks no longer participate in active processing/export but historical attempts/artifacts remain until retention cleanup or permanent Project deletion.
- Deleting a Batch/Page marks related active outputs and exports as not current; artifacts become trash-eligible unless retained by policy.

Result deletion:

- OCRResult and TranslationResult are not individually hard-deleted in normal workflow. They may become inactive/superseded.
- User edits create new versions instead of overwriting or deleting old versions.

Artifact cleanup:

- Original images are must-keep until permanent Project deletion.
- Active cleaned/typeset/export artifacts are retained while current.
- Failed attempt artifacts are retained by default.
- Successful raw payload artifacts can be cleaned under ProcessingProfile/global retention settings while WorkflowAttempt metadata remains.
- Cleaned artifacts are represented by ProcessingArtifact.cleanup_state = `cleaned`; attempts/tool logs keep references with nullable/missing artifact status rather than losing metadata.

QualityIssue cleanup:

- Issues are resolved/superseded, not deleted during normal workflow.
- Export gates check unresolved blocking issues only.

Export retention:

- ExportRecord remains after export so users can see export history.
- Export files can be deleted or regenerated later; the record should reflect missing/cleaned artifact state.

Decision: use soft delete plus artifact cleanup states instead of immediate hard delete.

Rationale: recovery, audit, and user restore require metadata to survive accidental deletion. Filesystem cleanup can happen asynchronously and should be explainable.

Rejected alternative: immediately remove records and files. It saves space but breaks restore, traceability, and crash-safe cleanup.

# 15. Migration concerns

- Every database has its own schema_migrations table: app.db for global/project registry/profile settings, project.db for Project-local workflow schema.
- project.db migrations must be independent so older Projects can be opened and upgraded.
- Additive nullable fields should be preferred for early MVP evolution, especially around status enums and artifact metadata.
- Status enums should be represented so new statuses can be added without destructive data migration.
- ProcessingProfile snapshots protect old tasks from global profile changes across migrations.
- WorkflowAttempt and WorkflowDecision append-only records may grow quickly; migrations should support indexes on target/stage/status early.
- Artifact path migrations must handle moved Project workspaces by storing paths relative to the Project root where possible.
- If active pointer columns are added after results exist, migration must infer active OCR/Translation from the latest active flag or latest version with successful status and write the pointer once.
- If retention cleanup removes files before metadata fields exist, migration should mark artifacts `missing` rather than deleting attempts/logs.
- TranslationResult glossary_version should be mandatory going forward; migration for legacy rows should create an initial GlossaryVersion representing the current or empty glossary.

Risk: changing state vocabulary after data exists can strand tasks in unknown states.

Mitigation: define a compatibility mapping for deprecated statuses and keep recovery tolerant of unknown non-terminal statuses by pausing/blocking with a clear migration issue.

# 16. Risks

- State model complexity may slow implementation if every stage tries to update too many records synchronously.
- Crash recovery reconciliation can be subtle when a crash occurs between artifact write, artifact registration, active pointer update, and status update.
- Page-level translation creates one provider call but many TranslationResult records; partial invalid output needs careful mapping to TextBlocks.
- Idempotency keys can become wrong if normalization omits a real input such as glossary version, prompt template version, or geometry hash.
- Too much raw payload retention can expose sensitive local content; too little retention can make failures hard to debug.
- Soft delete and trash handling can diverge between app.db, project.db, and filesystem if operations are interrupted.
- If active pointers are not transactionally updated with status changes, UI can show inconsistent current results.
- ProcessingProfile snapshots may duplicate policy data, but without them old workflow decisions become hard to explain.
- Overusing generic target_type/target_id can reduce referential integrity unless supported by clear repository-level validation.

# 17. Rejected alternatives

| Alternative | Rejected because |
| --- | --- |
| Single `status` column on Page drives all recovery | Cannot represent TextBlock-level partial retry, stale downstream stages, skipped blocks, or crash recovery after partial success. |
| Store workflow state only in ProcessingTask logs | Logs are poor active state. UI/export/retry need queryable stage statuses, active pointers, and issue records. |
| Provider adapters persist artifacts and logs directly | Violates architecture constraints and scatters persistence decisions outside WorkflowLoopEngine/ArtifactService. |
| In-place update OCR/translation text | Violates versioning and user edit invariants; old results and glossary versions would be lost. |
| Global app.db owns all ProcessingTasks and WorkflowAttempts | Complicates Project backup/restore and weakens Project isolation. |
| Store image/payload BLOBs in SQLite | Violates hard invariant and is unsuitable for large manga images/debug payloads. |
| Cache only by source text for translation | Ignores page context, glossary version, prompt/config, provider/model, and can reuse wrong translations. |
| Delete failed artifacts by default | Fails debugging/audit scenario for invalid LLM JSON/provider refusals. |
| Automatically overwrite locked translations during rerun | Violates user control and could destroy accepted edits. |
| Treat skipped TextBlock as failed | Incorrect for MVP; complex areas may be skipped with warning and still allow export-with-warnings. |

# 18. Decisions intentionally left to later rounds

- Exact enum spellings and whether they live as constrained strings, lookup tables, or application-level constants.
- Whether active OCR/Translation is implemented by owner pointers, active flags, or both for query performance.
- Exact JSON shape for profile snapshot policy and whether some fields are normalized.
- Exact issue taxonomy, message keys, and user-facing wording.
- Exact artifact directory layout and path normalization rules.
- Whether WorkflowDecision-to-QualityIssue is a join table or stored list of ids.
- Whether page-level translation attempts get a first-class `PageTranslationAttemptGroup` entity or are represented by WorkflowAttempt/context_hash only.
- Exact handling of forced/incomplete export with blocking issues. HLD mentions advanced forced export as possible, but HARNESS requires normal export rejection.
- Exact transaction boundaries for stage completion across result rows, artifact rows, active pointers, and status updates.
- Exact old-task recovery policy for stale `running` tasks: `paused`, `recovering`, or `failed_after_crash`.
- Whether Project-local mirror metadata duplicates app.db Project metadata for portable backup.

# 19. Validation against all scenarios in HARNESS.md

### S1: Happy path

PASS.

Project is created in app.db with isolated project.db/workspace. Batch and Page are created in project.db. Original image is registered as a must-keep ProcessingArtifact. Detection creates TextBlocks with geometry and detection_status done. OCR creates OCRResult versions and active OCR pointers. Page-level translation creates TranslationResult versions for TextBlocks, each recording source hash, context_hash, and glossary_version. Cleaning and typesetting create artifacts and active output pointers. QualityIssue records remain resolved or non-blocking. WorkflowDecision records `finish_ready_for_export`. Export checks unresolved blocking issues, writes ExportRecord and export artifact.

### S2: Restart after OCR

PASS.

Completed OCRResult rows, active OCR pointers, OCR stage statuses, WorkflowAttempts, ToolRunLogs, and artifacts survive restart. A stale/running ProcessingTask is paused/recovered. WorkflowLoopEngine sees OCR done with valid active OCR and matching idempotency keys, so translation continues without rerunning OCR.

### S3: OCR edit

PASS.

User edit creates a new OCRResult. TextBlock.active_ocr_result_id points to it. Old OCRResult remains immutable. Translation, translation_check, and typesetting statuses become stale; Page.translation_context_stale and Page.has_stale_blocks become true. Later retranslation uses the new OCR source hash and creates new TranslationResult versions.

### S4: Translation edit

PASS.

User edit creates a new TranslationResult. TextBlock.active_translation_result_id points to it. Old TranslationResult remains immutable. Typesetting status becomes stale and Page.has_stale_blocks becomes true. Re-typesetting uses the edited active translation.

### S5: Provider refusal

PASS.

TranslationProvider returns a standardized refusal error. ToolRunLog records failed sanitized provider invocation. WorkflowAttempt records failed stage metadata and idempotency inputs. QualityIssue records discovered_stage/root_stage = translation, issue_type such as `translation_provider_refused`, and blocking severity as determined by policy. WorkflowDecision records fallback_provider, mark_warning, skip_target, or block according to ProcessingProfile.

### S6: Complex cleaning skipped

PASS.

Cleaning attempt or pre-check creates/open QualityIssue with root_stage = cleaning and warning severity. WorkflowDecision records skip_target or mark_warning. TextBlock.cleaning_status = skipped and typesetting can use original/base image policy or leave original region unchanged. Page can aggregate to ready_for_export_with_warnings, not pure ready_for_export.

### S7: Typeset overflow

PASS.

Typesetting attempt stores preview/attempt artifact. QualityIssue records `typeset_overflow`, discovered_stage/root_stage = typesetting, warning or blocking depending on profile. WorkflowDecision can mark_warning or block. If warning, active preview/typeset artifact is retained and Page remains previewable as ready_for_export_with_warnings.

### S8: Glossary changed

PASS.

GlossaryTerm edit creates a new GlossaryVersion. Existing TranslationResult rows keep their original glossary_version_id. Stale policy compares active translations with current glossary version and can mark translation_context_stale or create needs_review issues without mutating old translations.

### S9: Failed raw payload

PASS.

Invalid LLM JSON creates a failed ToolRunLog and failed WorkflowAttempt. Raw response artifact is registered with retention_class = failed_attempt and retained by default. WorkflowDecision records retry_same_stage, fallback_provider, needs_review, or block after QualityCheckService creates the issue.

### S10: Project soft delete

PASS.

app.db Project gets deleted_at/delete_state and workspace is moved to trash or marked for trash. project.db records and artifacts remain recoverable before permanent deletion. Permanent deletion requires explicit confirmation and removes project.db/workspace files.

Additional GOAL scenarios:

- Scenario 11, Project restore before permanent deletion: PASS through soft delete and trash state.
- Scenario 12, same page filename in two Projects: PASS because Page and ProcessingArtifact are Project-scoped and paths are under separate Project workspaces.
- Scenario 13, export with unresolved blocking issue rejected: PASS because ExportRecord creation requires unresolved blocking QualityIssue check.
- Scenario 14, warning-only export follows ProcessingProfile: PASS because ProcessingProfile snapshot controls warning export policy and ExportRecord stores issue snapshot.
- Scenario 15, unchanged TextBlock rerun avoids duplicate provider call: PASS because OCR/translation idempotency keys include input/config/provider/model/context/glossary values and WorkflowAttempt can record `reused_cached`.

# 20. Open questions

1. Should active OCR/Translation be implemented only as TextBlock pointer columns, or should result rows also include an `is_active` flag for easier querying?
2. What exact recovery status should replace stale `running` tasks after crash: `paused`, `recovering`, or `failed_after_crash`?
3. Should page-level translation attempts be represented by a dedicated grouping entity, or is WorkflowAttempt plus context_hash sufficient for MVP?
4. How strict should glossary-change stale propagation be by default: warning-only, needs_review, or automatic retranslation suggestion?
5. Should forced/incomplete export with blocking issues exist in MVP advanced mode, or should MVP only reject all normal exports with blocking issues?
6. Which successful raw payloads should be retained by default: none, small OCR outputs only, or profile-dependent?
7. Should Batch/Page aggregate status be fully persisted, fully derived, or persisted with reconciliation from TextBlock states?
8. How much denormalized owner data should generic workflow records keep before it becomes a consistency risk?
9. Should Project-local ProcessingProfile snapshots be shared across tasks with the same policy hash or copied per task?
10. What exact transaction boundaries are required for artifact registration, result creation, active pointer update, and stage status update?
