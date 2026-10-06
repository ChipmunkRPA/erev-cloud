"""frps3c-2 CPU tests (FAIL-FIRST: written before the code; the first run must fail on the missing
`tie_outs.require_members` and on the contracts still declaring the memberships open)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal, getcontext
from fractions import Fraction
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

import pytest
from erev_api.domain.reports import framework, tie_outs
from erev_api.domain.reports.builders import ADAPTER, ReportParams, SourceBinding, SourceCollector
from erev_api.problems import Problem
from sqlalchemy.orm import Session

K = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
US01 = uuid5(NAMESPACE_URL, "erev://tests/entity/US01")
L1 = uuid5(NAMESPACE_URL, "erev://tests/line/1")
L2 = uuid5(NAMESPACE_URL, "erev://tests/line/2")
P1 = uuid5(NAMESPACE_URL, "erev://tests/product/1")
BOUND = SourceBinding(
    cutoff=K,
    versions={"ASC606": ()},
    labels={"product_family": {str(P1): "Platform"}, "product_revenue_category": {str(P1): None}},
    members={"subledger_line": (str(L1), str(L2))},
    row_keys=frozenset(),
)


def _params(**over: Any) -> ReportParams:
    base: dict[str, Any] = {
        "report_code": "contract_balances",
        "report_version": 1,
        "parameters": {},
        "entity_ids": (US01,),
        "known_at": K,
        "book_code": "ASC606",
    }
    base.update(over)
    return ReportParams(**base)


def test_require_members_refuses_by_name_a_bound_line_the_read_did_not_return() -> None:
    """D4: exact identities, never counts — a read that returned L1 and an UNBOUND line L3 (same
    count as the two bound ids) still refuses, naming the missing L2."""
    bound = _params(binding=BOUND)
    tie_outs.require_members(bound, "subledger_line", (L1, L2))  # exactly the bound ids: fine
    other = uuid5(NAMESPACE_URL, "erev://tests/line/3")
    with pytest.raises(Problem) as missing:
        tie_outs.require_members(bound, "subledger_line", (L1, other))
    assert "members.subledger_line" in str(missing.value.detail) and str(L2) in str(
        missing.value.detail
    )
    assert str(L1) not in str(missing.value.detail)
    tie_outs.require_members(
        _params(sources=SourceCollector()), "subledger_line", ()
    )  # live: nothing


def test_the_bound_member_predicate_restricts_within_scope_and_records_live() -> None:
    from erev_api.db.tables import subledger_line

    bound = tie_outs.bound_member_where(
        _params(binding=BOUND), "subledger_line", subledger_line.c.id
    )
    assert len(bound) == 1 and "subledger_line.id IN" in str(bound[0])
    assert tie_outs.bound_member_where(_params(), "subledger_line", subledger_line.c.id) == []
    collector = SourceCollector()
    tie_outs.record_members(_params(sources=collector), "subledger_line", (L1, L2))
    assert collector.members["subledger_line"] == {str(L1), str(L2)}


def test_disaggregation_product_labels_are_bound_values_never_the_live_join() -> None:
    bound = _params(report_code="disaggregation", binding=BOUND)
    assert tie_outs.label_for(bound, "product_family", P1, "Renamed") == "Platform"
    assert (
        tie_outs.label_for(bound, "product_revenue_category", P1, "SUBSCRIPTION") is None
    )  # retained null
    with pytest.raises(Problem):
        tie_outs.label_for(
            bound, "product_family", uuid5(NAMESPACE_URL, "erev://tests/product/2"), "X"
        )


def test_the_balance_family_and_disaggregation_declare_nothing_open_and_name_the_memberships() -> (
    None
):
    for code in (
        "contract_balances",
        "contract_balance_rollforward",
        "contract_cost_rollforward",
        "revenue_from_opening_liability",
        "disaggregation",
    ):
        contract = framework.SOURCE_CONTRACTS[code]
        assert contract.strategy == ADAPTER and contract.open == (), code
        assert any(
            "subledger-line membership (the consumed line ids" in item for item in contract.bound
        ), code
    assert any(
        "product grouping labels" in item
        for item in framework.SOURCE_CONTRACTS["disaggregation"].bound
    )
    # the remaining OPEN dimension of any adapter is C4's reference-line population only (3c-3)
    for code, contract in framework.SOURCE_CONTRACTS.items():
        if contract.strategy == ADAPTER and code != "revenue_from_prior_period_obligations":
            assert contract.open == (), code


# --- Codex production-20260921-1004 §1 on 259b7db1: R1 absent vs empty; R2 capture consistency ---


def test_an_absent_membership_kind_refuses_by_name_and_a_captured_empty_one_is_admitted() -> None:
    """R1 (design §10.5): a pre-3c-2 ADAPTER binding whose readers did not capture `subledger_line`
    is refused by NAME before any id is obtained — never a silent `false()` read whose empty result
    passes the missing-id check; an explicit EMPTY population is a captured membership: it reads
    nothing and nothing is missing."""
    from erev_api.db.tables import subledger_line

    absent = _params(binding=replace(BOUND, members={}))
    with pytest.raises(Problem) as refused:
        tie_outs.bound_member_where(absent, "subledger_line", subledger_line.c.id)
    assert "members.subledger_line" in str(refused.value.detail)
    with pytest.raises(Problem) as refused_too:
        tie_outs.require_members(absent, "subledger_line", ())
    assert "members.subledger_line" in str(refused_too.value.detail)
    empty = _params(binding=replace(BOUND, members={"subledger_line": ()}))
    (predicate,) = tie_outs.bound_member_where(empty, "subledger_line", subledger_line.c.id)
    assert str(predicate) == "false"
    tie_outs.require_members(empty, "subledger_line", ())  # captured empty: nothing missing


class _OneStatement:
    """A session stub: `execute` is counted; the given rows come back through `.mappings()`."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.statements: list[Any] = []

    def execute(self, statement: Any) -> _OneStatement:
        self.statements.append(statement)
        return self

    def mappings(self) -> list[dict[str, Any]]:
        return self.rows


