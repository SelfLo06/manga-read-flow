# Slice 01: Foundation and Project Store

## 1. Objective

Plan the minimal backend foundation needed to initialize a temporary `app.db`, create a Project workspace, initialize a per-Project `project.db`, verify Project identity, and expose Project-scoped repositories only after the Project store is ready.

This slice establishes the testable persistence shell for all later FakeProvider work. It does not implement workflow execution, ArtifactService import, provider calls, FastAPI routes, frontend code, real migrations, or export output.

## 2. Why this slice comes now

All later slices depend on a verified `app.db + project.db` boundary. Repository, artifact, workflow, quality, idempotency, and recovery tests need real temporary SQLite files and a temporary workspace before they can validate architecture boundaries.

Decisions:

- Use one global `app.db` for Project registry and app migration ledger.
- Use one `project.db` per Project for Project-owned content, workflow, quality, result, artifact, and project migration data.
- Expose Project repositories only after ProjectMetadata identity and migration readiness pass.
- Keep migration support minimal in MVP-0: baseline ledger and verification hooks, not a production Alembic topology.

Rejected alternatives:

- A single SQLite database for all Projects, because it weakens Project isolation and recovery.
- In-memory fake persistence, because it cannot validate recovery, idempotency, migration ledgers, or file/database consistency.
- Exposing repositories before Project open verification, because it permits mutation against mismatched or broken project.db files.

## 3. Inputs from prior designs

- `AGENTS.md`: minimal-change mode, Project isolation, `app.db + project.db`, no image BLOBs, no unrelated files.
- `docs/SRS-v1.0.md`: Project, Batch, Page, task recovery, original image safety, SQLite plus filesystem.
- `docs/HLD.md` and `docs/HLD-v0.2.md`: local Web UI/FastAPI/backend architecture, SQLite/workspace storage, repository boundary.
- `docs/PROJECT-PLAN.md`: Phase 4 MVP-0 single Page backend vertical slice.
- `docs/design/data-model/final/data-model-dd-v0.1.md`: `app.db` and `project.db` split, `ProjectMetadata`, migration ledgers.
- `docs/design/persistence/final/persistence-readiness-dd-v0.1.md`: Project store gate, immediate app/project tables.
- `docs/design/persistence/final/migration-strategy-minimal.md`: independent migration lifecycles and Project open outcomes.
- `docs/implementation/mvp0-fakeprovider-slice/GOAL.md`
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

## 4. Allowed files or directories to change during implementation

For the future implementation task only:

- `pyproject.toml` or equivalent minimal Python project metadata if absent.
- `src/manga_read_flow/**` for backend package foundation, or the existing backend package if one exists by then.
- `tests/integration/test_project_store_init.py`
- `tests/conftest.py`
- `tests/fixtures/**` only for tiny non-sensitive test fixtures.
- Minimal documentation under `docs/implementation/mvp0-fakeprovider-slice/` only if the implementation discovers a plan defect.

## 5. Forbidden changes

- Production Web UI, Next.js, React, or frontend files.
- FastAPI routes or API schemas.
- Real provider integrations.
- SQL DDL design documents, ORM model documentation, or Alembic migration files unless a later task explicitly authorizes them.
- Previous final design documents under `docs/design/**/final/`.
- Export output, ZIP, manifest artifact, or `ExportRecord`.
- Secrets, local config, logs, caches, build outputs, `.codex/`, `.claude/`, `.idea/`, or generated scratch files.
- Any file outside the allowed implementation paths unless the user explicitly approves after seeing a reason.

## 6. Implementation tasks

1. Inspect branch and `git status --short`; stop if unrelated changes exist.
2. Add the smallest backend package skeleton needed for persistence tests.
3. Add a temporary workspace fixture that creates isolated directories and temporary SQLite file paths.
4. Implement app store initialization enough to create or verify `app.db` and an app `schema_migrations` ledger.
5. Implement Project creation/open scaffolding enough to create a Project workspace and `project.db`.
6. Implement project store initialization enough to create or verify `project_metadata` and a project `schema_migrations` ledger.
7. Implement explicit Project open outcomes such as `ready`, `identity_mismatch`, `database_missing`, and `checksum_mismatch` as contract-level values or test-visible outcomes.
8. Ensure Project-scoped repository access is not returned unless open outcome is `ready`.
9. Add integration tests using real temporary SQLite files.

