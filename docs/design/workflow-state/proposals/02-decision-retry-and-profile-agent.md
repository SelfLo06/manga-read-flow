# 1. Scope

This proposal covers the decision layer of the MVP single-Page Workflow Loop:

- `WorkflowDecision` vocabulary.
- Retry budget semantics.
- Fallback provider semantics.
- Warning, blocking, skip, and pause-for-user decisions.
- Minimal `ProcessingProfileSnapshot` policy fields needed by `WorkflowLoopEngine`.
- Loop termination rules that prevent infinite automatic processing.

It does not design full profile management, Provider Adapter DTOs, SQL DDL, ORM mappings, API routes, UI flows, prompt templates, or full QualityIssue taxonomy.

# 2. Role Bias

This proposal is intentionally conservative. It favors explicit, auditable workflow decisions over hidden heuristics. When a result cannot be safely made export-effective, the workflow should either retry within a finite budget, use an allowed fallback, skip a limited target with a visible warning, pause for user action, or block.

The bias is toward:

- bounded automation;
- explainable recovery;
- preserving user-visible partial progress;
- avoiding provider-policy bypass behavior;
- keeping `ProcessingProfileSnapshot` small enough for MVP.

# 3. Assumptions

- `WorkflowLoopEngine` owns retry, fallback, skip, warning, pause, and block decisions.
- `QualityCheckService` creates/classifies `QualityIssue` records and root-stage attribution, but does not advance workflow state.
- Provider Adapters return structured output or standardized errors only. They do not persist, register official artifacts, retry, fallback, skip, block, or create issues.
- `ArtifactService` owns official artifact lifecycle.
- Repository / DAO owns SQLite access.
- Active pointers remain the P0 source of truth for current OCR, translation, cleaned image, and typeset image.
- Provider refusal is a first-class workflow path, not a crash.
- Normal export blocks unresolved open blocking issues.
- Warning export follows the immutable `ProcessingProfileSnapshot`, not the mutable current profile template.
- The current `docs/HLD.md` baseline clarifies data-model alignment while preserving the same architecture direction.

# 4. Proposed Model

After every bounded stage attempt, the loop evaluates:

1. stage and target;
2. attempt status and standardized provider/tool error;
3. active pointer and artifact state;
4. open `QualityIssue` records for the target/scope;
5. dependency hashes and stale flags;
6. retry and fallback history for the same stage/target/input key;
7. `ProcessingProfileSnapshot` policy.

The engine then persists one `WorkflowDecision` before advancing, retrying, falling back, skipping, warning, pausing, blocking, or finishing export readiness.

Decision selection should be deterministic for the same persisted state. The engine should not make a hidden in-memory decision that is required for recovery.

Recommended priority order:

1. Honor cancel request.
2. Honor pause request at the nearest safe boundary.
3. Reuse valid cached/export-effective output when hashes and artifacts match.
4. Continue when the stage output is complete and no open issue blocks the next stage.
5. Retry if the issue/error is retryable and budget remains.
6. Fallback if retry is not useful or budget is exhausted and an allowed fallback is available.
7. Retry an upstream stage only when the issue root cause points upstream and the upstream budget remains.
8. Skip a limited target only when skip is allowed by scope and profile/user action.
9. Mark warning when the issue is non-blocking or downgraded by profile and output is still usable.
10. Pause for user action when automation cannot continue but user action can plausibly resolve the issue and the profile requests pause.
11. Block when no allowed automatic or user-paused path remains, or export safety requires rejection.

# 5. State Vocabulary or Decision Vocabulary

Use the data-model baseline decision vocabulary with two additions already listed in the data-model final design:

| Decision type | Meaning | Retry budget impact |
| --- | --- | --- |
| `continue` | Current stage accepted; advance to the next required stage. | Does not consume retry budget. |
| `reuse_cached_result` | Existing result/artifact is valid for current input/config/context. | Does not consume retry budget. |
| `retry_same_stage` | Run the same stage/target again with the same provider class/config family. | Consumes that stage/target retry budget. |
| `fallback_provider` | Switch to an allowed fallback provider or implementation for the same stage. | Consumes fallback provider allowance, not same-provider retry budget. The fallback attempt may later consume its own retry budget. |
| `retry_upstream_stage` | Re-run an upstream stage to repair a downstream issue rooted upstream. | Consumes the upstream stage budget for that target/input key. |
| `skip_target` | Skip a TextBlock or stage target and keep the workflow moving with an issue. | Does not consume retry budget. Creates or links warning/blocking issue. |
| `mark_warning` | Accept usable output with an unresolved non-blocking issue. | Does not consume retry budget. |
| `pause_for_user` | Stop automatic progress at a safe boundary for user/config/manual input. | Does not consume retry budget. |
| `block` | Stop because normal processing/export cannot safely continue. | Does not consume retry budget. |
| `finish_ready_for_export` | Page has export-effective output and no open blocking or warning issue in scope. | Does not consume retry budget. |
| `finish_ready_for_export_with_warnings` | Page has export-effective output, no open blockers, and warning export policy permits warnings. | Does not consume retry budget. |
| `cancel` | Stop because user cancelled the task. | Does not consume retry budget. |

The exact enum spellings can remain open until final synthesis, but the semantics above should be stable.

# 6. Transition or Decision Rules

## Which decisions consume retry budget?

Only decisions that authorize another automatic attempt consume retry budget:

- `retry_same_stage` consumes the retry budget for the same stage, target, provider/config family, and input/context key.
- `retry_upstream_stage` consumes the retry budget for the upstream stage it schedules.

`fallback_provider` consumes fallback allowance, not same-provider retry budget. A later retry of the fallback provider consumes the fallback attempt's stage budget.

`continue`, `reuse_cached_result`, `skip_target`, `mark_warning`, `pause_for_user`, `block`, finish decisions, and `cancel` do not consume retry budget.

Provider refusals and failed attempts are persisted as attempts. The budget is decremented when the engine decides to perform another automatic attempt, not merely because a failed attempt exists. This keeps the audit trail clear: the decision explains why another attempt was allowed.

## When is retry allowed?

`retry_same_stage` is allowed only when all are true:

- The stage has a retryable error or issue, such as timeout, transient provider unavailable, invalid JSON, low confidence, recoverable file IO error, or repairable quality issue.
- The same stage/target/input key has retry budget remaining in the active snapshot.
- The input/config/context key is still current and not stale.
- The target is not cancelled, deleted, or explicitly skipped.
- The retry does not attempt to bypass a provider policy refusal.
- The previous attempt produced no accepted export-effective output for that same key.

Retry is not allowed when:

- the issue is a policy/provider refusal against the same provider and retry would be policy evasion;
- the root cause is missing user configuration or missing API key and no config change has happened;
- a required original artifact is missing and cannot be rebuilt;
- the active result is user-locked and the retry would replace it without explicit user action;
- the budget is exhausted.

`retry_upstream_stage` is allowed only when:

- a downstream issue has `root_stage` pointing to an upstream stage;
- rerunning that upstream stage can plausibly repair the downstream issue;
- the upstream input key can be recomputed safely;
- the upstream stage budget remains;
- stale propagation will mark downstream outputs non-export-effective until regenerated.

Examples:

- Invalid translation JSON: `retry_same_stage` for translation.
- Typesetting overflow caused by long translation: `retry_upstream_stage` to translation shortening, if the profile has shortening budget.
- Missing cleaned artifact: rebuild cleaning if the original/base artifact and mask are present; otherwise block or pause.

## When is fallback allowed?

`fallback_provider` is allowed only when all are true:

