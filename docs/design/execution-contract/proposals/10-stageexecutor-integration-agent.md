# 10 StageExecutor Integration Proposal

## 1. Scope

This proposal defines the minimum `StageExecutor` integration contract for the FakeProvider single-Page backend vertical slice.

Focus areas:

- StageExecutor input and output contract.
- Execution sequence for one stage attempt.
- Provider call boundary.
- ArtifactService registration boundary.
- QualityCheckService invocation boundary.
- Transaction boundary before and after provider calls.
- Evidence returned to `WorkflowLoopEngine`.

Non-goals: implementation code, SQL DDL, ORM models, API handlers, frontend code, real provider integrations, real prompt templates, full retry policy, and full quality taxonomy.

## 2. Role Bias

Bias: maximize implementability of one backend Page slice while preventing `StageExecutor` from becoming a hidden `WorkflowLoopEngine`.

`StageExecutor` should be a deterministic execution adapter:

```text
durable stage context
-> one bounded attempt
-> provider/local tool call
-> artifact registration
-> quality classification
-> normalized stage result evidence
```

It must not choose the next workflow action.

## 3. Source Tension

One tension needs final synthesis:

- Data-model final says `QualityCheckService` owns issue creation.
- Phase 1B quality debate recommends `QualityCheckService` returns issue drafts/reports and persistence happens through the caller/Repository.

This proposal stays compatible with either API shape. `StageExecutor` may receive persisted issue ids or issue drafts from `QualityCheckService`, but it does not decide workflow outcome or active result acceptance.

## 4. Decisions

| Decision | Contract | Rationale |
| --- | --- | --- |
| D1 | `StageExecutor` receives a durable `StageExecutionContext` assembled by `WorkflowLoopEngine`/Repository. | Keeps provider inputs reproducible and avoids ad hoc reads scattered across executors. |
| D2 | Attempt start is persisted before any provider/local tool call. | Crash recovery can distinguish running, abandoned, failed, refused, and succeeded attempts. |
| D3 | No SQLite write transaction is held across provider/local tool calls. | Prevents long DB locks and supports pause/cancel/recovery at safe boundaries. |
| D4 | Providers receive only structured request DTOs, read-only input files, sanitized config, and an attempt temp root. | Preserves provider boundary and avoids SQLite/workspace ownership leaks. |
| D5 | Provider temp outputs become official only through `ArtifactService`. | Hash, path, retention, storage state, and safety flags stay centralized. |
| D6 | `QualityCheckService` is invoked after provider output normalization and after required artifact registration attempts. | Quality checks need provider evidence plus artifact evidence, but should not run workflow policy. |
| D7 | `StageExecutor` returns a normalized `StageResult` to `WorkflowLoopEngine`. | The loop gets enough evidence for continue/retry/fallback/skip/warning/pause/block without ceding decision ownership. |
| D8 | Result rows and active pointers are not made export-effective by `StageExecutor` alone. | Acceptance belongs to the `WorkflowLoopEngine` decision transaction. |

## 5. StageExecutor Input Contract

`StageExecutor` receives durable context, not live domain objects with hidden behavior.

Minimal `StageExecutionContext`:

| Field group | Required content |
| --- | --- |
| Identity | `task_id`, optional existing `attempt_id` if planned, `stage`, `target_type`, `target_id`, `project_id`, `batch_id`, `page_id`, optional `text_block_id`. |
| Policy snapshot | `profile_snapshot_id`, `profile_hash`, sanitized provider/config refs, stage retry budget before, debug/retention hints, quality strictness reference. |
| Provider selection | Provider kind/name/version/model/tool metadata chosen by `WorkflowLoopEngine`, plus capability evidence needed to build the request. |
| Inputs | Current active pointers, required result ids and hashes, official artifact ids and hash/storage evidence, language codes, glossary version/hash, page context hash, geometry/mask hashes, config hashes. |
| Idempotency evidence | Input/config/context hashes and attempt number. `StageExecutor` uses them for audit and request construction only. |
| Temp boundary | Stage/attempt-scoped temp root or token where provider may write temporary files. |
| Cancellation boundary | Read-only pause/cancel signal handle or equivalent safe-boundary indicator. |

