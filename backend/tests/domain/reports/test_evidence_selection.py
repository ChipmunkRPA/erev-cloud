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
from decimal import Decimal
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.audit import verify as audit_verify
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id, transitions
from erev_api.db.tables import (
    audit_chain_head,
    audit_chain_verification,
    evidence_pack,
    job,
    journal_run,
    legal_entity,
    lock_snapshot,
    period,
    period_lock,
    reconciliation,
    reconciliation_item,
    report_run,
)
from erev_api.domain.close import certification, relock_diff
from erev_api.domain.close import snapshots as close_snapshots
from erev_api.domain.reports import (
    evidence_archive,
    evidence_audit,
    evidence_close,
    evidence_journals,
    evidence_reconciliations,
    evidence_relock,
    evidence_report_plan,
    evidence_reports,
    evidence_sources,
    locked,
)
from erev_api.domain.reports.evidence_selection import resolve
from erev_api.enums import FilePurpose
from erev_api.files.store import LocalFileStore, open_file, store_file
from erev_api.main import create_app
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import ClosePackCreateIn, EvidencePackCreateIn
from erev_engine.canonical import canonical_bytes
from fastapi import FastAPI
from pydantic import TypeAdapter
from sqlalchemy import func, insert, select
from support import reconciliations as recon_api
from support.close_world import (
    CloseWorld,
    acknowledged_run_for,
    actor_with_role,
    close_world,
    contract_of,
    other_entity,
    run_journal_job,
    system_session,
)
from support.db import TestDatabase
from support.principals import enrolled
from support.rows import (
    evidence_pack_values,
    insert_close_parts,
    journal_run_values,
    period_lock_values,
    reconciliation_item_values,
    reconciliation_values,
)

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
    sources: Sources,
    *,
    fault: str | None = None,
    formula_cells: bool = False,
    certification_rows: list[dict[str, Any]] | None = None,
    audit_head: tuple[int, str | None] | None = None,
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
            created_at=uow.now,
            cutoff_known_at=uow.now,
            snapshot_manifest_sha256=manifest,
        )
        if certification_rows is not None:
            row["certification"] = certification_rows
        if audit_head is not None:
            row["audit_head_chain_seq"], row["audit_head_hmac"] = audit_head
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


def _relock_for_pack(sources: Sources, *, fault: str | None = None) -> tuple[dict[str, Any], UUID]:
    """Seed a LOCK→REOPEN→LOCK history with the production stored diff over real frozen files."""
    first = _freeze_for_pack(sources)
    first_id = UUID(first["period_lock_id"])
    with sources.world.place.uow(sources.principal) as uow:
        original = dict(
            uow.session.execute(select(period_lock).where(period_lock.c.id == first_id))
            .mappings()
            .one()
        )
        rows = (
            uow.session.execute(
                select(lock_snapshot).where(lock_snapshot.c.period_lock_id == first_id)
            )
            .mappings()
            .all()
        )
        datasets = [
            close_snapshots.DatasetFile(
                str(row["snapshot_kind"]),
                row["file_id"],
                row["file_sha256"],
                row["row_count"],
                row["control_totals"],
            )
            for row in rows
        ]
        reopened_id, current_id = new_id(), new_id()
        reopened = {
            **original,
            "id": reopened_id,
            "kind": "REOPEN",
            "cutoff_known_at": None,
            "reason_code": "ERROR_CORRECTION",
            "previous_lock_id": first_id,
        }
        if fault == "cycle":
            reopened["previous_lock_id"] = reopened_id
        if fault == "missing-history":
            reopened["previous_lock_id"] = None
        if fault == "other-period":
            parts = insert_close_parts(uow.session, sources.world.tenant_id)
            reopened = period_lock_values(
                sources.world.tenant_id,
                parts=parts,
                kind="REOPEN",
                reason_code="ERROR_CORRECTION",
                previous_lock_id=first_id,
            )
            reopened_id = reopened["id"]
        uow.session.execute(insert(period_lock).values(**reopened))
        certification = [{"gate_check_code": "JE_COMPLETE", "status": "PASSED"}]
        report = relock_diff.report(
            uow,
            previous_lock_id=first_id,
            lock_id=current_id,
            manifest_sha256=original["snapshot_manifest_sha256"],
            certification=certification,
            datasets=datasets,
        )
        if fault == "wrong-lock":
            report["lock_id"] = str(uuid4())
        if fault == "wrong-manifest":
            report["manifest"]["previous"] = "0" * 64
        if fault == "missing-kind":
            report["kinds"].pop(next(iter(report["kinds"])))
        if fault == "wrong-difference":
            report["certification"]["changed"] = []
        file_id = relock_diff.store_report(uow, report, period_key=first["period_key"])
        if fault == "wrong-purpose":
            file_id = store_file(
                uow,
                purpose=FilePurpose.AUDIT_DIGEST,
                stream=BytesIO(relock_diff.encode(report)),
                original_filename="comparison.json",
                media_type=relock_diff.MEDIA_TYPE,
            )["id"]
        current = {
            **original,
            "id": current_id,
            "previous_lock_id": reopened_id,
            "certification": certification,
            "diff_report_file_id": file_id,
        }
        if fault == "missing-file":
            current["diff_report_file_id"] = None
        if fault == "no-reopen":
            current["previous_lock_id"] = first_id
        if fault == "unexpected-first-file":
            current["previous_lock_id"] = None
        uow.session.execute(insert(period_lock).values(**current))
        close_snapshots.write_lock_snapshots(uow, current_id, datasets)
        uow.commit()
    return {**first, "period_lock_id": str(current_id)}, first_id


