# Slice 03: ArtifactService and Import

## 1. Objective

Plan original image import and official artifact registration for one Page.

This slice proves the filesystem/artifact metadata boundary: original bytes live in the Project workspace, SQLite stores only metadata, and Page import state is valid only when the original artifact pointer commits with Batch/Page rows.

## 2. Why this slice comes now

After Project store and repository/UoW boundaries exist, the system can safely register official artifacts and create Page import state. FakeProvider stages need an original artifact as durable input, and recovery needs artifact metadata before any workflow processing starts.

Decisions:

- Implement import as an ApplicationService/import use case for MVP-0, not a WorkflowLoopEngine stage.
- ArtifactService is the only official artifact lifecycle entry.
- Store artifact paths project-relative.
- Original images are permanent originals and are never overwritten.
- Import acceptance commits Page original pointer and content state through repository/UoW.

Rejected alternatives:

- Provider or workflow code directly writing official workspace paths.
- Page rows storing authoritative file paths instead of artifact ids.
- Storing original image bytes in SQLite.
- Treating an imported Page as complete before original artifact metadata and pointer commit together.

## 3. Inputs from prior designs

- `docs/design/data-model/final/data-model-dd-v0.1.md`: ProcessingArtifact metadata, Page original pointer, artifact states.
- `docs/design/execution-contract/final/artifact-service-contract.md`
- `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`
- `docs/design/persistence/final/unit-of-work-and-transactions.md`: import transaction.
- `docs/design/persistence/final/fakeprovider-persistence-readiness.md`: mandatory original artifact.
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

## 4. Allowed files or directories to change during implementation

For the future implementation task only:

- `src/manga_read_flow/artifacts/**`
- `src/manga_read_flow/application/**` for import use case only.
- `src/manga_read_flow/persistence/**` for artifact metadata and content state repository operations needed by import.
- `src/manga_read_flow/domain/**` for artifact/page DTOs.
- `tests/integration/test_import_and_artifactservice.py`
- `tests/fixtures/**` for a tiny fake image fixture.

## 5. Forbidden changes

- WorkflowLoopEngine stage implementation.
- Provider adapters writing official artifacts.
- Export artifacts, ZIP, manifest, or `ExportRecord`.
- Image BLOB storage in SQLite.
- Overwriting original files.
- Cleanup scheduler or full retention policy beyond minimal states needed by import/missing detection.
- UI/API upload routes.
- Real provider integrations.

## 6. Implementation tasks

1. Inspect branch and `git status --short`; stop if unrelated changes exist.
2. Add ArtifactService path boundary checks that prevent path traversal and keep files under Project workspace.
3. Add original artifact registration with project-relative path, hash, byte size, MIME/type metadata, dimensions if practical, retention class, and safety flags.
4. Add an import use case that validates a local image fixture, calls ArtifactService, and commits Batch/Page import state with `Page.original_artifact_id`.
5. Add missing/corrupt artifact detection support as metadata state update or service report needed by later recovery.
6. Add tests proving bytes stay on filesystem and SQLite stores metadata only.
7. Add tests proving original artifact is not overwritten on rerun or duplicate filename import.

## 7. Validation command or test target

```bash
pytest tests/integration/test_import_and_artifactservice.py
```

## 8. Acceptance criteria

- Original image is copied or stored into the Project workspace through ArtifactService.
- `processing_artifacts` metadata is persisted with project-relative path, hash, size, type, retention, and `storage_state = present`.
- Page points to `original_artifact_id`.
- Original image bytes remain on filesystem and are not stored in SQLite.
- Original image is never overwritten; duplicate names are made safe by deterministic or unique path handling.
- Deleting or corrupting an artifact can be detected later as missing/hash mismatch without WorkflowLoopEngine deciding the outcome.

## 9. Failure cases to test

- Import path traversal attempt.
- Unsupported file extension or MIME/type.
- Duplicate original filename in the same Project.
- Original artifact file deleted after registration.
- Hash mismatch after file corruption.
- Import transaction fails after artifact registration; artifact remains official but Page is not treated as imported until pointer commit.

## 10. Commit strategy

Use one focused implementation commit after `pytest tests/integration/test_import_and_artifactservice.py` passes, if commits are explicitly allowed. Stage only ArtifactService, import use case, repository additions, fixtures, and tests for this slice.

## 11. Risks and scope traps

- Building full upload/API behavior instead of a backend import use case.
- Implementing export output while adding artifact paths.
- Letting ArtifactService decide workflow rebuild, warning, pause, or block on missing files. It should report artifact state only.
- Using absolute paths as domain truth. Use project-relative artifact paths in metadata.
- Adding cleanup scheduler complexity before active outputs exist.

## 12. Codex implementation prompt

```text
Goal:
Implement Slice 03, ArtifactService original registration and one-Page import for MVP-0.

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/HLD-v0.2.md
- docs/design/data-model/final/data-model-dd-v0.1.md
- docs/design/execution-contract/final/artifact-service-contract.md
- docs/design/execution-contract/final/execution-contract-dd-v0.1.md
- docs/design/persistence/final/unit-of-work-and-transactions.md
- docs/design/persistence/final/fakeprovider-persistence-readiness.md
- docs/implementation/mvp0-fakeprovider-slice/slices/03-artifactservice-and-import.md

Allowed files:
- src/manga_read_flow/artifacts/**
- src/manga_read_flow/application/** for import use case only
- src/manga_read_flow/persistence/**
- src/manga_read_flow/domain/**
- tests/integration/test_import_and_artifactservice.py
- tests/fixtures/**

Forbidden files:
- WorkflowLoopEngine full stage implementation
- Provider adapters writing official artifacts
- UI/API/frontend files
- real providers
- export output, ZIP, manifest, or ExportRecord code
- docs/design/**/final/**

Implementation boundaries:
- ArtifactService owns official artifact path, hash, registration, retention metadata, and missing detection.
- ArtifactService does not decide retry, fallback, warning, block, or readiness.
- Repository/DAO remains the only SQLite access entry.
- Original images are never overwritten.
- No image bytes or large payloads in SQLite.

Validation command:
pytest tests/integration/test_import_and_artifactservice.py

Expected output:
- One Page can be imported through backend service code.
- Original artifact metadata is persisted.
- Page original artifact pointer is set.
- Filesystem bytes and SQLite metadata remain separated.
- Missing/corrupt artifact can be detected as artifact evidence.

Commit rule:
Do not commit unless explicitly allowed. If allowed, make one focused slice commit after validation passes and stage only allowed files.

Stop conditions:
- Unrelated dirty working tree exists.
- Implementation requires UI/API upload routes.
- Implementation requires export output.
- ArtifactService starts making workflow decisions.
- Provider adapter needs official artifact registration authority.
- Validation command is unavailable or failing for unrelated reasons.
```
