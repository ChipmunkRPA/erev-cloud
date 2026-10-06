"""API-R-48 migration routes, CPU-runnable (BUILD_SPEC LMG-1 rev 1.8; lane record §25): the
command handlers and queries over a fake unit of work, the ``MIGRATION_IMPORT`` phase dispatch, the
router's shape (operation ids, guards, commands on every write route, the list specification).
The database-bound route cases are ``tests/api/test_migrations_api.py`` (WRITTEN, NOT RUN on the
lane).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from erev_api.api.v1 import migrations as routes
from erev_api.domain.migration import commands, jobs, queries
from erev_api.enums import (
    ApprovalSubjectType,
    JobKind,
    JobState,
    MigrationMode,
    MigrationStatus,
    PrincipalKind,
)
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.common import ActorOut, JobOut, JobProgressOut
from erev_api.schemas.migrations import (
    EntityMappingIn,
    MigrationCreateIn,
    OpeningBalancesImportIn,
    ReplayImportIn,
    ReplayPlanItemIn,
)
from erev_api.uow import UnitOfWork
from fastapi.routing import APIRoute
from sqlalchemy.dialects import postgresql

BATCH = UUID(int=0x48)
FILE_ID = UUID(int=0x12)
JOB = UUID(int=0x77)
USER = UUID(int=9)
NOW = datetime(2026, 9, 21, 0, 30, tzinfo=UTC)
CUTOVER = date(2023, 1, 31)
PROFILE = {
    "source_sha256": "a" * 64,
    "tables": {"Contract_Live": 24, "SKU_SSP": 7},
    "contract_live_rows": 24,
    "contracts": 4,
    "legacy_pob_rows": 16,
    "sku_ssp_rows": 7,
    "ssp_versions": ["2023-01-01"],
    "selling_entities": ["Mock Entity 1", "Mock Entity 2"],
    "latest_current_period": "2023-01-31",
    "version_tokens": ["v1"],
    "columns": [["Contract Unique Name", "TEXT"]],
    # 04 rev 1.72: the replay evidence the /import confirmation binds
    "sku_ssp_sha256": "b" * 64,
    "sku_ssp_findings": [],
    "sku_ssp_keys": [["2023-01-01", "Hardware 1", "Hardware 1"]],
}


# ---- fakes ---------------------------------------------------------------------------------------


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

    def __iter__(self) -> Any:
        return iter(self._rows)


class _Session:
    """A queue of results, plus table-keyed answers (``FROM erev.<table>``) for the confirmation's
    reads (Codex 1106 R2: the real resolver runs over this session, no fake resolver)."""

    def __init__(self, *results: _Result, answers: dict[str, _Result] | None = None) -> None:
        self.results = list(results)
        self.answers = dict(answers or {})
        self.calls: list[tuple[str, Any]] = []

    def execute(self, statement: Any, params: Any = None) -> _Result:
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.calls.append((sql, params))
        for table, result in self.answers.items():
            if f"FROM erev.{table}" in sql:
                return result
        return self.results.pop(0) if self.results else _Result()


class _Uow:
    """The slice of ``UnitOfWork`` the handlers use: session, clock, principal and its request
    context, defer, audit."""

    def __init__(self, *results: _Result, answers: dict[str, _Result] | None = None) -> None:
        self.session = _Session(*results, answers=answers)
        self.now = NOW
        self.principal = SimpleNamespace(id=USER, kind=PrincipalKind.USER, tenant_id=UUID(int=1))
        self.ctx = SimpleNamespace(principal=self.principal)
        self.deferred: list[tuple[JobKind, dict[str, Any], dict[str, Any]]] = []
        self.audited: list[dict[str, Any]] = []

    def defer(self, kind: JobKind, params: Any, **kwargs: Any) -> dict[str, Any]:
        self.deferred.append((kind, dict(params), dict(kwargs)))
        return {"id": JOB}

    def audit(self, **kwargs: Any) -> None:
        self.audited.append(dict(kwargs))

    def commit(self) -> None:
        self.commits = getattr(self, "commits", 0) + 1


CAL_A = UUID(int=0xA1)


def _confirmation_answers(
    *,
    entities: tuple[str, ...] = ("Mock Entity 1", "Mock Entity 2"),
    calendars: tuple[UUID, ...] = (CAL_A,),
    currency: str = "USD",
) -> dict[str, _Result]:
    """What the confirmation reads: the tenant reporting currency, the fiscal calendars (with
    periods), the entity codes the tenant already has (default: both selling entities of WLD-F-15
    exist — nothing to create)."""
    return {
        "tenant": _Result(scalar=currency),
        "fiscal_calendar": _Result(rows=tuple((c, f"CAL-{i}") for i, c in enumerate(calendars))),
        "period": _Result(rows=tuple((c,) for c in calendars)),
        "legal_entity": _Result(rows=tuple((e,) for e in entities)),
    }


def _uow(*results: _Result, answers: dict[str, _Result] | None = None) -> tuple[UnitOfWork, _Uow]:
    fake = _Uow(*results, answers=_confirmation_answers() if answers is None else answers)
    return cast(UnitOfWork, fake), fake


def _batch(status: str = "PROFILED", **over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "tenant_id": UUID(int=1),
        "id": BATCH,
        "migration_no": "MIG-000001",
        "mode": MigrationMode.OPENING_BALANCES.value,
        "status": status,
        "source_file_id": FILE_ID,
        "source_sha256": "a" * 64,
        "cutover_date": None,
        "sandbox_tenant_id": None,
        "profile": dict(PROFILE),
        "import_upload_ids": [],
        "registry_version_id": None,
        "reconciliation_id": None,
        "reconciliation_report_run_id": None,
        "approval_request_id": None,
        "job_id": None,
        "started_at": None,
        "finished_at": None,
        "problem": None,
        "capture_operation_id": None,
        "row_version": 3,
        "created_at": NOW,
        "created_by": USER,
        "created_by_kind": PrincipalKind.USER.value,
        "updated_at": NOW,
        "updated_by": USER,
        "updated_by_kind": PrincipalKind.USER.value,
    }
    row.update(over)
    return row


def _job_out(state: JobState = JobState.QUEUED, *, created_by: UUID | None = USER) -> JobOut:
    return JobOut(
        id=JOB,
        kind=JobKind.MIGRATION_IMPORT,
        state=state,
        progress=JobProgressOut(done=0, total=None),
        result=None,
        problem=None,
        created_by=ActorOut(id=created_by, kind=PrincipalKind.USER, display_name="Maya"),
        created_at=NOW,
        started_at=None,
        finished_at=None,
    )


REQUEST = UUID(int=0x5E9)


@pytest.fixture(autouse=True)
def replay_requests(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """04 rev 1.72: every confirmed /import submits the MIGRATION_SSP_REPLAY request through the
    approvals engine — faked here (the engine is DB-bound); the calls are recorded for assertion."""
    calls: list[dict[str, Any]] = []

    def fake_submit(uow: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(dict(kwargs))
        return {"id": REQUEST, "status": "APPROVED"}

    monkeypatch.setattr(commands, "submit_request", fake_submit)
    return calls


@pytest.fixture
def transitions(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture ``repository.transition`` calls instead of compiling DB-03 SQL against the fake."""
    seen: list[dict[str, Any]] = []

    def fake_transition(uow: Any, batch_id: UUID, **kwargs: Any) -> dict[str, Any]:
        seen.append({"batch_id": batch_id, **kwargs})
        return {"id": batch_id}

    monkeypatch.setattr(commands.repository, "transition", fake_transition)
    return seen


