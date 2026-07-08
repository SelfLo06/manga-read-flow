## 1. Scope

This proposal defines the minimal Unit of Work and transaction boundary design for persistence readiness before the FakeProvider single-Page backend vertical slice.

It covers:

- short transaction boundaries around one workflow stage execution;
- the acceptance transaction that makes provider output effective;
- crash-safe ordering between attempt records, provider calls, artifact registration, result rows, active pointers, statuses, issues, and decisions;
- recovery behavior when a crash lands between those boundaries.

It does not define SQL DDL, ORM models, migrations, API routes, frontend behavior, provider schemas, prompt templates, or a generic persistence framework.

## 2. Role Bias

This proposal is biased toward recoverability and auditability over transactional cleverness.

The core rule is:

```text
No SQLite write transaction may span an external provider call or long file-producing operation.
```

Provider output becomes durable in stages:

1. workflow intent is persisted before the call;
2. provider/tool evidence is persisted after the call;
3. official artifacts are registered by ArtifactService as unselected evidence;
4. WorkflowLoopEngine acceptance atomically updates result rows, active pointers, issue lifecycle, decisions, retry budgets, and statuses.

The design treats active pointers as the only P0 source of current effective OCR, translation, cleaned image, and typeset image selection. Timestamps and artifact recency are never acceptance rules.

## 3. Assumptions

- `app.db` stores global registry/config templates; `project.db` stores Project-owned workflow state, attempts, results, issues, decisions, artifacts, and task state.
- A stage execution operates inside one Project and one `project.db`; no cross-database atomic transaction is required for stage execution.
- Repository / DAO is the only SQLite access boundary.
- Provider Adapter never accesses SQLite, never registers official artifacts, and never decides retry, fallback, skip, warning, pause, or block.
- ArtifactService owns official artifact path, promotion, hash, registration, storage state, retention, cleanup, and missing-file checks.
- QualityCheckService returns issue classifications or drafts; WorkflowLoopEngine owns workflow decisions and state advancement.
- StageExecutor may read state, call providers, and produce evidence, but does not accept results or mutate active pointers outside WorkflowLoopEngine acceptance.
- SQLite and the filesystem are not a single atomic resource. Recovery must tolerate files without metadata and metadata whose file later becomes missing.
- Single-process TaskRunner is acceptable for MVP, but crash recovery must not depend on in-memory state.

## 4. Minimal Proposal

Use a small repository-managed Unit of Work concept for each short `project.db` transaction. The Unit of Work is an implementation boundary, not a new framework: callers ask repositories to perform named workflow persistence operations and do not see SQL, ORM sessions, savepoints, or connection details.

Recommended stage sequence:

| Step | Transaction boundary | Required behavior |
| --- | --- | --- |
| 1. Load and reserve stage | Short read/write transaction | Confirm task is runnable, task is not cancelled, target is not deleted, locked translation rules are respected, retry budget is available, and no current active pointer/status conflicts exist. Create or mark `WorkflowAttempt` as `running`, set task/current stage or heartbeat fields, and set narrow stage status to `running` where applicable. Commit before provider call. |
| 2. Provider call | No write transaction | StageExecutor calls Provider Adapter using committed context, artifact refs, hashes, and an attempt temp root. Provider may produce temp files only. |
| 3. Persist tool outcome | Short transaction | Persist sanitized `ToolRunLog` outcome and update attempt evidence fields that are known before artifact registration. Provider refusal is recorded as refusal evidence, not as a crash. |
| 4. Register artifacts | One or more short ArtifactService transactions | ArtifactService promotes/registers official artifacts and writes `ProcessingArtifact` metadata. Registered artifacts are official but unselected. Registration must not update active pointers or stage completion by itself. |
| 5. Quality check | No required write transaction | QualityCheckService evaluates provider output, registered artifacts, hashes, and current state, then returns issue drafts/lifecycle suggestions. |
| 6. Workflow acceptance | One short write transaction | WorkflowLoopEngine persists the decision, issue lifecycle changes, accepted result rows or active artifact pointer changes, active pointer updates, retry budget after, task progress, and target stage statuses together. This is the only boundary that makes outputs current/export-effective candidates. |

