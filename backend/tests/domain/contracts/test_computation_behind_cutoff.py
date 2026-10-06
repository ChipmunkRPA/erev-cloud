"""The head's own cutoff decides whether a computation is behind it (item COMPUTE-BEHIND-CUTOFF-1,
register index 285; 04 T-CON-07 ``cutoff_at`` and §14.1 "A computation behind its group" rev
1.302; 05 RCP-22 rev 1.208; dev-guide DG-CMD-10 rev 1.288).

Clause (iii) of ``computation.behind_its_group`` compared the head's ``created_at`` — the
instant of its unit of work, on the APPLICATION's clock — with this bundle's cutoff, which is
the later of the unit's instant and its transaction's start (``bundles.record_cutoff``). Where the
application's clock runs behind the database's, a head carries an instant earlier than the bound
it admitted by, and a computation whose cutoff lies between the two was not told apart: measured
before the item with the clock twenty seconds behind, in the world of
``test_fx_remeasurement_recompute.py`` — a computation that began before a rate version's
approval and persisted after another computation had posted the version's difference was
stored, posted the difference (GBP 540.00) back out, became the head and left the group clean.

A computation now stores the bound its bundle admitted by (T-CON-07 ``cutoff_at``), and the
clause compares bound with bound: no clock is assumed. A head stored before the column carries
none and answers as it did, by its ``created_at``.

The cases have the shape of ``test_computation_behind_group.py`` and use its helpers: a
computation BEGINS (``_begun``), something happens to its group and commits, and the computation
is then asked how it stands (``_behind``) and persisted.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import combination_group, contract_computation, fx_rate_set
from erev_api.domain.contracts import bundles, computation
from erev_api.enums import ComputationStatus
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select, update
from support.db import TestDatabase
from support.factories import Workspace
from support.rows import contract_computation_values
from test_computation_behind_group import (
    JULY_CORRECTED,
    _begun,
    _behind,
    _computed_now,
    _ledger,
    _logged,
    _refused,
    _resigned,
    _state,
)
from test_fx_remeasurement_recompute import World as FxWorld
from test_fx_remeasurement_recompute import _published_version, delivered
from test_fx_remeasurement_recompute import world as fx  # noqa: F401  (the FX world's fixture)

# How far the computing hosts' clock runs behind the database's in these cases.
LAG = timedelta(seconds=20)
DIFFERENCE = ("FY2026-P07", "REVENUE", Decimal("0.0000"), Decimal("-540.0000"))


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _servers_present(place: Workspace) -> datetime:
    stamp = place.scalar(select(func.clock_timestamp()))
    assert isinstance(stamp, datetime)
    return stamp


def _cutoff(uow: Any) -> datetime:
    """The bound a bundle of ``uow`` admits by: the later of its instant and its transaction's
    start."""
    return bundles.record_cutoff(uow.session, uow.now)


def _head(place: Workspace, group_id: UUID) -> dict[str, Any]:
    (row,) = place.rows(
        select(contract_computation)
        .join(
            combination_group,
            (combination_group.c.tenant_id == contract_computation.c.tenant_id)
            & (combination_group.c.head_computation_id == contract_computation.c.id),
        )
        .where(combination_group.c.id == group_id)
    )
    return row


def test_a_head_that_admitted_by_a_later_cutoff_refuses_whatever_its_clock_read(
    fx: FxWorld,  # noqa: F811
    log_stream: io.StringIO,
) -> None:
    """The limit of clause (iii), measured before the item. The computing hosts' clock runs
    twenty seconds behind the database's. A computation begins: its cutoff is its transaction's
    start. On a host whose clock is right a rate version is approved and the group marked —
    after that cutoff; while the mark stands the computation is behind by the mark. ANOTHER
    computation, begun after the approval on the lagging clock, admits the version, posts its
    difference (GBP 540.00), ends the mark and is the head — with a ``created_at`` EARLIER than
    the first computation's cutoff, which is all the clause read. The first computation is
    refused by the head: the head admitted by a later bound than this bundle's."""
    contract_id, group_id = delivered(fx)
    place = fx.place
    set_id = place.scalar(select(fx_rate_set.c.id).where(fx_rate_set.c.code == "AVM-UK-AVERAGE"))
    place.clock.set(_servers_present(place) - LAG)
    with _begun(place) as late:
        began, cutoff = late.now, _cutoff(late)
        assert began < cutoff  # the cutoff is the transaction's start, not the lagging instant

        place.clock.set(_servers_present(place))  # a host whose clock is right
        maya, marcus = _resigned(fx, fx.maya), _resigned(fx, fx.marcus)
        _published_version(fx.app, maya, marcus, str(set_id), JULY_CORRECTED)
        # the approval marks the group itself (item FX-REPUBLISH-DIRTY-1; by hand until then)
        assert _state(place, group_id, contract_id)["dirty_since"] > cutoff
        assert _behind(late, group_id) == (computation.BEHIND_MARK,)

        place.clock.set(began + timedelta(seconds=1))  # the lagging clock again, a second on
        assert _computed_now(place, group_id).status is ComputationStatus.SUCCEEDED
        corrected = _ledger(place, contract_id)
        assert DIFFERENCE in corrected
        stood = _state(place, group_id, contract_id)
        assert stood["dirty_since"] is None
        head = _head(place, group_id)
        # What the clause read before the item, and what it reads now.
        assert head["created_at"] <= cutoff
        assert head["cutoff_at"] is not None and head["cutoff_at"] > cutoff

        assert _behind(late, group_id) == (computation.BEHIND_HEAD,)
        _refused(lambda: computation.recompute(late, group_id))
    assert _ledger(place, contract_id) == corrected
    assert _state(place, group_id, contract_id) == stood
    assert _logged(log_stream) == [(str(group_id), (computation.BEHIND_HEAD,), "COMMAND")]