@pytest.fixture
def job_outs(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"out": _job_out(), "cancelled": []}
    monkeypatch.setattr(commands, "job_out_of", lambda _session, job_id: state["out"])
    monkeypatch.setattr(
        commands, "cancel_job", lambda _uow, job_id: state["cancelled"].append(job_id)
    )
    return state


# ---- create --------------------------------------------------------------------------------------


def _sqlite(path: Path, *, with_contract_live: bool) -> None:
    # DG-ARC-05: sqlite3 is imported only under tests/support/parity (and the migration domain)
    from support.parity.sqlite_fixtures import (
        sqlite_with_contract_live,
        sqlite_without_contract_live,
    )

    (sqlite_with_contract_live if with_contract_live else sqlite_without_contract_live)(path)


def _stored(purpose: str = "LEGACY_DATABASE") -> dict[str, Any]:
    return {
        "id": FILE_ID,
        "tenant_id": UUID(int=1),
        "purpose": purpose,
        "sha256": "a" * 64,
        "original_filename": "ASC606.db",
        "size_bytes": 4096,
        "storage_key": "k",
        "shredded_at": None,
    }


def _caller_reads_the_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """The caller may read the stored source — the first thing the command asks, through
    ``file_access.bound`` (04 T-PLT-29 Read access, rev 1.151; Binding). The rule itself needs
    rows: ``tests/api/test_files.py`` holds it."""
    monkeypatch.setattr(commands.file_access, "bound", lambda *_args: _stored())


def test_create_recognises_the_stored_source_then_creates_an_uploaded_batch_without_cutover(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    good = tmp_path / "good.db"
    _sqlite(good, with_contract_live=True)
    _caller_reads_the_source(monkeypatch)
    monkeypatch.setattr(
        commands,
        "open_file",
        lambda _session, _file_id, *, files, keyring: (_stored(), good.open("rb")),
    )
    created: list[dict[str, Any]] = []

    def fake_create(uow: Any, **kwargs: Any) -> dict[str, Any]:
        created.append(kwargs)
        return _batch("UPLOADED")

    monkeypatch.setattr(commands.repository, "create_batch", fake_create)
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: _batch("UPLOADED"))
    uow, fake = _uow()
    body = MigrationCreateIn(mode=MigrationMode.OPENING_BALANCES, source_file_id=FILE_ID)
    row = commands.create_batch(uow, body, files=object(), keyring=object())  # type: ignore[arg-type]
    # D-98 candidate 128: the opening-balances batch is created WITHOUT a cutover
    assert created == [
        {
            "mode": MigrationMode.OPENING_BALANCES,
            "source_file_id": FILE_ID,
            "source_sha256": "a" * 64,
        }
    ]
    assert row["status"] == "UPLOADED"
    assert fake.audited[0]["action"] == commands.CREATE_ACTION
    assert fake.audited[0]["after"]["status"] == "UPLOADED"
    assert fake.deferred == []  # creation defers nothing: profiling is its own command


def test_create_refuses_a_non_legacy_purpose_and_an_unrecognised_database_by_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    other = tmp_path / "other.db"
    _sqlite(other, with_contract_live=False)
    _caller_reads_the_source(monkeypatch)
    uow, _ = _uow()
    body = MigrationCreateIn(mode=MigrationMode.OPENING_BALANCES, source_file_id=FILE_ID)
    # purpose: 422 upload-type-not-allowed with the ERR-37 copy (SCREENS_B §10.2)
    monkeypatch.setattr(
        commands,
        "open_file",
        lambda *_a, **_k: (_stored("IMPORT_SOURCE"), other.open("rb")),
    )
    with pytest.raises(Problem) as refused:
        commands.create_batch(uow, body, files=object(), keyring=object())  # type: ignore[arg-type]
    assert refused.value.slug == "upload-type-not-allowed"
    assert refused.value.errors[0].field == "source_file_id"
    # content: 422 legacy-database-unrecognized (ERR-20; J-20-ALT-2) — the stored object is spooled
    # to a copy and the copy removed
    monkeypatch.setattr(commands, "open_file", lambda *_a, **_k: (_stored(), other.open("rb")))
    with pytest.raises(Problem) as refused:
        commands.create_batch(uow, body, files=object(), keyring=object())  # type: ignore[arg-type]
    assert refused.value.slug == "legacy-database-unrecognized"
    assert "Contract_Live" in str(refused.value.detail)


# ---- profile -------------------------------------------------------------------------------------


def test_profile_moves_uploaded_to_profiling_with_the_deferred_profile_phase(
    monkeypatch: pytest.MonkeyPatch, transitions: list[dict[str, Any]], job_outs: dict[str, Any]
) -> None:
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: _batch("UPLOADED"))
    uow, fake = _uow()
    out = commands.profile_batch(uow, BATCH)
    assert out.id == JOB
    assert fake.deferred == [
        (
            JobKind.MIGRATION_IMPORT,
            {"migration_id": str(BATCH), "phase": "PROFILE"},
            {"subject_type": "migration_batch", "subject_id": BATCH},
        )
    ]
    assert transitions == [
        {
            "batch_id": BATCH,
            "to_status": MigrationStatus.PROFILING,
            "expected_status": MigrationStatus.UPLOADED,
            "job_id": JOB,
            "started_at": NOW,
        }
    ]
    assert fake.audited[0]["action"] == commands.PROFILE_ACTION


