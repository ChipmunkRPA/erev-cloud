"""``domain.migration.jobs`` — the ``MIGRATION_IMPORT`` composition over fakes (BUILD_SPEC LMG-2;
04 T-MIG-01 note, T-MIG-02, T-MIG-04 / T-MIG-05 rev 1.60; ENGINE_SPEC S07-R-11; D-98 candidates
122 and 126). The legacy side is the shipped WLD-F-15 fixture; the dry run is a port (a prepared
capture stands in for the platform applier, whose payload builders and refusals are tested in
``test_migration_capture.py``); the session is a recorder. Written AFTER the module (disclosed in
the record §24.5); no fail-first log for this file. The database path
(``tests/pg/test_migration_capture_pg.py``) is written and NOT RUN on the lane.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from erev_api.domain.migration import (
    capture,
    jobs,
    legacy_db,
    opening_balances,
    prerequisites,
    repository,
)
from erev_api.enums import JobKind, MigrationMode, PrincipalKind
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import HANDLERS
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork
from sqlalchemy.dialects import postgresql
from support.architecture import ROOT

FIXTURE = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"
BATCH = UUID(int=31)
JOB = UUID(int=32)
CUTOVER = date(2023, 1, 31)
KNOWN_AT = datetime(2026, 9, 20, 19, 0, tzinfo=UTC)


class _Result:
    def __init__(self, *, rows: tuple[Any, ...] = (), scalar: Any = None) -> None:
        self._rows, self._scalar = rows, scalar

    def mappings(self) -> _Result:
        return self

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        return self._scalar

    def scalars(self) -> list[Any]:
        return [row[0] if isinstance(row, tuple) else row for row in self._rows]


class _Session:
    def __init__(self, *results: _Result) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, Any]] = []

    def execute(self, statement: Any, params: Any = None) -> _Result:
        self.calls.append((str(statement.compile(dialect=postgresql.dialect())), params))
        return self.results.pop(0) if self.results else _Result()


def _uow(*results: _Result) -> tuple[UnitOfWork, _Session]:
    session = _Session(*results)
    uow = SimpleNamespace(
        session=session,
        now=KNOWN_AT,
        principal=SimpleNamespace(id=UUID(int=9), kind=PrincipalKind.SYSTEM, tenant_id=UUID(int=1)),
        commits=0,
    )
    return cast(UnitOfWork, uow), session


@pytest.fixture(autouse=True)
def _prerequisites_are_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    """The import-phase tests of this module provision nothing: the LM-CL-09 / LM-CL-03 writers
    (04 rev 1.64) plan and apply nothing here; the order / params witness below overrides both."""
    monkeypatch.setattr(
        jobs.prerequisites,
        "plan",
        lambda *_a, **_k: jobs.prerequisites.PrerequisitePlan(entities=(), products=()),
    )
    monkeypatch.setattr(jobs.prerequisites, "apply", lambda *_a, **_k: jobs.prerequisites.Applied())


def _batch(status: str = "PROFILED", **over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": BATCH,
        "migration_no": "MIG-000001",
        "mode": MigrationMode.OPENING_BALANCES.value,
        "status": status,
        "cutover_date": CUTOVER,
        # 04 rev 1.72: the PROFILE binds the SKU_SSP digest (here of an empty table) the import
        # re-verifies
        "profile": {"contracts": 4, "sku_ssp_sha256": legacy_db.sku_ssp_digest(())},
        "row_version": 3,
        "capture_operation_id": None,
    }
    row.update(over)
    return row


def _rows() -> tuple[legacy_db.LegacyRow, ...]:
    return legacy_db.rows(FIXTURE)


def _capture(staging: opening_balances.Staging) -> capture.Capture:
    """A prepared capture with one captured version per staged contract (a stand-in for the dry
    run; the reader and applier are tested in test_migration_capture)."""
    versions = []
    for index, contract in enumerate(staging.contracts):
        versions.append(
            capture.CapturedVersion(
                contract_version_id=UUID(int=100 + index),
                version_no=1,
                book_code="ASC606",
                combination_group_id=UUID(int=200 + index),
                status_in_book="ACTIVE",
                contract_computation_id=UUID(int=300 + index),
                input_sha256="a" * 64,
                output_sha256="b" * 64,
                engine_version="test",
                engine_release_id=None,
                known_at=KNOWN_AT,
                bundle_known_at=KNOWN_AT,
                cutover_date=CUTOVER,
                payload_migration_batch_id=BATCH,
                opening_event_id=UUID(int=600 + index),
                opening_event_key=f"{contract.external_id}/EV-000002",
                opening_event_binding_sha256=capture.opening_event_binding(
                    UUID(int=600 + index), f"{contract.external_id}/EV-000002", "e" * 64
                ),
                members=(capture.Member(UUID(int=400 + index), contract.external_id),),
                expected_output_captured=True,
                obligation_version_ids=(),
                capture_operation_id=JOB,
                calc_trace_id=UUID(int=500 + index),
                format_version=1,
                node_count=0,
                root_measures={},
                trace_sha256="c" * 64,
                trace={"nodes": []},
                input_evidence={"bundle": {}, "evidence_format": 1},
                input_evidence_sha256="d" * 64,
            )
        )
    return capture.Capture(
        batch_id=BATCH,
        capture_operation_id=JOB,
        cutover_date=CUTOVER,
        versions=tuple(versions),
        obligations=(),
    )


def test_import_handler_is_registered_for_the_job_kind() -> None:
    assert HANDLERS[JobKind.MIGRATION_IMPORT].handler is jobs.import_migration


def test_import_batch_stages_stores_captures_and_moves_profiled_to_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _rows()
    staging = opening_balances.stage(rows, CUTOVER)
    prepared = _capture(staging)
    seen: list[Any] = []

    def fake_dry_run(uow: Any, batch: Any, staged: Any, *, applier: Any = None) -> capture.Capture:
        seen.append((batch["id"], staged.legacy_pob_rows, applier))
        return prepared

    monkeypatch.setattr(capture, "dry_run", fake_dry_run)
    # results in call order: batch row; UPDATE … RETURNING (→ IMPORTING); INSERT T-MIG-02; capture
    # count (0); INSERT T-MIG-04; UPDATE … RETURNING (→ IMPORTED)
    importing = {"id": BATCH, "status": "IMPORTING", "row_version": 4}
    imported = {"id": BATCH, "status": "IMPORTED", "row_version": 5}
    uow, session = _uow(
        _Result(rows=(_batch(),)),
        _Result(rows=(importing,)),
        _Result(),
        _Result(scalar=0),
        _Result(),
        _Result(rows=(imported,)),
    )
    profile = jobs.import_batch(uow, BATCH, job_id=JOB, params={}, rows=rows)
    assert seen == [(BATCH, 16, None)]
    kinds = [call[0].split()[0] for call in session.calls]
    assert kinds == ["SELECT", "UPDATE", "INSERT", "SELECT", "INSERT", "UPDATE"]
    assert seen[0][0] == BATCH
    importing = session.calls[1][0]  # transitions.apply binds the SET values as parameters
    assert "SET status=" in importing and "capture_operation_id=" in importing
    legacy_insert = session.calls[2]
    assert "migrated_legacy_row" in legacy_insert[0] and len(legacy_insert[1]) == 24
    capture_insert = session.calls[4]
    assert "migration_population_version" in capture_insert[0]
    assert [row["contract_version_id"] for row in capture_insert[1]] == [
        UUID(int=100 + i) for i in range(4)
    ]
    assert capture_insert[1][0]["payload_migration_batch_id"] == BATCH
    assert capture_insert[1][0]["capture_operation_id"] == JOB
    assert capture_insert[1][0]["expected_output_captured"] is True
    assert capture_insert[1][0]["members"] == [
        {"contract_id": str(UUID(int=400)), "contract_external_id": "Contract 1"}
    ]
    assert profile["contracts"] == 4 and profile["legacy_pob_rows"] == 16
    assert profile["migrated_rows"] == 24 and profile["captured_versions"] == 4
    assert profile["captured_obligation_versions"] == 0 and profile["findings"] == 0
    assert "IMPORTED" in session.calls[5][0] or "status" in session.calls[5][0]


def test_import_batch_refuses_by_name_before_any_write() -> None:
    rows = _rows()
    for batch, expected in (
        (_batch("UPLOADED"), jobs.NOT_PROFILED_COPY.format(status="UPLOADED")),
        (_batch(mode=MigrationMode.REPLAY.value, cutover_date=None), jobs.REPLAY_IMPORT_COPY),
    ):
        uow, session = _uow(_Result(rows=(batch,)))
        with pytest.raises(Problem) as refused:
            jobs.import_batch(uow, BATCH, rows=rows)
        assert refused.value.slug == "invalid-transition"
        assert refused.value.detail == expected
        assert [call[0].split()[0] for call in session.calls] == ["SELECT"]
    # a cutover after the latest legacy period (SCREENS_B §10.3), a bad batch parameter — 422
    uow, session = _uow(_Result(rows=(_batch(cutover_date=date(2023, 2, 28)),)))
    with pytest.raises(Problem) as refused:
        jobs.import_batch(uow, BATCH, job_id=JOB, rows=rows)
    assert refused.value.slug == "validation-failed"
    assert refused.value.detail == opening_balances.CUTOVER_COPY
    # no job id → no operation identity → refused by name before any write
    uow, session = _uow(_Result(rows=(_batch(),)))
    with pytest.raises(Problem, match="capture_operation_id"):
        jobs.import_batch(uow, BATCH, rows=rows)
    assert len(session.calls) == 1
    uow, session = _uow(_Result(rows=(_batch(),)))
    with pytest.raises(Problem) as refused:
        jobs.import_batch(
            uow,
            BATCH,
            job_id=JOB,
            rows=rows,
            params={"batch_parameters": {"migration.legacy_vc_rows": "X"}},
        )
    assert refused.value.slug == "validation-failed"
    assert refused.value.errors[0].field == "batch_parameters.migration.legacy_vc_rows"
    assert len(session.calls) == 1


def test_batch_parameters_take_the_route_literals_and_keep_the_forced_values() -> None:
    parameters = jobs.batch_parameters({"migration.nondistinct_mapping": "SINGLE_POB"})
    assert parameters.nondistinct_mapping == "SINGLE_POB"
    assert parameters.material_right_convention == "KEEP_QUANTITY_CONVENTION"
    assert parameters.legacy_vc_rows == "VC_ELEMENT_PLUS_CREDIT_EVENTS"
    assert parameters.split_upload_allocation == "ALLOCATE_ACROSS_ALL_POBS"


def test_import_batch_raises_the_s07_r_03_findings_as_migration_exception_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a copy in which one obligation's revenue_cum exceeds its allocation →
    # OPENING_BALANCE_INCONSISTENT (S07-R-03; 04 table 15.4-C)
    rows = list(_rows())
    latest = legacy_db.latest_rows(rows)
    target = next(r for r in latest if r.contract_external_id == "Contract 1")
    broken = dict(target.values)
    broken["Current Rev Rec - Cumulative"] = "999999"
    rows[rows.index(target)] = legacy_db.LegacyRow(target.source_rowid, broken)
    staging = opening_balances.stage(rows, CUTOVER)
    assert staging.findings and staging.findings[0].code == "OPENING_BALANCE_INCONSISTENT"
    raised: list[dict[str, Any]] = []

    def fake_raise(uow: Any, **kwargs: Any) -> Any:
        raised.append(kwargs)
        return SimpleNamespace(id=UUID(int=77))

    import erev_api.domain.imports.exceptions as exceptions_module

    monkeypatch.setattr(exceptions_module, "raise_exception_item", fake_raise)
    monkeypatch.setattr(
        capture, "dry_run", lambda uow, batch, staged, *, applier=None: _capture(staged)
    )
    importing = {"id": BATCH, "status": "IMPORTING", "row_version": 4}
    imported = {"id": BATCH, "status": "IMPORTED", "row_version": 5}
    uow, _session = _uow(
        _Result(rows=(_batch(),)),
        _Result(rows=(importing,)),
        _Result(),
        _Result(scalar=0),
        _Result(),
        _Result(rows=(imported,)),
    )
    profile = jobs.import_batch(uow, BATCH, job_id=JOB, rows=tuple(rows))
    assert profile["findings"] == len(staging.findings) == len(raised)
    assert (
        raised[0]["source"].value == "MIGRATION"
        and raised[0]["code"] == "OPENING_BALANCE_INCONSISTENT"
    )
    assert raised[0]["dedupe"].startswith(f"MIGRATION:OPENING_BALANCE_INCONSISTENT:{BATCH}:")


def test_insert_population_refuses_a_second_capture_for_the_batch() -> None:
    staging = opening_balances.stage(_rows(), CUTOVER)
    uow, session = _uow(_Result(scalar=4))
    with pytest.raises(Problem) as refused:
        repository.insert_population(uow, BATCH, _capture(staging))
    assert refused.value.slug == "invalid-transition"
    assert refused.value.detail == repository.ALREADY_CAPTURED_COPY
    assert [call[0].split()[0] for call in session.calls] == ["SELECT"]  # counted, nothing written


def test_insert_population_stamps_the_tenant_on_every_capture_row() -> None:
    """FLMG-CAPTURE-TENANT-1 (lane FIX-E): T-MIG-04 / T-MIG-05 are RLS-T (04 T-MIG-04, T-MIG-05
    class row), so a row without the tenant is refused by the policy — "new row violates row-level
    security policy for table migration_population_version", which the registered job reported as
    its sanitized 500. Every inserted row of both tables carries the unit of work's tenant, as the
    T-MIG-02 / T-MIG-03 writers' rows do. The pre-fix builders omitted the key."""
    staging = opening_balances.stage(_rows(), CUTOVER)
    prepared = _capture(staging)
    first = prepared.versions[0]
    document, digest = capture.canonical_row({"id": UUID(int=700), "obligation_key": "POB #1"})
    obligation = capture.CapturedObligation(
        contract_version_id=first.contract_version_id,
        obligation_version_id=UUID(int=700),
        contract_id=first.members[0].contract_id,
        contract_external_id=first.members[0].contract_external_id,
        obligation_key="POB #1",
        obligation_kind="STANDARD",
        capture_operation_id=JOB,
        original_allocated_exact=Decimal("322.10"),
        remaining_quantity=Decimal(3),
        billed_cum=Decimal(100),
        revenue_cum=Decimal("128.84"),
        remaining_allocation=Decimal("193.26"),
        position_obligation=Decimal("-28.84"),
        netting_reclass_amount=Decimal(0),
        trace_nodes={},
        row=document,
        row_sha256=digest,
    )
    prepared = dataclasses.replace(prepared, obligations=(obligation,))
    uow, session = _uow(_Result(scalar=0))
    assert repository.insert_population(uow, BATCH, prepared) == (4, 1)
    (_, _), version_insert, obligation_insert = session.calls
    assert "INSERT INTO erev.migration_population_version" in version_insert[0]
    assert "INSERT INTO erev.migration_population_obligation" in obligation_insert[0]
    tenant = uow.principal.tenant_id
    assert [row["tenant_id"] for row in version_insert[1]] == [tenant] * 4
    assert [row["tenant_id"] for row in obligation_insert[1]] == [tenant]
    # the T-MIG-02 / T-MIG-03 builders' convention the capture builders now share
    assert repository.legacy_row_values(uow, BATCH, _rows()[0])["tenant_id"] == tenant


