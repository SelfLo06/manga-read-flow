# 1. Scope

This proposal evaluates the data model from the perspective of later SQLAlchemy mapping, Pydantic DTOs, FastAPI endpoint readiness, transaction boundaries, repository boundaries, query patterns, and dependency direction.

It intentionally does not design:

- Full SQL DDL.
- Full SQLAlchemy classes.
- Full Pydantic schemas.
- Full FastAPI routes.
- Migrations.
- Provider implementations.
- Workflow, prompt, OCR, cleaning, or typesetting algorithms.

The design goal is to keep the final data model implementation-ready without turning the model into a large object graph that is difficult to map, validate, migrate, or expose safely through APIs.

# 2. Role Bias

The API/ORM readiness bias is conservative:

- Prefer simple tables with explicit foreign keys over deeply nested domain aggregates.
- Prefer repository-level query methods over ORM lazy-loading chains.
- Prefer explicit active pointer fields or active flags that are easy to query and serialize.
- Prefer stable Pydantic DTO boundaries that expose IDs, state summaries, and artifact references, not internal ORM objects.
- Prefer transaction scopes around use cases, not around provider calls.
- Prefer append-only result/version records for OCRResult, TranslationResult, WorkflowAttempt, WorkflowDecision, ToolRunLog, ProcessingArtifact, ExportRecord, and GlossaryVersion.
- Avoid designing polymorphic inheritance hierarchies for artifacts, attempts, issues, tasks, and results unless implementation evidence later proves the need.

Rationale: the MVP must recover reliably from local interruptions, run on SQLite, and support partial retry. That favors explicit persistence records and focused repository queries over clever ORM abstractions.

# 3. Assumptions

- `app.db` stores global application records and pointers to project workspaces.
- Each Project has an isolated `project.db` under its workspace directory.
- The backend opens at most one Project database for a normal Project-scoped request, plus `app.db` when resolving Project metadata.
- IDs should be opaque API-facing identifiers, stable across restarts, and unique within their database. The final design may choose UUID/ULID/string IDs or integer primary keys with public IDs, but API DTOs should not require exposing database row mechanics.
- File content is never stored as image BLOBs in SQLite. Databases store metadata and relative artifact paths managed by ArtifactService.
- Provider adapters return structured outputs and errors but never write database records, register artifacts, or decide retry/fallback/skip/block behavior.
- WorkflowLoopEngine and Application Services own use-case transactions; Repository/DAO owns SQLite access details.
- Long-running provider calls occur outside open database write transactions. Metadata is persisted before and after calls so recovery is possible.
- API keys and secrets are stored outside `project.db`; logs, artifacts, examples, and DTOs must not contain secrets.
- Page-level translation call is the MVP execution grain, while TranslationResult persistence remains TextBlock-level.

# 4. Proposed entities

| Entity | Responsibility | ORM/API readiness decision |
| --- | --- | --- |
| Project | Global Project identity, workspace pointer, default language/profile summary, lifecycle status. | Map in `app.db`; expose list/detail DTOs without joining into `project.db`. |
| Batch | Project-local upload/processing group containing ordered Pages. | Map in `project.db`; API should query by `batch_id` within a Project context. |
| Page | Single original image and page-level state/active output pointers. | Keep Page as an API summary root for preview/progress; avoid embedding all TextBlocks by default. |
| TextBlock | Detected text region with geometry, reading order, skip flags, and stage statuses. | Keep geometry scalar/JSON fields on TextBlock unless later editing requires separate geometry history. |
| OCRResult | Immutable OCR result version for one TextBlock. | Append-only; active selection is explicit on TextBlock or by constrained active flag. |
| TranslationResult | Immutable translation version for one TextBlock. | Append-only; records source hash, context hash, glossary version, provider/model metadata. |
| GlossaryTerm | Project-owned editable glossary entry. | Mutable current term table with soft delete/status; changes produce GlossaryVersion. |
| GlossaryVersion | Snapshot identity/hash of glossary state at a point in time. | Append-only version record referenced by TranslationResult. |
| ProcessingTask | User-visible asynchronous work item for batch/page/textblock processing. | Query by status/progress; do not store provider payloads here. |
| WorkflowAttempt | Persisted metadata for one stage attempt. | Append-only; attach payload artifacts through ProcessingArtifact. |
| WorkflowDecision | Persisted WorkflowLoopEngine decision and rationale. | Append-only; references attempt/issues/target when applicable. |
| QualityIssue | User-visible and workflow-visible issue with discovered/root stage attribution. | Query unresolved blocking issues efficiently for export gates. |
| ProcessingArtifact | Metadata for filesystem artifact path, hash, type, ownership, retention. | Central artifact table; no image/blob payloads. |
| ToolRunLog | Trace of external tool/provider invocation. | Append-only; sanitized errors only; references input/output artifacts by ID. |
| ExportRecord | Export attempt/result metadata and manifest artifact reference. | Append-only; records blocked/forced/warning policy result. |
| ProcessingProfile | Global or project-selected processing policy. | Store built-in/global profiles in `app.db`; Project/Batch/Page store selected profile reference/snapshot hash. |

