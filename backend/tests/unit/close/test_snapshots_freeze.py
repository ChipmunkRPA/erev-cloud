"""``close/snapshots.py`` orchestration without a database (F-CLO record §17.1): a registry missing
kinds refuses naming them before any write; the engine formula is used for the manifest; the
T-CLS-05 rows are built with ``report_run_id`` NULL (ruling Q-10). The engine and registry are
injected test doubles here; production resolves the real producers by name and refuses when
absent."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.close import dependencies, snapshots
from erev_api.enums import SnapshotKind

KINDS = tuple(kind.value for kind in SnapshotKind)
ENTITY = UUID("00000000-0000-0000-0000-0000000000e1")
PERIOD = UUID("00000000-0000-0000-0000-0000000000f1")
TENANT = UUID("00000000-0000-0000-0000-00000000aa01")
LOCK = UUID("00000000-0000-0000-0000-00000000bb01")
NOW = datetime(2026, 10, 5, 14, 30, tzinfo=UTC)


class _Untouchable:
    """A unit of work the refusal path must never read."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the refusal touched uow.{name}")


def _engine() -> dependencies.SnapshotEngine:
    return dependencies.SnapshotEngine(
        kinds=KINDS,
        encoded=object,
        manifest_sha256=lambda hashes: "|".join(f"{k}:{v}" for k, v in sorted(hashes.items())),
    )


def _scope(**values: Any) -> dict[str, Any]:
    return values


def test_twelve_kinds_follow_e_64() -> None:
    assert (
        len(KINDS) == 12 and KINDS[0] == "WATERFALL" and KINDS[-1] == "MANUAL_ADJUSTMENT_REGISTER"
    )


def test_missing_kinds_refuse_before_any_write() -> None:
    registry = {kind: (lambda uow, scope: None) for kind in KINDS[:6]}  # six registered today
    with pytest.raises(dependencies.ProducerMissing) as caught:
        snapshots.freeze_datasets(
            _Untouchable(),  # type: ignore[arg-type]
            ENTITY,
            "ASC606",
            PERIOD,
            NOW,
            registry=registry,
            scope_type=_scope,
            engine=_engine(),
        )
    assert caught.value.module == dependencies.SNAPSHOT_REGISTRY
    assert set(caught.value.names) == set(KINDS[6:])
    assert "no partial manifest" in str(caught.value)


def test_engine_absent_refuses_by_name_before_the_registry() -> None:
    try:
        dependencies.snapshot_engine()
    except dependencies.ProducerMissing:
        with pytest.raises(dependencies.ProducerMissing) as caught:
            snapshots.freeze_datasets(_Untouchable(), ENTITY, "ASC606", PERIOD, NOW)  # type: ignore[arg-type]
        assert caught.value.module == dependencies.SNAPSHOT_ENGINE
    else:
        with pytest.raises(dependencies.ProducerMissing) as caught:
            snapshots.freeze_datasets(
                _Untouchable(),  # type: ignore[arg-type]
                ENTITY,
                "ASC606",
                PERIOD,
                NOW,
                registry={},
                scope_type=_scope,
            )
        assert set(caught.value.names) == set(KINDS)


def _datasets() -> tuple[snapshots.DatasetFile, ...]:
    return tuple(
        snapshots.DatasetFile(
            kind=kind,
            file_id=UUID(int=index + 1),
            file_sha256=f"{index:064x}",
            row_count=index,
            control_totals={"rows": index},
        )
        for index, kind in enumerate(KINDS)
    )


def test_manifest_uses_the_engine_formula_over_every_kind() -> None:
    datasets = _datasets()
    manifest = snapshots.manifest_of(datasets, engine=_engine())
    assert manifest == "|".join(
        f"{d.kind}:{d.file_sha256}" for d in sorted(datasets, key=lambda d: d.kind)
    )
    with pytest.raises(ValueError, match="twelve"):
        snapshots.manifest_of(datasets[:-1], engine=_engine())


def test_snapshot_rows_have_report_run_id_null_and_one_row_per_kind() -> None:
    stamp = {"created_at": NOW, "created_by": None, "created_by_kind": "SYSTEM"}
    rows = snapshots.snapshot_rows(TENANT, LOCK, _datasets(), stamp=stamp)
    assert [row["snapshot_kind"] for row in rows] == list(KINDS)
    assert all(row["report_run_id"] is None for row in rows)  # ruling Q-10
    assert all(row["period_lock_id"] == LOCK and row["tenant_id"] == TENANT for row in rows)
    assert rows[3]["file_sha256"] == f"{3:064x}" and rows[3]["row_count"] == 3
    assert rows[3]["control_totals"] == {"rows": 3} and rows[3]["created_at"] == NOW