def test_relock_collector_includes_original_diff_and_both_lock_identities(sources: Sources) -> None:
    body, first_id = _relock_for_pack(sources)
    with sources.world.place.uow(sources.principal) as uow:
        selection = resolve(uow, ADAPTER.validate_python(body))
        files = evidence_relock.collect(uow, selection)
        assert evidence_relock.collect(uow, selection) == files
        payloads = {file.path: json.loads(file.content) for file in files}
        diff = payloads["relock/stored_comparison.json"]
        assert diff["previous_lock_id"] == str(first_id)
        assert diff["lock_id"] == body["period_lock_id"]
        assert diff["certification"]["changed"] == [
            {"gate_check_code": "JE_COMPLETE", "previous_status": None, "current_status": "PASSED"}
        ]
        assert len(diff["kinds"]) == 12
        refs = payloads["relock/sources.json"]
        assert refs["previous_lock_id"] == str(first_id)
        assert refs["period_lock_id"] == body["period_lock_id"]
        assert refs["diff_report_sha256"] == hashlib.sha256(files[0].content).hexdigest()
        section = evidence_archive.build((*evidence_close.collect_locked(uow, selection), *files))
        evidence_archive.verify(section.content, expected_manifest_sha256=section.manifest_sha256)


@pytest.mark.parametrize(
    "fault",
    [
        "wrong-lock",
        "wrong-manifest",
        "missing-kind",
        "wrong-difference",
        "missing-file",
        "cycle",
        "missing-history",
        "other-period",
        "no-reopen",
        "unexpected-first-file",
        "wrong-purpose",
    ],
)
def test_relock_collector_refuses_wrong_history_or_saved_comparison(
    sources: Sources, fault: str
) -> None:
    body, _ = _relock_for_pack(sources, fault=fault)
    with sources.world.place.uow(sources.principal) as uow:
        selection = resolve(uow, ADAPTER.validate_python(body))
        with pytest.raises(Problem) as error:
            evidence_relock.collect(uow, selection)
        assert error.value.slug == "validation-failed"


def test_first_close_has_no_relock_payload(sources: Sources) -> None:
    request = ADAPTER.validate_python(_freeze_for_pack(sources))
    with sources.world.place.uow(sources.principal) as uow:
        assert evidence_relock.collect(uow, resolve(uow, request)) == ()


