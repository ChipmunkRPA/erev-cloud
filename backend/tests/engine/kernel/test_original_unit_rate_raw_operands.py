"""D-98 candidate 117 (Codex production-20260921-0112 committed-source review at main 010a6a9c; lane
ENG-T1F): ``original_unit_revenue_rate`` = raw x_p ÷ Q (S05-R-16, CV-34, CV-47 (b)) — computed from
the
RAW original quota and the RAW original quantity, never from the decoded values of already encoded
trace nodes (CV-51 encodes an exact node at 18 places, so a non-terminating quota such as 1/3 loses
its
tail and the quotient of decoded inputs is short by 3e-18).

Codex's counterexample: allocation basis 100 minor units at mu 2 (TP 1.00), three equal weights →
x_p = 1/3 each; a positive fractional quantity Q = 0.1 (admitted by the payload grammar and the
ordinary
POB path). Required raw rate 10/3, final Q18 ``3.333333333333333333``; the decoded-input quotient
formats as ``3.33333333333333333``. The regression checks, independently: the raw quotient, the
final
encoding, the source identity of the node (the producing ``original_allocated_exact`` and
``original_quantity`` nodes as its inputs, the raw operands as its params) and the exact replay. The
REMAINING rate is not touched here (its numerator is a trace reconstruction by design; lane T1).
The SOURCE binding of the numerator — the node(s) that produced the CURRENT original allocation
(Codex production-20260921-0144 F1: a repin's share, or the relative node with the targeted
shares) — is ``test_original_unit_rate_provenance``; this module adds the explicit zero / NULL,
routed-out and remaining-rate cases (C1)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import (
    InputBundle,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.errors import EngineError
from erev_engine.formulas import FORMULAS
from erev_engine.money import format_exact
from erev_engine.trace import reevaluate
from support import bundles

CONTRACT = "K-P117"
ZERO_SHA = "0" * 64
TEMPLATE = TemplateInput(
    template_code="TPL-RATABLE",
    version_key="TPL-RATABLE@v1",
    version_no=1,
    content_sha256=ZERO_SHA,
    obligation_kind="STANDARD",
    distinctness="distinct",
    series_increment_unit=None,
    satisfaction_pattern="OVER_TIME",
    over_time_criterion="OT_A",
    recognition_method="TIME_ELAPSED",
    ratable_convention="DAILY",
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


def _entry(product: str, point: Decimal) -> SspEntryInput:
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
        ranges=(SspRangeInput("NONE", None, None, point, None, None, None),),
    )


def _world() -> InputBundle:
    """TP 1.00 (100 minor units) over three equal-SSP lines; POB-01 has quantity 0.1."""
    calendar = bundles.entity(months=12, books=("ASC606",))
    us = bundles.book("ASC606", entity=calendar)
    products = ["SKU-1", "SKU-2", "SKU-3"]
    prices = ["0.34", "0.33", "0.33"]
    quantities = ["0.1", "1", "1"]
    lines = [
        bundles.booking_line(
            f"POB-{number:02d}",
            product_code=product,
            quantity=quantity,
            total_price=price,
            end=date(2026, 12, 31),
        )
        for number, (product, price, quantity) in enumerate(
            zip(products, prices, quantities, strict=True), start=1
        )
    ]
    header = bundles.contract(CONTRACT)
    booked = bundles.event(
        CONTRACT,
        1,
        "CONTRACT_BOOKED",
        bundles.INCEPTION,
        {"lines": lines},
        obligation_keys=[str(line["obligation_key"]) for line in lines],
    )
    activated = bundles.event(
        CONTRACT, 2, "CONTRACT_ACTIVATED", bundles.INCEPTION, {"checklist": {}}
    )
    version = SspVersionInput(
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
        # equal EXTENDED SSP for the three lines: 5.00 × 0.1 = 0.50 × 1 = 0.50 → equal weights
        entries=(
            _entry("SKU-1", Decimal("5.00")),
            _entry("SKU-2", Decimal("0.50")),
            _entry("SKU-3", Decimal("0.50")),
        ),
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2027, 1, 1, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(us,),
        entities=(calendar,),
        group=bundles.group(
            (header,),
            products=[
                bundles.product(code, template_code="TPL-RATABLE", family=None) for code in products
            ],
        ),
        contracts=(header,),
        events=(booked, activated),
        ssp_versions=(version,),
        pob_template_versions=(TEMPLATE,),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def test_original_unit_revenue_rate_is_the_raw_quotient() -> None:
    output = compute(_world())
    book = next(item for item in output.books if item.book_code == "ASC606")
    version = next(
        item for item in book.obligation_versions if item.columns["obligation_key"] == "POB-01"
    )
    nodes = {node.id: node for node in book.trace.nodes}
    subject = version.subject_key
    # independent rational calculation: TP 1.00 over three equal weights, Q = 0.1
    x_p, quantity = Fraction(1, 3), Fraction(1, 10)
    assert version.columns["original_allocated_exact"] == x_p
    assert version.columns["original_quantity"] == quantity
    raw_rate = x_p / quantity
    assert raw_rate == Fraction(10, 3)
    # the column is the raw quotient, exactly
    assert version.columns["original_unit_revenue_rate"] == raw_rate
    # the node: final Q18 encoding of the raw quotient, not of the decoded-input quotient
    node = nodes[version.trace_nodes["original_unit_revenue_rate"]]
    assert node.value == format_exact(raw_rate) == "3.333333333333333333"
    decoded = Fraction(nodes[f"original_allocated_exact:{subject}:-"].value) / Fraction(
        nodes[f"original_quantity:{subject}:-"].value
    )
    assert format_exact(decoded) == "3.33333333333333333" and decoded < raw_rate
    # source identity: the producing nodes are the inputs; the raw operands are the params
    assert tuple(node.inputs) == (
        f"original_allocated_exact:{subject}:-",
        f"original_quantity:{subject}:-",
    )
    assert node.params.get("allocation") == "1/3" and node.params.get("quantity") == "1/10"
    # replay reproduces the node exactly from its bound sources / formula representation
    assert reevaluate(book.trace)[node.id] == node.value


def _versions(bundle: InputBundle) -> tuple[dict[str, object], dict[str, object], object]:
    output = compute(bundle)
    book = next(item for item in output.books if item.book_code == "ASC606")
    nodes = {node.id: node for node in book.trace.nodes}
    versions = {item.columns["obligation_key"]: item for item in book.obligation_versions}
    return versions, nodes, book.trace


def test_remaining_rate_untouched_amount_and_replay() -> None:
    """C1: the remaining rate keeps its own producer — the exact value (value + residue) of the
    posted ``remaining_allocation`` node over the ``remaining_quantity`` node — with its amount
    checked and its replay exact; the original rate of the whole-quantity lines is exactly 1/3."""
    versions, nodes, trace = _versions(_world())
    replayed = reevaluate(trace)
    for key in ("POB-02", "POB-03"):
        version = versions[key]
        subject = version.subject_key
        node = nodes[version.trace_nodes["remaining_unit_revenue_rate"]]
        assert node.inputs == (
            f"remaining_allocation:{subject}:-",
            f"remaining_quantity:{subject}:-",
        )
        allocation = nodes[f"remaining_allocation:{subject}:-"]
        exact_allocation = Fraction(allocation.value) + Fraction(allocation.rounding_residue or 0)
        remaining_quantity = Fraction(nodes[f"remaining_quantity:{subject}:-"].value)
        assert remaining_quantity == 1  # nothing delivered at the version date
        assert (
            version.columns["remaining_unit_revenue_rate"] == exact_allocation / remaining_quantity
        )
        assert (
            node.params["allocation"]
            == f"{exact_allocation.numerator}/{exact_allocation.denominator}"
        )
        assert "quantity" not in node.params  # the remaining rate keeps the decoded quantity input
        assert replayed[node.id] == node.value
        assert version.columns["original_unit_revenue_rate"] == Fraction(1, 3)


def test_zero_quantity_at_the_boundary_in_the_formula_and_after_a_full_delivery() -> None:
    """C1 (explicit zero / NULL cases). (1) Q = 0 on a booking line never reaches the rate: the
    engine refuses the line (S03-R-04, ``ENGINE_INVARIANT_VIOLATED``), so the original rate's
    NULL-at-zero branch is the formula's contract, exercised directly — (2) the formula with
    quantity 0 raises without a ``zero`` param (the original rate: NULL, no node) and returns 0
    with ``zero: "0"`` (the remaining rate; legacy 01 §3.7 NaN → 0). (3) A fully delivered line has
    remaining quantity 0 → ``remaining_unit_revenue_rate`` = 0 with its node (params zero "0",
    replay "0"), while its raw original rate and the other lines' rates are unchanged."""
    bundle = _world()
    booked, activated = bundle.events
    # (1) the engine boundary
    lines = [dict(line) for line in booked.payload["lines"]]  # type: ignore[union-attr]
    lines.append(
        bundles.booking_line(
            "POB-04", product_code="SKU-3", quantity="0", total_price="0.00", end=date(2026, 12, 31)
        )
    )
    rebooked = dataclasses.replace(
        booked,
        payload={**booked.payload, "lines": lines},
        obligation_keys=tuple(str(line["obligation_key"]) for line in lines),
    )
    with pytest.raises(EngineError) as refused:
        compute(dataclasses.replace(bundle, events=(rebooked, activated)))
    assert refused.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert "quantity 0" in refused.value.message
    # (2) the formula's zero rule
    formula = FORMULAS["books.unit_revenue_rate.v1"]
    with pytest.raises(ValueError, match="quantity is zero"):
        formula([Fraction(1, 3), Fraction(0)], {})
    assert formula([Fraction(1, 3), Fraction(0)], {"zero": "0"}) == 0
    assert formula([Fraction(1, 3), Fraction(0)], {"zero": "0", "allocation": "1/3"}) == 0
    # (3) remaining quantity 0 after the full delivery of POB-02
    delivered = bundles.event(
        CONTRACT,
        3,
        "DELIVERY_RECORDED",
        date(2026, 3, 31),
        {"obligation_key": "POB-02", "quantity": Decimal("1"), "trigger": "DELIVERY"},
        obligation_keys=["POB-02"],
    )
    versions, nodes, trace = _versions(
        dataclasses.replace(bundle, events=(booked, activated, delivered))
    )
    version = versions["POB-02"]
    subject = version.subject_key
    assert Fraction(nodes[f"remaining_quantity:{subject}:-"].value) == 0
    assert version.columns["remaining_unit_revenue_rate"] == 0
    node = nodes[version.trace_nodes["remaining_unit_revenue_rate"]]
    assert node.inputs == (
        f"remaining_allocation:{subject}:-",
        f"remaining_quantity:{subject}:-",
    )
    assert node.value == "0" and node.params["zero"] == "0"
    assert reevaluate(trace)[node.id] == "0"
    assert version.columns["original_unit_revenue_rate"] == Fraction(1, 3)
    assert versions["POB-01"].columns["original_unit_revenue_rate"] == Fraction(10, 3)
    other = versions["POB-03"]
    assert other.columns["original_unit_revenue_rate"] == Fraction(1, 3)
    assert "quantity" not in nodes[other.trace_nodes["remaining_unit_revenue_rate"]].params


