"""Share-based consideration payable measured from posted related revenue in stage 10 (ENGINE_SPEC
S04-R-17 rev 1.6; ENGINE_SPEC_B S10-R-26, §10.5; POLICIES PT-10 CHK-120, POL-246; 04 T-CON-13,
table 15.4-C ``CPC_RELATED_SCOPE_INVALID``; D-91 C606-03).

Main measured the reduction on related purchases invoiced from the grant date: 400,000.00 invoiced
without a delivery posted Dr REVENUE 20,000.00 with ``contract_version.revenue_cum`` −20,000.00,
and 400,000.00 delivered without an invoice posted nothing. The ruling reads R(t) as the POSTED
stage 09 ``revenue_cum`` of the related obligations at the latest performing-period end ≤ t less
the posted stage 10 ``concession_created_cum`` that the selected revenue node cannot yet contain
(a concession created after the node's own performing cutoff; the supervisor's count-once ruling on
L9-ENG-B3-Q-1), per element Red_e(t) = round_half_up(min(F, F × R ÷ E)), 0 while t < grant or
vesting is not probable, element node ``tp.cpc_share_based.v1`` and posted sums
``tp.cpc_release.v1``. Full ``compute`` worlds, no database; every trace is replayed by
``reevaluate`` (PROP:P14). Figures: ``.run/l9/d91-c606-03-b3/derive-output.json``.
"""

from __future__ import annotations

from datetime import date
from fractions import Fraction

import pytest
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, to_fraction
from erev_engine.trace import SourceRef, reevaluate
from support import cpc_worlds as w
from support.cpc_worlds import D1, D2, JAN, KEY, SUBJECT, SUPPLY, WARRANT, Y1, Y2

ELEMENT_NODE = f"share_based_reduction_element_cum:{KEY}"
SHARE_NODE = f"share_based_reduction_cum:{SUBJECT}"
RELEASE_NODE = f"incentive_release_cum:{SUBJECT}"
ORDINARY_NODE = f"incentive_release_ordinary_cum:{SUBJECT}"
REVENUE_NODE = f"revenue_cum:{WARRANT}/{SUPPLY}"
CONCESSION_NODE = f"concession_created_cum:{WARRANT}/{SUPPLY}"
CPC_MEASURES = (
    "consideration_payable",
    "incentive_release_ordinary_cum",
    "customer_incentive_asset",
    "share_based_reduction_element_cum",
    "share_based_reduction_cum",
    "incentive_release_cum",
)
V1 = w.sbc_version(1, JAN, True, "1000000.00")
TWO_YEARS = [
    ("D", Y1, "400000"),
    ("I", Y1, "400000.00"),
    ("D", Y2, "600000"),
    ("I", Y2, "600000.00"),
]
DELAYED = [("D", Y1, "400000"), ("I", D1, "400000.00"), ("D", Y2, "600000"), ("I", D2, "600000.00")]
P = "FY2026-P{:02d}".format


def test_matched_advance_and_unbilled_purchases() -> None:
    """CHK-120 first year: the reduction follows the 400,000.00 of related revenue, whether the
    invoice matches the delivery, precedes it or never comes (D-91 (1); the Codex table)."""
    matched = w.checked(w.units_world([("D", Y1, "400000"), ("I", Y1, "400000.00")], [V1]))
    assert w.equity_credits(matched) == {P(6): 2_000_000}
    assert w.revenue_cum(matched) == 38_000_000
    advance = w.checked(w.units_world([("I", Y1, "400000.00")], [V1]))
    assert w.equity_credits(advance) == {}
    assert w.revenue_cum(advance) == 0
    assert w.revenue_credits(advance) == {}
    unbilled = w.checked(w.units_world([("D", Y1, "400000")], [V1]))
    assert w.equity_credits(unbilled) == {P(6): 2_000_000}
    assert w.revenue_cum(unbilled) == 38_000_000
    assert w.revenue_credits(unbilled) == {P(6): 38_000_000}


def test_billing_timing_invariance_s1_s2_s3() -> None:
    """S1 advance and S2 delayed billing post the same credits as the matched key; invoices alone
    move nothing (S3a) and deliveries alone move everything (S3b)."""
    advance = [
        ("I", date(2026, 1, 31), "400000.00"),
        ("D", Y1, "400000"),
        ("I", date(2027, 1, 31), "600000.00"),
        ("D", Y2, "600000"),
    ]
    for steps in (advance, DELAYED):
        book = w.checked(w.units_world(steps, [V1]))
        assert w.equity_credits(book) == {P(6): 2_000_000, "FY2027-P06": 3_000_000}
    invoices_only = w.checked(w.units_world([("I", Y1, "400000.00"), ("I", Y2, "600000.00")], [V1]))
    assert (w.equity_credits(invoices_only), w.revenue_cum(invoices_only)) == ({}, 0)
    deliveries_only = w.checked(w.units_world([("D", Y1, "400000"), ("D", Y2, "600000")], [V1]))
    assert w.equity_credits(deliveries_only) == {P(6): 2_000_000, "FY2027-P06": 3_000_000}
    assert w.revenue_cum(deliveries_only) == 95_000_000


# The DAILY 12-month service of 1,200,000.00: deltas of round_half_up(50,000 × elapsed ÷ 365).
MONTHLY_CREDITS = {
    P(1): 424_658,
    P(2): 383_561,
    P(3): 424_658,
    P(4): 410_959,
    P(5): 424_657,
    P(6): 410_959,
    P(7): 424_658,
    P(8): 424_657,
    P(9): 410_959,
    P(10): 424_658,
    P(11): 410_958,
    P(12): 424_658,
}


def test_over_time_daily_service_quarterly_in_advance_and_single_in_arrears() -> None:
    """S4 quarterly in advance and S5 once in arrears post identical monthly credits summing to
    50,000.00. S4's version date is 1 October 2026 (its last invoice):
    ``contract_version.revenue_cum`` = 900,821.92 at d_v less the 41,643.84 release of the period
    holding d_v = 859,178.08 (period-end-basis-dependent, S04-R-02 rev 1.6; the d_v-consistent
    863,287.67 is post-rc)."""
    version = w.sbc_version(1, JAN, True, "1200000.00", obligation_key="L1-SAAS")
    quarterly = [(date(2026, m, 1), "300000.00") for m in (1, 4, 7, 10)]
    s4 = w.checked(w.saas_world(quarterly, [version]))
    assert w.equity_credits(s4) == MONTHLY_CREDITS
    assert sum(MONTHLY_CREDITS.values()) == 5_000_000
    assert w.revenue_cum(s4) == 85_917_808
    s5 = w.checked(w.saas_world([(date(2026, 12, 31), "1200000.00")], [version]))
    assert w.equity_credits(s5) == MONTHLY_CREDITS
    assert w.revenue_cum(s5) == 115_000_000
    assert w.node_values(s4, "share_based_reduction_element_cum") == w.node_values(
        s5, "share_based_reduction_element_cum"
    )


def test_unrelated_obligation_excluded_s6() -> None:
    """Only the promise's related obligation drives the numerator; an empty related list means
    every obligation of the contract (D-91 (3))."""
    steps = [
        ("D", Y1, "400000", SUPPLY),
        ("D", Y1, "400000", "L2-OTHER"),
        ("I", Y1, "400000.00", "L2-OTHER"),
        ("I", D1, "400000.00", SUPPLY),
    ]
    related = w.checked(w.units_world(steps, [V1], extra_line=True))
    assert w.equity_credits(related) == {P(6): 2_000_000}
    assert w.revenue_cum(related) == 78_000_000
    element = w.nodes(related)[f"{ELEMENT_NODE}:{P(6)}"]
    assert [item for item in element.inputs if isinstance(item, str)] == [f"{REVENUE_NODE}:{P(6)}"]
    # An empty promise list means every obligation; the element then names none either (equality
    # of the two scopes, D-91 (3)).
    every = w.checked(
        w.units_world(
            steps,
            [w.sbc_version(1, JAN, True, "1000000.00", obligation_key=None)],
            extra_line=True,
            promises=[w.payable("50000.00", JAN, (), share_based=True)],
        )
    )
    assert w.equity_credits(every) == {P(6): 4_000_000}
    element = w.nodes(every)[f"{ELEMENT_NODE}:{P(6)}"]
    assert sorted(item for item in element.inputs if isinstance(item, str)) == [
        f"{REVENUE_NODE}:{P(6)}",
        f"revenue_cum:{WARRANT}/L2-OTHER:{P(6)}",
    ]