The acceptance transaction is the semantic commit point. If it rolls back, provider output and registered artifacts may remain as evidence or reuse candidates, but they are not selected by active pointers and do not make the workflow advance.

Provider failure/refusal still follows the same shape:

- pre-call attempt reservation commits;
- provider call returns standardized failure/refusal;
- tool outcome commits;
- failed evidence artifacts may be registered separately;
- acceptance commits the issue, decision, retry budget/status outcome, and any pause/block/fallback state atomically.

Cache reuse should also use acceptance:

- a reuse lookup may happen before provider call;
- if reuse is selected, no provider call occurs;
- the acceptance transaction records `reuse_cached_result`, reconciles active pointers/statuses, links decision/issues as needed, and advances the workflow.

## 5. Repository / Transaction / Migration Implications

Repository implications:

- Provide a Project-scoped Unit of Work boundary for short `project.db` write transactions.
- Keep app-level registry/profile-template operations outside stage acceptance. Stage execution uses the immutable `ProcessingProfileSnapshot` already copied into `project.db`.
- Expose named persistence operations for attempt reservation, tool outcome persistence, artifact metadata registration, acceptance, user edit acceptance, recovery reconciliation, and export-readiness reconciliation.
- Hide SQL/ORM sessions from WorkflowLoopEngine, StageExecutor, ArtifactService, QualityCheckService, API handlers, and Provider Adapters.

Writes that must commit atomically:

- accepted `OCRResult` plus `TextBlock.active_ocr_result_id`, OCR stage status, downstream stale propagation, relevant issue lifecycle, `WorkflowDecision`, retry budget after, and task progress;
- accepted `TranslationResult` rows plus `TextBlock.active_translation_result_id`, translation/check statuses, downstream stale propagation, relevant issue lifecycle, `WorkflowDecision`, retry budget after, and task progress;
- accepted cleaned/typeset artifact pointer changes plus stage status, artifact dependency hash references, issue lifecycle, `WorkflowDecision`, retry budget after, and task progress;
- provider refusal outcome decision plus `WorkflowAttempt` status, relevant `QualityIssue`, `WorkflowDecision`, retry budget after, and task/stage status;
- user OCR or translation edit result row plus active pointer update, downstream stale statuses, page stale flags, and stale/superseded downstream issues;
- final readiness decision plus Page/Task status and unresolved warning/blocking issue interpretation used for that decision.

Writes that can be separate short transactions:

- task creation and profile snapshot creation;
- attempt start/reservation;
- heartbeat/progress updates that do not accept output;
- sanitized ToolRunLog start/outcome records;
- official artifact metadata registration;
- failed/debug evidence artifact registration;
- cleanup or missing-file storage-state updates;
- recovery marking stale running task/attempt as `interrupted`, `recovering`, or `abandoned_after_crash`;
- read-only reuse lookups and export gate queries.

Migration implications are limited to supporting this behavior with the already planned tables, constraints, and indexes. This proposal does not add P0 entities. It does require later implementation to support owner checks for active pointers, recovery indexes for running tasks/attempts, blocker queries for `QualityIssue`, and reuse lookups by input/config/context/provider hashes.

## 6. Software Engineering Principle Checks

- Single Responsibility: repositories persist state; ArtifactService manages files and artifact metadata; QualityCheckService classifies issues; WorkflowLoopEngine decides acceptance; Provider Adapter calls tools only.
- Information Hiding: transaction mechanics, SQL, ORM sessions, and locking details stay inside Repository / DAO.
- High Cohesion / Low Coupling: Unit of Work operations are grouped by workflow persistence need, not by table convenience.
- Dependency Inversion: WorkflowLoopEngine depends on repository contracts for acceptance and recovery, not concrete SQLite details.
- Testability: short transaction boundaries can be verified with temporary SQLite by killing/restarting between boundaries and checking durable evidence.
- Recoverability: every boundary leaves either no durable effect or enough persisted evidence to reconcile without Page.status alone.
- Traceability: attempts, tool logs, artifacts, issues, decisions, active pointer changes, result versions, and status changes remain explainable.
- Scope Control: no event sourcing, distributed transaction manager, CQRS layer, plugin persistence layer, or generic enterprise Unit of Work framework is introduced.

