"""Database witnesses for the evidence required by an error-correction reopen."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.tables import judgement_record
from erev_api.domain.close.reopen_judgements import reviewed_basis
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.problems import Problem
from fastapi import FastAPI
from sqlalchemy import insert, select
from sqlalchemy.exc import DBAPIError
from support.close_world import CloseWorld, close_world, contract_of, other_entity, system_session
from support.db import TestDatabase
from support.rows import judgement_record_values


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> CloseWorld:
    return close_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _record(world: CloseWorld, clock: FrozenClock, **extra: Any) -> UUID:
    with system_session(world) as session:
        entity_id = extra.pop("entity_id", world.entity_id)
        contract_id, _, _ = contract_of(session, world, entity_id)
        values = judgement_record_values(
            world.tenant_id,
            topic="ESTIMATE_VS_ERROR",
            subject_type="contract",
            subject_id=contract_id,
            contract_id=contract_id,
            status="REVIEWED",
            reviewer_id=world.maya.member.user_id,
            reviewed_at=clock.now(),
        )
        values.update(extra)
        session.execute(insert(judgement_record).values(**values))
    return UUID(str(values["id"]))


def _basis(world: CloseWorld, judgement_id: UUID | None, **extra: Any) -> dict[str, Any]:
    with system_session(world) as session:
        return reviewed_basis(
            session,
            tenant_id=extra.get("tenant_id", world.tenant_id),
            entity_id=world.entity_id,
            book_code="ASC606",
            judgement_id=judgement_id,
        )


@pytest.mark.parametrize("book", [None, "ASC606"])
def test_reviewed_reopen_basis_binds_the_record_and_independent_review(
    world: CloseWorld, clock: FrozenClock, book: str | None
) -> None:
    record = _record(world, clock, book_code=book)
    basis = _basis(world, record)
    assert basis["id"] == str(record)
    assert basis["reviewer_id"] == str(world.maya.member.user_id)
    assert basis["content"]["topic"] == "ESTIMATE_VS_ERROR"
    assert basis["content"]["rationale"] == "Probe judgement record."
    assert basis["reviewed_at"] == clock.now().isoformat()


@pytest.mark.parametrize("missing", [None, "unknown", "other_tenant", "other_entity"])
def test_missing_or_out_of_scope_record_has_the_same_refusal(
    world: CloseWorld, clock: FrozenClock, missing: str | None
) -> None:
    record = None
    tenant_id = world.tenant_id
    if missing == "unknown":
        record = new_id()
    elif missing == "other_tenant":
        record = _record(world, clock)
        tenant_id = new_id()
    elif missing == "other_entity":
        with system_session(world) as session:
            entity_id = other_entity(session, world)
        record = _record(world, clock, entity_id=entity_id)
    with pytest.raises(Problem) as error:
        _basis(world, record, tenant_id=tenant_id)
    assert error.value.slug == "validation-failed"
    assert error.value.errors[0].rule_id == "REOPEN_REVIEWED_JUDGEMENT"


@pytest.mark.parametrize("book", ["IFRS15", "LEGACY"])
def test_reviewed_record_for_another_book_is_refused(
    world: CloseWorld, clock: FrozenClock, book: str
) -> None:
    record = _record(world, clock, book_code=book)
    with pytest.raises(Problem):
        _basis(world, record)


def test_a_concurrent_review_is_retryable_and_does_not_abort_the_caller_session(
    world: CloseWorld, clock: FrozenClock
) -> None:
    record = _record(world, clock)
    with system_session(world) as writer:
        writer.execute(
            select(judgement_record.c.id).where(judgement_record.c.id == record).with_for_update()
        ).one()
        with system_session(world) as reader:
            with pytest.raises(Problem) as error:
                reviewed_basis(
                    reader,
                    tenant_id=world.tenant_id,
                    entity_id=world.entity_id,
                    book_code="ASC606",
                    judgement_id=record,
                )
            assert error.value.slug == "invalid-transition"
            assert reader.execute(select(judgement_record.c.id)).first() is not None
    assert _basis(world, record)["status"] == "REVIEWED"


@pytest.mark.parametrize("status", ["DRAFT", "SUBMITTED", "SUPERSEDED"])
def test_an_unreviewed_or_superseded_record_is_refused(
    world: CloseWorld, clock: FrozenClock, status: str
) -> None:
    record = _record(world, clock, status=status, reviewer_id=None, reviewed_at=None)
    with pytest.raises(Problem) as error:
        _basis(world, record)
    assert error.value.errors[0].rule_id == "REOPEN_REVIEWED_JUDGEMENT"


def test_a_reviewed_judgement_on_another_topic_is_not_reopen_evidence(
    world: CloseWorld, clock: FrozenClock
) -> None:
    record = _record(world, clock, topic="PRINCIPAL_AGENT")
    with pytest.raises(Problem):
        _basis(world, record)


def test_validated_evidence_stays_locked_until_the_reopen_transaction_ends(
    world: CloseWorld, clock: FrozenClock
) -> None:
    record = _record(world, clock)
    with system_session(world) as reader:
        reviewed_basis(
            reader,
            tenant_id=world.tenant_id,
            entity_id=world.entity_id,
            book_code="ASC606",
            judgement_id=record,
        )
        with system_session(world) as writer:
            with pytest.raises(DBAPIError) as error, writer.begin_nested():
                writer.execute(
                    select(judgement_record.c.id)
                    .where(judgement_record.c.id == record)
                    .with_for_update(nowait=True)
                ).one()
            assert getattr(error.value.orig, "sqlstate", None) == "55P03"
    with system_session(world) as writer:
        assert (
            writer.execute(
                select(judgement_record.c.id)
                .where(judgement_record.c.id == record)
                .with_for_update(nowait=True)
            ).scalar_one()
            == record
        )