@pytest.mark.parametrize("status", ["PROFILING", "PROFILED", "IMPORTED", "CANCELLED", "FAILED"])
def test_profile_refuses_any_status_but_uploaded_by_name(
    monkeypatch: pytest.MonkeyPatch, transitions: list[dict[str, Any]], status: str
) -> None:
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: _batch(status))
    uow, fake = _uow()
    with pytest.raises(Problem) as refused:
        commands.profile_batch(uow, BATCH)
    assert refused.value.slug == "invalid-transition"
    assert status in str(refused.value.detail) and "UPLOADED" in str(refused.value.detail)
    assert fake.deferred == [] and transitions == [] and fake.audited == []


# ---- import --------------------------------------------------------------------------------------


def _opening(**over: Any) -> OpeningBalancesImportIn:
    values: dict[str, Any] = {
        "cutover_date": CUTOVER,
        "entity_mapping": [
            EntityMappingIn(legacy_name="Mock Entity 1", entity_code="Mock Entity 1"),
        ],
        "batch_parameters": {},
    }
    values.update(over)
    return OpeningBalancesImportIn(**values)


def test_import_writes_the_cutover_once_and_defers_the_import_phase(
    monkeypatch: pytest.MonkeyPatch, transitions: list[dict[str, Any]], job_outs: dict[str, Any]
) -> None:
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: _batch("PROFILED"))
    uow, fake = _uow()
    out = commands.import_batch(uow, BATCH, _opening())
    assert out.id == JOB
    kind, params, binding = fake.deferred[0]
    assert kind is JobKind.MIGRATION_IMPORT and params["phase"] == "IMPORT"
    assert params["migration_id"] == str(BATCH) and params["batch_parameters"] == {}
    assert params["entity_mapping"] == [
        {
            "legacy_name": "Mock Entity 1",
            "entity_code": "Mock Entity 1",
            "calendar_id": None,
            "time_zone": None,
        }
    ]
    assert params["resolved_entities"] == [] and params["create_missing_products"] is True
    assert binding == {"subject_type": "migration_batch", "subject_id": BATCH}
    # D-98 candidate 128: the cutover is written ONCE, with the job id, status unchanged (the job
    # moves PROFILED → IMPORTING → IMPORTED itself)
    assert transitions == [
        {
            "batch_id": BATCH,
            "to_status": None,
            "expected_status": MigrationStatus.PROFILED,
            "job_id": JOB,
            "cutover_date": CUTOVER,
        }
    ]
    assert fake.audited[0]["action"] == commands.IMPORT_ACTION
    assert fake.audited[0]["after"]["cutover_date"] == "2023-01-31"


def test_import_keeps_an_already_set_equal_cutover_and_refuses_a_different_one(
    monkeypatch: pytest.MonkeyPatch, transitions: list[dict[str, Any]], job_outs: dict[str, Any]
) -> None:
    monkeypatch.setattr(
        commands.repository, "get_batch", lambda _uow, _id: _batch("PROFILED", cutover_date=CUTOVER)
    )
    uow, _ = _uow()
    commands.import_batch(uow, BATCH, _opening())
    assert "cutover_date" not in transitions[0]  # set once: an equal restatement writes nothing
    uow, fake = _uow()
    with pytest.raises(Problem) as refused:
        commands.import_batch(uow, BATCH, _opening(cutover_date=date(2023, 1, 15)))
    assert refused.value.slug == "validation-failed"
    assert refused.value.errors[0].field == "cutover_date"
    assert "set once" in refused.value.errors[0].message
    assert fake.deferred == []


def test_import_validates_the_body_against_the_stored_profile_by_name(
    monkeypatch: pytest.MonkeyPatch, transitions: list[dict[str, Any]], job_outs: dict[str, Any]
) -> None:
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: _batch("PROFILED"))
    uow, fake = _uow()
    with pytest.raises(Problem) as refused:
        commands.import_batch(
            uow,
            BATCH,
            _opening(
                cutover_date=date(2023, 2, 28),  # after the latest legacy period (S07-R-11)
                entity_mapping=[EntityMappingIn(legacy_name="Nobody", entity_code="X")],
                batch_parameters={"migration.nondistinct_mapping": "NOT-AN-OPTION"},
            ),
        )
    assert refused.value.slug == "validation-failed"
    fields = [(error.field, error.rule_id) for error in refused.value.errors]
    assert ("cutover_date", "S07-R-11") in fields
    assert ("entity_mapping[0].legacy_name", "LM-CL-09") in fields
    assert any(field == "batch_parameters.migration.nondistinct_mapping" for field, _ in fields)
    assert fake.deferred == [] and transitions == []
    # without a profile there is nothing to validate against — refused by name
    monkeypatch.setattr(
        commands.repository, "get_batch", lambda _uow, _id: _batch("PROFILED", profile=None)
    )
    with pytest.raises(Problem) as refused:
        commands.import_batch(uow, BATCH, _opening())
    assert "no profile" in refused.value.errors[0].message


def test_import_refuses_a_mode_mismatch_and_replay_by_name(
    monkeypatch: pytest.MonkeyPatch, transitions: list[dict[str, Any]], job_outs: dict[str, Any]
) -> None:
    replay = ReplayImportIn(
        plan=[
            ReplayPlanItemIn(
                file_id=UUID(int=5),
                file_name="SKU SSP Template.xlsx",
                template_code="legacy_sku_ssp",
            )
        ]
    )
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: _batch("PROFILED"))
    uow, fake = _uow()
    with pytest.raises(Problem) as refused:
        commands.import_batch(uow, BATCH, replay)  # a REPLAY body on an OPENING_BALANCES batch
    assert refused.value.slug == "validation-failed" and refused.value.errors[0].field == "mode"
    monkeypatch.setattr(
        commands.repository,
        "get_batch",
        lambda _uow, _id: _batch("PROFILED", mode=MigrationMode.REPLAY.value, cutover_date=None),
    )
    with pytest.raises(Problem) as refused:
        commands.import_batch(uow, BATCH, replay)  # mode (b) is not built: refused, never staged
    assert refused.value.slug == "invalid-transition"
    assert "not available yet" in str(refused.value.detail)
    assert fake.deferred == [] and transitions == []