Decision: keep these as separate persistence entities rather than one generic event table.

Rationale: API screens need targeted queries for progress, quality issues, artifacts, active results, and exports. Typed records are easier to map, index, migrate, validate, and explain to users.

# 5. P0 / P1 / P2 classification

| Entity/field group | P0 | P1 | P2 |
| --- | --- | --- | --- |
| Project | Identity, name, workspace path, default languages, status, soft delete fields, default profile reference. | Per-project advanced defaults. | Import/export of project metadata. |
| Batch | Name, page count, ordering, status, selected ProcessingProfile reference/snapshot. | Batch-level advanced strategy fields. | Multi-page translation context metadata. |
| Page | Page order, original artifact pointer, active cleaned/typeset artifact pointers, state, quality summary. | Manual reorder invalidation metadata. | Reader-oriented metadata. |
| TextBlock | bbox/polygon, direction, reading order, stage statuses, skip reason, active OCR/translation pointers. | Manual geometry adjustment metadata. | Geometry history/advanced layout hints. |
| OCRResult | Versioned text, confidence, provider/model metadata, input/config hashes, artifacts, user-edit flag. | OCR alternatives and comparison metadata. | Advanced OCR ensemble metadata. |
| TranslationResult | Versioned translation, source/context/config hashes, provider/model/prompt metadata, glossary version, lock flag. | Cost/token estimate, reviewer metadata. | Multi-style translation variants. |
| GlossaryTerm | Project-local terms, aliases, priority, status, source TextBlock, timestamps. | Quick-add source spans/candidate state. | Automated term mining metadata. |
| GlossaryVersion | Version number/hash/reason/timestamp. | Optional compact diff summary. | Full snapshot artifact if needed. |
| ProcessingTask | Async task status, target, progress summary, pause/cancel fields, selected profile snapshot. | Detailed progress counters by stage. | External worker lease metadata. |
| WorkflowAttempt | Stage/target/provider attempt metadata, status, input/config hashes, timing, error code. | Retry budget counters by issue type. | Distributed tracing IDs. |
| WorkflowDecision | Decision type, rationale, target, linked attempt/issues, profile policy basis. | Structured policy evaluation details. | Explainability timeline export. |
| QualityIssue | Issue type, severity, blocking, discovered/root stage, target, status, suggested action. | User acceptance/waiver metadata. | Issue clustering. |
| ProcessingArtifact | Type, relative path, hash, owner target, retention/debug flags, cleanup status. | Artifact derivation graph fields. | Deduplicated content store. |
| ToolRunLog | Tool/provider call metadata, sanitized error, input/output artifact IDs, timing. | Token/cost estimates. | Provider performance analytics. |
| ExportRecord | Export target, status, artifact/manifest references, warning/blocking snapshot. | User-selected export options. | Export presets. |
| ProcessingProfile | Built-in profiles, retry budgets, warning export policy, debug retention policy. | User-created custom profiles. | Profile version marketplace/import. |

Decision: P0 should include all required entities, but not every advanced field.

Rationale: the workflow cannot satisfy recovery, traceability, active versioning, export blocking, and idempotency without all required entity types. Simplicity should come from narrow P0 fields and disciplined repositories, not from omitting trace records.

# 6. app.db vs project.db placement