C1 = uuid5(NAMESPACE_URL, "erev://tests/contract/1")
C2 = uuid5(NAMESPACE_URL, "erev://tests/contract/2")
LINES = tuple(uuid5(NAMESPACE_URL, f"erev://tests/line/{n}") for n in (1, 2, 3, 4, 5))
SEPTEMBER = tie_outs.PeriodRef(
    id=uuid5(NAMESPACE_URL, "erev://tests/period/2026-09"),
    key="FY2026-P09",
    name="September 2026",
    fiscal_year=2026,
    period_no=9,
    quarter_no=3,
    start=date(2026, 9, 1),
    end=date(2026, 9, 30),
)


def _line(line: Any, contract: Any, role: str, amount: str) -> dict[str, Any]:
    return {
        "id": line,
        "contract_id": contract,
        "entity_id": US01,
        "account_role": role,
        "entry_kind": "REVENUE_RECOGNITION",
        "amount_txn": Decimal(amount),
    }


ROWS = [
    _line(LINES[0], C1, "REVENUE", "-100.00"),
    _line(LINES[1], C1, "REVENUE", "-25.50"),
    _line(LINES[2], C1, "CONTRACT_LIABILITY", "125.50"),
    _line(LINES[3], C2, "CONTRACT_LIABILITY", "40.00"),
    _line(LINES[4], C2, "CONTRACT_LIABILITY", "-60.00"),  # C2's group sums to -20.00: no relief
]


def _activity(rows: list[dict[str, Any]], params: ReportParams) -> tuple[Any, Any, _OneStatement]:
    from erev_api.domain.reports.builders import revenue_from_opening_liability as opening

    session = _OneStatement(rows)
    revenue, relief = opening._activity(
        cast(Session, session),
        entity_ids=(US01,),
        book_code="ASC606",
        periods={US01: (SEPTEMBER,)},
        known_at=K,
        params=params,
    )
    return revenue, relief, session


def test_opening_liability_activity_takes_ids_and_values_from_one_statement() -> None:
    """R2: the ids recorded as members and the amounts summed come from the SAME rows of ONE
    statement (a writer committing between two reads cannot split the population); the group rule
    of the former SQL aggregate is kept (revenue = -Σ REVENUE lines; relief = Σ of a liability
    group's REVENUE_RECOGNITION lines only when that group sum is positive)."""
    collector = SourceCollector()
    live = _params(report_code="revenue_from_opening_liability", sources=collector)
    revenue, relief, session = _activity(ROWS, live)
    assert len(session.statements) == 1
    assert revenue == {(C1, US01): Decimal("125.50")}
    assert relief == {(C1, US01): Decimal("125.50")}
    assert collector.members["subledger_line"] == {str(line) for line in LINES}


