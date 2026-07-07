# ADR 0003: Export Check and Warning Readiness

## Status

Accepted for workflow-state v0.1.

## Context

The data model includes export records, while workflow-state must decide readiness. Warning export policy also needed a clear owner.

## Decision

- `export_check` is a workflow stage/precondition.
- Actual ExportRecord lifecycle, output artifacts, ZIP/manifest behavior, and per-export acknowledgement belong to export design.
- Normal export/readiness blocks unresolved open blocking QualityIssues.
- Warning readiness/export requires `ProcessingProfileSnapshot.allow_warning_export = true`.
- Skipped TextBlocks or all-skipped Pages cannot produce pure `ready_for_export`; they are warning-bearing or blocked.

## Consequences

Workflow can finish Pages as pure ready or warning-ready without absorbing full export design. Export remains data-driven and cannot silently bypass blockers.
