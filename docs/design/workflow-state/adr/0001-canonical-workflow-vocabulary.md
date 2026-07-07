# ADR 0001: Canonical Workflow Vocabulary

## Status

Accepted for workflow-state v0.1.

## Context

Proposals used mixed spellings such as `completed` versus `done`, task `completed` versus `succeeded`, `export` versus `export_check`, and `locked` as a TextBlock stage status. Cross-review requested a single vocabulary.

## Decision

- TextBlock stage completion is `done`, not `completed`.
- ProcessingTask terminal success values are `succeeded` and `succeeded_with_warnings`.
- The workflow stage is `export_check`; actual export records remain export-design scope.
- Page status is a persisted, repairable aggregate, not recovery truth.
- `locked` is not a generic TextBlock stage status. Use `locked_translation_result_id` and lock metadata.

## Consequences

Implementation and tests have stable names. Recovery must inspect durable evidence rather than Page status. Lock handling stays separate from stage progress.