def test_import_job_handler_reads_the_source_commits_and_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _rows()
    monkeypatch.setattr(
        capture, "dry_run", lambda uow, batch, staged, *, applier=None: _capture(staged)
    )
    monkeypatch.setattr(jobs, "legacy_source_with_ssp", lambda jc, uow, batch: (rows, ()))
    importing = {"id": BATCH, "status": "IMPORTING", "row_version": 4}
    imported = {"id": BATCH, "status": "IMPORTED", "row_version": 5}
    uow, session = _uow(
        _Result(rows=(_batch(),)),  # the handler's batch read
        _Result(rows=(_batch(),)),  # import_batch's batch read
        _Result(rows=(importing,)),
        _Result(),
        _Result(scalar=0),
        _Result(),
        _Result(rows=(imported,)),
    )
    commits: list[int] = []
    cast(Any, uow).commit = lambda: commits.append(1)

    @contextmanager
    def unit_of_work() -> Iterator[UnitOfWork]:
        yield uow

    jc = cast(
        JobContext,
        SimpleNamespace(
            unit_of_work=unit_of_work,
            job_id=JOB,
            clock=None,
            runtime=SimpleNamespace(files=object(), keyring=object(), clock=None),
            principal=SimpleNamespace(tenant_id=UUID(int=1), on_behalf_of_id=None),
        ),
    )
    # the IMPORT phase's outer unit under the limited migration authority (Codex 1106 R1) IS this
    # test's unit of work: the authority carrying itself is witnessed by its own test below
    monkeypatch.setattr(
        jobs, "system_unit_of_work", lambda runtime, principal, *, request_id, clock: unit_of_work()
    )
    outcome = jobs.import_migration(jc, {"migration_id": str(BATCH), "batch_parameters": {}})
    assert outcome.state == "SUCCEEDED" and commits == [1]
    assert outcome.result["href"] == f"/api/v1/migrations/{BATCH}"
    assert outcome.result["profile"]["captured_versions"] == 4


