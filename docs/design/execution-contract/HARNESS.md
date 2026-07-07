# Execution Contract Design HARNESS

## 1. Purpose

This HARNESS validates whether the Execution Contract Design is sufficient for the MVP FakeProvider single-Page backend vertical slice.

The final design passes only if the proposed contracts can support provider calls, artifact registration, quality checking, workflow decisions, and recovery evidence without violating architecture boundaries.

## 2. Validation format

For each scenario, the final validation should mark:

```text
PASS / FAIL / UNCLEAR
```

Each result should briefly explain:

* Stage involved
* Provider output or error
* ArtifactService behavior
* QualityCheckService behavior
* StageExecutor behavior
* WorkflowLoopEngine decision input
* Persistence or recovery evidence
* Boundary check

## 3. Provider Adapter contract scenarios

### P01: Provider success result

A provider returns a valid successful output.

Expected:

* Provider returns structured output and metadata.
* Provider does not write official artifact records.
* Provider does not access SQLite.
* StageExecutor can pass output to ArtifactService and QualityCheckService.
* WorkflowLoopEngine receives enough evidence to decide `continue`.

### P02: Provider timeout or transient failure

A provider times out or returns a retryable failure.

Expected:

* Provider returns standardized error.
* No `QualityIssue` is created by Provider Adapter.
* StageExecutor preserves error evidence.
* QualityCheckService can classify issue if needed.
* WorkflowLoopEngine receives enough evidence to decide retry, fallback, pause, or block.

### P03: Provider refusal

A provider refuses content.

Expected:

* Refusal is represented explicitly, not as generic crash.
* Refusal includes sanitized provider metadata and error code.
* No bypass or evasion behavior exists.
* QualityCheckService can classify provider refusal.
* WorkflowLoopEngine can decide fallback, manual path, warning, skip, pause, or block.

### P04: Invalid structured output

Translation provider returns invalid JSON or schema-invalid output.

Expected:

* Provider or StageExecutor reports invalid output in a standardized way.
* Raw output may be retained as artifact according to policy.
* QualityCheckService can create invalid-output issue.
* WorkflowLoopEngine can retry or block according to budget/profile.

### P05: Page translation partial output

Translation provider returns valid translations for some TextBlocks and misses others.

Expected:

* Valid block outputs can become TranslationResults.
* Missing/invalid blocks can become issues.
* One page-scoped provider attempt remains explainable.
* StageExecutor can return partial success evidence.
* WorkflowLoopEngine can decide retry, warning, pause, or block.

## 4. ArtifactService contract scenarios

### A01: Register original image

Import stage registers the original image.

Expected:

* Original image becomes official artifact.
* Original image is never overwritten.
* Hash, media type, size, and path metadata are recorded.
* Domain rows reference artifact id, not authoritative raw path.

### A02: Promote temporary provider output

A provider produces a temporary output file.

Expected:

* Provider does not decide official artifact path.
* ArtifactService promotes or copies the temp file into official workspace location.
* ArtifactService computes hash and registers metadata.
* StageExecutor receives artifact id or registration result.

### A03: Register failed attempt evidence

A failed provider call produces raw output or diagnostic payload.

Expected:

* Evidence can be registered as failed/debug artifact.
* Artifact is marked with suitable type, retention class, and safety flags.
* Artifact metadata is enough for audit and recovery.
* Secrets are not stored.

### A04: Missing active artifact

Recovery or export check finds that an active artifact path is missing or hash-invalid.

Expected:

* ArtifactService detects missing/hash mismatch.
* Artifact storage state can become `missing`.
* ArtifactService does not decide rebuild, retry, warning, or block.
* WorkflowLoopEngine receives evidence for decision making.

### A05: Artifact cleanup boundary

A cleanup policy marks some rebuildable artifacts eligible for cleanup.

Expected:

* Cleanup does not remove original images.
* Cleanup does not remove active cleaned/typeset/export artifacts.
* Cleanup does not remove required failed-attempt evidence.
* Cleanup decisions remain separate from provider execution.

## 5. QualityCheckService / IssueType scenarios

### Q01: OCR empty result

OCR provider returns empty text.

Expected:

* QualityCheckService can create OCR issue.
* Issue has discovered stage, root stage, severity, blocking flag, message key, and suggested action.
* WorkflowLoopEngine decides retry, fallback, manual input, or block.

### Q02: Translation invalid JSON

Translation output is invalid or unparseable.

Expected:

* QualityCheckService can classify translation invalid output.
* Issue can be blocking or retryable according to policy.
* WorkflowLoopEngine decides retry/fallback/block.
* Provider Adapter does not make that decision.

### Q03: Translation missing TextBlock

Page-level translation omits one TextBlock.

Expected:

* Valid translations remain usable.
* Missing TextBlock gets issue.
* Issue target can be Page or TextBlock as appropriate.
* WorkflowLoopEngine can choose retry, warning, pause, or block.

