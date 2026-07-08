## 1. Scope

This proposal defines the MVP execution contract for how `QualityCheckService` classifies quality issues and feeds `WorkflowLoopEngine` without taking over workflow decisions.

In scope:

- `discovered_stage` and `root_stage` assignment.
- `suggested_action` meaning and limits.
- Quality check input/output shape for `WorkflowLoopEngine`.
- Classification of invalid JSON, partial translation, provider refusal, cleaning skip, and typesetting overflow.
- Recovery/audit implications for `QualityIssue`, `WorkflowAttempt`, `ToolRunLog`, artifacts, and decisions.

Out of scope:

- Full issue taxonomy.
- SQL DDL, ORM, migrations, API routes, UI, real provider integrations, and real prompts.
- Retry budget arithmetic and final workflow state transitions, which remain owned by `WorkflowLoopEngine`.

## 2. Role Bias

Bias: maximize decision traceability and keep `QualityCheckService` as a classifier, not a workflow controller.

Design stance:

- Quality checks produce issue evidence, severity, blocking flags, attribution, and non-binding remediation hints.
- Workflow decisions remain separate, persisted as `WorkflowDecision`.
- The same issue evidence must explain retry, fallback, pause, warning, block, recovery, and export gate behavior after restart.

## 3. Assumptions

| Assumption | Rationale |
| --- | --- |
| `docs/HLD.md` is the current HLD baseline. | It explicitly syncs data-model decisions and architecture validation; no blocking conflict with source documents was found for this proposal. |
| Canonical workflow stages are `import`, `detection`, `ocr`, `translation`, `translation_check`, `cleaning`, `typesetting`, `export_check`. | From workflow-state final vocabulary. |
| `QualityIssue` fields from the data-model baseline are available conceptually. | This proposal does not create DDL; it uses existing field concepts. |
| `QualityCheckService` may receive quality-strictness policy from `ProcessingProfileSnapshot`. | Severity/blocking can vary by profile, but retry/fallback/skip/pause/block policy must remain outside quality classification. |
| StageExecutor or provider contract validation may normalize invalid provider output before quality classification. | Invalid JSON still becomes quality/workflow evidence, not a provider-owned decision. |

## 4. Proposed Contract

### Decisions

| Decision | Contract | Rationale |
| --- | --- | --- |
| D1 | `discovered_stage` is the stage whose output, error, artifact, or dependency is being checked. | Keeps "where detected" stable and replayable. |
| D2 | `root_stage` is the earliest probable cause stage/domain supported by current evidence. If uncertain, set it equal to `discovered_stage`. | Avoids over-attribution while preserving upstream repair signals. |
| D3 | `suggested_action` is a non-binding remediation hint, not a `WorkflowDecision`. | Prevents QualityCheckService from choosing retry/fallback/skip/warning/block. |
| D4 | QualityCheckService returns a quality report containing issue records/drafts plus summary facts. | WorkflowLoopEngine gets enough evidence without delegating decisions. |
| D5 | Provider refusal is classified as quality/workflow evidence with `root_stage = provider_policy`. | Refusal is first-class and must not collapse into generic failure or evasion retries. |
| D6 | Partial outputs are classifiable as `partial`, preserving valid result candidates while flagging missing/invalid targets. | Supports page-level translation without losing successful TextBlock results. |

### Input To QualityCheckService

| Input group | Minimal content |
| --- | --- |
| Check context | `stage`, `target_type`, `target_id`, common `project_id`/`batch_id`/`page_id`/`text_block_id`, `profile_snapshot_id`, quality strictness. |
| Attempt evidence | `workflow_attempt_id`, attempt status, attempt stage, input/config/context hashes, provider/tool/model metadata. |
| Tool evidence | `tool_run_id`, standardized provider error/output status, `error_code`, `error_class`, `is_provider_refusal`, sanitized message. |
| Candidate outputs | Candidate result ids or result drafts, candidate artifact ids or registration results, output integrity facts. |
| Dependency state | Active pointers, dependency hashes, artifact storage states, prior open/stale issues relevant to the target. |

### Output To WorkflowLoopEngine

QualityCheckService returns a `QualityCheckReport` conceptually shaped as:

| Field | Meaning |
| --- | --- |
| `stage` | Stage checked. |
| `target` | Page/TextBlock/Batch/artifact target scope. |
| `output_integrity` | `complete`, `partial`, `empty`, `invalid`, `refused`, `skipped`, `missing_artifact`, or `usable_with_warning`. |
| `issues` | Zero or more `QualityIssue` records/drafts with classification and provenance. |
| `summary` | Counts by severity, `has_blocking_issue`, `max_severity`, and issue ids/dedupe keys. |
| `classification_version` | Stable checker/taxonomy version for audit and FakeQuality repeatability. |

