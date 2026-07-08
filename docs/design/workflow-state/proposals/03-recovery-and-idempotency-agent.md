# 1. Scope

This proposal covers MVP recovery and idempotency for the single-Page workflow-state design.

It focuses on:

- Crash recovery and restart reconciliation.
- Stale `ProcessingTask.status = running` rows.
- Stale `WorkflowAttempt.status = running` rows.
- Abandoned attempts after process death.
- Reuse of completed OCR, translation, cleaned image, and typeset image outputs.
- Input, config, profile, context, glossary, geometry, and artifact hashes used for safe reuse.
- Missing artifact detection and workflow impact.
- Safe resume from the next required stage without relying only on `Page.status`.

This proposal does not define SQL DDL, ORM mappings, API routes, full ArtifactService behavior, full QualityIssue taxonomy, or provider interfaces.

# 2. Role Bias

The recovery model should be conservative: never discard durable user-visible work, never silently trust summary status, and never mark output export-effective unless its active pointer, dependency hashes, artifact state, and open blocking issues agree.

Biases:

- Prefer reuse when durable evidence proves the output still matches current inputs.
- Prefer retry when work was interrupted before durable completion evidence exists and retry budget/profile allows it.
- Prefer rebuild when an output artifact is missing but its inputs are still available and deterministic enough for MVP regeneration.
- Prefer warning only when the `ProcessingProfileSnapshot` allows a non-blocking degradation.
- Prefer block when evidence is missing, inconsistent, policy-refused without acceptable fallback, or export would be unsafe.

# 3. Assumptions

- `docs/HLD.md` is treated as the current detailed-design baseline.
- No blocking conflicts were found among the required source documents. One expected evolution exists: SRS has simpler Page/TextBlock state examples, while HLD v0.2 and the data-model final docs refine them with active pointers, attempts, decisions, artifacts, and recovery vocabulary.
- MVP uses an in-process `TaskRunner`; recovery still persists enough state that a later runner can use the same model.
- Recovery is a WorkflowService / WorkflowLoopEngine responsibility. It may use a named internal recovery routine, but this proposal does not require a new generic workflow engine.
- Provider Adapters may have been executing when the process died. Recovery cannot ask the old provider call what happened; it must inspect persisted state and official artifacts.
- Official artifact presence and hash validation go through ArtifactService.
- SQLite access goes through Repository / DAO.
- Active pointers remain selected UI/downstream data even when downstream stages become stale. Export-effective is stricter than active.

# 4. Proposed Model

Use startup and project-open reconciliation before scheduling new work for a Project:

1. Find stale running tasks: `ProcessingTask.status = running` with stale or absent `heartbeat_at`.
2. Mark each stale task `interrupted`, then `recovering`, in a short transaction.
3. Find running attempts for those tasks and for the Project scope.
4. Reconcile each running attempt from durable evidence:
   - accepted active result pointers,
   - immutable result rows,
   - result dependency hashes,
   - official artifact metadata and storage state,
   - ToolRunLog outcome,
   - QualityIssue status,
   - WorkflowDecision history.
5. Mark attempts as `succeeded`, `failed`, `refused`, `interrupted`, or `abandoned_after_crash` according to evidence.
6. Recompute stage readiness from per-TextBlock stage statuses, active pointers, dependency hashes, artifacts, open issues, and profile policy.
7. Create a recovery `WorkflowDecision` explaining reuse, retry, rebuild, warning, pause, or block.
8. Return the task to a schedulable state if auto-resume is allowed, or keep it paused/blocked if profile, user control, or missing evidence requires user action.

Recovery should distinguish three concepts:

- Durable completion evidence: result rows and official artifacts that match current dependencies.
- Summary state: `Page.status`, task progress JSON, and aggregate flags. Useful for UI, not authoritative for recovery.
- Export-effective state: active output plus fresh dependency hashes, required artifact presence, and no open blocking issue in scope.

Idempotent rerun uses the same reconciliation logic even when there was no crash. A new task or rerun first asks, "Is the requested stage already satisfied for these exact inputs and policy?" If yes, it records reuse and does not create duplicate active results.

# 5. State Vocabulary or Decision Vocabulary

Recovery relies on the following vocabulary already present or implied by the source documents.

Task statuses relevant to recovery:

- `running`: task was actively executing.
- `interrupted`: task was running but its runner disappeared or heartbeat became stale.
- `recovering`: task is being reconciled before normal scheduling.
- `paused`: task waits for user/system resume.
- `blocked`: workflow cannot safely continue without user action or changed inputs.
- `cancelled`: task is terminal and must not auto-resume.
- `completed`: task reached its requested finish condition.

Attempt statuses relevant to recovery:

- `running`: attempt started but no terminal outcome was recorded.
- `succeeded`: accepted output exists and passed the WorkflowLoopEngine decision boundary.
- `failed`: attempt ended with non-refusal failure.
- `refused`: provider refusal was recorded.
- `interrupted`: attempt was stopped at a safe boundary or cancelled before provider completion.
- `abandoned_after_crash`: process died during an unsafe or unknown boundary, and no durable completion evidence proves success.
- `reused_cached`: no provider/tool call was needed because matching durable output already existed.
- `skipped`: stage/target was intentionally skipped by workflow decision.

Recovery decision vocabulary:

- `reuse_cached_result`: existing result/artifact is fresh and selected or selectable.
- `retry_same_stage`: previous attempt lacks successful evidence and retry budget allows another attempt.
- `retry_upstream_stage`: downstream output is invalid because upstream dependency changed or disappeared.
- `fallback_provider`: previous provider failed/refused and profile allows fallback.
- `skip_target`: profile permits skipping this target/stage with an auditable issue.
- `mark_warning`: non-blocking issue remains but workflow may continue.
- `block`: workflow cannot continue or export safely.
- `pause_for_user`: workflow needs explicit user choice, edit, or provider/config action.
- `continue`: reconciliation repaired state and normal next-stage execution can proceed.

Artifact storage states relevant to recovery:

- `present`: file exists and hash matches.
- `metadata_only_cleaned`: payload was intentionally removed by retention; metadata remains.
- `moved_to_trash`: artifact is not available for normal processing unless restored.
- `missing`: expected file is absent or hash check fails.
- `deleted`: artifact is permanently gone.

# 6. Transition or Decision Rules

Running task after crash:

- If `ProcessingTask.status = running` and heartbeat is stale, mark it `interrupted`, then `recovering`.
- If `cancel_requested_at` is set, finish recovery by marking the task `cancelled`; do not auto-resume.
- If `pause_requested_at` is set, finish recovery by marking the task `paused`; keep completed results.
- If no requested work remains after reconciliation, mark `completed`.
- If work remains and auto-resume is allowed by task resume policy/profile, enqueue or return to runnable state.
- If work remains but evidence/config/artifacts are insufficient, mark `blocked` or `paused` with a recovery decision.

Running attempt after crash:

- If matching accepted result rows and active pointers exist, dependency hashes match, and required artifacts are present or intentionally metadata-only, mark the attempt `succeeded` or leave a recovery decision `reuse_cached_result`.
- If a ToolRunLog/attempt recorded provider refusal, mark the attempt `refused`; do not call it a crash.
- If a ToolRunLog recorded failure or invalid output, mark the attempt `failed` and let WorkflowLoopEngine decide retry/fallback/block.
- If output artifacts exist but result rows or active pointer updates did not commit, treat the attempt as incomplete. Recovery may parse/reuse retained official output only if hashes match and the same acceptance rules can be replayed; otherwise mark `abandoned_after_crash`.
- If no durable output exists, mark `abandoned_after_crash`.

Reuse decision:

- OCR reuse requires active OCR pointer or selectable OCRResult for the same TextBlock, matching `input_hash`, `config_hash`, provider/model/tool version where relevant, and matching `geometry_hash`.
- Translation reuse requires active TranslationResult or selectable TranslationResult with matching `source_ocr_result_id`, `source_text_hash`, `context_hash`, `glossary_version_id` or `glossary_terms_hash`, provider/model/prompt/config hash, and no stale translation/check state.
- Cleaned image reuse requires active cleaned artifact pointer, artifact state `present`, matching source original/mask/geometry/config hash, and no open blocking cleaning issue for current inputs.
- Typeset image reuse requires active typeset artifact pointer, artifact state `present`, matching active translation text/hash, layout/config hash, cleaned source artifact hash, and no open blocking typesetting issue for current inputs.
- Page/status summaries can confirm the user-facing view but cannot independently authorize reuse.

Retry/rebuild decision:

- Retry the same stage when the prior attempt has no accepted durable output, the failure/refusal policy permits retry or fallback, and retry budget remains.
- Rebuild a downstream artifact when the missing output is derivable from fresh upstream active results and artifacts.
- Retry upstream when the downstream output depends on stale or missing upstream data.
- Do not retry provider calls merely because Page status is incomplete if matching active results already satisfy the stage.

Warn/block decision:

- Warn only for non-blocking issues or allowed stage skips under the effective `ProcessingProfileSnapshot`.
- Block when original image is missing, active output required for export is missing and cannot be rebuilt, dependency hashes conflict, unresolved blocking QualityIssue remains, provider refusal has no allowed fallback/manual/warning path, or active pointer ownership is inconsistent.

# 7. Recovery Impact

Recovery becomes an evidence-reconciliation pass, not a blind rerun.

Crash after OCR before translation:

- Task: `running` -> `interrupted` -> `recovering`.
- OCR attempt: marked `succeeded` or reused if active OCR result and hashes are valid.
- OCR stage: repaired to completed/done if necessary.
- Translation: remains pending or stale as appropriate.
- Decision: `continue` or `reuse_cached_result`, next stage `translation`.
- OCR provider is not called again.

Crash during provider call:

- Task enters `recovering`.
- Running attempt becomes `abandoned_after_crash` unless durable success/refusal/failure evidence exists.
- If retry budget remains and profile permits, next decision is `retry_same_stage`.
- If provider refusal evidence exists, decision follows refusal policy, not crash recovery.
- If output artifacts exist but were not accepted atomically, recovery either replays validation from retained official artifacts or abandons them as failed evidence.

Abandoned attempts:

- Are not deleted.
- Do not create active result pointers.
- May retain failed/partial artifacts by retention policy.
- Count as recovery evidence for audit, but do not by themselves consume additional retry budget unless the workflow-state final design chooses that arithmetic. This arithmetic should be finalized by the decision/retry design.

Restart reconciliation:

- Runs before task scheduling.
- Repairs inconsistent summary statuses when durable evidence is clear.
- Creates recovery decisions so UI and logs explain why the workflow resumed, reused, retried, warned, or blocked.

# 8. Stale Propagation Impact

Recovery must honor stale flags and may create stale propagation when dependency checks find drift.

Rules:

- Active pointer with matching dependency hashes and present artifacts can repair an accidentally stale or incomplete summary state.
- Active pointer with mismatched dependency hashes does not become export-effective. Downstream stages become stale or blocked.
- OCR edit keeps active OCR selected but makes translation, translation_check, and typesetting stale.
- Translation edit keeps active translation selected but makes typesetting stale.
- Missing cleaned image makes typesetting stale or blocked depending on rebuildability.
- Missing active typeset image blocks export until rebuilt or policy permits a warning path for a non-export use case. Normal export must not proceed with a missing active output.
- Old issues tied to obsolete input/result hashes should be marked `stale` or `superseded`; recovery should not count stale issues in export gates.

Recovery should not clear active pointers only because downstream state is stale. It should leave selected results available for review and make their export-effectiveness explicit through stage status and issues.

# 9. ProcessingProfileSnapshot Impact

Recovery decisions use the `ProcessingProfileSnapshot` attached to the task/attempt/export, not the current mutable profile template.

Snapshot inputs needed by recovery:

- Retry budgets by stage and whether an abandoned attempt counts against the budget.
- Fallback provider policy and allowed provider order.
- Whether skip is allowed for complex or failed targets.
- Warning policy, including whether warning export is allowed.
- Refusal policy: fallback, pause, warning, skip, or block.
- Retention/debug policy needed to interpret `metadata_only_cleaned` and missing payloads.
- Auto-resume behavior after crash, if included in MVP profile/task resume policy.

Profile changes after a crash do not rewrite historical attempt meaning. A new user-triggered task may create a new snapshot and use new config hashes; it must still treat older results as reusable only when dependencies match the new snapshot/config requirements.

# 10. Artifact / QualityIssue / Active Pointer Impact

Artifacts:

- ArtifactService validates registered artifacts by project-relative path, storage state, and hash.
- If a file is absent or hash mismatches, ArtifactService marks the artifact `missing`.
- Recovery never overwrites original images.
- Missing original artifact blocks processing and export.
- Missing failed-attempt payload does not necessarily block processing, but should remain visible as reduced diagnostic evidence.
- Missing successful payload with `metadata_only_cleaned` is acceptable only if no active result depends on those bytes for preview/export/rebuild.
- Active cleaned/typeset artifacts must be `present` for preview/export unless rebuilt first.

