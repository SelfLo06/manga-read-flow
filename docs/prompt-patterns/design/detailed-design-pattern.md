# Detailed Design Prompt Pattern

Detailed-design prompt-patterns are templates for writing real prompts. They are not real prompts themselves.

Use this pattern to prepare future design tasks without copying the full Data Model process every time.

## Use For

- API design
- UI flow design
- Export design
- Real tool integration design
- Testing strategy design
- Other architecture-adjacent decisions that need trade-off analysis before code

## Do Not Use For

- Small implementation fixes
- Mechanical documentation cleanup
- Direct code generation
- Dependency upgrades
- Product code tasks that already have a slice document and validation command
- Any task where one focused design note is enough

## Required Inputs

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/PROJECT-PLAN.md`
- Relevant prior detailed designs
- Existing ADRs relevant to the design area
- A task-specific `GOAL.md`
- A task-specific `HARNESS.md`

If SRS, HLD, final detailed designs, and task files conflict, the prompt should require the agent to report the conflict before editing final documents.

## Recommended Outputs

Adjust the file names for the design area, but keep the output set small:

- `final/<design-area>-dd-v0.1.md`
- Optional focused supporting notes only when they clarify contracts or validation
- `final/open-questions.md`
- ADRs for important accepted trade-offs
- A validation report or validation section

Do not generate proposal, review, or ADR files unless the task explicitly calls for a multi-agent design round.

## GOAL Structure

A good GOAL should state:

- design area and purpose;
- product stage it supports;
- in-scope decisions;
- out-of-scope decisions;
- authoritative source documents;
- files allowed to change;
- files forbidden to change;
- required final outputs;
- hard invariants;
- expected final report;
- commit rule.

The GOAL should be narrow enough that the design can finish without re-planning the whole product.

## HARNESS Structure

A design HARNESS should define what the design must prove or explain:

- required scenarios;
- architecture invariants;
- ownership boundaries;
- failure and recovery behavior;
- readiness or export behavior when relevant;
- scope-control checks;
- acceptance criteria for final design;
- conditions that must become open questions.

## Harness Principles For Design Tasks

- HARNESS is not a longer prompt.
- HARNESS defines what must be proven or explained.
- For design tasks, HARNESS should map scenarios to invariants, ownership boundaries, recovery behavior, export/readiness behavior, and scope-control checks.
- If a scenario cannot be proven by design evidence, record it as an open question or implementation validation need.

## Proposal Agent Structure

Use proposal agents only when the design has multiple credible approaches or multiple risk surfaces.

Each proposal should include:

- scope;
- role bias;
- assumptions;
- proposed model, contract, flow, or policy;
- P0 / P1 / P2 classification when scope risk exists;
- ownership and boundaries;
- interaction with existing architecture;
- failure modes;
- recovery and idempotency impact when relevant;
- rejected alternatives;
- validation against HARNESS scenarios;
- risks;
- open questions.

Proposal agents should not edit final design files directly.

## Cross-Review Structure

Cross-review should look for:

- conflicts between proposals;
- missing concepts;
- unsupported HARNESS scenarios;
- violated architecture invariants;
- ownership ambiguity;
- duplicated source-of-truth risks;
- over-design;
- under-design;
- migration, recovery, readiness, or export gaps when relevant;
- blocking issues;
- non-blocking issues;
- ADR candidates;
- open questions that block synthesis;
- open questions that can be deferred.

Cross-review should not merely summarize or polish.

## Limited Revision Loop

Use a limited revision loop only for blocking issues.

Rules:

- set a maximum number of revision rounds;
- change only proposal files affected by blocking review findings;
- add revision notes;
- do not edit final design or ADRs during proposal revision;
- do not silently delete open questions;
- stop and report if blockers remain after the limit.

For small design tasks, skip this loop and let the final author record the trade-off directly.

## Synthesis Structure

Synthesis should produce one coherent design, not a document merge.

It should include:

- selected design;
- rationale;
- rejected alternatives;
- scope boundaries;
- ownership boundaries;
- state, artifact, persistence, API, UI, or provider impacts as relevant;
- failure behavior;
- recovery/idempotency behavior when relevant;
- scenario replay against HARNESS;
- risks and mitigations;
- ADR list;
- open questions.

## Harness Validation Structure

Validation should check the final design against the HARNESS:

- invariants: pass / fail / unclear;
- scenarios: pass / fail / unclear;
- ownership boundaries;
- recovery behavior;
- readiness/export behavior when relevant;
- missing decisions;
- over-scoped decisions;
- implementation validation needs.

Validation should be separate from synthesis when the design is foundational or high risk.

## ADR / Open Questions Rules

- Create ADRs only for durable architectural decisions with real alternatives.
- Do not create ADRs for simple task mechanics or wording preferences.
- Blocking questions must be resolved before final baseline.
- Non-blocking questions may remain in `open-questions.md` with an owner or future phase.
- If an unresolved question affects MVP-0 implementation, say so explicitly.

## Stop Conditions

Stop and report instead of forcing a design when:

- authoritative documents conflict;
- required source documents are missing;
- no design can satisfy a hard invariant;
- the task requires implementation code to prove the design;
- the design would broaden the current product phase;
- a blocking open question remains after the allowed revision loop;
- the requested file edits fall outside allowed paths.
