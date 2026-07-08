# Slice 05: WorkflowLoop Happy Path

## 1. Objective

Plan the first full single-Page happy path from imported Page to `ready_for_export` using deterministic FakeProvider evidence.

This slice introduces WorkflowLoopEngine orchestration, acceptance transactions, active pointer updates, and export readiness checks without implementing actual export output.

## 2. Why this slice comes now

The lower boundaries now exist: Project store, repositories/UoW, ArtifactService import, FakeProvider, and StageExecutor. The system can now validate the core end-to-end state transition that proves the architecture hangs together for one Project, one Batch, and one Page.

Decisions:

- WorkflowLoopEngine owns stage decisions and acceptance.
- Acceptance transaction is the only boundary that selects active OCR, translation, cleaned, and typeset outputs.
- `export_check` is in scope; actual export output is out of scope.
- ProcessingProfileSnapshot is bootstrapped deterministically for FakeProvider and contains no secrets.
- WorkflowAttempt, ToolRunLog, WorkflowDecision, ProcessingArtifact, and profile snapshot evidence must be inspectable in tests.

Rejected alternatives:

- Updating active pointers in StageExecutor.
- Selecting latest result/artifact by timestamp.
- Treating Page.status as the source of recovery truth.
- Creating an ExportRecord or export artifact to prove readiness.

## 3. Inputs from prior designs

- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/workflow-state/final/state-vocabulary.md`
- `docs/design/workflow-state/final/stage-transition-table.md`
- `docs/design/workflow-state/final/decision-matrix.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/execution-contract/final/stage-executor-contract.md`
- `docs/design/persistence/final/unit-of-work-and-transactions.md`
- `docs/design/persistence/final/fakeprovider-persistence-readiness.md`
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

## 4. Allowed files or directories to change during implementation

For the future implementation task only:

- `src/manga_read_flow/workflow/**`
- `src/manga_read_flow/application/**` for task start/run use case only.
- `src/manga_read_flow/persistence/**` for acceptance, readiness, workflow, result, content, glossary, and artifact metadata operations.
- `src/manga_read_flow/domain/**`
- `src/manga_read_flow/providers/**` only to use existing FakeProvider modes, not to add real providers.
- `src/manga_read_flow/artifacts/**` only for artifact validation/registration calls already required by stages.
- `tests/integration/test_workflow_happy_path.py`
- `tests/fixtures/**`

## 5. Forbidden changes

- Actual export output, ZIP, manifest artifact, or `ExportRecord`.
- FastAPI routes, frontend UI, or Web UI behavior.
- Real providers or real prompt templates.
- Quality issue-heavy paths beyond minimal no-blocker happy path.
- Idempotency/recovery breadth beyond the happy-path reuse hooks needed later.
- Direct SQL or ORM session access from WorkflowLoopEngine.

## 6. Implementation tasks

1. Inspect branch and `git status --short`; stop if unrelated changes exist.
2. Add ProcessingTask creation and deterministic ProcessingProfileSnapshot bootstrap for a single imported Page.
3. Implement WorkflowLoopEngine happy-path stage progression:
   - detection;
   - OCR;
   - translation;
   - translation_check as no-blocker pass for the fake happy path;
   - cleaning;
   - typesetting;
   - export_check.
4. Use StageExecutor for provider/tool evidence and ArtifactService for official artifact registration.
5. Implement acceptance transactions that create TextBlocks, OCRResults, TranslationResults, active OCR/translation pointers, cleaned/typeset artifact pointers, WorkflowDecisions, retry budget/task progress, and stage statuses together.
6. Ensure active pointers are selected by acceptance only, never by latest timestamp.
7. Implement readiness query for no open blocking issues plus present/hash-valid active typeset artifact.
8. Add a happy-path integration test from Project/Page import to `ready_for_export`.

## 7. Validation command or test target

```bash
pytest tests/integration/test_workflow_happy_path.py
```

## 8. Acceptance criteria

- One Project, one Batch, and one Page run through fake detection, OCR, translation, cleaning, typesetting, and `export_check`.
- TextBlocks are created from fake detection.
- OCRResults and TranslationResults are immutable versions and selected through active pointers.
- Page active cleaned and typeset artifact pointers are set through acceptance.
- WorkflowAttempt, ToolRunLog, WorkflowDecision, ProcessingArtifact, and ProcessingProfileSnapshot evidence exist.
- Page reaches `ready_for_export`.
- No ExportRecord, output export artifact, ZIP, or manifest is required.

## 9. Failure cases to test

- Acceptance guard fails when active pointer or stage status changed concurrently; loop reloads or reports conflict rather than silently overwriting.
- Missing active OCR pointer blocks translation acceptance.
- Missing active translation pointer blocks typesetting acceptance.
- Typeset artifact registered but not accepted remains unselected and not readiness-effective.
- Open blocking issue query, if manually seeded, prevents pure readiness.

## 10. Commit strategy

Use one focused implementation commit after `pytest tests/integration/test_workflow_happy_path.py` passes, if commits are explicitly allowed. Stage only workflow, repository, domain, artifact/provider touchpoints, fixtures, and tests needed for the happy path.

## 11. Risks and scope traps

- Implementing broad batch workflow instead of one Page.
- Creating export output to satisfy readiness.
- Collapsing translation_check into translation in a way that prevents Slice 06 quality paths.
- Letting Page.status become the only truth for recovery/readiness.
- Accepting artifacts/results outside the expected-state transaction.

## 12. Codex implementation prompt

```text
Goal:
Implement Slice 05, the first full FakeProvider happy path from one imported Page to ready_for_export.

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/HLD.md
- docs/design/data-model/final/data-model-dd-v0.1.md
- docs/design/workflow-state/final/workflow-state-dd-v0.1.md
- docs/design/workflow-state/final/state-vocabulary.md
- docs/design/workflow-state/final/stage-transition-table.md
- docs/design/workflow-state/final/decision-matrix.md
- docs/design/execution-contract/final/stage-executor-contract.md
- docs/design/persistence/final/unit-of-work-and-transactions.md
- docs/design/persistence/final/fakeprovider-persistence-readiness.md
- docs/implementation/mvp0-fakeprovider-slice/slices/05-workflowloop-happy-path.md

Allowed files:
- src/manga_read_flow/workflow/**
- src/manga_read_flow/application/** for task start/run use case only
- src/manga_read_flow/persistence/**
- src/manga_read_flow/domain/**
- src/manga_read_flow/providers/** only for existing FakeProvider modes
- src/manga_read_flow/artifacts/** only for stage artifact calls
- tests/integration/test_workflow_happy_path.py
- tests/fixtures/**

Forbidden files:
- export output, ZIP, manifest, or ExportRecord code
- UI/API/frontend files
- real providers or real prompt templates
- docs/design/**/final/**

Implementation boundaries:
- WorkflowLoopEngine owns workflow decisions.
- StageExecutor must not update active pointers or create WorkflowDecision.
- QualityCheckService must not advance workflow state.
- ArtifactService must not decide retry, fallback, warning, block, or readiness.
- WorkflowLoopEngine must not depend directly on SQL or ORM session internals.
- Active result/artifact selection must use guarded active pointers, not timestamps.

Validation command:
pytest tests/integration/test_workflow_happy_path.py

Expected output:
- One imported Page reaches ready_for_export through deterministic FakeProvider.
- TextBlocks, OCRResults, TranslationResults, cleaned/typeset artifacts, attempts, logs, decisions, and profile snapshot are persisted.
- Active pointers are set only during acceptance.
- No actual export output exists.

Commit rule:
Do not commit unless explicitly allowed. If allowed, make one focused slice commit after validation passes and stage only allowed files.

Stop conditions:
- Unrelated dirty working tree exists.
- Implementation requires actual export output, UI/API routes, real providers, or prompt templates.
- WorkflowLoopEngine needs direct SQL/session access.
- Active output selection requires timestamp or Page.status-only logic.
- Validation command is unavailable or failing for unrelated reasons.
```