### Q04: Provider refusal issue

Provider refusal occurs in translation.

Expected:

* Issue type or error code captures refusal.
* `root_stage` can identify provider policy or provider boundary.
* User-facing message can explain safe options.
* No bypass/evasion instruction is produced.

### Q05: Cleaning complex background

Cleaner cannot safely clean a complex background.

Expected:

* Issue can be warning by default unless profile makes it blocking.
* Stage can be skipped only through workflow decision.
* Page cannot become pure ready_for_export if skipped content remains.

### Q06: Typesetting overflow

Typesetter cannot fit translated text.

Expected:

* Preview artifact may be retained.
* Issue records overflow.
* Suggested action can be shorten translation, manual edit, retry upstream, warning, or block.
* WorkflowLoopEngine owns the decision.

## 6. StageExecutor integration scenarios

### S01: Happy path stage execution

A stage executes successfully.

Expected sequence:

```text
load durable context
create/start attempt
call provider or local tool
register artifacts through ArtifactService
run QualityCheckService
return normalized stage result to WorkflowLoopEngine
WorkflowLoopEngine decides continue
persist accepted result/pointers/statuses through Repository
```

Expected:

* No write transaction is held across provider call.
* StageExecutor does not make final workflow decision.
* Provider does not access database.
* ArtifactService owns official artifact registration.

### S02: Provider call fails before artifact output

Provider call fails before producing output.

Expected:

* Attempt can be marked failed/refused by workflow-side handling.
* ToolRunLog or equivalent evidence can be persisted.
* QualityCheckService can classify issue from standardized error.
* WorkflowLoopEngine has enough information for retry/fallback/block.

### S03: File produced but artifact registration fails

Provider output file exists, but ArtifactService registration fails.

Expected:

* Provider result is not treated as official artifact.
* StageExecutor reports artifact registration failure.
* QualityCheckService or workflow can produce issue.
* Recovery can treat temp/orphan file as non-official unless replayed through normal registration.

### S04: QualityCheck returns blocking issue

Provider output and artifact registration succeed, but quality check finds blocker.

Expected:

* Output may remain auditable.
* Active pointer is not updated as export-effective.
* WorkflowLoopEngine decides retry, fallback, pause, or block.
* QualityCheckService does not advance workflow state.

### S05: QualityCheck returns warning issue

Output is usable but has warning.

Expected:

* Issue remains visible.
* WorkflowLoopEngine may mark warning.
* Export readiness later depends on ProcessingProfileSnapshot.
* Warning is auditable.

## 7. FakeProvider readiness scenarios

### F01: Fake happy path

Fake providers simulate detection, OCR, translation, cleaning, and typesetting success.

Expected:

* All stages can run without real external tools.
* Official artifacts can be registered.
* Quality checks pass.
* Workflow reaches ready_for_export.

### F02: Fake OCR failure then retry

Fake OCR fails once then succeeds.

Expected:

* First attempt produces standardized failure.
* Retry path is testable.
* Second attempt succeeds.
* Attempt and decision evidence is sufficient.

### F03: Fake translation invalid JSON

Fake translation returns invalid JSON.

Expected:

* Invalid output artifact may be retained.
* Quality issue is generated.
* Retry or block path is testable.

### F04: Fake provider refusal

Fake translation returns refusal.

Expected:

* Refusal path is testable without real provider.
* ToolRunLog / WorkflowAttempt / QualityIssue / WorkflowDecision evidence can be produced.
* No bypass logic exists.

### F05: Fake cleaning skip

Fake cleaner reports complex background.

Expected:

* Cleaning skip path is testable.
* Warning-bearing page path is testable.
* Pure ready_for_export is not allowed if skipped content remains.

### F06: Fake typesetting overflow

Fake typesetter returns overflow with preview artifact.

Expected:

* Preview artifact registration is testable.
* Overflow issue is testable.
* Warning/pause/block path is testable.

### F07: Fake missing artifact

Fake or test setup removes an expected artifact.

Expected:

* ArtifactService detects missing state.
* Workflow receives evidence.
* Recovery/rebuild/block behavior can be tested.

## 8. Boundary failure checks

The final design fails if:

* Provider Adapter creates QualityIssue.
* Provider Adapter accesses Repository / DAO.
* Provider Adapter registers official artifacts.
* Provider Adapter decides retry/fallback/skip/warning/block.
* QualityCheckService advances workflow state.
* QualityCheckService updates active pointers.
* ArtifactService decides workflow retry/fallback/warning/block.
* StageExecutor replaces WorkflowLoopEngine decision logic.
* Images or large payloads are stored in SQLite.
* Original image overwrite is allowed.
* Provider refusal is represented only as generic failure.
* FakeProvider requires real OCR, LLM, cleaning, or typesetting tools.
