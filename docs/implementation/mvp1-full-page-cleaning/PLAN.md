# MVP-1 Full-page Cleaning — Implementation Plan

## Scope and status

The former Full-page Cleaning Closure Goal is superseded by the Full-page
Cleaning Ledger design. Its frozen evidence remains historical input only;
this implementation does not reuse its temporary state or caller booleans.

The implementation is deliberately divided into exactly three external
slices:

1. **Slice 1 — Ledger Foundation (current):** v3 migration, run, immutable
   inventory, disposition ledger, per-instance result attribution, durable
   correction reservation, recovery reads, and focused tests.
2. **Slice 2 — Composition, Validation and Atomic Acceptance:** combined
   members, deterministic composition, page validation, issue lifecycle,
   stale propagation, and the only active-cleaned-pointer acceptance path.
3. **Slice 3 — case-71 Closure and case-72 Generalization:** real-page
   execution and separate human gates using the Slice 1/2 contract.

This plan authorizes only Slice 1. It does not implement image composition,
page validation, active pointer selection, case-71/72 execution, UI/API,
typesetting, export, batch, or provider behavior.

## Slice 1 decisions

- Add `project_full_page_cleaning_ledger_v3` as an additive, per-project
  migration. It does not semantically backfill Slice E/F records.
- Keep ledger facts in normalized project.db tables; image, mask, and
  validator payloads remain ProcessingArtifact references.
- Expose named, use-case-oriented repository/UoW operations only. The
  repository records supplied facts and guards; it does not classify quality
  or decide workflow acceptance.
- Preserve immutable history through supersession. Current dispositions are
  selected by an explicit current relation, never an active flag, timestamp,
  Page status, or manifest scan.
- Persist one correction reservation per effective chain. Replaying the same
  idempotency key returns ordinal 1; a different key cannot create ordinal 2.
- `CLEANED_PASS` is not a Slice 1 disposition. Slice 1 records only validated
  or ready-for-composition instance results; Slice 2 alone may create
  `CLEANED_PASS` after member, validation, and atomic acceptance facts exist.
- Slice 1 stale handling is limited to unaccepted ledger runs where
  `Page.active_cleaned_artifact_id` is null. A non-null pointer is rejected
  with `ACTIVE_POINTER_STALE_REPAIR_REQUIRES_SLICE_2`.

## Validation strategy

Use temporary real app.db/project.db integration tests, starting with a
v3-project creation/replay tracer bullet and then adding one behavior per
test. The focused suite covers migration, inventory immutability,
disposition supersession, result attribution, correction recovery/staleness,
and case-71/case-72 ledger expression. Existing ProjectStore and repository
UoW tests remain regression checks.

## Risks and open questions

- The concrete artifact-type vocabulary remains open; Slice 1 stores only
  existing ProcessingArtifact ids and does not own artifact creation.
- Per-segment residue attribution for multi-segment instances is deferred to
  Slice 2 validator work.
- Slice 1 may never update `Page.active_cleaned_artifact_id`; doing so would
  leak Slice 2 acceptance behavior.

## Final Slice status

Slice 1 is `ACCEPTED_WITH_RECORDED_ENVIRONMENT_LIMITS`. The focused validation
passes; `FULL_INTEGRATION_SUITE = ENVIRONMENT_BLOCKED` due to unavailable
`cv2` and Windows/UNC SQLite file-handle behavior. Slice 2 is the next allowed
Slice, remains unimplemented, and is excluded from the Slice 1 commit.
