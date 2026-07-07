# 1. Scope

This proposal covers the MVP single-Page workflow state vocabulary and transition rules for:

- MVP workflow stages.
- `ProcessingTask` lifecycle.
- `WorkflowAttempt` lifecycle.
- Page-level workflow status.
- TextBlock stage statuses.
- Safe stage boundaries.
- Legal and illegal state transitions.
- Persisted versus derived statuses.
- Single-Page happy-path advancement.

This proposal is design documentation only. It does not define SQL DDL, ORM models, API routes, frontend behavior, provider schemas, prompt templates, retry-budget arithmetic, or full QualityIssue taxonomy.

# 2. Role Bias

This agent optimizes for explicit, boring, recoverable state. The preferred model is:

- persist the minimum current-state fields needed for UI, recovery, and export gates;
- persist append-only `WorkflowAttempt` and `WorkflowDecision` records for explanation;
- derive aggregate readiness where doing so avoids duplicated truth;
- keep Provider Adapter, QualityCheckService, ArtifactService, and Repository boundaries strict.

The bias is against a generic workflow engine. A small stage vocabulary plus clear transitions is enough for MVP.

# 3. Assumptions

- `docs/HLD-v0.2.md` is treated as the stronger HLD baseline because it explicitly incorporates the data-model v0.1 feedback, while remaining consistent with `docs/HLD.md` at the architecture level.
- The source documents contain non-blocking vocabulary drift:
  - SRS Page status uses `translation_done`, while HLD v0.2 uses `translated`.
  - SRS TextBlock stage status includes `user_edited`; HLD v0.2 and the data-model final documents model user edits through versioned result rows, active pointers, and stale propagation instead.
  - Data-model open questions defer exact enum spellings.
- This proposal therefore recommends canonical MVP spellings for synthesis, but exact enum names remain open until final design.
- Recovery must use `ProcessingTask`, `WorkflowAttempt`, `WorkflowDecision`, `ProcessingArtifact`, `QualityIssue`, active pointers, hashes, and TextBlock stage statuses. `Page.status` alone is never authoritative.
- Page-level translation is executed per Page but saved per TextBlock.
- Cleaning and typesetting may be page-output operations while still needing TextBlock-level stage state for skipped, stale, or overflow blocks.

# 4. Proposed Model

Use four layers of state:

| Layer | Entity | Purpose | Persistence recommendation |
| --- | --- | --- | --- |
| Command state | `ProcessingTask.status`, `current_stage` | User/system requested work lifecycle and task control. | Persisted. |
| Execution evidence | `WorkflowAttempt.status` | One bounded attempt at one stage for one target. | Persisted append-only metadata. |
| Workflow rationale | `WorkflowDecision.decision_type` | Why the loop continued, retried, skipped, warned, blocked, paused, cancelled, or finished. | Persisted append-only. |
| Current domain state | `Page.status`, TextBlock stage statuses, active pointers | UI summary, recovery hints, export readiness inputs, stale propagation. | TextBlock statuses and active pointers persisted; Page status persisted as reconciled summary, not sole truth. |

MVP workflow stages:

| Stage | Main target | Output owner |
| --- | --- | --- |
| `import` | Page | Page original artifact pointer. |
| `detection` | Page / TextBlock | TextBlock rows, geometry, masks, detection status. |
| `ocr` | TextBlock | OCRResult rows and `TextBlock.active_ocr_result_id`. |
| `translation` | Page attempt, TextBlock results | TranslationResult rows and `TextBlock.active_translation_result_id`. |
| `translation_check` | Page / TextBlock | QualityIssue rows and translation check statuses. |
| `cleaning` | Page / TextBlock region | cleaned artifact pointer and TextBlock cleaning statuses. |
| `typesetting` | Page / TextBlock region | typeset artifact pointer and TextBlock typesetting statuses. |
| `export_check` | Page or Batch | export readiness, ExportRecord precheck when export is requested. |

`artifact_cleanup` exists in the data-model design as a workflow/audit stage, but it should not be required for the MVP single-Page happy path and should not affect export readiness except through artifact storage states.

