"""The contract balance rollforward by kind, through the product (supervisor ruling R-72;
ENGINE_SPEC_B §15.2.2 S15-R-03, S15-R-03a, S15-R-07; SCREENS_B §5.6.1 RPT-03 "kind → line",
RPT-04; 03 REQ-RPT-006, REQ-RPT-007; POLICIES POL-004, POL-126, JET-01b, JET-03, JET-13).

Item RPT-ROLLFWD-KINDS-1, parts D1 and D3. Under ``billing.posting = ERP`` — the registry default
and the mode of every world here — an invoice is ingested and never posted, so the role holds no
line of it. The report walked the posted lines alone: every period that holds an invoice showed
the billing as ``OTHER`` and failed ``TO_ROLLFORWARD_BALANCES``; every credit of the role was
labelled ``BILLINGS`` (a deposit transfer); and the relief another entity's performance makes of
the liability was a reclassification that RPT-04 left out. Each test names what it measured
before.

Worlds (``support.worlds``), all through the product's commands at the frozen clock
2026-09-12T12:00:00Z: ``k01_pellworth`` (WLD-K-01), ``k02_marrowby_commission`` with
``k09_orrin_vale`` (WLD-K-02, WLD-K-09), ``k04_saltmarsh`` (WLD-K-04: AVM-UK contracts, AVM-US
performs O1) and ``k09_deposit_transfer`` (WLD-K-09 as an arrangement that is not a contract at
first). Report runs play the worker as ``test_framework.py`` does.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Final

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import period_lock
from erev_api.domain.reports import tie_outs
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support import worlds
from support.db import TestDatabase
from support.reference import assign
from support.worlds import (
    AVM_UK,
    AVM_US,
    JANUARY_2026,
    K01,
    K02,
    K04,
    K09,
    SEPTEMBER_2026,
    report_run,
)

ROLLFORWARD: Final = "contract_balance_rollforward"
OPENING_LIABILITY: Final = "revenue_from_opening_liability"
LIABILITY: Final = "contract_liability"
ASSET: Final = "contract_asset"
UNBILLED: Final = "unbilled_receivable"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def amount(cell: Any) -> str:
    """The amount of a money cell: a live run's ``{amount, currency}`` or a frozen row's text."""
    return str(cell["amount"]) if isinstance(cell, Mapping) else str(cell)


def section_1(rows: Sequence[Mapping[str, Any]], balance: str = LIABILITY) -> dict[str, str]:
    """The non-zero cells of one balance in section 1 "Rollforward", by line code."""
    return {
        str(row["line_code"]): amount(row[balance])
        for row in rows
        if row["line_code"] and amount(row[balance]) != "0.00"
    }


def by_contract(rows: Sequence[Mapping[str, Any]], external_id: str) -> dict[str, str]:
    """The non-zero movement cells of the section 2 row of one contract."""
    (row,) = [row for row in rows if row.get("contract_external_id") == external_id]
    columns = (
        "opening",
        "billings",
        "revenue_from_opening",
        "revenue_from_period_billings",
        "reclassifications",
        "fx_remeasurement",
        "business_combinations",
        "other",
        "closing",
    )
    return {name: amount(row[name]) for name in columns if amount(row[name]) != "0.00"}


def ranged(first: str, last: str | None = None, *, entity: str = AVM_US) -> dict[str, Any]:
    return {
        "entity_codes": [entity],
        "book": "ASC606",
        "from_period_key": first,
        "to_period_key": last or first,
    }


def tie(run: Mapping[str, Any], code: str) -> Mapping[str, Any]:
    (found,) = [item for item in run["tie_out_results"] if item["code"] == code]
    return found


def balanced(run: Mapping[str, Any], closing: str, currency: str = "USD") -> None:
    """``TO_ROLLFORWARD_BALANCES`` passes at ``closing``: opening plus the lines equals closing over
    the three balances, and no ``OTHER`` cell holds an amount (S15-R-07)."""
    money = {"amount": closing, "currency": currency}
    assert tie(run, tie_outs.TO_ROLLFORWARD_BALANCES) == {
        "code": "TO_ROLLFORWARD_BALANCES",
        "result": "PASS",
        "expected": [money],
        "actual": [money],
        "difference": [{"amount": "0.00", "currency": currency}],
    }


# --- D1: the billing that posts no line ----------------------------------------------------------


@pytest.mark.slow
def test_rollforward_ties_in_the_periods_that_hold_an_invoice_k01(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """S15-R-03a: the billing of a period enters the path from the billing documents, against the
    engine's ``billed_unconditional_cum``. WLD-K-01: INV-US-1001 120,000.00 (01 Jan 2026) and
    INV-US-1044 15,000.00 (27 Feb 2026). Before: January ``OTHER`` 103,430.14 on the liability and
    (16,569.86) on the contract asset, February ``OTHER`` 15,000.00, the year to date 29,944.11
    and (105,055.89) — ``TO_ROLLFORWARD_BALANCES`` FAIL in each."""
    world = worlds.k01_pellworth(app, keyring, clock, files)
    january, rows = report_run(world, ROLLFORWARD, ranged(JANUARY_2026))
    # revenue of January: O1 10,089.86 and O2 at 40% 6,480.00, relieving the month's invoice
    assert section_1(rows) == {
        "BILLINGS": "120000.00",
        "REVENUE_FROM_PERIOD_BILLINGS": "-16569.86",
        "CLOSING": "103430.14",
    }
    assert section_1(rows, ASSET) == section_1(rows, UNBILLED) == {}
    balanced(january, "103430.14")
    february, rows = report_run(world, ROLLFORWARD, ranged("FY2026-P02"))
    # first in first out (POL-126): February's revenue relieves the opening liability, and the
    # invoice of 27 Feb stays whole in the closing balance
    assert section_1(rows) == {
        "OPENING": "103430.14",
        "BILLINGS": "15000.00",
        "REVENUE_FROM_OPENING": "-18833.43",
        "CLOSING": "99596.71",
    }
    assert section_1(rows, ASSET) == {}
    balanced(february, "99596.71")
    to_date, rows = report_run(world, ROLLFORWARD, ranged(JANUARY_2026, SEPTEMBER_2026))
    assert section_1(rows) == {
        "BILLINGS": "135000.00",
        "REVENUE_FROM_PERIOD_BILLINGS": "-105055.89",  # WLD-X-03 cumulative revenue
        "CLOSING": "29944.11",
    }
    assert section_1(rows, ASSET) == {}
    balanced(to_date, "29944.11")
    assert by_contract(rows, K01) == {
        "billings": "135000.00",
        "revenue_from_period_billings": "-105055.89",
        "closing": "29944.11",
    }


@pytest.mark.slow
def test_an_invoice_and_the_revenue_of_its_period_k09(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """WLD-K-09 ``SF-ORD-10417``: INV-US-3101 36,000.00 on 01 Sep 2026 and the revenue of
    September, 2,956.20 = 108,000.00 × 30 / 1,096, beside WLD-K-02, which holds no invoice in
    September. The invoice enters at its date, before the revenue line of the period end, so the
    revenue relieves it. Before: ``OTHER`` 33,043.80 on the liability and (2,956.20) on the
    contract asset, the revenue shown as revenue in excess of billing; difference (30,087.60)."""
    world = worlds.k09_orrin_vale(worlds.k02_marrowby_commission(app, keyring, clock, files))
    run, rows = report_run(world, ROLLFORWARD, ranged(SEPTEMBER_2026))
    assert section_1(rows) == {
        "OPENING": "40109.59",  # K-02 at 31 Aug 2026
        "BILLINGS": "36000.00",
        "REVENUE_FROM_OPENING": "-9863.01",  # K-02
        "REVENUE_FROM_PERIOD_BILLINGS": "-2956.20",  # K-09
        "CLOSING": "63290.38",
    }
    assert section_1(rows, ASSET) == section_1(rows, UNBILLED) == {}
    balanced(run, "63290.38")
    assert by_contract(rows, K09) == {
        "billings": "36000.00",
        "revenue_from_period_billings": "-2956.20",
        "closing": "33043.80",
    }
    assert by_contract(rows, K02) == {
        "opening": "40109.59",
        "revenue_from_opening": "-9863.01",
        "closing": "30246.58",
    }


@pytest.mark.slow
def test_a_lock_freezes_the_billing_of_its_period(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The dataset a lock freezes is the same rollforward (S15-R-18): WLD-K-01 with INV-US-1001
    only, January 2026 locked through the product. The ``CONTRACT_BALANCE_ROLLFORWARD`` dataset of
    the lock holds the invoice under ``BILLINGS`` and the month's revenue, O1 10,089.86, against
    it; a run "as locked" serves those rows."""
    world = worlds.k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 1))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: the journal run is hers to approve
    world = worlds.on_record_clock(world, clock)
    live, live_rows = report_run(world, ROLLFORWARD, ranged(JANUARY_2026))
    expected = {
        "BILLINGS": "120000.00",
        "REVENUE_FROM_PERIOD_BILLINGS": "-10089.86",
        "CLOSING": "109910.14",
    }
    assert section_1(live_rows) == expected
    balanced(live, "109910.14")
    _, world = worlds.period_locked(world, clock, entity_code=AVM_US, period_key=JANUARY_2026)
    lock_id = world.place.scalar(select(period_lock.c.id).where(period_lock.c.kind == "LOCK"))
    frozen, frozen_rows = report_run(
        world, ROLLFORWARD, {**ranged(JANUARY_2026), "period_lock_id": str(lock_id)}
    )
    assert frozen["period_lock_id"] == str(lock_id)
    assert section_1(frozen_rows) == expected
    assert section_1(frozen_rows, ASSET) == {}
    assert by_contract(frozen_rows, K01) == {
        "billings": "120000.00",
        "revenue_from_period_billings": "-10089.86",
        "closing": "109910.14",
    }


