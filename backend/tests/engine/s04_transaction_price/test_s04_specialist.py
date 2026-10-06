"""Stage 04 consideration payable, share-based consideration payable, noncash consideration and the
assurance-type warranty accrual.

ENGINE_SPEC §4.3 S04-R-14 to S04-R-19, S04-R-02 (memo sign and ``revenue_cum``, rev 1.3), §4.4
S04-INV-04 (released incentive), §4.5 EX-04-C, EX-04-D; POLICIES POL-022, POL-048, POL-049, PT-10
(CHK-120), JET-14, JET-16, JET-17 (CHK-133 to CHK-135); BUILD_SPEC ENA-9. Bundles come from
``support.bundles``; stages 01 to 05 run for real. No database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest
import yaml
from erev_engine import ENGINE_VERSION, money
from erev_engine.bundle import (
    ContractInput,
    EstimateVersionInput,
    EventInput,
    InputBundle,
    NoncashInput,
    PayableInput,
    ProductInput,
    ResolvedPolicyInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.enums import BookCode
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
)
from erev_engine.stages.s04_transaction_price import PricedState, specialist
from erev_engine.stages.state import AllocatedState, BookContext, EventView, PolicyResolver, Target
from erev_engine.trace import TraceBuilder, TraceNode
from support import bundles
from support.answer_keys.loader import ANSWER_KEY_ROOT
from support.recognition import event_view

ENTITY = bundles.ENTITY_CODE
JANUARY_2026 = date(2026, 1, 1)
ZERO = "0" * 64
SSP_BOOK = "SSP-MAIN"
RELEASE_BASIS = "cpc.incentive_asset_release_basis"


def template(code: str, *, method: str) -> TemplateInput:
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


UNITS = template("TPL-UNITS", method="UNITS_DELIVERED")
PIT = template("TPL-PIT", method="POINT_IN_TIME")


def product(code: str, template_code: str, **changes: object) -> ProductInput:
    return dataclasses.replace(
        bundles.product(code, template_code=template_code, family=None), **changes
    )


def ssp_book(product_code: str, point: str) -> SspVersionInput:
    entry = SspEntryInput(
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
        entries=(entry,),
    )


def booked(
    contract: str, key: str, product_code: str, quantity: str, price: str, end: date = JANUARY_2026
) -> list[EventInput]:
    line = bundles.booking_line(
        key,
        product_code=product_code,
        quantity=quantity,
        total_price=price,
        start=JANUARY_2026,
        end=end,
    )
    return [
        bundles.event(
            contract, 1, "CONTRACT_BOOKED", JANUARY_2026, {"lines": [line]}, obligation_keys=[key]
        ),
        bundles.event(contract, 2, "CONTRACT_ACTIVATED", JANUARY_2026, {}),
    ]


def then(
    events: list[EventInput], kind: str, on: date, payload: Mapping[str, object]
) -> list[EventInput]:
    """``events`` with one more event of the same contract, numbered after the last."""
    contract = events[0].contract_key
    key = payload.get("obligation_key")
    keys = [key] if isinstance(key, str) else []
    return [
        *events,
        bundles.event(contract, len(events) + 1, kind, on, payload, obligation_keys=keys),
    ]


def delivered(events: list[EventInput], key: str, on: date, quantity: str) -> list[EventInput]:
    payload = {"obligation_key": key, "quantity": Decimal(quantity), "trigger": "DELIVERY"}
    return then(events, "DELIVERY_RECORDED", on, payload)


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


def world(
    contract: ContractInput,
    events: Sequence[EventInput],
    *,
    products: Sequence[ProductInput],
    templates: Sequence[TemplateInput],
    estimates: Sequence[EstimateVersionInput] = (),
    ssp: Sequence[SspVersionInput] = (),
    policies: Mapping[str, str] | None = None,
    overrides: Mapping[str, str] | None = None,
) -> InputBundle:
    calendar = bundles.entity(start=JANUARY_2026, months=24)
    book = bundles.book("ASC606", entity=calendar)
    values = policies or {}
    rows = [
        dataclasses.replace(row, value=values[row.code]) if row.code in values else row
        for row in book.policies
    ]
    for code, value in (overrides or {}).items():
        source = f"{contract.external_id}/policy_overrides/{code}"
        rows.append(
            ResolvedPolicyInput(code, "CONTRACT", contract.external_id, value, "C", source, "K")
        )
    book = dataclasses.replace(
        book, policies=tuple(sorted(rows, key=lambda p: (p.code, p.scope, p.subject_key)))
    )
    last = max(event.effective_date for event in events)
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(last.year, last.month, last.day, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
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


def context(value: InputBundle) -> BookContext:
    (book,) = value.books
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
) -> tuple[BookContext, PricedState, AllocatedState | None, dict[str, TraceNode]]:
    """Stages 01 to 05 with one trace builder for stages 03 to 05; stage 05 runs only when the
    bundle carries an SSP book."""
    ctx = context(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, tb), tb)
    allocated = s05_allocation.run(ctx, priced, tb) if value.ssp_versions else None
    return ctx, priced, allocated, {node.id: node for node in tb.build(root_measures={}).nodes}


def series(targets: Sequence[Target], measure: str) -> dict[str, Target]:
    return {target.period_key: target for target in targets if target.measure == measure}


def checkpoint(key: str, name: str) -> Mapping[str, str]:
    """The contract ``version`` block of an answer-key checkpoint (read only)."""
    path = ANSWER_KEY_ROOT / key.split("-", 1)[0].lower() / f"{key}.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    (point,) = [item for item in document["checkpoints"] if item["name"] == name]
    (contract,) = point["contracts"]
    version: Mapping[str, str] = contract["version"]
    return version


def payable(
    amount: str, on: date, key: str, *, committed: str | None = None, share_based: bool = False
) -> PayableInput:
    return PayableInput(
        amount=Decimal(amount),
        promise_date=on,
        related_obligation_keys=(key,),
        distinct_good_fair_value=None,
        committed_purchases=None if committed is None else Decimal(committed),
        share_based=share_based,
    )


# --- S04-R-14 to S04-R-16 consideration payable (EX-04-D; CHK-133) ------------------------------

EX32 = "C-EX32"
MONTH_1 = date(2026, 1, 31)


def ex_32() -> InputBundle:
    """CPC-CHK-133-S3-EX32 inputs: 1,500,000.00 paid at inception for shelving, committed purchases
    15,000,000.00 and a January invoice of 2,000,000.00."""
    header = bundles.contract(
        EX32,
        inception=JANUARY_2026,
        consideration_payable=[
            payable("1500000.00", JANUARY_2026, "L1-GOODS", committed="15000000.00")
        ],
    )
    events = booked(EX32, "L1-GOODS", "CONSUMER-GOODS", "15000000", "15000000.00")
    events = invoiced(
        delivered(events, "L1-GOODS", MONTH_1, "2000000"), "L1-GOODS", MONTH_1, "2000000.00"
    )
    return world(
        header,
        events,
        products=[product("CONSUMER-GOODS", "TPL-UNITS")],
        templates=[UNITS],
        ssp=[ssp_book("CONSUMER-GOODS", "1")],
        overrides={RELEASE_BASIS: "COMMITTED_PURCHASES"},
    )


def test_ex_04_d_consideration_payable() -> None:
    _, priced, allocated, nodes = fold(ex_32())
    assert priced.findings == ()
    assert allocated is not None and allocated.findings == ()
    (tp,) = allocated.tp_history
    assert (tp.consideration_payable.posted, tp.total.posted, tp.allocation_basis.posted) == (
        -150_000_000,
        1_350_000_000,
        1_500_000_000,
    )
    version = checkpoint("CPC-CHK-133-S3-EX32", "at-inception")
    assert version["consideration_payable_amount"] == "-1500000.00"  # the member sign (R-SGN-01)
    assert (
        money.format_money(tp.consideration_payable.posted, 2)
        == version["consideration_payable_amount"]
    )
    assert money.format_money(tp.total.posted, 2) == version["transaction_price"]
    (goods,) = allocated.obligations
    allocated_amount = goods.original_allocation.a_posted
    assert allocated_amount == tp.total.posted - tp.consideration_payable.posted  # DB-17 V1
    assert allocated_amount == 1_500_000_000
    memo = nodes["consideration_payable_amount:CG-1:-"]
    assert (memo.value, memo.formula_id, memo.params["signs"]) == (
        "-1500000.00",
        "tp.cpc_reduction.v1",
        "-",
    )
    targets = priced.specialist_targets.customer_consideration
    release = series(targets, "incentive_release_ordinary_cum")["FY2026-P01"]
    asset = series(targets, "customer_incentive_asset")["FY2026-P01"]
    promised = series(targets, "consideration_payable")["FY2026-P01"]
    assert (release.value, asset.value, promised.value) == (20_000_000, 130_000_000, 150_000_000)
    assert (release.entity, release.subject_key) == (ENTITY, f"{EX32}@{ENTITY}")
    node = nodes[f"incentive_release_ordinary_cum:{EX32}@{ENTITY}:FY2026-P01"]
    assert (node.formula_id, node.params["rates"], node.params["basis"]) == (
        "tp.cpc_release.v1",
        "0.1",
        "COMMITTED_PURCHASES",
    )
    assert allocated.specialist_targets == priced.specialist_targets


def test_s04_r15_promise_after_revenue_released_at_promise_date() -> None:
    def bundle(on: date) -> InputBundle:
        header = bundles.contract(
            "C-AFTER",
            inception=JANUARY_2026,
            consideration_payable=[payable("100000.00", on, "L1-GOODS", committed="1000000.00")],
        )
        events = booked("C-AFTER", "L1-GOODS", "GOODS", "1000000", "1000000.00")
        events = invoiced(
            delivered(events, "L1-GOODS", MONTH_1, "400000"), "L1-GOODS", MONTH_1, "400000.00"
        )
        return world(
            header,
            events,
            products=[product("GOODS", "TPL-UNITS")],
            templates=[UNITS],
            overrides={RELEASE_BASIS: "COMMITTED_PURCHASES"},
        )

    later = date(2026, 3, 15)
    ctx, priced, _, _ = fold(bundle(later))
    assert priced.findings == ()
    targets = priced.specialist_targets.customer_consideration
    release = series(targets, "incentive_release_ordinary_cum")
    assert "FY2026-P02" not in release  # the targets begin in the period of the promise
    assert release["FY2026-P03"].value == 10_000_000  # released in full, not 0.1 × 400,000.00
    assert series(targets, "customer_incentive_asset")["FY2026-P03"].value == 0
    assert series(targets, "consideration_payable")["FY2026-P03"].value == 10_000_000
    assert priced.tp.consideration_payable.posted == 0  # the promise postdates the inception price
    after = s04_transaction_price.price_at(ctx, priced.pob, date(2026, 3, 31), None)
    assert (after.consideration_payable.posted, after.total.posted) == (-10_000_000, 90_000_000)
    # A promise made before the related revenue creates the asset and releases 10% of invoices.
    _, priced, _, _ = fold(bundle(JANUARY_2026))
    targets = priced.specialist_targets.customer_consideration
    assert series(targets, "incentive_release_ordinary_cum")["FY2026-P01"].value == 4_000_000
    assert series(targets, "customer_incentive_asset")["FY2026-P01"].value == 6_000_000


# --- D-91 C606-05h: S04-R-15/16 incentive invoices read the S10-R-07 identity from the kernel ---

FEBRUARY_10 = date(2026, 2, 10)
INCENTIVE_LINE: Mapping[str, object] = {
    "invoice_number": "INV-4",
    "line_external_id": "INV-4-1",
    "obligation_key": "L1-GOODS",
    "amount": Decimal("400000.00"),
    "issue_date": MONTH_1,
}


def _incentive_world(*repeats: Mapping[str, object]) -> InputBundle:
    """The S04-R-15 promise-before-revenue world: 100,000.00 promised on 1 January against
    1,000,000.00 of committed purchases (ρ 0.1), 400,000.00 delivered and invoiced as INV-4 /
    INV-4-1 on 31 January (``is_cancellable`` absent), then one ``BILLING_RECORDED`` per entry of
    ``repeats`` on 10 February carrying that identity with the entry's changes."""
    header = bundles.contract(
        "C-05H",
        inception=JANUARY_2026,
        consideration_payable=[
            payable("100000.00", JANUARY_2026, "L1-GOODS", committed="1000000.00")
        ],
    )
    events = booked("C-05H", "L1-GOODS", "GOODS", "1000000", "1000000.00")
    events = invoiced(
        delivered(events, "L1-GOODS", MONTH_1, "400000"), "L1-GOODS", MONTH_1, "400000.00"
    )
    assert events[-1].payload["invoice_number"] == INCENTIVE_LINE["invoice_number"]
    for changes in repeats:
        events = then(events, "BILLING_RECORDED", FEBRUARY_10, {**INCENTIVE_LINE, **changes})
    return world(
        header,
        events,
        products=[product("GOODS", "TPL-UNITS")],
        templates=[UNITS],
        overrides={RELEASE_BASIS: "COMMITTED_PURCHASES"},
    )


