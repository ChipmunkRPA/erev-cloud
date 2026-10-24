"""Native contract-cost postings and reporting retain capitalisation-date carrying."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from support import bundles
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _build_checkpoint_bundles

from erev_api.domain.reports.functional_balances import project
from erev_engine import compute
from erev_engine.bundle import FxRateInput
from erev_engine.errors import EngineError
from erev_engine.trace import reevaluate


def source():
    key = load(ANSWER_KEY_ROOT / "cost/COST-S8-CONTRACT-COSTS-EX1.yaml")
    (value,) = _build_checkpoint_bundles(key)[-1].bundles
    rates = [
        FxRateInput("cost-spot", "1", "spot", "USD", "EUR", date(2026, 1, 1), None, Decimal(".9"))
    ]
    for period in value.entities[0].periods:
        for kind in ("average", "closing"):
            rates.append(
                FxRateInput(
                    f"{kind}-{period.period_key}",
                    "1",
                    kind,
                    "USD",
                    "EUR",
                    period.end_date,
                    period.period_key,
                    Decimal("1.2"),
                )
            )
    return replace(
        value,
        evidence_revision=55,
        currencies=bundles.currencies("USD", "EUR"),
        entities=tuple(replace(e, functional_currency="EUR") for e in value.entities),
        fx_rates=tuple(
            sorted(
                rates,
                key=lambda r: (
                    r.rate_type,
                    r.base_currency,
                    r.quote_currency,
                    r.effective_date,
                    r.version_key,
                ),
            )
        ),
    )


def test_historical_cost_postings_carrying_and_reporting():
    value = source()
    computed = compute(value)
    assert not [d for d in computed.diagnostics if d.severity == "ERROR"]
    result = computed.books[0]
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
    rows = [r for r in result.balances if r.period_key == "FY2026-P12"]
    assert rows
    row = rows[0]
    assert row.columns["cost_asset_carrying_txn"] == 500000
    stored = {k: Decimal(v) / 100 if isinstance(v, int) else v for k, v in row.columns.items()}
    output = project(
        result.trace,
        external_id=value.contracts[0].external_id,
        entity_code="US01",
        period_key=row.period_key,
        stored=stored,
        version_id=UUID(int=1),
        measures=("cost_asset_carrying",),
    )
    assert output["cost_asset_carrying"] == Decimal("4500")
    lines = [
        line
        for entry in result.posting_intents
        if entry.posting_period_key <= row.period_key
        for line in entry.lines
        if line.account_role == "COST_TO_OBTAIN_ASSET"
    ]
    assert lines
    assert sum((1 if line.side == "D" else -1) * line.amount_functional for line in lines) == 450000
    rate_refs = dict(result.line_rates)
    assert all(rate_refs[line.line_key] == (("cost-spot", "1"),) for line in lines)
    terminal = [
        n
        for n in result.trace.nodes
        if n.measure == "cost_asset_carrying_functional" and n.id.endswith(":FY2027-P12")
    ]
    assert terminal and all(Decimal(n.value) == 0 for n in terminal)
    assert computed == compute(value)
    # Earlier evidence stays reproducible and cannot pretend to support foreign costs.
    with pytest.raises(EngineError, match="no functional amount"):
        compute(replace(value, evidence_revision=54))


def test_missing_cost_spot_rate_is_reported():
    value = source()
    value = replace(value, fx_rates=tuple(r for r in value.fx_rates if r.rate_type != "spot"))
    with pytest.raises(EngineError) as error:
        compute(value)
    assert error.value.code == "FX_RATE_MISSING"


def test_same_currency_costs_keep_existing_outputs():
    value = source()
    value = replace(
        value, entities=tuple(replace(e, functional_currency="USD") for e in value.entities)
    )
    assert compute(value).books == compute(replace(value, evidence_revision=54)).books
