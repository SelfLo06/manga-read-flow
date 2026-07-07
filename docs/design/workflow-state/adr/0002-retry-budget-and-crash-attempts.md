# ADR 0002: Retry Budget and Crash Attempts

## Status

Accepted for workflow-state v0.1.

## Context

The loop needs finite retry behavior. Proposals agreed retry decisions should be auditable, but crash-abandoned attempts could either consume normal retry budget or loop forever if unbounded.

## Decision

- Retry budget is consumed when WorkflowLoopEngine persists `retry_same_stage` or `retry_upstream_stage`.
- WorkflowAttempt mirrors retry budget before/after for audit.
- `abandoned_after_crash` does not consume normal provider retry budget by itself.
- Automatic recovery retries after abandoned attempts are bounded by a separate `crash_recovery_retry_budget` or equivalent task-level crash retry ceiling.
- Implementations should also enforce a hard per-task automatic decision ceiling.

## Consequences

Failed attempts remain factual evidence, while decisions explain why another attempt was authorized. Repeated crashes cannot loop forever, and ordinary provider retry budgets are not unexpectedly exhausted by process death alone.
