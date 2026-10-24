# Rated usage workbench entry — October 24, 2026

## Delivered

The engine and manual-event API already supported rated usage, including original combined
components, but the workbench offered no usage entry drawer. Record usage is now available in
the contract event menu and the USAGE/RIGHT_TO_INVOICE obligation actions. It collects the
original obligation, metric, decimal quantity, usage period, rated contract-currency amount and
effective date. A combined host allows selection of its retained original component keys.

The drawer retains the original identity in both the top-level event and payload, validates
period ordering and prevents an effective date before the period end. It accepts zero quantity
and rated amount, rejects negative rated amounts, and preserves decimal strings. Existing
preview, uncertain-response command keys, permissions and manual-event approval remain in use.
No new posting logic or automatic approval was introduced. Evidence is optional for usage.

## Necessary verification

The drawer interaction submits an original combined member with quantity 50000.125, rated
amount 5000.25 and September dates. Focused validation covers reversed periods, early effective
dates, zero values, invalid amounts and obligation action availability. Existing drawer checks
exercise adjacent submissions and preview behavior. TypeScript and scoped ESLint pass.

The existing populated public usage workflow was rerun: submission leaves revenue unchanged
until independent approval, then appends the usage event and computes the fee. This is the
actual backend command reused by the new UI; it is not a browser end-to-end claim.

## Boundaries

This is ordinary rated usage. Royalty-statement authoring and unrated metering inputs remain
available through their existing API/import payloads and are not added to this drawer. Broader
combination reassessment and shared breakage application remain unfinished. The expected-
redemption rule for shared breakage remains pending owner input. No deployment.
