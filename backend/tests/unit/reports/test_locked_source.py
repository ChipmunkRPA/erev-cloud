"""As-locked report runs read the lock's frozen dataset, never a live table (ENGINE_SPEC_B S15-R-19
rev 1.31; supervisor ruling D-98 candidate 96; 04 T-RPT-02 rev 1.53; SCREENS_B RV-04 rev 1.17;
BUILD_SPEC CLO-8).

CPU-only: the frozen bytes come from the EDS-6 engine encoder (``erev_engine`` S15-R-18), the
database is a fake that refuses every read, and the framework's own ``_render_locked`` and
``explain_cell`` are exercised with their database-bound collaborators replaced. The database
scenarios (a seeded lock, a live source changed after it, the API surface) are
``tests/domain/reports/test_as_locked.py``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from io import BytesIO
from types import SimpleNamespace
from typing import Any, Final, cast
from uuid import UUID, uuid4

import pytest
from erev_api.domain.reports import framework, locked
from erev_api.domain.reports.catalogue import DEFINITIONS_BY_CODE
from erev_api.domain.reports.outputs import ROW_KEY, RunStamp
from erev_api.enums import SnapshotKind
from erev_api.problems import Problem
from erev_engine.stages.s15_disclosures import snapshots as engine

LOCK: Final = UUID("00000000-0000-4000-8000-000000000c10")
KIND: Final = SnapshotKind.CONTRACT_BALANCES.value
CODE: Final = "contract_balances"
UNSUPPORTED: Final = "revenue_from_opening_liability"
COLUMNS: Final = (
    engine.Column(engine.ROW_KEY, "text"),
    engine.Column("entity_code", "text"),
    engine.Column("contract_external_id", "text"),
    engine.Column("currency", "text"),
    engine.Column("contract_liability", "text"),
    engine.Column("billed_count", "integer"),
    engine.Column("as_of", "date"),
)
ROWS: Final = (
    {
        engine.ROW_KEY: "AVM-US:SF-ORD-10002",
        "entity_code": "AVM-US",
        "contract_external_id": "SF-ORD-10002",
        "currency": "USD",
        "contract_liability": "39708.49",
        "billed_count": 1,
        "as_of": date(2026, 9, 30),
    },
    {
        engine.ROW_KEY: "AVM-US:SF-ORD-10001",
        "entity_code": "AVM-US",
        "contract_external_id": "SF-ORD-10001",
        "currency": "USD",
        "contract_liability": "30000.00",
        "billed_count": 2,
        "as_of": date(2026, 9, 30),
    },
)
TOTALS: Final = {"contract_liability:USD": "69708.49"}
RUN_AT: Final = datetime(2026, 9, 20, 12, tzinfo=UTC)


def _encoded(rows: tuple[Mapping[str, object], ...] = ROWS) -> engine.Encoded:
    return engine.encode(engine.Dataset(KIND, COLUMNS, rows), TOTALS)


def _dataset(encoded: engine.Encoded, **over: Any) -> locked.LockedDataset:
    return dataclasses.replace(
        locked.LockedDataset(
            lock_id=LOCK,
            kind=KIND,
            file_id=uuid4(),
            file_sha256=encoded.file_sha256,
            row_count=encoded.row_count,
            control_totals=dict(encoded.control_totals),
            content=encoded.content,
        ),
        **over,
    )


def _refusal(caught: pytest.ExceptionInfo[Problem]) -> str:
    """The refusal's shape: 422 validation-failed on the lock parameter with the S15-R-19 rule."""
    problem = caught.value
    assert isinstance(problem, locked.LockedRefusal)
    assert problem.slug == "validation-failed"
    (error,) = problem.errors
    assert (error.field, error.rule_id) == (locked.FIELD, locked.RULE)
    assert error.message == problem.detail
    return str(problem.detail)


class _NoReads:
    """A session that refuses every statement: the as-locked branch reads no live table."""

    def execute(self, *_: Any, **__: Any) -> Any:
        raise AssertionError("the as-locked branch read a live table")


class _OneRow:
    def __init__(self, row: Mapping[str, Any] | None) -> None:
        self.row = row
        self.statements: list[Any] = []

    def execute(self, statement: Any, *_: Any, **__: Any) -> Any:
        self.statements.append(statement)
        return _Result(self.row)


class _Result:
    def __init__(self, row: Mapping[str, Any] | None) -> None:
        self.row = row

    def mappings(self) -> _Result:
        return self

    def one_or_none(self) -> Mapping[str, Any] | None:
        return self.row


