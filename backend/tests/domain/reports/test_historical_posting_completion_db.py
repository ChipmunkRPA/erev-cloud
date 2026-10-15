"""Historical line queries wait for the completed posting's server-stamped seal."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import pytest
from erev_api.db import new_id
from erev_api.db.tables import subledger_line, subledger_posting_seal
from erev_api.domain.journals import subledger
from erev_api.enums import SubledgerPostingKind
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from support.factories import K11World
from tests.domain.reports.test_historical_line_cutoff_db import _lines_of, _posted
from tests.domain.reports.test_historical_line_cutoff_db import app as app
from tests.domain.reports.test_historical_line_cutoff_db import world as world


def test_cutoff_before_sealing_excludes_the_entire_posting(
    world: K11World, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, stored = _posted(world)
    copied = [{**line, "id": new_id()} for line in _lines_of(world, first)]
    original_store = subledger._store_lines
    cutoffs: list[datetime] = []

    def store_then_capture(session: Session, line_rows: Sequence[dict[str, Any]]) -> None:
        original_store(session, line_rows)
        stamp = world.place.scalar(select(func.clock_timestamp()))
        assert isinstance(stamp, datetime)
        assert all(line["recorded_server_at"] <= stamp for line in line_rows)
        cutoffs.append(stamp)

    monkeypatch.setattr(subledger, "_store_lines", store_then_capture)
    with world.place.uow() as uow:
        later = subledger.post(
            uow,
            book_code="ASC606",
            posting_kind=SubledgerPostingKind.ENGINE_COMPUTE,
            idempotency_key=f"{subledger.compute_key(stored['id'])}:seal-after-cutoff",
            description="Lines inserted before the cutoff; seal inserted afterward",
            lines=copied,
            contract_computation_id=stored["id"],
        )
        uow.commit()
    (stamp,) = cutoffs
    sealed = world.place.scalar(
        select(subledger_posting_seal.c.sealed_server_at).where(
            subledger_posting_seal.c.subledger_posting_id == later.posting_id
        )
    )
    assert sealed > stamp
    with world.place.uow() as uow:
        visible = set(
            uow.session.scalars(
                select(subledger_line.c.subledger_posting_id).where(
                    subledger.recorded_by(stamp, historical=True)
                )
            )
        )
        complete = set(
            uow.session.scalars(
                select(subledger_line.c.id).where(
                    subledger_line.c.subledger_posting_id == later.posting_id,
                    subledger.recorded_by(sealed, historical=True),
                )
            )
        )
    assert first in visible
    assert later.posting_id not in visible
    assert complete == {line["id"] for line in copied}
