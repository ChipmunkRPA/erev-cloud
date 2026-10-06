"""Codex's closure of F-DIN-SSP-R1 / R2 at bb54f6c (PRODUCTION-F-DIN-SSP-RETEST-bb54f6c): the v2
``ssp_values.apply`` issued ``create_ssp_book_version`` before its entry-consistency loop, so a
refused upload had issued one mutating command (rolled back with the transaction) and the local
"nothing is written" comment overstated the guard. Supervisor ruling: validate before the first
mutating command — a refused upload issues no mutating command at all. The commands are recorded
here through the module's own names; no database."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from erev_api.domain.imports.csv_v2 import ssp_values
from erev_api.domain.imports.csv_v2.framework import CsvRow, Plan
from erev_api.problems import Problem

BOOK_ID = UUID("00000000-0000-0000-0000-00000000b00c")
VERSION_ID = UUID("00000000-0000-0000-0000-0000000000e1")


class _Result:
    def scalar_one_or_none(self) -> UUID:
        return BOOK_ID


class _Session:
    def execute(self, statement: Any) -> _Result:
        del statement
        return _Result()


class _Uow:
    session = _Session()


def _line(basis: str, band: tuple[str, str, str], unit: str | None = None) -> dict[str, Any]:
    return {
        "product_code": "AVM-PLAT-100",
        "currency": "USD",
        "method": "observable",
        "distinctness": "distinct",
        "value_basis": basis,
        "quantity_unit": unit,
        "ranges": {
            "band_dimension": "QUANTITY",
            "band_from": band[0],
            "band_to": band[1],
            "point_value": band[2],
        },
    }


def _plan(lines: list[dict[str, Any]]) -> Plan:
    rows = tuple(
        CsvRow(uuid4(), "ssp_values", number, {}, {}, None) for number in range(2, 2 + len(lines))
    )
    return Plan(
        key="US-LIST",
        rows=rows,
        body={
            "ssp_book_code": "US-LIST",
            "legacy_version_label": "2026-Q3",
            "effective_from_date": "2026-07-01",
            "methodology_label": "Q3 list-price study",
            "lines": lines,
        },
    )


def _record(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    calls: list[tuple[str, Any]] = []

    def create_version(uow: Any, book_id: UUID, *, body: Any) -> UUID:
        del uow
        calls.append(("create_ssp_book_version", book_id))
        return VERSION_ID

    def upsert(uow: Any, version_id: UUID, *, body: Any) -> list[UUID]:
        del uow
        calls.append(("upsert_ssp_entries", [len(e.ranges or []) for e in body.entries]))
        return [uuid4() for _ in body.entries]

    monkeypatch.setattr(ssp_values, "create_ssp_book_version", create_version)
    monkeypatch.setattr(ssp_values, "upsert_ssp_entries", upsert)
    return calls


@pytest.mark.parametrize("amount_first", [True, False])
def test_refused_band_rows_issue_no_mutating_command(
    monkeypatch: pytest.MonkeyPatch, amount_first: bool
) -> None:
    calls = _record(monkeypatch)
    amount = _line("AMOUNT", ("0", "10", "1000.00"))
    other = _line("PER_BOOKED_TERM", ("10", "20", "900.00"))
    plan = _plan([amount, other] if amount_first else [other, amount])
    with pytest.raises(Problem) as raised:
        ssp_values.apply(cast("Any", _Uow()), plan, context=cast("Any", None))
    text = str(getattr(raised.value, "detail", None) or raised.value)
    assert "band rows of one SSP entry" in text
    assert calls == []  # no create_ssp_book_version, no upsert_ssp_entries


def test_consistent_band_rows_issue_create_then_upsert_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _record(monkeypatch)
    plan = _plan([_line("AMOUNT", ("0", "10", "1000.00")), _line("AMOUNT", ("10", "20", "900.00"))])
    applied = ssp_values.apply(cast("Any", _Uow()), plan, context=cast("Any", None))
    assert calls == [("create_ssp_book_version", BOOK_ID), ("upsert_ssp_entries", [2])]
    assert applied.targets == [("ssp_book_version", VERSION_ID)]
    assert len(applied.row_targets) == 2
