# Code Health Gate

Version: v0.1  
Status: Engineering baseline  
Scope: Implementation slices, code review, AI-assisted coding, and maintainability control

---

## 1. Purpose

The Code Health Gate controls non-bug defects introduced during implementation.

A non-bug defect is code that may pass tests today but makes the system harder to change, harder to test, harder to recover, or easier to break later.

This gate focuses on:

- architecture boundary drift;
- responsibility drift;
- excessive coupling;
- low cohesion;
- information leakage;
- fragile state handling;
- weak testability;
- large-file growth;
- AI-generated code bloat.

This document is a high-priority engineering rule. It applies to every implementation slice after the functional validation for that slice passes.

---

## 2. Authority and Precedence

This gate must preserve the current project baselines:

- SRS;
- HLD;
- final detailed designs;
- implementation slice documents;
- architecture invariants recorded in existing plans.

This document does not override accepted design baselines. When this document and a final design conflict, stop and report the conflict.

A Code Health Gate pass may refactor local implementation details. It may not expand product scope or change accepted architecture decisions.

---

## 3. Scope

Run this gate after a functional implementation slice passes its focused tests.

Review only the current slice diff unless the user explicitly authorizes a broader review.

The gate may:

- identify smells;
- fix local safe smells;
- add focused tests for boundary failures;
- split files along already accepted architecture boundaries;
- report deferred risks.

The gate may not:

- introduce new product features;
- implement real providers unless the slice explicitly allows it;
- add UI, API, frontend, export, ZIP, or manifest behavior unless the slice explicitly allows it;
- rewrite final design baselines;
- perform broad cross-slice refactors;
- perform formatting-only rewrites across unrelated files.

---

## 4. Severity Categories

### A. Architecture Boundary Smells — Blocking

These must be fixed before merge or explicitly escalated.

#### Provider Adapter

Blocking smells:

- accesses Repository, DAO, SQLite, ORM session, cursor, `app.db`, or `project.db`;
- registers official artifacts;
- writes active OCR, translation, cleaned, or typeset pointers;
- creates `QualityIssue`;
- creates `WorkflowDecision`;
- decides retry, fallback, skip, warning, block, pause, cancel, or readiness;
- stores secrets in logs, snapshots, artifacts, or database rows;
- contains provider-policy bypass or evasion behavior.

Preferred direction:

- Provider returns structured provider results, standardized errors, temporary outputs, and sanitized metadata only.

#### StageExecutor

Blocking smells:

- owns retry, fallback, skip, warning, block, pause, cancel, or readiness logic;
- updates active pointers;
- creates `WorkflowDecision`;
- creates or lifecycle-manages `QualityIssue`;
- receives broad repository access;
- holds SQLite write transactions during provider calls;
- selects latest artifact or result by timestamp.

Preferred direction:

- StageExecutor executes one stage, calls Provider Adapter or local tool, records narrow tool evidence through `StageEvidenceWriter`, and returns evidence to WorkflowLoopEngine.

#### ArtifactService

Blocking smells:

- decides workflow retry, fallback, skip, warning, block, pause, cancel, or readiness;
- selects active page outputs;
- directly mutates workflow state;
- allows path traversal outside the Project workspace;
- overwrites original images;
- treats filesystem paths as workflow source of truth.

Preferred direction:

- ArtifactService owns official artifact lifecycle: path generation, atomic write or promotion, hash, metadata registration, storage state, missing or corrupt detection, and cleanup boundaries.

#### QualityCheckService

Blocking smells:

- advances workflow state;
- updates active pointers;
- directly persists issues in MVP-0 unless explicitly authorized by design;
- creates `WorkflowDecision`;
- performs provider calls;
- rewrites artifacts or result versions.

Preferred direction:

- QualityCheckService returns quality reports, issue drafts, severity, blocking flag, attribution, and suggested action keys.

#### WorkflowLoopEngine

Blocking smells:

- directly uses SQL, ORM sessions, cursors, or table-shaped row dictionaries;
- calls Provider Adapter without StageExecutor when the stage design requires StageExecutor;
- uses filesystem paths as source of truth for active artifacts;
- selects active result or artifact by latest timestamp;
- treats `Page.status` as recovery source of truth;
- performs official artifact lifecycle operations directly;
- bypasses QualityCheckService for quality classification.

Preferred direction:

- WorkflowLoopEngine owns decisions, acceptance, retry budgets, fallback, skip, warning, block, readiness, and recovery decisions through repository contracts and ArtifactService reports.

#### Repository / DAO

Blocking smells:

- exposes raw connections, cursors, sessions, or SQL to workflow/application/provider layers;
- becomes a generic `Repository<T>` with table-shaped CRUD as the main abstraction;
- embeds provider calls, artifact filesystem writes, or workflow policy decisions;
- uses cross-database foreign keys between `app.db` and `project.db`;
- stores image bytes or large payloads in SQLite.

Preferred direction:

- Repository / DAO is the only SQLite access entry and exposes named, task-oriented operations.

#### Data and Recovery

Blocking smells:

- original images are overwritten;
- image bytes or large payloads are stored in SQLite;
- recovery relies only on `Page.status`;
- normal export or readiness ignores unresolved blocking `QualityIssue`;
- warning readiness silently becomes pure readiness;
- active output selection uses timestamps;
- stale OCR, translation, cleaned, or typeset outputs become export-effective without validation, rerun, or explicit reuse decision.

Preferred direction:

- Use active pointers, dependency hashes, artifacts, attempts, decisions, tool logs, issues, and stage statuses as durable evidence.

---

### B. Modularity and Responsibility Smells — Usually Fix Before Merge

These usually indicate design erosion. Fix locally when safe.

Smells:

- God class or God service;
- one file mixes orchestration, persistence, provider calls, quality checking, artifact lifecycle, and readiness;
- helper module becomes a dumping ground;
- duplicated state transition logic;
- duplicated active pointer update logic;
- duplicated acceptance transaction logic;
- concrete implementation types leak through public interfaces;
- public mutable state;
- message chains such as `a.getB().getC().doSomething()`;
- over-wide interfaces that force clients to depend on unused methods;
- cross-layer imports that violate HLD dependency direction;
- domain DTOs contain persistence, provider, or filesystem behavior;
- workflow policy is scattered across multiple services.

Preferred directions:

- split by responsibility;
- introduce narrow contracts;
- delegate to the module that owns the information;
- move state transitions into one workflow-owned place;
- keep public APIs small and intention-revealing;
- hide data layout, SQL shape, artifact paths, and provider temp outputs.

---

### C. Testability Smells — Fix When Local, Otherwise Record Risk

Smells:

- provider calls happen inside SQLite write transactions;
- FakeProvider mode is hidden in global state;
- time, UUID, hash, workspace path, provider mode, or retry budget cannot be controlled in tests;
- critical boundary is covered only by broad full-suite tests;
- failure paths have no focused tests;
- tests assert only `Page.status` rather than durable evidence;
- tests depend on local absolute paths;
- tests depend on network, real OCR, real LLM, or GPU during FakeProvider slices;
- tests require ordering by latest timestamp to pass.

Preferred directions:

- inject clocks, UUID factories, workspace roots, and FakeProvider modes;
- use temporary real SQLite files for persistence slices;
- use focused integration tests for boundary behavior;
- assert attempts, decisions, issues, artifacts, active pointers, and dependency hashes;
- keep real provider integration behind explicit Spike or later slice scope.

---

### D. Local Readability Smells — Opportunistic

Fix when it is safe and small.

Smells:

- unclear names;
- magic strings;
- duplicated small blocks;
- long `if/elif` chains;
- unclear exception messages;
- excessive comments compensating for poor structure;
- inconsistent enum or status naming;
- local functions with hidden side effects;
- broad `except Exception` without normalization.

Preferred directions:

- rename private helpers;
- extract small private functions;
- replace magic strings with existing enums or constants;
- improve error normalization;
- keep comments for rationale, not for explaining tangled control flow.

---

## 5. Design Principles Applied as Review Rules

