# Goal 6 — Final Report v0.1

状态：`COMPLETED`  
最终裁决：`GO_TO_EXPANDED_CLEANING_VALIDATION`

## Scope and frozen method

Goal 6 used the frozen Goal 5 routes and the post-calibration
`P0_conservative` mask policy only.  P0 includes constrained, seed-connected
soft-edge completion for gray anti-alias pixels; it does not expand outside the
context or through intrinsic protected structure.  E1 uses the permitted local
border-sampled fill.  E2 remains Telea r=2 comparison-only, and E3/E4 or
regionless inputs remain unmodified.

No Provider, Workflow, database, product artifact, AUTO_ACCEPT, prohibited
model, source overwrite, commit or push was used.

## Evidence

The independent input lock and rendered outputs are local-only:

```text
data/local/text-seeded-container-association/goal6-minimal-cleaning-v0.1/
  evaluation-runs/goal6-p0-evaluation-v0.1/INPUT-LOCK.json
  evaluation-runs/goal6-p0-evaluation-v0.1/matrix.json
  evaluation-runs/goal6-p0-evaluation-v0.1/FORM.md
```

| Case | Frozen Goal 5 route | Result | Human review | Safety evidence |
| --- | --- | --- | --- | --- |
| case-51 | same, 1 coarse container | E1 candidate | ACCEPTABLE; no residue/damage | 10,626 changed / 10,626 effective; outside 0 |
| case-52 | different, 3 coarse containers | three independent E1 candidates | ACCEPTABLE; no residue/damage | 2,332 changed / 2,332 effective; outside 0; masks disjoint |
| case-53 | 1 bounded support | E3 abstain | SKIP; readable source is expected | candidate changes 0 |
| case-54 | regionless | fixed abstain | SKIP | mask and candidate changes 0 |

All four sources, S1 inputs, Goal 5 matrix and P0 policy matched the recorded
hash locks.  Evaluation labels were not accessed and no parameter update
occurred after the lock.

## Gate audit

| Gate | Result |
| --- | --- |
| source/S1/Goal 5/P0 lock integrity | PASS |
| mask contained by context; protected overlap | PASS / 0 effective overlap |
| different-container isolation | PASS; 0 effective-mask overlap, 0 external changes |
| readable residue in accepted E1 candidate | PASS; none |
| accepted non-text/border damage | PASS; none |
| bounded-support abstention | PASS (`case-53`) |
| regionless control unchanged | PASS (`case-54`) |
| E2 automatic adoption | PASS; not adopted |
| AUTO_ACCEPT/product integration | PASS; absent |

## Decision and limits

The result supports **expanded manual cleaning validation**, not product
integration and not automatic clearing.  It is evidence only for ordinary E1
bubbles under the frozen P0 policy.  E2 remains comparison-only; E3/E4 and
regionless inputs must abstain.

The full-page `gura_color` demonstration additionally found that a tiny
core/protected overlap can force an entire ordinary-looking bubble to E3.  That
is a separate risk-gate investigation (overlap ratio/type/connectivity or
protected-pixel subtraction), not a post-evaluation P0 change.

## Subsequent status

This is a historical Goal 6 verdict, not current authorization to expand
Cleaning.  Goal 7 subsequently showed that local B1 coarse candidates can be
`WRONG_OR_LEAK`; it blocks Pixel Text Mask, safe edit regions and E1/E2
automatic cleaning until a later decision resolves semantic qualification.
