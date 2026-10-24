# Frozen currency conversion for shared return unit costs — October 23, 2026

Shared return versions now support nonzero carrying/recovery unit costs across member transaction
currencies. Saving resolves a published direct spot rate on or before the estimate effective date,
using the existing engine rate-selection rule. It freezes the source/target currencies, original
unit costs, exact converted unit costs, rate date/key/version and rate in the version's application
basis. No inverse or triangulated rate is inferred. Missing direct coverage refuses the save.

Submission and approval compare the saved basis with current published rate evidence under the
FX publication lock. Changed evidence requires a refreshed draft; a submitted version must be
withdrawn and replaced. After approval the loader validates and applies the retained conversion
without querying a newer rate. Source version values are not rewritten. Native input parameters
retain the full conversion evidence alongside the member-currency costs. Costs remain exact unit
inputs; the existing engine rounds final amounts, avoiding premature cent rounding.

The version editor displays original/converted costs and the retained rate references before the
user submits for approval. Existing basis rows default to no conversions without rewriting their
stored hashes. Same-currency costs and foreign dimensionless rates keep their existing behavior.
Draft saves now take the FX publication gate before the portfolio row, matching approval order.

## Necessary verification

- Public PostgreSQL API: missing-rate refusal, published GBP/USD rate, save/preview, subsequent
  publication invalidates the draft preview, resave, independent approval, later publication,
  and retained-input rebuild. £12.50 × 1.25 saves $15.625; resaving at 1.50 saves $18.75; a later
  1.75 publication leaves the approved $18.75 unchanged. Passed.
- 22 focused loader/conversion cases passed, including exact sub-cent costs, original-row
  preservation, no rate lookup on replay, tampered amount refusal, and missing/inverse/future
  rate refusals.
- 11 portfolio UI cases passed, including unrounded converted costs and original rate references.
- Scoped types/lint and regenerated OpenAPI/client types passed.

## Remaining work

Shared breakage application still needs the expected-redemption rule. Other shared kinds,
changing common target keys, combined percentage/milestone progress, combination reassessment
and special-source opening attribution remain unfinished. This checkpoint does not claim full
Reporting or system completion. No deployment.