# --- D3: the line of each kind -------------------------------------------------------------------


@pytest.mark.slow
def test_intercompany_relief_is_revenue_in_the_contracting_entity_k04(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """WLD-K-04 ``SF-ORD-UK-2001`` (GBP): AVM-UK contracts and bills INV-UK-0501 68,000.00 on
    01 Apr 2026; AVM-US performs O1, so its revenue relieves AVM-UK's liability through the
    intercompany account (JET-13, entry kind ``INTERCOMPANY``). That relief is shown under the
    revenue lines, with AVM-UK's own revenue of O2 (R-72 (c)), and RPT-04 counts it (R-72 (d)).
    Before: April ``OTHER`` 58,352.25 and (9,647.75); May and June showed the intercompany relief
    — 4,950.29 and 4,790.61 — under ``RECLASSIFICATIONS``, and RPT-04 stated 4,857.15 for May and
    no row for June."""
    world = worlds.k04_saltmarsh(app, keyring, clock, files).report
    april, rows = report_run(world, ROLLFORWARD, ranged("FY2026-P04", entity=AVM_UK))
    # April: O2 at 50% 4,857.14 (AVM-UK) and O1 4,790.61 (performed by AVM-US)
    assert section_1(rows) == {
        "BILLINGS": "68000.00",
        "REVENUE_FROM_PERIOD_BILLINGS": "-9647.75",
        "CLOSING": "58352.25",
    }
    assert section_1(rows, ASSET) == section_1(rows, UNBILLED) == {}
    balanced(april, "58352.25", "GBP")
    may, rows = report_run(world, ROLLFORWARD, ranged("FY2026-P05", entity=AVM_UK))
    # May: O2 to 100% 4,857.15 and O1 4,950.29, both from the opening liability
    assert section_1(rows) == {
        "OPENING": "58352.25",
        "REVENUE_FROM_OPENING": "-9807.44",
        "CLOSING": "48544.81",
    }
    balanced(may, "48544.81", "GBP")
    june, rows = report_run(world, ROLLFORWARD, ranged("FY2026-P06", entity=AVM_UK))
    # June: nothing but the relief by AVM-US's performance of O1
    assert section_1(rows) == {
        "OPENING": "48544.81",
        "REVENUE_FROM_OPENING": "-4790.61",
        "CLOSING": "43754.20",
    }
    assert by_contract(rows, K04) == {
        "opening": "48544.81",
        "revenue_from_opening": "-4790.61",
        "closing": "43754.20",
    }
    balanced(june, "43754.20", "GBP")

    def opening_liability(period_key: str) -> dict[str, tuple[str, str, str]]:
        _, found = report_run(world, OPENING_LIABILITY, ranged(period_key, entity=AVM_UK))
        return {
            str(row["row_key"]): (
                amount(row["opening_contract_liability"]),
                amount(row["revenue_recognized"]),
                amount(row["revenue_from_opening"]),
            )
            for row in found
        }

    row_key = f"contract:{K04}:{AVM_UK}"
    assert opening_liability("FY2026-P05") == {
        "summary:GBP": ("58352.25", "9807.44", "9807.44"),
        row_key: ("58352.25", "9807.44", "9807.44"),
    }
    assert opening_liability("FY2026-P06") == {
        "summary:GBP": ("48544.81", "4790.61", "4790.61"),
        row_key: ("48544.81", "4790.61", "4790.61"),
    }


@pytest.mark.slow
def test_a_deposit_transfer_is_a_reclassification_not_a_billing(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """``worlds.k09_deposit_transfer``: no invoice; 36,000.00 received while the arrangement was
    not a contract is transferred from the deposit liability to the contract liability when the
    criteria are met (JET-01b, entry kind ``DEPOSIT``), and the revenue of September with its
    catch-up, 2,956.20, relieves it. The transfer is a movement of the role that is not billing:
    ``RECLASSIFICATIONS`` (R-72 (c)). Before: the transfer was shown as "Billings" 36,000.00."""
    world = worlds.k09_deposit_transfer(app, keyring, clock, files)
    run, rows = report_run(world, ROLLFORWARD, ranged(SEPTEMBER_2026))
    assert section_1(rows) == {
        "REVENUE_FROM_PERIOD_BILLINGS": "-2956.20",
        "RECLASSIFICATIONS": "36000.00",
        "CLOSING": "33043.80",
    }
    assert section_1(rows, ASSET) == section_1(rows, UNBILLED) == {}
    balanced(run, "33043.80")
    assert by_contract(rows, K09) == {
        "revenue_from_period_billings": "-2956.20",
        "reclassifications": "36000.00",
        "closing": "33043.80",
    }
