# Mixed acquisition reporting

The contract-balance rollforward supports reporting for the existing mixed ordinary/acquired
principal-group calculations. It uses authenticated original monthly group snapshots and
preserves the original member population, transaction currency, functional currency and
reporting-currency rates.

Acquisition changes are signed. An acquisition can settle an existing group asset, so a
business-combination movement can be negative. The report presents those movements once at
group level. Member rows show opening and closing balances; movement cells remain unavailable
when the original computation does not establish a member allocation. Member endpoint rows
are informational and do not enter aggregate totals.

Monthly opening-revenue and asset-settlement movements retain separate named lines. Reporting
translation and rounding are separate from functional remeasurement. Original group endpoints
must reconcile to the sum of member balances.

Acquisition-cell explanations include original member history links, event/FX source sets,
trace links and computation hashes. Saved-input reruns rebuild from those retained sources.
Missing snapshots, incomplete populations and inconsistent original evidence refuse explicitly.
The public report does not accept a standalone contract-selection parameter.

This reporting feature preserves the supported acquisition methods and entity boundaries.
It does not add acquisition scenarios or change journal, FX, schedule or balance calculations.
Source reconciliation, signed explanations and three-currency retained reruns are covered by
focused calculation and public-report checks.
