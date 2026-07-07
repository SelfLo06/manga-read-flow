# Stage Transition Table v0.1

## Stage flow

```text
import
-> detection
-> ocr
-> translation
-> translation_check
-> cleaning
-> typesetting
-> export_check
-> ready_for_export | ready_for_export_with_warnings | blocked
```

Stages may be re-entered by explicit rerun, stale propagation, recovery, retry, fallback, or upstream retry. Re-entry must validate current input/config/context hashes.

## Legal stage transitions

| Current stage | Entry prerequisites | Accepted output | Warning / partial output | Blocking output | Safe boundary |
| --- | --- | --- | --- | --- | --- |
| `import` | Valid local file, Project/Batch/Page scope, allowed file type. | Original artifact registered; Page `uploaded`; next `detection`. | Metadata warnings may remain visible. | No original artifact means Page `blocked`. | Yes |
| `detection` | Original artifact `present`. | TextBlocks/geometry/masks created; detection `done`; next `ocr`. | Low confidence or complex regions become `needs_review`/`skipped` with issues. | No usable region when profile requires text means `blocked` or `pause_for_user`. | Yes |
| `ocr` | TextBlock detection `done`, block not skipped, crop/mask rebuildable. | OCRResult created; active OCR pointer set; OCR `done`. | Low confidence OCR may become warning/needs_review and continue if allowed. | Target `failed`/`blocked`; Page partial/warning/pause/block by profile. | Yes, per block and batch slice |
| `translation` | Active OCR pointers, current Page context, glossary snapshot/hash. | TranslationResults created; active translation pointers set; translation `done`. | Partial output persists valid block results; missing/invalid blocks get issues and retry/warn/pause/block decision. | Provider refusal, invalid output, exhausted budget, or missing config leads fallback/pause/block. | Yes |
| `translation_check` | Active translations or explicit missing/skipped targets. | Check status `done`; next `cleaning`. | Warnings such as terminology/length/awkwardness remain visible; continue if profile allows. | Open blocking issue sets target/Page `blocked`. | Yes |
| `cleaning` | Original artifact, geometry/mask, processable regions. | Cleaned artifact registered; Page active cleaned pointer set; cleaning `done`. | Complex background may be `skipped`; warning issue required. | Missing original/mask or profile-blocking cleaning issue blocks/pause. | Yes |
| `typesetting` | Active translations, cleaned artifact or original-plus-skip strategy. | Typeset artifact registered; Page active typeset pointer set; typesetting `done`. | Overflow may retain preview and become warning if allowed. | Blocking overflow/font/artifact issue sets Page `blocked`. | Yes |
| `export_check` | Fresh active typeset artifact; issue query available. | `finish_ready_for_export` or `finish_ready_for_export_with_warnings`. | Warnings require `allow_warning_export = true`; skipped blocks cannot become pure ready. | Open blockers or disallowed warnings block export readiness. | Yes |

## Legal ProcessingTask transitions

| From | Legal to | Notes |
| --- | --- | --- |
| `queued` | `running`, `cancelled` | Runner starts or user cancels before start. |
| `running` | `pausing`, `cancelling`, `interrupted`, `succeeded`, `succeeded_with_warnings`, `blocked`, `failed` | Terminal workflow outcomes require persisted decisions unless infrastructure failure prevents it. |
| `pausing` | `paused`, `interrupted` | Pause completes only at safe boundary. |
| `paused` | `queued`, `running`, `cancelled` | Resume may requeue or run immediately. |
| `cancelling` | `cancelled`, `interrupted` | Cancellation completes at safe boundary. |
| `interrupted` | `recovering`, `cancelled`, `failed` | Startup reconciliation normally enters `recovering`. |
| `recovering` | `running`, `paused`, `blocked`, `failed`, `succeeded`, `succeeded_with_warnings` | Outcome depends on durable evidence and resume policy. |
| `succeeded`, `succeeded_with_warnings`, `failed`, `cancelled` | none | Create a new task for rework. |
| `blocked` | none for same automatic task | Create a new task or explicit resume after state changes. |

## Legal WorkflowAttempt transitions

| From | Legal to |
| --- | --- |
| `planned` | `running`, `skipped`, `reused_cached`, `cancelled` |
| `running` | `succeeded`, `failed`, `refused`, `cancelled`, `interrupted`, `abandoned_after_crash` |
| `interrupted` | `succeeded`, `failed`, `refused`, `abandoned_after_crash` during recovery |
| Terminal statuses | none |

Terminal statuses are `succeeded`, `failed`, `refused`, `cancelled`, `skipped`, `reused_cached`, and `abandoned_after_crash`.

## Legal TextBlock stage transitions

| From | Legal to | Notes |
| --- | --- | --- |
| `pending` | `running`, `done`, `skipped`, `blocked` | Direct `done` only by valid reuse/repair. |
| `running` | `done`, `failed`, `skipped`, `needs_review`, `blocked`, `stale` | `stale` if upstream edit invalidates in-flight work. |
| `done` | `stale`, `needs_review`, `skipped`, `blocked`, `running` | `running` requires explicit rerun/refresh. |
| `failed` | `running`, `skipped`, `needs_review`, `blocked` | Retry/manual path. |
| `skipped` | `pending`, `running`, `stale` | Unskip recomputes from upstream state. |
| `needs_review` | `running`, `done`, `skipped`, `blocked`, `stale` | User acceptance/edit/check may resolve. |
| `stale` | `running`, `done`, `skipped`, `blocked` | `done` only after validation/reuse/rerun. |
| `blocked` | `pending`, `running`, `needs_review`, `skipped` | Only after blocker is resolved or an allowed path is selected. |

## Illegal transitions

- `cancelled` ProcessingTask -> `running` on the same task.
- `succeeded` / `succeeded_with_warnings` ProcessingTask -> `running` on the same task.
- `blocked` ProcessingTask -> `running` without changed evidence, config, profile, user action, or explicit resume request.
- WorkflowAttempt terminal status -> any other status.
- `WorkflowAttempt.succeeded` without accepted durable result/artifact evidence or a valid reuse decision.
- Provider refusal represented only as generic `failed`.
- Downstream stage `done` while required upstream stage is `pending`, `failed`, `blocked`, or `stale`.
- `ocr_status = done` without active OCR pointer, except explicit skipped/non-text target.
- `translation_status = done` without active TranslationResult pointer, except explicit skipped target.
- Clearing `stale` without dependency-hash validation, rerun, reuse decision, or user acceptance path.
- Automatic replacement of a locked translation without explicit user override.
- Export readiness while active typeset artifact is missing, stale, or hash-incompatible.
- Normal export/readiness while open blocking QualityIssues remain.
- Pure `ready_for_export` when any TextBlock or required stage is skipped.

## Pause and cancel boundaries

Pause/cancel requests are honored at the nearest safe boundary:

- No database write transaction is held across provider/tool calls.
- If a provider/tool call cannot be interrupted safely, the task enters `pausing` or `cancelling` and waits for the call to return or for recovery to mark the attempt `interrupted` / `abandoned_after_crash`.
- Completed durable outputs before the boundary remain available.
- Cancelled tasks do not auto-resume; a later task may reuse valid outputs by hash.