@pytest.mark.parametrize("status", ["UPLOADED", "PROFILING", "IMPORTING", "IMPORTED", "FAILED"])
def test_import_needs_a_profiled_batch(
    monkeypatch: pytest.MonkeyPatch, transitions: list[dict[str, Any]], status: str
) -> None:
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: _batch(status))
    uow, fake = _uow()
    with pytest.raises(Problem) as refused:
        commands.import_batch(uow, BATCH, _opening())
    assert refused.value.slug == "invalid-transition" and status in str(refused.value.detail)
    assert fake.deferred == [] and transitions == []


def test_import_accepts_a_non_identity_target_and_consolidates_a_shared_target(
    monkeypatch: pytest.MonkeyPatch, transitions: list[dict[str, Any]], job_outs: dict[str, Any]
) -> None:
    # Codex 1227 F1 / F2 through the ACTUAL resolver → command: (a) Mock Entity 1 → AVM-US with
    # AVM-US and Mock Entity 2 present is accepted; the confirmed mapping travels in the params (the
    # import phase applies it at staging — witnessed in test_migration_import_job); (b) both absent,
    # the explicit Mock Entity 1 → Mock Entity 2 plus the implicit identity consolidate to ONE
    # resolved entity named by its code
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: _batch("PROFILED"))
    uow, fake = _uow(answers=_confirmation_answers(entities=("AVM-US", "Mock Entity 2")))
    commands.import_batch(
        uow,
        BATCH,
        _opening(
            entity_mapping=[EntityMappingIn(legacy_name="Mock Entity 1", entity_code="AVM-US")]
        ),
    )
    _kind, params, _binding = fake.deferred[0]
    assert params["entity_mapping"][0]["entity_code"] == "AVM-US"
    assert params["resolved_entities"] == []  # the target exists: nothing to create
    uow, fake = _uow(answers=_confirmation_answers(entities=()))
    commands.import_batch(
        uow,
        BATCH,
        _opening(
            entity_mapping=[
                EntityMappingIn(legacy_name="Mock Entity 1", entity_code="Mock Entity 2")
            ],
            entity_defaults={"time_zone": "UTC"},
        ),
    )
    _kind, params, _binding = fake.deferred[0]
    assert [(r["legacy_name"], r["entity_code"]) for r in params["resolved_entities"]] == [
        ("Mock Entity 2", "Mock Entity 2")
    ]


def test_import_confirms_every_selling_entity_through_the_real_resolver(
    monkeypatch: pytest.MonkeyPatch, transitions: list[dict[str, Any]], job_outs: dict[str, Any]
) -> None:
    # Codex 1106 R2 — through the ACTUAL resolver → command composition over a by-table session:
    # (a) an OMITTED mapping with an absent entity and no defaults is refused by name on
    # entity_defaults.* before deferral; (b) a PARTIAL mapping plus defaults resolves the omitted
    # entity as the identity mapping (legacy text = code) from the defaults; (c) both entities
    # present → nothing to resolve, nothing refused. No fake resolver; no invented values.
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: _batch("PROFILED"))
    # (a)
    uow, fake = _uow(
        answers=_confirmation_answers(
            entities=("Mock Entity 1",), calendars=(CAL_A, UUID(int=0xB2))
        )
    )
    with pytest.raises(Problem) as refused:
        commands.import_batch(uow, BATCH, _opening(entity_mapping=[]))
    fields = {(e.field, e.rule_id) for e in refused.value.errors}
    assert fields == {
        ("entity_defaults.calendar_id", "LM-CL-09"),
        ("entity_defaults.time_zone", "LM-CL-09"),
    }
    assert {e.message for e in refused.value.errors} == {
        "Choose a calendar for Mock Entity 2.",
        "Choose a time zone for Mock Entity 2.",
    }
    assert fake.deferred == [] and transitions == []
    # (b)
    uow, fake = _uow(answers=_confirmation_answers(entities=("Mock Entity 1",)))
    body = _opening(
        entity_mapping=[EntityMappingIn(legacy_name="Mock Entity 1", entity_code="Mock Entity 1")],
        entity_defaults={"time_zone": "Europe/Dublin"},
    )
    commands.import_batch(uow, BATCH, body)
    _kind, params, _binding = fake.deferred[0]
    assert params["resolved_entities"] == [
        {
            "legacy_name": "Mock Entity 2",
            "entity_code": "Mock Entity 2",
            "functional_currency": "USD",
            "calendar_id": str(CAL_A),
            "time_zone": "Europe/Dublin",
        }
    ]
    # (c)
    uow, fake = _uow()
    commands.import_batch(uow, BATCH, _opening(entity_mapping=[]))
    assert fake.deferred[0][1]["resolved_entities"] == []


