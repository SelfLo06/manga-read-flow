# Workflow State / Workflow Loop Detailed Design GOAL

## 1. Objective

Define the MVP Workflow State / Workflow Loop detailed design for the single-Page processing workflow.

This design must make the workflow implementable, reviewable, recoverable, and testable before coding begins.

The design should answer:

* What workflow stages exist in MVP.
* What state vocabulary is used by `ProcessingTask`, `WorkflowAttempt`, `Page`, and `TextBlock`.
* How stages advance from detection to export readiness.
* How retry, fallback, skip, warning, pause, cancel, and block decisions are made.
* How stale state propagates after user edits.
* How crash recovery reconstructs workflow state.
* How minimal `ProcessingProfileSnapshot` policy inputs affect the loop.

## 2. Scope

This design covers:

* MVP single-Page workflow state.
* Page-level and TextBlock-level stage statuses.
* `ProcessingTask` lifecycle.
* `WorkflowAttempt` lifecycle.
* `WorkflowDecision` decision types.
* Retry budget and fallback decision rules.
* Stale propagation rules for OCR edit and translation edit.
* Crash recovery rules.
* Export readiness rules.
* Minimal ProcessingProfile policy inputs needed by WorkflowLoopEngine.

## 3. Non-goals

This design does not cover:

* Production code.
* SQL DDL.
* ORM mappings.
* Database migration files.
* Full API route design.
* Full Provider Adapter interface design.
* Full ArtifactService design.
* Full QualityIssue taxonomy.
* Frontend UI design.
* Real OCR / translation / cleaning / typesetting tool parameters.
* Batch-scale optimization.
* P1/P2 features such as forced export, multi-page context translation, GeometryRevision, advanced review UI, or professional typesetting.

## 4. Source documents

The design must stay consistent with:

* `docs/SRS-v1.0.md`
* `docs/HLD.md`
* `docs/PROJECT-PLAN.md`
* `docs/design/data-model/final/data-model-dd-v0.1.md`
* `docs/design/data-model/final/schema-outline.md`
* `docs/design/data-model/final/state-data-impact.md`
* `docs/design/data-model/final/open-questions.md`
* `docs/design/data-model-detailed-design-template.md`

## 5. Architecture invariants

The design must preserve these rules:

* Provider Adapter only calls tools and returns structured results or standardized errors.
* Provider Adapter must not access SQLite.
* Provider Adapter must not register official artifacts.
* Provider Adapter must not create `QualityIssue`.
* Provider Adapter must not decide retry, fallback, skip, warning, pause, or block.
* ArtifactService is the only official artifact lifecycle entry.
* Repository / DAO is the only SQLite access entry.
* WorkflowLoopEngine owns workflow decisions.
* QualityCheckService checks outputs and classifies issues, but does not advance workflow state.
* Original images are never overwritten.
* Image files and large payloads are not stored in SQLite.
* Active pointers are the source of truth for current OCR, translation, cleaned image, and typeset image.
* Recovery must not rely only on `Page.status`.
* Normal export blocks unresolved blocking `QualityIssue`.
* Warning export follows `ProcessingProfileSnapshot`.

## 6. Required design outputs

The final synthesis should produce:

* `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
* `docs/design/workflow-state/final/state-vocabulary.md`
* `docs/design/workflow-state/final/stage-transition-table.md`
* `docs/design/workflow-state/final/decision-matrix.md`
* `docs/design/workflow-state/final/recovery-rules.md`
* `docs/design/workflow-state/final/stale-propagation-rules.md`
* `docs/design/workflow-state/final/open-questions.md`

ADR files are optional unless a decision is controversial or likely to affect implementation.

## 7. Required design questions

The proposal and final synthesis must answer:

* What are the MVP workflow stages?
* Which statuses are allowed for `ProcessingTask`?
* Which statuses are allowed for `WorkflowAttempt`?
* Which statuses are allowed for Page-level workflow state?
* Which statuses are allowed for TextBlock stage state?
* When is a `WorkflowAttempt` created?
* When is a `WorkflowDecision` created?
* What decision types exist?
* Which decisions consume retry budget?
* When does the workflow fallback to another provider?
* When does the workflow skip a target?
* When does the workflow mark a warning?
* When does the workflow block?
* When does the workflow pause for user action?
* How are OCR edits propagated downstream?
* How are translation edits propagated downstream?
* How is a stale running task reconciled after crash?
* How is export readiness computed?
* What minimal ProcessingProfile policy fields are needed?

## 8. Scope control

Keep this design small enough for MVP implementation.

Prefer explicit tables and scenario rules over abstract frameworks.

Do not introduce a generic workflow engine, plugin system, distributed queue, multi-worker orchestration, or full BPM/state-machine library unless the design proves it is required for MVP.

## 9. Exit criteria

This design goal is complete when:

* All required design questions have a clear answer.
* HARNESS scenarios are marked PASS or explicitly deferred with reason.
* No architecture invariant is violated.
* The design can be implemented with FakeProvider in a single-Page backend vertical slice.
* P1/P2 features are not required for MVP.
