"""RPS-SNAP SNAP-1b DB witnesses for `erev_api.domain.reports.snapshots` (design note
PRODUCTION-F-RPS-RPS-SNAP-DESIGN.md §6, §13; record §50). DB-bound: written for the lane's
``erev_rv_l17_test`` and recorded NOT RUN (the lane database is absent, Ray-side); first run in
lane FIX-D2's database (2026-09-29).

Chronology (A4 13.3 R1; DG-TST-14 — the frozen clock is moved explicitly): the world is built on
the APPLICATION clock at T0 (2026-09-12T12:00Z); four additional contracts are booked, activated
and computed at T0 — the two identity pairs of Codex 1653 (`=A` / `'=A`; `A:B` + `C` / `A` +
`B:C`), each a 2026 PLATFORM line active in September; the September journal is calculated at T0.
The retained inputs carry TWO record clocks (F-RPS-CUTOFF-R1; dev-guide DG-AK-41 rev 1.39;
``test_historical_line_cutoff_db.py``): subledger and journal lines the application clock (T0),
but a contract version is known at its events' SERVER ``recorded_at`` (04 DB-08: ``now()``) — the
wall clock of the run, days after T0. A freeze reads on the historical basis (READ-1: the supplied
cutoff exactly), so a cutoff on the business clock an hour after T0 precedes every version and
freezes — and compares against — an EMPTY population (measured in lane FIX-D2: five witnesses
failed on the missing population while the wrapped equalities held vacuously). The scene therefore
moves the clock onto the RECORD-TIME clock, as ``test_report_run_clock_db.py`` does: T1 = one
second after the server stamp read once the world is committed (never earlier than T0 + 1 h) =
the CUTOFF (`SnapshotScope.known_at` = the clock: every retained input <= cutoff <= request
clock, so no request is refused as future).

(a) for the eight wrapped kinds, the dataset frozen for (AVM-US, ASC606, FY2026-P09, T1) equals
    the LIVE report run a user would request for the same selectors and cutoff MINUS its
    presentation ``TOTAL:<ISO>`` rows: the rows' CANONICAL texts (raw, A4 13.1) and the builder's
    control totals; the re-lock consumer accepts every header. Population is asserted per kind
    (R3): non-empty where the fixture provides one, legitimately EMPTY for COST_ROLLFORWARD.
(a') ``WATERFALL`` and ``RPO`` are frozen LONG-FORM: both collision pairs are four distinct keyed
    rows, `decode_row_key(row_key)` is the key tuple, the figures sum to the live totals.
(a'') ``JE_POPULATION`` at ``frozen_at``: after T1 the clock advances one hour to T2 and the
    journal is recalculated (cancel + calculate again); the T2 lines are in the dataset frozen
    at T2 and not in the dataset frozen at the cutoff; the scope without ``frozen_at`` equals
    the cutoff one.
(b) F-CLO's real ``freeze_datasets`` refuses the lock by NAME with exactly the ONE kind a registry
    deliberately withholds (``MANUAL_ADJUSTMENT_REGISTER`` in the witness; twelve of twelve are
    registered) and writes NOTHING.
(c) as-locked runs over datasets this registry froze, planted through the private CLO-8 writer
    fixture of test_as_locked.py (writer-fixture evidence, not public freeze proof): the CSV run
    of a dataset holding `=A` serves the GUARDED export (`'=A`) whose hash is the run's
    ``output_sha256`` and the RV-02 manifest's while the frozen artefact keeps `=A` and its
    `file_sha256` — and the generic ``GET /files/{id}/content`` serves that artefact as a MACHINE
    artefact — exact bytes and hash, `application/octet-stream`, `<kind>.snapshot` (A4 13.5 (ii);
    the constants are F-CLO's line-2 change, which lands BEFORE this slice — planted here through
    the imported MEDIA_TYPE); a JSON run serves the raw rows; the CSV run of a trigger-free
    (header-only) dataset serves the frozen bytes themselves with ``output_sha256`` =
    ``file_sha256``.
(d) the production future-cutoff refusal is untouched: a request with `known_at` after the clock
    is refused at creation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.tables import file_object, journal_line, legal_entity, lock_snapshot, period
from erev_api.domain.close import dependencies as close_dependencies
from erev_api.domain.close import relock_diff
from erev_api.domain.close import snapshots as close_snapshots
from erev_api.domain.reports import locked, snapshots
from erev_api.domain.reports.builders import contract_balance_rollforward as cbr_builder
from erev_api.domain.reports.builders import rpo as rpo_builder
from erev_api.domain.reports.outputs import csv as csv_output
from erev_api.domain.reports.outputs import utc_text
from erev_api.enums import FilePurpose
from erev_api.files.store import LocalFileStore, store_file
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select
from support.db import TestDatabase
from support.factories import booked_contract, computed
from support.record_clock import on_record_time
from support.reference import get, post
from support.worlds import (
    AVM_US,
    K01,
    REPORT_RUNS,
    ReportWorld,
    journal_run,
    k01_body,
    k01_pellworth,
    recalculated_journal,
    resigned,
)
from support.worlds import report_run as run_report

BOOK: Final = "ASC606"
SEPTEMBER: Final = "FY2026-P09"
DEPENDENT: Final[tuple[str, ...]] = ()  # twelve of twelve: F-CLO's manual_adjustment_register in
ID1_PAIR: Final = (("=A", "POB1"), ("'=A", "POB1"))  # the export guard would merge the ids
ID2_PAIR: Final = (("A:B", "C"), ("A", "B:C"))  # an unescaped ``:`` join would merge the keys
PAIRS: Final = (*ID1_PAIR, *ID2_PAIR)
# the ten adapter kinds and the report request a user would make for the lock's scope
REQUESTS: Final[dict[str, dict[str, Any]]] = {
    "WATERFALL": {"from_period_key": SEPTEMBER, "to_period_key": SEPTEMBER},
    "CONTRACT_BALANCES": {"period_key": SEPTEMBER},
    "CONTRACT_BALANCE_ROLLFORWARD": {"from_period_key": SEPTEMBER, "to_period_key": SEPTEMBER},
    "RPO": {"period_key": SEPTEMBER},
    "RPO_ROLLFORWARD": {"from_period_key": SEPTEMBER, "to_period_key": SEPTEMBER},
    "DISAGGREGATION": {"from_period_key": SEPTEMBER, "to_period_key": SEPTEMBER},
    "PRIOR_PERIOD_POB_REVENUE": {"from_period_key": SEPTEMBER, "to_period_key": SEPTEMBER},
    "COST_ROLLFORWARD": {"from_period_key": SEPTEMBER, "to_period_key": SEPTEMBER},
    "JE_POPULATION": {"from_period_key": SEPTEMBER, "to_period_key": SEPTEMBER},
    "OUT_OF_PERIOD_REGISTER": {"from_period_key": SEPTEMBER, "to_period_key": SEPTEMBER},
    # SNAP-2 (§14): a DATE-selected report takes the lock period's bounds
    "MODIFICATION_REGISTER": {"from_date": "2026-09-01", "to_date": "2026-09-30"},
    "MANUAL_ADJUSTMENT_REGISTER": {"from_period_key": SEPTEMBER, "to_period_key": SEPTEMBER},
}
WRAPPED: Final = tuple(k for k in sorted(REQUESTS) if k not in ("WATERFALL", "RPO"))
# R3: what the fixture's population lets a witness assert about a wrapped kind's row count
POPULATED: Final = frozenset(
    {
        "CONTRACT_BALANCES",
        "CONTRACT_BALANCE_ROLLFORWARD",  # nine line rows + one by-contract row per contract
        "DISAGGREGATION",
        "JE_POPULATION",
        "RPO_ROLLFORWARD",  # ten line rows + one by-contract row per contract
    }
)
LEGITIMATELY_EMPTY: Final = frozenset(
    {"COST_ROLLFORWARD", "MODIFICATION_REGISTER", "MANUAL_ADJUSTMENT_REGISTER"}
)  # no cost; no modifications; no manual adjustment posted by the scene


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> ReportWorld:
    return k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))


@dataclass(frozen=True)
class Scene:
    world: ReportWorld
    clock: FrozenClock
    t0: datetime  # the application clock of the world and of the September journal
    cutoff: datetime  # T1 = SnapshotScope.known_at = the record-time clock at the requests
    journal: dict[str, Any]  # the T0 journal run (API-S-JournalRun)


def _pair_body(world: ReportWorld, external_id: str, obligation_key: str) -> dict[str, Any]:
    """A contract of the K01 customer with ONE 2026 PLATFORM line (ratable daily; active in
    September; RPO remaining after it) under the given identity."""
    customer = world.contracts[K01].contract["customer_id"]
    body = k01_body(UUID(str(customer)))
    body["external_id"] = external_id
    body["lines"] = [{**body["lines"][0], "obligation_key": obligation_key}]
    return body


@pytest.fixture
def scene(world: ReportWorld, clock: FrozenClock) -> Scene:
    t0 = clock.now()
    for external_id, obligation_key in PAIRS:
        found = booked_contract(
            world.place, _pair_body(world, external_id, obligation_key), activate=True
        )
        computed(world.place, UUID(str(found.combination_group["id"])))
    journal = journal_run(world)  # September, AVM-US, at T0: the JE population before the cutoff
    clock.advance(timedelta(hours=1))
    # The record-time clock (module docstring): the cutoff follows the SERVER stamp of the last
    # commit — the versions' ``known_at`` — and is never earlier than T0 + 1 h. Codex 1824 §3
    # (RPS-SNAP-TEST-SESSION-1): every actor is re-signed after the move (the helper calls
    # `worlds.resigned`), never a global session extension.
    world = on_record_time(world)
    _prerequisite(clock.now() >= t0 + timedelta(hours=1), "the cutoff follows T0")
    return Scene(world=world, clock=clock, t0=t0, cutoff=clock.now(), journal=journal)


def _prerequisite(condition: bool, what: str) -> None:
    if not condition:
        raise RuntimeError(f"prerequisite not met (not the registry under test): {what}")


def _scope(scene: Scene, *, frozen_at: datetime | None = None) -> snapshots.SnapshotScope:
    world = scene.world
    period_id = world.place.scalar(
        select(period.c.id)
        .join(legal_entity, legal_entity.c.calendar_id == period.c.calendar_id)
        .where(legal_entity.c.id == world.entity_id, period.c.period_key == SEPTEMBER)
    )
    return snapshots.SnapshotScope(
        entity_id=world.entity_id,
        book_code=BOOK,
        period_id=UUID(str(period_id)),
        known_at=scene.cutoff,
        frozen_at=frozen_at,
    )


def _frozen(scene: Scene, kind: str, *, frozen_at: datetime | None = None) -> Any:
    with scene.world.place.uow() as uow:
        encoded = snapshots.SNAPSHOT_DATASETS[kind](uow, _scope(scene, frozen_at=frozen_at))
        uow.commit()  # the freeze writes nothing itself
    return encoded


def _live(scene: Scene, code: str, kind: str, *, output_format: str = "JSON") -> Any:
    return run_report(
        scene.world,
        code,
        {
            "entity_codes": [AVM_US],
            "book": BOOK,
            **REQUESTS[kind],
            "known_at": utc_text(scene.cutoff),  # the cutoff = the clock: never future
        },
        output_format=output_format,
    )


def _typed(column: Any, value: Any) -> Any:
    """A live JSON cell as the builder's value of its column kind: ``csv.canonical`` reads the
    typed values of ``outputs`` ("``date`` a date; ``timestamp`` an aware datetime"), and the API
    states exactly those two kinds as text (``outputs.json_value``: ISO date, RFC 3339 UTC) — the
    text is parsed back, every other kind's JSON value is already what ``canonical`` reads."""
    if value is None:
        return None
    if column.kind == "date":
        return date.fromisoformat(str(value))
    if column.kind == "timestamp":
        return datetime.fromisoformat(str(value))
    return value