The durable context answers "what should be attempted now?" It must not ask `StageExecutor` to discover retry budget, choose fallback providers, or infer whether the stage should run.

## 6. Attempt Start Boundary

Attempt start is persisted in a short transaction before the provider call.

Persist before provider call:

- `WorkflowAttempt.status = running`.
- stage, target scope, attempt number.
- provider/model/tool identity selected by the loop.
- `input_hash`, `config_hash`, `context_hash`, profile snapshot/hash.
- retry budget before, if already computed by the loop.
- start timestamp and correlation ids.

Optionally persist a `ToolRunLog` in `running` if the implementation wants a separate provider-call row before the call. If not, the first `ToolRunLog` may be written after provider return, as long as the running `WorkflowAttempt` exists before the call.

The write transaction ends before provider execution starts.

## 7. Execution Sequence

### Before provider call

1. Load and validate the durable context supplied by the loop.
2. Recheck required active inputs enough to avoid unsafe execution: target exists, project scope matches, required official artifacts are present/hash-valid or explicitly marked as missing evidence.
3. Create or mark the attempt `running` in a short transaction.
4. Allocate an attempt-scoped temp root outside official artifact paths.
5. Build the provider request DTO from durable context.
6. Redact/sanitize request diagnostics before any log or retained payload.
7. Release DB write transaction.

### Provider call

1. Call exactly one provider/local tool operation for this attempt.
2. Provider may read supplied input files and write only under the attempt temp root.
3. Provider returns `ProviderResult` with `success`, `partial_success`, `failure`, `refusal`, or `invalid_output`.
4. Provider must not access SQLite, register artifacts, create issues, update state, or decide retry/fallback/skip/warning/block.

### After provider call

1. Normalize provider result and map parse/schema failures to `invalid_output`.
2. Persist sanitized `ToolRunLog` evidence and attempt terminal status candidate: `succeeded`, `failed`, or `refused`.
3. Register required temp outputs and retained failed/debug payloads through `ArtifactService`.
4. Build candidate domain result drafts or candidate result evidence, without selecting active pointers.
5. Invoke `QualityCheckService` with provider evidence, artifact registration evidence, dependency state, result candidates, and profile quality strictness.
6. Return normalized `StageResult` to `WorkflowLoopEngine`.

## 8. ArtifactService Boundary

`ArtifactService` is called only for bytes that need official metadata or retained evidence.

Call `ArtifactService`:

- after provider returns temp output files;
- after a failed/refused/invalid attempt returns raw payload or diagnostic temp files that retention policy keeps;
- during import when an uploaded original image must become an official original artifact;
- during integrity checks when active artifact evidence is missing or hash-invalid.

`StageExecutor` supplies artifact intent: stage, target scope, expected artifact type, retention intent, safety flags, attempt/tool refs, and temp ref. `ArtifactService` validates and derives official path, hash, size, media type, storage state, and final safety/retention metadata.

Registration failure is not provider failure. It becomes `artifact_registration_failed` evidence in `StageResult`, and the temp file remains non-official unless replayed through normal registration.

## 9. QualityCheckService Boundary

Invoke `QualityCheckService` after provider normalization and artifact registration attempts, because quality classification needs the combined evidence:

- provider outcome/error/refusal evidence;
- registered artifact ids or registration failures;
- candidate result drafts or ids;
- active dependency state and hashes;
- profile quality strictness;
- attempt/tool metadata.

`QualityCheckService` may classify:

- empty OCR;
- invalid provider output;
- provider refusal;
- missing translation TextBlocks;
- cleaning complex background/skip evidence;
- typesetting overflow;
- artifact unavailable/hash-invalid/registration failure.

It returns a `QualityCheckReport` with issue ids or issue drafts, summary counts, blocking/severity facts, root/discovered stages, and non-binding suggested actions. It does not update active pointers, advance workflow state, consume retry budget, or choose fallback/warning/block.

## 10. StageExecutor Output Contract

