"""FX movement persistence preserves units and refuses unresolved lineage before writing."""

from datetime import UTC, date, datetime
from fractions import Fraction
from types import SimpleNamespace
from uuid import uuid4

import pytest
from erev_api.domain.contracts import fx_layers
from erev_api.enums import PrincipalKind


def case(monkeypatch: pytest.MonkeyPatch):
    contract, version, entity, rate_id, rate_version, event_id = (uuid4() for _ in range(6))
    written = []
    uow = SimpleNamespace(
        principal=SimpleNamespace(tenant_id=uuid4(), id=uuid4(), kind=PrincipalKind.SYSTEM),
        now=datetime(2026, 1, 1, tzinfo=UTC),
        session=SimpleNamespace(execute=lambda statement, rows: written.extend(rows)),
    )
    monkeypatch.setattr(
        fx_layers.bundles, "fx_rate_ids", lambda *args: {"rate": (rate_id, rate_version, None)}
    )
    bundle = SimpleNamespace(
        currencies={"JPY": SimpleNamespace(minor_unit=0), "KWD": SimpleNamespace(minor_unit=3)},
        fx_rates=[SimpleNamespace(rate_key="rate", version_key="version")],
        events=[SimpleNamespace(event_key="event", contract_key="owner", stream_version=1)],
    )
    found = SimpleNamespace(
        contracts={"owner": {"id": contract}},
        entities={"E": {"id": entity}},
        events={("owner", 1): event_id},
    )
    values = dict(
        contract_key="owner",
        entity="E",
        layer_key="CONTRACT_ASSET:origin",
        movement_kind="ASSET_LAYER_CREATED",
        balance_role="CONTRACT_ASSET",
        effective_date=date(2026, 1, 1),
        txn_currency="JPY",
        functional_currency="KWD",
        amount_txn=125,
        amount_functional=100100,
        rate_key="rate",
        version_key="version",
        rate=Fraction(1001, 1250),
        source_key="event",
    )
    movement = SimpleNamespace(columns=values, trace_nodes={"amount_functional": "trace"})
    book = SimpleNamespace(book_code="ASC606", fx_layer_movements=[movement])
    return uow, bundle, found, book, version, values, written, rate_id, event_id


def test_different_currency_minor_units_and_lineage(monkeypatch: pytest.MonkeyPatch) -> None:
    from decimal import Decimal

    uow, bundle, found, book, version, _, written, rate_id, event_id = case(monkeypatch)
    ids = fx_layers.persist(uow, bundle, found, book, version)
    (row,) = written
    assert ids == [row["id"]]
    assert row["amount_txn"] == Decimal("125")
    assert row["amount_functional"] == Decimal("100.100")
    assert row["rate"] == Decimal("0.8008")
    assert row["fx_rate_id"] == rate_id and row["source_event_id"] == event_id
    assert row["contract_id"] == found.contracts["owner"]["id"]


@pytest.mark.parametrize(
    "changed",
    [
        {"contract_key": "missing"},
        {"rate_key": None},
        {"rate_key": "missing"},
        {"version_key": "wrong-version"},
        {"rate": 0.8008},
        {"amount_txn": True},
    ],
)
def test_unresolved_owner_or_rate_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, changed: dict
) -> None:
    uow, bundle, found, book, version, values, written, _, _ = case(monkeypatch)
    values.update(changed)
    with pytest.raises(ValueError):
        fx_layers.persist(uow, bundle, found, book, version)
    assert written == []