def test_vesting_probable_not_probable_probable_s7() -> None:
    """The version pinned at each period end decides: +20,000 (P06-26), −20,000 (P12-26), +20,000
    (P03-27), +30,000 (P06-27); a compute truncated at each cutoff reproduces the closed periods."""
    v2 = w.sbc_version(2, D1, False, "1000000.00", supersedes=V1.version_key)
    v3 = w.sbc_version(3, date(2027, 3, 31), True, "1000000.00", supersedes=v2.version_key)
    bundle = w.units_world(DELAYED, [V1, v2, v3])
    full = w.checked(bundle)
    expected = {
        P(6): 2_000_000,
        P(12): -2_000_000,
        "FY2027-P03": 2_000_000,
        "FY2027-P06": 3_000_000,
    }
    assert w.equity_credits(full) == expected
    assert w.revenue_cum(full) == 95_000_000
    for cutoff in (Y1, D1, date(2027, 3, 31), Y2):
        replay = w.checked(w.truncated(bundle, cutoff))
        limit = f"FY{cutoff.year}-P{cutoff.month:02d}"
        closed = {k: v for k, v in expected.items() if k <= limit}
        assert {k: v for k, v in w.equity_credits(replay).items() if k <= limit} == closed


def test_expected_related_revenue_change_s8() -> None:
    """E 1,000,000 → 2,000,000 at 31 December 2026: cumulative catch-up −10,000.00 (10,000.00
    cumulative), then +15,000.00 (25,000.00 cumulative); revenue_cum 975,000.00."""
    v2 = w.sbc_version(2, D1, True, "2000000.00", supersedes=V1.version_key)
    book = w.checked(w.units_world(DELAYED, [V1, v2]))
    assert w.equity_credits(book) == {P(6): 2_000_000, P(12): -1_000_000, "FY2027-P06": 1_500_000}
    assert w.revenue_cum(book) == 97_500_000
    element = w.nodes(book)[f"{ELEMENT_NODE}:{P(12)}"]
    assert (element.params["expected"], element.value) == ("2000000", "10000.00")


def test_grant_after_performance_later_of_s9() -> None:
    """POL-246 LATER_OF: a grant on 1 July 2026 after 400,000.00 delivered on 30 June reduces
    revenue by 20,000.00 at FY2026-P07 and 30,000.00 at FY2027-P06 (never the FROM_GRANT
    30,000.00 / 970,000.00)."""
    grant = date(2026, 7, 1)
    version = w.sbc_version(1, grant, True, "1000000.00", grant="2026-07-01")
    promise = w.payable("50000.00", grant, (SUPPLY,), share_based=True)
    book = w.checked(w.units_world(TWO_YEARS, [version], promises=[promise]))
    assert w.equity_credits(book) == {P(7): 2_000_000, "FY2027-P06": 3_000_000}
    assert w.revenue_cum(book) == 95_000_000
    assert f"{ELEMENT_NODE}:{P(6)}" not in w.nodes(book)  # the series opens at the grant
    july = w.nodes(book)[f"{ELEMENT_NODE}:{P(7)}"]
    assert (july.params["grant_date"], july.params["period_end"], july.params["timing"]) == (
        "2026-07-01",
        "2026-07-31",
        "LATER_OF_RELATED_REVENUE_AND_GRANT",
    )


def test_mid_period_grant_counts_period_revenue() -> None:
    """A grant on 15 July after a 10 July delivery counts that period's revenue at its end."""
    grant = date(2026, 7, 15)
    version = w.sbc_version(1, grant, True, "1000000.00", grant="2026-07-15")
    promise = w.payable("50000.00", grant, (SUPPLY,), share_based=True)
    steps = [("D", date(2026, 7, 10), "400000"), ("I", date(2026, 7, 10), "400000.00")]
    book = w.checked(w.units_world(steps, [version], promises=[promise]))
    assert w.equity_credits(book) == {P(7): 2_000_000}


def _fractional(currency: str, fair: str, expected: str) -> tuple[dict[str, int], dict[str, str]]:
    version = w.sbc_version(1, JAN, True, expected, fair=fair, currency=currency)
    promise = w.payable(fair, JAN, (SUPPLY,), share_based=True)
    steps = [
        ("D", date(2026, 3, 31), "123457"),
        ("D", date(2026, 9, 30), "456789"),
        ("D", date(2027, 3, 31), "419754"),
        ("I", D2, expected.split(".")[0].replace("900000", "1000000")),
    ]
    book = w.checked(w.units_world(steps, [version], promises=[promise], currency=currency))
    return w.equity_credits(book), w.node_values(book, "share_based_reduction_element_cum")


def test_fractional_cap_usd_jpy_bhd_s10() -> None:
    """F 33,333.33 / E 900,000 over 123,457 / 456,789 / 419,754 units: cumulative 4,572.48 /
    21,490.59 / 33,333.33 (exact 137174430727/30000000, 322358856653/15000000, the cap), deltas
    4,572.48 / 16,918.11 / 11,842.74; JPY 4,572 / 16,918 / 11,843; BHD 4,572.481 / 16,918.111 /
    11,842.741 (CV-35 at each minor unit)."""
    credits, values = _fractional("USD", "33333.33", "900000.00")
    assert credits == {P(3): 457_248, P(9): 1_691_811, "FY2027-P03": 1_184_274}
    assert (values[f"{ELEMENT_NODE}:{P(3)}"], values[f"{ELEMENT_NODE}:{P(9)}"]) == (
        "4572.48",
        "21490.59",
    )
    assert values[f"{ELEMENT_NODE}:FY2027-P03"] == "33333.33"
    credits, values = _fractional("JPY", "33333", "900000")
    assert credits == {P(3): 4572, P(9): 16918, "FY2027-P03": 11843}
    assert values[f"{ELEMENT_NODE}:{P(9)}"] == "21490"
    credits, values = _fractional("BHD", "33333.333", "900000.000")
    assert credits == {P(3): 4_572_481, P(9): 16_918_111, "FY2027-P03": 11_842_741}
    assert values[f"{ELEMENT_NODE}:{P(9)}"] == "21490.592"


def test_fractional_cap_exact_residues() -> None:
    """The USD element nodes carry the exact cumulative as value plus residue."""
    version = w.sbc_version(1, JAN, True, "900000.00", fair="33333.33")
    promise = w.payable("33333.33", JAN, (SUPPLY,), share_based=True)
    steps = [("D", date(2026, 3, 31), "123457"), ("D", date(2026, 9, 30), "456789")]
    book = w.checked(w.units_world(steps, [version], promises=[promise]))
    found = w.nodes(book)
    for period, exact in (
        (P(3), Fraction(137174430727, 30000000)),
        (P(9), Fraction(322358856653, 15000000)),
    ):
        node = found[f"{ELEMENT_NODE}:{period}"]
        assert node.rounding_residue == format_exact(exact - to_fraction(node.value))