def test_import_resolves_the_will_be_created_entities_and_carries_them_in_the_params(
    monkeypatch: pytest.MonkeyPatch, transitions: list[dict[str, Any]], job_outs: dict[str, Any]
) -> None:
    # 04 LM-CL-09 rev 1.64 (D-98 candidate 133): the confirmation resolves calendar / time zone /
    # currency per "Will be created" entity; the RESOLVED rows (not the raw mapping alone) and the
    # product flag travel in the job params; a resolution refusal propagates by name, nothing
    # deferred
    from erev_api.domain.migration import prerequisites

    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: _batch("PROFILED"))
    captured: dict[str, Any] = {}

    def fake_resolve(session: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return (
            prerequisites.ResolvedEntity(
                legacy_name="Mock Entity 2",
                code="Mock Entity 2",
                functional_currency="USD",
                calendar_id=UUID(int=0xA1),
                time_zone="UTC",
            ),
        )

    monkeypatch.setattr(commands.prerequisites, "resolve_entities", fake_resolve)
    uow, fake = _uow()
    body = _opening(
        entity_mapping=[
            EntityMappingIn(legacy_name="Mock Entity 1", entity_code="Mock Entity 1"),
            EntityMappingIn(legacy_name="Mock Entity 2", entity_code="Mock Entity 2"),
        ],
        entity_defaults={"time_zone": "UTC"},
        create_missing_products=False,
    )
    commands.import_batch(uow, BATCH, body)
    assert captured["entity_defaults"] == {"calendar_id": None, "time_zone": "UTC"}
    assert captured["create_missing_entities"] is True
    _kind, params, _binding = fake.deferred[0]
    assert params["resolved_entities"] == [
        {
            "legacy_name": "Mock Entity 2",
            "entity_code": "Mock Entity 2",
            "functional_currency": "USD",
            "calendar_id": str(UUID(int=0xA1)),
            "time_zone": "UTC",
        }
    ]
    assert params["create_missing_products"] is False
    assert fake.audited[0]["after"]["resolved_entities"] == params["resolved_entities"]

    def refuse(session: Any, **kwargs: Any) -> Any:
        raise Problem(
            "validation-failed",
            "1 field needs attention.",
            errors=[
                ProblemError(
                    field="entity_mapping[1].time_zone",
                    rule_id="LM-CL-09",
                    message="Choose a time zone for Mock Entity 2.",
                )
            ],
        )

    monkeypatch.setattr(commands.prerequisites, "resolve_entities", refuse)
    uow, fake = _uow()
    with pytest.raises(Problem) as refused:
        commands.import_batch(uow, BATCH, body)
    assert refused.value.errors[0].field == "entity_mapping[1].time_zone"
    assert fake.deferred == [] and len(transitions) == 1  # only the first call deferred / moved


# ---- reconcile -----------------------------------------------------------------------------------


def test_reconcile_defers_the_reconciliation_job_from_imported_only(
    monkeypatch: pytest.MonkeyPatch, transitions: list[dict[str, Any]], job_outs: dict[str, Any]
) -> None:
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: _batch("IMPORTED"))
    uow, fake = _uow()
    out = commands.reconcile_batch(uow, BATCH)
    assert out.id == JOB
    assert fake.deferred[0][0] is JobKind.MIGRATION_RECONCILE
    assert fake.deferred[0][1] == {"migration_id": str(BATCH)}
    assert transitions[0]["expected_status"] is MigrationStatus.IMPORTED
    assert transitions[0]["to_status"] is None and transitions[0]["job_id"] == JOB
    assert fake.audited[0]["action"] == commands.RECONCILE_ACTION
    for status in ("PROFILED", "RECONCILED", "SUBMITTED", "CANCELLED"):
        monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id, s=status: _batch(s))
        with pytest.raises(Problem, match="reconciling needs a IMPORTED"):
            commands.reconcile_batch(_uow()[0], BATCH)


# ---- cancel --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    ["UPLOADED", "PROFILING", "PROFILED", "IMPORTING", "IMPORTED", "RECONCILED", "SUBMITTED"],
)
def test_cancel_moves_any_non_terminal_status_to_cancelled(
    monkeypatch: pytest.MonkeyPatch,
    transitions: list[dict[str, Any]],
    job_outs: dict[str, Any],
    status: str,
) -> None:
    rows = iter([_batch(status, job_id=JOB), _batch("CANCELLED", job_id=JOB)])
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: next(rows))
    uow, fake = _uow()
    row = commands.cancel_batch(uow, BATCH)
    assert row["status"] == "CANCELLED"
    assert transitions == [
        {
            "batch_id": BATCH,
            "to_status": MigrationStatus.CANCELLED,
            "expected_status": MigrationStatus(status),
            "finished_at": NOW,
        }
    ]
    assert job_outs["cancelled"] == [JOB]  # the caller's QUEUED job is cancelled with the batch
    assert fake.audited[0]["action"] == commands.CANCEL_ACTION
    assert fake.audited[0]["before"] == {"status": status}


@pytest.mark.parametrize("status", ["PROMOTED", "FAILED", "CANCELLED"])
def test_cancel_refuses_a_terminal_status_by_name(
    monkeypatch: pytest.MonkeyPatch, transitions: list[dict[str, Any]], status: str
) -> None:
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: _batch(status))
    with pytest.raises(Problem) as refused:
        commands.cancel_batch(_uow()[0], BATCH)
    assert refused.value.slug == "invalid-transition" and "cannot be cancelled" in str(
        refused.value.detail
    )
    assert transitions == []


def test_cancel_leaves_a_finished_or_foreign_job_alone(
    monkeypatch: pytest.MonkeyPatch, transitions: list[dict[str, Any]], job_outs: dict[str, Any]
) -> None:
    rows = iter([_batch("PROFILED", job_id=JOB), _batch("CANCELLED")])
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: next(rows))
    job_outs["out"] = _job_out(JobState.SUCCEEDED)
    commands.cancel_batch(_uow()[0], BATCH)
    assert job_outs["cancelled"] == []  # finished: nothing to cancel
    rows = iter([_batch("PROFILING", job_id=JOB), _batch("CANCELLED")])
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: next(rows))
    job_outs["out"] = _job_out(JobState.RUNNING, created_by=UUID(int=8))
    commands.cancel_batch(_uow()[0], BATCH)
    assert job_outs["cancelled"] == []  # another initiator's job fails closed on its own transition


# ---- queries -------------------------------------------------------------------------------------


def test_migration_out_maps_the_row_with_the_profile_key_figures_and_unexplained_count() -> None:
    out = queries.migration_out(
        _batch("RECONCILED", cutover_date=CUTOVER), names={USER: "Maya"}, unexplained=2
    )
    assert out.id == BATCH and out.status is MigrationStatus.RECONCILED
    assert out.cutover_date == CUTOVER and out.unexplained_count == 2 and out.row_version == 3
    assert out.profile is not None and out.profile.contracts == 4
    assert out.profile.latest_current_period == CUTOVER
    assert out.created_by == ActorOut(id=USER, kind=PrincipalKind.USER, display_name="Maya")
    assert queries.migration_out(_batch(profile=None), names={}, unexplained=None).profile is None
    assert routes.migration_etag(out) == 'W/"r3"' or routes.migration_etag(out) == '"r3"'


def test_unexplained_counts_groups_lines_outside_tolerance_without_deviation_ref() -> None:
    other = UUID(int=0x49)
    session = _Session(_Result(rows=((BATCH, 2),)))
    counts = queries.unexplained_counts(session, [BATCH, other, BATCH])  # type: ignore[arg-type]
    assert counts == {BATCH: 2, other: 0}
    statement = session.calls[0][0]
    assert "migration_reconciliation_line.is_within_tolerance IS false" in statement
    assert "migration_reconciliation_line.deviation_ref IS NULL" in statement
    # Codex 0727: an exception link explains nothing — the predicate never looks at it
    assert "exception_item_id" not in statement
    assert "GROUP BY erev.migration_reconciliation_line.migration_batch_id" in statement
    assert queries.unexplained_counts(session, []) == {}  # type: ignore[arg-type]


