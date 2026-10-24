# Acquired functional POB sources — October 23, 2026

Evidence revision 16 links the existing cutover billing adjustment flow to original obligation
baseline amounts, subtracting fully identified pre-cutover billing. The source trace uses the
original event member for ASC606 and the original fair-value allocation node for IFRS15. The
existing S12 conversion and largest-remainder calculation retain the actual functional amount,
original rate and rounding; no new journal or historical exchange rate is inferred.

The functional opening-report reader now accepts these original cutover nodes alongside ordinary
billing documents and still requires complete document coverage. Native functional POB
classification and closing eligibility snapshots consume the same source population. Pre-cutover
invoices are counted with the corresponding cutover correction, not again beside a full baseline.
Snapshots remain obligation eligibility before the group cap, not allocated group carrying values.

Incomplete document populations, mismatched raw baselines and mixed signed POB corrections
are not admitted through this path. A mixed positive/negative split of one net FX flow still
requires a defined allocation rule; no arbitrary share is fabricated. All source inputs are
validated before new attribution nodes are emitted. Older evidence revisions remain unchanged.

## Necessary verification

35 focused cases pass, including two full foreign-currency engine scenarios with and without
pre-acquisition billing. Both ASC606 and IFRS15 books compare revision 15 against 16: posting
intents and layer movements match exactly; trace formulas reconcile. Contract and POB policies
produce the same journals. January opening relief is EUR 9,000 in ASC606; IFRS15 is EUR 6,750
from the .9 cutover layer or EUR 6,000 from an original .8 prepayment layer. A prior invoice also
exercises the negative IFRS15 cutover correction. Actual engine traces feed the API functional
opening reader and preserve its complete-source check. Scoped lint and Python types pass.

This covers the engine-to-report-reader source path. A populated public acquired-contract
report/approval/lock/rerun workflow and reporting-currency presentation still require direct
verification. Multiple POB rounding, mixed-sign offsets, acquisition agents/cross-entity cases
and broader historical membership remain separate scope. No deployment or live migration.
