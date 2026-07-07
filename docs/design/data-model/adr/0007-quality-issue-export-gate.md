# ADR 0007: QualityIssue Export Gate

## Status

Accepted.

## Context

The app must allow warning-only outputs when policy permits, but normal export must reject unresolved blocking issues.

## Decision

Normal export queries `QualityIssue` for open blocking issues within the export target scope. Warning export follows the active `ProcessingProfileSnapshot.allow_warning_export` policy. Blocked export attempts are recorded as `ExportRecord.status = blocked`.

## Rationale

Export safety should be a data query, not hidden UI logic. Recording rejected attempts explains why export did not produce an artifact.

## Rejected alternatives

- Gate export only by Page.status: can drift from issue state.
- Let warnings always export: ignores strict profiles.
- Allow normal export with blockers: violates safety and HLD.

## Consequences

- QualityIssue status semantics must be explicit.
- ExportRecord stores issue counts/hash and optional snapshot artifact.
- P1 forced/incomplete export must be a distinct advanced path.

## Validation

Supports export blocked by unresolved blocking issue, warning-only export under profile policy, accepted warnings, and export history after later edits.
