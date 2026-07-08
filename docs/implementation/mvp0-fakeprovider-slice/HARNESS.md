# MVP-0 FakeProvider Single-Page Backend Slice HARNESS

## 1. Purpose

This HARNESS validates whether the implementation plan is sufficient to start MVP-0 backend implementation safely.

The plan passes only if it can drive a small, testable, FakeProvider-first backend vertical slice without introducing real providers, Web UI, FastAPI routes, actual export output, or P1/P2 features.

## 2. Validation format

For each scenario, mark:

```text
PASS / FAIL / UNCLEAR
```

Each result should briefly explain:

* implementation slice responsible;
* required modules;
* required test or validation command;
* required persisted evidence;
* boundary check;
* scope check.

## 3. Planning completeness scenarios

### G01: Slice order is implementation-ready

Expected:

* The plan defines a concrete implementation order.
* Each slice has a narrow goal.
* Each slice has allowed files and forbidden files.
* Each slice has validation commands or test targets.
* No slice requires the entire product to exist.

### G02: Codex tasks are bounded

Expected:

* Each implementation task can be given to Codex as a small goal.
* Each task states what files may be changed.
* Each task states what must not be changed.
* Each task has acceptance criteria.
* Each task has a commit strategy.

### G03: Prior design baselines are respected

Expected:

* Data model, workflow-state, execution-contract, and persistence-readiness designs are treated as constraints.
* Goal 4 does not reopen major architecture decisions.
* Open questions are listed only if they block implementation planning.

## 4. Backend foundation scenarios

### B01: Project store initialization

Expected:

* Plan includes app.db initialization.
* Plan includes project.db initialization.
* Plan includes ProjectMetadata verification.
* Plan includes independent migration ledgers.
* Plan uses temporary SQLite tests.

### B02: Import one Page

Expected:

* Plan includes original image registration through ArtifactService.
* Page points to original artifact id.
* Original bytes remain on filesystem.
* Original image is never overwritten.
* No image bytes are stored in SQLite.

### B03: Minimal repository contracts

Expected:

* Plan includes repository implementation order.
* Repository / DAO remains the only SQLite access entry.
* WorkflowLoopEngine does not depend on SQL or ORM internals.
* Provider Adapter has no persistence dependency.

## 5. Workflow execution scenarios

### W01: Fake happy path

Expected:

* Plan supports deterministic FakeProvider detection, OCR, translation, cleaning, and typesetting.
* Workflow creates TextBlocks, OCRResults, TranslationResults, cleaned artifact, and typeset artifact.
* Active pointers are updated only through acceptance.
* Workflow reaches `ready_for_export`.

### W02: Stage execution boundary

Expected:

* StageExecutor calls FakeProvider.
* StageExecutor can persist only narrow tool evidence through StageEvidenceWriter.
* StageExecutor does not create WorkflowDecision.
* StageExecutor does not update active pointers.
* Provider call does not hold SQLite write transaction.

### W03: Acceptance transaction

Expected:

* Plan includes an implementation slice for acceptance transaction.
* Accepted results, active pointers, issue lifecycle, WorkflowDecision, retry budget, task progress, and stage statuses commit together.
* Guard failures are handled by reload and redecision, not silent overwrite.

## 6. Quality and readiness scenarios

### Q01: Invalid or partial translation

Expected:

* Plan includes at least one issue-bearing FakeProvider mode.
* Invalid or partial translation creates QualityIssue evidence.
* WorkflowDecision records retry, warning, pause, or block.
* Valid partial outputs do not become fully ready without issue visibility.

### Q02: Provider refusal

Expected:

* Plan includes FakeProvider refusal mode.
* Refusal is persisted as ToolRunLog, WorkflowAttempt, QualityIssue, and WorkflowDecision evidence.
* No policy bypass or evasion data appears.

### Q03: Blocking issue prevents readiness

Expected:

* Plan includes readiness check.
* Open blocking QualityIssue prevents pure `ready_for_export`.
* Warning state does not silently become pure readiness.

## 7. Idempotency and recovery scenarios

### I01: Rerun unchanged Page

Expected:

* Plan includes idempotency validation.
* Unchanged OCR/translation/cleaning/typesetting can be reused.
* Reuse is auditable through attempt or decision evidence.
* No duplicate active result rows are created.

### R01: Crash after OCR acceptance

Expected:

* Plan includes a test or simulation for crash after OCR acceptance.
* Recovery finds durable OCRResult and active OCR pointer.
* Workflow resumes from translation without rerunning OCR.
* Recovery does not rely only on Page.status.

### R02: Crash after artifact registration before acceptance

Expected:

* Plan includes registered-but-unselected artifact scenario.
* Registered artifact remains official but unselected.
* It is not selected by latest timestamp.
* WorkflowLoopEngine decides reuse, retry, pause, or block.

### R03: Missing active artifact

Expected:

* Plan includes missing artifact validation.
* ArtifactService marks artifact storage state as missing.
* WorkflowLoopEngine decides rebuild, warning, pause, or block.
* ArtifactService does not make workflow decisions.

## 8. Scope failure checks

The implementation plan fails if it requires:

* Web UI;
* FastAPI routes;
* real OCR / translation / cleaning / typesetting providers;
* real translation prompt templates;
* actual export output;
* ZIP export;
* manifest artifact;
* ExportRecord;
* Batch-scale workflow;
* provider config UI;
* secret storage integration;
* P1/P2 geometry, context, or advanced review features.

## 9. Architecture failure checks

The implementation plan fails if it allows:

* Provider Adapter to access SQLite;
* Provider Adapter to register official artifacts;
* Provider Adapter to create QualityIssues;
* ArtifactService to decide workflow retry/fallback/warning/block;
* QualityCheckService to update active pointers or workflow state;
* StageExecutor to become a hidden WorkflowLoopEngine;
* WorkflowLoopEngine to depend directly on SQL or ORM session internals;
* latest timestamp to select active result or artifact;
* Page.status-only recovery;
* image bytes or large payloads in SQLite;
* original image overwrite.