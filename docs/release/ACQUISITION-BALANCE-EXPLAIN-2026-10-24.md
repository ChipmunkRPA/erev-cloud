# Acquisition balance cell explanations — October 24, 2026

Contract balances now supports cell explanations for rows backed by the retained
native acquisition-cutover reader. An Acquisition source period column identifies
those rows. The viewer enables drills on their liability, asset, receivable and
current/noncurrent amounts; other balances and older rows without retained sources
do not advertise the feature. Totals are not offered a partial-source explanation.

The builder retains each cell's presented value with its original acquisition
snapshot, version identity and reporting closing-rate evidence. The explanation
shows the original event and input/output hashes, measurement versus requested
period, original amounts, maturity horizons and eligibility. Mixed-maturity asset
observations also show the original allocation policy, basis and obligation shares.
Original billing, revenue and maturity nodes link to the saved calculation trace.
Currency translation and displayed noncurrent subtraction are explained explicitly.

This uses the existing report authorization and contributor entity-scope filtering.
Saved-source reruns compare the captured contribution with the original binding;
pre-feature reports retain their original columns. This feature does not provide
ordinary-balance or frozen-snapshot explanations and does not infer missing source
amounts. It does not close the absent-member-balance-row reporting gap.

Validation: a public persisted-computation case covers transaction, functional and
reporting views, matching displayed and explained amounts, source links and maturity
and FX details. The reporting-currency saved run reproduces its explanation after
rerun. Four viewer cases pass, including refusing an ordinary row and an unsupported
balance measure. Scoped backend Ruff/mypy and frontend TypeScript pass. No deployment.
