# ADR 0008: Provider Refusal Handling

## Status

Accepted.

## Context

Cloud providers can refuse content. The app must comply with provider policies and must not treat refusal as a generic crash or attempt to bypass it.

## Decision

Persist provider refusal as:

- `ToolRunLog` with refusal status/error metadata.
- `WorkflowAttempt` with refused outcome.
- `QualityIssue` with provider refusal issue type and root attribution.
- `WorkflowDecision` choosing fallback, warning, skip, manual path, or block.

Provider adapters only return structured refusal information.

## Rationale

Refusal affects workflow control, export readiness, user explanation, and fallback policy. It belongs in the same trace model as other quality and workflow decisions.

## Rejected alternatives

- Store refusal only in error_message: not queryable and not export-gate aware.
- Let provider adapter decide fallback: violates separation of concerns.
- Retry refusal blindly: risks policy bypass behavior and wasted calls.

## Consequences

- Refusal issue taxonomy must be standardized.
- Evidence artifacts may be retained under failed/debug policy.
- WorkflowLoopEngine owns policy reaction.

## Validation

Supports provider refusal scenario with fallback/manual/block, quality report visibility, and no provider-policy bypass semantics.
