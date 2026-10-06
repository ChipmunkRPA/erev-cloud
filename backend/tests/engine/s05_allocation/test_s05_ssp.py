"""Stage 05 SSP resolution under native policies (ENGINE_SPEC §5.3; EX-05-B; BUILD_SPEC ENA-10).

Bundles come from ``support.bundles`` with SSP books built here; stages 01 to 05 run for real. No
database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    ContractInput,
    EstimateVersionInput,
    EventInput,
    FxRateInput,
    InputBundle,
    MaterialRightInput,
    ResolvedPolicyInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.enums import BookCode
from erev_engine.errors import EngineError
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
)
from erev_engine.stages.s04_transaction_price import PricedState
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    Finding,
    ObligationState,
    PolicyResolver,
)
from erev_engine.trace import TraceBuilder, TraceNode
from support import bundles

CONTRACT = "K-01"
INCEPTION = date(2026, 1, 1)
END = date(2026, 12, 31)
ZERO = "0" * 64
BOOK = "BOOK-A"
KNOWN_AT = datetime(2026, 12, 31, 23, tzinfo=UTC)
LIKELIHOOD = f"{CONTRACT}/LIKELIHOOD-1"


def template(code: str, kind: str = "STANDARD") -> TemplateInput:
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256=ZERO,
        obligation_kind=kind,
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
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )


TEMPLATES = (
    template("TPL-MR", "MATERIAL_RIGHT"),
    template("TPL-PIT"),
    template("TPL-VC", "VC_LINE"),
)
PRODUCTS = (
    bundles.product("SKU-LIC", template_code="TPL-PIT", family=None),
    bundles.product("SKU-SVC", template_code="TPL-PIT", family=None),
    bundles.product("SKU-VC", template_code="TPL-VC", family=None),
    bundles.product("SKU-VOUCHER", template_code="TPL-MR", family=None),
)


def legacy_entry(
    version_key: str,
    product: str,
    *,
    list_price: str,
    discount: str,
    spread: str,
    observable: str | None = None,
) -> SspEntryInput:
    return SspEntryInput(
        entry_key=f"{version_key}/{product}//-/USD",
        product_code=product,
        stratification="",
        region=None,
        channel=None,
        segment=None,
        deal_size_band=None,
        term_band=None,
        currency="USD",
        method="legacy_range",
        value_basis="AMOUNT",
        unit_list_price=Decimal(list_price),
        midpoint_discount_ratio=Decimal(discount),
        range_ratio=Decimal(spread),
        cost_basis=None,
        margin_ratio=None,
        distinctness="distinct",
        revenue_account_code="4100",
        observable_point=None if observable is None else Decimal(observable),
        ranges=(),
    )


def point_entry(
    version_key: str, product: str, value: str, *, currency: str = "USD"
) -> SspEntryInput:
    return SspEntryInput(
        entry_key=f"{version_key}/{product}//-/{currency}",
        product_code=product,
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
        ranges=(SspRangeInput("NONE", None, None, Decimal(value), None, None, None),),
    )


def ssp_version(
    number: int,
    entries: Sequence[SspEntryInput],
    *,
    label: str | None = None,
    start: date | None = date(2025, 1, 1),
    end: date | None = None,
    approved: datetime = datetime(2025, 12, 1, tzinfo=UTC),
) -> SspVersionInput:
    return SspVersionInput(
        ssp_book_code=BOOK,
        version_key=f"{BOOK}@v{number}",
        version_no=number,
        resolution_mode="EFFECTIVE_DATE" if label is None else "BY_LABEL",
        legacy_version_label=label,
        effective_from_date=start,
        effective_to_date=end,
        status="APPROVED",
        approved_at=approved,
        content_sha256=ZERO,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=tuple(
            sorted(entries, key=lambda e: (e.product_code, e.stratification, e.currency))
        ),
    )


def booking_line(
    key: str, product: str, quantity: str, price: str, **members: object
) -> dict[str, object]:
    line = bundles.booking_line(
        key, product_code=product, quantity=quantity, total_price=price, start=INCEPTION, end=END
    )
    return {**line, **members}


def bundle(
    *lines: dict[str, object],
    versions: Sequence[SspVersionInput],
    overrides: Mapping[str, str] | None = None,
    rights: Sequence[MaterialRightInput] = (),
    estimates: Sequence[EstimateVersionInput] = (),
    rates: Iterable[FxRateInput] = (),
) -> InputBundle:
    calendar = bundles.entity(start=INCEPTION, months=24)
    base = bundles.book("ASC606", entity=calendar)
    values = overrides or {}
    policies = tuple(
        dataclasses.replace(policy, value=values[policy.code])
        if policy.code in values and policy.scope == "GROUP"
        else policy
        for policy in base.policies
    )
    header: ContractInput = dataclasses.replace(
        bundles.contract(CONTRACT, inception=INCEPTION), material_rights=tuple(rights)
    )
    keys = [str(line["obligation_key"]) for line in lines]
    events: list[EventInput] = [
        bundles.event(
            CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, {"lines": list(lines)}, obligation_keys=keys
        )
    ]
    for number, version in enumerate(estimates, start=2):
        payload = {"estimate_version_id": version.version_key}
        events.append(bundles.event(CONTRACT, number, "ESTIMATE_CHANGED", INCEPTION, payload))
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=KNOWN_AT,
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("EUR", "USD"),
        books=(dataclasses.replace(base, policies=policies),),
        entities=(calendar,),
        group=bundles.group((header,), products=PRODUCTS),
        contracts=(header,),
        events=tuple(events),
        ssp_versions=tuple(versions),
        pob_template_versions=TEMPLATES,
        rule_set_versions=(),
        estimate_versions=tuple(estimates),
        fx_rates=tuple(
            sorted(
                rates,
                key=lambda r: (
                    r.rate_type,
                    r.base_currency,
                    r.quote_currency,
                    r.effective_date,
                    r.version_key,
                ),
            )
        ),
        posted=(),
    )


def context(value: InputBundle) -> BookContext:
    book = value.books[0]
    return BookContext(
        book_code=BookCode(book.book_code),
        framework=BookCode(book.book_code),
        currencies=value.currencies,
        txn_currency=value.group.transaction_currency,
        entities={entity.code: entity for entity in value.entities},
        horizon={entity.code: entity.periods[-1].period_key for entity in value.entities},
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=value.trigger,
        tenant_preset=value.tenant_preset,
    )


def fold(
    value: InputBundle,
) -> tuple[BookContext, PricedState, AllocatedState, dict[str, TraceNode]]:
    """Stages 01 to 05 with one trace builder for stages 03 to 05 (§0.3)."""
    ctx = context(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, tb), tb)
    allocated = s05_allocation.run(ctx, priced, tb)
    return ctx, priced, allocated, {node.id: node for node in tb.build(root_measures={}).nodes}


def obligation(allocated: AllocatedState, key: str) -> ObligationState:
    return next(ob for ob in allocated.obligations if ob.obligation_key == key)


def ex_05_b(policy: str, observable: str | None = None) -> InputBundle:
    """EX-05-B: licence L 200, d 0.20, r 0.15 at P 120; services point 300 at P 300."""
    version = ssp_version(
        1,
        [
            legacy_entry(
                f"{BOOK}@v1",
                "SKU-LIC",
                list_price="200",
                discount="0.20",
                spread="0.15",
                observable=observable,
            ),
            point_entry(f"{BOOK}@v1", "SKU-SVC", "300"),
        ],
    )
    return bundle(
        booking_line("POB-01", "SKU-LIC", "1", "120.00"),
        booking_line("POB-02", "SKU-SVC", "1", "300.00"),
        versions=[version],
        overrides={"ssp.outside_range_point": policy},
    )


def test_chk_030_point_policies() -> None:
    expected = {"NEAREST_BOUND": 136, "LOW_POINT": 136, "MIDPOINT": 160, "HIGH_POINT": 184}
    for policy, value in expected.items():
        _, _, allocated, traced = fold(ex_05_b(policy))
        licence = obligation(allocated, "POB-01").ssp
        assert licence is not None
        assert (licence.low, licence.mid, licence.high) == (136, 160, 184)
        assert (licence.selected, licence.in_range, licence.point_policy) == (value, False, policy)
        services = obligation(allocated, "POB-02").ssp
        assert services is not None
        assert (services.selected, services.point_policy) == (300, "POINT")
        node = traced["original_ssp_selected:K-01/POB-01:-"]
        assert (node.params["low"], node.params["mid"], node.params["high"]) == (
            "136",
            "160",
            "184",
        )
        assert (node.params["policy"], node.value) == (policy, str(value))
    _, _, allocated, _ = fold(ex_05_b("OBSERVABLE_POINT", observable="150"))
    licence = obligation(allocated, "POB-01").ssp
    assert licence is not None and licence.selected == 150
    assert allocated.findings == ()
    _, _, allocated, _ = fold(ex_05_b("OBSERVABLE_POINT"))
    licence = obligation(allocated, "POB-01").ssp
    assert licence is not None and licence.selected == 136  # the nearer bound
    (warning,) = allocated.findings
    assert (warning.code, warning.severity, warning.subject_key) == (
        "OBSERVABLE_POINT_MISSING",
        "WARNING",
        "K-01/POB-01",
    )
    assert len(allocated.obligations) == 2  # a warning does not block the stage


def test_s05_r03_version_selection() -> None:
    versions = [
        ssp_version(
            1,
            [point_entry(f"{BOOK}@v1", "SKU-LIC", "100")],
            label="2023-01-01",
            start=date(2025, 1, 1),
            end=date(2025, 12, 31),
            approved=datetime(2024, 12, 1, tzinfo=UTC),
        ),
        ssp_version(2, [point_entry(f"{BOOK}@v2", "SKU-LIC", "200")], start=INCEPTION),
        ssp_version(
            3,
            [point_entry(f"{BOOK}@v3", "SKU-LIC", "300")],
            start=INCEPTION,
            approved=datetime(2027, 1, 15, tzinfo=UTC),  # approved after known_at
        ),
    ]
    line = booking_line("POB-01", "SKU-LIC", "1", "150.00", ssp_version_label="2023-01-01")
    _, _, allocated, _ = fold(bundle(line, versions=versions))
    ssp = obligation(allocated, "POB-01").ssp
    assert ssp is not None
    assert (ssp.version_key, ssp.selected) == (f"{BOOK}@v2", 200)
    named = {"ssp.version_basis": "NAMED_VERSION"}
    _, _, allocated, _ = fold(bundle(line, versions=versions, overrides=named))
    ssp = obligation(allocated, "POB-01").ssp
    assert ssp is not None
    assert (ssp.version_key, ssp.version_label, ssp.selected) == (f"{BOOK}@v1", "2023-01-01", 100)
    missing = booking_line("POB-02", "SKU-SVC", "1", "10.00")
    _, _, allocated, _ = fold(bundle(line, missing, versions=versions))
    assert allocated.obligations == ()  # an ERROR blocks the stage (CV-15)
    (finding,) = allocated.findings
    assert (finding.code, finding.severity, finding.subject_key, finding.stage) == (
        "SSP_KEY_NOT_FOUND",
        "ERROR",
        "K-01/POB-02",
        5,
    )
    assert finding.detail["product_code"] == "SKU-SVC"
    assert {"stratification", "ssp_version_label"} <= set(finding.detail)


def recorded(value: InputBundle, **by_key: str) -> InputBundle:
    """``value`` with the orchestrator's read-back rows (S05-R-03): per obligation key, written
    with ``_`` for ``-``, the key of the version recorded for the obligation's own pricing."""
    book = value.books[0]
    rows = tuple(
        ResolvedPolicyInput(
            "ssp.version_basis",
            "OBLIGATION",
            f"{CONTRACT}/{key.replace('_', '-')}",
            {"recorded": version_key},
            "O",
            version_key,
            "K",
        )
        for key, version_key in by_key.items()
    )
    policies = tuple(
        sorted((*book.policies, *rows), key=lambda p: (p.code, p.scope, p.subject_key))
    )
    return dataclasses.replace(value, books=(dataclasses.replace(book, policies=policies),))