class _Uow:
    def __init__(self, session: Any) -> None:
        self.session = session
        self.files = object()
        self.keyring = object()


# --- the kinds table ------------------------------------------------------------------------------


def test_each_snapshot_kind_has_exactly_one_report_in_the_catalogue() -> None:
    kinds = list(locked.SNAPSHOT_KIND_BY_REPORT.values())
    assert sorted(kinds) == sorted(kind.value for kind in SnapshotKind)
    assert len(kinds) == len(set(kinds)) == 12
    assert set(locked.SNAPSHOT_KIND_BY_REPORT) <= set(DEFINITIONS_BY_CODE)
    assert locked.snapshot_kind_of(CODE) == KIND
    assert locked.snapshot_kind_of("rpo") == SnapshotKind.RPO.value


def test_every_dataset_report_accepts_the_lock_parameter() -> None:
    """CLO-8b (F-CLO record §25.27) retired the pinned omission: the two registers'
    catalogue rows now carry ``period_lock_id`` like every other dataset report, so an as-locked
    run of them is reachable through the framework (S15-R-19; E-64)."""
    lacking = {
        code
        for code in locked.SNAPSHOT_KIND_BY_REPORT
        if "period_lock_id" not in DEFINITIONS_BY_CODE[code].parameters_schema["properties"]
    }
    assert lacking == set()


def test_a_report_that_accepts_the_lock_but_has_no_dataset_is_the_unsupported_source() -> None:
    assert "period_lock_id" in DEFINITIONS_BY_CODE[UNSUPPORTED].parameters_schema["properties"]
    assert locked.snapshot_kind_of(UNSUPPORTED) is None
    assert locked.snapshot_kind_of("no_such_report") is None


def test_row_key_column_is_the_engine_sort_key() -> None:
    assert ROW_KEY == engine.ROW_KEY == "row_key"


# --- verification ---------------------------------------------------------------------------------


def test_verify_accepts_the_frozen_dataset() -> None:
    dataset = _dataset(_encoded())
    assert locked.verify(dataset) is dataset
    assert hashlib.sha256(dataset.content).hexdigest() == dataset.file_sha256


def test_verify_refuses_stored_bytes_that_do_not_hash_to_file_sha256() -> None:
    encoded = _encoded()
    tampered = encoded.content.replace(b"39708.49", b"39708.50")
    assert tampered != encoded.content
    with pytest.raises(Problem) as caught:
        locked.verify(_dataset(encoded, content=tampered))
    detail = _refusal(caught)
    assert detail == locked.HASH_MISMATCH.format(kind=KIND, lock=LOCK)
    assert "S15-INV-06" in detail and str(LOCK) in detail and KIND in detail


def test_verify_refuses_a_row_count_that_differs_from_the_snapshot() -> None:
    encoded = _encoded()
    with pytest.raises(Problem) as caught:
        locked.verify(_dataset(encoded, row_count=5))
    assert _refusal(caught) == locked.ROW_COUNT_MISMATCH.format(
        kind=KIND, lock=LOCK, actual=2, expected=5
    )


# --- the frozen rows as report data ---------------------------------------------------------------


def test_report_data_renders_the_frozen_rows_as_text_columns_keyed_by_row_key() -> None:
    encoded = _encoded()
    data = locked.report_data(_dataset(encoded))
    assert [column.key for column in data.columns] == [
        "entity_code",
        "contract_external_id",
        "currency",
        "contract_liability",
        "billed_count",
        "as_of",
    ]
    assert all(column.kind == "text" and column.header == column.key for column in data.columns)
    # S15-R-18 sorts by row key: SF-ORD-10001 before SF-ORD-10002 although encoded second.
    assert [row[ROW_KEY] for row in data.rows] == ["AVM-US:SF-ORD-10001", "AVM-US:SF-ORD-10002"]
    first = data.rows[0]
    assert first["contract_liability"] == "30000.00"
    assert first["billed_count"] == "2"
    assert first["as_of"] == "2026-09-30"
    assert ROW_KEY not in [column.key for column in data.columns]
    assert data.row_count == encoded.row_count == 2
    assert data.control_totals == TOTALS
    assert data.tie_out_results == ()


