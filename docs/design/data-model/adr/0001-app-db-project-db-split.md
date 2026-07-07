# ADR 0001: app.db and project.db Split

## Status

Accepted.

## Context

The product must isolate Project data, support local backup/restore, prevent cross-project glossary/result leakage, and keep a global Project list available before opening any Project workspace.

## Decision

Use `app.db` for global registry/settings and one `project.db` per Project for Project-owned content, workflow, quality, artifact, glossary, task, and export data. Do not use cross-database foreign keys.

## Rationale

`app.db` can list Projects, locate workspaces, and manage global profiles/provider config. `project.db` keeps each Project portable and recoverable with its local files. Avoiding cross-db FKs keeps SQLite behavior predictable.

## Rejected alternatives

- Single global SQLite database: simpler global queries, weaker isolation and larger deletion/corruption blast radius.
- Project data in app.db with project_id filters: easy to leak cross-project data by query mistake.
- Cross-database ORM relationships: fragile session and FK semantics.

## Consequences

- Project open must verify app.db Project row against project.db ProjectMetadata.
- Cross-project dashboards require explicit app-level summary/index design later.
- Migrations run independently for app.db and each project.db.

## Validation

Supports same filename in different Projects, Project soft delete/restore, per-project glossary isolation, and restart recovery using only the Project workspace plus app registry.
