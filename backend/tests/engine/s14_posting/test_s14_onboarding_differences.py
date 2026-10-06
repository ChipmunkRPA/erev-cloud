"""The stage 14 onboarding-difference mapping (ENGINE_SPEC S07-R-07 rev 1.17; ENGINE_SPEC_B
S14-R-26 rev 1.18; ONB-DIFF-ROLES): the imported role amounts of every S07-R-07 family and the
refusals the template cannot map. No database (DG-TST-18)."""

from __future__ import annotations

import dataclasses
from datetime import date
from fractions import Fraction
from types import MappingProxyType

from erev_engine.stages.s14_posting import onboarding
from erev_engine.stages.s14_posting.targets import PartTarget
from support import bundles
from support import onboarding_worlds as w
from support.recognition import book_context


def _part(
    part: str, amount: int, *, counterparty: str | None = None, currency: str = "USD"
) -> PartTarget:
    weights = ()
    if part.startswith("JET-03"):
        weights = (("CONTRACT_LIABILITY", Fraction(amount)), ("SALES_TAX_PAYABLE", Fraction(0)))
    if part == "JET-02 agent":
        weights = (("REVENUE", Fraction(3)), ("BILLING_CLEARING", Fraction(1)))
    return PartTarget(
        book_code="ASC606",
        entity=bundles.ENTITY_CODE,
        subject_key=w.SUBJECT,
        part=part,
        component=None,
        period_key="FY2025-P12",
        txn_currency="USD",
        amount_txn=amount,
        functional_currency=currency,
        amount_functional=amount,
        counterparty_entity=counterparty,
        by_cause=(),
        rates=(),
        node_ids=(),
        weights=weights,
    )


