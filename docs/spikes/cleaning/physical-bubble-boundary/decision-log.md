# Decision Log

| Decision | Rationale | Rejected alternatives |
| --- | --- | --- |
| A1/A2/A5 only produce evidence and abstention | Stage A must not create a Cleaning candidate; protected physical pixels are non-writable. | Mask shrink, safe expansion, Cleaner trial. |
| Human FORM is a locked evaluation oracle, not an algorithm input | Avoids case-specific product rules and preserves reproducibility. | Writing labels into safe/protected/required masks. |
| Stage A=`NO_GO`; Stage B denied | Human-confirmed g002 text intersects frozen protected, 2 px remain uncertain, and g004 boundary has no automatic generic proof. | GO_WITH_LIMITS for g004 based only on two labelled components; Slice F reuse. |
| Keep Slice 3 blocked | Spike has not proven a general safe capability. | New case-72 run, acceptance, active-pointer update. |
