"""F-RPS-CUTOFF-R1 — the later-version witness at the REAL boundaries (Codex 1952 item 1): the
run, its rerun and its saved output, through ``POST /report-runs``, the worker, ``POST
/report-runs/{id}/rerun`` and ``GET /report-runs/{id}/data``. DB-bound: written for the lane's
``erev_rv_l17_test`` and recorded **not run — databases not provisioned**; it runs in an admitted
database stage (the integrated batch's ``ci`` stage collects this directory).

``contract_history`` rows are one per obligation version the run can see (row key
``version:<external id>:<version no>:<obligation key>``), so a later contract version shows as
rows, not as money. The world is WLD-K-01 (``SF-ORD-10001``); the later version comes from a
billing appended and computed AFTER the original runs, exactly as F-CLO's as-locked test moves the
live source.

- ``historical`` basis (a run created with ``known_at`` = the server stamp taken before the later
  version): the rerun preserves the requested cutoff and, for THIS dataset (event and computation
  both after the stamp), selects the original version rows — an AUTHORED DB case (NOT RUN) with
  the intended assertion scope; a result exists only when the admitted candidate-bound execution
  retains it; not a general reproduction guarantee (Codex 2015 / 2052). Codex 2000's
  deferred-computation case — an
  event admitted before the stamp, computed later, so the new version's ``known_at``
  (the greatest event ``recorded_at``, not the persistence time) is still below the fixed cutoff —
  is not exercised here; binding the consumed sources is frps3b's control.
- ``record`` basis (``known_at`` defaulted to the application clock): before frps3b the rerun
  resolved against the CURRENT request's transaction time, so the later version entered it while
  the original output stayed saved (Codex 1952's residual, carried as a strict expected failure).
  frps3b (S15-R-24) binds the consumed sources with the run and the rerun resolves against the
  binding, so the same-rows expectation now stands as a plain assertion — the marker came off
  with the fix, as §43.1 promised; a mismatch raises ``ProvenanceMismatch``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract, contract_version
from erev_api.domain.reports.catalogue import HISTORICAL_BASIS, KNOWN_AT_BASIS_KEY, RECORD_BASIS
from erev_api.domain.reports.outputs import utc_text
from erev_api.enums import ContractEventType
from erev_api.events.payloads import BillingRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.money import MoneyIn
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import appended, computed
from support.reference import get, post
from support.worlds import (
    AVM_US,
    K01,
    REPORT_RUN_ID_HEADER,
    REPORT_RUNS,
    ReportWorld,
    k01_pellworth,
    report_run,
    resigned,
    run_now,
)

CODE: Final = "contract_history"
HISTORY: Final = {"entity_codes": [AVM_US], "book": "ASC606", "contract_external_id": K01}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> ReportWorld:
    return k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _rerun(world: ReportWorld, run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """``POST /report-runs/{id}/rerun`` (REQ-RPT-002), the job run as the worker does, then the
    new run and its data rows."""
    started = post(world.app, f"{REPORT_RUNS}/{run_id}/rerun", world.maya, {})
    assert started.status_code == 202, started.text
    new_id = started.headers[REPORT_RUN_ID_HEADER]
    finished = run_now(world, UUID(str(started.json()["id"])))
    assert finished["state"] == "SUCCEEDED", finished
    shown = get(world.app, f"{REPORT_RUNS}/{new_id}", world.maya)
    assert shown.status_code == 200, shown.text
    listed = get(world.app, f"{REPORT_RUNS}/{new_id}/data", world.maya, {"limit": "200"})
    assert listed.status_code == 200, listed.text
    return dict(shown.json()), list(listed.json()["items"])


def _keys(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row["row_key"]) for row in rows}


class ProvenanceMismatch(Exception):
    """Raised ONLY where the preserved final provenance comparison mismatches (Codex 2058): a
    distinct failure type, so a setup ``AssertionError`` (the ``world`` fixture's ``k01_pellworth``
    asserts HTTP statuses; helpers assert mapping / book / compute results) is never confused with
    the provenance comparison. frps3b binds the sources, so this is a plain failure signal now."""


def _prerequisite(condition: bool, what: str) -> None:
    """A setup condition that is NOT the comparison under test: its failure is a RuntimeError, kept
    distinct from ``ProvenanceMismatch`` (Codex 2048 / 2058)."""
    if not condition:
        raise RuntimeError(f"prerequisite not met (not the frps3b residual): {what}")


def _stream_head(world: ReportWorld, contract_id: UUID) -> int:
    """The contract's ACTUAL admitted stream head (T-CON-05), read from the row — never a literal:
    the k01_pellworth world appends four seeded events after activation, so the head is not 3."""
    return int(
        world.place.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
    )


def _version_count(world: ReportWorld, group_id: UUID) -> int:
    return int(
        world.place.scalar(
            select(func.count())
            .select_from(contract_version)
            .where(contract_version.c.combination_group_id == group_id)
        )
    )


def _later_version(world: ReportWorld) -> None:
    """A billing appended to SF-ORD-10001 at its ACTUAL stream head and computed: a new contract
    version, recorded (DB-08) after every stamp taken before this call. Every step is asserted as a
    prerequisite (a visible failure), never as the residual."""
    booked = world.contracts[K01]
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))
    head, versions = _stream_head(world, contract_id), _version_count(world, group_id)
    _prerequisite(head >= 2 and versions >= 1, f"fixture head {head} / versions {versions}")
    appended(
        world.place,
        contract_id,
        head,
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 9, 15),
                payload=BillingRecordedV1(
                    invoice_number="INV-US-1099",
                    line_external_id="INV-US-1099-1",
                    obligation_key="O1",
                    amount=MoneyIn(amount="5000.00", currency="USD"),
                    issue_date=date(2026, 9, 15),
                ),
            )
        ],
    )
    _prerequisite(_stream_head(world, contract_id) == head + 1, "the billing was not appended")
    computed(world.place, group_id)
    _prerequisite(_version_count(world, group_id) == versions + 1, "no new version was computed")


def _run_then_later_version_then_rerun(
    world: ReportWorld, parameters: dict[str, Any], basis: str
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Setup shared by both cases: the original run, the later version, the rerun — every setup
    condition a visible prerequisite (HTTP status, stored basis, version-1 rows, the stored
    parameters carried by the rerun). Returns the original run and rows, the rerun and its rows."""
    try:
        original, rows = report_run(world, CODE, parameters)
        _prerequisite(original["parameters"][KNOWN_AT_BASIS_KEY] == basis, f"stored basis {basis}")
        _prerequisite(
            bool(rows) and all(key.startswith(f"version:{K01}:1:") for key in _keys(rows)),
            "the original run's rows are version-1 rows",
        )
        _later_version(world)
        rerun, rerun_rows = _rerun(world, str(original["id"]))
        _prerequisite(rerun["parameters"] == original["parameters"], "REQ-RPT-002 parameters")
    except AssertionError as exc:  # the helpers assert HTTP statuses: setup, not the residual
        raise RuntimeError(f"setup failed before the residual assertion: {exc}") from exc
    return original, rows, rerun, rerun_rows