def test_legacy_rows_cursor_is_the_last_source_rowid_of_a_full_page() -> None:
    rows = [{"source_rowid": 3}, {"source_rowid": 7}]
    assert queries.legacy_rows_cursor(rows, limit=2) == "7"
    assert queries.legacy_rows_cursor(rows, limit=3) is None
    assert queries.legacy_rows_cursor([], limit=1) is None


def test_a_reconciliation_line_states_its_stored_values_as_plain_decimal_text() -> None:
    """04 API-C-06: an ``erev.exact`` value is a string with trailing zeros trimmed and no
    exponent. The driver returns a NUMERIC(38,18) at its full scale, where ``str`` writes a zero
    as ``0E-18`` and a difference below one millionth as ``3.3333333333E-8`` — texts the response
    model refuses, so the line of every measure that reconciles failed the whole answer (500).
    The values below are the ``Decimal`` objects the driver hands over."""

    def stored(text: str) -> Decimal:
        return Decimal(text).quantize(Decimal(1).scaleb(-18))

    reconciled = {
        "id": UUID(int=0x51),
        "contract_external_id": "Contract 1",
        "obligation_key": None,
        "measure": "TRANSACTION_PRICE",
        "source_value": stored("1300"),
        "erev_value": stored("1300"),
        "difference": stored("0"),
        "tolerance": stored("0.0001"),
        "is_within_tolerance": True,
    }
    assert str(reconciled["difference"]) == "0E-18"  # what the route answered before
    line = queries.reconciliation_line_out(reconciled, {})
    assert (line.source_value, line.erev_value, line.difference, line.tolerance) == (
        "1300",
        "1300",
        "0",
        "0.0001",
    )
    small = queries.reconciliation_line_out(
        reconciled
        | {
            "obligation_key": "POB 1",
            "measure": "ALLOCATION",
            "source_value": stored("433.333333333333333333"),
            "erev_value": stored("433.3333333"),
            "difference": stored("0.000000033333333333"),
        },
        {},
    )
    assert (small.source_value, small.erev_value, small.difference) == (
        "433.333333333333333333",
        "433.3333333",
        "0.000000033333333333",
    )
    over = {"erev_value": stored("1300.5"), "difference": stored("-0.5")}
    short = queries.reconciliation_line_out(reconciled | over | {"is_within_tolerance": False}, {})
    assert (short.erev_value, short.difference) == ("1300.5", "-0.5")


# ---- the MIGRATION_IMPORT phase dispatch --------------------------------------------------------


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/legacy_db/ASC606-shipped-step04.db"


class _JobContext:
    """The slice of ``JobContext`` the handler uses: the job id, the runtime, one unit of work."""

    def __init__(self, uow: Any) -> None:
        self.job_id = JOB
        self.runtime = SimpleNamespace(files=object(), keyring=object())
        self._uow = uow

    def unit_of_work(self) -> Any:
        uow = self._uow

        class _Scope:
            def __enter__(self) -> Any:
                return uow

            def __exit__(self, *_exc: Any) -> None:
                return None

        return _Scope()


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _spool_of(copy: Path) -> Any:
    """A fake ``spooled_source`` with the real lifetime rule: the path lives for the block and is
    removed on exit, on success or failure."""
    from contextlib import contextmanager

    @contextmanager
    def spool(_jc: Any, _uow: Any, _batch: Any) -> Any:
        try:
            yield copy
        finally:
            copy.unlink(missing_ok=True)

    return spool


def _never_opened(_jc: Any, _uow: Any, _batch: Any) -> Any:
    raise AssertionError("the source must not be reopened")


def test_profile_phase_profiles_the_spooled_copy_and_moves_profiling_to_profiled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    copy = tmp_path / "spooled.db"
    copy.write_bytes(FIXTURE.read_bytes())
    digest = _sha256(FIXTURE)
    seen: list[dict[str, Any]] = []
    batch = _batch("PROFILING", job_id=JOB, source_sha256=digest, profile=None)
    monkeypatch.setattr(jobs.repository, "get_batch", lambda _uow, _id: batch)
    monkeypatch.setattr(
        jobs.repository,
        "transition",
        lambda _uow, batch_id, **kwargs: seen.append({"batch_id": batch_id, **kwargs}) or {},
    )
    monkeypatch.setattr(jobs, "spooled_source", _spool_of(copy))
    uow, fake = _uow()
    outcome = jobs.import_migration(
        _JobContext(uow), {"migration_id": str(BATCH), "phase": "PROFILE"}
    )  # type: ignore[arg-type]
    assert outcome.state == "SUCCEEDED" and fake.commits == 1
    profile = outcome.result["profile"]
    # SCREENS_B §10.3 "Key figures" of WLD-F-15 (PRD J-20.1)
    assert profile["source_sha256"] == digest and profile["contract_live_rows"] == 24
    assert profile["contracts"] == 4 and profile["legacy_pob_rows"] == 16
    assert profile["sku_ssp_rows"] == 7 and profile["ssp_versions"] == ["2023-01-01"]
    assert profile["selling_entities"] == ["Mock Entity 1", "Mock Entity 2"]
    assert profile["latest_current_period"] == "2023-01-31"
    assert seen == [
        {
            "batch_id": BATCH,
            "to_status": MigrationStatus.PROFILED,
            "expected_status": MigrationStatus.PROFILING,
            "profile": profile,
            "finished_at": NOW,
        }
    ]
    assert not copy.exists()  # the spool lifetime ended: removed after profiling (REQ-MIG-004)
    # Codex 0727 (b): success re-entry — the SAME job retried after its commit returns the stored
    # profile from the row, opens no source, moves nothing
    seen.clear()
    monkeypatch.setattr(
        jobs.repository,
        "get_batch",
        lambda _uow, _id: _batch("PROFILED", job_id=JOB, source_sha256=digest, profile=profile),
    )
    monkeypatch.setattr(jobs, "spooled_source", _never_opened)
    again = jobs.import_migration(
        _JobContext(_uow()[0]), {"migration_id": str(BATCH), "phase": "PROFILE"}
    )  # type: ignore[arg-type]
    assert again.state == "SUCCEEDED" and again.result["profile"]["recovered"] is True
    assert again.result["profile"]["contracts"] == 4 and seen == []


