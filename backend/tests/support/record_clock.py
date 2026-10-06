"""The record-time clock for worlds that read on the historical basis (F-RPS-CUTOFF-R1; dev-guide
DG-AK-41 rev 1.39; 04 §16.9 rev 1.54, DB-08).

A test world lives on a frozen business clock (DG-TST-14: 2026-09-12T12:00Z), but the retained
inputs carry TWO record clocks: a subledger or journal line is recorded on the application clock
(``uow.now``), while a contract event's ``recorded_at`` — and so its contract version's
``known_at`` — is the SERVER clock (DB-08 ``tg_contract_event__insert``: ``now()``), the wall
clock of the run. An explicit as-of read keeps its cutoff exactly (READ-1, ``known_at_basis =
historical``): a report run given ``known_at``, and every lock dataset the snapshot registry
freezes at the lock instant. Cut at a business-clock instant, such a read precedes every version
and returns an empty population — the comparison then holds vacuously or the witness finds no
row. In production the application clock IS the server clock, so the lock instant follows every
record stamp; ``on_record_time`` puts a world in that position, as
``tests/domain/reports/test_report_run_clock_db.py`` does for one run.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from support.worlds import ReportWorld, resigned


def on_record_time(world: ReportWorld) -> ReportWorld:
    """The same world with its frozen application clock one second after the server's
    ``clock_timestamp()`` — read once, after everything committed so far; never moved backwards —
    and fresh sessions for its actors (``worlds.resigned``: a jump of days ends every session at
    the absolute limit). Nothing is substituted or bypassed: the clock is where a production
    request's would be."""
    stamp = world.place.scalar(select(func.clock_timestamp()))
    assert isinstance(stamp, datetime), stamp
    clock = world.place.clock
    clock.set(max(clock.now(), stamp + timedelta(seconds=1)))
    return resigned(world)
