## 1. Scope

This proposal covers the minimal repository support needed for crash recovery and idempotent rerun in the FakeProvider single-Page backend vertical slice.

In scope:

- Recovery queries for stale running `ProcessingTask` rows and running or incomplete `WorkflowAttempt` rows.
- Repository read bundles needed to recover without relying only on `Page.status`.
- Reuse lookup keys for OCR, translation, cleaned image, and typeset image outputs.
- Reconciliation of skipped, stale, blocked, missing, warning, interrupted, refused, and abandoned states.
- Minimal correctness indexes needed for recovery and reuse.

Out of scope:

- SQL DDL, ORM mappings, migration files, API routes, frontend behavior, real providers, prompt templates, and any redesign of the data model.
- Cross-project/global result cache. MVP-0 reuse stays inside one verified `project.db`.

## 2. Role Bias

The recovery/idempotency bias should be conservative:

- Prefer committed active pointers, result rows, artifact metadata, workflow decisions, issues, and tool logs over aggregate status summaries.
- Reuse only when the input/config/context/provenance key matches and active or candidate artifacts are present and hash-valid.
- Treat official-but-unselected artifacts as evidence or reuse candidates, never as export-effective output by timestamp.
- Treat provider refusal as a persisted workflow path, not as a crash.
- Do not add new P0 entities; use `ProcessingTask`, `WorkflowAttempt`, `WorkflowDecision`, `QualityIssue`, `ProcessingArtifact`, `ToolRunLog`, active pointers, and result version rows.

## 3. Assumptions

- `docs/HLD.md` is the HLD source present in this workspace. Older SRS/HLD examples that mention direct image paths or active result flags are refined by the final data-model documents into `ProcessingArtifact` metadata plus active owner pointers.
- Project identity has already been verified before project recovery starts: the app registry project id matches `project_metadata.project_id`.
- MVP-0 uses a local TaskRunner; stale detection still uses persisted `heartbeat_at` so restart recovery is deterministic.
- Exact heartbeat timeout, crash retry ceiling, and enum spellings remain final-design or implementation constants, but the repository must support them.
- ArtifactService can validate file existence and hash, then persist `ProcessingArtifact.storage_state` changes through repository contracts.
- WorkflowLoopEngine owns decisions after recovery evidence is loaded. Repository methods return evidence and perform requested persistence; they do not decide retry, fallback, warning, skip, or block behavior.

## 4. Minimal Proposal

1. Recovery should begin with a project-scoped stale task scan.

   The repository should expose a recovery query that finds non-terminal `ProcessingTask` rows whose status is running-like and whose `heartbeat_at` is older than the configured stale threshold, including tasks left in `recovering` past a recovery timeout. The query must return the task id, target scope, current stage, profile snapshot id, idempotency key, heartbeat, last attempt id, and last decision id.

2. Stale task claiming should be a short transaction.

   On startup or project open, recovery should mark each claimed stale task `interrupted`, then `recovering`, using an expected current status/heartbeat check so a newly active TaskRunner cannot be overwritten. This transaction should not perform provider work or artifact file scanning.

3. Running attempts should be reconciled from durable evidence.

   For each stale task, the repository should load running or incomplete attempts for the task and current target. Reconciliation should use:

   - terminal or latest `WorkflowDecision` for the task/stage/target;
   - accepted OCR/translation result rows linked to the attempt;
   - owner active pointers that select those rows or artifacts;
   - official `ProcessingArtifact` rows linked to the attempt/tool run;
   - `ToolRunLog` outcome, including refusal;
   - open/stale/superseded `QualityIssue` rows tied to the attempt/result/artifact;
   - TextBlock stage statuses and dependency hashes.

   If accepted result rows, active pointers, and stage statuses are consistent, the attempt can be closed to the matching terminal outcome and the loop can resume downstream. If refusal or failure evidence exists, the attempt should be closed as refused or failed and passed back to WorkflowLoopEngine for policy. If official artifacts exist but no acceptance decision or active pointer exists, keep them unselected and treat them as evidence/reuse candidates only. If only temp/orphan files exist, the attempt should become `abandoned_after_crash` or `interrupted`, while ArtifactService handles temp cleanup or explicit registration. If no durable completion evidence exists, mark the attempt `abandoned_after_crash`.