| Placement | Entities | Reasoning |
| --- | --- | --- |
| `app.db` | Project, global settings, provider configs without secrets in Project DB, workspace config, recent projects, global/built-in ProcessingProfile, schema migrations. | Needed before opening a Project; applies across Projects; must not duplicate project-local workflow data. |
| `project.db` | Batch, Page, TextBlock, OCRResult, TranslationResult, GlossaryTerm, GlossaryVersion, ProcessingTask, WorkflowAttempt, WorkflowDecision, QualityIssue, ProcessingArtifact, ToolRunLog, ExportRecord, project-local schema migrations. | Project isolation, portable project workspace, recovery from local state. |
| Reference across boundary | Project stores `project_db_path`/workspace path in `app.db`; project-local records may store `project_id` as a defensive/scoping field. | API services resolve the Project through `app.db`, then open the target `project.db`. |
| ProcessingProfile split | Built-in/global profiles in `app.db`; project-local selected profile reference and execution-time profile snapshot/hash in `project.db` records such as Batch/ProcessingTask/WorkflowAttempt. | Keeps global defaults manageable while preserving historical execution behavior if a profile changes later. |

Decision: do not join `app.db` and `project.db` in ORM relationships.

Rationale: cross-database ORM relationships create fragile session lifetimes and can weaken Project isolation. Application services should resolve Project context explicitly.

Rejected alternative: store all Projects in one SQLite database with `project_id` on every table. This simplifies cross-project listing but conflicts with the explicit app.db/project.db architecture and makes Project portability/deletion riskier.

# 7. Key fields

Key fields are design-level groups, not DDL.

| Entity | Key fields for ORM/API readiness |
| --- | --- |
| Project | `project_id`, `name`, `workspace_path`, `project_db_path`, `default_source_language`, `default_target_language`, `default_processing_profile_id`, `status`, `deleted_at`, `trash_path`, timestamps. |
| Batch | `batch_id`, defensive `project_id`, `name`, `source_language`, `target_language`, `page_count`, `status`, `processing_profile_id` or `profile_snapshot_hash`, `last_processed_at`, `deleted_at`, timestamps. |
| Page | `page_id`, `batch_id`, defensive `project_id`, `page_index`, `original_artifact_id`, `active_cleaned_artifact_id`, `active_typeset_artifact_id`, `status`, quality summary fields, stale summary flags, `deleted_at`, timestamps. |
| TextBlock | `text_block_id`, `page_id`, `batch_id`, defensive `project_id`, `reading_order`, bbox fields, `polygon_json`, `source_direction`, `detection_confidence`, `detection_provider`, `mask_artifact_id`, `active_ocr_result_id`, `active_translation_result_id`, stage statuses, `is_skipped`, `skip_reason`, `is_manual_adjusted`, timestamps. |
| OCRResult | `ocr_result_id`, `text_block_id`, `source_text`, `ocr_confidence`, `quality_flags`, `provider`, `model_id`, `tool_version`, `input_artifact_id`, `raw_output_artifact_id`, `input_hash`, `config_hash`, `version_number`, `is_user_edited`, `created_from_result_id`, timestamps. |
| TranslationResult | `translation_result_id`, `text_block_id`, `ocr_result_id` or `source_text_hash`, `translation_text`, `provider`, `model_id`, `prompt_template_version`, `glossary_version_id`, `context_hash`, `generation_config_hash`, `used_terms_json`, `confidence`, `needs_review`, `quality_flags`, `error_code`, `version_number`, `is_user_edited`, `is_locked`, `created_from_result_id`, timestamps. |
| GlossaryTerm | `term_id`, defensive `project_id`, `source_text`, `target_text`, `term_type`, `reading`, `aliases_json`, `case_sensitive`, `priority`, `status`, `created_from_text_block_id`, `created_by_user`, `note`, timestamps. |
| GlossaryVersion | `glossary_version_id`, defensive `project_id`, `version_number`, `terms_hash`, `term_count`, `created_reason`, `created_from_term_id`, timestamp. |
| ProcessingTask | `task_id`, defensive `project_id`, `target_type`, `target_id`, `task_type`, `status`, `requested_by`, `profile_snapshot_hash`, progress counters, `pause_requested_at`, `cancel_requested_at`, `started_at`, `finished_at`, timestamps. |
| WorkflowAttempt | `attempt_id`, `task_id`, `stage`, `target_type`, `target_id`, `attempt_number`, `provider`, `model_id`, `input_hash`, `config_hash`, `status`, `error_code`, `tool_run_id`, timestamps. |
| WorkflowDecision | `decision_id`, `task_id`, `attempt_id`, `decision_type`, `target_type`, `target_id`, `reason_code`, `rationale`, `linked_quality_issue_ids_json`, `profile_policy_snapshot`, timestamp. |
| QualityIssue | `quality_issue_id`, `target_type`, `target_id`, `discovered_stage`, `root_stage`, `issue_type`, `severity`, `is_blocking`, `status`, `message`, `suggested_action`, `created_by`, `resolved_at`, timestamps. |
| ProcessingArtifact | `artifact_id`, defensive `project_id`, `batch_id`, `page_id`, `text_block_id`, `owner_type`, `owner_id`, `artifact_type`, `relative_path`, `file_hash`, `mime_type`, `byte_size`, `source_step`, `tool_run_id`, `retention_policy`, `is_debug`, `cleanup_status`, timestamps. |
| ToolRunLog | `tool_run_id`, defensive `project_id`, `batch_id`, `page_id`, `text_block_id`, `stage`, `tool_name`, `tool_version`, `model_id`, `input_artifact_id`, `output_artifact_id`, `input_hash`, `config_hash`, `status`, `error_code`, sanitized `error_message`, `started_at`, `finished_at`. |
| ExportRecord | `export_id`, defensive `project_id`, `batch_id`, optional `page_id`, `export_type`, `status`, `output_artifact_id`, `manifest_artifact_id`, `profile_policy_snapshot`, `blocking_issue_count`, `warning_issue_count`, `forced_export`, timestamps. |
| ProcessingProfile | `profile_id`, `name`, `scope`, `is_builtin`, `is_default`, retry budgets, warning export policy, debug artifact policy, auto-skip policy, provider preference fields, timestamps. |

