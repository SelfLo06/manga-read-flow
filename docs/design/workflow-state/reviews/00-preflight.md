# Workflow-State Core Design Preflight

## 1. Current Branch

`main`

## 2. Initial Git Status

Initial `git status --short --untracked-files=all` before creating workflow-state output directories and this report:

```text
<clean>
```

No unrelated user changes were present at the time Phase 0 began.

## 3. Required File Presence Check

| Required input | Present | Notes |
| --- | --- | --- |
| `AGENTS.md` | PASS | Readable. |
| `docs/SRS-v1.0.md` | PASS | Readable. |
| `docs/HLD.md` | PASS | Readable authoritative HLD per `AGENTS.md`. |
| `docs/HLD.md` | PASS | Also present and checked for alignment because the goal allows either HLD. |
| `docs/PROJECT-PLAN.md` | PASS | Readable. |
| `docs/design/workflow-state/GOAL.md` | PASS | Readable. |
| `docs/design/workflow-state/HARNESS.md` | PASS | Readable. |
| `docs/design/workflow-state/PLAN.md` | PASS | Readable. |
| `docs/design/data-model/final/data-model-dd-v0.1.md` | PASS | Readable. |
| `docs/design/data-model/final/schema-outline.md` | PASS | Readable. |
| `docs/design/data-model/final/state-data-impact.md` | PASS | Readable. |
| `docs/design/data-model/final/open-questions.md` | PASS | Readable. |

Required output directories were created if absent:

- `docs/design/workflow-state/proposals/`
- `docs/design/workflow-state/reviews/`
- `docs/design/workflow-state/final/`
- `docs/design/workflow-state/adr/`

## 4. Non-Empty GOAL / HARNESS / PLAN Check

| File | Non-empty | Line count |
| --- | --- | ---: |
| `docs/design/workflow-state/GOAL.md` | PASS | 138 |
| `docs/design/workflow-state/HARNESS.md` | PASS | 252 |
| `docs/design/workflow-state/PLAN.md` | PASS | 585 |

## 5. Authoritative Input Readability

All required authoritative inputs are readable. The design loop can rely on:

- `AGENTS.md` for collaboration, boundaries, data invariants, and commit rules.
- `docs/SRS-v1.0.md` for product scope, functional requirements, MVP/P1/P2 boundaries, status candidates, retry/fallback expectations, and acceptance criteria.
- `docs/HLD.md` for architecture boundaries, workflow loop ownership, quality gates, provider adapter boundaries, artifact ownership, and recovery requirements.
- `docs/PROJECT-PLAN.md` for phase sequencing and the FakeProvider-first implementation direction.
- Workflow-state `GOAL.md`, `HARNESS.md`, and `PLAN.md` for the exact loop execution and deliverables.
- Data-model final documents for active pointers, attempt/decision persistence, artifact metadata, provider refusal persistence, crash recovery source-of-truth, export gates, and known non-blocking questions.

## 6. Conflicts and Source Tensions

No blocking conflict was found that prevents Phase 1 proposal generation.

Non-blocking tensions to carry into proposals and synthesis:

| Topic | Source tension | Preflight handling |
| --- | --- | --- |
| HLD version | `AGENTS.md` names `docs/HLD.md`; the goal allows `docs/HLD.md`. | Use `docs/HLD.md` as the required AGENTS input and current baseline. |
| Exact enum spellings | SRS/HLD include candidate statuses; data-model final explicitly leaves exact enum spellings open. | Phase 1 and final synthesis must define MVP vocabulary clearly enough for implementation guidance without writing DDL. |
| Page aggregate status source | Data-model final asks whether Batch/Page aggregate status is persisted with reconciliation or mostly derived in early implementation. | Treat as a design question for the workflow-state final; recovery must not rely only on `Page.status`. |
| QualityCheckService boundary | HLD and data-model documents say QualityCheckService creates or generates `QualityIssue`; architecture rules say QualityCheckService owns detection/attribution but must not advance workflow state. | Synthesis should clarify whether QualityCheckService returns issue classifications for repository persistence inside WorkflowLoopEngine transactions, while still owning detection and attribution. |
| Warning export acknowledgement | Data-model open questions ask whether warning export needs explicit per-export user acknowledgement in addition to profile policy. | Non-blocking for MVP workflow-state; final design should keep warning export governed by `ProcessingProfileSnapshot` and defer extra acknowledgement if needed. |
| Forced/incomplete export | HLD mentions possible advanced forced export, but GOAL/HARNESS forbid P1 forced export as an MVP prerequisite. | Defer forced/incomplete export to P1 and exclude it from MVP readiness. |
| Automatic fallback | SRS notes some fallback behavior may be manual/P1; HLD/workflow-state goal need retry/fallback decision rules. | Define minimal MVP decision semantics that work with FakeProvider and do not require advanced provider orchestration UI. |

## 7. Workflow-State Design Risks Before Proposal Generation

- Status vocabulary drift could create duplicate sources of truth between `Page.status`, TextBlock stage statuses, active pointers, attempts, decisions, and issues.
- Retry/fallback/skip/warning/block rules could become too broad and accidentally require P1/P2 provider orchestration.
- Recovery may become unsafe if it trusts a single aggregate status instead of active pointers, hashes, artifacts, attempts, decisions, and issues.
- User edits can leave export-effective stale outputs unless active pointer changes and downstream stale propagation are atomic.
- Provider refusal could be mishandled as a crash or generic failure unless refusal remains first-class and auditable.
- Artifact missing states could be hidden by successful result rows unless recovery checks artifact storage state and active artifact pointers.
- Infinite loops are possible if retries, upstream retries, fallback, warning, and pause decisions do not have explicit budgets and terminal states.
- Export gates could be weakened if warning export and normal export are not separated.
- Proposal agents may overdesign a generic workflow engine, distributed worker model, or P1/P2 features unless scope control remains explicit.

## 8. Questions Before Proposal Subagents Start

No blocking question must be answered before Phase 1.

Questions to assign into Phase 1 and final synthesis:

1. What exact MVP status vocabulary is allowed for `ProcessingTask`, `WorkflowAttempt`, `Page`, and TextBlock stage fields?
2. Which `Page.status` values are persisted versus derived or reconciled?
3. Which `WorkflowDecision` types consume retry budget, and how is loop termination guaranteed?
4. How should QualityCheckService-owned issue detection be persisted without letting QualityCheckService advance workflow state?
5. Which minimal `ProcessingProfileSnapshot` policy fields are needed for retry, fallback, skip, warning export, pause, block, and retention-sensitive decisions?
6. How should missing artifacts alter stage status, active pointers, issues, and recovery decisions?
7. How should OCR and translation edits mark prior `QualityIssue` rows as stale or superseded?

## 9. Phase 1 May Proceed

PASS. Phase 1 may proceed with five independent proposal subagents.

Subagents must not read or depend on other workflow-state proposal files during Phase 1. Each subagent may read only the authoritative inputs and must write only its own proposal file.