def test_legacy_source_refuses_by_name_without_a_file_store() -> None:
    jc = cast(JobContext, SimpleNamespace(runtime=SimpleNamespace(files=None, keyring=None)))
    uow, _ = _uow()
    with pytest.raises(Problem, match="no file store"):
        jobs.legacy_source(jc, uow, _batch(source_file_id=UUID(int=8)))


# --- lifecycle witnesses (Codex 0422 lifecycle; 04 T-MIG-01 note rev 1.60) ----------------------


def test_import_refuses_a_profiled_batch_without_a_cutover_before_any_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # D-98 candidate 128 / Codex 0727: the 1.60 CHECK admits a NULL cutover until /import binds the
    # date; the import phase never consumes one — refused by name, no staging, no transition
    staged: list[int] = []
    monkeypatch.setattr(jobs.opening_balances, "stage", lambda *_a, **_k: staged.append(1))
    uow, session = _uow(_Result(rows=(_batch("PROFILED", cutover_date=None),)))
    with pytest.raises(Problem, match="no cutover date"):
        jobs.import_batch(uow, BATCH, job_id=JOB, params={}, rows=())
    assert staged == []
    assert [call[0].split()[0] for call in session.calls] == ["SELECT"]


def test_import_phase_plans_and_applies_the_confirmed_prerequisites_before_the_dry_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 04 LM-CL-09 / LM-CL-03 rev 1.64 (D-98 candidate 133): plan + apply run in the OUTER unit of
    # work, after the findings and BEFORE capture.dry_run, with the RESOLVED rows and flags the
    # confirmation captured; the dry run then sees the created rows; nothing is written inside the
    # rolled-back savepoint
    order: list[str] = []
    resolved = [
        {
            "legacy_name": "Mock Entity 2",
            "entity_code": "Mock Entity 2",
            "functional_currency": "USD",
            "calendar_id": str(UUID(int=0xA1)),
            "time_zone": "UTC",
        }
    ]
    seen: dict[str, Any] = {}

    def fake_plan(session: Any, staging: Any, **kwargs: Any) -> Any:
        order.append("plan")
        seen.update(kwargs)
        return jobs.prerequisites.PrerequisitePlan(entities=(), products=())

    def fake_apply(uow: Any, batch_id: UUID, plan: Any, **kwargs: Any) -> Any:
        order.append("apply")
        seen["apply_uow"] = uow
        return jobs.prerequisites.Applied()

    def fake_dry_run(uow: Any, batch: Any, staging: Any, **kwargs: Any) -> Any:
        order.append("dry_run")
        raise Problem("validation-failed", "stop here: the writers ran first")

    monkeypatch.setattr(jobs.prerequisites, "plan", fake_plan)
    monkeypatch.setattr(jobs.prerequisites, "apply", fake_apply)
    monkeypatch.setattr(jobs.capture, "dry_run", fake_dry_run)
    monkeypatch.setattr(jobs.repository, "insert_legacy_rows", lambda *_a, **_k: 24)
    monkeypatch.setattr(jobs, "_raise_findings", lambda *_a, **_k: None)
    monkeypatch.setattr(jobs.repository, "transition", lambda *_a, **_k: {})
    uow, _session = _uow(_Result(rows=(_batch("PROFILED"),)))
    rows = legacy_db.rows(FIXTURE)
    with pytest.raises(Problem, match="stop here"):
        jobs.import_batch(
            uow,
            BATCH,
            job_id=JOB,
            params={
                "resolved_entities": resolved,
                "create_missing_entities": True,
                "create_missing_products": False,
            },
            rows=rows,
        )
    assert order == ["plan", "apply", "dry_run"]
    assert seen["resolved_entities"] == resolved
    assert seen["create_missing_entities"] is True and seen["create_missing_products"] is False
    assert seen["apply_uow"] is uow  # the outer unit, never the dry run's child