`StageExecutor` returns a normalized `StageResult`.

| Field group | Required content |
| --- | --- |
| Identity | `stage`, `target_type`, `target_id`, `task_id`, `attempt_id`, scope ids. |
| Attempt outcome | `attempt_status_candidate`: `succeeded`, `failed`, `refused`, `cancelled`, or `interrupted`; timings; sanitized error/refusal fields. |
| Provider evidence | `ProviderResult.outcome`, provider identity, error code/class, `is_provider_refusal`, sanitized message, raw payload artifact ids when retained. |
| Artifact evidence | Registered artifact ids/metadata, registration failures, missing/hash-invalid evidence, non-official temp refs discarded or retained. |
| Candidate outputs | Result drafts or persisted candidate ids for valid OCR/translation outputs, detection candidates, cleaned/typeset artifact candidates, partial target map. |
| Quality evidence | `QualityCheckReport`, issue ids or issue drafts, summary counts, `has_blocking_issue`, max severity, root/discovered stage evidence. |
| Dependency evidence | Input/config/context hashes used, active dependency ids observed, freshness notes. |
| Boundary flags | `safe_boundary_reached`, `provider_called`, `artifact_registration_attempted`, `quality_check_invoked`. |

The `StageResult` contains evidence, not policy. It must not include `decision_type`, `next_stage`, selected fallback provider, accepted warning state, final Page readiness, or active pointer mutation instructions.

## 11. What WorkflowLoopEngine Receives

`WorkflowLoopEngine` receives `StageResult` plus current task/profile/budget/history state and decides:

- `continue`;
- `reuse_cached_result`;
- `retry_same_stage`;
- `fallback_provider`;
- `retry_upstream_stage`;
- `skip_target`;
- `mark_warning`;
- `pause_for_user`;
- `block`;
- `finish_ready_for_export`;
- `finish_ready_for_export_with_warnings`;
- `cancel`.

Only after that decision should Repository commit acceptance effects such as result rows, active pointers, issue lifecycle updates, `WorkflowDecision`, stage statuses, retry budget after, and Page aggregate status.

If the final implementation persists candidate result rows before the decision, they must remain unselected historical candidates until the loop accepts them.

## 12. What StageExecutor Must Never Decide

`StageExecutor` must never decide:

- whether to retry, fallback, skip, warn, pause, cancel, block, or finish ready;
- which fallback provider to use;
- whether provider refusal may be bypassed or re-prompted around;
- whether a warning is acceptable for export;
- whether retry budget is consumed;
- whether a result/artifact becomes active or export-effective;
- whether cached historical results should replace active pointers;
- whether missing artifacts should be rebuilt, ignored, warned, or blocked;
- whether a TextBlock/Page is finally skipped;
- whether a locked translation may be overwritten.

It may report evidence that makes those decisions possible.

## 13. Transaction Boundaries

| Boundary | Transaction rule | Durable evidence after crash |
| --- | --- | --- |
| Before provider | Short write transaction persists running attempt and optional running tool log. | Recovery can mark in-flight work `abandoned_after_crash` or reconcile returned evidence. |
| During provider | No SQLite write transaction. | A crash leaves at most running attempt plus temp/orphan files, not accepted output. |
| Provider returned, before artifact registration | Short writes may persist tool result/attempt evidence. | Recovery sees provider failure/refusal/invalid evidence if committed. |
| Artifact registration | ArtifactService uses short Repository transaction per official artifact registration. | Registered artifact is official but unselected until workflow acceptance. |
| Quality classification | Either returns drafts or persists issues through the agreed quality API. | Issues must reference attempt/tool/artifact evidence when persisted. |
| Workflow acceptance | One loop-owned transaction persists `WorkflowDecision`, result acceptance, active pointers, issue lifecycle updates, retry budget after, and stage statuses. | Recovery can trust accepted pointers/statuses only when this transaction committed. |

Do not combine the provider call with the acceptance transaction. Do not mark active pointers before quality and workflow decision evidence exists.

## 14. Rejected Alternatives