WorkflowLoopEngine consumes this report with current state, profile policy, retry budgets, attempt history, provider availability, and artifact state to create a `WorkflowDecision`.

## 5. Minimal Vocabulary / Fields

### Attribution Fields

| Field | Rule |
| --- | --- |
| `discovered_stage` | Always one canonical workflow stage. It is the stage under check, not necessarily the cause. |
| `root_stage` | Canonical workflow stage when the cause is a workflow stage; otherwise a minimal root domain such as `provider_policy`, `config`, or `filesystem_artifact`. |
| `issue_type` | Stable quality category, for example `translation_invalid_json`, `translation_missing_textblock`, `provider_refusal`, `cleaning_complex_background`, `typeset_overflow`. |
| `error_code` | Stage/provider-specific code when available; may equal `issue_type` for MVP. |
| `severity` | `info`, `warning`, `error`, `blocking`. |
| `is_blocking` | Whether the current target/output is not export-effective until fixed, superseded, accepted, or policy permits warning readiness. |
| `suggested_action` | Non-binding remediation hint. |
| `status` | `open`, `resolved`, `accepted_warning`, `stale`, `superseded`. |

### Suggested Action Values

| Value | Meaning | Not allowed to mean |
| --- | --- | --- |
| `retry_candidate` | Retrying the same stage may repair this class of issue. | Does not consume budget or order retry. |
| `fallback_candidate` | Another configured provider/tool may repair this issue. | Does not select provider. |
| `manual_ocr_needed` | User text input/review is likely useful. | Does not pause task. |
| `manual_translation_needed` | User translation/edit is likely useful. | Does not skip or block automatically. |
| `shorten_translation` | Translation length likely causes fit/readability issue. | Does not order upstream retry. |
| `review_cleaning_skip` | User should inspect skipped/complex cleaning area. | Does not mark skip accepted. |
| `adjust_layout_or_translation` | Layout or text length needs correction. | Does not choose manual layout vs retry. |
| `restore_or_rebuild_artifact` | Missing artifact evidence needs repair. | Does not trigger rebuild. |
| `configure_provider` | Missing/unavailable configuration likely blocks progress. | Does not mutate config. |
| `review_warning` | Output may be usable with visible warning. | Does not allow export. |

## 6. Normal Path

| Step | QualityCheckService behavior | WorkflowLoopEngine input |
| --- | --- | --- |
| Stage output is structurally valid. | Checks target-specific integrity and quality rules. | `output_integrity = complete`; zero or non-blocking issues. |
| No issues found. | Returns empty issue list and summary `has_blocking_issue = false`. | Engine may decide `continue` or `finish_ready_for_export` based on state/profile. |
| Warning issue found. | Creates open warning issue with target, attribution, message key, suggested action, and evidence refs. | Engine decides `mark_warning`, continue, pause, or block based on profile and stage. |
| Result candidates exist. | Does not update active pointers. | Engine decides whether accepted results become active in the same transaction as decision/status updates. |

Example: translation returns valid entries for every required TextBlock and TranslationCheck finds no empty, untranslated, refusal, glossary, or length issue. Quality report has `output_integrity = complete`, no issues, and WorkflowLoopEngine can decide `continue` to cleaning.

## 7. Failure / Edge Path

| Edge case | Classification |
| --- | --- |
| Invalid translation JSON | `discovered_stage = translation`; `root_stage = translation`; `issue_type = translation_invalid_json`; `error_code = translation_invalid_json` or provider `invalid_output`; target is Page for page-level response; default `severity = error`, `is_blocking = true`; `suggested_action = retry_candidate` or `fallback_candidate`; retained raw response artifact may be evidence. |
| Partial page translation | `discovered_stage = translation_check` when valid JSON omits required blocks; `root_stage = translation`; issue per missing/invalid TextBlock with `issue_type = translation_missing_textblock` or `translation_partial_output`; valid block result candidates remain usable evidence; default missing required block is blocking unless policy/user later accepts skip/warning. |
| Provider refusal in translation | `discovered_stage = translation`; `root_stage = provider_policy`; `issue_type = provider_refusal` or `translation_provider_refused`; preserve stage-specific `error_code` such as `translation_provider_refused` or `translation_nsfw_policy_refused`; default blocking while required translation is absent; `suggested_action = fallback_candidate` or `manual_translation_needed`; never suggest bypass/evasion. |
| Cleaning skip for complex background | `discovered_stage = cleaning`; `root_stage = cleaning` unless evidence points to bad detection/mask; `issue_type = cleaning_complex_background`; target TextBlock or Page region; default `severity = warning`, `is_blocking = false` unless strict profile makes it blocking; `suggested_action = review_cleaning_skip`; Page cannot become pure `ready_for_export` while skip remains. |
| Typesetting overflow | `discovered_stage = typesetting`; default `root_stage = typesetting`; use `root_stage = translation` when evidence shows excessive translation length caused overflow; `issue_type = typeset_overflow`; target TextBlock, optionally Page summary; preview artifact can be evidence; default warning for inspectable preview, blocking if clipped/unreadable or strict profile; `suggested_action = shorten_translation` or `adjust_layout_or_translation`. |