def test_import_phase_runs_under_the_limited_migration_writer_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Codex 1106 R1: the registered worker's plain SYSTEM principal holds NO permission, so the
    # confirmed writers would be refused by the reference authorization on the real path. The
    # IMPORT phase opens its OUTER unit of work as capture.migration_principal — SYSTEM with exactly
    # MIGRATION_PERMISSIONS, on behalf of the job's creator — through the job context's own
    # system_unit_of_work (same transaction, audit buffer and hooks); the PROFILE phase keeps the
    # plain job principal.
    from contextlib import contextmanager

    seen: list[Any] = []
    uow, _session = _uow(_Result(rows=(_batch("PROFILED"),)))
    uow.commit = lambda: None  # type: ignore[method-assign]

    @contextmanager
    def fake_system_unit_of_work(
        runtime: Any, principal: Any, *, request_id: str, clock: Any
    ) -> Any:
        seen.append((principal, request_id))
        yield uow

    monkeypatch.setattr(jobs, "system_unit_of_work", fake_system_unit_of_work)
    monkeypatch.setattr(jobs, "legacy_source_with_ssp", lambda *_a, **_k: ((), ()))
    monkeypatch.setattr(jobs, "import_batch", lambda *_a, **_k: {"contracts": 0})
    creator = UUID(int=77)
    jc = SimpleNamespace(
        job_id=JOB,
        clock=None,
        runtime=SimpleNamespace(files=object(), keyring=object(), clock=None),
        principal=SimpleNamespace(
            tenant_id=UUID(int=1), on_behalf_of_id=creator, permissions=frozenset()
        ),
        unit_of_work=lambda: (_ for _ in ()).throw(
            AssertionError("the IMPORT phase must not use the plain job principal")
        ),
    )
    outcome = jobs.import_migration(jc, {"migration_id": str(BATCH), "phase": "IMPORT"})  # type: ignore[arg-type]
    assert outcome.state == "SUCCEEDED"
    ((principal, request_id),) = seen
    assert principal.kind is PrincipalKind.SYSTEM and principal.tenant_id == UUID(int=1)
    assert principal.permissions == capture.MIGRATION_PERMISSIONS  # exactly the limited set
    assert "masterdata.maintain" in principal.permissions and principal.on_behalf_of_id == creator
    assert request_id == f"job-{JOB}"