- The `ProcessingProfileSnapshot` allows fallback for the stage.
- An enabled fallback provider/config reference exists for the stage.
- The fallback has the required capability for the same input and target language.
- The current error or issue is fallback-eligible, such as provider unavailable, timeout, invalid output, provider refusal, dependency missing, or quality failure.
- The fallback does not try to bypass third-party policy restrictions. For provider refusal, fallback means using a separately configured allowed provider such as local translation, or pausing for manual translation. It must not mutate prompts to evade the refusing provider.
- The same fallback provider has not already failed for the same stage/target/input key without a state-changing reason to try again.

Fallback is not required for MVP automatic behavior in every stage. It is enough that the decision model can represent it and that the snapshot can say whether automatic fallback is allowed.

## When is skip allowed?

`skip_target` is allowed for limited targets where SRS/HLD permit partial output:

- complex TextBlock detection region;
- OCR no-text region when user/profile accepts skip;
- cleaning for complex background;
- typesetting of a skipped TextBlock where original content remains visible;
- a specific TextBlock manually skipped by the user.

Skip is allowed only when:

- the target is a TextBlock or stage-level target that can be omitted without overwriting original content;
- the profile enables automatic skip for that issue class, or the user explicitly requested skip;
- the skip creates or links a visible `QualityIssue`;
- page state becomes warning-bearing, not pure `ready_for_export`;
- original image/artifacts are preserved.

Skip is not allowed when:

- it would hide an unresolved blocking safety/policy issue;
- it would make the Page appear fully translated without warning;
- the target is a required whole-Page output and no usable typeset/export artifact can be produced;
- the source document requires user/manual handling instead.

## When does warning export become possible?

Warning export becomes possible when:

- the Page has export-effective active output, normally an active typeset artifact;
- all required dependencies are fresh enough for export;
- there are no open blocking `QualityIssue` rows in export scope;
- remaining open issues are warnings or accepted warnings;
- `ProcessingProfileSnapshot.allow_warning_export` is true for the task/export snapshot;
- skipped blocks or stage skips are represented in issue/export metadata.

If warning export is not allowed by the snapshot, the Page may still show preview output, but export precheck must reject or the workflow must remain blocked/reviewing until warnings are fixed or accepted according to the final UI policy.

## When must the workflow block?

The workflow must choose `block` when any of the following apply:

- An unresolved open blocking `QualityIssue` remains and no retry, fallback, skip, or user-pause path is allowed.
- Retry/fallback budgets are exhausted and the remaining issue is blocking.
- A required artifact is missing and cannot be rebuilt from preserved inputs.
- Provider refusal affects required output and there is no allowed fallback, manual translation path, skip path, or profile-driven warning path.
- API key/provider config is required for the selected provider and no fallback or pause-for-config path is available.
- The output would depend on stale OCR/translation/cleaning/typesetting state.
- Export precheck finds open blocking issues in scope.
- The content/tool error is classified as unsupported or not processable by policy.

If the profile says to pause on blocking errors and a realistic user action exists, the engine should use `pause_for_user` first. If the user resumes without changing the blocking condition, the next decision should be `block` unless a budgeted path is newly available.

## When does the workflow pause for user action?

`pause_for_user` is appropriate when automation cannot proceed safely but user action can plausibly resolve the issue:

- missing/invalid provider configuration;
- manual OCR text needed;
- manual translation needed;
- user confirmation required to skip a target;
- user review required before warning export if final policy requires acknowledgement;
- active locked translation prevents automatic overwrite;
- profile requests pause on blocking errors.

Pause is a safe-boundary decision. It must persist task state, current stage, last attempt/decision, and visible issue guidance.

# 7. Recovery Impact

Recovery must replay decision state from durable records, not from `Page.status` alone.

During recovery:

- stale running attempts are marked `interrupted` or `abandoned_after_crash`;
- completed active OCR/translation pointers are reused if hashes match;
- valid active cleaned/typeset artifacts are reused if present and hash-compatible;
- unresolved issues are re-evaluated against current snapshot and active pointers;
- retry budget is reconstructed from persisted `WorkflowDecision` records, not in-memory counters;
- fallback visited sets are reconstructed from prior `fallback_provider` decisions for the same stage/target/input key;
- no provider call is repeated if a valid `reuse_cached_result` path exists.

