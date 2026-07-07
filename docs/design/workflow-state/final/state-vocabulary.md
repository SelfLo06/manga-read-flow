# Workflow State Vocabulary v0.1

This file defines canonical MVP workflow-state names for implementation. Exact database enum enforcement remains a persistence-design decision, but code and tests should use this vocabulary unless a later ADR changes it.

## Workflow stages

| Stage | Meaning |
| --- | --- |
| `import` | Register user-provided local image as the original artifact. |
| `detection` | Detect TextBlocks, geometry, reading order, and masks. |
| `ocr` | Produce OCRResult versions and active OCR pointers. |
| `translation` | Produce TranslationResult versions from active OCR and Page context. |
| `translation_check` | Check translation quality, structure, terminology, length, and refusals. |
| `cleaning` | Produce cleaned image artifacts or explicit cleaning skips. |
| `typesetting` | Produce typeset image artifacts from active translations and cleaned/base image. |
| `export_check` | Compute export readiness and export preconditions. Actual ExportRecord behavior belongs to export design. |

`artifact_cleanup` is an audit/maintenance stage from the data-model baseline. It is not required for the MVP single-Page happy path.

## ProcessingTask status

| Status | Meaning | Terminal |
| --- | --- | --- |
| `queued` | Task is persisted and waiting for TaskRunner. | No |
| `running` | TaskRunner is executing and heartbeat is current. | No |
| `pausing` | Pause requested; task is moving to a safe boundary. | No |
| `paused` | Task stopped at a safe boundary and can resume. | No |
| `cancelling` | Cancel requested; task is moving to a safe boundary. | No |
| `cancelled` | Task was cancelled and must not auto-resume. | Yes |
| `interrupted` | Task lost heartbeat or process crashed before reconciliation. | No |
| `recovering` | Recovery is reconciling durable evidence. | No |
| `succeeded` | Requested work reached ready output with no warning outcome. | Yes |
| `succeeded_with_warnings` | Requested work reached warning-bearing ready output. | Yes |
| `blocked` | Workflow cannot proceed without changed state or user/config action. | Yes for that task |
| `failed` | Non-recoverable task-level infrastructure failure outside normal block semantics. | Yes |

`blocked` can be followed by a new task or explicit resume task after the blocking condition changes. The same task must not silently resume from `blocked`.

## WorkflowAttempt status

| Status | Meaning |
| --- | --- |
| `planned` | Attempt row reserved before execution. |
| `running` | Stage execution started. |
| `succeeded` | Accepted durable evidence exists for the attempt output. |
| `failed` | Attempt ended with non-refusal error or invalid output. |
| `refused` | Provider policy/refusal path was returned and recorded. |
| `cancelled` | Attempt stopped due to task cancellation at a safe boundary. |
| `skipped` | Attempt intentionally did no provider/tool work because target/stage was skipped. |
| `reused_cached` | Matching durable result/artifact satisfied the stage without provider/tool call. |
| `interrupted` | Attempt was safely interrupted before terminal outcome. |
| `abandoned_after_crash` | Process died during/around the attempt and no durable accepted evidence proves success. |

Attempt rows are append-only execution evidence. A terminal attempt is never reopened for a second provider call.

## Page status

Page status is a persisted, repairable aggregate for UI and filtering. It is never recovery truth.

| Status | Meaning |
| --- | --- |
| `uploaded` | Original artifact is registered. |
| `queued` | Work for this Page is queued. |
| `processing` | A task is actively processing this Page. |
| `paused` | Processing is paused at a safe boundary. |
| `cancelled` | Last active task was cancelled; durable outputs may remain. |
| `interrupted` | Last active task lost heartbeat before recovery. |
| `recovering` | Recovery is reconciling this Page. |
| `needs_review` | User review or manual action is recommended or required. |
| `partially_failed` | Some targets failed/skipped, but the whole Page is not purely blocked. |
| `blocked` | Current state cannot produce normal export because required state/artifact or open blockers remain. |
| `ready_for_export` | Fresh active typeset output exists, no open blockers, and no unresolved warning/skipped state. |
| `ready_for_export_with_warnings` | Fresh active output exists, no open blockers, and unresolved warnings/skips are allowed by snapshot policy. |
| `exported` | At least one successful export exists. Export records remain the detailed source. |
| `deleted` | Page is soft-deleted and excluded from normal workflow/export. |

Aggregate flags such as `has_stale_blocks`, `translation_context_stale`, and issue counts may be persisted for speed, but must be repairable from TextBlock statuses, active pointers, artifacts, issues, attempts, and decisions.

## TextBlock stage status

Use the same canonical status values for `detection_status`, `ocr_status`, `translation_status`, `translation_check_status`, `cleaning_status`, `typesetting_status`, and `review_status` where applicable.

| Status | Meaning |
| --- | --- |
| `pending` | Stage has not yet produced accepted current output. |
| `running` | Stage is executing for this TextBlock or as part of a Page attempt. |
| `done` | Stage output is accepted and dependency hashes match current upstream state. |
| `failed` | Latest attempt failed and no accepted current output exists. |
| `skipped` | Stage/target intentionally skipped; this is not failure. |
| `needs_review` | User review/manual correction is needed or recommended. |
| `stale` | Existing selected output no longer matches active upstream input/context. |
| `blocked` | Stage cannot proceed under current evidence/profile/config. |

Do not use `completed`; the canonical completion value is `done`.

Do not use `locked` as a generic stage status. Translation locking is represented by `locked_translation_result_id` and lock metadata. Automatic workflow must not replace a locked translation without explicit user override, but stale propagation may still mark downstream state `stale`.

## QualityIssue status used by workflow

| Status | Meaning |
| --- | --- |
| `open` | Issue still applies. Open blocking issues block normal export. |
| `resolved` | Fixed by rerun, edit, user action, or explicit resolution. |
| `accepted_warning` | Warning remains auditable and is accepted under allowed policy. |
| `stale` | Active input/result changed; issue no longer applies to current state. |
| `superseded` | Replaced by a newer issue for the same target/root cause. |

## WorkflowDecision types

| Decision | Meaning |
| --- | --- |
| `continue` | Current stage accepted; advance to next required stage. |
| `reuse_cached_result` | Matching result/artifact satisfies stage without new provider/tool call. |
| `retry_same_stage` | Run the same stage/target again. Consumes retry budget. |
| `fallback_provider` | Switch to an allowed provider/implementation for the same stage. Consumes fallback allowance. |
| `retry_upstream_stage` | Rerun an upstream stage to repair downstream issue. Consumes upstream retry budget. |
| `skip_target` | Skip target/stage with visible issue and warning/block semantics. |
| `mark_warning` | Accept usable output with non-blocking issue still visible. |
| `pause_for_user` | Stop automation at safe boundary for user/config/manual action. |
| `block` | Stop because no safe automatic or paused path remains. |
| `finish_ready_for_export` | Page reaches pure export readiness. |
| `finish_ready_for_export_with_warnings` | Page reaches warning-bearing export readiness allowed by snapshot. |
| `cancel` | Stop because user/system cancelled the task. |
