# StageExecutor Contract v0.1

## 1. Scope

StageExecutor executes one bounded stage attempt. It builds provider/local tool requests from durable context, records attempt evidence, calls one provider/local operation, routes files through ArtifactService, invokes QualityCheckService, and returns normalized evidence to WorkflowLoopEngine.

StageExecutor is not a workflow decision engine.

## 2. Input contract

StageExecutor receives `StageExecutionContext`.

| Field group | Required content |
| --- | --- |
| Identity | `task_id`, `stage`, `target_type`, `target_id`, `project_id`, `batch_id`, `page_id`, optional `text_block_id`, attempt number. |
| Policy snapshot | `profile_snapshot_id`, `profile_hash`, quality strictness, retention/debug hints, retry budget before as computed by WorkflowLoopEngine. |
| Provider selection | Provider kind/name/version/model/tool metadata chosen by WorkflowLoopEngine, plus capability metadata. |
| Inputs | Active pointers, result ids/hashes, official artifact ids and validation evidence, language codes, glossary version/hash, page context hash, geometry/mask hashes, config hashes. |
| Idempotency evidence | Input/config/context hashes for request construction and audit only. |
| Temp boundary | Attempt-scoped temp root or token. |
| Control boundary | Pause/cancel signal visible at safe boundaries. |

The context says what to attempt now. StageExecutor must not discover retry budget, select fallback providers, decide cache reuse, or infer final readiness.

## 3. Output contract

StageExecutor returns `StageResult`.

| Field group | Required content |
| --- | --- |
| Identity | Stage, target, task, attempt, and scope ids. |
| Attempt evidence | Candidate terminal status: `succeeded`, `failed`, `refused`, `cancelled`, `interrupted`; timings and sanitized error/refusal fields. |
| Provider evidence | ProviderResult outcome, provider identity, error kind/code, refusal marker, sanitized message, raw payload artifact ids when retained. |
| Artifact evidence | Registered artifact ids/metadata, registration failures, integrity reports, non-official temp refs discarded or retained as evidence. |
| Candidate outputs | Result drafts for OCR/translation, detection candidates, cleaned/typeset artifact candidates, partial target map. |
| Quality evidence | QualityCheckReport, issue drafts, lifecycle suggestions, summary counts, blocking/severity facts. |
| Dependency evidence | Input/config/context hashes, active dependency ids observed, freshness notes. |
| Boundary flags | `safe_boundary_reached`, `provider_called`, `artifact_registration_attempted`, `quality_check_invoked`. |

`StageResult` must not contain a WorkflowDecision, next stage, selected fallback provider, accepted warning state, final readiness, retry budget mutation instruction, active pointer mutation instruction, or provider-policy workaround.

## 4. Execution sequence

### 4.1 Before provider call

1. Load/validate the durable context supplied by WorkflowLoopEngine.
2. Recheck required preconditions enough to avoid unsafe execution: scope match, target exists, required official artifacts are present/hash-valid or missing evidence is explicit.
3. Persist or mark `WorkflowAttempt.status = running` in a short Repository transaction.
4. Include stage, target, attempt number, provider identity, input/config/context hashes, profile snapshot/hash, retry budget before, and start timestamp.
5. Allocate an attempt-scoped temp root outside official artifact paths.
6. Build ProviderRequest from durable context.
7. Run central sanitization for retained request diagnostics.
8. Release DB write transaction.

### 4.2 Provider/local tool call

1. Call exactly one provider/local tool operation for this attempt.
2. Provider may read supplied read-only input files and write only under the attempt temp root.
3. Provider returns `ProviderResult`.
4. Provider does not access SQLite, register official artifacts, create QualityIssues, update state, or decide workflow actions.

### 4.3 After provider call

1. Normalize ProviderResult.
2. Map adapter or StageExecutor parse/schema failures to `outcome = invalid_output`.
3. Persist sanitized ToolRunLog evidence. ToolRunLog can be created after return as long as the running WorkflowAttempt existed before the call.
4. Register required output temp files and retained failed/refusal/debug payloads through ArtifactService.
5. Build candidate domain result drafts. MVP-0 does not persist OCR/TranslationResult rows before workflow acceptance.
6. Invoke QualityCheckService with provider evidence, artifact evidence, candidate outputs, dependencies, and quality strictness.
7. Return StageResult to WorkflowLoopEngine.

## 5. ArtifactService boundary

StageExecutor calls ArtifactService for:

- original import;
- provider/local output temp files;
- retained failed/refusal/invalid/debug payloads;
- overflow previews;
- artifact integrity checks when active bytes are required.

StageExecutor supplies artifact intent and context. ArtifactService derives/validates official path, hash, size, media, retention class, storage state, and final safety flags.

If registration fails:

- provider output remains non-official;
- StageExecutor reports `artifact_registration_failed` in StageResult;
- QualityCheckService may classify `artifact_unavailable`;
- WorkflowLoopEngine decides retry, pause, or block.

## 6. QualityCheckService boundary

StageExecutor invokes QualityCheckService after provider normalization and artifact registration attempts.

QualityCheck receives:

- provider outcome/error/refusal evidence;
- registered artifacts or registration failures;
- candidate result drafts;
- active dependency state and hashes;
- profile quality strictness;
- attempt/tool metadata.

QualityCheck returns a report/drafts. It does not persist workflow state, update pointers, or choose next action.

## 7. Transaction boundaries

| Boundary | Rule | Crash evidence |
| --- | --- | --- |
| Attempt start | Short write transaction before provider call. | Recovery can mark running attempt abandoned/interrupted/refused/failed based on later evidence. |
| Provider call | No SQLite write transaction. | Crash leaves running attempt and possible temp/orphan files, not accepted output. |
| Tool evidence | Short write after provider return. | Recovery can distinguish failed/refused/invalid when committed. |
| Artifact registration | ArtifactService uses short Repository transaction(s). | Registered artifacts are official but unselected. |
| Quality classification | Returns report/drafts for caller persistence. | No state advancement by QualityCheck. |
| Workflow acceptance | Loop-owned transaction persists WorkflowDecision, issues, accepted result rows, active pointers, retry budget after, and statuses. | Recovery trusts accepted pointers/statuses only when this transaction committed. |

Do not hold a provider call inside the acceptance transaction. Do not mark active pointers before quality and workflow decision evidence exists.

## 8. Candidate persistence timing

MVP-0 rule:

- StageExecutor returns OCR/Translation result drafts.
- WorkflowLoopEngine acceptance transaction creates accepted result rows and updates active pointers together.

Allowed later variation:

- StageExecutor may persist candidate rows before acceptance only if they are explicitly unselected historical candidates.
- They must not become active or export-effective without WorkflowLoopEngine acceptance.

Artifact metadata is different: ArtifactService may register official artifacts before acceptance. Those artifacts are official but unselected until accepted.

## 9. WorkflowLoopEngine decision input

WorkflowLoopEngine receives StageResult plus current state and decides:

- continue;
- reuse cached result;
- retry same stage;
- fallback provider;
- retry upstream stage;
- skip target;
- mark warning;
- pause for user/config/manual action;
- block;
- finish ready for export;
- finish ready for export with warnings;
- cancel.

WorkflowLoopEngine also owns:

- retry/fallback budget consumption;
- provider fallback selection;
- warning acceptance;
- active pointer updates;
- TextBlock/Page/Task status updates;
- locked translation override behavior;
- rebuild decisions after missing artifacts;
- refusal path routing.

## 10. Stage-specific notes

| Stage | StageExecutor role |
| --- | --- |
| `import` | Register original through ArtifactService; no provider required. |
| `detection` | Call DetectorProvider, register masks if retained, return TextBlock candidate drafts. |
| `ocr` | Build crop/original+bbox request, call OCRProvider, return OCRResult drafts. |
| `translation` | Build Page context from active OCR/glossary, call TranslationProvider, return TranslationResult drafts and partial target evidence. |
| `translation_check` | May call QualityCheckService only; no provider required unless later design adds reviewer provider. |
| `cleaning` | Call CleanerProvider, register cleaned output or skip/cannot-clean evidence. |
| `typesetting` | Call TypesetterProvider, register typeset output/preview and layout evidence. |
| `export_check` | Validate active artifacts and open issues; no Provider Adapter. Actual ExportRecord/output is export design. |

## 11. Forbidden decisions

StageExecutor must never decide:

- retry/fallback/upstream retry/skip/warning/pause/cancel/block/readiness;
- fallback provider selection;
- same-provider retry after refusal;
- provider-policy bypass or re-prompting around refusal;
- warning export allowance;
- retry budget consumption;
- whether a result/artifact becomes active or export-effective;
- whether a cached historical result should replace active pointer;
- whether a missing artifact should be rebuilt, ignored, warned, or blocked;
- whether a TextBlock/Page is finally skipped;
- whether a locked translation may be overwritten.
