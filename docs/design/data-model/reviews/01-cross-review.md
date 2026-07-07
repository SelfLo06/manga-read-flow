# 1. Summary of each proposal

## `docs/design/data-model/proposals/01-domain-model-agent.md`

The domain model proposal is the broadest and most balanced proposal. It defines the Project -> Batch -> Page -> TextBlock spine, immutable `OCRResult` and `TranslationResult` versions, active pointers on `TextBlock`, project-local glossary/versioning, workflow trace records, quality issues, artifacts, exports, and ProcessingProfile snapshots. It explicitly validates all HARNESS scenarios and aligns strongly with HLD sections 6-10 and SRS FR-TS-001 through FR-TS-012.

Strongest decisions:

- Use explicit `TextBlock.active_ocr_result_id` and `TextBlock.active_translation_result_id`.
- Treat active selection as "selected active", while export/use requires freshness checks.
- Store `ProcessingProfile` definitions in `app.db` and immutable execution snapshots/hashes in `project.db`.
- Use `ProcessingArtifact` as the durable file metadata source of truth.
- Keep Page-level translation calls but store `TranslationResult` per TextBlock.

Main gaps:

- Glossary snapshots are optional, so exact historical prompt reconstruction is not guaranteed unless the final design makes a clear policy decision.
- Geometry history is intentionally light for MVP; this is reasonable, but final synthesis must state how SRS `text_block_geometry` maps to the model.
- Page-level translation grouping relies on shared `WorkflowAttempt` / `ToolRunLog` / `context_hash`; there is no dedicated group entity.

## `docs/design/data-model/proposals/02-persistence-agent.md`

The persistence proposal is strongest on `app.db` / `project.db` separation, migration readiness, indexing, uniqueness, soft delete, and avoiding cross-database foreign keys. It emphasizes stable IDs, project-relative paths, same-database FKs inside `project.db`, and denormalized scope columns for operational tables.

Strongest decisions:

- Store all Project-owned workflow/content records in `project.db`.
- Keep `Project`, global settings, provider config references, and global ProcessingProfile templates in `app.db`.
- Do not use cross-database foreign keys.
- Keep per-database `schema_migrations`.
- Keep explicit indexes for recovery, unresolved blocking issues, artifact retention, active pointers, and idempotency.

Main gaps:

- It introduces both `owner_type` / `owner_id` and concrete scope columns for artifacts/issues/attempts, which is practical but needs strict final ownership rules to avoid drift.
- It is less specific than proposal 04 on artifact lifecycle state names and cleanup failure behavior.
- It leaves several important relationship implementation choices open, especially `WorkflowDecision` to `QualityIssue` as JSON list versus join table.

## `docs/design/data-model/proposals/03-workflow-state-agent.md`

The workflow-state proposal is strongest on durable recovery, stale propagation, retry/fallback decisions, task lifecycle, and crash reconciliation. It closely follows HLD 7-9 and HARNESS scenarios S2, S3, S4, S5, S13, and S15.

Strongest decisions:

- Recovery must combine `ProcessingTask`, TextBlock stage statuses, `WorkflowAttempt`, `WorkflowDecision`, artifacts, issues, and active result pointers.
- Persist per-stage TextBlock status fields instead of relying on Page status.
- Record cache reuse and skipped provider calls as workflow decisions or attempt statuses.
- Store task heartbeat/recovery markers for stale `running` tasks.
- Treat provider refusal as structured `ToolRunLog` + `WorkflowAttempt` + `QualityIssue` + `WorkflowDecision`, not as a crash.

Main gaps:

- Crash reconciliation is identified but not fully specified; final synthesis must define transaction boundaries and recovery outcomes for stale `running` tasks/attempts.
- It allows optional active cleaning/typesetting pointers at TextBlock level, creating a granularity decision that must be resolved.
- It leaves the page-level translation grouping entity open.

## `docs/design/data-model/proposals/04-artifact-quality-agent.md`

The artifact-quality proposal is strongest on `ProcessingArtifact`, `QualityIssue`, `ToolRunLog`, provider refusal, failed payload retention, debug artifact safety, cleanup, and export blocking. It most directly answers HLD 5.9, 6.12, 10.5-10.8, 13.4, 13.8, and 13.10.

Strongest decisions:

- Keep `ToolRunLog`, `WorkflowAttempt`, `WorkflowDecision`, `QualityIssue`, and `ProcessingArtifact` separate.
- Make provider refusal a first-class issue/attempt/log/decision path.
- Use project-relative artifact paths and ArtifactService-only registration.
- Add explicit artifact states such as `present`, `metadata_only_cleaned`, `moved_to_trash`, `missing`, and `deleted`.
- Keep failed attempt payloads by default while allowing successful payload cleanup by policy.

Main gaps:

- It adds many optional ownership columns on `ProcessingArtifact`; final synthesis must avoid turning the artifact table into an unclear catch-all.
- It proposes safety flags such as `may_contain_original_image`, `may_contain_ocr_text`, and `contains_secret_redacted`; useful, but final P0 should choose a compact minimum.
- It leaves cleanup failure reporting open: `QualityIssue` versus maintenance log.

## `docs/design/data-model/proposals/05-api-orm-readiness-agent.md`

The API/ORM readiness proposal is strongest on implementation discipline: shallow ORM relationships, DTO boundaries, avoiding lazy-load chains, transaction scopes, repository boundaries, and SQLite-friendly constraints. It keeps the model implementation-ready without designing code.

Strongest decisions:

- Use explicit tables instead of a generic event table or polymorphic inheritance hierarchy.
- Prefer active pointers on `TextBlock`, while noting active flags as a fallback.
- Do not join `app.db` and `project.db` through ORM relationships.
- Keep provider calls outside open write transactions; persist before and after calls.
- Prefer repository query methods such as `list_page_text_blocks_with_active_results` and `get_export_gate_summary`.

Main gaps:

- It frames several final-schema choices as open, including active pointer versus active flag and direct `TranslationResult` -> `OCRResult` FK.
- It is less prescriptive on artifact retention defaults than proposal 04.
- It risks under-specifying reproducibility if DTO/API convenience causes profile snapshots, glossary snapshots, or page translation input artifacts to remain only hashes.

# 2. Conflicts between proposals

The proposals do not conflict on the core architecture. All five agree on:

- `app.db` plus one `project.db` per Project.
- Project -> Batch -> Page -> TextBlock hierarchy.
- Versioned immutable `OCRResult` and `TranslationResult`.
- Project-local `GlossaryTerm` and `GlossaryVersion`.
- `TranslationResult` records glossary version.
- `ProcessingTask`, `WorkflowAttempt`, `WorkflowDecision`, `QualityIssue`, `ProcessingArtifact`, `ToolRunLog`, `ExportRecord`, and `ProcessingProfile` are P0-capable.
- Provider adapters do not own persistence, artifact lifecycle, cache decisions, retry/fallback/skip/block decisions, or QualityIssue creation.
- Export checks unresolved blocking `QualityIssue`.

Real synthesis conflicts:

| Topic | Proposal positions | Review recommendation |
| --- | --- | --- |
| Active current result | 01/02/03/04 prefer owner pointers. 05 prefers pointers but leaves active flags acceptable. | Final should choose `TextBlock.active_ocr_result_id` and `TextBlock.active_translation_result_id` as the single source of truth. Do not also maintain independent `is_active` flags in P0. |
| TranslationResult source link | 01/02/03/04 include `source_ocr_result_id` or equivalent. 05 leaves direct FK versus source hash open. | Final should include `source_ocr_result_id` plus `source_text_hash`. The FK gives traceability; the hash supports stale/idempotency checks. |
| GlossaryVersion snapshot | 01/04 recommend optional snapshot artifact; 02/03 lean hash/version; 05 says full snapshot may be P2. | Final should require `glossary_version_id`, `version_number`, and `terms_hash` in P0, with optional `snapshot_artifact_id`. It should not require full snapshots for MVP unless reproducibility is elevated. |
| Page translation grouping | All proposals use shared `WorkflowAttempt` / `ToolRunLog` / `context_hash`; several leave a dedicated group entity open. | Final should avoid a new P0 entity unless needed. Use one page-scoped `WorkflowAttempt` and `ToolRunLog`, and link each `TranslationResult` to them. Record a `page_translation_group_key` or equivalent field if needed for query clarity. |
| Cleaned/typeset artifact granularity | 01/02/05 emphasize Page active cleaned/typeset artifacts. 03/04 also allow TextBlock-level active cleaning/typesetting artifacts. HLD 6.5 says TextBlock associates cleaning/typesetting artifacts. | Final should keep Page-level active cleaned/typeset artifact pointers for current preview/export, and allow `ProcessingArtifact` rows to scope cleaned/typeset attempts to TextBlock. Avoid separate TextBlock active cleaned/typeset pointers in P0 unless local rerender requires them. |
| Artifact ownership fields | 02/04/05 propose both generic target fields and denormalized scope columns. 01 is simpler. | Final should use concrete scope columns for common scopes plus optional `owner_type` / `owner_id` only for less common ownership. Define allowed owner per `artifact_type`. |
| WorkflowDecision to QualityIssue | Proposals mention JSON lists, primary issue id, or join table. | Final should prefer a small join table or explicit relation concept in design. If schema-outline defers it, state JSON list is MVP-only and not a source of truth for export gates. |
| Forced/incomplete export | 04 models it explicitly; 01/03/05 leave as later/advanced; all agree normal export blocks. | Final should keep normal export blocking as P0. Forced/incomplete export should be marked P1/advanced unless MVP explicitly includes advanced export. |
| ProcessingTask in app.db | All proposals reject app.db-owned recovery tasks, but some allow an optional app.db summary/index. | Final should keep durable tasks in `project.db`; optional app.db recent-task summary is out of P0 data model. |