## 7. Validation command or test target

```bash
pytest tests/integration/test_project_store_init.py
```

## 8. Acceptance criteria

- `app.db` initializes in a temporary workspace and records an app migration ledger.
- `project.db` initializes under a Project workspace and records a project migration ledger.
- `ProjectMetadata.project_id` matches the app Project registry id on open.
- Identity mismatch or missing project.db blocks repository exposure.
- Project repository access is available only after open outcome is `ready`.
- No UI/API/export code exists.
- No image bytes or large payloads are stored in SQLite.

## 9. Failure cases to test

- Opening a Project whose `project_metadata.project_id` differs from app registry.
- Opening a Project with a missing `project.db`.
- Opening with a failed or incompatible migration ledger marker.
- Attempting to obtain Project repositories before readiness.
- Creating a second Project with an isolated workspace and project.db.

## 10. Commit strategy

Use one small implementation commit for this slice only after the validation command passes, if the task prompt explicitly allows commits. Stage only files changed for this slice. Do not push.

If validation cannot run because project scaffolding is intentionally incomplete, stop and report the exact blocker instead of committing a partial foundation.

## 11. Risks and scope traps

- Accidentally designing a complete migration framework instead of minimal ledgers and open outcomes.
- Letting Project open silently recreate a missing project.db for an existing Project identity.
- Choosing a package layout that conflicts with a later backend structure. Mitigation: prefer `src/manga_read_flow/**` unless an existing backend package is present.
- Adding FastAPI routes or UI to "prove" Project creation. This slice is backend persistence only.
- Hiding identity or migration failures behind exceptions that tests cannot assert.

## 12. Codex implementation prompt

```text
Goal:
Implement Slice 01, the MVP-0 foundation and Project store initialization needed for temporary app.db/project.db tests.

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/HLD-v0.2.md
- docs/PROJECT-PLAN.md
- docs/design/data-model/final/data-model-dd-v0.1.md
- docs/design/persistence/final/persistence-readiness-dd-v0.1.md
- docs/design/persistence/final/migration-strategy-minimal.md
- docs/implementation/mvp0-fakeprovider-slice/GOAL.md
- docs/implementation/mvp0-fakeprovider-slice/HARNESS.md
- docs/implementation/mvp0-fakeprovider-slice/PLAN.md
- docs/implementation/mvp0-fakeprovider-slice/slices/01-foundation-and-project-store.md

Allowed files:
- pyproject.toml or equivalent minimal Python project metadata if absent
- src/manga_read_flow/**, or the existing backend package if one exists
- tests/integration/test_project_store_init.py
- tests/conftest.py
- tests/fixtures/**

Forbidden files:
- frontend/UI files
- FastAPI route files
- real provider integrations
- Alembic migrations, production SQL DDL, or ORM model documentation unless explicitly authorized
- docs/design/**/final/**
- export output, ZIP, manifest, or ExportRecord code
- secrets, logs, caches, build outputs, local config, .codex/, .claude/, .idea/

Implementation boundaries:
- Repository/DAO remains the only SQLite access entry.
- Project repositories are exposed only after Project identity and migration readiness are verified.
- Do not store image bytes or large payloads in SQLite.
- Do not add UI, API, real providers, or export output.

Validation command:
pytest tests/integration/test_project_store_init.py

Expected output:
- Temporary app.db initialization works.
- Temporary project.db initialization works.
- ProjectMetadata identity is verified.
- Repository access is blocked before readiness.
- Tests document success and failure paths.

Commit rule:
Do not commit unless the user explicitly allows commits for this implementation task. If commits are allowed, stage only the files changed for this slice and make one focused commit after validation passes.

Stop conditions:
- Unrelated dirty working tree exists.
- Implementing this slice requires UI, API routes, real providers, export output, or prior final design doc edits.
- Project open cannot be made test-visible without inventing a broad persistence framework.
- Validation command is unavailable or failing for an unrelated reason.
```
