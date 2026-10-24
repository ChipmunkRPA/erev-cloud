from decimal import Decimal as D
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from erev_api.problems import Problem
from erev_api.domain.reports.opening_relief_periods import deltas
from erev_api.domain.reports.opening_relief_reporting_pob import translate


def test_original_opening_is_not_reset_and_reversal_uses_its_own_average_rate():
    a, b, entity, contract = (uuid4() for _ in range(4))
    entries = [
        NS(period_id=p, subject_key="pob", flow=NS(is_revenue=True, amount=D(value)))
        for p, value in ((a, "120"), (b, "-40"))
    ]
    amounts = deltas(
        periods=[a, b],
        opening=D(100),
        obligations={"pob": D(100)},
        entries=entries,
        consumption={a: D(120), b: D(-40)},
        expected=D(80),
    )
    assert amounts == {a: D(100), b: D(-20)}
    rows = [{"row_key": "combined:test", "entity_code": "UK", "summary": "A; B"}]
    projected = [
        NS(
            contract_id=contract,
            entity_id=entity,
            currency="USD",
            lines={
                "OPENING": {"contract_liability": D(110)},
                "REVENUE_FROM_OPENING": {
                    "contract_asset": D(0),
                    "unbilled_receivable": D(0),
                    "contract_liability": D(-100),
                },
            },
        )
    ]
    slices = {
        "test": {
            "row_key": "combined:test",
            "entity": entity,
            "members": [(contract, entity)],
            "currency": "GBP",
            "periods": amounts,
        }
    }
    periods = {entity: (NS(id=a, key="A"), NS(id=b, key="B"))}
    rates = [
        {
            "entity_code": "UK",
            "period_key": key,
            "rate_type": "average",
            "base_currency": "GBP",
            "quote_currency": "USD",
            "rate": rate,
        }
        for key, rate in (("A", "1.2"), ("B", "1.5"))
    ]
    translate(rows, slices, projected, periods, rates)
    assert rows[0]["revenue_from_opening"] == {"amount": "90.00", "currency": "USD"}
    assert rows[0]["summary"] == "A; B"
    with pytest.raises(Problem) as exc:
        deltas(
            periods=[a, b],
            opening=D(100),
            obligations={"pob": D(100)},
            entries=entries,
            consumption={a: D(120), b: D(-40)},
            expected=D(100),
        )

    assert "reconcile" in exc.value.errors[0].message


def test_agent_periods_cap_net_income_by_original_opening_source_eligibility():
    a, b = uuid4(), uuid4()

    def entry(period, amount):
        return NS(period_id=period, subject_key="agent", flow=NS(is_revenue=True, amount=D(amount)))

    # First period earns 25 from original opening sources and 15 from current receipts.
    # Next period reverses 10 of opening-sourced net income.
    entries = [entry(a, "40"), entry(b, "-10")]
    amounts = deltas(
        periods=[a, b],
        opening=D(100),
        obligations={"agent": D(100)},
        entries=entries,
        consumption={a: D(100), b: D(-20)},
        expected=D(15),
        source_eligibility={"agent": [entry(a, "25"), entry(b, "-10")]},
    )
    assert amounts == {a: D(25), b: D(-10)}
    with pytest.raises(Problem):
        deltas(
            periods=[a, b],
            opening=D(100),
            obligations={"agent": D(100)},
            entries=entries,
            consumption={a: D(100), b: D(-20)},
            expected=D(15),
            source_eligibility={"agent": [entry(uuid4(), "25")]},
        )


def test_agent_reporting_translates_net_revenue_not_gross_control_path():
    entity, contract, a, b = (uuid4() for _ in range(4))
    rows = [{"row_key": "agent", "entity_code": "UK"}]
    projected = [
        NS(
            contract_id=contract,
            entity_id=entity,
            currency="USD",
            lines={
                "OPENING": {"contract_liability": D(120)},
                "REVENUE_FROM_OPENING": {
                    "contract_asset": D(0),
                    "unbilled_receivable": D(0),
                    "contract_liability": D(-120),
                },
            },
        )
    ]
    slices = {
        "agent": {
            "row_key": "agent",
            "entity": entity,
            "members": [(contract, entity)],
            "currency": "GBP",
            "periods": {a: D(25), b: D(-10)},
            "net_revenue": {a: D(40), b: D(-10)},
        }
    }
    periods = {entity: (NS(id=a, key="A"), NS(id=b, key="B"))}
    rates = [
        {
            "entity_code": "UK",
            "period_key": key,
            "rate_type": "average",
            "base_currency": "GBP",
            "quote_currency": "USD",
            "rate": rate,
        }
        for key, rate in (("A", "1.2"), ("B", "1.5"))
    ]
    translate(rows, slices, projected, periods, rates)
    assert rows[0]["revenue_recognized"] == {"currency": "USD", "amount": "33.00"}
    assert rows[0]["revenue_from_opening"] == {"currency": "USD", "amount": "15.00"}