@pytest.mark.parametrize(
    ("repeats", "release", "asset"),
    [
        pytest.param((), 4_000_000, 6_000_000, id="line"),
        pytest.param(({"is_cancellable": False},), 4_000_000, 6_000_000, id="repeat_false"),
        pytest.param(
            ({"is_cancellable": "false"},), 4_000_000, 6_000_000, id="repeat_string_false"
        ),
        pytest.param(({},), 4_000_000, 6_000_000, id="repeat_absent"),
        pytest.param(
            ({"is_cancellable": False}, {"is_cancellable": False}),
            4_000_000,
            6_000_000,
            id="two_updates",
        ),
        pytest.param(({"is_cancellable": True},), 8_000_000, 2_000_000, id="repeat_true"),
        pytest.param(({"is_cancellable": "true"},), 8_000_000, 2_000_000, id="repeat_string_true"),
        pytest.param(
            ({"line_external_id": "INV-4-2"},), 8_000_000, 2_000_000, id="different_line_id"
        ),
    ],
)
def test_d91_05h_incentive_release_counts_kernel_lines_only(
    repeats: tuple[Mapping[str, object], ...], release: int, asset: int
) -> None:
    """S04-R-15 / S04-R-16 through stages 01 to 04: the ordinary release min(R, ρ × invoiced) reads
    the contract's invoices from the kernel kept-lines view. A 10 February repeat of INV-4 /
    INV-4-1 whose ``is_cancellable`` is not true (``false``, ``"false"``, absent; two of them) is
    an S10-R-07 status update and invoices nothing more (FY2026-P02 release 40,000.00 on
    400,000.00, asset 60,000.00); a repeat flagged ``True`` / ``"true"`` (the
    noncancellable-then-cancellable edge, D-91 C606-01 (2)) or another line id is another
    400,000.00 invoice (release 80,000.00, asset 20,000.00). January is untouched either way (D-91
    C606-05h)."""
    _, priced, _, _ = fold(_incentive_world(*repeats))
    assert priced.findings == ()
    targets = priced.specialist_targets.customer_consideration
    released = series(targets, "incentive_release_ordinary_cum")
    remaining = series(targets, "customer_incentive_asset")
    assert (released["FY2026-P01"].value, remaining["FY2026-P01"].value) == (4_000_000, 6_000_000)
    assert (released["FY2026-P02"].value, remaining["FY2026-P02"].value) == (release, asset)


