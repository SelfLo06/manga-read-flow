# Slice 04: FakeProvider and StageExecutor

## 1. Objective

Plan deterministic FakeProvider contracts and the StageExecutor evidence boundary for detection, OCR, translation, cleaning, and typesetting.

This slice proves that provider-style stage execution can produce deterministic outputs and failures without accessing SQLite, registering official artifacts directly, creating QualityIssues, updating active pointers, or creating WorkflowDecisions.

## 2. Why this slice comes now

The Project store, repositories, UoW, and ArtifactService boundaries are now available. The next risk is boundary drift around provider execution. This slice isolates provider calls and stage evidence before WorkflowLoopEngine starts making decisions from that evidence.

Decisions:

- FakeProvider uses the real provider result envelope: `success`, `partial_success`, `failure`, `refusal`, and `invalid_output`.
- FakeProvider modes are deterministic and test-visible through task/profile/test configuration, not hidden process globals.
- Providers may write temp outputs only under an attempt temp root.
- StageExecutor records only sanitized tool evidence through `StageEvidenceWriter`.
- Official artifact registration is performed through ArtifactService after provider output, but active pointer selection remains forbidden here.

Rejected alternatives:

- Providers returning OCRResult, TranslationResult, QualityIssue, WorkflowDecision, or artifact ids.
- StageExecutor doing retry/fallback/skip/warning/block logic.
- Provider calls inside SQLite write transactions.
- Real OCR/LLM/cleaner/typesetter integrations before FakeProvider validation.

## 3. Inputs from prior designs

- `docs/design/execution-contract/final/provider-adapter-contract.md`
- `docs/design/execution-contract/final/stage-executor-contract.md`
- `docs/design/execution-contract/final/fakeprovider-readiness.md`
- `docs/design/execution-contract/final/error-and-issue-taxonomy-minimal.md`
- `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`
- `docs/design/persistence/final/repository-contract-minimal.md`
- `docs/design/persistence/final/unit-of-work-and-transactions.md`
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

## 4. Allowed files or directories to change during implementation

For the future implementation task only:

- `src/manga_read_flow/providers/**`
- `src/manga_read_flow/workflow/stage_executor*`
- `src/manga_read_flow/workflow/stages/**`
- `src/manga_read_flow/artifacts/**` only for temp-to-official registration calls needed by stage outputs.
- `src/manga_read_flow/persistence/**` only for `StageEvidenceWriter` support.
- `src/manga_read_flow/domain/**` for provider/stage DTOs.
- `tests/integration/test_fakeprovider_stageexecutor.py`
- `tests/fixtures/**`

## 5. Forbidden changes

- WorkflowLoopEngine final decision logic.
- Active OCR/translation/cleaned/typeset pointer updates.
- QualityIssue creation or lifecycle persistence.
- WorkflowDecision creation.
- Retry, fallback, skip, warning, pause, block, or readiness decisions.
- Real provider integrations, real translation prompt templates, cloud calls, or local OCR/model calls.
- UI/API/frontend/export code.

## 6. Implementation tasks

1. Inspect branch and `git status --short`; stop if unrelated changes exist.
2. Define minimal provider input/output DTOs and `ProviderResult` envelope.
3. Implement FakeProvider modes:
   - deterministic detection success;
   - deterministic OCR success;
   - deterministic translation success;
   - invalid translation output;
   - partial translation output;
   - provider refusal;
   - cleaning skip or success;
   - typesetting overflow or success.
4. Implement StageExecutor to reserve/use a stage context, call the provider outside SQLite write transactions, normalize result/failure/refusal, and persist sanitized tool evidence only through `StageEvidenceWriter`.
5. For cleaning/typesetting success, ensure temp file outputs can be registered through ArtifactService as official but unselected artifacts.
6. Add tests proving no provider receives repository, SQLite, or official artifact registration access.
7. Add tests proving StageExecutor does not create WorkflowDecision or active pointer writes.

## 7. Validation command or test target

```bash
pytest tests/integration/test_fakeprovider_stageexecutor.py
```

## 8. Acceptance criteria