# 5. State Vocabulary or Decision Vocabulary

## ProcessingTask statuses

Recommended canonical statuses:

| Status | Meaning | Persisted? |
| --- | --- | --- |
| `queued` | Task exists and is waiting for TaskRunner. | Yes |
| `running` | TaskRunner is actively executing or heartbeat is current. | Yes |
| `pausing` | Pause requested; task is moving to a safe boundary. | Yes |
| `paused` | Stopped at a safe boundary and resumable. | Yes |
| `cancelling` | Cancel requested; task is moving to a safe boundary. | Yes |
| `cancelled` | User/system cancelled; not automatically resumed. | Yes |
| `interrupted` | Previously running task lost heartbeat or process crashed. | Yes |
| `recovering` | Recovery reconciliation is in progress. | Yes |
| `succeeded` | Requested work reached a terminal successful outcome. | Yes |
| `succeeded_with_warnings` | Requested work completed with non-blocking warning state. | Yes |
| `blocked` | Workflow cannot proceed without user/config/provider/artifact action. | Yes |
| `failed` | Non-recoverable task-level failure outside normal quality/block decisions. | Yes |

`ready_for_export` and `ready_for_export_with_warnings` should primarily be Page-level workflow outcomes. A ProcessingTask may end as `succeeded` or `succeeded_with_warnings` and point to the final WorkflowDecision that set the Page outcome.

## WorkflowAttempt statuses

Use the data-model vocabulary:

| Status | Meaning | Persisted? |
| --- | --- | --- |
| `planned` | Attempt row reserved before execution, if needed. | Yes |
| `running` | Stage execution has started. | Yes |
| `succeeded` | Attempt produced accepted stage output or durable completion evidence. | Yes |
| `failed` | Attempt returned an error or invalid output. | Yes |
| `refused` | Provider refused content or policy disallowed processing. | Yes |
| `cancelled` | Attempt stopped due to task cancellation at a safe boundary. | Yes |
| `skipped` | Attempt intentionally did no provider/tool work because target was skipped. | Yes |
| `reused_cached` | Existing valid result/artifact was reused. | Yes |
| `interrupted` | Attempt was running when task/process was interrupted. | Yes |
| `abandoned_after_crash` | Recovery found no safe durable completion evidence. | Yes |

## Page-level statuses

Recommended canonical Page statuses:

| Status | Meaning | Persisted or derived? |
| --- | --- | --- |
| `uploaded` | Original artifact is registered; processing not started. | Persisted |
| `queued` | Work for this Page is queued. | Persisted summary |
| `processing` | One or more stages are running. | Persisted summary |
| `paused` | Active task paused for this Page. | Persisted summary |
| `cancelled` | Active task was cancelled; durable results may remain. | Persisted summary |
| `interrupted` | Active task crashed or heartbeat went stale before recovery. | Persisted summary |
| `recovering` | Recovery is reconciling this Page. | Persisted summary |
| `needs_review` | User action is recommended before pure ready/export quality. | Derived from issues/stage statuses, optionally persisted as summary |
| `partially_failed` | Some TextBlocks/stages failed but Page is not fully blocked. | Derived, optionally persisted |
| `has_warnings` | Non-blocking open warnings/skips exist. | Derived from QualityIssue and skipped statuses |
| `blocked` | Open blocking issue or missing required state prevents normal progress/export. | Persisted summary derived from issues |
| `ready_for_export` | All required outputs fresh; no open blocking issues; no unresolved warning state affecting pure readiness. | Persisted final summary plus derivable |
| `ready_for_export_with_warnings` | Exportable only under warning policy; warnings/skips remain auditable. | Persisted final summary plus derivable |
| `exported` | At least one successful export exists. | Derived from ExportRecord, optionally persisted |
| `deleted` | Page soft deleted and excluded from normal processing/export. | Persisted lifecycle |

Avoid persisting every micro-stage as Page status (`detecting`, `ocr_done`, `typesetting`) as the source of truth. Use `ProcessingTask.current_stage` and TextBlock stage statuses for detail; Page status is an aggregate UI/recovery hint.

