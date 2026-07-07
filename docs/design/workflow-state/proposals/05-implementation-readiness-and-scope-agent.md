# 1. Scope

This proposal evaluates whether the Workflow State / Workflow Loop design can move into a FakeProvider single-Page backend vertical slice without widening MVP scope.

It covers:

- FakeProvider MVP-0 implementation readiness.
- Conceptual repository methods needed by the workflow loop.
- Transaction boundaries and atomicity expectations.
- StageExecutor boundary assumptions.
- ArtifactService boundary assumptions.
- QualityCheckService boundary assumptions.
- Provider Adapter boundary assumptions.
- Scope control and overdesign rejection.

It does not design:

- SQL DDL.
- ORM models.
- API schemas.
- Provider DTO schemas.
- Artifact directory layout.
- QualityIssue taxonomy.
- Prompt templates.
- Frontend flows.
- Real OCR, translation, cleaning, or typesetting integrations.

# 2. Role Bias

This agent is biased toward MVP implementation readiness, small vertical slices, and early rejection of scope expansion.

The preferred design shape is:

- Explicit stage boundaries over a generic workflow framework.
- Conceptual repository contracts over ORM decisions.
- FakeProvider-driven validation before real Provider integration.
- Durable attempts, decisions, artifacts, issues, and active pointers over hidden in-memory state.
- Minimal ProcessingProfileSnapshot policy inputs over a full profile management design.

The design should be considered ready only if a single command or backend task can process one Project, one Batch, one Page through FakeProviders and explain every retry, warning, block, export gate, and recovery outcome from durable state.

# 3. Assumptions

- MVP-0 means backend or CLI/script-triggered single-Page vertical slice, not full Web UI.
- A real `Project`, `Batch`, and `Page` still exist even for one uploaded image.
- FakeProvider implementations stand in for detector, OCR, translator, cleaner, and typesetter behavior.
- FakeProvider can return success, invalid output, partial output, provider refusal, cleaning skip, typesetting overflow, timeout/failure, and deterministic artifacts or payloads.
- StageExecutors are thin application-layer executors for one workflow stage; they call Provider Adapters, ArtifactService, repositories, and QualityCheckService through WorkflowLoopEngine-controlled flow.
- Repository / DAO owns SQLite access and exposes conceptual operations; exact method names and ORM mapping are deferred.
- ArtifactService is the only official path/hash/registration/lifecycle owner.
- Provider Adapters may use temporary files but cannot register official artifacts or write official workspace paths.
- QualityCheckService creates and classifies QualityIssues but does not advance workflow state or choose workflow decisions.
- WorkflowLoopEngine owns retry, fallback, skip, warning, pause, block, and finish decisions.
- Recovery uses task, attempt, decision, artifact, issue, result, active pointer, and stage-status evidence; it never trusts `Page.status` alone.

# 4. Proposed Model

The design can support FakeProvider MVP-0 if the first implementation is constrained to a single-Page backend slice with explicit stage contracts:

```text
Import
→ Detection
→ OCR
→ Translation
→ TranslationCheck
→ Cleaning
→ Typesetting
→ ExportCheck
→ ready_for_export | ready_for_export_with_warnings | blocked
```

Each stage should follow the same implementation pattern:

```text
1. WorkflowLoopEngine selects next required stage and target.
2. Repository persists ProcessingTask / WorkflowAttempt start.
3. StageExecutor performs the stage without holding a write transaction.
4. Provider Adapter returns structured output or standardized error.
5. ArtifactService registers any official file outputs.
6. QualityCheckService evaluates stage output and creates or updates QualityIssues.
7. WorkflowLoopEngine creates WorkflowDecision.
8. Repository atomically persists result rows, active pointer changes, issue updates, decision, and stage status changes.
```

FakeProvider MVP-0 should prove the architecture, not Provider quality. It should be able to create:

- Original image artifact.
- TextBlock rows.
- OCRResult rows and active OCR pointers.
- TranslationResult rows and active translation pointers.
- Cleaned and typeset image artifacts and Page active artifact pointers.
- ToolRunLog records.
- WorkflowAttempt records.
- WorkflowDecision records.
- QualityIssue records for warning and blocking paths.
- ExportRecord records for success, warning success, and blocked export.

