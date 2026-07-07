# Workflow Decision Matrix v0.1

WorkflowLoopEngine owns all workflow decisions. Provider Adapters return structured results/errors only. QualityCheckService classifies issues but does not advance state.

## Decision priority

1. Honor cancel request at a safe boundary.
2. Honor pause request at a safe boundary.
3. Reuse valid cached/current output if hashes, active pointers, artifacts, and locks permit.
4. Continue when the stage output is complete and no issue blocks the next stage.
5. Retry when issue/error is retryable and budget remains.
6. Fallback when allowed and useful.
7. Retry upstream when downstream root cause points upstream and budget remains.
8. Skip a limited target when allowed by profile or user action.
9. Mark warning when output is usable and issue is non-blocking/accepted by policy.
10. Pause for user when a user/config/manual action can plausibly resolve the issue.
11. Block when no safe path remains.

## Decision rules

| Condition | Decision | Budget impact | Required side effects |
| --- | --- | --- | --- |
| Accepted output and fresh dependencies | `continue` | None | Persist attempt outcome, result/artifact registration, active pointer updates, issue updates, stage status. |
| Existing result/artifact matches current input/config/context | `reuse_cached_result` | None | Persist reused attempt or decision; avoid duplicate provider call/result. |
| Transient/retryable failure and stage budget remains | `retry_same_stage` | Consumes same-stage budget | Persist decision before retry; mirror before/after budget on decision/attempt. |
| Downstream issue rooted upstream and upstream budget remains | `retry_upstream_stage` | Consumes upstream budget | Mark downstream outputs stale/non-export-effective. |
| Current provider unavailable/refused/invalid and fallback allowed | `fallback_provider` | Consumes fallback allowance | Record selected fallback provider/config ref; do not mutate prompts to bypass policy. |
| Target is skippable and profile/user permits | `skip_target` | None | Set stage/target skipped; create/link visible QualityIssue; Page becomes warning-bearing. |
| Output usable with non-blocking issue | `mark_warning` | None | Leave or accept warning issue; Page may become warning-ready only if snapshot allows. |
| User/config/manual action can resolve | `pause_for_user` | None | Task `paused`; issue guidance visible; no hidden auto-loop on unchanged resume. |
| No retry/fallback/skip/pause path or export safety fails | `block` | None | Open blocking issue remains visible; Page/task blocked. |
| Export precheck has fresh output and no open blockers/warnings | `finish_ready_for_export` | None | Page aggregate `ready_for_export`. |
| Export precheck has fresh output, no blockers, warnings allowed | `finish_ready_for_export_with_warnings` | None | Page aggregate `ready_for_export_with_warnings`; warnings remain auditable. |
| User/system cancels | `cancel` | None | Running work stops at safe boundary; task terminal `cancelled`. |

## Retry budget rules

- Retry budget is consumed by persisted `retry_same_stage` and `retry_upstream_stage` decisions, not merely by failed attempts.
- `WorkflowAttempt.retry_budget_before/after` mirrors the decision values for audit and recovery.
- Count budget by stage, target, provider/config family when relevant, and input/config/context hash.
- A changed input/config/context key starts a new budget scope only when the change is real and persisted.
- `fallback_provider` consumes fallback allowance/visited-provider state. Later retries of the fallback consume the fallback attempt's stage budget.
- Provider refusal is not retryable against the same provider unless a non-policy transient error is also recorded and retry would not be policy evasion.
- Add a hard per-task automatic decision ceiling in implementation to protect against bugs even if per-stage budgets are misconfigured.

## Crash and abandoned-attempt budget rule

- `abandoned_after_crash` does not consume normal provider retry budget by itself.
- Automatic recovery retries after abandoned attempts are finite through `crash_recovery_retry_budget` in the snapshot or equivalent task-level crash retry ceiling.
- If crash retry budget is exhausted, recovery chooses `pause_for_user` when user action can help, otherwise `block`.
- If durable accepted evidence exists, recovery uses `reuse_cached_result` / `continue` instead of consuming crash retry budget.

## Fallback rules

Fallback is allowed only when:

- The snapshot allows fallback for the stage.
- A configured fallback provider/implementation is available and capable.
- The fallback provider has not already failed/refused for the same stage/target/input key without changed evidence.
- The fallback does not attempt provider-policy bypass or prompt evasion.

For provider refusal, fallback means an allowed separate route such as local provider, manual translation, allowed skip, warning path when valid, or block. It never means retrying the refusing provider with evasion logic.

## Skip rules

Skip is allowed for limited targets:

- complex detection/OCR region;
- no-text TextBlock;
- cleaning of complex background;
- manually skipped TextBlock;
- typesetting/rendering of an already skipped block where original content remains visible.

Skip requires:

- profile permission or explicit user action;
- visible QualityIssue or skip reason;
- warning-bearing Page outcome, never pure `ready_for_export`;
- preservation of original image and historical outputs.

Skip is illegal when it hides an unresolved blocker, makes the Page appear fully translated, or removes a required whole-Page output.

## Warning rules

`mark_warning` is allowed only when:

- output is usable and dependencies are fresh;
- issue is not blocking under the effective snapshot and QualityCheck policy;
- remaining risk is visible in QualityIssue/export metadata.

Warning export/readiness requires `ProcessingProfileSnapshot.allow_warning_export = true`. Per-export acknowledgement is deferred, but the workflow state must be able to block warning export if that later export design requires acknowledgement.

## Blocking rules

The workflow must block when:

- open blocking QualityIssue remains and no allowed retry/fallback/skip/pause path exists;
- required original or active output artifact is missing and not rebuildable;
- dependency hashes conflict;
- provider refusal affects required output and no allowed fallback/manual/skip/warning path exists;
- required provider config/API key is missing and no fallback or pause-for-config path exists;
- output would depend on stale state;
- export_check finds open blockers;
- warning export is disallowed and unresolved warnings/skips remain for export.

## Pause rules

Pause is appropriate for missing config, manual OCR/translation, user confirmation to skip, locked translation overwrite, warning acknowledgement if later required, or profile `pause_on_blocking`.

If the user resumes without changing the blocking evidence/config/profile/edit, the next decision should be `block` unless a budgeted path is newly available.

## Cancel rules

Cancel stops the current task at a safe boundary. Completed durable results/artifacts remain. Cancelled tasks do not auto-resume; new tasks may reuse valid outputs by hash.

## Minimal ProcessingProfileSnapshot policy fields

| Field group | Minimal fields |
| --- | --- |
| Identity | `snapshot_schema_version`, source profile id/version/name, `settings_hash`. |
| Retry budgets | Per-stage budgets for detection, OCR, translation, translation_check, translation_shorten/upstream repair, cleaning, typesetting, export rebuild if used. |
| Crash retry | `crash_recovery_retry_budget` or task-level abandoned-attempt retry ceiling. |
| Fallback | `allow_automatic_fallback`, per-stage ordered fallback provider/config refs or capability refs. |
| Refusal policy | Per-stage behavior: fallback, pause/manual, allowed skip, warning if valid, or block. |
| Warning export | `allow_warning_export`, optional warning issue allowlist. |
| Auto-skip | Stage/issue allowlist for automatic skip, especially complex regions. |
| Pause/block | `pause_on_blocking`, `pause_on_missing_config`, `pause_on_manual_needed`. |
| Quality strictness | Compact strictness/profile reference or severity override map consumed by QualityCheck/loop policy. |
| Artifact/debug retention hints | Flags affecting evidence retention, never workflow ownership. |

Snapshots must not contain API keys, tokens, credentials, secret headers, or raw authorization values.
