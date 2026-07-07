# ADR 0005: Workflow Recovery Source of Truth

## Status

Accepted.

## Context

The app must recover after crashes, avoid duplicate provider calls, and support Page/TextBlock partial retry. Page status alone cannot explain what completed or what should be rerun.

## Decision

Recovery reads the combination of ProcessingTask, TextBlock stage statuses, active pointers, WorkflowAttempt, WorkflowDecision, ToolRunLog, ProcessingArtifact, and QualityIssue. Page/Batch statuses are aggregate UI summaries, not the sole recovery source.

Crash vocabulary:

- `interrupted`
- `recovering`
- `abandoned_after_crash`

## Rationale

Crashes can occur after provider output, artifact write, artifact registration, result creation, active pointer update, or status update. Recovery needs multiple persisted records to reconcile safely.

## Rejected alternatives

- Trust only Page.status: too coarse.
- Replay only logs: inefficient and loses explicit current state.
- Reset all running stages to pending: causes duplicate provider calls.

## Consequences

- Attempts start before provider calls and complete after outcome persistence.
- Cache reuse is recorded as attempt/decision state.
- Recovery has to reconcile evidence and repair statuses.

## Validation

Supports restart after OCR, crash after provider output, crash after active pointer update, and unchanged TextBlock rerun without duplicate provider calls.
