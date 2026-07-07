# Phase 5 HARNESS Validation: Workflow-State Core Design

## Verdict

The final workflow-state design is acceptable for a FakeProvider single-Page backend vertical slice.

No hard invariant fails. The remaining `UNCLEAR` items are non-blocking implementation-detail deferrals, mainly exact export attempt metadata, QualityIssue taxonomy, Provider Adapter DTOs, default profile budgets, and ArtifactService layout/retention mechanics.

## Files read

- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/design/workflow-state/HARNESS.md`
- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/workflow-state/final/state-vocabulary.md`
- `docs/design/workflow-state/final/stage-transition-table.md`
- `docs/design/workflow-state/final/decision-matrix.md`
- `docs/design/workflow-state/final/recovery-rules.md`
- `docs/design/workflow-state/final/stale-propagation-rules.md`
- `docs/design/workflow-state/final/open-questions.md`
- `docs/design/workflow-state/adr/0001-canonical-workflow-vocabulary.md`
- `docs/design/workflow-state/adr/0002-retry-budget-and-crash-attempts.md`
- `docs/design/workflow-state/adr/0003-export-check-and-warning-readiness.md`
- `docs/design/workflow-state/adr/0004-recovery-committed-results-first.md`

## Invariant checklist

| Invariant | Result | Notes |
| --- | --- | --- |
| Provider Adapter only calls tools and returns structured results or standardized errors. | PASS | Final design limits adapters to tool calls, structured outputs/errors, temporary files, and metadata. |
| Provider Adapter must not access SQLite. | PASS | Repository / DAO is the only SQLite access entry. |
| Provider Adapter must not register official artifacts. | PASS | ArtifactService is the only official lifecycle entry. |
| Provider Adapter must not create QualityIssue. | PASS | QualityCheckService owns issue creation/classification. |
| Provider Adapter must not decide retry, fallback, skip, warning, pause, cancel, or block. | PASS | WorkflowLoopEngine owns all workflow decisions. |
| ArtifactService is the only official artifact lifecycle entry. | PASS | Path generation, atomic write/promotion, hash, registration, retention, cleanup, trash, and missing checks are assigned to ArtifactService. |
| Repository / DAO is the only SQLite access entry. | PASS | Final design states DAO persists tasks, attempts, decisions, issues, artifacts, versions, pointers, and statuses. |
| WorkflowLoopEngine owns workflow decisions. | PASS | Decision matrix explicitly assigns continue/reuse/retry/fallback/skip/warning/pause/block/finish/cancel to the loop. |
| QualityCheckService checks outputs and classifies issues, but does not advance workflow state. | PASS | Final design keeps state advancement and workflow outcomes out of QualityCheckService. |
| Original images are never overwritten. | PASS | Import/artifact/recovery rules preserve original image and block if it is missing. |
| Image files and large payloads are not stored in SQLite. | PASS | Design stores metadata/pointers/hashes in SQLite and files in workspace artifacts. |
| Active pointers are the source of truth for current OCR, translation, cleaned image, and typeset image. | PASS | Reuse, stale propagation, and export-effective rules all depend on active pointers plus hashes/artifacts. |
| Recovery must not rely only on Page.status. | PASS | Recovery uses tasks, attempts, decisions, pointers, hashes, artifacts, ToolRunLogs, QualityIssues, and TextBlock stage statuses. |
| Normal export blocks unresolved blocking QualityIssue. | PASS | Export readiness and ADR 0003 enforce this. |
| Warning export follows ProcessingProfileSnapshot. | PASS | Warning readiness/export requires `allow_warning_export = true`. |
| No manga search/scraping/download/distribution/publishing. | PASS | Final design repeats the product boundary and adds no such behavior. |
| No provider policy bypass/evasion logic. | PASS | Refusal paths allow fallback/manual/skip/warn/block only; evasion is explicitly rejected. |

## Scenario replay results

### H01: Single Page happy path