def _texts(rows: list[dict[str, Any]], columns: Any) -> list[dict[str, str]]:
    """The live rows as canonical texts (A4 13.1: raw, exactly what the frozen file stores)."""
    return [
        {
            "row_key": str(row["row_key"]),
            **{c.key: csv_output.canonical(c, "value", _typed(c, row.get(c.key))) for c in columns},
        }
        for row in rows
    ]


def _columns(shown: list[dict[str, Any]]) -> Any:
    from erev_api.domain.reports.outputs import Column

    return tuple(Column(c["key"], c["header"], c["kind"]) for c in shown)


def _plant(world: ReportWorld, lock_id: UUID, encoded: Any) -> UUID:
    """Store the encoded bytes exactly as F-CLO's writer does (`close/snapshots.py:84–90`) through
    F-CLO's IMPORTED constants only — `MEDIA_TYPE` and `FILE_SUFFIX` (Codex 1824 §3: a private
    fallback literal proves nothing; on a head where F-CLO's line-2 slice b has not landed this
    fails by name) — and write the T-CLS-05 row of the lock (`report_run_id` NULL, ruling Q-10);
    returns the FILE id (A4 13.5: a machine artefact; F-CLO line 2 lands before SNAP-1b)."""
    suffix = close_snapshots.FILE_SUFFIX  # F-CLO's constant (Q11); no fallback
    with world.place.uow() as uow:
        stored = store_file(
            uow,
            purpose=FilePurpose.SNAPSHOT_DATASET,
            stream=BytesIO(bytes(encoded.content)),
            original_filename=f"{encoded.kind}{suffix}",
            media_type=close_snapshots.MEDIA_TYPE,
        )
        assert str(stored["sha256"]) == encoded.file_sha256  # S15-INV-06
        row = {
            "tenant_id": world.tenant_id,
            "id": new_id(),
            "period_lock_id": lock_id,
            "snapshot_kind": encoded.kind,
            "report_run_id": None,
            "file_id": stored["id"],
            "file_sha256": encoded.file_sha256,
            "row_count": encoded.row_count,
            "control_totals": dict(encoded.control_totals),
            "created_at": uow.now,
            "created_by": None,
            "created_by_kind": "SYSTEM",
        }
        uow.session.execute(insert(lock_snapshot).values(**row))
        uow.commit()
    return UUID(str(stored["id"]))


