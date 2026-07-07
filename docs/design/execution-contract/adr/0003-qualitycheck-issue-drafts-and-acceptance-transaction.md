# ADR 0003: QualityCheck Issue Drafts and Workflow Acceptance Transaction

## Status

Accepted for MVP-0.

## Context

The HLD says QualityCheckService generates QualityIssues, while cross-module review found transaction ambiguity if QualityCheckService persists issues independently from WorkflowDecision, result rows, active pointers, and stage statuses.

## Decision

For MVP-0, QualityCheckService owns issue classification but returns `QualityCheckReport` with issue drafts and lifecycle suggestions. WorkflowLoopEngine persists issue lifecycle updates together with:

- WorkflowDecision;
- accepted result rows;
- active pointer updates;
- retry budget after;
- stage statuses;
- Page/Task aggregate status.

This is the loop-owned acceptance transaction.

## Consequences

- Quality classification remains centralized.
- Active pointers, issues, decisions, and statuses cannot drift as easily.
- StageExecutor remains evidence-only.
- Later implementations may let QualityCheckService call Repository for issue persistence only if it still does not advance workflow state or update active pointers.

## Rejected alternatives

| Alternative | Reason rejected |
| --- | --- |
| QualityCheckService persists issues and advances state. | Splits workflow ownership. |
| Provider creates issues directly. | Couples tools to persistence and taxonomy. |
| StageExecutor persists decisions from quality summary. | Turns StageExecutor into a hidden loop engine. |
| Use severity alone for export gate. | `is_blocking` must be explicit and queryable. |
