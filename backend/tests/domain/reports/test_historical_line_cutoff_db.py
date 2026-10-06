"""F-RPS-CUTOFF-R1 (record §43; Codex packet 1849): the persisted line time against the historical
cutoff. DB-bound: written for the lane's ``erev_rv_l17_test`` and recorded **not run — databases
not provisioned** by this lane; it runs in an admitted database stage (the integrated batch's
``ci`` stage collects this directory).

``subledger.post`` stamps every line ``recorded_at = uow.now`` — the application clock: in
production the request's server time captured once (DG-KRN-UOW-01), under the answer-key runner
the item's business time (DG-AK-41) — while ``contract_version.known_at`` is the events' server
``recorded_at`` (DB-08) and a checkpoint's stamp is ``clock_timestamp()`` after its commit. The
historical basis (``known_at_basis = historical``) cuts versions at the supplied stamp on the
server clock and lines by ``recorded_at <= known_at`` (API-C-10) on the application clock. The
first test shows the two record clocks on one posting. The second is the exclusion the historical
basis promises for a line whose posting COMMITTED after the stamp with an EARLIER application
clock in the SAME effective period: it does not hold on today's persisted line time and is carried
as a strict expected failure — UNRESOLVED EVIDENCE, not a fix (Codex 1922). The supervisor ruled
Q-3 (D-98 candidate 113) as option (b): a new server-stamped T-SL-04 column used only by the
historical-basis line predicate, a later slice (frps5, after Alembic 0064 lands); for this slice
the window is accepted and documented (option (c)); record §43. Nothing here is stubbed green or
relabelled; ``strict`` turns this test into a FAILURE the moment frps5 lands, so the marker must
come off with it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.tables import contract_version, subledger_line
from erev_api.domain.journals import subledger
from erev_api.enums import SubledgerPostingKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import K11World, computed, delivered_k11, k11_world

BOOK = "ASC606"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> K11World:
    return k11_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _posted(world: K11World) -> tuple[UUID, Any]:
    """K-11 delivered and computed once: the ENGINE_COMPUTE posting id, the stored computation."""
    booked = delivered_k11(world)
    _, _, stored = computed(world.place, booked.combination_group["id"])
    return UUID(stored["subledger_posting_ids"][BOOK]), stored


def _lines_of(world: K11World, posting_id: UUID) -> list[dict[str, Any]]:
    return world.place.rows(
        select(subledger_line).where(subledger_line.c.subledger_posting_id == posting_id)
    )


def test_one_posting_carries_two_record_clocks(world: K11World, clock: FrozenClock) -> None:
    """The posting's lines are recorded on the application clock (``subledger.post``:
    ``recorded_at = uow.now``); the version the same computation persisted is known on the
    server clock (DB-08) — later, under a frozen application clock."""
    posting_id, stored = _posted(world)
    lines = _lines_of(world, posting_id)
    assert lines and {line["recorded_at"] for line in lines} == {clock.now()}
    version_known_at = world.place.scalar(
        select(contract_version.c.known_at).where(
            contract_version.c.id == UUID(stored["contract_version_ids"][BOOK])
        )
    )
    assert isinstance(version_known_at, datetime) and version_known_at > clock.now()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "record §43 / Q-3 (D-98 candidate 113: option (b), a server-stamped line column for the "
        "historical predicate, scheduled as frps5 after Alembic 0064; option (c) for now): "
        "subledger_line.recorded_at is the application clock (subledger.post), so a posting "
        "committed after the stamp with an earlier application clock is not excluded from a "
        "historical read as of the stamp — unresolved evidence, not a fix; strict: FAILS when "
        "frps5 lands and this marker must come off"
    ),
)
def test_historical_read_excludes_a_line_posted_after_the_stamp(
    world: K11World, clock: FrozenClock
) -> None:
    """Later actual posting, earlier application clock, same effective period: not known at the
    stamp (READ-1), so a historical read as of the stamp must exclude it."""
    first, stored = _posted(world)
    stamp = world.place.scalar(select(func.clock_timestamp()))  # the checkpoint's record time
    assert isinstance(stamp, datetime)
    clock.set(clock.now() + timedelta(minutes=1))  # the application clock moves on, still earlier
    assert clock.now() < stamp
    copied = [{**line, "id": new_id()} for line in _lines_of(world, first)]  # same effective dates
    with world.place.uow() as uow:
        later = subledger.post(
            uow,
            book_code=BOOK,
            posting_kind=SubledgerPostingKind.ENGINE_COMPUTE,
            idempotency_key=f"{subledger.compute_key(stored['id'])}:after-the-stamp",
            description="Committed after the stamp; earlier application clock; same period",
            lines=copied,
            contract_computation_id=stored["id"],
        )
        uow.commit()
    assert later.replayed is False
    with world.place.uow() as uow:
        visible = (
            uow.session.execute(
                subledger.line_statement(
                    uow.session, subledger.LineFilters(book=BOOK, known_at=stamp)
                )
            )
            .mappings()
            .all()
        )
    postings = {row["subledger_posting_id"] for row in visible}
    assert first in postings
    assert later.posting_id not in postings
