# Persistence Readiness Preflight

## 1. Current Branch

`main`

## 2. Initial `git status --short`

Clean working tree at preflight start.

## 3. Required File Presence Check

| Required input | Status |
| --- | --- |
| `AGENTS.md` | Present |
| `docs/SRS-v1.0.md` | Present |
| `docs/HLD.md` | Present |
| `docs/HLD.md` | Present |
| `docs/PROJECT-PLAN.md` | Present |
| `docs/design/persistence/GOAL.md` | Present |
| `docs/design/persistence/HARNESS.md` | Present |
| `docs/design/persistence/PLAN.md` | Present |
| `docs/design/data-model/final/data-model-dd-v0.1.md` | Present |
| `docs/design/data-model/final/schema-outline.md` | Present |
| `docs/design/data-model/final/state-data-impact.md` | Present |
| `docs/design/workflow-state/final/workflow-state-dd-v0.1.md` | Present |
| `docs/design/execution-contract/final/execution-contract-dd-v0.1.md` | Present |

## 4. GOAL / HARNESS / PLAN Non-Empty Check

| File | Status |
| --- | --- |
| `docs/design/persistence/GOAL.md` | Non-empty |
| `docs/design/persistence/HARNESS.md` | Non-empty |
| `docs/design/persistence/PLAN.md` | Non-empty |

## 5. Authoritative Input Readability

All required source documents are readable.

`docs/HLD.md` is the promoted HLD baseline because it explicitly reconciles the data-model, workflow-state, Provider Adapter, ArtifactService, export gate, active pointer, and recovery decisions.

## 6. Source Document Conflict Check

No current blocking source conflict prevents Phase 1.

Resolved history note: earlier preflight attempts observed `docs/design/persistence/PLAN.md` duplicated the HARNESS content. The current file is a distinct `# Persistence Readiness Design PLAN`, so the design loop can now follow the plan exactly.

Non-blocking tensions to carry into proposals and synthesis:

- `docs/PROJECT-PLAN.md` still lists several detailed designs as pending, while workflow-state and execution-contract final documents now exist. Treat the final documents as current authoritative inputs for persistence readiness.
- `docs/design/execution-contract/final/execution-contract-dd-v0.1.md` originally reflected an older HLD path state. Use the current promoted `docs/HLD.md` baseline for this loop while preserving execution-contract final decisions unless a hard conflict is found.
- Workflow-state uses `export_check` for readiness, while the data model includes `export` / `ExportRecord`. Persistence design must keep readiness checks and export records distinct.
- QualityCheckService may create/classify issue drafts or issues depending on design layer wording. Execution-contract final chooses issue drafts for MVP-0, with WorkflowLoopEngine persisting issue lifecycle changes in the acceptance transaction. Persistence design should preserve that for implementation readiness.

## 7. Persistence-Specific Design Risks

| Risk | Why it matters | Mitigation to require in proposals |
| --- | --- | --- |
| Repository boundary leakage | SQL, ORM sessions, or SQLite details leaking into WorkflowLoopEngine, ArtifactService, QualityCheckService, StageExecutor, API handlers, or Provider Adapter would break information hiding and testability. | Define repository contract groups and forbidden dependencies. |
| Transaction drift | Active pointers, result rows, QualityIssues, WorkflowDecision, retry budgets, and stage statuses can diverge if accepted in separate uncoordinated writes. | Define a short Unit of Work acceptance transaction. |
| Long write transaction across provider call | Provider calls may hang or fail, causing locks and poor recovery. | Persist attempt start first, call provider outside write transaction, then commit short outcome/acceptance transactions. |
| Recovery relying on `Page.status` | Page status is repairable aggregate state, not recovery truth. | Require stale task, running attempt, active pointer, result hash, artifact state, ToolRunLog, QualityIssue, and decision queries. |
| Idempotency under-specified | Reruns could duplicate provider calls or overwrite locked/user-edited results. | Define lookup keys for OCR, translation, cleaned, and typeset reuse plus auditable reuse decisions. |
| Artifact metadata/file drift | Registered files can be missing or unselected; temp files can be orphaned. | Keep ArtifactService as lifecycle owner, Repository as metadata owner, WorkflowLoopEngine as decision owner. |
| Migration lifecycle ambiguity | app.db and each project.db migrate independently; project identity must be verified before use. | Define minimal migration ledgers, open verification, and deferred migration details. |
| Scope creep into ORM/API/provider work | This loop is readiness design only. | Keep outputs to docs and avoid DDL, ORM, route, frontend, prompt, or real provider designs. |

## 8. Whether Phase 1 May Proceed

PASS. Phase 1 may proceed with exactly five independent proposal agents:

1. Repository Boundary and Module Responsibility Agent.
2. Unit of Work and Transaction Boundary Agent.
3. Migration and Database Lifecycle Agent.
4. Recovery and Idempotency Repository Agent.
5. FakeProvider Slice Persistence Readiness Agent.

Phase 1 guardrails:

- Each proposal agent must read the authoritative inputs independently.
- During Phase 1, proposal agents must not read or depend on other persistence proposal files.
- Each proposal agent may write only its own proposal file.
- No code, SQL DDL, ORM models, migrations, API handlers, frontend code, real provider integrations, or real prompt templates may be created.