def priced(allocated: AllocatedState) -> list[tuple[str, str, Fraction]]:
    found = []
    for ob in allocated.obligations:
        assert ob.ssp is not None
        found.append((ob.obligation_key, ob.ssp.version_key, ob.ssp.selected))
    return found


def test_s05_r03_a_recorded_version_prices_the_obligation_it_is_recorded_for() -> None:
    """S05-R-03, a recorded version (rev 1.121): the version an earlier computation priced an
    obligation from is the answer for that obligation's booking pricing, whatever the dates of
    the versions say now and whichever book S05-R-02 would select now. Version 1 ended before the
    inception, as a superseded version does once a later one is dated back; by date both lines
    take version 2. POB-01 with its record keeps version 1 and its book; POB-02, without one,
    selects by date. A recorded version the bundle does not carry resolves nothing."""
    first = ssp_version(
        1,
        [point_entry(f"{BOOK}@v1", "SKU-LIC", "100"), point_entry(f"{BOOK}@v1", "SKU-SVC", "300")],
        start=date(2025, 1, 1),
        end=date(2025, 12, 31),
        approved=datetime(2024, 12, 1, tzinfo=UTC),
    )
    second = ssp_version(
        2,
        [point_entry(f"{BOOK}@v2", "SKU-LIC", "200"), point_entry(f"{BOOK}@v2", "SKU-SVC", "400")],
        start=INCEPTION,
    )
    lines = (
        booking_line("POB-01", "SKU-LIC", "1", "150.00"),
        booking_line("POB-02", "SKU-SVC", "1", "300.00"),
    )
    by_date = bundle(*lines, versions=[first, second])
    _, _, allocated, _ = fold(by_date)
    assert priced(allocated) == [("POB-01", f"{BOOK}@v2", 200), ("POB-02", f"{BOOK}@v2", 400)]

    _, _, allocated, traced = fold(recorded(by_date, POB_01=f"{BOOK}@v1"))
    assert priced(allocated) == [("POB-01", f"{BOOK}@v1", 100), ("POB-02", f"{BOOK}@v2", 400)]
    node = traced["original_ssp_selected:K-01/POB-01:-"]
    assert (node.params["version_key"], node.params["book_code"]) == (f"{BOOK}@v1", BOOK)

    # A book of equal scope whose code sorts first wins S05-R-02 by date; the record names its own.
    rival_entries = (
        point_entry("BOOK-0@v1", "SKU-LIC", "500"),
        point_entry("BOOK-0@v1", "SKU-SVC", "600"),
    )
    rival = dataclasses.replace(
        ssp_version(1, rival_entries, start=INCEPTION),
        ssp_book_code="BOOK-0",
        version_key="BOOK-0@v1",
    )
    books = bundle(*lines, versions=[rival, second])
    _, _, allocated, _ = fold(books)
    assert priced(allocated) == [("POB-01", "BOOK-0@v1", 500), ("POB-02", "BOOK-0@v1", 600)]
    _, _, allocated, _ = fold(recorded(books, POB_01=f"{BOOK}@v2", POB_02=f"{BOOK}@v2"))
    assert priced(allocated) == [("POB-01", f"{BOOK}@v2", 200), ("POB-02", f"{BOOK}@v2", 400)]

    _, _, allocated, _ = fold(recorded(by_date, POB_01=f"{BOOK}@v9"))
    assert allocated.obligations == ()
    (finding,) = allocated.findings
    assert (finding.code, finding.subject_key, finding.detail["rule"]) == (
        "SSP_KEY_NOT_FOUND",
        "K-01/POB-01",
        "S05-R-02",
    )


