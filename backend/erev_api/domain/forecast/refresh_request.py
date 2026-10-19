"""Enqueue a fresh production copy and reserve its forecast replay in one transaction."""

from uuid import UUID

from erev_api.domain.forecast import archive, creation, refresh_state
from erev_api.domain.platform import snapshots
from erev_api.enums import PrincipalKind
from erev_api.problems import Problem
from erev_api.schemas.scenarios import ScenarioRefreshRequestedOut
from erev_api.uow import UnitOfWork


def request(
    uow: UnitOfWork, *, scenario_id: UUID, input_set_id: UUID, expected_version: int
) -> ScenarioRefreshRequestedOut:
    actor = uow.principal
    if (
        actor.kind is not PrincipalKind.USER
        or actor.id is None
        or actor.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    current = archive._row(uow.session, scenario_id, lock=True)
    if current["status"] != "ACTIVE" or current["row_version"] != expected_version:
        raise Problem("precondition-failed", "The scenario changed; reload it before refreshing.")
    requested = creation.ScenarioRequest(
        id=scenario_id, name=current["name"], purpose=current["purpose"], requested_by=actor.id
    )
    snapshot, job = snapshots.request_scenario_snapshot(
        uow,
        known_at=uow.now,
        name=current["name"],
        scenario_request=requested.model_dump(mode="json"),
    )
    pending = refresh_state.reserve(
        uow,
        scenario_id=scenario_id,
        expected_version=expected_version,
        input_set_id=input_set_id,
        snapshot_id=snapshot["id"],
    )
    return ScenarioRefreshRequestedOut(
        **job.model_dump(),
        scenario_id=scenario_id,
        tenant_snapshot_id=snapshot["id"],
        refresh_id=pending["id"],
    )
