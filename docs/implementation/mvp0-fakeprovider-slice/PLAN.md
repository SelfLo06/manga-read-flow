# MVP-0 FakeProvider Single-Page Backend Slice PLAN

This plan defines the implementation planning process for Goal 4.

This is not an implementation task.
This is an implementation planning task.

Do not write production code.
Do not create SQL DDL.
Do not create ORM models.
Do not create Alembic migrations.
Do not create FastAPI routes.
Do not create frontend code.
Do not integrate real OCR, translation, cleaning, or typesetting providers.
Do not implement export output, ZIP, manifest, or ExportRecord.

The goal is to produce small, verifiable implementation slices for the next backend implementation phase.

---

## 1. Planning Principles

The final plan must apply these principles:

* Vertical Slice First: prove one Project / one Batch / one Page before broadening.
* Validation-Driven Development: every slice must have a test or validation command.
* Small Batches: every implementation task must be small enough for review.
* Boundary Preservation: do not bypass Repository, ArtifactService, Provider Adapter, QualityCheckService, or WorkflowLoopEngine boundaries.
* FakeProvider First: validate workflow mechanics before real provider integration.
* Recoverability First: idempotency and recovery are part of MVP-0 planning, not future cleanup.
* Scope Control: stop at `ready_for_export`.

---

## 2. Authoritative Inputs

Use these source documents:

* `AGENTS.md`
* `docs/SRS-v1.0.md`
* `docs/HLD.md`
* `docs/PROJECT-PLAN.md`
* `docs/design/data-model/final/data-model-dd-v0.1.md`
* `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
* `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`
* `docs/design/persistence/final/persistence-readiness-dd-v0.1.md`
* `docs/design/persistence/final/repository-contract-minimal.md`
* `docs/design/persistence/final/unit-of-work-and-transactions.md`
* `docs/design/persistence/final/migration-strategy-minimal.md`
* `docs/design/persistence/final/fakeprovider-persistence-readiness.md`
* `docs/implementation/mvp0-fakeprovider-slice/GOAL.md`
* `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
* `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

---

## 3. Required Outputs

Create or update only files under:

```text
docs/implementation/mvp0-fakeprovider-slice/
```

Required final outputs:

```text
docs/implementation/mvp0-fakeprovider-slice/slices/01-foundation-and-project-store.md
docs/implementation/mvp0-fakeprovider-slice/slices/02-repository-and-uow-core.md
docs/implementation/mvp0-fakeprovider-slice/slices/03-artifactservice-and-import.md
docs/implementation/mvp0-fakeprovider-slice/slices/04-fakeprovider-and-stageexecutor.md
docs/implementation/mvp0-fakeprovider-slice/slices/05-workflowloop-happy-path.md
docs/implementation/mvp0-fakeprovider-slice/slices/06-quality-issues-and-readiness.md
docs/implementation/mvp0-fakeprovider-slice/slices/07-idempotency-and-recovery.md
docs/implementation/mvp0-fakeprovider-slice/checklists/implementation-readiness-checklist.md
docs/implementation/mvp0-fakeprovider-slice/checklists/codex-task-template.md
docs/implementation/mvp0-fakeprovider-slice/reviews/01-plan-review.md
docs/implementation/mvp0-fakeprovider-slice/open-questions.md
```

Do not modify final design documents from previous goals.

---

## 4. Slice File Structure

Each slice file must use this structure:

```text
# Slice N: <Name>

