# Persistence Readiness Design HARNESS

## 1. Purpose

This HARNESS validates whether the Persistence Readiness Design is sufficient to start implementing the FakeProvider single-Page backend vertical slice.

The design passes only if persistence boundaries, repository responsibilities, transaction rules, migration strategy, recovery support, and idempotency support are clear enough for safe implementation.

## 2. Validation format

For each scenario, mark:

```text
PASS / FAIL / UNCLEAR
```

Each result should briefly explain:

* Required repository capability
* Required transaction boundary
* Required persisted evidence
* Recovery or idempotency impact
* Boundary check

## 3. Core persistence scenarios

### P01: Create Project and project database

Expected:

* `app.db` registers Project and project database location.
* `project.db` stores Project-owned data.
* Project open verifies project identity.
* No cross-database foreign keys are required.

### P02: Import one Page

Expected:

* Original image is registered as artifact metadata.
* Page points to original artifact id.
* Original image is never overwritten.
* File bytes stay on filesystem, not in SQLite.

### P03: Run happy-path single Page workflow

Expected:

* TextBlocks, OCRResults, TranslationResults, cleaned artifact, typeset artifact, attempts, decisions, issues, and tool logs can be persisted.
* Active OCR, translation, cleaned, and typeset pointers can be updated.
* Workflow can reach `ready_for_export`.

### P04: Acceptance transaction

Expected:

* Accepted result rows, active pointer updates, QualityIssue lifecycle changes, WorkflowDecision, retry budget after, and stage statuses are committed consistently.
* A partially accepted state is either impossible or recoverable.
* Provider call is not inside a long write transaction.

## 4. Recovery scenarios

### R01: Crash after OCR result committed

Expected:

* Repository can find stale running task.
* Repository can find running or incomplete attempt.
* Active OCR pointer and OCRResult are reusable.
* Recovery resumes from translation without rerunning OCR.

### R02: Crash after provider temp file but before artifact registration

Expected:

* Temp/orphan file is not treated as official artifact.
* Recovery can mark attempt abandoned or retry.
* ArtifactService and Repository boundaries remain clear.

### R03: Crash after artifact registration but before active pointer update

Expected:

* Registered artifact remains official but unselected.
* Recovery does not treat it as export-effective by timestamp.
* WorkflowLoopEngine can decide reuse, retry, pause, or block.

### R04: Missing active artifact

Expected:

* Repository can load artifact metadata.
* ArtifactService can mark storage state as missing.
* WorkflowLoopEngine decides rebuild, warning, pause, or block.
* ArtifactService does not make workflow decisions.

## 5. Idempotency scenarios

### I01: Rerun unchanged OCR stage

Expected:

* Repository can find matching OCRResult by input/config/provider/tool key.
* Workflow can reuse result without duplicate provider call.
* Reuse is auditable.

### I02: Rerun unchanged translation stage

Expected:

* Repository can find matching TranslationResult by source OCR, source hash, context, glossary, provider, model, prompt, and config key.
* Reuse does not create duplicate active result rows.
* Locked translation is not overwritten automatically.

### I03: Rerun unchanged cleaned/typeset artifacts

Expected:

* Repository and ArtifactService can verify artifact provenance and hash.
* Existing artifact can be reused if present and compatible.
* Missing or incompatible artifact does not become export-effective.

## 6. Issue and export gate scenarios

### Q01: Provider refusal persistence

Expected:

* ToolRunLog records refusal metadata.
* WorkflowAttempt status can be `refused`.
* QualityIssue records refusal.
* WorkflowDecision records fallback, pause, warning, skip, or block.
* No bypass/evasion data is introduced.

### Q02: Blocking issue prevents normal readiness/export

Expected:

* Repository can query open blocking QualityIssues by Page or Batch scope.
* Normal export/readiness is blocked.
* Warning export remains controlled by ProcessingProfileSnapshot.

### Q03: Cleaning skip creates warning-bearing state

Expected:

* Cleaning skip can be persisted.
* Warning issue remains visible.
* Page cannot become pure `ready_for_export`.

## 7. User edit and stale scenarios

### S01: OCR edit

Expected:

* New OCRResult is created.
* Active OCR pointer is updated.
* Translation, translation_check, and typesetting statuses become stale.
* Downstream issues can become stale or superseded.
* Updates are atomic enough to prevent pointer/status drift.

### S02: Translation edit

Expected:

* New TranslationResult is created.
* Active translation pointer is updated.
* Translation check and typesetting become stale.
* Old typeset artifact remains preview/history, not export-effective.

## 8. Migration scenarios

### M01: Initialize app.db

Expected:

* app.db migration state can be tracked.
* Global Project registry and provider/profile templates can be created later without changing project.db design.

### M02: Initialize project.db

Expected:

* project.db migration state can be tracked independently.
* ProjectMetadata can verify the database belongs to the selected Project.
* Project migration can be run independently per Project.

### M03: Add enum value later

Expected:

* Stable string values can evolve without rewriting historical audit rows.
* Existing attempts, decisions, issues, and artifacts remain readable.

## 9. Boundary failure checks

The final design fails if:

* Provider Adapter accesses SQLite.
* Provider Adapter writes repository records.
* ArtifactService decides retry, fallback, warning, or block.
* QualityCheckService advances workflow state.
* WorkflowLoopEngine depends directly on SQL or ORM session internals.
* UI or API handler bypasses Repository / DAO.
* Recovery relies only on Page.status.
* Active result is derived from latest timestamp instead of active pointer.
* Image files or large payloads are stored in SQLite.
* The design requires full API, frontend, real provider integration, or P1/P2 features before MVP-0.