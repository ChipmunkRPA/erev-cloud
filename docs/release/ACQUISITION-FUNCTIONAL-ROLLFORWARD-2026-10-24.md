# Foreign acquisition functional rollforward — October 24, 2026

The contract-balance rollforward now reads the three required original functional
balance totals for supported singleton principal foreign acquisitions with no ordinary
cutover balance row. It no longer requires current/noncurrent classifications that
this report does not display. Full contract-balance reports still request all measures
and refuse missing functional classifications; no classification policy was inferred.

Endpoint projection consumes the already authenticated original acquisition observation,
checks its currency, requested period and transaction endpoint, and selects only the
requested retained functional measures. Acquisition movements use the matching original
functional targets and trace nodes. Ordinary original cutover nodes take precedence.
For the liability member bridge, original open layers supply carrying when ordinary
persisted movements are absent; the original layer reconciliation remains required.
Locked endpoint selection continues through the existing frozen computation path.

The public foreign example verifies USD 22,000 closing liability and acquisition
movement, EUR 19,909.50 reporting closing balance, EUR 20,000 translated acquisition
movement, EUR -90.50 translation and zero unexplained OTHER. Balance comparison passes;
cell explanations link to original functional nodes and saved reruns reproduce rows.
This is a fixture with the original cutover outside the posting horizon, not a claim
that this new acquisition path has been closed and locked in production.

Necessary regression coverage includes the existing actually locked foreign acquisition
and same-currency complete observation. Scoped lint/types and diff checks pass.
No deployment. Full foreign current/noncurrent balances, multi-member/mixed acquisition
and agent scenarios remain separate outstanding work.
