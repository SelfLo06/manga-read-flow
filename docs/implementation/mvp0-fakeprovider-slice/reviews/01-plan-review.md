# MVP-0 FakeProvider Slice Plan Review

## 1. Scenario replay against HARNESS

| Scenario | Result | Responsible slice | Required modules | Validation command | Persisted evidence | Boundary check | Scope check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| G01: Slice order is implementation-ready | PASS | Slices 01-07 | Project store, repositories, ArtifactService, StageExecutor, WorkflowLoopEngine, QualityCheckService | All slice commands | Slice docs define sequence and acceptance criteria | Later slices depend on earlier boundaries | No slice requires full product |
| G02: Codex tasks are bounded | PASS | Slices 01-07 | Same as slice-specific modules | Slice-specific pytest target | Each slice has allowed files, forbidden files, acceptance, commit strategy, and prompt | Prompts repeat hard boundaries | Scope stops at readiness |
| G03: Prior design baselines are respected | PASS | All slices | Data model, workflow-state, execution-contract, persistence | Review only | Source docs listed per slice | No final design is reopened | Open questions are non-blocking |
| B01: Project store initialization | PASS | Slice 01 | Project store, app/project lifecycle repositories | `pytest tests/integration/test_project_store_init.py` | app ledger, project ledger, ProjectMetadata | Project repositories gated by ready open | No UI/API |
| B02: Import one Page | PASS | Slice 03 | ArtifactService, import use case, content/artifact repositories | `pytest tests/integration/test_import_and_artifactservice.py` | original ProcessingArtifact, Page original pointer | ArtifactService owns official artifact lifecycle | No image BLOBs, no export |
| B03: Minimal repository contracts | PASS | Slice 02 | Repository groups, UoW, StageEvidenceWriter | `pytest tests/integration/test_repository_uow_core.py` | contract tests and guarded acceptance shape | Repository / DAO only SQLite entry | No generic framework required |
| W01: Fake happy path | PASS | Slice 05 | WorkflowLoopEngine, StageExecutor, FakeProvider, ArtifactService, repositories | `pytest tests/integration/test_workflow_happy_path.py` | TextBlocks, OCRResults, TranslationResults, artifacts, attempts, logs, decisions, snapshot | Active pointers selected by acceptance | No ExportRecord/output |
| W02: Stage execution boundary | PASS | Slice 04 | FakeProvider, StageExecutor, StageEvidenceWriter | `pytest tests/integration/test_fakeprovider_stageexecutor.py` | ToolRunLog and narrow attempt evidence | StageExecutor does not decide or select active pointers | No real providers |
| W03: Acceptance transaction | PASS | Slices 02 and 05 | Acceptance UoW, WorkflowLoopEngine, repositories | `pytest tests/integration/test_repository_uow_core.py`; `pytest tests/integration/test_workflow_happy_path.py` | result rows, pointers, issues, decisions, statuses | Guard failures reload/redecide | No direct SQL in loop |
| Q01: Invalid or partial translation | PASS | Slice 06 | FakeProvider, QualityCheckService, WorkflowLoopEngine | `pytest tests/integration/test_quality_issues_and_readiness.py` | QualityIssue, WorkflowDecision, decision-issue link | QualityCheck classifies; loop decides | Partial output not hidden |
| Q02: Provider refusal | PASS | Slice 06 | FakeProvider, StageExecutor, QualityCheckService, WorkflowLoopEngine | `pytest tests/integration/test_quality_issues_and_readiness.py` | refused attempt, ToolRunLog, QualityIssue, WorkflowDecision | Provider does not create issue or bypass policy | No evasion data |
| Q03: Blocking issue prevents readiness | PASS | Slice 06 | ReadinessQueryRepository, WorkflowLoopEngine | `pytest tests/integration/test_quality_issues_and_readiness.py` | blocker query, readiness decision | Quality issue gate preserved | No export output |
| I01: Rerun unchanged Page | PASS | Slice 07 | Reuse queries, WorkflowLoopEngine, ArtifactService | `pytest tests/integration/test_idempotency_and_recovery.py` | reused attempt/decision evidence | Provider does not decide cache | No duplicate active result |
| R01: Crash after OCR acceptance | PASS | Slice 07 | Recovery snapshot, active OCR pointer, WorkflowLoopEngine | `pytest tests/integration/test_idempotency_and_recovery.py` | OCRResult, active OCR pointer, recovery decision | Recovery uses durable evidence | OCR not rerun |
| R02: Crash after artifact registration before acceptance | PASS | Slice 07 | ArtifactService, recovery, WorkflowLoopEngine | `pytest tests/integration/test_idempotency_and_recovery.py` | official unselected artifact, repair decision | No timestamp selection | No export-effectiveness without acceptance |
| R03: Missing active artifact | PASS | Slice 07 | ArtifactService, WorkflowLoopEngine, repositories | `pytest tests/integration/test_idempotency_and_recovery.py` | `storage_state = missing`, decision evidence | ArtifactService marks state only | Loop decides rebuild/warn/block |

