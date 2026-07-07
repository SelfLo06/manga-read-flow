# ADR 0009: Soft Delete and Trash

## Status

Accepted.

## Context

Users can accidentally delete Projects, Batches, Pages, or TextBlocks. The system must preserve recovery context and artifact traceability until permanent deletion is confirmed.

## Decision

Use soft delete first. Project soft delete marks app.db Project lifecycle fields and moves or marks workspace files as trash-pending. Batch/Page/TextBlock deletions set deleted metadata and make associated artifacts trash-eligible. Permanent deletion requires explicit confirmation.

## Rationale

Soft delete protects ordinary users, keeps workflow history explainable, and allows restore before permanent cleanup.

## Rejected alternatives

- Immediate hard delete: breaks restore and audit.
- Never delete artifacts: grows disk usage and retains sensitive debug data too long.
- Delete database rows while leaving files: creates orphaned artifacts.

## Consequences

- Artifact storage state records trash/missing/deleted outcomes.
- Restore validates file paths and hashes.
- Deleted records are hidden from normal processing/export but remain until purge.

## Validation

Supports Project soft delete/restore, file cleanup after retention, missing trash file detection, and export history retention after output deletion.