def test_numerator_posted_basis_threshold() -> None:
    """A DAILY obligation of 14,600,007.28 at day 1 of 365 (a term from 31 January 2026) has exact
    related revenue 365000182/9125 and posted 40,000.02; with F 12,500.00 / E 50,000.00 the element
    is 10,000.01 on the posted basis in the stored value AND its replay (the exact basis would give
    10,000.00, which is never produced; D-91 (1))."""
    start, end = date(2026, 1, 31), date(2027, 1, 30)
    version = w.sbc_version(
        1, start, True, "50000.00", fair="12500.00", grant="2026-01-31", obligation_key="L1-SAAS"
    )
    promise = w.payable("12500.00", start, ("L1-SAAS",), share_based=True)
    book = w.checked(
        w.saas_world([], [version], promises=[promise], start=start, end=end, total="14600007.28")
    )
    found = w.nodes(book)
    revenue = found[f"revenue_cum:{WARRANT}/L1-SAAS:{P(1)}"]
    assert revenue.value == "40000.02"
    assert revenue.rounding_residue == format_exact(
        Fraction(365000182, 9125) - to_fraction(revenue.value)
    )
    element = found[f"{ELEMENT_NODE}:{P(1)}"]
    assert element.value == "10000.01"
    assert reevaluate(book.trace)[element.id] == "10000.01"
    assert "10000.00" not in {element.value, reevaluate(book.trace)[element.id]}
    assert w.equity_credits(book)[P(1)] == 1_000_001


def test_return_lowers_related_revenue() -> None:
    """Returns lower R(t) through the stage 09 revenue target: 100,000 units returned in July
    give Dr EQUITY 5,000.00 (cumulative 15,000.00) and net revenue 285,000.00; case C (50,000
    returned 30 September) gives −2,500.00 at FY2026-P09 (17,500.00), +30,000.00 at FY2027-P06 and
    revenue_cum 902,500.00."""
    codex = w.checked(
        w.units_world(
            [("D", Y1, "400000"), ("I", Y1, "400000.00"), ("R", date(2026, 7, 31), "100000")], [V1]
        )
    )
    assert w.equity_credits(codex) == {P(6): 2_000_000, P(7): -500_000}
    assert w.revenue_cum(codex) == 28_500_000
    case_c = w.checked(
        w.units_world(
            [
                ("D", Y1, "400000"),
                ("I", Y1, "400000.00"),
                ("R", date(2026, 9, 30), "50000"),
                ("D", Y2, "600000"),
                ("I", Y2, "600000.00"),
            ],
            [V1],
        )
    )
    assert w.equity_credits(case_c) == {P(6): 2_000_000, P(9): -250_000, "FY2027-P06": 3_000_000}
    assert w.revenue_cum(case_c) == 90_250_000


def _concession_world(
    quantity: str = "1000000", *, named: bool = True, on: date = date(2026, 8, 31)
):
    """CHK-120 with a JET-05c CONCESSION of 50,000.00 on L1-SUPPLY: ``named`` prices the delivered
    portion of the partially delivered 1,000,000-unit obligation (S06-R-09 delivered portion);
    ``quantity`` 400,000 without a line is the Codex fixture (fully delivered and billed)."""
    modification = w.concession("-50000.00", on, named=named)
    steps = [
        ("D", Y1, "400000"),
        ("I", Y1, "400000.00"),
        ("A", on, "MOD-CONCESSION-1"),
    ]
    if quantity == "1000000":
        steps.extend([("D", Y2, "600000"), ("I", Y2, "600000.00")])
    return w.units_world(steps, [V1], modifications=[modification], quantity=quantity)


def test_post_satisfaction_concession_counts_once() -> None:
    """A JET-05c CONCESSION of 50,000.00 on L1-SUPPLY at 31 August 2026 on one calendar: stage 06
    applies the negative share to the recognition segment, so the selected stage 09 node (cutoff
    31 August) is already 350,000.00 and contains the concession created on 31 August; the element
    cites the revenue node only (no concession input, ``concessions_embedded`` 1) and counts the
    concession once (supervisor ruling on L9-ENG-B3-Q-1)."""
    book = w.checked(_concession_world())
    found = w.nodes(book)
    assert found[f"{REVENUE_NODE}:{P(8)}"].value == "350000.00"
    assert found[f"{CONCESSION_NODE}:{P(8)}"].value == "50000.00"
    element = found[f"{ELEMENT_NODE}:{P(8)}"]
    assert [item for item in element.inputs if isinstance(item, str)] == [f"{REVENUE_NODE}:{P(8)}"]
    assert (element.params["signs"], element.params["concessions_embedded"]) == ("+", "1")
    assert element.params["revenue_cutoff"] == "2026-08-31"  # the selected node's own cutoff
    assert element.value == "17500.00"
    assert w.role_net(book, "REFUND_LIABILITY", credit=True) == {P(8): 5_000_000}


def test_post_satisfaction_concession_lowers_related_revenue() -> None:
    """D-91 (1) figures: R(Aug) 350,000 → cumulative 17,500.00, movement −2,500.00 at FY2026-P08;
    FY2027-P06 47,500.00 (+30,000.00); ``contract_version.revenue_cum`` 902,500.00 (the obligation's
    ``revenue_cum`` 950,000.00 already carries the concession, less 47,500.00)."""
    book = w.checked(_concession_world())
    assert w.equity_credits(book) == {P(6): 2_000_000, P(8): -250_000, "FY2027-P06": 3_000_000}
    assert w.nodes(book)[f"{SHARE_NODE}:FY2027-P06"].value == "47500.00"
    assert w.revenue_cum(book) == 90_250_000


def test_codex_post_satisfaction_concession_fully_delivered() -> None:
    """The Codex blocker fixture: a fully delivered and billed 400,000.00 contract, award F 50,000
    / E 1,000,000 (June reduction 20,000.00), then an August PRICE_CHANGE of −50,000.00 settled by
    CREDIT_OR_REFUND. Related revenue 350,000.00 (counted once), cumulative reduction 17,500.00,
    August equity movement −2,500.00, net revenue journal and ``contract_version.revenue_cum``
    332,500.00 (main on 554c7aa: 300,000.00 / 15,000.00 / −5,000.00 / 335,000.00)."""
    book = w.checked(_concession_world("400000", named=False))
    found = w.nodes(book)
    assert found[f"{REVENUE_NODE}:{P(8)}"].value == "350000.00"
    assert found[f"{CONCESSION_NODE}:{P(8)}"].value == "50000.00"
    assert found[f"{ELEMENT_NODE}:{P(8)}"].value == "17500.00"
    assert [item for item in found[f"{ELEMENT_NODE}:{P(8)}"].inputs if isinstance(item, str)] == [
        f"{REVENUE_NODE}:{P(8)}"
    ]
    assert w.equity_credits(book) == {P(6): 2_000_000, P(8): -250_000}
    assert w.revenue_credits(book) == {P(6): 38_000_000, P(8): -4_750_000}
    assert sum(w.revenue_credits(book).values()) == 33_250_000
    assert w.role_net(book, "REFUND_LIABILITY", credit=True) == {P(8): 5_000_000}
    assert w.revenue_cum(book) == 33_250_000


def test_two_elements_sum_and_round_per_element() -> None:
    """Elements of 50,000.00 and 10,000.00 (E 1,000,000.00 each): 24,000.00 at FY2026-P06 and
    36,000.00 at FY2027-P06, revenue_cum 940,000.00, the aggregate node the signed sum of the two
    element nodes; two elements each exactly 0.005 post E = 0.02, not 0.01 (D-91 (5))."""
    second_key = f"{WARRANT}/SBC-2"
    v_second = w.sbc_version(
        1, JAN, True, "1000000.00", key=second_key, element="SBC-2", fair="10000.00"
    )
    promises = [
        w.payable("50000.00", JAN, (SUPPLY,), share_based=True),
        w.payable("10000.00", JAN, (SUPPLY,), share_based=True),
    ]
    book = w.checked(w.units_world(DELAYED, [V1, v_second], promises=promises))
    assert w.equity_credits(book) == {P(6): 2_400_000, "FY2027-P06": 3_600_000}
    assert w.revenue_cum(book) == 94_000_000
    found = w.nodes(book)
    aggregate = found[f"{SHARE_NODE}:{P(6)}"]
    # Element nodes in sorted element-key order: SBC-2 before SBC-WARRANT.
    assert list(aggregate.inputs) == [
        f"share_based_reduction_element_cum:{second_key}:{P(6)}",
        f"{ELEMENT_NODE}:{P(6)}",
    ]
    assert (aggregate.formula_id, aggregate.params["signs"], aggregate.value) == (
        "tp.cpc_release.v1",
        "+,+",
        "24000.00",
    )
    assert found[f"share_based_reduction_element_cum:{second_key}:{P(6)}"].value == "4000.00"
    # Half-cent: a 2-unit contract at 1.00, one unit delivered; two elements F 0.01 / E 2.00.
    tiny = [
        w.sbc_version(1, JAN, True, "2.00", fair="0.01"),
        w.sbc_version(1, JAN, True, "2.00", key=second_key, element="SBC-2", fair="0.01"),
    ]
    tiny_promises = [w.payable("0.01", JAN, (SUPPLY,), share_based=True)] * 2
    half = w.checked(
        w.units_world(
            [("D", Y1, "1"), ("I", Y1, "1.00")], tiny, promises=tiny_promises, quantity="2"
        )
    )
    assert w.equity_credits(half) == {P(6): 2}
    assert w.nodes(half)[f"{SHARE_NODE}:{P(6)}"].value == "0.02"
    assert w.revenue_cum(half) == 98


