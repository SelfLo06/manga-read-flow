Run the Persistence Readiness Design loop for the manga translation workflow project.

This is Goal 3: Persistence Readiness Design.

This task is design-documentation only. Do not implement code, migrations, SQL DDL, SQLAlchemy models, Alembic files, API handlers, frontend code, real provider integrations, or real translation provider prompt templates.

The goal is not to redesign the data model. The goal is to make the existing data model, workflow-state design, and execution-contract design ready for safe persistence implementation.

Use these authoritative inputs:

* `AGENTS.md`
* `docs/SRS-v1.0.md`
* `docs/HLD.md` or `docs/HLD-v0.2.md`
* `docs/PROJECT-PLAN.md`
* `docs/design/persistence/GOAL.md`
* `docs/design/persistence/HARNESS.md`
* `docs/design/persistence/PLAN.md`
* `docs/design/data-model/final/data-model-dd-v0.1.md`
* `docs/design/data-model/final/schema-outline.md`
* `docs/design/data-model/final/state-data-impact.md`
* `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
* `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`

Follow `docs/design/persistence/PLAN.md` exactly.

The design loop must apply software engineering principles as explicit checks, especially:

* Single Responsibility
* Information Hiding
* High Cohesion / Low Coupling
* Dependency Inversion
* Testability
* Recoverability
* Traceability
* Scope Control

The design loop must include exactly five independent proposal agents in Phase 1:

1. Repository Boundary and Module Responsibility Agent
2. Unit of Work and Transaction Boundary Agent
3. Migration and Database Lifecycle Agent
4. Recovery and Idempotency Repository Agent
5. FakeProvider Slice Persistence Readiness Agent

If true parallel execution is unavailable, run proposal agents sequentially while preserving independence. During Phase 1, each proposal agent must not read or depend on other proposal files.

Before starting, inspect the current branch and working tree. If unrelated user changes already exist, stop and report them instead of mixing changes.

Commits are allowed for this documentation design loop only. Commit after each completed phase or completed proposal group, staging only the intended files.

Do not push, pull, rebase, upgrade dependencies, or commit unrelated files.

Never commit `.codex/`, `.claude/`, `.idea/`, logs, caches, build outputs, local config, secrets, temporary files, or implementation code.

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
10. How software engineering principles were applied.
11. Rejected alternatives.
12. Blocking issues, if any.
13. Non-blocking open questions.
14. HARNESS validation summary.
15. Whether the Persistence Readiness Design loop is complete.
16. Whether the design is ready for the next Goal: FakeProvider single-Page backend vertical slice planning.

Do not claim readiness if HARNESS validation was not performed.
Do not fabricate validation results.
