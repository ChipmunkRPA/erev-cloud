"""Metamorphic suite (dev-guide §9.7 row "Metamorphic", rev 1.10; research 06 §18.5; BUILD_SPEC
END-14).

Four transformations of a generated world that must not change its results:

- scaling every amount by F = 10^k (k in 1..3) with quantities, dates and policies fixed: every
  exact figure scales by F (trace node exact values within the roundings along their derivation,
  schedule ``cumulative_exact`` and the exact amount columns exactly) and every posted figure
  within the propagated roundings: a nearest rounding drifts by at most (F + 1) ÷ 2 minor units, a
  largest-remainder share by less than F + 1, a sum by the sum of its terms' drifts; residues are
  validated against the same propagation; nonmonetary nodes and columns are unchanged. A posted
  figure need not scale exactly (100.00 over three equal SSPs posts 33.33 / 33.33 / 33.34, tenfold
  333.33 / 333.33 / 333.34; T1-Q-2). The ALG-03 split of a debit position between unbilled
  receivable and contract asset follows posted figures and may move; the pair total is compared;
- one batch equals several arrivals: a prefix (an effective-date slice, or a record prefix that may
  leave out an earlier-effective event arriving later) computed and sealed as ``posted``, then the
  full stream, gives the cumulative intents of the full stream computed at once (RCP-05,
  S14-R-04) and the same versions, balances and schedules;
- a calendar shift by whole months with equal day counts per period leaves every figure unchanged
  once period keys, dates and date ordinals are read relative to the inception (``DAILY`` and
  point-in-time lines);
- an IFRS15 book whose resolved policies equal the ASC606 book's gives identical obligation
  versions, balances, schedules, intents and trace values.
"""

from __future__ import annotations

import dataclasses
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Final

import pytest
from erev_engine import compute
from erev_engine.bundle import (
    BalanceOut,
    BookOutput,
    EventInput,
    FxLayerMovementOut,
    InputBundle,
    ObligationVersionOut,
    PostedAmountInput,
    PostingIntent,
    TemplateInput,
)
from erev_engine.canonical import canonical_bytes
from erev_engine.dates import add_months
from erev_engine.money import EXACT_PLACES, to_fraction
from erev_engine.stages.state import ScheduleLineOut
from erev_engine.trace import TraceNode
from hypothesis import assume, example, given
from hypothesis import strategies as st
from support import intent_totals, prop_worlds
from support.answer_keys import loader
from support.prop_worlds import (
    GROUP,
    INCEPTION,
    LineSpec,
    MeasureSpec,
    WorldSpec,
    bundle,
    month_lengths,
    scaled,
    span_months,
)
from support.strategies import world_specs
from support.trace_linkage import FUNCTIONAL, balance_link_columns

pytestmark = pytest.mark.property

# T-CON-11 erev.exact columns that are amounts (scale with the world) and those that are
# quantities or ratios (unchanged by scaling).
EXACT_AMOUNT_COLUMNS: Final = frozenset(
    {
        "allocated_exact",
        "original_allocated_exact",
        "original_ssp_high",
        "original_ssp_low",
        "original_ssp_mid",
        "original_ssp_selected",
        "original_total_contract_ssp",
        "original_unit_revenue_rate",  # S05-R-16 / CV-47 (b): x_p ÷ Q; strict exact scaling
        # (the engine's Q18(x_p) numerator is D-98 candidate 117, an ENG-T1F item)
        "original_unit_ssp",
        "remaining_ssp",
        "ssp_delivered",
        "ssp_delivered_cum",
        "ssp_unit_list_price",
        "unit_ssp",
    }
)
EXACT_DIMENSIONLESS_COLUMNS: Final = frozenset(
    {
        "allocation_weight",
        "delivered_quantity",
        "delivered_quantity_cum",
        "original_quantity",
        "progress_ratio",
        "quantity",
        "remaining_quantity",
        "returned_quantity_cum",
        "ssp_midpoint_discount_ratio",
        "ssp_range_ratio",
    }
)
CONTRACT_EXACT_AMOUNT_COLUMNS: Final = frozenset({"total_ssp"})
# Column provenance (Codex 2329 exact-encoding advisory; supervisor addendum to D-98 candidate 116):
# the assembler derives these stored exact columns from an ENCODED node value — ``allocated_exact``
# from the ``allocated_amount`` node's value + residue, ``original_ssp_selected`` from the
# ``residual_ssp`` node for a residual candidate, ``total_ssp`` from the ``total_ssp`` node
# (``erev_engine.__init__``: ``_exact``, ``_selected_ssp``) — so they carry the CV-51 /
# DG-KRN-EXP-03 18-place half-up encoding and scale within ``_encoding_tolerance`` — but only on
# the branch that actually encoded (Codex 2341): ``allocated_exact`` when the version links an
# ``allocated_amount`` node (its no-node segment-sum fallback is raw), ``original_ssp_selected``
# when the column links the ``residual_ssp`` node under the CV-53 alias (ordinary SSP, a missing
# residual node and the zero path are raw), ``total_ssp`` when the contract version links the
# ``total_ssp`` node (the resolved-SSP-sum fallback is raw). ``encoded_columns`` reads the branch
# from the row's links. Every other exact amount column is the raw rational (SSP bounds and
# units, ``original_allocated_exact``, ``ssp_delivered*``, ``remaining_ssp``,
# ``original_total_contract_ssp``) and scales exactly. ``original_unit_revenue_rate`` keeps the
# strict
# exact scaling assertion (S05-R-16 x_p ÷ Q; the engine's Q18(x_p) numerator is D-98 candidate 117,
# an ENG-T1F engine item — this test does not soften it). ``remaining_unit_revenue_rate`` is checked
# by ``_assert_remaining_rate`` alone (REMAINING-ONLY conditional law; capsule §5).
ENCODED_EXACT_COLUMNS: Final = frozenset({"allocated_exact", "original_ssp_selected", "total_ssp"})


def encoded_columns(links: Mapping[str, str], nodes: Mapping[str, TraceNode]) -> frozenset[str]:
    """The exact amount columns of one row whose encoded producer branch applied (Codex 2341).

    Unit revenue rates are NOT members: ``original_unit_revenue_rate`` keeps the strict exact
    scaling law (D-98 candidate 117 is the engine's item) and ``remaining_unit_revenue_rate`` is
    judged by ``_assert_remaining_rate`` alone (D-98 candidate 116 ADDENDUM 3 REVISION 4)."""
    found: set[str] = set()
    if links.get("allocated_amount") in nodes:
        found.add("allocated_exact")
    if links.get("original_ssp_selected", "").startswith("residual_ssp:"):
        found.add("original_ssp_selected")
    if links.get("total_ssp") in nodes:
        found.add("total_ssp")
    assert found <= ENCODED_EXACT_COLUMNS
    return frozenset(found)


REMAINING_RATE: Final = "remaining_unit_revenue_rate"
HALF_QUANTUM: Final = Fraction(1, 2 * 10**EXACT_PLACES)  # h/2: the 18-place encoding error
# POSITIVE WHITELIST of the eligible input family (D-98 candidate 116 ADDENDUM 3 REVISION 4; Codex
# production-20260921-0139 requirement 1). Inspected on the CONSTRUCTED bundle and its defaults as
# well as on the WorldSpec, so a future constructor change cannot widen eligibility silently:
# ordinary distinct STANDARD PRINCIPAL obligations, TIME_ELAPSED DAILY / MONTHLY_EVEN or
# POINT_IN_TIME only, positive observable AMOUNT SSP and prices, inception booking / activation
# plus DELIVERY / BILLING only, no returns or policy pins, modifications, special methods, payment
# / deposit release, VC / royalty / extra components, holds / manual / posted input, residual or
# bundle SSP, specialist policies or features. Output zeros and method blacklists are not
# eligibility.
ELIGIBLE_LINE_KINDS: Final = frozenset(prop_worlds.KINDS)
ELIGIBLE_MEASURE_KINDS: Final = frozenset({prop_worlds.DELIVERY, prop_worlds.BILLING})
ELIGIBLE_EVENT_TYPES: Final = frozenset(
    {"CONTRACT_BOOKED", "CONTRACT_ACTIVATED", "DELIVERY_RECORDED", "BILLING_RECORDED"}
)
ELIGIBLE_METHODS: Final = frozenset({"TIME_ELAPSED", "POINT_IN_TIME"})
ELIGIBLE_CONVENTIONS: Final = frozenset({"DAILY", "MONTHLY_EVEN", None})
BOOKING_LINE_KEYS: Final = frozenset(
    {"obligation_key", "product_code", "quantity", "total_price", "start_date", "end_date"}
)
DELIVERY_KEYS: Final = frozenset({"obligation_key", "quantity", "trigger"})
BILLING_KEYS: Final = frozenset(
    {"invoice_number", "line_external_id", "obligation_key", "amount", "issue_date"}
)