def test_import_phase_stages_with_the_confirmed_entity_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Codex 1227 F1: the CONFIRMED mapping in the job params (immutable) is applied at staging —
    # the dry run then requires the TARGET code, not the legacy text; an unmapped text is its own
    # code (the identity mapping)
    seen: dict[str, Any] = {}
    original_stage = jobs.opening_balances.stage

    def capture_stage(rows: Any, cutover: Any, params: Any = None, entity_codes: Any = None) -> Any:
        seen["entity_codes"] = dict(entity_codes or {})
        return original_stage(rows, cutover, params, entity_codes=entity_codes)

    monkeypatch.setattr(jobs.opening_balances, "stage", capture_stage)
    monkeypatch.setattr(jobs.repository, "insert_legacy_rows", lambda *_a, **_k: 24)
    monkeypatch.setattr(jobs, "_raise_findings", lambda *_a, **_k: None)
    monkeypatch.setattr(jobs.repository, "transition", lambda *_a, **_k: {})

    def stop(uow: Any, batch: Any, staging: Any, **kwargs: Any) -> Any:
        seen["contract_entities"] = sorted({c.entity_code for c in staging.contracts})
        raise Problem("validation-failed", "stop here: staged with the confirmed mapping")

    monkeypatch.setattr(jobs.capture, "dry_run", stop)
    uow, _session = _uow(_Result(rows=(_batch("PROFILED"),)))
    with pytest.raises(Problem, match="stop here"):
        jobs.import_batch(
            uow,
            BATCH,
            job_id=JOB,
            params={
                "entity_mapping": [
                    {"legacy_name": "Mock Entity 1", "entity_code": "AVM-US"},
                    {"legacy_name": "Mock Entity 2", "entity_code": "Mock Entity 2"},
                ]
            },
            rows=legacy_db.rows(FIXTURE),
        )
    assert seen["entity_codes"] == {"Mock Entity 1": "AVM-US", "Mock Entity 2": "Mock Entity 2"}
    assert seen["contract_entities"] == ["AVM-US", "Mock Entity 2"]