Boundary note: a blocking issue can still be retryable. `is_blocking = true` means the current target/output is not export-effective now; it does not mean the task must immediately choose `block`.

## 8. Boundary Rules

| Concern | QualityCheckService owns | WorkflowLoopEngine owns |
| --- | --- | --- |
| Issue detection | Detect invalid, missing, refused, skipped, overflow, stale, or low-quality evidence. | Decide what to do after classification. |
| Attribution | Assign `discovered_stage`, `root_stage`, issue type, severity, blocking flag, message key, and suggested action. | Decide retry/fallback/upstream retry/skip/warning/pause/block/finish. |
| Suggested action | Provide non-binding remediation hint. | Convert evidence plus policy/budget/history into a persisted `WorkflowDecision`. |
| Provider refusal | Classify refusal safely and preserve sanitized evidence. | Choose allowed fallback, manual path, warning, skip, pause, or block. |
| Results | Assess candidate result quality. | Accept/reject result candidates, update active pointers, and mutate stage statuses. |
| Artifacts | Classify missing/hash-invalid/unsafe artifact evidence. | Decide rebuild, retry, warning, pause, or block. |

QualityCheckService must never:

- Decide `continue`, `retry_same_stage`, `fallback_provider`, `retry_upstream_stage`, `skip_target`, `mark_warning`, `pause_for_user`, `block`, or finish readiness.
- Consume retry or fallback budget.
- Select providers, alter prompts, or attempt provider-policy evasion.
- Update ProcessingTask/Page/TextBlock workflow state.
- Update active OCR, translation, cleaned, or typeset pointers.
- Register, clean, promote, or delete official artifacts.
- Access SQLite except through Repository/DAO if the implementation persists issues inside the service boundary.
- Log secrets or include raw API keys/tokens in issues, logs, or artifacts.

## 9. FakeProvider or FakeQuality Implications

FakeProvider modes should return deterministic evidence that exercises classification without real OCR, LLM, cleaning, or typesetting tools.

| Fake mode | Required evidence for quality contract |
| --- | --- |
| `translation_invalid_json` | Raw invalid payload reference, standardized `invalid_output`/`translation_invalid_json` error, no accepted TranslationResults. |
| `translation_partial_output` | Valid block outputs for a subset, expected block id list, omitted block ids, shared page attempt id. |
| `provider_refusal` | `is_provider_refusal = true`, sanitized refusal code/message, provider/model metadata, no bypass hint. |
| `cleaning_complex_background` | Region/block id, skip reason, optional preview/base artifact evidence. |
| `typeset_overflow` | Overflow flag, affected TextBlock id, attempted preview artifact, fit metrics if available. |
| `missing_artifact` | Registered artifact id whose file/hash check fails through ArtifactService evidence. |

FakeQuality should be deterministic by `classification_version` and fixture input. It may emit predefined QualityIssues, but it must not emit WorkflowDecisions or mutate active pointers.

## 10. Recovery / Audit Impact

| Audit need | Contract impact |
| --- | --- |
| Explain a decision after restart. | Every issue links to attempt/tool/artifact/result evidence where available. |
| Dedupe on rerun. | Issue dedupe key should include target, issue type, discovered/root stage, input/config/context hash, and applies-to result/artifact id when relevant. |
| Mark obsolete issues. | When active inputs change, old issues become `stale` or `superseded`, not deleted. |
| Provider refusal recovery. | ToolRunLog/WorkflowAttempt refusal evidence can recreate or verify refusal issue; WorkflowDecision still records chosen path. |
| Partial translation recovery. | Valid block results remain traceable under one page attempt; missing-block issues explain why Page did not become pure ready. |
| Export gate. | Normal export/readiness queries open blocking issues in scope; warning readiness also checks warning/skip policy in `ProcessingProfileSnapshot`. |

Recovery must not infer success from a raw provider payload alone. Retained raw output can be replayed only through the normal validation, artifact registration, quality classification, and workflow acceptance path.

## 11. HARNESS Scenario Coverage