## 1. Objective
## 2. Why this slice comes now
## 3. Inputs from prior designs
## 4. Allowed files or directories to change during implementation
## 5. Forbidden changes
## 6. Implementation tasks
## 7. Validation command or test target
## 8. Acceptance criteria
## 9. Failure cases to test
## 10. Commit strategy
## 11. Risks and scope traps
## 12. Codex implementation prompt
```

Every slice must include a ready-to-use Codex prompt.

The Codex prompt must state:

* goal;
* source documents;
* allowed files;
* forbidden files;
* implementation boundaries;
* validation command;
* expected output;
* commit rule;
* stop conditions.

---

# 5. Required Implementation Slices

## Slice 01: Foundation and Project Store

Output:

```text
docs/implementation/mvp0-fakeprovider-slice/slices/01-foundation-and-project-store.md
```

Purpose:

Plan the minimal backend foundation for temporary `app.db`, temporary `project.db`, project workspace directories, project identity, migration ledger placeholders, and Project open verification.

Must cover:

* minimal Python package/module layout;
* temporary workspace layout for tests;
* app.db initialization plan;
* project.db initialization plan;
* ProjectMetadata verification;
* independent migration ledger placeholder;
* no real Alembic implementation unless explicitly deferred to later;
* temporary SQLite integration test entry.

Validation target:

```text
pytest tests/integration/test_project_store_init.py
```

Acceptance must prove:

* app.db can initialize;
* project.db can initialize;
* project identity is verified;
* project repositories are not exposed before readiness;
* no production UI/API exists.

---

## Slice 02: Repository and Unit of Work Core

Output:

```text
docs/implementation/mvp0-fakeprovider-slice/slices/02-repository-and-uow-core.md
```

Purpose:

Plan the minimal repository and Unit of Work implementation needed by the FakeProvider slice.

Must cover:

* repository groups to implement first;
* minimal DTO/evidence objects;
* transaction helper boundary;
* no generic `Repository<T>`;
* no ORM/session leakage;
* expected-state guard pattern;
* acceptance transaction placeholder;
* narrow `StageEvidenceWriter`.

Validation target:

```text
pytest tests/integration/test_repository_uow_core.py
```

Acceptance must prove:

* repository contracts hide SQLite details;
* WorkflowLoopEngine-facing code does not need SQL/session objects;
* StageExecutor can only use narrow evidence writer;
* provider code has no repository dependency.

---

## Slice 03: ArtifactService and Import

Output:

```text
docs/implementation/mvp0-fakeprovider-slice/slices/03-artifactservice-and-import.md
```

Purpose:

Plan original image import and official artifact registration.

Must cover:

* project-relative artifact paths;
* original artifact registration;
* file hash and metadata;
* Page original artifact pointer;
* no image bytes in SQLite;
* original image never overwritten;
* import as ApplicationService/import use case for MVP-0;
* no actual export output.

Validation target:

```text
pytest tests/integration/test_import_and_artifactservice.py
```

Acceptance must prove:

* original image is copied or stored into workspace;
* artifact metadata is persisted;
* Page points to original artifact id;
* original image bytes stay on filesystem;
* deleting or corrupting artifact can be detected later.

---

## Slice 04: FakeProvider and StageExecutor

Output:

```text
docs/implementation/mvp0-fakeprovider-slice/slices/04-fakeprovider-and-stageexecutor.md
```

Purpose:

Plan deterministic FakeProvider contracts and StageExecutor boundary.

Must cover:

* fake detection;
* fake OCR;
* fake translation;
* fake cleaning;
* fake typesetting;
* fake provider failure modes;
* `ProviderResult` envelope use;
* temp file outputs;
* StageExecutor input/output;
* StageEvidenceWriter usage only;
* no active pointer updates by StageExecutor;
* no WorkflowDecision creation by StageExecutor.

Validation target:

```text
pytest tests/integration/test_fakeprovider_stageexecutor.py
```

Acceptance must prove:

* FakeProvider can produce deterministic success outputs;
* FakeProvider can produce invalid translation and refusal outputs;
* StageExecutor records tool evidence only;
* provider call holds no SQLite write transaction;
* temp outputs are not official artifacts until ArtifactService registration.

---

## Slice 05: WorkflowLoop Happy Path

Output:

```text
docs/implementation/mvp0-fakeprovider-slice/slices/05-workflowloop-happy-path.md
```

Purpose:

Plan the first full happy-path workflow from imported Page to `ready_for_export`.

Must cover:

* processing task creation;
* profile snapshot bootstrap;
* attempt reservation;
* stage progression;
* acceptance transaction;
* TextBlock creation;
* OCRResult creation;
* TranslationResult creation;
* active pointer updates;
* cleaned/typeset artifact pointer updates;
* final `export_check` readiness;
* no actual export output.

Validation target:

```text
pytest tests/integration/test_workflow_happy_path.py
```

Acceptance must prove:

* one Project / one Batch / one Page can run through fake detection, OCR, translation, cleaning, typesetting, and export_check;
* active OCR, translation, cleaned, and typeset pointers are set;
* WorkflowAttempt, ToolRunLog, WorkflowDecision, ProcessingArtifact, and profile snapshot evidence exist;
* Page reaches `ready_for_export`;
* no ExportRecord or output export artifact is required.

---

## Slice 06: Quality Issues and Readiness

Output:

```text
docs/implementation/mvp0-fakeprovider-slice/slices/06-quality-issues-and-readiness.md
```

Purpose:

Plan issue-bearing paths and readiness gating.

Must cover:

* minimal QualityCheckService behavior;
* invalid translation;
* partial translation;
* provider refusal;
* cleaning skip;
* typesetting overflow;
* open blocking QualityIssue;
* warning readiness;
* readiness query;
* WorkflowDecisionIssue link when decision links persisted issues;
* no policy bypass/evasion.

Validation target:

```text
pytest tests/integration/test_quality_issues_and_readiness.py
```

Acceptance must prove:

* invalid/partial translation creates issue evidence;
* provider refusal creates ToolRunLog, refused attempt, QualityIssue, WorkflowDecision, and decision-issue link;
* open blocking issue prevents pure `ready_for_export`;
* warning state remains visible and does not silently become pure readiness;
* QualityCheckService does not advance workflow state.

---

## Slice 07: Idempotency and Recovery

Output:

```text
docs/implementation/mvp0-fakeprovider-slice/slices/07-idempotency-and-recovery.md
```

Purpose:

Plan the first idempotency and crash recovery validations.

Must cover:

* rerun unchanged Page;
* OCR reuse;
* translation reuse;
* cleaned/typeset artifact reuse;
* auditable reuse attempt or decision;
* crash after OCR acceptance;
* crash after artifact registration before acceptance;
* missing active artifact;
* recovery without Page.status-only logic;
* official unselected artifact behavior.

Validation target:

```text
pytest tests/integration/test_idempotency_and_recovery.py
```

Acceptance must prove:

* unchanged rerun avoids duplicate provider calls;
* reuse is auditable;
* crash after OCR acceptance resumes from translation without OCR rerun;
* registered-but-unselected artifact is not selected by timestamp;
* missing active artifact becomes `storage_state = missing`;
* WorkflowLoopEngine decides rebuild/warning/pause/block.

---

# 6. Implementation Readiness Checklist

Create:

```text
docs/implementation/mvp0-fakeprovider-slice/checklists/implementation-readiness-checklist.md
```

The checklist must include:

```text
Project foundation
Repository boundary
Unit of Work boundary
ArtifactService import
FakeProvider modes
StageExecutor boundary
WorkflowLoop happy path
QualityIssue paths
Readiness gate
Idempotency
Recovery
Forbidden scope
Commit hygiene
```

Each checklist item must be checkable as:

```text
PASS / FAIL / N/A
```

---

# 7. Codex Task Template

Create:

```text
docs/implementation/mvp0-fakeprovider-slice/checklists/codex-task-template.md
```

The template must include:

```text
# Codex Implementation Task

