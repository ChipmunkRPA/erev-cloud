"""RPS-16 identity selection against PostgreSQL/RLS; not complete-pack or CTL-041 evidence.

Contract and lock rows are seeded fixtures. No calculation, close certification or file
generation is claimed. Permission variants are explicit Principals inside real tenant UOWs.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import legal_entity, period_lock
from erev_api.domain.reports.evidence_selection import resolve
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import EvidencePackCreateIn
from fastapi import FastAPI
from pydantic import TypeAdapter
from sqlalchemy import insert, select
from support.close_world import CloseWorld, close_world, contract_of, other_entity, system_session
from support.db import TestDatabase
from support.rows import insert_close_parts, period_lock_values

ADAPTER = TypeAdapter(EvidencePackCreateIn)
FROZEN_AT = datetime(2026, 9, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Sources:
    world: CloseWorld
    second_entity: UUID
    first_contract: UUID
    second_contract: UUID
    close: dict[str, Any]
    non_locks: tuple[UUID, ...]

    @property
    def principal(self) -> Principal:
        return replace(
            self.world.place.principal,
            permissions=frozenset({"report.run", "audit.read"}),
            permission_scopes={"report.run": "*", "audit.read": "*"},
        )


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def sources(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> Sources:
    world = close_world(app, keyring, clock, LocalFileStore(app_settings.file_root))
    with system_session(world) as session:
        second = other_entity(session, world)
        first_contract, _, _ = contract_of(session, world, external_id="SAMPLE-US")
        second_contract, _, _ = contract_of(session, world, second, external_id="SAMPLE-UK")
        parts = insert_close_parts(session, world.tenant_id)
        locks = []
        for kind in ("LOCK", "REOPEN", "PERMANENT_LOCK"):
            row = period_lock_values(
                world.tenant_id,
                parts=parts,
                kind=kind,
                created_at=FROZEN_AT,
                reason_code="ERROR_CORRECTION" if kind == "REOPEN" else None,
            )
            session.execute(insert(period_lock).values(**row))
            locks.append(row["id"])
        entity_code = session.execute(
            select(legal_entity.c.code).where(legal_entity.c.id == parts.entity_id)
        ).scalar_one()
        session.commit()
    return Sources(
        world,
        second,
        first_contract,
        second_contract,
        {
            "kind": "CLOSE",
            "entity_code": entity_code,
            "book": "ASC606",
            "period_key": "FY2026-P01",
            "period_lock_id": str(locks[0]),
        },
        tuple(locks[1:]),
    )


def test_close_binds_exact_historical_lock_and_its_cutoff(sources: Sources) -> None:
    with sources.world.place.uow(sources.principal) as uow:
        result = resolve(uow, ADAPTER.validate_python(sources.close))
        assert result.tenant_id == sources.world.tenant_id
        assert result.known_at == uow.now
        assert result.lock_known_at == FROZEN_AT != result.known_at
        assert result.lock is not None
        assert str(result.lock.lock_id) == sources.close["period_lock_id"]
        assert result.entity_ids == (result.lock.entity_id,)
        assert result.contract_ids == ()


def test_close_rejects_each_mismatched_selector_and_nonfreeze_records(sources: Sources) -> None:
    with sources.world.place.uow(sources.principal) as uow:
        for field, value in (("entity_code", "OTHER"), ("book", "IFRS15"), ("period_key", "OTHER")):
            with pytest.raises(Problem) as error:
                resolve(uow, ADAPTER.validate_python({**sources.close, field: value}))
            assert error.value.slug == "validation-failed"
            assert [item.field for item in error.value.errors] == [field]
        for lock_id in sources.non_locks:
            with pytest.raises(Problem) as error:
                resolve(
                    uow, ADAPTER.validate_python({**sources.close, "period_lock_id": str(lock_id)})
                )
            assert error.value.slug == "validation-failed"
            assert error.value.errors[0].field == "period_lock_id"


def test_sample_keeps_request_order_and_all_entities(sources: Sources) -> None:
    request = ADAPTER.validate_python(
        {
            "kind": "CONTRACT_SAMPLE",
            "contract_external_ids": ["SAMPLE-UK", "SAMPLE-US"],
            "as_of": "2026-09-30",
        }
    )
    with sources.world.place.uow(sources.principal) as uow:
        result = resolve(uow, request)
    assert result.contract_ids == (sources.second_contract, sources.first_contract)
    assert result.entity_ids == tuple(sorted((sources.second_entity, sources.world.entity_id)))
    assert result.lock is None and result.lock_known_at is None


@pytest.mark.parametrize("permission", ["report.run", "audit.read"])
def test_scope_intersection_refuses_whole_sample_without_naming_hidden_rows(
    sources: Sources, permission: str
) -> None:
    principal = replace(
        sources.principal,
        permission_scopes={
            **sources.principal.permission_scopes,
            permission: frozenset({sources.world.entity_id}),
        },
    )
    with sources.world.place.uow(principal) as uow:
        for external in ("SAMPLE-UK", "DOES-NOT-EXIST"):
            with pytest.raises(Problem) as error:
                resolve(
                    uow,
                    ADAPTER.validate_python(
                        {
                            "kind": "CONTRACT_SAMPLE",
                            "contract_external_ids": ["SAMPLE-US", external],
                            "as_of": "2026-09-30",
                        }
                    ),
                )
            assert error.value.slug == "not-found"
            assert not error.value.errors


def test_hidden_and_absent_locks_do_not_disclose_scope_or_kind(sources: Sources) -> None:
    principal = replace(
        sources.principal,
        permission_scopes={"report.run": frozenset({sources.world.entity_id}), "audit.read": "*"},
    )
    with sources.world.place.uow(principal) as uow:
        for lock_id in (sources.close["period_lock_id"], *sources.non_locks, uuid4()):
            with pytest.raises(Problem) as error:
                resolve(
                    uow,
                    ADAPTER.validate_python(
                        {**sources.close, "period_lock_id": str(lock_id), "entity_code": "WRONG"}
                    ),
                )
            assert error.value.slug == "not-found"
            assert not error.value.errors


def test_workspace_packs_bind_only_intersection_and_rls_does_not_expand(sources: Sources) -> None:
    for kind in ("CHANGE", "ACCESS"):
        request = ADAPTER.validate_python(
            {"kind": kind, "from_date": "2026-09-01", "to_date": "2026-09-30"}
            if kind == "CHANGE"
            else {"kind": kind, "as_of": "2026-09-30"}
        )
        for via_rls in (False, True):
            principal = replace(
                sources.principal,
                entity_scope=(sources.world.entity_id,) if via_rls else "*",
                permission_scopes={
                    "report.run": "*",
                    "audit.read": "*" if via_rls else frozenset({sources.world.entity_id}),
                },
            )
            with sources.world.place.uow(principal) as uow:
                result = resolve(uow, request)
            assert result.entity_ids == (sources.world.entity_id,)


def test_missing_permission_or_scope_and_system_do_not_gain_generation_access(
    sources: Sources,
) -> None:
    variants = [system_principal(sources.world.tenant_id)]
    for permission in ("report.run", "audit.read"):
        variants.extend(
            (
                replace(
                    sources.principal, permissions=sources.principal.permissions - {permission}
                ),
                replace(
                    sources.principal,
                    permission_scopes={
                        k: v
                        for k, v in sources.principal.permission_scopes.items()
                        if k != permission
                    },
                ),
                replace(
                    sources.principal,
                    permission_scopes={
                        **sources.principal.permission_scopes,
                        permission: frozenset(),
                    },
                ),
            )
        )
    request = ADAPTER.validate_python({"kind": "ACCESS", "as_of": "2026-09-30"})
    for principal in variants:
        with sources.world.place.uow(principal) as uow, pytest.raises(Problem) as error:
            resolve(uow, request)
        assert error.value.slug == "forbidden"


def test_other_tenant_sources_stay_hidden_even_when_business_keys_match(
    sources: Sources, app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    other = close_world(app, keyring, clock, LocalFileStore(app_settings.file_root))
    principal = replace(
        other.place.principal,
        permissions=sources.principal.permissions,
        permission_scopes=sources.principal.permission_scopes,
    )
    with other.place.uow(principal) as uow, pytest.raises(Problem) as error:
        resolve(uow, ADAPTER.validate_python(sources.close))
    assert error.value.slug == "not-found"
    with system_session(other) as session:
        own_contract, _, _ = contract_of(session, other, external_id="SAMPLE-US")
        session.commit()
    with other.place.uow(principal) as uow:
        result = resolve(
            uow,
            ADAPTER.validate_python(
                {
                    "kind": "CONTRACT_SAMPLE",
                    "contract_external_ids": ["SAMPLE-US"],
                    "as_of": "2026-09-30",
                }
            ),
        )
        assert result.contract_ids == (own_contract,)
        assert own_contract != sources.first_contract
        assert result.entity_ids == (other.entity_id,)
        with pytest.raises(Problem) as error:
            resolve(
                uow,
                ADAPTER.validate_python(
                    {
                        "kind": "CONTRACT_SAMPLE",
                        "contract_external_ids": ["SAMPLE-US", "SAMPLE-UK"],
                        "as_of": "2026-09-30",
                    }
                ),
            )
        assert error.value.slug == "not-found"