- Initial state: Project/Batch/Page exist; original image imported as an official artifact; Page `uploaded`; TextBlock stages `pending`.
- Trigger: Start one-page processing with a ProcessingProfileSnapshot and FakeProvider success responses.
- Expected state changes: `import -> detection -> ocr -> translation -> translation_check -> cleaning -> typesetting -> export_check`; required TextBlock stages become `done`; Page becomes `ready_for_export`; task becomes `succeeded`.
- Expected WorkflowAttempt behavior: One accepted attempt per stage, each terminal `succeeded`.
- Expected WorkflowDecision behavior: `continue` between stages, then `finish_ready_for_export`.
- Expected QualityIssue behavior: No open blocking issue remains; no warning issue required.
- Expected artifact or active pointer behavior: Active OCR and translation pointers set on TextBlocks; active cleaned and typeset Page artifacts set; artifacts are official, present, and hash-valid.
- Export impact: Normal export allowed.
- Result: PASS.

### F01: OCR fails once then succeeds by retry

- Initial state: Detection `done`; TextBlock OCR `pending`; retry budget remains.
- Trigger: OCR provider returns a retryable failure, then a valid OCR result.
- Expected state changes: First OCR state becomes `failed` or remains non-current with issue evidence; retry returns OCR to `running`; accepted retry sets OCR `done`; downstream stages continue.
- Expected WorkflowAttempt behavior: Failed OCR attempt persists; successful retry attempt persists.
- Expected WorkflowDecision behavior: `retry_same_stage` persisted before retry and consumes OCR budget; then `continue`.
- Expected QualityIssue behavior: Failure issue is recorded and then resolved, superseded, or no longer blocking after success.
- Expected artifact or active pointer behavior: Active OCR pointer is set only after accepted retry; old failed payload may remain as failed-attempt artifact.
- Export impact: No export block after successful retry.
- Result: PASS.

### F02: Translation output is invalid JSON then retry succeeds

- Initial state: Active OCR pointers exist; translation `pending`; translation retry budget remains.
- Trigger: Translation provider returns invalid JSON, then valid structured output.
- Expected state changes: Invalid output leaves translation not `done`; retry success creates TranslationResults and sets translation `done`.
- Expected WorkflowAttempt behavior: Invalid attempt persists as `failed` or invalid-output outcome; retry attempt persists as `succeeded`.
- Expected WorkflowDecision behavior: `retry_same_stage` consumes translation budget; then `continue`.
- Expected QualityIssue behavior: Invalid-output issue is available and later resolved/superseded/stale after valid retry.
- Expected artifact or active pointer behavior: No active translation pointer is set from invalid JSON; valid retry sets active TranslationResult pointers.
- Export impact: Normal export can proceed after later stages succeed.
- Result: PASS.

### F03: Page-level translation returns partial output

- Initial state: Multiple TextBlocks with active OCR; Page-level translation `pending`.
- Trigger: Provider returns valid translations for some blocks and missing/invalid entries for others.
- Expected state changes: Valid block translations become `done`; missing/invalid blocks become `failed`, `needs_review`, `skipped`, or `blocked` according to profile decision.
- Expected WorkflowAttempt behavior: Page-level attempt remains persisted and explainable as partial/invalid rather than disappearing.
- Expected WorkflowDecision behavior: One of `retry_same_stage`, `mark_warning`, `pause_for_user`, or `block`; `skip_target` may apply when allowed.
- Expected QualityIssue behavior: Missing/invalid block issues are created with translation or root-stage attribution.
- Expected artifact or active pointer behavior: Active pointers are set only for valid accepted block translations; invalid/missing blocks have no false active current result.
- Export impact: Pure normal export only if all required blocks are fresh and no warnings/skips remain; otherwise warning-ready or blocked by profile.
- Result: PASS.

### F04: Provider refusal

- Initial state: A provider-backed stage is required; relevant fallback/refusal policy is in the snapshot.
- Trigger: Provider returns a policy refusal.
- Expected state changes: Stage does not silently become `done`; target/Page moves to fallback, warning, skipped, paused, or blocked path according to policy.
- Expected WorkflowAttempt behavior: Attempt status is `refused`, not generic crash.
- Expected WorkflowDecision behavior: `fallback_provider`, `skip_target`, `mark_warning`, `pause_for_user`, or `block`; no same-provider evasion retry.
- Expected QualityIssue behavior: Provider refusal or stage-specific refusal issue is created.
- Expected artifact or active pointer behavior: Sanitized ToolRunLog/refusal metadata is recorded; no active result is created from refusal content.
- Export impact: Export allowed only if a valid fallback/manual/skipped-warning path creates fresh usable output and profile permits; otherwise blocked.
- Result: PASS.

