# Persistence Readiness Design PLAN

You are the orchestrator for Goal 3: Persistence Readiness Design.

This plan defines the design-documentation loop for the minimal persistence readiness design needed before implementing the FakeProvider single-Page backend vertical slice.

This is not a data-model redesign.
This is not implementation.
This is not a full ORM or migration specification.

The goal is to make persistence implementation ready while preserving software engineering principles:

* Single Responsibility
* Information Hiding
* High Cohesion / Low Coupling
* Dependency Inversion
* Testability
* Recoverability
* Traceability
* Scope Control

Do not implement code.
Do not create SQL DDL.
Do not create SQLAlchemy models.
Do not create Alembic migrations.
Do not create FastAPI routes.
Do not create frontend code.
Do not create real provider integrations.
Do not modify SRS, HLD, PROJECT-PLAN, data-model final documents, workflow-state final documents, or execution-contract final documents.

---

## Execution Mode

Prefer parallel proposal agents when available.

If true parallel execution is unavailable, run proposal agents sequentially while preserving independence.

During Phase 1, proposal agents must not read or depend on other proposal files.

Each proposal agent writes only its own proposal file.

Proposal agents must not edit review files, final files, ADR files, or unrelated files.

---

## Commit Rule

Commits are allowed for this documentation design loop.

Before each commit:

1. Inspect `git status --short`.
2. Inspect `git diff -- <target-file-or-directory>`.
3. Stage only intended files.
4. Commit only after the relevant phase or file group is complete.

Do not push.
Do not pull.
Do not rebase.
Do not upgrade dependencies.
Do not commit `.codex/`, `.claude/`, `.idea/`, logs, caches, build outputs, local config, secrets, or temporary files.

If unrelated user changes already exist before starting, stop and report them.

---

# Phase 0: Preflight Validation

Create:

* `docs/design/persistence/reviews/00-preflight.md`

The preflight report must include:

1. Current branch.
2. Initial `git status --short`.
3. Required file presence check.
4. Whether `GOAL.md`, `HARNESS.md`, and `PLAN.md` are non-empty.
5. Whether authoritative inputs are readable.
6. Any conflict between source documents.
7. Persistence-specific design risks.
8. Whether Phase 1 may proceed.

Required source documents:

* `AGENTS.md`
* `docs/SRS-v1.0.md`
* `docs/HLD.md`
* `docs/PROJECT-PLAN.md`
* `docs/design/persistence/GOAL.md`
* `docs/design/persistence/HARNESS.md`
* `docs/design/persistence/PLAN.md`
* `docs/design/data-model/final/data-model-dd-v0.1.md`
* `docs/design/data-model/final/schema-outline.md`
* `docs/design/data-model/final/state-data-impact.md`
* `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
* `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`

If blocking issues exist, stop after writing the preflight report.

Commit message:

```text id="iiakb4"
docs: add persistence preflight report
```

---

# Phase 1: Independent Proposal Agents

Use exactly five independent proposal agents.

Each proposal should be concise, implementation-readiness focused, and scenario-driven.

Do not restate the full data model.
Do not invent new P0 entities unless a documented blocker proves they are required.
Do not write DDL.
Do not write ORM code.
Do not list every possible repository method.
Focus on minimal contracts and transaction readiness.

## 1. Repository Boundary and Module Responsibility Agent

Output:

* `docs/design/persistence/proposals/01-repository-boundary-agent.md`

Focus:

* Repository / DAO as the only SQLite access boundary.
* Repository grouping.
* What each application module may depend on.
* Information hiding and dependency inversion.
* Avoiding SQL/ORM leakage into WorkflowLoopEngine, ArtifactService, QualityCheckService, StageExecutor, API handlers, and Provider Adapter.

Must answer:

* What repository groups are needed for MVP-0?
* Which modules are allowed to call which repository contracts?
* What must never depend on ORM/session details?
* How does this preserve single responsibility and information hiding?
* What repository complexity should be deferred?

## 2. Unit of Work and Transaction Boundary Agent

Output:

* `docs/design/persistence/proposals/02-unit-of-work-transaction-agent.md`

Focus:

* Unit of Work boundary.
* Transaction scope for stage execution.
* Acceptance transaction.
* Crash-safe transaction sequence.
* Avoiding long DB write transactions across provider calls.

Must answer:

* What transaction boundaries are required before provider call, after provider call, after artifact registration, and during workflow acceptance?
* Which writes must commit atomically?
* What can be separate short transactions?
* What failure modes must be recoverable?
* How are active pointer/status/issue/decision drift prevented?

## 3. Migration and Database Lifecycle Agent

Output:

* `docs/design/persistence/proposals/03-migration-db-lifecycle-agent.md`

Focus:

* app.db initialization.
* project.db initialization.
* independent schema migration ledgers.
* Project open verification.
* Workspace/project identity.
* Migration safety and resumability.

Must answer:

* How are app.db and project.db initialized?
* How is project.db identity verified?
* How are migrations tracked independently?
* What is the minimal migration strategy before MVP-0?
* What migration details are deferred?
* How does the strategy support backup, restore, and project isolation?

## 4. Recovery and Idempotency Repository Agent

Output:

* `docs/design/persistence/proposals/04-recovery-idempotency-agent.md`

Focus:

* Queries needed for crash recovery.
* Queries needed for idempotent rerun.
* Reuse lookup keys.
* Stale task and abandoned attempt reconciliation.
* Active pointer and artifact validation support.

Must answer:

* How does recovery find stale running tasks?
* How does recovery reconcile running attempts?
* What data must be loaded to avoid relying only on Page.status?
* How does idempotency find reusable OCR, translation, cleaned, and typeset outputs?
* How are skipped, stale, blocked, missing, and warning states handled?
* What indexes are minimally important for recovery/reuse?

## 5. FakeProvider Slice Persistence Readiness Agent

Output:

* `docs/design/persistence/proposals/05-fakeprovider-slice-readiness-agent.md`

Focus:

* Minimal table/entity subset for FakeProvider single-Page backend slice.
* Minimal repository capabilities needed by the first implementation milestone.
* What can be stubbed, simplified, or deferred.
* Testability using temporary SQLite.

Must answer:

* What is the minimum persistence scope for create project → import page → fake workflow → ready_for_export?
* Which entities/tables are required immediately?
* Which entities can be present as minimal skeletons?
* Which entities can be deferred?
* What temporary SQLite integration tests should this design enable?
* What would be overengineering for MVP-0?

## Proposal Structure

Each proposal must use this structure:

1. Scope
2. Role Bias
3. Assumptions
4. Minimal Proposal
5. Repository / Transaction / Migration Implications
6. Software Engineering Principle Checks
7. Recovery / Idempotency Impact
8. FakeProvider Slice Impact
9. HARNESS Scenario Coverage
10. Rejected Alternatives
11. Risks
12. Open Questions

## Phase 1 Hard Rules

* Do not implement code.
* Do not write SQL DDL.
* Do not write ORM model code.
* Do not write migration files.
* Do not design full API routes.
* Do not design frontend behavior.
* Do not edit final files.
* Do not edit ADR files.
* Do not modify another proposal.
* Do not invent a generic persistence framework.
* Do not introduce event sourcing, distributed transactions, CQRS, or a plugin persistence layer for MVP.
* Do not make Provider Adapter depend on Repository.
* Do not make WorkflowLoopEngine depend on SQL or ORM session internals.
* Do not store images or large payloads in SQLite.
* Do not make Page.status the recovery source of truth.
* If unclear, list as open question.

Commit all five proposals together.

Commit message:

```text id="l5o4z1"
docs: add persistence readiness proposals
```

---

# Phase 2: Cross-Review

Create:

* `docs/design/persistence/reviews/01-cross-review.md`

The cross-reviewer must read:

* all authoritative inputs;
* all five proposal files;
* GOAL;
* HARNESS;
* PLAN.

The review must include:

1. Summary of each proposal.
2. Agreements.
3. Conflicts.
4. Missing repository boundaries.
5. Missing Unit of Work / transaction boundaries.
6. Migration lifecycle gaps.
7. Recovery and idempotency gaps.
8. FakeProvider slice readiness gaps.
9. Software engineering principle violations.
10. Scope creep.
11. Recommended final decisions.
12. ADR candidates.
13. Blocking issues.
14. Non-blocking issues.
15. Open questions that block synthesis.
16. Open questions that do not block synthesis.

Commit message:

```text id="9a6c8j"
docs: add persistence cross review
```

---

# Phase 3: Limited Revision

If the cross-review finds blocking issues, run at most one revision round.

Rules:

* Revise only affected proposal files.
* Add `Revision Notes` to revised proposal files.
* Do not edit final files.
* Do not edit ADR files.
* Do not edit unrelated files.
* Do not silently remove open questions.

Commit message:

```text id="s2gd6h"
docs: revise persistence readiness proposals
```

Then create or update:

* `docs/design/persistence/reviews/02-revision-review.md`

Commit message:

```text id="wk52th"
docs: add persistence revision review
```

If no blocking issues exist, create:

* `docs/design/persistence/reviews/02-no-blocking-revision-needed.md`

Commit message:

```text id="q60psw"
docs: note no persistence revision needed
```

If blockers remain after one revision round, stop and report them.

---

# Phase 4: Final Synthesis

If synthesis may proceed, create final documents.

The synthesizer may edit only:

* `docs/design/persistence/final/persistence-readiness-dd-v0.1.md`
* `docs/design/persistence/final/repository-contract-minimal.md`
* `docs/design/persistence/final/unit-of-work-and-transactions.md`
* `docs/design/persistence/final/migration-strategy-minimal.md`
* `docs/design/persistence/final/fakeprovider-persistence-readiness.md`
* `docs/design/persistence/final/open-questions.md`
* `docs/design/persistence/adr/*.md`

The final synthesis must include:

1. Design goals.
2. Source documents.
3. Software engineering principle application.
4. app.db / project.db boundary.
5. Minimal persistence scope for FakeProvider slice.
6. Required entity/table priority.
7. Repository group responsibilities.
8. Module dependency rules.
9. Unit of Work boundary.
10. Transaction sequences.
11. Acceptance transaction.
12. Recovery query requirements.
13. Idempotency query requirements.
14. Minimal migration strategy.
15. Minimal correctness constraints and indexes.
16. Testability plan with temporary SQLite.
17. Scenario replay against HARNESS.
18. Rejected alternatives.
19. Risks and mitigations.
20. ADR list.
21. Open questions and deferred decisions.

The final design must preserve:

* Repository / DAO is the only SQLite access entry.
* Provider Adapter must not access SQLite.
* WorkflowLoopEngine must not depend on SQL or ORM session internals.
* ArtifactService owns official artifact lifecycle but not workflow decisions.
* QualityCheckService does not advance workflow state.
* Active pointers are the source of truth.
* Images and large payloads are not stored in SQLite.
* Recovery does not rely only on Page.status.
* Normal export blocks unresolved open blocking QualityIssue.
* No P1/P2 feature is required for MVP-0.

Commit message:

```text id="kxdiro"
docs: add persistence readiness detailed design
```

---

# Phase 5: HARNESS Validation

Create:

* `docs/design/persistence/reviews/03-harness-validation.md`

The validation agent must read:

* `docs/design/persistence/HARNESS.md`
* all final design files
* ADR files if present

The validation report must include:

1. Invariant checklist with PASS / FAIL / UNCLEAR.
2. Scenario replay results with PASS / FAIL / UNCLEAR.
3. Repository boundary gaps.
4. Transaction boundary gaps.
5. Migration strategy gaps.
6. Recovery/idempotency gaps.
7. FakeProvider slice readiness gaps.
8. Software engineering principle check results.
9. Whether design is acceptable for FakeProvider single-Page backend vertical slice implementation.

For each HARNESS scenario, include:

* Required repository capability
* Required transaction boundary
* Required persisted evidence
* Recovery or idempotency impact
* Boundary check
* PASS / FAIL / UNCLEAR

Commit message:

```text id="h9sb1h"
docs: add persistence harness validation
```

---

# Final Report

At the end, report:

1. Current branch.
2. Final `git status --short`.
3. Commits created.
4. Files changed.
5. Proposal files created.
6. Review files created.
7. Final design files created.
8. ADR files created.
9. Key persistence decisions.
10. Software engineering principles applied.
11. Rejected alternatives.
12. Blocking issues, if any.
13. Non-blocking open questions.
14. HARNESS validation summary.
15. Whether the design is ready for the next Goal: FakeProvider single-Page backend vertical slice planning.

Do not push.

Do not claim readiness if HARNESS validation was not performed.
Do not fabricate validation results.