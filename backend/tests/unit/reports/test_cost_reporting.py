"""Reporting cost movements conserve monthly FX and independently checked carrying balances."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from erev_api.domain.reports import cost_reporting, reporting_currency, tie_outs
from erev_api.domain.reports.builders import ReportParams, SourceCollector
from erev_api.domain.reports.builders.contract_cost_rollforward import CostMovement
from erev_api.problems import Problem


def world(monkeypatch):
    eid = uuid4()
    entity = tie_outs.EntityRef(eid, "E", uuid4(), "USD", "UTC")
    ends = [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
    periods = tuple(
        tie_outs.PeriodRef(uuid4(), str(n), str(n), 2026, n, 1, d.replace(day=1), d)
        for n, d in enumerate(ends, 1)
    )
    params = ReportParams(
        "contract_cost_rollforward",
        1,
        {"currency_view": "reporting"},
        (eid,),
        datetime.now(UTC),
        sources=SourceCollector(),
    )
    uow = SimpleNamespace(session=None, principal=SimpleNamespace(tenant_id=uuid4()))
    calls = []

    def rates(*args, periods, rate_type, **kwargs):
        month = periods[eid].period_no
        calls.append((month, rate_type))
        value = ({1: "1.5", 2: "3", 3: "5"} if rate_type == "closing" else {2: "2", 3: "4"})[month]
        return reporting_currency.Translation("GBP", {eid: {"rate": value, "base_currency": "USD"}})

    monkeypatch.setattr(reporting_currency, "rates_for_period", rates)
    return uow, params, entity, periods, calls


def movement(period, amount, code="ADDITIONS", kind="OBTAIN", in_range=True):
    return CostMovement(
        "E", kind, code, int(Decimal(amount) * 100), "USD", in_range, "C", period.end
    )


def balance(entity, amount):
    return tie_outs.BalanceRow(
        uuid4(), "C", None, entity.id, "E", "USD", uuid4(), {"cost_asset_carrying": Decimal(amount)}
    )


def test_monthly_rates_are_not_replaced_with_one_range_average(monkeypatch):
    uow, params, entity, ps, calls = world(monkeypatch)
    data = cost_reporting.build(
        uow,
        params,
        (entity,),
        {entity.id: ps[1:]},
        {entity.id: ps[0]},
        [
            movement(ps[0], "100", in_range=False),
            movement(ps[1], "20"),
            movement(ps[1], "-10", "AMORTIZATION"),
            movement(ps[2], "30"),
            movement(ps[2], "-20", "AMORTIZATION"),
        ],
        [balance(entity, "120")],
    )
    values = {r["line_code"]: Decimal(r["amount"]["amount"]) for r in data.rows}
    assert {
        k: values[k] for k in ("OPENING", "ADDITIONS", "AMORTIZATION", "FX", "ROUNDING", "CLOSING")
    } == {
        "OPENING": 150,
        "ADDITIONS": 160,
        "AMORTIZATION": -100,
        "FX": 390,
        "ROUNDING": 0,
        "CLOSING": 600,
    }
    assert data.tie_out_results[0]["result"] == "PASS"
    assert set(calls) == {
        (1, "closing"),
        (2, "closing"),
        (2, "average"),
        (3, "closing"),
        (3, "average"),
    }


def test_rounding_conserves_category_endpoint_and_source_failure_remains_visible(monkeypatch):
    uow, params, entity, ps, _ = world(monkeypatch)
    monkeypatch.setattr(
        reporting_currency,
        "rates_for_period",
        lambda *a, **k: reporting_currency.Translation(
            "GBP", {entity.id: {"rate": "1.5", "base_currency": "USD"}}
        ),
    )
    moves = [movement(ps[1], ".01"), movement(ps[1], ".01", kind="FULFILL")]
    args = (uow, params, (entity,), {entity.id: (ps[1],)}, {entity.id: ps[0]}, moves)
    data = cost_reporting.build(*args, [balance(entity, ".02")])
    assert data.control_totals["closing"] == {"GBP": "0.03"}
    assert data.tie_out_results[0]["result"] == "PASS"
    assert sum(
        Decimal(r["amount"]["amount"]) for r in data.rows if r["line_code"] == "ROUNDING"
    ) == Decimal("-.01")
    broken = cost_reporting.build(*args, [balance(entity, ".03")])
    assert broken.tie_out_results[0]["result"] == "FAIL"
    assert broken.control_totals["functional_source_check"]["result"] == "FAIL"


def test_nonzero_opening_cannot_invent_a_rate(monkeypatch):
    uow, params, entity, ps, _ = world(monkeypatch)
    with pytest.raises(Problem):
        cost_reporting.build(
            uow,
            params,
            (entity,),
            {entity.id: (ps[1],)},
            {},
            [movement(ps[0], "1", in_range=False)],
            [balance(entity, "1")],
        )
