# QualityCheckService Contract v0.1

## 1. Scope

QualityCheckService checks stage outputs, provider errors/refusals, artifact evidence, result candidates, and dependencies. It classifies issues with severity, blocking flags, discovered/root attribution, message keys, and suggested action keys.

QualityCheckService does not:

- call providers;
- register, promote, clean, or delete artifacts;
- advance workflow state;
- update active OCR, translation, cleaned, typeset, or mask pointers;
- decide retry, fallback, upstream retry, skip, warning acceptance, pause, block, cancel, or readiness;
- consume retry/fallback budgets.

## 2. MVP-0 persistence decision

For MVP-0, QualityCheckService returns issue drafts and lifecycle suggestions in a `QualityCheckReport`. WorkflowLoopEngine persists issue lifecycle updates together with WorkflowDecision and accepted result/pointer/status changes.

QualityCheckService still owns classification. Repository / DAO remains the only SQLite access path.

Later implementations may wrap issue persistence behind QualityCheckService methods only if they preserve these rules:

- no workflow state advancement;
- no active pointer mutation;
- no retry/fallback/skip/warning/block decision;
- issue persistence still uses Repository / DAO.

## 3. Input contract

QualityCheckService receives a `QualityCheckInput`.

| Input group | Minimal content |
| --- | --- |
| Check context | `stage`, `target_type`, `target_id`, project/batch/page/textblock scope ids, `profile_snapshot_id`, quality strictness reference. |
| Attempt evidence | `workflow_attempt_id`, attempt status, provider/tool/model metadata, input/config/context hashes. |
| Tool evidence | `tool_run_id`, `ProviderResult.outcome`, error kind/code, `is_provider_refusal`, sanitized message. |
| Candidate outputs | Detector candidates, OCR/Translation result drafts, cleaned/typeset artifact candidates, partial target map. |
| Artifact evidence | Registered artifact ids/metadata, registration failures, integrity reports, storage states. |
| Dependency state | Active pointers, dependency hashes, prior open/stale/superseded issues relevant to the target. |

QualityCheckService may use quality strictness/severity overrides from `ProcessingProfileSnapshot`. It must not read retry budgets or fallback policy as decision instructions.

## 4. Output contract

QualityCheckService returns a `QualityCheckReport`.

| Field | Required | Meaning |
| --- | --- | --- |
| `stage` | Yes | Stage checked. |
| `target` | Yes | Page/TextBlock/Artifact scope. |
| `output_integrity` | Yes | `complete`, `partial`, `empty`, `invalid`, `refused`, `skipped`, `missing_artifact`, or `usable_with_warning`. |
| `issue_drafts` | Yes | Zero or more issue drafts. |
| `issue_lifecycle_suggestions` | Optional | Existing issues to mark `resolved`, `stale`, or `superseded` by caller transaction. |
| `summary` | Yes | Counts by severity, `has_blocking_issue`, `max_severity`, and dedupe keys. |
| `classification_version` | Yes | Checker/taxonomy version for audit and FakeQuality repeatability. |

Issue draft shape:

| Field | Required | Notes |
| --- | --- | --- |
| `target_type`, `target_id`, scope ids | Yes | Page/TextBlock/Artifact/Batch scope. |
| `discovered_stage` | Yes | Stage where issue was detected. |
| `root_stage` | Yes | Probable cause stage or root domain. |
| `issue_type` | Yes | Compact P0 IssueType. |
| `error_code` | Yes | Specific observed condition. |
| `severity` | Yes | `info`, `warning`, `error`, or `blocking`. |
| `is_blocking` | Yes | Export-effectiveness gate while open. |
| `status` | Yes | Usually `open` for new drafts. |
| `message_key` | Yes | Stable UI/API key. |
| `message_params` | Optional | Sanitized counts/labels only. |
| `suggested_action_key` | Yes | Non-binding action hint. |
| Evidence refs | Optional | Attempt, tool, artifact, result, input/config/context hashes. |
| `dedupe_key` | Yes | Stable key for issue lifecycle handling. |

## 5. Severity and `is_blocking`

| Severity | Meaning | Blocking implication |
| --- | --- | --- |
| `info` | Audit or diagnostic note. Rare in MVP-0. | Always `is_blocking = false`. |
| `warning` | Output may be usable but imperfect/incomplete. | Always `is_blocking = false`. |
| `error` | Target output failed, is missing, or is suspect. | May be blocking or non-blocking. |
| `blocking` | Current target/scope cannot be export-effective while issue is open. | Always `is_blocking = true`. |

`is_blocking = true` means the current candidate or active output is not export-effective while the issue is `open`. It is not a command to stop the task. WorkflowLoopEngine can still choose retry, fallback, upstream retry, manual pause, or other allowed paths.

Profile influence:

- QualityCheckService may apply quality strictness to classify severity and `is_blocking`.
- Warning export permission, skip acceptance, retry budget use, fallback provider selection, and final `block` decision remain WorkflowLoopEngine-owned.

## 6. `discovered_stage` and `root_stage`

`discovered_stage` is one canonical workflow stage:

```text
import
detection
ocr
translation
translation_check
cleaning
typesetting
export_check
```