def _scope_error(bundle) -> tuple[str, str]:
    with pytest.raises(EngineError) as raised:
        w.run(bundle)
    error = raised.value
    findings = error.detail.get("findings", "")
    reason = "UNKNOWN_OBLIGATION" if "UNKNOWN_OBLIGATION" in findings else "MISMATCH"
    return error.code, reason


def test_scope_validation_and_pairing() -> None:
    """Element keys, when set, must name obligations of the contract and equal the promise scope
    (D-91 (3); 04 table 15.4-C; PRD IMP-107); an element without a share-based promise is measured
    on its own keys; a promise with an empty list means every obligation (S6 world 40,000.00)."""
    unknown = w.sbc_version(
        1, JAN, True, "1000000.00", obligation_key=None, target_keys=("L9-NOPE",)
    )
    assert _scope_error(w.units_world(TWO_YEARS, [unknown])) == (
        "CPC_RELATED_SCOPE_INVALID",
        "UNKNOWN_OBLIGATION",
    )
    other = w.sbc_version(1, JAN, True, "1000000.00", obligation_key="L2-OTHER")
    assert _scope_error(w.units_world(TWO_YEARS, [other], extra_line=True)) == (
        "CPC_RELATED_SCOPE_INVALID",
        "MISMATCH",
    )
    element_only = w.checked(
        w.units_world([("D", Y1, "400000"), ("I", Y1, "400000.00")], [V1], promises=[])
    )
    assert w.equity_credits(element_only) == {P(6): 2_000_000}
    assert w.revenue_cum(element_only) == 38_000_000
    assert w.nodes(element_only)[f"consideration_payable:{SUBJECT}:{P(6)}"].value == "0.00"
    every = w.units_world(
        [("D", Y1, "400000", SUPPLY), ("D", Y1, "400000", "L2-OTHER")],
        [w.sbc_version(1, JAN, True, "1000000.00", obligation_key=None)],
        extra_line=True,
        promises=[w.payable("50000.00", JAN, (), share_based=True)],
    )
    assert w.equity_credits(w.checked(every)) == {P(6): 4_000_000}


def test_expected_zero_guard() -> None:
    """E ≤ 0 with related revenue raises NON_FINITE_AMOUNT (CV-32) naming the formula and the
    element; E ≤ 0 without related revenue gives 0 before any division (D-91 (7))."""
    zero = w.sbc_version(1, JAN, True, "0.00")
    promise = w.payable("50000.00", JAN, (SUPPLY,), share_based=True)
    with pytest.raises(EngineError) as raised:
        w.run(w.units_world([("D", Y1, "400000")], [zero], promises=[promise]))
    error = raised.value
    assert (error.code, error.formula_id, error.subject_key) == (
        "NON_FINITE_AMOUNT",
        "tp.cpc_share_based.v1",
        KEY,
    )
    quiet = w.checked(w.units_world([("I", Y1, "400000.00")], [zero], promises=[promise]))
    assert w.equity_credits(quiet) == {}
    assert w.nodes(quiet)[f"{ELEMENT_NODE}:{P(6)}"].value == "0.00"


def test_expected_zero_guard_with_offsetting_concession() -> None:
    """Codex's validated full-offset case: inception E 1,000,000.00; 400,000.00 delivered and
    billed on 30 June (reduction 20,000.00); on 31 August a PRICE_CHANGE of −400,000.00 settled by
    CREDIT_OR_REFUND and an explicit version setting E = 0. Under count-once the selected 31 August
    node already holds the concession (revenue 0.00), R = 0 and the element is 0 before any
    division: equity +20,000.00 (P06) / −20,000.00 (P08), journal and contract net revenue 0, and
    no NON_FINITE_AMOUNT (on 554c7aa the double subtraction hit the guard at P08 with related
    revenue −400,000.00)."""
    zero = w.sbc_version(2, date(2026, 8, 31), True, "0.00", supersedes=V1.version_key)
    modification = w.concession("-400000.00", date(2026, 8, 31), named=False)
    steps = [
        ("D", Y1, "400000"),
        ("I", Y1, "400000.00"),
        ("A", date(2026, 8, 31), "MOD-CONCESSION-1"),
    ]
    book = w.checked(
        w.units_world(steps, [V1, zero], modifications=[modification], quantity="400000")
    )
    found = w.nodes(book)
    assert found[f"{REVENUE_NODE}:{P(8)}"].value == "0.00"
    assert found[f"{CONCESSION_NODE}:{P(8)}"].value == "400000.00"
    element = found[f"{ELEMENT_NODE}:{P(8)}"]
    assert (element.value, element.params["expected"], element.params["concessions_embedded"]) == (
        "0.00",
        "0",
        "1",
    )
    assert w.equity_credits(book) == {P(6): 2_000_000, P(8): -2_000_000}
    assert sum(w.revenue_credits(book).values()) == 0
    assert w.revenue_cum(book) == 0


def _cutoff_world():
    """The Codex differing-calendar cutoff fixture (input sha256 a498d44f… at 554c7aa): the fully
    delivered and billed 400,000.00 contract of US01 (monthly) performed by US02 on a contiguous
    4-4-5 calendar from 4 January 2026 (P08 ends 29 August, P09 3 October, P10 31 October), the
    award F 50,000 / E 1,000,000 granted at inception, and a −50,000.00 CREDIT_OR_REFUND price
    change on 30 August."""
    inception = date(2026, 1, 4)
    version = w.sbc_version(1, inception, True, "1000000.00", grant=inception.isoformat())
    modification = w.concession("-50000.00", date(2026, 8, 30), named=False)
    steps = [
        ("D", Y1, "400000"),
        ("I", Y1, "400000.00"),
        ("A", date(2026, 8, 30), "MOD-CONCESSION-1"),
    ]
    return w.with_performing_445(
        w.units_world(
            steps, [version], modifications=[modification], quantity="400000", inception=inception
        )
    )


