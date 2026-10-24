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

This is ordinary rated usage. Unrated metering inputs remain available through existing API/import payloads. The subsequent
royalty entry addition is described below. Broader
combination reassessment and shared breakage application remain unfinished. The expected-
redemption rule for shared breakage remains pending owner input. No deployment.


## Royalty statement entry — subsequent October 24 update

Record royalty statement is now a separate workbench action and the event action for ROYALTY
obligations. It reuses the usage fields, date validation, preview and approval commands while
explicitly retaining is_royalty_statement=true. Ordinary usage continues to omit that flag.
This makes the statement usable by the existing royalty measurement and accrual true-up paths;
it does not change their calculation or revenue timing rules.

Current obligation keys are selectable. Original merged-away combined components are deliberately
not offered: the royalty source reader currently matches the selected obligation directly and
has not implemented aggregation across those members. That remains an engine development gap.

Necessary verification: a rendered drawer submission preserves the explicit statement marker,
original entered decimal quantities/rated amounts and period; pure checks prove flag separation,
early-date refusal and ROYALTY action availability. Adjacent drawer tests, TypeScript and scoped
ESLint pass. No backend code changed and no additional backend lifecycle coverage is claimed.


## Original-member royalty omission — October 24 correctness fix

A complete native calculation reproduced a silent source loss: SERVICE and LEASE each carried
an original royalty statement (100 and 200) for January, but a combined ratable SERVICE host
priced only 100 of realised consideration. Its original lease statement was ignored. Treating
both statements as one period's latest record would also be incorrect source handling.

Until explicit member/whole-combination scope and member-specific correction/accrual replacement
are implemented, stage 04 refuses an admitted royalty statement naming a non-host original
combined member. The refusal carries the original event and combined subject identities. It
applies to ratable and usage hosts before a partial result can be published; ordinary combined
usage and RTI paths remain available. Future statements outside the pricing date/order cutoff
are not prematurely admitted. Existing saved reports are not rewritten.

Eight focused native cases pass, including the two omission refusals and six existing ordinary
combined usage/RTI cases. Scoped lint and types pass. This is an interim source-completeness
fix, not completion of combined royalties. The owner was asked whether to adopt explicit
COMBINATION/MEMBERS scope, as already used for EAC and actual hours. No answer is inferred.


## Unrated redemption entry — subsequent October 24 update

Record redemption now exposes the existing quantity-only USAGE_REPORTED path to the workbench
and REDEMPTION_PATTERN obligation actions. It offers current redemption-pattern obligations,
requires metric/quantity/period/effective date, omits rated_amount and royalty flags, and uses
existing preview and manual-event approval. Ordinary rated usage and royalty statements still
require their amounts. It does not add original-member redemption aggregation or modify the
pending shared-breakage expected-redemption rule.

Necessary checks: rendered submission with decimal quantity and no money control; payload and
action assertions; native redemption/breakage measurement with unrated usage instead of the
same control-transferring deliveries. Four resulting cumulative revenue amounts remain
33,600 / 84,000 / 100,181.82 / 116,000 and the calculation trace reevaluates exactly. The native
fixture starts from allocated state, not a new full public lifecycle. Frontend types/lint and
adjacent drawer cases pass. No deployment.