def test_s05_r05_currency_conversion() -> None:
    version = ssp_version(1, [point_entry(f"{BOOK}@v1", "SKU-LIC", "100", currency="EUR")])
    line = booking_line("POB-01", "SKU-LIC", "1", "110.00")
    _, _, allocated, _ = fold(bundle(line, versions=[version]))
    (finding,) = allocated.findings
    assert (finding.code, finding.severity) == ("FX_RATE_MISSING", "ERROR")
    assert (finding.detail["base_currency"], finding.detail["quote_currency"]) == ("EUR", "USD")
    direct = FxRateInput(
        "FX-1", "FX@v1", "spot", "EUR", "USD", date(2025, 12, 31), None, Decimal("1.1")
    )
    _, _, allocated, traced = fold(bundle(line, versions=[version], rates=[direct]))
    ssp = obligation(allocated, "POB-01").ssp
    assert ssp is not None
    assert (ssp.selected, ssp.rate_key) == (110, "FX-1")
    node = traced["original_ssp_selected:K-01/POB-01:-"]
    assert [getattr(ref, "ref_type", None) for ref in node.inputs] == ["ssp_entry", "fx_rate"]
    inverse = FxRateInput("FX-2", "FX@v1", "spot", "USD", "EUR", INCEPTION, None, Decimal("0.5"))
    _, _, allocated, _ = fold(bundle(line, versions=[version], rates=[inverse]))
    ssp = obligation(allocated, "POB-01").ssp
    assert ssp is not None
    assert (ssp.selected, ssp.rate_key) == (200, "FX-2")
    required = {"ssp.currency_conversion": "CURRENCY_SPECIFIC_BOOK_REQUIRED"}
    _, _, allocated, _ = fold(bundle(line, versions=[version], rates=[direct], overrides=required))
    assert [f.code for f in allocated.findings] == ["SSP_KEY_NOT_FOUND"]


