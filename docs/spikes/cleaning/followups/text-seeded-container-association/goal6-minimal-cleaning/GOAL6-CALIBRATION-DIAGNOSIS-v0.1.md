# Goal 6 calibration diagnosis v0.1

## Scope

This is a single-case, deterministic diagnosis of `cal-61` from the targeted
calibration supplement v0.2.  It is not an evaluation, a policy calibration,
or a Cleaning result.

Inputs are frozen local artifacts:

- S1: `supplement-v0.2/s1-runs/goal6-targeted-s1-v0.2/results.json`
- Goal 5 routed result: `.../results/cal-61.json`
- preview bundle: `.../goal6-targeted-previews-v0.2/bundle.json`
- replay record: `supplement-v0.2/diagnostics/cal-61-replay-v0.2.json`

## Scope boundary: cal-65 is an upstream false positive

`cal-65` contains no target text. Its star-field diagonal decoration was
misidentified upstream as a text/container candidate. Its `ALL_SKIP` outcome
therefore validates negative-case rejection only; it is not residual-text
evidence and must not participate in P0/P1/P2 Cleaning-policy comparison.

Keep the two failure classes separate:

- `cal-61` and `cal-62`: real text was found, but the candidate left readable
  text residue.
- `cal-65`: no target text existed; detection/association created a false
  positive candidate.

`cal-65` must be recorded separately as an upstream false-positive issue.

## Reproduced findings

| Check | Result | Evidence |
| --- | --- | --- |
| final binary mask covers its thresholded seed-dark pixels | Pass, 100% for P0/P1/P2 | `effective_seed_dark_coverage = 1.0` |
| a normal preview candidate changes pixels | Fail by design | all `candidate_changed_pixels = 0` |
| preview points to a wrong artifact | No | third panel exactly equals the replayed candidate; first panel equals source |
| border-sampled fill fails to write back | No | forced diagnostic probe changes 9,218 / 9,652 / 10,094 pixels, with 0 changes outside `effective` |
| P0/P1/P2 enter the execution path | Yes, before the risk gate | thresholds 155 / 167 / 177; effective pixels 9,218 / 9,652 / 10,094 |

The mask coverage claim is deliberately limited to the harness's own
thresholded seed-dark definition.  It is not pixel-ground-truth segmentation
accuracy and does not claim coverage of every anti-aliased or semantic stroke.

## Root cause in v0.2

`cal-61` is classified E2 because its background standard deviation exceeds
the E1 limit.  In the current preview builder, `border_sampled_fill` is called
only for `risk == E1`; E2 takes `source.copy()`.  Thus all three policy
previews intentionally show an unchanged candidate even though their masks
and parameters differ.

The calibration form exposed P0/P1/P2 as if those were comparable Cleaning
policies for this E2 case.  That presentation was invalid: no local Cleaning
method was actually executed for `cal-61`.

This was an implementation defect, not an open policy choice.  The Algorithm
Lock and Goal 6 Harness already freeze E2 to `Telea r=2` as a comparison-only,
human-reviewed candidate.

## Correction in v0.3

The preview harness now invokes only `Telea r=2` for E2.  It was replayed on
the same frozen `cal-61` input; no threshold, route, S1 result, or source crop
was changed.

| Policy | method | changed pixels | changes outside `M_effective` | preview equals replay |
| --- | --- | ---: | ---: | --- |
| P0 | Telea r=2 comparison | 9,218 | 0 | yes |
| P1 | Telea r=2 comparison | 9,652 | 0 | yes |
| P2 | Telea r=2 comparison | 10,094 | 0 | yes |

The new visual review still shows readable residual text for `cal-61`; this is
now a valid quality finding rather than an artifact-generation failure.

## Soft-edge diagnosis and v0.4 candidate correction

The residual is not a Telea write-back failure. On `cal-61`, all measured gray
residual pixels lay within the detector seed and outside intrinsic protected
structure; most were immediately adjacent to the hard core but were classified
as provisional `uncertain` by the old harness. That classification made them
non-editable even though they were anti-alias edge evidence.

The v0.4 candidate construction adds a constrained soft-edge completion step
before the uncertain band is derived: it promotes only seed-connected pixels
that are gray (`threshold < luminance <= 250`), within a declared 1/2/3 pixel
radius, and outside contour/structure/other-container protection. The remaining
outer band is still `uncertain` and remains non-editable.

