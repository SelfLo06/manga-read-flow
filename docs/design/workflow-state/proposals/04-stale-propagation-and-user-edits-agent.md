# 1. Scope

This proposal covers MVP stale propagation and user-edit behavior for the single-Page workflow-state design.

It focuses on:

- OCR edit.
- Translation edit.
- Manual review state.
- Downstream stale propagation.
- `QualityIssue` stale or superseded behavior.
- Active pointer changes.
- Workflow resume after stale state.
- MVP versus P1/P2 boundaries.

It does not design implementation code, SQL DDL, ORM mappings, API routes, frontend UI, Provider Adapter contracts, prompt templates, or final workflow-state synthesis files.

No blocking source-document conflict was found for this proposal. `docs/HLD.md` is the accepted strengthened baseline; this proposal follows it where it adds active pointer, profile snapshot, export gate, provider refusal, and recovery decisions.

# 2. Role Bias

This agent is biased toward preserving user edits, auditability, and export safety over automatic cleanup or silent replacement.

The model treats stale propagation as dependency invalidation, not deletion:

- Old OCR, translation, cleaned image, typeset image, attempts, decisions, artifacts, and issues remain explainable.
- Active pointers identify the currently selected user-facing result.
- Stale stage status and dependency hashes determine whether a selected result is export-effective.
- Rework should resume from the earliest stale downstream stage rather than rerunning completed upstream work without cause.

# 3. Assumptions

- MVP scope is single Project, single Page workflow, with Page-level translation and TextBlock-level OCR/translation results.
- `TextBlock.active_ocr_result_id` and `TextBlock.active_translation_result_id` are the only P0 active OCR/translation source of truth.
- `Page.active_cleaned_artifact_id` and `Page.active_typeset_artifact_id` are the only P0 active page image output pointers.
- OCR and translation results are immutable. User edits create new result versions.
- Stale downstream state does not clear active pointers, because the UI still needs prior selected data for review and comparison.
- Normal export must block unresolved open blocking `QualityIssue` rows in scope.
- Warning export must follow the effective `ProcessingProfileSnapshot`.
- `QualityCheckService` detects and classifies issues but does not advance workflow state.
- `WorkflowLoopEngine` owns decisions to continue, rerun, pause, warn, block, skip, or resume.
- `ArtifactService` owns official artifact lifecycle. Provider Adapters cannot register official artifacts.
- Repository / DAO owns SQLite access.

# 4. Proposed Model

Use a simple dependency invalidation model for MVP:

```text
OCRResult
  -> PageTranslationContext
  -> TranslationResult
  -> TranslationCheck
  -> Typeset artifact
  -> Export readiness
```

Cleaned image dependency is intentionally narrow:

- OCR edit does not make the cleaned image stale by default, because text geometry and mask are unchanged.
- Translation edit does not make the cleaned image stale.
- Typesetting becomes stale after OCR or translation edit because rendered Chinese text no longer matches the selected text inputs.
- Geometry or mask edit stale behavior is recognized from the data-model documents but is not the focus of this proposal.

State after an edit should be enough for three readers:

- UI can show the edited value, stale downstream outputs, and issues needing review.
- Workflow recovery can resume from durable pointers, statuses, attempts, decisions, artifacts, hashes, and issues.
- Export gate can reject stale or blocked output without trusting only `Page.status`.

MVP should keep stale handling explicit and local:

- OCR edit affects the edited TextBlock plus Page translation context.
- Translation edit affects the edited TextBlock's typesetting and Page stale aggregate.
- Page-level translation rework may update one or more block translations because the Page translation context has changed.
- Typesetting rework regenerates the Page typeset artifact from active cleaned image plus active translations.

# 5. State Vocabulary or Decision Vocabulary

Recommended stage status values used by this proposal:

| Vocabulary | Meaning in stale/edit flow |
| --- | --- |
| `pending` | Stage has not produced an accepted current result yet. |
| `running` | Stage is currently executing. |
| `completed` | Stage has a current accepted result whose dependencies are fresh. |
| `stale` | Stage has an existing result or pointer, but dependencies changed and it is not export-effective. |
| `needs_review` | User or workflow attention is required before treating the block/page as cleanly reviewed. |
| `skipped` | Stage or target was intentionally skipped. |
| `blocked` | Workflow cannot proceed automatically under the active profile. |
| `failed` | Latest attempt failed but may be retried or handled by decision policy. |

