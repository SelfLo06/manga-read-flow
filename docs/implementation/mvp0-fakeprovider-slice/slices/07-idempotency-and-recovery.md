# Slice 07: Idempotency and Recovery

## 1. Objective

Plan the first idempotent rerun and crash recovery validations for the MVP-0 FakeProvider single-Page backend slice.

This slice proves the workflow can reuse unchanged OCR/translation/cleaned/typeset outputs, recover after selected crashes, handle official-but-unselected artifacts, and respond to missing active artifacts without relying only on Page.status or timestamps.

## 2. Why this slice comes now

Happy path and quality paths create the durable evidence recovery needs. The last MVP-0 backend planning slice verifies that the evidence is sufficient after reruns and crashes, before any real provider or UI makes failures costlier.

Decisions:

- Idempotency is a WorkflowLoopEngine/repository decision, not a Provider Adapter decision.
- Reuse is auditable through `WorkflowAttempt.status = reused_cached` and/or `WorkflowDecision.decision_type = reuse_cached_result`.
- Recovery prefers committed results, active pointers, artifact metadata, decisions, attempts, and dependency hashes.
- Official unselected artifacts are evidence/reuse candidates only and are never selected by latest timestamp.
- ArtifactService marks missing/hash-invalid artifacts; WorkflowLoopEngine decides rebuild, warning, pause, or block.

Rejected alternatives:

- Rerunning providers on every unchanged Page.
- Inferring recovery success from Page.status.
- Promoting latest artifact/result by timestamp.
- Parsing raw provider temp output into accepted results during recovery without normal validation/acceptance replay.
- Letting ArtifactService decide workflow outcome after missing file detection.

## 3. Inputs from prior designs