def _accepted_by_relock(kind: str, encoded: Any) -> dict[tuple[str, ...], Any]:
    headers, rows = locked._rows(encoded.content)
    return relock_diff._keyed(kind, headers, rows, relock_diff.key_columns_of(kind))


# --- (a) the eight wrapped kinds equal the live report minus its presentation totals -------------


@pytest.mark.parametrize("kind", WRAPPED)
def test_a_wrapped_kind_equals_the_live_report_without_presentation_totals(
    scene: Scene, kind: str
) -> None:
    code = next(c for c, k in locked.SNAPSHOT_KIND_BY_REPORT.items() if k == kind)
    encoded = _frozen(scene, kind)
    live, rows = _live(scene, code, kind)  # a JSON run: its data rows are the comparison
    _prerequisite(live["status"] == "SUCCEEDED", f"live {code} run")
    kept = [r for r in rows if not str(r["row_key"]).startswith(snapshots.TOTAL_PREFIX)]
    assert encoded.kind == kind and encoded.row_count == len(kept)
    assert dict(encoded.control_totals) == dict(live["control_totals"])
    frozen_rows = locked.report_data(
        locked.LockedDataset(
            lock_id=scene.world.entity_id,  # any id: only the bytes are read here
            kind=kind,
            file_id=scene.world.entity_id,
            file_sha256=encoded.file_sha256,
            row_count=encoded.row_count,
            control_totals=dict(encoded.control_totals),
            content=encoded.content,
        )
    ).rows
    page = get(
        scene.world.app, f"{REPORT_RUNS}/{live['id']}/data", scene.world.maya, {"limit": "200"}
    )
    _prerequisite(page.status_code == 200, page.text)
    assert {r["row_key"]: r for r in frozen_rows} == {
        r["row_key"]: r for r in _texts(kept, _columns(page.json()["columns"]))
    }
    keyed = _accepted_by_relock(kind, encoded)  # the re-lock consumer accepts the header and rows
    assert len(keyed) == len(kept)
    if kind in POPULATED:
        assert keyed, f"{kind}: the fixture provides a population"
    if kind in LEGITIMATELY_EMPTY:
        assert not keyed and encoded.row_count == 0  # header-only == the empty live run