def _bill(
    version: int,
    on: date,
    *,
    contract: str = "C-05H",
    cancellable: object | None = True,
    **changes: object,
) -> EventView:
    payload: dict[str, object] = {**INCENTIVE_LINE, "issue_date": on, **changes}
    if cancellable is not None:
        payload["is_cancellable"] = cancellable
    keys = [str(payload["obligation_key"])]
    return event_view(contract, version, "BILLING_RECORDED", on, payload, obligation_keys=keys)


def _canonical(*events: EventView) -> SimpleNamespace:
    ordered = tuple(sorted(events, key=lambda ev: ev.order_key))
    return SimpleNamespace(identified=SimpleNamespace(canonical=SimpleNamespace(events=ordered)))


def test_d91_05h_specialist_invoices_apply_the_kernel_identity() -> None:
    """``specialist.invoices`` classifies the contract's whole stream before the [since, at] window
    and the obligation filter: a status update inside the window of a line outside it is not an
    invoice (on main the window-first mirror counted it as the first-seen line); a repeat flagged
    ``"true"`` is another invoice; a status update naming another obligation never re-attributes
    (its mismatch is stage 10's finding); a line of another contract never counts (D-91
    C606-05h)."""
    line = _bill(3, date(2026, 1, 10))
    update = _bill(4, FEBRUARY_10, cancellable=False)
    other = _bill(3, FEBRUARY_10, contract="C-OTHER")
    st = _canonical(line, update, other)
    february = (date(2026, 2, 1), date(2026, 2, 28))
    assert specialist.invoices(st, "C-05H", (), *february) == ()
    assert specialist.invoices(st, "C-05H", (), JANUARY_2026, february[1]) == (
        (line, Fraction(400000)),
    )
    assert specialist.invoices(st, "C-OTHER", (), *february) == ((other, Fraction(400000)),)
    again = _bill(5, date(2026, 2, 20), cancellable="true")
    moved = _bill(6, date(2026, 2, 25), cancellable=False, obligation_key="L2-OTHER")
    st = _canonical(line, update, again, moved)
    assert specialist.invoices(st, "C-05H", ("L1-GOODS",), JANUARY_2026, february[1]) == (
        (line, Fraction(400000)),
        (again, Fraction(400000)),
    )
    assert specialist.invoices(st, "C-05H", ("L2-OTHER",), JANUARY_2026, february[1]) == ()