def _stored_capture(operation: UUID) -> tuple[dict[str, Any], dict[str, Any]]:
    """A complete stored capture of one version and one obligation (T-MIG-04 / 05 rows as the
    repository reads them), consistent in every hash and identity."""
    from erev_api.explain.store import trace_document
    from erev_engine.trace import Trace, TraceNode

    node = TraceNode(
        id="revenue_cum:POB #1",
        measure="revenue_cum",
        value="295.69",
        currency="USD",
        formula_id="f",
        inputs=(),
        params={},
        rounding_residue="0.000000000000000000",
        narrative_key="k",
    )
    trace = Trace(format_version=1, engine_version="test", nodes=(node,), root_measures={})
    version_id, trace_id, obligation_id, contract_id = (
        UUID(int=100),
        UUID(int=200),
        UUID(int=600),
        UUID(int=500),
    )
    row_document = {
        "id": str(obligation_id),
        "contract_version_id": str(version_id),
        "contract_id": str(contract_id),
        "obligation_key": "POB #1",
        "obligation_kind": "STANDARD",
        "original_allocated_exact": "1300.000000000000000000",
        "remaining_quantity": "0.000000000000000000",
        "billed_cum": "300.00",
        "revenue_cum": "295.69",
        "remaining_allocation": "1004.31",
        "position_obligation": "4.31",
        "netting_reclass_amount": "0.00",
        "trace_nodes": {"revenue_cum": "revenue_cum:POB #1"},
    }
    document, digest = capture.canonical_row(row_document)
    from support.migration_capture import capture_world

    world = capture_world(BATCH)  # a real, decodable producing input (Codex 0515 R1)
    opening_event_id = UUID(int=700)
    version_row = {
        "id": UUID(int=9000),
        "migration_batch_id": BATCH,
        "contract_version_id": version_id,
        "calc_trace_id": trace_id,
        "book_code": "ASC606",
        # Codex 0605 R1: the declared opening event is bound to the bundle's logical event
        "opening_event_id": opening_event_id,
        "opening_event_key": world.opening_event_key,
        "opening_event_binding_sha256": capture.opening_event_binding(
            opening_event_id, world.opening_event_key, world.opening_payload_sha256
        ),
        "members": [{"contract_id": str(contract_id), "contract_external_id": world.contract_key}],
        "obligation_version_ids": [obligation_id],
        "cutover_date": CUTOVER,
        "payload_migration_batch_id": BATCH,
        "trace_sha256": trace.sha256(),
        "expected_output_captured": True,
        "capture_operation_id": operation,
        "format_version": 1,
        "engine_version": "test",
        "root_measures": {},
        "trace": trace_document(trace),
        "input_sha256": world.input_sha256,
        "bundle_known_at": world.bundle.known_at,
        "input_evidence": world.evidence_document,
        "input_evidence_sha256": world.evidence_sha256,
    }
    obligation_row = {
        "migration_batch_id": BATCH,
        "population_version_id": UUID(int=9000),  # the parent T-MIG-04 row
        "capture_operation_id": operation,
        "obligation_version_id": obligation_id,
        "contract_version_id": version_id,
        "contract_id": contract_id,
        "contract_external_id": world.contract_key,
        "obligation_key": "POB #1",
        "obligation_kind": "STANDARD",
        "original_allocated_exact": "1300.000000000000000000",
        "remaining_quantity": "0.000000000000000000",
        "billed_cum": "300.00",
        "revenue_cum": "295.69",
        "remaining_allocation": "1004.31",
        "position_obligation": "4.31",
        "netting_reclass_amount": "0.00",
        "trace_nodes": {"revenue_cum": "revenue_cum:POB #1"},
        "row": document,
        "row_sha256": digest,
    }
    return version_row, obligation_row


def _recovery_session(
    operation: UUID, *, version_row: Any, obligation_row: Any, status: str = "IMPORTED"
) -> _Session:
    """The reads of captured_operation in order: the batch row, the T-MIG-04 rows (population),
    the operation ids of both tables, the parents of the children, the T-MIG-05 rows, the trace
    mirror, the evidence rows."""
    return _Session(
        _Result(rows=(_batch(status, capture_operation_id=operation),)),
        _Result(rows=(version_row,)),
        _Result(rows=((operation,),)),
        _Result(rows=((operation,),)),
        _Result(rows=(version_row,)),
        _Result(rows=(obligation_row,)),
        _Result(rows=(version_row,)),
        _Result(rows=(version_row,)),
    )


def test_same_operation_recovery_returns_the_stored_result_without_rerunning() -> None:
    # a retry after the durable commit: the batch is IMPORTED with THIS job's capture → validated
    # (operation ids, batch / cutover binding, row hashes, trace hash) and returned; no dry run, no
    # insert, no transition
    version_row, obligation_row = _stored_capture(JOB)
    session = _recovery_session(JOB, version_row=version_row, obligation_row=obligation_row)
    uow = cast(UnitOfWork, SimpleNamespace(session=session, now=KNOWN_AT))
    profile = jobs.import_batch(uow, BATCH, job_id=JOB, rows=_rows())
    assert profile["recovered"] is True
    assert profile["captured_versions"] == 1 and profile["captured_obligation_versions"] == 1
    assert profile["contracts"] == 4  # the stored profile, untouched
    assert all(call[0].startswith("SELECT") for call in session.calls)  # reads only
    # C1: the same recognition after later phases moved the batch on — RECONCILED, SUBMITTED,
    # PROMOTED — with no rerun, no write, no status moved backward
    for later in ("RECONCILED", "SUBMITTED", "PROMOTED"):
        session = _recovery_session(
            JOB, version_row=version_row, obligation_row=obligation_row, status=later
        )
        uow = cast(UnitOfWork, SimpleNamespace(session=session, now=KNOWN_AT))
        recovered = jobs.import_batch(uow, BATCH, job_id=JOB, rows=_rows())
        assert recovered["recovered"] is True
        assert all(call[0].startswith("SELECT") for call in session.calls)