Fields directly involved:

| Entity | Fields |
| --- | --- |
| `TextBlock` | `active_ocr_result_id`, `active_translation_result_id`, `ocr_status`, `translation_status`, `translation_check_status`, `cleaning_status`, `typesetting_status`, `review_status`, `is_skipped`, `locked_translation_result_id` |
| `Page` | `status`, `translation_context_hash`, `translation_context_stale`, `has_stale_blocks`, `active_cleaned_artifact_id`, `active_typeset_artifact_id`, `quality_flags` |
| `OCRResult` | `parent_ocr_result_id`, `source_type`, `source_text_hash`, `is_user_edited`, dependency hashes, provenance |
| `TranslationResult` | `parent_translation_result_id`, `source_ocr_result_id`, `source_text_hash`, `translation_text_hash`, `context_hash`, `glossary_version_id`, `is_user_edited`, provenance |
| `QualityIssue` | `status`, `is_blocking`, `applies_to_result_id`, `input_hash`, `config_hash`, `superseded_by_issue_id`, scope fields |
| `WorkflowDecision` | `decision_type`, `reason_code`, `next_stage`, linked issues |

Recommended issue statuses:

| Status | Meaning |
| --- | --- |
| `open` | Still applies and counts for export gate if blocking. |
| `resolved` | Fixed by edit, rerun, user action, or explicit resolution. |
| `accepted_warning` | User/profile accepts warning for allowed warning export; remains auditable. |
| `stale` | Issue no longer applies to active inputs/results after edit or pointer change. |
| `superseded` | Replaced by a newer issue for the same target/root cause. |

# 6. Transition or Decision Rules

## OCR edit

When the user edits OCR text for a TextBlock:

1. Create a new `OCRResult` with `source_type = user_edit`, `is_user_edited = true`, and `parent_ocr_result_id` set to the previous active OCR result when available.
2. Set `TextBlock.active_ocr_result_id` to the new OCR result.
3. Set `TextBlock.ocr_status = completed` unless the edit is empty or invalid under QualityCheck rules.
4. Set `TextBlock.translation_status = stale`.
5. Set `TextBlock.translation_check_status = stale`.
6. Set `TextBlock.typesetting_status = stale`.
7. Set `TextBlock.review_status = needs_review`.
8. Set `Page.translation_context_stale = true`.
9. Set `Page.has_stale_blocks = true`.
10. Do not clear `TextBlock.active_translation_result_id`; the prior translation remains selected for review but is not export-effective.
11. Do not clear `Page.active_typeset_artifact_id`; the prior rendered output remains previewable as stale but is not export-effective.
12. Create a `WorkflowDecision` or equivalent edit audit decision with reason such as `user_ocr_edit_marks_downstream_stale`.

Translation context impact:

- The Page translation context must be rebuilt before automated page translation rework.
- Existing TranslationResults whose `source_ocr_result_id` or `source_text_hash` no longer match active OCR are stale for export.
- If profile or user action requests single-block retranslation, the workflow may use current Page context plus the edited block as target, but the resulting `TranslationResult` must still store current context/source hashes.

## Translation edit

When the user edits translation text for a TextBlock:

1. Create a new `TranslationResult` with `source_type = user_edit`, `is_user_edited = true`, `parent_translation_result_id` set when available, and `source_ocr_result_id` / `source_text_hash` copied from the current active OCR.
2. Set `TextBlock.active_translation_result_id` to the new translation result.
3. Set `TextBlock.translation_status = completed` if the edited translation passes basic persistence validation.
4. Set `TextBlock.translation_check_status = stale` or `needs_review` until translation checks are rerun or user explicitly accepts review outcome. MVP recommendation: `stale`, with `review_status = needs_review`.
5. Set `TextBlock.typesetting_status = stale`.
6. Set `TextBlock.review_status = needs_review`.
7. Set `Page.has_stale_blocks = true`.
8. Do not set `Page.translation_context_stale = true` solely because the target translation changed; the source OCR context did not change.
9. Do not clear `Page.active_typeset_artifact_id`; prior rendered output remains stale preview, not export-effective output.
10. Create a `WorkflowDecision` or equivalent edit audit decision with reason such as `user_translation_edit_marks_typesetting_stale`.

Locked translation impact:

- If the edited translation is intended to be locked, update `TextBlock.locked_translation_result_id` only through an explicit user lock action.
- Automatic retranslation must not replace a locked translation unless the user explicitly overrides it.
- Exact lock/unlock UI and API semantics are outside this proposal and should remain an open question for later API/UI design if not already decided.

## Manual review state

- OCR edit and translation edit set `review_status = needs_review` for the edited TextBlock.
- `needs_review` is not necessarily blocking by itself; export blocking depends on open blocking `QualityIssue` rows and profile policy.
- A manual review completion action may set `review_status = completed` only after the current active OCR/translation and downstream required stages are fresh or accepted under profile.
- MVP should not require every TextBlock to be manually reviewed on the happy path.

# 7. Recovery Impact

Recovery must reconcile stale/edit state from durable records, not from `Page.status` alone.

On startup or task resume:

1. Load `ProcessingTask`, stale/running `WorkflowAttempt`, last `WorkflowDecision`, TextBlock stage statuses, active pointers, artifact storage states, QualityIssues, and dependency hashes.
2. For each TextBlock, compare active `TranslationResult.source_ocr_result_id` and `source_text_hash` with active OCR. If mismatched, keep the active translation pointer but ensure translation/check/typesetting are stale.
3. For each TextBlock, compare active translation/context hashes with the active typeset artifact provenance when available. If mismatched, keep the active typeset pointer but ensure typesetting/Page export readiness are stale.
4. If `Page.translation_context_stale = true`, rebuild context before translation rework; do not rerun OCR unless OCR status/input hashes require it.
5. If a stale running attempt exists from before an edit or crash, mark it `interrupted` or `abandoned_after_crash` according to recovery evidence and create a recovery decision before starting new work.
6. If a provider result arrives after a user edit and its input hash references old active inputs, do not auto-select it as active. Persist it as historical attempt output if valid, then mark it stale or ignored by decision.

Recovery outcome examples:

- Crash after OCR edit transaction completed: active OCR points to edited result; translation/check/typesetting remain stale; resume from translation, not OCR.
- Crash after translation edit transaction completed: active translation points to edited result; typesetting remains stale; resume from typesetting or translation check according to profile.
- Crash between new result row and active pointer update should be repaired only if repository transaction boundaries prove both were intended; otherwise leave the orphan result historical and require explicit selection or recovery decision.

# 8. Stale Propagation Impact

Downstream stale matrix:

| Trigger | Same TextBlock OCR | Translation | Translation check | Cleaning | Typesetting | Page context | Page stale aggregate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OCR edit | `completed` with new active OCR | `stale` | `stale` | unchanged | `stale` | `translation_context_stale = true` | `has_stale_blocks = true` |
| Translation edit | unchanged | `completed` with new active translation | `stale` or `needs_review` | unchanged | `stale` | unchanged | `has_stale_blocks = true` |
| Review acceptance only | unchanged | unchanged | may become `completed` | unchanged | unchanged unless rerender required | unchanged | recompute |
| Re-translation after OCR edit | unchanged | `completed` if accepted | `completed` if check passed | unchanged | remains `stale` until rerender | `translation_context_stale = false` if all active OCR covered | recompute |
| Re-typeset after edit | unchanged | unchanged | unchanged | unchanged | `completed` if accepted | unchanged | recompute |

Page `has_stale_blocks` should be recomputed or repaired from TextBlock statuses during recovery. It may be persisted for UI speed, but it must not become the sole source of truth.

Export-effective rule:

```text
selected_by_active_pointer
+ stage status fresh/accepted
+ dependency hashes match active upstream inputs
+ required artifact exists and hash-valid
+ no open blocking QualityIssue in scope
+ warning export allowed when warnings remain
= export-effective
```

# 9. ProcessingProfileSnapshot Impact

User edits themselves should not require a new `ProcessingProfileSnapshot` unless they create a new task/export or explicitly rerun workflow under a selected profile.

The snapshot affects stale recovery and rework decisions:

- Whether translation rework is automatic, pauses for user, or blocks after an OCR edit.
- Whether translation check warnings after a user translation edit can be accepted.
- Whether typesetting overflow after rerender is warning, pause, retry-upstream, or block.
- Whether warning export is allowed after unresolved warnings remain.
- Retry budgets for rework attempts created after the edit.
- Retention/debug behavior for new attempts and artifacts produced during rework.