# --- S04-R-17 share-based consideration payable (PT-10; CHK-120) --------------------------------

WARRANT = "C-WARRANT"
YEAR_1 = date(2026, 6, 30)
YEAR_2 = date(2027, 6, 30)


def warrants(*, not_probable_at: date | None = None) -> InputBundle:
    key = f"{WARRANT}/SBC-WARRANT"

    def version(number: int, on: date, probable: bool) -> EstimateVersionInput:
        return EstimateVersionInput(
            estimate_key=key,
            estimate_kind="SHARE_BASED_CONSIDERATION",
            element_code="SBC-WARRANT",
            method="ENTERED_AMOUNT",
            vc_element_type=None,
            allocation_target="CONTRACT",
            target_obligation_keys=(),
            obligation_key="L1-SUPPLY",
            version_key=f"{key}@v{number}",
            version_no=number,
            status="APPROVED",
            effective_date=on,
            scenarios=(),
            parameters={
                "grant_date": "2026-01-01",
                "grant_date_fair_value": "50000.00",
                "vesting_probable": probable,
            },
            unconstrained_amount=None,
            most_conservative_amount=None,
            constrained_amount=None,
            rate=None,
            expected_total_amount=Decimal("1000000.00"),
            expected_quantity=None,
            amortization_months=None,
            currency="USD",
            supersedes_version_key=None if number == 1 else f"{key}@v1",
            judgement_key=None,
            content_sha256=ZERO,
        )

    header = bundles.contract(
        WARRANT,
        inception=JANUARY_2026,
        consideration_payable=[payable("50000.00", JANUARY_2026, "L1-SUPPLY", share_based=True)],
    )
    versions = [version(1, JANUARY_2026, True)]
    events = booked(WARRANT, "L1-SUPPLY", "SUPPLY-UNIT", "1000000", "1000000.00")
    events = then(events, "ESTIMATE_CHANGED", JANUARY_2026, {"estimate_version_id": f"{key}@v1"})
    events = invoiced(
        delivered(events, "L1-SUPPLY", YEAR_1, "400000"), "L1-SUPPLY", YEAR_1, "400000.00"
    )
    if not_probable_at is not None:
        versions.append(version(2, not_probable_at, False))
        payload = {"estimate_version_id": f"{key}@v2"}
        events = then(events, "ESTIMATE_CHANGED", not_probable_at, payload)
    events = invoiced(
        delivered(events, "L1-SUPPLY", YEAR_2, "600000"), "L1-SUPPLY", YEAR_2, "600000.00"
    )
    return world(
        header,
        events,
        products=[product("SUPPLY-UNIT", "TPL-UNITS")],
        templates=[UNITS],
        estimates=versions,
    )