## TextBlock stage statuses

TextBlock keeps per-stage statuses:

- `detection_status`
- `ocr_status`
- `translation_status`
- `translation_check_status`
- `cleaning_status`
- `typesetting_status`
- `review_status`

Canonical stage status values:

| Status | Meaning | Persisted? |
| --- | --- | --- |
| `pending` | Stage has not run and has sufficient upstream prerequisites or awaits them. | Yes |
| `running` | Stage currently executing for this TextBlock or as part of a Page attempt. | Yes |
| `done` | Stage output is accepted and dependency hashes match current upstream state. | Yes |
| `failed` | Stage failed and no accepted output exists for current inputs. | Yes |
| `skipped` | Stage or block intentionally skipped; not equivalent to failed. | Yes |
| `needs_review` | User review or manual correction is recommended/required. | Yes |
| `stale` | Previously selected output exists but no longer matches active upstream input/context. | Yes |
| `blocked` | Stage cannot proceed due to blocking issue/config/artifact/provider state. | Yes |
| `locked` | For review/translation selection, automatic replacement is not allowed without explicit user override. | Yes, only meaningful for review/translation lock semantics |

`user_edited` should not be a stage status in MVP. User edits are persisted by new `OCRResult` or `TranslationResult` rows with `source_type = user_edit` / `is_user_edited = true`, followed by active pointer updates and stale propagation.

# 6. Transition or Decision Rules

## Legal ProcessingTask transitions

| From | Legal to | Notes |
| --- | --- | --- |
| `queued` | `running`, `cancelled` | Runner starts or user cancels before start. |
| `running` | `pausing`, `cancelling`, `interrupted`, `succeeded`, `succeeded_with_warnings`, `blocked`, `failed` | Terminal outcome must have a WorkflowDecision except infrastructure failure. |
| `pausing` | `paused`, `interrupted` | Pause completes only at safe boundary. |
| `paused` | `queued`, `running`, `cancelled` | Resume can requeue or run immediately. |
| `cancelling` | `cancelled`, `interrupted` | Cancellation completes at safe boundary. |
| `interrupted` | `recovering`, `cancelled`, `failed` | Startup reconciliation normally enters recovering. |
| `recovering` | `running`, `paused`, `blocked`, `failed`, `succeeded`, `succeeded_with_warnings` | Based on recovered durable state. |
| terminal statuses | none, except new task creation | `succeeded`, `succeeded_with_warnings`, `blocked`, `failed`, `cancelled` are terminal for that task. |

Illegal ProcessingTask transitions:

- `cancelled` -> `running` on the same task. Create a new task to continue.
- `succeeded` -> `running` on the same task. Create a new task for rerun/rework.
- `blocked` -> `running` without a resolving user/config/artifact/profile action or explicit resume decision.
- Any state -> `succeeded` without reconciling required outputs, active pointers, artifacts, and open blocking issues.

## Legal WorkflowAttempt transitions

| From | Legal to |
| --- | --- |
| `planned` | `running`, `skipped`, `reused_cached`, `cancelled` |
| `running` | `succeeded`, `failed`, `refused`, `cancelled`, `interrupted`, `abandoned_after_crash` |
| `interrupted` | `succeeded`, `failed`, `abandoned_after_crash` during recovery only |
| terminal statuses | none |

Illegal WorkflowAttempt transitions:

- Reopening a terminal attempt for another provider call.
- Marking `succeeded` before provider/tool output, reused cache, or durable artifact/result evidence is registered.
- Marking provider policy refusal as `failed` only; refusal must use `refused` or carry first-class refusal metadata.

## TextBlock stage transitions