def _template_reason(template: TemplateInput) -> str | None:
    ratable = template.recognition_method == "TIME_ELAPSED"
    checks = (
        (template.obligation_kind == "STANDARD", "obligation_kind"),
        (template.distinctness == "distinct", "distinctness"),
        (template.principal_agent == "PRINCIPAL", "principal_agent"),
        (template.series_increment_unit is None, "series"),
        (template.recognition_method in ELIGIBLE_METHODS, "recognition_method"),
        (template.ratable_convention in ELIGIBLE_CONVENTIONS, "ratable_convention"),
        ((template.ratable_convention is not None) == ratable, "convention / method mismatch"),
        (template.satisfaction_pattern == ("OVER_TIME" if ratable else "POINT_IN_TIME"), "pattern"),
        (template.over_time_criterion == ("OT_A" if ratable else "NOT_APPLICABLE"), "criterion"),
        (
            template.start_date_rule == "LINE_START" and template.end_date_rule == "LINE_END",
            "dates",
        ),
        (template.term_months is None, "template term"),
        (template.warranty_type == "NONE", "warranty"),
        (template.licence_nature == "NOT_APPLICABLE", "licence"),
        (not template.sfc_assessment_required, "sfc"),
        (not template.account_role_overrides, "account overrides"),
        (not template.is_excluded_from_netting_attribution, "netting exclusion"),
        (not template.policy_values, "policy values"),
    )
    failed = [name for ok, name in checks if not ok]
    return None if not failed else f"template {template.template_code}: {failed}"


def _world_whitelist(spec: WorldSpec, world: InputBundle) -> str | None:
    """None when the world's CONSTRUCTED inputs lie inside the eligible family, else the named
    prerequisite that fails (REVISION 4 requirement 1)."""
    lines = [line for _, contract_lines in spec.contracts for line in contract_lines]
    if not {line.kind for line in lines} <= ELIGIBLE_LINE_KINDS:
        return "line kinds outside DAILY / MONTHLY_EVEN / PIT"
    if any(line.price <= 0 or line.ssp <= 0 or line.quantity < 1 for line in lines):
        return "non-positive price, SSP or quantity"
    if not {measure.kind for measure in spec.measures} <= ELIGIBLE_MEASURE_KINDS:
        return "measures other than deliveries and billings"
    if world.tenant_preset != "DEFAULT":
        return f"tenant preset {world.tenant_preset!r}"
    if world.rule_set_versions or world.estimate_versions or world.fx_rates or world.posted:
        return "rule sets, estimates, FX rates or posted input present"
    for contract in world.contracts:
        if (
            contract.judgements
            or contract.material_rights
            or contract.modifications
            or contract.noncash_consideration
            or contract.consideration_payable
            or contract.payment_schedule
            or not contract.has_commercial_substance
            or contract.termination_party is not None
            or contract.renewal_of_contract_key is not None
            or contract.scope_605_35
        ):
            return f"contract {contract.external_id}: special terms present"
    for product in world.group.products:
        if (
            product.principal_agent != "PRINCIPAL"
            or product.distinctness_default != "distinct"
            or product.is_bundle
            or product.policy_values
            or product.components
            or product.assurance_cost_per_unit is not None
            or product.is_franchisor_preopening_service
        ):
            return f"product {product.code}: not an ordinary distinct principal product"
    for template in world.pob_template_versions:
        reason = _template_reason(template)
        if reason is not None:
            return reason
    for version in world.ssp_versions:
        for entry in version.entries:
            band = entry.ranges[0] if len(entry.ranges) == 1 else None
            if (
                entry.method != "observable"
                or entry.value_basis != "AMOUNT"
                or entry.distinctness != "distinct"
                or entry.observable_point is not None
                or entry.unit_list_price is not None
                or entry.midpoint_discount_ratio is not None
                or entry.range_ratio is not None
                or entry.cost_basis is not None
                or entry.margin_ratio is not None
                or band is None
                or band.band_dimension != "NONE"
                or band.point_value is None
                or band.point_value <= 0
                or band.low_value is not None
                or band.high_value is not None
            ):
                return f"SSP entry {entry.entry_key}: not a positive observable AMOUNT point"
    for event in world.events:
        if event.event_type not in ELIGIBLE_EVENT_TYPES:
            return f"event type {event.event_type}"
        if event.is_manual or event.origin != "API":
            return f"manual or non-API event {event.event_key}"
        if (
            event.supersedes_event_key
            or event.modification_key
            or event.estimate_version_key
            or event.manual_adjustment_key
        ):
            return f"{event.event_key}: void, modification, estimate or manual-adjustment reference"
        payload = event.payload
        if event.event_type == "CONTRACT_BOOKED":
            booking = payload.get("lines")
            if not isinstance(booking, list | tuple) or not booking:
                return f"{event.event_key}: booking without lines"
            for line in booking:
                if not isinstance(line, Mapping) or set(line) != BOOKING_LINE_KEYS:
                    members = sorted(line) if isinstance(line, Mapping) else line
                    return f"{event.event_key}: booking line members {members}"
                if to_fraction(line["total_price"]) <= 0 or to_fraction(line["quantity"]) < 1:
                    return f"{event.event_key}: non-positive line price or quantity"
        elif event.event_type == "DELIVERY_RECORDED":
            if set(payload) != DELIVERY_KEYS or payload.get("trigger") != "DELIVERY":
                return f"{event.event_key}: delivery payload {sorted(payload)}"
        elif event.event_type == "BILLING_RECORDED":
            if set(payload) != BILLING_KEYS:
                return f"{event.event_key}: billing payload {sorted(payload)}"
        elif dict(payload) != {"checklist": {}}:
            return f"{event.event_key}: activation payload {dict(payload)}"
    return None


def _booking_lines(event: EventInput) -> list[Mapping[str, object]]:
    lines = event.payload.get("lines")
    assert isinstance(lines, list | tuple), (event.event_key, "booking lines")
    for line in lines:
        assert isinstance(line, Mapping), (event.event_key, "booking line")
    return list(lines)


def _worlds_invariant(base: InputBundle, other: InputBundle) -> str | None:
    """None when the two worlds differ only in money amounts: same contracts, dates, calendars,
    quantities, event order and keys, templates, products and SSP entry keys (requirement 1)."""
    if len(base.events) != len(other.events):
        return "event count differs"
    for one, two in zip(base.events, other.events, strict=True):
        if (
            one.event_key,
            one.event_type,
            one.effective_date,
            one.record_seq,
            one.obligation_keys,
        ) != (
            two.event_key,
            two.event_type,
            two.effective_date,
            two.record_seq,
            two.obligation_keys,
        ):
            return f"event {one.event_key}: key, type, date, sequence or obligations differ"
        if one.event_type == "CONTRACT_BOOKED":
            for a, b in zip(_booking_lines(one), _booking_lines(two), strict=True):
                for member in (
                    "obligation_key",
                    "product_code",
                    "quantity",
                    "start_date",
                    "end_date",
                ):
                    if a[member] != b[member]:
                        return f"{one.event_key}: booking line {member} differs"
        elif one.event_type == "DELIVERY_RECORDED":
            if one.payload["quantity"] != two.payload["quantity"]:
                return f"{one.event_key}: delivered quantity differs"
    if [(c.external_id, c.inception_date) for c in base.contracts] != [
        (c.external_id, c.inception_date) for c in other.contracts
    ]:
        return "contracts or inception dates differ"
    if base.pob_template_versions != other.pob_template_versions:
        return "templates differ"
    if base.group.products != other.group.products:
        return "products differ"
    if [e.entry_key for v in base.ssp_versions for e in v.entries] != [
        e.entry_key for v in other.ssp_versions for e in v.entries
    ]:
        return "SSP entry keys differ"
    if base.entities != other.entities or base.currencies != other.currencies:
        return "calendars or currencies differ"
    if (
        base.books != other.books
        or base.known_at != other.known_at
        or base.trigger != other.trigger
    ):
        return "books, known_at or trigger differ"
    return None


UNIT_RATE_FORMULA: Final = "books.unit_revenue_rate.v1"  # CV-47 (b), stage 13 output step
REMAINING_FORMULA: Final = "rec.remaining.v1"  # §9.5 remaining allocation / quantity, stage 09
REVENUE_CUM_FORMULA: Final = "rec.revenue_cum.v1"  # §9.5 revenue_cum, stage 09


@dataclasses.dataclass(frozen=True)
class _RateSources:
    """Every source of one eligible row's remaining rate, resolved BY NAME (Codex 0214 C2)."""

    stored: Fraction  # raw ``remaining_unit_revenue_rate`` column
    x_raw: Fraction  # raw ``original_allocated_exact`` column
    f_raw: Fraction  # raw ``progress_ratio`` column
    q_raw: Fraction  # raw ``remaining_quantity`` column
    allocated: int  # posted ``allocated_amount`` column (minor units)
    revenue_posted: int  # posted ``revenue_cum`` column
    remaining_posted: int  # posted ``remaining_allocation`` column
    rate: TraceNode  # ``remaining_unit_revenue_rate:<subject>:-``
    top: TraceNode  # ``remaining_allocation:<subject>:-``
    bottom: TraceNode  # ``remaining_quantity:<subject>:-``
    revenue: TraceNode  # ``revenue_cum:<subject>:-``
    quantity: TraceNode  # ``original_quantity:<subject>:-``
    minor_unit: int


