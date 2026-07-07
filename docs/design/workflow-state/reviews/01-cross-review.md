# 1. Summary of each proposal.

## Proposal 01: State vocabulary and transitions

The proposal defines a layered state model: `ProcessingTask` for command lifecycle, `WorkflowAttempt` for bounded execution evidence, `WorkflowDecision` for rationale, and Page/TextBlock state plus active pointers for current domain state. It recommends aggregate Page statuses, per-TextBlock stage statuses, safe stage boundaries, legal/illegal transitions, and explicit recovery from tasks, attempts, decisions, artifacts, issues, hashes, and active pointers rather than `Page.status` alone.

Strong points:

- Clear rejection of `Page.status` as recovery source of truth.
- Good separation between Page aggregate status and TextBlock stage statuses.
- Strong provider, artifact, quality, repository, active-pointer, export-gate invariants.
- Covers all HARNESS scenarios at a high level.

Review concerns:

- Uses `done` while other proposals use `completed`.
- Introduces `locked` as a TextBlock stage status while also acknowledging `locked_translation_result_id`; this can duplicate lock state.
- Treats `ready_for_export_with_warnings` as both readiness and warning export policy outcome; final synthesis must distinguish readiness from actual export attempt.
- Leaves all-skipped Page aggregation unresolved.

## Proposal 02: Decision, retry, and profile

The proposal defines `WorkflowDecision` semantics, retry budget consumption, fallback rules, skip rules, warning versus block behavior, pause-for-user behavior, and minimal `ProcessingProfileSnapshot` inputs. It correctly keeps retry, fallback, skip, warning, pause, and block decisions inside `WorkflowLoopEngine`.

Strong points:

- Good decision priority order.
- Explicit finite retry semantics.
- Strong provider refusal handling without bypass or evasion.
- Good distinction between same-stage retry budget and fallback allowance.
- Clear minimal snapshot fields.

Review concerns:

- Retry budget is decremented when a retry decision is created, while attempts also carry retry budget before/after. Final design must choose the canonical counter reconstruction rule.
- The profile/QualityCheckService split is close to ambiguous: QualityCheckService owns issue classification, while profile may influence warning/blocking policy. Final synthesis must define which layer owns severity and `is_blocking`.
- Warning export acknowledgement remains unresolved.
- Whether translation provider refusal can ever become warning is left open and should be conservative.

## Proposal 03: Recovery and idempotency

The proposal defines startup/project-open reconciliation, stale running task handling, stale running attempt handling, recovery evidence, idempotent reuse rules, missing artifact behavior, and export-effective checks. It treats recovery as evidence reconciliation, not blind rerun.

Strong points:

- Strongest coverage of R01/R02/R03 and I01/I02.
- Explicit active pointer plus dependency hash checks for reuse.
- Explicit warning against trusting files alone or `Page.status` alone.
- Good treatment of provider refusal as first-class workflow path.

Review concerns:

- Uses `completed` as a task/stage status while Proposal 01/05 prefer `succeeded`/`done`.
- Says recovery may parse/reuse retained provider output when hashes match and acceptance rules can be replayed. This is safe only if final design narrows replay rules; otherwise recovery could bypass normal QualityCheck/WorkflowDecision acceptance.
- Does not decide whether `abandoned_after_crash` consumes retry budget, which is needed to prevent crash/retry loops.
- Auto-resume after crash is left open.

## Proposal 04: Stale propagation and user edits

The proposal defines OCR edit and translation edit behavior, active pointer updates, downstream stale propagation, issue stale/superseded behavior, review state, and late provider output handling. It correctly treats stale as dependency invalidation, not deletion.

Strong points:

- Best coverage of S01/S02 and I02.
- Preserves old results/artifacts for review while blocking stale outputs from export-effectiveness.
- Correctly leaves cleaned image unchanged after OCR/translation text edits.
- Strong issue staling guidance based on result ids and hashes.

Review concerns:

- Uses `completed` while other proposals use `done`.
- Suggests user edit actions may create a `WorkflowDecision` or "audit-equivalent decision"; final design must decide whether `WorkflowDecision` is engine-only.
- Translation edit sets `translation_check_status = stale` or `needs_review`; the proposal recommends stale but leaves canonical state unresolved.
- Locked translation after OCR edit is unresolved.

## Proposal 05: Implementation readiness and scope