Abandoned attempts should not be treated as success. Recovery may retry them only if the relevant budget remains and the input key is still current.

# 8. Stale Propagation Impact

Decision rules must respect stale propagation:

- A stale upstream dependency makes downstream output non-export-effective even if an active pointer still exists.
- `retry_same_stage` is not valid against stale input. The engine must first schedule the stage whose input changed.
- `continue` is valid only when dependency hashes match the active upstream pointers and artifacts.
- `reuse_cached_result` must verify input/config/context hashes against the current active pointers.
- `finish_ready_for_export` and `finish_ready_for_export_with_warnings` are illegal while required downstream stages are stale.

OCR edit impact:

- translation, translation check, and typesetting decisions must be recomputed;
- old translation/typesetting issues tied to old inputs become stale or superseded;
- export readiness is withdrawn until regeneration or explicit accepted warning policy applies.

Translation edit impact:

- typesetting decisions must be recomputed;
- prior typesetting overflow issues tied to the old translation become stale or superseded;
- active translation pointer changes immediately, but active typeset output is not export-effective until refreshed.

# 9. ProcessingProfileSnapshot Impact

Keep the snapshot minimal for WorkflowLoopEngine. Recommended MVP policy fields:

| Field group | Minimal content | Used for |
| --- | --- | --- |
| Identity | `snapshot_schema_version`, `settings_hash`, source profile id/version/name | Historical explainability. |
| Stage retry budgets | `detection`, `ocr`, `translation`, `translation_check`, `translation_shorten`, `cleaning`, `typesetting`, `export_rebuild` | `retry_same_stage` and `retry_upstream_stage`. |
| Fallback policy | per-stage ordered fallback provider refs or capability refs; `allow_automatic_fallback`; stage allowlist | `fallback_provider`. |
| Provider refusal policy | per-stage behavior: fallback, pause, skip if target-skippable, block | Refusal path without bypass. |
| Warning export policy | `allow_warning_export`; optional `warning_issue_allowlist` by issue class/severity | Export readiness and `finish_ready_for_export_with_warnings`. |
| Auto-skip policy | `allow_auto_skip_complex_regions`; optional stage/issue allowlist | `skip_target`. |
| Blocking/pause policy | `pause_on_blocking`; `pause_on_missing_config`; `pause_on_manual_needed` | `pause_for_user` vs `block`. |
| Quality strictness reference | compact strictness level or severity override map | Interpreting QualityIssue severity/blocking where final Quality design permits profile influence. |
| Artifact/debug retention hints | only flags that affect attempt evidence retention, not workflow correctness | Attempt artifact retention, not decision ownership. |

Do not include raw API keys, tokens, secret headers, prompt templates, full provider config bodies, or mutable profile-only fields in the snapshot.

The snapshot affects choices as follows:

- Higher retry budgets allow more automatic attempts.
- Fallback policy controls whether fallback is automatic, manual, or forbidden.
- Warning export policy decides whether warning-only output may finish/export.
- Auto-skip policy decides whether complex regions can be skipped without user confirmation.
- Pause policy decides whether blocking conditions become `pause_for_user` first or immediate `block`.
- Strictness can make a quality issue warning or blocking, but the exact QualityIssue taxonomy belongs to QualityCheckService detailed design.

# 10. Artifact / QualityIssue / Active Pointer Impact

Artifacts:

- Failed attempt payload artifacts are retained by default through `ArtifactService`.
- Successful large payload artifacts may be cleanup-eligible by retention policy, but metadata and hashes remain.
- Provider Adapter temporary files are not official artifacts.
- No image BLOBs are stored in SQLite.
- Original images are never overwritten.

QualityIssue:

- Every decision reacting to issues should link to the relevant issues through `WorkflowDecisionIssue` when implemented.
- Provider refusal creates or links a `provider_refusal` or stage-specific refusal issue.
- `skip_target` creates or links a warning issue unless the profile makes the condition blocking.
- `mark_warning` does not resolve the issue; it leaves it visible or moves it to `accepted_warning` only if user/profile policy explicitly permits that status.
- `block` leaves open blocking issues visible for export gate and recovery.