## 2. Missing implementation slices

No required implementation slice is missing.

The plan includes:

- Slice 01: Foundation and Project Store
- Slice 02: Repository and Unit of Work Core
- Slice 03: ArtifactService and Import
- Slice 04: FakeProvider and StageExecutor
- Slice 05: WorkflowLoop Happy Path
- Slice 06: Quality Issues and Readiness
- Slice 07: Idempotency and Recovery

The required checklist, Codex task template, review, and open questions files are also included.

## 3. Overly large slices

Potentially large slices:

- Slice 05 is the broadest because it connects every earlier boundary into the happy path. It remains acceptable because it is limited to one Project, one Batch, one Page, deterministic FakeProvider, and one validation command.
- Slice 07 combines idempotency and selected recovery cases. It remains acceptable because it covers only the harness-required rerun and crash scenarios for one Page.

Mitigation:

- If Slice 05 or Slice 07 produce large implementation diffs, split within the same documented order without changing scope: for example, Slice 05a happy path to translation, Slice 05b cleaning/typesetting/readiness; Slice 07a idempotency, Slice 07b recovery.

## 4. Missing validation commands

No validation command is missing.

Planned commands:

```bash
pytest tests/integration/test_project_store_init.py
pytest tests/integration/test_repository_uow_core.py
pytest tests/integration/test_import_and_artifactservice.py
pytest tests/integration/test_fakeprovider_stageexecutor.py
pytest tests/integration/test_workflow_happy_path.py
pytest tests/integration/test_quality_issues_and_readiness.py
pytest tests/integration/test_idempotency_and_recovery.py
```

These commands are implementation targets. They were not run in this planning task because the production code and tests are intentionally not implemented yet.

## 5. Architecture boundary risks

| Risk | Plan response |
| --- | --- |
| Provider Adapter accesses SQLite | Every provider/stage slice forbids repository/SQLite dependencies for providers. |
| Provider Adapter registers official artifacts | Slice 04 limits providers to temp outputs; ArtifactService registers official artifacts. |
| Provider Adapter creates QualityIssues | Slice 06 keeps QualityCheckService as classifier and WorkflowLoopEngine as persistence coordinator. |
| ArtifactService decides retry/fallback/warning/block/readiness | Slices 03 and 07 restrict ArtifactService to artifact lifecycle and storage state evidence. |
| QualityCheckService advances workflow state | Slice 06 keeps it repository-free for MVP-0. |
| StageExecutor becomes hidden WorkflowLoopEngine | Slice 04 limits StageExecutor to execution and tool evidence. |
| WorkflowLoopEngine depends on SQL/session internals | Slice 02 introduces repository contracts before loop implementation. |
| Latest timestamp selects active output | Slices 05 and 07 require active pointers and guarded acceptance only. |
| Page.status-only recovery | Slice 07 requires recovery bundles from attempts, decisions, active pointers, artifacts, issues, hashes, and statuses. |
| Image bytes in SQLite | Slices 01 and 03 explicitly forbid image/large payload BLOBs. |
| Original image overwritten | Slice 03 requires original immutability and duplicate-name safety. |

## 6. Scope creep risks

| Risk | Plan response |
| --- | --- |
| FastAPI routes or Web UI enter MVP-0 | All slices forbid UI/API/frontend files. |
| Real provider integration displaces FakeProvider | Slices 04-07 forbid real providers and prompt templates. |
| Actual export output appears before readiness is proven | Slices 05-07 stop at `export_check` and forbid ExportRecord/output/ZIP/manifest. |
| Batch-scale workflow enters the single-Page slice | Slices 05 and 07 limit tests to one Project, one Batch, one Page. |
| Full migration framework replaces minimal readiness | Slice 01 allows only minimal ledgers/open outcomes unless later authorized. |
| Full quality taxonomy delays MVP-0 | Slice 06 limits quality to harness-required issue modes. |
| Cleanup scheduler or full retention policy expands ArtifactService | Slice 03 limits cleanup to minimal artifact states and missing detection. |

## 7. Goal 4 readiness

Goal 4 is ready to generate Codex implementation tasks.

Readiness is planning readiness only. No production code or validation tests were implemented or run in this task.

## 8. Noted input conflict

`docs/implementation/mvp0-fakeprovider-slice/GOAL.md` lists Slice 02 as import/artifact and Slice 03 as repository/UoW, while `docs/implementation/mvp0-fakeprovider-slice/PLAN.md` and the task prompt require Slice 02 repository/UoW and Slice 03 ArtifactService/import.

Resolution:

- Follow `PLAN.md` and the task prompt exactly for file names and implementation order.
- Treat the `GOAL.md` ordering as stale planning text, not a blocking design conflict.