| From | Legal to | Notes |
| --- | --- | --- |
| `pending` | `running`, `skipped`, `reused via done`, `blocked` | Reuse may directly set `done` with reuse decision/attempt. |
| `running` | `done`, `failed`, `skipped`, `needs_review`, `blocked`, `stale` | `stale` during running only if upstream edit/cancel/recovery invalidates work. |
| `done` | `stale`, `needs_review`, `skipped`, `blocked`, `running` | `running` only for explicit rerun or forced refresh. |
| `failed` | `running`, `skipped`, `needs_review`, `blocked` | Retry/manual path. |
| `skipped` | `pending`, `running`, `stale` | Unskip resets according to upstream state. |
| `needs_review` | `running`, `done`, `skipped`, `blocked` | User edit or acceptance can resolve. |
| `stale` | `running`, `done`, `skipped`, `blocked` | `done` only by cache/reuse validation against current inputs. |
| `blocked` | `pending`, `running`, `needs_review`, `skipped` | Only after blocker is resolved or user selects allowed path. |
| `locked` | `stale`, `needs_review`, `done` | Lock should prevent automatic replacement, not prevent stale marking. |

Illegal TextBlock transitions:

- Downstream `done` while upstream required stage is `pending`, `failed`, `blocked`, or `stale`.
- `translation_status = done` when `active_translation_result_id` is missing.
- `ocr_status = done` when `active_ocr_result_id` is missing, except a truly skipped/non-text block.
- Clearing `stale` without dependency-hash validation, rerun, user acceptance, or documented reuse.
- Treating `skipped` as `failed`.
- Replacing a locked translation through automatic workflow without explicit user override.

## Stage transition table

| Current stage | Entry prerequisites | On accepted output | On warning / non-blocking issue | On blocking issue / unrecoverable failure | Safe boundary after stage? |
| --- | --- | --- | --- | --- | --- |
| `import` | Valid local image upload and Project/Batch/Page scope. | Set `Page.original_artifact_id`; Page `uploaded`; next `detection`. | Unsupported metadata may warn but original remains. | Block import; no processing without original artifact. | Yes |
| `detection` | Original artifact present. | Create/update TextBlocks; detection `done`; next `ocr`. | Low confidence/complex blocks become `needs_review` or `skipped`; continue if profile permits. | Page `blocked` if no processable blocks and profile requires text. | Yes |
| `ocr` | TextBlock detection `done`; not skipped; crop/mask available or rebuildable. | Create OCRResult; update active OCR pointer; OCR `done`; next page translation when eligible blocks complete. | Low confidence -> OCR `needs_review` with warning; may continue. | OCR `failed`/`blocked` for target; Page may be partial, warning, pause, or blocked by profile. | Yes, per TextBlock and after OCR batch |
| `translation` | Page context from active OCR pointers and glossary version. | Create TranslationResults for valid blocks; update active translation pointers; translation `done`; next `translation_check`. | Partial output persists valid block translations; missing blocks get issues; decision retry/warn/pause/block. | Provider refusal/invalid output may retry, fallback, pause, or block. | Yes |
| `translation_check` | Active translations or known missing translations. | translation_check `done`; next `cleaning`. | `needs_review`, term mismatch, too long, etc.; continue only if non-blocking/profile allows. | Blocking issue sets target/Page `blocked`. | Yes |
| `cleaning` | Original artifact, masks/geometry, processable blocks. | Register cleaned artifact; update `Page.active_cleaned_artifact_id`; cleaning `done`; next `typesetting`. | Complex background can be `skipped`; warning issue; output may preserve original area. | Missing mask/artifact or profile-blocking cleaning issue blocks affected target/Page. | Yes |
| `typesetting` | Active cleaned artifact or original-plus-skip strategy; active translations. | Register typeset artifact; update `Page.active_typeset_artifact_id`; typesetting `done`; next `export_check`. | Overflow can retain preview and mark warning; Page may become exportable with warnings. | Blocking overflow/font/artifact issue sets Page `blocked`. | Yes |
| `export_check` | Active typeset artifact present/fresh; issue query available. | Page `ready_for_export` or `ready_for_export_with_warnings`. | Warnings allowed only by ProcessingProfileSnapshot. | Page `blocked`; normal export rejected. | Yes |

Pause and cancel are legal only at safe boundaries unless the current provider/tool call can be safely interrupted with a persisted `interrupted` or `cancelled` attempt. No write transaction should span a provider call.