def test_report_data_refuses_a_dataset_without_the_row_key_column() -> None:
    content = b"entity_code,contract_external_id\nAVM-US,SF-ORD-10001\n"
    dataset = locked.LockedDataset(
        lock_id=LOCK,
        kind=KIND,
        file_id=uuid4(),
        file_sha256=hashlib.sha256(content).hexdigest(),
        row_count=1,
        control_totals={},
        content=content,
    )
    assert locked.verify(dataset) is dataset
    with pytest.raises(Problem) as caught:
        locked.report_data(dataset)
    assert _refusal(caught) == locked.KEY_MISSING.format(kind=KIND, lock=LOCK, column=ROW_KEY)


def test_csv_bytes_are_the_frozen_file_and_its_hash() -> None:
    encoded = _encoded()
    content, sha256 = locked.csv_bytes(_dataset(encoded))
    assert content == encoded.content
    assert sha256 == encoded.file_sha256 == hashlib.sha256(content).hexdigest()


# --- resolution against the lock ------------------------------------------------------------------


def test_a_report_without_a_dataset_refuses_by_name_before_any_read() -> None:
    with pytest.raises(Problem) as caught:
        locked.locked_dataset(cast(Any, _Uow(_NoReads())), report_code=UNSUPPORTED, lock_id=LOCK)
    detail = _refusal(caught)
    assert detail == locked.NO_DATASET.format(code=UNSUPPORTED)
    assert UNSUPPORTED in detail


def test_a_lock_without_the_kinds_snapshot_refuses_by_name() -> None:
    session = _OneRow(None)
    with pytest.raises(Problem) as caught:
        locked.locked_dataset(cast(Any, _Uow(session)), report_code=CODE, lock_id=LOCK)
    detail = _refusal(caught)
    assert detail == locked.SNAPSHOT_MISSING.format(lock=LOCK, kind=KIND, code=CODE)
    assert len(session.statements) == 1


def test_the_stored_file_is_read_back_and_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    encoded = _encoded()
    file_id = uuid4()
    row = {
        "file_id": file_id,
        "file_sha256": encoded.file_sha256,
        "row_count": encoded.row_count,
        "control_totals": dict(encoded.control_totals),
    }
    opened: list[UUID] = []

    def open_file(session: Any, wanted: UUID, *, files: Any, keyring: Any) -> Any:
        opened.append(wanted)
        return {}, BytesIO(encoded.content)

    monkeypatch.setattr(locked, "open_file", open_file)
    dataset = locked.locked_dataset(cast(Any, _Uow(_OneRow(row))), report_code=CODE, lock_id=LOCK)
    assert opened == [file_id]
    assert (dataset.kind, dataset.lock_id, dataset.file_id) == (KIND, LOCK, file_id)
    assert dataset.content == encoded.content
    assert dataset.row_count == 2 and dataset.control_totals == TOTALS


def test_a_stored_file_that_differs_from_the_snapshot_hash_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded = _encoded()
    row = {
        "file_id": uuid4(),
        "file_sha256": encoded.file_sha256,
        "row_count": encoded.row_count,
        "control_totals": {},
    }
    monkeypatch.setattr(
        locked, "open_file", lambda *_, **__: ({}, BytesIO(encoded.content + b"x,y\n"))
    )
    with pytest.raises(Problem) as caught:
        locked.locked_dataset(cast(Any, _Uow(_OneRow(row))), report_code=CODE, lock_id=LOCK)
    assert _refusal(caught) == locked.HASH_MISMATCH.format(kind=KIND, lock=LOCK)


# --- the framework branch -------------------------------------------------------------------------


def _run(output_format: str) -> dict[str, Any]:
    return {
        "output_format": output_format,
        "report_code": CODE,
        "report_version": 1,
        "report_run_no": "RPT-000001",
        "parameters": {"period_lock_id": str(LOCK), "entity_codes": ["AVM-US"]},
        "period_lock_id": LOCK,
        "known_at": RUN_AT,
    }


DEFINITION: Final = {"code": CODE, "name": "Contract balances", "version": 1}


def _stamp(*_: Any, output_sha256: str, style: str, **__: Any) -> RunStamp:
    return RunStamp(
        report_code=CODE,
        report_name="Contract balances",
        report_version=1,
        report_run_no="RPT-000001",
        parameters={"period_lock_id": str(LOCK)},
        entity_codes=("AVM-US",),
        book="ASC606",
        as_of=None,
        source="As locked on 20 Sep 2026",
        engine_version="test",
        build_sha="0" * 40,
        run_by="Maya",
        run_at=RUN_AT,
        output_sha256=output_sha256,
        negative_number_style=style,
    )