Important index/constraint readiness:

- Unique Page order within a Batch.
- Unique TextBlock reading order within a Page unless skipped/deleted ordering semantics say otherwise.
- Unique GlossaryVersion version number per Project.
- Unique active OCR/Translation per TextBlock if the final design uses active flags.
- Fast lookup of unresolved blocking QualityIssue by target and by Project/Batch/Page.
- Fast lookup of reusable OCR/Translation by idempotency/cache key.
- Fast lookup of ProcessingArtifact by owner and artifact type.
- Fast lookup of ProcessingTask by status for recovery.

# 8. Relationships

Relationship summary:

- Project has many Batches, GlossaryTerms, GlossaryVersions, ProcessingTasks, WorkflowAttempts, WorkflowDecisions, QualityIssues, ProcessingArtifacts, ToolRunLogs, and ExportRecords within its `project.db`.
- Batch belongs to Project and has many Pages.
- Page belongs to Batch and has many TextBlocks.
- TextBlock belongs to Page and has many OCRResults and TranslationResults.
- TextBlock has one active OCRResult and one active TranslationResult by pointer or active flag.
- OCRResult may be referenced by TranslationResult to show which OCR version was translated.
- GlossaryTerm belongs to Project.
- GlossaryVersion belongs to Project and is referenced by TranslationResult.
- ProcessingTask targets Batch, Page, or TextBlock through explicit `target_type`/`target_id`.
- WorkflowAttempt belongs to ProcessingTask and targets a stage target.
- WorkflowDecision belongs to ProcessingTask and usually references a WorkflowAttempt and related QualityIssues.
- QualityIssue targets Project, Batch, Page, TextBlock, OCRResult, TranslationResult, ProcessingArtifact, WorkflowAttempt, or ExportRecord through `target_type`/`target_id`.
- ProcessingArtifact has explicit nullable ownership columns for common query paths plus owner fields for less common targets.
- ToolRunLog may reference input/output ProcessingArtifacts and may be linked from WorkflowAttempt.
- ExportRecord targets Batch or Page and references output/manifest ProcessingArtifacts.
- ProcessingProfile is referenced by Project defaults and snapshotted by Batch/ProcessingTask/WorkflowAttempt for historical behavior.

