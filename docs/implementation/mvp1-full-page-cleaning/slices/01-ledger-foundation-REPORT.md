# Slice 1 — Full-page Cleaning Ledger Foundation Report

## Scope delivered

Slice 1 adds the additive `project_full_page_cleaning_ledger_v3` migration,
the dedicated project.db ledger repository, and narrow UoW operations for:

- page-scoped runs and their Slice 1 lifecycle;
- immutable frozen inventory and deterministic recovery reads;
- immutable instance result facts with normalized target attribution;
- append-only disposition supersession;
- one durable correction reservation per effective chain;
- unaccepted-run stale marking with no active-pointer repair.

No combined candidate, composition, page validation, issue lifecycle update,
active-cleaned-pointer acceptance, real case execution, provider, or UI/API
behavior is implemented.

## Decisions and rationale

- `CLEANED_PASS` is forbidden at both repository and SQLite-constraint levels.
  Case-71 `g002/s01` and `g002/s02` are persisted as validated results only.
- The inventory/result/disposition/correction entities are normalized rows;
  image and mask payloads remain artifact references, never SQLite BLOBs.
- Current disposition selection uses supersession, not timestamps or active
  flags. Recovery is addressed by run id and does not consult `Page.status`.
- A correction chain permanently consumes its single automatic budget at
  ordinal 1. Replays reuse it; a different key cannot create ordinal 2.
- `mark_unaccepted_cleaning_run_stale` requires a null active cleaned pointer.
  A non-null pointer returns
  `ACTIVE_POINTER_STALE_REPAIR_REQUIRES_SLICE_2` without changing it.

## Rejected alternatives

- Reusing `cleaning_result_records` as ledger truth or backfilling legacy
  Slice E/F evidence: rejected because it lacks the complete durable ledger
  semantics.
- Provisional `CLEANED_PASS`: rejected by the maintained Slice 1 boundary.
- Clearing a non-null active pointer during stale handling: deferred to Slice
  2's atomic acceptance/stale repair operation.

## Validation evidence

- `E:\APPS\anaconda\python.exe -m pytest -q tests/integration/test_full_page_cleaning_ledger_foundation.py`
  — 20 passed.
- `E:\APPS\anaconda\python.exe -m pytest -q tests/integration/test_project_store_init.py -k "not missing_project_db_blocks_project_repositories and not repository_access_after_project_db_removed_does_not_recreate_database"`
  — 10 passed, 2 deselected.
- `python -m compileall -q src tests/integration/test_full_page_cleaning_ledger_foundation.py`
  — passed.
- Native WSL isolated deletion probe — passed; it distinguishes the Windows
  UNC file-handle behavior from ProjectStore deletion recovery.

## Risks and open questions

- The available Windows test interpreter lacks `cv2`, so the entire
  integration suite cannot currently collect Slice F tests.
- The same interpreter holds SQLite files open during two existing
  `project.db.unlink()` ProjectStore tests. Those test failures remain
  environment-specific and are not treated as a Slice 1 pass.
- Artifact type/hash integrity enforcement and page-level completeness remain
  inputs to later Slice 2 validation; Slice 1 records their identifiers and
  evidence facts only.

## Final automatic Gate decision

`SLICE_1 = ACCEPTED_WITH_RECORDED_ENVIRONMENT_LIMITS`.

All Slice 1 persistence, migration, recovery, attribution, correction, and
scope-boundary exit conditions are satisfied by the recorded focused evidence.
`FULL_INTEGRATION_SUITE = ENVIRONMENT_BLOCKED`, not PASS. The next allowed
work is Slice 2; it is not part of this Slice 1 commit.