Use these principles as practical review questions.

### Responsibility Assignment

Ask:

- What is this module responsible for?
- What data does it maintain?
- What operation does it perform?
- Does it have more than one reason to change?

Smells:

- a service both orchestrates workflow and writes SQL;
- a provider both calls tools and creates domain rows;
- a repository both persists data and decides workflow policy.

Preferred direction:

- keep data responsibility and behavior responsibility close when appropriate;
- keep orchestration, persistence, quality classification, provider calls, and artifact lifecycle separate.

---

### Collaboration

Ask:

- Which objects collaborate to complete this behavior?
- Is the collaboration explicit and testable?
- Does one object know too much about the internals of another?

Smells:

- deep message chains;
- service reaches through several objects to mutate nested state;
- workflow code depends on provider-specific response internals.

Preferred direction:

- use narrow DTOs and explicit stage results;
- let each module expose behavior, not internal structure.

---

### Information Expert

Ask:

- Which module has the information needed to make this decision?
- Is the decision located there?

Project-specific mapping:

- workflow decision → WorkflowLoopEngine;
- quality classification → QualityCheckService;
- official artifact state → ArtifactService plus artifact metadata repository;
- SQLite query and persistence → Repository / DAO;
- provider invocation details → Provider Adapter;
- acceptance transaction → WorkflowLoopEngine through Unit of Work.

Smell:

- a module makes a decision while depending on another module’s hidden internals.

Preferred direction:

- move the behavior to the module that owns the needed information, or expose a narrow query/report.

---

### Creator

Ask:

- Who has the data required to create this object safely?
- Who should create official domain rows?

Project-specific mapping:

- Provider Adapter may create provider output DTOs only;
- StageExecutor may create stage evidence only;
- WorkflowLoopEngine acceptance creates accepted OCR/Translation result versions and active pointer changes;
- ArtifactService creates official artifact metadata;
- Repository persists rows through named operations.

Smell:

- Provider creates `OCRResult`, `TranslationResult`, `QualityIssue`, or official artifact rows.

Preferred direction:

- keep provider outputs as candidates until accepted by the workflow.

---

### Controller

Ask:

- Which module receives and coordinates the system event?

Project-specific mapping:

- API handler validates and delegates;
- ApplicationService owns use-case entry;
- WorkflowLoopEngine controls workflow decisions;
- StageExecutor controls one stage execution only;
- TaskRunner runs background tasks.

Smell:

- API handler performs long workflow execution;
- StageExecutor becomes a hidden WorkflowLoopEngine;
- Repository starts controlling task progress.

Preferred direction:

- keep control at the correct abstraction level.

---

### Low Coupling

Ask:

- Can this module change without forcing unrelated modules to change?
- Does it depend on concrete implementation details?

Smells:

- workflow imports concrete SQLite repository implementation;
- provider imports repository modules;
- tests require internal table names;
- public APIs expose implementation-specific DTOs.

Preferred direction:

- depend on narrow contracts;
- keep concrete implementation behind adapters or repositories.

---

### High Cohesion

Ask:

- Do all functions in this file serve one clear responsibility?
- Would a new developer know where to add a related behavior?

Smells:

- `workflow_loop.py` contains decision policy, recovery, acceptance, readiness, provider calls, and persistence mapping;
- `repositories.py` contains every query in the system;
- `utils.py` contains unrelated helpers.

Preferred direction:

- split by accepted architecture boundary or cohesive responsibility.

---

### Law of Demeter

Ask:

- Is the caller talking only to its direct collaborators?
- Is it navigating another object’s internal structure?

Smells:

- `a.getB().getC().doSomething()`;
- workflow code reads nested provider internals;
- service reaches through repository return objects to mutate nested data.

Preferred direction:

- add a domain method, service method, query method, or DTO that expresses the needed operation directly.

---

### Program to Interfaces

Ask:

- Does the caller depend on a contract or a concrete implementation?
- Can the implementation be replaced in tests?

Smells:

- application or workflow code depends on `Sqlite...` classes directly;
- provider implementation is hardcoded where a provider contract should be used;
- FakeProvider cannot be swapped for real provider adapter later.

Preferred direction:

- use narrow protocol/interface/contract-like boundaries where replacement is expected.

---

### Interface Segregation

Ask:

- Does the caller receive more methods than it needs?
- Could the interface allow forbidden writes?

Smells:

- StageExecutor receives broad repositories;
- QualityCheckService receives persistence writers;
- Provider receives context with database or artifact registration capability;
- one repository interface exposes unrelated operations.

Preferred direction:

- split into narrow interfaces such as `StageEvidenceWriter`, readiness query, artifact metadata query, result version writer, and workflow acceptance operation.

---

### Liskov Substitution and Inheritance Coupling

Ask:

- Can a subclass replace the parent without changing behavior expectations?
- Is inheritance being used for implementation reuse?

Smells:

- subclass overrides parent method with different semantics;
- test FakeProvider inherits real provider and disables major behavior;
- base class contains workflow policy and subclasses override only parts of it.

Preferred direction:

- prefer composition and explicit strategy objects;
- use pure abstract contracts when polymorphism is needed.

---

### Composition Over Inheritance

Ask:

- Is behavior assembled from collaborators, or buried in a parent class?

Smells:

- deep inheritance hierarchy for providers, repositories, or stage executors;
- subclass requires knowledge of parent internals;
- overriding methods to disable behavior in tests.

Preferred direction:

- compose provider clients, mappers, validators, and policies through narrow collaborators.

---

### Information Hiding

Ask:

- What design decision does this module hide?
- Is that hidden detail leaking?

Project-specific hidden details:

- SQLite schema and SQL details;
- artifact filesystem paths and temp paths;
- provider-specific response format;
- retry budget storage;
- active pointer update mechanics;
- readiness query mechanics;
- recovery reconciliation details.

Smells:

- workflow code depends on table names;
- UI/API receives artifact filesystem paths as authoritative data;
- provider temp paths leak into official metadata without ArtifactService;
- result selection depends on timestamp ordering.

Preferred direction:

- expose stable operations and reports, not internal representation.

---

### Encapsulate Change

Ask:

- What is likely to change?
- Is that variation isolated?

Likely change points:

- OCR provider;
- translation provider;
- cleaner;
- typesetter;
- quality policy;
- retry/fallback policy;
- artifact retention;
- repository implementation;
- API schema;
- UI review flow.

Smells:

- provider-specific logic spreads into workflow;
- quality thresholds are hardcoded in multiple places;
- artifact retention logic appears outside ArtifactService.

Preferred direction:

- isolate changing policy or provider behavior behind the owning module.

---

### Least Privilege

Ask:

- Does this caller have only the capability it needs?

Smells:

- StageExecutor receives full Unit of Work;
- Provider receives Project repositories;
- QualityCheckService receives active pointer writer;
- tests use private internals when public evidence would work.

Preferred direction:

- pass narrow capabilities;
- deny access by API shape, not by convention.

---

## 6. File Size Policy

Line count is not a design rule by itself, but large files are strong evidence of responsibility drift.

Project thresholds for hand-written Python product code:

| File size | Policy |
| --- | --- |
| <= 400 lines | Normal. |
| 400–700 lines | Acceptable when responsibility is cohesive. |
| 700–1000 lines | Review trigger. Explain why the file remains cohesive. |
| > 1000 lines | Split by responsibility unless explicitly justified. |
| > 2000 lines | Severe smell. Must be split or escalated before merge. |

Allowed exceptions:

- generated code;
- vendored third-party code;
- one-off migration or bootstrap scripts with clear labels;
- rare test fixture generation scripts.

Normally unacceptable at 2000+ lines:

- workflow modules;
- repositories;
- provider adapters;
- artifact services;
- application services;
- domain models;
- quality services;
- stage executors.

Preferred split examples:

```text
workflow/
  engine.py
  decision_policy.py
  acceptance.py
  readiness.py
  recovery.py
  retry_budget.py
  stage_plan.py
````

```text
persistence/
  project_identity_repository.py
  content_state_repository.py
  result_version_repository.py
  workflow_execution_repository.py
  quality_issue_repository.py
  artifact_metadata_repository.py
  readiness_query_repository.py
  unit_of_work.py
```

---

## 7. Slice Integration

Standard implementation flow:

```text
1. Implement the slice.
2. Run the focused slice test.
3. Run Code Health Gate on the current diff.
4. Apply local safe refactors only.
5. Rerun the focused slice test.
6. Run full pytest if feasible.
7. Commit only when validation passes and commit is authorized.
```

The Code Health Gate runs after functional correctness is established, so refactoring has a working safety net.

Do not use this gate to expand the slice.

---

## 8. Review Checklist

### Provider Adapter

Check:

* no database imports;
* no repository or Unit of Work access;
* no official artifact registration;
* no QualityIssue creation;
* no WorkflowDecision creation;
* no retry/fallback/skip/warning/block/readiness logic;
* no policy bypass or evasion behavior;
* secrets are never persisted;
* outputs are structured and sanitized.

### StageExecutor

Check:

* calls provider outside SQLite write transactions;
* writes only narrow tool evidence;
* does not update active pointers;
* does not decide final workflow outcome;
* does not create QualityIssues or WorkflowDecisions;
* handles refusal/failure/invalid output as evidence;
* does not promote temp files except through ArtifactService.

### ArtifactService

Check:

* all official artifacts go through ArtifactService;
* paths are project-relative in metadata;
* path traversal is blocked;
* original images are immutable;
* missing/hash-invalid detection reports artifact state only;
* no workflow outcome decisions.

### QualityCheckService

Check:

* repository-free unless explicitly authorized;
* classifies issues without advancing workflow state;
* returns issue drafts/reports;
* does not update active pointers;
* does not call providers;
* does not persist decisions.

### WorkflowLoopEngine

Check:

* owns decisions and acceptance;
* no direct SQL/session/cursor usage;
* no provider call bypassing StageExecutor;
* no timestamp-based active selection;
* no `Page.status`-only recovery;
* uses profile snapshot policy;
* records decisions and issue links where required;
* guards acceptance with expected state and dependency hashes.

### Repository / Unit of Work

Check:

* hides SQLite details;
* no raw session/cursor/connection escapes;
* no generic table-shaped repository as primary abstraction;
* named operations align with workflow needs;
* provider code cannot access persistence;
* write transactions are short;
* provider calls are outside write transactions;
* acceptance transaction is guarded.

### Domain DTOs / Value Objects

Check:

* no database behavior;
* no filesystem side effects;
* no provider calls;
* no workflow decisions;
* immutable where practical;
* names reflect domain concepts;
* no large payloads embedded.

### Tests

Check:

* focused integration test exists for slice behavior;
* architecture boundary failure is tested when relevant;
* durable evidence is asserted;
* tests do not depend on real providers during FakeProvider slices;
* tests do not require absolute local paths;
* failure/refusal/invalid-output paths are covered when in scope.

### File Size

Check:

* any file above 700 lines has a clear reason;
* any file above 1000 lines has a split plan or explicit justification;
* any product file above 2000 lines blocks merge unless escalated.

---

## 9. Allowed Refactors During Code Health Gate

Allowed when local and safe:

* extract private helpers;
* split a file along existing architecture boundaries;
* rename unclear private functions, classes, or variables;
* replace direct concrete dependencies with existing contracts;
* add focused tests for discovered boundary smells;
* remove duplicated local logic;
* normalize local error handling;
* replace magic strings with existing enums or constants;
* reduce message chains through delegation;
* narrow an interface when no accepted public contract is broken.

---

## 10. Forbidden Refactors During Code Health Gate

Forbidden without explicit authorization:

* new product features;
* real provider integration;
* API/UI/frontend changes unless the slice allows them;
* export output, ZIP, manifest, or `ExportRecord` unless the slice allows export;
* final design baseline changes;
* broad formatting-only rewrites;
* large cross-slice refactors;
* public contract changes requiring design approval;
* migration strategy changes;
* dependency upgrades;
* CI/toolchain expansion;
* cleanup scheduler or retention policy expansion outside slice scope.

---

## 11. Stop Conditions

Stop and report when:

* unrelated dirty working tree exists;
* fixing the smell requires broader architecture redesign;
* the current slice boundaries are insufficient;
* final design documents appear wrong, missing, or contradictory;
* product behavior would change outside the slice;
* validation cannot run;
* a required fix touches forbidden files;
* a code smell reveals an unresolved design decision;
* a file exceeds 2000 lines and cannot be split safely inside the current slice.

A stopped Code Health Gate should produce a short report with the blocker and recommended next action.

---

## 12. Validation

Minimum validation after local refactor:

```bash
pytest <focused-slice-test>
```

Preferred validation when feasible:

```bash
pytest <focused-slice-test>
pytest -q
```

Optional checks only when already configured:

```bash
ruff check .
mypy .
markdownlint docs/engineering/code-health-gate.md
```

Do not add new tooling during a Code Health Gate pass unless a separate task authorizes it.

---

## 13. Codex Review Prompt Pattern

Use this after a slice implementation has passed its focused test.

```text
Goal:
Perform a Code Health Review Pass for the current implementation slice.

