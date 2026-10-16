"""Persist a deterministic release-validation selection before child-job dispatch."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import insert, select

from erev_api.db import new_id
from erev_api.db.tables import (
    release_validation,
    release_validation_attempt,
    release_validation_group,
)
from erev_api.db.transitions import apply
from erev_api.problems import Problem
from erev_api.registry.resolve import setting
from erev_api.uow import UnitOfWork

from .release_validation import select_population
from .validation_population import read


@dataclass(frozen=True, slots=True)
class FrozenAttempt:
    id: UUID
    created: bool


def freeze(
    uow: UnitOfWork, *, validation_id: UUID, attempt_no: int, seed: int | None = None
) -> FrozenAttempt:
    """Save selection atomically in the caller's transaction; retries never redraw it.

    The replay seed is resolved for a new attempt unless supplied explicitly. A later
    attempt requires its predecessor to have been superseded explicitly. This function neither
    starts jobs nor changes validation/attempt status or enables a release.
    """
    if uow.principal.db_context.entity_scope != "*":
        raise Problem("forbidden", "Release validation requires the complete tenant population.")
    if (
        type(attempt_no) is not int
        or attempt_no < 1
        or (seed is not None and type(seed) is not int)
    ):
        raise Problem(
            "validation-failed", "An attempt number and integer replay seed are required."
        )
    if seed is not None and not -(2**63) <= seed < 2**63:
        raise Problem("validation-failed", "The replay seed must fit a signed 64-bit integer.")
    tenant_id = uow.principal.tenant_id
    validation = (
        uow.session.execute(
            select(release_validation)
            .where(
                release_validation.c.tenant_id == tenant_id,
                release_validation.c.id == validation_id,
            )
            .with_for_update(key_share=True)
        )
        .mappings()
        .one_or_none()
    )
    if validation is None:
        raise Problem("not-found")
    # Every creator takes the parent lock, so concurrent deliveries cannot both draw a sample.
    attempts = (
        uow.session.execute(
            select(release_validation_attempt)
            .where(
                release_validation_attempt.c.tenant_id == tenant_id,
                release_validation_attempt.c.release_validation_id == validation_id,
            )
            .order_by(release_validation_attempt.c.attempt_no)
        )
        .mappings()
        .all()
    )
    existing = next((row for row in attempts if row["attempt_no"] == attempt_no), None)
    if existing is not None:
        if seed is not None and existing["seed"] != seed:
            raise Problem("validation-failed", "The frozen attempt has a different replay seed.")
        return FrozenAttempt(existing["id"], False)
    if (
        validation["effective_level"] not in {"MINOR", "MAJOR"}
        or validation["status"] not in {"PENDING", "RUNNING", "INCOMPLETE"}
        or validation["enabled_at"] is not None
        or validation["accepted_attempt_id"] is not None
        or attempt_no != (attempts[-1]["attempt_no"] + 1 if attempts else 1)
        or any(row["status"] != "SUPERSEDED" for row in attempts)
    ):
        raise Problem(
            "invalid-transition", "Supersede the prior attempt before freezing a new one."
        )
    if seed is None:
        resolved = setting(uow.session, "platform.replay_seed", known_at=uow.now)
        if type(resolved) is not int or not -(2**63) <= resolved < 2**63:
            raise Problem("validation-failed", "The configured replay seed is invalid.")
        seed = resolved
    facts = read(uow)
    population = select_population(facts.groups, seed=seed, tenant_id=tenant_id)
    stamps = {
        "tenant_id": tenant_id,
        "created_at": uow.now,
        "created_by": uow.principal.id,
        "created_by_kind": uow.principal.kind.value,
        "updated_at": uow.now,
        "updated_by": uow.principal.id,
        "updated_by_kind": uow.principal.kind.value,
    }
    attempt_id = new_id()
    uow.session.execute(
        insert(release_validation_attempt).values(
            **stamps,
            id=attempt_id,
            release_validation_id=validation_id,
            attempt_no=attempt_no,
            seed=seed,
            population={
                **population.summary,
                "fingerprint_version": 1,
                "fingerprint": facts.fingerprint(),
            },
            required_entity_ids=list(facts.required_entity_ids),
            status="SELECTED",
        )
    )
    selections = [
        {
            **stamps,
            "id": new_id(),
            "release_validation_attempt_id": attempt_id,
            "combination_group_id": group.group_id,
            "source_computation_id": group.source_computation_id,
            "selection": group.selection,
            "strata": [list(pair) for pair in group.strata],
            "rank_sha256": group.rank_sha256,
            "orchestration_state": "PENDING",
        }
        for group in population.selected
    ]
    if selections:
        uow.session.execute(insert(release_validation_group), selections)
    uow.audit(
        action="release_validation_attempt.freeze",
        object_type="release_validation_attempt",
        object_id=attempt_id,
        after={"attempt_no": attempt_no, "seed": seed, "selected_groups": len(selections)},
    )
    return FrozenAttempt(attempt_id, True)


def start(uow: UnitOfWork, *, validation_id: UUID, attempt_id: UUID) -> bool:
    """Start a still-current frozen attempt; return False on a matching running retry.

    Population must also be revalidated at final acceptance: this start boundary does not
    prohibit subsequent business activity and cannot itself authorize release enablement.
    """
    if uow.principal.db_context.entity_scope != "*":
        raise Problem("forbidden", "Release validation requires the complete tenant population.")
    tenant_id = uow.principal.tenant_id
    parent = (
        uow.session.execute(
            select(release_validation)
            .where(
                release_validation.c.tenant_id == tenant_id,
                release_validation.c.id == validation_id,
            )
            .with_for_update(key_share=True)
        )
        .mappings()
        .one_or_none()
    )
    attempt = (
        uow.session.execute(
            select(release_validation_attempt)
            .where(
                release_validation_attempt.c.tenant_id == tenant_id,
                release_validation_attempt.c.id == attempt_id,
                release_validation_attempt.c.release_validation_id == validation_id,
            )
            .with_for_update(key_share=True)
        )
        .mappings()
        .one_or_none()
    )
    if parent is None or attempt is None:
        raise Problem("not-found")
    if (
        parent["effective_level"] not in {"MINOR", "MAJOR"}
        or parent["status"] not in {"PENDING", "RUNNING", "INCOMPLETE"}
        or parent["enabled_at"] is not None
        or parent["accepted_attempt_id"] is not None
        or attempt["status"] not in {"SELECTED", "RUNNING"}
    ):
        raise Problem("invalid-transition")
    if (
        attempt["population"].get("fingerprint_version") != 1
        or attempt["population"].get("fingerprint") != read(uow).fingerprint()
    ):
        raise Problem(
            "validation-failed",
            "The population changed; supersede this attempt and freeze a new one.",
        )
    if attempt["status"] == "RUNNING":
        if parent["status"] != "RUNNING":
            raise Problem("invalid-transition")
        return False
    for table, row in ((release_validation, parent), (release_validation_attempt, attempt)):
        if row["status"] == "RUNNING":
            continue
        apply(
            uow.session,
            table.name,
            row["id"],
            to_status="RUNNING",
            expected_status=row["status"],
            expected_row_version=row["row_version"],
            set_values={
                "row_version": row["row_version"] + 1,
                "updated_at": uow.now,
                "updated_by": uow.principal.id,
                "updated_by_kind": uow.principal.kind.value,
            },
        )
    uow.audit(
        action="release_validation_attempt.start",
        object_type="release_validation_attempt",
        object_id=attempt_id,
        before={"status": attempt["status"], "validation_status": parent["status"]},
        after={"status": "RUNNING", "validation_status": "RUNNING"},
    )
    return True