`root_stage` is:

- one canonical workflow stage when the cause is a stage output/input; or
- one root domain when the cause is outside stage output quality:

```text
provider
provider_policy
artifact
config
workflow
unknown
```

Rules:

- If uncertain, set `root_stage = discovered_stage`.
- Provider policy refusal uses `root_stage = provider_policy`.
- Missing/hash-invalid official files use `root_stage = artifact`.
- Missing provider/API key/config uses `root_stage = config`.
- Downstream overflow may use `root_stage = translation` only when evidence shows translation length caused the overflow; otherwise use `typesetting`.

## 7. Suggested action and message key rules

`suggested_action_key` is a hint for UI/API and WorkflowLoopEngine. It is not a WorkflowDecision.

Allowed P0 action keys:

```text
action.retry_same_stage
action.use_allowed_alternative_or_manual
action.enter_or_retry_ocr
action.retry_or_manual_translate
action.review_skip_or_retry_cleaning
action.shorten_or_review_layout
action.rebuild_or_restore_artifact
action.configure_provider
action.review_warning
action.none_required
```

Message keys are stable identifiers, not final UI copy. They must not include raw provider payloads or bypass guidance.

Safe params:

- canonical stage;
- target type;
- user-readable target label;
- sanitized provider display name;
- counts;
- artifact type.

Forbidden params:

- secrets;
- raw authorization/header/base URL values;
- raw provider payload by default;
- prompt rewrite or evasion guidance;
- unredacted filesystem paths unless explicitly needed in a debug-only surface.

## 8. Key classifications

| Condition | IssueType | Error code | Default |
| --- | --- | --- | --- |
| OCR completed with empty text | `ocr_text_missing` | `ocr_no_text` | Blocking until retry/fallback/manual/accepted skip path. |
| Provider timeout/unavailable/model/dependency failure | `provider_call_failed` | Stage-specific code | Blocking while required output absent. |
| Translation invalid JSON/schema | `stage_output_invalid` | `translation_invalid_json` or `translation_schema_invalid` | Blocking current output; retry/fallback possible. |
| Page translation omits a TextBlock | `translation_missing_block` | `translation_missing_text_block` | TextBlock-scoped blocking until handled. |
| Translation empty/untranslated/term mismatch/too long | `translation_quality_problem` | Specific translation code | Warning or error by strictness; export-effectiveness follows `is_blocking`. |
| Provider refusal | `provider_refusal` | Stage-specific refusal code | Blocking while required output absent; no evasion suggestion. |
| Cleaner cannot safely clean complex region | `cleaning_skipped_complex_region` | `cleaning_complex_background` | Warning by default; pure ready forbidden while unresolved skip remains. |
| Typesetting overflow | `typesetting_overflow` | `typeset_overflow` | Warning if preview usable and profile allows; blocking if unreadable/no usable output/strict. |
| Artifact missing/hash-invalid/registration failed | `artifact_unavailable` | `artifact_missing`, `artifact_hash_mismatch`, or `artifact_registration_failed` | Blocking for required active artifacts. |
| Direct export readiness defect not otherwise represented | `export_precondition_failed` | Export-check code | Blocking. Use sparingly to avoid duplicate issues. |

## 9. Partial translation rule

For Page-level translation with valid and missing block outputs:

- Valid block translations remain candidate outputs.
- Missing or invalid blocks get TextBlock-scoped issue drafts.
- A Page summary issue may be derived later for UI; MVP-0 does not require it.
- Active translation pointers are updated only if WorkflowLoopEngine accepts those candidates through the acceptance transaction.
- Pure `ready_for_export` is impossible while unresolved missing/invalid required blocks remain.

If all requested blocks are missing or invalid, classify as `stage_output_invalid`, not `partial_success`.

## 10. Refusal safety rule

Provider refusal issue drafts must:

- use `issue_type = provider_refusal`;
- use `root_stage = provider_policy`;
- include sanitized provider metadata only;
- use `message_key = provider.refused` or `provider.refused.translation`;
- use `suggested_action_key = action.use_allowed_alternative_or_manual`;
- never suggest bypass, jailbreak, obfuscation, content laundering, or prompt rewriting to avoid provider policy.

## 11. Issue lifecycle suggestions

QualityCheckService may suggest lifecycle changes:

| Status | Meaning |
| --- | --- |
| `open` | Issue applies to current evidence. |
| `resolved` | Fixed by rerun, edit, user action, or validation. |
| `accepted_warning` | Warning remains visible and is accepted under policy. |
| `stale` | Active input/result changed and issue no longer applies. |
| `superseded` | Newer issue replaces same target/root cause. |

The caller transaction persists lifecycle updates. QualityCheckService does not mutate workflow state.

## 12. FakeQualityCheck requirements

FakeQualityCheck must be deterministic from:

```text
stage + target_id + input_hash + config_hash + fake_mode + classification_version
```

It must produce issue drafts for:

- OCR empty text;
- provider failure;
- translation invalid JSON;
- provider refusal;
- missing translation block;
- cleaning complex background;
- typesetting overflow;
- artifact missing/hash mismatch;
- artifact registration failure.

It must not emit WorkflowDecisions or update active pointers.
