# Data Model Detailed Design Case Study

This file preserves the Data Model prompt-pattern as a case study of a successful detailed-design collaboration.

It is not the default template for every future design task. Use it to understand what worked in the Data Model round, then scale the reusable pattern down for smaller design areas.

Source case study:

- `docs/prompt-patterns/data-model-detailed-design-template.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/data-model/final/schema-outline.md`
- `docs/design/data-model/final/state-data-impact.md`
- `docs/design/data-model/final/open-questions.md`

## Case Flow

The Data Model round used this collaboration flow:

```text
GOAL
-> HARNESS
-> proposal agents
-> cross-review
-> limited revision loop
-> synthesizer
-> harness validation
-> ADR / open questions
```

The point was not to let one agent write a final answer immediately. The point was to expose design differences, review them against architecture invariants and scenarios, then synthesize one coherent baseline.

## Useful Ideas Preserved

### Role-Biased Proposal Agents

The Data Model task used proposal agents with different biases:

- Domain model
- Persistence
- Workflow state
- Artifact and quality
- API / ORM readiness

Each proposal had to read the same authoritative inputs but approach the problem from a different risk surface. This reduced the chance that a single framing would hide important conflicts.

### P0 / P1 / P2 Classification

Every proposal had to classify entities and behavior into MVP-critical, near-term, and deferred scope.

This helped prevent the data model from becoming either too thin for MVP-0 recovery or too broad for future P1/P2 features.

### Hard Invariants

The prompts repeated architecture rules that could not be violated:

- No image BLOBs in SQLite.
- Original images are never overwritten.
- Provider adapters do not access the database.
- Provider adapters do not own artifact lifecycle.
- Provider adapters do not decide retry, fallback, skip, warning, or block.
- ArtifactService owns official artifact lifecycle.
- Repository / DAO is the SQLite boundary.
- API keys and secrets are not stored in project databases or logs.

These were not optional preferences; they were design guards inherited from SRS and HLD.

### Validation Against HARNESS Scenarios

The HARNESS forced proposals and final synthesis to explain scenarios such as:

- OCR edit
- Translation edit
- Provider refusal
- Cleaning skip
- Typesetting overflow
- Crash recovery
- Export blocking
- Idempotent rerun

The final Data Model design had to prove that the data layer could explain those scenarios through entities, active pointers, attempts, decisions, issues, artifacts, and dependency hashes.

### Cross-Review Focus

Cross-review was not a prose-polishing step. It looked for:

- conflicts between proposals;
- missing entities;
- missing relationships;
- over-design;
- under-design;
- violated invariants;
- unsupported HARNESS scenarios;
- duplicated source-of-truth risks;
- recovery and export gate gaps;
- blocking issues and non-blocking issues.

This made review useful as an engineering filter, not just a second opinion.

### Limited Revision Loop

The process allowed a limited revision loop instead of endless debate.

Revision was only for blocking issues, had to preserve open questions, and did not allow proposal agents to edit final design files directly. If blockers remained after the limit, the process was supposed to stop and report the unresolved decision.

### Synthesizer As Decision-Maker

The synthesizer did not merge proposal text mechanically.

It had to choose one coherent design, reject alternatives, resolve conflicts, produce final documents, and create ADRs for important decisions. This is why the final Data Model result became a baseline instead of a stitched-together proposal bundle.

### Validation Agent Separate From Synthesizer

The final validation step was separate from synthesis.

That kept the synthesizer from self-certifying its own design. Validation checked whether the final design satisfied invariants, replayed HARNESS scenarios, and identified remaining gaps as open questions or implementation validation needs.

## Data-Model-Specific Parts

Do not blindly copy these into every design task:

- The exact five proposal roles were Data-Model-specific.
- The required entity list was Data-Model-specific.
- Schema outline, ERD, active pointer rules, migration concerns, and data placement are not needed in every design area.
- The heavy proposal/review/synthesis process is justified for foundational architecture, but too much for a narrow implementation decision.
- Data Model needed deep persistence and recovery analysis; a UI flow, API endpoint, export manifest, or testing strategy may need different roles and different harness scenarios.

## Lessons Reusable Elsewhere

- Start with a clear GOAL and a HARNESS before asking for proposals.
- Use role-biased agents only when multiple real risk surfaces exist.
- Make P0/P1/P2 scope explicit early.
- Repeat hard invariants inside task prompts when violation would corrupt the design.
- Make every proposal validate against the HARNESS, not only describe a preferred design.
- Review for conflicts, missing concepts, and unsupported scenarios.
- Limit revision loops so design does not become an endless debate.
- Let synthesis make decisions, not concatenate documents.
- Run validation separately from synthesis.
- Convert major trade-offs into ADRs and unresolved non-blockers into open questions.

## What This Case Study Should Not Become

This case study should not become a new heavyweight framework, custom agent runtime, or mandatory process for every task.

Future prompt-patterns should stay lightweight and be filled in only when a real task needs them.