def test_profile_phase_refuses_a_changed_source_or_a_foreign_job_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    copy = tmp_path / "spooled.db"
    copy.write_bytes(FIXTURE.read_bytes())
    seen: list[Any] = []
    monkeypatch.setattr(jobs.repository, "transition", lambda *_a, **_k: seen.append(1))
    monkeypatch.setattr(jobs, "spooled_source", _spool_of(copy))
    # the stored object's digest is not the batch's source digest — refused by name (REQ-MIG-004)
    monkeypatch.setattr(
        jobs.repository,
        "get_batch",
        lambda _uow, _id: _batch("PROFILING", job_id=JOB, source_sha256="b" * 64),
    )
    with pytest.raises(Problem, match="not the migration's source digest"):
        jobs.import_migration(
            _JobContext(_uow()[0]), {"migration_id": str(BATCH), "phase": "PROFILE"}
        )  # type: ignore[arg-type]
    # another job's PROFILING claim — refused
    copy.write_bytes(FIXTURE.read_bytes())
    monkeypatch.setattr(
        jobs.repository,
        "get_batch",
        lambda _uow, _id: _batch("PROFILING", job_id=UUID(int=5), source_sha256=_sha256(FIXTURE)),
    )
    with pytest.raises(Problem, match="not the migration's job"):
        jobs.import_migration(
            _JobContext(_uow()[0]), {"migration_id": str(BATCH), "phase": "PROFILE"}
        )  # type: ignore[arg-type]
    # not PROFILING — refused by name
    copy.write_bytes(FIXTURE.read_bytes())
    monkeypatch.setattr(
        jobs.repository, "get_batch", lambda _uow, _id: _batch("UPLOADED", job_id=JOB)
    )
    with pytest.raises(Problem, match="profiling needs an UPLOADED"):
        jobs.import_migration(
            _JobContext(_uow()[0]), {"migration_id": str(BATCH), "phase": "PROFILE"}
        )  # type: ignore[arg-type]
    assert seen == []
    # an unknown phase never reaches a unit of work
    with pytest.raises(Problem, match="not one of"):
        jobs.import_migration(_JobContext(_uow()[0]), {"migration_id": str(BATCH), "phase": "X"})  # type: ignore[arg-type]


def test_profile_failed_moves_a_profiling_batch_to_failed_and_leaves_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(
        jobs.repository,
        "transition",
        lambda _uow, batch_id, **kwargs: seen.append({"batch_id": batch_id, **kwargs}) or {},
    )
    problem = {"type": "about:blank", "status": 500, "instance": f"/api/v1/jobs/{JOB}"}
    monkeypatch.setattr(
        jobs.repository, "get_batch", lambda _uow, _id: _batch("PROFILING", job_id=JOB)
    )
    jobs.profile_failed(_uow()[0], {"migration_id": str(BATCH), "phase": "PROFILE"}, problem)
    assert seen[0]["to_status"] is MigrationStatus.FAILED
    # operation-bound (Codex 0727 (b)): a PROFILING claim held by ANOTHER job is not settled here
    monkeypatch.setattr(
        jobs.repository, "get_batch", lambda _uow, _id: _batch("PROFILING", job_id=UUID(int=5))
    )
    jobs.profile_failed(_uow()[0], {"migration_id": str(BATCH), "phase": "PROFILE"}, problem)
    assert len(seen) == 1
    assert seen[0]["expected_status"] is MigrationStatus.PROFILING and seen[0]["problem"] == problem
    for status in ("PROFILED", "IMPORTED", "CANCELLED"):
        monkeypatch.setattr(jobs.repository, "get_batch", lambda _uow, _id, s=status: _batch(s))
        jobs.profile_failed(_uow()[0], {"migration_id": str(BATCH), "phase": "PROFILE"}, problem)
    assert len(seen) == 1  # a batch past PROFILING is never degraded by the profiling hook


def test_spooled_source_removes_a_partial_copy_when_the_read_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Codex 0801 R4: the spool lifetime encloses creation and copy, not only the profiling — a
    # stream failing midway leaves no temporary file behind and the failure propagates
    import tempfile

    from erev_api.files import store as file_store

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    class _BrokenStream:
        def __init__(self) -> None:
            self.reads = 0

        def read(self, _size: int) -> bytes:
            self.reads += 1
            if self.reads == 1:
                return b"SQLite format 3\x00" + b"x" * 64
            raise OSError("stream failed midway")

    stream = _BrokenStream()
    monkeypatch.setattr(file_store, "open_file", lambda *_a, **_k: (_stored(), stream))
    jc = _JobContext(_uow()[0])
    with pytest.raises(OSError, match="midway"):
        with jobs.spooled_source(jc, _uow()[0], _batch("PROFILING")):  # type: ignore[arg-type]
            raise AssertionError("the block must not run on a failed copy")
    assert stream.reads == 2
    assert [p for p in tmp_path.iterdir() if p.suffix == ".db"] == []  # the partial copy is gone
    # and a worker without a file store or key ring refuses before any spool exists
    jc.runtime = SimpleNamespace(files=None, keyring=None)
    with pytest.raises(Problem, match="no file store or key ring"):
        with jobs.spooled_source(jc, _uow()[0], _batch("PROFILING")):  # type: ignore[arg-type]
            pass
    assert [p for p in tmp_path.iterdir() if p.suffix == ".db"] == []


def test_profile_re_entry_checks_the_stored_profiles_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Codex 0801 R3: retained-success recognition validates the stored profile's digest against
    # the batch's source digest before returning it; a mismatch is refused by name, nothing moved
    seen: list[Any] = []
    monkeypatch.setattr(jobs.repository, "transition", lambda *_a, **_k: seen.append(1))
    monkeypatch.setattr(jobs, "spooled_source", _never_opened)
    stale = dict(PROFILE, source_sha256="b" * 64)
    monkeypatch.setattr(
        jobs.repository,
        "get_batch",
        lambda _uow, _id: _batch("PROFILED", job_id=JOB, source_sha256="a" * 64, profile=stale),
    )
    with pytest.raises(Problem, match="not the migration's source digest"):
        jobs.import_migration(
            _JobContext(_uow()[0]), {"migration_id": str(BATCH), "phase": "PROFILE"}
        )  # type: ignore[arg-type]
    assert seen == []


# ---- the router's shape -------------------------------------------------------------------------


def _routes() -> dict[str, APIRoute]:
    return {
        route.operation_id: route
        for route in routes.router.routes
        if isinstance(route, APIRoute) and route.operation_id
    }