The conceptual StageExecutor boundary:

- Receives a durable task/stage/target context and profile snapshot.
- Builds stage input from repositories and ArtifactService lookups.
- Calls exactly the needed Provider Adapter or local stage operation.
- Returns a stage output object or standardized failure to the loop.
- Does not decide retry/fallback/skip/warning/block.
- Does not directly mutate active pointers outside the WorkflowLoopEngine decision path.
- Does not hide output files from ArtifactService.

The conceptual Provider Adapter boundary:

- Converts structured inputs to tool calls.
- Returns structured outputs and provider metadata.
- Normalizes provider/tool errors.
- Reports provider refusal as a first-class standardized error.
- Does not access SQLite.
- Does not own official artifact lifecycle.
- Does not create QualityIssues.
- Does not choose retry, fallback, skip, warning, pause, or block.
- Does not perform policy evasion or prompt bypass behavior.

The conceptual QualityCheckService boundary:

- Checks stage outputs, retained errors, artifacts, and result metadata.
- Creates or updates QualityIssues with discovered stage, root stage, severity, blocking flag, status, and suggested action.
- Can classify provider refusal or invalid output.
- Can attribute downstream failures to upstream stages.
- Does not advance `ProcessingTask`, Page, or TextBlock workflow state.
- Does not choose fallback, retry, skip, warning export, pause, or block.

The conceptual ArtifactService boundary:

- Generates official project-relative paths.
- Safely writes files.
- Computes hashes.
- Registers ProcessingArtifact metadata.
- Marks artifact storage state changes.
- Owns temp-to-official promotion.
- Owns missing-file checks, retention, cleanup, and trash behavior.
- Protects original images and active artifacts from overwrite or cleanup.

# 5. State Vocabulary or Decision Vocabulary

This proposal does not replace the final state vocabulary, but MVP-0 needs the following vocabulary to be implementable.

Stage vocabulary:

- `import`
- `detection`
- `ocr`
- `translation`
- `translation_check`
- `cleaning`
- `typesetting`
- `export`

Attempt statuses needed for FakeProvider:

- `planned`
- `running`
- `succeeded`
- `failed`
- `refused`
- `skipped`
- `reused_cached`
- `interrupted`
- `abandoned_after_crash`
- `cancelled`

Decision types needed for FakeProvider:

- `continue`
- `reuse_cached_result`
- `retry_same_stage`
- `fallback_provider`
- `retry_upstream_stage`
- `skip_target`
- `mark_warning`
- `pause_for_user`
- `block`
- `finish_ready_for_export`
- `finish_ready_for_export_with_warnings`
- `cancel`

TextBlock stage statuses needed for implementation readiness:

- `pending`
- `running`
- `done`
- `failed`
- `skipped`
- `needs_review`
- `stale`
- `locked`

ProcessingTask statuses needed for MVP-0 and harness validation:

- `queued`
- `running`
- `paused`
- `cancelled`
- `interrupted`
- `recovering`
- `succeeded`
- `succeeded_with_warnings`
- `blocked`
- `failed`

QualityIssue statuses needed for export and stale propagation:

- `open`
- `resolved`
- `accepted_warning`
- `stale`
- `superseded`

Artifact storage states needed for recovery:

- `present`
- `metadata_only_cleaned`
- `moved_to_trash`
- `missing`
- `deleted`

# 6. Transition or Decision Rules

Can this design support FakeProvider MVP-0?

Yes, if MVP-0 is intentionally narrow:

- One Project.
- One Batch.
- One Page.
- Page-level translation with TextBlock-level result persistence.
- FakeProvider stage outputs.
- Minimal retry budgets from ProcessingProfileSnapshot.
- Export check against QualityIssues.
- Artifact registration through ArtifactService.
- Recovery from durable task, attempt, result, artifact, issue, decision, and active pointer evidence.

Provider Adapter must not decide:

- Whether to retry the same stage.
- Whether to fallback to another Provider.
- Whether to skip a TextBlock, Page, or stage.
- Whether a warning is acceptable.
- Whether a QualityIssue is blocking.
- Whether the Page is ready for export.
- Whether warning export is allowed.
- Whether to pause for user action.
- Whether to mark workflow blocked.
- Whether to reuse cached results.
- Whether an artifact is official, retained, cleaned, or deleted.
- Whether provider refusal should be bypassed.

QualityCheckService must not decide:

- Next workflow stage.
- Retry budget consumption.
- Provider fallback.
- Cache reuse.
- Stage status transitions.
- Active pointer selection.
- Export success or failure.
- Task completion.
- Pause, cancel, or resume behavior.
- Artifact retention or cleanup.

WorkflowLoopEngine must decide:

- Continue to next stage.
- Retry same stage when retry budget remains.
- Fallback provider when policy and provider availability permit.
- Retry upstream stage when downstream issue root cause requires it.
- Skip target when profile allows skip and issue is non-blocking or accepted as warning.
- Mark warning when issue can remain visible without blocking export.
- Pause for user when automatic path is exhausted but user action can unblock.
- Block when unresolved blocking issues remain or required artifacts/results are unavailable.
- Finish ready only when active outputs are fresh and no open blocking issue is in scope.
- Finish with warnings only when warning export/readiness is allowed by ProcessingProfileSnapshot.

StageExecutor must not:

- Hold a database write transaction across provider/tool calls.
- Persist secrets or raw authorization values.
- Write official files outside ArtifactService.
- Make final workflow decisions.
- Bypass active pointer and stale propagation rules.

# 7. Recovery Impact

MVP-0 recovery can be implemented without a generic workflow engine if the repositories expose enough durable evidence.

Recovery should:

- Find stale `ProcessingTask.status = running` by heartbeat.
- Mark stale task `interrupted`, then `recovering`.
- Find `WorkflowAttempt.status = running`.
- Mark attempts `interrupted` or `abandoned_after_crash` when no durable completion evidence exists.
- Reconcile active OCR, translation, cleaned, and typeset pointers against result and artifact hashes.
- Check ProcessingArtifact storage state and file/hash presence.
- Reuse completed OCR/translation/results when hashes and profile-relevant config match.
- Resume from the next required stale/pending/failed stage.
- Create a WorkflowDecision explaining reuse, retry, warning, block, or recovery transition when useful for auditability.

Recovery must not:

- Reconstruct truth only from `Page.status`.
- Blindly rerun OCR, translation, cleaning, or typesetting when valid active outputs already exist.
- Promote orphan output files to official artifacts without ArtifactService validation.
- Treat provider refusal as crash.
- Clear blocking QualityIssues just because a task restarts.

Crash cases that are implementation-ready:

- Crash after OCR result and active pointer commit: resume translation without OCR rerun.
- Crash during provider call before output commit: mark attempt abandoned/interrupted and retry or block by profile.
- Crash after file write but before artifact registration: ArtifactService recovery handles orphan temp/attempt files.
- Crash after result creation but before active pointer update: recovery only promotes if an accepted decision or deterministic recovery rule proves validity.

# 8. Stale Propagation Impact

Implementation readiness depends on stale propagation being atomic with active pointer changes.

OCR edit should atomically:

- Create new OCRResult.
- Update `TextBlock.active_ocr_result_id`.
- Mark translation, translation_check, and typesetting stale.
- Set review status to needs_review.
- Mark Page translation context stale.
- Mark Page as having stale blocks.
- Mark downstream issues tied to old active translation/typesetting inputs stale or superseded.

Translation edit should atomically:

- Create new TranslationResult.
- Update `TextBlock.active_translation_result_id`.
- Mark typesetting stale.
- Set review status to needs_review.
- Mark Page as having stale blocks.
- Mark prior typesetting issues tied to old translation input stale or superseded.

FakeProvider MVP-0 should include at least one rerun-after-edit path:

- Re-run after OCR edit must not overwrite OCR history.
- Re-run after translation edit must not treat old typeset artifact as export-effective.
- Stale active pointers may remain selected for UI review, but export-effective checks must require fresh dependency hashes and no open blocking issue.