The snapshot must not contain API keys, tokens, or raw secrets. It may contain provider/config references and sanitized identity.

MVP recommendation:

- The edit transaction records the edit and stale propagation without changing profile.
- A subsequent `ProcessingTask` for rework uses an immutable snapshot captured at task start.
- Export uses the relevant export/task snapshot, not the mutable current profile template.

# 10. Artifact / QualityIssue / Active Pointer Impact

## Active pointers

After OCR edit:

- Change `TextBlock.active_ocr_result_id` to the new OCR result.
- Do not change `TextBlock.active_translation_result_id`.
- Do not change `Page.active_cleaned_artifact_id`.
- Do not change `Page.active_typeset_artifact_id`.

After translation edit:

- Change `TextBlock.active_translation_result_id` to the new translation result.
- Do not change `TextBlock.active_ocr_result_id`.
- Do not change `Page.active_cleaned_artifact_id`.
- Do not change `Page.active_typeset_artifact_id`.

After successful re-translation:

- Change `TextBlock.active_translation_result_id` for each accepted result.
- Keep old TranslationResults as history.
- If page-level translation returns partial output, update only valid block results and leave missing/invalid blocks stale or open with issues.

After successful re-typesetting:

- Register new typeset artifact through ArtifactService.
- Update `Page.active_typeset_artifact_id` to the new artifact.
- Keep old typeset artifact according to retention policy; do not overwrite it.

## QualityIssue behavior

After OCR edit, mark as `stale` or `superseded`:

- Translation issues whose `applies_to_result_id`, `input_hash`, or `source_text_hash` points to a translation based on the previous OCR.
- Translation check issues for the old Page translation context.
- Typesetting issues whose root cause was old translation text or old translation length.
- Export blocking issues caused only by old translation/typeset outputs.

Keep `open`:

- OCR edit validation issues that apply to the new edited OCR.
- Detection/geometry issues that still apply.
- Cleaning issues that depend on geometry/mask/background and are unaffected by OCR text.
- Provider refusal records as historical issues unless they are tied only to an obsolete attempted translation and the new route no longer depends on them. Historical refusal attempts still remain auditable through ToolRunLog/WorkflowAttempt.

After translation edit, mark as `stale` or `superseded`:

- Prior translation quality issues tied to the old TranslationResult when the manual edit directly addresses them.
- Prior typesetting overflow or layout issues tied to the old translation text/hash.
- Export blocking issues caused by old typeset output.

Keep `open`:

- OCR issues still applying to active OCR.
- Provider refusal issues for unresolved blocks without active user translation.
- Cleaning issues unrelated to translation text.
- New translation review issues created by QualityCheckService for the edited translation.

Stale versus superseded rule:

- Use `stale` when the issue no longer applies because active inputs changed and no direct replacement issue exists yet.
- Use `superseded` when a newer issue records the same target/root cause under current inputs; set `superseded_by_issue_id`.

QualityCheckService can classify new issues after checks. WorkflowLoopEngine decides how those issues affect state and export readiness.

## Artifact behavior

- User OCR/translation text edits do not create image artifacts by themselves.
- Existing cleaned/typeset/export artifacts are not overwritten.
- Active stale typeset artifact may remain previewable with an explicit stale indicator.
- New official typeset/export artifacts must be created through ArtifactService.
- Normal export must not use stale active typeset output as if it were current.

# 11. Repository and Transaction Implications

The edit plus stale propagation must be atomic at repository level.

OCR edit transaction should include:

- Insert new `OCRResult`.
- Update `TextBlock.active_ocr_result_id`.
- Update TextBlock downstream statuses.
- Update Page stale fields.
- Mark affected QualityIssues `stale` or `superseded`.
- Insert a `WorkflowDecision` or audit-equivalent decision record if the final workflow design uses decisions for user actions.

Translation edit transaction should include:

- Insert new `TranslationResult`.
- Update `TextBlock.active_translation_result_id`.
- Update TextBlock downstream statuses.
- Update Page stale fields.
- Mark affected QualityIssues `stale` or `superseded`.
- Insert a `WorkflowDecision` or audit-equivalent decision record if applicable.

Rework acceptance transaction should include:

- Insert accepted result rows or artifact records already registered through ArtifactService.
- Update active pointers.
- Update stage statuses.
- Update or create QualityIssues.
- Insert WorkflowAttempt and WorkflowDecision outcome records.
- Recompute Page stale/export-readiness summary fields.

