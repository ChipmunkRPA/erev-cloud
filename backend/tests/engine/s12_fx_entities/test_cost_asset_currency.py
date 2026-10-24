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
from erev_engine.bundle import FxRateInput, MappingRuleInput
from erev_engine.canonical import sha256_hex
from erev_engine.errors import EngineError
from erev_engine.trace import reevaluate


def source(path="cost/COST-S8-CONTRACT-COSTS-EX1.yaml"):
    key = load(ANSWER_KEY_ROOT / path)
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
    value = replace(source(), evidence_revision=57)
    value = replace(
        value, entities=tuple(replace(e, functional_currency="USD") for e in value.entities)
    )
    assert compute(value).books == compute(replace(value, evidence_revision=54)).books


@pytest.mark.parametrize("spot, expected", [(".9", "7560"), (".9000005", "7560.01")])
def test_termination_accelerates_remaining_historical_cost(spot, expected):
    value = replace(
        source("mod/MOD-FS-09-CANCELLATION-REFUND-COMMISSION.yaml"), evidence_revision=56
    )
    value = replace(
        value,
        fx_rates=tuple(
            replace(rate, rate=Decimal(spot)) if rate.rate_type == "spot" else rate
            for rate in value.fx_rates
        ),
    )
    mapping = value.books[0].account_mapping
    rules = tuple(
        sorted(
            (
                *mapping.rules,
                MappingRuleInput(
                    "FX_GAIN_LOSS",
                    None,
                    None,
                    None,
                    None,
                    None,
                    "7200",
                    {},
                    0,
                    0,
                ),
            ),
            key=lambda r: (
                r.account_role,
                r.clearing_purpose or "",
                -r.specificity,
                -r.priority,
                r.account_code,
            ),
        )
    )
    value = replace(
        value,
        books=(
            replace(
                value.books[0],
                account_mapping=replace(mapping, rules=rules, content_sha256=sha256_hex(rules)),
            ),
        ),
    )
    result = compute(value).books[0]
    accelerated = [
        n
        for n in result.trace.nodes
        if n.measure == "cost_accelerated_cum_functional" and n.id.endswith(":FY2027-P03")
    ]
    assert len(accelerated) == 1
    assert Decimal(accelerated[0].value) == Decimal(expected)
    held = [
        n
        for n in result.trace.nodes
        if n.measure == "cost_asset_carrying_functional" and n.id.endswith(":FY2027-P03")
    ]
    assert held and all(Decimal(n.value) == 0 for n in held)
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
    lines = [
        line
        for entry in result.posting_intents
        if entry.posting_period_key <= "FY2027-P03"
        for line in entry.lines
        if line.account_role == "COST_TO_OBTAIN_ASSET"
    ]
    assert lines
    assert sum((1 if line.side == "D" else -1) * line.amount_functional for line in lines) == 0
    assert all(dict(result.line_rates)[line.line_key] == (("cost-spot", "1"),) for line in lines)
    with pytest.raises(EngineError, match="no functional amount"):
        compute(replace(value, evidence_revision=55))


def test_cost_before_activation_uses_capitalization_date_rate():
    value = replace(source(), evidence_revision=57)
    activation = date(2026, 3, 1)
    value = replace(
        value,
        events=tuple(
            sorted(
                (
                    replace(e, effective_date=activation)
                    if e.event_type == "CONTRACT_ACTIVATED"
                    else e
                    for e in value.events
                ),
                key=lambda e: (e.effective_date, e.record_seq, e.event_key),
            )
        ),
        fx_rates=tuple(
            sorted(
                (
                    *value.fx_rates,
                    FxRateInput(
                        "activation-spot",
                        "1",
                        "spot",
                        "USD",
                        "EUR",
                        activation,
                        None,
                        Decimal(".8"),
                    ),
                ),
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
    result = compute(value).books[0]
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
    capital = [n for n in result.trace.nodes if n.measure == "cost_capitalised_functional"]
    assert capital and all(Decimal(n.value) == Decimal("8000") for n in capital)
    assert all(n.params["capitalization_date"] == "2026-03-01" for n in capital)
    assert not [n for n in capital if n.id.endswith((":FY2026-P01", ":FY2026-P02"))]
    held = [
        n
        for n in result.trace.nodes
        if n.measure == "cost_asset_carrying_functional" and n.id.endswith(":FY2026-P12")
    ]
    assert held and all(Decimal(n.value) == Decimal("4000") for n in held)
    lines = [
        line
        for entry in result.posting_intents
        if entry.posting_period_key <= "FY2026-P12"
        for line in entry.lines
        if line.account_role == "COST_TO_OBTAIN_ASSET"
    ]
    assert sum((1 if line.side == "D" else -1) * line.amount_functional for line in lines) == 400000
    assert all(
        dict(result.line_rates)[line.line_key] == (("activation-spot", "1"),) for line in lines
    )
    with pytest.raises(EngineError, match="no functional amount"):
        compute(replace(value, evidence_revision=56))
