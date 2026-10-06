"""Stage 04 expected returns, implicit price concessions, sales taxes and the unconstrained view.

ENGINE_SPEC §4.3 S04-R-08, S04-R-08b, S04-R-09, S04-R-20, S04-R-21; §4.4 S04-INV-03; §4.5 EX-04-E
to EX-04-G2; POLICIES ALG-06 §2.7.5 (CHK-029, CHK-060), CHK-023, CHK-138; BUILD_SPEC ENA-7. Bundles
come from ``support.bundles``; stages 01 to 05 run for real. No database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest
import yaml
from erev_engine import ENGINE_VERSION, formulas, money
from erev_engine.bundle import (
    ContractInput,
    EstimateVersionInput,
    EventInput,
    InputBundle,
    JudgementInput,
    ProductInput,
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
from erev_engine.stages.s04_transaction_price import PricedState, UnconstrainedView, taxes
from erev_engine.stages.s10_billing_balances import reclass
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EventView,
    PolicyResolver,
    ReturnPin,
)
from erev_engine.trace import TraceBuilder, TraceNode
from support import bundles
from support.answer_keys.loader import ANSWER_KEY_ROOT
from support.recognition import book_context, event_view

GROUP = "CG-1"
K_01 = "K-01"
C_RET = "C-RET"
O_RET = f"{C_RET}/L1-PROD"
CALENDAR = date(2026, 1, 1)
TRANSFER = date(2026, 1, 10)
RETURNED = date(2026, 2, 10)
WINDOW_END = date(2026, 3, 15)
FEBRUARY_END = date(2026, 2, 28)
EXPIRED = date(2026, 3, 31)
ZERO = "0" * 64
SSP_BOOK = "SSP-MAIN"
BOTH_BOOKS = ("ASC606", "IFRS15")


def template(code: str, *, method: str = "POINT_IN_TIME") -> TemplateInput:
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256=ZERO,
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


def product(code: str, template_code: str = "TPL-PIT", **changes: object) -> ProductInput:
    return dataclasses.replace(
        bundles.product(code, template_code=template_code, family=None), **changes
    )


def estimate(
    contract: str,
    element: str,
    *,
    kind: str,
    effective: date = CALENDAR,
    method: str = "RATE",
    obligation_key: str | None = None,
    vc_type: str | None = None,
    scenarios: Sequence[tuple[str, str]] = (),
    rate: str | None = None,
    expected_total: str | None = None,
    expected_quantity: str | None = None,
    parameters: Mapping[str, object] | None = None,
    unconstrained: str | None = None,
    conservative: str | None = None,
    constrained: str | None = None,
) -> EstimateVersionInput:
    key = f"{contract}/{element}"

    def amount(value: str | None) -> Decimal | None:
        return None if value is None else Decimal(value)

    return EstimateVersionInput(
        estimate_key=key,
        estimate_kind=kind,
        element_code=element,
        method=method,
        vc_element_type=vc_type,
        allocation_target="CONTRACT",
        target_obligation_keys=(),
        obligation_key=obligation_key,
        version_key=f"{key}@v1",
        version_no=1,
        status="APPROVED",
        effective_date=effective,
        scenarios=tuple(
            {"amount": Decimal(value), "probability": Decimal(probability)}
            for value, probability in scenarios
        ),
        parameters=dict(parameters or {}),
        unconstrained_amount=amount(unconstrained),
        most_conservative_amount=amount(conservative),
        constrained_amount=amount(constrained),
        rate=amount(rate),
        expected_total_amount=amount(expected_total),
        expected_quantity=amount(expected_quantity),
        amortization_months=None,
        currency="USD",
        supersedes_version_key=None,
        judgement_key=None,
        content_sha256=ZERO,
    )


def event(
    contract: str,
    stream: int,
    kind: str,
    on: date,
    payload: Mapping[str, object],
    keys: Sequence[str] = (),
) -> EventInput:
    return bundles.event(contract, stream, kind, on, payload, obligation_keys=keys)


def changed(contract: str, stream: int, applied: EstimateVersionInput, on: date) -> EventInput:
    payload = {"estimate_version_id": applied.version_key}
    return event(contract, stream, "ESTIMATE_CHANGED", on, payload)


def entry(product_code: str, point: str) -> SspEntryInput:
    return SspEntryInput(
        entry_key=f"{SSP_BOOK}@v1/{product_code}//-/USD",
        product_code=product_code,
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
        ranges=(SspRangeInput("NONE", None, None, Decimal(point), None, None, None),),
    )


def ssp_book(*entries: SspEntryInput) -> SspVersionInput:
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
        content_sha256=ZERO,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=tuple(sorted(entries, key=lambda e: e.product_code)),
    )


def world(
    contract: ContractInput,
    events: Iterable[EventInput],
    *,
    products: Sequence[ProductInput],
    templates: Sequence[TemplateInput],
    estimates: Sequence[EstimateVersionInput] = (),
    ssp: Sequence[SspVersionInput] = (),
    books: tuple[str, ...] = ("ASC606",),
) -> InputBundle:
    calendar = bundles.entity(start=CALENDAR, months=24, books=books)
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=tuple(bundles.book(code, entity=calendar) for code in books),
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


def context(value: InputBundle, book_code: str = "ASC606") -> BookContext:
    book = next(b for b in value.books if b.book_code == book_code)
    return BookContext(
        book_code=BookCode(book_code),
        framework=BookCode(book_code),
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
    value: InputBundle, book_code: str = "ASC606"
) -> tuple[BookContext, PricedState, AllocatedState | None, dict[str, TraceNode]]:
    """Stages 01 to 05 with one trace builder for stages 03 to 05 (§0.3); stage 05 runs only when
    the bundle carries an SSP book."""
    ctx = context(value, book_code)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, tb), tb)
    allocated = s05_allocation.run(ctx, priced, tb) if value.ssp_versions else None
    return ctx, priced, allocated, {node.id: node for node in tb.build(root_measures={}).nodes}


def checkpoint(key: str, name: str) -> Mapping[str, str]:
    """The contract ``version`` block of an answer-key checkpoint (read only)."""
    path = ANSWER_KEY_ROOT / key.split("-", 1)[0].lower() / f"{key}.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    (point,) = [item for item in document["checkpoints"] if item["name"] == name]
    (contract,) = point["contracts"]
    version: Mapping[str, str] = contract["version"]
    return version


# --- S04-R-08 expected returns (EX-04-G, EX-04-G2; CHK-029, CHK-060) ----------------------------


def chk_029(*, returned: bool = False, revised: bool = False, ssp: bool = False) -> InputBundle:
    """RET-CHK-029-S3-EX22 inputs: 100 units at 100.00 sold on 10 January 2026 with E = 3."""
    first = estimate(
        C_RET,
        "RET-JAN",
        kind="RETURN_RATE",
        effective=TRANSFER,
        obligation_key="L1-PROD",
        rate="0.03",
        expected_quantity="3",
        parameters={
            "carrying_cost_per_unit": "60.00",
            "recovery_cost_per_unit": "0.00",
            "window_end_date": "2026-03-15",
        },
    )
    goods = bundles.booking_line(
        "L1-PROD",
        product_code="PROD-RET",
        quantity="100",
        total_price="10000.00",
        start=TRANSFER,
        end=TRANSFER,
    )
    events = [
        event(C_RET, 1, "CONTRACT_BOOKED", TRANSFER, {"lines": [goods]}, ["L1-PROD"]),
        event(C_RET, 2, "CONTRACT_ACTIVATED", TRANSFER, {"checklist": {}}),
        changed(C_RET, 3, first, TRANSFER),
        event(
            C_RET,
            4,
            "DELIVERY_RECORDED",
            TRANSFER,
            {"obligation_key": "L1-PROD", "quantity": Decimal("100"), "trigger": "DELIVERY"},
            ["L1-PROD"],
        ),
        event(
            C_RET,
            5,
            "BILLING_RECORDED",
            TRANSFER,
            {
                "invoice_number": "INV-RET-1",
                "line_external_id": "INV-RET-1-1",
                "obligation_key": "L1-PROD",
                "amount": Decimal("10000.00"),
                "issue_date": TRANSFER,
            },
            ["L1-PROD"],
        ),
    ]
    versions = [first]
    stream = 6
    if revised:  # CHK-060: E revised to 4 at the first period end, before any return
        second = dataclasses.replace(
            first,
            version_key=f"{C_RET}/RET-JAN@v2",
            version_no=2,
            effective_date=date(2026, 1, 31),
            expected_quantity=Decimal("4"),
            supersedes_version_key=first.version_key,
        )
        versions.append(second)
        events.append(changed(C_RET, stream, second, date(2026, 1, 31)))
        stream += 1
    if returned:
        payload = {
            "obligation_key": "L1-PROD",
            "quantity": Decimal("2"),
            "refund_amount": Decimal("200.00"),
        }
        events.append(event(C_RET, stream, "RETURN_RECORDED", RETURNED, payload, ["L1-PROD"]))
    returnable = product(
        "PROD-RET",
        "TPL-UNITS",
        policy_values={
            "returns.model": "EXPECTED_RETURNS",
            "returns.returned_units_scope": "REDUCE_CONTRACT_QUANTITY",
        },
    )
    return world(
        bundles.contract(C_RET, inception=TRANSFER),
        events,
        products=[returnable],
        templates=[template("TPL-UNITS", method="UNITS_DELIVERED")],
        estimates=versions,
        ssp=[ssp_book(entry("PROD-RET", "100"))] if ssp else (),
    )


def test_ex_04_g_expected_returns() -> None:
    ctx, priced, allocated, nodes = fold(chk_029(ssp=True))
    assert priced.findings == ()
    assert priced.returns_pending and priced.return_paths[O_RET].r == ()
    assert allocated is not None and allocated.findings == ()
    (tp,) = allocated.tp_history
    assert (tp.expected_returns.posted, tp.total.posted, tp.allocation_basis.posted) == (
        -30_000,
        970_000,
        1_000_000,
    )
    identity = tp.total.exact - tp.expected_returns.exact - tp.consideration_payable.exact
    assert tp.allocation_basis.exact == identity  # S04-INV-03
    (goods,) = allocated.obligations  # the whole basis is targeted at the returnable obligation
    assert goods.original_allocation.a_posted == 1_000_000
    version = checkpoint("RET-CHK-029-S3-EX22", "end-of-january")
    assert money.format_money(tp.expected_returns.posted, 2) == version["expected_returns_amount"]
    assert version["expected_returns_amount"] == "-300.00"  # the memo carries the member sign
    assert money.format_money(tp.total.posted, 2) == version["transaction_price"]
    memo = nodes[f"expected_returns_amount:{GROUP}:-"]
    assert (memo.value, memo.formula_id, memo.params["expected"], memo.params["unit_rates"]) == (
        "-300.00",
        "tp.returns_expected.v1",
        "3",
        "100",
    )
    assert nodes[f"transaction_price:{GROUP}:-"].value == "9700.00"
    assert nodes[f"tp_allocation_basis:{GROUP}:-"].value == "10000.00"
    path = allocated.return_paths[O_RET]
    assert (path.estimate_key, path.p_ref, path.r) == (
        f"{C_RET}/RET-JAN",
        Fraction(100),
        ((TRANSFER, Fraction(100)),),
    )
    assert path.pins == (
        ReturnPin(
            TRANSFER, f"{C_RET}/RET-JAN@v1", Fraction(3), Fraction(60), Fraction(0), WINDOW_END
        ),
    )
    assert (path.policy["returns.model"], path.policy["returns.returned_units_scope"]) == (
        "EXPECTED_RETURNS",
        "REDUCE_CONTRACT_QUANTITY",
    )
    with pytest.raises(ValueError, match="unit rate"):
        s04_transaction_price.price_at(ctx, priced.pob, TRANSFER, None)


def test_ex_04_g2_memo_on_returned_and_expected() -> None:
    rates = {O_RET: Fraction(100)}
    for revised, after_returns in ((False, (-30_000, 970_000)), (True, (-40_000, 960_000))):
        ctx, priced, _, _ = fold(chk_029(returned=True, revised=revised))
        february = s04_transaction_price.price_at(ctx, priced.pob, FEBRUARY_END, None, rates=rates)
        assert (february.expected_returns.posted, february.total.posted) == after_returns
        expired = s04_transaction_price.price_at(ctx, priced.pob, EXPIRED, None, rates=rates)
        assert (expired.expected_returns.posted, expired.total.posted) == (-20_000, 980_000)
    # CHK-029 after the two returns (Y = 2, E = 1): total = round(100 × (100 − 2 − 1)), the target.
    assert money.round_half_up(Fraction(100) * (100 - 2 - 1), 2) == 970_000
    ctx, priced, _, _ = fold(chk_029(returned=True))
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    february = s04_transaction_price.price_at(ctx, priced.pob, FEBRUARY_END, tb, rates=rates)
    memo = {node.id: node for node in tb.build(root_measures={}).nodes}[
        f"expected_returns_amount:{GROUP}:-"
    ]
    assert (memo.params["returned"], memo.params["expected"]) == ("2", "1")
    on_e_alone = -money.round_half_up(Fraction(100) * 1, 2)  # would break V1 by 200.00
    assert (on_e_alone, february.expected_returns.posted) == (-10_000, -30_000)


def test_s04_r08_return_estimate_missing() -> None:
    def returnable_world(
        *,
        judgements: Sequence[JudgementInput] = (),
        activate: bool = True,
        policy_values: Mapping[str, str] | None = None,
    ) -> InputBundle:
        goods = bundles.booking_line(
            "L1-PROD",
            product_code="PROD-RET",
            quantity="100",
            total_price="10000.00",
            start=TRANSFER,
            end=TRANSFER,
        )
        events = [event(C_RET, 1, "CONTRACT_BOOKED", TRANSFER, {"lines": [goods]}, ["L1-PROD"])]
        if activate:
            events.append(event(C_RET, 2, "CONTRACT_ACTIVATED", TRANSFER, {"checklist": {}}))
        delivery = {"obligation_key": "L1-PROD", "quantity": Decimal("100"), "trigger": "DELIVERY"}
        events.append(event(C_RET, 3, "DELIVERY_RECORDED", TRANSFER, delivery, ["L1-PROD"]))
        values = {"returns.model": "EXPECTED_RETURNS"} if policy_values is None else policy_values
        header = dataclasses.replace(
            bundles.contract(C_RET, inception=TRANSFER), judgements=tuple(judgements)
        )
        return world(
            header,
            events,
            products=[product("PROD-RET", "TPL-UNITS", policy_values=values)],
            templates=[template("TPL-UNITS", method="UNITS_DELIVERED")],
        )

    _, priced, _, _ = fold(returnable_world())
    assert [(f.code, f.severity, f.subject_key, f.stage) for f in priced.findings] == [
        ("RETURN_ESTIMATE_MISSING", "ERROR", O_RET, 4)
    ]
    assert priced.findings[0].detail["first_transfer"] == "2026-01-10"
    immaterial = JudgementInput(
        "J-RET-1", "OTHER", C_RET, None, {"obligation_key": "L1-PROD", "returns_immaterial": "true"}
    )
    assert fold(returnable_world(judgements=[immaterial]))[1].findings == ()
    assert fold(returnable_world(activate=False))[1].findings == ()  # a DRAFT contract
    default_only = fold(returnable_world(policy_values={}))[1]  # OQ-A-15: never by the default
    assert (default_only.findings, dict(default_only.return_paths)) == ((), {})


# --- S04-R-09 implicit price concession (EX-04-F; CHK-138) --------------------------------------


def concession_world(
    *, rate: str | None = None, expected_total: str | None = None, constrained: str | None = None
) -> InputBundle:
    version = estimate(
        K_01,
        "IPC-1",
        kind="IMPLICIT_PRICE_CONCESSION",
        rate=rate,
        expected_total=expected_total,
        constrained=constrained,
    )
    goods = bundles.booking_line(
        "POB-01", product_code="SKU-MED", quantity="1000", total_price="1000000.00", start=CALENDAR
    )
    events = [
        event(K_01, 1, "CONTRACT_BOOKED", CALENDAR, {"lines": [goods]}, ["POB-01"]),
        changed(K_01, 2, version, CALENDAR),
    ]
    return world(
        bundles.contract(K_01, inception=CALENDAR),
        events,
        products=[product("SKU-MED")],
        templates=[template("TPL-PIT")],
        estimates=[version],
    )


def test_ex_04_f_implicit_price_concession() -> None:
    _, priced, _, nodes = fold(concession_world(expected_total="400000.00"))
    tp = priced.tp
    assert priced.findings == ()
    assert (tp.fixed.posted, tp.vc_constrained.posted, tp.total.posted) == (
        100_000_000,
        -60_000_000,
        40_000_000,
    )
    assert tp.allocation_basis.posted == 40_000_000
    node = nodes[f"vc_constrained:{K_01}/IPC-1:-"]
    assert (node.value, node.formula_id, node.params["kappa"], node.params["basis"]) == (
        "-600000.00",
        "tp.concession_implicit.v1",
        "0.6",  # κ = (1,000,000 − 400,000) ÷ 1,000,000 = 3/5
        "EXPECTED_TOTAL_AMOUNT",
    )
    assert f"vc_constrained:{K_01}/IPC-1:-" in nodes[f"vc_constrained_amount:{GROUP}:-"].inputs
    assert [(e.estimate_key, e.amount.posted) for e in tp.elements] == [
        (f"{K_01}/IPC-1", -60_000_000)
    ]
    _, by_rate, _, _ = fold(concession_world(rate="0.60"))
    assert (by_rate.tp.vc_constrained.posted, by_rate.tp.total.posted) == (-60_000_000, 40_000_000)


def test_l7_5_implicit_price_concession_from_the_constrained_amount() -> None:
    """D-87 L6-5-Q-12 (ii): with only ``constrained_amount`` the component is −constrained and
    κ = constrained ÷ stated fixed consideration (STP1-S1-EX2); precedence ``rate``, then
    ``expected_total_amount``, then ``constrained_amount``; with none of the three CV-45 stays."""
    _, priced, _, nodes = fold(concession_world(constrained="600000.00"))
    tp = priced.tp
    assert priced.findings == ()
    assert (tp.fixed.posted, tp.vc_constrained.posted, tp.total.posted) == (
        100_000_000,
        -60_000_000,
        40_000_000,
    )
    node = nodes[f"vc_constrained:{K_01}/IPC-1:-"]
    assert (node.value, node.formula_id, node.params["kappa"], node.params["basis"]) == (
        "-600000.00",
        "tp.concession_implicit.v1",
        "0.6",  # κ = 600,000 ÷ 1,000,000
        "CONSTRAINED_AMOUNT",
    )
    formula = formulas.FORMULAS["tp.concession_implicit.v1"]
    assert formula(
        [Fraction(600_000), Fraction(1_000_000)], {**node.params, "minor_unit": "2"}
    ) == Fraction(-600_000)
    by_rate = fold(concession_world(rate="0.50", constrained="600000.00"))[1]
    assert by_rate.tp.vc_constrained.posted == -50_000_000
    by_total = fold(concession_world(expected_total="700000.00", constrained="600000.00"))[1]
    assert by_total.tp.vc_constrained.posted == -30_000_000
    with pytest.raises(ValueError, match="needs rate, expected total or constrained amount"):
        fold(concession_world())
    with pytest.raises(EngineError) as raised:
        fold(concession_world(constrained="1000000.01"))
    assert raised.value.code == "NON_FINITE_AMOUNT"
    version = estimate(K_01, "IPC-1", kind="IMPLICIT_PRICE_CONCESSION", constrained="600000.00")
    assert reclass._kappa(version, Fraction(1_000_000), K_01) == Fraction(3, 5)  # S10-R-18


# --- S04-R-20 sales taxes (EX-04-E; CHK-023) ----------------------------------------------------


def invoiced(tax: Mapping[str, object], books: tuple[str, ...]) -> InputBundle:
    goods = bundles.booking_line("POB-01", product_code="SKU-1", total_price="1000.00")
    billing = {
        "invoice_number": "INV-1",
        "line_external_id": "INV-1-1",
        "obligation_key": "POB-01",
        "amount": Decimal("1000.00"),
        "issue_date": CALENDAR,
        **tax,
    }
    events = [
        event(K_01, 1, "CONTRACT_BOOKED", CALENDAR, {"lines": [goods]}, ["POB-01"]),
        event(K_01, 2, "BILLING_RECORDED", CALENDAR, billing, ["POB-01"]),
    ]
    return world(
        bundles.contract(K_01, inception=CALENDAR),
        events,
        products=[product("SKU-1")],
        templates=[template("TPL-PIT")],
        books=books,
    )


def test_ex_04_e_sales_tax_excluded() -> None:
    _, priced, _, nodes = fold(invoiced({"tax_amount": Decimal("80.00")}, ("ASC606",)))
    assert (priced.tp.total.posted, priced.tp.sales_tax_excluded.posted) == (100_000, 8_000)
    node = nodes[f"sales_tax_excluded_amount:{GROUP}:-"]
    assert (node.value, node.formula_id, node.params["treatment"]) == (
        "80.00",
        "tp.tax_excluded.v1",
        "EXCLUDE_ALL_IN_SCOPE",
    )
    assert nodes[f"transaction_price:{GROUP}:-"].value == "1000.00"
    # IFRS15 ASSESS_EACH_TAX: every tax line is collected on behalf of the authority in 1.0
    # (S04-R-20; OQ-A-14), so a PRINCIPAL-flagged line is evidence and still excluded (L2-2-Q-9).
    for principal_or_agent in ("AGENT", "PRINCIPAL"):
        line = {
            "tax_type": "VAT",
            "amount": Decimal("80.00"),
            "principal_or_agent": principal_or_agent,
        }
        value = invoiced({"tax_lines": [line]}, BOTH_BOOKS)
        for book_code, treatment in (
            ("ASC606", "EXCLUDE_ALL_IN_SCOPE"),
            ("IFRS15", "ASSESS_EACH_TAX"),
        ):
            _, priced, _, nodes = fold(value, book_code)
            assert (priced.tp.total.posted, priced.tp.sales_tax_excluded.posted) == (100_000, 8_000)
            assert nodes[f"sales_tax_excluded_amount:{GROUP}:-"].params["treatment"] == treatment


# --- D-91 C606-05h: S04-R-20 taxes read the S10-R-07 identity from the kernel -------------------

JAN_20 = date(2026, 1, 20)
K_02 = "K-02"
K_OUT = "K-OUT"
TAX_LINE: Mapping[str, object] = {
    "invoice_number": "INV-1",
    "line_external_id": "INV-1-1",
    "obligation_key": "POB-01",
    "amount": Decimal("1000.00"),
    "tax_amount": Decimal("80.00"),
}


def _tax_payload(
    on: date, cancellable: object | None, changes: Mapping[str, object]
) -> dict[str, object]:
    """INV-1 / INV-1-1, 1,000.00 with 80.00 of tax; ``cancellable`` ``None`` leaves
    ``is_cancellable`` absent (the 04 default ``false``, 04:2649; L2-4-Q-8)."""
    payload: dict[str, object] = {**TAX_LINE, "issue_date": on, **changes}
    if cancellable is not None:
        payload["is_cancellable"] = cancellable
    return payload


def _tax_line(
    version: int,
    on: date,
    *,
    contract: str = K_01,
    cancellable: object | None = True,
    **changes: object,
) -> EventInput:
    return event(
        contract,
        version,
        "BILLING_RECORDED",
        on,
        _tax_payload(on, cancellable, changes),
        ["POB-01"],
    )


def _tax_view(
    version: int,
    on: date,
    *,
    contract: str = K_01,
    cancellable: object | None = True,
    **changes: object,
) -> EventView:
    payload = _tax_payload(on, cancellable, changes)
    return event_view(
        contract, version, "BILLING_RECORDED", on, payload, obligation_keys=["POB-01"]
    )


def taxed(repeat: EventInput | None) -> InputBundle:
    """A 5,000.00 point-in-time line, a cancellable 1,000.00 / 80.00 invoice line INV-1 / INV-1-1 on
    1 January and, when given, a repeat of that identity."""
    goods = bundles.booking_line("POB-01", product_code="SKU-1", total_price="5000.00")
    events = [
        event(K_01, 1, "CONTRACT_BOOKED", CALENDAR, {"lines": [goods]}, ["POB-01"]),
        _tax_line(2, CALENDAR),
        *([] if repeat is None else [repeat]),
    ]
    return world(
        bundles.contract(K_01, inception=CALENDAR),
        events,
        products=[product("SKU-1")],
        templates=[template("TPL-PIT")],
    )


@pytest.mark.parametrize(
    ("repeat", "tax"),
    [
        pytest.param(None, "80.00", id="line"),
        pytest.param(_tax_line(3, JAN_20, cancellable=False), "80.00", id="repeat_false"),
        pytest.param(_tax_line(3, JAN_20, cancellable="false"), "80.00", id="repeat_string_false"),
        pytest.param(_tax_line(3, JAN_20, cancellable=None), "80.00", id="repeat_absent"),
        pytest.param(
            _tax_line(3, JAN_20, cancellable=False, tax_amount=Decimal("99.00")),
            "80.00",
            id="repeat_false_other_tax",
        ),
        pytest.param(_tax_line(3, JAN_20, cancellable=True), "160.00", id="repeat_true"),
        pytest.param(_tax_line(3, JAN_20, cancellable="true"), "160.00", id="repeat_string_true"),
        pytest.param(
            _tax_line(3, JAN_20, line_external_id="INV-1-2"), "160.00", id="different_line_id"
        ),
    ],
)
def test_d91_05h_sales_tax_counts_kernel_lines_only(repeat: EventInput | None, tax: str) -> None:
    """S04-R-20 through stages 01 to 04: a repeat of INV-1 / INV-1-1 whose ``is_cancellable`` is
    not true (``false``, ``"false"``, absent) is an S10-R-07 status update and adds no tax, whatever
    ``tax_amount`` it carries (the first line's tax stands; stage 04 validates nothing); a repeat
    flagged ``True`` or ``"true"``, or another line id, is another line (D-91 C606-05h; C606-01
    (2)). The price never holds the tax; the repeats are dated 20 January, so the view at 31 January
    (``price_at``) carries them and the inception price does not."""
    ctx, priced, _, _ = fold(taxed(repeat))
    assert priced.findings == ()
    # The inception price (1 January) precedes every 20 January repeat: 80.00 in every row.
    assert (priced.tp.total.posted, priced.tp.sales_tax_excluded.posted) == (500_000, 8_000)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    at_january_end = s04_transaction_price.price_at(ctx, priced.pob, date(2026, 1, 31), tb)
    assert at_january_end.sales_tax_excluded.posted == {"80.00": 8_000, "160.00": 16_000}[tax]
    assert at_january_end.total.posted == 500_000
    (node,) = [
        n for n in tb.build(root_measures={}).nodes if n.measure == "sales_tax_excluded_amount"
    ]
    assert (node.value, node.formula_id) == (tax, "tp.tax_excluded.v1")
    lines = 1 if tax == "80.00" else 2
    assert node.params["signs"] == ",".join("+" for _ in range(lines))
    assert len(node.inputs) == lines


def _members_state(events: Sequence[EventView], members: Sequence[str]) -> SimpleNamespace:
    """The ``PobState`` members ``taxes.excluded`` reads: the canonical measure events in ENG-06
    order, the contract headers (one contracting entity) and the member contract keys."""
    ordered = tuple(sorted(events, key=lambda ev: ev.order_key))
    contracts = {
        key: SimpleNamespace(header=SimpleNamespace(contracting_entity_code=bundles.ENTITY_CODE))
        for key in sorted({ev.contract_key for ev in events})
    }
    canonical = SimpleNamespace(measure_events=ordered, contracts=contracts)
    return SimpleNamespace(
        identified=SimpleNamespace(canonical=canonical, member_contract_keys=tuple(members))
    )


def test_d91_05h_taxes_identity_is_contract_scoped() -> None:
    """The identity is (contract key, ``invoice_number``, ``line_external_id``): identical
    identifiers on two member contracts are two lines (on main their taxes merged into one), each
    contract's status update is its own, a non-member contract's line never counts, and ``before``
    and ``at`` filter after the identity is classified (D-91 C606-05h; S10-R-07 contract scope)."""
    ctx = book_context()
    line_1 = _tax_view(3, CALENDAR)
    line_2 = _tax_view(3, CALENDAR, contract=K_02)
    outside = _tax_view(3, CALENDAR, contract=K_OUT)
    update_1 = _tax_view(4, JAN_20, cancellable=False)
    update_2 = _tax_view(4, JAN_20, contract=K_02, cancellable="false")
    events = [line_1, line_2, outside, update_1, update_2]
    st = _members_state(events, (K_01, K_02))
    at = date(2026, 12, 31)
    found = taxes.excluded(ctx, st, at, None)
    assert [(tax.event.event_key, tax.amount) for tax in found] == [
        (line_1.event_key, Fraction(80)),
        (line_2.event_key, Fraction(80)),
    ]
    assert {tax.treatment for tax in found} == {"EXCLUDE_ALL_IN_SCOPE"}
    named = taxes.excluded(ctx, st, at, None, contract_key=K_02)
    assert [tax.event.event_key for tax in named] == [line_2.event_key]
    # ``before`` at the update keeps the line; ``at`` before every line keeps nothing.
    positioned = taxes.excluded(ctx, st, at, update_1, contract_key=K_01)
    assert [tax.event.event_key for tax in positioned] == [line_1.event_key]
    assert taxes.excluded(ctx, st, date(2025, 12, 31), None) == ()
    # ``collected_tax`` (the S04-R-20 memo at d_v) sums the same lines for the same members.
    ordered = sorted(events, key=lambda ev: ev.order_key)
    assert taxes.collected_tax(ordered, {K_01, K_02}, at) == Fraction(160)
    assert taxes.collected_tax(ordered, {K_01}, at) == Fraction(80)
    assert taxes.collected_tax(ordered, {K_OUT}, at) == Fraction(80)
    assert taxes.collected_tax(ordered, {"K-NONE"}, at) == Fraction(0)
    assert taxes.collected_tax(ordered, {K_01, K_02}, date(2026, 1, 19)) == Fraction(160)


# --- S04-R-21 unconstrained, credit-adjusted view -----------------------------------------------


INCENTIVE = estimate(
    K_01,
    "VC-INCENTIVE",
    kind="VARIABLE_CONSIDERATION",
    method="EXPECTED_VALUE",
    vc_type="PERFORMANCE_INCENTIVE",
    scenarios=(("100000.00", "0.2"), ("0.00", "0.5"), ("-50000.00", "0.3")),
    unconstrained="5000.00",
    constrained="5000.00",
)
BONUS = estimate(
    K_01,
    "VC-BONUS",
    kind="VARIABLE_CONSIDERATION",
    method="MOST_LIKELY_AMOUNT",
    vc_type="BONUS",
    scenarios=(("150000.00", "0.7"), ("0.00", "0.3")),
    unconstrained="150000.00",
    conservative="0.00",
    constrained="0.00",
)


def ex_04_a(*extra: EventInput) -> InputBundle:
    goods = bundles.booking_line("POB-01", product_code="SKU-1", total_price="2500000.00")
    events = [
        event(K_01, 1, "CONTRACT_BOOKED", CALENDAR, {"lines": [goods]}, ["POB-01"]),
        changed(K_01, 2, INCENTIVE, CALENDAR),
        changed(K_01, 3, BONUS, CALENDAR),
        *extra,
    ]
    return world(
        bundles.contract(K_01, inception=CALENDAR),
        events,
        products=[product("SKU-1")],
        templates=[template("TPL-PIT")],
        estimates=[INCENTIVE, BONUS],
    )


def test_s04_r21_unconstrained_view() -> None:
    _, priced, _, _ = fold(ex_04_a())
    view = priced.tp_unconstrained[K_01]
    assert isinstance(view, UnconstrainedView)
    point = view.at(CALENDAR)
    assert (point.fixed.posted, point.vc_constrained.posted, point.total.posted) == (
        250_000_000,
        15_500_000,  # U 5,000.00 + U 150,000.00
        265_500_000,
    )
    assert priced.tp.total.posted == 250_500_000  # the constrained price keeps K
    assessed = event(
        K_01,
        4,
        "COLLECTIBILITY_ASSESSED",
        date(2026, 6, 30),
        {
            "book": "ASC606",
            "is_probable": True,
            "expected_collectible_amount": Decimal("2000000.00"),
        },
    )
    _, credit, _, _ = fold(ex_04_a(assessed))
    view = credit.tp_unconstrained[K_01]
    assert [build.at for build in view] == [CALENDAR, date(2026, 6, 30)]
    assert view.at(date(2026, 3, 31)).total.posted == 265_500_000
    assert view.at(date(2026, 7, 1)).total.posted == 200_000_000  # 605-35-25-46A: lower wins