def _rational_param(node: TraceNode, name: str) -> Fraction | str:
    """A ``"<n>"`` / ``"<n>/<d>"`` node parameter as a Fraction, or the named reason."""
    text = node.params.get(name)
    if text is None or not re.fullmatch(r"-?\d+(/\d+)?", text):
        return f"{node.id}: params {name!r} absent or not a rational ({text!r})"
    return Fraction(text)


def _rate_sources(row: ObligationVersionOut, nodes: Mapping[str, TraceNode]) -> _RateSources | str:
    """Resolve the row's rate sources with a NAMED refusal for every absent column, link or node
    (Codex 0214 C2) — no direct dictionary lookup reaches the assertions."""
    subject = row.subject_key
    columns = row.columns
    for column in (
        REMAINING_RATE,
        "original_allocated_exact",
        "progress_ratio",
        "remaining_quantity",
        "allocated_amount",
        "revenue_cum",
        "remaining_allocation",
    ):
        if columns.get(column) is None:
            return f"eligible row without a {column} value (NULL or absent)"
    link = row.trace_nodes.get(REMAINING_RATE)
    if link is None:
        return "eligible row without a remaining-rate link"
    if link != f"{REMAINING_RATE}:{subject}:-":
        return f"rate link {link!r} is not the row's version-state node"
    ids = {
        "rate": link,
        "top": f"remaining_allocation:{subject}:-",
        "bottom": f"remaining_quantity:{subject}:-",
        "revenue": f"revenue_cum:{subject}:-",
        "quantity": f"original_quantity:{subject}:-",
    }
    found: dict[str, TraceNode] = {}
    for name, node_id in ids.items():
        node = nodes.get(node_id)
        if node is None:
            return f"{name} node {node_id!r} missing from the trace"
        found[name] = node
    for column, expected in (
        ("remaining_allocation", ids["top"]),
        ("remaining_quantity", ids["bottom"]),
        ("revenue_cum", ids["revenue"]),
    ):
        if row.trace_nodes.get(column) != expected:
            return f"{column} column links {row.trace_nodes.get(column)!r}, not {expected!r}"
    minor_unit = found["top"].params.get("minor_unit")
    if minor_unit is None or not minor_unit.isdigit():
        return "remaining_allocation node without a minor_unit parameter (not a posted node)"
    for column in ("allocated_amount", "revenue_cum", "remaining_allocation"):
        if not isinstance(columns[column], int) or isinstance(columns[column], bool):
            return f"posted column {column} is not whole minor units"
    return _RateSources(
        stored=to_fraction(columns[REMAINING_RATE]),  # type: ignore[arg-type]
        x_raw=to_fraction(columns["original_allocated_exact"]),  # type: ignore[arg-type]
        f_raw=to_fraction(columns["progress_ratio"]),  # type: ignore[arg-type]
        q_raw=to_fraction(columns["remaining_quantity"]),  # type: ignore[arg-type]
        allocated=int(columns["allocated_amount"]),  # type: ignore[call-overload]
        revenue_posted=int(columns["revenue_cum"]),  # type: ignore[call-overload]
        remaining_posted=int(columns["remaining_allocation"]),  # type: ignore[call-overload]
        rate=found["rate"],
        top=found["top"],
        bottom=found["bottom"],
        revenue=found["revenue"],
        quantity=found["quantity"],
        minor_unit=int(minor_unit),
    )


def _rate_identities(s: _RateSources, row: ObligationVersionOut) -> str | None:
    """The EXPECTED formula identities of the rate, numerator, quantity and revenue nodes on the
    unchanged inception FIXED path (Codex 0214 C2; ENGINE_SPEC CV-47 (b), §9.5), or the named
    identity that fails. Cross-world equality of formula ids proves nothing about the formula
    itself; each node is compared with the formula the engine states for it."""
    mu = s.minor_unit
    # the rate node: books.unit_revenue_rate.v1 over exactly its two inputs, zero → 0, the
    # posted numerator's exact value in params ``allocation``, the node separately Q18-encoded
    if s.rate.measure != REMAINING_RATE or s.rate.formula_id != UNIT_RATE_FORMULA:
        return f"rate node is {s.rate.measure} / {s.rate.formula_id}, not {UNIT_RATE_FORMULA}"
    if tuple(s.rate.inputs) != (s.top.id, s.bottom.id):
        return f"rate node cites {s.rate.inputs!r}, not ({s.top.id!r}, {s.bottom.id!r})"
    if s.rate.params.get("zero") != "0":
        return "rate node without the zero → 0 parameter (not the remaining rate's formula)"
    allocation = _rational_param(s.rate, "allocation")
    if isinstance(allocation, str):
        return allocation
    if allocation != _exact(s.top):
        return "rate params allocation is not the numerator node's exact value"
    if s.rate.rounding_residue is not None:
        return "rate node carries a residue (not the separately encoded exact node)"
    if abs(_exact(s.rate) - s.stored) > HALF_QUANTUM:
        return "rate node's encoded value is not the stored raw quotient within h/2"
    # the numerator: the posted rec.remaining.v1 allocation node, residue present, citing only the
    # same subject's revenue_cum, posting the row's allocated_amount less that posted revenue
    if s.top.measure != "remaining_allocation" or s.top.formula_id != REMAINING_FORMULA:
        return f"numerator node is {s.top.measure} / {s.top.formula_id}, not {REMAINING_FORMULA}"
    if s.top.params.get("kind") != "allocation":
        return "numerator node is not the allocation kind of rec.remaining.v1"
    if s.top.rounding_residue is None:
        return "remaining_allocation node without a residue (adjusted branch: no criterion)"
    if tuple(s.top.inputs) != (s.revenue.id,):
        return f"numerator cites {s.top.inputs!r}, not the same subject's {s.revenue.id!r}"
    allocated = _rational_param(s.top, "allocated")
    if isinstance(allocated, str):
        return allocated
    if allocated != s.allocated:
        return "numerator params allocated is not the row's posted allocated_amount"
    if _posted(s.top, mu) != s.remaining_posted:
        return "remaining_allocation node's posted value is not the row's remaining_allocation"
    if _posted(s.top, mu) != s.allocated - _posted(s.revenue, mu):
        return "numerator formula A − C (allocated_amount less posted revenue_cum) not met"
    # the same-subject revenue input: an unadjusted rec.revenue_cum.v1 node the row links, whose
    # posted value is the row's revenue_cum and whose exact value is E = X·f encoded once
    if s.revenue.measure != "revenue_cum" or s.revenue.formula_id != REVENUE_CUM_FORMULA:
        return f"revenue node is {s.revenue.measure} / {s.revenue.formula_id}"
    if "adjusted" in s.revenue.params:
        return "revenue_cum node is the adjusted chain's node (holds / manual adjustments)"
    if _posted(s.revenue, mu) != s.revenue_posted:
        return "revenue_cum node's posted value is not the row's revenue_cum"
    if abs(_exact(s.revenue) - s.x_raw * s.f_raw) > HALF_QUANTUM:
        return "revenue_cum exact value is not X·f within h/2 (not the inception FIXED target)"
    # the quantity: the exact rec.remaining.v1 quantity node, no inputs, Q − consumed with Q the
    # original_quantity node's value, equal to the row's raw remaining_quantity column
    if s.bottom.measure != "remaining_quantity" or s.bottom.formula_id != REMAINING_FORMULA:
        return f"quantity node is {s.bottom.measure} / {s.bottom.formula_id}"
    if s.bottom.params.get("kind") != "quantity" or tuple(s.bottom.inputs):
        return "quantity node is not the input-free quantity kind of rec.remaining.v1"
    if s.bottom.rounding_residue is not None or s.bottom.currency is not None:
        return "quantity node is not a dimensionless exact node"
    total, consumed = _rational_param(s.bottom, "quantity"), _rational_param(s.bottom, "consumed")
    if isinstance(total, str):
        return total
    if isinstance(consumed, str):
        return consumed
    if s.quantity.measure != "original_quantity" or total != _exact(s.quantity):
        return "quantity params quantity is not the original_quantity node's value"
    if _exact(s.bottom) != total - consumed:
        return "quantity formula Q − consumed not met"
    if _exact(s.bottom) != s.q_raw:
        return "remaining_quantity node's value is not the row's raw remaining_quantity"
    boundary = row.columns.get("modification_boundary_no")
    if boundary != 0 or row.columns.get("last_modification_key"):
        return "modification boundary present: not the unchanged inception FIXED segment"
    if row.columns.get("obligation_kind") != "STANDARD":
        return "obligation_kind is not STANDARD"
    return None


