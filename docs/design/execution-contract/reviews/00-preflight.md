# Execution Contract Design Preflight

## 1. Current branch

`main`

## 2. Initial `git status --short`

Clean working tree at preflight start.

## 3. Required file presence check

| Required input | Present | Readable | Notes |
| --- | --- | --- | --- |
| `AGENTS.md` | Yes | Yes | Project governance and architecture invariants. |
| `docs/SRS-v1.0.md` | Yes | Yes | Formal requirements baseline. |
| `docs/HLD.md` | Yes | Yes | HLD file exists; document header says v0.1 while project plan also mentions current HLD-v0.2 as acceptable. |
| `docs/HLD-v0.2.md` | No | N/A | Not required because `docs/HLD.md` is present. |
| `docs/PROJECT-PLAN.md` | Yes | Yes | Development process and FakeProvider milestone baseline. |
| `docs/design/execution-contract/GOAL.md` | Yes | Yes | Goal-specific design scope. |
| `docs/design/execution-contract/HARNESS.md` | Yes | Yes | Goal-specific validation scenarios. |
| `docs/design/execution-contract/PLAN.md` | Yes | Yes | Required phase plan. |
| `docs/design/data-model/final/data-model-dd-v0.1.md` | Yes | Yes | Data model baseline. |
| `docs/design/data-model/final/schema-outline.md` | Yes | Yes | Schema outline; not SQL DDL. |
| `docs/design/data-model/final/state-data-impact.md` | Yes | Yes | State/data impact baseline. |
| `docs/design/workflow-state/final/workflow-state-dd-v0.1.md` | Yes | Yes | Workflow-state baseline. |
| `docs/design/workflow-state/final/state-vocabulary.md` | Yes | Yes | Canonical workflow vocabulary. |
| `docs/design/workflow-state/final/stage-transition-table.md` | Yes | Yes | Legal/illegal transition baseline. |
| `docs/design/workflow-state/final/decision-matrix.md` | Yes | Yes | WorkflowLoopEngine decision ownership baseline. |
| `docs/design/workflow-state/final/recovery-rules.md` | Yes | Yes | Recovery evidence baseline. |
| `docs/design/workflow-state/final/stale-propagation-rules.md` | Yes | Yes | Stale/export-effective rules baseline. |

Required execution-contract directories are present:

- `docs/design/execution-contract/proposals/`
- `docs/design/execution-contract/reviews/`
- `docs/design/execution-contract/final/`
- `docs/design/execution-contract/adr/`

## 4. Non-empty check

| File | Non-empty |
| --- | --- |
| `docs/design/execution-contract/GOAL.md` | Yes |
| `docs/design/execution-contract/HARNESS.md` | Yes |
| `docs/design/execution-contract/PLAN.md` | Yes |

## 5. Authoritative input readability

All required authoritative inputs are readable. No implementation, migration, SQL, ORM, API, frontend, real provider integration, or real prompt-template files need to be read or changed for this design loop.

## 6. Conflicts found

No blocking conflict was found.

Non-blocking vocabulary or version tensions to carry into proposal work:

| Tension | Resolution for Goal 2 |
| --- | --- |
| `docs/HLD.md` header says HLD v0.1, while `docs/PROJECT-PLAN.md` says `docs/HLD.md` or current `HLD-v0.2.md` is accepted as baseline. | Use the existing readable `docs/HLD.md` because PLAN allows `docs/HLD.md` or `docs/HLD-v0.2.md`. Do not modify HLD. |
| HLD and SRS mention some Page/TextBlock quality flags directly, while data model and workflow-state designs use `QualityIssue`, active pointers, and repairable aggregate statuses. | Follow later final data-model/workflow-state baselines for detailed contract behavior; treat earlier flags as user-facing or aggregate summaries. |
| Data model says a typesetting overflow preview artifact may be retained and, if accepted as preview, may update the active typeset pointer; HARNESS says blocking quality should not make the result export-effective. | Distinguish selected preview/history from export-effective output using stale/export-effective rules and open blocking issue checks. |
| Data model includes `artifact_cleanup`; workflow-state excludes it from MVP single-Page happy path. | Keep cleanup vocabulary minimal for ArtifactService design; do not require cleanup execution in the FakeProvider vertical slice. |

## 7. Execution-contract design risks before proposal generation

| Risk | Impact | Mitigation in this design loop |
| --- | --- | --- |
| Provider output may accidentally include workflow decisions. | Violates Provider Adapter boundary. | Provider proposal agents must define strict forbidden responsibilities and standardized result/error envelopes only. |
| Artifact promotion and database registration may be conflated. | Crash recovery and active pointer updates become unclear. | Artifact proposals must distinguish ArtifactService file/metadata lifecycle from WorkflowLoopEngine/Repository transaction acceptance. |
| QualityCheckService may drift into workflow policy. | Splits ownership with WorkflowLoopEngine. | Quality proposals must separate issue classification from retry/fallback/skip/block decisions. |
| StageExecutor may become hidden orchestration engine. | WorkflowLoopEngine ownership becomes ambiguous. | Integration proposal must define narrow stage input/output and return normalized evidence only. |
| FakeProvider may require real OCR/LLM/image tools. | Blocks next milestone. | FakeProvider readiness proposal must require deterministic fake outputs and fake failures only. |
| Secret or sensitive payload retention may be under-specified. | Logs/artifacts could leak keys or local content unexpectedly. | Provider and ArtifactService proposals must include redaction, safety flags, and retention classes. |
| Cross-module vocabulary drift. | HARNESS scenarios become untestable. | Module debate, cross-review, and final synthesis must align stage, issue, error, artifact, and storage vocabularies. |

## 8. Questions that must be answered before proposal agents start

No blocking questions must be answered before Phase 1A.

Known non-blocking questions to keep visible:

- Exact enum enforcement mechanism remains a later persistence-design decision.
- Exact artifact directory layout and temp naming are in scope only at contract level, not as implementation paths.
- Exact ProcessingProfile defaults and retry budgets remain later profile design, except for the minimal fields needed by StageExecutor and WorkflowLoopEngine evidence.
- Exact API DTOs and repository method names remain later design work.

## 9. Whether Phase 1A may proceed

Phase 1A may proceed.

The working tree was clean before this report was created, all required inputs are readable, no blocking source conflict was found, and the planned changes are documentation-only within the execution-contract design area.