def test_stage_04_ordinary_series_and_asset_identity() -> None:
    """D-91 C606-03: stage 04 publishes the promise memo, the ordinary release
    (``incentive_release_ordinary_cum``, S04-R-16) and the asset as the identity posted payable −
    posted ordinary release (signed sum of the two nodes, S04-R-16 rev 1.6); the share-based
    reduction is a stage 10 measure, so no share row leaves stage 04. Figures unchanged: CHK-133
    200,000.00 / 1,300,000.00 / 1,500,000.00; after-revenue 100,000.00 at P03; before-revenue
    40,000.00 / 60,000.00; CHK-120 ordinary 0 with the memo −50,000.00; the tie world (R 0.01,
    committed 2.00, invoice 1.00) releases 0.01 and keeps an asset of 0.00 where an independently
    rounded round(R − O) gave 0.01."""
    _, priced, _, nodes = fold(ex_32())
    targets = priced.specialist_targets.customer_consideration
    assert {t.measure for t in targets} == {
        "consideration_payable",
        "incentive_release_ordinary_cum",
        "customer_incentive_asset",
    }
    january = "FY2026-P01"
    assert series(targets, "incentive_release_ordinary_cum")[january].value == 20_000_000
    assert series(targets, "customer_incentive_asset")[january].value == 130_000_000
    assert series(targets, "consideration_payable")[january].value == 150_000_000
    asset = nodes[f"customer_incentive_asset:{EX32}@{ENTITY}:{january}"]
    assert (asset.formula_id, asset.params["signs"], asset.rounding_residue) == (
        "tp.cpc_release.v1",
        "+,-",
        "0",
    )
    assert list(asset.inputs) == [
        f"consideration_payable:{EX32}@{ENTITY}:{january}",
        f"incentive_release_ordinary_cum:{EX32}@{ENTITY}:{january}",
    ]
    # CHK-120: the share-based promise leaves the memo at −50,000.00 and the ordinary series at 0.
    _, priced, _, nodes = fold(warrants())
    assert priced.findings == ()
    targets = priced.specialist_targets.customer_consideration
    assert "share_based_reduction_cum" not in {t.measure for t in targets}
    assert not any(node_id.startswith("share_based_reduction") for node_id in nodes)
    assert series(targets, "incentive_release_ordinary_cum")["FY2027-P06"].value == 0
    assert series(targets, "consideration_payable")["FY2027-P06"].value == 0  # EQUITY, not payable
    assert series(targets, "customer_incentive_asset")["FY2027-P06"].value == 0
    assert "FY2026-P01" in series(targets, "incentive_release_ordinary_cum")  # opens at the pin
    assert priced.tp.consideration_payable.posted == -5_000_000  # the promise memo (S04-R-14)
    # Tie world: R 0.01 over 2.00 committed, one unit of two invoiced at 1.00.
    header = bundles.contract(
        "C-TIE",
        inception=JANUARY_2026,
        consideration_payable=[payable("0.01", JANUARY_2026, "L1-GOODS", committed="2.00")],
    )
    events = booked("C-TIE", "L1-GOODS", "CONSUMER-GOODS", "2", "2.00")
    events = invoiced(delivered(events, "L1-GOODS", MONTH_1, "1"), "L1-GOODS", MONTH_1, "1.00")
    _, priced, _, nodes = fold(
        world(
            header,
            events,
            products=[product("CONSUMER-GOODS", "TPL-UNITS")],
            templates=[UNITS],
            ssp=[ssp_book("CONSUMER-GOODS", "1")],
            overrides={RELEASE_BASIS: "COMMITTED_PURCHASES"},
        )
    )
    targets = priced.specialist_targets.customer_consideration
    release = series(targets, "incentive_release_ordinary_cum")[january]
    assert (release.value, release.exact) == (1, Fraction(1, 200))
    assert series(targets, "customer_incentive_asset")[january].value == 0
    assert series(targets, "consideration_payable")[january].value == 1


