# Minimal Migration Strategy v0.1

## 1. Purpose

This document defines the minimal app.db and project.db lifecycle needed before the FakeProvider single-Page backend vertical slice.

It is not a migration tool specification and contains no DDL.

## 2. Core Decision

Use independent migration lifecycles:

- app.db has its own `schema_migrations`.
- every project.db has its own `schema_migrations`.
- app.db never records project.db migrations as authoritative.
- project.db migrations run per Project after Project identity is verified.

## 3. app.db Lifecycle

Startup sequence:

1. Resolve workspace app.db path.
2. If app.db is missing, initialize it and apply app baseline migrations.
3. If app.db exists, verify migration ledger and checksums.
4. Apply pending compatible app migrations.
5. Block startup mutation if an applied migration checksum mismatches.
6. Expose Project listing/open operations only after app.db is ready.

Immediate app tables:

- `projects`
- `schema_migrations`

Skeleton or follow-up app tables:

- `provider_configs`
- `processing_profiles`
- `global_settings`

MVP-0 may create deterministic project-local ProcessingProfileSnapshots without full provider/profile UI, as long as the app schema keeps room for later app-level templates.

## 4. project.db Lifecycle

Project creation sequence:

1. Generate Project identity.
2. Create Project workspace directory.
3. Initialize project.db under the Project directory.
4. Apply project baseline migrations.
5. Write ProjectMetadata with project identity and workspace identity evidence.
6. Verify ProjectMetadata.
7. Register/finalize app.db Project row.

Project open sequence:

1. Load Project registry row from app.db.
2. Resolve project.db path.
3. Open project.db for metadata check.
4. Verify ProjectMetadata.project_id matches app registry Project id.
5. Verify migration ledger and compatibility.
6. Apply pending compatible project migrations.
7. Return ready Project persistence context.

If any check fails, project repositories are not exposed.

## 5. Project Open Outcomes

Project open must return explicit outcomes:

- `ready`
- `app_migration_required`
- `app_migration_failed`
- `project_migration_required`
- `project_migration_failed`
- `identity_mismatch`
- `database_missing`
- `database_unreadable`
- `checksum_mismatch`
- `newer_incompatible_schema`
- `repair_required`

Exact UI/API representation is deferred. Workflow must only run for `ready`.

## 6. Migration Application Rules

- Apply one migration at a time.
- Commit migration effects and ledger update together for that database.
- Checksum mismatch blocks further mutation.
- No workflow processing while project migration is running.
- Stable string values for stages, statuses, decisions, issue types, artifact states, and error codes must be additive.
- Historical audit rows are not rewritten just to rename values.
- JSON fields that may evolve must include schema/version markers.
- Do not rewrite OCR or translation text during migrations. If semantic correction is needed later, create a new result version or migration note.

## 7. Compatibility Rules

MVP-0 must support:

- empty app.db initialization;
- empty project.db initialization;
- compatible forward migration of MVP-created databases;
- independent app/project migration ledgers;
- Project open identity verification.

MVP-0 does not need:

- downgrade migrations;
- legacy production backfills;
- online migration of all Projects at startup;
- automatic repair of mismatched Projects;
- restore/relink UX;
- migration across released incompatible versions.

Opening a newer incompatible project.db must block mutation. Read-only inspection can be designed later.

## 8. Backup, Restore, and Workspace Moves

Design assumptions:

- Project backup is the Project directory, including project.db and project-relative artifacts.
- app.db backup preserves global registry/templates.
- Artifact paths are project-relative to support workspace moves.
- ProjectMetadata provides identity evidence after restore.

Restore/relink is deferred, but silent guessing is forbidden:

- if same Project identity appears in multiple paths, require explicit restore/relink decision later;
- if app row points to missing project.db, do not create a replacement with same identity automatically;
- if project.db identity mismatches app row, block workflow and mark repair required.

## 9. Migration and Recovery Relationship

Recovery runs only after Project identity and schema readiness pass.

Migration logic must not:

- infer workflow success from Page.status, result rows, or artifact timestamps;
- select active pointers;
- register official artifacts;
- decide retry/fallback/warning/block;
- rewrite historical attempts, decisions, issues, or result text.

After migration, normal recovery uses tasks, attempts, decisions, active pointers, artifacts, tool logs, QualityIssues, dependency hashes, and TextBlock statuses.

## 10. Temporary SQLite Tests

Migration/lifecycle tests for MVP-0:

- initialize empty app.db and verify app ledger;
- initialize empty project.db and verify project ledger;
- create Project and reopen it through app registry;
- fail Project open when ProjectMetadata project_id mismatches;
- fail Project open when project.db is missing;
- fail mutation when migration checksum mismatches;
- add a stable string status in test fixture without requiring historical rewrite;
- verify project repositories are not exposed until open outcome is `ready`.

## 11. Deferred Details

- exact migration tool: Alembic app/project streams, two environments, or lightweight runner;
- migration file naming;
- workspace identity format;
- multi-process project lock implementation;
- backup manifest;
- restore/relink UX;
- newer-version read-only behavior;
- orphan directory cleanup policy.