# 7. Recovery Impact

On startup or task pickup:

1. Find `ProcessingTask.status = running` or transitional statuses with stale `heartbeat_at`.
2. Mark task `interrupted`, then `recovering`.
3. Find `WorkflowAttempt.status = running`.
4. For each running attempt:
   - if durable result/artifact evidence exists and dependency hashes match, mark the attempt `succeeded` or create a recovery decision to reuse/accept;
   - if no safe evidence exists, mark `abandoned_after_crash` or `interrupted`;
   - if provider refusal evidence exists, keep refusal as refusal, not crash.
5. Reconcile TextBlock stages from active pointers, result hashes, artifact storage states, QualityIssues, and decisions.
6. Resume from the earliest required non-done/non-fresh stage.

Recovery outcomes:

- Completed OCR with active pointer and valid hashes is not rerun.
- Completed translation with active pointers and matching context/glossary/source hashes is not rerun.
- Missing active cleaned/typeset artifacts mark the relevant artifact `missing` and make cleaning/typesetting/export_check stale, warning, or blocked according to rebuildability/profile.
- Page status is repaired as an aggregate after reconciliation.

# 8. Stale Propagation Impact

Stale is a first-class persisted TextBlock stage status and Page summary input.

OCR edit:

- Create new OCRResult and set `TextBlock.active_ocr_result_id`.
- Set `translation_status = stale`.
- Set `translation_check_status = stale`.
- Set `typesetting_status = stale`.
- Set `review_status = needs_review`.
- Set `Page.translation_context_stale = true` and `Page.has_stale_blocks = true`.
- Mark downstream issues tied to old translation/typesetting inputs `stale` or `superseded`.

Translation edit:

- Create new TranslationResult and set `TextBlock.active_translation_result_id`.
- Set `typesetting_status = stale`.
- Set `review_status = needs_review`.
- Set `Page.has_stale_blocks = true`.
- Mark prior typesetting issues tied to old translation input `stale` or `superseded`.

TextBlock skipped:

- Set relevant downstream stages to `skipped`.
- Preserve original image content for that region.
- Create warning QualityIssue unless profile makes the skip blocking.
- Page cannot be pure `ready_for_export`; it can become `ready_for_export_with_warnings` if policy allows.

TextBlock unskipped:

- Reset downstream stages to `pending` when upstream prerequisites are missing.
- Set downstream stages to `stale` when old outputs exist but dependency hashes do not match current inputs.

# 9. ProcessingProfileSnapshot Impact

This proposal does not design full profile management, but state transitions depend on immutable `ProcessingProfileSnapshot` policy for:

- whether warnings may continue to `ready_for_export_with_warnings`;
- whether warning export is allowed;
- whether skipped complex regions are warning or blocking;
- whether low OCR confidence or translation quality issues become `needs_review`, retry, pause, warning, or block;
- whether provider refusal may fallback, pause for user, warn/skip, or block;
- retry/fallback budget decisions, owned by the WorkflowLoopEngine.

Status changes must reference the snapshot used for the task/decision. Mutable ProcessingProfile template edits must not reinterpret historical task outcomes.

# 10. Artifact / QualityIssue / Active Pointer Impact

Artifact impact:

- Official artifacts are registered only through ArtifactService.
- Page stores artifact IDs for original, active cleaned, and active typeset outputs.
- TextBlock stores active mask artifact where applicable.
- Image bytes and large payloads are never stored in SQLite.
- Original images are never overwritten.
- Missing files become `ProcessingArtifact.storage_state = missing`; records are not silently deleted.

QualityIssue impact:

- QualityCheckService creates/classifies QualityIssues but does not advance workflow state.
- WorkflowLoopEngine consumes QualityIssues and emits WorkflowDecisions.
- Open blocking QualityIssues in export scope block normal export.
- Warning issues can allow `ready_for_export_with_warnings` only under the active ProcessingProfileSnapshot.
- Provider refusal creates ToolRunLog + WorkflowAttempt + QualityIssue + WorkflowDecision.