### F05: Cleaning skips complex background

- Initial state: OCR/translation/check are fresh; cleaning target is complex but skippable by profile.
- Trigger: Cleaning check/provider reports complex background.
- Expected state changes: Cleaning target/stage is `skipped` or warning-bearing; Page cannot become pure ready solely through this skip.
- Expected WorkflowAttempt behavior: Cleaning attempt is `skipped` or records the detected issue and accepted skip path.
- Expected WorkflowDecision behavior: `skip_target` or `mark_warning`; `block` if profile makes it blocking.
- Expected QualityIssue behavior: Visible cleaning warning issue is required unless profile escalates to blocking.
- Expected artifact or active pointer behavior: Original image remains preserved; cleaned pointer may use original-plus-skip strategy only as explicit warning-bearing evidence.
- Export impact: Page may become `ready_for_export_with_warnings` only if usable output exists and warnings are allowed.
- Result: PASS.

### F06: Typesetting overflow

- Initial state: Active translations and base/cleaned image are fresh; typesetting `pending`.
- Trigger: Typesetter cannot fit text inside constraints.
- Expected state changes: Typesetting target becomes warning, needs review, or blocked depending on profile and issue severity.
- Expected WorkflowAttempt behavior: Typesetting attempt persists; preview artifact may be retained.
- Expected WorkflowDecision behavior: `retry_upstream_stage`, `mark_warning`, `pause_for_user`, or `block`.
- Expected QualityIssue behavior: Typesetting overflow issue is created with root-stage attribution when appropriate.
- Expected artifact or active pointer behavior: Preview may be retained but should not become export-effective unless accepted as warning/fresh output.
- Export impact: Normal export blocked if overflow is blocking; warning export depends on profile.
- Result: PASS.

### S01: OCR edit after translation exists

- Initial state: Active OCR, translation, and typeset output exist; Page may already be ready.
- Trigger: User edits OCR text for one TextBlock.
- Expected state changes: New OCRResult active; OCR `done` if valid; translation, translation_check, and typesetting become `stale`; review `needs_review`; Page `translation_context_stale = true` and `has_stale_blocks = true`.
- Expected WorkflowAttempt behavior: Existing attempts remain audit evidence; no provider rerun is implied until resume/rework.
- Expected WorkflowDecision behavior: On resume, workflow starts from translation or translation_check according to scope/profile; old downstream output is not accepted as current.
- Expected QualityIssue behavior: Downstream issues tied to old translation/typeset inputs become `stale` or `superseded`; still-applicable geometry/cleaning/new OCR issues remain open.
- Expected artifact or active pointer behavior: Active OCR pointer moves to the edited result; old translation/typeset pointers may remain for review/history but are not export-effective.
- Export impact: Ready status is withdrawn until downstream freshness is restored.
- Result: PASS.

### S02: Translation edit after typesetting exists

- Initial state: Active translation and active typeset artifact exist.
- Trigger: User edits translation text for one TextBlock.
- Expected state changes: New TranslationResult active; translation `done` if valid; translation_check and typesetting become `stale`; review `needs_review`; Page has stale blocks.
- Expected WorkflowAttempt behavior: Existing attempts remain; rerender/check attempts are created only when rework resumes.
- Expected WorkflowDecision behavior: Resume from translation_check or typesetting; no OCR or cleaning rerun unless another dependency requires it.
- Expected QualityIssue behavior: Old translation/typesetting/export issues tied to old text/hash become `stale` or `superseded`; still-applicable OCR/cleaning issues remain.
- Expected artifact or active pointer behavior: Active translation pointer updates; old typeset pointer remains preview/history only and is not export-effective.
- Export impact: Export readiness is withdrawn until check/typesetting freshness is restored.
- Result: PASS.

### R01: Crash after OCR before translation