ORM readiness decisions:

- Use shallow ORM relationships for direct parent/child navigation only: Batch to Pages, Page to TextBlocks, TextBlock to active result summaries when needed.
- Do not rely on multi-hop lazy loads such as `project.batches.pages.text_blocks.translation_results`.
- Prefer repository methods such as `list_page_text_blocks_with_active_results(page_id)` and `get_export_gate_summary(batch_id)`.
- Use DTO assemblers in application services to build API responses from repository query results.

Rationale: this avoids cyclic imports between ORM models, DTOs, services, workflow modules, and provider adapters.

# 9. Versioning rules

- OCRResult is immutable after creation except for non-semantic cleanup metadata if the final implementation permits it. User OCR edits create a new OCRResult.
- TranslationResult is immutable after creation except for non-semantic cleanup metadata if the final implementation permits it. User translation edits create a new TranslationResult.
- GlossaryTerm is the mutable current term record. Every material glossary change creates a new GlossaryVersion.
- TranslationResult records the GlossaryVersion used at creation time. Later glossary changes do not mutate existing TranslationResults.
- ExportRecord is append-only. Re-export creates a new ExportRecord.
- WorkflowAttempt, WorkflowDecision, ToolRunLog, ProcessingArtifact, and GlossaryVersion are append-only audit/recovery records.
- ProcessingProfile changes must not retroactively change historical decisions. ProcessingTask and WorkflowAttempt should store profile ID plus profile snapshot/hash or policy snapshot.

Decision: do not introduce a generic version table.

Rationale: OCRResult and TranslationResult have different idempotency keys, API DTOs, validation needs, and downstream stale rules. Typed version tables are clearer and easier to expose.

# 10. Active pointer rules

Two viable designs exist:

- Preferred for API/ORM readiness: TextBlock stores `active_ocr_result_id` and `active_translation_result_id`.
- Acceptable alternative: OCRResult/TranslationResult have `is_active` with a uniqueness constraint per TextBlock.

Recommendation: use active pointers on TextBlock unless final SQLite migration constraints or repository ergonomics argue otherwise.

Rationale:

- Active pointers make common API queries simple and avoid filtering through version lists.
- Pointers make stale transitions explicit: when a new OCRResult becomes active, translation/typesetting state can be marked stale in the same transaction.
- Pointers avoid ambiguity if historical result rows are imported or restored.

Rules:

- Active OCRResult must belong to the same TextBlock.
- Active TranslationResult must belong to the same TextBlock.
- Active TranslationResult should record or hash the OCR/source text it depends on.
- Locked TranslationResult remains active until the user explicitly unlocks, edits, or reruns translation.
- If a TextBlock is skipped, active pointers may remain for audit but downstream stages must honor skip state.
- Page active cleaned/typeset artifact pointers should reference ProcessingArtifact rows owned by that Page or its TextBlocks according to the final artifact granularity.

# 11. State and stale rules

State should be queryable without replaying every attempt:

- Batch keeps aggregate processing status.
- Page keeps page-level processing status and stale/quality summaries.
- TextBlock keeps stage statuses: detection, OCR, translation, translation_check, cleaning, typesetting, review.
- ProcessingTask keeps asynchronous execution status.
- QualityIssue keeps unresolved/resolved/accepted status and blocking severity.

Stale transitions:

- OCR edit creates a new OCRResult, sets TextBlock active OCR pointer, marks translation, translation_check, and typesetting stale, and marks review as needs_review.
- Translation edit creates a new TranslationResult, sets TextBlock active Translation pointer, marks typesetting stale, and marks review as needs_review.
- TextBlock geometry or mask edit marks cleaning and typesetting stale.
- Glossary edit creates a new GlossaryVersion and may mark affected existing TranslationResults or TextBlocks as glossary-stale by query or stored stale flag, but must not mutate old TranslationResult glossary_version.
- Page reorder may mark page translation context stale without deleting existing OCR/Translation rows.

Transaction boundary:

- State changes caused by user edits should commit atomically with new result version creation and stale flag updates.
- Provider calls should not run inside write transactions. The workflow should persist an attempt start, release the DB, call the provider, then persist ToolRunLog/artifacts/results/decisions in a new transaction.

# 12. Artifact relationships

ArtifactService owns artifact path, hash, registration, retention, and cleanup.

ProcessingArtifact should support:

- Original images.
- Detection masks and visualizations.
- OCR crops and raw OCR output.
- Translation request/response payloads when retained.
- Cleaning masks and cleaned images.
- Typeset previews/final images.
- Quality reports.
- Failed attempt payloads.
- Export images/ZIPs/manifests.
- Debug bundles/log artifacts when enabled.

Rules:

- Original image artifact is immutable and required for each Page.
- File paths should be relative to Project workspace, not arbitrary absolute paths in API DTOs.
- Artifact metadata records file hash, artifact type, owner, source step, retention policy, debug flag, cleanup status, and optional tool_run_id.
- Failed attempt artifacts are retained by default.
- Successful raw payload artifacts are retention-policy controlled.
- If a successful large payload file is cleaned, ProcessingArtifact remains with cleanup status so WorkflowAttempt metadata stays explainable.
- Provider adapters may use temporary files but must not choose final workspace paths or register ProcessingArtifact rows.

API readiness:

- DTOs should expose artifact IDs, preview/download URLs, artifact type, created time, and cleanup status.
- DTOs should not expose raw filesystem paths unless restricted to local admin/debug views.

# 13. Idempotency and cache keys

Idempotency keys should be stage-specific and repository-queryable.

OCR reusable result key should include:

- TextBlock geometry/mask hash or input crop artifact hash.
- Source image artifact hash.
- OCR provider.
- model ID/version.
- OCR config hash.

Translation reusable result key should include:

- source_text_hash.
- page/context hash.
- glossary_version_id or glossary terms hash.
- provider.
- model ID.
- prompt template version.
- generation config hash.
- target/source language.

Cleaning reusable artifact key should include:

- original/previous image artifact hash.
- TextBlock geometry/mask hash.
- cleaning mode/provider.
- config hash.

Typesetting reusable artifact key should include:

- cleaned image artifact hash.
- active TranslationResult ID or translation hash.
- TextBlock geometry.
- font/config hash.
- typesetting provider/version.

Decision: keep cache/idempotency decision in WorkflowService/WorkflowLoopEngine repositories, not in provider adapters.

Rationale: providers cannot know Project retention policy, active pointers, stale state, user locks, or whether a user explicitly requested rerun.

API readiness:

- Rerun endpoints should accept an explicit intent such as `reuse_cache`, `force_rerun`, or `from_failed_stage` in later API design.
- The data model must be able to explain why no provider call occurred when a cached result was reused, likely through WorkflowDecision.

# 14. Deletion and retention policy

Deletion:

- Project deletion is soft delete/trash first. `app.db` marks Project deleted and Project workspace files move to trash or are marked for trash.
- Batch deletion is soft delete in `project.db`; associated Pages, TextBlocks, results, artifacts, attempts, issues, and exports remain recoverable until permanent purge.
- Page deletion is soft delete. Original image artifact is not overwritten and should remain until permanent purge.
- TextBlock deletion should usually be represented as status/skipped/deleted rather than physical removal, so previous attempts and quality issues remain explainable.
- GlossaryTerm deletion should set status/deleted and create a GlossaryVersion.
- ExportRecord deletion should remove or trash output artifacts according to retention policy but preserve audit metadata unless permanent purge is confirmed.

Retention:

- Original images, active cleaned/typeset images, export artifacts, masks, quality reports, and failed attempt artifacts are retained by default.
- Successful raw provider payloads are configurable and may be cleaned under default policy.
- Debug artifacts are explicitly marked and subject to user-visible retention controls.
- Cleanup should update ProcessingArtifact cleanup status rather than deleting rows first.

Rejected alternative: cascade hard-delete child records immediately. This makes recovery, audit, and user restore semantics fragile and can break WorkflowAttempt traceability.

# 15. Migration concerns

Migration readiness decisions:

- Keep enum values as stable strings in the design; avoid relying on Python enum names that may churn.
- Store JSON only for naturally flexible payloads such as polygon coordinates, aliases, used terms, linked issue IDs, and profile policy snapshots. Do not hide core query fields inside JSON.
- Keep provider/model/config metadata as scalar fields where they are part of idempotency or filtering.
- Use nullable fields for P1/P2 expansion rather than premature subtyping tables.
- Keep schema migrations per database: `app.db` and each `project.db`.
- Record schema version in both databases.
- Plan project-open migration flow: open `app.db`, discover Project, lock/open Project DB, run project-local migrations, then allow editing/processing.
- Avoid cross-db foreign key assumptions between Project and project-local entities.
- Treat path migration carefully: Project workspace moves should update Project path in `app.db`; project-local artifact paths should remain relative.

Risk: SQLite plus SQLAlchemy can make partial indexes, JSON querying, and concurrent writes tricky. The final implementation should choose constraints that are enforceable in SQLite and back them with repository tests.

# 16. Risks

- Active pointer vs active flag is a major final-schema choice; both are viable, but mixing both would create consistency bugs.
- `target_type`/`target_id` references are flexible but not FK-enforced. Overuse can hide invalid references unless repositories validate target existence.
- Too many defensive `project_id` fields in `project.db` can feel redundant, but they help API scoping, artifact ownership, and future export/import checks.
- Storing too many payload details in ToolRunLog risks leaking secrets or sensitive content. Raw payloads belong in controlled ProcessingArtifact records with retention policy and sanitization.
- Repository methods can become god objects if grouped poorly. Bound repositories should follow use cases: ProjectRepository, BatchRepository, PageRepository, TextBlockRepository, ResultRepository, WorkflowRepository, ArtifactRepository, QualityIssueRepository, ExportRepository, ProfileRepository.
- If API DTOs mirror ORM models one-to-one, cyclic dependencies and overexposure of internal fields become likely.
- If WorkflowAttempt metadata is too thin, recovery and user explanations will be weak.
- If QualityIssue is too generic, export gating and root-stage attribution become unreliable.
- If every future feature gets modeled in P0, MVP migrations and DTOs become heavy before implementation feedback exists.

# 17. Rejected alternatives

- Single monolithic `project_state` JSON document: rejected because it weakens queryability, migrations, recovery, export gates, and partial retry.
- Generic `result` table for OCR, translation, cleaning, and typesetting: rejected because OCR/translation versioning and image artifacts have different keys, DTOs, and stale rules.
- Provider adapters write directly to database/artifacts: rejected because it violates architecture boundaries and makes retry/fallback decisions untraceable.
- Keep only latest OCR/translation text on TextBlock: rejected because user edits and provider outputs must be versioned and recoverable.
- Store raw images or large provider payloads directly in SQLite: rejected by hard invariant and poor SQLite fit.
- Full polymorphic ORM inheritance for tasks, attempts, artifacts, and issues: rejected for MVP because it adds mapper complexity without proven benefit.
- Cross-database ORM relationships from Project to Batch/Page: rejected because Project DB isolation should be explicit.
- Synchronous API handler does full processing: rejected because long tasks must create ProcessingTask and run through TaskRunner.
- Make Batch optional for single-page MVP: rejected because SRS/HLD require Page belongs to Batch and Batch belongs to Project.

# 18. Decisions intentionally left to later rounds

- Exact primary key format: UUID, ULID, integer plus public ID, or another scheme.
- Final choice between active pointer and active flag.
- Exact SQL constraints and indexes.
- Exact Pydantic DTO names, nesting, and response shapes.
- Exact FastAPI route layout.
- Exact migration implementation and Alembic environment strategy for many Project DBs.
- Exact enum value set for every state, issue type, artifact type, and error code.
- Exact profile snapshot serialization format.
- Exact artifact directory naming rules and cleanup scheduler behavior.
- Exact project trash implementation: physical move versus logical trash marker.
- Whether TextBlock geometry edits need a separate history table in P1.
- Whether GlossaryVersion stores only a hash/version or also a snapshot artifact/diff.
- Whether TranslationResult should directly FK to OCRResult or only store `source_text_hash`.

# 19. Validation against all scenarios in HARNESS.md