def test_concession_after_the_selected_nodes_cutoff_is_subtracted_until_embedded() -> None:
    """Supervisor cutoff ruling (Codex B3-CONCESSION-CUTOFF-REVIEW-20260918): at contracting
    cutoff t the numerator is the selected performing node's posted revenue less the concessions
    created after that node's own cutoff and on or before t, each cited; once a later performing
    close embeds the concession it drops out. Contracting 31 Aug and 30 Sep select the 29 Aug node
    (400,000.00) and cite the 30 Aug concession (350,000.00 → 17,500.00); 31 Oct selects the 31 Oct
    node (350,000.00, concession embedded) → 17,500.00 with no concession input; the cited input
    is the dated portion node, never the aggregate ``concession_created_cum`` node. The dated
    before-incentive journal basis is 350,000.00 and the net 332,500.00 at each of the three
    closes (each intent on its own entity's period end; CONSIDERATION_PAYABLE intents excluded for
    the basis); every trace node replays and every intent balances (main on 554c7aa: 17,500 /
    17,500 / 15,000; b2029bb's blanket marker: 20,000 / 20,000 / 17,500)."""
    bundle = _cutoff_world()
    book = w.checked(bundle)
    assert w.balanced(book)
    found = w.nodes(book)
    revenue_aug = f"revenue_cum:{WARRANT}/{SUPPLY}:FY2026-P08"  # US02 P08 ends 29 Aug
    revenue_oct = f"revenue_cum:{WARRANT}/{SUPPLY}:FY2026-P10"  # US02 P10 ends 31 Oct
    assert (found[revenue_aug].value, found[revenue_oct].value) == ("400000.00", "350000.00")
    august = found[f"{ELEMENT_NODE}:{P(8)}"]
    cited = [item for item in august.inputs if isinstance(item, str)]
    assert cited[0] == revenue_aug and len(cited) == 2
    portion_id = cited[1]
    assert portion_id.startswith("concession_portion@") and portion_id.endswith(f":{P(8)}")
    assert f"{CONCESSION_NODE}:{P(8)}" not in cited  # the aggregate node is never the input
    portion = found[portion_id]
    assert (portion.value, portion.params["effective_date"], portion.params["aggregate_node"]) == (
        "50000.00",
        "2026-08-30",
        f"{CONCESSION_NODE}:{P(8)}",
    )
    assert (august.params["signs"], august.params["revenue_cutoff"], august.value) == (
        "+,-",
        "2026-08-29",
        "17500.00",
    )
    september = found[f"{ELEMENT_NODE}:{P(9)}"]
    cited = [item for item in september.inputs if isinstance(item, str)]
    assert cited[0] == revenue_aug and cited[1].startswith("concession_portion@")
    assert cited[1].endswith(f":{P(9)}") and september.value == "17500.00"
    october = found[f"{ELEMENT_NODE}:{P(10)}"]
    assert [item for item in october.inputs if isinstance(item, str)] == [revenue_oct]
    assert (october.params["concessions_embedded"], october.value) == ("1", "17500.00")
    assert w.equity_credits(book) == {P(7): 2_000_000, P(8): -250_000}
    for cutoff in (date(2026, 8, 31), date(2026, 9, 30), date(2026, 10, 31)):
        basis = w.dated_revenue(bundle, book, cutoff, exclude_kinds=("CONSIDERATION_PAYABLE",))
        assert basis == 35_000_000, cutoff
        assert w.dated_revenue(bundle, book, cutoff) == 33_250_000, cutoff
    # Signed lineage over the cited portion: zeroing it replays 20,000.00 from the revenue node.
    zeroed = w.with_zeroed_input(book.trace, august.id, portion_id)
    assert reevaluate(zeroed)[august.id] == "20000.00"


def test_trace_identity_and_lineage_sensitivity_every_case() -> None:
    """Every node replays (``checked`` above and here); the element node's inputs hold the revenue
    node and one SourceRef, the award; no param replays a precomputed numerator; zeroing the cited
    revenue node of a two-obligation award replays the result from the remaining revenue node; the
    EMBEDDED concession is no input, so zeroing the concession world's revenue node replays 0.00; a
    trace whose revenue inputs are all zero replays 0.00 with the release equal to the ordinary node
    (D-91 (6); supervisor ruling on L9-ENG-B3-Q-1)."""
    book = w.checked(w.units_world(TWO_YEARS, [V1]))
    element = w.nodes(book)[f"{ELEMENT_NODE}:{P(6)}"]
    assert f"{REVENUE_NODE}:{P(6)}" in element.inputs
    sources = [item for item in element.inputs if isinstance(item, SourceRef)]
    assert [(item.ref_type, item.ref_id) for item in sources] == [
        ("estimate_version", V1.version_key)
    ]
    assert sources[0].detail["value"] == "50000"
    assert element.inputs[0] == sources[0]
    assert "related_revenue" not in element.params
    assert element.params["vesting_probable"] == "true"
    # Lineage sensitivity over a real remaining input: the two-obligation world cites both
    # revenue nodes; zeroing L1-SUPPLY's leaves L2-OTHER's 400,000.00, so the element replays
    # 20,000.00 from 40,000.00.
    every = w.checked(
        w.units_world(
            [("D", Y1, "400000", SUPPLY), ("D", Y1, "400000", "L2-OTHER")],
            [w.sbc_version(1, JAN, True, "1000000.00", obligation_key=None)],
            extra_line=True,
            promises=[w.payable("50000.00", JAN, (), share_based=True)],
        )
    )
    element_id = f"{ELEMENT_NODE}:{P(6)}"
    assert w.nodes(every)[element_id].value == "40000.00"
    zeroed = w.with_zeroed_input(every.trace, element_id, f"{REVENUE_NODE}:{P(6)}")
    assert reevaluate(zeroed)[element_id] == "20000.00"
    # The EMBEDDED concession is not an input: zeroing the only cited revenue node replays 0.00.
    concession = w.checked(_concession_world())
    element_id = f"{ELEMENT_NODE}:{P(8)}"
    zeroed = w.with_zeroed_input(concession.trace, element_id, f"{REVENUE_NODE}:{P(8)}")
    assert reevaluate(zeroed)[element_id] == "0.00"
    advance = w.checked(w.units_world([("I", Y1, "400000.00")], [V1]))
    found = w.nodes(advance)
    element = found[f"{ELEMENT_NODE}:{P(6)}"]
    cited = [item for item in element.inputs if isinstance(item, str)]
    assert cited == [f"{REVENUE_NODE}:{P(6)}"]  # stage 09 publishes the 0.00 target
    assert {found[item].value for item in cited} == {"0.00"}
    assert element.value == "0.00"
    assert found[f"{RELEASE_NODE}:{P(6)}"].value == found[f"{ORDINARY_NODE}:{P(6)}"].value == "0.00"
    assert list(found[f"{RELEASE_NODE}:{P(6)}"].inputs) == [
        f"{ORDINARY_NODE}:{P(6)}",
        f"{SHARE_NODE}:{P(6)}",
    ]


def _fingerprint(book) -> tuple[tuple[object, ...], dict[str, str]]:
    postings = tuple(
        sorted(
            (
                intent.posting_period_key,
                tuple(
                    sorted(
                        (item.account_role, item.clearing_purpose, item.side, item.amount_txn)
                        for item in intent.lines
                    )
                ),
            )
            for intent in book.posting_intents
        )
    )
    values = {node.id: node.value for node in book.trace.nodes if node.measure in CPC_MEASURES}
    return postings, values


def test_ordering_same_date_invoice_before_delivery() -> None:
    """Swapping a same-date invoice and delivery leaves every posting and every CPC node unchanged
    (stage 12 layer node ids differ by construction and are outside this topic)."""
    a = w.checked(w.units_world(TWO_YEARS, [V1]))
    swapped = [
        ("I", Y1, "400000.00"),
        ("D", Y1, "400000"),
        ("I", Y2, "600000.00"),
        ("D", Y2, "600000"),
    ]
    b = w.checked(w.units_world(swapped, [V1]))
    assert _fingerprint(a) == _fingerprint(b)
    assert len(_fingerprint(a)[1]) >= 6 * 24


def _two_concession_world():
    """Codex's two-concession cutoff fixture (input sha256 6ac0c586… at 14479e4): the fully
    delivered and billed 400,000.00 contract performed by US02 on the 4-4-5 calendar, a 20,000.00
    CREDIT_OR_REFUND price change on 15 August and a 30,000.00 one on 30 August (class S, no
    line); performing close 29 August, contracting close 31 August."""
    inception = date(2026, 1, 4)
    version = w.sbc_version(1, inception, True, "1000000.00", grant=inception.isoformat())
    first = w.concession("-20000.00", date(2026, 8, 15), reference="MOD-FIRST-20000", named=False)
    second = w.concession("-30000.00", date(2026, 8, 30), reference="MOD-SECOND-30000", named=False)
    steps = [
        ("D", Y1, "400000"),
        ("I", Y1, "400000.00"),
        ("A", first.effective_date, first.modification_key),
        ("A", second.effective_date, second.modification_key),
    ]
    return w.with_performing_445(
        w.units_world(
            steps, [version], modifications=[first, second], quantity="400000", inception=inception
        )
    )


