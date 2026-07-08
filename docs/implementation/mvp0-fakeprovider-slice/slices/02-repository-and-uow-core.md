# Slice 02: Repository and Unit of Work Core

## 1. Objective

Plan the minimal repository contracts and Unit of Work boundaries required by the FakeProvider backend slice.

This slice creates the persistence access shape for content state, result versions, workflow evidence, quality issues, artifact metadata, glossary versions, and readiness queries without exposing SQLite, cursors, ORM sessions, or table-shaped generic repositories to workflow modules.

## 2. Why this slice comes now

ArtifactService, StageExecutor, QualityCheckService integration, WorkflowLoopEngine acceptance, idempotency, and recovery all need repository boundaries before they can be implemented safely. This slice comes before import and provider execution so later code cannot grow ad hoc SQLite access in services.

Decisions:

- Implement named repository groups instead of a generic `Repository<T>`.
- Keep SQLite access behind Repository / DAO only.
- Use named Unit of Work operations for lifecycle, import, attempt reservation, tool evidence, artifact metadata, acceptance, and recovery repair.
- Introduce a narrow `StageEvidenceWriter` for StageExecutor.
- Reserve the acceptance transaction shape before the happy path uses it.

Rejected alternatives:

- Generic CRUD repositories, because they leak table shape and invite business decisions in persistence.
- Passing SQL sessions or connections into WorkflowLoopEngine or StageExecutor.
- Letting StageExecutor write active pointers, QualityIssues, WorkflowDecisions, retry budget, or stage completion.

## 3. Inputs from prior designs

- `docs/design/persistence/final/repository-contract-minimal.md`
- `docs/design/persistence/final/unit-of-work-and-transactions.md`
- `docs/design/persistence/final/persistence-readiness-dd-v0.1.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

## 4. Allowed files or directories to change during implementation

For the future implementation task only:

- `src/manga_read_flow/persistence/**`
- `src/manga_read_flow/domain/**` for minimal DTO/value objects used by repository contracts.
- `src/manga_read_flow/workflow/**` only for contract-facing DTOs needed to compile repository tests.
- `tests/integration/test_repository_uow_core.py`
- `tests/conftest.py`
- `tests/fixtures/**` only for small persistence fixtures.

## 5. Forbidden changes

- Provider adapter code that accesses repositories or SQLite.
- StageExecutor writes beyond `StageEvidenceWriter`.
- WorkflowLoopEngine implementation of the full happy path.
- ArtifactService file promotion or official artifact lifecycle implementation beyond metadata contract stubs needed for tests.
- UI/API/routes/frontend files.
- Real provider integrations, real prompt templates, export output, ZIP, manifest, or `ExportRecord`.
- Broad schema redesign or previous final design doc edits.

## 6. Implementation tasks

1. Inspect branch and `git status --short`; stop if unrelated changes exist.
2. Add repository contract interfaces or concrete minimal modules for:
   - ProjectIdentityRepository
   - ContentStateRepository
   - ResultVersionRepository
   - GlossaryRepository
   - WorkflowExecutionRepository
   - QualityIssueRepository
   - ArtifactMetadataRepository
   - ReadinessQueryRepository
3. Add named Unit of Work helpers for short transactions, keeping implementation details hidden.
4. Add an acceptance transaction placeholder with expected-state guard inputs and a visible conflict outcome.
5. Add `StageEvidenceWriter` with only ToolRunLog and narrow attempt evidence operations.
6. Add tests proving workflow-facing code can use repository contracts without SQL/session handles.
7. Add tests proving provider code has no repository dependency.
8. Add tests proving StageExecutor-facing evidence writes cannot update active pointers, QualityIssues, WorkflowDecisions, or retry budget.

## 7. Validation command or test target

```bash
pytest tests/integration/test_repository_uow_core.py
```

## 8. Acceptance criteria

- Repository contracts hide SQLite details from callers.
- No workflow-facing test uses SQL strings, ORM sessions, cursors, or table-shaped row dictionaries.
- `StageEvidenceWriter` can create/update ToolRunLog and narrow attempt evidence only.
- Provider adapter modules have no repository or SQLite dependency.
- Acceptance transaction shape can represent accepted results, active pointers, issue lifecycle, WorkflowDecision, retry budget, task progress, stage statuses, and expected-state conflict.
- No generic `Repository<T>` abstraction is introduced.

## 9. Failure cases to test

- Expected active pointer guard fails and acceptance returns a conflict/reload outcome.
- StageEvidenceWriter caller tries to perform a forbidden write and the API does not expose that capability.
- Provider adapter import path cannot reach repository modules.
- Repository access before verified Project context remains blocked from Slice 01.
- Attempt reservation avoids duplicate runner claim through expected task status/current stage guard.

## 10. Commit strategy

Use one small implementation commit after `pytest tests/integration/test_repository_uow_core.py` passes, if commits are explicitly allowed for that implementation task. Stage only repository/UoW contract and test files from this slice.

## 11. Risks and scope traps

- Building a full ORM layer or DDL suite before the FakeProvider slice needs it.
- Letting convenience APIs expose sessions to WorkflowLoopEngine.
- Making QualityCheckService persistence-aware too early.
- Giving StageExecutor broad repository access because it is near provider execution.
- Hiding conflict handling as a generic exception instead of a workflow-decision input.

## 12. Codex implementation prompt

```text
Goal:
Implement Slice 02, the minimal repository and Unit of Work core for MVP-0 FakeProvider backend tests.

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/HLD.md
- docs/design/data-model/final/data-model-dd-v0.1.md
- docs/design/workflow-state/final/workflow-state-dd-v0.1.md
- docs/design/execution-contract/final/execution-contract-dd-v0.1.md
- docs/design/persistence/final/persistence-readiness-dd-v0.1.md
- docs/design/persistence/final/repository-contract-minimal.md
- docs/design/persistence/final/unit-of-work-and-transactions.md
- docs/implementation/mvp0-fakeprovider-slice/slices/02-repository-and-uow-core.md

Allowed files:
- src/manga_read_flow/persistence/**
- src/manga_read_flow/domain/**
- src/manga_read_flow/workflow/** only for minimal contract DTOs
- tests/integration/test_repository_uow_core.py
- tests/conftest.py
- tests/fixtures/**

Forbidden files:
- Provider adapter code with repository or SQLite dependency
- StageExecutor code that writes active pointers, QualityIssues, WorkflowDecisions, retry budget, or stage completion
- UI/API/frontend files
- real providers or prompt templates
- export output, ZIP, manifest, or ExportRecord code
- docs/design/**/final/**

Implementation boundaries:
- Repository / DAO is the only SQLite access entry.
- WorkflowLoopEngine-facing code must not need SQL/session objects.
- StageExecutor may use only StageEvidenceWriter for tool evidence.
- Provider adapters must receive no persistence dependency.
- Use named operations, not generic Repository<T>.

Validation command:
pytest tests/integration/test_repository_uow_core.py

Expected output:
- Minimal repository groups and UoW helpers exist.
- Acceptance transaction placeholder has expected-state guards.
- StageEvidenceWriter is narrow.
- Tests prove SQL/session details do not leak.

Commit rule:
Do not commit unless explicitly allowed. If allowed, make one focused slice commit after validation passes and stage only allowed files.

Stop conditions:
- Unrelated dirty working tree exists.
- A broad ORM/migration framework becomes necessary.
- Any provider adapter needs SQLite/repository access.
- StageExecutor needs active pointer, issue, decision, or retry writes.
- Validation command is unavailable or failing for unrelated reasons.
```