| Scenario | Validation |
| --- | --- |
| S1: Happy path | PASS. Project resolves workspace and Project DB; Batch contains ordered Page; Page has original artifact; detection creates TextBlocks; OCRResult and TranslationResult versions become active; cleaning/typesetting artifacts are registered; ExportRecord references output artifact after export gate checks unresolved blocking QualityIssues. |
| S2: Restart after OCR | PASS. ProcessingTask, TextBlock OCR stage status, active OCRResult, WorkflowAttempt, ToolRunLog, and ProcessingArtifact records allow WorkflowLoopEngine to continue translation without re-running OCR if idempotency keys match and no stale flags exist. |
| S3: OCR edit | PASS. User edit creates a new OCRResult and active OCR pointer update in one transaction. Translation, translation_check, and typesetting statuses become stale; old OCRResult remains. |
| S4: Translation edit | PASS. User edit creates a new TranslationResult and active Translation pointer update in one transaction. Typesetting becomes stale; old TranslationResult remains. |
| S5: Provider refusal | PASS. ToolRunLog records provider refusal with sanitized error; WorkflowAttempt records failed/refused attempt; QualityIssue records issue with discovered/root stage; WorkflowDecision records fallback, warning, skip, or block according to ProcessingProfile. |
| S6: Complex cleaning skipped | PASS. TextBlock cleaning_status becomes skipped with skip reason; QualityIssue can be warning/non-blocking; Page can enter ready_for_export_with_warnings if ProcessingProfile allows. |
| S7: Typeset overflow | PASS. Typesetting attempt artifact can be retained as preview; QualityIssue records `typeset_overflow`, discovered/root stage, severity/blocking policy; TextBlock/Page remain previewable. |
| S8: Glossary changed | PASS. GlossaryTerm mutation creates GlossaryVersion. Old TranslationResult keeps old glossary_version reference/hash. New translations use the new version. |
| S9: Failed raw payload | PASS. Failed LLM raw response is stored as a failed attempt ProcessingArtifact by default and linked from WorkflowAttempt/ToolRunLog. |
| S10: Project soft delete | PASS. Project is marked deleted in `app.db`; workspace/project files move to trash or are marked for trash; permanent deletion requires confirmation and retention cleanup. |

Additional GOAL.md scenario checks:

| Scenario | Validation |
| --- | --- |
| 11: Project restore before permanent deletion | PASS. Soft delete/trash metadata supports restore before purge. |
| 12: Same page filename in two Projects | PASS. Each Project has isolated workspace and `project.db`; artifact paths are project-relative. |
| 13: Export with unresolved blocking issue | PASS. Export gate queries unresolved blocking QualityIssues; normal ExportRecord is rejected/blocked. |
| 14: Export with warnings only | PASS. ProcessingProfile warning export policy decides whether export proceeds, is blocked, or is marked forced/incomplete. |
| 15: Re-run unchanged TextBlock | PASS. Stage idempotency keys allow repository lookup and WorkflowDecision records cache reuse/no provider call. |

Validation result: all HARNESS.md scenarios are supported at design level. No implementation tests were run because this is a documentation-only proposal.

# 20. Open questions

- Should active result selection use TextBlock pointer fields or per-result `is_active` flags?
- Should TranslationResult FK directly to OCRResult, or is `source_text_hash` enough for MVP traceability?
- Should ProcessingProfile custom profiles live only in `app.db`, or can a Project carry project-local profile copies for portability?
- How much profile policy should be snapshotted on ProcessingTask/WorkflowAttempt versus referenced by hash?
- Should QualityIssue `target_type`/`target_id` remain polymorphic, or should common Page/TextBlock target IDs be explicit nullable fields for stronger queryability?
- Should TextBlock geometry edits create new version records in P1, or is mutable geometry with stale flags sufficient for MVP?
- Should GlossaryVersion store a full snapshot artifact, a compact diff, or only `terms_hash` plus version number for MVP?
- What is the exact export behavior for advanced forced export when blocking issues exist, given HLD allows advanced forced/incomplete export but normal export must be blocked?
- How should Project DB migrations be coordinated when many Project workspaces exist and some are offline or moved?
- What retention defaults should be used for successful raw LLM requests/responses in normal mode versus debug mode?