Active pointer impact:

- `TextBlock.active_ocr_result_id` is required for OCR `done`.
- `TextBlock.active_translation_result_id` is required for translation `done`, except skipped blocks.
- `Page.active_cleaned_artifact_id` is required for cleaning `done` at Page-output level unless cleaning is intentionally skipped by policy.
- `Page.active_typeset_artifact_id` is required for Page export readiness.
- Active pointers are not cleared by stale propagation; they remain selected but not export-effective until refreshed/reconciled.

# 11. Repository and Transaction Implications

Conceptual transaction boundaries:

- Persist `ProcessingTask` and `ProcessingProfileSnapshot` before work starts.
- Persist `WorkflowAttempt` start before calling a provider/tool.
- Do not hold a database write transaction during provider/tool execution.
- After provider/tool returns, register files through ArtifactService before committing accepted result pointers.
- Commit result rows, active pointer changes, TextBlock stage statuses, QualityIssues, WorkflowDecision, and Page summary status in one transaction when they represent one workflow decision.
- Commit pause/cancel/interrupted/recovering transitions with heartbeat/recovery metadata so restart can explain them.

Repository/DAO implications without specifying method names:

- query runnable/stale tasks by status and heartbeat;
- query latest attempts and decisions by task/stage/target;
- query active OCR/translation pointers and dependency hashes;
- query unresolved blocking/warning issues by export scope;
- update active pointers only with same-TextBlock/Page ownership validation;
- update stage statuses with expected-current-state checks to avoid accidental stale overwrite;
- persist append-only attempt/decision records.

# 12. Invariants

- Provider Adapter must not access SQLite.
- Provider Adapter must not register official artifacts.
- Provider Adapter must not create QualityIssues.
- Provider Adapter must not decide retry, fallback, skip, warning, pause, cancel, or block.
- QualityCheckService must not advance workflow state.
- WorkflowLoopEngine owns workflow decisions.
- ArtifactService owns official artifact path, hash, registration, retention, cleanup, missing, and trash lifecycle.
- Repository / DAO owns SQLite access.
- No image BLOBs in SQLite.
- Original images are never overwritten.
- Active pointers are the P0 current-result source of truth; no independent active flags.
- Recovery must not rely only on `Page.status`.
- Normal export blocks unresolved open blocking QualityIssues.
- Warning export follows ProcessingProfileSnapshot.
- Logs, examples, ToolRunLog messages, and artifacts must not contain API keys, tokens, or secrets.

# 13. Rejected Alternatives

| Alternative | Rejection rationale |
| --- | --- |
| Single Page status as source of truth | Fails recovery, partial failure, TextBlock isolation, and stale propagation. |
| One generic status for TextBlock | Cannot represent OCR done, translation stale, cleaning skipped, and typesetting blocked at the same time. |
| `user_edited` as a stage status | User edits are better represented by immutable result versions, active pointers, and downstream stale states. |
| Result-table `is_active` flags | Conflicts with data-model decision to use owner active pointers only. |
| Treat skipped as failed | Violates MVP rule that complex regions may be skipped without failing the whole Page. |
| Treat provider refusal as crash/failure only | Violates first-class provider refusal path and compliance traceability. |
| Automatic resume of cancelled tasks | Cancelled work should remain terminal; continuation should create a new task that may reuse valid results. |
| Persist only append-only logs and derive all current state | UI, recovery, and export gates need explicit active pointers and stage statuses. |
| Generic BPM/workflow library | Overkill for MVP single-Page workflow and risks hiding recovery rules. |

# 14. Validation Against HARNESS Scenarios