# 3. Missing entities

No required HARNESS entity is missing from the proposal set. The required core entities are all covered:

- `Project`
- `Batch`
- `Page`
- `TextBlock`
- `OCRResult`
- `TranslationResult`
- `GlossaryTerm`
- `GlossaryVersion`
- `ProcessingTask`
- `ProcessingProfile`
- `WorkflowAttempt`
- `WorkflowDecision`
- `QualityIssue`
- `ProcessingArtifact`
- `ToolRunLog`
- `ExportRecord`

Potentially missing or intentionally folded entities:

| Candidate entity | Source requirement | Proposal coverage | Review decision |
| --- | --- | --- | --- |
| `ProjectConfig` | SRS 7.2 and FR-PJ-007 list project configuration/default providers. | Proposals mostly fold this into `Project.default_profile_id`, `ProcessingProfile`, and provider config references. | Not missing if final explicitly maps SRS `project_config` to Project defaults + ProcessingProfile + app-level provider configs. |
| `ProviderConfig` / provider capability metadata | SRS 4.2, 4.3, HLD 10.2, HLD 12.9 require provider settings and API key handling; SRS says external tool/model license info should be recorded. | Proposals mention app.db provider configs, no secrets, and ToolRunLog provider metadata, but do not detail a provider config/license entity. | Non-blocking for data-model synthesis, but final should mention app.db provider config metadata and license/capability fields or explicitly defer to Provider Adapter detailed design. |
| `TextBlockGeometry` / `GeometryRevision` | SRS 7.6 names `text_block_geometry`; SRS marks manual coordinate adjustment P1; HLD stale rules require geometry changes. | 01/05 prefer geometry fields on TextBlock; 03/04 allow future geometry versioning. | Not required as separate P0 entity. Final must state geometry fields live on `TextBlock` in MVP and `GeometryRevision` is P1 if manual history is needed. |
| `PageTranslationContext` / `TranslationAttemptGroup` | HLD 8.3/8.4 require Page-level translation context; GOAL asks for Page-level translation context. | Proposals use `context_hash`, page-scoped attempts/logs, and optional request artifacts. | Not required as P0 entity if final requires enough context hash/request metadata/artifact linkage for recovery and idempotency. |
| `QualityIssueDecisionLink` join | HLD requires WorkflowDecision rationale and issue links; GOAL requires WorkflowDecision. | Some proposals use JSON issue IDs. | Not a domain entity, but final schema-outline should decide relation representation. A join table is safer if many-to-many links matter. |
| `ExportIssueSnapshot` | GOAL scenarios require export blocking/warning snapshots. | Proposals use `issue_snapshot_hash`, artifact, JSON list, or counts. | Not required as entity; final should require `ExportRecord` counts/hash and optional artifact/list. |
| `ArtifactRetentionPolicy` | HLD 10.6-10.7 and debug artifact policy. | Proposals fold into `ProcessingProfile` and artifact fields. | Not separate P0 entity. |

# 4. Missing relationships

Relationships needing final synthesis attention:

1. `TranslationResult` -> `OCRResult`
   - 01/02/03/04 include `source_ocr_result_id`; 05 leaves it open.
   - Final should require this relationship. SRS FR-TR-005 requires source text hash, but recovery and stale attribution are stronger with a direct source OCR version link.

2. Page-level `WorkflowAttempt` / `ToolRunLog` -> many `TranslationResult`
   - All proposals describe the pattern, but final must make it explicit in the relationship map.
   - This supports HLD 8.3: call grain is Page, storage grain is TextBlock.

3. `WorkflowDecision` -> `QualityIssue`
   - Current proposals vary between JSON id lists, primary issue fields, and join-like concepts.
   - Final must identify how a decision records the issues it was based on, especially for provider refusal, retry exhaustion, skip, warning, and block.

4. `ExportRecord` -> issue snapshot
   - All proposals include counts or snapshots, but final must specify how rejected export attempts preserve blocker evidence.
   - Normal export must be rejected when unresolved blocking issues exist; rejected attempts should still be explainable.

5. `ProcessingArtifact` -> owning scope
   - Proposals agree every artifact belongs to Project and may scope to Batch/Page/TextBlock/Attempt/ToolRun/Export/Result.
   - Final must define allowed owner scopes by artifact type, especially original image, mask, crop, raw request/response, cleaned image, typeset image, export zip, quality report, and failed payload.

6. `GlossaryVersion` -> snapshot artifact
   - Optional in proposals, but if full reproducibility is desired, final should include optional `snapshot_artifact_id`.
   - `TranslationResult` must always link to `GlossaryVersion`.

7. `ProcessingTask` -> profile snapshot
   - All proposals agree tasks need immutable profile snapshot/hash, but final should specify whether this is a snapshot row, JSON field, artifact, or all of these.

8. Soft-delete relationships
   - Proposals describe soft delete but final should state how Batch/Page/TextBlock soft delete affects child records, artifacts, unresolved issues, active pointers, and export eligibility.

# 5. Violated invariants

No proposal clearly violates a hard invariant from `HARNESS.md` or `GOAL.md`.

Near-misses or risks to guard during synthesis:

| Invariant | Risky proposal detail | Review judgment |
| --- | --- | --- |
| Active OCR and active Translation are explicit | 05 keeps active flags as acceptable alternative. | Not a violation, but final should choose pointers to avoid duplicate source of truth. |
| ProcessingArtifact records file path, hash, type, ownership | Some proposals allow temporary crops to be deleted or metadata-only. | Not a violation if the artifact record remains and cleanup state is explicit. |
| TranslationResult records glossary_version | 05 says full snapshot may be P2 but still records glossary version. | No violation. |
| Provider adapters do not own persistence | All proposals preserve this. | No violation. |
| Export checks unresolved blocking issues | All proposals preserve this. | No violation. |
| Failed attempt artifacts persisted by default | All proposals preserve this. | No violation. |
| API keys are not stored in project.db | All proposals preserve this. | No violation. |

# 6. Unsupported scenarios

All required HARNESS scenarios S1-S10 and GOAL scenarios 1-15 are supported at proposal level.

Scenarios that need final-design precision but do not require Phase 3 proposal revisions:

| Scenario | Support status | Needed final precision |
| --- | --- | --- |
| S2 restart after OCR | Supported by all proposals. | Define stale `running` task/attempt recovery status and reconciliation order. |
| S5 provider refusal | Supported by all proposals. | Standardize refusal issue/error codes and root-stage taxonomy: `provider_policy` versus provider stage plus `issue_type`. |
| S7 typeset overflow preview | Supported. | Define whether warning preview artifact may become `Page.active_typeset_artifact_id` or only an attempt artifact until user/profile accepts. |
| S8 glossary changed | Supported. | Define strictness policy for marking old translations stale: all translations, used-terms only, or profile-dependent. |
| S9 failed raw payload | Supported. | Define failed payload retention class and whether redacted raw payload is file artifact, debug artifact, or both. |
| S10 soft delete | Supported. | Define physical move versus logical trash marker as a final open question or policy choice. |
| GOAL 15 unchanged TextBlock rerun | Supported. | Define cache-reuse record: `WorkflowAttempt.status = reused_cached`, `WorkflowDecision = reuse_cached_result`, or both. |

# 7. Over-designed parts