## 7. Recovery / Idempotency Impact

Recoverable failure modes:

| Failure point | Required recovery behavior |
| --- | --- |
| Crash before attempt reservation commits | Task remains queued/runnable or previous state remains authoritative. Stage may be started normally. |
| Crash after attempt reservation but before provider call | Stale running attempt is marked `interrupted` or `abandoned_after_crash`; retry is bounded by crash policy. |
| Crash during provider call | No write transaction is open. Running attempt/tool log is reconciled from heartbeat and durable evidence. Provider output is not assumed. |
| Crash after provider temp file but before artifact registration | Temp/orphan file is not official. ArtifactService may clean or register only through explicit recovery policy. WorkflowLoopEngine decides retry/pause/block. |
| Crash after ToolRunLog outcome but before artifact registration | Tool evidence remains, but no official output is selected. Recovery retries, falls back, or records issue according to decision policy. |
| Crash after artifact registration but before acceptance | Artifact is official but unselected. It is not export-effective by timestamp. Recovery may reuse it only if provenance, hashes, and normal validation/acceptance rules pass. |
| Crash during acceptance | SQLite commits all acceptance writes or none. Half-selected active pointer/status/issue/decision drift is prevented. |
| Crash after acceptance | Active pointers, result rows, issues, decisions, retry budget, and statuses already agree. Recovery may repair aggregate Page/Task summaries from durable facts. |
| Artifact missing after acceptance | ArtifactService marks storage state `missing`; WorkflowLoopEngine decides rebuild, warning, pause, or block. |

Idempotency impact:

- Reuse is a workflow decision, not an implicit repository side effect.
- OCR reuse requires matching TextBlock/input or geometry hash, provider/model/tool version, config hash, and source language.
- Translation reuse requires matching source OCR/result hash, page context, glossary version/terms hash, provider/model, prompt template version, generation config, and target language.
- Cleaned/typeset reuse requires matching artifact provenance, source hashes, mask/geometry/layout/font/config hashes, and artifact presence/hash validation.
- Reuse acceptance must not create duplicate active result rows or override locked translations.
- Failed attempts and refusals are auditable and may affect retry/fallback decisions, but they are not successful cache hits.

## 8. FakeProvider Slice Impact

The FakeProvider single-Page slice should exercise the same transaction sequence as real providers:

- create Project/Batch/Page and original artifact through normal repository/artifact boundaries;
- reserve each stage attempt before the fake call;
- call FakeProvider without a write transaction;
- register fake output artifacts as official but unselected;
- run fake quality checks;
- accept results through the same atomic acceptance transaction;
- support injected crash points between reservation, fake call return, artifact registration, and acceptance.

Minimal validation enabled by this proposal:

- happy path reaches `ready_for_export` with consistent active OCR, translation, cleaned, and typeset pointers;
- provider refusal creates ToolRunLog, WorkflowAttempt, QualityIssue, WorkflowDecision, and a bounded outcome;
- invalid or partial fake translation can persist valid evidence without accepting incomplete output as current;
- rerun of unchanged fake OCR/translation records reuse decisions and avoids duplicate provider calls;
- crash after OCR acceptance resumes at translation;
- crash after typeset artifact registration but before acceptance leaves an unselected artifact and no false readiness.

## 9. HARNESS Scenario Coverage