# 9. ProcessingProfileSnapshot Impact

MVP-0 needs only the profile snapshot fields that affect workflow decisions. Full profile management can remain deferred.

Minimal conceptual policy inputs:

- Retry budgets per stage, especially OCR, translation, cleaning, and typesetting.
- Fallback provider policy per stage, even if FakeProvider uses named fake alternatives.
- Allow skip for complex detection/cleaning cases.
- Allow warning readiness/export.
- Strictness that maps issues to warning or blocking through QualityCheckService and loop policy.
- Pause-on-blocking flag or equivalent policy for user-action paths.
- Debug/retention policy needed to decide whether successful payload artifacts are retained.
- Provider references and sanitized provider identity.
- Settings hash / profile hash for reproducible decisions.

Warning export/readiness must use the immutable ProcessingProfileSnapshot attached to the task or export, not the mutable current profile template.

The snapshot must not include raw API keys, tokens, credentials, or secret header values.

# 10. Artifact / QualityIssue / Active Pointer Impact

What must go through ArtifactService:

- Original uploaded image registration.
- Detection masks and visualizations when retained.
- OCR crops when retained.
- Raw OCR output when retained.
- Raw translation request/response payloads when retained.
- Failed attempt payloads.
- Provider refusal evidence artifacts when available.
- Cleaned image outputs.
- Typeset image outputs and overflow previews.
- Export image, ZIP, manifest, and issue snapshot artifacts.
- Debug bundles.
- Artifact missing checks.
- Retention cleanup and metadata-only cleanup.
- Trash moves and restore validation.

What must not go through Provider Adapter as official lifecycle:

- Official workspace path selection.
- Official file registration.
- File retention class selection.
- Cleanup eligibility.
- Artifact storage state updates.
- Active artifact pointer updates.

QualityIssue impact:

- QualityCheckService owns creation/classification.
- WorkflowLoopEngine consumes issues to decide next action.
- Export gate queries open blocking QualityIssues in scope.
- Warning issues may remain open/accepted and visible.
- Stale propagation must mark outdated issues stale or superseded.
- Provider refusal must create a provider refusal or stage-specific refusal issue, not a crash-only error.

Active pointer impact:

- Active OCR and translation pointers are on TextBlock.
- Active original, cleaned, and typeset artifact pointers are on Page.
- Active pointers are not duplicated with independent active flags on result rows.
- User edits create new result versions and update active pointers.
- Provider-created results become active only after workflow acceptance.
- Active does not always mean export-effective; freshness, dependency hashes, artifact state, and QualityIssues must be checked.

# 11. Repository and Transaction Implications

Conceptual repository methods likely needed for MVP-0:

- Project open/verify methods:
  - Verify app Project maps to project.db ProjectMetadata.
  - Load project workspace identity.

- Import methods:
  - Create Project/Batch/Page records where applicable.
  - Attach original artifact id to Page.
  - Query existing Page by import idempotency key or original artifact hash when appropriate.

- Task methods:
  - Create ProcessingTask with ProcessingProfileSnapshot.
  - Load active task by idempotency key.
  - Update task status/current_stage/progress/heartbeat.
  - Request pause/cancel.
  - Find stale running tasks.

- Attempt methods:
  - Create WorkflowAttempt before provider/tool call.
  - Mark attempt succeeded/failed/refused/skipped/reused/interrupted/abandoned.
  - Query attempts by task/stage/target.
  - Compute next attempt number.

- Decision methods:
  - Create WorkflowDecision.
  - Link WorkflowDecision to QualityIssues.
  - Load last decision for task/target/stage.

- Result methods:
  - Create OCRResult version.
  - Create TranslationResult version.
  - Query reusable OCRResult by input/config/provider/model/tool/geometry hashes.
  - Query reusable TranslationResult by source/context/glossary/provider/model/prompt/config hashes.
  - Update TextBlock active OCR pointer.
  - Update TextBlock active translation pointer.
  - Respect locked translation pointer.

- Stage status methods:
  - Load Page and TextBlock stage statuses.
  - Update TextBlock stage status.
  - Update Page summary status and stale flags.
  - Reconcile status from active pointers and artifact states.

