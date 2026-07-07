# 1. Scope

This proposal defines the domain model boundaries for the manga translation and basic typesetting workflow. It is design-only and covers:

- Project / Batch / Page / TextBlock ownership.
- OCRResult and TranslationResult versioning.
- Active result selection and stale propagation.
- Project-owned glossary and glossary versioning.
- Workflow, quality, artifact, task, export, and profile records needed for restart recovery and traceability.
- app.db versus per-project project.db placement.
- Idempotency keys, deletion behavior, retention policy, and migration concerns.

This proposal intentionally does not define SQL DDL, ORM classes, API schemas, frontend behavior, provider integrations, prompts, migrations, or implementation code.

No material conflict was found between the required documents. Where SRS and HLD differ in detail, this proposal treats HLD as the more specific architecture source. Example: HLD refines Batch/Page status names and adds ready_for_export / blocked workflow outcomes.

# 2. Role Bias

As Domain Model Agent, I bias toward clear ownership, recoverability, and minimal domain concepts.

Primary bias:

- The Project is the isolation and deletion boundary.
- Batch, Page, and TextBlock form the content ownership spine.
- Result rows are historical versions, not mutable working buffers.
- Active pointers are explicit and separate from result history.
- WorkflowAttempt, WorkflowDecision, ToolRunLog, QualityIssue, and ProcessingArtifact explain what happened, but they do not own business content.
- Provider adapters never own persistence, artifact paths, retry policy, fallback policy, or active result selection.

Rejected bias:

- A highly normalized event-sourced model for every field change. It improves audit depth but is too heavy for MVP.
- A flat task-log model where the current state must be reconstructed from logs. It hurts restart recovery and ordinary UI queries.

# 3. Assumptions

- IDs should be stable opaque IDs, preferably globally unique, so project data can be moved or restored without ID collisions.
- Every project has one project.db and one project workspace directory.
- app.db stores the Project registry and global configuration; project.db stores project content and workflow history.
- project.db rows still carry project_id as an isolation guard even though a project.db is already project-scoped.
- File paths in project.db should be relative to the project workspace root where practical, so a project directory can move.
- ProcessingProfile definitions live in app.db, but each ProcessingTask/WorkflowAttempt records an immutable profile snapshot hash or snapshot artifact sufficient for recovery.
- User edits to OCR or translation create new result versions. They do not mutate previous result text.
- Geometry edits on TextBlock are represented by a geometry revision/hash on TextBlock rather than a separate GeometryResult entity for MVP.
- GlossaryVersion is an immutable version boundary. A compact snapshot artifact is allowed when needed for reproducibility, but the core model does not require a full term-history table in P0.
- API keys, tokens, and secrets are never stored in project.db, ToolRunLog, WorkflowAttempt payloads, debug artifacts, or examples.

# 4. Proposed entities

| Entity | Responsibility | Ownership boundary | Key rationale |
| --- | --- | --- | --- |
| Project | Registry record for one manga/workflow project, including workspace path, default languages, default profile, lifecycle status, and project.db location. | Root aggregate and isolation boundary. | Prevents cross-project leakage and supports per-project backup, restore, and deletion. |
| Batch | A user upload/processing collection within a Project, such as a chapter or uploaded set. Owns Page ordering and batch-level processing summary. | Owned by Project. | Separates import batches and preserves page order without making Project a god object. |
| Page | One manga image in a Batch. Owns page-level status, quality summary, active page image outputs, and TextBlocks. | Owned by Batch. | Page is the natural restart and preview unit; translation context is page-level in MVP. |
| TextBlock | One detected text region on a Page. Owns geometry, reading order, skip/manual flags, phase statuses, active OCR/translation pointers, and local retry state. | Owned by Page. | TextBlock is the local repair unit for OCR, translation, cleaning, and typesetting. |
| OCRResult | Immutable versioned OCR output for one TextBlock. | Owned by TextBlock. | Supports provider retry, fallback, user edits, stale checks, and auditability. |
| TranslationResult | Immutable versioned translation output for one TextBlock, generated from a page-level context but stored per TextBlock. | Owned by TextBlock. | Supports page-level translation while enabling single-block review, edit, retry, and typeset. |
| GlossaryTerm | Current Project-owned term entry. | Owned by Project. | Terms must not leak across Projects and are core translation constraints. |
| GlossaryVersion | Immutable Project glossary version boundary. | Owned by Project. | TranslationResult can record which glossary state influenced it. |
| ProcessingTask | User/system requested processing job targeting Batch, Page, or TextBlock. | Owned by Project, references target aggregate. | Enables async execution, pause/cancel/resume, and UI progress. |
| WorkflowAttempt | One attempt to run a workflow stage for a target. | Owned by ProcessingTask or Project workflow history. | Preserves retry metadata even when output artifacts are cleaned. |
| WorkflowDecision | WorkflowLoopEngine decision after an attempt or quality check. | Owned by ProcessingTask/WorkflowAttempt. | Explains continue/retry/fallback/skip/warning/block outcomes. |
| QualityIssue | A quality, provider, data, or export issue with discovered/root stage attribution. | Owned by Project and targeted to Project/Batch/Page/TextBlock/Result/Artifact. | Allows warnings, blocking export checks, root-cause tracing, and user review. |
| ProcessingArtifact | Metadata for a filesystem artifact. | Owned by Project, optionally scoped to Batch/Page/TextBlock/Attempt/ToolRun. | Keeps image and payload files out of SQLite while preserving traceability. |
| ToolRunLog | One external or local provider/tool invocation. | Owned by WorkflowAttempt or Project history. | Supports debugging, cost estimation, idempotency, and provider refusal records. |
| ExportRecord | One export attempt/result for a Page or Batch. | Owned by Project, target Page or Batch. | Records export eligibility checks, output artifact, manifest artifact, and rejected exports. |
| ProcessingProfile | Configurable policy for workflow budgets, strictness, fallback, warning export, and artifact retention. | Definition in app.db; execution snapshot in project.db workflow records. | Keeps workflow behavior explicit and recoverable without storing secrets. |