@pytest.mark.parametrize("reference_in", ["item", "not_stated_total"])
def test_reconciliation_pack_keeps_signed_lock_history_after_new_generation_and_reopen(
    sources: Sources,
    clock: FrozenClock,
    reference_in: str,
) -> None:
    body = _freeze_for_pack(sources)
    reader = replace(
        sources.principal,
        permissions=sources.principal.permissions | {"contract.read"},
        permission_scopes={**sources.principal.permission_scopes, "contract.read": "*"},
    )
    with sources.world.place.uow(reader) as uow:
        selected = resolve(uow, ADAPTER.validate_python(body))
        assert selected.lock is not None
        row = reconciliation_values(
            sources.world.tenant_id,
            entity_id=selected.lock.entity_id,
            period_id=selected.lock.period_id,
            kind="BILLING_TO_SUBLEDGER",
            as_of_known_at=uow.now,
            totals=[]
            if reference_in == "item"
            else [
                {
                    "currency": "USD",
                    "account_role": "CONTRACT_LIABILITY",
                    "account_codes": ["2100"],
                    "subledger_amount": None,
                    "source_amount": None,
                    "difference": None,
                    "not_stated": {
                        "reason": "Fixture contract reference",
                        "contracts": [
                            {"id": str(sources.first_contract), "external_id": "SAMPLE-US"}
                        ],
                    },
                }
            ],
        )
        uow.session.execute(insert(reconciliation).values(**row))
        # A cross-entity reference exercises the supported schema's confidentiality rule;
        # it is a seeded statement, not an engine-created cross-entity accounting balance.
        if reference_in == "item":
            item = reconciliation_item_values(
                sources.world.tenant_id,
                reconciliation_id=row["id"],
                contract_id=sources.first_contract,
                subledger_amount=Decimal(0),
                source_amount=Decimal(0),
                difference=Decimal(0),
            )
            uow.session.execute(insert(reconciliation_item).values(**item))
        uow.commit()
    preparer = enrolled(sources.world.app, clock, sources.world.maya.member)
    reviewer = actor_with_role(
        sources.world.app, clock, sources.world.tenant_id, "revenue_reviewer", name="packreviewer"
    )
    prepared = recon_api.prepare(sources.world.app, preparer, str(row["id"]))
    assert prepared.status_code == 200, prepared.text
    reviewed = recon_api.sign(sources.world.app, reviewer, str(row["id"]))
    assert reviewed.status_code == 200, reviewed.text
    # Seed only the lock-certification transition; the two signatures above are real API commands.
    with sources.world.place.uow(reader) as uow:
        transitions.apply(
            uow.session,
            "reconciliation",
            row["id"],
            to_status="CERTIFIED",
            expected_status="REVIEWED",
            set_values={"period_lock_id": selected.lock.lock_id, "certified_at": uow.now},
        )
        uow.commit()
    with sources.world.place.uow(reader) as uow:
        before = evidence_reconciliations.collect(uow, selected)
    payload = json.loads(before[0].content)
    assert payload["reconciliation_id"] == str(row["id"])
    assert payload["certification_basis"]["kind"] == "SIGNOFFS"
    assert {s["id"] for s in payload["certification_basis"]["signoffs"]} == {
        s["id"] for s in reviewed.json()["signoffs"]
    }
    assert (
        hashlib.sha256(
            # Re-encode the exported statement with the same published canonical representation.
            canonical_bytes(payload["statement"])
        ).hexdigest()
        == payload["certification_basis"]["snapshot_sha256"]
    )
    with sources.world.place.uow(reader) as uow:
        transitions.apply(
            uow.session,
            "reconciliation",
            row["id"],
            to_status="REOPENED",
            expected_status="CERTIFIED",
            set_values={},
        )
        newer = reconciliation_values(
            sources.world.tenant_id,
            entity_id=selected.lock.entity_id,
            period_id=selected.lock.period_id,
            kind="BILLING_TO_SUBLEDGER",
            as_of_known_at=uow.now + timedelta(seconds=1),
            totals=[{"different": "new generation"}],
        )
        uow.session.execute(insert(reconciliation).values(**newer))
        uow.commit()
    with sources.world.place.uow(reader) as uow:
        assert evidence_reconciliations.collect(uow, selected) == before
    denied = replace(
        reader,
        permission_scopes={
            **reader.permission_scopes,
            "contract.read": frozenset({sources.world.entity_id}),
        },
    )
    with sources.world.place.uow(denied) as uow, pytest.raises(Problem) as error:
        evidence_reconciliations.collect(uow, selected)
    assert error.value.slug == "not-found"
    # Parent access is insufficient when the signed statement names a hidden contract.
    referenced_denied = replace(
        reader,
        permission_scopes={
            **reader.permission_scopes,
            "contract.read": frozenset({selected.lock.entity_id}),
        },
    )
    with sources.world.place.uow(referenced_denied) as uow, pytest.raises(Problem) as error:
        evidence_reconciliations.collect(uow, selected)
    assert error.value.slug == "not-found"


