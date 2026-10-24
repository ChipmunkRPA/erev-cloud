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

Shared-breakage submission, impact, atomic approval/application and member override;
effective-date split allocation/application; broader foreign current balances
(including nonzero mixed contract assets, ordinary/combined paths and specialist
balances). These are development work, not unanswered owner choices. This checkpoint
does not claim whole-system completion.