def test_foreign_or_incomplete_capture_is_refused_by_name() -> None:
    # another operation's capture under this batch
    version_row, obligation_row = _stored_capture(UUID(int=99))
    uow, session = _uow(_Result(rows=(_batch("IMPORTED", capture_operation_id=UUID(int=99)),)))
    with pytest.raises(Problem) as refused:
        jobs.import_batch(uow, BATCH, job_id=JOB, rows=_rows())
    assert refused.value.slug == "invalid-transition"
    assert (refused.value.detail or "").startswith(repository.FOREIGN_CAPTURE_COPY.split("{")[0])
    assert len(session.calls) == 1  # refused on the batch row alone
    # IMPORTED for this operation but no capture rows at all → refused, never adopted
    uow, session = _uow(
        _Result(rows=(_batch("IMPORTED", capture_operation_id=JOB),)), _Result(rows=())
    )
    with pytest.raises(Problem, match="IMPORTED without a capture"):
        jobs.import_batch(uow, BATCH, job_id=JOB, rows=_rows())
    # a stored row whose retained representation disagrees with its typed column → refused
    version_row, obligation_row = _stored_capture(JOB)
    broken = dict(obligation_row, revenue_cum="295.70")
    session = _recovery_session(JOB, version_row=version_row, obligation_row=broken)
    uow = cast(UnitOfWork, SimpleNamespace(session=session, now=KNOWN_AT))
    with pytest.raises(Exception, match="disagrees with the retained row"):
        jobs.import_batch(uow, BATCH, job_id=JOB, rows=_rows())
    # a mirrored trace whose hash is not the captured one → refused
    version_row, obligation_row = _stored_capture(JOB)
    tampered = dict(version_row, trace_sha256="e" * 64)
    session = _Session(
        _Result(rows=(_batch("IMPORTED", capture_operation_id=JOB),)),
        _Result(rows=(tampered,)),
        _Result(rows=((JOB,),)),
        _Result(rows=((JOB,),)),
        _Result(rows=(tampered,)),
        _Result(rows=(obligation_row,)),
        _Result(rows=(tampered,)),
    )
    uow = cast(UnitOfWork, SimpleNamespace(session=session, now=KNOWN_AT))
    with pytest.raises(Exception, match="trace_sha256|hash"):
        jobs.import_batch(uow, BATCH, job_id=JOB, rows=_rows())


def test_terminal_hook_fails_a_profiled_batch_and_never_degrades_a_verified_capture() -> None:
    problem = {"instance": f"/api/v1/jobs/{JOB}", "detail": "boom", "status": 500}
    # PROFILED (the import's transaction rolled back): the batch ends FAILED with the problem
    failed = {"id": BATCH, "status": "FAILED", "row_version": 4}
    uow, session = _uow(_Result(rows=(_batch(),)), _Result(rows=(failed,)))
    jobs.import_failed(uow, {"migration_id": str(BATCH)}, problem)
    kinds = [call[0].split()[0] for call in session.calls]
    assert kinds == ["SELECT", "UPDATE"]
    assert "SET status=" in session.calls[1][0] and "problem=" in session.calls[1][0]
    # IMPORTED with THIS job's verified capture: left as it is — reads only, no UPDATE
    version_row, obligation_row = _stored_capture(JOB)
    session = _recovery_session(JOB, version_row=version_row, obligation_row=obligation_row)
    uow = cast(UnitOfWork, SimpleNamespace(session=session, now=KNOWN_AT))
    jobs.import_failed(uow, {"migration_id": str(BATCH)}, problem)
    assert all(call[0].startswith("SELECT") for call in session.calls)
    # IMPORTED under another operation: not this job's to touch — the batch row read, nothing else
    uow, session = _uow(_Result(rows=(_batch("IMPORTED", capture_operation_id=UUID(int=99)),)))
    jobs.import_failed(uow, {"migration_id": str(BATCH)}, problem)
    assert [call[0].split()[0] for call in session.calls] == ["SELECT"]
    # the handler registers the hook
    # LMG-API-1: the registered hook dispatches on the job's phase — the import phase (the
    # default) keeps import_failed's contract above; the profiling phase has its own share
    assert HANDLERS[JobKind.MIGRATION_IMPORT].on_failure is jobs.migration_failed
    calls: list[str] = []
    original = (jobs.import_failed, jobs.profile_failed)
    jobs.import_failed = lambda *_a, **_k: calls.append("import")  # type: ignore[assignment]
    jobs.profile_failed = lambda *_a, **_k: calls.append("profile")  # type: ignore[assignment]
    try:
        jobs.migration_failed(uow, {"migration_id": str(BATCH)}, problem)
        jobs.migration_failed(uow, {"migration_id": str(BATCH), "phase": "IMPORT"}, problem)
        jobs.migration_failed(uow, {"migration_id": str(BATCH), "phase": "PROFILE"}, problem)
    finally:
        jobs.import_failed, jobs.profile_failed = original  # type: ignore[assignment]
    assert calls == ["import", "import", "profile"]


def test_registered_handler_recovers_before_reopening_the_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Codex 0533 L2: the REGISTERED handler checks completed-operation recovery first; the stored
    # legacy source is not reopened on that path — a reader that must not be called proves it.
    version_row, obligation_row = _stored_capture(JOB)
    session = _Session(
        _Result(rows=(_batch("RECONCILED", capture_operation_id=JOB),)),  # the handler's read
        _Result(rows=(_batch("RECONCILED", capture_operation_id=JOB),)),  # import_batch's read
        _Result(rows=(version_row,)),
        _Result(rows=((JOB,),)),
        _Result(rows=((JOB,),)),
        _Result(rows=(version_row,)),  # the parents of the children
        _Result(rows=(obligation_row,)),
        _Result(rows=(version_row,)),  # the trace mirror
        _Result(rows=(version_row,)),  # the evidence rows
    )
    uow = cast(UnitOfWork, SimpleNamespace(session=session, now=KNOWN_AT, commit=lambda: None))

    def must_not_be_called(jc: Any, uow_: Any, batch: Any) -> Any:
        raise AssertionError("legacy_source must not be reopened on the recovery path")

    monkeypatch.setattr(jobs, "legacy_source_with_ssp", must_not_be_called)

    @contextmanager
    def unit_of_work() -> Iterator[UnitOfWork]:
        yield uow

    jc = cast(
        JobContext,
        SimpleNamespace(
            unit_of_work=unit_of_work,
            job_id=JOB,
            clock=None,
            runtime=SimpleNamespace(files=object(), keyring=object(), clock=None),
            principal=SimpleNamespace(tenant_id=UUID(int=1), on_behalf_of_id=None),
        ),
    )
    # the IMPORT phase's outer unit under the limited migration authority (Codex 1106 R1) IS this
    # test's unit of work: the authority carrying itself is witnessed by its own test below
    monkeypatch.setattr(
        jobs, "system_unit_of_work", lambda runtime, principal, *, request_id, clock: unit_of_work()
    )
    outcome = jobs.import_migration(jc, {"migration_id": str(BATCH), "batch_parameters": {}})
    assert outcome.state == "SUCCEEDED" and outcome.result["profile"]["recovered"] is True
    assert all(call[0].startswith("SELECT") for call in session.calls)  # reads only, no write