4. Recovery must load a page recovery bundle, not only `Page.status`.

   The minimal bundle should include:

   - `Page` active artifact pointers, translation context hash/stale flag, stale-block flag, quality flags, and deletion state;
   - all active TextBlocks for the page with reading order, geometry hash, skip flags, active mask pointer, active OCR pointer, active translation pointer, locked translation pointer, and per-stage statuses;
   - active OCR/translation result rows and their source/input/config/context/glossary/provider/model/tool hashes;
   - active original, cleaned, typeset, mask, and candidate attempt artifacts with storage state and file hash;
   - open blocking and warning QualityIssues in page/textblock scope plus stale/superseded issues tied to active dependency hashes;
   - latest task, attempt, decision, and tool log history for the current page/task scope;
   - ProcessingProfileSnapshot settings hash and policy references needed to interpret warning export, retry, refusal, and crash recovery behavior.

5. Idempotency lookup order should be explicit.

   Before calling a provider or local tool, WorkflowLoopEngine should ask repositories for reusable evidence in this order:

   - current active pointer if dependency hashes, status, and artifact validation prove it is fresh;
   - historical result or official artifact matching the stage reuse key;
   - failed/refused attempts for retry-budget and fallback accounting, not as cache hits;
   - no hit, so execute the stage.

   A reuse hit should still produce auditable workflow evidence: either `WorkflowAttempt.status = reused_cached`, `WorkflowDecision.decision_type = reuse_cached_result`, or both, depending on the final transaction design. Reuse must not create duplicate active result rows.

6. OCR reuse key.

   OCR reuse should match within the same Project/TextBlock on geometry hash, crop or input artifact hash, OCR config hash, provider, model id, tool version, and source language. A current active user-edited OCR result may satisfy the stage if the rerun is not an explicit provider rerun. A historical provider OCR result may become active only through the normal reuse decision and pointer/status reconciliation transaction.

7. Translation reuse key.

   Translation reuse should match on source OCR result id and source text hash, page context hash, glossary version id or terms hash, provider, model id, prompt template version, generation config hash, target language, and page translation group key when applicable. Locked translations must not be automatically replaced by a reused provider result unless the user explicitly overrides the lock.

8. Cleaned artifact reuse key.

   Cleaning reuse should match on base image artifact hash, mask artifact hash or mask set hash, relevant TextBlock geometry hashes, skip set, cleaning provider/mode/tool version, and cleaning config hash. The candidate cleaned artifact must be an official `ProcessingArtifact` with compatible provenance and `storage_state = present` after ArtifactService validation.

9. Typeset artifact reuse key.

   Typesetting reuse should match on active cleaned artifact id/hash, active translation result ids and translation text hashes in reading order, relevant geometry hashes, font/layout config hash, typesetter version, and target language/direction policy. The candidate typeset artifact must be official, selected only through an active pointer update, and present/hash-valid before export readiness.

10. State handling rules.

   - `skipped`: preserve skip state and warning issue; never allow pure `ready_for_export` solely because skipped blocks were ignored.
   - `stale`: keep active pointers for review, but treat output as not export-effective until dependency hashes are refreshed by rerun, reuse, or explicit recovery repair.
   - `blocked`: do not auto-resume a blocked task without changed evidence or a new explicit resume/rerun request.
   - `missing`: ArtifactService marks missing artifacts; WorkflowLoopEngine decides rebuild, warning, pause, or block.
   - `warning`: keep warning issues visible; warning readiness/export depends on the effective `ProcessingProfileSnapshot`.
   - `refused`: keep refusal attempts/logs/issues as policy evidence; do not treat them as reusable successful outputs.

## 5. Repository / Transaction / Migration Implications

Repository contracts should be grouped by workflow need rather than table shape:

- Recovery reads: find stale tasks, claim recovery, load task recovery bundle, load running attempts, load latest decisions/logs/issues/artifacts for a task/stage/target.
- Reuse reads: find matching OCR result, translation result, cleaned artifact, and typeset artifact by full reuse key; verify current active-pointer freshness.
- Artifact metadata reads/writes: load active and candidate artifact metadata, persist storage-state changes requested by ArtifactService, and find official artifacts linked to an attempt/tool run.
- Issue reads/writes: query open blockers/warnings by scope, load issues tied to result/artifact/input hashes, and mark issues stale/superseded/resolved as part of acceptance or edit transactions.
- Workflow writes: close abandoned/interrupted attempts, record cache reuse attempts/decisions, and repair task/page/textblock statuses after WorkflowLoopEngine decides.

Transaction guidance:

- Stale task claim is one short transaction per task.
- Attempt reconciliation status changes should be committed separately from provider calls and filesystem temp cleanup.
- Acceptance or reuse selection should be one transaction that updates result rows if needed, active pointers, issue lifecycle, WorkflowDecision, retry budget after, and stage statuses.
- Artifact validation may read files outside a DB transaction, then persist the resulting storage-state change in a short repository transaction.
- Recovery should never hold a write transaction while calling a provider, parsing large payloads, or scanning temp directories.