The proposal checks whether the combined design can support a FakeProvider single-Page backend vertical slice. It defines conceptual StageExecutor, Provider Adapter, QualityCheckService, ArtifactService, Repository, transaction, active pointer, and scope boundaries.

Strong points:

- Strong MVP-0 readiness framing.
- Strongest explicit boundary checklist.
- Good atomicity list for result acceptance, partial translation, export gate, retry/fallback, pause/cancel, recovery.
- Correctly rejects P1/P2 features and overengineering.

Review concerns:

- Its `StageExecutor` wording says executors call Provider Adapters, ArtifactService, repositories, and QualityCheckService "through WorkflowLoopEngine-controlled flow"; final design must make sure StageExecutor cannot mutate official state or decide workflow outcomes.
- Uses `done` and `locked`, while Proposal 04 uses `completed`.
- Leaves safe-boundary mechanics for pause/cancel under-specified.
- Lists many conceptual repository methods; final synthesis should not accidentally turn this workflow-state design into a persistence design.

# 2. Agreements across proposals.

All proposals agree on the main architecture:

- MVP stages are import, detection, OCR, translation, translation check, cleaning, typesetting, and export/export check.
- `WorkflowLoopEngine` owns continue, retry, fallback, skip, warning, pause, cancel, block, and finish decisions.
- Provider Adapters only call tools and return structured outputs/errors.
- Provider Adapters do not access SQLite, register official artifacts, create `QualityIssue`, decide retry/fallback/skip/warning/pause/cancel/block, or perform policy bypass.
- `ArtifactService` owns official artifact path, hash, registration, retention, cleanup, missing state, and trash behavior.
- Repository / DAO owns SQLite access.
- `QualityCheckService` checks outputs, classifies issues, and attributes root stage, but does not advance workflow state.
- Active pointers are the P0 current-result source of truth.
- Stale state does not clear active pointers; it makes selected output non-export-effective.
- Recovery must use tasks, attempts, decisions, artifacts, issues, active pointers, hashes, and stage statuses, not `Page.status` alone.
- Normal export blocks unresolved open blocking `QualityIssue`.
- Warning export/readiness follows `ProcessingProfileSnapshot`.
- Original images are never overwritten.
- Image files and large payloads are not stored in SQLite.
- Provider refusal is a first-class workflow path.
- P1/P2 features such as forced export, GeometryRevision, multi-page context translation, distributed workers, and a generic workflow engine are not MVP prerequisites.

# 3. Conflicts between proposals.

- Stage status spelling: Proposal 01/05 use `done`; Proposal 03/04 use `completed`. Final synthesis must choose one canonical value. Prefer `done` only if aligning with data-model stage examples, or `completed` only if used consistently across task/page/stage vocabularies.
- Task terminal spelling: Proposal 01 uses `succeeded` / `succeeded_with_warnings`; Proposal 03 uses `completed`. Final synthesis should prefer `succeeded` / `succeeded_with_warnings` for `ProcessingTask` to avoid confusing task completion with stage `done`.
- Stage enum spelling: Proposal 01 uses `export_check`; Proposal 05 uses `export`; data model includes `export`. Final synthesis must decide whether `export_check` is a workflow stage or a decision/precheck inside `export`.
- Lock state: Proposal 01/05 include `locked` as a TextBlock stage status; data model already has `locked_translation_result_id`. Final synthesis should avoid duplicate lock truth.
- User edit audit: Proposal 04 suggests `WorkflowDecision` or audit-equivalent records for user edits; other proposals mostly reserve decisions for loop outcomes. Final synthesis must decide whether user actions create `WorkflowDecision` or a separate future audit concept.
- Recovery promotion: Proposal 03 allows replaying retained provider output into results under strict conditions; Proposal 05 warns recovery should only promote after accepted decision or deterministic rule. Final synthesis must narrow this path.
- Retry budget counting: Proposal 02 decrements on retry decision; Proposal 03 leaves `abandoned_after_crash` budget treatment open. Final synthesis must make crash-loop behavior finite.
- Translation edit check state: Proposal 04 leaves `translation_check_status = stale` versus `needs_review` open.
- Warning export acknowledgement: multiple proposals keep this open. It does not block workflow-state synthesis if per-export acknowledgement is explicitly deferred.

# 4. Missing HARNESS coverage.

The proposal set covers every HARNESS scenario at least at a high level, but several scenarios need sharper final replay:

- T01 pause/resume: proposals say "safe boundary" but do not define per-stage behavior for non-cancellable provider calls.
- R02 crash during provider call: final design must state whether abandoned attempts count against retry or a separate crash budget.
- R03 missing artifact: proposals state rebuild/retry/warn/block but do not define minimum rebuildability rules by stage.
- F03 partial Page translation: proposals agree valid block results persist, but final design must define stage statuses for valid, missing, and invalid blocks in one page-level attempt.
- F04 provider refusal: proposals allow fallback/warning/skip/pause/block, but final design should make translation refusal conservative and prohibit automatic warning unless a valid manual/local/skipped path exists.
- E02/E03 warning export: warning export follows snapshot, but per-export user acknowledgement is unresolved.
- I01 rerun completed Page: proposals say reuse cached result, but final design must prevent duplicate active results when reusable historical result exists but is not currently active.
- I02 rerun after OCR edit: proposals cover stale propagation, but final design must specify old TranslationResults are not export-effective even if still active.

# 5. Ambiguous status vocabulary.

Ambiguities to resolve in final synthesis:

- `done` versus `completed` for TextBlock stage state.
- `succeeded` versus `completed` for `ProcessingTask`.
- `export` versus `export_check` as stage name.
- `paused`, `pausing`, `cancelled`, `cancelling`: Proposal 01 includes transitional statuses; Proposal 05's MVP list omits `pausing` and `cancelling`.
- `locked` as stage status versus `locked_translation_result_id` plus review metadata.
- `needs_review` as Page status, TextBlock review status, and issue-driven UI state.
- `ready_for_export_with_warnings` as Page readiness versus export permission.
- `failed`, `blocked`, and `needs_review` for per-block partial translation failures.
- `stale` versus `superseded` versus `resolved` for old issues after user edits.

Recommended stance: keep status vocabulary small and stable. Use result pointers and issue state for truth; treat Page status as a repairable aggregate.

# 6. Unsafe transitions.

No proposal intentionally defines an unsafe transition that violates a hard invariant. The final design should explicitly reject these risky transitions:

- `cancelled` task resuming automatically; continuation must create a new task.
- `blocked` task resuming without a resolving action or explicit resume decision.
- `translation_status = done/completed` without an active translation pointer, except skipped/non-processable block rules.
- `ocr_status = done/completed` without an active OCR pointer, except truly skipped/non-text block rules.
- Downstream stage becoming fresh while upstream required state is stale, failed, blocked, or missing.
- Recovery selecting provider output whose input/context hashes no longer match current active inputs.
- Automatic workflow replacing a locked translation without explicit user override.
- Export using stale active typeset artifact as current output.
- Normal export creating an output artifact while open blocking issues remain.
- Warning export proceeding when the relevant `ProcessingProfileSnapshot` disallows it.

# 7. Infinite loop risk.

Potential loop risks:

- `abandoned_after_crash` retry accounting is unresolved. If abandoned attempts never consume any budget or crash budget, repeated crashes can loop forever.
- Recovery may retry a provider call after crash without checking reusable durable output or prior fallback decisions.
- Fallback provider visited-set semantics are only described at a high level.
- `retry_upstream_stage` can loop between translation shortening and typesetting overflow unless profile has explicit upstream retry/shortening budget and issue hash keys.
- Pause-for-user can become a resume/block loop if the user resumes without changing the blocking condition.

Recommended final decisions:

- Count automatic retry authorization from persisted `WorkflowDecision` records.
- Add a hard per-task automatic decision ceiling in addition to per-stage budgets.
- Track fallback providers already attempted for the stage/target/input key.
- Treat unchanged resume from `pause_for_user` as `block` when no new evidence/config/edit exists.
- Define whether `abandoned_after_crash` consumes normal retry budget or a separate crash-retry budget.

# 8. Recovery gaps.

Recovery is broadly well covered, but final synthesis must fill these gaps:

- Exact heartbeat stale threshold can remain implementation detail, but final design should state it is configurable/implementation-defined.
- Whether recovery auto-resumes after crash or leaves tasks paused is open. This can be task/profile policy.
- Recovery promotion of retained raw provider output must be constrained. MVP should prefer already committed result rows and active pointers; parsing raw output can be deferred unless the same validation and acceptance path is replayed.
- Result row exists but active pointer is missing after crash needs a canonical rule.
- Artifact missing rebuildability by stage is not fully defined.
- Recovery should define issue handling when artifact metadata is present but bytes were `metadata_only_cleaned`.
- Concurrent user edit during recovery is only mentioned as a risk; final design should require expected-state/transaction checks.

