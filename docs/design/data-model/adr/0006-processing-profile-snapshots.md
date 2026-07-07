# ADR 0006: ProcessingProfile Snapshots

## Status

Accepted.

## Context

ProcessingProfile controls retry budgets, fallback, warning export, debug retention, and cleanup policy. Editable profile templates can change after a task runs.

## Decision

Store mutable ProcessingProfile templates in app.db. Store immutable `ProcessingProfileSnapshot` rows in project.db for tasks, attempts, decisions, and exports.

## Rationale

Historical workflow behavior must remain explainable after profile edits. Snapshots also make Project recovery independent of mutable app-level profile state.

## Rejected alternatives

- Store only `profile_id` on tasks: historical meaning changes after edits.
- Copy raw API keys into snapshots: violates secret boundary.
- Separate P0 ProjectConfig table: duplicates profile/default/provider responsibilities.

## Consequences

- Snapshots include schema version, serialized policy, and hash.
- Provider config references may be included; raw secrets are not.
- Warning export uses the effective snapshot, not the current template.

## Validation

Supports warning export replay, successful payload cleanup policy, retry budget recovery, and provider fallback explanation after global profile edits.
