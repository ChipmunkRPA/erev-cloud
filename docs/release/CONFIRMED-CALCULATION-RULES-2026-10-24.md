# Confirmed calculation rules — October 24, 2026

The owner answered all three outstanding choices. These supersede earlier notes
that these decisions are pending; implementation and verification are still required.

1. Functional current contract liability uses the existing release order and original
   FX layers, preserving layer carrying and reconciling to total liability. It does
   not use the transaction current ratio to split the total functional liability.
2. Shared breakage is a total quantity allocated by SSP. Each member's expected
   redemptions equal total rights at the effective date less allocated breakage;
   the shared estimate overrides the member's previous expected-redemption estimate.
3. On a combination split, allocate unrecognized consideration by remaining SSP at
   the modification effective date. Preserve grouping and recognized revenue before
   that date.

## Implemented in this checkpoint

Evidence revision 47 captures functional current liability from original open
acquisition layers for supported singleton principal foreign acquisitions. FIFO
keeps native layer insertion order; PRO_RATA uses native key ordering and largest
remainder for transaction quantities. Historical partial releases use original
cumulative rounding. Monetary exceptions classify the existing remeasured layer
carrying, without forecasting future FX or posting any revenue. Each layer retains
current and noncurrent carrying; the report reader independently checks the
classification against original policy and inputs.

The acquired balance reader now admits requested functional measures supplied by
that original observation, with the existing zero-component convention for
original zero transaction components. Missing nonzero functional components still
refuse; this does not supply mixed current-asset allocation or nonzero specialist
cost/return functional measures. Cell explanations show each liability layer's split.
The supported foreign acquisition contract-balance report now runs in transaction,
functional and reporting views and retains its explanation and rerun sources.

Necessary validation: 11 native/source cases and one public API workflow pass.
The public workflow exercises three balance/report views, original sources and
saved reruns. Layer cases include FIFO versus PRO_RATA, partial historical release,
cumulative rounding, full exhaustion and conservation. Scoped Ruff/mypy pass.
No deployment.

## Still to implement

Effective-date split allocation/application; broader foreign current balances
(including nonzero mixed contract assets, ordinary/combined paths and specialist
balances). These are development work, not unanswered owner choices. This checkpoint
does not claim whole-system completion.


## Shared breakage application — evidence revision 48

Saved SSP allocations now feed read-only impact, submission and atomic approval/application.
Each original member/obligation and book receives its saved quantity; expected redemptions
are effective-date rights minus that share. Shared pins override local estimates even when
local version numbers are higher. Revised scopes do not resurrect older broader shared pins.
Original per-book rational quantities travel in the computation input and are replayed
without reallocating the portfolio total inside each member group. Trace sources show the
member-specific expected redemption quantity.

Submission and approval rebuild the effective-date preview against the original verified
computation and current population/FX sources. A changed source or missing book prevents
application. The existing approval content hash, routing, member locks, immutable events
and atomic group recomputations apply. The UI exposes impact, submit and withdraw for
breakage, alongside retained allocation review. No financial change occurs when saving
an allocation or previewing its impact.

Necessary checks: 29 native/source cases, three public portfolio API workflows (including
explicit and automatic breakage target selection), and two UI impact cases pass. Scoped
Ruff, mypy, ESLint and frontend TypeScript pass. OpenAPI and generated types are updated.
The public fixtures cover singleton redemption members; broader combination/loyalty
populations and empty-population retirement are not claimed as verified by these cases.
No deployment or overall readiness claim.