def test_render_locked_csv_is_the_frozen_file_with_the_snapshot_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded = _encoded()
    dataset = _dataset(encoded)
    monkeypatch.setattr(framework, "_run_stamp", _stamp)
    rendered = framework._render_locked(
        cast(Any, _NoReads()),
        _run("CSV"),
        DEFINITION,
        dataset,
        locked.report_data(dataset),
        "PARENTHESES",
    )
    assert rendered.content == encoded.content
    assert rendered.sha256 == encoded.file_sha256
    assert (rendered.media_type, rendered.extension) == ("text/csv", "csv")
    assert rendered.manifest is not None
    manifest = json.loads(rendered.manifest)
    assert manifest["sha256"] == encoded.file_sha256
    assert manifest["row_count"] == 2


def test_render_locked_json_carries_the_frozen_rows_as_text() -> None:
    encoded = _encoded()
    dataset = _dataset(encoded)
    rendered = framework._render_locked(
        cast(Any, _NoReads()),
        _run("JSON"),
        DEFINITION,
        dataset,
        locked.report_data(dataset),
        "PARENTHESES",
    )
    document = json.loads(rendered.content)
    assert document["row_count"] == 2
    assert {column["kind"] for column in document["columns"]} == {"text"}
    assert [row[ROW_KEY] for row in document["rows"]] == [
        "AVM-US:SF-ORD-10001",
        "AVM-US:SF-ORD-10002",
    ]
    assert document["rows"][0]["contract_liability"] == "30000.00"
    assert document["control_totals"] == TOTALS
    assert rendered.sha256 == hashlib.sha256(rendered.content).hexdigest()


# The request context ``explain_cell`` takes since 04 API-R-41 rev 1.99 (ruling R-13): ``run_row``
# is patched here and neither report declares a further permission. Its principal holds the run
# permission of both reports, ``report.run``, which ``require_report`` checks for every report
# since ruling R-63 (a).
_CALLER: Final = SimpleNamespace(
    principal=SimpleNamespace(
        permissions=frozenset({framework.RUN_PERMISSION}),
        permission_scopes={framework.RUN_PERMISSION: "*"},
    )
)


def test_explain_cell_is_not_offered_on_an_as_locked_run(monkeypatch: pytest.MonkeyPatch) -> None:
    row = {"status": framework.SUCCEEDED, "period_lock_id": LOCK, "report_code": CODE}
    monkeypatch.setattr(framework, "run_row", lambda *_, **__: row)
    with pytest.raises(Problem) as caught:
        framework.explain_cell(
            cast(Any, _CALLER), cast(Any, _NoReads()), uuid4(), row_key="r", column_key="c"
        )
    assert caught.value.slug == "not-found"
    assert caught.value.detail == locked.EXPLAIN_LOCKED


def test_explain_cell_of_a_current_run_still_reaches_its_explainer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = {"status": framework.SUCCEEDED, "period_lock_id": None, "report_code": "no_explainer"}
    monkeypatch.setattr(framework, "run_row", lambda *_, **__: row)
    with pytest.raises(Problem) as caught:
        framework.explain_cell(
            cast(Any, _CALLER), cast(Any, _NoReads()), uuid4(), row_key="r", column_key="c"
        )
    assert caught.value.detail == framework.NO_CELL_EXPLAINER


# --- CLO8-SCOPE-R1: the scope of an as-locked run is the lock's ----------------------------------

ENTITY_A: Final = UUID("00000000-0000-4000-8000-00000000000a")
ENTITY_B: Final = UUID("00000000-0000-4000-8000-00000000000b")
PERIOD: Final = UUID("00000000-0000-4000-8000-000000000909")
SCOPE: Final = locked.LockScope(
    lock_id=LOCK,
    entity_id=ENTITY_A,
    entity_code="AVM-US",
    book_code="ASC606",
    period_id=PERIOD,
    period_key="FY2026-P09",
)
BALANCES_PROPERTIES: Final = DEFINITIONS_BY_CODE[CODE].parameters_schema["properties"]
RANGE_PROPERTIES: Final = DEFINITIONS_BY_CODE["contract_balance_rollforward"].parameters_schema[
    "properties"
]
MATCHING: Final = {
    "period_lock_id": str(LOCK),
    "entity_codes": ["AVM-US"],
    "book": "ASC606",
    "period_key": "FY2026-P09",
}


def _findings(errors: Sequence[Any]) -> dict[str, str]:
    for error in errors:
        assert error.rule_id == locked.RULE
    return {str(error.field): str(error.message) for error in errors}