Repository methods are conceptual only in this proposal, but implementation will likely need atomic operations for:

- `apply_user_ocr_edit_and_stale_downstream`.
- `apply_user_translation_edit_and_stale_downstream`.
- `mark_issues_stale_for_result_dependencies`.
- `select_active_translation_results_after_page_attempt`.
- `replace_active_typeset_artifact_after_successful_render`.
- `recompute_page_stale_summary`.

Do not hold a database write transaction during provider calls.

# 12. Invariants

- User edits never overwrite prior OCRResult or TranslationResult rows.
- Active OCR/translation selection is stored only through TextBlock active pointers.
- Stale downstream state does not clear active pointers.
- Stale active outputs are previewable but not export-effective.
- Original images are never overwritten.
- No image BLOBs are stored in SQLite.
- Provider Adapters do not access SQLite, create QualityIssues, register official artifacts, or decide retry/fallback/skip/warning/block.
- ArtifactService owns official artifact path, hash, registration, retention, cleanup, and missing-file state.
- Repository / DAO owns SQLite access and transaction boundaries.
- QualityCheckService detects/classifies issues but does not advance workflow state.
- WorkflowLoopEngine owns decisions after edits, checks, attempts, and profile policy.
- Recovery cannot rely only on `Page.status`.
- Normal export blocks unresolved open blocking issues in scope.
- Warning export follows `ProcessingProfileSnapshot`.
- API keys, tokens, and secrets must not appear in examples, logs, snapshots, or debug artifacts.

# 13. Rejected Alternatives

| Alternative | Rejection rationale |
| --- | --- |
| Overwrite OCR/translation text in place | Violates versioning, auditability, user edit traceability, and recovery explainability. |
| Clear downstream active pointers on edit | UI loses comparison/review context, and recovery has less evidence. Stale status is safer than deletion. |
| Let latest timestamp imply active result | Conflicts with active pointer decision and locked/manual selection use cases. |
| Immediately delete old typeset artifacts after edit | Loses preview/audit value and conflicts with ArtifactService retention policy. |
| Mark the whole Page failed after one stale TextBlock | Conflicts with partial retry, review, warning export, and local rework goals. |
| Treat manual translation edit as automatically export-ready | Typesetting and export gate still need fresh rendered output and issue checks. |
| Let QualityCheckService update workflow state directly | Violates HLD boundary; it should report issues, not advance states. |
| Let Provider Adapter decide that stale output should be retried or skipped | Violates Provider Adapter boundary and makes recovery decisions opaque. |
| Add P0 GeometryRevision to solve edit propagation generally | Data-model final defers GeometryRevision to P1; P0 geometry fields plus hashes are enough. |
| Add forced export for stale output in MVP | Data-model final defers forced/incomplete export to P1; normal export must remain safe. |

# 14. Validation Against HARNESS Scenarios