Migration implications:

- No new P0 entities are required.
- The schema needs the already-planned fields for heartbeat, attempt status, active pointers, dependency hashes, artifact storage state, issue status/blocking flags, and workflow decisions.
- Minimal migrations should include recovery/reuse indexes listed below, but exact DDL and partial-index mechanics are deferred.

Minimally important indexes for recovery/reuse:

- `ProcessingTask` by project, status, and heartbeat; active idempotency key where duplicate suppression is required.
- `WorkflowAttempt` by task/stage/status and by target/stage/status; uniqueness of task/stage/target/attempt number.
- `WorkflowDecision` by task creation order, attempt id, and target/stage.
- `ToolRunLog` by attempt id and by project/stage/status/start time.
- `TextBlock` by page and each stage status used by recovery; active OCR/translation pointer lookups; page reading order.
- `OCRResult` by TextBlock plus input hash, config hash, provider, model id, tool version, with geometry hash as a required equality filter or indexed part.
- `TranslationResult` by source text hash, context hash, glossary version, provider, model id, prompt version, and generation config hash; source OCR result lookup.
- `ProcessingArtifact` by owner/type, page/type, TextBlock/type, file hash/type, and project retention/storage state.
- `QualityIssue` by project/batch/page/textblock scope plus blocking flag and status; target issue dedupe support.
- `GlossaryVersion` by project/version and project/terms hash when no-op version reuse is allowed.

## 6. Software Engineering Principle Checks

- Single Responsibility: repositories retrieve/persist recovery evidence; WorkflowLoopEngine decides recovery outcomes; ArtifactService validates files; Provider Adapters remain uninvolved.
- Information Hiding: callers ask for recovery bundles and reuse candidates, not SQL joins, ORM sessions, or table layouts.
- High Cohesion / Low Coupling: recovery and reuse contracts are grouped around task/stage/page needs, not around arbitrary table access.
- Dependency Inversion: WorkflowLoopEngine, StageExecutor, ArtifactService, and QualityCheckService depend on repository contracts, not SQLite details.
- Testability: temporary SQLite tests can seed stale tasks, running attempts, artifacts, issues, and active pointers, then assert recovery/reuse behavior without real providers.
- Recoverability: stale task and attempt queries are explicit and require active pointers, artifacts, issues, decisions, and result hashes; `Page.status` is only a repairable summary.
- Traceability: reuse and recovery both create or repair attempts/decisions/issues rather than silently mutating pointers.
- Scope Control: no event store, CQRS layer, distributed lock manager, plugin persistence layer, or cross-project cache is introduced.

## 7. Recovery / Idempotency Impact

Recovery finds stale running tasks by querying `ProcessingTask` rows in running-like states with stale `heartbeat_at`, scoped to the opened Project. It then claims each task for recovery in a short transaction and loads attempts plus page/task evidence.

Recovery reconciles running attempts by comparing attempt status with durable outputs: accepted result rows, active pointers, official artifacts, tool logs, quality issues, and workflow decisions. Attempts with no durable completion evidence become `abandoned_after_crash`; attempts with partial official evidence become interrupted evidence for WorkflowLoopEngine rather than automatic success.

Recovery avoids `Page.status` dependence by loading the page recovery bundle described in section 4. Page aggregate status can then be repaired after the evidence is reconciled.

Idempotency finds reusable outputs by full stage keys. The reuse decision should always be auditable and should reconcile active pointers and statuses even when no provider call happens.

Failure-state impact:

- Skipped outputs stay warning-bearing and are not pure-ready.
- Stale outputs remain visible but not export-effective.
- Blocked tasks remain blocked until evidence changes or the user explicitly resumes.
- Missing active artifacts block freshness until ArtifactService marks state and WorkflowLoopEngine decides rebuild/warn/block.
- Warning states remain visible and are gated by ProcessingProfileSnapshot.

## 8. FakeProvider Slice Impact

For the FakeProvider single-Page slice, repository support can stay narrow:

- One Project, one Batch, one Page, one task, and deterministic fake stage hashes are enough to validate recovery/reuse.
- FakeProvider should produce stable provider/model/tool/config identities so OCR, translation, cleaning, and typesetting reuse keys are predictable.
- Crash-after-OCR tests should seed or produce an active OCR pointer plus OCRResult, then verify recovery resumes at translation and records no new OCR provider call.
- Rerun tests should assert `reused_cached` attempt/decision evidence and no duplicate active OCR/translation rows.
- Cleaning/typesetting reuse tests should validate official artifact metadata and hash before pointer reuse.
- Provider refusal tests should show refusal attempts/logs/issues/decisions are loaded for policy, not treated as successful cache hits.
- Missing artifact tests should let ArtifactService mark `storage_state = missing`, after which WorkflowLoopEngine decides the page outcome.

