"""Activation gate for a completed snapshot held pending forecast replay."""

from uuid import UUID

from sqlalchemy import select, update

from erev_api.db.tables import tenant
from erev_api.domain.forecast import event_sets
from erev_api.domain.platform import sandboxes
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def activate(
    uow: UnitOfWork, *, snapshot_id: UUID, input_set_id: UUID, content_sha256: str
) -> None:
    """Activate in the refresh completion transaction, after atomic input publication.

    Only the worker can reach a suspended workspace. The caller remains the requester with
    current copied grants, and must complete the source scenario switch in the same transaction.
    This internal helper never commits or changes the source scenario pointer itself.
    """
    if (
        "scenario.use" not in uow.principal.permissions
        or uow.principal.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    identity = uow.principal.tenant_id
    row = dict(
        uow.session.execute(select(tenant).where(tenant.c.id == identity).with_for_update())
        .mappings()
        .one()
    )
    if row["kind"] != "sandbox" or row["status"] != "SUSPENDED":
        raise Problem("invalid-transition", "The forecast copy is not awaiting activation.")
    loaded = sandboxes.sandbox_load_of(uow.session, row, awaiting_forecast=True)
    if loaded is None or loaded["tenant_snapshot_id"] != snapshot_id:
        raise Problem(
            "precondition-failed", "The forecast snapshot load is incomplete or different."
        )
    sandboxes.require_point_in_time(uow.session, identity)
    scenario_id = event_sets._scenario(uow.session, uow.principal.db_context)
    inputs = event_sets._row(uow.session, input_set_id, lock=True)
    if (
        inputs["production_scenario_id"] != scenario_id
        or inputs["status"] != "PUBLISHED"
        or inputs["content_sha256"] != content_sha256
    ):
        raise Problem("precondition-failed", "The expected forecast inputs are not published.")
    uow.session.execute(
        update(tenant)
        .where(tenant.c.id == identity)
        .values(
            status="ACTIVE",
            updated_at=uow.now,
            updated_by=uow.principal.id,
            updated_by_kind=uow.principal.kind.value,
        )
    )
    uow.audit(
        action="scenario.activate_refreshed_copy",
        object_type="scenario",
        object_id=scenario_id,
        before={"status": "SUSPENDED"},
        after={"status": "ACTIVE"},
        detail={
            "tenant_snapshot_id": str(snapshot_id),
            "input_set_id": str(input_set_id),
            "content_sha256": content_sha256,
        },
    )