def _head_by_hand(
    place: Workspace, group_id: UUID, *, created_at: datetime, cutoff_at: datetime | None
) -> None:
    """The group pointed at a SUCCEEDED computation with the given stamps, written beside the
    product: one with no ``cutoff_at`` is a head as revision 0129 found it."""
    standing = _head(place, group_id)
    row = contract_computation_values(
        place.tenant_id,
        combination_group_id=group_id,
        engine_release_id=standing["engine_release_id"],
        stream_heads=standing["stream_heads"],
        known_at=standing["known_at"],
        created_at=created_at,
        cutoff_at=cutoff_at,
    )
    context = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(insert(contract_computation).values(**row))
        session.execute(
            update(combination_group)
            .where(combination_group.c.id == group_id)
            .values(
                head_computation_id=row["id"],
                row_version=combination_group.c.row_version + 1,
            )
        )


def test_a_head_stored_before_the_column_answers_by_its_created_at(fx: FxWorld) -> None:  # noqa: F811
    """No backfill: a computation stored before revision 0129 has no ``cutoff_at``, and the bound
    it admitted by is kept nowhere. Such a head answers as the clause was built — by its
    ``created_at`` — until the group is computed again: later than the cutoff it refuses, at or
    before the cutoff it does not, which is the limit as it stood. A head with its cutoff is
    read by the cutoff alone, strictly: an equal one refuses nothing, and a later one refuses
    whatever its ``created_at`` says."""
    _, group_id = delivered(fx)
    place = fx.place
    place.clock.set(_servers_present(place) - LAG)
    second = timedelta(seconds=1)
    with _begun(place) as late:
        cutoff = _cutoff(late)
        _head_by_hand(place, group_id, created_at=cutoff + second, cutoff_at=None)
        assert _behind(late, group_id) == (computation.BEHIND_HEAD,)
        _head_by_hand(place, group_id, created_at=cutoff, cutoff_at=None)
        assert _behind(late, group_id) == ()

        _head_by_hand(place, group_id, created_at=cutoff - LAG, cutoff_at=cutoff + second)
        assert _behind(late, group_id) == (computation.BEHIND_HEAD,)
        _head_by_hand(place, group_id, created_at=cutoff - LAG, cutoff_at=cutoff)
        assert _behind(late, group_id) == ()
