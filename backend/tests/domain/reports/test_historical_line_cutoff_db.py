"""Historical line reads use database insertion time, independent of the application clock.

The stamp is included in the seal and overrides caller values. It is not a commit timestamp:
transactions overlapping a historical cutoff require separate commit-visibility treatment.
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
from erev_api.enums import ControlResult, SubledgerPostingKind
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
    assert all(line["recorded_server_at"] > clock.now() for line in lines)
    version_known_at = world.place.scalar(
        select(contract_version.c.known_at).where(
            contract_version.c.id == UUID(stored["contract_version_ids"][BOOK])
        )
    )
    assert isinstance(version_known_at, datetime) and version_known_at > clock.now()


def test_historical_read_excludes_a_line_posted_after_the_stamp(
    world: K11World, clock: FrozenClock
) -> None:
    """Later actual posting, earlier application clock, same effective period: not known at the
    stamp (READ-1), so a historical read as of the stamp must exclude it."""
    first, stored = _posted(world)
    clock.set(clock.now() + timedelta(minutes=1))  # the application clock moves on, still earlier
    copied = [{**line, "id": new_id()} for line in _lines_of(world, first)]  # same effective dates
    with world.place.uow() as uow:
        transaction_start = uow.session.scalar(select(func.transaction_timestamp()))
        stamp = uow.session.scalar(select(func.clock_timestamp()))
        assert isinstance(transaction_start, datetime)
        assert isinstance(stamp, datetime) and transaction_start < stamp
        assert clock.now() < stamp
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
    with world.place.uow() as uow:
        record_visible = set(
            uow.session.scalars(
                select(subledger_line.c.subledger_posting_id).where(
                    subledger.recorded_by(stamp, historical=False)
                )
            )
        )
    assert {first, later.posting_id} <= record_visible
    later_lines = _lines_of(world, later.posting_id)
    assert all(row["recorded_server_at"] > stamp for row in later_lines)
    # Copies carry the old server timestamp; the trigger must override it.
    assert all(row["recorded_at"] < stamp for row in later_lines)
    with world.place.uow() as uow:
        assert (
            subledger.verify_ledger_chain(uow.session, book_code=BOOK).result is ControlResult.PASS
        )