- Initial state: Task was running; OCR result and active OCR pointer committed; translation not started or not accepted.
- Trigger: Process restarts and recovery scans stale heartbeat.
- Expected state changes: Task `interrupted -> recovering -> running/queued`; Page aggregate repaired; translation resumes next.
- Expected WorkflowAttempt behavior: OCR attempt is accepted/reused; no duplicate OCR attempt is needed.
- Expected WorkflowDecision behavior: `reuse_cached_result` or `continue` for OCR evidence; then continue to translation.
- Expected QualityIssue behavior: No new issue if OCR evidence is consistent.
- Expected artifact or active pointer behavior: Active OCR pointer remains valid; OCR provider is not rerun unless hashes/config changed.
- Export impact: No export readiness until downstream stages complete.
- Result: PASS.

### R02: Crash during provider call

- Initial state: Task/attempt were `running`; no accepted durable result may exist.
- Trigger: Process restarts while provider call outcome is unknown.
- Expected state changes: Task `interrupted -> recovering`; stage either retries, reuses committed evidence, pauses, or blocks.
- Expected WorkflowAttempt behavior: Running attempt becomes `abandoned_after_crash` unless durable success/refusal/failure evidence exists.
- Expected WorkflowDecision behavior: Recovery persists reuse/retry/fallback/pause/block decision; crash retries are bounded by crash retry budget.
- Expected QualityIssue behavior: Issue created only when failure/refusal/blocking evidence exists; abandoned unknown alone does not masquerade as provider refusal.
- Expected artifact or active pointer behavior: Orphan/raw output is not promoted without normal validation/ArtifactService/QualityCheck/WorkflowLoop acceptance.
- Export impact: No readiness from unknown in-flight output.
- Result: PASS.

### R03: Missing artifact during recovery

- Initial state: Metadata references an artifact that may be required for current output.
- Trigger: Recovery or ArtifactService missing-check detects absent bytes/hash mismatch.
- Expected state changes: Artifact storage state becomes missing; Page/task repaired to rebuild, warning, paused, or blocked state.
- Expected WorkflowAttempt behavior: New rebuild/retry attempts may be created only if inputs and budgets allow.
- Expected WorkflowDecision behavior: WorkflowLoopEngine decides rebuild, retry, warning, pause, or block.
- Expected QualityIssue behavior: Missing required active artifact creates or preserves visible issue; missing debug-only payload may be reduced diagnostic evidence.
- Expected artifact or active pointer behavior: Original image missing blocks because it cannot be rebuilt; cleaned/typeset may rebuild if dependencies are fresh; original is never overwritten.
- Export impact: Export readiness blocked when active typeset artifact is missing or hash-invalid.
- Result: PASS.

### E01: Normal export with unresolved blocking issue

- Initial state: Page has an unresolved open blocking QualityIssue in export scope.
- Trigger: Export check or normal export attempt.
- Expected state changes: Page/task remains or becomes `blocked`; no pure ready state.
- Expected WorkflowAttempt behavior: Export-check attempt/decision evidence is persisted by workflow; exact ExportRecord schema is export-design scope.
- Expected WorkflowDecision behavior: `block`.
- Expected QualityIssue behavior: Blocking issue remains visible and open.
- Expected artifact or active pointer behavior: No normal export artifact is produced; active typeset artifact, if present, is not sufficient to bypass blocker.
- Export impact: Normal export rejected.
- Result: PASS for workflow-state gate; UNCLEAR for exact ExportRecord fields because export metadata is explicitly deferred.

### E02: Warning export allowed by profile

- Initial state: Fresh active output exists; no open blockers; unresolved warnings/skips remain; snapshot permits warning export.
- Trigger: Export check.
- Expected state changes: Page becomes `ready_for_export_with_warnings`; task may become `succeeded_with_warnings`.
- Expected WorkflowAttempt behavior: Export-check attempt persists accepted warning-readiness evidence.
- Expected WorkflowDecision behavior: `finish_ready_for_export_with_warnings`.
- Expected QualityIssue behavior: Warning issues remain open/accepted-warning and auditable.
- Expected artifact or active pointer behavior: Active typeset artifact must be official, present, hash-valid, and fresh.
- Export impact: Warning export allowed by profile; exact export manifest/acknowledgement is export-design scope.
- Result: PASS for workflow-state gate; UNCLEAR for per-export acknowledgement/manifest details.