Potential over-design:

1. Artifact optional owner columns
   - 04 and 05 list many optional fields on `ProcessingArtifact`, including result/task/attempt/tool/export owner references and safety booleans.
   - Recommendation: keep P0 compact: project/page/text_block/attempt/tool_run/export scopes, `owner_type`/`owner_id` for uncommon cases, and a minimal sensitive/debug classification.

2. Broad status vocabularies duplicated across Batch/Page/TextBlock
   - 03 and 04 list large status vocabularies.
   - Recommendation: final should separate aggregate UI statuses from TextBlock phase statuses and avoid requiring every listed aggregate value in the first schema unless HLD needs it.

3. Forced/incomplete export
   - 04 models forced export strongly.
   - Recommendation: keep as P1/advanced. P0 normal export must reject unresolved blocking issues.

4. Cost/token accounting
   - Several proposals mention token/cost fields.
   - Recommendation: optional P1 fields on `ToolRunLog`; not part of final P0 invariants unless needed for cloud budget warnings.

5. Full glossary snapshot/diff history
   - Some proposals suggest snapshots or diffs.
   - Recommendation: `GlossaryVersion` with version/hash is P0; snapshot artifact optional. Full term-history/diff tables are not P0.

6. Dedicated event-sourcing or generic event table
   - No proposal recommends it, correctly. Keep it rejected.

# 8. Under-designed parts

Areas that need final synthesis detail:

1. Transaction boundaries
   - Proposals agree provider calls must not occur inside write transactions, but final should state the transaction boundaries for attempt start, artifact registration, result creation, active pointer update, stage status update, issue creation, and decision creation.

2. Crash recovery reconciliation
   - 03 is strongest here, but final must specify what happens to stale `running` tasks and attempts after restart.
   - This directly affects SRS FR-TS-004, FR-TS-005, and HLD 9.7.

3. Page-level translation partial output
   - Final must describe invalid JSON, missing TextBlock translation, partial parse, and per-block result creation.
   - The design must preserve one page-scoped attempt while supporting zero/some/many `TranslationResult` rows.

4. Artifact cleanup state
   - 04 is strongest, but final should choose exact cleanup states and state transitions.
   - This affects successful payload cleanup, missing-file repair, trash restore, and export history.

5. OCR crop retention
   - SRS FR-OCR-009 requires OCR input crop or artifact record for tracing/review.
   - Final must state whether crop file bytes are retained by default, rebuildable, or metadata-only after cleanup.

6. Profile snapshot representation
   - All proposals require snapshots, but final must decide row versus JSON field versus artifact and include a snapshot schema/version/hash.

7. Issue status semantics
   - Final must define which statuses count as unresolved blocking for export.
   - Recommended statuses: `open`, `resolved`, `accepted_warning`, `superseded`, `stale`.

8. `ProjectConfig` mapping
   - Final must explicitly map SRS `project_config` to `Project` fields, `ProcessingProfile`, provider config references, and profile snapshots.

# 9. Migration risks

Key migration risks:

1. app.db/project.db independent migration drift
   - All proposals call for separate migration ledgers.
   - Final must define project-open migration behavior and how app.db records project_db schema compatibility.

2. Active pointer introduction
   - If early implementation starts with active flags, migration to pointers must detect multiple-active conflicts.
   - Final should choose pointers from day one to reduce this risk.

3. Artifact path migration
   - Absolute paths would make workspace moves difficult.
   - Final should require project-relative paths in `ProcessingArtifact`, with app.db holding the project workspace root.

4. Status vocabulary churn
   - HLD expands SRS states. Migrations can strand old `running`, `auto_retrying`, or unknown statuses.
   - Final should define stable string values and tolerant recovery for unknown non-terminal statuses.

5. Profile snapshot schema evolution
   - Snapshots as JSON need `snapshot_schema_version`.
   - Old tasks must remain explainable after global profile edits.

6. Glossary version backfill
   - Legacy `TranslationResult` rows without glossary version should be backfilled to an initial/unknown glossary version and marked if needed.

7. Artifact cleanup before metadata maturity
   - If files are deleted before cleanup states exist, migration must mark artifacts `missing` or `metadata_only_cleaned`, not delete workflow records.

# 10. ORM risks

Main ORM/API risks, mostly from proposal 05:

1. Polymorphic `target_type` / `target_id` cannot be fully FK-enforced.
   - Mitigation: keep concrete scope columns for common cases and validate target existence in repositories.

2. Too many nullable FKs on `ProcessingArtifact`.
   - Mitigation: allowed owner rules by artifact type; repository factory methods only through ArtifactService.

3. Lazy-loading chains can become performance and coupling traps.
   - Mitigation: shallow relationships plus explicit repository queries.

4. `app.db` and `project.db` cross-session relationships can leak project isolation.
   - Mitigation: no ORM relationships across database files.

5. JSON fields can hide query predicates.
   - Mitigation: keep recovery/idempotency/export predicates as scalar columns; use JSON only for bounded flexible metadata.

6. Active pointer integrity needs same-TextBlock validation.
   - Mitigation: same-database FK where feasible plus repository checks before pointer updates.

7. DTOs may overexpose sensitive artifact paths/logs.
   - Mitigation: API exposes artifact IDs and controlled preview/download endpoints, not raw paths by default.

# 11. Artifact lifecycle risks

Key lifecycle risks:

1. File metadata drift from filesystem state
   - Artifact records can become stale if files are moved/deleted outside ArtifactService.
   - Final should include `storage_state` / `cleanup_state`, hash verification, and repair/missing-file behavior.

2. Active artifact cleanup
   - Cleanup must not remove original images, active cleaned/typeset artifacts, active masks, export outputs still referenced, or failed payloads retained by policy.

3. Successful payload cleanup versus traceability
   - Successful raw payload bytes may be cleaned, but `WorkflowAttempt`, `ToolRunLog`, hashes, status, error/success metadata, and artifact metadata must remain.

4. Failed payload sensitivity
   - Failed raw LLM/OCR payloads may include original content, OCR text, translations, prompts, provider responses, or sensitive local content.
   - Final should require debug/sensitive flags and no secrets.

5. Trash restore drift
   - Soft delete may move files or only mark them.
   - Final should specify whether restore validates paths/hashes and how missing trash files are reported.

6. Original image immutability
   - All proposals satisfy this, but final should explicitly prohibit replacing `Page.original_artifact_id` except controlled repair/restore.

# 12. Recovery risks

Recovery risks needing final rules:

1. Crash between artifact write and artifact registration
   - Final should state whether orphan file cleanup scans workspace attempts/temp directories.

2. Crash after provider call but before result rows
   - `ToolRunLog`/raw output artifact may exist without result version. Recovery must decide parse/reuse versus retry.

3. Crash after result row but before active pointer update
   - Recovery must identify valid result versions not selected and decide whether to select or leave pending based on decision/status evidence.

4. Crash after active pointer update but before status update
   - Recovery must reconcile active pointers and stage status; pointer + result dependency hashes should be authoritative enough to avoid duplicate provider call.

5. Stale `running` attempts/tasks
   - 03 proposes paused/recovering/failed/abandoned outcomes. Final must pick a vocabulary and rule.

6. Page-level translation partial result
   - One LLM call can produce partial block translations. Recovery must not lose successfully parsed block results or rerun unchanged blocks unnecessarily.

7. Cache reuse without audit trail
   - Reuse must be recorded in `WorkflowDecision` and/or `WorkflowAttempt.status`, otherwise users cannot explain why no provider call occurred.

# 13. Duplicated source-of-truth risks

1. Active pointer plus active flag
   - Highest source-of-truth risk.
   - Final should choose pointer-only for P0.

2. Page status versus TextBlock stage statuses
   - Page/Batch status should be aggregate UI state, not recovery source of truth.
   - Final should say recovery uses TextBlock stage statuses plus attempts/decisions/artifacts/issues/pointers.

3. File path on domain rows versus ProcessingArtifact
   - SRS field examples include `original_image_path`, `cleaned_image_path`, `typeset_image_path`, and `export_image_path`.
   - Final should reinterpret these as artifact IDs/pointers, not authoritative path fields.

4. ProcessingProfile mutable app.db row versus per-task snapshot
   - Historical behavior must come from snapshot/hash, not mutable profile definition.

5. QualityIssue blocking flag versus dynamic ProcessingProfile policy
   - Store evaluated `is_blocking` with profile context; export gate queries stored unresolved blocking issues. Recompute only through a defined QualityCheck/Workflow decision path.

