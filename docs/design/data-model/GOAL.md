# Data Model Detailed Design Goal

## 1. Task

Design the detailed data model for the Manga Translation and Basic Typesetting Workflow application.

This task is design-only. Do not implement code, migrations, ORM models, API handlers, frontend pages, or provider integrations unless explicitly requested later.

## 2. Inputs

Read these documents first:

- `docs/SRS-v1.0.md`
- `docs/HLD.md`

Treat them as authoritative. If they conflict, prefer `docs/HLD.md` for architecture decisions and record the conflict in `open-questions.md`.

## 3. Design Scope

Produce a detailed data model that supports:

- Project / Batch / Page / TextBlock hierarchy
- Project-level glossary and glossary versioning
- Page-level translation context
- OCR result versioning
- Translation result versioning
- Active result pointer
- Artifact metadata
- WorkflowAttempt and WorkflowDecision
- ProcessingTask
- ProcessingProfile
- QualityIssue
- ToolRunLog
- ExportRecord
- app.db + project.db separation
- soft delete / trash
- migration readiness
- restart recovery
- idempotent processing
- local filesystem artifact lifecycle

## 4. Non-goals

Do not design:

- Full API schema
- Full SQL DDL
- Full SQLAlchemy implementation
- Full frontend UI
- Prompt templates
- OCR / translation / cleaning / typesetting algorithms
- Cloud deployment
- Multi-user permission system
- Professional scanlation workflow

## 5. Required Deliverables

Each design proposal must include:

1. Entity list
2. Entity responsibility
3. Relationship map
4. Ownership boundary
5. app.db vs project.db placement
6. Key fields, without full DDL
7. Important indexes and uniqueness constraints
8. Deletion / soft delete behavior
9. Versioning rules
10. Active pointer rules
11. State-related fields
12. Artifact relationship
13. Idempotency keys
14. Migration considerations
15. Risks and trade-offs
16. Open questions

The final synthesized design must produce:

- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/data-model/final/erd.mmd`
- `docs/design/data-model/final/schema-outline.md`
- `docs/design/data-model/final/state-data-impact.md`
- `docs/design/data-model/final/open-questions.md`
- ADR files under `docs/design/data-model/adr/`

## 6. Quality Bar

A valid design must satisfy these invariants:

- No image BLOBs in SQLite.
- Original images are never overwritten.
- Filesystem artifacts are referenced by metadata records.
- Every external tool run can be traced.
- Every generated OCR / translation result is immutable.
- User edits create new result versions.
- Current effective OCR / translation is selected by active pointer or active flag.
- WorkflowAttempt metadata is always persisted.
- Large successful raw payloads may be cleaned by policy.
- Failed attempt artifacts are persisted by default.
- Project data is isolated from other Projects.
- GlossaryTerm belongs to Project.
- TranslationResult records glossary_version.
- Provider adapters never own persistence.
- API keys are not stored in project.db.
- Debug artifacts are explicitly marked.
- Normal export is blocked by unresolved blocking issues.
- Warning export is controlled by ProcessingProfile.
- The model supports restart recovery without re-running completed stages.
- The model supports partial failure and local retry at Page and TextBlock level.

## 7. Evaluation Scenarios

The design must be validated against these scenarios:

1. Create Project, upload one Page, process successfully, export.
2. App crashes after OCR but before translation; restart and continue.
3. OCR result is manually edited; translation and typesetting become stale.
4. Translation result is manually edited; typesetting becomes stale.
5. Cloud translation provider refuses one TextBlock; fallback or manual path is recorded.
6. Cleaning fails for complex background; TextBlock is skipped with warning.
7. Typesetting overflows after minimum font size; result is still previewable with warning.
8. Glossary is edited after translation; old TranslationResult keeps previous glossary_version.
9. A failed LLM JSON response is stored as failed attempt artifact.
10. Successful LLM raw payload is cleaned under default policy but attempt metadata remains.
11. Project is soft-deleted and can be restored before permanent deletion.
12. Two Projects contain the same page filename but remain isolated.
13. Export is attempted with unresolved blocking issue and is rejected.
14. Export is attempted with warning only and follows ProcessingProfile policy.
15. User re-runs a TextBlock with unchanged input and config; cache/idempotency prevents duplicate provider call.

## 8. Output Style

Be precise. Use tables where helpful.

Avoid vague claims such as “easy to extend” unless you explain what future change is supported and which design decision enables it.

Every major decision must include rationale and rejected alternatives.