### E03: Warning export not allowed by profile

- Initial state: Fresh active output exists; no open blockers; unresolved warnings/skips remain; snapshot disallows warning export.
- Trigger: Export check.
- Expected state changes: Page does not become warning-ready; Page/task becomes blocked or export is rejected.
- Expected WorkflowAttempt behavior: Export-check evidence persists.
- Expected WorkflowDecision behavior: `block` with profile-based rationale.
- Expected QualityIssue behavior: Warnings remain visible with user-fix guidance.
- Expected artifact or active pointer behavior: Active output remains for preview/history but is not export-effective for warning export.
- Export impact: Export rejected until warnings are resolved or profile/user policy changes.
- Result: PASS.

### T01: Pause then resume

- Initial state: ProcessingTask `running` at some stage.
- Trigger: User requests pause, then resume.
- Expected state changes: Task `pausing -> paused`; resume moves to `queued` or `running`; completed results remain.
- Expected WorkflowAttempt behavior: Running stage reaches safe boundary, or attempt is `interrupted`/later reconciled if call cannot stop safely.
- Expected WorkflowDecision behavior: Pause honored before lower-priority decisions; resume recomputes from durable evidence.
- Expected QualityIssue behavior: No issue required solely for pause.
- Expected artifact or active pointer behavior: Completed durable outputs remain valid and reusable by hash.
- Export impact: No export readiness change unless work had already completed before pause.
- Result: PASS.

### T02: Cancel then new task

- Initial state: ProcessingTask `running` with some completed durable outputs.
- Trigger: User cancels, then starts a new task.
- Expected state changes: First task `cancelling -> cancelled` and does not auto-resume; new task starts from durable evidence.
- Expected WorkflowAttempt behavior: In-flight attempt becomes `cancelled` or safely interrupted/reconciled; new task may create `reused_cached` attempts.
- Expected WorkflowDecision behavior: `cancel` for first task; new task may use `reuse_cached_result`.
- Expected QualityIssue behavior: No issue required solely for cancel; prior stage issues remain if still applicable.
- Expected artifact or active pointer behavior: Completed valid results/artifacts remain and may be reused when hashes match.
- Export impact: Cancelled task produces no new readiness by itself; new task can reach readiness later.
- Result: PASS.

### I01: Re-run completed Page without input changes

- Initial state: Page is `ready_for_export` or warning-ready; active OCR/translation/artifacts are fresh and present.
- Trigger: User reruns the same Page with unchanged inputs/config/context.
- Expected state changes: Stages remain or become `done` through reuse; Page remains ready.
- Expected WorkflowAttempt behavior: At least cost/provider stages record `reused_cached` attempts or equivalent durable reuse evidence.
- Expected WorkflowDecision behavior: `reuse_cached_result` rather than provider/tool calls.
- Expected QualityIssue behavior: Existing resolved/accepted warning state remains consistent; no duplicate issues.
- Expected artifact or active pointer behavior: No duplicate active results; historical matching result may become active only through explicit reuse decision and atomic pointer update.
- Export impact: Export remains allowed if no blockers/warnings disallowed.
- Result: PASS.

### I02: Re-run after OCR edit

- Initial state: OCR was edited; old translation/typeset outputs may still be selected for review/history but are stale.
- Trigger: User reruns the Page.
- Expected state changes: OCR is not overwritten; translation/check/typesetting regenerate or remain stale/blocked until regenerated.
- Expected WorkflowAttempt behavior: No OCR provider attempt unless explicitly requested or input hash requires it; downstream attempts are new or reused only if hashes match edited OCR.
- Expected WorkflowDecision behavior: Reuse OCR; translate/check/typeset according to fresh dependency evidence.
- Expected QualityIssue behavior: Old downstream issues become stale/superseded; current blockers/warnings remain visible.
- Expected artifact or active pointer behavior: Active OCR pointer stays on edited result; old translation/typeset outputs are not export-effective when source hashes mismatch.
- Export impact: Export blocked until downstream outputs are fresh and issue policy permits.
- Result: PASS.

## Missing state vocabulary

