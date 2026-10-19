"""Seed every accepted upgrade portion atomically and retain the original queue identity."""

import hashlib
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import insert, select

from erev_api.db import new_id
from erev_api.db.tables import (
    book,
    combination_group,
    combination_group_member,
    contract,
    release_group_processing,
    release_validation,
    release_validation_attempt,
)
from erev_api.db.transitions import apply
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

from .validation_fence import hold
from .validation_population import read


def seed(uow: UnitOfWork, *, validation_id: UUID) -> int:
    """Seed once in the accepting transaction; return the retained initial portion count.

    The caller must accept and seed in one transaction. This function never enables a release.
    On retry, compare the immutable initial rows with the manifest, not today's population.
    """
    hold(uow)
    tenant = uow.principal.tenant_id
    parent = (
        uow.session.execute(
            select(release_validation)
            .where(
                release_validation.c.tenant_id == tenant, release_validation.c.id == validation_id
            )
            .with_for_update(key_share=True)
        )
        .mappings()
        .one_or_none()
    )
    if parent is None:
        raise Problem("not-found")
    if (
        parent["effective_level"] not in {"MINOR", "MAJOR"}
        or parent["status"] not in {"PASSED", "APPROVED"}
        or parent["enabled_at"] is None
        or parent["accepted_attempt_id"] is None
    ):
        raise Problem("invalid-transition")
    attempt_id = parent["accepted_attempt_id"]
    attempt = (
        uow.session.execute(
            select(release_validation_attempt)
            .where(
                release_validation_attempt.c.tenant_id == tenant,
                release_validation_attempt.c.id == attempt_id,
                release_validation_attempt.c.release_validation_id == validation_id,
            )
            .with_for_update(key_share=True)
        )
        .mappings()
        .one_or_none()
    )
    if attempt is None or attempt["status"] != "COMPLETE" or attempt["dataset_file_id"] is None:
        raise Problem("invalid-transition")
    existing = (
        uow.session.execute(
            select(release_group_processing).where(
                release_group_processing.c.tenant_id == tenant,
                release_group_processing.c.release_validation_id == validation_id,
                release_group_processing.c.seq == 1,
            )
        )
        .mappings()
        .all()
    )
    manifest = parent["processing_seed"]
    if manifest is not None:
        keys = sorted(
            (str(row["combination_group_id"]), str(row["entity_id"]), str(row["book_code"]))
            for row in existing
        )
        if (
            not isinstance(manifest, dict)
            or type(manifest.get("version")) is not int
            or type(manifest.get("count")) is not int
            or manifest != _manifest(attempt_id, keys)
        ) or any(row["release_validation_attempt_id"] != attempt_id for row in existing):
            raise Problem("validation-failed", "The retained processing queue is incomplete.")
        return len(keys)
    if existing:
        raise Problem("validation-failed", "Processing rows exist without their seed manifest.")
    if (
        attempt["population"].get("fingerprint_version") != 1
        or attempt["population"].get("fingerprint") != read(uow).fingerprint()
    ):
        raise Problem(
            "validation-failed", "The accepted validation population changed before seeding."
        )
    portions = uow.session.execute(
        select(combination_group.c.id, contract.c.contracting_entity_id, book.c.code)
        .select_from(combination_group)
        .join(
            combination_group_member,
            (combination_group_member.c.tenant_id == combination_group.c.tenant_id)
            & (combination_group_member.c.combination_group_id == combination_group.c.id),
        )
        .join(
            contract,
            (contract.c.tenant_id == combination_group_member.c.tenant_id)
            & (contract.c.id == combination_group_member.c.contract_id),
        )
        .join(book, book.c.tenant_id == combination_group.c.tenant_id)
        .where(
            combination_group.c.tenant_id == tenant,
            combination_group_member.c.valid_to_known_at.is_(None),
            book.c.is_enabled.is_(True),
        )
        .distinct()
    ).all()
    keys = sorted((str(group), str(entity), str(code)) for group, entity, code in portions)
    manifest = _manifest(attempt_id, keys)
    if keys:
        uow.session.execute(
            insert(release_group_processing),
            [
                {
                    "tenant_id": tenant,
                    "id": new_id(),
                    "release_validation_id": validation_id,
                    "release_validation_attempt_id": attempt_id,
                    "combination_group_id": UUID(group),
                    "entity_id": UUID(entity),
                    "book_code": code,
                    "seq": 1,
                    "upgrade_state": "PENDING",
                    "created_at": uow.now,
                    "created_by": uow.principal.id,
                    "created_by_kind": uow.principal.kind.value,
                }
                for group, entity, code in keys
            ],
        )
    apply(
        uow.session,
        "release_validation",
        validation_id,
        to_status=None,
        expected_status=parent["status"],
        expected_row_version=parent["row_version"],
        set_values={
            "processing_seed": manifest,
            "row_version": parent["row_version"] + 1,
            "updated_at": uow.now,
            "updated_by": uow.principal.id,
            "updated_by_kind": uow.principal.kind.value,
        },
    )
    uow.audit(
        action="release_validation.seed_processing",
        object_type="release_validation",
        object_id=validation_id,
        after={"processing_seed": manifest},
    )
    return len(keys)


def _manifest(attempt_id: UUID, keys: list[tuple[str, str, str]]) -> dict[str, object]:
    return {
        "version": 1,
        "attempt_id": str(attempt_id),
        "count": len(keys),
        "sha256": hashlib.sha256(canonical_bytes(keys)).hexdigest(),
    }