def test_matching_selectors_are_accepted_and_normalised() -> None:
    parameters, errors = locked.reconcile_selectors(MATCHING, SCOPE, BALANCES_PROPERTIES, kind=KIND)
    assert errors == []
    assert parameters == MATCHING


def test_omitted_selectors_are_derived_from_the_lock() -> None:
    parameters, errors = locked.reconcile_selectors(
        {"period_lock_id": str(LOCK)}, SCOPE, BALANCES_PROPERTIES, kind=KIND
    )
    assert errors == []
    assert parameters == MATCHING
    ranged, errors = locked.reconcile_selectors(
        {"period_lock_id": str(LOCK), "known_at": "2026-09-20T12:00:00Z"},
        SCOPE,
        RANGE_PROPERTIES,
        kind=KIND,
    )
    assert errors == []
    assert ranged == {
        "period_lock_id": str(LOCK),
        "known_at": "2026-09-20T12:00:00Z",
        "entity_codes": ["AVM-US"],
        "book": "ASC606",
        "from_period_key": "FY2026-P09",
        "to_period_key": "FY2026-P09",
    }


def test_another_entity_than_the_locks_is_refused_by_name() -> None:
    for codes in (["AVM-UK"], ["AVM-US", "AVM-UK"], ["AVM-UK", "AVM-US"]):
        _, errors = locked.reconcile_selectors(
            {**MATCHING, "entity_codes": codes}, SCOPE, BALANCES_PROPERTIES, kind=KIND
        )
        assert _findings(errors) == {
            "parameters.entity_codes": locked.ENTITY_MISMATCH.format(entity="AVM-US", lock=LOCK)
        }, codes


def test_another_book_or_period_than_the_locks_is_refused_by_name() -> None:
    _, errors = locked.reconcile_selectors(
        {**MATCHING, "book": "IFRS15"}, SCOPE, BALANCES_PROPERTIES, kind=KIND
    )
    assert _findings(errors) == {
        "parameters.book": locked.BOOK_MISMATCH.format(book="ASC606", lock=LOCK)
    }
    _, errors = locked.reconcile_selectors(
        {**MATCHING, "period_key": "FY2026-P08"}, SCOPE, BALANCES_PROPERTIES, kind=KIND
    )
    assert _findings(errors) == {
        "parameters.period_key": locked.PERIOD_MISMATCH.format(
            key="period_key", period="FY2026-P09", lock=LOCK
        )
    }
    _, errors = locked.reconcile_selectors(
        {
            "period_lock_id": str(LOCK),
            "from_period_key": "FY2026-P08",
            "to_period_key": "FY2026-P09",
        },
        SCOPE,
        RANGE_PROPERTIES,
        kind=KIND,
    )
    assert set(_findings(errors)) == {"parameters.from_period_key"}


def test_a_filter_or_view_on_an_as_locked_run_is_refused_by_name() -> None:
    for key, value in (
        ("contract_external_id", "SF-ORD-10001"),
        ("include_zero", True),
        ("currency_view", "TRANSACTION"),
    ):
        _, errors = locked.reconcile_selectors(
            {**MATCHING, key: value}, SCOPE, BALANCES_PROPERTIES, kind=KIND
        )
        assert _findings(errors) == {
            f"parameters.{key}": locked.NOT_A_LOCK_SELECTOR.format(key=key, kind=KIND, lock=LOCK)
        }, key
    _, errors = locked.reconcile_selectors(
        {"period_lock_id": str(LOCK), "as_of": "2026-09-30"},
        SCOPE,
        DEFINITIONS_BY_CODE["revenue_waterfall"].parameters_schema["properties"],
        kind=SnapshotKind.WATERFALL.value,
    )
    assert set(_findings(errors)) == {"parameters.as_of"}


def _consistent_run(**over: Any) -> dict[str, Any]:
    return {
        "report_run_no": "RPT-000007",
        "entity_ids": [ENTITY_A],
        "book_code": "ASC606",
        "period_lock_id": LOCK,
        "parameters": dict(MATCHING, known_at="2026-09-20T12:00:00Z"),
        **over,
    }