# --- S04-R-18 noncash consideration (EX-04-C; CHK-135) ------------------------------------------

EX31 = "C-EX31"


def ex_31(weeks: int) -> InputBundle:
    """NCC-CHK-135-S3-EX31 inputs: 100 customer shares per completed week for 52 weeks at 10.00."""
    header = dataclasses.replace(
        bundles.contract(EX31, inception=JANUARY_2026),
        noncash_consideration=(
            NoncashInput(Decimal("5200"), Decimal("10.00"), JANUARY_2026, "FORM", "SHARES"),
        ),
    )
    events = booked(EX31, "L1-WEEKS", "WEEKLY-SVC", "52", "0.00", end=date(2026, 12, 30))
    for week in range(1, weeks + 1):
        events = delivered(events, "L1-WEEKS", date(2026, 1, 7 * week), "1")
    return world(
        header,
        events,
        products=[product("WEEKLY-SVC", "TPL-UNITS")],
        templates=[UNITS],
        policies={"noncash.measurement_date": "CONTRACT_INCEPTION"},
    )


def test_ex_04_c_noncash_consideration() -> None:
    _, priced, _, nodes = fold(ex_31(1))
    assert priced.findings == ()
    tp = priced.tp
    assert (tp.noncash.posted, tp.total.posted, tp.allocation_basis.posted) == (
        5_200_000,
        5_200_000,
        5_200_000,
    )
    amount = nodes["noncash_consideration_amount:CG-1:-"]
    assert (amount.value, amount.formula_id, amount.params["policies"]) == (
        "52000.00",
        "tp.noncash.v1",
        "CONTRACT_INCEPTION",
    )
    recognised = series(priced.specialist_targets.noncash, "noncash_asset_recognised_cum")
    week_1 = recognised["FY2026-P01"]
    assert (week_1.value, week_1.entity, week_1.subject_key) == (
        100_000,
        ENTITY,
        f"{EX31}@{ENTITY}",
    )
    node = nodes[f"noncash_asset_recognised_cum:{EX31}@{ENTITY}:FY2026-P01"]
    assert (node.formula_id, node.value, node.params["completed"]) == (
        "tp.noncash.v1",
        "1000.00",
        "0.019230769230769231",  # 1 ÷ 52 at 18 places
    )
    # Four completed weeks by the end of January: 4,000.00.
    _, priced, _, _ = fold(ex_31(4))
    recognised = series(priced.specialist_targets.noncash, "noncash_asset_recognised_cum")
    assert recognised["FY2026-P01"].value == 400_000