Aggregate-like ownership decisions:

- Project owns Batch, GlossaryTerm, GlossaryVersion, ProcessingTask, WorkflowAttempt, WorkflowDecision, QualityIssue, ProcessingArtifact, ToolRunLog, and ExportRecord.
- Batch owns Page order and batch processing summary, but does not own glossary or profile definitions.
- Page owns TextBlock collection and active page-level output artifacts.
- TextBlock owns OCRResult and TranslationResult histories and is the active-result selection boundary.
- Results do not own artifacts globally. They reference ProcessingArtifact rows managed by ArtifactService.
- Workflow records explain changes; they do not replace explicit domain state fields needed for fast recovery.

# 5. P0 / P1 / P2 classification

| Classification | Entities / capabilities | Notes |
| --- | --- | --- |
| P0 | Project, Batch, Page, TextBlock, OCRResult, TranslationResult, GlossaryTerm, GlossaryVersion, ProcessingTask, WorkflowAttempt, WorkflowDecision, QualityIssue, ProcessingArtifact, ToolRunLog, ExportRecord, ProcessingProfile. | All required for one-click processing, restart recovery, traceability, idempotency, and export blocking. |
| P0 | Active OCR and active Translation pointers on TextBlock. | Required by result versioning and user edit flows. |
| P0 | Page active original/cleaned/typeset artifact pointers. | Required to avoid image paths as ad hoc state and to preserve original images. |
| P0 | TextBlock phase statuses and stale flags. | Required because Page status alone cannot support restart recovery. |
| P0 | Glossary version number and terms hash on TranslationResult. | Required for translation cache keys and stale detection. |
| P0 | Failed attempt artifact persistence and configurable successful payload retention. | Required by HARNESS S9 and GOAL quality bar. |
| P1 | Manual TextBlock geometry editing with richer geometry history. | MVP can use geometry_revision/hash; later rounds may add GeometryRevision if needed. |
| P1 | Term candidate extraction and quick-add provenance from selected translation spans. | SRS marks candidates as P1. |
| P1 | Cost/token accounting on ToolRunLog and profile budget warnings. | Useful but not necessary for first end-to-end loop. |
| P1 | Batch manifest export details and forced/incomplete export controls. | ZIP export is P0; richer manifest is P1 in SRS. |
| P2 | Multi-page translation context, context packs, and chapter-level cache keys. | HLD makes page-level context MVP. |
| P2 | Advanced profile variants for style, vertical Chinese typesetting, and provider orchestration UI. | Outside first data model minimum but should be enabled by extensible fields. |

# 6. app.db vs project.db placement

| Database | Entity/data | Placement decision |
| --- | --- | --- |
| app.db | Project | Stores project_id, name, workspace path, project_db_path, default languages, default_profile_id, status, timestamps, soft-delete metadata, and recent/open metadata. |
| app.db | ProcessingProfile | Stores global and project-scoped profile definitions, profile versions, policy fields, provider config references, and retention policy. No secrets. |
| app.db | Provider/global settings | Stores provider configuration metadata and references to secret storage. API keys are not in project.db. |
| app.db | schema_migrations | Tracks app.db schema version. |
| project.db | Batch, Page, TextBlock | Stores project content hierarchy and processing state. |
| project.db | OCRResult, TranslationResult | Stores immutable version histories and dependency hashes. |
| project.db | GlossaryTerm, GlossaryVersion | Stores Project-owned glossary and immutable version boundaries. |
| project.db | ProcessingTask | Stores project-local tasks, targets, status, and profile snapshot references. |
| project.db | WorkflowAttempt, WorkflowDecision | Stores workflow audit and loop decisions. |
| project.db | QualityIssue | Stores quality/reporting/export-blocking issues. |
| project.db | ProcessingArtifact | Stores metadata for project workspace files. No file BLOBs. |
| project.db | ToolRunLog | Stores sanitized tool invocation records. |
| project.db | ExportRecord | Stores export attempts, outputs, and rejection reasons. |
| project.db | schema_migrations | Tracks project.db schema version per project. |

Rationale:

- Project registry belongs in app.db so the application can list and open Projects without attaching every project.db.
- Content belongs in project.db so Project backup, restore, and deletion are isolated.
- ProcessingProfile definitions are global enough to live in app.db, but task execution must store profile_version, profile_hash, and optionally a redacted profile snapshot artifact in project.db. This avoids "profile changed after crash" recovery ambiguity.

Rejected alternatives:

- Store all Projects in one SQLite database. Rejected because it weakens Project isolation and makes backup/delete riskier.
- Store profile definitions only in project.db. Rejected because global defaults and provider selections are application settings, not manga content.
- Store image paths directly on Page as authoritative state. Rejected because ArtifactService must own file paths, hashes, retention, and cleanup.

# 7. Key fields

The following are key fields and constraints, not SQL DDL.

