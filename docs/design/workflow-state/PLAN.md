# Workflow-State Core Design PLAN

You are the orchestrator for the Workflow-State Core Design loop.

This plan defines the detailed execution steps for Goal 1: Workflow State / Workflow Loop detailed design.

This is a design-documentation task only.

Do not implement code.
Do not create migrations.
Do not write SQL DDL.
Do not write ORM models.
Do not write API handlers.
Do not write frontend code.
Do not write provider integrations.
Do not write real translation provider prompt templates.
Do not modify SRS, HLD, PROJECT-PLAN, or existing final data-model documents.
Do not introduce P1/P2 features as MVP prerequisites.

## Execution Mode

Prefer true parallel execution for proposal subagents.

If true parallel execution is not supported by the current Codex client, run the five proposal subagents sequentially while preserving independence.

Independence rule:

* During Phase 1, each proposal subagent must read the required input documents independently.
* During Phase 1, proposal subagents must not read or depend on other proposal files.
* If running sequentially, do not let later proposal subagents inspect earlier proposal files.
* Each proposal subagent writes only its own proposal file.
* Proposal subagents must not edit final design files.
* Proposal subagents must not edit review files.
* Proposal subagents must not overwrite another proposal.

## Commit Rule

Commits are explicitly allowed for this documentation design loop.

Before each commit:

1. Inspect `git status --short`.
2. Inspect `git diff -- <target-file>`.
3. Stage only the intended file or files.
4. Commit only after the relevant file or phase is complete.
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

* `docs/design/workflow-state/proposals/`
* `docs/design/workflow-state/reviews/`
* `docs/design/workflow-state/final/`
* `docs/design/workflow-state/adr/`

Create only these required directories if missing.

Do not create unrelated files.

---

# Phase 0: Preflight Validation

Create:

* `docs/design/workflow-state/reviews/00-preflight.md`

The preflight report must include:

1. Current branch.
2. Initial `git status --short`.
3. Required file presence check.
4. Whether `GOAL.md`, `HARNESS.md`, and `PLAN.md` are non-empty.
5. Whether authoritative inputs are readable.
6. Conflicts found between SRS, HLD, data-model final documents, GOAL, HARNESS, and PLAN.
7. Workflow-state design risks before proposal generation.
8. Questions that must be answered before proposal subagents start.
9. Whether Phase 1 may proceed.

Required checks:

* `docs/design/workflow-state/GOAL.md` exists and is non-empty.
* `docs/design/workflow-state/HARNESS.md` exists and is non-empty.
* `docs/design/workflow-state/PLAN.md` exists and is non-empty.
* `docs/SRS-v1.0.md` exists.
* `docs/HLD.md` or `docs/HLD-v0.2.md` exists.
* `docs/design/data-model/final/data-model-dd-v0.1.md` exists.
* `docs/design/data-model/final/state-data-impact.md` exists.

If blocking issues exist, stop after writing the preflight report and report the blockers.

Commit message:

```text
docs: add workflow state preflight report
```

---

# Phase 1: Five Independent Proposal Subagents

You must use exactly five independent proposal subagents.

Create these files:

1. `docs/design/workflow-state/proposals/01-state-vocabulary-and-transitions-agent.md`
2. `docs/design/workflow-state/proposals/02-decision-retry-and-profile-agent.md`
3. `docs/design/workflow-state/proposals/03-recovery-and-idempotency-agent.md`
4. `docs/design/workflow-state/proposals/04-stale-propagation-and-user-edits-agent.md`
5. `docs/design/workflow-state/proposals/05-implementation-readiness-and-scope-agent.md`

## 1. State Vocabulary and Transitions Agent

Focus:

* MVP workflow stages.
* `ProcessingTask` lifecycle.
* `WorkflowAttempt` lifecycle.
* Page-level workflow status.
* TextBlock stage statuses.
* Stage transition table.
* Safe stage boundaries.
* Legal and illegal transitions.
* Completion, warning, blocked, skipped, stale, paused, cancelled, interrupted, and recovering states.

Must answer:

* What statuses exist?
* Which entity owns which status?
* Which transitions are legal?
* Which transitions are illegal?
* Which statuses are persisted?
* Which statuses may be derived?
* How does the single-Page happy path advance?

