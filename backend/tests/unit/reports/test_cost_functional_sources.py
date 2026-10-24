"""Cost rollforward reads posted functional amounts, retaining legacy source bindings."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams, SourceBinding, SourceCollector
from erev_api.domain.reports.builders import contract_cost_rollforward as costs
from erev_api.problems import Problem


@pytest.mark.parametrize(
    "view,legacy,currency,amount",
    [
        ("functional", False, "EUR", 9000),
        ("reporting", False, "EUR", 9000),
        ("transaction", False, "USD", 10000),
        ("functional", True, "USD", 10000),
    ],
)
def test_posted_source_currency_and_legacy_binding(view, legacy, currency, amount):
    eid, line_id = uuid4(), uuid4()
    at = datetime.now(UTC)
    sources = SourceCollector()
    binding = (
        SourceBinding(
            at,
            {},
            {"entity_code": {str(eid): "E"}},
            frozenset(),
            members={"subledger_line": (str(line_id),)},
        )
        if legacy
        else None
    )
    params = ReportParams(
        costs.CODE, 1, {"currency_view": view}, (eid,), at, binding=binding, sources=sources
    )
    period = tie_outs.PeriodRef(
        uuid4(), "FY2026-P01", "Jan", 2026, 1, 1, date(2026, 1, 1), date(2026, 1, 31)
    )
    row = dict(
        id=line_id,
        entity_id=eid,
        entity_code="E",
        external_id="C",
        account_role="COST_TO_OBTAIN_ASSET",
        entry_kind="CONTRACT_COST_CAPITALIZATION",
        dr_cr="D",
        reason_code=None,
        amount_txn=Decimal(100),
        txn_currency="USD",
        amount_functional=Decimal(90),
        functional_currency="EUR",
        period_end_date=period.end,
    )
    statements = []

    def execute(statement):
        statements.append(str(statement))
        return SimpleNamespace(mappings=lambda: [row])

    session = SimpleNamespace(execute=execute)
    movements = costs._movements(
        session,
        entity_ids=(eid,),
        book_code="ASC606",
        periods={eid: (period,)},
        known_at=at,
        params=params,
    )
    assert movements[0].currency == currency
    assert movements[0].amount_minor == amount
    assert "subledger_line.amount_functional" in statements[0]
    if not legacy:
        assert str(line_id) in sources.members["subledger_line"]
    entity = tie_outs.EntityRef(eid, "E", uuid4(), "EUR", "UTC")
    if legacy:
        with pytest.raises(Problem):
            costs._check_view(params, (entity,), movements)
    else:
        costs._check_view(params, (entity,), movements)


def test_build_converts_closing_cost_balance_for_tie_out(monkeypatch):
    eid = uuid4()
    entity = tie_outs.EntityRef(eid, "E", uuid4(), "EUR", "UTC")
    period = tie_outs.PeriodRef(
        uuid4(), "FY2026-P01", "Jan", 2026, 1, 1, date(2026, 1, 1), date(2026, 1, 31)
    )
    params = ReportParams(
        costs.CODE,
        1,
        {"currency_view": "functional"},
        (eid,),
        datetime.now(UTC),
        sources=SourceCollector(),
    )
    original = tie_outs.BalanceRow(
        uuid4(), "C", None, eid, "E", "USD", uuid4(), {"cost_asset_carrying": Decimal(100)}
    )
    monkeypatch.setattr(tie_outs, "book_of", lambda *a: "ASC606")
    monkeypatch.setattr(costs, "ranges", lambda *a: ((entity,), {eid: (period,)}, {eid: None}))
    monkeypatch.setattr(
        costs,
        "_movements",
        lambda *a, **kw: [
            costs.CostMovement("E", "OBTAIN", "ADDITIONS", 9000, "EUR", True, "C", period.end)
        ],
    )
    monkeypatch.setattr(tie_outs, "cutoff_for", lambda *a: params.known_at)
    monkeypatch.setattr(tie_outs, "balances_at", lambda *a, **kw: [original])
    reader = object()
    monkeypatch.setattr(costs.locked_ends, "Reader", lambda *a, **kw: reader)

    def functional(session, actual_params, rows, **kwargs):
        assert rows == [original]
        assert kwargs["measures"] == ("cost_asset_carrying",)
        assert kwargs["locked"] is reader
        return (replace(original, currency="EUR", values={"cost_asset_carrying": Decimal(90)}),)

    monkeypatch.setattr(costs.functional_balances, "read", functional)
    result = costs.build(SimpleNamespace(session=None), params)
    assert result.control_totals["closing"] == {"EUR": "90.00"}
    assert result.tie_out_results[0]["result"] == "PASS"
    assert params.sources.evidence[costs.FUNCTIONAL_EVIDENCE] is True
