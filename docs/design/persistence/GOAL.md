# Persistence Readiness Design GOAL

## 1. Objective

Define the minimal persistence readiness design needed before implementing the FakeProvider single-Page backend vertical slice.

This design must explain how the existing data model, workflow-state design, and execution contracts can be implemented safely through Repository / DAO, Unit of Work, transaction boundaries, and migration strategy.

The goal is not to redesign the data model. The goal is to make persistence implementation ready.

## 2. Scope

This design covers:

* Minimal `app.db` / `project.db` persistence boundary.
* Minimal repository / DAO responsibilities.
* Unit of Work and transaction boundary guidance.
* Minimal migration strategy.
* Minimal table implementation priority for FakeProvider single-Page backend vertical slice.
* Persistence support for active pointers.
* Persistence support for `WorkflowAttempt`, `WorkflowDecision`, `QualityIssue`, `ProcessingArtifact`, `ToolRunLog`, and result versions.
* Persistence support for crash recovery and idempotent rerun.
* Repository interfaces needed by WorkflowLoopEngine, ArtifactService, QualityCheckService, StageExecutor, and Application Service.

## 3. Non-goals

This design does not cover:

* Production code.
* SQL DDL.
* SQLAlchemy model code.
* Alembic migration files.
* Full repository method implementation.
* FastAPI route design.
* Frontend UI.
* Real Provider integration.
* Real OCR / translation / cleaning / typesetting parameters.
* Real translation prompt templates.
* Complete export design.
* Complete ProcessingProfile UI/config design.
* P1/P2 features.

## 4. Source documents

Use these inputs:

* `AGENTS.md`
* `docs/SRS-v1.0.md`
* `docs/HLD.md`
* `docs/PROJECT-PLAN.md`
* `docs/design/data-model/final/data-model-dd-v0.1.md`
* `docs/design/data-model/final/schema-outline.md`
* `docs/design/data-model/final/state-data-impact.md`
* `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
* `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`

## 5. Software engineering principles

The final design must apply these principles as explicit checks:

* Single Responsibility: Repository / DAO owns persistence access only.
* Information Hiding: callers must not depend on table layout, SQL details, or ORM session internals.
* High Cohesion / Low Coupling: persistence contracts should be grouped by workflow need, not by convenience hacks across modules.
* Dependency Inversion: WorkflowLoopEngine, ArtifactService, and QualityCheckService depend on repository contracts, not concrete ORM details.
* Testability: the design must support temporary SQLite integration tests.
* Recoverability: crash recovery queries must be explicit and must not rely only on `Page.status`.
* Traceability: attempts, decisions, issues, artifacts, tool logs, active pointer changes, and result versions must remain auditable.
* Scope Control: do not introduce a generic persistence framework or full enterprise repository layer for MVP.

## 6. Architecture invariants

The design must preserve:

* Repository / DAO is the only SQLite access entry.
* Provider Adapter must not access SQLite.
* Provider Adapter must not register official artifacts.
* ArtifactService owns official artifact lifecycle but uses Repository / DAO for metadata persistence.
* QualityCheckService creates/classifies issue drafts or issues but does not advance workflow state.
* WorkflowLoopEngine owns workflow decisions.
* Active pointers are the source of truth for current OCR, translation, cleaned image, and typeset image.
* Images and large payloads are not stored in SQLite.
* Original images are never overwritten.
* Recovery must not rely only on `Page.status`.
* Normal export blocks unresolved open blocking `QualityIssue`.

## 7. Required design questions

The final design must answer:

* Which tables/entities are required for the FakeProvider single-Page vertical slice?
* Which data can be deferred until after MVP-0?
* What belongs in `app.db` and what belongs in `project.db`?
* What repository groups are needed?
* What Unit of Work boundary is required?
* Which writes must be committed atomically?
* How are active pointer updates protected from drift?
* How are `WorkflowAttempt`, `ToolRunLog`, `ProcessingArtifact`, `QualityIssue`, `WorkflowDecision`, result rows, and stage statuses persisted around one stage execution?
* How does recovery find stale running tasks and abandoned attempts?
* How does idempotent rerun find reusable OCR, translation, cleaned, and typeset results?
* How are migrations tracked for `app.db` and each `project.db`?
* What minimal constraints/indexes are needed for correctness and recovery?
* What implementation details should remain deferred?

## 8. Required outputs

Final synthesis should produce:

* `docs/design/persistence/final/persistence-readiness-dd-v0.1.md`
* `docs/design/persistence/final/repository-contract-minimal.md`
* `docs/design/persistence/final/unit-of-work-and-transactions.md`
* `docs/design/persistence/final/migration-strategy-minimal.md`
* `docs/design/persistence/final/fakeprovider-persistence-readiness.md`
* `docs/design/persistence/final/open-questions.md`

ADR files are optional. Create ADRs only for decisions that affect implementation direction.

## 9. Exit criteria

This goal is complete when:

* Repository / DAO boundaries are clear.
* Minimal persistence scope for FakeProvider single-Page slice is clear.
* Transaction boundaries are clear enough to implement safely.
* Recovery and idempotency have repository support.
* No architecture invariant is violated.
* No P1/P2 feature is required for MVP-0.