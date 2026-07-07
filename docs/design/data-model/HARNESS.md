# Data Model Design Harness

## 1. Purpose

This harness validates whether a proposed data model supports the SRS and HLD requirements for recovery, idempotency, artifact traceability, partial retry, project isolation, and one-click processing.

## 2. Hard Invariants

A proposal fails if any hard invariant is violated.

- No image BLOBs in SQLite.
- Original image is immutable.
- Project data is isolated.
- Page belongs to Batch.
- Batch belongs to Project.
- TextBlock belongs to Page.
- Detection creates TextBlock.
- OCRResult is versioned.
- TranslationResult is versioned.
- User edits create new versions.
- Active OCR and active Translation are explicit.
- TranslationResult records glossary_version.
- WorkflowAttempt metadata is always persisted.
- WorkflowDecision is persisted.
- QualityIssue supports discovered_stage and root_stage.
- ProcessingArtifact records file path, hash, type, and ownership.
- Failed attempt artifacts are persisted by default.
- Successful raw payload retention is configurable.
- Provider adapters do not own persistence.
- API keys are not stored in project.db.
- Export checks unresolved blocking issues.

## 3. Required Scenario Replays

Every proposal must explain these scenarios:

### S1: Happy path
Project → Batch → Page → TextBlocks → OCR → Page-level Translation → Cleaning → Typesetting → Export

### S2: Restart after OCR
App stops after OCR. On restart, translation continues without re-running OCR.

### S3: OCR edit
User edits OCR. Old OCRResult remains. New OCRResult becomes active. Translation and typesetting become stale.

### S4: Translation edit
User edits translation. Old TranslationResult remains. New TranslationResult becomes active. Typesetting becomes stale.

### S5: Provider refusal
Cloud translation provider refuses. Record ToolRunLog, WorkflowAttempt, QualityIssue, WorkflowDecision. Apply fallback or blocked policy.

### S6: Complex cleaning skipped
Cleaning is skipped for one TextBlock. Page can still become ready_for_export_with_warnings.

### S7: Typeset overflow
Typesetting overflows after minimum font size. Keep preview artifact and mark QualityIssue.

### S8: Glossary changed
Glossary changes after translation. Old TranslationResult keeps old glossary_version.

### S9: Failed raw payload
Invalid LLM JSON is preserved as failed attempt artifact.

### S10: Project soft delete
Project is soft-deleted. Files move to trash or are marked for trash. Permanent deletion requires confirmation.

## 4. Evaluation Criteria

Score each proposal from 0 to 3:

- Recovery support
- Idempotency support
- Traceability
- Simplicity
- Migration readiness
- ORM friendliness
- Avoidance of over-design
- Artifact lifecycle clarity
- QualityIssue expressiveness
- Project isolation
- Future extensibility

## 5. Output Contract

Each proposal must include:

- entity table
- relationship summary
- ownership rules
- app.db/project.db split
- state impact
- artifact impact
- deletion policy
- idempotency policy
- migration notes
- rejected alternatives
- unresolved questions

## 6. Design Round Validation Gates

Before a proposal is considered complete:

- The proposal follows the required structure.
- The proposal explicitly discusses all required entities.
- The proposal validates all required scenarios.
- The proposal lists open questions instead of silently guessing.
- The proposal does not implement code.
- The proposal does not edit final design files.
- The proposal does not edit ADR files in proposal rounds.
- The proposal does not modify files owned by other agents.
- The proposal does not introduce features outside SRS/HLD.
- The proposal does not store images as SQLite BLOBs.
- The proposal does not put API keys or secrets into project.db, logs, examples, or artifacts.

Before synthesis:

- All proposal files exist.
- Cross-review exists.
- Blocking review issues are resolved or explicitly accepted as open questions.
- Remaining open questions do not block MVP data model design.

Before final acceptance:

- All hard invariants pass.
- All scenario replays are PASS or explicitly marked as non-blocking open questions.
- ADRs exist for major decisions.
- `final/data-model-dd-v0.1.md` is internally consistent with `schema-outline.md`, `erd.mmd`, and `state-data-impact.md`.