| Alternative | Rejected because |
| --- | --- |
| Let `StageExecutor` decide retry/fallback/block from provider errors. | Duplicates `WorkflowLoopEngine` and makes retry budget/recovery opaque. |
| Let providers write official artifacts directly. | Violates ArtifactService ownership of paths, hashes, retention, and cleanup. |
| Hold a DB transaction open across provider calls. | Creates lock, recovery, pause/cancel, and long-running call hazards. |
| Treat artifact registration success as active result acceptance. | Skips quality/workflow policy and can make bad output export-effective. |
| Treat provider refusal as ordinary failure. | Loses policy semantics and can trigger unsafe same-provider retry behavior. |
| Persist only Page status and skip attempt/tool evidence. | Breaks crash recovery and auditability. |
| Make `StageExecutor` perform cache reuse selection. | Cache/reuse is a workflow decision tied to active pointers, locks, and budgets. |

## 15. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Quality persistence API remains unresolved. | StageExecutor transaction ordering may be ambiguous. | Final synthesis must choose persisted issues vs issue drafts; `StageResult` supports both. |
| Candidate result persistence before acceptance is mishandled. | Invalid/partial output could become active accidentally. | Use active pointers only in loop-owned acceptance transaction. |
| Registration failure path is under-specified. | S03 recovery behavior becomes unclear. | Normalize `artifact_registration_failed` evidence and classify through QualityCheck/WorkflowLoopEngine. |
| Temp files are treated as durable evidence. | Crash recovery may trust unverified bytes. | Only official artifacts and committed result/decision state are recovery truth. |
| StageExecutor accumulates stage-specific policy branches. | It quietly becomes a workflow engine. | Limit branches to DTO construction, provider normalization, registration, and quality invocation. |
| Redaction ownership is split. | Provider payload artifacts could leak secrets. | Require sanitized provider metadata before ToolRunLog/artifact retention; final synthesis should assign a central redaction helper. |

## 16. HARNESS Coverage

| Scenario | Coverage |
| --- | --- |
| S01 Happy path stage execution | PASS: context load, attempt start, provider call, ArtifactService registration, QualityCheck report, `StageResult`, then loop decision. |
| S02 Provider call fails before artifact output | PASS: running attempt exists; provider error/refusal evidence is normalized; QualityCheck can classify; loop decides retry/fallback/block. |
| S03 File produced but artifact registration fails | PASS: temp output is non-official; registration failure is returned as artifact evidence; loop receives enough evidence. |
| S04 QualityCheck returns blocking issue | PASS: artifacts may remain auditable, but active/export-effective acceptance waits for loop decision. |
| S05 QualityCheck returns warning issue | PASS: issue remains visible in quality evidence; loop decides warning/continue/export policy. |
| P01-P05 Provider scenarios | PASS: provider envelope outcomes are preserved and never become direct workflow decisions. |
| A02-A04 Artifact scenarios | PASS: temp promotion, failed evidence, and missing/hash-invalid facts are routed through ArtifactService evidence. |
| Q01-Q06 Quality scenarios | PASS: QualityCheck gets provider/artifact/result/dependency evidence and returns classification, not workflow state changes. |
| F01-F07 FakeProvider scenarios | PASS: deterministic fake outputs use the same provider/temp/artifact/quality/stage result path as real providers. |

## 17. Open Questions

| Question | Blocking for final synthesis? |
| --- | --- |
| Does `QualityCheckService` persist issues directly or return issue drafts for the acceptance transaction? | Yes |
| Are candidate OCR/TranslationResult rows created before the loop decision, or only inside the acceptance transaction? | Yes |
| Should `ToolRunLog` be created as `running` before provider call or only written after provider returns? | No, as long as `WorkflowAttempt` start is durable. |
| What exact enum names are used for `artifact_registration_failed`, provider `invalid_output`, and attempt status after malformed output? | Yes |
| Which component owns central redaction before retained raw provider payload artifacts are registered? | Yes |
| Can MVP replay orphan temp files after crash, or always treat them as abandoned evidence? | No; recommended MVP behavior is abandoned unless replayed through normal registration/check/decision. |