| Scenario | Result | Stale/edit replay |
| --- | --- | --- |
| H01 Single Page happy path | PASS for this focus | No stale propagation occurs. Active OCR, translation, cleaned, and typeset pointers become fresh; no open blocking issue remains. |
| F02 Translation invalid JSON then retry succeeds | PASS for this focus | Failed/invalid attempt issues remain tied to old attempt; successful retry creates active TranslationResults and can supersede invalid-output issues. |
| F03 Page-level translation partial output | PASS for this focus | Valid block TranslationResults can become active; missing/invalid blocks keep translation/check stale or issue-open; Page remains not cleanly export-ready until policy decision. |
| F04 Provider refusal | PASS for this focus | Refusal issues stay auditable. If user supplies manual translation, refusal issue for that block may become stale for active export path but ToolRunLog/WorkflowAttempt remain. |
| F06 Typesetting overflow | PASS for this focus | If translation edit changes text length, old overflow issue tied to old translation hash becomes stale/superseded; rerender creates current issue if overflow remains. |
| S01 OCR edit after translation exists | PASS | New OCRResult active; translation, translation_check, and typesetting stale; Page translation context stale; Page has stale blocks; old downstream issues stale/superseded. |
| S02 Translation edit after typesetting exists | PASS | New TranslationResult active; typesetting stale; review needs_review; Page has stale blocks; prior typesetting issues tied to old translation stale/superseded. |
| R01 Crash after OCR before translation | PASS for this focus | Recovery keeps active OCR and resumes translation. If OCR was user-edited before crash, stale flags direct resume from translation without rerunning OCR. |
| R02 Crash during provider call | PASS for this focus | If provider call used old inputs and user edit happened, recovery must not select late old output as active; attempt becomes interrupted/abandoned or historical. |
| R03 Missing artifact during recovery | PASS for this focus | Missing stale active typeset artifact cannot be exported; if rebuildable from active cleaned and translation, workflow resumes typesetting. |
| E01 Normal export with unresolved blocking issue | PASS | Stale/superseded issues are ignored by blocker query, but open blocking current issues block export; stale active typeset output is not export-effective. |
| E02 Warning export allowed by profile | PASS | Open warning issues after rework may export only when ProcessingProfileSnapshot allows warning export. |
| E03 Warning export not allowed by profile | PASS | Export is rejected/blocked when warnings remain and snapshot disallows warning export. |
| T01 Pause then resume | PASS for this focus | Resume recomputes stale stages from active pointers and dependencies, preserving completed results. |
| T02 Cancel then new task | PASS for this focus | New task can reuse valid active edited OCR/translation and starts from stale downstream stages. |
| I01 Re-run completed Page without input changes | PASS for this focus | No stale flags or dependency mismatches means results/artifacts can be reused. |
| I02 Re-run after OCR edit | PASS | Edited OCR remains active; OCR is not overwritten; translation/typesetting are regenerated or remain stale; old outputs are not export-effective. |

# 15. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Active pointer/status drift | Export may use stale output or UI may show wrong readiness. | Atomic edit transactions plus recovery reconciliation from hashes, statuses, issues, and artifacts. |
| Over-marking issues stale | Real blockers could disappear from export gate. | Only stale issues tied to old result ids/hashes; keep geometry, cleaning, and current-input issues open. |
| Under-marking issues stale | User sees obsolete blockers after fixing text. | Use `applies_to_result_id`, input hashes, and superseded links for targeted updates. |
| Page-level translation context ambiguity | OCR edit in one block may affect translations for other blocks. | Mark Page context stale and rerun page translation or targeted block translation with current context. Exact breadth remains policy-driven. |
| Stale active typeset preview confusion | User may think old preview is current. | UI/API should expose stale/export-effective distinction; final UI wording is deferred. |
| Late provider result after edit | Old provider output may overwrite user edit. | Select results only when input/context hashes match current active dependencies and WorkflowLoopEngine accepts them. |
| Manual edit bypasses quality checks | Bad edited text could become active without review. | Active does not equal export-effective; mark review/check stale or needs_review and run checks before export readiness. |
| Aggregate Page stale fields drift | `has_stale_blocks` could become incorrect. | Treat aggregate fields as repairable summaries, recomputed from TextBlock statuses during recovery. |

# 16. Open Questions

1. Should user edit actions always create a `WorkflowDecision`, or should there be a separate audit event type for user actions while `WorkflowDecision` remains engine-only?
2. Exact enum spellings for `stale`, `needs_review`, `accepted_warning`, `superseded`, and related reason codes remain deferred to final workflow-state synthesis.
3. After translation edit, should `translation_check_status` be `stale` or `needs_review` in the canonical state table? This proposal recommends `stale` plus `review_status = needs_review`.
4. What is the MVP UI/API action that marks manual review complete, and does it require rerunning TranslationCheck first?
5. How broad should automatic retranslation be after one OCR edit: only the edited TextBlock, all blocks whose context hash changed, or the full Page? This proposal keeps Page context stale and leaves breadth to WorkflowLoopEngine/profile policy.
6. Should stale active typeset artifacts remain available for preview by default, or hidden unless the user opens history/debug view?
7. Whether warning export requires per-export acknowledgement in addition to `ProcessingProfileSnapshot.allow_warning_export` remains a data-model open question.
8. Exact handling of `locked_translation_result_id` after OCR edit needs later API/UI design: should a locked translation become stale, remain locked-but-stale, or require explicit unlock before retranslation?
9. Exact QualityIssue taxonomy for stale versus resolved manual-edit fixes belongs to QualityCheckService detailed design.
10. Exact repository method names, SQL constraints, and transaction implementation are deferred to persistence detailed design.
