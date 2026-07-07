## 1. Summary of each proposal.

Proposal 07 gives the strongest taxonomy baseline. It separates `error_code`, `issue_type`, `severity`, and `is_blocking`, keeps P0 issue types compact, and clearly preserves WorkflowLoopEngine ownership of retry, fallback, skip, warning, block, and readiness decisions.

Proposal 08 gives the strongest attribution and report contract. It defines `discovered_stage`, `root_stage`, non-binding `suggested_action`, and a `QualityCheckReport` that can feed WorkflowLoopEngine without becoming a decision engine.

Proposal 09 gives the strongest user-facing and FakeQuality contract. It adds stable `message_key`, sanitized params, safe refusal wording, deterministic fake issue behavior, and clear warnings for cleaning skip and typesetting overflow.

## 2. Agreements.

- Provider refusal must be first-class, not a generic crash, and must never produce bypass or evasion guidance.
- QualityCheckService may classify issue type, severity, blocking flag, discovered stage, root cause, message key, and non-binding remediation hints.
- WorkflowLoopEngine owns retry, fallback, upstream retry, skip, warning acceptance, pause, block, and final readiness.
- Provider adapters must not access SQLite, register official artifacts, create `QualityIssue`, or provide remediation policy.
- ArtifactService reports artifact evidence and storage state, but does not decide rebuild, retry, warning, or block.
- Cleaning skips and typesetting overflow must remain visible as issues; they are not silent success.
- Partial translation must preserve valid block results while flagging missing or invalid blocks.

## 3. Conflicts.

- Issue naming differs: proposal 07 favors compact `issue_type` values such as `stage_output_invalid` and `translation_missing_block`; proposals 08 and 09 use more stage-specific names such as `translation_invalid_json`, `translation_missing_textblock`, and `ocr_no_text`.
- Message and suggested-action naming differs: proposal 08 uses conceptual values like `retry_candidate`; proposal 09 uses UI-style keys like `action.retry_same_stage`.
- Blocking policy is not consistent. Proposal 07 defines stronger default blocking semantics, while proposals 08 and 09 repeatedly say profile-dependent. The final contract must keep profile strictness separate from workflow decisions.
- Proposal 07 allows QualityCheckService to mark older issues resolved, stale, or superseded. Proposal 08 mostly frames QualityCheckService as returning reports. The final contract must choose whether QualityCheckService mutates issue lifecycle or only returns drafts.
- Root cause vocabulary varies between canonical stages and domains such as `provider_policy`, `config`, `filesystem_artifact`, and `artifact`.

## 4. Missing contract details.

- Exact `QualityCheckReport` schema: required inputs, output fields, issue draft shape, evidence refs, summary counts, and classification version.
- Whether QualityCheckService persists issues or only returns issue drafts for StageExecutor/WorkflowLoopEngine to persist through Repository.
- Dedupe key rules and lifecycle transitions for `open`, `resolved`, `accepted_warning`, `stale`, and `superseded`.
- Precise severity and `is_blocking` algorithm for warning, error, blocking, and accepted-warning states.
- Targeting rules for Page-level translation attempts with TextBlock-level missing outputs.
- Artifact issue boundary: ArtifactService detects missing/hash-invalid/registration failure; QualityCheckService classifies workflow relevance.
- Minimal fake fixtures and expected issue payloads for HARNESS scenarios.

## 5. Boundary violations.

No proposal has a direct hard violation like allowing Provider Adapter to create issues, register official artifacts, or decide workflow policy.

Potential violations to prevent in synthesis:

- QualityCheckService must not directly update active OCR, translation, cleaned image, or typeset image pointers.
- QualityCheckService must not advance Page/TextBlock/Task workflow state while marking issue status.
- Profile-dependent `is_blocking` must not become a hidden decision to skip, warn, block, or allow export.
- Suggested actions must not use names that callers can treat as executable `WorkflowDecision` values.
- Artifact recovery suggestions must remain hints; ArtifactService and QualityCheckService must not trigger rebuild or cleanup decisions.

## 6. Over-designed parts.

- Proposal 09's `safe_detail_level`, `debug_summary`, and full message-param catalog are useful but can be optional for MVP-0.
- Persisting `classification_version` on every issue may be more than needed for the FakeProvider slice; report-level or fixture-level versioning may be enough.
- `export_precondition_failed` may duplicate existing upstream or artifact issues unless limited to direct readiness defects.
- Stage-specific provider refusal message keys may be deferred if `provider.refused` plus `stage = translation` is enough for MVP.

## 7. Under-designed parts.

