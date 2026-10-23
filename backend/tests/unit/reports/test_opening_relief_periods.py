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
