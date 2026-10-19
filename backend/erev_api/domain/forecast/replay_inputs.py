"""Materialize verified published inputs before a scenario refresh changes its source workspace."""

import hashlib
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from pydantic import ValidationError
from sqlalchemy import select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import (
    contract,
    file_object,
    forecast_event_set,
    import_mapping_profile,
    import_upload,
)
from erev_api.domain.forecast import event_sets, input_order
from erev_api.domain.imports import mapping_profiles, scope
from erev_api.domain.platform import file_access
from erev_api.domain.policies import lifecycle
from erev_api.enums import FilePurpose
from erev_api.files.store import lock_readable, open_file
from erev_api.problems import Problem
from erev_api.schemas.events import EventAppendIn
from erev_api.uow import UnitOfWork

MAX_BYTES = 256 * 1024 * 1024
_COMMAND_PATH = re.compile(r"/contracts/([0-9a-f-]{36})/events")


@dataclass(frozen=True)
class ReplayFile:
    id: UUID
    purpose: str
    name: str | None
    media_type: str
    sha256: str
    content: bytes


@dataclass(frozen=True)
class ReplayInputs:
    source_id: UUID
    scenario_id: UUID
    content_sha256: str
    steps: tuple[dict[str, Any], ...]
    files: tuple[ReplayFile, ...]


def _refuse(detail: str) -> Problem:
    return Problem("precondition-failed", detail)