def _assert_remaining_rate(
    spec: WorldSpec,
    worlds: tuple[InputBundle, InputBundle],
    x: ObligationVersionOut,
    y: ObligationVersionOut,
    nodes_x: Mapping[str, TraceNode],
    nodes_y: Mapping[str, TraceNode],
    factor: int,
) -> None:
    """The narrowed REMAINING-ONLY law (D-98 candidate 116 ADDENDUM 3 REVISION 4; Codex 0139;
    capsule §5 (d)–(e)) — a stated change from exact equality of at most (1 + F)·h/(2·q̂), 5.5·10^-18
    at F = 10 and q̂ = 1, with no currency term. Requirement 1: both worlds inside the positively
    whitelisted constructed input family and differing only in money amounts. Requirement 2: strict
    raw ``original_allocated_exact`` scaling, raw ``progress_ratio`` invariance within [0, 1], raw
    and decoded remaining-quantity invariance, exact node subjects / source links / branch
    correspondence. Requirement 3: the per-world anchor |N̂ − X·(1 − f)| ≤ h/2 on the active
    unchanged inception FIXED segment (the pre-recognition guard is f = 0, N = X — not an inactive
    segment; an inactive branch has no allowance here), the cross-world numerator bound
    |N̂′ − F·N̂| ≤ (1 + F)·h/2, then for a nonzero invariant q the per-world identity rate = N̂ ÷ q
    and |rate′ − F·rate| ≤ (1 + F)·h/(2·|q|); q = 0 stores 0 exactly. Requirement 4: any input
    outside the family fails a NAMED prerequisite or keeps the strict exact law; nothing inherits
    the tolerance. ``_assert_scaled_nodes`` and every other assertion stay unchanged. Codex 0214
    C2: every source is resolved by name (``_rate_sources``) and each node is checked against the
    formula the engine states for it (``_rate_identities``) before the numeric law runs."""
    where = (x.subject_key, REMAINING_RATE)
    sx, sy = x.columns.get(REMAINING_RATE), y.columns.get(REMAINING_RATE)
    off_path = (
        _world_whitelist(spec, worlds[0])
        or _world_whitelist(spec, worlds[1])
        or _worlds_invariant(worlds[0], worlds[1])
    )
    if off_path is not None:
        # requirement 4: outside the theorem the strict exact law applies, failing closed by name
        if sx is None or sy is None:
            assert sx is None and sy is None, (*where, off_path, "NULL on one world only")
            return
        assert to_fraction(sy) == factor * to_fraction(sx), (
            *where,
            f"outside the eligible family ({off_path}): exact scaling required and not met",
            str(sx),
            str(sy),
        )
        return
    sources: list[_RateSources] = []
    for row, nodes in ((x, nodes_x), (y, nodes_y)):
        resolved = _rate_sources(row, nodes)
        assert not isinstance(resolved, str), (*where, "source not found", resolved)
        identity = _rate_identities(resolved, row)
        assert identity is None, (*where, "expected formula identity not met", identity)
        sources.append(resolved)
    sx_, sy_ = sources
    # requirement 2: raw premises
    x_orig, y_orig = sx_.x_raw, sy_.x_raw
    assert y_orig == factor * x_orig, (*where, "raw X′ = F·X not met", str(x_orig), str(y_orig))
    f_x, f_y = sx_.f_raw, sy_.f_raw
    assert f_x == f_y and 0 <= f_x <= 1, (*where, "raw progress_ratio not invariant in [0, 1]")
    q_raw_x, q_raw_y = sx_.q_raw, sy_.q_raw
    assert q_raw_x == q_raw_y, (*where, "raw remaining_quantity not invariant")
    n_x, n_y = _exact(sx_.top), _exact(sy_.top)
    q_x, q_y = _exact(sx_.bottom), _exact(sy_.bottom)
    assert q_x == q_y == q_raw_x, (*where, "decoded remaining_quantity not invariant / not the raw")
    sx, sy = sx_.stored, sy_.stored
    # requirement 3: per-world raw-numerator anchor on the active unchanged inception FIXED segment
    for n, x_raw, f in ((n_x, x_orig, f_x), (n_y, y_orig, f_y)):
        assert abs(n - x_raw * (1 - f)) <= HALF_QUANTUM, (
            *where,
            "anchor |N̂ − X·(1 − f)| ≤ h/2 not met (not the active unchanged inception FIXED path)",
            str(n),
            str(x_raw),
            str(f),
        )
    assert abs(n_y - factor * n_x) <= _encoding_tolerance(factor), (
        *where,
        "cross-world numerator bound |N̂′ − F·N̂| ≤ (1 + F)·h/2 not met",
        str(n_x),
        str(n_y),
    )
    if q_x == 0:
        assert sx == 0 and sy == 0, (*where, "zero quantity stores 0")
        return
    assert sx == n_x / q_x and sy == n_y / q_y, (
        *where,
        "per-world identity rate = N̂ ÷ q not met",
    )
    assert abs(sy - factor * sx) <= _encoding_tolerance(factor) / abs(q_x), (
        *where,
        "rate bound (1 + F)·h/(2·|q|) not met",
        str(sx),
        str(sy),
    )


# R-SGN-01 / L4-3-Q-33: the column is the magnitude of the signed build-up member.
MAGNITUDE_COLUMNS: Final = frozenset({"vc_constrained_amount"})
# Trace measures without a currency: amounts (scale) and dimensionless values (unchanged). A
# currencyless measure outside both sets fails the scaling law until it is classified here.
SCALING_CURRENCYLESS_MEASURES: Final = frozenset(
    {
        "allocated_exact",
        "mod_ssp",
        "revenue_target_exact",
        # ENGINE_SPEC CV-64 rev 1.30 / ENGINE_SPEC_B 1.36 (lane ENG-T1F, T1F-89-1): the exact
        # revenue-activity chain's currencyless exact endpoints ``revenue_target_exact_<side>@<event
        # key>`` (schedule.py: ``value=fixed.exact``, ``currency=None``) are money amounts and scale
        # with the money inputs; ``revenue_exact_<side>@…``, ``revenue_exact_delta@…`` and
        # ``revenue_amount_exact`` carry the transaction currency and take the currency branch
        "revenue_target_exact_after",
        "revenue_target_exact_before",
    }
)
# Quantity nodes stage 01 and stage 09 emit since ENGINE_SPEC rev 1.24 (D-97 (8): every stored
# figure links the node that produced it) are quantities: unchanged by scaling the money inputs.
DIMENSIONLESS_MEASURES: Final = frozenset(
    {
        "allocation_weight",
        "delivered_quantity",
        "delivered_quantity_cum",
        "enforceable_end_date",
        "estimate_pin",
        "financing_gap_test",
        "original_quantity",
        "progress_ratio",
        # ENGINE_SPEC_B 1.36 (T1F-89-1): the boundary progress nodes ``progress_ratio_<side>@<event
        # key>`` of the exact revenue-activity chain are progress ratios — dimensionless
        "progress_ratio_after",
        "progress_ratio_before",
        "quantity",
        "remaining_quantity",
        "returned_quantity_cum",
        "status",
    }
)
# A mapping-rule ordinal per posted line, not a figure; its id hashes the period and the role.
ORDINAL_MEASURE: Final = "account_resolution"
SHIFT_CANDIDATES: Final = tuple(range(1, 48))
# ALG-03: the debit position splits between these roles by posted figures (the ``reclass.py``
# comparison of two posted shares; a right unconditional only because a remaining allocation
# rounds to zero).
DEBIT_ROLES: Final = frozenset({"UNBILLED_RECEIVABLE", "CONTRACT_ASSET"})
# The debit roles in ids and account codes, and the two balance measures of the split.
_UR_OR_CA: Final = re.compile(
    "UNBILLED_RECEIVABLE|CONTRACT_ASSET|unbilled_receivable|contract_asset"
)
# ALG-02 step 5: the group's debit position is split between the roles and attributed to member
# contracts and obligations by posted classifications and weights, so a rounding that moves a
# classification moves amounts between members, obligations, layers and reclass lines. The pool per
# entity and period (group level, the sum over members, the sum over obligations) is the invariant.
POOL_MEASURES: Final = frozenset(
    {
        "contract_asset",
        "contract_asset_current",
        "netting_reclass_amount",
        "unbilled_receivable",
        "unbilled_receivable_current",
    }
)
NETTING_RECLASS: Final = "NETTING_RECLASS"
_PERIOD_KEY: Final = re.compile(r"FY(\d{4})-P(\d{2})")
_ACCOUNT_RESOLUTION: Final = re.compile(r"account_resolution:[0-9a-f]{64}")
# Nodes whose values or params are date ordinals (``date.toordinal()``), read relative to inception.
ORDINAL_MEASURES: Final = frozenset({"enforceable_end_date", "financing_gap_test"})
_ORDINAL: Final = re.compile(r"(?<![\d.])7\d{5}(?:\.\d+)?(?!\d)")
_ISO_DATE: Final = re.compile(r"(?<![\dA-Za-z])(\d{4})-(\d{2})-(\d{2})")
# E-86 movement kind suffix -> the stage 12 node measure of the movement amount.
_MOVEMENT_MEASURES: Final = {
    "CREATED": "fx_layer_created",
    "CONSUMED": "fx_layer_consumed",
    "SETTLED": "fx_layer_settled",
    "REMEASURED": "fx_layer_remeasured",
}
# The thorough counter-example of 2026-09-19 at 1c2bacb (DG-PROP-02): the ratable line's allocation
# rounds to 0 in the base world and to 0.005 tenfold, so the delivered line's debit position is an
# unbilled receivable in the base world and a contract asset in the scaled one.
BHD_DEBIT_SPLIT_EXAMPLE: Final = WorldSpec(
    currency="BHD",
    contracts=(
        (
            "K-1",
            (
                LineSpec("POB-01", "DAILY", 226, 1, 1, 0, 1),
                LineSpec("POB-02", "PIT", 1, 453, 1, 0, 0),
            ),
        ),
    ),
    measures=(MeasureSpec("K-1", "POB-02", "DELIVERY", 0, 1),),
)
# The ci-profile counter-example of 2026-09-19 at fc25409 (DG-PROP-02): K-2's ratable line
# allocates 0 in the base world and 0.001 tenfold, so K-2's delivered line holds an unconditional
# right only in the base world; ALG-02 then attributes the group's debit position to the two
# contracts differently (15.649 / 0.865 against 158.183 / 6.957): the pool per period is invariant.
BHD_TWO_CONTRACT_POOL_EXAMPLE: Final = WorldSpec(
    currency="BHD",
    contracts=(
        (
            "K-1",
            (
                LineSpec("POB-01", "DAILY", 20521, 1, 1, 0, 1),
                LineSpec("POB-02", "DAILY", 1, 145413, 1, 0, 1),
            ),
        ),
        (
            "K-2",
            (
                LineSpec("POB-01", "DAILY", 1, 1, 1, 0, 1),
                LineSpec("POB-02", "PIT", 1, 6395, 1, 0, 0),
            ),
        ),
    ),
    measures=(
        MeasureSpec("K-1", "POB-01", "BILLING", 0, 4009),
        MeasureSpec("K-2", "POB-01", "BILLING", 0, 1),
        MeasureSpec("K-2", "POB-02", "DELIVERY", 0, 1),
    ),
)