## 9. HARNESS Scenario Coverage

| Scenario | Coverage in this proposal |
| --- | --- |
| P03: Happy-path single Page workflow | Supports persistence reads for active OCR, translation, cleaned, and typeset outputs plus attempts/decisions/issues/logs. |
| P04: Acceptance transaction | Requires reuse/acceptance selection to atomically update pointers, issues, decision, retry budget after, and stage statuses. |
| R01: Crash after OCR result committed | Recovery finds stale task/running attempt, loads active OCR pointer/result, and resumes downstream without rerunning OCR. |
| R02: Crash after provider temp file before artifact registration | Temp/orphan files are not official artifacts; running attempt becomes abandoned/interrupted unless ArtifactService later registers through normal rules. |
| R03: Crash after artifact registration before active pointer update | Official artifact remains unselected evidence; no timestamp promotion; loop decides reuse/retry/pause/block. |
| R04: Missing active artifact | Artifact metadata is loaded, ArtifactService marks missing, and WorkflowLoopEngine decides rebuild/warning/block. |
| I01: Rerun unchanged OCR stage | OCR reuse key finds matching result and records auditable cache reuse without duplicate provider call. |
| I02: Rerun unchanged translation stage | Translation reuse key includes OCR/source/context/glossary/provider/model/prompt/config and respects locked translation. |
| I03: Rerun unchanged cleaned/typeset artifacts | Artifact provenance, storage state, and hash validation are required before reuse. |
| Q01: Provider refusal persistence | Refusal logs/attempts/issues/decisions are recovery evidence, not successful cache hits. |
| Q02: Blocking issue prevents readiness/export | Open blocking issue queries by scope remain part of recovery/readiness evidence. |
| Q03: Cleaning skip creates warning-bearing state | Skips persist as skipped stage plus warning issue and cannot yield pure ready state. |
| S01: OCR edit | Active OCR pointer and downstream stale statuses prevent reuse of stale translation/typeset outputs. |
| S02: Translation edit | Active translation pointer plus stale typesetting status prevents old typeset artifact from being export-effective. |
| M03: Add enum value later | Repository contracts rely on stable string states but do not require rewriting historical audit rows. |

## 10. Rejected Alternatives

- Recover from `Page.status` alone: rejected because it cannot explain active pointer drift, missing artifacts, partial attempts, or stale downstream state.
- Select latest result or artifact by timestamp: rejected because active pointers, locks, and warning decisions define current/effective output.
- Treat registered artifacts as automatically active: rejected because artifact registration is not workflow acceptance.
- Let Provider Adapters perform cache lookup or artifact registration: rejected because it violates provider boundaries and hides reuse decisions.
- Use failed attempts or provider refusals as cache hits: rejected because they are retry/fallback/block evidence, not successful outputs.
- Add a global cross-project cache for MVP-0: rejected because Project isolation and local recovery are enough for the first vertical slice.
- Introduce event sourcing/CQRS for recovery: rejected as scope creep; existing attempts, decisions, issues, artifacts, and result versions provide enough audit evidence.

## 11. Risks

- False reuse if a key omits context, geometry, glossary, or config. Mitigation: repository lookup must require full stage keys and dependency-hash checks.
- Under-reuse if keys are too strict. Mitigation: start conservative for MVP-0, then relax only with explicit design evidence.
- Artifact filesystem drift can make a DB cache hit unusable. Mitigation: ArtifactService validation is required before cleaned/typeset artifact reuse or export-effective status.
- Recovery could race with an active TaskRunner after restart-like flows. Mitigation: expected status/heartbeat claim transaction.
- Recovery repair could hide data corruption if it silently changes too much. Mitigation: persist decisions/status repair evidence and keep issues visible.
- Index sprawl could overcomplicate MVP-0. Mitigation: implement only recovery/reuse indexes tied to harness scenarios and observed queries.

## 12. Open Questions

- What exact heartbeat stale threshold and recovery timeout should MVP-0 use?
- What exact status value should close interrupted `ToolRunLog` rows after a crash, if tool logs have a narrower status vocabulary than attempts?
- Should MVP-0 implement `WorkflowDecisionIssue` immediately for recovery traceability, or is this allowed to follow immediately after the first FakeProvider slice?
- Are cleaned/typeset reuse keys page-level only for MVP-0, or should they also support single-TextBlock rerender keys in the first implementation?
- When an official unselected artifact exists after crash, should default recovery retry the stage, pause for review, or attempt normal validation replay first?