- The proposals do not fully define the transaction boundary around quality issue persistence versus WorkflowDecision persistence.
- Partial translation acceptance is underspecified: valid TranslationResults can exist, but active pointer update must wait for WorkflowLoopEngine acceptance.
- Profile influence on severity/blocking needs a narrow rule. QualityCheckService can apply quality strictness, but warning export and skip acceptance belong to WorkflowLoopEngine.
- Root attribution needs a canonical enum and uncertainty rule to prevent overconfident upstream retries.
- Missing artifact classification needs a clear path for import, active cleaned/typeset artifacts, failed-attempt artifacts, and export_check.

## 8. Recommended module-level decisions.

- Adopt proposal 07's three-layer classification: specific `error_code`, compact `issue_type`, and separate `severity` plus `is_blocking`.
- Adopt proposal 08's `QualityCheckReport` as the module output. For MVP-0, QualityCheckService should return issue drafts and summary evidence; persistence should happen through the caller using Repository.
- Adopt proposal 09's `message_key` and sanitized message params as optional but recommended fields. Keep `suggested_action_key` as a hint, not a decision.
- Normalize P0 IssueTypes to a compact set: `provider_call_failed`, `provider_refusal`, `stage_output_invalid`, `ocr_text_missing`, `translation_missing_block`, `translation_quality_problem`, `cleaning_skipped_complex_region`, `typesetting_overflow`, `artifact_unavailable`, and optionally `export_precondition_failed`.
- Define `is_blocking` as "current candidate or active output is not export-effective while this issue is open." It is not a command to stop the workflow.
- Allow root stages to include canonical workflow stages plus minimal domains: `provider`, `provider_policy`, `artifact`, and `config`. If uncertain, set `root_stage = discovered_stage`.
- Default cleaning complex background to warning and non-blocking, but never allow pure `ready_for_export` while unresolved skipped content remains.
- Default provider refusal to blocking while required output is absent, then let WorkflowLoopEngine decide allowed fallback, manual input, warning, skip, pause, or block.
- Export_check should reuse existing open blockers and create a new issue only for direct readiness defects not already represented.

## 9. Blocking issues.

- Final synthesis must resolve whether QualityCheckService mutates/persists issues or returns issue drafts only. Without this, StageExecutor transaction and recovery behavior are ambiguous.
- Final synthesis must define severity and `is_blocking` rules tightly enough that QualityCheckService cannot become the warning/export/block policy owner.
- Final synthesis must normalize `issue_type`, `error_code`, `message_key`, and `suggested_action_key` naming so FakeQuality and HARNESS assertions have one source of truth.
- Final synthesis must specify partial translation behavior, including Page attempt evidence, TextBlock issues, valid result candidates, and active pointer acceptance timing.

## 10. Non-blocking issues.

- Decide later whether message params are persisted as JSON or derived from evidence.
- Decide later whether `classification_version` is persisted per issue or only in quality report/debug artifacts.
- Decide later whether `translation.partial_output` exists as a Page issue or is derived from TextBlock issues.
- Decide later whether stage-specific refusal message keys are needed for MVP UI clarity.
- Revisit `export_precondition_failed` after cross-module review to avoid duplicate issue chains.

## 11. Open questions.

- Should MVP-0 keep QualityCheckService pure, with no Repository writes, or allow it to persist issues through Repository?
- Should `severity = error` with `is_blocking = false` be allowed after accepted skip/warning, or should accepted issues be downgraded to `warning`?
- Should profile strictness influence QualityCheckService only through severity thresholds, or also through `is_blocking`?
- What is the canonical root domain name for artifact failures: `artifact` or `filesystem_artifact`?
- Should partial translation create only TextBlock issues, or also a Page summary issue?
- Should warning export require explicit user acknowledgement beyond `ProcessingProfileSnapshot.allow_warning_export`?

## 12. What the cross-module reviewer must inspect.

- Provider contract: standardized error/refusal fields must provide enough sanitized evidence for QualityCheckService without creating issues or remediation advice.
- ArtifactService contract: missing/hash-invalid/registration-failed evidence must be explicit, and official artifact lifecycle must remain outside providers and QualityCheckService.
- StageExecutor contract: sequence must be load durable context, start attempt, call provider, register artifacts, run quality check, return normalized evidence; no final workflow decision.
- WorkflowLoopEngine contract: decisions must consume issues, budgets, profile snapshot, provider availability, and attempt history, then update active pointers/statuses only after acceptance.
- Data model contract: `QualityIssue` must support target scope, discovered/root stage, issue type, error code, severity, blocking flag, status, message key, suggested action, dedupe, and evidence refs.
- FakeProvider/FakeQuality contract: fake modes must deterministically cover OCR empty, provider failure, provider refusal, invalid JSON, partial translation, cleaning skip, typesetting overflow, and missing artifact.