6. Artifact owner fields
   - `owner_type`/`owner_id` plus nullable scope columns can drift.
   - Final should define scope columns as query denormalization and enforce consistency in repositories.

7. Export readiness status versus unresolved issues
   - `ready_for_export` should be derived/reconciled from issue state and stage state; normal export should still run ExportCheck.

# 14. Recommended final decisions

Recommended decisions for synthesis:

1. Use active pointers as the only P0 current-result source of truth:
   - `TextBlock.active_ocr_result_id`
   - `TextBlock.active_translation_result_id`
   - `Page.original_artifact_id`
   - `Page.active_cleaned_artifact_id`
   - `Page.active_typeset_artifact_id`

2. Keep result rows immutable:
   - User OCR edits create new `OCRResult`.
   - User translation edits create new `TranslationResult`.
   - Old rows are never overwritten.

3. Link `TranslationResult` to both `source_ocr_result_id` and `source_text_hash`.

4. Represent Page-level translation with:
   - one page-scoped `WorkflowAttempt`;
   - one or more `ToolRunLog` records as needed;
   - shared request/response artifacts when retained;
   - one `TranslationResult` per valid TextBlock output;
   - `context_hash` and optional page translation group key.

5. Store `ProcessingProfile` templates in `app.db`; store immutable profile snapshots/hashes in `project.db` task/attempt/export records.

6. Keep all Project-owned content/workflow/audit/artifact/export/glossary records in `project.db`.

7. Avoid cross-database FKs; validate `project_id` on Project open and in repository writes.

8. Use `ProcessingArtifact` as the file metadata source of truth. Domain rows store artifact IDs, not authoritative paths.

9. Use project-relative artifact paths and explicit storage/cleanup states.

10. Persist failed attempt payload artifacts by default. Successful raw payload bytes may be cleaned by policy while metadata remains.

11. Make provider refusal a structured issue path:
    - standardized provider error;
    - `ToolRunLog`;
    - `WorkflowAttempt`;
    - `QualityIssue`;
    - `WorkflowDecision`.

12. Define export gate as a query over unresolved blocking `QualityIssue` records in target scope. Warning export follows the effective ProcessingProfile snapshot.

13. Treat forced/incomplete export as P1/advanced unless explicitly pulled into MVP. It must never be confused with normal export.

14. Keep TextBlock geometry fields on `TextBlock` for P0. Add `GeometryRevision` only when P1 manual geometry history requires it.

15. Model SRS `project_config` through Project defaults, ProcessingProfile, provider config references, and profile snapshots rather than a separate P0 table unless final schema needs it.

# 15. ADR candidates

Recommended ADRs:

1. app.db plus per-project project.db split
   - Decision: Project registry/global settings in `app.db`; Project-owned workflow/content in `project.db`; no cross-db FKs.

2. Active result pointers versus active flags
   - Decision: owner pointers on `TextBlock` and `Page` are the P0 source of truth.

3. Artifact metadata and filesystem lifecycle
   - Decision: `ProcessingArtifact` owns path/hash/type/retention/storage state; no image BLOBs; no direct authoritative paths on domain rows.

4. Page-level translation call with TextBlock-level result storage
   - Decision: one page-scoped attempt/log can create many TextBlock `TranslationResult` rows.

5. Workflow recovery source of truth
   - Decision: recovery uses task, TextBlock stage states, attempts, decisions, artifacts, issues, and active pointers, not Page status alone.

6. ProcessingProfile snapshot policy
   - Decision: mutable global templates plus immutable per-run snapshots/hashes.

7. QualityIssue export gate
   - Decision: normal export rejects unresolved blocking issues; warning export controlled by profile.

8. Provider refusal handling
   - Decision: provider adapters return standardized refusal; WorkflowLoopEngine decides fallback/warning/skip/block and persists decision.

9. Soft delete and artifact trash
   - Decision: Project/Batch/Page/TextBlock delete is soft/trash first; permanent deletion requires confirmation.

10. GlossaryVersion reproducibility level
   - Decision: P0 requires version/hash/reference; optional snapshot artifact for reproducibility/debug.

# 16. Blocking issues

No blocking issue requires Phase 3 proposal revisions.

Rationale:

- All HARNESS hard invariants are addressed by at least one proposal and not contradicted by the others.
- All required entities are present across the proposal set.
- All required scenarios are supported at design level.
- Remaining conflicts are synthesis decisions, not missing proposal work.