- Detection methods:
  - Create TextBlocks for detected candidates.
  - Update TextBlock geometry, reading order, mask artifact pointer, detection status.
  - Query TextBlocks by Page in reading order.

- Artifact metadata methods:
  - Register ProcessingArtifact metadata through ArtifactService.
  - Update artifact storage state through ArtifactService-controlled flow.
  - Query active artifact pointers and artifact metadata.
  - Find missing or cleanup-eligible artifacts.

- Quality methods:
  - Create QualityIssue.
  - Deduplicate open issues by target/type/hash when appropriate.
  - Update issue status to resolved, accepted_warning, stale, or superseded.
  - Query open blocking issues in export scope.
  - Query warning issues in export scope.

- Tool log methods:
  - Create ToolRunLog with sanitized metadata.
  - Link tool run to attempt and artifacts.

- Export methods:
  - Create ExportRecord planned/blocked/succeeded/succeeded_with_warnings/failed.
  - Attach output artifact, manifest artifact, and issue snapshot artifact ids.
  - Persist blocked export metadata even when no output artifact is produced.

What must be atomic:

- New OCRResult creation + active OCR pointer update + downstream stale propagation + issue stale/supersede updates.
- New TranslationResult creation + active translation pointer update + typesetting stale propagation + issue stale/supersede updates.
- Accepted provider result creation + QualityIssue updates + WorkflowDecision + active pointer update + stage status update.
- Page-level translation partial success: valid TranslationResults + missing/invalid block QualityIssues + WorkflowDecision + stage statuses.
- Cleaned/typeset artifact acceptance: artifact metadata registration already complete, then Page active artifact pointer + issue updates + decision + stage status.
- Export gate decision: unresolved issue counts/hash + ExportRecord status + output artifact pointer if export succeeds.
- Retry/fallback decision: attempt outcome + issue updates + decision + retry budget before/after.
- Pause/cancel at safe boundary: task status + running attempt status + decision when applicable.
- Recovery reconciliation: stale task/attempt status changes + repair/reuse/block decision + stage status adjustments.

What must not be atomic with external calls:

- Provider/tool invocation must not hold a SQLite write transaction.
- Long file generation must not hold a SQLite write transaction except for short registration/update steps.
- Real OCR/LLM/image processing must run outside database write transactions.

Transaction failure implications:

- If DB commit fails after provider output, official artifact registration and orphan cleanup rules must keep recovery explainable.
- If file write fails before artifact registration, no active pointer may reference the failed file.
- If active pointer commit fails, the result may exist but must not be export-effective until recovery or a later decision selects it.

# 12. Invariants

- Provider Adapter only calls tools and returns structured outputs or standardized errors.
- Provider Adapter does not access SQLite.
- Provider Adapter does not register official artifacts.
- Provider Adapter does not create QualityIssues.
- Provider Adapter does not decide retry, fallback, skip, warning, pause, block, export, or cache reuse.
- QualityCheckService detects/classifies issues and root-stage attribution, but does not advance workflow state.
- WorkflowLoopEngine owns loop decisions.
- ArtifactService owns official artifact path, hash, registration, retention, cleanup, trash, and missing-file lifecycle.
- Repository / DAO owns SQLite access.
- No image BLOBs or large payload bytes are stored in SQLite.
- Original images are never overwritten.
- Domain rows use artifact ids rather than authoritative file paths.
- OCRResult and TranslationResult are immutable and versioned.
- Active OCR/translation result selection uses TextBlock pointers, not result active flags.
- Current cleaned/typeset Page outputs use Page active artifact pointers.
- Recovery does not rely only on `Page.status`.
- WorkflowAttempt metadata is always persisted.
- Failed attempt artifacts are persisted by default when available.
- Normal export blocks unresolved open blocking QualityIssues.
- Warning export/readiness follows ProcessingProfileSnapshot.
- API keys, tokens, credentials, and secret headers are not stored in project.db, logs, snapshots, examples, or debug artifacts.
- Provider refusal is a workflow path, not a crash and not a bypass target.

# 13. Rejected Alternatives

Rejected for MVP-0 or as overengineering:

- Generic workflow engine or BPM library.
- Distributed queue or multi-worker orchestration.
- Plugin system for stages or Providers.
- Full Provider Adapter DTO schema in this workflow-state design.
- Full ArtifactService directory layout in this workflow-state design.
- Full QualityIssue taxonomy in this workflow-state design.
- ORM mapping and migration design in this workflow-state design.
- API route schema in this workflow-state design.
- Frontend review UI design in this workflow-state design.
- Prompt template design or policy-bypass prompting.
- P1 forced/incomplete export as a requirement for MVP.
- P1 GeometryRevision as a requirement for MVP.
- P2 multi-page ContextPack or multi-page translation as a requirement for MVP.
- Advanced artifact lineage graph as a requirement for MVP.
- Full manual typography controls as a requirement for MVP.
- LaMa as a required MVP cleaning path.
- Automatic local translation fallback as a required MVP path; manual or fake fallback is enough for MVP-0 validation.
- Export manifest detail schema as a requirement for MVP-0.
- Cost/token rollups as a requirement for MVP-0.
- Project-wide batch optimization as a requirement for single-Page MVP-0.

Rejected because they violate boundaries:

- Provider Adapter writes directly to project.db.
- Provider Adapter writes official artifacts to workspace paths.
- Provider Adapter decides fallback or retry.
- QualityCheckService advances Page or Task state.
- StageExecutor updates active pointers without WorkflowLoopEngine decision.
- UI or API handler directly calls OCR/LLM/cleaning/typesetting tools.
- Page.status as the sole recovery source of truth.
- Active flags on OCRResult or TranslationResult rows.
- Image BLOBs in SQLite.
- Overwriting original uploaded images.

# 14. Validation Against HARNESS Scenarios

H01 Single Page happy path: PASS.

The proposed MVP-0 path can create original, detected TextBlocks, OCRResults, TranslationResults, cleaned/typeset artifacts, attempts, decisions, and export readiness through FakeProviders. Normal export is allowed when no open blocking issue remains.

F01 OCR fails once then succeeds by retry: PASS.

The repository/transaction model persists failed attempt, retry decision, retry budget consumption, successful retry attempt, OCRResult, active OCR pointer, and downstream continuation.

F02 Translation output is invalid JSON then retry succeeds: PASS.

FakeProvider can return invalid output. The design records attempt/log/artifact evidence, QualityIssue, retry decision, budget consumption, and then valid TranslationResults after retry.

F03 Page-level translation returns partial output: PASS.

The design requires atomic persistence of valid per-block TranslationResults, issues for missing/invalid blocks, WorkflowDecision, and stage status updates.

F04 Provider refusal: PASS.

Provider refusal is standardized by Provider Adapter, recorded in ToolRunLog and WorkflowAttempt, classified as QualityIssue, and handled by WorkflowLoopEngine through fallback, warning, skip, pause, or block according to profile.

F05 Cleaning skips complex background: PASS.

Cleaning skip is represented as skipped stage status and warning or blocking QualityIssue according to profile. Page can become ready_for_export_with_warnings when allowed.

F06 Typesetting overflow: PASS.

Typesetting overflow preview goes through ArtifactService, issue creation goes through QualityCheckService, and decision is warning, retry upstream, pause, or block by WorkflowLoopEngine/profile.

S01 OCR edit after translation exists: PASS.

Atomic OCR edit transaction creates a new OCRResult, updates active OCR pointer, marks translation/check/typesetting stale, marks page context stale, and stales/supersedes downstream issues.

S02 Translation edit after typesetting exists: PASS.

Atomic translation edit creates a new TranslationResult, updates active translation pointer, marks typesetting stale, sets review needs_review, marks page stale, and stales/supersedes prior typesetting issues.

R01 Crash after OCR before translation: PASS.

Recovery reuses active OCR pointer and result/hash evidence, marks stale task/attempt states, and resumes translation without rerunning OCR.

R02 Crash during provider call: PASS.

Stale running attempt becomes interrupted or abandoned_after_crash. Recovery chooses retry, reuse, or block from durable evidence and profile.

R03 Missing artifact during recovery: PASS.