class _Stop(Exception):
    """Raised by the first builder so the freeze stops before any store (unit scope capture)."""


def _same_unit(uow: Any) -> Any:
    """The reader of an orchestration test: the unit of work itself. Production reads through
    ``freeze.system_unit`` — a transaction of the tenant's SYSTEM principal (R-94 (a))."""
    return nullcontext(uow)


def _capturing_registry(seen: list[dict[str, Any]]) -> dict[str, Any]:
    def builder(uow: Any, scope: dict[str, Any]) -> None:
        seen.append(scope)
        raise _Stop

    return {kind: builder for kind in KINDS}


def test_the_scope_carries_frozen_at_only_when_given() -> None:
    """D-98 candidate 139 amendment 3 (S15-R-18b Q5): ``JE_POPULATION`` cuts and reconstructs at the
    FREEZE INSTANT while the other kinds read as of ``known_at``, so the lock passes both and the
    registry's scope receives ``frozen_at`` — and an older / injected scope type that does not know
    the member is not handed one."""
    later = NOW.replace(hour=NOW.hour + 1)
    seen: list[dict[str, Any]] = []
    with pytest.raises(_Stop):
        snapshots.freeze_datasets(
            _Untouchable(),  # type: ignore[arg-type]
            ENTITY,
            "ASC606",
            PERIOD,
            NOW,
            frozen_at=later,
            registry=_capturing_registry(seen),
            scope_type=_scope,
            engine=_engine(),
            reader=_same_unit,
        )
    assert seen == [
        {
            "entity_id": ENTITY,
            "book_code": "ASC606",
            "period_id": PERIOD,
            "known_at": NOW,
            "frozen_at": later,
        }
    ]
    seen.clear()
    with pytest.raises(_Stop):
        snapshots.freeze_datasets(
            _Untouchable(),  # type: ignore[arg-type]
            ENTITY,
            "ASC606",
            PERIOD,
            NOW,
            registry=_capturing_registry(seen),
            scope_type=_scope,
            engine=_engine(),
            reader=_same_unit,
        )
    assert seen == [
        {"entity_id": ENTITY, "book_code": "ASC606", "period_id": PERIOD, "known_at": NOW}
    ]


def test_the_builders_read_through_the_reader_and_the_caller_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supervisor ruling R-94 (a) (04 T-CLS-05 rev 1.140; S15-R-18c rev 1.88): every builder is
    handed the READER — in production ``freeze.system_unit``, a read-only transaction of the
    tenant's SYSTEM principal — for the whole freeze, and the CALLER's unit of work stores each
    file; the reader is left when the last file is stored. Fail-first: the builders were handed
    the caller's unit of work, so a dataset held only what the decider's row-level scope shows."""
    caller, source = SimpleNamespace(name="caller"), SimpleNamespace(name="reader")
    trail: list[tuple[str, str]] = []

    @contextmanager
    def reading(uow: Any) -> Iterator[Any]:
        assert uow is caller
        trail.append(("reader", "entered"))
        yield source
        trail.append(("reader", "left"))

    def builder_of(kind: str) -> Any:
        def build(uow: Any, scope: Any) -> Any:
            trail.append((kind, f"built through the {uow.name}"))
            content = kind.encode()
            return SimpleNamespace(
                kind=kind,
                content=content,
                file_sha256=hashlib.sha256(content).hexdigest(),
                row_count=1,
                control_totals={"rows": 1},
            )

        return build

    def store(uow: Any, *, stream: Any, original_filename: str, **stored: Any) -> dict[str, Any]:
        kind = original_filename.removesuffix(snapshots.FILE_SUFFIX)
        trail.append((kind, f"stored by the {uow.name}"))
        return {
            "id": UUID(int=len(trail)),
            "sha256": hashlib.sha256(stream.read()).hexdigest(),
            "media_type": stored["media_type"],
            "original_filename": original_filename,
        }

    monkeypatch.setattr(snapshots, "store_file", store)
    frozen = snapshots.freeze_datasets(
        caller,  # type: ignore[arg-type]
        ENTITY,
        "ASC606",
        PERIOD,
        NOW,
        registry={kind: builder_of(kind) for kind in KINDS},
        scope_type=_scope,
        engine=_engine(),
        reader=reading,
    )
    assert [dataset.kind for dataset in frozen] == list(KINDS)
    expected = [("reader", "entered")]
    for kind in KINDS:
        expected += [(kind, "built through the reader"), (kind, "stored by the caller")]
    assert trail == [*expected, ("reader", "left")]


def test_a_caller_that_names_no_reader_reads_through_the_system_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default reader is ``freeze.system_unit`` (R-94 (a)): a caller that names none — the
    close run's step, the sandbox replay — freezes under the tenant's SYSTEM scope. The freeze
    sets the idle bound for the reader it opens (05 TXN-03 rev 1.121; supervisor ruling R-119 (d)):
    one ``set_config`` on the reader's session, and nothing on a reader a caller hands in (the
    tests above)."""
    caller = SimpleNamespace(name="caller")
    entered: list[Any] = []
    statements: list[str] = []

    def execute(statement: Any, parameters: Any = None) -> None:
        statements.append(str(statement))

    @contextmanager
    def system_unit(uow: Any) -> Iterator[Any]:
        entered.append(uow)
        yield SimpleNamespace(name="system reader", session=SimpleNamespace(execute=execute))

    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(snapshots.freeze, "system_unit", system_unit)
    with pytest.raises(_Stop):
        snapshots.freeze_datasets(
            caller,  # type: ignore[arg-type]
            ENTITY,
            "ASC606",
            PERIOD,
            NOW,
            registry=_capturing_registry(seen),
            scope_type=_scope,
            engine=_engine(),
        )
    assert entered == [caller] and len(seen) == 1
    (bound,) = statements
    assert "set_config('idle_in_transaction_session_timeout'" in bound