# --- S04-R-19 assurance-type warranty accrual (CHK-134) -----------------------------------------

WTY = "C-WTY"


def warranty(
    *, on: date = date(2026, 1, 10), cost: str | None = "200.00", policy: str = "ENGINE"
) -> InputBundle:
    equipment = product(
        "EQUIP",
        "TPL-PIT",
        assurance_cost_per_unit=None if cost is None else Decimal(cost),
    )
    events = booked(WTY, "L1-EQUIP", "EQUIP", "1", "9700.00")
    payload = {
        "obligation_key": "L1-EQUIP",
        "quantity": Decimal("1"),
        "trigger": "CONTROL_TRANSFER",
    }
    events = then(events, "DELIVERY_RECORDED", on, payload)
    return world(
        bundles.contract(WTY, inception=JANUARY_2026),
        events,
        products=[equipment],
        templates=[PIT],
        policies={"pob.assurance_warranty_accrual": policy},
    )


def test_s04_r19_warranty_accrual() -> None:
    _, priced, _, nodes = fold(warranty())
    assert priced.findings == ()
    accrued = series(priced.specialist_targets.warranty, "warranty_accrual_cum")
    delivery = accrued["FY2026-P01"]
    assert (delivery.value, delivery.subject_key, delivery.entity) == (
        20_000,
        f"{WTY}/L1-EQUIP",
        ENTITY,
    )
    node = nodes[f"warranty_accrual_cum:{WTY}/L1-EQUIP:FY2026-P01"]
    assert (node.formula_id, node.value, node.params["cost_per_unit"], node.params["units"]) == (
        "tp.warranty_accrual.v1",
        "200.00",
        "200",
        "1",
    )
    assert accrued["FY2027-P12"].value == 20_000
    # The accrual follows transferred units: nothing before a February delivery.
    _, priced, _, _ = fold(warranty(on=date(2026, 2, 10)))
    accrued = series(priced.specialist_targets.warranty, "warranty_accrual_cum")
    assert (accrued["FY2026-P01"].value, accrued["FY2026-P02"].value) == (0, 20_000)
    # POL-022 EXTERNAL or a product without a cost rate: no target.
    assert fold(warranty(policy="EXTERNAL"))[1].specialist_targets.warranty == ()
    assert fold(warranty(cost=None))[1].specialist_targets.warranty == ()