| Entity | Key fields | Important constraints and indexes |
| --- | --- | --- |
| Project | project_id, name, workspace_path, project_db_path, default_source_language, default_target_language, default_profile_id, status, created_at, updated_at, deleted_at, trash_path | project_id unique in app.db. Name need not be globally unique. Index status and updated_at for recent lists. |
| Batch | batch_id, project_id, name, source_language, target_language, page_count, status, quality_summary, last_processed_at, created_at, updated_at, deleted_at | Index project_id/status. Page order is owned by Page.page_index. |
| Page | page_id, project_id, batch_id, page_index, original_artifact_id, active_cleaned_artifact_id, active_typeset_artifact_id, status, quality_flags, has_stale_blocks, translation_context_hash, created_at, updated_at, deleted_at | Unique active page_index within batch among non-deleted Pages. Index batch_id/page_index and status. |
| TextBlock | text_block_id, project_id, batch_id, page_id, reading_order, bbox, polygon, geometry_revision, geometry_hash, source_direction, detection_confidence, detection_provider, active_mask_artifact_id, active_ocr_result_id, active_translation_result_id, translation_lock_result_id, phase statuses, is_skipped, skip_reason, is_manual_adjusted, deleted_at | Index page_id/reading_order, page_id/phase statuses, active result pointers. Geometry changes increment revision/hash. |
| OCRResult | ocr_result_id, project_id, text_block_id, version_number, parent_ocr_result_id, source_type, source_text, confidence, provider, model_id, tool_version, input_artifact_id, raw_output_artifact_id, input_hash, config_hash, geometry_hash, tool_run_id, workflow_attempt_id, quality_flags, is_user_edited, created_at | Unique version_number per TextBlock. Index text_block_id/version_number and input_hash/config_hash/provider/model_id for cache lookup. |
| TranslationResult | translation_result_id, project_id, text_block_id, version_number, parent_translation_result_id, source_type, source_ocr_result_id, source_text_hash, translation_text, provider, model_id, prompt_template_version, glossary_version_id, glossary_version_number, glossary_terms_hash, context_hash, generation_config_hash, used_terms, confidence, needs_review, quality_flags, error_code, tool_run_id, workflow_attempt_id, is_user_edited, created_at | Unique version_number per TextBlock. Index cache key fields: source_text_hash, context_hash, glossary_version_number, provider, model_id, prompt_template_version, generation_config_hash. |
| GlossaryTerm | term_id, project_id, source_text, target_text, term_type, reading, aliases, case_sensitive, priority, status, created_from_text_block_id, created_by_user, note, created_at, updated_at, deleted_at | Index project_id/source_text/status. Prevent exact duplicate active source_text + target_text + term_type where practical. |
| GlossaryVersion | glossary_version_id, project_id, version_number, terms_hash, term_count, snapshot_artifact_id, created_reason, created_at | Unique version_number per Project. Index project_id/version_number. |
| ProcessingTask | task_id, project_id, target_type, target_id, requested_stage_range, profile_id, profile_version, profile_hash, profile_snapshot_artifact_id, status, priority, pause_requested, cancel_requested, started_at, finished_at, created_at, updated_at | Index project_id/status and target_type/target_id. |
| WorkflowAttempt | attempt_id, project_id, task_id, stage, target_type, target_id, attempt_number, provider_name, provider_version, model_id, input_hash, config_hash, profile_hash, status, started_at, finished_at, error_code, metadata_artifact_id | Unique attempt_number within task/stage/target. Index task_id/stage/status. |
| WorkflowDecision | decision_id, project_id, task_id, attempt_id, decision_type, from_stage, to_stage, target_type, target_id, reason_code, based_on_quality_issue_ids, retry_budget_before, retry_budget_after, fallback_provider, created_at | Index task_id/created_at and target_type/target_id. |
| QualityIssue | issue_id, project_id, target_type, target_id, discovered_stage, root_stage, issue_type, severity, is_blocking, status, message_code, suggested_action, related_attempt_id, related_tool_run_id, related_artifact_id, created_at, resolved_at, accepted_at | Index unresolved blocking issues by project_id/target/status/is_blocking. |
| ProcessingArtifact | artifact_id, project_id, batch_id, page_id, text_block_id, attempt_id, tool_run_id, artifact_type, source_step, file_path, file_hash, file_size, mime_type, retention_class, is_debug, contains_sensitive_content, status, created_at, deleted_at | Index project_id/artifact_type, page_id, text_block_id, file_hash. file_path is relative to project root when possible. |
| ToolRunLog | tool_run_id, project_id, task_id, attempt_id, stage, target_type, target_id, tool_name, tool_version, provider_name, model_id, input_artifact_id, output_artifact_id, input_hash, config_hash, status, error_code, sanitized_error_message, started_at, finished_at, token_estimate, cost_estimate | Index attempt_id and provider/status. Sanitized fields only. |
| ExportRecord | export_id, project_id, target_type, target_id, export_type, profile_id, profile_hash, status, output_artifact_id, manifest_artifact_id, issue_snapshot_artifact_id, blocking_issue_count, warning_issue_count, page_order_hash, created_at, finished_at, rejected_reason | Index project_id/target/status and created_at. Rejected export attempts may have no output artifact. |
| ProcessingProfile | profile_id, scope, project_id_if_scoped, name, version, provider_refs, retry_budgets, quality_strictness, allow_warning_export, auto_skip_complex_regions, retention_policy, debug_artifact_policy, created_at, updated_at, disabled_at | Stored in app.db. Unique active name per scope. No secrets. |

Implementation-ready field decisions:

- Use artifact_id references for images and payloads. Do not duplicate file_path as authoritative state on Page or Result rows.
- Store enough dependency hashes on result and artifact records to determine stale state without opening large files.
- Keep human-visible error text sanitized. Raw provider output, if retained, must be a ProcessingArtifact marked debug/sensitive where appropriate.

# 8. Relationships

Relationship summary:

- Project 1 -> many Batch.
- Project 1 -> many GlossaryTerm.
- Project 1 -> many GlossaryVersion.
- Project 1 -> many ProcessingTask, WorkflowAttempt, WorkflowDecision, QualityIssue, ProcessingArtifact, ToolRunLog, ExportRecord.
- Batch many -> 1 Project.
- Batch 1 -> many Page.
- Page many -> 1 Batch.
- Page 1 -> many TextBlock.
- Page references ProcessingArtifact for original_artifact_id, active_cleaned_artifact_id, and active_typeset_artifact_id.
- TextBlock many -> 1 Page.
- TextBlock 1 -> many OCRResult.
- TextBlock 1 -> many TranslationResult.
- TextBlock references active_ocr_result_id and active_translation_result_id.
- TextBlock references active_mask_artifact_id when a current mask exists.
- OCRResult many -> 1 TextBlock and optionally references parent_ocr_result_id.
- TranslationResult many -> 1 TextBlock, optionally references parent_translation_result_id, and references source_ocr_result_id.
- TranslationResult many -> 1 GlossaryVersion by glossary_version_id or version number.
- ProcessingTask targets Batch, Page, or TextBlock.
- WorkflowAttempt belongs to a ProcessingTask and targets a stage/target.
- WorkflowDecision belongs to a ProcessingTask and usually follows a WorkflowAttempt.
- ToolRunLog belongs to a WorkflowAttempt when a provider/tool was invoked.
- ProcessingArtifact can be linked to Page, TextBlock, WorkflowAttempt, ToolRunLog, ExportRecord, or GlossaryVersion snapshot.
- QualityIssue can target Batch, Page, TextBlock, OCRResult, TranslationResult, ProcessingArtifact, ToolRunLog, WorkflowAttempt, or ExportRecord.
- ExportRecord targets Page or Batch and references output artifacts.

Ownership rules:

- Deleting or restoring a Project cascades at the project workspace boundary, not by crossing into other project.db files.
- Deleting a Batch soft-deletes its Pages, TextBlocks, result histories, project-scoped artifacts, and export records.
- Deleting a Page soft-deletes its TextBlocks and page-scoped artifacts but keeps audit rows until permanent deletion.
- Deleting a TextBlock means user removed or disabled that region. Its history remains until permanent cleanup.
- Result rows are never reassigned to another TextBlock.
- GlossaryTerm never belongs to Batch/Page/TextBlock, but it may reference created_from_text_block_id as provenance.

Rejected relationship alternatives:

- TranslationResult owned by Page only. Rejected because user edits and local retry happen at TextBlock granularity.
- Global glossary shared by default. Rejected because SRS requires Project glossary isolation.
- WorkflowAttempt as owner of OCRResult/TranslationResult. Rejected because results are domain state for TextBlock; attempts are audit.

# 9. Versioning rules

OCRResult:

- Each OCR execution or user OCR edit creates a new OCRResult version for the TextBlock.
- source_text, provider metadata, dependency hashes, input artifact references, and raw output references are immutable once created.
- User edits set source_type = user_edit and is_user_edited = true, and reference parent_ocr_result_id where applicable.
- Provider retry/fallback results set source_type = provider and reference tool_run_id/workflow_attempt_id.
- Invalid provider output may create ToolRunLog, WorkflowAttempt, QualityIssue, and failed artifacts without creating OCRResult.

TranslationResult:

- Each translation generation, shortening attempt, fallback result, or user translation edit creates a new TranslationResult version for the TextBlock.
- translation_text, source_ocr_result_id, source_text_hash, context_hash, glossary version, provider metadata, prompt version, and generation config hash are immutable once created.
- User edits set source_type = user_edit and is_user_edited = true, and reference parent_translation_result_id where applicable.
- Page-level translation calls create one WorkflowAttempt and one ToolRunLog, then zero or more TranslationResult rows, one per valid returned TextBlock.
- Invalid JSON or provider refusal may produce no TranslationResult for affected TextBlocks, but still must produce ToolRunLog, WorkflowAttempt, QualityIssue, WorkflowDecision, and failed artifacts where available.

GlossaryVersion:

- Any create/edit/delete/status change to an active GlossaryTerm creates a new GlossaryVersion.
- GlossaryVersion records version_number, terms_hash, term_count, and created_reason.
- A snapshot_artifact_id is recommended when the version needs reproducible prompt context after later term edits/deletes.
- TranslationResult records the glossary version used at generation time and is not rewritten when the glossary changes.

TextBlock geometry:

- TextBlock geometry is versioned lightly by geometry_revision and geometry_hash.
- Manual adjustment or redetection that changes geometry increments revision/hash and marks dependent OCR, cleaning, and typesetting state stale.
- A later round may add a full TextBlockGeometryRevision entity if manual layout history becomes important.

Rationale:

- Versioned results support audit, rollback, manual edit history, and idempotent cache lookup.
- Keeping active selection outside result payload lets old versions remain immutable.

Rejected alternatives:

- Overwrite OCR/translation rows on edit. Rejected because it destroys recovery and auditability.
- A single JSON blob per TextBlock containing all result history. Rejected because it weakens querying, migration, and active pointer integrity.

# 10. Active pointer rules

Decision:

- Use explicit active pointers on TextBlock for OCRResult and TranslationResult.
- Use explicit active artifact pointers on Page for original, cleaned, and typeset page images.
- Keep result rows immutable; active selection is mutable domain state on the owning entity.

Rules:

- TextBlock.active_ocr_result_id identifies the currently selected OCRResult for review and downstream translation.
- TextBlock.active_translation_result_id identifies the currently selected TranslationResult for review and downstream typesetting.
- TextBlock.translation_lock_result_id, when set to active_translation_result_id, prevents automatic workflow from replacing that active translation.
- Locked translations can only be superseded by explicit user action or a task mode that clearly says locked results may be replaced.
- A newly generated result can be stored without becoming active if it fails quality checks or requires user review.
- WorkflowLoopEngine updates active pointers only after the relevant QualityCheckService result and WorkflowDecision.
- User edits create a new version and immediately select it as active.
- Active pointer updates should be atomic with phase-status updates and any related WorkflowDecision.

Effective versus selected:

- "Selected active" means the row the UI should show as current.
- "Export-effective active" means the selected active row is not stale, matches current upstream dependency hashes, and is not blocked by unresolved QualityIssue.
- When upstream state changes, active pointers may remain for user context, but downstream stages become stale and are not export-effective.

Page active artifact rules:

- Page.original_artifact_id is set on import and never changed except restore/repair operations. Original image files are immutable.
- Page.active_cleaned_artifact_id points to the current cleaned image artifact, if any.
- Page.active_typeset_artifact_id points to the current typeset preview/export candidate image, if any.
- ExportRecord uses Page.active_typeset_artifact_id only if export preconditions pass.

Rejected alternatives:

- Use only is_active flags on OCRResult/TranslationResult. Rejected because partial uniqueness and stale detection are harder, especially during migrations and failed updates.
- Clear downstream active pointers on stale. Rejected because the UI loses useful context for review. Stale status is enough to prevent unsafe export/use.

# 11. State and stale rules

State model:

- Batch has a persisted summary status for UI and task progress.
- Page has a persisted summary status for UI and page-level workflow.
- TextBlock has phase statuses as the recovery source of truth:
  - detection_status
  - ocr_status
  - translation_status
  - translation_check_status
  - cleaning_status
  - typesetting_status
  - review_status
- Valid phase values should include pending, running, done, failed, skipped, needs_review, stale, and locked where applicable.
- Restart recovery must read TextBlock phase statuses, active result pointers, WorkflowAttempt, WorkflowDecision, ProcessingArtifact, and QualityIssue. It must not rely only on Page.status.

Stale triggers:

| Trigger | Required state impact |
| --- | --- |
| User edits OCR | New OCRResult becomes active. translation_status = stale, translation_check_status = stale, typesetting_status = stale, review_status = needs_review. Page.has_stale_blocks = true and Page.translation_context_hash becomes stale. |
| User edits translation | New TranslationResult becomes active. typesetting_status = stale, review_status = needs_review. Page.has_stale_blocks = true. |
| User changes TextBlock geometry | geometry_revision/hash changes. ocr_status may become stale if crop changed. cleaning_status = stale and typesetting_status = stale. translation may remain selected but becomes export-ineffective if OCR dependency is stale. |
| User changes reading_order | Page.translation_context_hash becomes stale. Active TranslationResults remain selected, but page-level translation context is stale and TranslationCheck may raise warning/needs_review. |
| User marks TextBlock skipped | Remaining stages for that block become skipped. Page may become ready_for_export_with_warnings, not pure ready_for_export. |
| User unskips TextBlock | Relevant phase statuses reset to pending or stale based on available active upstream results. |
| GlossaryTerm changes | New GlossaryVersion is created. TranslationResults keep old glossary_version. Results using changed terms become glossary_stale or needs_review based on profile; unrelated results may remain usable with a page/project warning. |
| Provider refusal | ToolRunLog and WorkflowAttempt fail with provider_refusal. QualityIssue is created with discovered_stage = translation and root_stage = provider or translation. WorkflowDecision decides fallback, warning, skip, or block. |
| QualityIssue resolved/accepted | Export eligibility is recomputed. Accepted warning may allow export if profile permits. Blocking issue must be resolved or explicitly forced by a later design path. |

QualityIssue rules:

- discovered_stage records where the issue was detected.
- root_stage records the suspected cause, such as detection, ocr, translation, cleaning, typesetting, provider, export, filesystem, or config.
- status should distinguish open, resolved, accepted_warning, ignored_nonblocking, and superseded.
- Normal export is blocked by any unresolved blocking issue in the target Page/Batch scope.

Rationale:

- Stale status makes dependency changes explicit without deleting historical result rows.
- Separate discovered/root stages let TypesettingCheck attribute overflow to translation_too_long rather than only typesetting.

# 12. Artifact relationships

ArtifactService owns artifact path, hash, registration, retention, and cleanup. Provider adapters may use temporary files but must not write official workspace paths or insert ProcessingArtifact records.

ProcessingArtifact ownership:

- Every artifact belongs to Project.
- Artifacts may additionally reference Batch, Page, TextBlock, WorkflowAttempt, ToolRunLog, GlossaryVersion, or ExportRecord context.
- artifact_type should distinguish original_image, detection_output, detection_visualization, crop_image, mask, ocr_raw_output, translation_request, translation_response, cleaned_image, typeset_image, export_image, export_zip, export_manifest, quality_report, attempt_payload, debug_bundle, and log_bundle.
- retention_class should distinguish required, failed_attempt, successful_payload, debug, temporary, export, and trash_pending.
- is_debug and contains_sensitive_content must be explicit because debug artifacts may include original images, OCR text, translations, provider requests, and provider responses.

