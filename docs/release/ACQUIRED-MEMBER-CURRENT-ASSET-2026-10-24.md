# Acquired member current assets — October 24, 2026

Evidence revision 61 publishes dated current contract assets for principal acquisition
members using either admitted onboarding method, including groups with ordinary members.
Transaction amounts follow each member's original obligation reclassification shares and
maturity. Functional amounts follow the corresponding original functional reclassification
amounts. Neither uses the liability proportional-allocation rule. Noncurrent remains total
less current; group transaction totals and individual carrying bounds are checked.

The existing functional report adapter reads the new nodes. Single-member closed-cutover
observations reuse the member current-asset nodes when present and retain the older independent
capture path for earlier evidence revisions, avoiding duplicate node identities. Posting intents,
revenue schedules and FX layer movements are unchanged.

Validation: 56 focused acquired/ordinary current-asset, acquisition-adapter and mixed-group
cases pass. New cases cover long/short member maturity, acquisition cutover baselines, same-currency
recomputed baselines, mixed ordinary/acquired groups and foreign report projection. Existing
closed-cutover tests also run at revision 61, including unconditional rights and mixed maturity.
A foreign recomputed onboarding case explicitly verifies the original posting refusal under both
revisions 60 and 61; the reporting extension does not remove it. Scoped Ruff, mypy and diff checks
pass. Acquired agents and non-acquisition openings remain excluded. No deployment.