| Scenario | Coverage by this proposal |
| --- | --- |
| P03 / Q04 / F04 Provider refusal | First-class `provider_refusal`, `root_stage = provider_policy`, sanitized evidence, no bypass/evasion suggestion; engine receives issue evidence for fallback/manual/warn/skip/block. |
| P04 / Q02 / F03 Invalid structured output | Invalid JSON classified as translation-stage invalid output with raw evidence and blocking current output; provider does not create issue or decide retry. |
| P05 / Q03 Partial translation | Valid block outputs can remain candidates/evidence; missing blocks get TextBlock issues; engine decides retry/warning/pause/block. |
| Q01 OCR empty result | Same attribution rules apply: discovered `ocr`, root `ocr`, issue `ocr_no_text`, suggested manual OCR/retry candidate; engine decides path. |
| Q05 / F05 Cleaning complex background | Warning issue by default, cleaning root, visible skip; pure ready is prevented by export_check rules. |
| Q06 / F06 Typesetting overflow | Overflow issue records preview evidence and root attribution; suggested shorten/layout hint remains non-binding. |
| S02 Provider fails before artifact | Quality can classify standardized error evidence; no result/artifact acceptance is implied. |
| S03 Artifact registration fails | Artifact evidence classified as missing/registration failure; provider output remains non-official. |
| S04 Blocking issue | Quality returns blocking issue; engine decides retry/fallback/pause/block and withholds active/export-effective acceptance. |
| S05 Warning issue | Quality returns warning issue; engine decides warning readiness according to profile. |

Validation status: proposal-level coverage only. Final synthesis must replay HARNESS scenarios with the chosen provider, artifact, quality, and StageExecutor contracts.

## 12. Rejected Alternatives

| Alternative | Rejection rationale |
| --- | --- |
| QualityCheckService returns `WorkflowDecision`. | Violates WorkflowLoopEngine ownership and makes retry/fallback/block behavior less auditable. |
| `root_stage` always equals `discovered_stage`. | Hides upstream causes such as translation length causing typesetting overflow or provider-policy refusal. |
| `suggested_action` uses workflow decision names directly. | Encourages callers to execute hints as decisions and bypass budget/profile checks. |
| Provider Adapter creates QualityIssue for invalid output/refusal. | Violates provider boundary and couples tools to workflow persistence. |
| Invalid JSON is only a provider error, not a quality issue. | Loses export/recovery/audit visibility and makes retry/block decisions harder to explain. |
| Cleaning skips and overflow are treated as success without issues. | Would allow hidden incomplete output and pure ready/export states that contradict SRS/HLD. |
| QualityCheckService updates active pointers when output passes. | Splits acceptance state across services and risks active pointer/status drift. |

## 13. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Root attribution overconfidence. | Engine may retry wrong stage if final design treats root as command. | If uncertain, set root to discovered stage; keep suggested action non-binding; engine must validate budgets and evidence. |
| Blocking flag confused with workflow `block`. | Retryable issues could prematurely stop automation. | Define `is_blocking` as export-effective gate only; WorkflowDecision remains separate. |
| Profile-specific severity creep. | QualityCheckService could absorb workflow policy. | Pass only quality strictness/severity overrides to quality checks, not retry/fallback/skip budgets. |
| Partial translation acceptance ambiguity. | Valid results might become active before missing blocks are handled. | Engine must accept active pointer updates atomically with decision/status updates after reading quality report. |
| Provider refusal mishandled as evasion retry. | Policy/safety boundary violation. | Refusal issue uses `root_stage = provider_policy`; same-provider retry is not a quality suggestion. |
| Too many issue types. | MVP implementation slows down. | Keep only P0 issue types needed by FakeProvider/HARNESS; defer full catalog. |

## 14. Open Questions

| Question | Why it matters |
| --- | --- |
| Should final `root_stage` vocabulary allow non-stage domains beyond `provider_policy`, such as `config` and `filesystem_artifact`? | Data model already uses `provider_policy`; artifact/config failures need equally traceable roots. |
| Should `classification_version` be persisted on each QualityIssue or only included in quality report/debug artifacts? | Persisting helps recovery and FakeQuality reproducibility but adds schema surface. |
| Should `is_blocking` be computed entirely by QualityCheckService or split into quality-blocking plus export-policy blocking? | Cleaning skip and overflow may vary by profile; final design must avoid policy leakage. |
| Should partial translation create one Page issue plus TextBlock issues, or only TextBlock issues with Page summary derived? | Affects UI aggregation, dedupe, and WorkflowDecisionIssue links. |
| What exact default severity should `typeset_overflow` use for balanced profile when a preview artifact exists but text is clipped? | SRS allows warning paths, but unreadable output may need blocking by default. |