- FakeProvider produces deterministic success outputs for detection, OCR, translation, cleaning, and typesetting.
- FakeProvider produces deterministic invalid translation and refusal outputs.
- StageExecutor records sanitized ToolRunLog/attempt evidence only through `StageEvidenceWriter`.
- Provider call holds no SQLite write transaction.
- Temp outputs are not official artifacts until ArtifactService registration.
- Official artifacts registered during this slice are unselected evidence only.
- No active pointers, QualityIssues, WorkflowDecisions, retry budgets, or readiness state are updated by StageExecutor.

## 9. Failure cases to test

- Provider refusal creates a refused ProviderResult and sanitized tool evidence, but no QualityIssue or WorkflowDecision yet.
- Invalid translation output is captured as provider/stage evidence without active translation selection.
- Cleaning skip is returned as evidence for later QualityCheck/loop decision.
- Typesetting overflow returns preview/evidence without readiness.
- Artifact registration failure is returned as stage evidence for the loop, not hidden as provider success.
- Provider call attempts to access repository/SQLite and test proves no such dependency exists.

## 10. Commit strategy

Use one focused implementation commit after `pytest tests/integration/test_fakeprovider_stageexecutor.py` passes, if commits are explicitly allowed. Stage only provider, StageExecutor, evidence-writer support, fixtures, and tests for this slice.

## 11. Risks and scope traps

- Turning StageExecutor into a hidden WorkflowLoopEngine.
- Letting provider failure modes contain policy bypass or evasion behavior.
- Allowing providers to write official workspace paths.
- Treating a registered artifact as active because it is latest.
- Adding real provider clients before deterministic FakeProvider evidence is proven.

## 12. Codex implementation prompt

```text
Goal:
Implement Slice 04, deterministic FakeProvider modes and the StageExecutor evidence boundary.

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/HLD.md
- docs/design/execution-contract/final/provider-adapter-contract.md
- docs/design/execution-contract/final/stage-executor-contract.md
- docs/design/execution-contract/final/fakeprovider-readiness.md
- docs/design/execution-contract/final/error-and-issue-taxonomy-minimal.md
- docs/design/execution-contract/final/execution-contract-dd-v0.1.md
- docs/design/persistence/final/repository-contract-minimal.md
- docs/design/persistence/final/unit-of-work-and-transactions.md
- docs/implementation/mvp0-fakeprovider-slice/slices/04-fakeprovider-and-stageexecutor.md

Allowed files:
- src/manga_read_flow/providers/**
- src/manga_read_flow/workflow/stage_executor*
- src/manga_read_flow/workflow/stages/**
- src/manga_read_flow/artifacts/** only for temp output registration calls
- src/manga_read_flow/persistence/** only for StageEvidenceWriter support
- src/manga_read_flow/domain/**
- tests/integration/test_fakeprovider_stageexecutor.py
- tests/fixtures/**

Forbidden files:
- WorkflowLoopEngine decision implementation
- active pointer update code
- QualityIssue lifecycle code
- WorkflowDecision creation code
- real provider clients or real prompt templates
- UI/API/frontend/export files
- docs/design/**/final/**

Implementation boundaries:
- Provider Adapter must not access SQLite.
- Provider Adapter must not register official artifacts.
- Provider Adapter must not create QualityIssues.
- Provider Adapter must not decide retry, fallback, skip, warning, block, or readiness.
- StageExecutor must not update active pointers or create WorkflowDecision.
- StageExecutor uses StageEvidenceWriter only for tool evidence.
- Provider calls must not hold SQLite write transactions.

Validation command:
pytest tests/integration/test_fakeprovider_stageexecutor.py

Expected output:
- Deterministic FakeProvider success, invalid, partial, refusal, skip, and overflow modes exist.
- StageExecutor records only evidence.
- Temp outputs can become official unselected artifacts through ArtifactService.
- Tests prove provider and stage boundaries.

Commit rule:
Do not commit unless explicitly allowed. If allowed, make one focused slice commit after validation passes and stage only allowed files.

Stop conditions:
- Unrelated dirty working tree exists.
- A real provider, cloud call, local OCR/model call, or real prompt template becomes necessary.
- Provider or StageExecutor needs forbidden persistence/decision authority.
- Validation command is unavailable or failing for unrelated reasons.
```
