"""Loss persistence retains all contributors and rejects invalid output before any insert."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from erev_api.domain.contracts import loss_provisions as writer
from erev_api.enums import PrincipalKind


def case(monkeypatch: pytest.MonkeyPatch):
    contract, entity, period, version, first, second = (uuid4() for _ in range(6))
    written = {}
    uow = SimpleNamespace(
        principal=SimpleNamespace(tenant_id=uuid4(), id=None, kind=PrincipalKind.SYSTEM),
        now=datetime(2026, 1, 31, tzinfo=UTC),
        session=SimpleNamespace(
            execute=lambda statement, rows: written.setdefault(statement.table.name, []).extend(
                rows
            )
        ),
    )
    monkeypatch.setattr(
        writer, "_eac_ids", lambda *args: {"a": (first, contract), "b": (second, contract)}
    )
    bundle = SimpleNamespace(currencies={"KWD": SimpleNamespace(minor_unit=3)})
    found = SimpleNamespace(
        contracts={"owner": {"id": contract}},
        entities={"E": {"id": entity}},
        periods={("E", "P1"): (period, date(2026, 1, 31))},
        obligations={},
    )
    values = {
        "contract_key": "owner",
        "entity": "E",
        "unit": "CONTRACT",
        "unit_key": "owner",
        "obligation_key": None,
        "as_of": date(2026, 1, 31),
        "eac_version_keys": ("a", "b"),
        "currency": "KWD",
        "measurement_basis": "ASC_605_35",
        "in_scope": True,
        **dict.fromkeys(writer.AMOUNTS, 1050),
    }
    values["expected_margin"] = -1050
    output = SimpleNamespace(
        subject_key="owner",
        period_key="P1",
        columns=values,
        trace_nodes={"provision_balance": "trace"},
    )
    book = SimpleNamespace(book_code="ASC606", loss_provision_versions=[output])
    return uow, bundle, found, book, version, values, written, {first, second}


def test_complete_multi_eac_lineage_and_currency_units(monkeypatch: pytest.MonkeyPatch) -> None:
    uow, bundle, found, book, version, _, written, expected = case(monkeypatch)
    facts = writer.persist(uow, bundle, found, book, version)
    (row,) = written["loss_provision_version"]
    assert row["expected_margin"] == Decimal("-1.050")
    assert row["provision_balance"] == Decimal("1.050")
    assert row["eac_estimate_version_id"] is None
    assert row["trace_nodes"] == {"provision_balance": "trace"}
    links = written["loss_provision_eac"]
    assert {link["estimate_version_id"] for link in links} == expected
    assert {link["loss_provision_version_id"] for link in links} == {row["id"]}
    assert facts["loss_provision_version"] == [row["id"]]
    assert set(facts["loss_provision_eac"]) == {link["id"] for link in links}


@pytest.mark.parametrize(
    "changed",
    [
        {"contract_key": "missing"},
        {"eac_version_keys": ("unavailable",)},
        {"as_of": date(2026, 2, 28)},
        {"unit": "POB", "obligation_key": "missing"},
        {"expected_consideration": 10.5},
        {"expected_consideration": True},
        {"in_scope": 1},
        {"unit_key": "wrong-owner"},
    ],
)
def test_invalid_later_result_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, changed: dict
) -> None:
    uow, bundle, found, book, version, values, written, _ = case(monkeypatch)
    bad = SimpleNamespace(**vars(book.loss_provision_versions[0]))
    bad.columns = {**values, **changed}
    book.loss_provision_versions.append(bad)
    with pytest.raises(ValueError):
        writer.persist(uow, bundle, found, book, version)
    assert written == {}


def test_eac_of_another_group_member_is_not_attributed_to_this_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow, bundle, found, book, version, _, written, _ = case(monkeypatch)
    owner = found.contracts["owner"]["id"]
    monkeypatch.setattr(
        writer, "_eac_ids", lambda *args: {"a": (uuid4(), owner), "b": (uuid4(), uuid4())}
    )
    with pytest.raises(ValueError, match="another contract"):
        writer.persist(uow, bundle, found, book, version)
    assert written == {}