def test_two_concessions_only_the_unembedded_portion_is_subtracted() -> None:
    """Supervisor blocker on 14479e4 (Codex B3-TWO-CONCESSION-HANDOFF-20260918): the selected 29
    August node is 380,000.00 (it embeds the 15 August 20,000.00); only the 30 August 30,000.00 is
    unembedded at 31 August, so R = 350,000.00 and the element 17,500.00 at 31 Aug, 30 Sep (same
    node) and 31 Oct (the 31 Oct node 350,000.00 embeds both). The element cites the revenue node
    and a dated event-level portion node for the 30,000.00 only, never the collapsed 50,000.00
    aggregate (14479e4 subtracted the aggregate dated by its latest event: 16,500.00). Dated
    journal basis 350,000.00 and net 332,500.00 at each close; every node replays and every intent
    balances."""
    bundle = _two_concession_world()
    book = w.checked(bundle)
    assert w.balanced(book)
    found = w.nodes(book)
    revenue_aug = f"revenue_cum:{WARRANT}/{SUPPLY}:FY2026-P08"
    revenue_oct = f"revenue_cum:{WARRANT}/{SUPPLY}:FY2026-P10"
    assert (found[revenue_aug].value, found[revenue_oct].value) == ("380000.00", "350000.00")
    assert found[f"{CONCESSION_NODE}:{P(8)}"].value == "50000.00"
    for period in (P(8), P(9)):
        element = found[f"{ELEMENT_NODE}:{period}"]
        cited = [item for item in element.inputs if isinstance(item, str)]
        assert cited[0] == revenue_aug
        assert len(cited) == 2 and cited[1].startswith("concession_portion@")
        assert f"{CONCESSION_NODE}:{period}" not in cited
        portion = found[cited[1]]
        assert (portion.value, portion.params["effective_date"]) == ("30000.00", "2026-08-30")
        assert (element.params["signs"], element.params["concessions_embedded"]) == ("+,-", "1")
        assert (element.params["revenue_cutoff"], element.value) == ("2026-08-29", "17500.00")
    october = found[f"{ELEMENT_NODE}:{P(10)}"]
    assert [item for item in october.inputs if isinstance(item, str)] == [revenue_oct]
    assert (october.params["concessions_embedded"], october.value) == ("2", "17500.00")
    assert w.equity_credits(book) == {P(7): 2_000_000, P(8): -250_000}
    for cutoff in (date(2026, 8, 31), date(2026, 9, 30), date(2026, 10, 31)):
        assert (
            w.dated_revenue(bundle, book, cutoff, exclude_kinds=("CONSIDERATION_PAYABLE",))
            == 35_000_000
        )
        assert w.dated_revenue(bundle, book, cutoff) == 33_250_000
    # Signed lineage over the cited portion: zeroing it replays 19,000.00 from the 380,000.00 node.
    august = found[f"{ELEMENT_NODE}:{P(8)}"]
    portion_id = next(
        item
        for item in august.inputs
        if isinstance(item, str) and item.startswith("concession_portion@")
    )
    assert (
        reevaluate(w.with_zeroed_input(book.trace, august.id, portion_id))[august.id] == "19000.00"
    )


def test_cross_month_concessions_july_portion_then_august_portion() -> None:
    """Supervisor blocker on cf5b2f9 (Codex B3-CROSS-MONTH-HANDOFF-20260918): the first 20,000.00
    concession on 15 JULY, the second 30,000.00 on 30 August (4-4-5 performing closes 4 Jul, 1 Aug,
    29 Aug, 3 Oct, 31 Oct). Derived with Fraction (derive-output.json ``cross_month_v``): at
    contracting 31 Jul the selected 4 Jul node 400,000.00 minus the 15 Jul portion → 380,000 →
    19,000.00; at 31 Aug the 29 Aug node 380,000.00 (July embedded) minus the 30 Aug portion →
    350,000 → 17,500.00; 30 Sep 17,500.00; 31 Oct the 350,000.00 node → 17,500.00. cf5b2f9 raised
    ENGINE_INVARIANT_VIOLATED at P07 because its guard compared the July history portion with an
    aggregate target dated by the latest event (30 Aug); the aggregate posting path is unchanged."""
    inception = date(2026, 1, 4)
    version = w.sbc_version(1, inception, True, "1000000.00", grant=inception.isoformat())
    first = w.concession("-20000.00", date(2026, 7, 15), reference="MOD-FIRST-20000", named=False)
    second = w.concession("-30000.00", date(2026, 8, 30), reference="MOD-SECOND-30000", named=False)
    steps = [
        ("D", Y1, "400000"),
        ("I", Y1, "400000.00"),
        ("A", first.effective_date, first.modification_key),
        ("A", second.effective_date, second.modification_key),
    ]
    bundle = w.with_performing_445(
        w.units_world(
            steps, [version], modifications=[first, second], quantity="400000", inception=inception
        )
    )
    book = w.checked(bundle)
    assert w.balanced(book)
    found = w.nodes(book)
    june_node = f"revenue_cum:{WARRANT}/{SUPPLY}:FY2026-P06"  # US02 P06 ends 4 Jul
    august_node = f"revenue_cum:{WARRANT}/{SUPPLY}:FY2026-P08"  # US02 P08 ends 29 Aug
    october_node = f"revenue_cum:{WARRANT}/{SUPPLY}:FY2026-P10"
    assert (found[june_node].value, found[august_node].value, found[october_node].value) == (
        "400000.00",
        "380000.00",
        "350000.00",
    )
    july = found[f"{ELEMENT_NODE}:{P(7)}"]
    cited = [item for item in july.inputs if isinstance(item, str)]
    assert cited[0] == june_node and len(cited) == 2 and cited[1].startswith("concession_portion@")
    assert (found[cited[1]].value, found[cited[1]].params["effective_date"]) == (
        "20000.00",
        "2026-07-15",
    )
    assert (july.value, july.params["revenue_cutoff"], july.params["concessions_embedded"]) == (
        "19000.00",
        "2026-07-04",
        "0",
    )
    # No aggregate concession_created_cum target exists at P07: the aggregate is dated by its latest
    # event (30 Aug), the legacy posting path the ruling preserves.
    assert f"{CONCESSION_NODE}:{P(7)}" not in found
    assert found[f"{CONCESSION_NODE}:{P(8)}"].value == "50000.00"
    august = found[f"{ELEMENT_NODE}:{P(8)}"]
    cited = [item for item in august.inputs if isinstance(item, str)]
    assert cited[0] == august_node and len(cited) == 2
    assert (found[cited[1]].value, found[cited[1]].params["effective_date"]) == (
        "30000.00",
        "2026-08-30",
    )
    assert (august.value, august.params["concessions_embedded"]) == ("17500.00", "1")
    assert found[f"{ELEMENT_NODE}:{P(9)}"].value == "17500.00"
    october = found[f"{ELEMENT_NODE}:{P(10)}"]
    assert [item for item in october.inputs if isinstance(item, str)] == [october_node]
    assert (october.value, october.params["concessions_embedded"]) == ("17500.00", "2")
    assert w.equity_credits(book) == {P(7): 1_900_000, P(8): -150_000}


