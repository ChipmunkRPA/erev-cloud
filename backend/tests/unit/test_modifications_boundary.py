"""CTR-17 Modifications — CPU witnesses of the preview measured at the boundary, the BR-MOD-01
questionnaire prefill and the request's retained snapshot (lane FIX-A; 04 §16.14 rev 1.92,
dev-guide DG-CMD-15 / DG-KRN-APR-01 rev 1.75; PRD WLD-X-05, WLD-X-06, BR-MOD-01; ENGINE_SPEC
S06-R-04, S06-R-05, S06-R-17; ENGINE_SPEC_B EX-09-A). No database: the engine's trace nodes are
written here with the params the stages emit (``segments.emit_catch_up``, ``classify.emit``,
``price_test._emit``); the database witnesses are in ``tests/domain/contracts``."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.approvals import engine as approvals
from erev_api.domain.contracts import modifications
from erev_api.problems import Problem
from erev_api.schemas.events import ImpactSummaryOut
from erev_engine.trace import TraceNode

EVENT: str = "SF-ORD-10002/EV-000003"
ROW_ID: UUID = UUID("00000000-0000-0000-0000-000000000123")
POSITION: str = f"SF-ORD-10002/{ROW_ID}"


def _rational(value: Fraction) -> str:
    return (
        str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"
    )


def _node(measure: str, subject: str, shown: str, params: dict[str, str]) -> TraceNode:
    return TraceNode(
        id=f"{measure}:{subject}:-",
        measure=measure,
        value=shown,
        currency="USD",
        formula_id="mod.catch_up.v1",
        inputs=(),
        params=params,
        rounding_residue="0",
        narrative_key="mod.catch_up",
    )


def _catch_up(key: str, shown: str, **params: str) -> TraceNode:
    return _node(f"catch_up@{EVENT}", f"SF-ORD-10002/{key}", shown, {"minor_unit": "2", **params})


# K-02 at its 16 Sep 2026 boundary: O1 240,000.00 over 730 days, 84,821.92 recognised through
# 15 Sep 2026; the pool 215,178.08 = 155,178.08 + 60,000.00 apportioned over the weights.
POOL = Fraction(21517808, 100)
REVENUE = Fraction(8482192, 100)


def _boundary(weights: tuple[Fraction, Fraction], posted: tuple[str, str]) -> dict[str, TraceNode]:
    """The two ``catch_up@`` nodes ``segments.emit_catch_up`` writes for the seat add: ``posted``
    are the largest-remainder shares in minor units (O1's on top of its recognised revenue)."""
    total = weights[0] + weights[1]
    return {
        "O1": _catch_up(
            "O1",
            "0.00",
            a_before="24000000",
            x_before="240000",
            exact_before=_rational(Fraction(240000 * 258, 730)),
            complete_before="false",
            a_after=posted[0],
            x_after=_rational(REVENUE + POOL * weights[0] / total),
            exact_after=_rational(REVENUE),
            complete_after="false",
            base="8482192",
        ),
        "O2": _catch_up(
            "O2",
            "0.00",
            a_before="0",
            x_before="0",
            exact_before="0",
            complete_before="false",
            a_after=posted[1],
            x_after=_rational(POOL * weights[1] / total),
            exact_after="0",
            complete_after="false",
            base="0",
        ),
    }


# The seeded PRD world (WLD-X-06 rev 1.21, supervisor ruling R-17) — the node params the engine
# wrote in the lane database: O1's remaining increments 2,400 × 472 ÷ 730 × 100.00 = 11,328,000 ÷
# 73 (S06-R-11 series row, DAILY) and the added seats 775 × 90.00, the nearest bound (POL-072).
K02 = _boundary((Fraction(11328000, 73), Fraction(69750)), ("23327347", "6672653"))
# ENGINE_SPEC_B EX-09-A, the worked example over its own point entries 155,000.00 : 77,500.00.
EX_09_A = _boundary((Fraction(155000), Fraction(77500)), ("22827397", "7172603"))


def test_boundary_measure_is_the_unrecognised_allocation_on_each_side_of_the_boundary() -> None:
    """S06-R-17 / CV-63 read back from the ``catch_up@<event key>`` node: A − C before and after,
    and C_after − C_before. PRD WLD-X-06 rev 1.21: O1 155,178.08 → 148,451.55, the added O2 →
    66,726.53, no catch-up (S06-INV-02); ENGINE_SPEC_B EX-09-A over its own weights: 143,452.05 and
    71,726.03. A class N obligation keeps less than its share: the catch-up is recognised at the
    boundary."""
    assert modifications.boundary_measure(K02["O1"]) == (
        Decimal("155178.08"),
        Decimal("148451.55"),
        Decimal("0.00"),
    )
    assert modifications.boundary_measure(K02["O2"]) == (
        Decimal("0.00"),
        Decimal("66726.53"),
        Decimal("0.00"),
    )
    assert K02["O1"].params["x_after"] == "127676400372/547325"  # as the engine wrote it
    assert K02["O2"].params["x_after"] == "36521099628/547325"
    assert modifications.boundary_measure(EX_09_A["O1"]) == (
        Decimal("155178.08"),
        Decimal("143452.05"),
        Decimal("0.00"),
    )
    assert modifications.boundary_measure(EX_09_A["O2"]) == (
        Decimal("0.00"),
        Decimal("71726.03"),
        Decimal("0.00"),
    )
    class_n = _catch_up(
        "O3",
        "200.00",
        a_before="100000",
        x_before="1000",
        exact_before="400",
        complete_before="false",
        a_after="120000",
        x_after="1200",
        exact_after="600",
        complete_after="false",
        base="40000",
    )
    assert modifications.boundary_measure(class_n) == (
        Decimal("600.00"),
        Decimal("600.00"),
        Decimal("200.00"),
    )
    # a side at completion posts its whole allocation (CV-63: C = A when f = 1)
    satisfied = _catch_up(
        "O4",
        "50.00",
        a_before="100000",
        x_before="1000",
        exact_before="1000",
        complete_before="true",
        a_after="105000",
        x_after="1050",
        exact_after="1050",
        complete_after="true",
        base="100000",
    )
    assert modifications.boundary_measure(satisfied) == (
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("50.00"),
    )


def _money(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def _summary() -> ImpactSummaryOut:
    """The dry run's version-state summary of the K-02 seat add with an untouched obligation O9
    beside it: the stored version is dated 1 Jan 2026 and the dry-run version the END of 16 Sep."""
    return ImpactSummaryOut.model_validate(
        {
            "transaction_price_before": _money("240010.00"),
            "transaction_price_after": _money("300010.00"),
            "catch_up_total": _money("0.00"),
            "catch_up_by_obligation": [
                {"obligation_key": key, "treatment": None, "amount": _money("0.00")}
                for key in ("O1", "O2", "O9")
            ],
            "remaining_allocation_before": [
                {"obligation_key": "O1", "amount": _money("239671.23")},
                {"obligation_key": "O9", "amount": _money("10.00")},
            ],
            "remaining_allocation_after": [
                {"obligation_key": "O1", "amount": _money("148137.03")},
                {"obligation_key": "O2", "amount": _money("66585.16")},
                {"obligation_key": "O9", "amount": _money("10.00")},
            ],
            "revenue_by_period": [],
            "rpo_before": _money("239681.23"),
            "rpo_after": _money("214732.19"),
            "rpo_date": "2026-09-16",
            "balances_before": [],
            "balances_after": [],
            "journal_lines": [],
            "progress_before": None,
            "progress_after": None,
            "replay_from_date": "2026-09-16",
            "posting_period_key": "FY2026-P09",
            "origin_period_key": None,
        }
    )


def _amounts(items: list[Any]) -> dict[str, str]:
    return {item.obligation_key: item.amount.amount for item in items}


def test_boundary_summary_measures_allocation_and_rpo_at_the_boundary() -> None:
    """PRD WLD-X-05 / WLD-X-06 (rev 1.21), J-05.3: remaining O1 155,178.08 → 148,451.55, the
    added obligation 66,726.53, RPO at 16 Sep 2026 155,178.08 → 215,178.08 (here + 10.00 of the
    untouched O9, which keeps its version-state figure on both sides), catch-up 0.00 with the
    chosen treatment. The version-state figures (239,671.23 at 1 Jan; 148,137.03 / 66,585.16
    after the boundary date's own revenue, 314.52 and 141.37) are replaced for the re-measured
    obligations only."""
    nodes = {node.id: node for node in K02.values()}
    found = modifications.boundary_summary(
        _summary(),
        nodes,
        external_id="SF-ORD-10002",
        event_key=EVENT,
        treatments={"O1": "PROSPECTIVE", "O2": "PROSPECTIVE"},
    )
    assert _amounts(found.remaining_allocation_before) == {"O1": "155178.08", "O9": "10.00"}
    assert _amounts(found.remaining_allocation_after) == {
        "O1": "148451.55",
        "O2": "66726.53",
        "O9": "10.00",
    }
    assert (found.rpo_before.amount, found.rpo_after.amount) == ("155188.08", "215188.08")
    assert [(item.obligation_key, item.treatment) for item in found.catch_up_by_obligation] == [
        ("O1", "PROSPECTIVE"),
        ("O2", "PROSPECTIVE"),
        ("O9", None),
    ]
    assert found.catch_up_total.amount == "0.00"
    # RPO moves by exactly what the boundary adds to the pool: + 60,000.00
    assert Decimal(found.rpo_after.amount) - Decimal(found.rpo_before.amount) == Decimal("60000")
    assert found.transaction_price_after == _summary().transaction_price_after  # untouched


def test_boundary_summary_without_boundary_nodes_keeps_the_version_state() -> None:
    """A candidate that produced no boundary node (a blocking finding returns the state without
    a segment, CV-15) leaves every amount as the dry run measured it; only the chosen treatments
    are named. Another event's nodes are not this candidate's."""
    other = {node.id.replace(EVENT, "SF-ORD-10002/EV-000009"): node for node in K02.values()}
    found = modifications.boundary_summary(
        _summary(), other, external_id="SF-ORD-10002", event_key=EVENT, treatments={"O1": "MIXED"}
    )
    base = _summary()
    assert found.remaining_allocation_before == base.remaining_allocation_before
    assert found.remaining_allocation_after == base.remaining_allocation_after
    assert (found.rpo_before, found.rpo_after) == (base.rpo_before, base.rpo_after)
    assert found.catch_up_by_obligation[0].treatment == "MIXED"


def test_boundary_summary_sums_the_boundary_catch_ups() -> None:
    """A class N obligation's boundary catch-up is the ``catch_up_by_obligation`` amount and the
    total; its remaining allocation after is net of it."""
    node = _catch_up(
        "O1",
        "200.00",
        a_before="100000",
        x_before="1000",
        exact_before="400",
        complete_before="false",
        a_after="120000",
        x_after="1200",
        exact_after="600",
        complete_after="false",
        base="40000",
    )
    found = modifications.boundary_summary(
        _summary(),
        {node.id: node},
        external_id="SF-ORD-10002",
        event_key=EVENT,
        treatments={"O1": "CUMULATIVE_CATCH_UP"},
    )
    assert found.catch_up_total.amount == "200.00"
    first = found.catch_up_by_obligation[0]
    assert (first.treatment, first.amount.amount) == ("CUMULATIVE_CATCH_UP", "200.00")
    assert _amounts(found.remaining_allocation_after)["O1"] == "600.00"


# --- BR-MOD-01: the questionnaire prefill ---------------------------------------------------------


def _class(key: str, label: str, reason: str, progress: str = "0") -> TraceNode:
    return _node(
        f"mod_class@{POSITION}",
        f"SF-ORD-10002/{key}",
        progress,
        {"class": label, "progress_measure": "TIME_ELAPSED", "reason": reason, "value": progress},
    )


def _price_test(key: str, price: str, *, passed: bool, **params: str) -> TraceNode:
    values = {
        "basis": "RANGE",
        "entry_key": "US-LIST@v1/AVM-SEAT-MO//||||/USD",
        "high": "85250",
        "low": "69750",
        "mid": "77500",
        "point": "",
        "point_tolerance_pct": "0",
        "version_key": "US-LIST@v1",
        **params,
    }
    return _node(
        f"mod_price_test@{POSITION}",
        f"SF-ORD-10002/{key}",
        price,
        {"passed": "true" if passed else "false", "value": price, **values},
    )


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": ROW_ID,
        "lines": [
            {
                "obligation_key": "O2",
                "action": "ADD",
                "product_code": "AVM-SEAT-MO",
                "quantity_delta": "775",
                "consideration_delta": {"amount": "60000.00", "currency": "USD"},
            }
        ],
        "questionnaire": {},
    }
    row.update(overrides)
    return row


def _by_id(*nodes: TraceNode) -> dict[str, TraceNode]:
    return {node.id: node for node in nodes}


K02_NODES = _by_id(
    _class("O1", "D", "SERIES", "0.354794520547945205"),
    _class("O2", "D", "NEW_DISTINCT"),
    _price_test("O2", "60000", passed=False),
)


def test_prefill_k02_seat_add_answers_yes_no_yes() -> None:
    """PRD J-05.2 on the engine's own nodes: the added seats are distinct (Yes), 60,000.00 is
    below the modification-date range 69,750.00 – 85,250.00 (No), O1's remaining increments are
    distinct from those transferred (Yes: a series). Each answer carries its catalogue key and
    the caption's params (04 §16.14 ``prefill_reasons``)."""
    found = modifications.questionnaire_prefill(
        _row(), K02_NODES, external_id="SF-ORD-10002", classified=["O1", "O2"]
    )
    remaining = "remaining_goods_distinct_from_transferred"
    assert found == {
        "O1": {
            remaining: {
                "value": True,
                "reason_key": f"modifications.prefill.{remaining}.series",
                "params": {
                    "progress": "0.354794520547945205",
                    "progress_measure": "TIME_ELAPSED",
                },
            }
        },
        "O2": {
            "added_goods_distinct": {
                "value": True,
                "reason_key": "modifications.prefill.added_goods_distinct.new_distinct",
                "params": {},
            },
            "priced_at_ssp": {
                "value": False,
                "reason_key": "modifications.prefill.priced_at_ssp.below_range",
                "params": {
                    "price": "60000",
                    "low": "69750",
                    "high": "85250",
                    "ssp_version_key": "US-LIST@v1",
                },
            },
        },
    }
    assert modifications._prefilled({}, found) == {
        "O1": {"remaining_goods_distinct_from_transferred": True},
        "O2": {"added_goods_distinct": True, "priced_at_ssp": False},
    }


def test_prefill_never_replaces_an_answer_the_preparer_gave() -> None:
    """The engine reads a stored answer as the preparer's (S06-R-05 reason ``QUESTIONNAIRE``;
    S06-R-04 ``priced_at_ssp = true`` is the attestation): an answered question is not prefilled
    and the response keeps the stored value. A contract-level member is not an obligation's
    answer. Item MOD-PREFILL-STORED-ANSWER-1 (04 §16.14 rev 1.235): this holds for the price test
    as for the class questions — rev 1.210 had reported it as ``attested`` beside the stored
    answer, and a client took the stored answer for a proposal still to confirm."""
    row = _row(
        questionnaire={
            "O1": {"remaining_goods_distinct_from_transferred": False},
            "O2": {"priced_at_ssp": True},
            "price_change_settlement": "FUTURE_PRICING",
        }
    )
    nodes = _by_id(
        _class("O1", "N", "QUESTIONNAIRE", "0.35"),
        _class("O2", "D", "NEW_DISTINCT"),
        _price_test("O2", "60000", passed=True, basis="ATTESTED"),
    )
    found = modifications.questionnaire_prefill(
        row, nodes, external_id="SF-ORD-10002", classified=["O1", "O2"]
    )
    assert found == {
        "O2": {
            "added_goods_distinct": {
                "value": True,
                "reason_key": "modifications.prefill.added_goods_distinct.new_distinct",
                "params": {},
            }
        }
    }
    assert modifications._prefilled(row["questionnaire"], found) == {
        "O1": {"remaining_goods_distinct_from_transferred": False},
        "O2": {"priced_at_ssp": True, "added_goods_distinct": True},
        "price_change_settlement": "FUTURE_PRICING",
    }


@pytest.mark.parametrize(
    ("price", "passed", "params", "reason", "shown"),
    [
        ("70000", True, {}, "within_range", {"low": "69750", "high": "85250"}),
        ("90000", False, {}, "above_range", {"low": "69750", "high": "85250"}),
        (
            "77500",
            True,
            {"basis": "POINT", "point": "77500", "low": "", "high": "", "mid": ""},
            "at_point",
            {"point": "77500", "point_tolerance_pct": "0"},
        ),
        (
            "60000",
            False,
            {"basis": "POINT", "point": "77500", "low": "", "high": "", "mid": ""},
            "off_point",
            {"point": "77500", "point_tolerance_pct": "0"},
        ),
        (
            "60000",
            False,
            {"basis": "NO_SSP", "low": "", "high": "", "mid": "", "version_key": ""},
            "no_ssp",
            {},
        ),
    ],
)
def test_prefill_priced_at_ssp_names_the_pol_101_outcome(
    price: str, passed: bool, params: dict[str, str], reason: str, shown: dict[str, str]
) -> None:
    """POL-101 ``WITHIN_MOD_DATE_RANGE``: inside the inclusive range or at the point is "priced
    at SSP"; the reason names where the price stands and the params carry the figures shown."""
    nodes = _by_id(
        _class("O2", "D", "NEW_DISTINCT"), _price_test("O2", price, passed=passed, **params)
    )
    found = modifications.questionnaire_prefill(
        _row(), nodes, external_id="SF-ORD-10002", classified=["O2"]
    )
    answer = found["O2"]["priced_at_ssp"]
    assert answer["value"] is passed
    assert answer["reason_key"] == f"modifications.prefill.priced_at_ssp.{reason}"
    expected = {"price": price, "ssp_version_key": params.get("version_key", "US-LIST@v1")}
    assert answer["params"] == {**expected, **shown}


def test_prefill_names_no_price_test_the_preparer_answered() -> None:
    """Item MOD-PREFILL-STORED-ANSWER-1 (the supervisor's ruling of 2026-10-01; 04 §16.14 rev
    1.235; it replaces item MOD-PREFILL-READ-1's "the price test is reported whatever the
    preparer answered"). ``priced_at_ssp`` answered FALSE: the engine still computes the test
    (S06-R-04 attests on true only) and the entry is named no more — the answer is the
    preparer's. Answered TRUE the engine passes on the answer (basis ``ATTESTED``): no entry
    either, and no reason ``attested``. With both questions of the added line answered the
    obligation is not named at all; a member sent as null is no answer."""
    distinct = {
        "added_goods_distinct": {
            "value": True,
            "reason_key": "modifications.prefill.added_goods_distinct.new_distinct",
            "params": {},
        }
    }

    def found(test: TraceNode, **answers: bool | None) -> dict[str, dict[str, dict[str, Any]]]:
        return modifications.questionnaire_prefill(
            _row(questionnaire={"O2": answers}),
            _by_id(_class("O2", "D", "NEW_DISTINCT"), test),
            external_id="SF-ORD-10002",
            classified=["O2"],
        )

    computed = _price_test("O2", "60000", passed=False)
    attested = _price_test("O2", "60000", passed=True, basis="ATTESTED")
    assert found(computed, priced_at_ssp=False) == {"O2": distinct}
    assert found(attested, priced_at_ssp=True) == {"O2": distinct}
    assert found(computed, added_goods_distinct=True, priced_at_ssp=False) == {}
    assert found(attested, added_goods_distinct=True, priced_at_ssp=True) == {}
    reopened = found(computed, added_goods_distinct=True, priced_at_ssp=None)
    assert {key: sorted(value) for key, value in reopened.items()} == {"O2": ["priced_at_ssp"]}
    assert reopened["O2"]["priced_at_ssp"]["reason_key"].endswith(".below_range")
    # nothing is prefilled over a stored answer: the response's questionnaire is the stored one
    stored = {"O2": {"added_goods_distinct": True, "priced_at_ssp": False}}
    assert modifications._prefilled(stored, found(computed, **stored["O2"])) == stored


def test_mod_price_test_fact_1_the_price_test_is_stated_whatever_the_preparer_answered() -> None:
    """Item MOD-PRICE-TEST-FACT-1 (the supervisor's ruling of 2026-10-01; 04 §16.14 rev 1.250).
    ``modifications.price_tests``: the engine's price test of each added line, as a fact beside
    the proposals — the entry of an unanswered question, the same entry once the answer is
    stored, and for an answer of true what the engine did: passed on the attestation, reason
    ``attested``, with the price and the entry's range or point complete — a price outside the
    range beside an attestation is exactly what a reviewer must be able to read, and nothing is
    concluded from the two figures. A line the engine does not test has no entry."""
    below = {
        "value": False,
        "reason_key": "modifications.prefill.priced_at_ssp.below_range",
        "params": {
            "price": "60000",
            "low": "69750",
            "high": "85250",
            "ssp_version_key": "US-LIST@v1",
        },
    }

    def stated(test: TraceNode | None, **answers: bool) -> dict[str, dict[str, Any]]:
        nodes = [_class("O1", "D", "SERIES", "0.35"), _class("O2", "D", "NEW_DISTINCT")]
        return modifications.price_tests(
            _row(questionnaire={"O2": answers} if answers else {}),
            _by_id(*nodes, *([] if test is None else [test])),
            external_id="SF-ORD-10002",
        )

    computed = _price_test("O2", "60000", passed=False)
    assert stated(computed) == {"O2": below}
    # the proposal of the unanswered question is this very entry
    proposed = modifications.questionnaire_prefill(
        _row(), K02_NODES, external_id="SF-ORD-10002", classified=["O1", "O2"]
    )
    assert proposed["O2"]["priced_at_ssp"] == below
    assert stated(computed, added_goods_distinct=True, priced_at_ssp=False) == {"O2": below}

    def attested(**params: str) -> dict[str, Any]:
        test = _price_test("O2", "60000", passed=True, basis="ATTESTED", **params)
        return stated(test, added_goods_distinct=True, priced_at_ssp=True)["O2"]

    assert attested() == {
        "value": True,
        "reason_key": "modifications.prefill.priced_at_ssp.attested",
        "params": {
            "price": "60000",
            "low": "69750",
            "high": "85250",
            "ssp_version_key": "US-LIST@v1",
        },
    }
    assert attested(point="77500", low="", high="", mid="") == {
        "value": True,
        "reason_key": "modifications.prefill.priced_at_ssp.attested",
        "params": {
            "price": "60000",
            "point": "77500",
            "point_tolerance_pct": "0",
            "ssp_version_key": "US-LIST@v1",
        },
    }
    assert attested(low="", high="", mid="", version_key="") == {
        "value": True,
        "reason_key": "modifications.prefill.priced_at_ssp.attested",
        "params": {"price": "60000", "ssp_version_key": ""},
    }
    # no test of the engine, no entry: O1 is not an added line, and O2 here has no node
    assert stated(None) == {}
    assert (
        modifications.price_tests(
            _row(lines=[{"obligation_key": "O1", "action": "CHANGE"}]),
            K02_NODES,
            external_id="SF-ORD-10002",
        )
        == {}
    )


def test_prefill_covers_only_what_the_engine_classified() -> None:
    """Existing obligations: class D reasons answer Yes, a partially satisfied non-distinct
    obligation No, a satisfied one has nothing remaining (no answer). An added line is answered
    only from a class of its own — ``NEW_UNSTARTED`` is a non-distinct new obligation; a line the
    engine integrated into an existing obligation, or built no draft for, is left to the
    preparer. Keys are matched in their CV-21 encoded form."""
    row = _row(
        lines=[
            {"obligation_key": "POB #7", "action": "ADD", "product_code": "P"},
            {"obligation_key": "O8", "action": "ADD", "product_code": "P"},
            {"obligation_key": "O1", "action": "CHANGE"},
        ]
    )
    nodes = _by_id(
        _class("O1", "D", "UNSTARTED"),
        _class("O3", "D", "DISTINCT_UNITS", "0.5"),
        _class("O4", "N", "PARTIALLY_SATISFIED", "0.5"),
        _class("O5", "S", "SATISFIED", "1"),
        _class("POB %237", "D", "NEW_UNSTARTED"),
    )
    found = modifications.questionnaire_prefill(
        row, nodes, external_id="SF-ORD-10002", classified=["O1", "O3", "O4", "O5", "POB #7"]
    )
    remaining = "remaining_goods_distinct_from_transferred"
    assert {key: list(value) for key, value in found.items()} == {
        "O1": [remaining],
        "O3": [remaining],
        "O4": [remaining],
        "POB #7": ["added_goods_distinct"],
    }
    assert [found[key][remaining]["value"] for key in ("O1", "O3", "O4")] == [True, True, False]
    assert found["O4"][remaining]["reason_key"].endswith(".partially_satisfied")
    assert found["POB #7"]["added_goods_distinct"] == {
        "value": False,
        "reason_key": "modifications.prefill.added_goods_distinct.new_unstarted",
        "params": {},
    }


def test_classify_returns_the_prefill_and_stores_none_of_it() -> None:
    """Source witness (the database witness is ``test_br_mod_01_…``): ``classify`` derives the
    prefill from the proposal nodes after the proposal is read, returns it in the response and
    writes no ``questionnaire`` value — a stored prefill would come back to the engine as the
    preparer's answer."""
    import inspect

    source = inspect.getsource(modifications.classify)
    assert source.index("_proposal(output, row)") < source.index("questionnaire_prefill(")
    assert source.index("questionnaire_prefill(") < source.index("transitions.apply(")
    written = source[source.index("set_values={") : source.index("uow.audit(")]
    assert '"questionnaire"' not in written
    assert '"questionnaire": _prefilled(row["questionnaire"], reasons)' in source


# --- item MOD-CLASSIFICATION-KEYS-1: the three members of a stored classification -----------------

_DETAIL: dict[str, str] = {
    "class[O1]": "D",
    "class[proposal]": "D",
    "modification_key": str(ROW_ID),
}
_PROPOSED: dict[str, Any] = {
    "value": True,
    "reason_key": "modifications.prefill.added_goods_distinct.new_distinct",
    "params": {},
}
_TESTED: dict[str, Any] = {
    "value": False,
    "reason_key": "modifications.prefill.priced_at_ssp.below_range",
    "params": {"price": "60000", "low": "69750", "high": "85250"},
}
_QUESTIONS: dict[str, Any] = {"added_goods_distinct": _PROPOSED, "priced_at_ssp": _TESTED}


def test_mod_classification_keys_1_the_stored_classification_is_read_by_its_three_members() -> None:
    """04 T-CON-06 ``classification`` rev 1.286: the engine's detail, the obligations' proposals
    and the price tests, each under its member — so an obligation may bear any key, a member's
    name too. A classification that proposes nothing and tests nothing is one still."""
    stored = {
        "proposal": _DETAIL,
        "obligations": {
            "proposal": _QUESTIONS,
            "price_tests": _QUESTIONS,
            "obligations": _QUESTIONS,
        },
        "price_tests": {"proposal": _TESTED, "price_tests": _TESTED, "obligations": _TESTED},
    }
    assert modifications.stored_classification(stored) == (
        _DETAIL,
        stored["obligations"],
        stored["price_tests"],
    )
    bare = {"proposal": _DETAIL, "obligations": {}, "price_tests": {}}
    assert modifications.stored_classification(bare) == (_DETAIL, {}, {})


def test_questionnaire_proposals_need_explicit_answers_including_false() -> None:
    row = {
        "classification": {
            "proposal": _DETAIL,
            "obligations": {"O2": _QUESTIONS},
            "price_tests": {"O2": _TESTED},
        },
        "questionnaire": {},
    }
    errors = modifications.questionnaire_confirmation_errors(row)
    assert [(error.field, error.rule_id) for error in errors] == [
        ("questionnaire.O2.added_goods_distinct", "REQ-MOD-002"),
        ("questionnaire.O2.priced_at_ssp", "REQ-MOD-002"),
    ]
    assert row["questionnaire"] == {}  # Reading the proposal never confirms it.
    row["questionnaire"] = {"O2": {"added_goods_distinct": True}}
    assert [error.field for error in modifications.questionnaire_confirmation_errors(row)] == [
        "questionnaire.O2.priced_at_ssp"
    ]
    row["questionnaire"] = {"O2": {"added_goods_distinct": True, "priced_at_ssp": False}}
    assert modifications.questionnaire_confirmation_errors(row) == []


@pytest.mark.parametrize("value", ["true", "false", 0, 1, [], {}])
def test_questionnaire_answers_do_not_accept_truthy_substitutes(value: Any) -> None:
    errors = modifications.questionnaire_value_errors({"O2": {"priced_at_ssp": value}})
    assert [(error.field, error.rule_id) for error in errors] == [
        ("questionnaire.O2.priced_at_ssp", "REQ-MOD-002")
    ]


def test_questionnaire_confirmation_requires_readable_classification() -> None:
    assert modifications.questionnaire_confirmation_errors({"classification": None})[0].field == (
        "classification"
    )
    assert (
        modifications.questionnaire_confirmation_errors(
            {"classification": {"proposal": _DETAIL, "obligations": {}, "price_tests": {}}}
        )
        == []
    )
    assert (
        modifications.questionnaire_value_errors(
            {"price_change_settlement": "CREDIT_OR_REFUND", "separate_contract_external_id": "NEW"}
        )
        == []
    )


def test_mod_classification_keys_1_a_classification_stored_flat_reads_as_none() -> None:
    """The supervisor's ruling of 2026-10-02 (D-99 (3)): what ``classify`` stored before the item
    — the obligations' entries beside ``proposal`` and ``price_tests`` — reads as none, and so
    does everything that is not the three members by NAME AND SHAPE: the two collisions as they
    were stored, and the flat row whose only obligation was keyed ``obligations``, where the
    member holds one obligation's questions and not obligations."""
    none: tuple[dict[str, Any], dict[str, Any], dict[str, Any]] = ({}, {}, {})
    remaining = {"remaining_goods_distinct_from_transferred": _PROPOSED}
    flat = {"proposal": _DETAIL, "O1": remaining, "O2": _QUESTIONS, "price_tests": {"O2": _TESTED}}
    keyed_proposal = {"proposal": _QUESTIONS, "O1": remaining, "price_tests": {"proposal": _TESTED}}
    keyed_price_tests = {
        "proposal": _DETAIL,
        "O1": remaining,
        "price_tests": {"price_tests": _TESTED},
    }
    keyed_obligations = {
        "proposal": _DETAIL,
        "obligations": _QUESTIONS,
        "price_tests": {"obligations": _TESTED},
    }
    not_the_members: tuple[Any, ...] = (
        None,
        {},
        [],
        "classified",
        flat,
        keyed_proposal,
        keyed_price_tests,
        keyed_obligations,
        {"proposal": _DETAIL, "obligations": {}},  # a member is missing
        {"proposal": _DETAIL, "obligations": {}, "price_tests": {}, "O1": remaining},  # one more
        {"proposal": [], "obligations": {}, "price_tests": {}},
        {"proposal": _DETAIL, "obligations": {"O1": _PROPOSED}, "price_tests": {}},
        {"proposal": _DETAIL, "obligations": {}, "price_tests": {"O2": {"value": True}}},
    )
    for value in not_the_members:
        assert modifications.stored_classification(value) == none, value


# --- REQ-PLT-015: one retained snapshot -----------------------------------------------------------


def test_preview_document_carries_the_request_sides_beside_summary_and_provenance() -> None:
    """04 §16.14 rev 1.92: the retained ``IMPACT_PREVIEW`` document holds the request's ``before``
    / ``after`` members (04 §16.10) beside ``summary`` and ``provenance``."""
    summary = _summary()
    row = {**_row(), "row_version": 4, "chosen_treatments": {"O2": "PROSPECTIVE"}}
    row.update(
        effective_date=date(2026, 9, 16),
        ssp_basis={},
        noncash_consideration=None,
        consideration_payable=None,
        scope_605_35=None,
    )
    document = modifications._preview_document(
        summary,
        bundle_sha256="b" * 64,
        engine_version="1.0.0",
        known_at=datetime(2026, 9, 12, 12, tzinfo=UTC),
        current={"id": uuid4(), "head_stream_version": 2},
        row=row,
        event=modifications._amended_event(row, approval_request_id=None),
        basis={"modifications": []},
        fx_basis={},
    )
    assert sorted(document) == ["after", "before", "provenance", "summary"]
    data = summary.model_dump(mode="json")
    assert (document["before"], document["after"]) == modifications.request_sides(data)
    assert document["summary"] == data
    assert document["before"]["remaining_allocation"] == data["remaining_allocation_before"]
    assert document["after"]["catch_up_total"] == data["catch_up_total"]
    assert document["after"]["rpo"] == data["rpo_after"]
    assert "provenance" not in document["after"]  # one copy, at the top level


def test_submit_hands_the_rows_retained_snapshot_to_the_request() -> None:
    """The request's impact preview IS the row's retained file and hash (REQ-PLT-015: the preview
    is stored with the approval as a hashed snapshot) — never a second document derived from
    it."""
    file_id, sha = uuid4(), "a" * 64
    row = {"impact_preview_file_id": file_id, "impact_preview_sha256": sha}
    document = {"before": {"rpo": _money("1.00")}, "after": {"rpo": _money("2.00")}}
    handed = modifications._impact_preview(row, document)
    assert (handed.retained_file_id, handed.retained_sha256) == (file_id, sha)
    assert handed.sha256() == sha
    assert (handed.before, handed.after) == (document["before"], document["after"])


def test_kernel_impact_preview_retained_snapshot_names_file_and_hash_together() -> None:
    """DG-KRN-APR-01 rev 1.75: without a retained snapshot the request's hash is the canonical
    ``{before, after}`` hash; a retained snapshot names its file AND its hash."""
    plain = approvals.ImpactPreview(before={"a": 1}, after={"a": 2})
    assert plain.sha256() == approvals.preview.preview_sha256({"a": 1}, {"a": 2})
    with pytest.raises(ValueError, match="names its file and its hash"):
        approvals.ImpactPreview(before={}, after={}, retained_file_id=uuid4())
    with pytest.raises(ValueError, match="names its file and its hash"):
        approvals.ImpactPreview(before={}, after={}, retained_sha256="a" * 64)


def test_only_the_modification_submission_hands_a_retained_snapshot_to_the_kernel() -> None:
    """DG-KRN-APR-01 rev 1.75 is an ADDITION: every other ``ImpactPreview(...)`` call of the
    product (activation, estimates, void, imports, roles, SoD ×2, support grants, users, policy
    overrides, reference commands ×2: the principal-agent change and, since security finding
    SN-7, the change of a product's policy values; the request to shred an evidence file; the
    grant of an API client's scopes) names ``before`` and ``after`` only, so the kernel takes
    the branch it always took — ``store_preview`` over the canonical ``{before, after}`` — and
    those requests' files and hashes are what they were."""
    import ast
    import inspect
    from pathlib import Path

    import erev_api

    root = Path(inspect.getfile(erev_api)).parent
    calls: dict[str, list[set[str]]] = {}
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else None
            name = node.func.id if isinstance(node.func, ast.Name) else name
            if name != "ImpactPreview":
                continue
            assert not node.args, f"{path}: ImpactPreview is built by keyword"
            calls.setdefault(str(path.relative_to(root)), []).append(
                {str(keyword.arg) for keyword in node.keywords}
            )
    retained = {"retained_file_id", "retained_sha256"}
    handing = {name for name, found in calls.items() if any(keys & retained for keys in found)}
    # + the manual adjustment (BUILD_SPEC CLO-12, lane F-CLO-A; dev-guide DG-KRN-APR-01 rev 1.98):
    # the second subject whose own row holds its preview (04 T-SL-05 ``impact_preview_file_id``,
    # as T-CON-06 does), retained by ``adjustments.submit`` before the submission — its posting
    # request and the deferral request that may replace it keep that one file.
    assert handing == {"domain/contracts/modifications.py", "domain/journals/adjustments.py"}
    assert calls["domain/contracts/modifications.py"] == [{"before", "after"} | retained]
    assert calls["domain/journals/adjustments.py"] == [{"before", "after"} | retained]
    others = {name: found for name, found in calls.items() if name not in handing}
    # + the request to shred an evidence file (lane SECFIX-IMP part B; supervisor rulings R-49 (a)
    # and R-86; ``domain/platform/evidence_shred.request_shred``): ``before`` and ``after`` only —
    # the proposal is the preview, stored by the kernel as every other.
    # + the grant of an API client's scopes (lane SECFIX-APR; supervisor ruling R-38 (iii);
    # ``auth/api_clients.create_api_client``): ``before`` and ``after`` only — the grant's
    # proposal is the preview of its ``ROLE_ASSIGNMENT`` request.
    assert sum(len(found) for found in others.values()) == 14 and len(others) == 12, sorted(others)
    assert all(keys == {"before", "after"} for found in others.values() for keys in found)
    submit = inspect.getsource(approvals.submit)
    assert "if impact_preview.retained_file_id is not None:" in submit
    assert "preview.store_preview(" in submit.split("else:", 1)[1]


def test_mod_linked_estimates_1_the_approval_hook_refuses_as_the_backstop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item MOD-LINKED-ESTIMATES-1 (supervisor's ruling of 2026-10-01; 04 §16.14 rev 1.210; PRD
    ERR-87). The rule is at the submission; the approval's check is the backstop. No command, no
    DB-03 pair and no request basis leads to it — nothing links to a modification once it is
    submitted, an approved version does not go back, and a link written afterwards changes the
    content the request pins — so it is reached here with a linked version handed to the hook:
    after the locks and the fresh-basis check, before anything is applied, one entry for every
    version that is not approved, ending on the approval. APPROVED and SUPERSEDED pass; a
    discarded version does not count."""
    change, contract_id, request = uuid4(), uuid4(), uuid4()
    row = {"id": change, "contract_id": contract_id, "status": "SUBMITTED", "kind": "CO_TERM"}
    steps: list[str] = []

    def linked(session: Any, modification_ids: Any) -> list[dict[str, Any]]:
        steps.append("linked")
        assert list(modification_ids) == [change]
        return [
            {"element_code": "REBATE-MH-01", "version_no": 1, "status": "SUPERSEDED"},
            {"element_code": "REBATE-MH-01", "version_no": 2, "status": "APPROVED"},
            {"element_code": "REBATE-MH-01", "version_no": 3, "status": "VOIDED"},
            {"element_code": "REBATE-MH-01", "version_no": 4, "status": "WITHDRAWN"},
            {"element_code": "RETURNS-01", "version_no": 1, "status": "DRAFT"},
        ]

    def applied_too_early(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the decision was applied past the backstop")

    monkeypatch.setattr(modifications, "modification_rows", lambda session, subject: [row])
    monkeypatch.setattr(
        modifications,
        "lock_group_then_contract",
        lambda session, found: (steps.append("locks"), (uuid4(), {"id": found}))[1],
    )
    monkeypatch.setattr(modifications, "_row", lambda session, subject, *, lock=False: row)
    monkeypatch.setattr(
        modifications.approvals, "assert_fresh_basis", lambda uow, found: steps.append("fresh")
    )
    monkeypatch.setattr(modifications, "linked_estimate_versions", linked)
    monkeypatch.setattr(modifications, "_preparer", applied_too_early)
    monkeypatch.setattr(modifications, "_apply_row", applied_too_early)
    with pytest.raises(Problem) as refused:
        modifications._approved(SimpleNamespace(session=object()), change, request)  # type: ignore[arg-type]
    assert refused.value.slug == "invalid-transition"
    assert [(error.field, error.rule_id, error.message) for error in refused.value.errors] == [
        (
            None,
            "SM-03",
            "Estimate version REBATE-MH-01 v4 of this modification is not approved. "
            "The modification is approved after it.",
        ),
        (
            None,
            "SM-03",
            "Estimate version RETURNS-01 v1 of this modification is not approved. "
            "The modification is approved after it.",
        ),
    ]
    assert steps == ["locks", "fresh", "linked"]