# --- 04 rev 1.72 (D-98 133 AMENDMENT 4): the SKU_SSP digest re-verification and the replay
# hand-over ------


def test_import_refuses_a_sku_ssp_table_that_is_not_the_profiled_one_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staged: list[int] = []
    monkeypatch.setattr(jobs.opening_balances, "stage", lambda *_a, **_k: staged.append(1))
    uow, session = _uow(_Result(rows=(_batch(),)))  # the profile bound the digest of an EMPTY table
    changed = ({"SKU Name": "Hardware 1", "SSP Version": "2023-01-01"},)
    with pytest.raises(Problem, match="is not the one the profile bound"):
        jobs.import_batch(uow, BATCH, job_id=JOB, params={}, rows=(), sku_ssp_rows=changed)
    assert staged == []  # refused by name before staging, storing or any prerequisite write
    assert [call[0].split()[0] for call in session.calls] == ["SELECT"]


def test_import_refuses_a_profile_without_a_sku_ssp_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs.opening_balances, "stage", lambda *_a, **_k: None)
    uow, _session = _uow(_Result(rows=(_batch(profile={"contracts": 4}),)))
    with pytest.raises(Problem, match="carries no SKU_SSP digest"):
        jobs.import_batch(uow, BATCH, job_id=JOB, params={}, rows=(), sku_ssp_rows=())


def test_import_hands_the_writers_the_sku_ssp_rows_and_the_replay_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The confirmed request id and the SKU_SSP rows reach ``prerequisites.plan`` / ``apply``; the
    profile records the replayed versions (fakes for the writers and the dry run)."""
    rows = _rows()
    ssp_rows = legacy_db.sku_ssp_rows(FIXTURE)
    seen: dict[str, Any] = {}

    def fake_plan(session: Any, staging: Any, **kwargs: Any) -> Any:
        seen["plan"] = kwargs
        return prerequisites.PrerequisitePlan(entities=(), products=())

    def fake_apply(uow: Any, batch_id: Any, plan_: Any, **kwargs: Any) -> Any:
        seen["apply"] = kwargs
        return prerequisites.Applied(
            ssp_version_ids={"2023-01-01": UUID(int=0x55)}, ssp_entry_counts={"2023-01-01": 7}
        )

    def fake_dry_run(uow: Any, batch: Any, staged: Any, *, applier: Any = None) -> capture.Capture:
        return capture.Capture(
            batch_id=BATCH,
            capture_operation_id=JOB,
            cutover_date=CUTOVER,
            versions=(),
            obligations=(),
        )

    monkeypatch.setattr(prerequisites, "plan", fake_plan)
    monkeypatch.setattr(prerequisites, "apply", fake_apply)
    monkeypatch.setattr(capture, "dry_run", fake_dry_run)
    monkeypatch.setattr(repository, "insert_legacy_rows", lambda *_a, **_k: 24)
    monkeypatch.setattr(repository, "insert_population", lambda *_a, **_k: (0, 0))
    monkeypatch.setattr(jobs, "_raise_findings", lambda *_a, **_k: None)
    digest = legacy_db.sku_ssp_digest(ssp_rows)
    batch = _batch(profile={"contracts": 4, "sku_ssp_sha256": digest})
    importing = {**batch, "status": "IMPORTING", "capture_operation_id": JOB}
    imported = {**importing, "status": "IMPORTED"}
    uow, _session = _uow(
        _Result(rows=(batch,)), _Result(rows=(importing,)), _Result(rows=(imported,))
    )
    params = {"ssp_replay_request_id": str(UUID(int=0x77)), "sku_ssp_sha256": digest}
    profile = jobs.import_batch(
        uow, BATCH, job_id=JOB, params=params, rows=rows, sku_ssp_rows=ssp_rows
    )
    assert seen["plan"]["sku_ssp_rows"] is ssp_rows
    assert seen["apply"]["replay_request_id"] == UUID(int=0x77)
    assert (
        seen["apply"]["sku_ssp_sha256"] == digest and seen["apply"]["migration_no"] == "MIG-000001"
    )
    assert profile["replayed_ssp_versions"] == [
        {
            "legacy_version_label": "2023-01-01",
            "ssp_book_version_id": str(UUID(int=0x55)),
            "entry_count": 7,
            "source_sha256": digest,
            "reused": False,
        }
    ]