def test_journal_register_ties_to_frozen_rows_and_ignores_later_runs(
    sources: Sources,
    clock: FrozenClock,
) -> None:
    """Seeded journal/certification, real frozen producer/store and tenant-scoped collector."""
    with system_session(sources.world) as session:
        scope = locked.lock_scope(session, UUID(sources.close["period_lock_id"]))
        assert scope is not None
        rows = acknowledged_run_for(
            session,
            tenant_id=sources.world.tenant_id,
            entity_id=scope.entity_id,
            period_id=scope.period_id,
            now=clock.now(),
        )
        clock.set(
            session.execute(select(func.clock_timestamp())).scalar_one() + timedelta(seconds=1)
        )
        session.commit()
    saved = [
        {
            "gate_check_code": code,
            "status": "PASSED",
            "count": 0,
            "evaluated_at": clock.now().isoformat(),
        }
        for code in certification.CANONICAL_GATES
    ]
    request = ADAPTER.validate_python(_freeze_for_pack(sources, certification_rows=saved))
    reader = replace(
        sources.principal,
        permissions=sources.principal.permissions | {"contract.read"},
        permission_scopes={**sources.principal.permission_scopes, "contract.read": "*"},
    )
    with sources.world.place.uow(reader) as uow:
        selection = resolve(uow, request)
        result = evidence_journals.collect(uow, selection)
        payload = json.loads(result[0].content)
        assert len(payload["batches"]) == 1
        batch = payload["batches"][0]
        assert batch["id"] == str(rows.batch["id"])
        assert batch["frozen_line_count"] == len(rows.lines) > 0
        assert batch["balanced"] is True
        assert Decimal(batch["total_debit_txn"]) == rows.batch["total_debit_txn"]
        assert payload["runs"][0]["state_at_cutoff"] == "acknowledged"
        assert {item["gate_check_code"] for item in payload["certification"]} == {
            "JE_BALANCED",
            "JE_COMPLETE",
        }
    with system_session(sources.world) as session:
        later = journal_run_values(
            sources.world.tenant_id,
            parts=rows.parts,
            created_at=clock.now() + timedelta(days=1),
            cutoff_known_at=clock.now() + timedelta(days=1),
        )
        session.execute(insert(journal_run).values(**later))
        session.commit()
    with sources.world.place.uow(reader) as uow:
        assert evidence_journals.collect(uow, selection) == result
    for denied, expected_slug in (
        (sources.principal, "forbidden"),
        (
            replace(
                reader,
                permission_scopes={
                    **reader.permission_scopes,
                    "contract.read": frozenset(),
                },
            ),
            "not-found",
        ),
    ):
        with sources.world.place.uow(denied) as uow, pytest.raises(Problem) as error:
            evidence_journals.collect(uow, selection)
        assert error.value.slug == expected_slug


