"""Authorize and verify frozen validation datasets for report construction and reruns."""

import hashlib
import json
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.auth.principal import Principal
from erev_api.db.tables import release_validation, release_validation_attempt
from erev_api.files.store import open_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


@dataclass(frozen=True, slots=True)
class ValidationDataset:
    attempt_id: UUID
    file_id: UUID
    sha256: str
    required_entity_ids: tuple[UUID, ...]
    content: bytes


def _invalid() -> Problem:
    return Problem(
        "validation-failed", "The frozen validation dataset cannot be used for reporting."
    )


def read_for_report(
    uow: UnitOfWork,
    attempt_id: UUID,
    *,
    entity_ids: Collection[UUID],
    known_at: datetime,
    expected_file_id: UUID | None = None,
    expected_sha256: str | None = None,
    requester: Principal | None = None,
) -> ValidationDataset:
    """Read the whole frozen population after checking the current report.run grant.

    Workers supply the authorized requester; SYSTEM has no implicit grant. A report cannot
    filter a group dataset to a partial entity selection. Reruns may bind the original file/hash.
    Only immutable source metadata is read from tables; all report figures come from the file.
    """
    principal = uow.principal if requester is None else requester
    if principal.tenant_id != uow.principal.tenant_id:
        raise Problem("forbidden")
    scope = principal.permission_scopes.get("report.run")
    if "report.run" not in principal.permissions or scope is None or scope == frozenset():
        raise Problem("forbidden")
    if (expected_file_id is None) != (expected_sha256 is None) or known_at > uow.now:
        raise _invalid()
    source = (
        uow.session.execute(
            select(
                release_validation_attempt,
                release_validation.c.effective_level,
                release_validation.c.engine_release_id,
                release_validation.c.source_engine_release_id,
            )
            .join(
                release_validation,
                (release_validation.c.tenant_id == release_validation_attempt.c.tenant_id)
                & (release_validation.c.id == release_validation_attempt.c.release_validation_id),
            )
            .where(
                release_validation_attempt.c.tenant_id == principal.tenant_id,
                release_validation_attempt.c.id == attempt_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if source is None:
        raise Problem("not-found")
    required = tuple(sorted(source["required_entity_ids"], key=str))
    selected = set(entity_ids)
    if not set(required) <= selected or (scope != "*" and (not required or not selected <= scope)):
        raise Problem("not-found")
    if (
        source["status"] not in {"COMPLETE", "INCOMPLETE", "SUPERSEDED"}
        or source["dataset_file_id"] is None
        or source["dataset_sha256"] is None
    ):
        raise _invalid()
    file_id, digest = source["dataset_file_id"], source["dataset_sha256"]
    if expected_file_id is not None and (file_id, digest) != (expected_file_id, expected_sha256):
        raise _invalid()
    try:
        meta, stream = open_file(uow.session, file_id, files=uow.files, keyring=uow.keyring)
    except FileNotFoundError as error:
        raise _invalid() from error
    except Problem as error:
        if error.slug != "not-found":
            raise
        raise _invalid() from error
    with stream:
        content = stream.read()
    if (
        meta["purpose"] != "VALIDATION_DATASET"
        or meta["media_type"] != "application/json"
        or meta["size_bytes"] != len(content)
        or meta["sha256"] != digest
        or hashlib.sha256(content).hexdigest() != digest
        or meta["created_at"] > known_at
    ):
        raise _invalid()
    expected = {
        "release_validation_attempt_id": attempt_id,
        "release_validation_id": source["release_validation_id"],
        "attempt_no": source["attempt_no"],
        "effective_level": source["effective_level"],
        "engine_release_id": source["engine_release_id"],
        "source_engine_release_id": source["source_engine_release_id"],
        "seed": source["seed"],
        "population": source["population"],
        "required_entity_ids": [str(item) for item in required],
    }
    try:
        payload = json.loads(content)
        if (
            not isinstance(payload, dict)
            or canonical_bytes(payload) != content
            or set(payload) != {"dataset_format", "attempt", "groups"}
            or type(payload["dataset_format"]) is not int
            or payload["dataset_format"] != 1
            or payload["attempt"] != json.loads(canonical_bytes(expected))
            or not isinstance(payload["groups"], list)
        ):
            raise _invalid()
    except (ValueError, TypeError, UnicodeError) as error:
        raise _invalid() from error
    return ValidationDataset(attempt_id, file_id, digest, required, content)
