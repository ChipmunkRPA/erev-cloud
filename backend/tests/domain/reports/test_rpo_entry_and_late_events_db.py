"""A contract enters the RPO family on the day it is activated, and revenue a later version
recognises for an earlier period is a late event (item RPT-RPO-ROLLFWD-1; ENGINE_SPEC_B S15-R-08
and S15-R-12 rev 1.161; SCREENS_B RPT-06, RPT-07 and RPT-11 rev 1.70; 04 API-C-10 rev 1.213;
supervisor ruling R-121 (g)). PostgreSQL-bound, through the product's commands and
``POST /report-runs``.

The RPO report, its rollforward, the Home figure and RPT-11 read a contract at a date from the
last version effective on or before it, and a version was dated by the LATEST of its causing
events. A computation takes in every event recorded so far, so a first version is often caused
by the activation and by measurements dated after it. Two worlds of ``support.worlds`` are built
that way, at the frozen clock 2026-09-12 with FY2026-P01 to P09 open:

- K-01 ``SF-ORD-10001`` (``k01_pellworth``): activated on 1 January 2026, 135,000.00; its one
  version also holds the progress of 31 January and of 27 February and is dated 27 February.
  Measured before the item: no RPO at 31 January; February's rollforward opened at 0.00, showed
  135,000.00 of new contracts and −16,569.86 unexplained — January's revenue.
- K-04 ``SF-ORD-UK-2001`` (``k04_saltmarsh``, contracted by AVM-UK): activated on 1 April 2026,
  68,000.00 GBP; its one version is dated 31 May. No RPO at 30 April; May −9,647.75 unexplained.

A third world holds a late event: K-01 through 1 January, January locked, the O2 progress of 31
January imported afterwards (``k01_late_progress``). Its revenue, 6,480.00, is posted in February
with January as its origin; the version that knows it is effective in February. February's
rollforward showed −6,480.00 unexplained.

The oracle stands outside the builders: the ledger — the revenue posted in the periods up to a
date, and the origin period of each line — and the contract's allocation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import period, subledger_line
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support import worlds
from support.db import TestDatabase
from support.reference import assign, get
from support.worlds import AVM_UK, AVM_US, K01, K04, ReportWorld, report_run
from tests.domain.contracts.test_to_date_reads import posted_revenue

HOME: Final = "/api/v1/dashboard/home"
ZERO: Final = Decimal(0)
LINES: Final = (
    "OPENING",
    "NEW_CONTRACTS",
    "MODIFICATIONS",
    "VC_ESTIMATE_CHANGES",
    "LATE_EVENTS",
    "REVENUE",
    "CANCELLATIONS",
    "FX",
    "UNEXPLAINED",
    "CLOSING",
)
BALANCED: Final = {"TO_ROLLFORWARD_BALANCES": "PASS", "TO_RPO_ROLLFORWARD_EQ_RPO": "PASS"}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def amount(value: Any) -> Decimal:
    return ZERO if value is None else Decimal(value["amount"])


def keyed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(row["row_key"]): row for row in rows}


def ties(run: Mapping[str, Any]) -> dict[str, str]:
    return {str(item["code"]): str(item["result"]) for item in run["tie_out_results"]}


def month_end(period_key: str) -> date:
    """The end of ``FY2026-P<month>`` in the worlds' calendar: months, the year from January."""
    month = int(period_key[8:10])
    return date(2026 + month // 12, month % 12 + 1, 1) - timedelta(days=1)


def rollforward(world: ReportWorld, entity: str, period_key: str) -> tuple[dict[str, Decimal], Any]:
    """The section 1 lines of RPT-07 for one period, by line code, and the run."""
    run, rows = report_run(
        world,
        "rpo_rollforward",
        {
            "entity_codes": [entity],
            "book": "ASC606",
            "from_period_key": period_key,
            "to_period_key": period_key,
        },
    )
    lines = {key: amount(row["rpo"]) for key, row in keyed(rows).items() if row.get("section") == 1}
    return lines, run


def stated(**movements: Decimal) -> dict[str, Decimal]:
    """Every line of S15-R-12 by code: the ones named, and zero for the rest."""
    return {code: movements.get(code, ZERO) for code in LINES}


@pytest.mark.slow
@pytest.mark.parametrize(
    ("contract", "entity", "entered", "following", "allocation"),
    [
        (K01, AVM_US, "FY2026-P01", "FY2026-P02", Decimal("135000.00")),
        (K04, AVM_UK, "FY2026-P04", "FY2026-P05", Decimal("68000.00")),
    ],
)
def test_a_contract_is_in_the_rpo_from_the_day_it_is_activated(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    contract: str,
    entity: str,
    entered: str,
    following: str,
    allocation: Decimal,
) -> None:
    """At the end of the period a contract was activated in — a date before the date of its one
    version — the RPO report, the contract read, the Home figure and RPT-11 state its remainder
    of that date: the allocation less the revenue the ledger holds through the period. The
    rollforward of that period shows the allocation as new and the period's revenue; the
    following period opens at that closing and nothing is unexplained in either.

    Fail-first, through the product: no RPO, no RPT-11 row and a Home figure of 0.00 at that
    date; the contract read stated the remainder less the obligation satisfied later; the
    following period's rollforward showed the whole allocation as new and the first period's
    revenue as unexplained, ``TO_ROLLFORWARD_BALANCES`` FAIL."""
    if contract == K04:
        k04 = worlds.k04_saltmarsh(app, keyring, clock, files)
        world, contract_id, currency = k04.report, str(k04.contract_id), "GBP"
    else:
        world = worlds.k01_pellworth(app, keyring, clock, files)
        contract_id, currency = str(world.contracts[K01].contract["id"]), "USD"
    first, second = month_end(entered), month_end(following)
    to_first = posted_revenue(world.place, contract_id, first)
    in_second = posted_revenue(world.place, contract_id, second) - to_first
    assert to_first > 0 and in_second > 0  # the ledger holds revenue of both periods
    remainder = allocation - to_first
    base = {"entity_codes": [entity], "book": "ASC606"}

    run, rows = report_run(world, "rpo", {**base, "period_key": entered})
    assert run["control_totals"]["total"] == {currency: f"{remainder:.2f}"}
    assert amount(keyed(rows)[f"contract:{contract}"]["total"]) == remainder
    assert ties(run) == {"TO_RPO_ROLLFORWARD_EQ_RPO": "PASS"}

    shown = get(app, f"/api/v1/contracts/{contract_id}", world.maya, {"as_of": first.isoformat()})
    assert shown.status_code == 200, shown.text
    kpis = shown.json()["kpis"]
    assert amount(kpis["rpo"]) == remainder
    assert amount(kpis["scheduled"]) + amount(kpis["awaiting_trigger"]) == remainder

    home = get(app, HOME, world.maya, {"entity": entity, "period": entered, "book": "ASC606"})
    assert home.status_code == 200, home.text
    assert amount(home.json()["rpo"]["total"]) == remainder

    _, listed = report_run(world, "latest_contract_status", {**base, "as_of": first.isoformat()})
    assert sorted(row["obligation_key"] for row in listed) == ["O1", "O2"]
    assert sum((amount(row["revenue_cum"]) for row in listed), ZERO) == to_first
    assert sum((amount(row["remaining_allocation"]) for row in listed), ZERO) == remainder

    lines, run = rollforward(world, entity, entered)
    assert lines == stated(NEW_CONTRACTS=allocation, REVENUE=-to_first, CLOSING=remainder)
    assert ties(run) == BALANCED
    lines, run = rollforward(world, entity, following)
    assert lines == stated(OPENING=remainder, REVENUE=-in_second, CLOSING=remainder - in_second)
    assert ties(run) == BALANCED


@pytest.mark.slow
def test_every_period_of_k01_rolls_forward_without_a_difference(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The identity period by period, January to September 2026: each period opens at the
    closing of the one before, its revenue line is the revenue the ledger holds for it, the
    allocation is new in January alone, and no other line holds an amount — nothing is a late
    event and nothing is unexplained.

    Fail-first: January had no line at all, and February showed the allocation as new."""
    world = worlds.k01_pellworth(app, keyring, clock, files)
    contract_id = str(world.contracts[K01].contract["id"])
    allocation = Decimal("135000.00")
    closing, posted = ZERO, ZERO
    for month in range(1, 10):
        key = f"FY2026-P{month:02d}"
        to_date = posted_revenue(world.place, contract_id, month_end(key))
        lines, run = rollforward(world, AVM_US, key)
        assert lines == stated(
            OPENING=closing,
            NEW_CONTRACTS=allocation if month == 1 else ZERO,
            REVENUE=-(to_date - posted),
            CLOSING=allocation - to_date,
        ), key
        assert ties(run) == BALANCED, key
        closing, posted = lines["CLOSING"], to_date
    assert posted > 0 and closing == allocation - posted


def _february_by_origin(world: ReportWorld, contract_id: str) -> dict[str | None, Decimal]:
    """The ledger: the contract's ``REVENUE`` posted in February 2026 by origin period key (None:
    revenue of February itself), credits positive."""
    origin = period.alias("origin_period")
    rows = world.place.rows(
        select(
            origin.c.period_key.label("origin"), func.sum(subledger_line.c.amount_txn).label("sum")
        )
        .select_from(
            subledger_line.join(period, period.c.id == subledger_line.c.period_id).outerjoin(
                origin, origin.c.id == subledger_line.c.origin_period_id
            )
        )
        .where(
            subledger_line.c.contract_id == UUID(contract_id),
            subledger_line.c.book_code == "ASC606",
            subledger_line.c.account_role == "REVENUE",
            period.c.period_key == "FY2026-P02",
        )
        .group_by(origin.c.period_key)
    )
    return {row["origin"]: -Decimal(row["sum"]) for row in rows}


@pytest.mark.slow
def test_revenue_posted_with_an_earlier_origin_is_the_late_events_line(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """S15-R-12 "late events" (SCREENS_B RPT-07 rev 1.70: the row ``LATE_EVENTS``). January is
    locked with K-01's RPO at 124,910.14; the O2 progress of 31 January arrives afterwards and its
    revenue is posted in February with January as its origin. February's rollforward opens at the
    locked figure, states that revenue — the ledger's lines of February with an earlier origin —
    on the late-events line and February's own revenue on the revenue line, and closes without a
    difference. January's RPO stays the figure it was locked at.

    Fail-first: no line carried the 6,480.00; ``UNEXPLAINED`` −6,480.00 and
    ``TO_ROLLFORWARD_BALANCES`` FAIL."""
    world = worlds.k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 1))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: journal runs and imports are hers
    world = worlds.on_record_clock(world, clock)
    _, world = worlds.period_locked(world, clock, entity_code=AVM_US, period_key="FY2026-P01")
    world, _, noted = worlds.k01_late_progress(world, clock)
    assert noted["computation"]["status"] == "SUCCEEDED", noted["computation"]
    contract_id = str(world.contracts[K01].contract["id"])
    by_origin = _february_by_origin(world, contract_id)
    own, late = by_origin[None], by_origin["FY2026-P01"]
    assert (own, late) == (Decimal("9113.43"), Decimal("6480.00"))  # 16,200.00 × 40% arrives late

    locked_at = Decimal("124910.14")
    run, _ = report_run(
        world, "rpo", {"entity_codes": [AVM_US], "book": "ASC606", "period_key": "FY2026-P01"}
    )
    assert run["control_totals"]["total"] == {"USD": f"{locked_at:.2f}"}

    lines, run = rollforward(world, AVM_US, "FY2026-P02")
    assert lines == stated(
        OPENING=locked_at, LATE_EVENTS=-late, REVENUE=-own, CLOSING=locked_at - late - own
    )
    assert ties(run) == BALANCED