- No blocking missing vocabulary for MVP workflow-state.
- Non-blocking deferred vocabulary: exact reason codes, issue type taxonomy, severity mapping, provider DTO/error classes, ExportRecord/precheck status, and implementation enum enforcement.
- HLD/SRS older vocabulary includes `completed` and `locked`; ADR 0001 resolves final workflow-state vocabulary to `done` and lock metadata rather than `locked` status.

## Ambiguous transitions

- Export attempt metadata is intentionally outside workflow-state design. The workflow gate transition is clear, but exact export attempt state/record transitions remain for export design.
- User resume from `pause_for_user` is clear when evidence changed, but exact UI/API proof of changed evidence is deferred.
- Historical non-active result reuse is safe in principle, but exact repository transaction shape and uniqueness/index constraints are deferred.
- Provider-call pause/cancel behavior is defined at safe-boundary level; exact process interruption mechanics are implementation-specific.

## Duplicated source-of-truth risks

- Page status is a repairable aggregate, not recovery truth. PASS.
- Active pointers, not active flags on result rows, are the current-result source of truth. PASS.
- Lock metadata is separate from stage status, avoiding duplicate `locked` truth. PASS.
- Risk remains that implementation could duplicate readiness in ExportRecord and Page aggregate; export design must treat workflow readiness as precondition and export records as audit/output records.

## Recovery gaps

- No hard recovery gap for FakeProvider vertical slice.
- Non-blocking gaps: exact heartbeat stale threshold, default auto-resume policy, exact transaction helpers, concurrent edit detection, and raw/orphan cleanup details.
- Recovery correctly prefers committed results, official artifacts, active pointers, and hashes; it rejects Page.status-only recovery.

## Idempotency gaps

- No hard idempotency gap for FakeProvider vertical slice.
- Non-blocking gaps: exact cache/reuse key constraints per table, exact repository API, and whether both `reused_cached` attempt and `reuse_cached_result` decision are always required.
- Design prevents duplicate active results and stale downstream export-effectiveness after OCR edits.

## Stale propagation gaps

- No hard stale propagation gap for S01/S02.
- Non-blocking gaps: exact UI/API flow for completing review, lock/unlock semantics after upstream OCR changes, and issue taxonomy details for stale versus superseded.
- Cleaning intentionally does not become stale after text-only OCR/translation edits; this matches the design rationale.

## Artifact lifecycle gaps

- No hard artifact lifecycle gap for FakeProvider vertical slice.
- Non-blocking gaps: exact directory layout, temp/orphan cleanup, retention TTLs, hash algorithm, artifact storage states, and rebuildability matrix.
- The ownership invariant is strong: Provider Adapters cannot register official artifacts, and original images are never overwritten.

## Export blocking gaps

- Normal export blocking is clear and passes the hard invariant.
- Warning readiness follows `ProcessingProfileSnapshot.allow_warning_export`.
- Exact ExportRecord fields, per-export warning acknowledgement, manifest schema, and batch/ZIP export behavior are deferred to export design. This is acceptable for workflow-state, but a backend vertical slice should include a minimal export-attempt audit record if it exposes an export endpoint.

## Provider boundary gaps

- No Provider Adapter boundary violation found.
- Non-blocking gaps: exact DTO/error schema, capability metadata, and sanitized ToolRunLog payload shape.
- Refusal handling is conservative and explicitly excludes bypass/evasion logic.

## Acceptability for FakeProvider single-Page backend vertical slice

Acceptable with constraints:

- Implement only the canonical stages and statuses from the final workflow-state documents.
- Use FakeProvider DTOs that obey the adapter boundary.
- Persist WorkflowAttempt, WorkflowDecision, QualityIssue, active pointers, and artifact metadata through Repository / DAO and ArtifactService boundaries.
- Treat export as workflow `export_check` readiness unless a minimal export design is also implemented.
- Do not implement P1/P2 scope such as forced export, GeometryRevision, multi-page context translation, generic workflow engine, distributed workers, production DDL, full ORM mapping, prompt templates, real provider integrations, or frontend flows.

Blocking status: no `FAIL`; no `UNCLEAR` item blocks FakeProvider readiness if the vertical slice keeps export metadata minimal and respects the ownership boundaries above.