@pytest.mark.parametrize("fault", [None, "anchor", "truncated", "content", "purpose"])
def test_audit_digest_uses_recorded_verification_and_real_chain(
    sources: Sources,
    fault: str | None,
) -> None:
    """Real audit HMACs and verification files; the close/snapshots are explicitly seeded."""
    with sources.world.place.uow(sources.principal) as uow:
        head = uow.session.execute(
            select(
                audit_chain_head.c.last_chain_seq,
                audit_chain_head.c.last_hmac,
            )
        ).one()
        assert head.last_chain_seq > 0
    request = ADAPTER.validate_python(
        _freeze_for_pack(
            sources,
            audit_head=(
                head.last_chain_seq,
                "0" * 64 if fault == "anchor" else head.last_hmac,
            ),
        )
    )
    with sources.world.place.uow() as uow:
        verification = dict(
            audit_verify.record_tenant_verification(
                uow,
                trigger="ON_DEMAND",
                job_id=None,
            )
        )
        assert verification["result"] == "PASS"
        uow.commit()
    if fault in {"truncated", "content", "purpose"}:
        # Explicit invalid fixture: file checks alone must not bless a wrong verification.
        with sources.world.place.uow() as uow:
            _, stream = open_file(
                uow.session, verification["digest_file_id"], files=uow.files, keyring=uow.keyring
            )
            with stream:
                document = json.loads(stream.read())
            verification["id"] = new_id()
            if fault == "truncated":
                verification["to_chain_seq"] += 1000
                verification["events_checked"] += 1000
                document["last_chain_seq"] = verification["to_chain_seq"]
                document["events_checked"] = verification["events_checked"]
            elif fault == "content":
                document["tenant_id"] = str(new_id())
            stored = store_file(
                uow,
                purpose=FilePurpose.REPORT_OUTPUT
                if fault == "purpose"
                else FilePurpose.AUDIT_DIGEST,
                stream=BytesIO((json.dumps(document, indent=2, sort_keys=True) + "\n").encode()),
                original_filename="chain_digest.json",
                media_type="application/json",
            )
            verification["digest_file_id"] = stored["id"]
            uow.session.execute(insert(audit_chain_verification).values(**verification))
            uow.commit()
    with sources.world.place.uow(sources.principal) as uow:
        selection = resolve(uow, request)
        if fault is not None:
            message = {
                "anchor": "does not bind",
                "truncated": "no longer verifies",
                "content": "inconsistent",
                "purpose": "file failed verification",
            }[fault]
            with pytest.raises(Problem, match=message):
                evidence_audit.collect(uow, selection, verification_id=verification["id"])
            return
        packed = evidence_audit.collect(uow, selection, verification_id=verification["id"])
        digest = json.loads(packed[0].content)
        metadata = json.loads(packed[1].content)
        assert digest["last_chain_seq"] == verification["to_chain_seq"] >= head.last_chain_seq
        assert metadata["verification_id"] == str(verification["id"])
        assert metadata["audit_head_hmac"] == head.last_hmac
        with pytest.raises(Problem) as missing:
            evidence_audit.collect(uow, selection, verification_id=new_id())
        assert missing.value.slug == "not-found"
    # Verification appends its own audit facts. A second run extends the chain but must
    # not replace the ID already bound to a pack's sources or change its delivered bytes.
    with sources.world.place.uow() as uow:
        later = audit_verify.record_tenant_verification(uow, trigger="ON_DEMAND", job_id=None)
        assert later["to_chain_seq"] > verification["to_chain_seq"]
        uow.commit()
    with sources.world.place.uow(sources.principal) as uow:
        assert evidence_audit.collect(uow, selection, verification_id=verification["id"]) == packed
    denied = replace(sources.principal, permissions=frozenset({"report.run"}))
    with sources.world.place.uow(denied) as uow, pytest.raises(Problem) as error:
        evidence_audit.collect(uow, selection, verification_id=verification["id"])
    assert error.value.slug == "forbidden"


