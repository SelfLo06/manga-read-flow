# State Data Impact

This document explains how key state transitions are represented in data.

## OCR edit

Data changes:

- Create a new `OCRResult` with `source_type = user_edit`, `is_user_edited = true`, and `parent_ocr_result_id` pointing to the previous active OCR when available.
- Update `TextBlock.active_ocr_result_id` to the new result.
- Set `TextBlock.translation_status = stale`.
- Set `TextBlock.translation_check_status = stale`.
- Set `TextBlock.typesetting_status = stale`.
- Set `TextBlock.review_status = needs_review`.
- Set `Page.translation_context_stale = true` and `Page.has_stale_blocks = true`.
- Mark downstream QualityIssues tied to old active translation/typesetting inputs as `stale` or `superseded`.

Reason:

- Old OCR remains auditable. Downstream translation and typesetting must not be considered export-effective.

## Translation edit

Data changes:

- Create a new `TranslationResult` with `source_type = user_edit`, `is_user_edited = true`, `source_ocr_result_id`, and `source_text_hash`.
- Update `TextBlock.active_translation_result_id` to the new result.
- Set `TextBlock.typesetting_status = stale`.
- Set `TextBlock.review_status = needs_review`.
- Set `Page.has_stale_blocks = true`.
- Mark prior typesetting issues tied to old translation input as `stale` or `superseded`.

Reason:

- The edited translation becomes selected, but rendered output must be regenerated or accepted through workflow.

## Provider refusal

Data changes:

- Create or update page/textblock-scoped `ToolRunLog` with `status = refused` or failed, `is_provider_refusal = true`, and a sanitized refusal error code.
- Persist `WorkflowAttempt` with `status = refused`, input/config/context hashes, provider/model metadata, and any retained evidence artifact ids.
- Create `QualityIssue` with:
  - `issue_type = provider_refusal` or stage-specific refusal code.
  - `discovered_stage = translation` for translation refusal.
  - `root_stage = provider_policy`.
  - severity/blocking based on QualityCheckService and ProcessingProfileSnapshot.
- Create `WorkflowDecision` and link it through `WorkflowDecisionIssue`.
- Decision type is one of `fallback_provider`, `mark_warning`, `skip_target`, `pause_for_user`, or `block`.

Reason:

- Provider refusal is not a crash and not a hidden provider detail. It is a first-class workflow path.

## Cleaning skip

Data changes:

- Set `TextBlock.cleaning_status = skipped`.
- Set `TextBlock.is_skipped = true` only if the user/workflow skips the block entirely; otherwise record stage-level skip with `skip_reason`.
- Create `QualityIssue` such as `cleaning_complex_background` with `severity = warning` unless the profile makes it blocking.
- Create `WorkflowDecision.decision_type = skip_target` or `mark_warning`.
- Page/Batch aggregate status may become `ready_for_export_with_warnings`.

Reason:

- Complex areas may be skipped in MVP and should not fail the whole Page by default.

## Typesetting overflow

Data changes:

- Register the attempted preview as a `ProcessingArtifact` with `artifact_type = typeset_image` or preview subtype.
- If accepted as the current preview candidate, update `Page.active_typeset_artifact_id`.
- Create `QualityIssue` with `issue_type = typeset_overflow`, discovered/root attribution, suggested action, and severity from profile.
- Create `WorkflowDecision` as `mark_warning`, `retry_upstream_stage`, `pause_for_user`, or `block`.
- If warning is allowed, Page may become `ready_for_export_with_warnings`; otherwise `blocked`.

Reason:

- The user can inspect a preview even when layout quality is imperfect.

## Crash recovery

Startup reconciliation:

- Find `ProcessingTask.status = running` with stale `heartbeat_at`.
- Mark task `interrupted`, then `recovering` while reconciliation runs.
- Find `WorkflowAttempt.status = running`.
- If valid output/result/artifact state exists, mark attempt according to evidence and continue.
- If no durable completion evidence exists, mark attempt `abandoned_after_crash` or `interrupted`.
- Reconcile TextBlock stage statuses from:
  - active OCR/translation pointers,
  - result dependency hashes,
  - ProcessingArtifact storage states,
  - ToolRunLog outcomes,
  - QualityIssue status,
  - WorkflowDecision history.

Recovery outcomes:

- Completed OCR with active OCR pointer is not rerun.
- Provider output artifact without result rows can be parsed/reused if retained and hashes match; otherwise retry or mark issue.
- Result row without active pointer can become active only if a WorkflowDecision or recovery rule proves it passed checks.
- Active pointer with stale stage status triggers status repair or downstream stale propagation, not blind provider rerun.

Reason:

- Recovery cannot rely on Page.status alone.

## Export blocking

Normal export query:

- Target scope is Page or Batch.
- Query `QualityIssue` rows where:
  - `is_blocking = true`,
  - `status = open`,
  - target falls within export scope.

Data changes when blockers exist:

- Create or update `ExportRecord.status = blocked`.
- Store `blocking_issue_count`, `warning_issue_count`, `issue_snapshot_hash`, and optional issue snapshot artifact.
- Do not create a normal output artifact.

Data changes when only warnings exist:

- If `ProcessingProfileSnapshot.allow_warning_export = true`, create output artifact and `ExportRecord.status = succeeded_with_warnings`.
- If warning export is not allowed, `ExportRecord.status = blocked` or equivalent rejected status with warning policy reason.

Reason:

- Export safety is data-driven and reproducible from project.db.