QualityIssue:

- Missing required artifact creates or updates an issue with root attribution to artifact/storage or the dependent stage, according to the later QualityIssue taxonomy.
- Provider refusal issues remain first-class and are not converted to crash issues.
- Open blocking issues in export scope block normal export.
- Warning issues can permit `ready_for_export_with_warnings` only if profile allows.
- Recovery should stale/supersede issues whose `input_hash`, `config_hash`, or `applies_to_result_id` no longer matches active inputs.

Active pointers:

- Active pointers are the P0 source of truth for current OCR, translation, cleaned image, and typeset image selection.
- Recovery may set an active pointer only when the result/artifact belongs to the same target scope, dependency hashes match current inputs, quality checks/decisions can be replayed or are already recorded, and no lock/manual rule is violated.
- Recovery must not create duplicate active results because results do not have active flags; pointer updates are single-field selections.
- Idempotent rerun reuses the existing active result where valid. If it creates a new result, it must be because input/config/context changed or the user explicitly requested regeneration.

# 11. Repository and Transaction Implications

Conceptual repository operations needed:

- Find stale running tasks by project/status/heartbeat.
- Mark task interrupted/recovering/paused/cancelled/blocked/completed.
- Find running attempts for a task or project.
- Load recovery evidence for a target: active pointers, result rows, stage statuses, artifacts, tool logs, issues, decisions, profile snapshot.
- Query reusable OCR/translation results by dependency hashes.
- Query reusable cleaned/typeset artifacts by owner/type/hash/storage state.
- Create WorkflowDecision and link related QualityIssues.
- Mark issues stale/superseded/resolved when recovery proves they no longer apply.
- Update active pointers and stage statuses atomically.

Transaction boundaries:

- Marking stale task to `interrupted` and then `recovering` should be transactional and short.
- Do not hold a write transaction while validating files on disk or calling providers.
- Artifact validation may update artifact storage state through ArtifactService/Repository.
- The following should commit atomically: result creation or selection, active pointer update, stage status repair, issue stale/supersede updates, and recovery WorkflowDecision.
- Attempt terminal status updates should commit before scheduling any retry.
- Idempotency-key duplicate suppression, if used for tasks, must be enforced before creating duplicate running tasks for the same target/request.

# 12. Invariants

- Recovery must not rely only on `Page.status`.
- Provider Adapter does not access SQLite.
- Provider Adapter does not register official artifacts.
- Provider Adapter does not decide retry, fallback, skip, warning, block, or recovery outcome.
- Provider Adapter does not create QualityIssue.
- ArtifactService owns official artifact lifecycle and missing-file detection.
- Repository / DAO owns SQLite access.
- QualityCheckService may classify issues but does not advance workflow state.
- WorkflowLoopEngine owns reuse, retry, fallback, skip, warning, pause, block, and finish decisions.
- No image BLOBs are stored in SQLite.
- Original images are never overwritten.
- Failed attempt metadata is persisted; failed artifacts are retained by default according to the data model baseline.
- Active pointers are the current result source of truth; no independent result active flags.
- Normal export blocks unresolved open blocking QualityIssues.
- Warning export follows the effective `ProcessingProfileSnapshot`.
- Logs, examples, ToolRunLogs, snapshots, and artifacts must not contain API keys, tokens, or secrets.

# 13. Rejected Alternatives

- Trust `Page.status` as the recovery source of truth. Rejected because HLD/GOAL explicitly require recovery to inspect tasks, attempts, artifacts, issues, decisions, and active pointers.
- Always rerun from the last incomplete summary stage. Rejected because it violates SRS idempotency and can waste OCR/LLM calls or overwrite user-selected work.
- Treat every running attempt after crash as failed. Rejected because durable result/artifact evidence may prove success and should be reused.
- Treat every running attempt after crash as succeeded if an output file exists. Rejected because files alone do not prove active pointer acceptance, quality checks, or dependency compatibility.
- Use active flags on result rows to avoid duplicate active outputs. Rejected by data-model final decision; active pointers are the only P0 active source.
- Let ArtifactService decide workflow rebuild/block. Rejected because ArtifactService owns file lifecycle, while WorkflowLoopEngine owns workflow decisions.
- Let QualityCheckService advance states after finding missing artifacts or quality problems. Rejected because QualityCheckService classifies issues only.
- Store provider payloads or secrets in recovery examples/logs. Rejected by security requirements.
- Add a distributed queue or generic BPM workflow engine for MVP recovery. Rejected as overengineering for the single-Page in-process TaskRunner scope.