Required artifact relationships:

- Page.original_artifact_id -> original image artifact. This file is immutable.
- TextBlock.active_mask_artifact_id -> current mask artifact, when available.
- OCRResult.input_artifact_id -> crop or input artifact used by OCR, when persisted.
- OCRResult.raw_output_artifact_id -> raw OCR provider output, when persisted.
- TranslationResult may reference request/response artifacts through ToolRunLog/WorkflowAttempt rather than directly duplicating file links.
- Page.active_cleaned_artifact_id -> current cleaned page image.
- Page.active_typeset_artifact_id -> current typeset page image.
- ToolRunLog.input_artifact_id/output_artifact_id -> sanitized or raw payload artifacts according to retention policy.
- ExportRecord.output_artifact_id and manifest_artifact_id -> export output files.
- GlossaryVersion.snapshot_artifact_id -> optional glossary snapshot used for reproducible translation context.

Retention decisions:

- Original images, active cleaned images, active typeset images, masks needed for current state, export outputs, quality reports, failed attempt artifacts, and workflow metadata are P0 retained.
- Successful raw LLM payload artifacts are configurable and may be deleted under default policy after metadata and hashes are saved.
- Failed LLM JSON response artifacts are retained by default.
- Temporary crops can be deleted if they are reconstructable and not required by current debug/quality policy.

Rejected alternatives:

- Store images or large payloads as SQLite BLOBs. Rejected by hard invariant.
- Let each stage choose arbitrary output paths. Rejected because cleanup, hashing, and recovery require central ArtifactService control.

# 13. Idempotency and cache keys

Idempotency rule:

- Re-running a stage with the same effective input, config, provider/tool identity, and relevant upstream versions must not duplicate provider calls unless the user explicitly requests force rerun.

Stage keys:

| Stage | Idempotency/cache key inputs | Reuse behavior |
| --- | --- | --- |
| Import | original file hash, file size, normalized file metadata, Batch/Page user intent | Same file may appear in multiple Projects or Pages. Do not collapse user-intended duplicate Pages. Artifact storage may dedupe internally later. |
| Detection | Page.original_artifact hash, detector provider, model/tool version, detection config hash | If matching TextBlock set and artifacts exist, skip provider call and reuse. |
| OCR | TextBlock geometry_hash, crop/input_hash, OCR provider, model_id, tool_version, config_hash | Reuse matching OCRResult unless force OCR or upstream geometry/image changed. |
| Page translation | ordered active OCR source hashes, reading_order, context_hash, glossary_version/terms_hash, provider, model_id, prompt_template_version, generation_config_hash | Reuse matching TranslationResults. Single-block rerun still includes page context and target TextBlock ID in context hash. |
| Cleaning | original/working image hash, mask hash, TextBlock geometry_hash, cleaner provider/tool version, cleaning config hash | Reuse matching cleaned artifact when current dependencies match. |
| Typesetting | active cleaned artifact hash, active TranslationResult ID/hash, geometry_hash, font config hash, typesetting provider/tool version, layout config hash | Reuse matching typeset artifact unless translation/geometry/font/config changed. |
| Export | active typeset artifact hashes, page_order_hash, export config hash, profile warning policy hash, unresolved issue snapshot hash | Reuse/reject according to issue state and target output settings. |

Cache lookup location:

- Result rows and ProcessingArtifact hashes are the primary cache records.
- WorkflowAttempt and ToolRunLog explain whether a provider call happened.
- A separate cache table is not required in P0. It can be added later if lookup performance or cross-project caching becomes a requirement.

Provider refusal:

- Refusal is not a successful cache hit for future processing unless the same provider/config/input is retried and the WorkflowLoopEngine policy says previous refusal should block or choose fallback.
- Refusal still contributes to attempt history and retry budget.

Rejected alternatives:

- Cache translation only by source_text. Rejected because page context, glossary version, prompt version, provider, and generation config all affect output.
- Treat duplicate image filename as duplicate page. Rejected because two Projects or Pages can legally share filenames while remaining isolated.

# 14. Deletion and retention policy

Project deletion:

- Project delete is soft delete by default.
- app.db Project.status/deleted_at records deletion.
- The project workspace is either moved to trash or marked trash_pending, preserving project.db and files for restore.
- Permanent deletion requires explicit confirmation and removes project.db, artifacts, exports, and project-local trash.

Batch/Page/TextBlock deletion:

- Batch, Page, and TextBlock delete should be soft delete first.
- Soft-deleted content is excluded from normal processing and export but can be restored while Project remains restorable.
- Result histories, WorkflowAttempt, WorkflowDecision, ToolRunLog, QualityIssue, and ProcessingArtifact records remain until permanent cleanup to preserve recovery context.

Glossary deletion:

- GlossaryTerm delete is status/deleted_at based.
- Deleting or restoring a term creates a new GlossaryVersion.
- Old TranslationResults keep the glossary_version used at creation.

Artifact cleanup:

- Original images are never overwritten and are retained until permanent Project/Page deletion.
- Failed attempt artifacts are retained by default.
- Successful raw payload artifacts may be cleaned by retention policy after hashes, tool metadata, and WorkflowAttempt metadata remain.
- Debug artifacts are retained only according to explicit debug policy and must be marked is_debug and contains_sensitive_content when applicable.
- Active artifacts cannot be cleaned while referenced by active Page/TextBlock pointers or export records.
- Cleaned or typeset artifacts superseded by newer versions may move to trash or be retained based on profile/project retention settings.