def test_a_persisted_run_is_reconciled_with_its_lock() -> None:
    assert locked.run_mismatch(_consistent_run(), SCOPE) is None
    assert locked.run_mismatch(_consistent_run(entity_ids=[ENTITY_B]), SCOPE) == "entity_ids"
    assert locked.run_mismatch(_consistent_run(entity_ids=[ENTITY_A, ENTITY_B]), SCOPE) == (
        "entity_ids"
    )
    assert locked.run_mismatch(_consistent_run(book_code="IFRS15"), SCOPE) == "book_code"
    assert (
        locked.run_mismatch(
            _consistent_run(parameters={**MATCHING, "entity_codes": ["AVM-UK"]}), SCOPE
        )
        == "parameters.entity_codes"
    )
    assert (
        locked.run_mismatch(
            _consistent_run(parameters={**MATCHING, "period_key": "FY2026-P08"}), SCOPE
        )
        == "parameters.period_key"
    )
    assert (
        locked.run_mismatch(
            _consistent_run(parameters={**MATCHING, "contract_external_id": "SF-ORD-10001"}),
            SCOPE,
        )
        == "parameters.contract_external_id"
    )
    assert locked.run_mismatch(_consistent_run(period_lock_id=uuid4()), SCOPE) == "period_lock_id"


def test_visibility_requires_the_locks_entity_to_be_the_runs_scope() -> None:
    from erev_api.db.tables import report_run
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    class _Principal:
        permission_scopes = {framework.RUN_PERMISSION: frozenset({ENTITY_B})}

    statement = framework.visible(
        select(report_run.c.id), cast(Any, _Principal()), framework.RUN_PERMISSION
    )
    sql = str(statement.compile(dialect=postgresql.dialect()))
    # Compiled with the erev schema prefix; the predicate is the caller's scope AND, for an
    # as-locked run, entity_ids = ARRAY[the lock's entity].
    assert "report_run.entity_ids <@" in sql
    assert "report_run.period_lock_id IS NULL" in sql
    assert "report_run.entity_ids = ARRAY[erev.period_lock.entity_id]" in sql
    assert "period_lock.id = erev.report_run.period_lock_id" in sql


def test_an_inconsistent_as_locked_run_is_refused_by_name_when_addressed() -> None:
    hidden = {"report_run_no": "RPT-000009", "period_lock_id": LOCK}

    class _Session:
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, *_: Any, **__: Any) -> Any:
            self.calls += 1
            return _Result(None if self.calls == 1 else hidden)

    class _Principal:
        permission_scopes = {framework.RUN_PERMISSION: "*"}

    session = _Session()
    with pytest.raises(Problem) as caught:
        framework.run_row(
            cast(Any, session), cast(Any, _Principal()), uuid4(), framework.RUN_PERMISSION
        )
    assert caught.value.slug == "not-found"
    assert caught.value.detail == locked.RUN_SCOPE_INCONSISTENT.format(run_no="RPT-000009")
    assert session.calls == 2


def test_a_run_absent_from_scope_stays_a_plain_not_found() -> None:
    class _Session:
        def execute(self, *_: Any, **__: Any) -> Any:
            return _Result(None)

    class _Principal:
        permission_scopes = {framework.RUN_PERMISSION: "*"}

    with pytest.raises(Problem) as caught:
        framework.run_row(
            cast(Any, _Session()), cast(Any, _Principal()), uuid4(), framework.RUN_PERMISSION
        )
    assert (caught.value.slug, caught.value.detail) == ("not-found", None)


# --- CLO8-SCOPE-R1 residual (Codex 1622): FULL consistency on the list and on every read ----------


def test_visibility_reconciles_book_period_and_parameters_with_the_lock() -> None:
    """The list predicate is the full scope, not the entity alone: book, every period selector,
    the admitted parameter keys and entity_codes — mirrored on run_mismatch."""
    from erev_api.db.tables import report_run
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    class _Principal:
        permission_scopes = {framework.RUN_PERMISSION: "*"}

    statement = framework.visible(
        select(report_run.c.id), cast(Any, _Principal()), framework.RUN_PERMISSION
    )
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "report_run.period_lock_id IS NULL" in sql
    assert "EXISTS (SELECT" in sql
    assert "period_lock.id = erev.report_run.period_lock_id" in sql
    assert "report_run.entity_ids = ARRAY[erev.period_lock.entity_id]" in sql
    assert "report_run.book_code = erev.period_lock.book_code" in sql
    # Each persisted period selector is NULL or the lock's period key (one clause per key).
    assert sql.count("= erev.period.period_key") == len(locked.PERIOD_KEYS)
    assert "jsonb_build_array(erev.legal_entity.code)" in sql
    assert "report_run.parameters - ARRAY[" in sql and "CAST(%(param_" in sql
    # Codex 1649 (a): the JSON text of `book` is compared with the ENUM column cast to text — the
    # trusted enum is cast, never the stored JSON into the enum (malformed values would raise).
    assert "(erev.report_run.parameters ->> %(parameters_" in sql
    assert "= CAST(erev.period_lock.book_code AS TEXT)" in sql
    assert "AS book_code)" not in sql and "::book_code" not in sql


