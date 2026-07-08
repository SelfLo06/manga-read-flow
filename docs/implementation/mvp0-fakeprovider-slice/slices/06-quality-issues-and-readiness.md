# Slice 06: Quality Issues and Readiness

## 1. Objective

Plan issue-bearing FakeProvider paths, minimal QualityCheckService behavior, provider refusal handling, and readiness gating.

This slice proves that invalid/partial outputs, provider refusal, cleaning skip, and typesetting overflow become visible workflow evidence and cannot silently become pure `ready_for_export`.

## 2. Why this slice comes now

The happy path proves the loop can finish. The next implementation risk is false readiness: partial translations, provider refusals, skipped cleaning, or typesetting overflow might be hidden if QualityIssue and WorkflowDecision evidence are not wired into acceptance and readiness checks.

Decisions:

- QualityCheckService remains repository-free for MVP-0 and returns issue drafts/reports.
- WorkflowLoopEngine persists QualityIssues, WorkflowDecision, and WorkflowDecisionIssue links during acceptance.
- Provider refusal is first-class evidence, not a generic crash.
- Pure `ready_for_export` is blocked by open blocking issues and unresolved skip/warning states.
- Warning readiness is explicit and remains visible as `ready_for_export_with_warnings` when policy allows.

Rejected alternatives:

- Provider Adapter creating QualityIssues.
- QualityCheckService advancing workflow state.
- Treating partial translation as full success.
- Treating provider refusal as same-provider retry/prompt evasion.
- Allowing warning state to silently become pure readiness.

## 3. Inputs from prior designs

