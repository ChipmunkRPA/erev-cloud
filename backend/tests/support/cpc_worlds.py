"""Full-compute worlds for consideration payable to a customer (ENGINE_SPEC S04-R-14 to S04-R-17;
ENGINE_SPEC_B S10-R-26; POLICIES PT-10 CHK-120, JET-14 CHK-133; D-91 C606-03).

The CHK-120 world: a distributor buys supplies at 1.00 a unit (``L1-SUPPLY``, 1,000,000 units) and
receives warrants with a grant-date fair value of 50,000.00 measured by a
``SHARE_BASED_CONSIDERATION`` element (expected related revenue 1,000,000.00). Builders vary the
deliveries, invoices, returns, concessions, promises and elements; the over-time variant is a
12-month DAILY service of 1,200,000.00. Observation helpers read the posting intents and the trace
of a ``compute`` output. No database.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import (
    BookOutput,
    ContractInput,
    EstimateVersionInput,
    EventInput,
    InputBundle,
    MappingRuleInput,
    ModificationInput,
    OutputBundle,
    PayableInput,
    ProductInput,
    ResolvedPolicyInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.trace import SourceRef, Trace, TraceNode, reevaluate
from support import bundles

WARRANT = "C-WARRANT"
ELEMENT = "SBC-WARRANT"
KEY = f"{WARRANT}/{ELEMENT}"
SUPPLY = "L1-SUPPLY"
JAN = date(2026, 1, 1)
Y1 = date(2026, 6, 30)
Y2 = date(2027, 6, 30)
D1 = date(2026, 12, 31)
D2 = date(2027, 12, 31)
ENTITY = bundles.ENTITY_CODE
SUBJECT = f"{WARRANT}@{ENTITY}"
ZERO_SHA = "0" * 64
SSP_BOOK = "SSP-MAIN"
RELEASE_BASIS = "cpc.incentive_asset_release_basis"
EQUITY_ACCOUNT = "3100"
# The JET-14 accounts the kernel chart of ``support.bundles`` lacks.
CPC_ACCOUNTS = (
    ("BILLING_CLEARING", "EQUITY", EQUITY_ACCOUNT),
    ("BILLING_CLEARING", "UNAPPLIED_CASH", "1900"),
    ("CONSIDERATION_PAYABLE", None, "2400"),
    ("CUSTOMER_INCENTIVE_ASSET", None, "1210"),
    ("DEPOSIT_LIABILITY", None, "2105"),
    ("REFUND_LIABILITY", None, "2110"),
)


def template(code: str, method: str, **changes: object) -> TemplateInput:
    base = TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256=ZERO_SHA,
        obligation_kind="STANDARD",
        distinctness="distinct",
        series_increment_unit=None,
        satisfaction_pattern="POINT_IN_TIME",
        over_time_criterion="NOT_APPLICABLE",
        recognition_method=method,
        ratable_convention=None,
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
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )
    return dataclasses.replace(base, **changes)  # type: ignore[arg-type]


UNITS = template("TPL-UNITS", "UNITS_DELIVERED")
PIT = template("TPL-PIT", "POINT_IN_TIME")
SAAS = template(
    "TPL-SAAS",
    "TIME_ELAPSED",
    satisfaction_pattern="OVER_TIME",
    over_time_criterion="OT_C",
    ratable_convention="DAILY",
)


def product(code: str, template_code: str) -> ProductInput:
    return bundles.product(code, template_code=template_code, family=None)


def ssp_book(points: Mapping[str, str], currency: str = "USD") -> SspVersionInput:
    """One APPROVED SSP version with a point entry per product."""
    entries = tuple(
        SspEntryInput(
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
            ranges=(SspRangeInput("NONE", None, None, Decimal(point), None, None, None),),
        )
        for code, point in sorted(points.items())
    )
    return SspVersionInput(
        ssp_book_code=SSP_BOOK,
        version_key=f"{SSP_BOOK}@v1",
        version_no=1,
        resolution_mode="EFFECTIVE_DATE",
        legacy_version_label=None,
        effective_from_date=date(2025, 1, 1),
        effective_to_date=None,
        status="APPROVED",
        approved_at=datetime(2025, 12, 1, tzinfo=UTC),
        content_sha256=ZERO_SHA,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=entries,
    )


def payable(
    amount: str,
    on: date = JAN,
    keys: Sequence[str] = (SUPPLY,),
    *,
    committed: str | None = None,
    share_based: bool = False,
) -> PayableInput:
    return PayableInput(
        amount=Decimal(amount),
        promise_date=on,
        related_obligation_keys=tuple(keys),
        distinct_good_fair_value=None,
        committed_purchases=None if committed is None else Decimal(committed),
        share_based=share_based,
    )


def sbc_version(
    number: int,
    on: date,
    probable: bool,
    expected: str,
    *,
    key: str = KEY,
    element: str = ELEMENT,
    fair: str = "50000.00",
    grant: str = "2026-01-01",
    obligation_key: str | None = SUPPLY,
    target_keys: Sequence[str] = (),
    currency: str = "USD",
    supersedes: str | None = None,
) -> EstimateVersionInput:
    """One APPROVED ``SHARE_BASED_CONSIDERATION`` version (04 T-CON-13)."""
    return EstimateVersionInput(
        estimate_key=key,
        estimate_kind="SHARE_BASED_CONSIDERATION",
        element_code=element,
        method="ENTERED_AMOUNT",
        vc_element_type=None,
        allocation_target="CONTRACT",
        target_obligation_keys=tuple(target_keys),
        obligation_key=obligation_key,
        version_key=f"{key}@v{number}",
        version_no=number,
        status="APPROVED",
        effective_date=on,
        scenarios=(),
        parameters={
            "grant_date": grant,
            "grant_date_fair_value": fair,
            "vesting_probable": probable,
        },
        unconstrained_amount=None,
        most_conservative_amount=None,
        constrained_amount=None,
        rate=None,
        expected_total_amount=Decimal(expected),
        expected_quantity=None,
        amortization_months=None,
        currency=currency,
        supersedes_version_key=supersedes,
        judgement_key=None,
        content_sha256=ZERO_SHA,
    )


def line(
    key: str, product_code: str, quantity: str, price: str, *, start: date = JAN, end: date = JAN
) -> dict[str, object]:
    return bundles.booking_line(
        key, product_code=product_code, quantity=quantity, total_price=price, start=start, end=end
    )


def booked(
    contract: str, lines: Sequence[Mapping[str, object]], on: date = JAN
) -> list[EventInput]:
    keys = [str(item["obligation_key"]) for item in lines]
    return [
        bundles.event(
            contract, 1, "CONTRACT_BOOKED", on, {"lines": list(lines)}, obligation_keys=keys
        ),
        bundles.event(contract, 2, "CONTRACT_ACTIVATED", on, {}),
    ]


def then(
    events: list[EventInput], kind: str, on: date, payload: Mapping[str, object], **extra: object
) -> list[EventInput]:
    """``events`` with one more event of the same contract, numbered after the last."""
    contract = events[0].contract_key
    key = payload.get("obligation_key")
    keys = [key] if isinstance(key, str) else []
    event = bundles.event(contract, len(events) + 1, kind, on, payload, obligation_keys=keys)
    if extra:
        event = dataclasses.replace(event, **extra)  # type: ignore[arg-type]
    return [*events, event]


def delivered(events: list[EventInput], key: str, on: date, quantity: str) -> list[EventInput]:
    payload = {"obligation_key": key, "quantity": Decimal(quantity), "trigger": "DELIVERY"}
    return then(events, "DELIVERY_RECORDED", on, payload)


def returned(events: list[EventInput], key: str, on: date, quantity: str) -> list[EventInput]:
    return then(
        events, "RETURN_RECORDED", on, {"obligation_key": key, "quantity": Decimal(quantity)}
    )


def invoiced(events: list[EventInput], key: str, on: date, amount: str) -> list[EventInput]:
    number = f"INV-{len(events) + 1}"
    payload = {
        "invoice_number": number,
        "line_external_id": f"{number}-1",
        "obligation_key": key,
        "amount": Decimal(amount),
        "issue_date": on,
    }
    return then(events, "BILLING_RECORDED", on, payload)


def pinned(events: list[EventInput], version: EstimateVersionInput) -> list[EventInput]:
    """An ``ESTIMATE_CHANGED`` applying ``version`` at its effective date."""
    return then(
        events,
        "ESTIMATE_CHANGED",
        version.effective_date,
        {"estimate_version_id": version.version_key},
    )


def concession(
    amount: str,
    on: date,
    reference: str = "MOD-CONCESSION-1",
    key: str = SUPPLY,
    *,
    named: bool = True,
) -> ModificationInput:
    """A price concession settled by credit or refund (JET-05c; the VC-CHK-113 / RND-CHK-003C
    shape): ``price_change_amount`` tagged and, when ``named``, a price-only line naming ``key`` so
    the delivered portion of a partially satisfied obligation receives ΔC_sat (S06-R-09); without a
    line the tagged amount goes to the satisfied (class S) obligations, the Codex fixture shape."""
    line_item = {
        "obligation_key": key,
        "action": "CHANGE",
        "product_code": "SUPPLY-UNIT",
        "quantity_delta": Decimal("0"),
        "consideration_delta": Decimal(amount),
    }
    return ModificationInput(
        modification_key=reference,
        effective_date=on,
        kind="PRICE_CHANGE",
        template_mode=None,
        status="APPROVED",
        reference=reference,
        questionnaire={"price_change_settlement": "CREDIT_OR_REFUND"},
        lines=(line_item,) if named else (),
        price_change_amount=Decimal(amount),
        noncash_consideration=None,
        consideration_payable=None,
        scope_605_35=None,
        currency="USD",
        proposed_treatments={},
        chosen_treatments={},
        treatment_summary=None,
        ssp_basis={},
        judgement_key=None,
        content_sha256=ZERO_SHA,
    )


def amended(
    events: list[EventInput],
    modification: ModificationInput,
    treatments: Mapping[str, str] | None = None,
) -> list[EventInput]:
    """The ``CONTRACT_AMENDED`` applying ``modification``; each named obligation is treated
    ``PROSPECTIVE`` unless ``treatments`` says otherwise."""
    if treatments is None:
        treatments = {str(item["obligation_key"]): "PROSPECTIVE" for item in modification.lines}
    payload = {
        "lines": [dict(item) for item in modification.lines],
        "modification_id": modification.modification_key,
        "price_change_settlement": "CREDIT_OR_REFUND",
        "ssp_basis": {},
        "treatments": dict(treatments),
    }
    return then(
        events,
        "CONTRACT_AMENDED",
        modification.effective_date,
        payload,
        modification_key=modification.modification_key,
    )


def world(
    contract: ContractInput,
    events: Sequence[EventInput],
    *,
    products: Sequence[ProductInput],
    templates: Sequence[TemplateInput],
    estimates: Sequence[EstimateVersionInput] = (),
    ssp: Sequence[SspVersionInput] = (),
    overrides: Mapping[str, str] | None = None,
    currency: str = "USD",
    months: int = 24,
    known_at: datetime | None = None,
) -> InputBundle:
    """One ASC606 book, one entity with monthly periods from January 2026, the JET-14 accounts."""
    calendar = bundles.entity(start=JAN, months=months, functional_currency=currency)
    book = bundles.book("ASC606", entity=calendar)
    rows = list(book.policies)
    for code, value in (overrides or {}).items():
        source = f"{contract.external_id}/policy_overrides/{code}"
        rows.append(
            ResolvedPolicyInput(code, "CONTRACT", contract.external_id, value, "C", source, "K")
        )
    mapping = book.account_mapping
    rules = tuple(
        sorted(
            (
                *mapping.rules,
                *(
                    MappingRuleInput(role, purpose, None, None, None, None, code, {}, 0, 0)
                    for role, purpose, code in CPC_ACCOUNTS
                ),
            ),
            key=lambda rule: (rule.account_role, rule.clearing_purpose or "", rule.account_code),
        )
    )
    book = dataclasses.replace(
        book,
        policies=tuple(sorted(rows, key=lambda p: (p.code, p.scope, p.subject_key))),
        account_mapping=dataclasses.replace(mapping, rules=rules),
    )
    last = max(event.effective_date for event in events)
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=known_at or datetime(last.year, last.month, last.day, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies(currency),
        books=(book,),
        entities=(calendar,),
        group=bundles.group((contract,), products=products),
        contracts=(contract,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=tuple(ssp),
        pob_template_versions=tuple(sorted(templates, key=lambda t: t.template_code)),
        rule_set_versions=(),
        estimate_versions=tuple(sorted(estimates, key=lambda v: (v.estimate_key, v.version_no))),
        fx_rates=(),
        posted=(),
    )


Step = tuple[str, date, str] | tuple[str, date, str, str]


def units_world(
    steps: Iterable[Step],
    versions: Sequence[EstimateVersionInput] = (),
    *,
    promises: Sequence[PayableInput] | None = None,
    extra_line: bool = False,
    currency: str = "USD",
    unit_price: str = "1",
    quantity: str = "1000000",
    overrides: Mapping[str, str] | None = None,
    modifications: Sequence[ModificationInput] = (),
    inception: date = JAN,
) -> InputBundle:
    """The CHK-120 world with the given steps: ``("D", date, units)`` delivers, ``("I", date,
    amount)`` invoices, ``("R", date, units)`` returns, ``("A", date, reference)`` applies the
    modification named; a fourth member names the obligation (default ``L1-SUPPLY``). ``promises``
    default to the share-based 50,000.00 promise on ``L1-SUPPLY``; ``extra_line`` adds the unrelated
    ``L2-OTHER`` (1,000,000 units at 1.00)."""
    if promises is None:
        promises = (payable("50000.00", inception, (SUPPLY,), share_based=True),)
    header = bundles.contract(
        WARRANT,
        inception=inception,
        currency=currency,
        consideration_payable=list(promises),
    )
    if modifications:
        header = dataclasses.replace(header, modifications=tuple(modifications))
    total = str(Decimal(unit_price) * Decimal(quantity))
    lines = [line(SUPPLY, "SUPPLY-UNIT", quantity, total, start=inception, end=inception)]
    products = [product("SUPPLY-UNIT", "TPL-UNITS")]
    points = {"SUPPLY-UNIT": unit_price}
    if extra_line:
        lines.append(
            line("L2-OTHER", "OTHER-UNIT", quantity, total, start=inception, end=inception)
        )
        products.append(product("OTHER-UNIT", "TPL-UNITS"))
        points["OTHER-UNIT"] = unit_price
    events = booked(WARRANT, lines, inception)
    for version in versions:
        events = pinned(events, version)
    by_reference = {item.modification_key: item for item in modifications}
    for step in steps:
        kind, on, amount = step[0], step[1], step[2]
        key = step[3] if len(step) > 3 else SUPPLY
        if kind == "D":
            events = delivered(events, key, on, amount)
        elif kind == "I":
            events = invoiced(events, key, on, amount)
        elif kind == "R":
            events = returned(events, key, on, amount)
        elif kind == "A":
            events = amended(events, by_reference[amount])
        else:
            raise ValueError(kind)
    return world(
        header,
        events,
        products=products,
        templates=[UNITS],
        estimates=list(versions),
        ssp=[ssp_book(points, currency)],
        overrides=overrides,
        currency=currency,
    )


def saas_world(
    invoices: Iterable[tuple[date, str]],
    versions: Sequence[EstimateVersionInput] = (),
    *,
    promises: Sequence[PayableInput] | None = None,
    overrides: Mapping[str, str] | None = None,
    start: date = JAN,
    end: date = date(2026, 12, 31),
    total: str = "1200000.00",
) -> InputBundle:
    """A DAILY service ``L1-SAAS`` of ``total`` over [``start``, ``end``] (12 months of 2026 by
    default, 1,200,000.00) with the given invoices."""
    if promises is None:
        promises = (payable("50000.00", JAN, ("L1-SAAS",), share_based=True),)
    header = bundles.contract(WARRANT, inception=JAN, consideration_payable=list(promises))
    events = booked(WARRANT, [line("L1-SAAS", "SAAS", "1", total, start=start, end=end)])
    for version in versions:
        events = pinned(events, version)
    for on, amount in invoices:
        events = invoiced(events, "L1-SAAS", on, amount)
    return world(
        header,
        events,
        products=[product("SAAS", "TPL-SAAS")],
        templates=[SAAS],
        estimates=list(versions),
        ssp=[ssp_book({"SAAS": total.split(".")[0]})],
        overrides=overrides,
    )


def with_performing_445(
    bundle: InputBundle, code: str = "US02", start: date = date(2026, 1, 4)
) -> InputBundle:
    """The bundle with every line performed by ``code``, a same-currency entity on a contiguous
    4-4-5 fiscal calendar from ``start`` (2026 and 2027: P08 ends 29 Aug 2026, P09 3 Oct, P10 31
    Oct), its resolved policies and the intercompany mappings (the Codex cutoff fixture of
    2026-09-18-b3-cutoff-public-probe.py)."""
    from datetime import timedelta

    from erev_engine.bundle import EntityInput, PeriodInput
    from erev_engine.canonical import sha256_hex

    periods: list[PeriodInput] = []
    first = start
    for year in (2026, 2027):
        for number, weeks in enumerate((4, 4, 5) * 4, 1):
            end = first + timedelta(days=7 * weeks - 1)
            periods.append(
                PeriodInput(
                    f"FY{year}-P{number:02d}", year, number, first, end, (("ASC606", "open"),)
                )
            )
            first = end + timedelta(days=1)
    assert all(
        a.end_date + timedelta(days=1) == b.start_date
        for a, b in zip(periods, periods[1:], strict=False)
    )
    performer = EntityInput(code, "USD", "America/New_York", "P445", tuple(periods))
    events = []
    for event in bundle.events:
        payload = event.payload
        if event.event_type == "CONTRACT_BOOKED":
            lines = payload["lines"]
            assert isinstance(lines, list)
            payload = {
                **payload,
                "lines": [{**item, "performing_entity_code": code} for item in lines],
            }
        events.append(
            dataclasses.replace(event, payload=payload, payload_sha256=sha256_hex(payload))
        )
    (book,) = bundle.books
    policies = {(p.code, p.scope, p.subject_key): p for p in book.policies}
    for policy in bundles.policy_set("DEFAULT", book_code="ASC606", entity=performer):
        policies.setdefault((policy.code, policy.scope, policy.subject_key), policy)
    rules = [
        *book.account_mapping.rules,
        MappingRuleInput("INTERCOMPANY_DUE_TO", None, None, None, None, None, "2800", {}, 0, 0),
        MappingRuleInput("INTERCOMPANY_DUE_FROM", None, None, None, None, None, "1800", {}, 0, 0),
    ]
    rules.sort(key=lambda r: (r.account_role, r.clearing_purpose or "", r.account_code))
    book = dataclasses.replace(
        book,
        entity_codes=(*book.entity_codes, code),
        policies=tuple(policies[k] for k in sorted(policies)),
        account_mapping=dataclasses.replace(book.account_mapping, rules=tuple(rules)),
    )
    return dataclasses.replace(
        bundle, events=tuple(events), books=(book,), entities=(*bundle.entities, performer)
    )


def dated_revenue(
    bundle: InputBundle, book: BookOutput, cutoff: date, *, exclude_kinds: Iterable[str] = ()
) -> int:
    """Σ REVENUE credits (debits negative) of the intents whose own entity's posting period ends on
    or before ``cutoff`` (each intent on its entity's calendar, never by period-key equality),
    excluding ``exclude_kinds`` entry kinds: the Codex dated-journal extraction of
    2026-09-18-b3-cutoff-dated-journal-reconciliation.json."""
    ends = {
        (entity.code, period.period_key): period.end_date
        for entity in bundle.entities
        for period in entity.periods
    }
    excluded = set(exclude_kinds)
    total = 0
    for intent in book.posting_intents:
        if intent.entry_kind in excluded:
            continue
        if ends[(intent.entity, intent.posting_period_key)] > cutoff:
            continue
        for item in intent.lines:
            if item.account_role == "REVENUE":
                total += item.amount_txn if item.side == "C" else -item.amount_txn
    return total


def balanced(book: BookOutput) -> bool:
    return all(
        sum(item.amount_txn * (1 if item.side == "D" else -1) for item in intent.lines) == 0
        and sum(item.amount_functional * (1 if item.side == "D" else -1) for item in intent.lines)
        == 0
        for intent in book.posting_intents
    )


def deposit_world(*, nonrefundable: bool) -> InputBundle:
    """T6b: point-in-time goods of 1,200.00 booked while ``NOT_A_CONTRACT`` (collectibility not
    probable), 1,200.00 received on 15 February 2026 and the goods delivered on 31 December 2026.
    With ``consideration_nonrefundable`` true stage 02 recognises the deposit as revenue at the
    delivery (606-10-25-7(a), S02-R-07); false keeps the deposit liability."""
    from erev_engine.bundle import JudgementInput

    contract = "C-DEPOSIT"
    outcome = {"consideration_nonrefundable": "true" if nonrefundable else "false"}
    header = dataclasses.replace(
        bundles.contract(contract, inception=JAN),
        judgements=(JudgementInput("J-NAC", "NOT_A_CONTRACT", contract, None, outcome),),
    )
    goods = line("L1-GOODS", "GOODS", "1", "1200.00")
    events = [
        bundles.event(
            contract, 1, "CONTRACT_BOOKED", JAN, {"lines": [goods]}, obligation_keys=["L1-GOODS"]
        ),
        bundles.event(
            contract,
            2,
            "COLLECTIBILITY_ASSESSED",
            JAN,
            {"book": "ASC606", "is_probable": False, "judgement_record_id": "J-2"},
        ),
        bundles.event(contract, 3, "CONTRACT_ACTIVATED", JAN, {"checklist": {}}),
        bundles.event(
            contract,
            4,
            "PAYMENT_RECEIVED",
            date(2026, 2, 15),
            {
                "receipt_reference": "R-4",
                "amount": Decimal("1200.00"),
                "receipt_date": date(2026, 2, 15),
            },
        ),
        bundles.event(
            contract,
            5,
            "DELIVERY_RECORDED",
            date(2026, 12, 31),
            {"obligation_key": "L1-GOODS", "quantity": Decimal("1"), "trigger": "DELIVERY"},
            obligation_keys=["L1-GOODS"],
        ),
    ]
    return world(
        header,
        events,
        products=[product("GOODS", "TPL-PIT")],
        templates=[PIT],
        ssp=[ssp_book({"GOODS": "1200"})],
    )


# --- observation ----------------------------------------------------------------------------------


def run(bundle: InputBundle) -> BookOutput:
    """``compute`` and return the one book."""
    output = compute(bundle)
    assert isinstance(output, OutputBundle)
    (book,) = output.books
    return book


def checked(bundle: InputBundle) -> BookOutput:
    """``run`` with every trace node reproduced by ``reevaluate`` (DG-KRN-EXP-04; PROP:P14)."""
    book = run(bundle)
    assert trace_mismatches(book.trace) == []
    return book


def trace_mismatches(trace: Trace) -> list[str]:
    values = reevaluate(trace)
    return [node.id for node in trace.nodes if values.get(node.id) != node.value]


def nodes(book: BookOutput) -> dict[str, TraceNode]:
    return {node.id: node for node in book.trace.nodes}


def role_net(
    book: BookOutput, role: str, purpose: str | None = None, *, credit: bool = False
) -> dict[str, int]:
    """Net posted amount of ``role`` per posting period: debit positive (``credit`` flips)."""
    out: dict[str, int] = {}
    for intent in book.posting_intents:
        for item in intent.lines:
            if item.account_role != role:
                continue
            if purpose is not None and item.clearing_purpose != purpose:
                continue
            sign = 1 if item.side == "D" else -1
            if credit:
                sign = -sign
            out[intent.posting_period_key] = (
                out.get(intent.posting_period_key, 0) + sign * item.amount_txn
            )
    return dict(sorted((k, v) for k, v in out.items() if v))


def equity_credits(book: BookOutput) -> dict[str, int]:
    """The JET-14 share-based movement per period: net Cr ``BILLING_CLEARING`` (``EQUITY``)."""
    return role_net(book, "BILLING_CLEARING", "EQUITY", credit=True)


def revenue_credits(book: BookOutput) -> dict[str, int]:
    return role_net(book, "REVENUE", credit=True)


def revenue_cum(book: BookOutput) -> int:
    assert book.contract_version is not None
    value = book.contract_version.columns["revenue_cum"]
    assert isinstance(value, int)
    return value


def balance(book: BookOutput, period_key: str, column: str) -> int:
    (row,) = [item for item in book.balances if item.period_key == period_key]
    value = row.columns[column]
    assert isinstance(value, int)
    return value


def node_values(book: BookOutput, measure: str) -> dict[str, str]:
    """``{node id: value}`` of the trace nodes of ``measure``."""
    return {node.id: node.value for node in book.trace.nodes if node.measure == measure}


def with_zeroed_input(trace: Trace, node_id: str, input_id: str) -> Trace:
    """A trace copy whose node ``node_id`` cites a zero source instead of ``input_id``."""
    found = []
    for node in trace.nodes:
        if node.id != node_id:
            found.append(node)
            continue
        inputs = tuple(
            SourceRef("source_record", f"ZEROED:{input_id}", {"value": "0"})
            if item == input_id
            else item
            for item in node.inputs
        )
        assert inputs != node.inputs, f"{node_id} does not cite {input_id}"
        found.append(dataclasses.replace(node, inputs=inputs))
    return dataclasses.replace(trace, nodes=tuple(found))


def truncated(bundle: InputBundle, cutoff: date) -> InputBundle:
    """The bundle with the events and estimate versions effective after ``cutoff`` removed."""
    return dataclasses.replace(
        bundle,
        events=tuple(e for e in bundle.events if e.effective_date <= cutoff),
        estimate_versions=tuple(v for v in bundle.estimate_versions if v.effective_date <= cutoff),
        known_at=datetime(cutoff.year, cutoff.month, cutoff.day, 23, tzinfo=UTC),
    )


def frac(minor: int, minor_unit: int = 2) -> Fraction:
    return Fraction(minor, 10**minor_unit)