ArtifactService detects missing/hash mismatch, updates storage state or creates issue path, and WorkflowLoopEngine decides rebuild, retry upstream, warning, or block.

E01 Normal export with unresolved blocking issue: PASS.

Export repository query rejects open blocking issues in scope, persists blocked ExportRecord, and produces no normal output artifact.

E02 Warning export allowed by profile: PASS.

Warning export/readiness follows ProcessingProfileSnapshot and records warning state in ExportRecord.

E03 Warning export not allowed by profile: PASS.

WorkflowDecision and/or ExportRecord can explain profile-based rejection or blocked state.

T01 Pause then resume: PASS for design readiness, but detailed safe-boundary mechanics remain final-design work.

The model supports pause request, safe-boundary attempt/task updates, and resume from durable state. Exact stage-specific interruption behavior should be finalized.

T02 Cancel then new task: PASS for design readiness.

Cancelled task does not auto-resume. New task can reuse durable active results/artifacts by hash-compatible cache/reuse rules.

I01 Re-run completed Page without input changes: PASS.

Repository cache lookups and `reuse_cached_result` decision avoid duplicate active results and provider calls.

I02 Re-run after OCR edit: PASS.

Active edited OCR remains selected, downstream stale state prevents old translation/typeset artifacts from being export-effective, and old outputs remain auditable.

Scope-control checks: PASS.

This proposal does not require production code, DDL, ORM mappings, API schemas, full Provider DTOs, full Artifact layout, full QualityIssue taxonomy, P1 forced export, P1 GeometryRevision, P2 multi-page context, distributed workers, or generic workflow engine.

# 15. Risks

- Repository contracts may become too broad if implementation tries to build every conceptual method at once.
  Mitigation: implement only the methods needed by the FakeProvider vertical slice first.

- StageExecutor boundaries may blur if executors start deciding retries or updating active pointers directly.
  Mitigation: require WorkflowLoopEngine decision before active selection and state advancement.

- Artifact registration and DB commit can drift if file writes and database updates are not carefully sequenced.
  Mitigation: use ArtifactService safe write/register semantics and recovery for orphan temp/attempt files.

- QualityCheckService may be tempted to encode workflow policy.
  Mitigation: keep QualityCheckService output limited to issues, severity/blocking classification, attribution, and suggested action.

- FakeProvider success can hide real Provider schema complexity.
  Mitigation: use FakeProvider for workflow architecture only, then run separate Provider Adapter and real-tool spikes.

- Page summary status can drift from TextBlock stage statuses and active pointers.
  Mitigation: treat Page status as summary/derived-repairable state, not recovery truth.

- Warning export semantics may be underspecified.
  Mitigation: final workflow-state design should define exact ProcessingProfileSnapshot fields and whether per-export acknowledgement is deferred.

- Retention and debug policies can expose sensitive local content if too broad.
  Mitigation: no secrets in logs/artifacts; debug artifacts must carry safety flags and follow explicit profile policy.

# 16. Open Questions

1. Exact repository method names and grouping are deferred to Repository / persistence detailed design.
2. Exact enum spellings for task, attempt, stage, issue, artifact, and export statuses remain open in the data-model final open questions.
3. Exact safe-boundary behavior for pause/cancel during each Provider call remains to be finalized.
4. Whether warning export requires per-export user acknowledgement in addition to ProcessingProfileSnapshot remains open.
5. Exact ArtifactService temp directory, atomic write, orphan recovery, and retention TTL behavior remains deferred to ArtifactService detailed design.
6. Exact QualityIssue issue types, severity mapping, and user-facing messages remain deferred to QualityCheckService detailed design.
7. Exact Provider Adapter structured input/output schemas remain deferred to Provider Adapter detailed design.
8. Exact retry budget arithmetic and whether fallback consumes the same or separate budget remains to be finalized by workflow-state synthesis.
9. Exact behavior for result row exists but active pointer is missing after crash needs a final recovery rule.
10. Whether MVP-0 needs `WorkflowDecisionIssue` physically implemented or can temporarily use structured issue references is open in data-model notes, though the final data model recommends the relation.