def test_frozen_datasets_are_stored_as_machine_artefacts_not_spreadsheets() -> None:
    """D-98 candidate 139 amendment 5 addendum (F-RPS §13.5): a frozen dataset carries RAW identity
    cells, and ``GET /files/{id}/content`` serves the stored plaintext under the stored media type —
    so it is stored as ``application/octet-stream`` named ``<kind>.snapshot`` (UTF-8 CSV bytes
    inside, unchanged), never as a ``text/csv`` ``.csv`` a spreadsheet would open unguarded."""
    assert snapshots.MEDIA_TYPE == "application/octet-stream"
    assert snapshots.FILE_SUFFIX == ".snapshot"
    assert snapshots.dataset_filename("WATERFALL") == "WATERFALL.snapshot"
    assert snapshots.dataset_filename("WATERFALL") == f"WATERFALL{snapshots.FILE_SUFFIX}"
    assert not snapshots.dataset_filename("JE_POPULATION").endswith(".csv")


def _row(**values: Any) -> dict[str, Any]:
    return {
        "id": UUID(int=99),
        "sha256": "0" * 64,
        "media_type": snapshots.MEDIA_TYPE,
        "original_filename": snapshots.dataset_filename("WATERFALL"),
        **values,
    }


def test_the_machine_artefact_row_is_accepted() -> None:
    snapshots.assert_machine_artefact(_row(), "WATERFALL")  # no error


def test_a_reused_legacy_csv_row_is_refused_by_name() -> None:
    """D-98 candidate 145 (A), option (ii): ``store_file`` dedups on (tenant, sha256, purpose) and
    returns a retained row with its OLD metadata; a ``text/csv`` / ``<kind>.csv`` row from before
    the machine-artefact ruling must not be frozen as if it were the artefact — the freeze refuses
    by name (kind, file id, stored media / name, the expected pair) and nothing is deleted or
    rewritten."""
    with pytest.raises(snapshots.MachineArtefactRefused) as caught:
        snapshots.assert_machine_artefact(
            _row(media_type="text/csv", original_filename="WATERFALL.csv"), "WATERFALL"
        )
    message = str(caught.value)
    for named in (
        "WATERFALL",
        str(UUID(int=99)),
        "text/csv",
        "WATERFALL.csv",
        "application/octet-stream",
        "WATERFALL.snapshot",
        "D-98 candidate 145",
    ):
        assert named in message, message


def test_a_right_media_wrong_name_row_is_refused_too() -> None:
    with pytest.raises(snapshots.MachineArtefactRefused):
        snapshots.assert_machine_artefact(_row(original_filename="WATERFALL.csv"), "WATERFALL")
    with pytest.raises(snapshots.MachineArtefactRefused):
        snapshots.assert_machine_artefact(
            _row(original_filename="JE_POPULATION.snapshot"), "WATERFALL"
        )