## 2. Decision, Retry, and Profile Agent

Focus:

* `WorkflowDecision` types.
* Retry budget semantics.
* Fallback provider semantics.
* Warning versus blocking decisions.
* Skip target decisions.
* Pause-for-user decisions.
* Minimal `ProcessingProfileSnapshot` policy fields needed by `WorkflowLoopEngine`.

Must answer:

* Which decisions consume retry budget?
* When is retry allowed?
* When is fallback allowed?
* When is skip allowed?
* When does warning export become possible?
* When must the workflow block?
* How does `ProcessingProfileSnapshot` affect these choices?
* How are infinite loops prevented?

Keep ProcessingProfile minimal. Do not design full profile management.

## 3. Recovery and Idempotency Agent

Focus:

* Crash recovery.
* Restart reconciliation.
* Stale running `ProcessingTask`.
* Stale running `WorkflowAttempt`.
* Abandoned attempts.
* Reusing completed results.
* Input/config/context hashes.
* Missing artifacts.
* Safe resume behavior.

Must answer:

* What happens to running tasks after crash?
* What happens to running attempts after crash?
* How does recovery decide whether to reuse, retry, rebuild, warn, or block?
* How does recovery avoid relying only on `Page.status`?
* How does idempotent rerun avoid duplicate active results?
* How does artifact missing affect workflow state?

## 4. Stale Propagation and User Edits Agent

Focus:

* OCR edit.
* Translation edit.
* Manual review state.
* Downstream stale propagation.
* `QualityIssue` stale/superseded behavior.
* Active pointer changes.
* Rework after edit.

Must answer:

* What state changes after OCR edit?
* What state changes after translation edit?
* Which downstream stages become stale?
* Which active pointers change?
* Which prior issues become stale or superseded?
* How does workflow resume from stale state?
* What is MVP scope, and what is deferred to P1/P2?

## 5. Implementation Readiness and Scope Agent

Focus:

* Whether the design can support FakeProvider single-Page backend vertical slice.
* Repository transaction implications without designing ORM.
* StageExecutor boundary assumptions.
* ArtifactService boundary assumptions.
* QualityCheckService boundary assumptions.
* Provider Adapter boundary assumptions.
* Scope control and overdesign detection.

Must answer:

* Can this design support FakeProvider MVP-0?
* What repository methods will likely be needed conceptually?
* What must be atomic?
* What must not be decided by Provider Adapter?
* What must not be decided by QualityCheckService?
* What must go through ArtifactService?
* Which ideas must be rejected as P1/P2 or overengineering?

## Proposal Structure

Each proposal must follow this exact structure:

1. Scope
2. Role Bias
3. Assumptions
4. Proposed Model
5. State Vocabulary or Decision Vocabulary
6. Transition or Decision Rules
7. Recovery Impact
8. Stale Propagation Impact
9. ProcessingProfileSnapshot Impact
10. Artifact / QualityIssue / Active Pointer Impact
11. Repository and Transaction Implications
12. Invariants
13. Rejected Alternatives
14. Validation Against HARNESS Scenarios
15. Risks
16. Open Questions

## Proposal Hard Rules

* Do not implement code.
* Do not create migrations.
* Do not write SQL DDL.
* Do not edit final design files.
* Do not edit ADR files in this round.
* Do not modify proposal files owned by other agents.
* Do not invent features outside SRS/HLD/GOAL/HARNESS.
* If a decision is unclear, list it as an open question.
* If source documents conflict, report the conflict instead of silently choosing.
* Provider Adapter must not own persistence, artifact lifecycle, retry/fallback decisions, skip/warning/block decisions, or quality issue attribution.
* QualityCheckService must not advance workflow state.
* ArtifactService must own official artifact lifecycle.
* Repository / DAO must own SQLite access.
* No image BLOBs in SQLite.
* Original images must never be overwritten.
* Recovery must not rely only on `Page.status`.
* Normal export must block unresolved blocking `QualityIssue`.
* Warning export must follow `ProcessingProfileSnapshot`.
* API keys must not be stored in `project.db`.
* Logs and examples must not include secrets.

## Phase 1 Commit Discipline

After each proposal file is completed:

1. Inspect `git status --short`.
2. Inspect `git diff -- <that proposal file>`.
3. Stage only that proposal file.
4. Commit it.

Use these commit messages:

```text
docs: add workflow state vocabulary proposal
docs: add workflow decision retry proposal
docs: add workflow recovery idempotency proposal
docs: add workflow stale propagation proposal
docs: add workflow implementation readiness proposal
```

Do not stage or commit any other files.

---

# Phase 2: Cross-Review Agent

After all five proposal files exist and are committed, run the reviewer agent.

The reviewer must read:

* `AGENTS.md`
* `docs/SRS-v1.0.md`
* `docs/HLD.md` or `docs/HLD-v0.2.md`
* `docs/PROJECT-PLAN.md`
* `docs/design/workflow-state/GOAL.md`
* `docs/design/workflow-state/HARNESS.md`
* `docs/design/workflow-state/PLAN.md`
* all files under `docs/design/workflow-state/proposals/`
* relevant final data-model documents

Create:

* `docs/design/workflow-state/reviews/01-cross-review.md`

The review must include:

1. Summary of each proposal.
2. Agreements across proposals.
3. Conflicts between proposals.
4. Missing HARNESS coverage.
5. Ambiguous status vocabulary.
6. Unsafe transitions.
7. Infinite loop risk.
8. Recovery gaps.
9. Idempotency gaps.
10. Provider Adapter boundary violations.
11. QualityCheckService boundary violations.
12. ArtifactService boundary violations.
13. Repository / DAO boundary violations.
14. Export gate mistakes.
15. P1/P2 scope creep.
16. Recommended final decisions.
17. ADR candidates.
18. Blocking issues.
19. Non-blocking issues.
20. Open questions that block final synthesis.
21. Open questions that do not block final synthesis.

Commit message:

```text
docs: add workflow state cross review
```

---

# Phase 3: Limited Revision Loop

If the cross-review identifies blocking issues, run at most two revision rounds.

Rules:

* Revise only the affected proposal files.
* Do not edit final files.
* Do not edit ADR files.
* Do not edit unrelated files.
* Each revised proposal must add a `Revision Notes` section at the top.
* The revised proposal must explain what changed and which review issue it addresses.
* Do not silently remove open questions.

After each revised proposal:

1. Inspect `git status --short`.
2. Inspect `git diff -- <revised proposal file>`.
3. Stage only that proposal file.
4. Commit it.

Commit message:

```text
docs: revise <agent-name> workflow proposal
```

After revisions, update the cross-review or create:

* `docs/design/workflow-state/reviews/01-cross-review-revision-notes.md`

Commit message:

```text
docs: add workflow proposal revision review
```

If there are still blocking issues after two revision rounds, stop and report them.

If no blocking issues are found, create:

* `docs/design/workflow-state/reviews/02-no-blocking-revision-needed.md`

Commit message:

```text
docs: note no workflow proposal revision needed
```

---

# Phase 4: Synthesizer Agent

If synthesis may proceed, run the synthesizer agent.

The synthesizer must read:

* `AGENTS.md`
* `docs/SRS-v1.0.md`
* `docs/HLD.md` or `docs/HLD-v0.2.md`
* `docs/PROJECT-PLAN.md`
* `docs/design/workflow-state/GOAL.md`
* `docs/design/workflow-state/HARNESS.md`
* `docs/design/workflow-state/PLAN.md`
* all workflow-state proposal files
* all workflow-state review files
* relevant final data-model documents

The synthesizer may edit only:

