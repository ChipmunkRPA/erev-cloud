"""Copy verified replay files into the target workspace and rebind command references."""

import hashlib
import io
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from erev_api.domain.forecast import event_sets
from erev_api.domain.forecast.replay_inputs import MAX_BYTES, ReplayInputs
from erev_api.domain.platform import attachments
from erev_api.problems import Problem
from erev_api.schemas.events import EventAppendIn
from erev_api.uow import UnitOfWork


@dataclass(frozen=True)
class MaterializedFiles:
    steps: tuple[dict[str, Any], ...]
    file_ids: dict[UUID, UUID]


def materialize_files(
    uow: UnitOfWork, inputs: ReplayInputs, *, target_set_id: UUID
) -> MaterializedFiles:
    """Re-encrypt source bytes through normal upload policy, authorization and audit.

    The caller supplies a bundle from the authorized published-input reader. Mapping profiles
    remain retained descriptors for the file executor's mapping_snapshot argument; they are
    never silently replaced by the latest target profile. No source object is mutated or linked by
    its old tenant storage key. The caller persists the returned bindings with its replay state.
    """
    if (
        "scenario.use" not in uow.principal.permissions
        or uow.principal.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    target = event_sets.require_draft(uow, target_set_id)
    if target["production_scenario_id"] != inputs.scenario_id:
        raise Problem("precondition-failed", "The replay inputs belong to another scenario.")
    steps = deepcopy(inputs.steps)
    required: set[UUID] = set()
    for step in steps:
        if step["kind"] == "API_COMMAND":
            required.update(EventAppendIn.model_validate(step["body"]).evidence_file_ids)
        elif step["kind"] == "IMPORT_UPLOAD":
            required.add(UUID(step["file_id"]))
        else:
            raise Problem("precondition-failed", "The replay input kind is unsupported.")
    available = {item.id for item in inputs.files}
    if available != required or len(available) != len(inputs.files):
        raise Problem(
            "precondition-failed", "The replay file manifest is incomplete or duplicated."
        )
    if sum(len(item.content) for item in inputs.files) > MAX_BYTES:
        raise Problem("precondition-failed", "The forecast replay files exceed the supported size.")
    for item in inputs.files:
        if hashlib.sha256(item.content).hexdigest() != item.sha256:
            raise Problem("precondition-failed", "A replay file does not match its retained hash.")
    bindings: dict[UUID, UUID] = {}
    with uow.savepoint():
        for item in inputs.files:
            with io.BytesIO(item.content) as stream:
                row = attachments.upload_file(
                    uow,
                    purpose=item.purpose,
                    stream=stream,
                    original_filename=item.name,
                    media_type=item.media_type,
                )
            if str(row["sha256"]).strip() != item.sha256:
                raise Problem("precondition-failed", "The copied replay file has a different hash.")
            bindings[item.id] = UUID(str(row["id"]))
        for step in steps:
            if step["kind"] == "API_COMMAND":
                body = EventAppendIn.model_validate(step["body"])
                step["body"] = body.model_copy(
                    update={
                        "evidence_file_ids": [bindings[value] for value in body.evidence_file_ids]
                    }
                ).model_dump(mode="json")
            else:
                step["file_id"] = str(bindings[UUID(step["file_id"])])
        uow.audit(
            contract_ids=tuple(
                UUID(step["contract_id"]) for step in steps if step["kind"] == "API_COMMAND"
            ),
            action="forecast_event_set.materialize_files",
            object_type="forecast_event_set",
            object_id=target_set_id,
            detail={
                "source_input_set_id": str(inputs.source_id),
                "source_content_sha256": inputs.content_sha256,
                "file_bindings": {str(source): str(target) for source, target in bindings.items()},
            },
        )
    return MaterializedFiles(steps=steps, file_ids=bindings)