def test_the_raw_identity_pair_is_two_contract_balance_rows(scene: Scene) -> None:
    """A4 13.1 on real data: `=A` and `'=A` are two frozen rows with raw identity cells."""
    keyed = _accepted_by_relock("CONTRACT_BALANCES", _frozen(scene, "CONTRACT_BALANCES"))
    assert {(AVM_US, "=A"), (AVM_US, "'=A"), (AVM_US, "A:B"), (AVM_US, "A")} <= set(keyed)


# --- supervisor ruling R-4: the two rollforwards, two row types under one key ---------------------

ROLLFORWARDS: Final = (
    ("CONTRACT_BALANCE_ROLLFORWARD", cbr_builder.LINES, "contract_liability"),
    ("RPO_ROLLFORWARD", rpo_builder.ROLLFORWARD_LINES, "rpo"),
)


@pytest.mark.parametrize(("kind", "lines", "measure"), ROLLFORWARDS)
def test_a_rollforward_is_frozen_with_its_line_rows_and_its_by_contract_rows(
    scene: Scene, kind: str, lines: tuple[str, ...], measure: str
) -> None:
    """R-4 (P1; 2026-09-29) on real data: a POPULATED rollforward freezes — one line row per line
    code keyed (`line_code`, "", currency) and one by-contract row per contract keyed ("",
    `contract_external_id`, currency), the raw pair `=A` / `'=A` two rows (04 T-CLS-05 dataset
    identity, D-98 85) — the re-lock consumer accepts it and the by-contract closings sum to the
    CLOSING line. Fail-first in lane FIX-D2, before the builders stated the inapplicable key column:
    ``SnapshotRefusal: <kind>: row OPENING lacks the required column contract_external_id`` — the
    refusal every period lock with contract-balance activity met."""
    encoded = _frozen(scene, kind)
    keyed = _accepted_by_relock(kind, encoded)
    contracts = {K01, *(external_id for external_id, _ in PAIRS)}
    assert set(keyed) == {
        *((line, "", "USD") for line in lines),
        *(("", external_id, "USD") for external_id in contracts),
    }
    assert encoded.row_count == len(lines) + len(contracts)
    for (line_code, external_id, _), row in keyed.items():
        assert row["section"] == ("1" if line_code else "2"), row["row_key"]
        assert bool(line_code) is not bool(external_id), row["row_key"]
    closing = Decimal(keyed[("CLOSING", "", "USD")][measure])
    assert closing != 0, f"{kind}: the fixture provides a closing balance"
    assert closing == sum(
        Decimal(keyed[("", external_id, "USD")]["closing"]) for external_id in contracts
    )