Active pointers:

- Provider results become active only after checks and a `continue`, `mark_warning`, or equivalent accepting decision.
- User edits update active pointers immediately, then mark downstream stages stale.
- Retry/fallback must not overwrite locked translations without explicit user action.
- Stale downstream active pointers may remain for UI preview, but are not export-effective.

# 11. Repository and Transaction Implications

Conceptual repository operations needed by this decision model:

- Load task with profile snapshot and current stage.
- Load stage target state, active pointers, dependency hashes, and artifact states.
- Load open issues in target/export scope.
- Count prior retry decisions by stage/target/input key.
- Load prior fallback decisions by stage/target/input key.
- Persist attempt start before external provider calls.
- Persist tool run, artifacts, attempt outcome, issues, result rows, active pointer updates, stage status updates, and workflow decision after a provider call.
- Create blocked/rejected export records during export precheck.

Transaction boundaries:

- Do not hold a database write transaction during provider calls.
- Persist `WorkflowAttempt` start before the call.
- Register official output artifacts through `ArtifactService` before result rows point to them.
- Commit result creation, issue updates, decision creation, active pointer changes, and status changes atomically when accepting stage output.
- Commit skip/warning/block decisions atomically with issue/status updates.
- Persist retry budget before/after values on `WorkflowDecision` and/or `WorkflowAttempt` so recovery can reconstruct counters.

# 12. Invariants

- Workflow decisions are append-only audit records.
- Retry loops are finite.
- Provider refusal is not retried against the same provider as a bypass strategy.
- Provider Adapter does not own persistence, artifact lifecycle, retry/fallback decisions, skip/warning/block decisions, or quality attribution.
- QualityCheckService does not advance workflow state.
- ArtifactService owns official artifact path, hash, registration, retention, and cleanup.
- Repository / DAO owns SQLite access.
- Original images are never overwritten.
- Image bytes and large payloads are never stored in SQLite.
- Active pointers are the P0 source of truth for selected OCR, translation, cleaned image, and typeset image.
- Export-effective output requires fresh dependencies and present/rebuildable artifacts.
- Normal export blocks unresolved open blocking `QualityIssue` records.
- Warning export follows the immutable `ProcessingProfileSnapshot`.
- Secrets do not appear in logs, snapshots, examples, or artifacts.

# 13. Rejected Alternatives

| Alternative | Reason rejected |
| --- | --- |
| Retry until success | Violates bounded loop requirement and can repeat provider costs/failures indefinitely. |
| Let Provider Adapter decide retry/fallback | Violates architecture boundaries and hides workflow rationale from recovery. |
| Treat provider refusal as generic failure | Loses policy semantics and risks retry behavior that looks like bypass. |
| Make fallback consume same-provider retry budget | Makes audit and tuning unclear; fallback is a distinct provider-choice decision. |
| Let warnings always export | Conflicts with profile-controlled warning export and strict profile behavior. |
| Let skipped blocks count as pure ready output | Hides incomplete processing from user/export manifest. |
| Block every warning | Too strict for MVP ordinary-reader goal and conflicts with HLD warning path. |
| Store only mutable profile id on decisions | Historical behavior would become inexplicable after profile edits. |
| Add a generic BPM/workflow engine | Overkill for MVP single-Page vertical slice. |
| Design full ProcessingProfile management here | Out of scope; this proposal only needs the snapshot fields consumed by the loop. |

# 14. Validation Against HARNESS Scenarios