def test_s05_r06_native_band_sign_aware() -> None:
    version = ssp_version(
        1,
        [legacy_entry(f"{BOOK}@v1", "SKU-LIC", list_price="100", discount="0.10", spread="0.15")],
    )
    ctx, priced, _, _ = fold(
        bundle(booking_line("POB-01", "SKU-LIC", "5", "500.00"), versions=[version])
    )
    base = priced.pob.obligations[0].line
    raw = dataclasses.replace(base, quantity=Fraction(-5), stated_price=Fraction(-500))
    findings: list[Finding] = []
    ssp = s05_allocation.resolve_ssp(
        ctx, raw, INCEPTION, raw.stated_price, findings=findings, identified=priced.pob.identified
    )
    assert findings == []
    assert ssp is not None
    assert (ssp.low, ssp.mid, ssp.high) == (Fraction("-517.5"), -450, Fraction("-382.5"))
    assert (ssp.selected, ssp.in_range) == (-500, True)
    above = dataclasses.replace(raw, stated_price=Fraction(-300))
    ssp = s05_allocation.resolve_ssp(
        ctx, above, INCEPTION, above.stated_price, identified=priced.pob.identified
    )
    assert ssp is not None and ssp.selected == Fraction("-382.5")  # nearer bound, high = max
    point = s05_allocation.resolve_ssp(ctx, base, INCEPTION, identified=priced.pob.identified)
    assert point is not None and point.selected == 450  # price None: the midpoint (S03-R-03)
    absent = dataclasses.replace(base, product_code="SKU-SVC")
    with pytest.raises(EngineError) as raised:
        s05_allocation.resolve_ssp(ctx, absent, INCEPTION, identified=priced.pob.identified)
    assert raised.value.code == "SSP_KEY_NOT_FOUND"


