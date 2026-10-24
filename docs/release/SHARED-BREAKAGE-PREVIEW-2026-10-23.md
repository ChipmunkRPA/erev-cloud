# Shared breakage allocation preview — October 23, 2026

The owner's shared total quantity now has an accessible SSP allocation preview on saved
shared breakage versions. Each row includes contract, obligation, retained contract version,
SSP weight, entitlement quantity and allocated breakage quantity. The result identifies the
primary book and shared currency. Decimal strings preserve quantity precision; largest
remainder allocation at 18 decimal places preserves the total with stable source-key ties.

The endpoint requires access to the shared estimate population, refuses stale computations,
missing eligible members, nonpositive total SSP, unsupported precision, currency mismatches,
and allocation above an individual entitlement. It never changes the chosen SSP weights to
force an over-capacity allocation. UI refresh failures hide the preceding allocation.

This is explicitly CURRENT_COMPUTED_SSP_PREVIEW. It does not approve or apply an estimate,
freeze effective-date weights, convert cross-currency SSP, or change accounting entries.
Shared precedence/application/recomputation and effective-date combination reassessment
remain development work. Breakage quantity is not silently treated as expected redemptions
or used to eliminate unclaimed-property obligations.

Validation: 8 exact allocation cases; 3 service source/refusal cases; 9 portfolio UI cases;
frontend TypeScript and scoped ESLint; backend scoped Ruff and mypy. The public portfolio
workflow checks cross-tenant/hidden-member refusal and a population without redemption
obligations. Successful source selection has service-level coverage; this checkpoint does
not claim a positive redemption DB workflow or full release verification. No deployment.
