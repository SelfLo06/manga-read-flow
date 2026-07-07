# ADR 0002: Artifact Promotion and Unselected Official Artifacts

## Status

Accepted.

## Context

Provider outputs can be files. Official artifacts need path, hash, size, media, retention, storage state, safety flags, scope, and provenance. SQLite and filesystem updates are not one atomic resource. Active pointers are the current result source of truth.

## Decision

A file becomes an official artifact only after ArtifactService promotes or writes bytes under the owning Project workspace and commits `processing_artifact` metadata through Repository / DAO.

Artifact registration does not update active pointers and does not make output export-effective. Registered but unselected artifacts are audit/reuse candidates. WorkflowLoopEngine acceptance later selects active pointers and result rows in its decision transaction.

Temp, orphan, staging, and quarantine files are not official storage states.

## Consequences

- Providers never choose official paths or artifact ids.
- Artifact registration failures are distinct from provider failures.
- Recovery can explain DB/filesystem partial states.
- Bad or blocked outputs can remain auditable without becoming current.

## Rejected alternatives

| Alternative | Reason rejected |
| --- | --- |
| Provider writes official workspace paths. | Breaks ArtifactService ownership and path safety. |
| File path alone means official artifact. | Cannot explain hash, scope, retention, storage state, or provenance. |
| ArtifactService updates active pointers on registration. | Bypasses quality and workflow acceptance. |
| Store file bytes in SQLite for transaction atomicity. | Violates project invariants and hurts performance/privacy. |