## Goal
## Source documents
## Allowed files
## Forbidden files
## Required behavior
## Validation command
## Acceptance criteria
## Stop conditions
## Commit rule
## Final report format
```

Stop conditions must include:

* unrelated dirty working tree;
* need for real provider;
* need for UI/API/export output;
* need to modify previous final design docs;
* broken architecture boundary;
* validation command unavailable or failing for unrelated reason.

---

# 8. Plan Review

Create:

```text
docs/implementation/mvp0-fakeprovider-slice/reviews/01-plan-review.md
```

The review must check the final plan against `HARNESS.md`.

It must include:

1. Scenario replay against HARNESS.
2. Missing implementation slices.
3. Overly large slices.
4. Missing validation commands.
5. Architecture boundary risks.
6. Scope creep risks.
7. Whether Goal 4 is ready to generate Codex implementation tasks.

---

# 9. Open Questions

Update:

```text
docs/implementation/mvp0-fakeprovider-slice/open-questions.md
```

Only include questions that affect implementation planning.

Do not repeat non-blocking detailed design questions unless they block slice planning.

Expected non-blocking examples:

* exact Python package names;
* exact test fixture names;
* exact temporary workspace helper names;
* exact ORM versus raw sqlite implementation choice if not already fixed;
* exact first fake image fixture.

Expected blocking examples:

* no repository boundary;
* no validation command;
* slice requires real provider;
* slice requires actual export output;
* slice requires UI/API.

---

# 10. Commit Rule

After creating all slice files, checklist, template, review, and open questions:

1. Run:

```text
git status --short
git diff -- docs/implementation/mvp0-fakeprovider-slice/
```

2. Stage only:

```text
docs/implementation/mvp0-fakeprovider-slice/
```

3. Commit with:

```text
docs: add mvp0 fakeprovider slice implementation plan
```

Do not push.

---

# 11. Final Report

At the end, report:

1. Current branch.
2. Final `git status --short`.
3. Files created.
4. Key implementation slices.
5. Validation commands.
6. Boundary risks.
7. Scope risks.
8. Open questions.
9. Whether the plan is ready for implementation tasks.
10. Recommended first Codex implementation goal.

Do not claim readiness if `reviews/01-plan-review.md` was not created.