def test_opening_liability_bound_read_requires_exactly_the_bound_lines() -> None:
    """R2 + D4 under a binding: the returned population satisfies the bound membership; a bound id
    the statement did not return refuses by NAME with that identity."""
    bound = _params(
        report_code="revenue_from_opening_liability",
        binding=replace(BOUND, members={"subledger_line": tuple(str(line) for line in LINES)}),
    )
    revenue, _, session = _activity(ROWS, bound)
    assert len(session.statements) == 1 and revenue == {(C1, US01): Decimal("125.50")}
    other = uuid5(NAMESPACE_URL, "erev://tests/line/9")
    short = _params(
        report_code="revenue_from_opening_liability",
        binding=replace(
            BOUND, members={"subledger_line": (*(str(line) for line in LINES), str(other))}
        ),
    )
    with pytest.raises(Problem) as missing:
        _activity(ROWS, short)
    assert str(other) in str(missing.value.detail)
    assert "members.subledger_line" in str(missing.value.detail)
    absent = _params(
        report_code="revenue_from_opening_liability", binding=replace(BOUND, members={})
    )
    with pytest.raises(Problem) as refused:
        _activity(ROWS, absent)  # R1 through the real reader: refused before the statement runs
    assert "members.subledger_line" in str(refused.value.detail)
    _, _, empty_session = _activity([], _params(sources=SourceCollector()))
    assert len(empty_session.statements) == 1  # live: a read that finds nothing still records


def test_opening_liability_sums_are_exact_in_every_order() -> None:
    """Codex production-20260921-1035 C2: a cancelling population at numeric(24,4) magnitude —
    10,001 lines of +99999999999999999999.9999 and 10,001 equal negatives — sums to EXACTLY zero in
    either order under the caller's default ``decimal`` context (precision 28): the rational
    accumulation decides the positive-group relief predicate exactly, where a context-rounded
    ``Decimal`` running sum leaves a ±0.0001 residue (the stdlib numeric-domain witness below; not
    an executed DB result). One extra minor unit then decides the relief exactly, in any order."""
    from erev_api.domain.reports.builders import revenue_from_opening_liability as opening

    big = Decimal("99999999999999999999.9999")
    plus = [
        _line(uuid5(NAMESPACE_URL, f"erev://tests/big/+{n}"), C1, "CONTRACT_LIABILITY", str(big))
        for n in range(10_001)
    ]
    minus = [
        _line(uuid5(NAMESPACE_URL, f"erev://tests/big/-{n}"), C1, "CONTRACT_LIABILITY", str(-big))
        for n in range(10_001)
    ]
    assert getcontext().prec == 28  # the caller's context is NOT widened: the sum is rational
    for rows in (plus + minus, minus + plus):
        revenue, relief, session = _activity(rows, _params(sources=SourceCollector()))
        assert len(session.statements) == 1 and revenue == {} and relief == {}
    unit = _line(uuid5(NAMESPACE_URL, "erev://tests/big/unit"), C1, "CONTRACT_LIABILITY", "0.0001")
    for rows in (plus + minus + [unit], [unit] + minus + plus, plus + [unit] + minus):
        _, relief, _ = _activity(rows, _params(sources=SourceCollector()))
        assert relief == {(C1, US01): Decimal("0.0001")}
    # the exact total is rendered from its digits, never through the context
    assert opening.exact_decimal(Fraction(-1234567, 10_000), 4) == Decimal("-123.4567")
    assert opening.exact_decimal(Fraction(10_001) * Fraction(big), 4) == Decimal(
        "1000099999999999999999998.9999"  # 29 significant digits: beyond precision 28, still exact
    )
    with pytest.raises(ValueError):
        opening.exact_decimal(
            Fraction(1, 3), 4
        )  # not a whole number of units: refused, not rounded
    # the defect the rational accumulation avoids (stdlib numeric domain; a reason, not a DB result)
    naive = Decimal(0)
    for row in plus + minus:
        naive += Decimal(row["amount_txn"])
    assert naive != 0
