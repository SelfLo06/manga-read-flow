# Workflow State Detailed Design v0.1

## 1. Design goals

Define an MVP single-Page Workflow State / Workflow Loop design that is implementable with FakeProvider, recoverable after crash, auditable through attempts/decisions/issues/artifacts, and small enough for the local manga translation workflow.

The design optimizes for ordinary-reader usability, bounded automation, original-image safety, and clear separation of responsibilities.

The workflow-state design does not add manga search, scraping, download, distribution, publishing, provider-policy bypass, or provider-policy evasion behavior.

## 2. Source documents

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/HLD-v0.2.md`
- `docs/PROJECT-PLAN.md`
- `docs/design/workflow-state/GOAL.md`
- `docs/design/workflow-state/HARNESS.md`
- `docs/design/workflow-state/PLAN.md`
- all `docs/design/workflow-state/proposals/*.md`
- all `docs/design/workflow-state/reviews/*.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/data-model/final/schema-outline.md`
- `docs/design/data-model/final/state-data-impact.md`
- `docs/design/data-model/final/open-questions.md`

No blocking conflict was found. The main vocabulary drift is resolved here: TextBlock completion is `done`, ProcessingTask success terminals are `succeeded` / `succeeded_with_warnings`, and workflow uses `export_check` for readiness while export records remain in export design.

## 3. MVP workflow stages

Canonical stages:

```text
import -> detection -> ocr -> translation -> translation_check -> cleaning -> typesetting -> export_check
```

`export_check` is workflow precondition/readiness logic. Actual single-page/batch/ZIP export records, output artifacts, and manifests remain export-design responsibilities.

## 4. State vocabularies

See `state-vocabulary.md` for canonical values.

Summary:

- ProcessingTask: `queued`, `running`, `pausing`, `paused`, `cancelling`, `cancelled`, `interrupted`, `recovering`, `succeeded`, `succeeded_with_warnings`, `blocked`, `failed`.
- WorkflowAttempt: `planned`, `running`, `succeeded`, `failed`, `refused`, `cancelled`, `skipped`, `reused_cached`, `interrupted`, `abandoned_after_crash`.
- Page: persisted repairable aggregate: `uploaded`, `queued`, `processing`, `paused`, `cancelled`, `interrupted`, `recovering`, `needs_review`, `partially_failed`, `blocked`, `ready_for_export`, `ready_for_export_with_warnings`, `exported`, `deleted`.
- TextBlock stage: `pending`, `running`, `done`, `failed`, `skipped`, `needs_review`, `stale`, `blocked`.

Page status is never recovery truth. Recovery uses tasks, attempts, decisions, active pointers, result dependency hashes, artifacts, ToolRunLogs, QualityIssues, and TextBlock stage statuses.

## 5. Legal and illegal transitions

See `stage-transition-table.md`.

Important illegal transitions:

- cancelled task auto-resumes;
- blocked task resumes without changed evidence or explicit resume;
- terminal attempts are reopened;
- downstream stage becomes `done` while required upstream state is stale/failed/blocked;
- OCR/translation `done` without active pointer, except explicit skipped/non-text target;
- stale output becomes export-effective without validation/rerun/reuse;
- automatic workflow replaces a locked translation;
- pure `ready_for_export` with skipped TextBlocks;
- normal export/readiness with open blocking issues.

## 6. WorkflowDecision and loop policy

See `decision-matrix.md`.

Decision types:

```text
continue
reuse_cached_result
retry_same_stage
fallback_provider
retry_upstream_stage
skip_target
mark_warning
pause_for_user
block
finish_ready_for_export
finish_ready_for_export_with_warnings
cancel
```

Retry budget is consumed by persisted retry decisions. Attempts mirror before/after budget for audit. `abandoned_after_crash` does not consume normal retry budget by itself; automatic recovery retry is bounded by a crash retry ceiling in the snapshot or task policy.

Provider refusal defaults to fallback, pause/manual, allowed skip, valid warning path, or block. The design provides no policy bypass or evasion logic.

## 7. Export readiness

Normal readiness requires:

- active typeset artifact exists, is official, present, and hash-valid;
- required upstream OCR/translation/cleaning/typesetting state is fresh;
- no open blocking QualityIssue exists in export scope;
- no skipped/warning state remains for pure readiness.

Warning readiness requires all normal freshness/artifact conditions plus:

- no open blockers;
- unresolved warnings/skips remain visible;
- `ProcessingProfileSnapshot.allow_warning_export = true`.

All-skipped Page cannot become pure `ready_for_export`. It can become `ready_for_export_with_warnings` only if a usable output exists and the snapshot allows warning export; otherwise it pauses or blocks.

## 8. Minimal ProcessingProfileSnapshot policy fields

The loop consumes only minimal immutable policy:

- snapshot identity and settings hash;
- per-stage retry budgets;
- crash recovery retry ceiling;
- fallback policy and sanitized provider/config refs;
- provider refusal policy;
- warning export policy;
- auto-skip allowlist;
- pause/block policy;
- quality strictness reference;
- artifact/debug retention hints.

Snapshots must not contain secrets.

## 9. Boundaries

Provider Adapter:

- calls tools and returns structured outputs/errors/provider metadata;
- may use temporary files;
- must not access SQLite, register official artifacts, create QualityIssues, decide retry/fallback/skip/warning/pause/cancel/block, decide cache reuse, or perform policy evasion.

ArtifactService:

- is the only official artifact lifecycle entry;
- owns path generation, atomic write/promotion, hash, metadata registration, storage state, retention, cleanup, trash, and missing checks;
- does not decide workflow reuse/retry/rebuild/warn/block.

QualityCheckService:

- checks outputs/errors/artifacts/result metadata;
- creates/classifies QualityIssues, severity/blocking, discovered stage, root stage, suggested action;
- does not advance workflow state or decide workflow outcomes.

Repository / DAO:

- is the only SQLite access entry;
- persists tasks, attempts, decisions, issues, artifacts, result versions, active pointers, and stage statuses;
- exact methods/DDL/ORM are deferred.

StageExecutor:

- executes one stage from a durable context;
- builds inputs from repository reads and ArtifactService lookups;
- calls Provider Adapters or local tools;
- returns stage output/standardized failure to the loop;
- does not make final workflow decisions, mutate active pointers outside accepted loop decisions, hold write transactions across provider calls, or bypass ArtifactService.

## 10. Crash recovery and idempotent rerun

See `recovery-rules.md`.

Recovery:

- marks stale running tasks `interrupted` then `recovering`;
- reconciles running attempts from durable evidence;
- prefers committed results/artifacts and active pointers;
- marks unknown in-flight attempts `abandoned_after_crash`;
- retries only within finite budget/policy;
- does not parse raw provider output into accepted results in MVP unless normal validation/acceptance is replayed;
- repairs Page aggregate status after evidence reconciliation.

Idempotent rerun reuses current or historical matching results through `reuse_cached_result` and avoids duplicate active results.

## 11. Stale propagation

See `stale-propagation-rules.md`.

OCR edit:

- creates new OCRResult and active OCR pointer;
- marks translation, translation_check, and typesetting stale;
- marks Page translation context stale;
- keeps old translation/typeset pointers for review but not export-effectiveness.

Translation edit:

- creates new TranslationResult and active translation pointer;
- marks translation_check and typesetting stale;
- does not mark Page translation context stale solely from target text change;
- keeps old typeset pointer for preview/history but not export-effectiveness.

Cleaning is not stale by default after OCR/translation text edits.

## 12. Scenario replay

| Scenario | Result | Replay summary |
| --- | --- | --- |
| H01 happy path | PASS | Stages continue to `export_check`; active OCR/translation/cleaned/typeset pointers set; final `finish_ready_for_export`. |
| F01 OCR fails once then succeeds | PASS | Failed attempt persists; `retry_same_stage` consumes OCR budget; retry sets active OCR and continues. |
| F02 invalid translation JSON then retry succeeds | PASS | Invalid attempt/issue recorded; retry consumes translation budget; valid retry creates TranslationResults. |
| F03 partial Page translation | PASS | Valid block translations persist; missing/invalid blocks get issues; profile chooses retry/warning/pause/block. |
| F04 provider refusal | PASS | Attempt `refused`; ToolRunLog/QualityIssue/Decision persisted; fallback/manual/skip/warn/block only, no bypass. |
| F05 cleaning skips complex background | PASS | Cleaning `skipped`; warning issue; Page may become warning-ready, never pure ready. |
| F06 typesetting overflow | PASS | Preview may be retained; decision retry-upstream/warning/pause/block; export readiness follows issue/profile. |
| S01 OCR edit after translation | PASS | New OCR active; downstream stale; old translation/typeset not export-effective. |
| S02 translation edit after typesetting | PASS | New translation active; check/typesetting stale; rerender needed before readiness. |
| R01 crash after OCR before translation | PASS | OCR result reused; task recovers and resumes at translation; OCR not rerun. |
| R02 crash during provider call | PASS | Running attempt abandoned unless durable evidence exists; retry bounded by crash/stage policy. |
| R03 missing artifact during recovery | PASS | ArtifactService marks missing; loop rebuilds/retries/warns/blocks; original never overwritten. |
| E01 normal export with blocker | PASS | `export_check` blocks; export design records blocked attempt; no normal output artifact. |
| E02 warning export allowed | PASS | `allow_warning_export = true` permits warning readiness/export; issues remain auditable. |
| E03 warning export not allowed | PASS | Warning-only output blocks/rejects export readiness with profile rationale. |
| T01 pause then resume | PASS | Task pauses at safe boundary; resume recomputes from durable state without discarding results. |
| T02 cancel then new task | PASS | Cancelled task terminal; new task may reuse valid outputs. |
| I01 rerun completed Page unchanged | PASS | Reuse decisions avoid duplicate provider calls and active results. |
| I02 rerun after OCR edit | PASS | Edited OCR remains active; stale translation/typeset regenerated or blocked until handled. |

## 13. ADR list

- `docs/design/workflow-state/adr/0001-canonical-workflow-vocabulary.md`
- `docs/design/workflow-state/adr/0002-retry-budget-and-crash-attempts.md`
- `docs/design/workflow-state/adr/0003-export-check-and-warning-readiness.md`
- `docs/design/workflow-state/adr/0004-recovery-committed-results-first.md`

## 14. Rejected alternatives

| Alternative | Reason rejected |
| --- | --- |
| Generic BPM/workflow engine | Overkill for MVP single-Page local workflow. |
| Page.status as recovery truth | Violates recovery invariants and cannot explain active pointer/artifact drift. |
| Provider Adapter decides retry/fallback/skip | Violates architecture boundary and makes recovery opaque. |
| QualityCheckService advances workflow state | Splits decision ownership and weakens auditability. |
| Store images/large payloads in SQLite | Violates data model and workspace artifact design. |
| Active flags on result rows | Data-model baseline uses active pointers as only P0 active source. |
| `completed` stage status | Replaced by canonical `done`. |
| `locked` stage status | Replaced by lock pointer/metadata. |
| Treat provider refusal as generic failure | Loses policy semantics and risks bypass-like retry behavior. |
| Retry until success | Unbounded cost/loop risk. |
| Warning export always allowed | Violates ProcessingProfileSnapshot policy. |
| Skipped blocks count as pure ready | Hides incomplete processing from user/export manifest. |
| Recovery promotes raw provider output by default | Too risky for MVP; must use committed results or normal validation path. |
| Forced/incomplete export in MVP | Deferred P1/P2 and must not be confused with normal export. |

## 15. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Retry/fallback loops | Persist retry decisions, crash retry ceiling, fallback visited set, and task decision ceiling. |
| Over-reuse stale results | Require source/config/context hashes and active pointer/artifact validation. |
| Under-reuse valid results | Use `reuse_cached_result` and recovery repair rules before provider calls. |
| Provider refusal mishandled as crash | First-class `refused` attempt, ToolRunLog, QualityIssue, decision. |
| Warning export confusion | `allow_warning_export` required; per-export acknowledgement deferred but not contradicted. |
| Missing artifact ambiguity | ArtifactService marks storage state; loop decides rebuild/warn/block. |
| Concurrent edit during recovery | Atomic expected-state pointer/status updates; exact repository mechanics deferred. |
| Lock semantics bypassed | Lock metadata, not status; automatic replacement prohibited without explicit override. |

## 16. Open questions and deferred decisions

See `open-questions.md`. Deferred areas include QualityCheck taxonomy, Provider DTOs, ArtifactService layout, ProcessingProfile defaults, Repository/DAO details, Export details, API/UI semantics, and P1/P2 features.