def likelihood(rate: str) -> EstimateVersionInput:
    return EstimateVersionInput(
        estimate_key=LIKELIHOOD,
        estimate_kind="EXERCISE_LIKELIHOOD",
        element_code="LIKELIHOOD-1",
        method="ENTERED_AMOUNT",
        vc_element_type=None,
        allocation_target="CONTRACT",
        target_obligation_keys=(),
        obligation_key="POB-02",
        version_key=f"{LIKELIHOOD}@v1",
        version_no=1,
        status="APPROVED",
        effective_date=INCEPTION,
        scenarios=(),
        parameters={},
        unconstrained_amount=None,
        most_conservative_amount=None,
        constrained_amount=None,
        rate=Decimal(rate),
        expected_total_amount=None,
        expected_quantity=None,
        amortization_months=None,
        currency=None,
        supersedes_version_key=None,
        judgement_key=None,
        content_sha256=ZERO,
    )


def voucher(method: str) -> MaterialRightInput:
    return MaterialRightInput(
        obligation_key="POB-02",
        option_type="OTHER",
        incremental_discount_ratio=Decimal("0.30"),
        is_discount_available_without_contract=False,
        expected_purchase_amount=Decimal("50.00"),
        currency="USD",
        ssp_method=method,
        expiry_date=None,
        likelihood_estimate_key=LIKELIHOOD if method == "DISCOUNT_X_LIKELIHOOD" else None,
        is_legacy_quantity_ssp_dollars=method == "ENTERED_AMOUNT",
    )