For frozen `cal-61`, seed-gray residual counts dropped from 5,816 / 5,382 /
4,940 to 808 / 346 / 125 for P0/P1/P2. All candidates still had zero changes
outside `M_effective`. This establishes a new human-review candidate only; it
does not freeze the policy.

## Current decision

`GOAL6_TARGETED_CALIBRATION_v0.2 = INVALID_FOR_POLICY_FREEZE`, but the
replacement v0.4 review is valid for the limited mask-policy decision below.

- `P0_conservative` is frozen for this Spike: `cal-61` and `cal-62` both
  selected P0 with `residual=none` and `structure_damage=none` in the v0.4
  `FORM.md` review.  The choice is the least invasive one when all three rows
  were visually equivalent.
- `cal-65=ALL_SKIP` remains a rejection of an upstream false positive, not a
  Cleaning-policy score.
- This does not convert the invalid v0.2 form into evidence and does not
  authorize parameter changes, global automatic cleaning, or AUTO_ACCEPT.
- Do not execute formal evaluation or workflow integration.
- E2 remains the already-frozen `Telea r=2` comparison-only path; it is never
  an automatic choice or acceptance.

## Post-lock full-page human demonstration

The user-authorized demonstration copied, without modifying, the two selected
source pages `local_samples/real/black2.webp` and
`local_samples/real/gura_color.webp` into a separate ignored input pack.  It
then used a new frozen S1 run, the unchanged Goal 5 association lock and the
P0 lock.  It is not Goal 6 independent evaluation and cannot update either
lock.

| Page | eligible route / topology | candidate regions | skip regions | changed outside `M_effective` |
| --- | --- | ---: | ---: | ---: |
| black2 | coarse container / different | 5 E1 | 0 | 0 |
| gura_color | coarse container / different | 3 E1, 2 E2 comparison | 2 E3 | 0 |

Both pages also passed effective-mask disjointness.  The E1-only output is the
conservative visible candidate; the second gura_color output adds E2 Telea
r=2 solely as a labelled review comparison.  Human visual review remains
required; no full-page candidate is an accepted cleaning result.

## gura_color context-semantics diagnosis

The original `mask-safe-overlay.png` overlaid every constructed context, even
when the risk gate later selected `E3/SKIP`.  This created the misleading
appearance that two text bubbles had been masked but silently missed by E1/E2
write-back.  A per-context replay proves the execution path is correct:

| Context | Risk / application | effective pixels | E1 changed | E2 comparison changed | gate reason |
| --- | --- | ---: | ---: | ---: | --- |
| container-002 (left blue text) | E3 / SKIP | 10,449 | 0 | 0 | 4 core/protected overlaps |
| container-003 (orange small bubble) | E3 / SKIP | 538 | 0 | 0 | 112 core/protected overlaps |

All E1 contexts changed their effective pixels (apart from a one-pixel
same-colour no-op); both E2 contexts changed only in the E2 comparison image.
The display now separately writes all-context, E1-applied, E1+E2-comparison,
E3-skipped and context-risk-map overlays in a fresh diagnostic directory.

This fixes the **display semantics**, not the E3 decision: zero tolerance for
core/protected overlap deliberately keeps those two bubbles unmodified.  The
left blue bubble may be a future risk-classification question, but changing it
would be a new calibration decision and is out of scope for the frozen P0
demonstration.  The full-page gura_color review is therefore `REVIEW`, not
`ACCEPTABLE`; E2 is not adopted.

### Formal conclusion

Candidate write-back behavior is consistent with the risk gate.  The original
anomaly came from a full-context mask overlay that did not distinguish `APPLY`
from `SKIP`: E1 contexts wrote normally, E2 was comparison-only and judged
worse by human review, and E3 remained unchanged by design.  The full-page
result remains `REVIEW`.

`container-003` has 112 core/protected overlaps in 538 effective pixels
(about 20.8%), so its E3 classification is straightforward.  `container-002`
has only 4 in 10,449 (about 0.04%) yet is also E3 because the current gate is
zero-tolerance.  Whether later gates should consider overlap ratio, protected
structure type, connectivity to text, or subtracting protected pixels instead
of rejecting a whole context is a separate risk-classification investigation.
It is explicitly not a reason to alter frozen P0 in this Goal 6 run.
