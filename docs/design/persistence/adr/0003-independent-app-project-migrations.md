# ADR 0003: Independent app.db and project.db Migration Lifecycle

Status: Accepted

## Context

The product stores global data in app.db and Project-owned data in per-Project project.db files. Projects may be moved, restored, backed up, or opened independently. SQLite cannot enforce cross-database foreign keys for this split.

## Decision

Maintain independent `schema_migrations` ledgers in app.db and every project.db.

app.db migration readiness is verified at startup. project.db identity and migration readiness are verified at Project open before project repositories are exposed.

ProjectMetadata inside project.db must match the app.db Project registry entry.

No workflow, recovery, artifact cleanup, or export readiness runs before Project open returns ready.

## Rationale

Independent ledgers preserve Project isolation and backup/restore boundaries. Project open verification prevents accidental use of the wrong database or incompatible schema.

## Rejected Alternatives

- Single global SQLite database for all Projects.
- One app-level ledger for all Project migrations.
- Migrating every Project at app startup.
- Silently replacing missing/mismatched project.db files.
- Cross-database foreign keys.

## Consequences

- Project open can return repair-only or blocked states.
- Restore/relink UX is deferred but must be explicit.
- Migration tests must cover app and project ledgers separately.