- `docs/design/execution-contract/final/quality-check-contract.md`
- `docs/design/execution-contract/final/error-and-issue-taxonomy-minimal.md`
- `docs/design/execution-contract/final/fakeprovider-readiness.md`
- `docs/design/workflow-state/final/decision-matrix.md`
- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/persistence/final/fakeprovider-persistence-readiness.md`
- `docs/design/persistence/final/unit-of-work-and-transactions.md`
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

## 4. Allowed files or directories to change during implementation

For the future implementation task only:

- `src/manga_read_flow/quality/**`
- `src/manga_read_flow/workflow/**`
- `src/manga_read_flow/persistence/**` for issue, decision-issue, readiness, and acceptance operations.
- `src/manga_read_flow/domain/**`
- `src/manga_read_flow/providers/**` only for deterministic FakeProvider issue modes.
- `tests/integration/test_quality_issues_and_readiness.py`
- `tests/fixtures/**`

## 5. Forbidden changes

- Provider adapters creating QualityIssues or deciding retry/fallback/skip/warning/block.
- QualityCheckService updating active pointers, stage status, task status, Page status, or WorkflowDecision.
- Actual export output, ZIP, manifest artifact, or `ExportRecord`.
- Policy bypass/evasion behavior or prompt workarounds for refusal.
- Real provider integrations or prompt templates.
- UI/API/frontend files.

## 6. Implementation tasks

1. Inspect branch and `git status --short`; stop if unrelated changes exist.
2. Implement minimal QualityCheckService reports for:
   - invalid translation;
   - partial translation/missing block;
   - provider refusal;
   - cleaning skip;
   - typesetting overflow.
3. Ensure reports include issue drafts with target scope, discovered stage, root stage, issue type, error code, severity, blocking flag, status, related attempt/tool/artifact/result refs, and suggested action keys where applicable.
4. Extend WorkflowLoopEngine acceptance to persist QualityIssues and WorkflowDecisionIssue links when decisions link issues.
5. Implement readiness query that distinguishes pure readiness, warning readiness, and block.
6. Add FakeProvider modes for issue-bearing scenarios if not already present from Slice 04.
7. Add integration tests for invalid/partial translation, provider refusal, warning readiness, and blocking readiness.

## 7. Validation command or test target

```bash
pytest tests/integration/test_quality_issues_and_readiness.py
```

## 8. Acceptance criteria

- Invalid or partial translation creates persisted QualityIssue evidence.
- Provider refusal creates ToolRunLog, refused WorkflowAttempt, QualityIssue, WorkflowDecision, and WorkflowDecisionIssue link.
- No policy bypass/evasion data appears.
- Open blocking QualityIssue prevents pure `ready_for_export`.
- Warning state remains visible and can only become `ready_for_export_with_warnings` when the active ProcessingProfileSnapshot policy allows it.
- QualityCheckService does not advance workflow state.
- Provider Adapter does not create QualityIssues.

## 9. Failure cases to test

- Invalid translation JSON with retry budget exhausted becomes block or pause according to policy.
- Partial translation persists valid block results only when accepted and issues for missing/invalid blocks.
- Provider refusal records `is_provider_refusal` evidence and no same-provider evasion attempt.
- Cleaning skip cannot become pure `ready_for_export`.
- Typesetting overflow blocks or warning-marks readiness according to severity/profile.
- Blocking issue manually seeded in readiness scope prevents pure readiness.

## 10. Commit strategy

Use one focused implementation commit after `pytest tests/integration/test_quality_issues_and_readiness.py` passes, if commits are explicitly allowed. Stage only quality, workflow, persistence, FakeProvider mode, fixture, and test files for this slice.

## 11. Risks and scope traps

- Implementing a full quality taxonomy instead of minimal MVP-0 issue modes.
- Making user-facing UI copy or localization part of backend readiness.
- Letting refusal handling drift into prompt bypass behavior.
- Treating warnings as success without preserving issue visibility.
- Creating ExportRecord for blocked readiness. This slice stops at workflow readiness.

## 12. Codex implementation prompt

```text
Goal:
Implement Slice 06, minimal QualityCheckService issue paths and readiness gating for MVP-0.

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/HLD.md
- docs/design/data-model/final/data-model-dd-v0.1.md
- docs/design/workflow-state/final/workflow-state-dd-v0.1.md
- docs/design/workflow-state/final/decision-matrix.md
- docs/design/execution-contract/final/quality-check-contract.md
- docs/design/execution-contract/final/error-and-issue-taxonomy-minimal.md
- docs/design/execution-contract/final/fakeprovider-readiness.md
- docs/design/persistence/final/unit-of-work-and-transactions.md
- docs/design/persistence/final/fakeprovider-persistence-readiness.md
- docs/implementation/mvp0-fakeprovider-slice/slices/06-quality-issues-and-readiness.md

Allowed files:
- src/manga_read_flow/quality/**
- src/manga_read_flow/workflow/**
- src/manga_read_flow/persistence/**
- src/manga_read_flow/domain/**
- src/manga_read_flow/providers/** only for deterministic FakeProvider issue modes
- tests/integration/test_quality_issues_and_readiness.py
- tests/fixtures/**

Forbidden files:
- Provider adapters creating QualityIssues or making workflow decisions
- QualityCheckService advancing workflow state or active pointers
- export output, ZIP, manifest, or ExportRecord code
- real providers or prompt templates
- UI/API/frontend files
- docs/design/**/final/**

Implementation boundaries:
- QualityCheckService owns quality issue detection and root-stage attribution.
- QualityCheckService returns issue drafts/reports but does not persist workflow state.
- WorkflowLoopEngine owns retry/fallback/warning/block/readiness decisions.
- Provider refusal must be recorded as first-class evidence.
- No provider policy bypass or evasion behavior.

Validation command:
pytest tests/integration/test_quality_issues_and_readiness.py

Expected output:
- Invalid/partial translation, provider refusal, cleaning skip, and typesetting overflow are issue-bearing paths.
- WorkflowDecisionIssue links exist when decisions link persisted issues.
- Open blockers prevent pure ready_for_export.
- Warning readiness remains explicit and policy-controlled.

Commit rule:
Do not commit unless explicitly allowed. If allowed, make one focused slice commit after validation passes and stage only allowed files.

Stop conditions:
- Unrelated dirty working tree exists.
- Implementation requires actual export output, UI/API routes, real providers, or prompt templates.
- QualityCheckService needs repository writes or state advancement.
- Provider refusal handling requires bypass/evasion logic.
- Validation command is unavailable or failing for unrelated reasons.
```