Blocking conditions for final synthesis if left unresolved:

1. Final design must choose active pointer versus active flag. Recommended: active pointer only.
2. Final design must define normal export blocking semantics using unresolved blocking `QualityIssue`.
3. Final design must preserve provider refusal as persisted log/attempt/issue/decision, not just an error string.
4. Final design must specify ProjectConfig/default processing configuration mapping.
5. Final design must define artifact cleanup states enough to distinguish present, cleaned metadata-only, trashed, missing, and deleted.

These are blocking for the final document if omitted, but they do not require Phase 3 revisions from proposal agents.

# 17. Non-blocking issues

Non-blocking issues for synthesis:

1. Whether `GlossaryVersion` snapshot artifact is required by default or optional.
2. Whether `WorkflowDecision` links to issues through a join table or structured list.
3. Whether an app.db global task summary/index is useful later.
4. Whether OCR crop files are retained by default or cleaned as rebuildable artifacts.
5. Whether cleanup failures become `QualityIssue` records or maintenance logs.
6. Whether warning export requires explicit per-export user acceptance in addition to ProcessingProfile policy.
7. Exact enum spellings for statuses, stages, issue types, decision types, artifact types, and retention classes.
8. Exact TTL/default retention durations for successful payloads, debug artifacts, and replaced preview artifacts.
9. Exact ID format: UUID, UUIDv7, ULID, integer plus public ID, etc.
10. Exact schema for profile snapshot JSON and profile snapshot versioning.
11. Whether `ExportRecord` stores blocked/warning issue IDs as join rows or compact structured metadata.
12. Whether TextBlock-level cleaned/typeset active pointers are needed in P0 or only artifact scope links.

# 18. Open questions that block final synthesis

1. Active result source of truth:
   - Will final design use owner pointer fields only, or allow active flags?
   - This must be decided to avoid duplicated source-of-truth.

2. Export gate semantics:
   - Which `QualityIssue.status` values count as unresolved blocking?
   - How does `accepted_warning` interact with `ProcessingProfile.allow_warning_export`?

3. Project configuration mapping:
   - Is SRS `project_config` represented by a separate ProjectConfig entity, or by `Project` defaults + `ProcessingProfile` + provider config references?

4. Crash recovery vocabulary:
   - What state replaces stale `running` ProcessingTasks/WorkflowAttempts after restart: `paused`, `recovering`, `failed_after_crash`, `abandoned_after_crash`, or another controlled value?

5. Artifact storage state:
   - What exact P0 storage/cleanup states will final schema use for present, cleaned metadata-only, trash, missing, and deleted files?

6. Page-level translation partial output:
   - When a page translation response is partially valid, does the model create TranslationResults for valid blocks and QualityIssues for invalid/missing blocks, or reject the whole attempt?

7. Profile snapshot representation:
   - Is the immutable snapshot a row in `project.db`, a JSON field on `ProcessingTask`, an artifact, or a combination?

# 19. Open questions that do not block final synthesis

1. Should `GlossaryVersion` always store a full snapshot artifact, or only when debug/strict reproducibility policy asks for it?
2. Should glossary changes mark all active translations stale or only translations whose `used_terms` intersect changed terms?
3. Should provider refusal root attribution use `root_stage = provider_policy` or `root_stage = translation` plus `issue_type = provider_refusal`?
4. Should OCR crop artifacts be kept by default for review, or treated as rebuildable after a retention grace period?
5. Should cleanup failures appear in user-facing quality reports or only in maintenance diagnostics?
6. Should forced/incomplete export be included in MVP advanced mode or deferred to P1?
7. Should Project soft delete immediately move the workspace to trash or mark it trash-pending until no tasks are running?
8. Should Page/Batch aggregate statuses be persisted, derived, or persisted with reconciliation from TextBlock statuses and issues?
9. Should project-local ProcessingProfile snapshots be reused by hash across tasks or copied per task?
10. Should provider/tool license metadata live in app.db provider config, ToolRunLog metadata, or a later Provider Adapter design document?
11. Should `WorkflowDecision` issue links be represented by a normalized join table in P0 or deferred until implementation feedback?
12. Should final ERD include optional TextBlock-level cleaned/typeset artifact pointers or just scoped `ProcessingArtifact` records?