| Scenario | Result | Decision-model validation |
| --- | --- | --- |
| H01 happy path | PASS | Each stage can `continue`; final decision is `finish_ready_for_export` when no blockers/warnings remain. |
| F01 OCR fails once then succeeds | PASS | Failed attempt persists; `retry_same_stage` consumes OCR budget; success can update active OCR pointer and continue. |
| F02 invalid translation JSON then retry succeeds | PASS | Invalid output is retryable; `retry_same_stage` consumes translation budget; later valid output continues. |
| F03 partial page translation | PASS | Valid block results may be accepted; missing/invalid blocks get issues; profile chooses retry, warning, pause, or block. |
| F04 provider refusal | PASS | Refusal maps to refused attempt, issue, and `fallback_provider`, `skip_target`, `mark_warning`, `pause_for_user`, or `block` without bypass. |
| F05 cleaning skips complex background | PASS | `skip_target` or `mark_warning` creates warning and can lead to warning-ready output if profile permits. |
| F06 typesetting overflow | PASS | Decision can be `retry_upstream_stage`, `mark_warning`, `pause_for_user`, or `block`; preview artifact may remain non-export-effective or warning-exportable. |
| S01 OCR edit after translation | PASS | Stale downstream states prevent `continue`/finish until translation and typesetting are regenerated or properly handled. |
| S02 translation edit after typesetting | PASS | Typesetting becomes stale; prior output is not export-effective until regenerated. |
| R01 crash after OCR before translation | PASS | Recovery can reuse active OCR pointer and continue at translation without OCR rerun. |
| R02 crash during provider call | PASS | Running attempt becomes interrupted/abandoned; retry only if budget remains and no reusable result exists. |
| R03 missing artifact during recovery | PASS | Artifact state drives rebuild/retry/warn/block decision; original image is preserved. |
| E01 normal export with unresolved blocker | PASS | Export precheck creates blocked export record and no normal output artifact. |
| E02 warning export allowed | PASS | `finish_ready_for_export_with_warnings` and export success with warnings require snapshot permission. |
| E03 warning export not allowed | PASS | Export is rejected/blocked with profile-based decision rationale. |
| T01 pause then resume | PASS | `pause_for_user` is safe-boundary and does not consume budget; resume recomputes next decision. |
| T02 cancel then new task | PASS | `cancel` terminates current task; later task may reuse valid cached results. |
| I01 rerun completed Page unchanged | PASS | `reuse_cached_result` avoids duplicate provider calls and explains reuse. |
| I02 rerun after OCR edit | PASS | Active edited OCR is preserved; stale downstream outputs cannot be treated as current export-effective output. |

# 15. Risks

- Exact retry arithmetic can become inconsistent if final synthesis does not define the key used for counting budget. Mitigation: count by stage, target, provider/config family, and input/context hash.
- Warning export may need explicit per-export user acknowledgement in addition to profile policy. This remains open in the data-model final questions.
- Quality severity/profile interaction can drift into WorkflowLoopEngine if not bounded. Mitigation: QualityCheckService owns issue classification; the loop only applies snapshot policy to decisions.
- Fallback provider order can become hidden configuration. Mitigation: snapshot stores sanitized ordered fallback refs used for the run.
- Skipping translated content can surprise users if UI/export reporting is weak. Mitigation: skipped targets must create visible issues and warning export state.
- Recovery could double-call providers if retry counters are reconstructed from attempts instead of decisions. Mitigation: reconstruct retry consumption from persisted retry decisions.

# 16. Open Questions

1. Exact enum spellings for decision types and reason codes remain for final workflow-state synthesis.
2. Should retry budget be decremented at retry decision creation only, or also mirrored on the next attempt as `retry_budget_before/after`? This proposal recommends both for audit clarity.
3. Should warning export require per-export user acknowledgement in addition to `ProcessingProfileSnapshot.allow_warning_export`?
4. Which specific issue classes are eligible for automatic skip in the default balanced profile?
5. Should provider refusal ever allow automatic warning for translation, or should translation refusal default to fallback/pause/block unless the affected TextBlock is explicitly skipped?
6. What hard global loop ceiling should protect against implementation bugs beyond per-stage retry budgets?
7. Is `export_rebuild` a real retry budget field, or should export rebuilds consume the upstream artifact-producing stage budget instead?
