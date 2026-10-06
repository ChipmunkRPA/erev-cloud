"""JET-14 part targets from the EMOD-22 measures (ENGINE_SPEC S04-R-02 rev 1.6, S04-R-14 to
S04-R-17; ENGINE_SPEC_B S10-R-26, S14-R-01, S14-R-11, Table 14-A row "JET-14 promised, after
revenue, release, share-based"; POLICIES JET-14, CHK-133, PT-10 CHK-120; lane L5-5; D-91 C606-03).

Stage 04 publishes ``consideration_payable``, ``incentive_release_ordinary_cum`` and
``customer_incentive_asset``; stage 10 adds ``share_based_reduction_cum`` and the composed
``incentive_release_cum`` = ordinary + share-based (posted sums). Stage 14 posts the promised part
from the payable node, the release part from the ordinary node on its own and the share-based part
from the share node: P + E = T with no residue (D-91 (5); main posted P = T − E, so the ordinary
asset line depended on the share measure). Figures: CHK-133 (1,500,000.00 promised, 200,000.00
released), CHK-120 (20,000.00 share-based), the mixed half-cent case (0.01 + 0.01 = 0.02) and the
mixed over-time case A (T 11,415.52 at P02, 23,105.03 at P04). No database.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import (
    AccountMappingInput,
    BookInput,
    InputBundle,
    MappingRuleInput,
    PayableInput,
    ResolvedPolicyInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.enums import BookCode
from erev_engine.errors import EngineError
from erev_engine.stages.s12_fx_entities import FxState
from erev_engine.stages.s14_posting import PartInputs
from erev_engine.stages.s14_posting.targets import part_targets
from erev_engine.stages.state import Target
from support import bundles
from support import cpc_worlds as w
from support.recognition import CONTRACT_KEY, allocated_state, book_context, usd

ENTITY = bundles.ENTITY_CODE
SUBJECT = f"{CONTRACT_KEY}@{ENTITY}"
PAYABLE = "consideration_payable"
ORDINARY = "incentive_release_ordinary_cum"
SHARE = "share_based_reduction_cum"
RELEASE = "incentive_release_cum"


def _target(measure: str, period: str, amount: str) -> Target:
    node = f"{measure}:{SUBJECT}:{period}"
    return Target(BookCode.ASC606, ENTITY, SUBJECT, measure, period, None, usd(amount), None, node)


def _state() -> FxState:
    return FxState(
        allocated=allocated_state([]),
        costs=None,  # type: ignore[arg-type]
        layer_movements=(),
        layer_balances=(),
        functional_targets=(),
        remeasurement_targets=(),
        gain_loss_targets=(),
        ic_pairs=(),
        findings=(),
    )


def _parts(targets: tuple[Target, ...]) -> dict[tuple[str, str], tuple[int, int]]:
    ctx = book_context(bundles.entity(months=6), book_code="ASC606", currency="USD")
    parts = part_targets(ctx, _state(), PartInputs(customer_consideration=targets))
    assert all((p.subject_key, p.entity, p.time_txn) == (SUBJECT, ENTITY, 0) for p in parts)
    return {(p.part, p.period_key): (p.amount_txn, p.amount_functional) for p in parts}


def test_jet_14_promised_and_release_from_the_emod_22_measures() -> None:
    # CHK-133: payable 1,500,000.00 from inception; January release 200,000.00; asset 1,300,000.00.
    targets = (
        _target(PAYABLE, "FY2026-P01", "1500000.00"),
        _target(ORDINARY, "FY2026-P01", "200000.00"),
        _target(RELEASE, "FY2026-P01", "200000.00"),
        # The incentive asset is a balance (T-CON-09), not a JET-14 part amount.
        _target("customer_incentive_asset", "FY2026-P01", "1300000.00"),
        _target(PAYABLE, "FY2026-P02", "1500000.00"),
        _target(ORDINARY, "FY2026-P02", "200000.00"),
        _target(RELEASE, "FY2026-P02", "200000.00"),
    )
    found = _parts(targets)
    assert found == {
        ("JET-14 promised", "FY2026-P01"): (150_000_000, 150_000_000),
        ("JET-14 release", "FY2026-P01"): (20_000_000, 20_000_000),
        ("JET-14 promised", "FY2026-P02"): (150_000_000, 150_000_000),
        ("JET-14 release", "FY2026-P02"): (20_000_000, 20_000_000),
    }
    ctx = book_context(bundles.entity(months=6), book_code="ASC606", currency="USD")
    parts = part_targets(ctx, _state(), PartInputs(customer_consideration=targets))
    release = next(p for p in parts if (p.part, p.period_key) == ("JET-14 release", "FY2026-P01"))
    assert release.value_inputs == ((f"{ORDINARY}:{SUBJECT}:FY2026-P01", 1),)


def test_jet_14_release_part_cites_the_ordinary_node_only() -> None:
    # CHK-120 PROBABLE: 50,000.00 × 400,000.00 ÷ 1,000,000.00 = 20,000.00 in June; no ordinary
    # promise, so the payable and the ordinary release stay 0 and T = 0 + 20,000.00.
    targets = (
        _target(PAYABLE, "FY2026-P06", "0.00"),
        _target(ORDINARY, "FY2026-P06", "0.00"),
        _target(SHARE, "FY2026-P06", "20000.00"),
        _target(RELEASE, "FY2026-P06", "20000.00"),
    )
    found = _parts(targets)
    assert found == {
        ("JET-14 promised", "FY2026-P06"): (0, 0),
        ("JET-14 release", "FY2026-P06"): (0, 0),
        ("JET-14 share-based", "FY2026-P06"): (2_000_000, 2_000_000),
    }
    ctx = book_context(bundles.entity(months=6), book_code="ASC606", currency="USD")
    parts = part_targets(ctx, _state(), PartInputs(customer_consideration=targets))
    release = next(p for p in parts if p.part == "JET-14 release")
    assert release.value_inputs == ((f"{ORDINARY}:{SUBJECT}:FY2026-P06", 1),)
    share = next(p for p in parts if p.part == "JET-14 share-based")
    assert share.value_inputs == ((f"{SHARE}:{SUBJECT}:FY2026-P06", 1),)
    # P + E = T with no residue (S14-R-11): a composed release that is not the sum fails closed.
    broken = (*targets[:3], _target(RELEASE, "FY2026-P06", "20000.01"))
    with pytest.raises(EngineError, match="S14-R-11"):
        part_targets(ctx, _state(), PartInputs(customer_consideration=broken))


def _chk_133_world() -> InputBundle:
    """CHK-133 through ``compute``: REVENUE is mapped only for the product (the keys' industry
    mapping), so a contract-subject JET-14 line resolves through its contract's one product
    (L5-5-Q-8)."""
    inception = date(2026, 1, 1)
    month_end = date(2026, 1, 31)
    contract = "C-EX32"
    header = bundles.contract(
        contract,
        inception=inception,
        consideration_payable=[
            PayableInput(
                amount=Decimal("1500000.00"),
                promise_date=inception,
                related_obligation_keys=("L1-GOODS",),
                distinct_good_fair_value=None,
                committed_purchases=Decimal("15000000.00"),
                share_based=False,
            )
        ],
    )
    line = bundles.booking_line(
        "L1-GOODS",
        product_code="GOODS",
        quantity="15000000",
        total_price="15000000.00",
        end=inception,
    )
    invoice = {
        "invoice_number": "INV-1",
        "line_external_id": "INV-1-1",
        "obligation_key": "L1-GOODS",
        "amount": Decimal("2000000.00"),
        "issue_date": month_end,
    }
    delivery = {"obligation_key": "L1-GOODS", "quantity": Decimal("2000000"), "trigger": "DELIVERY"}
    keys = ["L1-GOODS"]
    events = (
        bundles.event(
            contract, 1, "CONTRACT_BOOKED", inception, {"lines": [line]}, obligation_keys=keys
        ),
        bundles.event(contract, 2, "CONTRACT_ACTIVATED", inception, {}),
        bundles.event(contract, 3, "DELIVERY_RECORDED", month_end, delivery, obligation_keys=keys),
        bundles.event(contract, 4, "BILLING_RECORDED", month_end, invoice, obligation_keys=keys),
    )
    calendar = bundles.entity(months=12)
    rules = tuple(
        MappingRuleInput(role, None, None, None, product, None, code, {}, 0, 1 if product else 0)
        for role, product, code in (
            ("CONSIDERATION_PAYABLE", None, "2400"),
            ("CONTRACT_ASSET", None, "1200"),
            ("CONTRACT_LIABILITY", None, "2100"),
            ("CUSTOMER_INCENTIVE_ASSET", None, "1210"),
            ("REVENUE", "GOODS", "4000"),
            ("UNBILLED_RECEIVABLE", None, "1105"),
        )
    )
    policy = "cpc.incentive_asset_release_basis"
    source = f"{contract}/policy_overrides/{policy}"
    override = ResolvedPolicyInput(
        policy, "CONTRACT", contract, "COMMITTED_PURCHASES", "C", source, "K"
    )
    policies = (*bundles.policy_set(book_code="ASC606", entity=calendar), override)
    book = BookInput(
        "ASC606",
        True,
        (ENTITY,),
        tuple(sorted(policies, key=lambda p: (p.code, p.scope, p.subject_key))),
        AccountMappingInput("MAP-CPC@v1", "0" * 64, rules),
    )
    template = TemplateInput(
        template_code="TPL-UNITS",
        version_key="TPL-UNITS@v1",
        version_no=1,
        content_sha256="0" * 64,
        obligation_kind="STANDARD",
        distinctness="distinct",
        series_increment_unit=None,
        satisfaction_pattern="POINT_IN_TIME",
        over_time_criterion="NOT_APPLICABLE",
        recognition_method="UNITS_DELIVERED",
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
    entry = SspEntryInput(
        entry_key="SSP-MAIN@v1/GOODS//-/USD",
        product_code="GOODS",
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
        ranges=(SspRangeInput("NONE", None, None, Decimal("1"), None, None, None),),
    )
    ssp = SspVersionInput(
        ssp_book_code="SSP-MAIN",
        version_key="SSP-MAIN@v1",
        version_no=1,
        resolution_mode="EFFECTIVE_DATE",
        legacy_version_label=None,
        effective_from_date=date(2025, 1, 1),
        effective_to_date=None,
        status="APPROVED",
        approved_at=datetime(2025, 12, 1, tzinfo=UTC),
        content_sha256="0" * 64,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=(entry,),
    )
    products = (bundles.product("GOODS", template_code="TPL-UNITS", family=None),)
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 1, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(book,),
        entities=(calendar,),
        group=bundles.group((header,), products=products),
        contracts=(header,),
        events=events,
        ssp_versions=(ssp,),
        pob_template_versions=(template,),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def test_chk_133_compute_posts_jet_14_and_nets_the_version() -> None:
    output = compute(_chk_133_world())
    (book,) = output.books
    version = book.contract_version.columns
    # S04-R-02 rev 1.3: gross obligation revenue 2,000,000.00 less the 200,000.00 release.
    assert (version["transaction_price"], version["consideration_payable_amount"]) == (
        1_350_000_000,
        -150_000_000,
    )
    (goods,) = book.obligation_versions
    assert goods.columns["revenue_cum"] == 200_000_000
    assert version["revenue_cum"] == 180_000_000
    january = next(b for b in book.balances if b.period_key == "FY2026-P01")
    assert january.subject_key == f"C-EX32@{ENTITY}"
    assert (
        january.columns["customer_incentive_asset_txn"],
        january.columns["consideration_payable_txn"],
    ) == (130_000_000, 150_000_000)
    # T-CON-09 functional columns at rate 1 for a same-currency entity (D-87 L6-5-Q-18).
    assert (
        january.columns["customer_incentive_asset_functional"],
        january.columns["consideration_payable_functional"],
    ) == (130_000_000, 150_000_000)
    net: dict[tuple[str, str], int] = {}
    products: dict[str, str | None] = {}
    for intent in book.posting_intents:
        if intent.posting_period_key != "FY2026-P01":
            continue
        for line in intent.lines:
            sign = 1 if line.side == "D" else -1
            key = (line.account_role, line.account_code)
            net[key] = net.get(key, 0) + sign * line.amount_txn
            if intent.subject_key == f"C-EX32@{ENTITY}":  # the JET-14 contract-subject lines
                products[line.account_role] = line.dimensions.get("product")
    assert {key: value for key, value in net.items() if value} == {
        ("CONSIDERATION_PAYABLE", "2400"): -150_000_000,
        ("CONTRACT_LIABILITY", "2100"): 200_000_000,
        ("CUSTOMER_INCENTIVE_ASSET", "1210"): 130_000_000,
        ("REVENUE", "4000"): -180_000_000,
    }
    assert products["REVENUE"] == "GOODS"  # the contract's one product (JET rule R3)


def test_a_release_without_its_payable_target_fails_closed() -> None:
    targets = (_target(ORDINARY, "FY2026-P01", "200000.00"),)
    ctx = book_context(bundles.entity(months=6), book_code="ASC606", currency="USD")
    with pytest.raises(ValueError, match="lacks its payable, ordinary or release target"):
        part_targets(ctx, _state(), PartInputs(customer_consideration=targets))


def test_jet_14_mixed_half_cent_parts_compose() -> None:
    """Contract 2.00, one unit delivered and invoiced; ordinary R 0.01 over 2.00 committed and a
    share element F 0.01 over E 2.00: O = S = 0.005 exact; P 0.01 (Dr REVENUE / Cr
    CUSTOMER_INCENTIVE_ASSET), E 0.01 (Dr REVENUE / Cr BILLING_CLEARING EQUITY), T 0.02, net revenue
    0.98, ``customer_incentive_asset`` 0.00, 0 trace mismatches (main T 0.01 / P 0.00 / net
    0.99)."""
    promises = [
        w.payable("0.01", w.JAN, (w.SUPPLY,), committed="2.00"),
        w.payable("0.01", w.JAN, (w.SUPPLY,), share_based=True),
    ]
    book = w.checked(
        w.units_world(
            [("D", w.Y1, "1"), ("I", w.Y1, "1.00")],
            [w.sbc_version(1, w.JAN, True, "2.00", fair="0.01")],
            promises=promises,
            quantity="2",
            overrides={w.RELEASE_BASIS: "COMMITTED_PURCHASES"},
        )
    )
    found = w.nodes(book)
    june = "FY2026-P06"
    assert found[f"{ORDINARY}:{w.SUBJECT}:{june}"].value == "0.01"
    assert found[f"{SHARE}:{w.SUBJECT}:{june}"].value == "0.01"
    assert found[f"{RELEASE}:{w.SUBJECT}:{june}"].value == "0.02"
    assert w.equity_credits(book) == {june: 1}
    assert w.role_net(book, "CUSTOMER_INCENTIVE_ASSET") == {"FY2026-P01": 1, june: -1}
    assert w.revenue_credits(book) == {june: 98}
    assert w.revenue_cum(book) == 98
    assert w.balance(book, june, "customer_incentive_asset_txn") == 0
    assert w.balance(book, june, "consideration_payable_txn") == 1


def test_jet_14_mixed_over_time_case_a() -> None:
    """DAILY SaaS 1,200,000.00 with a share element (F 50,000 / E 1,200,000) and an ordinary
    promise (R 10,000 over 900,000 committed) invoiced 300,000.00 on 1 Jan / 1 Apr / 1 Jul / 1 Oct:
    ordinary release 3,333.33 / 6,666.67 / 10,000.00 at P01 / P04 / P07 (asset movements
    +6,666.67, −3,333.34, −3,333.33 and no ±0.01 elsewhere), share credits as the S4 list, T at P02
    = 3,333.33 + 8,082.19 = 11,415.52 and at P04 = 6,666.67 + 16,438.36 = 23,105.03 (main 11,415.53
    / 23,105.02); ``contract_version.revenue_cum`` 849,178.08 at d_v 1 October (period-end
    basis)."""
    promises = [
        w.payable("10000.00", w.JAN, ("L1-SAAS",), committed="900000.00"),
        w.payable("50000.00", w.JAN, ("L1-SAAS",), share_based=True),
    ]
    book = w.checked(
        w.saas_world(
            [(date(2026, m, 1), "300000.00") for m in (1, 4, 7, 10)],
            [w.sbc_version(1, w.JAN, True, "1200000.00", obligation_key="L1-SAAS")],
            promises=promises,
            overrides={w.RELEASE_BASIS: "COMMITTED_PURCHASES"},
        )
    )
    found = w.nodes(book)
    ordinary = {p: found[f"{ORDINARY}:{w.SUBJECT}:FY2026-P{p:02d}"].value for p in (1, 4, 7)}
    assert ordinary == {1: "3333.33", 4: "6666.67", 7: "10000.00"}
    assert w.role_net(book, "CUSTOMER_INCENTIVE_ASSET") == {
        "FY2026-P01": 666_667,
        "FY2026-P04": -333_334,
        "FY2026-P07": -333_333,
    }
    assert w.equity_credits(book) == {
        "FY2026-P01": 424_658,
        "FY2026-P02": 383_561,
        "FY2026-P03": 424_658,
        "FY2026-P04": 410_959,
        "FY2026-P05": 424_657,
        "FY2026-P06": 410_959,
        "FY2026-P07": 424_658,
        "FY2026-P08": 424_657,
        "FY2026-P09": 410_959,
        "FY2026-P10": 424_658,
        "FY2026-P11": 410_958,
        "FY2026-P12": 424_658,
    }
    assert found[f"{RELEASE}:{w.SUBJECT}:FY2026-P02"].value == "11415.52"
    assert found[f"{RELEASE}:{w.SUBJECT}:FY2026-P04"].value == "23105.03"
    assert w.revenue_cum(book) == 84_917_808