| Scenario | Result | Notes |
| --- | --- | --- |
| H01 Single Page happy path | PASS | Import registers original; detection creates TextBlocks; OCR and translation set active pointers; cleaning/typesetting set Page artifact pointers; export_check sets `ready_for_export`. |
| F01 OCR fails once then succeeds | PASS | First attempt `failed`; decision `retry_same_stage`; retry attempt `succeeded`; OCR status `done`; active OCR pointer set. |
| F02 Translation invalid JSON then retry succeeds | PASS | Failed/refused/invalid attempt persists; issue available; retry decision persists; successful retry creates TranslationResults. |
| F03 Page translation partial output | PASS | Valid TranslationResults persist; missing/invalid blocks get issues and status `failed`, `needs_review`, `blocked`, or warning by profile. |
| F04 Provider refusal | PASS | `WorkflowAttempt.refused`, sanitized ToolRunLog, QualityIssue, and WorkflowDecision are first-class. |
| F05 Cleaning skips complex background | PASS | TextBlock cleaning `skipped`; warning issue; Page can be `ready_for_export_with_warnings`. |
| F06 Typesetting overflow | PASS | Preview artifact may be active/retained; QualityIssue controls warning/retry/pause/block. |
| S01 OCR edit after translation exists | PASS | New OCRResult active; downstream translation/check/typesetting stale; Page context stale. |
| S02 Translation edit after typesetting exists | PASS | New TranslationResult active; typesetting stale; review needs_review. |
| R01 Crash after OCR before translation | PASS | Task `interrupted` -> `recovering`; active OCR reused; resume at translation. |
| R02 Crash during provider call | PASS | Running attempt becomes `interrupted` or `abandoned_after_crash` unless durable evidence proves success. |
| R03 Missing artifact during recovery | PASS | Artifact marked `missing`; workflow rebuilds, retries upstream, warns, or blocks. |
| E01 Normal export with unresolved blocking issue | PASS | Export_check/ExportRecord blocks; no normal output artifact. |
| E02 Warning export allowed by profile | PASS | `ready_for_export_with_warnings` and warning export depend on snapshot. |
| E03 Warning export not allowed by profile | PASS | Page/task blocked or export rejected with profile reason. |
| T01 Pause then resume | PASS | `pausing` reaches safe boundary then `paused`; resume requeues/runs from next required stage. |
| T02 Cancel then new task | PASS | Same task stays `cancelled`; new task may reuse valid outputs. |
| I01 Re-run completed Page without changes | PASS | `reused_cached` attempt/decision can repair statuses without duplicate active results. |
| I02 Re-run after OCR edit | PASS | Active edited OCR remains; translation/typesetting stale until regenerated or reused against new hashes. |

# 15. Risks

- Persisted Page summary status can drift from TextBlock statuses, active pointers, and QualityIssues unless every workflow decision updates them atomically or recovery reconciles them.
- Exact enum spellings are not yet final, so implementation should not start from this proposal alone.
- `locked` as a TextBlock stage status can be ambiguous; final synthesis may prefer a separate lock pointer/status and keep stage statuses simpler.
- Page-level cleaning/typesetting plus TextBlock-level statuses need careful final modeling so partial skips and page artifact pointers do not contradict each other.
- Warning export may require explicit per-export user acknowledgement in addition to ProcessingProfileSnapshot policy; data-model open questions leave this unresolved.
- Batch aggregation is mostly outside this proposal and must not be inferred solely from Page statuses.

# 16. Open Questions

1. Exact enum spellings for task statuses, Page statuses, TextBlock stage statuses, attempt statuses, stages, and decision types.
2. Should `locked` remain a TextBlock `review_status` value only, or should it be represented solely by `locked_translation_result_id` plus review metadata?
3. Should Page status persist detailed stage-like values such as `detecting`/`ocr_processing`, or should MVP persist only aggregate statuses plus `ProcessingTask.current_stage`?
4. Is `export_check` the final workflow stage name, or should final design use `export` for both precheck and export attempt records?
5. Should warning export require explicit per-export user acknowledgement beyond `ProcessingProfileSnapshot.allow_warning_export`?
6. How should Page status aggregate when all processable TextBlocks are skipped by profile: `ready_for_export_with_warnings`, `needs_review`, or `blocked`?
7. What exact safe-interrupt behavior is expected for provider calls that cannot be cancelled mid-call?
8. Should `artifact_cleanup` be represented in the same stage enum for MVP implementation, or kept as a later maintenance workflow outside the main Page loop?