# 14. Validation Against HARNESS Scenarios

- H01 Single Page happy path: PASS. Reuse rules preserve completed active pointers/artifacts and do not disturb normal completion.
- F01 OCR fails once then succeeds by retry: PASS. Failed attempt persists; successful retry becomes active only after decision; recovery reuses the successful active OCR if hashes match.
- F02 Translation invalid JSON then retry succeeds: PASS. Invalid attempt remains failed; successful TranslationResults are reused on rerun by source/context/glossary/config hashes.
- F03 Page-level translation partial output: PASS. Valid block results can remain; missing/invalid blocks keep issues and drive retry/warn/pause/block by profile.
- F04 Provider refusal: PASS. Refusal is `refused` attempt plus issue/decision, not crash; recovery follows profile policy.
- F05 Cleaning skips complex background: PASS. Skipped/warning state remains auditable and can produce warning readiness if profile permits.
- F06 Typesetting overflow: PASS. Preview artifact may be retained, but export-effectiveness depends on issue severity/profile.
- S01 OCR edit after translation exists: PASS. Recovery honors active edited OCR and downstream stale propagation; old translation is not export-effective.
- S02 Translation edit after typesetting exists: PASS. Recovery honors active edited translation and marks/requires typesetting regeneration.
- R01 Crash after OCR before translation: PASS. Stale task becomes interrupted/recovering; OCR active pointer is reused; translation resumes next.
- R02 Crash during provider call: PASS. Running attempt becomes abandoned unless durable evidence proves success/refusal/failure; next decision is retry/reuse/block per evidence and profile.
- R03 Missing artifact during recovery: PASS. ArtifactService marks missing; WorkflowLoopEngine decides rebuild/retry/warn/block; original image is untouched.
- E01 Normal export with unresolved blocking issue: PASS. Recovery does not bypass export gate; normal export is rejected.
- E02 Warning export allowed by profile: PASS. Warning export depends on ProcessingProfileSnapshot and keeps issues auditable.
- E03 Warning export not allowed by profile: PASS. Export is blocked/rejected with a profile-based decision.
- T01 Pause then resume: PASS. Recovery preserves completed results and keeps paused task from auto-running until resume.
- T02 Cancel then new task: PASS. Cancelled task does not auto-resume; a new task can reuse valid durable outputs by hashes.
- I01 Re-run completed Page without input changes: PASS. Existing active results/artifacts are reused and duplicate active results are avoided.
- I02 Re-run after OCR edit: PASS. Edited OCR remains active; stale downstream outputs are regenerated or kept non-export-effective until fixed.

# 15. Risks

- Exact retry-budget arithmetic for `abandoned_after_crash` is not fully specified. If counted too aggressively, users may be blocked after a crash; if not counted, repeated crashes may loop.
- Replaying acceptance from retained provider output can become complex. MVP may need to prefer retry unless result rows and active pointers already committed.
- Missing artifact rebuildability depends on later ArtifactService design details such as directory layout, retained masks, and deterministic config hashes.
- Hash definitions must be stable. If config/context hashes are inconsistent across versions, recovery may either over-reuse stale results or rerun too much.
- Concurrent user edits during recovery could race with pointer repair unless repository transaction rules are strict.
- Batch-scale recovery is deferred. The same model should extend, but MVP validation is single-Page.

# 16. Open Questions

1. Does `abandoned_after_crash` consume retry budget, or is it tracked separately from provider/tool failures?
2. What exact heartbeat staleness threshold should mark a running task interrupted in MVP?
3. Should recovery auto-resume by default after crash, or leave tasks paused until the user reopens/chooses resume?
4. Which stages are considered deterministic/rebuildable enough for automatic rebuild when artifacts are missing?
5. Can recovery parse retained raw provider output into result rows, or should MVP only reuse already committed result rows and retry otherwise?
6. What exact enum spellings should be used for repaired stage statuses such as completed/done/stale/blocked?
7. Should task-level `idempotency_key` suppress only simultaneously active duplicate tasks, or also historical duplicate reruns?
8. Should missing non-active successful payload artifacts create user-visible QualityIssues or only maintenance/audit records?