# --- scaling: trace nodes ------------------------------------------------------------------------


def _exact(node: TraceNode) -> Fraction:
    value = to_fraction(node.value)
    return value if node.rounding_residue is None else value + to_fraction(node.rounding_residue)


def _posted(node: TraceNode, minor_unit: int) -> int:
    scaled_value = to_fraction(node.value) * 10**minor_unit
    assert scaled_value.denominator == 1, node.id
    return scaled_value.numerator


def _unit(node: TraceNode) -> Fraction:
    return Fraction(1, 10 ** int(node.params["minor_unit"]))


def _encoding_tolerance(factor: int) -> Fraction:
    """Both encodings round half up at ``EXACT_PLACES``: half a unit each side, one side scaled."""
    return Fraction(1 + factor, 2 * 10**EXACT_PLACES)


def _rounding_bounds(
    nodes: Mapping[str, TraceNode], factor: int
) -> tuple[dict[str, Fraction], dict[str, Fraction]]:
    """Per node: the largest drift of its exact value from F × the base exact value that the
    roundings along its derivation allow, and the largest residue it may carry.

    Exact drift: every posted input contributes its own drift plus (F + 1) of its minor units (one
    rounding on each side), an exact input its drift; a posted node without node inputs (stage 12
    layers cite their source through params) one rounding of its own. Residue: a posted node
    carries at most one minor unit of its own rounding plus its posted inputs' residues (a sum of
    posted figures whose exact value is the sum of their exact values). Formulas are sums,
    differences, scalar multiples by dimensionless ratios and clamps, so neither drift exceeds the
    sum over the inputs.
    """
    drift: dict[str, Fraction] = {}
    residue: dict[str, Fraction] = {}

    def walk(node_id: str) -> None:
        if node_id in drift:
            return
        node = nodes[node_id]
        cited = [item for item in node.inputs if isinstance(item, str)]
        drift_total = Fraction(0)
        residue_total = _unit(node) if node.rounding_residue is not None else Fraction(0)
        for item in cited:
            walk(item)
            drift_total += drift[item]
            if nodes[item].rounding_residue is not None:
                drift_total += (1 + factor) * _unit(nodes[item])
                residue_total += residue[item]
        if not cited and node.rounding_residue is not None:
            drift_total += (1 + factor) * _unit(node)
        drift[node_id] = drift_total
        residue[node_id] = residue_total

    for node_id in nodes:
        walk(node_id)
    return drift, residue


@dataclasses.dataclass(frozen=True, slots=True)
class _Group:
    """Trace nodes of one collapsed id: the ALG-03 debit pair is one group."""

    members: tuple[TraceNode, ...]
    exact: Fraction
    posted: Fraction  # Σ posted values of the posted members (0 for an exact group)
    drift: Fraction
    residue: Fraction

    @property
    def has_posted(self) -> bool:
        return any(member.rounding_residue is not None for member in self.members)


def _pool_key(node: TraceNode) -> str:
    """The comparison key of a node: its id with the debit roles collapsed, and for the ALG-02
    family the pool it belongs to (group, member or obligation level per period)."""
    measure, rest = node.id.split(":", 1)
    subject, period = rest.rsplit(":", 1)
    base = measure.split("@")[0]
    if base in POOL_MEASURES:
        pair = _UR_OR_CA.sub("ur_or_ca", base)
        if subject.startswith(f"{GROUP}@"):
            level = "group"
        elif "@" in subject:
            level = "members"
        else:
            level = "obligations"
        return f"pool:{pair}:{level}:{period}"
    if base in ("posting_target", "posting_delta") and f"/{NETTING_RECLASS}/" in subject:
        tail = subject.split(f"/{NETTING_RECLASS}/", 1)[1]  # "<role>" or "<role>/<class>"
        return f"{base}:pool/{NETTING_RECLASS}/{_UR_OR_CA.sub('UR_OR_CA', tail)}:{period}"
    if base.startswith("fx_layer_") and subject.split(":", 1)[0] in DEBIT_ROLES:
        return f"{base}:UR_OR_CA:pool:{period}"
    return _UR_OR_CA.sub("UR_OR_CA", node.id)


def _groups(book: BookOutput, factor: int) -> dict[str, _Group]:
    nodes = {node.id: node for node in book.trace.nodes}
    drift, residue = _rounding_bounds(nodes, factor)
    grouped: dict[str, list[TraceNode]] = defaultdict(list)
    for node in book.trace.nodes:
        if node.measure == ORDINAL_MEASURE:
            continue
        grouped[_pool_key(node)].append(node)
    found: dict[str, _Group] = {}
    for key, members in grouped.items():
        posted = [member for member in members if member.rounding_residue is not None]
        group_drift = sum((drift[member.id] for member in members), Fraction(0))
        if len(members) > 1 and posted:
            group_drift += (len(members) - 1) * (1 + factor) * _unit(posted[0])
        found[key] = _Group(
            members=tuple(members),
            exact=sum((_exact(member) for member in members), Fraction(0)),
            posted=sum((to_fraction(member.value) for member in posted), Fraction(0)),
            drift=group_drift,
            residue=sum((residue[member.id] for member in members), Fraction(0)),
        )
    return found


def _assert_residues_valid(book: BookOutput, factor: int) -> None:
    """Every posted node's residue lies within the roundings its derivation allows, so a posted
    error cannot hide behind a compensating residue."""
    nodes = {node.id: node for node in book.trace.nodes}
    _, residue = _rounding_bounds(nodes, factor)
    for node in book.trace.nodes:
        if node.rounding_residue is not None:
            assert abs(to_fraction(node.rounding_residue)) <= residue[node.id], node.id


def _assert_scaled_nodes(base: BookOutput, other: BookOutput, factor: int, minor_unit: int) -> None:
    tolerance = _encoding_tolerance(factor)
    unit = Fraction(1 + factor, 10**minor_unit)
    empty = _Group((), Fraction(0), Fraction(0), Fraction(0), Fraction(0))
    _assert_residues_valid(base, factor)
    _assert_residues_valid(other, factor)
    one, two = _groups(base, factor), _groups(other, factor)
    for key in sorted(set(one) | set(two)):
        x, y = one.get(key, empty), two.get(key, empty)
        allowed = tolerance * max(len(x.members), len(y.members), 1) + x.drift + y.drift
        if not x.members or not y.members:
            allowed += unit  # the missing side is zero within one rounding
        measures = {member.measure.split("@")[0] for member in x.members + y.members}
        currencies = {member.currency for member in x.members + y.members}
        scales = abs(y.exact - factor * x.exact) <= allowed
        if currencies != {None}:
            assert currencies - {None} and len(currencies) == 1, key  # one currency, every member
            assert scales, (key, str(x.exact), str(y.exact), str(allowed))
        elif measures <= SCALING_CURRENCYLESS_MEASURES:
            assert scales, (key, str(x.exact), str(y.exact), str(allowed))
        elif measures <= DIMENSIONLESS_MEASURES:
            assert y.exact == x.exact, (key, str(x.exact), str(y.exact))
        else:
            raise AssertionError(f"unclassified currencyless measures {sorted(measures)} at {key}")
        if x.has_posted or y.has_posted:
            # the posted values themselves, apart from the residues they may carry
            posted_allowed = allowed + y.residue + factor * x.residue
            assert abs(y.posted - factor * x.posted) <= posted_allowed, (
                key,
                str(x.posted),
                str(y.posted),
                str(posted_allowed),
            )
        if [m.id for m in x.members] == [m.id for m in y.members]:
            # inputs are not compared: a node summing the non-zero periods of a role cites a
            # different set of periods when a period amount rounds to zero on one side only; the
            # sums agree above within the bound the inputs' roundings allow
            for a, b in zip(x.members, y.members, strict=True):
                assert (a.measure, a.currency, a.formula_id, a.params.get("minor_unit")) == (
                    b.measure,
                    b.currency,
                    b.formula_id,
                    b.params.get("minor_unit"),
                ), a.id


