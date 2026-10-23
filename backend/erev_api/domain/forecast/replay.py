"""Apply a published input bundle atomically to an empty target draft."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from erev_api.domain.forecast import event_sets, input_order, replay_apply, replay_resources
from erev_api.domain.forecast.replay_inputs import ReplayInputs
from erev_api.problems import Problem
from erev_api.schemas.events import EventAppendIn
from erev_api.schemas.imports import ImportCreateIn
from erev_api.uow import UnitOfWork


def apply(
    uow: UnitOfWork,
    inputs: ReplayInputs,
    *,
    target_set_id: UUID,
    heartbeat: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Copy, apply in retained order, then publish; any failure rolls back the whole bundle.

    The refresh worker owns the surrounding target transaction and durable completion state.
    It must not expose or switch to this workspace before that transaction succeeds. An empty
    draft is required so retrying cannot append the same forecast facts twice. This function
    never commits, switches scenarios, or queues child computations.
    """
    current = event_sets.require_draft(uow, target_set_id)
    if input_order.sequence(current):
        raise Problem("invalid-transition", "Forecast replay requires an empty target input set.")
    with uow.savepoint():
        materialized = replay_resources.materialize_files(uow, inputs, target_set_id=target_set_id)
        applied_uploads: dict[str, str] = {}
        for step in materialized.steps:
            if heartbeat is not None:
                heartbeat()
            if step["kind"] == "API_COMMAND":
                replay_apply.apply_command(
                    uow,
                    contract_id=UUID(step["contract_id"]),
                    input_set_id=target_set_id,
                    body=EventAppendIn.model_validate(step["body"]),
                )
            elif step["kind"] == "IMPORT_UPLOAD":
                identity = replay_apply.apply_file(
                    uow,
                    ImportCreateIn(
                        file_id=UUID(step["file_id"]),
                        template_code=step["template_code"],
                        template_version=step["template_version"],
                        parameters=step["parameters"],
                        forecast_event_set_id=target_set_id,
                    ),
                    quarantine=step["is_quarantine_mode"],
                    mapping_snapshot=step["mapping_profile"],
                )
                applied_uploads[step["source_upload_id"]] = str(identity)
            else:
                raise Problem("precondition-failed", "The replay input kind is unsupported.")
        if heartbeat is not None:
            heartbeat()
        latest = event_sets.require_draft(uow, target_set_id)
        published = event_sets.change(
            uow, target_set_id, expected_version=latest["row_version"], publish=True
        )
        uow.audit(
            contract_ids=event_sets.audit_contract_ids(uow.session, published),
            action="forecast_event_set.replay",
            object_type="forecast_event_set",
            object_id=target_set_id,
            detail={
                "source_input_set_id": str(inputs.source_id),
                "source_content_sha256": inputs.content_sha256,
                "target_content_sha256": published["content_sha256"],
                "input_count": len(materialized.steps),
                "upload_bindings": applied_uploads,
            },
        )
        return published
