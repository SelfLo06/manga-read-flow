# Workflow State / Workflow Loop HARNESS

## 1. Purpose

This HARNESS defines the scenario checks for the Workflow State / Workflow Loop detailed design.

The final design passes only if each MVP scenario can be replayed using the proposed state vocabulary, transition rules, decision matrix, stale propagation rules, and recovery rules.

## 2. Validation format

For each scenario, the final validation should mark:

```text
PASS / FAIL / UNCLEAR
```

Each result should briefly explain:

* Initial state
* Trigger
* Expected state changes
* Expected `WorkflowAttempt`
* Expected `WorkflowDecision`
* Expected `QualityIssue` behavior
* Expected artifact or active pointer behavior
* Export impact

## 3. Core happy path

### H01: Single Page happy path

Scenario:

```text
import original image
→ detect text blocks
→ OCR each block
→ translate page
→ run translation check
→ clean text areas
→ typeset translated text
→ export check
→ ready_for_export
```

Expected:

* Each stage reaches a completed state.
* Active OCR pointers are set on TextBlocks.
* Active translation pointers are set on TextBlocks.
* Page active cleaned/typeset artifact pointers are set.
* Attempts and decisions are persisted.
* No open blocking issue remains.
* Normal export is allowed.

## 4. Provider and tool failure scenarios

### F01: OCR fails once then succeeds by retry

Expected:

* Failed OCR attempt is persisted.
* Retry decision is persisted.
* Retry budget is consumed.
* Successful retry updates OCR state and active OCR pointer.
* Downstream stages can continue.

### F02: Translation output is invalid JSON then retry succeeds

Expected:

* Invalid output is recorded as failed or invalid attempt.
* Quality issue or standardized error is available.
* Retry decision is persisted.
* Retry budget is consumed.
* Successful retry creates valid TranslationResults.

### F03: Page-level translation returns partial output

Expected:

* Valid block translations are persisted.
* Missing or invalid block translations create issues.
* The page-level attempt remains explainable.
* Workflow decision is one of retry, warning, pause, or block according to profile.

### F04: Provider refusal

Expected:

* Provider refusal is not treated as crash.
* ToolRunLog records sanitized refusal metadata.
* WorkflowAttempt status reflects refusal.
* QualityIssue records provider refusal or stage-specific refusal.
* WorkflowDecision chooses fallback, warning, skip, pause, or block according to profile.
* No bypass or policy-evasion behavior is introduced.

### F05: Cleaning skips complex background

Expected:

* Cleaning stage can be skipped for the target.
* A warning issue is created unless profile makes it blocking.
* WorkflowDecision records skip or warning.
* Page may become ready_for_export_with_warnings.

### F06: Typesetting overflow

Expected:

* Preview artifact may be retained.
* Typesetting overflow issue is created.
* WorkflowDecision chooses warning, retry upstream, pause, or block.
* Export readiness depends on profile and blocking status.

## 5. User edit and stale propagation scenarios

### S01: OCR edit after translation exists

Expected:

* New OCRResult is created.
* TextBlock active OCR pointer is updated.
* Translation status becomes stale.
* Translation check status becomes stale.
* Typesetting status becomes stale.
* Page translation context becomes stale.
* Old downstream issues are stale or superseded.

### S02: Translation edit after typesetting exists

Expected:

* New TranslationResult is created.
* TextBlock active translation pointer is updated.
* Typesetting status becomes stale.
* Review status becomes needs_review.
* Page has stale blocks.
* Prior typesetting issues tied to old translation are stale or superseded.

## 6. Recovery scenarios

### R01: Crash after OCR before translation

Expected:

* Stale running task is marked interrupted then recovering.
* Completed OCR result remains reusable.
* Active OCR pointer remains valid.
* Translation resumes from the next required stage.
* Workflow does not rerun OCR unless input hash or state requires it.

### R02: Crash during provider call

Expected:

* Stale running attempt is marked abandoned_after_crash or equivalent.
* Task enters recovering.
* Recovery decides whether to retry, reuse prior result, or block.
* Recovery does not trust Page.status alone.

### R03: Missing artifact during recovery

Expected:

* Missing artifact is detected.
* Artifact status is updated or issue is created.
* Workflow either rebuilds, retries upstream, warns, or blocks.
* Original image is never overwritten.

## 7. Export gate scenarios

### E01: Normal export with unresolved blocking issue

Expected:

* Export is rejected.
* ExportRecord or equivalent export attempt metadata is persisted.
* Blocking issue remains visible.
* No normal export artifact is produced.

### E02: Warning export allowed by profile

Expected:

* Open warning issues are allowed only if ProcessingProfileSnapshot permits warning export.
* Export result records warning state.
* Warning issues remain auditable.

### E03: Warning export not allowed by profile

Expected:

* Export is rejected or page is blocked.
* WorkflowDecision explains profile-based rejection.
* User can see what must be fixed.

## 8. Task control scenarios

### T01: Pause then resume

Expected:

* ProcessingTask enters paused state.
* Running stage reaches a safe boundary or is marked safely interrupted.
* Resume continues from the next required stage.
* Completed results are not discarded.

### T02: Cancel then new task

Expected:

* ProcessingTask enters cancelled state.
* Cancelled task does not automatically resume.
* Completed durable artifacts/results may remain.
* A new task can reuse valid completed results when hashes match.

## 9. Idempotency scenarios

### I01: Re-run completed Page without input changes

Expected:

* Existing active OCR and translation results can be reused.
* Existing cleaned/typeset artifacts can be reused if still present and hash-compatible.
* Workflow does not create duplicate active results.
* New attempts or decisions explain reuse if needed.

### I02: Re-run after OCR edit

Expected:

* OCR is not overwritten.
* Active OCR pointer points to edited OCR.
* Translation and typesetting are regenerated or marked stale until regenerated.
* Old translation/typesetting outputs are not treated as export-effective.

## 10. Scope-control checks

The final design fails if it requires:

* Full production code.
* SQL DDL.
* ORM mapping decisions.
* Full API schema.
* Full Provider Adapter DTO design.
* Full ArtifactService directory layout.
* Full QualityIssue taxonomy.
* P1 forced export.
* P1 GeometryRevision.
* P2 multi-page context translation.
* Distributed workers or a generic workflow engine.