def test_field_mapping_read_serves_the_71_rows_verbatim_before_the_uuid_route() -> None:
    # D-98 133 AMENDMENT 1 (b): the static read the SF-19 "Field mapping" table renders; its rows
    # are field_mapping.FIELD_MAPPING in legacy order with the exact legacy names; the literal path
    # is declared before /migrations/{migration_id}
    from erev_api.domain.migration import field_mapping
    from erev_api.domain.reports import legacy_columns

    out = routes.migrations_field_mapping(cast(Any, object()))
    assert len(out.rows) == 71
    assert [row.legacy_column for row in out.rows] == list(legacy_columns.NAMES)
    assert [row.id for row in out.rows] == [f"LM-CL-{n:02d}" for n in range(1, 72)]
    assert [row.target for row in out.rows] == [item.target for item in field_mapping.FIELD_MAPPING]
    assert all(row.rule for row in out.rows)
    assert out.rows[2].legacy_column == "SKU Name" and out.rows[2].target.startswith("product.")
    ordered = [
        route.path
        for route in routes.router.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/migrations")
    ]
    assert ordered.index("/api/v1/migrations/field-mapping") < ordered.index(
        "/api/v1/migrations/{migration_id}"
    )
    assert _routes()["migrations_field_mapping"].status_code in (200, None)


def test_router_serves_the_ten_api_r_48_routes_and_not_submit_promotion() -> None:
    found = _routes()
    assert set(found) == {
        "migrations_list",
        "migrations_create",
        "migrations_get",
        "migrations_field_mapping",
        "migrations_profile",
        "migrations_import",
        "migrations_reconcile",
        "migrations_cancel",
        "migrations_reconciliation_lines",
        "migrations_legacy_rows",
    }
    paths = {(next(iter(route.methods)), route.path) for route in found.values()}
    assert ("POST", "/api/v1/migrations/{migration_id}/submit-promotion") not in paths  # D-98 129
    assert all(route.tags == ["API-R-48 Migrations"] for route in found.values())
    # DG-CMD-12 / DG-KRN-JOB-09: 201 for creation, 202 where a job does the work, 200 otherwise
    assert found["migrations_create"].status_code == 201
    assert {
        found[name].status_code
        for name in ("migrations_profile", "migrations_import", "migrations_reconcile")
    } == {202}
    assert found["migrations_cancel"].status_code in (200, None)


def _factories(route: APIRoute) -> set[str]:
    """The helpers that built the route's dependencies (``require``, ``command``, …), walking the
    dependant tree as tests/architecture/test_routes.py does (DG-ARC-04)."""

    def walk(dependant: Any) -> Any:
        for dependency in getattr(dependant, "dependencies", ()):
            call = dependency.call
            if call is not None:
                qualname = getattr(call, "__qualname__", "")
                if ".<locals>." in qualname:
                    yield qualname.split(".<locals>.", 1)[0]
            yield from walk(dependency)

    return set(walk(route.dependant))


def test_every_write_route_is_a_migration_run_command_and_every_read_requires_it() -> None:
    # DG-KRN-IDEM-01 / DG-KRN-AUTH-03: one permission (04 API-R-48), commands on every write
    for name, route in _routes().items():
        factories = _factories(route)
        if route.methods & {"POST", "PUT", "PATCH", "DELETE"}:
            assert "command" in factories, name
        else:
            assert "require" in factories, name
        # DG-KRN-AUTH-03 records the permission; command routes also carry the IdempotencyKey ref
        assert route.openapi_extra["x-erev-permission"] == "migration.run", name
    spec = routes.MIGRATION_LIST
    assert set(spec.filters) == {"status", "mode", "created_from"} and spec.default_sort == "-id"
    assert set(spec.sort_keys) == {"id", "migration_no", "created_at"}
    assert spec.filters["status"].choices == frozenset(s.value for s in MigrationStatus)
    assert spec.filters["mode"].choices == frozenset(m.value for m in MigrationMode)


# --- 04 rev 1.72 (D-98 133 AMENDMENT 4 option A2): the legacy SSP replay request at /import
# ----------------


def test_import_submits_the_replay_request_and_carries_its_id_in_the_params(
    monkeypatch: pytest.MonkeyPatch,
    transitions: list[dict[str, Any]],
    job_outs: dict[str, Any],
    replay_requests: list[dict[str, Any]],
) -> None:
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: _batch("PROFILED"))
    uow, fake = _uow()
    commands.import_batch(uow, BATCH, _opening())
    assert replay_requests == [
        {
            "subject_type": ApprovalSubjectType.MIGRATION_SSP_REPLAY,
            "subject_id": BATCH,
            "summary": "Legacy SSP replay of migration MIG-000001",
        }
    ]
    _kind, params, _binding = fake.deferred[0]
    assert params["ssp_replay_request_id"] == str(REQUEST)
    assert params["sku_ssp_sha256"] == "b" * 64
    after = fake.audited[0]["after"]
    assert after["ssp_replay_request_id"] == str(REQUEST) and after["sku_ssp_sha256"] == "b" * 64


def test_import_refuses_by_name_while_the_profile_holds_sku_ssp_findings(
    monkeypatch: pytest.MonkeyPatch,
    transitions: list[dict[str, Any]],
    job_outs: dict[str, Any],
    replay_requests: list[dict[str, Any]],
) -> None:
    findings = [
        {
            "row": 3,
            "code": "SSP_PERCENT_OUT_OF_RANGE",
            "column": "Midpoint Discount Percentage",
            "message": "Midpoint Discount Percentage must be at least 0 and below 1.",
        },
        {
            "row": 5,
            "code": "REQUIRED_VALUE_BLANK",
            "column": "SKU Unit List Price",
            "message": "SKU Unit List Price is required.",
        },
    ]
    batch = _batch("PROFILED", profile={**PROFILE, "sku_ssp_findings": findings})
    monkeypatch.setattr(commands.repository, "get_batch", lambda _uow, _id: batch)
    uow, fake = _uow()
    with pytest.raises(Problem) as excinfo:
        commands.import_batch(uow, BATCH, _opening())
    fields = [(e.field, e.rule_id) for e in excinfo.value.errors]
    assert fields == [
        ("sku_ssp[3].Midpoint Discount Percentage", "SSP_PERCENT_OUT_OF_RANGE"),
        ("sku_ssp[5].SKU Unit List Price", "REQUIRED_VALUE_BLANK"),
    ]
    assert replay_requests == [] and fake.deferred == [] and transitions == []  # nothing opened