def test_mixed_producers_stage_06_july_then_stage_08_august() -> None:
    """Supervisor blocker on b260878 (Codex B3-MIXED-PRODUCER-HANDOFF-20260919; public input sha
    1298cb3a…): the same economics as the cross-month case with the second concession produced by
    STAGE 08 — a targeted ``VARIABLE_CONSIDERATION`` ``DISCOUNT`` estimate (version 1 at inception
    0.00; version 2 on 30 Aug 30,000.00 on ``L1-SUPPLY``, no ``refund_liability_target``) — after
    the 15 Jul stage 06 ``CREDIT_OR_REFUND`` concession of 20,000.00. Derived with Fraction
    (derive-output.json ``mixed_vi``): 19,000.00 at 31 Jul (4 Jul node 400,000.00 minus the July
    portion), 17,500.00 at 31 Aug / 30 Sep (29 Aug node 380,000.00 minus the August portion) and
    31 Oct (350,000.00 node). The July portion node cites the stage 06 CONTRACT_AMENDED event, the
    August one the stage 08 ESTIMATE_CHANGED event. b260878 raised ENGINE_INVARIANT_VIOLATED at P07
    because its temporal lower bound compared the July portions (20,000.00) with the aggregate
    ``concession_created_cum`` (50,000.00), which ``refund_liability._concession_event`` dates by
    the settled modification (15 Jul) rather than the later TP_CHANGE; that legacy dating and the
    JET-05c posting are preserved unchanged (the aggregate node shows 50,000.00 from P07)."""
    import dataclasses
    from datetime import UTC, datetime
    from decimal import Decimal

    inception = date(2026, 1, 4)
    award = w.sbc_version(1, inception, True, "1000000.00", grant=inception.isoformat())
    first = w.concession("-20000.00", date(2026, 7, 15), reference="MOD-FIRST-20000", named=False)
    vc_key = f"{WARRANT}/VC-DISCOUNT"
    discount0 = dataclasses.replace(
        award,
        estimate_key=vc_key,
        element_code="VC-DISCOUNT",
        estimate_kind="VARIABLE_CONSIDERATION",
        vc_element_type="DISCOUNT",
        allocation_target="OBLIGATIONS",
        target_obligation_keys=(SUPPLY,),
        version_key=f"{vc_key}@v1",
        parameters={},
        unconstrained_amount=Decimal("0.00"),
        most_conservative_amount=Decimal("0.00"),
        constrained_amount=Decimal("0.00"),
        expected_total_amount=None,
    )
    discount1 = dataclasses.replace(
        discount0,
        version_key=f"{vc_key}@v2",
        version_no=2,
        effective_date=date(2026, 8, 30),
        supersedes_version_key=discount0.version_key,
        unconstrained_amount=Decimal("30000.00"),
        most_conservative_amount=Decimal("30000.00"),
        constrained_amount=Decimal("30000.00"),
    )
    steps = [
        ("D", Y1, "400000"),
        ("I", Y1, "400000.00"),
        ("A", first.effective_date, first.modification_key),
    ]
    bundle = w.units_world(
        steps, [award, discount0], modifications=[first], quantity="400000", inception=inception
    )
    bundle = dataclasses.replace(
        bundle,
        events=tuple(w.pinned(list(bundle.events), discount1)),
        estimate_versions=tuple(
            sorted(
                (*bundle.estimate_versions, discount1), key=lambda v: (v.estimate_key, v.version_no)
            )
        ),
        known_at=datetime(2026, 8, 30, 23, tzinfo=UTC),
    )
    bundle = w.with_performing_445(bundle)
    # The performing year extends into 2028, beyond the contracting calendar. Dated
    # consideration keeps covered performing cutoffs without measuring outside that calendar.
    from support.fold import fold_trace

    state, _ = fold_trace(bundle, "ASC606")
    consideration_dates = {build.at for build in state.tp_unconstrained[WARRANT]}
    assert date(2026, 8, 29) in consideration_dates
    assert date(2028, 1, 1) not in consideration_dates
    events = {event.event_key: event for event in bundle.events}
    estimate_event = next(
        event.event_key
        for event in bundle.events
        if event.event_type == "ESTIMATE_CHANGED"
        and event.payload.get("estimate_version_id") == discount1.version_key
    )
    book = w.checked(bundle)
    assert w.balanced(book)
    found = w.nodes(book)
    june_node = f"revenue_cum:{WARRANT}/{SUPPLY}:FY2026-P06"
    august_node = f"revenue_cum:{WARRANT}/{SUPPLY}:FY2026-P08"
    october_node = f"revenue_cum:{WARRANT}/{SUPPLY}:FY2026-P10"
    assert (found[june_node].value, found[august_node].value, found[october_node].value) == (
        "400000.00",
        "380000.00",
        "350000.00",
    )

    def portion(node_id: str) -> tuple[str, str, str, str]:
        node = found[node_id]
        (source,) = [item for item in node.inputs if isinstance(item, SourceRef)]
        return node.value, node.params["effective_date"], node.params["producer"], source.ref_id

    july = found[f"{ELEMENT_NODE}:{P(7)}"]
    cited = [item for item in july.inputs if isinstance(item, str)]
    assert cited[0] == june_node and len(cited) == 2
    value, on, producer, event_key = portion(cited[1])
    assert (value, on, producer) == ("20000.00", "2026-07-15", "06")
    assert events[event_key].event_type == "CONTRACT_AMENDED"
    assert events[event_key].effective_date == date(2026, 7, 15)
    assert (july.value, july.params["revenue_cutoff"], july.params["concessions_embedded"]) == (
        "19000.00",
        "2026-07-04",
        "0",
    )
    # Legacy aggregate dating preserved (not this lane's to change): the final 50,000.00 quota is
    # dated by the settled modification, so the aggregate node already shows 50,000.00 at P07.
    assert found[f"{CONCESSION_NODE}:{P(7)}"].value == "50000.00"
    assert found[f"{CONCESSION_NODE}:{P(8)}"].value == "50000.00"
    august = found[f"{ELEMENT_NODE}:{P(8)}"]
    cited = [item for item in august.inputs if isinstance(item, str)]
    assert cited[0] == august_node and len(cited) == 2
    value, on, producer, event_key = portion(cited[1])
    assert (value, on, producer, event_key) == ("30000.00", "2026-08-30", "08", estimate_event)
    assert (august.value, august.params["concessions_embedded"]) == ("17500.00", "1")
    assert found[f"{ELEMENT_NODE}:{P(9)}"].value == "17500.00"
    october = found[f"{ELEMENT_NODE}:{P(10)}"]
    assert [item for item in october.inputs if isinstance(item, str)] == [october_node]
    assert (october.value, october.params["concessions_embedded"]) == ("17500.00", "2")
    assert w.equity_credits(book) == {P(7): 1_900_000, P(8): -150_000}


def test_concession_history_sums_to_the_aggregate_quota() -> None:
    """The dated source subledger of accepted concession additions (per producing event and
    receiving obligation) reproduces the aggregate refund quota in both representations, Σ exact =
    quota.x_exact and Σ posted = quota.a_posted (never re-rounded), keeps the event chronology and
    the producer's revenue basis; the aggregate refund component, its trace node and the JET-05c
    posting are unchanged."""
    from support.fold import fold_book

    allocated = fold_book(_two_concession_world(), "ASC606")
    subject = f"{WARRANT}/{SUPPLY}"
    history = [item for item in allocated.concession_history if item.subject_key == subject]
    assert [
        (item.effective_date, item.posted, item.producer, item.revenue_basis) for item in history
    ] == [
        (date(2026, 8, 15), 2_000_000, "06", "EMBEDDED"),
        (date(2026, 8, 30), 3_000_000, "06", "EMBEDDED"),
    ]
    assert len({item.event_key for item in history}) == 2
    quota = allocated.refund_components[subject]
    assert sum((item.exact for item in history), Fraction(0)) == quota.x_exact == Fraction(50000)
    assert sum(item.posted for item in history) == quota.a_posted == 5_000_000