def test_routed_out_line_keeps_its_original_rate_and_has_no_remaining_rate() -> None:
    """C1: a LEASE_842 line routed out after allocation (ALC-BR-06, contract BR-06, L1-LEASE) has no
    stage 09 measures — its remaining rate is NULL with no node — while its original allocation and
    quantity exist, so the original rate is the raw quotient of those and cites them."""
    from support.answer_keys.loader import ANSWER_KEY_ROOT, load
    from support.answer_keys.runners import _build_checkpoint_bundles

    loaded = load(ANSWER_KEY_ROOT / "alc" / "ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT.yaml")
    checkpoint = _build_checkpoint_bundles(loaded)[-1]
    (bundle,) = [
        item
        for item in checkpoint.bundles
        if any(header.external_id == "BR-06" for header in item.contracts)
    ]
    versions, nodes, trace = _versions(bundle)
    lease = versions["L1-LEASE"]
    assert lease.columns["remaining_unit_revenue_rate"] is None
    assert "remaining_unit_revenue_rate" not in lease.trace_nodes
    assert f"remaining_unit_revenue_rate:{lease.subject_key}:-" not in nodes
    quantity = lease.columns["original_quantity"]
    quota = lease.columns["original_allocated_exact"]
    assert isinstance(quantity, Fraction) and isinstance(quota, Fraction) and quantity != 0
    assert lease.columns["original_unit_revenue_rate"] == quota / quantity
    node = nodes[lease.trace_nodes["original_unit_revenue_rate"]]
    assert node.inputs == (
        f"original_allocated_exact:{lease.subject_key}:-",
        f"original_quantity:{lease.subject_key}:-",
    )
    assert reevaluate(trace)[node.id] == node.value