def test_imported_role_amounts_cover_every_s07_r07_family_and_refuse_unmappable_parts() -> None:
    """The mapping module: refund liabilities (JET-04b) and return assets (JET-07c) import 0 on
    both roles (their whole recomputed cumulative is the difference); deposits import the
    baseline's deposit_liability on the receipt part; ENGINE billing imports billed_cum on the
    receivable and the contract liability with tax 0; revenue imports revenue_cum; a family outside
    S07-R-07 (JET-14 promised) is absent (deemed posted); JET-02 agent, an intercompany
    counterparty and a foreign functional currency are refused with ONBOARDING_DIFFERENCE_UNPOSTED
    bound to the obligation and the opening event."""
    ctx = book_context(bundles.entity(start=date(2025, 1, 1), months=24))
    opening = onboarding.Opening(
        date(2025, 12, 31),
        onboarding.RECOMPUTE,
        f"{w.CONTRACT}/EV-000003",
        MappingProxyType(
            {"revenue_cum": 12000000, "billed_cum": 20000000, "deposit_liability": 50000}
        ),
        w.CONTRACT,
        w.SUBJECT,
    )
    found = {w.SUBJECT: opening}
    recomputed = frozenset({w.SUBJECT})
    parts = [
        _part("JET-04b", 500000),
        _part("JET-07c", 300000),
        _part("JET-01b receipt", 120000),
        _part("JET-03 invoice", 24000000),
        _part("JET-02 principal", 13000000),
        _part("JET-14 promised", 700000),
    ]
    imported, refusals = onboarding.imported_role_amounts(ctx, parts, found, recomputed)
    by_role = {
        (key.entry_kind, key.account_role): (value.status, value.imported, value.recomputed)
        for key, value in imported.items()
    }
    E, D = onboarding.ELIGIBLE, onboarding.DEEMED_POSTED
    # JET-04b and JET-07c import 0 (the payload carries no member) and stay ELIGIBLE with the
    # whole recomputed cumulative as their difference (C5-PH2-R1: a zero import is eligible);
    # JET-14 promised (outside S07-R-07) is DEEMED_POSTED, never an imported 0.
    assert onboarding.FAMILIES["JET-04b"] == onboarding.ZERO
    assert onboarding.FAMILIES["JET-07c"] == onboarding.ZERO
    assert by_role == {
        ("REFUND_LIABILITY", "CONTRACT_LIABILITY"): (E, (0, 0), (500000, 500000)),
        ("REFUND_LIABILITY", "REFUND_LIABILITY"): (E, (0, 0), (-500000, -500000)),
        ("RETURN_ASSET", "RETURN_ASSET"): (E, (0, 0), (300000, 300000)),
        ("RETURN_ASSET", "COST_OF_REVENUE"): (E, (0, 0), (-300000, -300000)),
        ("DEPOSIT", "BILLING_CLEARING"): (E, (50000, 50000), (120000, 120000)),
        ("DEPOSIT", "DEPOSIT_LIABILITY"): (E, (-50000, -50000), (-120000, -120000)),
        ("BILLING", "ACCOUNTS_RECEIVABLE"): (E, (20000000, 20000000), (24000000, 24000000)),
        ("BILLING", "CONTRACT_LIABILITY"): (E, (-20000000, -20000000), (-24000000, -24000000)),
        ("REVENUE_RECOGNITION", "CONTRACT_LIABILITY"): (
            E,
            (12000000, 12000000),
            (13000000, 13000000),
        ),
        ("REVENUE_RECOGNITION", "REVENUE"): (E, (-12000000, -12000000), (-13000000, -13000000)),
        ("CONSIDERATION_PAYABLE", "CUSTOMER_INCENTIVE_ASSET"): (D, (0, 0), (0, 0)),
        ("CONSIDERATION_PAYABLE", "CONSIDERATION_PAYABLE"): (D, (0, 0), (0, 0)),
    }
    assert refusals == ()
    # Without ENGINE lines recomputed through the cutover the imported billing is the ERP's:
    # JET-03 maps nothing (S10-R-03; the baseline stands in billed_cum, no difference).
    erp_only, none = onboarding.imported_role_amounts(
        ctx, [_part("JET-03 invoice", 24000000)], found, frozenset()
    )
    assert ({k.account_role: v.status for k, v in erp_only.items()}, none) == (
        {"ACCOUNTS_RECEIVABLE": D, "CONTRACT_LIABILITY": D},
        (),
    )
    # An omitted deposit member is never read as 0: a non-zero recomputed deposit refuses with
    # ONBOARDING_MEMBER_MISSING; a zero recomputed deposit maps nothing and records nothing.
    absent = dataclasses.replace(
        opening,
        members=MappingProxyType(
            {"revenue_cum": 12000000, "billed_cum": 20000000, "deposit_liability": None}
        ),
    )
    nothing, missing = onboarding.imported_role_amounts(
        ctx, [_part("JET-01b receipt", 120000)], {w.SUBJECT: absent}, recomputed
    )
    assert {k.account_role: v.status for k, v in nothing.items()} == {
        "BILLING_CLEARING": onboarding.REFUSED,
        "DEPOSIT_LIABILITY": onboarding.REFUSED,
    }
    assert [(f.code, f.subject_key, f.event_key, f.detail) for f in missing] == [
        (
            "ONBOARDING_MEMBER_MISSING",
            w.SUBJECT,
            absent.event_key,
            {
                "cutover_date": "2025-12-31",
                "member": "deposit_liability",
                "part": "JET-01b receipt",
                "recomputed": "120000",
                "rule": "S07-R-07",
            },
        )
    ]
    quiet, none = onboarding.imported_role_amounts(
        ctx, [_part("JET-01b receipt", 0)], {w.SUBJECT: absent}, recomputed
    )
    assert (dict(quiet), none) == ({}, ())
    # An omitted billed_cum where ENGINE lines are recomputed through the cutover refuses the same
    # way (D-98 candidate 35, P2-Q-5); without recomputed ENGINE lines JET-03 stays deemed posted.
    no_billing = dataclasses.replace(
        opening,
        members=MappingProxyType(
            {"revenue_cum": 12000000, "billed_cum": None, "deposit_liability": 50000}
        ),
    )
    _, missing_billing = onboarding.imported_role_amounts(
        ctx, [_part("JET-03 invoice", 24000000)], {w.SUBJECT: no_billing}, recomputed
    )
    assert [(f.code, f.detail["member"], f.detail["part"]) for f in missing_billing] == [
        ("ONBOARDING_MEMBER_MISSING", "billed_cum", "JET-03 invoice")
    ]
    erp, silent = onboarding.imported_role_amounts(
        ctx, [_part("JET-03 invoice", 24000000)], {w.SUBJECT: no_billing}, frozenset()
    )
    assert ({v.status for v in erp.values()}, silent) == ({D}, ())
    states, refused = onboarding.imported_role_amounts(
        ctx,
        [
            _part("JET-02 agent", 100),
            _part("JET-04b", 100, counterparty="US02"),
            _part("JET-07c", 100, currency="EUR"),
        ],
        found,
        recomputed,
    )
    assert dict(states) == {}  # unmappable parts record findings, no key state (CV-15 blocks)
    assert [
        (f.code, f.severity, f.subject_key, f.event_key, f.detail["part"], f.detail["reason"])
        for f in refused
    ] == [
        (
            "ONBOARDING_DIFFERENCE_UNPOSTED",
            "ERROR",
            w.SUBJECT,
            f"{w.CONTRACT}/EV-000003",
            "JET-02 agent",
            "agent_split",
        ),
        (
            "ONBOARDING_DIFFERENCE_UNPOSTED",
            "ERROR",
            w.SUBJECT,
            f"{w.CONTRACT}/EV-000003",
            "JET-04b",
            "intercompany",
        ),
        (
            "ONBOARDING_DIFFERENCE_UNPOSTED",
            "ERROR",
            w.SUBJECT,
            f"{w.CONTRACT}/EV-000003",
            "JET-07c",
            "foreign_currency",
        ),
    ]