def test_concession_cutoff_rule_on_the_element_helper() -> None:
    """The count-once rule per selected node over the dated portions: an EMBEDDED portion dated
    after the selected revenue node's cutoff (and ≤ t) is subtracted and cited through its own
    ``concession_portion@<event>`` node (sign −); one dated on or before that cutoff is embedded
    (counted in ``concessions_embedded``, not cited); a SEPARATE portion is always subtracted and
    cited; an obligation without a revenue node subtracts every portion; the portions are never
    compared with the aggregate ``concession_created_cum`` at t (S10-R-26)."""
    from erev_engine.stages.s10_billing_balances import customer_consideration as cc
    from erev_engine.stages.state import ConcessionAddition, Target
    from erev_engine.trace import TraceBuilder
    from support import bundles
    from support.recognition import book_context

    ctx = book_context(bundles.entity(start=JAN, months=12), book_code="ASC606", currency="USD")
    version = w.sbc_version(1, JAN, True, "1000000.00")
    subject = f"{WARRANT}/{SUPPLY}"
    ends = {("US01", P(8)): date(2026, 8, 31), ("US02", "FY2026-P08"): date(2026, 8, 29)}

    def target(
        measure: str, value: int, entity: str, period: str, cause: str | None = None
    ) -> Target:
        node = f"{measure}:{subject}:{period}"
        return Target("ASC606", entity, subject, measure, period, cause, value, None, node)  # type: ignore[arg-type]

    def addition(event: str, on: date, posted: int, basis: str = "EMBEDDED") -> ConcessionAddition:
        return ConcessionAddition(
            subject, event, on, (on, 1, event), Fraction(posted, 100), posted, "06", basis
        )

    revenue = {subject: [target("revenue_cum", 40_000_000, "US02", "FY2026-P08")]}
    late = addition(f"{WARRANT}/EV-000007", date(2026, 8, 30), 5_000_000)
    early = addition(f"{WARRANT}/EV-000006", date(2026, 8, 15), 3_000_000)
    apart = addition(f"{WARRANT}/EV-000008", date(2026, 8, 15), 1_000_000, "SEPARATE")
    history = {subject: [early, apart, late]}
    aggregate = target("concession_created_cum", 9_000_000, "US01", P(8), "component")
    aggregates = {(subject, P(8)): aggregate}
    t, pk = date(2026, 8, 31), P(8)
    tb = TraceBuilder(engine_version="0.1.0")
    shared: dict[tuple[str, str, str], str] = {}
    posted, node_id = cc._element(
        ctx, tb, KEY, version, (subject,), t, pk, revenue, aggregates, history, ends, 100, shared
    )
    nodes = {item.id: item for item in tb.build(root_measures={}).nodes}
    node = nodes[node_id]
    # 50,000 × (400,000 − 50,000 EMBEDDED after 29 Aug − 10,000 SEPARATE) ÷ 1,000,000
    assert posted == 1_700_000
    cited = [item for item in node.inputs if isinstance(item, str)]
    assert cited == [
        revenue[subject][0].node_id,
        f"concession_portion@{WARRANT}/EV-000008:{subject}:{P(8)}",
        f"concession_portion@{WARRANT}/EV-000007:{subject}:{P(8)}",
    ]
    assert (
        node.params["signs"],
        node.params["concessions_embedded"],
        node.params["revenue_cutoff"],
    ) == ("+,-,-", "1", "2026-08-29")
    portion = nodes[cited[2]]
    assert (portion.value, portion.formula_id, portion.params["aggregate_node"]) == (
        "50000.00",
        "tp.cpc_release.v1",
        aggregate.node_id,
    )
    assert (portion.params["effective_date"], portion.params["producer"]) == ("2026-08-30", "06")
    assert len(shared) == 2  # emitted once per (event, obligation, period), shared by elements
    # No revenue node yet: every portion at t is subtracted.
    fresh = TraceBuilder(engine_version="0.1.0")
    posted, node_id = cc._element(
        ctx, fresh, KEY, version, (subject,), t, pk, {}, aggregates, history, ends, 100, {}
    )
    assert posted == -450_000  # 50,000 × (−90,000) ÷ 1,000,000: signed, no floor
    # The portions are never compared with the aggregate at t (its date is its producer's, unlike
    # the portions' across mixed producers): an aggregate below or above the portions changes
    # nothing; check_history validates the subledger over its full history instead.
    for value in (8_000_000, 9_500_000):
        posted, _ = cc._element(
            ctx, TraceBuilder(engine_version="0.1.0"), KEY, version, (subject,), t, pk, revenue,
            {(subject, P(8)): target("concession_created_cum", value, "US01", P(8), "c")},
            history, ends, 100, {},
        )  # fmt: skip
        assert posted == 1_700_000


def test_concession_history_conservation_check_fails_closed_on_corrupt_history() -> None:
    """``check_history``: the full dated history must conserve each obligation's final quota in
    exact and posted terms, name producing events of the state and known producers; a quota
    without history, history without a quota, a foreign event key or an unknown producer fails
    closed (S10-R-26). Termination refunds (``#TERMINATION@`` keys) are outside the check."""
    import dataclasses

    from erev_engine.stages.s10_billing_balances import customer_consideration as cc
    from erev_engine.stages.state import ConcessionAddition, ConcessionQuota, Quota
    from support.recognition import allocated_state, event_view

    subject = f"{WARRANT}/{SUPPLY}"
    booked = event_view(WARRANT, 1, "CONTRACT_BOOKED", JAN, {})
    amended = event_view(WARRANT, 2, "CONTRACT_AMENDED", date(2026, 8, 15), {})
    base = allocated_state([], events=[booked, amended])
    ev2, ev9 = amended.event_key, f"{WARRANT}/EV-000009"

    def state(quota, *portions):
        return dataclasses.replace(
            base,
            refund_components={subject: quota} if quota is not None else {},
            concession_history=tuple(portions),
        )

    def portion(event: str, posted: int, exact: Fraction | None = None, producer: str = "06"):
        return ConcessionAddition(
            subject,
            event,
            date(2026, 8, 15),
            (date(2026, 8, 15), 2, event),
            Fraction(posted, 100) if exact is None else exact,
            posted,
            producer,
            "EMBEDDED",
        )

    good = state(
        ConcessionQuota(Fraction(500), 50_000, revenue_basis="EMBEDDED"),
        portion(ev2, 20_000),
        portion(ev2, 30_000),
    )
    cc.check_history(good, {subject: list(good.concession_history)})
    # Deferred targeted cents: a zero-posted entry with a non-zero exact share is legitimate history
    # as long as the exact and posted totals both conserve the quota.
    cents = state(
        ConcessionQuota(Fraction(1, 100), 1, revenue_basis="EMBEDDED"),
        portion(ev2, 0, Fraction(1, 300)),
        portion(ev2, 1, Fraction(2, 300)),
    )
    cc.check_history(cents, {subject: list(cents.concession_history)})
    # Codex controls on b260878 (2026-09-18-b3-subcent-history-b260878.json): a complete sub-cent
    # history (exact 1/300, posted 0, one entry) and a genuinely empty quota accept; a MISSING
    # sub-cent history (exact 1/300, posted 0, no entry) and a missing one-cent history reject. The
    # posted-only early exit of b260878 accepted the missing sub-cent history.
    subcent = state(
        ConcessionQuota(Fraction(1, 300), 0, revenue_basis="EMBEDDED"),
        portion(ev2, 0, Fraction(1, 300)),
    )
    cc.check_history(subcent, {subject: list(subcent.concession_history)})
    empty = state(ConcessionQuota(Fraction(0), 0, revenue_basis="EMBEDDED"))
    cc.check_history(empty, {})
    for bad in (
        state(ConcessionQuota(Fraction(1, 300), 0, revenue_basis="EMBEDDED")),
        state(ConcessionQuota(Fraction(1, 100), 1, revenue_basis="EMBEDDED")),
        state(
            ConcessionQuota(Fraction(500), 50_000, revenue_basis="EMBEDDED"), portion(ev2, 20_000)
        ),
        state(
            ConcessionQuota(Fraction(500), 50_000, revenue_basis="EMBEDDED"), portion(ev9, 50_000)
        ),
        state(
            ConcessionQuota(Fraction(500), 50_000, revenue_basis="EMBEDDED"),
            portion(ev2, 50_000, producer="09"),
        ),
        state(None, portion(ev2, 50_000)),
        state(Quota(Fraction(500), 50_000)),
    ):
        with pytest.raises(EngineError) as raised:
            cc.check_history(bad, {subject: list(bad.concession_history)})
        assert (raised.value.code, raised.value.detail.get("rule")) == (
            "ENGINE_INVARIANT_VIOLATED",
            "S10-R-26",
        )
    termination = state(None)
    termination = dataclasses.replace(
        termination, refund_components={f"{WARRANT}#TERMINATION@{ev2}": Quota(Fraction(10), 1_000)}
    )
    cc.check_history(termination, {})
