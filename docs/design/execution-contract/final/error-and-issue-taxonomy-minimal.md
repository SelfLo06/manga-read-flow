# Minimal Error and Issue Taxonomy v0.1

## 1. Classification layers

Use three layers:

| Layer | Owner | Purpose |
| --- | --- | --- |
| Provider/stage `error.kind` and `error.code` | Provider Adapter, StageExecutor, ArtifactService evidence | Specific observed condition. |
| `issue_type` | QualityCheckService | Compact workflow/user-facing issue category. |
| `severity` plus `is_blocking` | QualityCheckService using quality strictness | UI/report urgency and export-effectiveness gate. |

WorkflowLoopEngine consumes these layers but owns workflow decisions.

## 2. Provider error kinds

```text
provider_timeout
provider_unavailable
provider_refusal
invalid_input
invalid_output
model_error
dependency_missing
file_io_error
unsupported_content
unknown_error
```

## 3. Minimal error codes

| Area | MVP codes |
| --- | --- |
| Detection | `detection_no_text`, `detection_low_confidence`, `detection_invalid_input`, `detection_invalid_output`, `detection_model_error`, `detection_unsupported_content`. |
| OCR | `ocr_timeout`, `ocr_provider_unavailable`, `ocr_invalid_input`, `ocr_invalid_output`, `ocr_no_text`, `ocr_model_error`, `ocr_dependency_missing`. |
| Translation | `translation_timeout`, `translation_provider_unavailable`, `translation_rate_limited`, `translation_quota_exceeded`, `translation_invalid_input`, `translation_invalid_json`, `translation_schema_invalid`, `translation_missing_text_block`, `translation_partial_output`, `translation_provider_refused`, `translation_nsfw_policy_refused`, `translation_child_safety_refused`, `translation_empty`, `translation_untranslated`, `translation_term_mismatch`, `translation_too_long`, `translation_model_error`. |
| Cleaning | `cleaning_timeout`, `cleaning_invalid_input`, `cleaning_invalid_output`, `cleaning_mask_missing`, `cleaning_complex_background`, `cleaning_model_error`, `cleaning_dependency_missing`, `cleaning_file_io_error`. |
| Typesetting | `typesetting_invalid_input`, `typesetting_invalid_output`, `typeset_overflow`, `typesetting_font_missing`, `typesetting_file_io_error`, `typesetting_model_error`. |
| Artifact | `artifact_registration_failed`, `artifact_missing`, `artifact_hash_mismatch`, `artifact_metadata_only`, `artifact_inaccessible`, `artifact_unregistered_output`. |
| Export check | `export_active_typeset_missing`, `export_stale_output`, `export_blocked_by_open_issue`, `export_warnings_not_allowed`. |
| Config/provider selection | `provider_missing_config`, `provider_invalid_config`, `provider_disabled`, `provider_unknown_error`. |

This is not a full future catalog. New codes may be added by later design when real providers require them.

## 4. Minimal IssueType catalog

| IssueType | Main use | Default severity | Default `is_blocking` |
| --- | --- | --- | --- |
| `provider_call_failed` | Timeout, unavailable, dependency/config/model/tool failures. | `error` | true while required output is absent. |
| `provider_refusal` | Provider policy/content refusal. | `error` | true while required output is absent. |
| `stage_output_invalid` | Unparseable, schema-invalid, or unsupported structured output. | `error` | true if no usable accepted output exists. |
| `ocr_text_missing` | OCR produced empty/unusable text for a processable TextBlock. | `error` | true until retry/fallback/manual/accepted skip. |
| `translation_missing_block` | Page translation omitted or invalidated a required TextBlock. | `error` | true for that TextBlock until handled. |
| `translation_quality_problem` | Empty translation, untranslated text, term mismatch, overlong text, or quality risk. | `warning` or `error` | profile/strictness-dependent. |
| `cleaning_skipped_complex_region` | Cleaner cannot safely clean complex background/region. | `warning` | false by default. |
| `typesetting_overflow` | Text cannot fit target area under current layout limits. | `warning` | profile/output-dependent. |
| `artifact_unavailable` | Official artifact missing, hash-invalid, inaccessible, or registration failed. | `blocking` for required active artifacts; otherwise `error`. | true for required active artifacts. |
| `export_precondition_failed` | Direct readiness defect not already represented by another open issue. | `blocking` | true. |