This is not a feature implementation task. Review the current slice diff for non-bug code smells and architecture boundary drift. Fix only local, safe issues within the current slice boundaries.

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/engineering/code-health-gate.md
- the exact slice document that was just implemented
- relevant final detailed designs for the touched modules

Scope:
Review only files changed in the current slice diff.

Check for:
- architecture boundary violations;
- responsibility drift;
- excessive coupling;
- low cohesion;
- information leakage;
- message chains;
- public mutable state;
- concrete implementation leakage;
- over-wide interfaces;
- provider/stage/artifact/quality/workflow/repository boundary drift;
- provider calls inside write transactions;
- timestamp-based active selection;
- Page.status-only recovery;
- large-file growth;
- tests that pass while hiding important boundary failures.

Allowed changes:
- local refactors inside files already changed by the slice;
- splitting a changed file along accepted architecture boundaries;
- focused test additions for discovered boundary smells;
- private helper extraction;
- private renaming;
- removing duplicated local logic.

Forbidden changes:
- new product features;
- real provider integration;
- API/UI/frontend changes unless the slice explicitly allowed them;
- export output, ZIP, manifest, or ExportRecord unless the slice explicitly allowed them;
- docs/design/**/final/**;
- broad formatting-only rewrites;
- cross-slice refactors;
- public contract changes without explicit authorization;
- dependency or toolchain changes.

Validation:
Run the focused slice test.
Then run pytest -q if feasible.

Stop conditions:
- unrelated dirty working tree exists;
- fixing the smell requires broader design work;
- required changes touch forbidden files;
- validation cannot run;
- current slice scope is insufficient;
- a product file exceeds 2000 lines and cannot be safely split in this pass.

Final report:
- files reviewed;
- smells found;
- smells fixed;
- smells deferred;
- validation commands and results;
- confirmation that no forbidden files changed;
- confirmation that no architecture boundary was violated;
- remaining risks.
```

---

## 14. Final Report Requirements

Every Code Health Gate pass must report:

* files reviewed;
* smells found;
* smells fixed;
* smells deferred;
* tests or commands run;
* pass/fail result;
* validation skipped and reason, if any;
* forbidden files touched: yes/no;
* final design baselines changed: yes/no;
* architecture boundary violation remaining: yes/no;
* file size risks remaining.

Do not claim success when validation did not run.

---

## 15. Merge Rule

A slice should not be merged when:

* any Category A smell remains;
* focused tests fail;
* validation did not run without a clear accepted reason;
* forbidden files changed;
* final design baselines changed without explicit authorization;
* hand-written product code exceeds 2000 lines without escalation;
* the implementation expanded beyond the slice.

A slice may merge with documented Category C or D issues only when:

* the issue is non-blocking;
* the risk is recorded;
* the next action is clear;
* architecture boundaries remain intact.