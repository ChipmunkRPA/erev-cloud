"""``compute``: orchestration, blocking findings, diagnostics and the Decimal context (ENGINE_SPEC
§0.3, §0.5, CV-15, CV-25, CV-41 to CV-43; ENGINE_SPEC_B S13-R-03; BUILD_SPEC END-9).

The kit world K-12 sells point-in-time kits for 1,000.00 each in US01 over 2026 and delivers them
in January. The diagnostics world keeps ``ASC606`` and ``IFRS15`` with equal policies, a range SSP
entry priced outside its bounds under POL-072 ``OBSERVABLE_POINT`` (``WARNING``) and a capitalised
cost to obtain without an EAC (``INFO``). No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
import decimal
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from typing import cast

import erev_engine
import pytest
from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import (
    BookInput,
    Diagnostic,
    EntityInput,
    EstimateVersionInput,
    EventInput,
    InputBundle,
    OutputBundle,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.errors import EngineError
from erev_engine.stages import s01_canonicalize
from erev_engine.trace import Trace, reevaluate
from support import bundles, golden_streams
from support.recognition import estimate_version

CONTRACT = "K-12"
ENTITY = bundles.ENTITY_CODE
INCEPTION = date(2026, 1, 1)
KNOWN_AT = datetime(2027, 12, 31, 23, tzinfo=UTC)
ZERO_SHA = "0" * 64


def template(code: str, **changes: object) -> TemplateInput:
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
        recognition_method="POINT_IN_TIME",
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
        effective_from=date(2020, 1, 1),
        effective_to=None,
    )
    return dataclasses.replace(base, **changes)  # type: ignore[arg-type]


def entry(
    product: str, *, point: str | None = None, bounds: tuple[str, str, str] | None = None
) -> SspEntryInput:
    low, mid, high = (None, None, None) if bounds is None else (Decimal(b) for b in bounds)
    ranges = SspRangeInput(
        "NONE", None, None, None if point is None else Decimal(point), low, mid, high
    )
    return SspEntryInput(
        entry_key=f"SSP-US@v1/{product}//-/USD",
        product_code=product,
        stratification="",
        region=None,
        channel=None,
        segment=None,
        deal_size_band=None,
        term_band=None,
        currency="USD",
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
        ranges=(ranges,),
    )


def ssp(entries: Sequence[SspEntryInput]) -> SspVersionInput:
    return SspVersionInput(
        ssp_book_code="SSP-US",
        version_key="SSP-US@v1",
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
        entries=tuple(sorted(entries, key=lambda item: item.product_code)),
    )


def book(code: str, calendar: EntityInput, replace: Mapping[str, str] | None = None) -> BookInput:
    """The DEFAULT ASC606 policy set for every book, so equal stage keys memoise (EX-13-B)."""
    changes = replace or {}
    policies = tuple(
        dataclasses.replace(policy, value=changes[policy.code])
        if policy.code in changes
        else policy
        for policy in bundles.policy_set(book_code="ASC606", entity=calendar)
    )
    return BookInput(code, code == "ASC606", (ENTITY,), policies, bundles.account_mapping())


def event(
    stream: int, kind: str, on: date, payload: Mapping[str, object], keys: Sequence[str] = ()
) -> EventInput:
    return bundles.event(CONTRACT, stream, kind, on, payload, obligation_keys=list(keys))


def world(
    events: Sequence[EventInput],
    *,
    products: Sequence[tuple[str, str, str]],
    entries: Sequence[SspEntryInput],
    books: Sequence[str] = ("ASC606",),
    replace: Mapping[str, str] | None = None,
    templates: Sequence[TemplateInput] = (),
    estimates: Sequence[EstimateVersionInput] = (),
    months: int = 12,
) -> InputBundle:
    """``products``: (code, template code, principal_agent)."""
    calendar = bundles.entity(months=months, books=books)
    header = bundles.contract(CONTRACT, inception=INCEPTION)
    catalogue = tuple(
        dataclasses.replace(
            bundles.product(code, template_code=tpl, family=None), principal_agent=agent
        )
        for code, tpl, agent in products
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=KNOWN_AT,
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=tuple(book(code, calendar, replace) for code in books),
        entities=(calendar,),
        group=bundles.group((header,), group_key=f"CG-{CONTRACT}", products=catalogue),
        contracts=(header,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(ssp(entries),),
        pob_template_versions=tuple(
            sorted((template("TPL-PIT"), *templates), key=lambda t: t.template_code)
        ),
        rule_set_versions=(),
        estimate_versions=tuple(estimates),
        fx_rates=(),
        posted=(),
    )


def kit_world(*, lines: int = 1, principal_agent: str = "PRINCIPAL") -> InputBundle:
    keys = [f"POB-{number:02d}" for number in range(1, lines + 1)]
    booking = [
        bundles.booking_line(
            key, product_code=f"KIT-{key}", quantity="1", total_price="1000.00", end=INCEPTION
        )
        for key in keys
    ]
    events = [
        event(1, "CONTRACT_BOOKED", INCEPTION, {"lines": booking}, keys),
        event(2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),
    ]
    for index, key in enumerate(keys):
        delivery = {"obligation_key": key, "quantity": Decimal("1"), "trigger": "CONTROL_TRANSFER"}
        events.append(event(3 + index, "DELIVERY_RECORDED", date(2026, 1, 20), delivery, [key]))
    return world(
        events,
        products=[(f"KIT-{key}", "TPL-PIT", principal_agent) for key in keys],
        entries=[entry(f"KIT-{key}", point="1000.00") for key in keys],
    )


def assert_reevaluates(trace: Trace) -> None:
    """Posted nodes exactly; exact nodes within 1e-12 (stage 05 exact inputs, L2-2-Q-40)."""
    recomputed = reevaluate(trace)
    for node in trace.nodes:
        if node.rounding_residue is not None:
            assert recomputed[node.id] == node.value, node.id
        else:
            gap = abs(Fraction(Decimal(recomputed[node.id])) - Fraction(Decimal(node.value)))
            assert gap <= Fraction(1, 10**12), node.id


# --- Tests ---------------------------------------------------------------------------------------


def test_version_mismatch() -> None:
    bundle = dataclasses.replace(kit_world(), engine_version="9.9.9")
    with pytest.raises(EngineError) as raised:
        compute(bundle)
    assert raised.value.code == "ENGINE_VERSION_MISMATCH"
    assert raised.value.detail == {"bundle": "9.9.9", "engine": ENGINE_VERSION}


def test_float_guard_on_entry_and_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    original = s01_canonicalize.run

    def recording(bundle: InputBundle, tb: object) -> object:
        calls.append(bundle.group.group_key)
        return original(bundle, tb)  # type: ignore[arg-type]

    monkeypatch.setattr(s01_canonicalize, "run", recording)
    value = kit_world()
    booked = value.events[0]
    floaty = dataclasses.replace(booked, payload={**booked.payload, "discount": 0.5})
    with pytest.raises(EngineError) as entered:
        compute(dataclasses.replace(value, events=(floaty, *value.events[1:])))
    assert entered.value.code == "FLOAT_DETECTED"
    assert entered.value.detail["path"].startswith("$.events[0].payload")
    assert calls == []  # no stage ran

    real = erev_engine.assemble_output

    def leaking(bundle: InputBundle, cb: object, results: object) -> OutputBundle:
        output = real(bundle, cb, results)  # type: ignore[arg-type]
        leak = Diagnostic("LEAK", "INFO", None, None, None, cast(Mapping[str, str], {"ratio": 0.5}))
        return dataclasses.replace(output, diagnostics=(leak,))

    monkeypatch.setattr(erev_engine, "assemble_output", leaking)
    with pytest.raises(EngineError) as exited:
        compute(value)
    assert exited.value.code == "FLOAT_DETECTED"
    assert exited.value.detail["path"].startswith("$.diagnostics[0].detail")
    assert calls == [f"CG-{CONTRACT}"]


def test_blocking_findings() -> None:
    # Two lines whose products were never assessed as principal or agent (S03-R-09).
    with pytest.raises(EngineError) as raised:
        compute(kit_world(lines=2, principal_agent="NOT_ASSESSED"))
    error = raised.value
    assert (error.code, error.subject_key) == ("PRINCIPAL_AGENT_NOT_ASSESSED", f"{CONTRACT}/POB-01")
    rows = json.loads(error.detail["findings"])
    assert [(row["code"], row["severity"], row["stage"], row["subject_key"], row["book_code"])
            for row in rows] == [
        ("PRINCIPAL_AGENT_NOT_ASSESSED", "ERROR", 3, f"{CONTRACT}/POB-01", "ASC606"),
        ("PRINCIPAL_AGENT_NOT_ASSESSED", "ERROR", 3, f"{CONTRACT}/POB-02", "ASC606"),
    ]  # fmt: skip
    assert rows == sorted(
        rows,
        key=lambda r: (r["stage"], r["code"], r["subject_key"] or "", r["event_key"] or "",
                       json.dumps(r["detail"], sort_keys=True)),
    )  # fmt: skip


def test_diagnostics_order() -> None:
    service = template(
        "TPL-SVC",
        satisfaction_pattern="OVER_TIME",
        over_time_criterion="OT_A",
        recognition_method="TIME_ELAPSED",
        ratable_convention="MONTHLY_EVEN",
    )
    renewal = dataclasses.replace(
        estimate_version(f"{CONTRACT}/AMORT", "RENEWAL_EXPECTATION", 1, INCEPTION),
        amortization_months=48,
        expected_total_amount=Decimal("25000.00"),
    )
    lines = [
        bundles.booking_line("POB-01", product_code="SKU-SVC", quantity="1", total_price="12000.00",
                             end=date(2026, 12, 31)),
        bundles.booking_line("POB-02", product_code="SKU-KIT", quantity="1", total_price="1000.00",
                             end=INCEPTION),
    ]  # fmt: skip
    applied = dataclasses.replace(
        event(2, "ESTIMATE_CHANGED", INCEPTION, {"estimate_version_id": renewal.version_key}),
        estimate_version_key=renewal.version_key,
    )
    commission = {"purpose": "COST_TO_OBTAIN", "amount": Decimal("4000.00"), "plan_code": "COMM-12",
                  "is_incremental": True}  # fmt: skip
    events = [
        event(1, "CONTRACT_BOOKED", INCEPTION, {"lines": lines}, ["POB-01", "POB-02"]),
        applied,
        event(3, "COST_INCURRED", INCEPTION, commission),
        event(4, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),
    ]
    value = world(
        events,
        products=[("SKU-SVC", "TPL-SVC", "PRINCIPAL"), ("SKU-KIT", "TPL-PIT", "PRINCIPAL")],
        entries=[
            entry("SKU-SVC", point="12000.00"),
            entry("SKU-KIT", bounds=("400.00", "500.00", "600.00")),
        ],
        books=("ASC606", "IFRS15"),
        replace={"ssp.outside_range_point": "OBSERVABLE_POINT"},
        templates=[service],
        estimates=[renewal],
    )
    output = compute(value)
    found = [(d.code, d.severity, d.book_code, d.subject_key) for d in output.diagnostics]
    assert {severity for _, severity, _, _ in found} == {"WARNING", "INFO"}
    # CV-43 order, each memoised finding once per book that uses the output (S13-R-03).
    warning = ("OBSERVABLE_POINT_MISSING", "WARNING")
    assert [row for row in found if row[:2] == warning] == [
        (*warning, "ASC606", f"{CONTRACT}/POB-02"),
        (*warning, "IFRS15", f"{CONTRACT}/POB-02"),
    ]
    assert {book for code, _, book, _ in found if code == "COST_NO_EAC"} == {"ASC606", "IFRS15"}
    ranks = {"ASC606": 0, "IFRS15": 1}
    stages = {"OBSERVABLE_POINT_MISSING": 5, "COST_NO_EAC": 11}
    assert found == sorted(
        found, key=lambda row: (stages[row[0]], row[0], row[3] or "", ranks[row[2] or ""])
    )
    ifrs = next(item for item in output.books if item.book_code == "IFRS15")
    assert any(node.params.get("alias_of_book") == "ASC606" for node in ifrs.trace.nodes)


def test_golden_contract2_setup_output() -> None:
    value = golden_streams.stream("Contract 2", "02").input_bundle(preset="LEGACY_PARITY")
    output = compute(value)
    assert (output.engine_version, output.input_sha256) == (ENGINE_VERSION, value.sha256())
    (book_output,) = output.books
    assert book_output.book_code == "ASC606" and book_output.contract_version is not None
    allocations = {
        version.columns["obligation_key"]: version.columns["allocated_amount"]
        for version in book_output.obligation_versions
    }
    assert allocations == {"POB #1": 47077, "POB #2": 31385, "POB #3": 11538, "VC #1": 0}  # CHK-002
    assert book_output.contract_version.columns["transaction_price"] == 90000
    assert_reevaluates(book_output.trace)
    assert compute(value).sha256() == output.sha256()  # PROP:P8 on one bundle


def test_decimal_context_is_local() -> None:
    outer = decimal.Context(prec=12, rounding=decimal.ROUND_DOWN, traps=[decimal.Inexact])
    with decimal.localcontext(outer):
        before = decimal.getcontext()
        snapshot = (before.prec, before.rounding, dict(before.traps), dict(before.flags))
        output = compute(kit_world())
        after = decimal.getcontext()
        assert after is before
        assert (after.prec, after.rounding, dict(after.traps), dict(after.flags)) == snapshot
    assert [intent.posting_period_key for intent in output.books[0].posting_intents] == [
        "FY2026-P01"
    ]