def load(uow: UnitOfWork, identity: UUID) -> ReplayInputs:
    """Read as the refresh requester in the old scenario tenant, without applying any input.

    The worker must reauthorize the requester when it starts; SYSTEM is not a substitute for
    that permission. File bytes and mapping definitions are retained here, never fetched from
    an arbitrary command URL or silently replaced with a newer mapping profile.
    """
    principal = uow.principal
    if (
        "scenario.use" not in principal.permissions
        or principal.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    scenario_id = event_sets._scenario(uow.session, principal.db_context)
    current = event_sets._row(uow.session, identity)
    if current["status"] != "PUBLISHED" or current["production_scenario_id"] != scenario_id:
        raise Problem("invalid-transition", "Choose a published input set of this scenario.")
    content = canonical_bytes(input_order.content(current))
    if hashlib.sha256(content).hexdigest() != current["content_sha256"]:
        raise _refuse("The published forecast input content does not match its hash.")
    ordered = input_order.sequence(current)
    total = len(content)
    if total > MAX_BYTES:
        raise _refuse("The forecast replay inputs exceed the supported size.")
    ancestors = {identity}
    previous = current
    while previous["supersedes_version_id"] is not None:
        ancestor_id = previous["supersedes_version_id"]
        if ancestor_id in ancestors:
            raise _refuse("The forecast input version chain contains a cycle.")
        # Earlier versions may each contain the same large input arrays. Read only lineage
        # metadata; the selected publication already hashes the exact input IDs and commands.
        found_ancestor = (
            uow.session.execute(
                select(
                    forecast_event_set.c.id,
                    forecast_event_set.c.code,
                    forecast_event_set.c.version_no,
                    forecast_event_set.c.production_scenario_id,
                    forecast_event_set.c.status,
                    forecast_event_set.c.supersedes_version_id,
                ).where(forecast_event_set.c.id == ancestor_id)
            )
            .mappings()
            .one_or_none()
        )
        if found_ancestor is None:
            raise _refuse("The forecast input version chain is incomplete.")
        ancestor = dict(found_ancestor)
        if (
            ancestor["code"] != current["code"]
            or ancestor["production_scenario_id"] != scenario_id
            or ancestor["version_no"] != previous["version_no"] - 1
            or ancestor["status"] != "SUPERSEDED"
        ):
            raise _refuse("The forecast input version chain is inconsistent.")
        ancestors.add(ancestor_id)
        previous = ancestor
    retained: dict[UUID, ReplayFile] = {}

    def read_file(file_id: UUID, expected_sha: str | None = None) -> None:
        nonlocal total
        if file_id not in retained:
            lock_readable(uow.session, (file_id,))
            stored_metadata = (
                uow.session.execute(select(file_object).where(file_object.c.id == file_id))
                .mappings()
                .one_or_none()
            )
            if stored_metadata is None:
                raise _refuse("A forecast input file is unavailable.")
            if int(stored_metadata["size_bytes"]) > MAX_BYTES - total:
                raise _refuse("The forecast replay inputs exceed the supported size.")
            metadata, stream = open_file(uow.session, file_id, files=uow.files, keyring=uow.keyring)
            with stream:
                raw = stream.read(MAX_BYTES - total + 1)
            digest = hashlib.sha256(raw).hexdigest()
            total += len(raw)
            if (
                total > MAX_BYTES
                or len(raw) != metadata["size_bytes"]
                or digest != str(metadata["sha256"]).strip()
            ):
                raise _refuse("A forecast input file does not match its retained metadata.")
            retained[file_id] = ReplayFile(
                file_id,
                str(metadata["purpose"]),
                metadata["original_filename"],
                str(metadata["media_type"]),
                digest,
                raw,
            )
        if expected_sha is not None and retained[file_id].sha256 != expected_sha:
            raise _refuse("The forecast import source does not match its committed file hash.")

    steps: list[dict[str, Any]] = []
    for entry in ordered:
        if entry["kind"] == "API_COMMAND":
            command = current["api_commands"][entry["index"]]
            if not isinstance(command, dict):
                raise _refuse("A forecast event command is malformed.")
            match = _COMMAND_PATH.fullmatch(str(command.get("path", "")))
            if (
                command.get("method") != "POST"
                or match is None
                or set(command) != {"method", "path", "body"}
            ):
                raise _refuse("The forecast input contains an unsupported command.")
            try:
                contract_id = UUID(match[1])
                body = EventAppendIn.model_validate(command["body"])
            except (ValueError, ValidationError) as error:
                raise _refuse("A forecast event command is malformed.") from error
            entity_id = uow.session.scalar(
                select(contract.c.contracting_entity_id).where(contract.c.id == contract_id)
            )
            if entity_id is None:
                raise Problem("not-found")
            require_for_entity(uow.ctx, "event.record", entity_id)
            for evidence_id in body.evidence_file_ids:
                if file_access.bound(uow.session, uow.ctx, evidence_id) is None:
                    raise Problem("not-found")
                read_file(evidence_id)
            steps.append(
                {
                    "kind": "API_COMMAND",
                    "contract_id": str(contract_id),
                    "body": body.model_dump(mode="json"),
                }
            )
            continue
        upload_id = UUID(entry["id"])
        found = (
            uow.session.execute(select(import_upload).where(import_upload.c.id == upload_id))
            .mappings()
            .one_or_none()
        )
        if found is None:
            raise Problem("not-found")
        upload = dict(found)
        scope.require_visible(principal, upload)
        if upload["status"] != "COMMITTED" or upload["forecast_event_set_id"] not in ancestors:
            raise _refuse("A forecast file is not a committed input of this version chain.")
        template_code = str(upload["template_code"])
        if template_code not in event_sets.FORECAST_TEMPLATES:
            raise _refuse("The forecast file uses an unsupported template.")
        permission = scope.scope_of(template_code).write_permission
        held = principal.permission_scopes.get(permission, frozenset())
        scope.require_covered(
            scope.committing_entity_ids(upload), scope.Bounds(allowed=held, db_scope=held)
        )
        if "import.upload" not in principal.permissions:
            raise Problem("forbidden")
        profile = None
        if upload["mapping_profile_id"] is not None:
            found_profile = (
                uow.session.execute(
                    select(import_mapping_profile).where(
                        import_mapping_profile.c.id == upload["mapping_profile_id"]
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (
                found_profile is None
                or found_profile["status"] not in {"PUBLISHED", "SUPERSEDED"}
                or found_profile["template_code"] != template_code
            ):
                raise _refuse("The committed forecast mapping profile is unavailable.")
            if (
                lifecycle.current_sha256(uow.session, mapping_profiles.KIND, found_profile["id"])
                != found_profile["content_sha256"]
            ):
                raise _refuse("The committed forecast mapping profile does not match its hash.")
            profile = {
                "id": str(found_profile["id"]),
                "content_sha256": found_profile["content_sha256"],
                **mapping_profiles.KIND.content(uow.session, found_profile["id"]),
            }
        file_id = upload["file_object_id"]
        read_file(file_id, str(upload["file_sha256"]).strip())
        if retained[file_id].purpose != FilePurpose.IMPORT_SOURCE.value:
            raise _refuse("The forecast file is not an import source.")
        steps.append(
            {
                "kind": "IMPORT_UPLOAD",
                "source_upload_id": str(upload_id),
                "file_id": str(file_id),
                "template_code": template_code,
                "template_version": upload["template_version"],
                "parameters": upload["parameters"],
                "mapping_profile": profile,
                "is_quarantine_mode": upload["is_quarantine_mode"],
            }
        )
    if total + len(canonical_bytes(steps)) > MAX_BYTES:
        raise _refuse("The forecast replay inputs exceed the supported size.")
    return ReplayInputs(
        identity,
        scenario_id,
        str(current["content_sha256"]),
        tuple(steps),
        tuple(retained.values()),
    )