def test_s05_r08_bypasses() -> None:
    entries = [
        point_entry(f"{BOOK}@v1", "SKU-LIC", "100"),
        legacy_entry(f"{BOOK}@v1", "SKU-VC", list_price="0", discount="0", spread="0"),
        legacy_entry(f"{BOOK}@v1", "SKU-VOUCHER", list_price="1", discount="0", spread="0.15"),
    ]
    version = ssp_version(1, entries)
    product = booking_line("POB-01", "SKU-LIC", "1", "100.00")
    vc_line = booking_line("VC-01", "SKU-VC", "1", "-10.00")
    _, _, allocated, _ = fold(bundle(product, vc_line, versions=[version]))
    vc = obligation(allocated, "VC-01")
    assert vc.is_vc_line and vc.ssp is not None
    assert (vc.ssp.selected, vc.ssp.in_range, vc.ssp.point_policy) == (0, None, "VC_LINE")
    assert vc.original_allocation.a_posted == 0
    # ENTERED_AMOUNT: Q dollar-units × list 1 = 1,000, where the range test would give 850.
    entered = booking_line("POB-02", "SKU-VOUCHER", "1000", "0.00")
    _, _, allocated, _ = fold(
        bundle(product, entered, versions=[version], rights=[voucher("ENTERED_AMOUNT")])
    )
    option = obligation(allocated, "POB-02")
    assert option.ssp is not None
    assert (option.ssp.low, option.ssp.high) == (850, 1150)
    assert (option.ssp.selected, option.ssp.in_range, option.ssp.point_policy) == (
        1000,
        None,
        "ENTERED_AMOUNT",
    )
    assert option.material_right is not None and option.material_right.option_ssp == 1000
    # DISCOUNT_X_LIKELIHOOD: 50.00 × 0.30 × 0.80 = 12.00 (EX-03-B).
    right = voucher("DISCOUNT_X_LIKELIHOOD")
    free = booking_line("POB-02", "SKU-VOUCHER", "1", "0.00")
    value = bundle(
        product, free, versions=[version], rights=[right], estimates=[likelihood("0.80")]
    )
    _, _, allocated, traced = fold(value)
    option = obligation(allocated, "POB-02")
    assert option.ssp is not None
    assert (option.ssp.selected, option.ssp.in_range, option.ssp.point_policy) == (
        12,
        None,
        "DISCOUNT_X_LIKELIHOOD",
    )
    node = traced["original_ssp_selected:K-01/POB-02:-"]
    assert [getattr(ref, "ref_type", None) for ref in node.inputs] == ["estimate_version"]
    _, _, allocated, _ = fold(
        bundle(product, free, versions=[version], rights=[right], estimates=[likelihood("1.2")])
    )
    assert [f.code for f in allocated.findings] == ["NON_FINITE_AMOUNT"]