def test_close_supporting_report_plan_queues_normalized_sources_and_collects_jobs(
    sources: Sources,
    clock: FrozenClock,
) -> None:
    """Seeded January lock, actual framework queue/worker and all five original outputs."""
    with sources.world.place.uow() as uow:
        clock.set(
            uow.session.execute(select(func.clock_timestamp())).scalar_one() + timedelta(seconds=1)
        )
    request = ADAPTER.validate_python(_freeze_for_pack(sources))
    permissions = frozenset({"report.run", "report.export", "audit.read", "contract.read"})
    reader = replace(
        sources.principal,
        permissions=permissions,
        permission_scopes={permission: "*" for permission in permissions},
    )
    with sources.world.place.uow(reader) as uow:
        selection = resolve(uow, request)
        planned = evidence_report_plan.plan(uow, selection)
        by_code = {body.report_code: body.parameters for body in planned}
        assert by_code["ssp_change_log"]["from_date"] == "2026-01-01"
        assert by_code["config_change_register"]["to_date"] == "2026-01-31"
        assert by_code["user_access_listing"]["as_of"] == "2026-01-31T23:59:59.999999+00:00"
        assert by_code["late_entry_report"]["period_key"] == "FY2026-P01"
        queued = evidence_report_plan.queue(uow, selection)
        assert {item.source.report_code for item in queued} == set(evidence_reports.PATHS)
        assert all(item.source.known_at == selection.lock_known_at for item in queued)
        assert all(item.source.entity_ids == selection.entity_ids for item in queued)
        uow.commit()
    for item in queued:
        finished = run_journal_job(sources.world, item.job_id, attempts=1)
        assert finished["state"] == "SUCCEEDED", finished
    with sources.world.place.uow(reader) as uow:
        outputs = [file for item in queued for file in evidence_reports.collect(uow, item.source)]
        assert len(outputs) == 15
        assert len({file.path for file in outputs}) == 15


def test_supporting_plan_refuses_unverifiable_historical_period_dates(
    sources: Sources,
    clock: FrozenClock,
) -> None:
    with sources.world.place.uow() as uow:
        scope = locked.lock_scope(uow.session, UUID(sources.close["period_lock_id"]))
        assert scope is not None
        changed_at = uow.session.execute(
            select(period.c.updated_at).where(
                period.c.id == scope.period_id,
            )
        ).scalar_one()
    clock.set(changed_at - timedelta(seconds=1))
    request = ADAPTER.validate_python(_freeze_for_pack(sources))
    with sources.world.place.uow(sources.principal) as uow:
        selection = resolve(uow, request)
        with pytest.raises(Problem, match="historical dates"):
            evidence_report_plan.plan(uow, selection)


def test_supporting_queue_requires_export_and_leaves_no_report_rows(
    sources: Sources,
    clock: FrozenClock,
) -> None:
    with sources.world.place.uow() as uow:
        clock.set(
            uow.session.execute(select(func.clock_timestamp())).scalar_one() + timedelta(seconds=1)
        )
        before = uow.session.execute(select(func.count()).select_from(report_run)).scalar_one()
    request = ADAPTER.validate_python(_freeze_for_pack(sources))
    with sources.world.place.uow(sources.principal) as uow:
        selection = resolve(uow, request)
        with pytest.raises(Problem) as error:
            evidence_report_plan.queue(uow, selection)
        assert error.value.slug == "forbidden"
    with sources.world.place.uow() as uow:
        assert (
            uow.session.execute(select(func.count()).select_from(report_run)).scalar_one() == before
        )