# --- scaling: columns, balances, schedules, movements, intents -----------------------------------


def _assert_linked_tie(
    column: str, value: object, node: TraceNode, minor_unit: int, subject: str
) -> None:
    """A linked money column equals its node's posted value (the magnitude for R-SGN-01 columns)."""
    posted = _posted(node, minor_unit)
    if column in MAGNITUDE_COLUMNS:
        assert abs(posted) == value, (subject, column, posted, value)
    else:
        assert posted == value, (subject, column, posted, value)


def _assert_scaled_columns(
    base: Mapping[str, object],
    other: Mapping[str, object],
    factor: int,
    types: Mapping[str, str],
    *,
    links: Mapping[str, str],
    nodes_x: Mapping[str, TraceNode],
    nodes_y: Mapping[str, TraceNode],
    minor_unit: int,
    terms: int,
    subject: str,
    encoded: frozenset[str] = frozenset(),
) -> None:
    """A linked money column equals its node's posted value on both sides, so the node law (with
    the roundings along the node's derivation) bounds it; an unlinked money column is a rounded
    figure or a largest-remainder share, or a sum of ``terms`` of them, and drifts by at most
    (F + 1) minor units per term. Exact amount columns scale exactly; quantities, ratios and text
    are unchanged."""
    assert set(base) == set(other), subject
    for column, x in base.items():
        y = other[column]
        kind = types.get(column)
        if kind == "erev.money":
            if x is None:
                assert y is None, (subject, column)
                continue
            assert isinstance(x, int) and isinstance(y, int), (subject, column)
            if column in links:
                # tied to its node on both sides; the node law bounds it by its own derivation
                _assert_linked_tie(column, x, nodes_x[links[column]], minor_unit, subject)
                _assert_linked_tie(column, y, nodes_y[links[column]], minor_unit, subject)
            else:
                assert abs(y - factor * x) <= (factor + 1) * terms, (subject, column, x, y)
        elif (
            kind == "erev.exact" and column in EXACT_AMOUNT_COLUMNS | CONTRACT_EXACT_AMOUNT_COLUMNS
        ):
            if x is None:
                assert y is None, (subject, column)
            else:
                assert isinstance(x, Fraction | Decimal), (subject, column)
                if column in encoded and to_fraction(x) != 0:
                    # CV-51 / DG-KRN-EXP-03: both sides carry half a unit of 18-place encoding
                    # rounding, one of them scaled — only on the encoded producer branch of this
                    # row (``encoded_columns``; Codex 2329 / 2341, D-98 candidate 116 addenda);
                    # a zero base value keeps exact scaling (Codex 0214 F1: the parent's branch).
                    assert abs(to_fraction(y) - factor * to_fraction(x)) <= _encoding_tolerance(
                        factor
                    ), (subject, column, str(x), str(y))
                else:
                    assert to_fraction(y) == factor * to_fraction(x), (subject, column)
        elif kind == "erev.exact" and column == REMAINING_RATE:
            continue  # ``_assert_remaining_rate``: the remaining-only conditional law
        elif kind == "erev.exact":
            assert column in EXACT_DIMENSIONLESS_COLUMNS, (subject, column)
            assert y == x, (subject, column)
        elif column == "netting_reclass_role":
            # ALG-03 split at a posted tie; None where the attribution rounds to zero on one side
            assert y == x or None in (x, y) or {x, y} <= DEBIT_ROLES, (subject, column)
        else:
            assert y == x, (subject, column)


def _balance_columns(columns: Mapping[str, object]) -> dict[str, object]:
    """Balance columns with the ALG-03 debit pair summed per suffix."""
    found: dict[str, object] = {}
    for column, value in columns.items():
        key = _UR_OR_CA.sub("ur_or_ca", column)
        if isinstance(value, int) and not isinstance(value, bool) and key != column:
            held = found.get(key, 0)
            assert isinstance(held, int)
            found[key] = held + value
        else:
            found[key] = value
    return found


def _pooled_debit(balances: Sequence[BalanceOut]) -> dict[tuple[str, str], int]:
    """Σ over the member rows of a period of each ALG-02 debit column pair (per suffix)."""
    pooled: dict[tuple[str, str], int] = defaultdict(int)
    for balance in balances:
        for column, value in _balance_columns(balance.columns).items():
            if (
                column.startswith("ur_or_ca")
                and isinstance(value, int)
                and not isinstance(value, bool)
            ):
                pooled[(balance.period_key, column)] += value
    return dict(pooled)


def _assert_scaled_balances(
    base: Sequence[BalanceOut],
    other: Sequence[BalanceOut],
    factor: int,
    nodes_x: Mapping[str, TraceNode],
    nodes_y: Mapping[str, TraceNode],
    minor_unit: int,
    terms: int,
) -> None:
    """Per member row every column but the ALG-02 debit pair within (F + 1) minor units per term;
    the debit pair pooled over the member rows of a period (its attribution to members follows
    posted classifications); every link tied to its node on both sides."""
    assert len(base) == len(other)
    for bx, by in zip(base, other, strict=True):
        assert (bx.subject_key, bx.period_key) == (by.subject_key, by.period_key)
        # every link of every row ties to its own node on both sides (independent of the pool)
        for balance, nodes in ((bx, nodes_x), (by, nodes_y)):
            _assert_balance_links(balance, nodes, minor_unit)
        columns_x, columns_y = _balance_columns(bx.columns), _balance_columns(by.columns)
        assert set(columns_x) == set(columns_y), bx.subject_key
        for column, value in columns_x.items():
            if column.startswith("ur_or_ca"):
                continue
            if isinstance(value, int) and not isinstance(value, bool):
                held = columns_y[column]
                assert isinstance(held, int)
                assert abs(held - factor * value) <= (factor + 1) * terms, (bx.subject_key, column)
            else:
                assert columns_y[column] == value, (bx.subject_key, column)
    pooled_x, pooled_y = _pooled_debit(base), _pooled_debit(other)
    assert set(pooled_x) == set(pooled_y)
    for key, value in pooled_x.items():
        assert abs(pooled_y[key] - factor * value) <= (factor + 1) * terms, (
            key,
            value,
            pooled_y[key],
        )


def _assert_balance_links(
    balance: BalanceOut, nodes: Mapping[str, TraceNode], minor_unit: int
) -> None:
    """Every link of a balance row resolves to a node of that measure whose posted value is the
    row's own column: a ``<m>_txn`` column links under ``<m>`` to a transaction-currency node, a
    ``<m>_functional`` column under its full name to a functional-currency node whose measure is
    the key or its base (T-CON-09 links, ENGINE_SPEC rev 1.24 / D-97 (8); ``support.trace_linkage``;
    the generated worlds have one currency, so one minor unit serves both)."""
    links = balance_link_columns(balance.columns)
    for key, node_id in balance.trace_nodes.items():
        node = nodes[node_id]
        base = key[: -len(FUNCTIONAL)] if key.endswith(FUNCTIONAL) else key
        assert node.measure in (key, base), (balance.subject_key, balance.period_key, node_id)
        assert _posted(node, minor_unit) == balance.columns[links[key]], (
            balance.subject_key,
            balance.period_key,
            node_id,
        )


def _schedule_key(line: ScheduleLineOut) -> tuple[object, ...]:
    return (str(line.schedule_kind), line.subject_key, line.entity, str(line.line_type))


def _period_start(line: ScheduleLineOut) -> str:
    return line.period_key


def _assert_scaled_schedules(
    base: Sequence[ScheduleLineOut], other: Sequence[ScheduleLineOut], factor: int
) -> None:
    """Per schedule (kind, subject, entity, line type) the cumulative trajectories over the union
    of periods: a period without a line carries the previous cumulative (its amount is 0, which is
    why the line is absent), so absence on one side is compared as the scaled figure it stands for.
    ``cumulative_exact`` scales exactly; C_t = round(X × f_t) clamped to [0, A] with A the
    largest-remainder share (DG-KRN-MONEY-03): half a minor unit of rounding plus one of clamping,
    each side; a period amount is a difference of two."""
    lines_x: dict[tuple[object, ...], dict[str, ScheduleLineOut]] = defaultdict(dict)
    lines_y: dict[tuple[object, ...], dict[str, ScheduleLineOut]] = defaultdict(dict)
    for line in base:
        assert line.period_key not in lines_x[_schedule_key(line)], line.subject_key
        lines_x[_schedule_key(line)][line.period_key] = line
    for line in other:
        assert line.period_key not in lines_y[_schedule_key(line)], line.subject_key
        lines_y[_schedule_key(line)][line.period_key] = line
    cumulative_bound = 3 * (1 + factor) // 2
    for key in sorted(set(lines_x) | set(lines_y), key=str):
        by_period_x, by_period_y = lines_x.get(key, {}), lines_y.get(key, {})
        posted_x = posted_y = 0
        for period in sorted(set(by_period_x) | set(by_period_y)):
            x, y = by_period_x.get(period), by_period_y.get(period)
            if x is not None:
                posted_x = x.cumulative_amount
            if y is not None:
                posted_y = y.cumulative_amount
            if x is not None and y is not None:
                # the exact cumulative may grow through a period whose posted amount rounds to
                # zero (no line), so it is compared where both sides emit a line
                assert y.cumulative_exact == factor * x.cumulative_exact, (key, period)
            assert abs(posted_y - factor * posted_x) <= cumulative_bound, (key, period)
            amount_x = x.amount if x is not None else 0
            amount_y = y.amount if y is not None else 0
            assert abs(amount_y - factor * amount_x) <= 3 * (1 + factor), (key, period)
            if x is not None and y is not None:
                assert (x.quantity, x.is_released_at_close, x.trace_node_id) == (
                    y.quantity,
                    y.is_released_at_close,
                    y.trace_node_id,
                ), (key, period)