def test_visibility_admits_exactly_the_admitted_parameter_keys() -> None:
    """The SQL key list the predicate subtracts is ADMITTED_KEYS, so the list predicate and
    run_mismatch admit the same parameters."""
    from erev_api.db.tables import report_run
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    class _Principal:
        permission_scopes = {framework.RUN_PERMISSION: "*"}

    compiled = framework.visible(
        select(report_run.c.id), cast(Any, _Principal()), framework.RUN_PERMISSION
    ).compile(dialect=postgresql.dialect())
    bound = {str(value) for value in compiled.params.values() if isinstance(value, str)}
    assert set(locked.ADMITTED_KEYS) <= bound
    assert set(locked.PERIOD_KEYS) <= bound
    assert "contract_external_id" not in bound


class _ScopeRow:
    """Session double for run_row: the run row first, then the lock-scope row."""

    def __init__(self, run: Mapping[str, Any] | None, scope: Mapping[str, Any] | None) -> None:
        self.answers = [run, scope]
        self.calls = 0

    def execute(self, *_: Any, **__: Any) -> Any:
        self.calls += 1
        return _Result(self.answers[self.calls - 1])


class _AllScopes:
    permission_scopes = {framework.RUN_PERMISSION: "*"}


SCOPE_ROW: Final = {
    "id": LOCK,
    "kind": "LOCK",  # S15-R-19 rev 1.167: the statement reads the record's kind as well
    "entity_id": ENTITY_A,
    "book_code": "ASC606",
    "period_id": PERIOD,
    "entity_code": "AVM-US",
    "period_key": "FY2026-P09",
}


def test_run_row_reconciles_a_returned_as_locked_row_with_its_lock() -> None:
    """Even when the database predicate admitted the row, run_row refuses by name unless the
    row's book, period and parameters are the lock's — the authoritative check on every read."""
    completed = _consistent_run(status=framework.SUCCEEDED, id=uuid4())
    for changed in (
        {"book_code": "IFRS15"},
        {"parameters": {**MATCHING, "period_key": "FY2026-P08"}},
        {"parameters": {**MATCHING, "contract_external_id": "SF-ORD-10001"}},
        {"parameters": {**MATCHING, "book": "IFRS15"}},
    ):
        session = _ScopeRow({**completed, **changed}, SCOPE_ROW)
        with pytest.raises(Problem) as caught:
            framework.run_row(
                cast(Any, session), cast(Any, _AllScopes()), uuid4(), framework.RUN_PERMISSION
            )
        assert caught.value.slug == "not-found", changed
        assert caught.value.detail == locked.RUN_SCOPE_INCONSISTENT.format(run_no="RPT-000007")
        assert session.calls == 2


def test_run_row_serves_a_consistent_as_locked_row_and_a_current_row() -> None:
    completed = _consistent_run(status=framework.SUCCEEDED, id=uuid4())
    session = _ScopeRow(completed, SCOPE_ROW)
    row = framework.run_row(
        cast(Any, session), cast(Any, _AllScopes()), uuid4(), framework.RUN_PERMISSION
    )
    assert row["report_run_no"] == "RPT-000007" and session.calls == 2
    current = {**completed, "period_lock_id": None}
    session = _ScopeRow(current, None)
    row = framework.run_row(
        cast(Any, session), cast(Any, _AllScopes()), uuid4(), framework.RUN_PERMISSION
    )
    assert row["period_lock_id"] is None and session.calls == 1


def test_run_row_refuses_an_as_locked_row_whose_lock_is_gone() -> None:
    completed = _consistent_run(status=framework.SUCCEEDED, id=uuid4())
    session = _ScopeRow(completed, None)
    with pytest.raises(Problem) as caught:
        framework.run_row(
            cast(Any, session), cast(Any, _AllScopes()), uuid4(), framework.RUN_PERMISSION
        )
    assert caught.value.slug == "not-found"
    assert caught.value.detail == locked.RUN_LOCK_MISSING.format(lock=LOCK, run_no="RPT-000007")


# --- RPS-SNAP A4 13.1: the export boundary of the as-locked CSV -----------------------------------