| Scenario | Coverage |
| --- | --- |
| P03 happy-path single Page workflow | Acceptance transaction selects OCR/translation/cleaned/typeset outputs and advances stage statuses with decisions/issues. |
| P04 acceptance transaction | Explicit atomic boundary covers accepted results, active pointers, issue lifecycle, WorkflowDecision, retry budget after, task progress, and statuses. Provider call is outside the write transaction. |
| R01 crash after OCR result committed | Accepted OCR pointer/result/status are durable together, so recovery resumes at translation without rerunning OCR. |
| R02 crash after provider temp file before artifact registration | Temp/orphan files are not official artifacts and cannot become active by filesystem presence. |
| R03 crash after artifact registration before active pointer update | Registered artifact is official but unselected; recovery cannot infer export-effectiveness from latest artifact. |
| R04 missing active artifact | ArtifactService marks `missing`; WorkflowLoopEngine decides rebuild/warning/pause/block through a later acceptance transaction. |
| I01 unchanged OCR rerun | Reuse lookup plus `reuse_cached_result` acceptance prevents duplicate provider call and keeps audit trail. |
| I02 unchanged translation rerun | Reuse key includes OCR/context/glossary/provider/model/prompt/config; locked translations are not overwritten automatically. |
| I03 unchanged cleaned/typeset artifacts | Artifact hash/provenance validation is required before reuse; missing/incompatible artifacts cannot become effective. |
| Q01 provider refusal persistence | Refusal is persisted through ToolRunLog/WorkflowAttempt evidence and accepted into issue/decision/status atomically. |
| Q02 blocking issue prevents readiness/export | Final readiness transaction relies on unresolved open blocking QualityIssue query, not Page.status alone. |
| Q03 cleaning skip warning state | Skip decision, warning issue, and warning-ready status are committed together so pure readiness is not falsely assigned. |
| S01 OCR edit | New OCR result, active pointer, downstream stale statuses, page stale flags, and issue staleness commit atomically. |
| S02 translation edit | New translation result, active pointer, typesetting stale status, and old typeset non-effectiveness commit atomically. |
| Boundary failure checks | Provider, ArtifactService, QualityCheckService, WorkflowLoopEngine, and Repository ownership boundaries are preserved. |

## 10. Rejected Alternatives

- One long transaction around provider call: rejected because it holds SQLite write locks during slow/fallible work and makes pause/cancel/recovery brittle.
- Provider Adapter writes result rows or artifacts directly: rejected because it violates database and artifact lifecycle boundaries.
- Artifact registration automatically updates active pointers: rejected because it bypasses quality checks and WorkflowLoopEngine decisions.
- Accept output by latest timestamp or newest artifact: rejected because active pointers are the P0 source of truth and locked/manual selections may point to older versions.
- Persist provider output as current before quality acceptance: rejected because invalid, partial, refused, or overflow outputs could become export-effective.
- Cross-database transaction between `app.db` and `project.db`: rejected for MVP stage execution because all Project-owned stage evidence lives in one `project.db`.
- Distributed transactions across SQLite and filesystem: rejected as unnecessary and unrealistic for local MVP; recovery handles the gap.
- Event sourcing, CQRS, plugin persistence, or a generic transaction framework: rejected as overengineering for FakeProvider MVP-0.

## 11. Risks

- Filesystem and SQLite can drift between artifact promotion and metadata registration. Mitigation: file presence alone is never official; artifact metadata plus hash validation controls official evidence.
- Acceptance transaction for Page-level translation may touch many TextBlocks. Mitigation: MVP single-Page scope keeps this bounded; later Batch processing should keep acceptance page-scoped or stage-target-scoped.
- Concurrent user edits can race with workflow acceptance. Mitigation: acceptance must use expected active pointer/status/hash checks and abort/reload on conflict.
- Too many small transactions could leave verbose audit records. Mitigation: this is intentional for recovery; retention policy can clean successful large payload bytes while keeping metadata.
- Registered but unselected artifacts may accumulate after crashes or retries. Mitigation: retention/cleanup can treat them as non-active evidence after recovery policy decides.
- If implementation forgets to include task progress or retry budget in acceptance, recovery may need repair. Mitigation: acceptance operation should include these fields by contract.

## 12. Open Questions

- What exact optimistic-concurrency guard should repositories expose: expected active pointer ids, expected stage statuses, updated timestamps, row versions, or a combination?
- Should ToolRunLog outcome and artifact metadata registration be one repository operation when ArtifactService already has file hashes, or remain separate short transactions for simpler failure isolation?
- For page-level translation with many block results, what is the maximum acceptance size before the workflow should split acceptance by page or target group?
- Should QualityIssue drafts ever be persisted before acceptance for debugging, or should MVP-0 persist them only inside the WorkflowLoopEngine acceptance transaction?
- What cleanup policy should apply to official but unselected artifacts created immediately before a crash?
- Should recovery create an explicit WorkflowDecision when it marks an attempt `abandoned_after_crash`, or is the recovery attempt/status update sufficient for MVP-0?
