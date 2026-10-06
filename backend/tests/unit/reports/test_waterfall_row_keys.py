"""RPT-01 revenue waterfall: rows are grouped by identity (SCREENS_B RPT-01 rev 1.26; D-98 104;
supervisor ruling R-40 (a), 2026-09-30; ENGINE_SPEC CV-21; found by the key audit of ruling R-16).
No database.

The builder groups obligations by their row key. The key was joined from the raw identifiers, so
the obligation ``C`` of contract ``A:B`` and the obligation ``B:C`` of contract ``A`` were ONE row
``obligation:A:B:C`` holding the sum of both — measured in lane FIX-D2: 19,726.02 where two rows of
9,863.01 belong, the contract ``A:B`` not shown at all. Each identifier is now CV-21-encoded by the
engine's one table (``encode_key``) before the join.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pytest
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import revenue_waterfall as waterfall
from erev_api.problems import Problem

SEPTEMBER = "FY2026-P09"
ENTITY = uuid5(NAMESPACE_URL, "erev://tests/entity/AVM-US")
PERIOD = uuid5(NAMESPACE_URL, f"erev://tests/period/{SEPTEMBER}")
# identifiers holding every CV-21 delimiter, the escape character itself, and plain ones
TRICKY = ("A", "B", "A:B", "B:C", "C", "A%3AB", "A/B", "A@B", "A#B", "A%B", "A:B:C", "USD")


def _obligation(
    external_id: str,
    obligation_key: str,
    september: str = "9863.01",
    *,
    product_code: str = "AVM-PLAT-ENT",
    revenue_category: str | None = "SUBSCRIPTION",
    currency: str = "USD",
) -> Any:
    identity = f"{external_id}|{obligation_key}|{product_code}|{currency}"
    return waterfall._Obligation(
        version_row_id=uuid5(NAMESPACE_URL, f"erev://tests/version/{identity}"),
        obligation_id=uuid5(NAMESPACE_URL, f"erev://tests/obligation/{identity}"),
        external_id=external_id,
        obligation_key=obligation_key,
        line_sequence=1,
        product_code=product_code,
        revenue_category=revenue_category,
        customer_name="Pellworth Logistics Inc. (Demo)",
        entity_id=ENTITY,
        entity_code="AVM-US",
        currency=currency,
        awaiting=Decimal(0),
        recognized={SEPTEMBER: Decimal(september)},
    )


def _population(*obligations: Any) -> waterfall.Population:
    return waterfall.Population(
        book_code="ASC606",
        obligations=tuple(obligations),
        buckets=(waterfall._Bucket(SEPTEMBER, "Sep 2026", (SEPTEMBER,)),),
        period_ids=(PERIOD,),
        entity_ids=(ENTITY,),
        restricted=True,  # a restricted run compares no journal: the tie-out reads no table
    )


def _rows(
    monkeypatch: pytest.MonkeyPatch, population: waterfall.Population, dimension: str
) -> dict[str, dict[str, Any]]:
    """The report's rows under ``dimension`` through the real ``build``, keyed by row key."""
    monkeypatch.setattr(waterfall, "population", lambda session, params: population)
    params = ReportParams(
        report_code=waterfall.CODE,
        report_version=1,
        parameters={"row_dimension": dimension},
        entity_ids=(ENTITY,),
        known_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    data = waterfall.build(SimpleNamespace(session=None), params)  # type: ignore[arg-type]
    keyed = {str(row["row_key"]): dict(row) for row in data.rows}
    assert len(keyed) == len(data.rows)  # no two rows share a key
    return keyed


def _september(row: dict[str, Any]) -> str:
    return str(row[f"{waterfall.PERIOD_PREFIX}{SEPTEMBER}"]["amount"])


def test_obligations_whose_joined_identifiers_coincide_are_two_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``(A:B, C)`` and ``(A, B:C)``: two rows of 9,863.01 each, each labelled with its own
    contract and obligation. Fail-first: one row ``obligation:A:B:C`` of 19,726.02."""
    population = _population(_obligation("A:B", "C"), _obligation("A", "B:C"))
    rows = _rows(monkeypatch, population, "OBLIGATION")
    assert {
        key: (row["contract_external_id"], row["obligation_key"], _september(row))
        for key, row in rows.items()
    } == {
        "obligation:A%3AB:C": ("A:B", "C", "9863.01"),
        "obligation:A:B%3AC": ("A", "B:C", "9863.01"),
        "TOTAL:USD": (None, None, "19726.02"),
    }
    by_contract = _rows(monkeypatch, population, "CONTRACT")
    assert {key: _september(row) for key, row in by_contract.items()} == {
        "contract:A%3AB": "9863.01",
        "contract:A": "9863.01",
        "TOTAL:USD": "19726.02",
    }


def test_an_identifier_without_a_delimiter_is_written_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The documented keys of ordinary identifiers do not move (SCREENS_B RPT-01; the test ids
    ``SF-08-row-<row key normalised>`` and every stored run of such ids)."""
    population = _population(
        _obligation("SF-ORD-10001", "O1", "9764.38"),
        _obligation("SF-ORD-10001", "O2", "0.00", product_code="AVM-IMPL-STD"),
        _obligation("Contract 1", "POB #1", "100.00", product_code="Hardware 1"),
    )
    assert set(_rows(monkeypatch, population, "CONTRACT")) == {
        "contract:SF-ORD-10001",
        "contract:Contract 1",
        "TOTAL:USD",
    }
    assert set(_rows(monkeypatch, population, "OBLIGATION")) == {
        "obligation:SF-ORD-10001:O1",
        "obligation:SF-ORD-10001:O2",
        "obligation:Contract 1:POB %231",  # `#` is a CV-21 delimiter: the legacy UAT key encodes
        "TOTAL:USD",
    }
    assert set(_rows(monkeypatch, population, "PRODUCT")) == {
        "product:AVM-PLAT-ENT",
        "product:AVM-IMPL-STD",
        "product:Hardware 1",
        "TOTAL:USD",
    }
    assert set(_rows(monkeypatch, population, "REVENUE_CATEGORY")) == {
        "category:SUBSCRIPTION",
        "TOTAL:USD",
    }


@pytest.mark.parametrize("dimension", ["CONTRACT", "OBLIGATION", "PRODUCT"])
def test_a_row_key_is_injective_in_its_identifiers(dimension: str) -> None:
    """Distinct identities never share a key, whatever delimiters the identifiers hold — also
    beside the ``:<ISO>`` suffix a key holding several currencies is split by."""
    obligations = [
        _obligation(external_id, obligation_key, product_code=external_id)
        for external_id, obligation_key in itertools.product(TRICKY, TRICKY)
    ]
    identity = {
        "CONTRACT": lambda ob: (ob.external_id,),
        "OBLIGATION": lambda ob: (ob.external_id, ob.obligation_key),
        "PRODUCT": lambda ob: (ob.product_code,),
    }[dimension]
    keys: dict[str, tuple[str, ...]] = {}
    for ob in obligations:
        key = waterfall._row_key(ob, dimension)
        assert keys.setdefault(key, identity(ob)) == identity(ob), key
        for suffix in ("USD", "EUR"):  # the split form of this identity
            split = f"{key}:{suffix}"
            assert keys.setdefault(split, (*identity(ob), suffix)) == (*identity(ob), suffix), split
    assert len({identity(ob) for ob in obligations}) * 3 == len(keys)


def test_a_key_split_by_currency_never_replaces_another_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A product sold in two currencies is split ``product:P:USD`` / ``product:P:EUR``; the
    product ``P:USD`` is its own row ``product:P%3AUSD``. Fail-first: the raw key ``product:P:USD``
    of the second product was replaced by the first product's split row — one row was lost."""
    population = _population(
        _obligation("K-1", "O1", "100.00", product_code="P:USD"),
        _obligation("K-2", "O1", "200.00", product_code="P"),
        _obligation("K-3", "O1", "300.00", product_code="P", currency="EUR"),
    )
    rows = _rows(monkeypatch, population, "PRODUCT")
    assert {key: (row["product_code"], _september(row)) for key, row in rows.items()} == {
        "product:P%3AUSD": ("P:USD", "100.00"),
        "product:P:USD": ("P", "200.00"),
        "product:P:EUR": ("P", "300.00"),
        "TOTAL:EUR": (None, "300.00"),
        "TOTAL:USD": (None, "300.00"),
    }


def test_the_cell_drill_resolves_each_row_by_its_own_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``GET /explain/report-runs/{id}/cell`` regroups with the same key: each of the two rows
    explains its own 9,863.01; the former merged key names no row."""
    population = _population(_obligation("A:B", "C"), _obligation("A", "B:C"))
    monkeypatch.setattr(waterfall, "population", lambda session, params: population)
    params = ReportParams(
        report_code=waterfall.CODE,
        report_version=1,
        parameters={"row_dimension": "OBLIGATION"},
        entity_ids=(ENTITY,),
        known_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    column = f"{waterfall.PERIOD_PREFIX}{SEPTEMBER}"
    for row_key in ("obligation:A%3AB:C", "obligation:A:B%3AC"):
        value, _ = waterfall.cell(None, params, row_key, column)  # type: ignore[arg-type]
        assert value == {"amount": "9863.01", "currency": "USD"}, row_key
    with pytest.raises(Problem):
        waterfall.cell(None, params, "obligation:A:B:C", column)  # type: ignore[arg-type]
