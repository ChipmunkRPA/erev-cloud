"""A shred in flight, for the tests of the commands that count a stored file as a document (item
EVIDENCE-COUNT-SHREDDED-1; 04 T-PLT-29 "A document a rule asks for"; 05 PRV-07 b).

``file.shred`` takes the ``file_object`` row FOR UPDATE, reads the records that hold the file and
marks the row, in one transaction. A command that counts the file — the submission of a manual
adjustment or of an SSP version, the approval of that version, the preparer's sign-off of a
reconciliation, an attachment — takes the row's lock as well, so that the later of the two sees
what the earlier committed. ``beside_a_shred`` plays the shred's side with a holder session: it
locks the row and marks it shredded without committing, starts the request on another connection
and waits until PostgreSQL reports one of the request's backends blocked by the holder in a
statement on ``file_object`` (``support.interleave``: bound to both participants, never a sleep).
Then it commits, and the request answers what it finds. A request that never waits for the row
ran past the shred: the holder rolls back and the answer is reported with ``waited = False``.

The request is watched for as long as it runs. That it "ran past" is known the moment it has
answered without one of its backends waiting for the row, however loaded the machine is; a
request that still runs has only not reached the row yet. ``settle`` bounds the watch and is no
measure of the request. (Until item FILE-SHRED-DURABLE-ORDER-1 the helper concluded "ran past"
after 20 seconds. Measured on a host at load 50: a request reached its lock 12.5 seconds after
the holder began, and a witness of the lock failed once for the machine's reason.)
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import file_object
from sqlalchemy import select, update
from support.interleave import await_lock_wait, backend_pid, observing_checkouts

IN_FLIGHT = "DSR-2026-0917: a shred in flight"


@dataclass(frozen=True, slots=True)
class BesideAShred:
    """Whether the request waited for the file's row, and what it answered."""

    waited: bool
    response: Any


def beside_a_shred(
    tenant_id: UUID,
    file_id: UUID,
    run_request: Callable[[], Any],
    *,
    at: datetime,
    settle: float = 180.0,
) -> BesideAShred:
    """Run ``run_request`` beside a shred of ``file_id`` that commits once the request waits for
    the file's row. The request is watched until it waits for the row, has answered, or
    ``settle`` seconds have passed."""
    ctx = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["result"] = run_request()
        except Exception as exc:  # noqa: BLE001 — surfaced by the assertion below
            outcome["error"] = exc

    waited = True
    with observing_checkouts() as backends, tenant_session(ctx) as holder:
        holder_pid = backend_pid(holder)
        holder.execute(
            select(file_object.c.id).where(file_object.c.id == file_id).with_for_update()
        )
        holder.execute(
            update(file_object)
            .where(file_object.c.id == file_id)
            .values(shredded_at=at, shredded_by_kind="SYSTEM", shred_reason=IN_FLIGHT)
        )
        request = threading.Thread(target=run, name="request-beside-a-shred")
        request.start()
        try:
            await_lock_wait(
                holder,
                holder_pid=holder_pid,
                backends=backends,
                timeout=settle,
                expect="file_object",
                while_running=request.is_alive,
            )
        except AssertionError:
            # The request answered — or the watch ended — and no backend of it waited for the
            # row: it ran past the shred, which is withdrawn so that the world is as the
            # request left it.
            waited = False
            holder.rollback()
    request.join(timeout=settle)
    assert not request.is_alive() and "error" not in outcome, outcome
    return BesideAShred(waited=waited, response=outcome["result"])
