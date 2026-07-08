# MVP-0 FakeProvider Single-Page Backend Slice GOAL

## 1. Objective

Create an implementation-ready plan for the MVP-0 FakeProvider single-Page backend vertical slice.

The plan must break the first backend implementation into small, verifiable slices that can be assigned to Codex without scope drift.

The goal is not to implement code in this planning step. The goal is to define the implementation sequence, file boundaries, validation commands, test strategy, commit strategy, and slice-level acceptance criteria.

## 2. Target milestone

The target milestone is:

```text
create Project
-> create Batch
-> import one Page
-> register original artifact
-> run deterministic FakeProvider workflow
-> create TextBlocks
-> create OCRResults
-> create TranslationResults
-> register cleaned and typeset artifacts
-> persist WorkflowAttempt, ToolRunLog, QualityIssue, WorkflowDecision
-> update active pointers
-> support idempotent rerun
-> support selected crash/recovery scenarios
-> reach ready_for_export or a documented warning/block state
```

MVP-0 stops at:

```text
ready_for_export
```

Actual export image output, ZIP output, manifest artifact, ExportRecord, FastAPI routes, and Web UI are out of scope unless a later goal explicitly adds them.

## 3. Scope

This planning package covers:

* Minimal backend package/module structure.
* Minimal implementation slice order.
* Minimal test and validation strategy.
* Temporary SQLite + temporary filesystem workspace validation.
* FakeProvider deterministic modes.
* Repository / Unit of Work implementation order.
* ArtifactService implementation order.
* WorkflowLoopEngine / StageExecutor implementation order.
* QualityCheckService fake/minimal implementation order.
* Crash recovery and idempotency validation order.
* Codex task prompts for implementation slices.
* Commit and review strategy.

## 4. Non-goals

This planning package does not cover:

* Production implementation.
* Full SQL DDL specification beyond referencing existing design.
* Full ORM model documentation.
* Full FastAPI route design.
* Frontend UI.
* Real OCR provider integration.
* Real translation provider integration.
* Real cleaner/typesetter provider integration.
* Real translation prompt templates.
* Actual export output, ZIP, manifest, or ExportRecord implementation.
* Batch-scale workflow.
* Multi-page context.
* Provider configuration UI.
* Secret storage integration.
* Desktop packaging.
* P1/P2 features.

## 5. Source documents

Use these authoritative inputs:

* `AGENTS.md`
* `docs/SRS-v1.0.md`
* `docs/HLD.md` or `docs/HLD-v0.2.md`
* `docs/PROJECT-PLAN.md`
* `docs/design/data-model/final/data-model-dd-v0.1.md`
* `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
* `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`
* `docs/design/persistence/final/persistence-readiness-dd-v0.1.md`
* `docs/design/persistence/final/repository-contract-minimal.md`
* `docs/design/persistence/final/unit-of-work-and-transactions.md`
* `docs/design/persistence/final/migration-strategy-minimal.md`
* `docs/design/persistence/final/fakeprovider-persistence-readiness.md`

## 6. Engineering principles

The implementation plan must apply these principles explicitly:

* Vertical Slice First: implement one end-to-end single-Page backend slice before broadening features.
* Validation-Driven Development: each slice must have a validation command or test target.
* Small Batches: each implementation task should produce a small, reviewable diff.
* Information Hiding: implementation tasks must preserve Repository, ArtifactService, Provider Adapter, and WorkflowLoopEngine boundaries.
* Dependency Inversion: workflow code depends on contracts, not concrete SQLite/ORM internals.
* Fail-Fast Scope Control: any task that requires UI, real providers, export output, P1/P2, or broad refactoring must stop and report.
* Recoverability First: recovery and idempotency are not afterthoughts; they must be planned as early backend validations.
* Traceability: attempts, decisions, issues, artifacts, tool logs, and active pointer changes must remain inspectable in tests.

## 7. Required planning outputs

Final planning should produce:

* `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`
* `docs/implementation/mvp0-fakeprovider-slice/slices/01-foundation-and-project-store.md`
* `docs/implementation/mvp0-fakeprovider-slice/slices/02-import-and-artifactservice.md`
* `docs/implementation/mvp0-fakeprovider-slice/slices/03-repository-and-uow-core.md`
* `docs/implementation/mvp0-fakeprovider-slice/slices/04-fakeprovider-and-stageexecutor.md`
* `docs/implementation/mvp0-fakeprovider-slice/slices/05-workflowloop-happy-path.md`
* `docs/implementation/mvp0-fakeprovider-slice/slices/06-quality-issues-and-readiness.md`
* `docs/implementation/mvp0-fakeprovider-slice/slices/07-idempotency-and-recovery.md`
* `docs/implementation/mvp0-fakeprovider-slice/checklists/implementation-readiness-checklist.md`
* `docs/implementation/mvp0-fakeprovider-slice/checklists/codex-task-template.md`
* `docs/implementation/mvp0-fakeprovider-slice/open-questions.md`

The exact slice count may be adjusted, but the final plan must keep implementation tasks small and verifiable.

## 8. Hard boundaries

The implementation plan must not ask Codex to:

* bypass Repository / DAO and write SQLite directly from workflow modules;
* let Provider Adapter access SQLite;
* let Provider Adapter register official artifacts;
* let Provider Adapter create QualityIssues;
* let ArtifactService decide retry, fallback, warning, block, or readiness;
* let QualityCheckService advance workflow state;
* let StageExecutor update active pointers or create WorkflowDecision;
* use Page.status as recovery truth;
* select latest result or artifact by timestamp;
* store image bytes or large payloads in SQLite;
* overwrite original images;
* implement real providers before FakeProvider validation;
* implement Web UI or FastAPI routes in MVP-0 planning;
* implement actual export output unless a later goal explicitly changes scope.

## 9. Exit criteria

Goal 4 is complete when:

* The implementation sequence is clear.
* Each implementation slice has objective, allowed files, forbidden files, validation commands, and acceptance criteria.
* The plan starts with FakeProvider and temporary SQLite, not real providers.
* The plan includes at least one happy path, one issue-bearing path, one idempotency path, and one recovery path.
* The plan preserves all architecture boundaries from prior designs.
* The plan is ready to generate small Codex implementation goals.