"""Compute-level property worlds shared by P8, P14 and the metamorphic suite (dev-guide §9.7;
BUILD_SPEC END-13, END-14; research 06 §18.3, §18.5).

A ``WorldSpec`` is plain data drawn by ``support.strategies.world_specs``: one entity whose
functional currency is the transaction currency, one or two contracts of point-in-time and
time-elapsed (``DAILY`` or ``MONTHLY_EVEN``) lines, deliveries on the point-in-time lines and
billings on any line, every amount an integer in minor units. ``bundle`` renders it as an
``InputBundle`` under the ``DEFAULT`` preset: ``CONTRACT_BOOKED`` and ``CONTRACT_ACTIVATED`` at
inception per contract, then the measure events in the spec's arrival order (their record
sequence). ``interleaved`` re-interleaves the contract streams while keeping each stream's own
order, which models a shuffled arrival of commuting events: the record sequence and the tuple
position change, the event keys do not (research 06 §18.3). ``scaled`` multiplies every amount by
10^k; a ``bundle`` built at another ``inception`` moves every date by whole months, the two
metamorphic transformations of END-14. No clock, no randomness, no database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Final

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    BookInput,
    EstimateVersionInput,
    EventInput,
    FxRateInput,
    InputBundle,
    PostedAmountInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.currencies import ISO_4217
from erev_engine.dates import add_months, month_end
from erev_engine.money import format_money
from support import bundles

__all__ = [
    "BILLING",
    "DELIVERY",
    "GROUP",
    "INCEPTION",
    "KINDS",
    "KNOWN_AT",
    "LineSpec",
    "MeasureSpec",
    "WorldSpec",
    "arrival_labels",
    "bundle",
    "interleaved",
    "month_lengths",
    "scaled",
    "span_months",
]

INCEPTION: Final = date(2026, 1, 1)
# The FX gain / loss account a two-currency world's mapping needs (JET-10a; S12-R-09).
FX_ACCOUNTS: Final = (("FX_GAIN_LOSS", None, "7200"),)
KNOWN_AT: Final = datetime(2040, 1, 1, tzinfo=UTC)
MONTHS: Final = 60  # the entity calendar: 60 monthly periods from the inception
KINDS: Final = ("DAILY", "MONTHLY_EVEN", "PIT")
DELIVERY: Final = "DELIVERY"
BILLING: Final = "BILLING"
SSP_BOOK: Final = "SSP-PROP"
GROUP: Final = "CG-PROP"
ZERO_SHA: Final = "0" * 64


@dataclass(frozen=True, slots=True)
class LineSpec:
    """One booking line: a point-in-time good or a ratable service, amounts in minor units."""

    key: str  # obligation key, unique in the contract
    kind: str  # KINDS
    price: int  # line total price, > 0
    ssp: int  # SSP point per unit, > 0
    quantity: int  # units, >= 1 (1 for a ratable line)
    start_offset: int  # months from the group inception
    term_months: int  # ratable term in whole months, >= 1; 0 for a point-in-time line


@dataclass(frozen=True, slots=True)
class MeasureSpec:
    """One measure event in arrival order: a delivery of units or a billing of an amount."""

    contract: str
    line: str
    kind: str  # DELIVERY | BILLING
    day: int  # days after the group inception (the effective date)
    amount: int  # units delivered, or the billed amount in minor units


@dataclass(frozen=True, slots=True)
class WorldSpec:
    currency: str
    contracts: tuple[tuple[str, tuple[LineSpec, ...]], ...]
    measures: tuple[MeasureSpec, ...]  # arrival order across contracts
    # contracts carrying one VARIABLE_CONSIDERATION element ``VC-1`` whose version 1 is approved
    # at the inception: its ESTIMATE_CHANGED is the contract's third event (PRP-7 ``change_vc``)
    vc: tuple[str, ...] = ()

    @property
    def minor_unit(self) -> int:
        return ISO_4217[self.currency].minor_unit


def _template(kind: str) -> TemplateInput:
    ratable = kind != "PIT"
    return TemplateInput(
        template_code=f"TPL-{kind}",
        version_key=f"TPL-{kind}@v1",
        version_no=1,
        content_sha256=ZERO_SHA,
        obligation_kind="STANDARD",
        distinctness="distinct",
        series_increment_unit=None,
        satisfaction_pattern="OVER_TIME" if ratable else "POINT_IN_TIME",
        over_time_criterion="OT_A" if ratable else "NOT_APPLICABLE",
        recognition_method="TIME_ELAPSED" if ratable else "POINT_IN_TIME",
        ratable_convention=kind if ratable else None,
        start_date_rule="LINE_START",
        end_date_rule="LINE_END",
        term_months=None,
        principal_agent="PRINCIPAL",
        warranty_type="NONE",
        licence_nature="NOT_APPLICABLE",
        sfc_assessment_required=False,
        revenue_category=None,
        disaggregation={},
        account_role_overrides={},
        stratification_label=None,
        is_excluded_from_netting_attribution=False,
        policy_values={},
        effective_from=date(2020, 1, 1),
        effective_to=None,
    )


def _product_code(contract: str, line: LineSpec) -> str:
    return f"SKU-{contract}-{line.key}"


def _entry(code: str, point: int, currency: str, minor_unit: int) -> SspEntryInput:
    return SspEntryInput(
        entry_key=f"{SSP_BOOK}@v1/{code}//-/{currency}",
        product_code=code,
        stratification="",
        region=None,
        channel=None,
        segment=None,
        deal_size_band=None,
        term_band=None,
        currency=currency,
        method="observable",
        value_basis="AMOUNT",
        unit_list_price=None,
        midpoint_discount_ratio=None,
        range_ratio=None,
        cost_basis=None,
        margin_ratio=None,
        distinctness="distinct",
        revenue_account_code=None,
        observable_point=None,
        ranges=(
            SspRangeInput(
                "NONE", None, None, Decimal(format_money(point, minor_unit)), None, None, None
            ),
        ),
    )


def _line_dates(line: LineSpec, inception: date) -> tuple[date, date]:
    start = add_months(inception, line.start_offset)
    if line.kind == "PIT":
        return start, start
    return start, add_months(start, line.term_months) - timedelta(days=1)


def _measure_payload(
    spec: MeasureSpec, minor_unit: int, on: date, ordinal: int
) -> tuple[str, dict[str, object]]:
    """The event payload; a billing's invoice and line ids are natural keys of the contract stream
    (``ordinal`` counts the contract's own measures), so an interleaving of the streams changes
    neither payload nor event key, only the record sequence (research 06 §18.3)."""
    if spec.kind == DELIVERY:
        delivery: dict[str, object] = {
            "obligation_key": spec.line,
            "quantity": Decimal(spec.amount),
            "trigger": "DELIVERY",
        }
        return "DELIVERY_RECORDED", delivery
    invoice = f"INV-{spec.contract}-{ordinal:03d}"
    billing: dict[str, object] = {
        "invoice_number": invoice,
        "line_external_id": f"{invoice}-1",
        "obligation_key": spec.line,
        "amount": Decimal(format_money(spec.amount, minor_unit)),
        "issue_date": on,
    }
    return "BILLING_RECORDED", billing


def bundle(
    spec: WorldSpec,
    *,
    inception: date = INCEPTION,
    books: Sequence[str] = ("ASC606",),
    identical_policies: bool = False,
    posted: Iterable[PostedAmountInput] = (),
    through: date | None = None,
    arrivals: int | None = None,
    months: int = MONTHS,
    period_states: Mapping[str, str] | None = None,
    functional_currency: str | None = None,
    fx_rates: Sequence[FxRateInput] = (),
    trigger: str = "COMMAND",
    policies: Mapping[str, str] | None = None,
    estimate_versions: Sequence[EstimateVersionInput] = (),
) -> InputBundle:
    """The ``InputBundle`` of ``spec``.

    ``books`` names the framework books; with ``identical_policies`` every book takes the ASC606
    resolved policies and mapping (END-14 book equivalence). ``through`` keeps only the measure
    events effective on or before it (an effective-date slice); ``arrivals`` keeps only the first
    ``arrivals`` measures in arrival order (a record prefix, which may exclude an earlier-effective
    event that arrives later); the event keys of the kept events are those of the full stream.
    ``posted`` seals earlier intents (RCP-05). ``months`` is the length of the entity calendar
    from ``inception`` (the CV-13 horizon is its last period). ``period_states`` maps period keys
    to an E-04 state other than ``open`` for every book (a locked period for P11; PRP-6).
    ``functional_currency`` (default: the transaction currency) is the entity's functional
    currency; when it differs, ``fx_rates`` are the published rate rows (base = transaction, quote
    = functional; S12-R-01) and every book's mapping gains the ``FX_GAIN_LOSS`` account (JET-10a).
    ``trigger`` is the E-87 computation trigger (``FX_REPUBLISH`` after a rate publication).
    ``policies`` overrides resolved policy values by code in every scope (POL-161 / POL-162 for the
    machine's FX rule; PRP-7). ``estimate_versions`` are the APPROVED estimate versions the events
    reference; for every contract in ``spec.vc`` version 1's ``ESTIMATE_CHANGED`` is emitted at the
    inception as the contract's third event (``stream_base``), so its measures are EV-(n+3).
    """
    minor_unit = spec.minor_unit
    functional = functional_currency or spec.currency
    if set(spec.vc) - {contract for contract, _ in spec.contracts}:
        raise ValueError("spec.vc names a contract outside spec.contracts")
    calendar = bundles.entity(
        functional_currency=functional,
        start=inception,
        months=months,
        books=books,
        states=period_states,
    )
    primary = bundles.book("ASC606", entity=calendar)
    if functional != spec.currency:
        primary = dataclasses.replace(
            primary, account_mapping=bundles.account_mapping(extra=FX_ACCOUNTS)
        )
    book_inputs: list[BookInput] = []
    for code in books:
        if code == "ASC606":
            book_inputs.append(primary)
        elif identical_policies:
            book_inputs.append(
                BookInput(
                    code, False, primary.entity_codes, primary.policies, primary.account_mapping
                )
            )
        else:
            other = bundles.book(code, entity=calendar)
            if functional != spec.currency:
                other = dataclasses.replace(other, account_mapping=primary.account_mapping)
            book_inputs.append(other)
    if policies:
        book_inputs = [
            dataclasses.replace(
                book,
                policies=tuple(
                    dataclasses.replace(policy, value=policies[policy.code])
                    if policy.code in policies
                    else policy
                    for policy in book.policies
                ),
            )
            for book in book_inputs
        ]
    headers = tuple(
        bundles.contract(contract, currency=spec.currency, inception=inception)
        for contract, _ in spec.contracts
    )
    products = []
    entries = []
    events: list[EventInput] = []
    record_seq = 0
    for contract, lines in spec.contracts:
        booking = []
        for line in lines:
            code = _product_code(contract, line)
            products.append(bundles.product(code, template_code=f"TPL-{line.kind}", family=None))
            entries.append(_entry(code, line.ssp, spec.currency, minor_unit))
            start, end = _line_dates(line, inception)
            booking.append(
                bundles.booking_line(
                    line.key,
                    product_code=code,
                    quantity=str(line.quantity),
                    total_price=format_money(line.price, minor_unit),
                    start=start,
                    end=end,
                )
            )
        record_seq += 1
        events.append(
            bundles.event(
                contract,
                1,
                "CONTRACT_BOOKED",
                inception,
                {"lines": booking},
                record_seq=record_seq,
                obligation_keys=[line.key for line in lines],
            )
        )
        record_seq += 1
        events.append(
            bundles.event(
                contract,
                2,
                "CONTRACT_ACTIVATED",
                inception,
                {"checklist": {}},
                record_seq=record_seq,
            )
        )
        if contract in spec.vc:
            record_seq += 1
            events.append(
                bundles.event(
                    contract,
                    3,
                    "ESTIMATE_CHANGED",
                    inception,
                    {"estimate_version_id": f"{contract}/{bundles.VC_ELEMENT}@v1"},
                    record_seq=record_seq,
                )
            )
    heads = {contract: stream_base(spec, contract) for contract, _ in spec.contracts}
    for index, measure in enumerate(spec.measures):
        on = inception + timedelta(days=measure.day)
        heads[measure.contract] += 1
        record_seq += 1
        if through is not None and on > through:
            continue
        if arrivals is not None and index >= arrivals:
            continue
        event_type, payload = _measure_payload(
            measure, minor_unit, on, heads[measure.contract] - stream_base(spec, measure.contract)
        )
        events.append(
            bundles.event(
                measure.contract,
                heads[measure.contract],
                event_type,
                on,
                payload,
                record_seq=record_seq,
                obligation_keys=[measure.line],
            )
        )
    ordered = tuple(
        sorted(events, key=lambda event: (event.effective_date, event.record_seq, event.event_key))
    )
    version = SspVersionInput(
        ssp_book_code=SSP_BOOK,
        version_key=f"{SSP_BOOK}@v1",
        version_no=1,
        resolution_mode="EFFECTIVE_DATE",
        legacy_version_label=None,
        effective_from_date=date(2020, 1, 1),
        effective_to_date=None,
        status="APPROVED",
        approved_at=datetime(2020, 1, 1, tzinfo=UTC),
        content_sha256=ZERO_SHA,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=tuple(sorted(entries, key=lambda entry: entry.entry_key)),
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger=trigger,
        known_at=KNOWN_AT,
        tenant_preset="DEFAULT",
        currencies=bundles.currencies(spec.currency, functional),
        books=tuple(book_inputs),
        entities=(calendar,),
        group=bundles.group(headers, group_key=GROUP, products=products),
        contracts=headers,
        events=ordered,
        ssp_versions=(version,),
        pob_template_versions=tuple(_template(kind) for kind in sorted(KINDS)),
        rule_set_versions=(),
        estimate_versions=tuple(
            sorted(estimate_versions, key=lambda v: (v.estimate_key, v.version_no))
        ),
        fx_rates=tuple(
            sorted(
                fx_rates,
                key=lambda r: (
                    r.rate_type,
                    r.base_currency,
                    r.quote_currency,
                    r.effective_date,
                    r.version_key,
                ),
            )
        ),
        posted=tuple(posted),
    )


def stream_base(spec: WorldSpec, contract: str) -> int:
    """The stream number of the contract's last inception event: 2 (booking, activation) or 3 when
    the contract carries a variable-consideration element (its version-1 ``ESTIMATE_CHANGED``);
    the contract's n-th measure is EV-(n + base)."""
    return 3 if contract in spec.vc else 2


def scaled(spec: WorldSpec, k: int) -> WorldSpec:
    """``spec`` with every amount (prices, SSP points, billed amounts) multiplied by 10^k."""
    factor = 10**k
    contracts = tuple(
        (
            contract,
            tuple(
                dataclasses.replace(line, price=line.price * factor, ssp=line.ssp * factor)
                for line in lines
            ),
        )
        for contract, lines in spec.contracts
    )
    measures = tuple(
        dataclasses.replace(m, amount=m.amount * factor) if m.kind == BILLING else m
        for m in spec.measures
    )
    return dataclasses.replace(spec, contracts=contracts, measures=measures)


def arrival_labels(spec: WorldSpec) -> tuple[str, ...]:
    """The contract of each arrival position; a permutation of it is an interleaving."""
    return tuple(measure.contract for measure in spec.measures)


def interleaved(spec: WorldSpec, order: Sequence[str]) -> WorldSpec:
    """``spec`` with its measures re-interleaved: ``order`` names the contract of each arrival
    position and holds each contract as often as the spec does; each contract's own measure order
    is kept, so only commuting arrivals move (research 06 §18.3)."""
    queues = {
        contract: [m for m in spec.measures if m.contract == contract]
        for contract, _ in spec.contracts
    }
    measures = tuple(queues[contract].pop(0) for contract in order)
    if any(queue for queue in queues.values()):
        raise ValueError("order does not consume every measure")
    return dataclasses.replace(spec, measures=measures)


def span_months(spec: WorldSpec) -> int:
    """Months from the inception that the spec's lines and events can touch, one more for the
    period after the last date."""
    lines = max(
        (
            line.start_offset + max(line.term_months, 1)
            for _, lines in spec.contracts
            for line in lines
        ),
        default=1,
    )
    days = max((measure.day for measure in spec.measures), default=0)
    return max(lines, days // 28 + 2) + 1


def month_lengths(start: date, months: int) -> tuple[int, ...]:
    """Day counts of ``months`` calendar months from ``start`` (the first of a month)."""
    return tuple(
        (month_end(add_months(start, offset)) - add_months(start, offset)).days + 1
        for offset in range(months)
    )