Export deletion:

- ExportRecord remains as history even if output artifact is deleted, with artifact status showing deleted.
- Rejected export attempts may be retained to explain why export was blocked.

Rationale:

- Soft delete protects ordinary users from losing local projects accidentally.
- Retention policy controls disk growth without sacrificing failed-attempt diagnosis.

# 15. Migration concerns

Migration readiness decisions:

- app.db and every project.db need independent schema_migrations records.
- app.db must record each Project's project_db_schema_version or last_opened_schema_version for safe open/migrate prompts.
- Migrations should be project-by-project and resumable because users may have many projects.
- Use stable enum values and avoid renaming statuses casually. Add new values rather than rewriting old audit records.
- Additive fields should be nullable or backfilled from existing artifact/result records.
- Active pointer migrations must verify each pointer target belongs to the same TextBlock/Page/Project.
- Artifact path migrations should operate on relative paths where possible and verify file_hash before rewriting metadata.
- ProcessingProfile changes require profile versioning. Old ProcessingTask rows must keep profile_hash/snapshot references.
- Result immutability means migrations should not rewrite result payload text. If correction is needed, create migration metadata or a new version, depending on later policy.
- If future multi-page context is added, TranslationResult can keep context_hash while a new ContextPack entity is introduced without changing TextBlock ownership.

Potential backfill paths:

- If early Page rows store original_image_path directly, migrate by creating ProcessingArtifact rows and replacing Page path fields with artifact IDs.
- If early TranslationResult rows lack glossary_version_id, backfill to the Project glossary version active at created_at or mark as unknown_glossary_version with a QualityIssue.
- If early active flags are used, migrate to TextBlock active pointer fields by selecting the newest active result per TextBlock and flagging conflicts.

Rejected migration approach:

- One global migration that opens and rewrites all project.db files at application startup. Rejected because it can make startup slow and failure-prone.

# 16. Risks

| Risk | Impact | Mitigation in this proposal |
| --- | --- | --- |
| Active pointer and stale status diverge | Export might use outdated translation/typeset output. | Define export-effective active as pointer plus dependency/stale/issue checks. |
| Geometry changes are under-versioned | Harder to audit manual layout changes. | Use geometry_revision/hash in P0; leave full GeometryRevision as P1 if needed. |
| GlossaryVersion without full snapshot can limit reproducibility | Old translation context may be hard to reconstruct after term edits. | Allow snapshot_artifact_id and require terms_hash/version on TranslationResult. |
| Workflow tables become too large | Long projects with many retries/debug payloads may grow quickly. | Retention classes and successful payload cleanup; keep metadata compact. |
| Page-level translation stored per TextBlock can obscure page call boundary | Harder to see which results came from one LLM response. | Link TranslationResult to shared WorkflowAttempt/ToolRunLog/context_hash. |
| Overly strict stale marking after glossary edits | Users may see too many warnings. | Use profile policy and used_terms to distinguish direct term impact from general version mismatch. |
| Soft delete plus filesystem trash can drift from DB state | Restore/delete can fail if files are moved manually. | Store artifact status, file_hash, trash_path, and validate on restore. |
| Secrets accidentally appear in logs/artifacts | Security and privacy issue. | Sanitized ToolRunLog only; debug artifacts marked sensitive; no API keys in project.db. |

# 17. Rejected alternatives

1. Single mutable OCR/translation row per TextBlock.
   - Rejected because user edits, retry, fallback, stale relationships, and audit history require versioning.

2. Page-level TranslationResult containing all translated blocks.
   - Rejected because local review, edit, lock, and typeset operate at TextBlock level. Page-level call context is captured by context_hash and WorkflowAttempt instead.

3. Active flags only on result rows.
   - Rejected because pointers on TextBlock make ownership and recovery clearer and avoid multiple-active cleanup problems.

4. Store original/cleaned/typeset image paths directly on Page as authoritative fields.
   - Rejected because ArtifactService owns path/hash/retention and files must be uniformly traceable.

5. Global glossary with Project overrides.
   - Rejected because SRS requires Project glossary isolation and ordinary users need predictable term behavior per manga.

6. Provider adapters write ProcessingArtifact and ToolRunLog records directly.
   - Rejected because provider adapters must not access the database or own artifact lifecycle.

7. Reconstruct current workflow state only from WorkflowAttempt/Decision logs.
   - Rejected because restart recovery and UI queries need explicit current state and active pointers.

8. Hard delete content immediately.
   - Rejected because SRS/HLD expect recoverability and safe local workspace behavior.

9. Store API key or provider secret snapshots in ProcessingProfile.
   - Rejected because API keys must not be stored in project.db or logs, and profiles should reference provider config without secrets.

# 18. Decisions intentionally left to later rounds

- Exact enum vocabulary for every status, issue_type, artifact_type, retention_class, and decision_type.
- Whether GlossaryVersion snapshot is stored as JSON in SQLite or as a ProcessingArtifact for MVP.
- Whether TextBlock geometry needs a full GeometryRevision entity in P1.
- Exact Page.translation_context_hash construction and whether it includes accepted stale translations as context.
- Exact rules for glossary_stale severity when glossary changes after translation.
- Whether forced_export / incomplete_export is supported in MVP or only a later advanced mode.
- Exact profile defaults for retry budgets, warning export, debug artifact retention, and local fallback.
- Whether cross-project artifact deduplication is ever allowed. This proposal assumes no cross-project dependency for MVP.
- Exact cost/token accounting fields for ToolRunLog.
- Exact permanent deletion grace period and trash directory layout.

