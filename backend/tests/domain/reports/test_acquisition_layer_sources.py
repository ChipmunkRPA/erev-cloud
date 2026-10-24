"""Original movement sources reconcile, including signed remeasurement deltas."""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest

from erev_api.domain.reports.acquisition_layer_sources import verify
from erev_api.problems import Problem


def sources():
    rate = SimpleNamespace(
        rate_key="spot",
        version_key="v1",
        base_currency="EUR",
        quote_currency="USD",
        rate=Decimal("1.1"),
    )
    bundle = SimpleNamespace(evidence_revision=46, fx_rates=[rate])
    moves = []
    nodes = {}
    for index, (kind, txn, functional) in enumerate(
        [
            ("CREATED", 10000, 11000),
            ("CONSUMED", 2000, 2200),
            ("REMEASURED", 8000, -100),
        ]
    ):
        key = str(index)
        moves.append(
            {
                "kind": f"LIABILITY_LAYER_{kind}",
                "effective_date": "2025-12-31",
                "amount_txn": txn,
                "amount_functional": functional,
                "node": key,
                "rate_key": "spot",
                "version_key": "v1",
                "rate": "11/10",
            }
        )
        nodes[key] = {"currency": "USD", "value": str(Decimal(functional) / 100)}
    layer = {
        "layer_key": "original",
        "txn_open": 8000,
        "functional_carrying": 8700,
        "movements": moves,
    }
    snapshot = {
        "currency": "EUR",
        "as_of": "2025-12-31",
        "functional": {
            "currency": "USD",
            "minor_unit": 2,
            "amounts": {"contract_liability": 8700},
            "liability_layers": [layer],
        },
    }
    return bundle, snapshot, nodes


def test_original_movements_reconcile_and_reject_changed_sources():
    bundle, snapshot, nodes = sources()
    verify(bundle, snapshot, nodes)
    for field, value in [("rate", "12/10"), ("node", "absent"), ("amount_txn", 1)]:
        changed = deepcopy(snapshot)
        changed["functional"]["liability_layers"][0]["movements"][0][field] = value
        with pytest.raises(Problem):
            verify(bundle, changed, nodes)
    changed = deepcopy(snapshot)
    changed["functional"]["amounts"]["contract_liability"] += 1
    with pytest.raises(Problem):
        verify(bundle, changed, nodes)
