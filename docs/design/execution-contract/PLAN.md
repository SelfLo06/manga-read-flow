# Execution Contract Design PLAN

You are the orchestrator for Goal 2: Execution Contract Design.

This plan defines the detailed execution steps for the MVP execution contracts among:

* Provider Adapters
* ArtifactService
* QualityCheckService / IssueType
* StageExecutor
* WorkflowLoopEngine decision input

This is a design-documentation task only.

Do not implement code.
Do not create migrations.
Do not write SQL DDL.
Do not write ORM models.
Do not write API handlers.
Do not write frontend code.
Do not write real provider integrations.
Do not write real translation provider prompt templates.
Do not modify SRS, HLD, PROJECT-PLAN, data-model final documents, or workflow-state final documents.

The purpose of this design is to make the next milestone possible:

```text
FakeProvider single-Page backend vertical slice
```

## Execution Mode

Prefer true parallel execution for independent proposal agents.

If true parallel execution is not supported by the current Codex client, run proposal agents sequentially while preserving independence.

Independence rule:

* During Phase 1A, module proposal agents must read the authoritative input documents independently.
* During Phase 1A, proposal agents must not read or depend on other proposal files.
* If running sequentially, do not let later Phase 1A proposal agents inspect earlier Phase 1A proposal files.
* Each proposal agent writes only its own proposal file.
* Proposal agents must not edit final design files.
* Proposal agents must not edit review files.
* Proposal agents must not overwrite another proposal.

After Phase 1A proposals exist, module debate reviewers may read all proposals within their own module. Cross-module reviewers may then read all proposals and module debate reviews.

## Commit Rule

Commits are explicitly allowed for this documentation design loop.

Before each commit:

1. Inspect `git status --short`.
2. Inspect `git diff -- <target-file-or-directory>`.
3. Stage only the intended file or files.
4. Commit only after the relevant file group or phase is complete.
5. Do not commit unrelated files.

Do not push.
Do not pull.
Do not rebase.
Do not create remote branches.
Do not upgrade dependencies.
Do not commit `.codex/`, `.claude/`, `.idea/`, logs, caches, build outputs, local config, secrets, or temporary files.

If the working tree already contains unrelated user changes before starting, stop and report them instead of overwriting or mixing with them.

## Required Directory Structure

Ensure these directories exist:

* `docs/design/execution-contract/proposals/`
* `docs/design/execution-contract/reviews/`
* `docs/design/execution-contract/final/`
* `docs/design/execution-contract/adr/`

Create only these required directories if missing.

Do not create unrelated files.

---

# Phase 0: Preflight Validation

Create:

* `docs/design/execution-contract/reviews/00-preflight.md`

The preflight report must include:

1. Current branch.
2. Initial `git status --short`.
3. Required file presence check.
4. Whether `GOAL.md`, `HARNESS.md`, and `PLAN.md` are non-empty.
5. Whether authoritative inputs are readable.
6. Conflicts found between SRS, HLD, data-model final documents, workflow-state final documents, GOAL, HARNESS, and PLAN.
7. Execution-contract design risks before proposal generation.
8. Questions that must be answered before proposal agents start.
9. Whether Phase 1A may proceed.

Required source documents:

* `AGENTS.md`
* `docs/SRS-v1.0.md`
* `docs/HLD.md`
* `docs/PROJECT-PLAN.md`
* `docs/design/execution-contract/GOAL.md`
* `docs/design/execution-contract/HARNESS.md`
* `docs/design/execution-contract/PLAN.md`
* `docs/design/data-model/final/data-model-dd-v0.1.md`
* `docs/design/data-model/final/schema-outline.md`
* `docs/design/data-model/final/state-data-impact.md`
* `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
* `docs/design/workflow-state/final/state-vocabulary.md`
* `docs/design/workflow-state/final/stage-transition-table.md`
* `docs/design/workflow-state/final/decision-matrix.md`
* `docs/design/workflow-state/final/recovery-rules.md`
* `docs/design/workflow-state/final/stale-propagation-rules.md`

If blocking issues exist, stop after writing the preflight report and report the blockers.

Commit message:

```text
docs: add execution contract preflight report
```

---

# Phase 1A: Module Proposal Debates

Phase 1A uses nine independent proposal agents.

Each of the three core modules must have exactly three proposal agents from different perspectives:

* Provider Adapter: 3 agents
* ArtifactService: 3 agents
* QualityCheckService / IssueType: 3 agents

Each proposal should be concise and decision-focused. Do not restate the full SRS/HLD. Do not write essays. Prefer tables, contract bullets, and concrete edge cases.

## Provider Adapter Module Agents

### 1. Provider Boundary and DTO Contract Agent

Output:

* `docs/design/execution-contract/proposals/01-provider-boundary-dto-agent.md`

Focus:

* Common Provider Adapter result envelope.
* Minimal input/output shape.
* Stage-specific contracts for Detector, OCR, Translation, Cleaner, and Typesetter.
* What belongs inside provider output versus StageExecutor versus ArtifactService.
* Temporary file boundary.
* Strict forbidden responsibilities.

Role bias:

* Maximize separation of concerns.
* Prevent Provider Adapter from becoming workflow-aware.

Must answer:

* What is the common provider result envelope?
* How are success and failure represented?
* What common metadata is required?
* What temporary file references may provider return?
* What must never be included in provider contract?
* What stage-specific payloads are minimally required for FakeProvider?

### 2. Provider Error, Refusal, and Metadata Agent

Output:

* `docs/design/execution-contract/proposals/02-provider-error-refusal-agent.md`

Focus:

* Standardized provider errors.
* Timeout, unavailable, invalid input, invalid output, provider refusal.
* Sanitized provider metadata.
* Refusal as first-class workflow evidence.
* Security and secret redaction.

Role bias:

* Maximize auditable failure behavior.
* Prevent provider refusal from being collapsed into generic failure.
* Prevent policy evasion logic.

Must answer:

* What error codes/classes are required for MVP?
* How is provider refusal represented?
* What sanitized metadata is retained?
* What raw payloads may be retained as artifacts?
* How are secrets prevented from entering logs/artifacts?
* How does this support WorkflowAttempt, ToolRunLog, QualityIssue, and WorkflowDecision?

### 3. Provider Capability and FakeProvider Agent

Output:

* `docs/design/execution-contract/proposals/03-provider-capability-fakeprovider-agent.md`

Focus:

* Minimal provider capability metadata.
* Local/cloud distinction.
* GPU requirement metadata.
* License note metadata.
* FakeProvider modes.
* FakeProvider deterministic outputs.

Role bias:

* Maximize implementation readiness for FakeProvider.
* Avoid designing a generic plugin framework.

Must answer:

* What capability metadata is required now?
* What capability metadata is deferred?
* How should FakeProvider simulate each provider type?
* Which deterministic fake modes are required?
* How does FakeProvider generate evidence for retry, refusal, invalid output, skip, overflow, and missing artifact tests?

## ArtifactService Module Agents

### 4. Artifact Lifecycle and Atomicity Agent

Output:

* `docs/design/execution-contract/proposals/04-artifact-lifecycle-atomicity-agent.md`

Focus:

* Official artifact lifecycle.
* Temp file to official artifact promotion.
* Atomic write/copy/promotion concept.
* Hash calculation.
* Transaction coordination with Repository / DAO.
* Relationship with active pointer update.

Role bias:

* Maximize file safety and crash safety.
* Prevent official artifacts from being created outside ArtifactService.

Must answer:

* What is an official artifact?
* How does temp output become official?
* When are path/hash/media/size recorded?
* What is atomic from ArtifactService perspective?
* What is atomic only when coordinated by WorkflowLoopEngine/Repository?
* What happens if file write succeeds but DB registration fails?
* What happens if DB registration succeeds but active pointer update does not happen?

### 5. Artifact Taxonomy, Retention, and Safety Agent

Output:

* `docs/design/execution-contract/proposals/05-artifact-taxonomy-retention-safety-agent.md`

Focus:

* Minimal artifact types.
* Storage states.
* Retention classes.
* Safety flags.
* Original image immutability.
* Debug/failed payload boundaries.

Role bias:

* Maximize privacy and data safety.
* Prevent image BLOBs or sensitive payloads from entering SQLite.
* Prevent cleanup from breaking recovery.

Must answer:

* What artifact types are required for MVP-0?
* Which artifacts must be retained?
* Which artifacts are rebuildable?
* What safety flags are required?
* What storage states are required?
* What must never be cleaned automatically?
* How should failed provider payloads and debug artifacts be classified?

### 6. Artifact Recovery and Integrity Agent

Output:

* `docs/design/execution-contract/proposals/06-artifact-recovery-integrity-agent.md`

Focus:

* Missing artifact detection.
* Hash mismatch.
* Orphan temp files.
* Recovery evidence.
* Rebuildability classification.
* ArtifactService boundary during recovery.

Role bias:

* Maximize recovery correctness.
* Prevent ArtifactService from making workflow decisions.

Must answer:

* How is missing/hash-invalid artifact detected?
* How is `storage_state = missing` or equivalent represented?
* How are orphan files treated?
* What does ArtifactService report to WorkflowLoopEngine?
* What does ArtifactService not decide?
* How does this support recovery-rules.md?

## QualityCheckService / IssueType Module Agents

### 7. Issue Taxonomy and Severity Agent

Output:

* `docs/design/execution-contract/proposals/07-quality-issue-taxonomy-severity-agent.md`

Focus:

* Minimal P0 IssueType set.
* Severity vocabulary.
* `is_blocking`.
* Error code versus issue type.
* Stage-specific issue groups.

Role bias:

* Maximize minimal but sufficient issue coverage.
* Avoid creating a full enterprise issue catalog.

Must answer:

* What minimal issue types are required for FakeProvider MVP-0?
* What severities are required?
* How is `is_blocking` different from severity?
* Which issues map to OCR, translation, cleaning, typesetting, artifact, export_check, and provider?
* Which issue types are deferred?

### 8. Quality Gate and Root Cause Agent

Output:

* `docs/design/execution-contract/proposals/08-quality-gate-root-cause-agent.md`

Focus:

* `discovered_stage`.
* `root_stage`.
* Suggested action.
* Boundary between quality classification and workflow decision.
* How issues feed WorkflowLoopEngine.

Role bias:

* Maximize decision traceability.
* Prevent QualityCheckService from becoming WorkflowLoopEngine.

Must answer:

* How does QualityCheckService assign discovered/root stage?
* What does suggested_action mean?
* What does QualityCheckService return to WorkflowLoopEngine?
* What must QualityCheckService never decide?
* How are invalid JSON, partial translation, provider refusal, cleaning skip, and typesetting overflow classified?

### 9. User-Facing Message and Fake Quality Agent

Output:

* `docs/design/execution-contract/proposals/09-quality-user-facing-fake-agent.md`

Focus:

* Minimal user-facing message keys.
* Safe messages for provider refusal.
* FakeQualityCheck behavior.
* Review/debug usefulness.
* Avoiding policy bypass suggestions.

Role bias:

* Maximize user comprehensibility and safe remediation.
* Keep implementation small.

Must answer:

* What minimal message keys are needed?
* How should provider refusal be shown safely?
* How should cleaning skip and typesetting overflow be explained?
* How can FakeQualityCheck produce predictable issues?
* Which messages are deferred to later UI/API design?

## Proposal Structure

Each Phase 1A proposal must use this structure:

1. Scope
2. Role Bias
3. Assumptions
4. Proposed Contract
5. Minimal Vocabulary / Fields
6. Normal Path
7. Failure / Edge Path
8. Boundary Rules
9. FakeProvider or FakeQuality Implications
10. Recovery / Audit Impact
11. HARNESS Scenario Coverage
12. Rejected Alternatives
13. Risks
14. Open Questions

## Phase 1A Hard Rules

* Do not implement code.
* Do not create migrations.
* Do not write SQL DDL.
* Do not design full ORM.
* Do not design full FastAPI routes.
* Do not write real provider prompt templates.
* Do not edit final design files.
* Do not edit ADR files in this phase.
* Do not modify proposal files owned by other agents.
* Do not invent features outside SRS/HLD/GOAL/HARNESS.
* If unclear, list as open question.
* If source documents conflict, report the conflict instead of silently choosing.
* Provider Adapter must not access SQLite.
* Provider Adapter must not register official artifacts.
* Provider Adapter must not create QualityIssue.
* Provider Adapter must not decide retry/fallback/skip/warning/block.
* ArtifactService must not decide workflow retry/fallback/warning/block.
* QualityCheckService must not advance workflow state.
* QualityCheckService must not update active pointers.
* StageExecutor must not replace WorkflowLoopEngine decision logic.
* Original images must never be overwritten.
* Images and large payloads must not be stored in SQLite.
* Logs and examples must not contain secrets.

## Phase 1A Commit Discipline

After all three Provider Adapter proposals are completed, commit them together.

Commit message:

```text
docs: add provider adapter contract proposals
```

After all three ArtifactService proposals are completed, commit them together.

Commit message:

```text
docs: add artifact service contract proposals
```

After all three QualityCheckService proposals are completed, commit them together.

Commit message:

```text
docs: add quality check contract proposals
```

---

# Phase 1B: Module Debate Reviews

Phase 1B creates one debate review per module.

Each module debate reviewer may read the three proposal files for that module only, plus authoritative inputs.

Create:

* `docs/design/execution-contract/reviews/01-provider-module-debate.md`
* `docs/design/execution-contract/reviews/02-artifact-module-debate.md`
* `docs/design/execution-contract/reviews/03-quality-module-debate.md`

Each module debate review must include:

1. Summary of each proposal.
2. Agreements.
3. Conflicts.
4. Missing contract details.
5. Boundary violations.
6. Over-designed parts.
7. Under-designed parts.
8. Recommended module-level decisions.
9. Blocking issues.
10. Non-blocking issues.
11. Open questions.
12. What the cross-module reviewer must inspect.

Commit all three module debate reviews together.

Commit message:

```text
docs: add execution contract module debates
```

---

# Phase 1C: Cross-Cutting Integration Proposals

After module debate reviews exist, create two cross-cutting integration proposals.

These agents may read all Phase 1A proposals and all Phase 1B module debate reviews.

## 10. StageExecutor Integration Agent

Output:

* `docs/design/execution-contract/proposals/10-stageexecutor-integration-agent.md`

Focus:

* StageExecutor input contract.
* StageExecutor output contract.
* Execution sequence.
* Provider call boundary.
* ArtifactService registration boundary.
* QualityCheckService invocation boundary.
* What is returned to WorkflowLoopEngine.
* Transaction boundary before and after provider calls.

Role bias:

* Maximize implementability of the single-Page backend vertical slice.
* Prevent StageExecutor from becoming a hidden WorkflowLoopEngine.

Must answer:

* What durable context does StageExecutor receive?
* When is attempt start persisted?
* What happens before provider call?
* What happens after provider call?
* When is ArtifactService called?
* When is QualityCheckService called?
* What normalized stage result goes back to WorkflowLoopEngine?
* What must StageExecutor never decide?

## 11. FakeProvider Vertical Slice Readiness Agent

Output:

* `docs/design/execution-contract/proposals/11-fakeprovider-vertical-slice-agent.md`

Focus:

* End-to-end FakeProvider testability.
* Required fake modes.
* Required fake artifacts.
* Required fake issues.
* Deterministic scenario control.
* Minimal backend vertical slice readiness.

Role bias:

* Maximize near-term implementation readiness.
* Reject contracts that cannot be tested with FakeProvider.

Must answer:

* Can the proposed contracts run the single-Page happy path?
* Can they simulate OCR failure then retry?
* Can they simulate invalid translation JSON?
* Can they simulate provider refusal?
* Can they simulate partial translation?
* Can they simulate cleaning skip?
* Can they simulate typesetting overflow?
* Can they simulate missing artifact?
* What minimal fixtures are needed?

Commit both cross-cutting integration proposals together.

Commit message:

```text
docs: add execution contract integration proposals
```

---

# Phase 2: Cross-Module Review

Create:

* `docs/design/execution-contract/reviews/04-cross-module-contract-review.md`

The cross-module reviewer must read:

* authoritative inputs;
* all Phase 1A proposals;
* all Phase 1B module debate reviews;
* all Phase 1C integration proposals.

The review must include:

1. Provider ↔ ArtifactService contract conflicts.
2. Provider ↔ QualityCheckService contract conflicts.
3. ArtifactService ↔ QualityCheckService contract conflicts.
4. StageExecutor boundary risks.
5. WorkflowLoopEngine ownership risks.
6. Repository / DAO boundary risks.
7. Recovery evidence gaps.
8. FakeProvider readiness gaps.
9. Issue taxonomy gaps.
10. Artifact taxonomy gaps.
11. Error envelope gaps.
12. Transaction boundary ambiguities.
13. Security and secret leakage risks.
14. P1/P2 scope creep.
15. Recommended final decisions.
16. ADR candidates.
17. Blocking issues.
18. Non-blocking issues.
19. Open questions that block synthesis.
20. Open questions that do not block synthesis.

Commit message:

```text
docs: add execution contract cross review
```

---

# Phase 3: Limited Revision Loop

If the cross-module review identifies blocking issues, run at most two revision rounds.

Rules:

* Revise only the affected proposal files.
* Do not edit final files.
* Do not edit ADR files.
* Do not edit unrelated files.
* Each revised proposal must add a `Revision Notes` section at the top.
* The revised proposal must explain what changed and which review issue it addresses.
* Do not silently remove open questions.

After revised proposals:

1. Inspect `git status --short`.
2. Inspect `git diff -- <revised proposal file>`.
3. Stage only the revised files.
4. Commit them.

Commit message:

```text
docs: revise execution contract proposals
```

After revisions, update the cross-review or create:

* `docs/design/execution-contract/reviews/05-cross-review-revision-notes.md`

Commit message:

```text
docs: add execution contract revision review
```

If blocking issues remain after two revision rounds, stop and report them.

If no blocking issues are found, create:

* `docs/design/execution-contract/reviews/05-no-blocking-revision-needed.md`

Commit message:

```text
docs: note no execution contract revision needed
```

---

# Phase 4: Final Synthesis

If synthesis may proceed, run the synthesizer agent.

The synthesizer must read:

* authoritative inputs;
* all proposal files;
* all module debate reviews;
* cross-module review files;
* revision notes if any.

The synthesizer may edit only:

* `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`
* `docs/design/execution-contract/final/provider-adapter-contract.md`
* `docs/design/execution-contract/final/artifact-service-contract.md`
* `docs/design/execution-contract/final/quality-check-contract.md`
* `docs/design/execution-contract/final/stage-executor-contract.md`
* `docs/design/execution-contract/final/error-and-issue-taxonomy-minimal.md`
* `docs/design/execution-contract/final/fakeprovider-readiness.md`
* `docs/design/execution-contract/final/open-questions.md`
* `docs/design/execution-contract/adr/*.md`

Do not implement code.

The final design must include:

1. Design goals.
2. Source documents.
3. Provider Adapter common result envelope.
4. Provider Adapter standard error envelope.
5. Provider metadata and capability metadata.
6. Detector minimal contract.
7. OCR minimal contract.
8. Translation minimal contract.
9. Cleaner minimal contract.
10. Typesetter minimal contract.
11. ArtifactService official artifact lifecycle.
12. Artifact type vocabulary.
13. Artifact storage state vocabulary.
14. Artifact retention/safety vocabulary.
15. Temp-to-official artifact promotion rule.
16. Missing artifact detection rule.
17. QualityCheckService input/output contract.
18. Minimal IssueType catalog.
19. Severity and `is_blocking` rules.
20. `discovered_stage` and `root_stage` rules.
21. Suggested action and message key rules.
22. StageExecutor input/output contract.
23. StageExecutor execution sequence.
24. Transaction boundary guidance.
25. WorkflowLoopEngine decision input.
26. FakeProvider required modes.
27. FakeQualityCheck required modes.
28. Scenario replay against HARNESS.
29. Rejected alternatives.
30. Risks and mitigations.
31. ADR list.
32. Open questions.
33. Decisions deferred to later design stages.

The final design must preserve these hard invariants:

* Provider Adapter only calls tools and returns structured outputs/errors/provider metadata.
* Provider Adapter must not access SQLite.
* Provider Adapter must not register official artifacts.
* Provider Adapter must not create QualityIssue.
* Provider Adapter must not decide retry, fallback, skip, warning, pause, cancel, or block.
* ArtifactService is the only official artifact lifecycle entry.
* ArtifactService must not decide workflow retry/fallback/warning/block.
* Repository / DAO is the only SQLite access entry.
* WorkflowLoopEngine owns workflow decisions.
* QualityCheckService checks outputs and classifies issues, but does not advance workflow state.
* QualityCheckService must not update active pointers.
* StageExecutor executes one stage but does not make final workflow decisions.
* Original images are never overwritten.
* Image files and large payloads are not stored in SQLite.
* Active pointers remain the source of truth for current OCR, translation, cleaned image, and typeset image.
* Provider refusal is a first-class workflow path, not a crash.
* No provider policy bypass or evasion logic is allowed.
* FakeProvider must not require real OCR, LLM, cleaning, or typesetting tools.

Commit all final files and ADRs together.

Commit message:

```text
docs: add execution contract detailed design
```

---

# Phase 5: HARNESS Validation

After synthesis, run the HARNESS validation agent.

Create:

* `docs/design/execution-contract/reviews/06-harness-validation.md`

The HARNESS validation agent must read:

* `docs/design/execution-contract/HARNESS.md`
* all final design files
* all ADR files if present

The validation report must include:

1. Invariant checklist with PASS / FAIL / UNCLEAR.
2. Scenario replay results with PASS / FAIL / UNCLEAR.
3. Missing provider contract details.
4. Missing artifact contract details.
5. Missing quality issue contract details.
6. Missing StageExecutor boundary details.
7. Recovery evidence gaps.
8. FakeProvider readiness gaps.
9. Boundary violations.
10. Whether final design is acceptable for FakeProvider single-Page backend vertical slice.

For each HARNESS scenario, include:

1. Stage involved.
2. Provider output or error.
3. ArtifactService behavior.
4. QualityCheckService behavior.
5. StageExecutor behavior.
6. WorkflowLoopEngine decision input.
7. Persistence or recovery evidence.
8. Boundary check.
9. PASS / FAIL / UNCLEAR.

If any hard invariant fails, do not modify final files automatically. Report the failure.

Commit message:

```text
docs: add execution contract harness validation
```

---

# Final Report

At the end, report:

1. Current branch.
2. Final `git status --short`.
3. Commits created.
4. Files changed.
5. Proposal files created.
6. Module debate review files created.
7. Cross-module review files created.
8. Final design files created.
9. ADR files created.
10. Key decisions.
11. Rejected alternatives.
12. Blocking issues, if any.
13. Non-blocking open questions.
14. HARNESS validation summary.
15. Whether the Execution Contract Design loop is complete.
16. Whether the design is ready for the next Goal: FakeProvider single-Page backend vertical slice planning or Repository / Persistence minimal implementation design.

Do not push.

Do not claim the design is ready if HARNESS validation was not performed.
Do not fabricate validation results.