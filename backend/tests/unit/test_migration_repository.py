"""``domain.migration.repository`` over a fake session (BUILD_SPEC LMG-1, LMG-3; 04 §17; PRD
BR-MIG-01, ERR-19, SM-12). The statements are compiled for PostgreSQL and recorded; no database.
The database behaviour (grants, DB-03 trigger, CHECKs, the partial unique index) is
``tests/pg/test_t_mig_tables.py`` — written, not run on the lane.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType, SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from erev_api.domain.migration import reconciliation, repository
from erev_api.domain.migration.legacy_db import LegacyRow
from erev_api.domain.reports import legacy_columns
from erev_api.enums import MigrationMode, MigrationStatus, PrincipalKind
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError

TENANT = UUID(int=1)
BATCH = UUID(int=3)
NOW = datetime(2026, 9, 20, 4, 0, tzinfo=UTC)


class _Result:
    def __init__(self, *, first: Any = None, rows: tuple[Any, ...] = (), scalar: Any = None):
        self._first, self._rows, self._scalar = first, rows, scalar

    def first(self) -> Any:
        return self._first

    def mappings(self) -> _Result:
        return self

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalar_one(self) -> Any:
        return self._scalar


class _Savepoint:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    def rollback(self) -> None:
        self._log.append("rollback")

    def commit(self) -> None:
        self._log.append("commit")


class _Session:
    """Records compiled statements; a queued ``Exception`` is raised in place of a result."""

    def __init__(self, *results: _Result | Exception) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, Any]] = []
        self.savepoints: list[str] = []

    def execute(self, statement: Any, params: Any = None) -> _Result:
        self.calls.append((str(statement.compile(dialect=postgresql.dialect())), params))
        outcome = self.results.pop(0) if self.results else _Result()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def begin_nested(self) -> _Savepoint:
        self.savepoints.append("begin")
        return _Savepoint(self.savepoints)


class _PgError(Exception):
    """A psycopg-shaped driver error: ``sqlstate`` and ``diag.constraint_name``."""

    def __init__(self, sqlstate: str, message: str, constraint: str | None = None) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate
        self.diag = SimpleNamespace(constraint_name=constraint)


def _db_error(sqlstate: str, message: str, constraint: str | None = None) -> DBAPIError:
    return DBAPIError(
        "INSERT INTO erev.migration_batch", {}, _PgError(sqlstate, message, constraint)
    )


def _uow(*results: _Result) -> tuple[UnitOfWork, _Session]:
    session = _Session(*results)
    uow = SimpleNamespace(
        session=session,
        now=NOW,
        principal=SimpleNamespace(id=UUID(int=9), kind=PrincipalKind.SYSTEM, tenant_id=TENANT),
    )
    return cast(UnitOfWork, uow), session


def _legacy_row(rowid: int = 1, key: str = "POB #1") -> LegacyRow:
    values: dict[str, str | None] = {c.name: None for c in legacy_columns.CONTRACT_LIVE}
    values.update(
        {
            "Contract Unique Name": "Contract 1",
            "POB Unique ID": key,
            "SKU Name": "Hardware 1",
            "Current Period": "2023-01-01",
            "Processing Time Log": "2023-01-15 09:11:44",
            "Record Unique ID without time": f"Contract 1/{key}",
            "Record Unique ID": f"2023-01-15 09:11:44 Contract 1/{key}",
        }
    )
    return LegacyRow(rowid, MappingProxyType(values))


def test_create_batch_refuses_an_active_duplicate() -> None:
    # BR-MIG-01 / ERR-19 (legacy 01 TC-setup-25): the same database and mode again → 409 with the
    # earlier migration's number and date; no INSERT is issued.
    earlier = SimpleNamespace(
        migration_no="MIG-000001", created_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    )
    uow, session = _uow(_Result(first=earlier))
    with pytest.raises(Problem) as refused:
        repository.create_batch(
            uow,
            mode=MigrationMode.OPENING_BALANCES,
            source_file_id=UUID(int=2),
            source_sha256="ab" * 32,
            cutover_date=date(2023, 1, 31),
        )
    assert refused.value.slug == "duplicate-import"
    assert refused.value.detail == (
        "This legacy database was already imported in migration MIG-000001 on 2026-09-01."
    )
    assert (refused.value.errors[0].field, refused.value.errors[0].rule_id) == (
        "source_file_id",
        "IMPORT_FILE_DUPLICATE",
    )
    assert len(session.calls) == 1 and session.calls[0][0].startswith("SELECT")


def test_create_batch_numbers_and_stamps_the_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        repository.numbering, "next_number", lambda uow, code, scope_key="": f"{code[:3]}-000002"
    )
    uow, session = _uow(_Result(first=None))
    values = repository.create_batch(
        uow,
        mode=MigrationMode.OPENING_BALANCES,
        source_file_id=UUID(int=2),
        source_sha256="ab" * 32,
        cutover_date=date(2023, 1, 31),
    )
    assert values["migration_no"] == "MIG-000002"
    assert (values["mode"], values["status"]) == ("OPENING_BALANCES", "UPLOADED")
    assert values["import_upload_ids"] == [] and values["profile"] is None
    assert values["created_by"] == UUID(int=9) and values["created_by_kind"] == "SYSTEM"
    assert values["updated_at"] == NOW and values["cutover_date"] == date(2023, 1, 31)
    assert values["tenant_id"] == TENANT
    assert session.calls[1][0].startswith("INSERT INTO erev.migration_batch")
    # a replay batch takes no cutover date and may name its sandbox
    uow, _ = _uow(_Result(first=None))
    replay = repository.create_batch(
        uow,
        mode=MigrationMode.REPLAY,
        source_file_id=UUID(int=2),
        source_sha256="cd" * 32,
        sandbox_tenant_id=UUID(int=7),
    )
    assert replay["cutover_date"] is None and replay["sandbox_tenant_id"] == UUID(int=7)


@pytest.mark.parametrize(
    ("mode", "cutover"),
    [(MigrationMode.REPLAY, date(2023, 1, 31))],  # D-98 cand. 128: only REPLAY + date is refused
)
def test_create_batch_mode_and_cutover_must_agree(
    mode: MigrationMode, cutover: date | None
) -> None:
    uow, session = _uow()
    with pytest.raises(Problem) as refused:
        repository.create_batch(
            uow,
            mode=mode,
            source_file_id=UUID(int=2),
            source_sha256="ab" * 32,
            cutover_date=cutover,
        )
    assert refused.value.slug == "validation-failed"
    assert refused.value.errors[0].field == "cutover_date"


def test_create_batch_admits_an_opening_balances_batch_without_a_cutover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 04 T-MIG-01 rev 1.60 in place (D-98 candidate 128; Codex 0727): the cutover is bound once at
    # /import — creation carries NULL and the repository's early refusal admits it
    monkeypatch.setattr(repository, "_active_duplicate", lambda *_a, **_k: None)
    monkeypatch.setattr(repository.numbering, "next_number", lambda _uow, _series: "MIG-000009")
    uow, session = _uow(_Result())
    values = repository.create_batch(
        uow,
        mode=MigrationMode.OPENING_BALANCES,
        source_file_id=UUID(int=2),
        source_sha256="a" * 64,
    )
    assert values["cutover_date"] is None and values["status"] == "UPLOADED"
    assert [call[0].split()[0] for call in session.calls] == ["INSERT"]


def test_transition_validates_in_python_before_any_sql() -> None:
    uow, session = _uow()
    with pytest.raises(Problem) as refused:
        repository.transition(
            uow,
            BATCH,
            to_status=MigrationStatus.PROMOTED,
            expected_status=MigrationStatus.UPLOADED,
        )
    assert refused.value.slug == "invalid-transition" and session.calls == []
    with pytest.raises(Problem) as frozen:
        repository.transition(
            uow, BATCH, to_status=None, expected_status=MigrationStatus.UPLOADED, source_sha256="x"
        )
    assert frozen.value.slug == "invalid-transition" and session.calls == []
    # a valid step issues one conditional UPDATE … RETURNING and stamps SC-M
    updated = {"id": BATCH, "status": "PROFILING", "row_version": 2}
    uow, session = _uow(_Result(rows=(updated,)))
    row = repository.transition(
        uow,
        BATCH,
        to_status=MigrationStatus.PROFILING,
        expected_status=MigrationStatus.UPLOADED,
        job_id=UUID(int=5),
    )
    assert row["status"] == "PROFILING"
    ((statement, _),) = session.calls
    assert statement.startswith("UPDATE erev.migration_batch SET")
    assert "updated_at" in statement and "job_id" in statement and "RETURNING" in statement


def test_legacy_rows_are_stored_verbatim_with_their_digest() -> None:
    uow, session = _uow()
    first, second = _legacy_row(1), _legacy_row(2, "POB #2")
    values = repository.legacy_row_values(uow, BATCH, first)
    assert values["label"] == "migrated, unattributed"
    assert values["legacy_row_sha256"] == first.sha256 and len(values["legacy_row"]) == 71
    assert (values["contract_external_id"], values["obligation_key"], values["product_code"]) == (
        "Contract 1",
        "POB #1",
        "Hardware 1",
    )
    assert values["current_period"] == date(2023, 1, 1) and values["source_rowid"] == 1
    assert values["record_unique_id"] == "2023-01-15 09:11:44 Contract 1/POB #1"
    assert values["contract_id"] is None and values["created_by_kind"] == "SYSTEM"
    assert repository.insert_legacy_rows(uow, BATCH, [first, second]) == 2
    ((statement, params),) = session.calls
    assert statement.startswith("INSERT INTO erev.migrated_legacy_row") and len(params) == 2
    assert repository.insert_legacy_rows(uow, BATCH, []) == 0 and len(session.calls) == 1


def test_reconciliation_lines_are_written_once_per_batch() -> None:
    source = {
        ("Contract 1", None, "TRANSACTION_PRICE"): Fraction(1300),
        ("Contract 3", "POB #5", "ORIGINAL_ALLOCATION"): Fraction(0),
    }
    erev = {
        ("Contract 1", None, "TRANSACTION_PRICE"): Fraction(1300)
        + Fraction(Decimal("0.00010000000004")),
        ("Contract 3", "POB #5", "ORIGINAL_ALLOCATION"): Fraction(Decimal("1268.1139")),
    }
    index = reconciliation.DeviationIndex(
        {
            ("Contract 3", "POB #5", "ORIGINAL_ALLOCATION"): reconciliation.Deviation(
                "DEV-052", Fraction(0), Fraction(Decimal("1268.1139"))
            )
        }
    )
    lines = reconciliation.lines(source, erev, index)
    uow, session = _uow(_Result(scalar=0))
    exception = UUID(int=11)
    written = repository.insert_reconciliation_lines(
        uow, BATCH, lines, exception_items={lines[0].key: exception}
    )
    assert written == 2
    (_, _), (statement, params) = session.calls
    assert statement.startswith("INSERT INTO erev.migration_reconciliation_line")
    unexplained, explained = params
    assert unexplained["measure"] == "TRANSACTION_PRICE"
    assert unexplained["difference"] == Decimal("0.00010000000004")  # exact, never rounded
    assert unexplained["is_within_tolerance"] is False
    assert unexplained["exception_item_id"] == exception and unexplained["deviation_ref"] is None
    assert explained["measure"] == "ORIGINAL_ALLOCATION"
    assert explained["deviation_ref"] == "DEV-052" and explained["exception_item_id"] is None
    assert explained["erev_value"] == Decimal("1268.1139") and explained["tolerance"] == Decimal(
        "0.0001"
    )
    # the table is IM-A: a batch that already holds lines is refused
    uow, session = _uow(_Result(scalar=3))
    with pytest.raises(Problem) as refused:
        repository.insert_reconciliation_lines(
            uow, BATCH, lines, exception_items={lines[0].key: exception}
        )
    assert refused.value.slug == "invalid-transition" and len(session.calls) == 1


def test_readers_return_plain_mappings() -> None:
    uow, session = _uow(_Result(rows=()))
    with pytest.raises(Problem) as missing:
        repository.get_batch(uow, BATCH)
    assert missing.value.slug == "not-found"
    row = {"id": BATCH, "migration_no": "MIG-000001", "status": "UPLOADED"}
    uow, session = _uow(_Result(rows=(row,)), _Result(rows=(row,)), _Result(rows=()), _Result())
    assert repository.get_batch(uow, BATCH) == row
    assert repository.list_batches(uow) == [row]
    assert repository.reconciliation_rows(uow, BATCH) == []
    assert repository.legacy_rows(uow, BATCH, after_rowid=10, limit=5) == []
    assert "ORDER BY" in session.calls[1][0] and "DESC" in session.calls[1][0]
    assert "NULLS FIRST" in session.calls[2][0]
    assert "source_rowid >" in session.calls[3][0] and "LIMIT" in session.calls[3][0]


def test_unexplained_lines_need_their_exception_items() -> None:
    # Codex TMIG-R1 (PRODUCTION-F-LMG-TMIG-REVIEW-1b567e9, D-98 candidate 52), exact input: a
    # REVENUE_CUM line source 1 / eRev 2 (difference 1 > 0.0001, needs_exception, no deviation) and
    # no exception_items. On 6ed10ec7 the call returned 1 and submitted exception_item_id = None;
    # 04 T-MIG-03 requires the link, so the whole set is refused before any insert.
    key = ("C1", "P1", "REVENUE_CUM")
    lines = reconciliation.lines({key: Fraction(1)}, {key: Fraction(2)})
    assert lines[0].needs_exception
    uow, session = _uow(_Result(scalar=0))
    with pytest.raises(Problem) as refused:
        repository.insert_reconciliation_lines(uow, BATCH, lines)
    assert refused.value.slug == "validation-failed"
    assert refused.value.errors[0].field == "lines[line:C1:P1:REVENUE_CUM].exception_item_id"
    assert refused.value.errors[0].rule_id == "T-MIG-03"
    assert session.calls == []  # validated before any SQL: no count, no INSERT
    # a missing item among several is named per line, still nothing submitted
    other = ("C1", "P2", "BILLED_CUM")
    two = reconciliation.lines(
        {key: Fraction(1), other: Fraction(5)}, {key: Fraction(2), other: Fraction(9)}
    )
    uow, session = _uow(_Result(scalar=0))
    with pytest.raises(Problem) as partial:
        repository.insert_reconciliation_lines(
            uow, BATCH, two, exception_items={two[0].key: UUID(int=4)}
        )
    assert [error.field for error in partial.value.errors] == [
        "lines[line:C1:P2:BILLED_CUM].exception_item_id"
    ]
    assert session.calls == []
    # hardening (Codex retest at 81708148): a present key with a None value is a missing link too
    uow, session = _uow(_Result(scalar=0))
    with pytest.raises(Problem) as null_link:
        repository.insert_reconciliation_lines(
            uow,
            BATCH,
            lines,
            exception_items={lines[0].key: None},  # type: ignore[dict-item]
        )
    assert null_link.value.slug == "validation-failed" and session.calls == []
    # the linked positive stays green
    uow, session = _uow(_Result(scalar=0))
    assert (
        repository.insert_reconciliation_lines(
            uow, BATCH, lines, exception_items={lines[0].key: UUID(int=4)}
        )
        == 1
    )
    assert session.calls[1][1][0]["exception_item_id"] == UUID(int=4)


def test_create_batch_recovers_the_lost_race_as_duplicate_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Codex TMIG-R2, exact input: the pre-read sees no duplicate, the INSERT loses the race and the
    # database raises SQLSTATE 23505 on ux_migration_batch__source. On 6ed10ec7 the DBAPIError
    # escaped (from_db_error maps P0001 / 42501 only); the declared refusal is duplicate-import
    # with the winning batch's number and date, after a rollback-safe re-read.
    monkeypatch.setattr(
        repository.numbering, "next_number", lambda uow, code, scope_key="": "MIG-000009"
    )
    winner = SimpleNamespace(
        migration_no="MIG-000008", created_at=datetime(2026, 9, 20, 3, 59, tzinfo=UTC)
    )
    uow, session = _uow(
        _Result(first=None),
        _db_error(
            "23505",
            'duplicate key value violates unique constraint "ux_migration_batch__source"',
            "ux_migration_batch__source",
        ),
        _Result(first=winner),
    )
    with pytest.raises(Problem) as refused:
        repository.create_batch(
            uow,
            mode=MigrationMode.OPENING_BALANCES,
            source_file_id=UUID(int=2),
            source_sha256="ab" * 32,
            cutover_date=date(2023, 1, 31),
        )
    assert refused.value.slug == "duplicate-import"
    assert refused.value.errors[0].rule_id == "IMPORT_FILE_DUPLICATE"
    assert refused.value.detail == (
        "This legacy database was already imported in migration MIG-000008 on 2026-09-20."
    )
    assert session.savepoints == ["begin", "rollback"]
    assert [call[0][:6] for call in session.calls] == ["SELECT", "INSERT", "SELECT"]
    # an unrelated constraint failure is never mapped to duplicate-import
    uow, session = _uow(
        _Result(first=None),
        _db_error("23503", 'violates foreign key constraint "fk_migration_batch__source_file"'),
    )
    with pytest.raises(DBAPIError):
        repository.create_batch(
            uow,
            mode=MigrationMode.OPENING_BALANCES,
            source_file_id=UUID(int=2),
            source_sha256="ab" * 32,
            cutover_date=date(2023, 1, 31),
        )
    assert session.savepoints == ["begin", "rollback"]