# 9. Idempotency gaps.

Idempotency is strong conceptually, but final synthesis needs sharper rules:

- The cache/reuse key for each stage must be canonical enough for MVP. Data-model final already lists keys; workflow final should reference them instead of re-inventing.
- Reuse of non-active historical results must state when the workflow may select them as active.
- Reuse should create `WorkflowAttempt.status = reused_cached` or `WorkflowDecision.decision_type = reuse_cached_result`; final design should decide whether both are required.
- Rerun after OCR edit must never treat old active translation as export-effective if `source_ocr_result_id` / `source_text_hash` mismatch.
- Rerun with a locked translation must preserve lock semantics.
- Rebuild of cleaned/typeset artifacts must validate active upstream artifact/result hashes, not only stage status.

# 10. Provider Adapter boundary violations.

No direct Provider Adapter boundary violation was found.

The proposals consistently state that Provider Adapters:

- call tools only;
- return structured outputs/errors and provider metadata;
- do not access SQLite;
- do not register official artifacts;
- do not create `QualityIssue`;
- do not decide retry, fallback, skip, warning, pause, cancel, block, cache reuse, or export readiness;
- do not perform provider policy bypass/evasion logic.

Non-blocking caution:

- Final synthesis should keep StageExecutor wording clear so Provider Adapter temporary files are promoted only by ArtifactService, never by the adapter.

# 11. QualityCheckService boundary violations.

No direct QualityCheckService boundary violation was found.

The proposals consistently keep QualityCheckService responsible for checking outputs, classifying issues, assigning severity/blocking/root-stage/suggested action, and not advancing workflow state.

Non-blocking caution:

- Proposal 02 and 05 discuss profile strictness affecting warning/blocking behavior. Final design must prevent policy drift: either QualityCheckService computes severity/is_blocking using the immutable snapshot as input, or WorkflowLoopEngine applies profile policy to already-classified issues. Do not split ownership ambiguously.

# 12. ArtifactService boundary violations.

No direct ArtifactService boundary violation was found.

The proposals consistently keep ArtifactService as the only official artifact lifecycle entry for paths, safe writes, hashes, registration, storage state, retention, cleanup, trash, missing detection, and restore validation.

Non-blocking cautions:

- Proposal 03/05 mention orphan file recovery. Final design must keep workflow decisions outside ArtifactService: ArtifactService may find/register/mark files, but WorkflowLoopEngine decides reuse/retry/rebuild/warn/block.
- Recovery should not promote raw provider artifacts into accepted domain results without the normal quality and decision path.

# 13. Repository / DAO boundary violations.

No direct Repository / DAO boundary violation was found.

The proposals consistently route all SQLite access through Repository / DAO.

Non-blocking cautions:

- Proposal 05 lists many conceptual repository methods. Final synthesis should keep them conceptual and avoid becoming an ORM/persistence design.
- Atomicity requirements are appropriate, but exact SQL constraints, method names, and migration details belong to persistence design.

# 14. Export gate mistakes.

No proposal permits normal export with unresolved open blocking `QualityIssue`.

Potential mistakes to avoid in synthesis:

- Do not equate `ready_for_export_with_warnings` with actual export if the export snapshot disallows warning export.
- Do not allow skipped TextBlocks to produce pure `ready_for_export`; they must be warning-bearing.
- Do not allow stale active typeset artifacts to satisfy export readiness.
- Do not let accepted/stale/superseded old issues hide current open blocking issues.
- Do not introduce P1 forced/incomplete export into MVP.
- Do not create a normal output artifact for blocked export; persist rejected/blocked export metadata only.

# 15. P1/P2 scope creep.

Scope control is mostly strong. The proposals correctly reject:

- forced/incomplete export as P0;
- `GeometryRevision` as P0;
- multi-page context translation as P0;
- distributed workers and generic workflow engines;
- plugin systems;
- full Provider Adapter DTO schema;
- full ArtifactService directory layout;
- full QualityIssue taxonomy;
- SQL DDL, ORM mappings, API schemas, frontend UI, provider integrations, prompt templates;
- professional typesetting, advanced manual typography, LaMa as required MVP, and batch optimization.

Minor scope creep risks:

- Recovery parsing retained provider raw output may pull Provider/Quality/Artifact details into workflow-state design. Prefer deferring or tightly constraining.
- User edit audit via `WorkflowDecision` may expand decision semantics beyond engine decisions. Decide narrowly.
- Repository method list could grow into persistence design if copied too literally.