Use `export_precondition_failed` sparingly. Export/readiness should normally rely on existing open blockers rather than duplicating root issues.

## 5. Severity and blocking rules

| Rule | Requirement |
| --- | --- |
| `severity = blocking` | Must imply `is_blocking = true`. |
| `severity = warning` or `info` | Must imply `is_blocking = false`. |
| `severity = error` | May be blocking or non-blocking depending on current output, target, profile strictness, and accepted warning/skip state. |
| `is_blocking = true` | Means output is not export-effective while issue status is `open`; it does not force immediate workflow `block`. |
| Warning readiness | Requires no open blocking issues and `ProcessingProfileSnapshot.allow_warning_export = true`. |
| Pure readiness | Not allowed while unresolved warnings/skips remain. |

## 6. Root-stage vocabulary

Canonical workflow stages:

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

Allowed root domains:

```text
provider
provider_policy
artifact
config
workflow
unknown
```

Attribution examples:

| Situation | `discovered_stage` | `root_stage` |
| --- | --- | --- |
| OCR empty text | `ocr` | `ocr` |
| Translation invalid JSON | `translation` | `translation` or `provider` |
| Translation provider refusal | `translation` | `provider_policy` |
| Missing translation block found by check | `translation_check` | `translation` |
| Cleaning complex background | `cleaning` | `cleaning` |
| Overflow caused by long translation | `typesetting` | `translation` |
| Overflow caused by layout limits | `typesetting` | `typesetting` |
| Active typeset file missing at readiness | `export_check` | `artifact` |
| Missing provider API key | `translation` | `config` |

If uncertain, set `root_stage = discovered_stage`.

## 7. Message keys

Minimal P0 message keys:

```text
ocr.no_text
translation.invalid_output
translation.missing_text_block
translation.partial_output
translation.quality_problem
provider.refused
provider.refused.translation
provider.unavailable
cleaning.skipped_complex_background
cleaning.mask_missing
typesetting.overflow
artifact.missing
artifact.registration_failed
export.blocked_by_open_issue
export.warnings_not_allowed
```

Message keys are stable identifiers. Final localized copy belongs to UI/API design.

## 8. Suggested action keys

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

Suggested actions are hints. They do not consume budgets, select providers, accept warnings, skip targets, pause tasks, or block tasks.

## 9. Scenario mappings

| Scenario | IssueType | Error code | Message/action |
| --- | --- | --- | --- |
| OCR empty result | `ocr_text_missing` | `ocr_no_text` | `ocr.no_text` / `action.enter_or_retry_ocr`. |
| Translation invalid JSON | `stage_output_invalid` | `translation_invalid_json` | `translation.invalid_output` / `action.retry_or_manual_translate`. |
| Translation missing TextBlock | `translation_missing_block` | `translation_missing_text_block` | `translation.missing_text_block` / `action.retry_or_manual_translate`. |
| Provider refusal | `provider_refusal` | `translation_provider_refused` or specific refusal code | `provider.refused.translation` / `action.use_allowed_alternative_or_manual`. |
| Cleaning complex background | `cleaning_skipped_complex_region` | `cleaning_complex_background` | `cleaning.skipped_complex_background` / `action.review_skip_or_retry_cleaning`. |
| Typesetting overflow | `typesetting_overflow` | `typeset_overflow` | `typesetting.overflow` / `action.shorten_or_review_layout`. |
| Missing active artifact | `artifact_unavailable` | `artifact_missing` or `artifact_hash_mismatch` | `artifact.missing` / `action.rebuild_or_restore_artifact`. |
| Artifact registration failure | `artifact_unavailable` | `artifact_registration_failed` | `artifact.registration_failed` / `action.rebuild_or_restore_artifact`. |

## 10. Deferred taxonomy

Deferred until later quality/API/UI design:

- Detailed OCR confidence bands.
- Fine-grained translation naturalness categories.
- Full provider-vendor error catalogs.
- Full export/manifest issue snapshots.
- Localized message text and parameter rendering.
- Maintenance-only cleanup warnings.
