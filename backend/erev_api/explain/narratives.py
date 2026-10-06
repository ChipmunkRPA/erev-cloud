"""Narrative templates for explain (dev-guide DG-KRN-EXP-06, DG-KRN-EXP-07; 05 RCP-26; REQ-RPT-018).

``NARRATIVES`` maps a ``narrative_key``, the formula id without its version suffix (ENGINE_SPEC
CV-54), to a template. Placeholders:

- ``{value}``: the node's value;
- ``{input:<n>}``: the value of the node's n-th input, a node or a source reference carrying
  ``detail["value"]`` or the node's ``params["value"]``;
- ``{period}``: the period part of the node id;
- ``{date:<param>}``: the node parameter ``<param>``, a ``YYYY-MM-DD`` date.

Money renders as ``<ISO code> <amount>`` with en-US grouping and the currency's minor-unit places
(DS-FMT-05), a negative amount in parentheses (the D-75 default style); other numbers keep their
exact digits with grouping; dates render as ``DD MMM YYYY`` (DS-FMT-16). The renderer formats only
node values and node parameters.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import Final

from erev_engine.currencies import ISO_4217
from erev_engine.money import round_half_up, to_fraction
from erev_engine.trace import TraceNode

__all__ = ["NARRATIVES", "format_amount", "format_date", "render"]

NARRATIVES: Final[Mapping[str, str]] = MappingProxyType(
    {
        # ENGINE_SPEC_B §9.5 revenue_cum; inputs (exact allocation X, posted allocation A,
        # progress f); nodes carry params["as_of"].
        "sched.cumulative_posted": (
            "Cumulative amount to {date:as_of} = {input:0} × {input:2}, rounded half up to the "
            "minor unit and bounded by the allocation {input:1} = {value}."
        ),
        # ENGINE_SPEC_B §9.5 revenue; inputs (current cumulative, previous cumulative).
        "sched.period_difference": (
            "Amount for {period} = cumulative {input:0} − previous cumulative {input:1} = {value}."
        ),
        # ENGINE_SPEC_B §9.5 progress_ratio (ENC-1); params start, end, as_of.
        "rec.progress.time_elapsed.daily": (
            "Time elapsed from {date:start} to {date:as_of}, in days over the term ending "
            "{date:end} = {value}."
        ),
        "rec.progress.time_elapsed.monthly_even": (
            "Time elapsed from {date:start} to {date:as_of} in equal periods, partial first and "
            "last periods prorated by days, over the term ending {date:end} = {value}."
        ),
        "rec.progress.time_elapsed.mid_month": (
            "Time elapsed from {date:start} to {date:as_of} in periods counted under the day-15 "
            "rule, over the term ending {date:end} = {value}."
        ),
        "rec.progress.prospective_segment": (
            "Progress since the boundary on {date:start} to {date:as_of}, over the remaining term "
            "ending {date:end} = {value}."
        ),
        "rec.progress.point_in_time": (
            "Units whose control has transferred by {date:as_of}, less units returned, over the "
            "contracted quantity = {value}."
        ),
        # ENC-4: units delivered (S09-R-10); ENC-3: output percent and milestones (§9.2.4).
        "rec.progress.units": (
            "Units delivered by {date:as_of}, less units returned, over the contracted quantity "
            "= {value}."
        ),
        # ENGINE_SPEC CV-50 rev 1.31 (T1F-LP-PR-1): the rule-produced zero under a guard / no FIXED.
        "rec.progress.unmeasured": (
            "No progress is measured at {date:as_of} — the target is under a status guard or the "
            "obligation has no FIXED component — so progress = {value} by rule."
        ),
        "rec.progress.output_percent": (
            "Latest recorded output progress by {date:as_of}, since the last boundary where one "
            "applies = {value}."
        ),
        "rec.progress.milestone": (
            "Cumulative weight of the milestones achieved by {date:as_of}, since the last boundary "
            "where one applies = {value}."
        ),
        # ENC-5: input measures (S09-R-14 to S09-R-16; POL-091).
        "rec.progress.cost_to_cost": (
            "Margin-bearing costs incurred by {date:as_of}, excluding wasted costs and uninstalled "
            "materials, over the estimated total costs net of the expected uninstalled materials, "
            "since the last boundary where one applies = {value}."
        ),
        "rec.progress.labour_hours": (
            "Labour hours to {date:as_of} over the expected total hours of the estimate, since the "
            "last boundary where one applies = {value}."
        ),
        "rec.progress.cost_recovery": (
            "Costs incurred by {date:as_of}, capped at the allocation, over the allocation, while "
            "the outcome cannot yet be measured = {value}."
        ),
        # ENC-6 (D-98 candidate 28): the right to invoice as the output measure (S09-R-18).
        "rec.progress.right_to_invoice": (
            "Right to invoice for performance by {date:as_of} over the stated price of the line, "
            "since the last boundary where one applies, capped at 1 = {value}."
        ),
        # ENGINE_SPEC_B §9.5 revenue_target_exact; input (progress).
        "rec.target_exact.inception": (
            "Exact revenue to {date:as_of} = allocation × progress {input:0} = {value}."
        ),
        "rec.target_exact.prospective": (
            "Exact revenue to {date:as_of} = revenue at the boundary + remaining allocation × "
            "progress since the boundary {input:0} = {value}."
        ),
        # ENC-5: zero-margin uninstalled materials (S09-R-14; D-76).
        "rec.uninstalled_materials": (
            "Exact revenue to {date:as_of} = progress {input:0} × the allocation net of the "
            "expected uninstalled materials, plus the uninstalled materials transferred at zero "
            "margin = {value}."
        ),
        # ENGINE_SPEC_B §9.5 revenue_cum (ENC-1): components summed, each posted once (S09-R-03).
        "rec.step1_net": (
            "Revenue target net of the 606-10-25-7 revenue already attributed to the obligation "
            "when the Step 1 criteria were met: the target less the share, not below 0 = {value}."
        ),
        "rec.revenue_cum": (
            "Cumulative revenue to {date:as_of}: the exact target rounded half up to the minor "
            "unit, bounded by the allocation, plus realised variable amounts = {value}."
        ),
        # ENGINE_SPEC_B §9.5 return_expected_units and returns targets (ENC-7; ALG-06).
        "returns.expected_units": (
            "Expected further returns at {date:as_of}: the estimate {input:0} less units returned "
            "since it, never below 0 and nil after the return window = {value}."
        ),
        "returns.revenue_target": (
            "Exact revenue to {date:as_of} on units kept, net of expected returns, at the unit "
            "allocation rate, or after the latest return at the refreshed unit rate = {value}."
        ),
        # ENGINE_SPEC_B S09-R-23a units billed or paid and E_b (D-91 C606-01).
        "returns.units_billed": (
            "Units billed or paid at {date:as_of}: the counted invoice lines, one per invoice line "
            "identity from its unconditional date, divided by the refund price per unit = {value}."
        ),
        "returns.refundable_units": (
            "Expected returns of units billed at {date:as_of}: the lesser of the expected further "
            "returns {input:0} and the units billed {input:1} less the units returned, never "
            "below 0 = {value}."
        ),
        "returns.excess_reversal": (
            "Exact revenue after the return on {date:as_of}: the returned units reversed at the "
            "configured reversal rate = {value}."
        ),
        # ENGINE_SPEC_B §9.2.8 redemption pattern and breakage, §9.2.9 royalties (ENC-8).
        "breakage.proportional": (
            "Redemption entitlement at {date:as_of}: units redeemed over units issued, or the "
            "expected entitlement ratio in proportion to redemptions over expected redemptions, "
            "whichever is greater and at most the whole allocation = {value}."
        ),
        "breakage.remote": (
            "Redemption entitlement at {date:as_of}: units redeemed over units issued, plus the "
            "remaining breakage share once its non-exercise is attested as remote = {value}."
        ),
        "breakage.expiry": (
            "Entitlement at the lapse of the rights by {date:as_of}: the whole allocation less the "
            "unclaimed-property share that is never revenue = {value}."
        ),
        "royalty.accrual": (
            "Royalties recognised to {date:as_of}: the licensee statements for ended usage periods "
            "and the accrued estimates for ended periods not yet reported, once the licence is "
            "satisfied = {value}."
        ),
        "royalty.minimum_guarantee": (
            "Royalties recognised to {date:as_of}: cumulative reported and accrued royalties above "
            "the minimum guarantee, which is fixed consideration recognised on the licence "
            "pattern = {value}."
        ),
        "royalty.report_true_up": (
            "Statement true-up on {date:as_of}: the licensee statement {input:0} less the prior "
            "measurement of the same usage period it replaces, the accrued estimates or the "
            "statement it corrects = {value}."
        ),
        # ENGINE_SPEC_B §9.5 revenue_by_cause, catch-up measures, manual and held targets (ENC-9).
        "rec.decompose.sequential": (
            "Revenue for {period} by cause: the catch-ups and event effects cited, with normal "
            "revenue taking the rest of the period amount = {value}."
        ),
        "rec.catch_up.sum": "Cumulative catch-up to {date:as_of}, the sum of the boundary "
        "catch-ups cited = {value}.",
        # ENGINE_SPEC_B §9.5 obligation measures at the version date (ENC-10).
        "rec.allocation": (
            "Allocation in force: the obligation's allocated amount at the version date is "
            "{value}, the segment in force net of any returns reduction."
        ),
        "rec.allocation_adjustment": (
            "Allocation adjustment at the version date: the allocation in force less the stated "
            "price gives {value}."
        ),
        "rec.segment_state": (
            "Segment in force: the obligation's {member} at the version date is {value}."
        ),
        "rec.activity_sum": ("Activity of this version: the cited events sum to {value}."),
        # ENGINE_SPEC CV-64 rev 1.30 (T1F-89-1): the exact revenue-activity chain.
        "rec.exact_endpoint": (
            "Exact revenue target at this event's position on {date:as_of} = {value}."
        ),
        "rec.exact_difference": (
            "Exact revenue effect of this event = after {input:0} − before {input:1} = {value}."
        ),
        "rec.exact_activity": (
            "Exact activity of this version: the cited event effects sum to {value}."
        ),
        "rec.remaining": (
            "Remaining at {date:as_of}: the allocation less revenue to date, or the contracted "
            "quantity less the units consumed = {value}."
        ),
        "rec.scheduled": (
            "Scheduled at {date:as_of}: the part of the allocation that a time-elapsed pattern "
            "places in later periods without further events, whereas revenue to date is "
            "{input:0} = {value}."
        ),
        "rec.awaiting": (
            "Awaiting a trigger at {date:as_of}: the remaining allocation {input:0} less the "
            "scheduled amount {input:1} = {value}."
        ),
        # ENGINE_SPEC_B §10.5 billing measures (ENC-11).
        "bil.attribution": (
            "Billing attributed to the obligation: the invoice lines that reference it less the "
            "credit memos, or its largest-remainder share of a document's unreferenced total = "
            "{value}."
        ),
        "books.contract_sum": (
            "Contract total: the obligations' figures cited sum to {value} for the contract "
            "version."
        ),
        "books.unit_revenue_rate": (
            "Unit revenue rate: the cited allocation over the cited quantity = {value} per unit "
            "(0 when no quantity remains)."
        ),
        "books.version_adjustment": (
            "Re-measured at the version date: the last build-up member adjusted by the cited "
            "change gives {value}."
        ),
        "bal.member_sum": (
            "Member balance: the components of this contract and entity at the period end sum to "
            "{value}."
        ),
        "cost.member_sum": (
            "Member balance: the contract cost assets or loss provisions of this contract and "
            "entity at the period end sum to {value}."
        ),
        "bil.billed_amount": (
            "Billing activity of this version: the billing documents first included sum to "
            "{value} for the obligation."
        ),
        "bil.remaining_billing": (
            "Remaining billing at {date:as_of}: the billing plan of the allocation segment in "
            "force less the billing since its boundary, whereas billing to date is {input:0} = "
            "{value}."
        ),
        "bil.unconditional_date": (
            "Billing unconditionally due to {date:as_of}: the attributed invoice lines whose right "
            "to consideration is unconditional by then, less credit memos = {value}."
        ),
        # ENGINE_SPEC_B §10.5 positions, refund liabilities and return assets (ENC-12).
        "pos.net_position": (
            "Contract liability less contract asset and unbilled receivable at {date:as_of}, "
            "before the netting reclass: billing unconditionally due, deposits transferred, "
            "noncash consideration and interest expense accreted, less revenue relief, interest "
            "income accreted, the receivable contra and the refund-liability flows through the "
            "contract liability = {value}."
        ),
        "pos.obligation": (
            "Billing to date {input:0} less revenue to date at {date:as_of}, or the same amount "
            "summed over the obligations of the contract and entity = {value}."
        ),
        "rl.return": (
            "Refund liability for expected returns at {date:as_of}: the refund price per unit × "
            "the expected returns of units billed, rounded half up = {value}."
        ),
        "rl.vc_target": (
            "Refund liability of the variable consideration element at {date:as_of}: the "
            "refund-liability target of the estimate version in force = {value}."
        ),
        "rl.termination": (
            "Termination refund liability at {date:as_of}: the refund agreed on termination less "
            "the credit memos that consumed it, or its share by posted allocation = {value}."
        ),
        "rl.concession": (
            "Concession refund liability at {date:as_of}: the concession settled by credit memo or "
            "refund less the credit memos that consumed it = {value}."
        ),
        "rl.unclaimed_property": (
            "Unclaimed-property refund liability at {date:as_of}: the amount to be remitted less "
            "the remittance credit memos = {value}."
        ),
        "rl.consumption": (
            "Credit memo of {input:0} on {date:as_of} consumes the refund-liability component, "
            "termination refunds first, then concessions, oldest first, up to its open balance "
            "= {value}."
        ),
        # ENGINE_SPEC_B §10.5 receivables and the presentation split (ENC-13).
        "pos.split_ca_ur": (
            "Presented at {date:as_of}: a credit balance {input:0} is the contract liability; a "
            "debit balance is an unbilled receivable up to the uninvoiced revenue of obligations "
            "with an unconditional right, and a contract asset for the rest = {value}."
        ),
        "pos.receivable_contra": (
            "Receivable contra at {date:as_of}: billing unconditionally due {input:0} × the "
            "expected implicit price concession rate, rounded half up = {value}."
        ),
        "bil.ar_balance": (
            "Accounts receivable at {date:as_of}: unconditional invoices including tax, less "
            "credit memos and payments applied = {value}."
        ),
        "pos.accretion_attribution": (
            "Interest accreted to {date:as_of}, attributed to the obligation by posted allocation "
            "over the obligations that carry the financing adjustment = {value}."
        ),
        # ENGINE_SPEC_B §10.5 reclass attribution and current parts (ENC-14).
        "pos.reclass_attribution.pob_debit_positions": (
            "Period-end reclass at {date:as_of} of the debit balance {input:0}: the unbilled "
            "receivable over obligations with an unconditional right and the contract asset over "
            "the others, each by uninvoiced revenue, attributed to this obligation = {value}."
        ),
        "pos.reclass_attribution.cumulative_ssp_delivered": (
            "Period-end reclass at {date:as_of} of the debit balance {input:0}, attributed by "
            "cumulative SSP delivered, then revenue, posted allocation or SSP; variable "
            "consideration lines take none = {value}."
        ),
        # ENGINE_SPEC_B C-05, S10-R-22 rev 1.100: a contract booked ahead of the open periods.
        "pos.reclass_attribution.no_measured_period": (
            "Period-end reclass at the version date {date:as_of}: no accounting period from the "
            "contract's inception on is open for its contracting entity yet, so none is "
            "evaluated and nothing is attributed to this obligation = {value}."
        ),
        "pos.current_split": (
            "Current part at {date:as_of}: revenue expected within 12 months for the contract "
            "liability, assets of obligations ending within 12 months, and every unbilled "
            "receivable = {value}."
        ),
        # ENGINE_SPEC_B §11.5 contract costs (ENC-15).
        "cost.capitalise": (
            "Cost of {input:0} capitalised on {date:capitalization_date} as a contract cost asset "
            "= {value}."
        ),
        "cost.expense_reason": (
            "Cost of {input:0} incurred on {date:as_of} not capitalised, for the recorded reason "
            "= {value}."
        ),
        "cost.amortise.straight_line": (
            "Amortisation to {date:as_of}: each segment's base spread evenly over its period and "
            "rounded cumulatively = {value}."
        ),
        "cost.amortise.proportional": (
            "Amortisation to {date:as_of}: each segment's base in proportion to the related "
            "revenue, rounded cumulatively = {value}."
        ),
        "cost.recoverable": (
            "Recoverable amount at {date:as_of}: remaining expected consideration including "
            "anticipated renewals, less remaining direct costs = {value}."
        ),
        "cost.impair.us": (
            "Impairment to {date:as_of}: the carrying amount above the recoverable amount "
            "{input:0}, never more than the carrying amount = {value}."
        ),
        "cost.impair.ifrs_reversal": (
            "Impairment reversed to {date:as_of}: the rise in the recoverable amount {input:0}, "
            "capped at the carrying amount without impairment = {value}."
        ),
        "cost.carrying": (
            "Carrying amount at {date:as_of}: capitalised less amortisation, impairment, clawbacks "
            "and acceleration, plus reversals = {value}."
        ),
        # ENGINE_SPEC_B §11.5 clawbacks, acceleration and loss provisions (ENC-16).
        "cost.clawback": (
            "Commission clawed back to {date:as_of}: each recovered amount taken from the oldest "
            "capitalisation first, never more than the carrying amount = {value}."
        ),
        "cost.accelerate": (
            "Amortisation accelerated on termination to {date:as_of}: the carrying amount in "
            "excess of the remaining benefit of the related obligations = {value}."
        ),
        "loss.tp_unconstrained": (
            "Expected consideration at {date:as_of}: the unconstrained, credit-adjusted "
            "transaction price allocated to the loss unit = {value}."
        ),
        "loss.expected_margin": (
            "Expected margin at {date:as_of}: the expected consideration {input:0} less the "
            "estimated total costs = {value}."
        ),
        "loss.required_provision": (
            "Loss provision required at {date:as_of}: the expected loss less the loss already "
            "recognised through margin to date, never below zero = {value}."
        ),
        "loss.movement": (
            "Loss provision movement to {date:as_of}: the required provision {input:0} less the "
            "previous period's = {value}."
        ),
        "returns.return_asset": (
            "Return asset at {date:as_of}: the carrying cost less recovery costs per unit × the "
            "expected returns, or × the units returned within the expected returns = {value}."
        ),
        "sched.manual_release": (
            "Target to {date:as_of} after the approved manual release: never below the scheduled "
            "target {input:0} and never above the allocation = {value}."
        ),
        "sched.manual_defer": (
            "Target to {date:as_of} after the approved manual deferral out of the period, never "
            "below the previous period's target = {value}."
        ),
        "sched.override_respread": (
            "Target to {date:as_of} under the approved schedule override: the listed amounts, then "
            "the remaining allocation spread over the remaining progress = {value}."
        ),
        "sched.hold_freeze": (
            "Target to {date:as_of} under a recognition hold applied on {date:applied}: frozen at "
            "the level before the hold, whereas the scheduled target is {input:0} = {value}."
        ),
        # ENGINE_SPEC §7.5 onboarding nodes (ENB-9).
        "onb.opening_segment": (
            "Posted allocation at the cutover: the contract transaction price apportioned by "
            "largest remainder over the imported allocations, revenue to date {input:0} plus "
            "remaining allocation {input:1} = {value}."
        ),
        "onb.baseline": (
            "Opening cumulative revenue on {date:cutover_date} from the imported revenue to date "
            "{input:0}, rounded to the minor unit within the allocation = {value}."
        ),
        "onb.difference": (
            "Onboarding difference on {date:cutover_date}: the recomputed cumulative target less "
            "the imported cumulative {input:0} = {value}."
        ),
        "onb.ifrs_fair_value_split": (
            "Acquisition-date fair value of the contract liability {input:0} apportioned over the "
            "remaining obligations by their remaining allocations = {value}."
        ),
        # ENGINE_SPEC §8.6 estimate reassessment nodes (ENB-10).
        "estimate.pin": "Estimate version in force from {date:effective_date} = {value}.",
        "estimate.tp_delta": (
            "Change in the allocated transaction price from the estimate change: allocation basis "
            "after {input:1} less before {input:0} = {value}."
        ),
        "estimate.route.inception": (
            "Share of the transaction price change {input:0} allocated to this obligation on the "
            "inception basis (its carried exact quota plus its relative standalone-selling-price "
            "share of the change, posted as one apportionment of the price over the exact "
            "quotas) = {value}."
        ),
        "estimate.route.32_45": (
            "Share of the transaction price change {input:0} routed to the obligations identified "
            "before the modification, the unsatisfied part re-split over the obligations after "
            "it = {value}."
        ),
        "estimate.catch_up": (
            "Catch-up on {date:as_of}: cumulative revenue with the new allocation less cumulative "
            "revenue with the previous allocation, at the same progress = {value}."
        ),
        # ENGINE_SPEC §1.5, §2.5, §3.4, §4.4 and §5.5 nodes of stages 01 to 05 (ENA-13).
        "input.echo": (
            "Stored as entered: this figure repeats its source value {value} without any "
            "calculation."
        ),
        "alloc.unit_ssp": (
            "Unit standalone selling price: the selected SSP divided by the original quantity "
            "gives {value} per unit."
        ),
        # CV-50 links of original_allocated_exact / original_allocated_amount (D-98 candidate 121):
        # the current original allocation over the node(s) that produced it.
        "alloc.original_total": (
            "Current original allocation (exact): {value}, the raw quota that the cited producer "
            "components — the relative share with its targeted shares, a repin's share or a "
            "created obligation's quota — reconstruct within the encoding bound at their exact "
            "values."
        ),
        "alloc.original_total_amount": (
            "Current original allocation (posted): the cited posted contributions, each counted "
            "once, sum to {value} — the posted amount itself, not a rounding of the exact total."
        ),
        "alloc.original_weight": (
            "Allocation weight of a boundary's created obligation: its raw weight over the raw "
            "total of the boundary's weights, bound to the cited weight and total nodes, = {value}."
        ),
        "ingest.ledger_sum": "Quantity to date: the delivered and returned quantities cited, "
        "summed = {value}.",
        "step1.status": "Contract status after the event, as its 04 status ordinal = {value}.",
        "step1.enforceable_term": (
            "End of the enforceable term on {date:date}, as an ordinal day number = {value}."
        ),
        "step1.deposit": (
            "Deposit amount to {period}: the receipts, refunds and transfers cited, signed and "
            "summed = {value}."
        ),
        "step1.event_25_7": (
            "Deposit balance recognised as revenue under 606-10-25-7: the deposit movements cited, "
            "signed and summed, capped at the stated consideration less the revenue already "
            "recognised under the rule = {value}."
        ),
        "step1.deposit_revenue_share": (
            "The obligation's share of the contract's 606-10-25-7 revenue: the recognitions cited, "
            "summed and apportioned by largest remainder over the in-scope obligations = {value}."
        ),
        "step1.transition_catch_up": (
            "Deposit balance transferred to the contract liability when the Step 1 criteria are "
            "met = {value}."
        ),
        "pob.template_match": (
            "Obligation term from its booking line under the matched template = {value}."
        ),
        "pob.merge": "Term of the combined obligation: the member lines' terms summed = {value}.",
        "pob.bundle_split": (
            "Component price: the bundle line price apportioned by largest remainder over the "
            "component weights = {value}."
        ),
        "pob.option_ssp": (
            "Standalone selling price of the option: the incremental discount weighted by the "
            "likelihood of exercise, or the entered amount = {value}."
        ),
        "pob.agent_net": (
            "Consideration retained as agent, net of the amount due to the supplier, or the gross "
            "amount kept as a memo = {value}."
        ),
        "tp.fixed": "Fixed consideration: the stated prices of the obligations in scope = {value}.",
        "tp.buildup": "Transaction price member: the members cited, signed and summed = {value}.",
        "tp.realised_usage": (
            "Usage-based fees or royalties reported to date, less any minimum guarantee = {value}."
        ),
        "tp.vc_expected_value": (
            "Variable consideration by the expected value method: the scenario amounts weighted "
            "by their probabilities = {value}."
        ),
        "tp.vc_most_likely": "Variable consideration by the most likely amount method = {value}.",
        "tp.vc_entered": "Variable consideration entered by the preparer = {value}.",
        "tp.vc_constrained": (
            "Variable consideration included in the transaction price after the constraint "
            "= {value}."
        ),
        "tp.concession_implicit": (
            "Implicit price concession: the concession ratio applied to the fixed consideration of "
            "the affected obligations = {value}."
        ),
        "tp.returns_expected": (
            "Expected returns: the unit allocation rate applied to the units returned and expected "
            "to be returned = {value}."
        ),
        "tp.tax_excluded": (
            "Sales taxes collected on behalf of third parties and excluded from the transaction "
            "price = {value}."
        ),
        "tp.cpc_reduction": "Consideration payable to the customer: the promises cited = {value}.",
        "tp.cpc_release": (
            "Customer incentive released to date: the ordinary release against related purchases, "
            "the release composed with the share-based reduction, or the incentive asset remaining "
            "(promised less released) = {value}."
        ),
        "tp.cpc_share_based": (
            "Share-based consideration payable to the customer: grant-date fair value × cumulative "
            "related revenue ÷ expected related revenue, capped at the fair value = {value}."
        ),
        "tp.noncash": (
            "Noncash consideration at fair value: units times fair value per unit, or the share "
            "whose right is unconditional = {value}."
        ),
        "tp.warranty_accrual": (
            "Assurance warranty accrual to {period}: the cost per unit times the units transferred "
            "= {value}."
        ),
        "sfc.gap_test": (
            "Financing gap test: the weighted payment date less the transfer date, in days "
            "= {value}."
        ),
        "sfc.cash_selling_price": (
            "Cash selling price: the payments discounted or accreted at the annual rate {input:0} "
            "= {value}."
        ),
        "sfc.effective_interest.monthly": (
            "Financing interest to {period}: the financed balance times the monthly rate, "
            "cumulated = {value}."
        ),
        "sfc.effective_interest.annual": (
            "Financing interest to {period}: each contract year's opening balance times the annual "
            "rate, spread monthly and cumulated = {value}."
        ),
        "sfc.accretion": (
            "Financed balance at the end of {period}: the opening balance plus interest, less or "
            "plus the payments = {value}."
        ),
        "ssp.select_version": "SSP book version selected for the pricing date = {value}.",
        "ssp.extend": "Extended standalone selling price: the unit value times the quantity "
        "= {value}.",
        "ssp.legacy_range": (
            "Legacy range SSP: quantity times the unit list price less the midpoint discount, "
            "spread by the range ratio, gives {value}."
        ),
        "ssp.convert": (
            "Standalone selling price converted to the transaction currency at the spot rate "
            "= {value}."
        ),
        "ssp.point": (
            "Standalone selling price selected from the SSP entry for the stated price = {value}."
        ),
        "alloc.relative_ssp": (
            "Relative standalone selling price: the obligation's weight, or its share of the "
            "amount allocated = {value}."
        ),
        "alloc.largest_remainder": (
            "Posted allocation: the amount apportioned by largest remainder at the minor unit "
            "= {value}."
        ),
        "alloc.targeted_vc": (
            "Variable consideration allocated entirely to its target obligations by relative "
            "standalone selling price, or the basis left for the other obligations = {value}."
        ),
        "alloc.discount_exception": (
            "Discount allocated entirely to the bundle's obligations: the bundle's share of the "
            "transaction price = {value}."
        ),
        "alloc.residual": (
            "Residual standalone selling price: the transaction price less the standalone selling "
            "prices of the other obligations = {value}."
        ),
        # ENGINE_SPEC §6.6 (ENB-2): modification weights, pool and shares, catch-up.
        "mod.weights.d18": (
            "Modification weight on {date:as_of}: standalone selling prices at the modification "
            "date of the remaining and added goods, or the inception basis of a partially "
            "satisfied obligation = {value}."
        ),
        "mod.pool.remaining_tp": (
            "Modification pool on {date:as_of}: remaining allocation of the pooled obligations "
            "plus the modification consideration and includable variable consideration, or its "
            "share by relative weight = {value}."
        ),
        "mod.stated_price": (
            "Stated price after the modification: the previous stated price plus the consideration "
            "change of the cited event gives {value}."
        ),
        "mod.allocation_adjustment": (
            "Allocation adjustment after the modification: the allocation in force less the stated "
            "price gives {value}."
        ),
        "mod.catch_up": (
            "Catch-up on {date:as_of}: cumulative revenue with the allocation after the "
            "modification less cumulative revenue before it, at the boundary = {value}."
        ),
        # ENGINE_SPEC §6.6 (ENB-13): proposal classes, price test and the total-price pool.
        "mod.classify": (
            "Progress of the obligation at the modification date, which classifies it as "
            "satisfied, distinct from the goods already transferred, or not distinct = {value}."
        ),
        "mod.price_test": (
            "Consideration of the added goods, compared with their standalone selling price to "
            "decide whether the modification is a separate contract = {value}."
        ),
        "mod.pool.total_tp": (
            "Modification pool on the total updated transaction price, or its share by delivered "
            "and remaining standalone selling price = {value}."
        ),
        # ENGINE_SPEC §6.6 (ENB-3): inception-basis weights, pools by line, satisfied performance.
        "mod.weights.inception_all": (
            "Modification weight on {date:as_of} on the inception basis: remaining units at the "
            "inception unit standalone selling price plus added goods at the modification date "
            "= {value}."
        ),
        "mod.pool.by_line": (
            "Modification pool on {date:as_of} attributed by line: remaining allocation plus the "
            "consideration of the lines on the obligation = {value}."
        ),
        "mod.satisfied_performance": (
            "Price change on satisfied performance on {date:as_of}, apportioned by original "
            "allocation or targeted to the attested obligation = {value}."
        ),
        # ENGINE_SPEC §6.6 (ENB-4): terminations.
        "mod.termination": (
            "Termination on {date:as_of}: revenue recognised before the termination plus the "
            "obligation's share of the pool, or the refund owed to the customer = {value}."
        ),
        # ENGINE_SPEC §6.6 (ENB-5): material-right exercise.
        "mod.exercise.continuation": (
            "Material right exercised on {date:as_of}: the option closes at the revenue already "
            "recognised, and its remaining allocation plus the additional consideration goes to "
            "the optioned goods by relative standalone selling price = {value}."
        ),
        "mod.exercise.modification": (
            "Material right exercised on {date:as_of} as a modification: the option's remaining "
            "allocation joins the pool, and the optioned goods are added for the additional "
            "consideration = {value}."
        ),
        # ENGINE_SPEC §6.5 (ENB-6 to ENB-8): legacy prospective, retrospective and POB-specific VC
        # templates.
        "mod.legacy.prospective": (
            "Prospective template on {date:as_of}: the revenue recognised to date plus the "
            "obligation's share of the remaining allocation and the modification billing by "
            "remaining standalone selling price, or the posted allocation = {value}."
        ),
        "mod.legacy.mod_ssp": (
            "Modification standalone selling price on {date:as_of}: the modification billing "
            "limited to the range of the file's price version for the modified quantity = {value}."
        ),
        "mod.legacy.retrospective": (
            "Retrospective template on {date:as_of}: the modified transaction price spread by "
            "delivered and remaining standalone selling prices over every obligation, or the "
            "posted allocation = {value}."
        ),
        "mod.legacy.pob_vc": (
            "Price change on one obligation on {date:as_of}: its remaining allocation plus the "
            "change plus the revenue recognised to date, or the posted allocation = {value}."
        ),
        # ENGINE_SPEC §8.5 prior-period decomposition (ENB-12); inputs are the boundary parts.
        "estimate.prior_period": (
            "Revenue of the period from performance satisfied before {date:period_start}: the "
            "change in cumulative revenue at the period start from each allocation or totals "
            "change in the period, plus late-event carries = {value}."
        ),
        # ENGINE_SPEC §8.4 posting-period assignment of a late event (ENB-11).
        "late.assign": (
            "An event effective {date:effective_date} falls in a closed period, so its effect "
            "posts in the first open period, {value} period(s) later, keeping its origin period."
        ),
        # ENGINE_SPEC_B §12.5 intercompany pairs (END-3).
        "ent.pair": (
            "Intercompany pair for {period}: the revenue of an obligation performed by another "
            "entity, in transaction currency or at the contracting entity's layer relief = {value}."
        ),
        "ent.performing_revenue_rate": (
            "Performing entity's revenue for {period}: each revenue amount of the pair at that "
            "entity's average or spot rate, rounded half up to the minor unit = {value}."
        ),
        # ENGINE_SPEC_B §12.5 foreign-currency layers (END-1).
        "fx.layer.create": (
            "Contract-liability layer created on {date:effective_date}: the transaction amount at "
            "the spot rate of that date, rounded half up to the minor unit = {value}."
        ),
        "fx.asset_layer.create": (
            "Asset layer created on {date:effective_date} for an amount beyond the open contract "
            "liability, at the average rate of the period or the spot rate = {value}."
        ),
        "fx.layer.consume.fifo": (
            "Layer relief on {date:effective_date}, oldest layer first: the cumulatively rounded "
            "share of the layer's historical functional amount = {value}."
        ),
        "fx.layer.consume.pro_rata": (
            "Layer relief on {date:effective_date}, apportioned over the open layers by open "
            "balance: the cumulatively rounded share of the layer's historical amount = {value}."
        ),
        "fx.credit_memo_difference": (
            "Credit memo on {date:effective_date}: the relieved amount at spot less the historical "
            "relief of the contract-liability layers = {value}."
        ),
        "fx.revenue_functional": (
            "Cumulative revenue in functional currency to the end of {period}: the layer reliefs "
            "and the asset layers created for the obligation's revenue = {value}."
        ),
        "fx.gain_loss.sum": (
            "Signed sum of the foreign-currency differences to the end of {period} = {value}."
        ),
        # ENGINE_SPEC_B §12.5 remeasurement and monetary liabilities (END-2).
        "fx.functional_member": (
            "Functional-currency balance of this contract and entity at the period end: {value}, "
            "from the entity's open layers and reclass shares."
        ),
        "fx.settlement.spot": (
            "Settlement on {date:effective_date}: the settled amount at spot, its carrying share, "
            "or the difference between them = {value}."
        ),
        "fx.remeasure.closing": (
            "Remeasurement at {date:effective_date}: the open transaction amount at the closing "
            "rate less the carrying amount before = {value}."
        ),
        "fx.monetary_liability.create": (
            "Monetary liability layer created on {date:effective_date} at the spot rate of that "
            "date = {value}."
        ),
        "fx.monetary_liability.recognition_difference": (
            "Recognition on {date:effective_date}: the liability at spot less the functional "
            "debit of the contract liability = {value}."
        ),
        "fx.monetary_liability.settle": (
            "Monetary liability settled on {date:effective_date}: the settled amount at spot, or "
            "its difference from the carrying share = {value}."
        ),
        "fx.monetary_liability.remeasure.closing": (
            "Monetary liability remeasured at {date:effective_date}: the open amount at the "
            "closing rate less the carrying amount before = {value}."
        ),
        # ENGINE_SPEC_B §13.5 LEGACY book fold (END-8).
        "books.legacy_fold": (
            "Pre-standard revenue to {period}: the signed amounts of the pre-standard revenue "
            "events recorded for the obligation = {value}."
        ),
        # ENGINE_SPEC_B §15.2.4 revenue from obligations satisfied in prior periods (EDS-4).
        "disc.prior_period_sum": (
            "Revenue of {period} from performance satisfied in earlier periods, summed over the "
            "contract's obligations = {value}."
        ),
        # ENGINE_SPEC_B §15.5 remaining performance obligations and time bands (EDS-1).
        "disc.rpo": (
            "Remaining performance obligation at the version date: the scheduled and "
            "awaiting-trigger amounts still to recognise, less the amounts a practical expedient "
            "omits = {value}."
        ),
        "disc.rpo_band": (
            "Remaining performance obligation expected in this time band, placed by period end and "
            "apportioned over the amount no practical expedient omits = {value}."
        ),
        "disc.rpo_exemption": (
            "Remaining performance obligation omitted under a practical expedient (606-10-50-14 to "
            "50-14A) = {value}."
        ),
        # ENGINE_SPEC_B §14.6 role targets and deltas (END-5).
        "post.role_target": (
            "Posting target to the end of {period}: the signed template part targets of the "
            "account role, a split side apportioned with largest remainder = {value}."
        ),
        "post.delta": (
            "Posting delta in {period}: the target movement of the posting class less the amounts "
            "already posted with the same origin period = {value}."
        ),
        # ENGINE_SPEC_B §14.6 account resolution (END-6).
        "post.account_resolution": (
            "Account of the line resolved in {period} at T-REF-15 step {value}: the obligation or "
            "template override, else the most specific rule of the pinned mapping version."
        ),
    }
)

MONTHS: Final = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_PLACEHOLDER: Final = re.compile(r"\{([^{}]*)\}")
_INPUT: Final = re.compile(r"input:([0-9]{1,2})")
_DATE: Final = re.compile(r"date:([a-z][a-z0-9_]*)")
_ISO_DATE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_EXACT: Final = re.compile(r"(-?)([0-9]+)(?:\.([0-9]+))?")


def format_amount(value: str, currency: str | None, minor_unit: int | None = None) -> str:
    """A node value: money with its ISO code and minor-unit places, or a grouped exact number."""
    if currency is None:
        match = _EXACT.fullmatch(value)
        if match is None:
            raise ValueError(f"{value!r} is not an exact decimal string")
        sign, whole, digits = match.groups()
        text = f"{int(whole):,}" + (f".{digits}" if digits else "")
        return f"({text})" if sign else text
    places = ISO_4217[currency].minor_unit if minor_unit is None else minor_unit
    scaled = round_half_up(to_fraction(value), places)
    whole_units, fraction = divmod(abs(scaled), 10**places)
    text = f"{whole_units:,}" + (f".{fraction:0{places}d}" if places else "")
    return f"{currency} ({text})" if scaled < 0 else f"{currency} {text}"


def format_date(value: str) -> str:
    """DS-FMT-16 ``DD MMM YYYY`` from a ``YYYY-MM-DD`` string, without time-zone conversion."""
    if not _ISO_DATE.fullmatch(value):
        raise ValueError(f"{value!r} is not a YYYY-MM-DD date")
    day = date.fromisoformat(value)
    return f"{day.day:02d} {MONTHS[day.month - 1]} {day.year:04d}"


def _node_amount(node: TraceNode) -> str:
    minor_unit = node.params.get("minor_unit")
    return format_amount(node.value, node.currency, None if minor_unit is None else int(minor_unit))


def _input_amount(node: TraceNode, index: int, inputs: Mapping[str, TraceNode]) -> str:
    if index >= len(node.inputs):
        raise ValueError(f"node {node.id!r} has no input {index}")
    item = node.inputs[index]
    if isinstance(item, str):
        return _node_amount(inputs[item])
    value = item.detail.get("value", node.params.get("value"))
    if value is None:
        raise ValueError(f"source input {item.ref_id!r} of {node.id!r} carries no value")
    return format_amount(value, None)


def render(node: TraceNode, inputs: Mapping[str, TraceNode]) -> str:
    """The node's sentence; ``inputs`` maps each node-id input to its node.

    An unknown ``narrative_key`` raises ``KeyError``; an unknown placeholder or a missing parameter
    raises ``ValueError``.
    """
    template = NARRATIVES[node.narrative_key]

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name == "value":
            return _node_amount(node)
        if name == "period":
            return node.id.rsplit(":", 1)[1]
        if (found := _INPUT.fullmatch(name)) is not None:
            return _input_amount(node, int(found.group(1)), inputs)
        if (found := _DATE.fullmatch(name)) is not None:
            parameter = node.params.get(found.group(1))
            if parameter is None:
                raise ValueError(f"node {node.id!r} has no parameter {found.group(1)!r}")
            return format_date(parameter)
        raise ValueError(f"unknown placeholder {{{name}}} in narrative {node.narrative_key!r}")

    return _PLACEHOLDER.sub(substitute, template)