* `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
* `docs/design/workflow-state/final/state-vocabulary.md`
* `docs/design/workflow-state/final/stage-transition-table.md`
* `docs/design/workflow-state/final/decision-matrix.md`
* `docs/design/workflow-state/final/recovery-rules.md`
* `docs/design/workflow-state/final/stale-propagation-rules.md`
* `docs/design/workflow-state/final/open-questions.md`
* `docs/design/workflow-state/adr/*.md`

Do not implement code.

The final design must include:

1. Design goals.
2. Source documents.
3. MVP workflow stages.
4. `ProcessingTask` status vocabulary.
5. `WorkflowAttempt` status vocabulary.
6. Page status vocabulary.
7. TextBlock stage status vocabulary.
8. Legal state transitions.
9. Illegal state transitions.
10. `WorkflowDecision` types.
11. Retry budget rules.
12. Fallback rules.
13. Skip rules.
14. Warning rules.
15. Blocking rules.
16. Pause rules.
17. Cancel rules.
18. Crash recovery rules.
19. Idempotent rerun rules.
20. OCR edit stale propagation.
21. Translation edit stale propagation.
22. Export readiness rules.
23. Minimal `ProcessingProfileSnapshot` policy fields.
24. Boundary with Provider Adapter.
25. Boundary with ArtifactService.
26. Boundary with QualityCheckService.
27. Boundary with Repository / DAO.
28. Boundary with StageExecutor.
29. Scenario replay.
30. ADR list.
31. Open questions.
32. Rejected alternatives.
33. Risks and mitigations.
34. Decisions deferred to later detailed design stages.

The final design must preserve these hard invariants:

* Provider Adapter only calls tools and returns structured results or standardized errors.
* Provider Adapter must not access SQLite.
* Provider Adapter must not register official artifacts.
* Provider Adapter must not create `QualityIssue`.
* Provider Adapter must not decide retry, fallback, skip, warning, pause, cancel, or block.
* ArtifactService is the only official artifact lifecycle entry.
* Repository / DAO is the only SQLite access entry.
* WorkflowLoopEngine owns workflow decisions.
* QualityCheckService checks outputs and classifies issues, but does not advance workflow state.
* Original images are never overwritten.
* Image files and large payloads are not stored in SQLite.
* Active pointers are the source of truth for current OCR, translation, cleaned image, and typeset image.
* Recovery must not rely only on `Page.status`.
* Normal export blocks unresolved blocking `QualityIssue`.
* Warning export follows `ProcessingProfileSnapshot`.
* No manga search, scraping, download, distribution, or publishing functionality.
* No provider policy bypass or evasion logic.

Commit all Phase 4 final and ADR files together.

Commit message:

```text
docs: add workflow state detailed design
```

---

# Phase 5: HARNESS Validation Agent

After synthesis, run the HARNESS validation agent.

The HARNESS validation agent must read:

* `docs/design/workflow-state/HARNESS.md`
* `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
* `docs/design/workflow-state/final/state-vocabulary.md`
* `docs/design/workflow-state/final/stage-transition-table.md`
* `docs/design/workflow-state/final/decision-matrix.md`
* `docs/design/workflow-state/final/recovery-rules.md`
* `docs/design/workflow-state/final/stale-propagation-rules.md`
* `docs/design/workflow-state/final/open-questions.md`
* `docs/design/workflow-state/adr/*.md`

Create:

* `docs/design/workflow-state/reviews/03-harness-validation.md`

The validation report must include:

1. Invariant checklist with PASS / FAIL / UNCLEAR.
2. Scenario replay results with PASS / FAIL / UNCLEAR.
3. Missing state vocabulary.
4. Ambiguous transitions.
5. Duplicated source-of-truth risks.
6. Recovery gaps.
7. Idempotency gaps.
8. Stale propagation gaps.
9. Artifact lifecycle gaps.
10. Export blocking gaps.
11. Provider boundary gaps.
12. Whether final design is acceptable for FakeProvider single-Page backend vertical slice.

For each HARNESS scenario, include:

1. Initial state.
2. Trigger.
3. Expected state changes.
4. Expected `WorkflowAttempt` behavior.
5. Expected `WorkflowDecision` behavior.
6. Expected `QualityIssue` behavior.
7. Expected artifact or active pointer behavior.
8. Export impact.
9. PASS / FAIL / UNCLEAR.

If any hard invariant fails, do not modify final files automatically. Report the failure.

Commit message:

```text
docs: add workflow state harness validation
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
9. Key decisions.
10. Rejected alternatives.
11. Blocking issues, if any.
12. Non-blocking open questions.
13. HARNESS validation summary.
14. Whether the Workflow-State Core Design loop is complete.
15. Whether the design is ready for the next Goal: Execution Contract Design.

Do not push.

Do not claim the design is ready if HARNESS validation was not performed.
Do not fabricate validation results.