# 16. Recommended final decisions.

- Canonical stages: `import`, `detection`, `ocr`, `translation`, `translation_check`, `cleaning`, `typesetting`, `export_check`; map `export_check` to export precondition logic and keep actual export records in export design.
- `ProcessingTask` statuses: `queued`, `running`, `pausing`, `paused`, `cancelling`, `cancelled`, `interrupted`, `recovering`, `succeeded`, `succeeded_with_warnings`, `blocked`, `failed`.
- `WorkflowAttempt` statuses: `planned`, `running`, `succeeded`, `failed`, `refused`, `cancelled`, `skipped`, `reused_cached`, `interrupted`, `abandoned_after_crash`.
- TextBlock stage statuses: use one canonical completion value. Recommendation: `done`, because data-model stage examples already use `done`. Do not also use `completed`.
- Do not use `locked` as a generic stage status. Use `locked_translation_result_id` and review/lock metadata.
- Page status is a persisted, repairable aggregate. It is never recovery truth.
- User edits should create immutable result versions and stale propagation. If audit is needed in MVP, use a narrowly defined workflow/user action decision only if final design clearly states it is not a provider-loop decision.
- Retry budget is consumed by persisted retry decisions; attempts mirror before/after budget for audit.
- Add a finite crash retry or abandoned-attempt rule.
- Recovery in MVP should reuse already committed results/artifacts. Parsing raw provider output into new accepted results should be deferred or require replay through QualityCheckService and WorkflowLoopEngine acceptance.
- Provider refusal must default to fallback, pause/manual, skip target where explicitly allowed, or block. Do not treat refusal as generic retryable failure.
- Warning export requires `ProcessingProfileSnapshot.allow_warning_export`; per-export acknowledgement can be a non-blocking deferred question.
- All-skipped Page should not become pure `ready_for_export`; final design should choose `ready_for_export_with_warnings` if profile allows and a usable output exists, otherwise pause/block.

# 17. ADR candidates.

Recommended ADRs for final synthesis:

- Canonical workflow status vocabulary and Page status as repairable aggregate.
- Retry budget accounting and crash-abandoned attempt handling.
- Warning readiness/export policy and optional user acknowledgement.
- Recovery promotion/reuse rules for committed results versus retained raw provider output.
- User edit audit boundary: `WorkflowDecision` versus separate future audit event.
- Locked translation state represented by pointer/metadata, not stage status.
- Export check as workflow stage versus export use-case precheck.

# 18. Blocking issues.

No blocking proposal issues found.

The proposal set does not violate hard architecture invariants and is sufficient for a synthesizer to produce final workflow-state design. The conflicts above are synthesis decisions, not blockers requiring proposal revision.

# 19. Non-blocking issues.

- Canonical enum spellings are inconsistent.
- `locked` stage status duplicates `locked_translation_result_id`.
- `export` versus `export_check` is unresolved.
- Warning export acknowledgement is unresolved.
- `abandoned_after_crash` retry accounting is unresolved.
- Recovery auto-resume policy is unresolved.
- Partial Page translation per-block status outcomes need final table detail.
- Safe-boundary behavior for pause/cancel during provider calls needs final table detail.
- Recovery promotion of retained raw provider output needs narrowing.
- Translation edit `translation_check_status` should be canonicalized.
- All-skipped Page aggregation needs final rule.
- User edit audit through `WorkflowDecision` needs final rule.

# 20. Open questions that block final synthesis.

None.

# 21. Open questions that do not block final synthesis.

- Exact enum spellings for stages, statuses, decisions, reason codes, issue types, and artifact types.
- Whether warning export requires per-export user acknowledgement in addition to `ProcessingProfileSnapshot`.
- Exact heartbeat timeout threshold.
- Whether recovery auto-resumes by default or waits for user/profile policy.
- Whether `abandoned_after_crash` consumes normal retry budget or separate crash budget.
- Exact rebuildability matrix for missing artifacts by stage.
- Exact QualityIssue taxonomy and user-facing messages.
- Exact Provider Adapter DTO schemas.
- Exact ArtifactService directory layout, orphan recovery, retention TTLs, and temp file rules.
- Exact Repository method names, ORM mappings, SQL constraints, and migrations.
- Exact UI/API semantics for locking/unlocking translations and marking review complete.
