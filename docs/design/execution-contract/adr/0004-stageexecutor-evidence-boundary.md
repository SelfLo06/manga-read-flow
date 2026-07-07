# ADR 0004: StageExecutor Evidence Boundary

## Status

Accepted.

## Context

StageExecutor is needed to run one stage but can easily become a hidden WorkflowLoopEngine if it interprets provider errors, artifact failures, or quality reports as retry/fallback/skip/block decisions.

## Decision

StageExecutor executes exactly one bounded attempt and returns `StageResult` evidence.

It may:

- persist running attempt before provider call;
- build provider request DTOs;
- call one provider/local tool operation;
- normalize provider output;
- call ArtifactService;
- call QualityCheckService;
- return candidate outputs and issue evidence.

It must not decide retry, fallback, upstream retry, skip, warning acceptance, pause, cancel, block, readiness, active pointer selection, cache reuse selection, or locked-translation overwrite.

## Consequences

- WorkflowLoopEngine remains the only workflow decision owner.
- No SQLite write transaction is held across provider calls.
- Recovery can reason about running attempts, provider evidence, artifact registration, and acceptance separately.
- FakeProvider tests exercise the same boundary as real providers.

## Rejected alternatives

| Alternative | Reason rejected |
| --- | --- |
| StageExecutor retries/falls back internally. | Retry budgets and decisions become unrecoverable. |
| StageExecutor marks active pointers after provider success. | Skips quality/workflow acceptance. |
| StageExecutor performs cache reuse selection. | Cache reuse is tied to active pointers, locks, profile, and workflow state. |
| Hold DB transaction across provider call. | Long locks and poor crash/pause/cancel behavior. |