# 19. Validation against all scenarios in HARNESS.md

### S1: Happy path

PASS.

Flow:

Project in app.db points to project.db and workspace. Batch is created in project.db. Page is created with original_artifact_id referencing immutable original image ProcessingArtifact. Detection creates TextBlock rows. OCR creates OCRResult versions and sets TextBlock.active_ocr_result_id. Page-level translation creates WorkflowAttempt/ToolRunLog plus per-TextBlock TranslationResult rows and active_translation_result_id pointers. Cleaning creates masks and cleaned image artifacts. Typesetting creates active typeset artifact. ExportRecord checks unresolved blocking QualityIssue rows, then references export image or ZIP artifact.

### S2: Restart after OCR

PASS.

OCRResult rows, active_ocr_result_id pointers, TextBlock.ocr_status, WorkflowAttempt metadata, ToolRunLog, and artifacts persist in project.db. On restart, WorkflowLoopEngine sees OCR done and matching idempotency keys, so it resumes translation without re-running OCR.

### S3: OCR edit

PASS.

User edit creates a new OCRResult with source_type = user_edit and parent_ocr_result_id. TextBlock.active_ocr_result_id moves to the new version. Existing TranslationResult rows remain. translation_status, translation_check_status, and typesetting_status become stale. Page.has_stale_blocks and translation context stale markers are set.

### S4: Translation edit

PASS.

User edit creates a new TranslationResult with source_type = user_edit and parent_translation_result_id. TextBlock.active_translation_result_id moves to the new version. Existing TranslationResult rows remain. typesetting_status becomes stale and review_status becomes needs_review until re-typeset or accepted.

### S5: Provider refusal

PASS.

Translation provider refusal creates sanitized ToolRunLog, WorkflowAttempt with failed/refused status, QualityIssue with discovered_stage = translation and root_stage = provider or translation, and WorkflowDecision. WorkflowLoopEngine uses ProcessingProfile to decide fallback_provider, warning, skip, or block. Provider adapter does not decide fallback or persist state.

### S6: Complex cleaning skipped

PASS.

CleaningCheck creates QualityIssue such as cleaning_complex_background with warning severity unless profile marks it blocking. TextBlock.cleaning_status becomes skipped and skip_reason is recorded. Page can become ready_for_export_with_warnings, not pure ready_for_export. Skipped block is visible in quality report.

### S7: Typeset overflow

PASS.

Typesetter can create a preview artifact even when overflow occurs. QualityIssue records issue_type = typeset_overflow, discovered_stage = typesetting, root_stage possibly translation or typesetting, with suggested_action. Page remains previewable. Export eligibility depends on severity/profile.

### S8: Glossary changed

PASS.

GlossaryTerm edit creates a new GlossaryVersion. Old TranslationResult rows keep their glossary_version_id/version_number and terms_hash. Active translations may be marked glossary_stale or needs_review by profile and used_terms impact, but old rows are not rewritten.

### S9: Failed raw payload

PASS.

Invalid LLM JSON creates ToolRunLog and WorkflowAttempt. Raw failed response is saved as ProcessingArtifact with retention_class = failed_attempt, artifact_type = translation_response or attempt_payload, and contains_sensitive_content if needed. WorkflowDecision records retry/fallback/block decision.

### S10: Project soft delete

PASS.

Project soft delete marks app.db Project deleted/trash state and moves or marks workspace trash_pending. project.db and files remain restorable. Permanent deletion requires explicit confirmation and removes project.db plus artifacts.

Additional GOAL scenario checks:

- Two Projects contain the same page filename: PASS. Project workspace, project.db, project_id, and artifact ownership isolate them.
- Export with unresolved blocking issue: PASS. ExportRecord is rejected or not completed because unresolved blocking QualityIssue rows are checked before normal export.
- Export with warning only: PASS. Export behavior follows ProcessingProfile.allow_warning_export and records warning counts/snapshot.
- Re-run TextBlock with unchanged input/config: PASS. OCR/translation/cleaning/typesetting keys reuse existing result/artifact records and avoid duplicate provider call unless forced.
- Successful LLM raw payload cleaned by default: PASS. WorkflowAttempt metadata and hashes remain; successful payload artifact can be deleted per retention policy.

# 20. Open questions

1. Should GlossaryVersion always store a full immutable snapshot, or is terms_hash plus current GlossaryTerm history enough for MVP?
2. Should glossary edits automatically mark all active TranslationResults stale, or only those whose used_terms intersect changed terms?
3. Should locked translation state live only on TextBlock, or should TranslationResult also carry locked_at for simpler querying?
4. Does MVP need full TextBlock geometry history, or is geometry_revision/hash sufficient until manual geometry editing becomes P1?
5. Should rejected export attempts always create ExportRecord, or only when the user explicitly clicks export?
6. What is the exact retention default for successful LLM request/response payloads in normal, strict, and debug profiles?
7. Should Page.active_cleaned_artifact_id represent a full-page image after all blocks, or should block-level cleaned patches be first-class P1 artifacts?
8. How should forced_export / incomplete_export be represented if allowed later: ExportRecord status only, or a separate user override decision?
9. Should ProcessingProfile project-scoped definitions be stored in app.db with project_id, or copied into project.db for portable project export?
10. What exact issue statuses count as unresolved blocking for export after a user accepts a warning or manually skips a block?