def test_close_source_binding_round_trips_without_reselecting_or_requeuing(
    sources: Sources,
    clock: FrozenClock,
) -> None:
    with sources.world.place.uow() as uow:
        clock.set(
            uow.session.execute(select(func.clock_timestamp())).scalar_one() + timedelta(seconds=1)
        )
        head = uow.session.execute(
            select(audit_chain_head.c.last_chain_seq, audit_chain_head.c.last_hmac)
        ).one()
    request = ClosePackCreateIn.model_validate(
        _freeze_for_pack(
            sources,
            audit_head=(head.last_chain_seq, head.last_hmac),
        )
    )
    with sources.world.place.uow() as uow:
        verification = audit_verify.record_tenant_verification(
            uow, trigger="ON_DEMAND", job_id=None
        )
        verification_id = verification["id"]
        uow.commit()
    permissions = frozenset({"report.run", "report.export", "audit.read", "contract.read"})
    reader = replace(
        sources.principal,
        permissions=permissions,
        permission_scopes={permission: "*" for permission in permissions},
    )
    with sources.world.place.uow(reader) as uow:
        bound = evidence_sources.prepare_close(uow, request, verification_id=verification_id)
        pack = evidence_pack_values(
            sources.world.tenant_id, **bound.pack_values(), created_at=uow.now
        )
        uow.session.execute(insert(evidence_pack).values(**pack))
        uow.commit()
    for report in bound.supporting_reports:
        finished = run_journal_job(sources.world, report.job_id, attempts=1)
        assert finished["state"] == "SUCCEEDED", finished
    with sources.world.place.uow(reader) as uow:
        restored = evidence_sources.load_close(uow, pack["id"])
        assert restored == bound
        outputs = tuple(
            file
            for report in restored.supporting_reports
            for file in evidence_reports.collect(uow, report.source())
        )
        assert len(outputs) == 15
        # Newer candidates must never replace the selected report or digest on a retry read.
        newer = evidence_report_plan.queue(uow, resolve(uow, request))
        assert {item.source.run_id for item in newer}.isdisjoint(
            report.run_id for report in restored.supporting_reports
        )
        uow.commit()
    with sources.world.place.uow() as uow:
        newer_digest = audit_verify.record_tenant_verification(
            uow, trigger="ON_DEMAND", job_id=None
        )
        assert newer_digest["id"] != verification_id
        uow.commit()
    with sources.world.place.uow(reader) as uow:
        count = uow.session.execute(select(func.count()).select_from(report_run)).scalar_one()
        assert evidence_sources.load_close(uow, pack["id"]) == bound
        assert evidence_sources.load_close(uow, pack["id"]) == bound
        assert (
            uow.session.execute(select(func.count()).select_from(report_run)).scalar_one() == count
        )
        assert (
            tuple(
                file
                for report in bound.supporting_reports
                for file in evidence_reports.collect(uow, report.source())
            )
            == outputs
        )
        legacy = evidence_pack_values(
            sources.world.tenant_id,
            **{**bound.pack_values(), "source_binding": None},
            created_at=uow.now,
        )
        uow.session.execute(insert(evidence_pack).values(**legacy))
        with pytest.raises(Problem, match="no valid retained"):
            evidence_sources.load_close(uow, legacy["id"])
    with sources.world.place.uow(reader) as uow:
        before = tuple(
            uow.session.execute(select(func.count()).select_from(table)).scalar_one()
            for table in (evidence_pack, report_run, job)
        )
    with pytest.raises(RuntimeError, match="pack transaction failed"):
        with sources.world.place.uow(reader) as uow:
            another = evidence_sources.prepare_close(uow, request, verification_id=verification_id)
            uow.session.execute(
                insert(evidence_pack).values(
                    **evidence_pack_values(
                        sources.world.tenant_id,
                        **another.pack_values(),
                        created_at=uow.now,
                    )
                )
            )
            raise RuntimeError("pack transaction failed")
    with sources.world.place.uow(reader) as uow:
        assert (
            tuple(
                uow.session.execute(select(func.count()).select_from(table)).scalar_one()
                for table in (evidence_pack, report_run, job)
            )
            == before
        )
    denied = replace(
        reader, permission_scopes={**reader.permission_scopes, "audit.read": frozenset()}
    )
    with sources.world.place.uow(denied) as uow, pytest.raises(Problem) as error:
        evidence_sources.load_close(uow, pack["id"])
    assert error.value.slug == "not-found"
    with sources.world.place.uow(reader) as uow, pytest.raises(Problem) as error:
        evidence_sources.load_close(uow, new_id())
    assert error.value.slug == "not-found"