TRIGGER_ROWS: Final = (
    {
        **ROWS[0],
        engine.ROW_KEY: "AVM-US:=A",
        "contract_external_id": "=A",
        "contract_liability": "-5.00",
    },
    {**ROWS[1], engine.ROW_KEY: "AVM-US:'=A", "contract_external_id": "'=A"},
)


KINDS: Final = {  # the DECLARED kinds of the fixture columns (Codex 1739 §3 (c))
    "entity_code": "code",
    "contract_external_id": "code",
    "currency": "code",
    "contract_liability": "money",
    "billed_count": "integer",
    "as_of": "date",
}


def test_export_csv_is_byte_identical_to_a_trigger_free_frozen_file() -> None:
    encoded = _encoded()
    content, sha256 = locked.export_csv(_dataset(encoded), KINDS)
    assert content == encoded.content and sha256 == encoded.file_sha256


def test_export_csv_guards_raw_formula_cells_and_leaves_machine_values_and_the_frozen_bytes() -> (
    None
):
    """A4 13.1: identity lives in the frozen bytes (`=A` and `'=A` are two contracts); the served
    CSV guards the cell that begins with a trigger, leaves the canonical negative decimal and the
    header alone, and hashes to its own bytes — the stored artefact and `file_sha256` unchanged."""
    encoded = _encoded(TRIGGER_ROWS)
    dataset = _dataset(encoded)
    assert b"\n=A," not in encoded.content and b",=A," in encoded.content  # raw in the artefact
    content, sha256 = locked.export_csv(dataset, KINDS)
    lines = content.decode("utf-8").split("\n")
    frozen_lines = encoded.content.decode("utf-8").split("\n")
    assert lines[0] == frozen_lines[0]  # the header as stored
    served = [line.split(",") for line in lines[1:3]]
    assert [cells[2] for cells in served] == ["'=A", "'=A"]  # display: both guarded (one already)
    # rows sort by row_key ("AVM-US:'=A" < "AVM-US:=A"); DECLARED money is never guarded
    assert [cells[4] for cells in served] == ["30000.00", "-5.00"]
    assert sha256 == hashlib.sha256(content).hexdigest() != encoded.file_sha256
    assert dataset.content == encoded.content and dataset.file_sha256 == encoded.file_sha256
    assert locked.csv_bytes(dataset) == (encoded.content, encoded.file_sha256)  # the artefact


def test_export_csv_guards_by_the_declared_kind_not_by_the_text_shape() -> None:
    """Codex 1739 §3 (c): a code id "-1" is TEXT and guarded; the same text under a declared money
    column follows the numeric branch; with nothing declared every cell is text (guarded)."""
    rows = (
        {
            **ROWS[0],
            engine.ROW_KEY: "AVM-US:-1",
            "contract_external_id": "-1",
            "contract_liability": "-1",
        },
    )
    encoded = _encoded(rows)
    content, _ = locked.export_csv(_dataset(encoded), KINDS)
    cells = content.decode("utf-8").split("\n")[1].split(",")
    assert (cells[2], cells[4]) == ("'-1", "-1")  # code → guarded; declared money → as stored
    content, _ = locked.export_csv(_dataset(encoded), {})
    cells = content.decode("utf-8").split("\n")[1].split(",")
    assert (cells[2], cells[4]) == ("'-1", "'-1")  # undeclared = text: guarded


def test_export_csv_verifies_the_stored_bytes_before_rendering() -> None:
    encoded = _encoded()
    with pytest.raises(Problem):
        locked.export_csv(_dataset(encoded, content=encoded.content + b"x"), KINDS)


def test_render_locked_csv_serves_the_guarded_export_and_its_manifest_names_that_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded = _encoded(TRIGGER_ROWS)
    dataset = _dataset(encoded)
    monkeypatch.setattr(framework, "_run_stamp", _stamp)
    rendered = framework._render_locked(
        cast(Any, _NoReads()),
        _run("CSV"),
        DEFINITION,
        dataset,
        locked.report_data(dataset),
        "PARENTHESES",
    )
    from erev_api.domain.reports import snapshots

    kinds = snapshots.declared_kinds(KIND, locked.headers_of(dataset), dataset.control_totals)
    assert kinds["contract_liability"] == "money" and kinds["contract_external_id"] == "code"
    content, sha256 = locked.export_csv(dataset, kinds)
    assert rendered.content == content and rendered.sha256 == sha256 != encoded.file_sha256
    assert rendered.manifest is not None
    manifest = json.loads(rendered.manifest)
    assert manifest["sha256"] == sha256 and manifest["row_count"] == 2
