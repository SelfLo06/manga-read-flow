# ADR 0004: Recovery Source of Truth Is Committed Evidence and Active Pointers

Status: Accepted

## Context

Crash recovery must determine whether to resume, reuse, retry, pause, warn, or block. Page.status is only an aggregate UI/filtering state and can drift from active pointers, attempts, artifacts, and issues.

## Decision

Recovery source of truth is committed evidence:

- ProcessingTask and heartbeat;
- WorkflowAttempt;
- WorkflowDecision and WorkflowDecisionIssue;
- ToolRunLog;
- active OCR/translation/artifact pointers;
- OCRResult and TranslationResult dependency hashes;
- ProcessingArtifact storage state and hash;
- QualityIssue status/severity/blocking;
- TextBlock stage statuses;
- ProcessingProfileSnapshot policy.

Page.status is repairable summary only.

Official but unselected artifacts after crash are evidence/reuse candidates only. They are never selected by timestamp.

## Rationale

Committed evidence explains what actually happened, what was accepted, what remains stale, and what can be reused. Page.status alone cannot explain partial acceptance, missing files, or locked/manual selections.

## Rejected Alternatives

- Recover from Page.status alone.
- Select latest result/artifact by timestamp.
- Promote orphan temp files by default.
- Treat provider refusal as generic crash.

## Consequences

- Recovery queries must load richer evidence bundles.
- Recovery can be conservative when evidence is incomplete.
- Tests must include crash-after-acceptance and registered-but-unselected artifact scenarios.