def _movement_measure(kind: object) -> str:
    return _MOVEMENT_MEASURES[str(kind).rsplit("_", 1)[1]]


def _assert_scaled_movements(
    base: Sequence[FxLayerMovementOut],
    other: Sequence[FxLayerMovementOut],
    factor: int,
    nodes_x: Mapping[str, TraceNode],
    nodes_y: Mapping[str, TraceNode],
    functional_minor_unit: int,
) -> None:
    """Stage 12 layer movements: every movement's node holds its functional amount in its
    functional currency; in the generator's single-currency domain every movement is an identity
    conversion, checked per row (transaction amount = functional amount, rate 1, no rate or
    version key, no rounding); per (book, entity, kind, role pair, date, currencies, reason) the
    amount totals drift by at most (F + 1) minor units per movement (each amount is a posted
    figure of a rounded position; the FIFO split across layers may move at a posted tie, so rows
    are not aligned)."""
    totals: dict[tuple[object, ...], list[list[int]]] = defaultdict(lambda: [[0, 0], [0, 0]])
    counts: dict[tuple[object, ...], int] = defaultdict(int)
    for side, (movements, nodes) in enumerate(((base, nodes_x), (other, nodes_y))):
        for movement in movements:
            columns = movement.columns
            node = nodes[movement.trace_nodes["amount_functional"]]
            assert node.measure == _movement_measure(columns["movement_kind"]), movement.subject_key
            assert node.currency == columns["functional_currency"], movement.subject_key
            functional = int(str(columns["amount_functional"]))
            assert _posted(node, functional_minor_unit) == functional, movement.subject_key
            if columns["txn_currency"] == columns["functional_currency"]:
                # identity conversion (S12; rates.py): the transaction amount is the functional
                # amount, the rate is 1 and no rate row is cited
                txn = int(str(columns["amount_txn"]))
                assert txn == functional, (movement.subject_key, txn, functional)
                assert columns["rate"] == Fraction(1), (movement.subject_key, columns["rate"])
                assert columns["rate_key"] is None and columns["version_key"] is None, (
                    movement.subject_key
                )
            key = (
                str(columns["book_code"]),
                columns["entity"],
                str(columns["movement_kind"]),
                _UR_OR_CA.sub("UR_OR_CA", str(columns["balance_role"])),
                columns["effective_date"],
                columns["txn_currency"],
                columns["functional_currency"],
                columns["reason"],
            )
            totals[key][side][0] += int(str(columns["amount_txn"]))
            totals[key][side][1] += functional
            counts[key] += 1
    for key, ((txn_x, functional_x), (txn_y, functional_y)) in totals.items():
        bound = (factor + 1) * counts[key]
        assert abs(txn_y - factor * txn_x) <= bound, (key, txn_x, txn_y)
        assert abs(functional_y - factor * functional_x) <= bound, (key, functional_x, functional_y)


def _intent_shape(intent: PostingIntent) -> tuple[object, ...]:
    """An intent by everything but its hashed keys and amounts."""
    return (
        intent.book_code,
        intent.entity,
        intent.posting_period_key,
        intent.origin_period_key,
        intent.entry_kind,
        intent.posting_class,
        intent.subject_key,
        intent.reason_code,
        tuple(
            (
                line.side,
                line.account_role,
                line.clearing_purpose,
                line.counterparty_entity,
                line.account_code,
                line.txn_currency,
                line.functional_currency,
                tuple(sorted(line.dimensions.items())),
                line.source_event_key,
            )
            for line in intent.lines
        ),
    )


def _collapsed_intents(
    intents: Iterable[PostingIntent],
) -> dict[tuple[object, ...], dict[tuple[object, ...], tuple[int, int]]]:
    """Entries by (book, entity, period, origin, kind, class, subject, reason) and their lines by
    shape with the ALG-03 debit roles collapsed (and their account codes masked), amounts summed;
    ``NETTING_RECLASS`` entries are pooled over their subjects."""
    found: dict[tuple[object, ...], dict[tuple[object, ...], tuple[int, int]]] = {}
    for intent in intents:
        entry = (
            intent.book_code,
            intent.entity,
            intent.posting_period_key,
            intent.origin_period_key,
            intent.entry_kind,
            intent.posting_class,
            # the reclass attribution to obligations follows posted classifications: pooled
            "pool" if intent.entry_kind == NETTING_RECLASS else intent.subject_key,
            intent.reason_code,
        )
        lines = found.setdefault(entry, {})
        for line in intent.lines:
            debit_role = line.account_role in DEBIT_ROLES
            shape = (
                line.side,
                "UR_OR_CA" if debit_role else line.account_role,
                line.clearing_purpose,
                line.counterparty_entity,
                None if debit_role else line.account_code,
                line.txn_currency,
                line.functional_currency,
                tuple(sorted(line.dimensions.items())),
                line.source_event_key,
            )
            txn, functional = lines.get(shape, (0, 0))
            lines[shape] = (txn + line.amount_txn, functional + line.amount_functional)
    return found


def _assert_scaled_intents(
    base: Sequence[PostingIntent], other: Sequence[PostingIntent], factor: int, terms: int
) -> None:
    bound = 2 * (factor + 1) * terms  # a delta of two posted figures, summed over the subject
    one, two = _collapsed_intents(base), _collapsed_intents(other)
    for entry in sorted(set(one) | set(two), key=str):
        lines_x, lines_y = one.get(entry, {}), two.get(entry, {})
        for shape in sorted(set(lines_x) | set(lines_y), key=str):
            txn_x, functional_x = lines_x.get(shape, (0, 0))
            txn_y, functional_y = lines_y.get(shape, (0, 0))
            assert abs(txn_y - factor * txn_x) <= bound, (entry, shape, txn_x, txn_y)
            assert abs(functional_y - factor * functional_x) <= bound, (entry, shape)


@given(spec=world_specs(), k=st.integers(1, 3))
@example(spec=BHD_DEBIT_SPLIT_EXAMPLE, k=1)
@example(spec=BHD_TWO_CONTRACT_POOL_EXAMPLE, k=1)
def test_scaling_by_powers_of_ten(spec: WorldSpec, k: int) -> None:
    factor = 10**k
    minor_unit = spec.minor_unit
    worlds = (bundle(spec), bundle(scaled(spec, k)))
    base, other = compute(worlds[0]), compute(worlds[1])
    assert other.diagnostics == base.diagnostics
    obligation_types = loader.obligation_columns()
    contract_types = loader.contract_version_columns()
    for one, two in zip(base.books, other.books, strict=True):
        nodes_x = {node.id: node for node in one.trace.nodes}
        nodes_y = {node.id: node for node in two.trace.nodes}
        terms = max(len(one.obligation_versions), 1)
        _assert_scaled_nodes(one, two, factor, minor_unit)
        assert one.contract_version is not None and two.contract_version is not None
        assert one.contract_version.trace_nodes == two.contract_version.trace_nodes
        _assert_scaled_columns(
            one.contract_version.columns,
            two.contract_version.columns,
            factor,
            contract_types,
            links=one.contract_version.trace_nodes,
            nodes_x=nodes_x,
            nodes_y=nodes_y,
            minor_unit=minor_unit,
            terms=terms,
            subject=one.contract_version.subject_key,
            encoded=encoded_columns(one.contract_version.trace_nodes, nodes_x),
        )
        assert one.status_in_book == two.status_in_book
        assert len(one.obligation_versions) == len(two.obligation_versions)
        for x, y in zip(one.obligation_versions, two.obligation_versions, strict=True):
            assert x.subject_key == y.subject_key and x.trace_nodes == y.trace_nodes
            _assert_scaled_columns(
                x.columns,
                y.columns,
                factor,
                obligation_types,
                links=x.trace_nodes,
                nodes_x=nodes_x,
                nodes_y=nodes_y,
                minor_unit=minor_unit,
                terms=1,
                subject=x.subject_key,
                encoded=encoded_columns(x.trace_nodes, nodes_x),
            )
            _assert_remaining_rate(spec, worlds, x, y, nodes_x, nodes_y, factor)
        _assert_scaled_balances(
            one.balances, two.balances, factor, nodes_x, nodes_y, minor_unit, terms
        )
        _assert_scaled_schedules(one.schedules, two.schedules, factor)
        _assert_scaled_movements(
            one.fx_layer_movements, two.fx_layer_movements, factor, nodes_x, nodes_y, minor_unit
        )
        assert one.cost_asset_versions == two.cost_asset_versions == ()
        assert one.loss_provision_versions == two.loss_provision_versions == ()
        _assert_scaled_intents(one.posting_intents, two.posting_intents, factor, terms)


