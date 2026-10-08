"""RPS-16 selection and frozen-source collection; not complete-pack or CTL-041 evidence.

Contract and lock rows are seeded fixtures; permission variants use real tenant UOWs.
Collector tests use the real snapshot producer and encrypted file store. They do not
establish an approved close or the complete evidence-pack generation/download workflow.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.tables import legal_entity, period_lock
from erev_api.domain.close import snapshots as close_snapshots
from erev_api.domain.reports import evidence_archive, evidence_close, locked
from erev_api.domain.reports.evidence_selection import resolve
from erev_api.enums import FilePurpose
from erev_api.files.store import LocalFileStore, store_file
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


def _freeze_for_pack(
    sources: Sources, *, fault: str | None = None, formula_cells: bool = False
) -> dict[str, Any]:
    """Real producer/store and seeded lock; adversarial cases alter explicit fixture inputs."""
    with sources.world.place.uow(sources.principal) as uow:
        scope = locked.lock_scope(uow.session, UUID(sources.close["period_lock_id"]))
        assert scope is not None
        datasets = list(
            close_snapshots.freeze_datasets(
                uow, scope.entity_id, scope.book_code, scope.period_id, uow.now
            )
        )
        if formula_cells or fault == "row-key":
            # Adversarial source cells, not an accounting calculation expectation.
            index = next(i for i, item in enumerate(datasets) if item.kind == "CONTRACT_BALANCES")
            content = (
                b"row_key,contract_external_id,contract_liability\n=ROW,=KEY,-100.00\n"
                if formula_cells
                else b"contract_external_id,contract_liability\nKEY,100.00\n"
            )
            stored = store_file(
                uow,
                purpose=FilePurpose.SNAPSHOT_DATASET,
                stream=BytesIO(content),
                original_filename=close_snapshots.dataset_filename("CONTRACT_BALANCES"),
                media_type=close_snapshots.MEDIA_TYPE,
            )
            datasets[index] = replace(
                datasets[index], file_id=stored["id"], file_sha256=stored["sha256"], row_count=1
            )
        if fault == "file-hash":
            datasets[0] = replace(datasets[0], file_sha256="0" * 64)
        if fault == "row-count":
            datasets[0] = replace(datasets[0], row_count=datasets[0].row_count + 1)
        manifest = close_snapshots.manifest_of(datasets)
        if fault == "missing-kind":
            datasets.pop()
        if fault == "manifest":
            manifest = "0" * 64
        original = (
            uow.session.execute(select(period_lock).where(period_lock.c.id == scope.lock_id))
            .mappings()
            .one()
        )
        identity = new_id()
        row = dict(original)
        row.update(
            id=identity,
            cutoff_known_at=uow.now,
            snapshot_manifest_sha256=manifest,
        )
        uow.session.execute(insert(period_lock).values(**row))
        close_snapshots.write_lock_snapshots(uow, identity, datasets)
        uow.commit()
    return {**sources.close, "period_lock_id": str(identity)}


def test_close_collector_uses_actual_frozen_sources_and_produces_verifiable_archive(
    sources: Sources,
) -> None:
    request = ADAPTER.validate_python(_freeze_for_pack(sources))
    with sources.world.place.uow(sources.principal) as uow:
        selection = resolve(uow, request)
        assert selection.lock is not None
        files = evidence_close.collect_locked(uow, selection)
        assert evidence_close.collect_locked(uow, selection) == files
        payloads = {file.path: file.content for file in files}
        sources_doc = json.loads(payloads["lock/snapshots.json"])
        assert sources_doc["period_lock_id"] == str(selection.lock.lock_id)
        assert len(sources_doc["snapshots"]) == 12
        assert len(files) == 14
        for snapshot in sources_doc["snapshots"]:
            frozen = locked.locked_dataset(
                uow, report_code=snapshot["report_code"], lock_id=selection.lock.lock_id
            )
            assert snapshot["file_id"] == str(frozen.file_id)
            assert snapshot["file_sha256"] == hashlib.sha256(frozen.content).hexdigest()
            assert (
                snapshot["export_sha256"] == hashlib.sha256(payloads[snapshot["path"]]).hexdigest()
            )
        archive = evidence_archive.build(files)
        assert (
            evidence_archive.verify(
                archive.content, expected_manifest_sha256=archive.manifest_sha256
            )
            == archive.manifest_document()
        )


@pytest.mark.parametrize("fault", ["missing-kind", "manifest", "file-hash", "row-count", "row-key"])
def test_close_collector_refuses_incomplete_or_inconsistent_frozen_sources(
    sources: Sources, fault: str
) -> None:
    request = ADAPTER.validate_python(_freeze_for_pack(sources, fault=fault))
    with sources.world.place.uow(sources.principal) as uow:
        selection = resolve(uow, request)
        with pytest.raises(Problem) as error:
            evidence_close.collect_locked(uow, selection)
        assert error.value.slug == "validation-failed"


def test_close_collector_guards_spreadsheet_text_and_keeps_both_hashes(sources: Sources) -> None:
    request = ADAPTER.validate_python(_freeze_for_pack(sources, formula_cells=True))
    with sources.world.place.uow(sources.principal) as uow:
        files = evidence_close.collect_locked(uow, resolve(uow, request))
    payloads = {file.path: file.content for file in files}
    delivered = payloads["reports/contract_balances.csv"]
    assert delivered == b"row_key,contract_external_id,contract_liability\n'=ROW,'=KEY,-100.00\n"
    identities = json.loads(payloads["lock/snapshots.json"])["snapshots"]
    source = next(row for row in identities if row["snapshot_kind"] == "CONTRACT_BALANCES")
    assert (
        source["file_sha256"]
        == hashlib.sha256(
            b"row_key,contract_external_id,contract_liability\n=ROW,=KEY,-100.00\n"
        ).hexdigest()
    )
    assert source["export_sha256"] == hashlib.sha256(delivered).hexdigest()
    assert source["file_sha256"] != source["export_sha256"]


def test_close_collector_rechecks_authorization_and_refuses_altered_selection(
    sources: Sources,
) -> None:
    request = ADAPTER.validate_python(_freeze_for_pack(sources))
    with sources.world.place.uow(sources.principal) as uow:
        selected = resolve(uow, request)
        assert selected.lock_known_at is not None
        for altered in (
            replace(selected, entity_ids=(sources.world.entity_id,)),
            replace(selected, lock_known_at=selected.lock_known_at + timedelta(seconds=1)),
            replace(selected, tenant_id=uuid4()),
            replace(selected, contract_ids=(sources.first_contract,)),
        ):
            with pytest.raises(Problem) as error:
                evidence_close.collect_locked(uow, altered)
            assert error.value.slug == "validation-failed"
    revoked = replace(
        sources.principal,
        permission_scopes={"report.run": "*", "audit.read": frozenset({sources.world.entity_id})},
    )
    with sources.world.place.uow(revoked) as uow, pytest.raises(Problem) as error:
        evidence_close.collect_locked(uow, selected)
    assert error.value.slug == "not-found"