# --- (a') the long-form kinds over the real populations ------------------------------------------


def test_waterfall_is_frozen_long_form_with_both_pairs_and_accepted_by_the_relock_consumer(
    scene: Scene,
) -> None:
    encoded = _frozen(scene, "WATERFALL")
    keyed = _accepted_by_relock("WATERFALL", encoded)
    expected = {(AVM_US, ext, ob, SEPTEMBER) for ext, ob in PAIRS}
    assert expected <= set(keyed)  # four distinct admitted rows; K01 O2 has no September row
    for key, row in keyed.items():
        assert snapshots.decode_row_key(str(row["row_key"])) == key
        assert key[0] == AVM_US and key[3] == SEPTEMBER
    live, _ = _live(scene, "revenue_waterfall", "WATERFALL")
    for measure, name in (
        ("recognised", "recognized_total"),
        ("scheduled", "scheduled_total"),
        ("awaiting_trigger", "awaiting_trigger_total"),
    ):
        frozen_sum = sum(Decimal(row[measure]) for row in keyed.values())
        assert frozen_sum == Decimal(live["control_totals"][name].get("USD", "0")), measure
    assert encoded.control_totals["row_count"] == len(keyed)


def test_rpo_is_frozen_long_form_with_both_pairs_and_accepted_by_the_relock_consumer(
    scene: Scene,
) -> None:
    encoded = _frozen(scene, "RPO")
    keyed = _accepted_by_relock("RPO", encoded)
    assert {(AVM_US, ext, ob) for ext, ob in PAIRS} <= set(keyed)
    for key, row in keyed.items():
        assert snapshots.decode_row_key(str(row["row_key"])) == key
    live, _ = _live(scene, "rpo", "RPO", output_format="CSV")  # CSV: nothing hidden for relief
    ordinary = [row for row in keyed.values() if row["section"] == "1"]
    assert sum(Decimal(row["total"]) for row in ordinary) == Decimal(
        live["control_totals"]["total"].get("USD", "0")
    )
    assert encoded.control_totals["excluded_total"] == live["control_totals"]["excluded_total"]
    assert encoded.control_totals["rpo_relief_elected"] == []  # the k01 world elects no relief


