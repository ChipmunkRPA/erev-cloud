# Shared return estimate precedence — October 23, 2026

New bundles (evidence revision 11) use the owner's shared-over-local precedence for native
RETURN_RATE calculations. Stage 04 carries all targeting return estimate histories into the
recognition path, and both the transaction-price memo and revenue measurement choose an
admitted shared estimate before a member-local estimate. Later local revisions cannot override
an already-effective shared estimate. Before the shared event's effective date/position,
local estimates remain in force. Return change decomposition includes both source histories.
Two simultaneously applicable shared elements targeting the same obligation refuse rather
than selecting an arbitrary source. This does not introduce portfolio membership transitions.

Revision 10 and earlier retain the previous first-element recognition path and date-based
memo selection for replay. New source priority is internal derived state; bundle source versions
remain identifiable in traces. This checkpoint does not expose shared submission or application
through the public API: bundle construction, approved member application and membership-effective
history still require development. Breakage total allocation is separate and its expected
redemption input source is awaiting the owner; no unclaimed-property assumption was inserted.

Verification: 49 targeted stage 04/09 return cases passed. The added native scenario runs
canonicalization, contract identification, POB building, price/allocation and revenue recognition:
January revenue is 9,200 under shared expected returns of 8 versus legacy 9,600 from the later
local estimate of 4. Same-date before/after admission, legacy replay behavior, and overlapping
shared-source refusal are checked. Scoped Ruff and mypy pass. No deployment.
