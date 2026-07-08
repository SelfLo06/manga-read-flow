# No Persistence Revision Needed

## 1. Review Basis

Phase 2 cross-review is recorded in `docs/design/persistence/reviews/01-cross-review.md`.

The cross-review read all authoritative inputs and all five Phase 1 persistence proposals.

## 2. Decision

No limited proposal revision round is required.

The cross-review found no blocking defect in the proposal set. The remaining issues are synthesis decisions, not proposal evidence gaps.

## 3. Synthesis Decisions Still Required

Final synthesis must explicitly decide:

- whether MVP-0 stops at `ready_for_export` or includes actual export records and output artifacts;
- whether StageExecutor persists ToolRunLog/tool evidence through a narrow evidence writer or returns all evidence for WorkflowLoopEngine persistence;
- whether QualityCheckService remains repository-free for MVP-0;
- whether import is an ApplicationService operation or a WorkflowLoopEngine stage for MVP-0;
- whether app-level `provider_configs` and `processing_profiles` are implemented as skeletons or deferred behind deterministic profile snapshot bootstrap;
- which optimistic-concurrency guards protect acceptance transactions;
- how recovery treats official but unselected artifacts after a crash;
- whether `workflow_decision_issues` is required for the first QualityIssue-bearing scenario.

## 4. Whether Synthesis May Proceed

PASS. Final synthesis may proceed.

The synthesizer should use the recommended decisions in the cross-review unless it records a clear rationale for choosing differently.