# --- (a'') JE_POPULATION at the freeze instant ----------------------------------------------------


def _je_numbers(encoded: Any) -> set[str]:
    _, rows = locked._rows(encoded.content)
    return {str(row["je_no"]) for row in rows}


def test_je_population_is_frozen_at_the_freeze_instant_when_given(scene: Scene) -> None:
    """S15-R-18b Q5 with a legal chronology: the T0 journal is in the cutoff dataset; after the
    cutoff the clock advances to T2 and the journal is recalculated through the public helper
    (cancel, then calculate again) — its lines are stamped T2; the scope with `frozen_at = T2`
    holds the T2 run and not the (then cancelled) T0 run; the scope without `frozen_at` equals
    the cutoff dataset."""
    at_cutoff = _frozen(scene, "JE_POPULATION")
    _prerequisite(bool(_je_numbers(at_cutoff)), "the T0 journal is in the cutoff population")
    scene.clock.advance(timedelta(hours=1))
    world = resigned(scene.world)  # RPS-SNAP-TEST-SESSION-1: fresh sessions after the advance
    later = recalculated_journal(world, scene.journal)
    _prerequisite("id" in later, f"recalculated journal {later}")
    latest = world.place.scalar(select(func.max(journal_line.c.created_at)))
    _prerequisite(latest is not None and latest > scene.cutoff, "lines stamped after the cutoff")
    with_freeze = _frozen(scene, "JE_POPULATION", frozen_at=scene.clock.now())
    without = _frozen(scene, "JE_POPULATION")
    assert _je_numbers(with_freeze) and _je_numbers(at_cutoff)
    assert _je_numbers(with_freeze).isdisjoint(_je_numbers(at_cutoff))
    assert without.content == at_cutoff.content and without.file_sha256 == at_cutoff.file_sha256


# --- (b) the F-CLO seam ---------------------------------------------------------------------------


def test_f_clo_freeze_refuses_by_name_and_writes_nothing(scene: Scene) -> None:
    """Twelve of twelve: the real registry refuses nothing, so the by-name refusal is proven with a
    registry that deliberately withholds F-CLO's kind — exactly that kind is named and NOTHING is
    written (the twelve-row public freeze witness is CLO-8c's, test_lock.py)."""
    world = scene.world
    files_before = int(world.place.scalar(select(func.count()).select_from(file_object)))
    rows_before = int(world.place.scalar(select(func.count()).select_from(lock_snapshot)))
    scope = _scope(scene)
    withheld = {
        k: v for k, v in snapshots.SNAPSHOT_DATASETS.items() if k != "MANUAL_ADJUSTMENT_REGISTER"
    }
    with world.place.uow() as uow, pytest.raises(close_dependencies.ProducerMissing) as refused:
        close_snapshots.freeze_datasets(
            uow,
            scope.entity_id,
            scope.book_code,
            scope.period_id,
            scope.known_at,
            registry=withheld,
            scope_type=snapshots.SnapshotScope,
        )
    assert refused.value.names == ("MANUAL_ADJUSTMENT_REGISTER",)
    assert int(world.place.scalar(select(func.count()).select_from(file_object))) == files_before
    assert int(world.place.scalar(select(func.count()).select_from(lock_snapshot))) == rows_before


# --- (c) as-locked runs over datasets this registry froze (private writer fixture) ----------------