# --- one batch equals several arrivals ------------------------------------------------------------


def _non_zero(posted: Iterable[PostedAmountInput]) -> tuple[PostedAmountInput, ...]:
    return tuple(item for item in posted if item.amount_txn or item.amount_functional)


def _assert_batch_equivalent(spec: WorldSpec, **prefix_cut: object) -> None:
    full = compute(bundle(spec))
    prefix = compute(bundle(spec, **prefix_cut))  # type: ignore[arg-type]
    rest = compute(bundle(spec, posted=intent_totals.posted(prefix)))
    assert _non_zero(intent_totals.posted(prefix, rest)) == _non_zero(intent_totals.posted(full))
    for one, two in zip(full.books, rest.books, strict=True):
        # the sealed amounts change the deltas of stage 14 and nothing before it
        assert one.obligation_versions == two.obligation_versions
        assert one.balances == two.balances
        assert one.schedules == two.schedules
        assert one.contract_version == two.contract_version


@given(spec=world_specs(), cut=st.integers(0, 700))
def test_one_batch_equals_several_arrivals(spec: WorldSpec, cut: int) -> None:
    """An effective-date slice as the first batch."""
    _assert_batch_equivalent(spec, through=INCEPTION + timedelta(days=cut))


@given(spec=world_specs(), data=st.data())
def test_one_batch_equals_several_arrivals_by_record_prefix(
    spec: WorldSpec, data: st.DataObject
) -> None:
    """A record prefix as the first batch: the later batch may bring an event effective before
    events the first batch already posted (a late arrival; S08-R-08 posts it in its open period)."""
    arrivals = data.draw(st.integers(0, len(spec.measures)))
    _assert_batch_equivalent(spec, arrivals=arrivals)


def test_one_batch_equals_several_arrivals_late_backdated_control() -> None:
    """A delivery effective in March arrives first and posts revenue; a second delivery effective in
    January arrives later. The record prefix of one holds the March delivery only, so the second
    computation introduces the earlier-effective delivery over sealed intents (a late event,
    S08-R-08) and the cumulative intents still equal the single computation's."""
    spec = WorldSpec(
        currency="USD",
        contracts=(("K-1", (LineSpec("POB-01", "PIT", 120000, 100000, 2, 0, 0),)),),
        measures=(
            MeasureSpec("K-1", "POB-01", "DELIVERY", 70, 1),
            MeasureSpec("K-1", "POB-01", "DELIVERY", 10, 1),
        ),
    )
    prefix = bundle(spec, arrivals=1)
    kept = [e for e in prefix.events if e.event_type == "DELIVERY_RECORDED"]
    assert [e.effective_date for e in kept] == [INCEPTION + timedelta(days=70)]
    late = [e for e in bundle(spec).events if e.event_type == "DELIVERY_RECORDED"]
    assert min(e.effective_date for e in late) == INCEPTION + timedelta(days=10)
    assert compute(prefix).books[0].posting_intents  # the first batch posts the March revenue
    _assert_batch_equivalent(spec, arrivals=1)


# --- calendar shift -------------------------------------------------------------------------------


def _relative(text: str, inception: date) -> str:
    """Period keys and ISO dates of ``text`` relative to ``inception`` (months, day of month)."""

    def period(match: re.Match[str]) -> str:
        months = (int(match.group(1)) - inception.year) * 12 + int(match.group(2)) - inception.month
        return f"P+{months}"

    def day(match: re.Match[str]) -> str:
        year, month, dom = (int(group) for group in match.groups())
        months = (year - inception.year) * 12 + month - inception.month
        return f"D+{months}/{dom}"

    return _ISO_DATE.sub(day, _PERIOD_KEY.sub(period, text))


def _relative_node(node: TraceNode, inception: date) -> str:
    text = _relative(canonical_bytes(node).decode("utf-8"), inception)
    text = _ACCOUNT_RESOLUTION.sub("account_resolution:#", text)
    if node.measure in ORDINAL_MEASURES:
        origin = inception.toordinal()
        text = _ORDINAL.sub(lambda match: f"O+{Fraction(match.group(0)) - origin}", text)
    return text


def _relative_view(book: BookOutput, inception: date) -> tuple[str, list[str]]:
    """The book's figures with every period key and date relative to ``inception``. Entry and line
    keys hash the period key, so intents are compared by shape and amounts, sorted;
    ``account_resolution`` node ids carry a hash of the period as well, so those ids are masked and
    the trace is compared as the sorted multiset of its relabelled nodes."""
    view = {
        "contract_version": book.contract_version,
        "status_in_book": book.status_in_book,
        "obligation_versions": book.obligation_versions,
        "balances": book.balances,
        "schedules": book.schedules,
        "cost_asset_versions": book.cost_asset_versions,
        "loss_provision_versions": book.loss_provision_versions,
        "fx_layer_movements": book.fx_layer_movements,
        "proposals": book.proposals,
        "time_triggers": book.time_triggers,
        "posting_intents": sorted(
            (
                _intent_shape(intent),
                tuple((line.amount_txn, line.amount_functional) for line in intent.lines),
            )
            for intent in book.posting_intents
        ),
    }
    figures = _relative(canonical_bytes(view).decode("utf-8"), inception)
    nodes = sorted(_relative_node(node, inception) for node in book.trace.nodes)
    return figures, nodes


def _equal_day_counts(spec: WorldSpec, months: int) -> bool:
    span = span_months(spec)
    return month_lengths(INCEPTION, span) == month_lengths(add_months(INCEPTION, months), span)


@given(spec=world_specs(kinds=("DAILY", "PIT")), data=st.data())
def test_calendar_shift_with_equal_day_counts(spec: WorldSpec, data: st.DataObject) -> None:
    order = data.draw(st.permutations(SHIFT_CANDIDATES))
    months = next((m for m in order if _equal_day_counts(spec, m)), None)
    assume(months is not None)
    assert months is not None
    shifted = add_months(INCEPTION, months)
    # the calendar covers the span with equal day counts; a longer calendar meets leap years
    span = span_months(spec)
    base = compute(bundle(spec, months=span))
    other = compute(bundle(spec, inception=shifted, months=span))
    assert _relative(canonical_bytes(other.diagnostics).decode(), shifted) == _relative(
        canonical_bytes(base.diagnostics).decode(), INCEPTION
    )
    for one, two in zip(base.books, other.books, strict=True):
        assert _relative_view(two, shifted) == _relative_view(one, INCEPTION)


# --- book equivalence -----------------------------------------------------------------------------


def _values_by_id(nodes: Sequence[TraceNode]) -> dict[str, str]:
    return {node.id: node.value for node in nodes if node.measure != ORDINAL_MEASURE}


def _without_book(intents: Iterable[PostingIntent]) -> list[tuple[object, ...]]:
    """Intents by shape and amounts, sorted: the entry keys that order them hash the book code."""
    return sorted(
        (
            _intent_shape(dataclasses.replace(intent, book_code="")),
            tuple((line.amount_txn, line.amount_functional) for line in intent.lines),
        )
        for intent in intents
    )


@given(spec=world_specs())
def test_ifrs_book_with_identical_policies_equals_asc606(spec: WorldSpec) -> None:
    output = compute(bundle(spec, books=("ASC606", "IFRS15"), identical_policies=True))
    us, ifrs = output.books
    assert (us.book_code, ifrs.book_code) == ("ASC606", "IFRS15")
    assert us.obligation_versions == ifrs.obligation_versions
    assert us.balances == ifrs.balances
    assert us.schedules == ifrs.schedules
    assert us.cost_asset_versions == ifrs.cost_asset_versions
    assert us.loss_provision_versions == ifrs.loss_provision_versions
    assert us.status_in_book == ifrs.status_in_book
    assert us.proposals == ifrs.proposals and us.time_triggers == ifrs.time_triggers
    assert us.contract_version is not None and ifrs.contract_version is not None
    assert us.contract_version.trace_nodes == ifrs.contract_version.trace_nodes
    assert {k: v for k, v in us.contract_version.columns.items() if k != "book_code"} == {
        k: v for k, v in ifrs.contract_version.columns.items() if k != "book_code"
    }
    assert [
        dataclasses.replace(m, columns={**m.columns, "book_code": ""})
        for m in us.fx_layer_movements
    ] == [
        dataclasses.replace(m, columns={**m.columns, "book_code": ""})
        for m in ifrs.fx_layer_movements
    ]
    assert _without_book(us.posting_intents) == _without_book(ifrs.posting_intents)
    assert _values_by_id(us.trace.nodes) == _values_by_id(ifrs.trace.nodes)
    # the two books' diagnostics are the memoised findings once per book (S13-R-03)
    assert [d for d in output.diagnostics if d.book_code == "ASC606"] == [
        dataclasses.replace(d, book_code="ASC606")
        for d in output.diagnostics
        if d.book_code == "IFRS15"
    ]