- `docs/design/workflow-state/final/recovery-rules.md`
- `docs/design/workflow-state/final/stale-propagation-rules.md`
- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/persistence/final/repository-contract-minimal.md`
- `docs/design/persistence/final/unit-of-work-and-transactions.md`
- `docs/design/persistence/final/fakeprovider-persistence-readiness.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/execution-contract/final/artifact-service-contract.md`
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

## 4. Allowed files or directories to change during implementation

For the future implementation task only:

- `src/manga_read_flow/workflow/**`
- `src/manga_read_flow/recovery/**` if a separate recovery module is created.
- `src/manga_read_flow/persistence/**` for recovery snapshots, reuse lookups, task claim/repair, and guarded acceptance.
- `src/manga_read_flow/artifacts/**` for missing/hash validation state updates.
- `src/manga_read_flow/domain/**`
- `src/manga_read_flow/providers/**` only for FakeProvider call-count/test modes if needed.
- `tests/integration/test_idempotency_and_recovery.py`
- `tests/fixtures/**`

## 5. Forbidden changes

- Real provider integrations or prompt templates.
- Batch-scale workflow broadening.
- UI/API/frontend routes.
- Export output, ZIP, manifest, or `ExportRecord`.
- Timestamp-selected active outputs.
- Page.status-only recovery logic.
- ArtifactService retry/fallback/warning/block/readiness decisions.
- Provider Adapter cache decisions.

## 6. Implementation tasks

1. Inspect branch and `git status --short`; stop if unrelated changes exist.
2. Add repository reuse lookups for OCR, translation, cleaned artifacts, and typeset artifacts using dependency keys and artifact validation.
3. Add auditable reuse decision/attempt persistence.
4. Add rerun unchanged Page integration test proving no duplicate provider calls and no duplicate active result rows.
5. Add crash simulation after OCR acceptance; recovery resumes from translation without OCR rerun.
6. Add crash simulation after artifact registration before acceptance; official unselected artifact remains unselected and is not chosen by timestamp.
7. Add missing active artifact scenario; ArtifactService marks `storage_state = missing`.
8. Add WorkflowLoopEngine recovery decisions for rebuild, warning, pause, or block based on evidence and policy.
9. Add recovery repair tests that use tasks, attempts, decisions, active pointers, dependency hashes, artifacts, issues, and TextBlock statuses, not Page.status alone.

## 7. Validation command or test target

```bash
pytest tests/integration/test_idempotency_and_recovery.py
```

## 8. Acceptance criteria

- Unchanged rerun avoids duplicate provider calls for reusable OCR, translation, cleaning, and typesetting outputs.
- Reuse is auditable through attempt or decision evidence.
- No duplicate active result rows are created.
- Crash after OCR acceptance resumes at translation without OCR rerun.
- Registered-but-unselected artifact is not selected by latest timestamp.
- Missing active artifact becomes `storage_state = missing`.
- WorkflowLoopEngine decides rebuild/warning/pause/block after missing artifact evidence.
- Recovery does not rely only on Page.status.

## 9. Failure cases to test

- Rerun after unchanged Page with compatible dependency hashes.
- Rerun after dependency hash change should not reuse stale result.
- Crash after OCRResult and active OCR pointer committed.
- Crash after typeset artifact registration before active pointer acceptance.
- Missing active cleaned or typeset artifact.
- Open blocking issue during recovery prevents pure readiness.
- Locked translation is not replaced by reuse without explicit override.

## 10. Commit strategy

Use one focused implementation commit after `pytest tests/integration/test_idempotency_and_recovery.py` passes, if commits are explicitly allowed. Stage only workflow/recovery, persistence, artifact, FakeProvider test support, fixture, and test files for this slice.

## 11. Risks and scope traps

- Expanding into full batch recovery instead of one Page.
- Treating failed/refused attempts as reusable successes.
- Over-reusing stale results because dependency keys are too small.
- Under-reusing valid results because artifact validation is missing.
- Promoting temp/orphan files without normal ArtifactService registration and acceptance.
- Adding cleanup scheduler or export records to explain missing artifacts.

## 12. Codex implementation prompt

```text
Goal:
Implement Slice 07, idempotency and crash recovery validation for the MVP-0 single-Page FakeProvider backend slice.

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/HLD.md
- docs/design/data-model/final/data-model-dd-v0.1.md
- docs/design/workflow-state/final/workflow-state-dd-v0.1.md
- docs/design/workflow-state/final/recovery-rules.md
- docs/design/workflow-state/final/stale-propagation-rules.md
- docs/design/persistence/final/repository-contract-minimal.md
- docs/design/persistence/final/unit-of-work-and-transactions.md
- docs/design/persistence/final/fakeprovider-persistence-readiness.md
- docs/design/execution-contract/final/artifact-service-contract.md
- docs/implementation/mvp0-fakeprovider-slice/slices/07-idempotency-and-recovery.md

Allowed files:
- src/manga_read_flow/workflow/**
- src/manga_read_flow/recovery/** if needed
- src/manga_read_flow/persistence/**
- src/manga_read_flow/artifacts/**
- src/manga_read_flow/domain/**
- src/manga_read_flow/providers/** only for FakeProvider test support
- tests/integration/test_idempotency_and_recovery.py
- tests/fixtures/**

Forbidden files:
- real providers or prompt templates
- Batch-scale workflow broadening
- UI/API/frontend files
- export output, ZIP, manifest, or ExportRecord code
- docs/design/**/final/**

Implementation boundaries:
- Recovery must not rely only on Page.status.
- Active result/artifact selection must not use latest timestamp.
- Provider Adapter must not decide cache reuse.
- ArtifactService marks storage state but does not decide rebuild, warning, pause, block, or readiness.
- WorkflowLoopEngine owns reuse and recovery decisions.

Validation command:
pytest tests/integration/test_idempotency_and_recovery.py

Expected output:
- Unchanged reruns reuse results/artifacts audibly.
- Crash after OCR acceptance resumes from translation.
- Official unselected artifacts remain unselected unless accepted.
- Missing active artifact is marked missing and loop decision is persisted.

Commit rule:
Do not commit unless explicitly allowed. If allowed, make one focused slice commit after validation passes and stage only allowed files.

Stop conditions:
- Unrelated dirty working tree exists.
- Implementation requires real providers, UI/API routes, export output, or batch-scale workflow.
- Recovery needs Page.status-only or timestamp-based active selection.
- ArtifactService needs workflow decision authority.
- Validation command is unavailable or failing for unrelated reasons.
```