def test_an_as_locked_csv_run_serves_the_guarded_export_and_keeps_the_raw_artefact(
    scene: Scene,
) -> None:
    """A4 13.1 export positive control (R2: a CSV run for the CSV oracle; a JSON run for rows)."""
    from tests.domain.reports import test_as_locked as fixture  # the private lock fixture (CLO-8)

    world = scene.world
    encoded = _frozen(scene, "CONTRACT_BALANCES")
    _prerequisite(b",=A," in encoded.content and b",'=A," in encoded.content, "raw pair frozen")
    lock_id = fixture._lock_by_writer(world)
    file_id = _plant(world, lock_id, encoded)
    run, _ = run_report(
        world,
        "contract_balances",
        {**fixture.BALANCES, "period_lock_id": str(lock_id)},
        output_format="CSV",
    )
    assert run["status"] == "SUCCEEDED" and run["row_count"] == encoded.row_count
    shown = get(world.app, f"{REPORT_RUNS}/{run['id']}/output", world.maya)
    assert shown.status_code == 200
    assert hashlib.sha256(shown.content).hexdigest() == run["output"]["sha256"]
    assert run["output"]["sha256"] != encoded.file_sha256  # a guarded cell: the served hash
    assert b",'=A," in shown.content and b",=A," not in shown.content  # the export is guarded
    manifest = get(world.app, f"{REPORT_RUNS}/{run['id']}/output", world.maya, {"part": "manifest"})
    assert manifest.status_code == 200, manifest.text
    assert manifest.json()["sha256"] == run["output"]["sha256"]  # RV-02: the DELIVERED bytes
    # A4 13.5 (ii): the generic file download is the MACHINE ARTEFACT — exact bytes, exact hash,
    # no spreadsheet association; the raw `=A` is inside the bytes, never a spreadsheet document.
    meta = get(world.app, f"/api/v1/files/{file_id}", world.maya)
    assert meta.status_code == 200 and meta.json()["sha256"] == encoded.file_sha256
    assert meta.json()["media_type"] == close_snapshots.MEDIA_TYPE == "application/octet-stream"
    assert str(meta.json()["original_filename"]).endswith(close_snapshots.FILE_SUFFIX)  # Q11
    assert (
        close_snapshots.FILE_SUFFIX == ".snapshot"
    )  # the ruled representation, by F-CLO's constant
    artefact = get(world.app, f"/api/v1/files/{file_id}/content", world.maya)
    assert artefact.status_code == 200 and artefact.content == encoded.content
    assert artefact.headers["content-type"].startswith("application/octet-stream")
    assert close_snapshots.FILE_SUFFIX in artefact.headers["content-disposition"]
    assert hashlib.sha256(artefact.content).hexdigest() == encoded.file_sha256
    with world.place.uow() as uow:
        stored = locked.locked_dataset(uow, report_code="contract_balances", lock_id=lock_id)
    assert locked.verify(stored).content == encoded.content  # the artefact is raw and intact
    as_json, rows = run_report(
        world, "contract_balances", {**fixture.BALANCES, "period_lock_id": str(lock_id)}
    )
    assert as_json["status"] == "SUCCEEDED"
    assert {"=A", "'=A"} <= {str(row["contract_external_id"]) for row in rows}  # raw rows


def test_an_as_locked_csv_run_of_a_trigger_free_dataset_is_the_frozen_file_itself(
    scene: Scene,
) -> None:
    from tests.domain.reports import test_as_locked as fixture

    world = scene.world
    encoded = _frozen(scene, "COST_ROLLFORWARD")
    _prerequisite(encoded.row_count == 0, "K01 and the pairs carry no cost movement")
    lock_id = fixture._lock_by_writer(world)
    _plant(world, lock_id, encoded)
    run, _ = run_report(
        world,
        "contract_cost_rollforward",
        {
            "entity_codes": [AVM_US],
            "book": BOOK,
            **REQUESTS["COST_ROLLFORWARD"],
            "period_lock_id": str(lock_id),
        },
        output_format="CSV",
    )
    assert run["status"] == "SUCCEEDED" and run["output"]["sha256"] == encoded.file_sha256
    shown = get(world.app, f"{REPORT_RUNS}/{run['id']}/output", world.maya)
    assert shown.status_code == 200 and shown.content == encoded.content


# --- (d) the production future-cutoff refusal is untouched ----------------------------------------


def test_a_request_after_the_clock_is_still_refused_as_future(scene: Scene) -> None:
    started = post(
        scene.world.app,
        REPORT_RUNS,
        scene.world.maya,
        {
            "report_code": "contract_balances",
            "parameters": {
                "entity_codes": [AVM_US],
                "book": BOOK,
                **REQUESTS["CONTRACT_BALANCES"],
                "known_at": utc_text(scene.cutoff + timedelta(hours=1)),
            },
            "output_format": "JSON",
        },
    )
    assert started.status_code == 422 and "known_at" in started.text