def test_a_historical_rerun_keeps_the_requested_cutoff_for_this_dataset(
    world: ReportWorld, clock: FrozenClock
) -> None:
    stamp = world.place.scalar(select(func.clock_timestamp()))
    _prerequisite(isinstance(stamp, datetime), "clock_timestamp()")
    clock.set(stamp + timedelta(seconds=1))  # record-time clock: the stamp is not "later than now"
    world = resigned(world)  # the jump (+ days) would end every session at the 12-hour limit
    original, rows, rerun, rerun_rows = _run_then_later_version_then_rerun(
        world, {**HISTORY, "known_at": utc_text(stamp)}, HISTORICAL_BASIS
    )
    assert _keys(rerun_rows) == _keys(rows)  # this dataset: the later version does not enter
    assert rerun["control_totals"] == original["control_totals"]


def test_a_record_basis_rerun_keeps_its_original_version_rows(world: ReportWorld) -> None:
    _, rows, _, rerun_rows = _run_then_later_version_then_rerun(world, HISTORY, RECORD_BASIS)
    # frps3b: the rerun resolves against the bound sources, so version 2 rows do not enter it.
    if _keys(rerun_rows) != _keys(rows):
        raise ProvenanceMismatch(
            f"rerun rows differ from the original: {sorted(_keys(rerun_rows) ^ _keys(rows))}"
        )
