# Execution Contract Design GOAL

## 1. Objective

Define the MVP execution contracts between:

* `StageExecutor`
* Provider Adapters
* `ArtifactService`
* `QualityCheckService`
* `WorkflowLoopEngine`

This design must make the single-Page FakeProvider backend vertical slice implementable without introducing real OCR, translation, cleaning, or typesetting integrations.

The goal is not to fully design each service. The goal is to define the minimum contracts needed for safe execution, artifact registration, quality checking, and workflow decisions.

## 2. Scope

This design covers:

* Minimal Provider Adapter input/output/error contract.
* Minimal Provider metadata and capability contract.
* Minimal ArtifactService contract for official artifacts.
* Minimal artifact type and storage state vocabulary.
* Minimal QualityCheckService contract.
* Minimal P0 IssueType / severity / blocking contract.
* StageExecutor execution boundary.
* FakeProvider readiness requirements.
* How provider output becomes artifact, result, issue, and workflow evidence.

## 3. Non-goals

This design does not cover:

* Production code.
* SQL DDL.
* ORM mappings.
* Database migrations.
* FastAPI routes.
* Frontend UI.
* Full DTO implementation.
* Full repository method design.
* Full ProcessingProfile management.
* Full ExportRecord / ZIP manifest design.
* Real provider integrations.
* Real OCR / LLM / cleaning / typesetting parameters.
* Real translation prompt templates.
* P1/P2 features.

## 4. Source documents

Use these inputs:

* `AGENTS.md`
* `docs/SRS-v1.0.md`
* `docs/HLD.md` or `docs/HLD-v0.2.md`
* `docs/PROJECT-PLAN.md`
* `docs/design/data-model/final/data-model-dd-v0.1.md`
* `docs/design/data-model/final/schema-outline.md`
* `docs/design/data-model/final/state-data-impact.md`
* `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
* `docs/design/workflow-state/final/state-vocabulary.md`
* `docs/design/workflow-state/final/stage-transition-table.md`
* `docs/design/workflow-state/final/decision-matrix.md`
* `docs/design/workflow-state/final/recovery-rules.md`
* `docs/design/workflow-state/final/stale-propagation-rules.md`

## 5. Architecture invariants

The design must preserve these rules:

* Provider Adapter only calls tools and returns structured outputs or standardized errors.
* Provider Adapter must not access SQLite.
* Provider Adapter must not register official artifacts.
* Provider Adapter must not create `QualityIssue`.
* Provider Adapter must not decide retry, fallback, skip, warning, pause, cancel, or block.
* ArtifactService is the only official artifact lifecycle entry.
* Repository / DAO is the only SQLite access entry.
* WorkflowLoopEngine owns workflow decisions.
* QualityCheckService checks outputs and classifies issues, but does not advance workflow state.
* StageExecutor executes one stage but does not make final workflow decisions.
* Original images are never overwritten.
* Image files and large payloads are not stored in SQLite.
* Active pointers remain the source of truth for current OCR, translation, cleaned image, and typeset image.
* Provider refusal is a first-class workflow path, not a crash.
* No provider policy bypass or evasion logic is allowed.

## 6. Required design questions

The final design must answer:

### Provider Adapter

* What common result envelope does every Provider Adapter return?
* How are success, failure, timeout, invalid output, and refusal represented?
* What metadata must every provider output include?
* What temporary files may a provider return?
* What must a provider never do?
* What minimal contracts are needed for Detector, OCR, Translation, Cleaner, and Typesetter?

### ArtifactService

* What is an official artifact?
* How are temporary files promoted into official artifacts?
* When are paths, hashes, media type, size, and storage state recorded?
* What artifact types are required for MVP?
* How is a missing artifact detected and reported?
* Which artifacts must be retained for MVP?
* What does ArtifactService decide, and what does it not decide?

### QualityCheckService

* What input does QualityCheckService receive?
* What output does it return?
* What minimal IssueTypes are required for MVP?
* How are severity and `is_blocking` determined?
* How are `discovered_stage` and `root_stage` assigned?
* How are provider refusal, invalid JSON, partial translation, cleaning skip, and typesetting overflow represented?
* What does QualityCheckService never decide?

### StageExecutor

* What is the StageExecutor input contract?
* What is the StageExecutor output contract?
* What sequence should a stage follow?
* What is the transaction boundary before and after provider calls?
* What should be returned to WorkflowLoopEngine for decision making?

### FakeProvider

* What fake modes are required for MVP validation?
* How does FakeProvider simulate happy path, failure, refusal, invalid JSON, partial output, cleaning skip, typesetting overflow, and missing artifact?
* What evidence should FakeProvider produce so workflow, artifact, quality, and recovery behavior can be tested?

## 7. Required outputs

Final synthesis should produce:

* `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`
* `docs/design/execution-contract/final/provider-adapter-contract.md`
* `docs/design/execution-contract/final/artifact-service-contract.md`
* `docs/design/execution-contract/final/quality-check-contract.md`
* `docs/design/execution-contract/final/stage-executor-contract.md`
* `docs/design/execution-contract/final/error-and-issue-taxonomy-minimal.md`
* `docs/design/execution-contract/final/fakeprovider-readiness.md`
* `docs/design/execution-contract/final/open-questions.md`

ADR files are optional. Create ADRs only for cross-cutting or controversial decisions.

## 8. Scope control

Keep this design minimal.

Do not design a generic plugin framework, full event bus, distributed worker protocol, complete DTO library, complete issue catalog, or complete artifact retention scheduler.

The design only needs to support the next implementation milestone:

```text
FakeProvider single-Page backend vertical slice
```

## 9. Exit criteria

This design goal is complete when:

* Provider Adapter, ArtifactService, QualityCheckService, and StageExecutor boundaries are clear.
* The final contract can support FakeProvider single-Page workflow execution.
* HARNESS scenarios are PASS or explicitly deferred with reason.
* No architecture invariant is violated.
* No P1/P2 feature is required for MVP-0.
