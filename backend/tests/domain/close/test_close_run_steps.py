"""CLO-20 close run period-end steps, journal summarization and dataset freeze (BUILD_SPEC CLO-20
acceptance; BS4-D-03, BS4-D-04; 03 REQ-CLS-012; 04 T-CLS-01, T-SL-01, T-SL-04, §14.1 DB-06, DB-07;
05 RCP-05 to RCP-08, SBX-08; ENGINE_SPEC_B §10, §11 S11-R-14, §12, §14 S14-R-05, Table 14-A,
§15.2.7 S15-R-18; POLICIES CHK-010, JET-06, JET-10a, JET-12; PRD SM-14, §2.5 AVM-RATES, §2.8
WLD-X-02, J-13.7; SCREENS_B §1.2; supervisor rulings R-79, R-99 (a), R-112 and R-114 (a)).

Each test runs whole close runs through ``POST /close-runs`` and the ``CLOSE_RUN`` job
(``support.close_runs.closed``) over a world built through the product's commands:

- ``worlds.k01_pellworth``: WLD-K-01, AVM-US with FY2026-P01 to P09 open; a deterministic schedule
  whose revenue the contract's computation posts, so the release pass has nothing to post;
- ``worlds.k03_castellan`` with ``close_run_worlds.k03_loss``: a cost-to-cost contract whose
  estimate at completion exceeds its unconstrained consideration — the loss provision is what only
  a period end decides — with a contract asset to reclassify at 31 Aug 2026, so that September
  closes only after August (supervisor ruling R-112);
- ``worlds.chk_010_position``: POLICIES CHK-010, unbilled receivable 3,000.00 and contract asset
  2,000.00 at 31 Jan 2026;
- ``close_run_worlds.eur_receivable``: a EUR receivable of AVM-US (USD) under the PRD §2.5 rates.

Expected amounts are the documents': a ledger assertion sums the lines of an account role and
never counts lines (a role delta may post as more than one line; supervisor rulings R-11, R-12,
R-44 (a)). A step's summary is rendered from its ``counts`` as SCREENS_B §1.2 words it
(``support.close_runs.summary``).
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    close_run,
    exception_item,
    file_object,
    gl_account,
    job,
    journal_batch,
    journal_run,
    lock_snapshot,
    obligation,
    outbox_message,
    period,
    period_lock,
    subledger_line,
    subledger_posting,
)
from erev_api.domain.close import close_runs, period_end
from erev_api.enums import CloseRunStatus, FilePurpose, GlAdapter, JournalState
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from erev_api.main import create_app
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.stages.s15_disclosures.snapshots import SNAPSHOT_KINDS
from fastapi import FastAPI
from sqlalchemy import and_, func, insert, select
from support import close_run_worlds, worlds
from support import close_runs as runs
from support import reconciliations as recon
from support.close_world import reviewed_reconciliations_for
from support.db import TestDatabase
from support.reference import PERIODS, approve, get, post
from support.rows import close_run_values, insert_journal_rows, insert_sandbox_tenant

AVM_US = worlds.AVM_US
US01 = worlds.US01
BOOK = "ASC606"
JANUARY = "FY2026-P01"
FEBRUARY = "FY2026-P02"
MARCH = "FY2026-P03"
AUGUST = "FY2026-P08"
SEPTEMBER = "FY2026-P09"
JOURNAL_RUNS = worlds.JOURNAL_RUNS
PASS_STEPS = ("FX_REMEASUREMENT", "RELEASE_SCHEDULES", "NETTING_RECLASS")
RECLASS = "NETTING_RECLASS"
REVERSAL = "NETTING_RECLASS_REVERSAL"
FX = "FX_REMEASUREMENT"
FAILED_CODE = "CLOSE_RUN_FAILED"
# WLD-K-03 at 31 Aug 2026 (PRD WLD-X-09): revenue 600,000.00 against invoices 550,000.00
K03_ASSET = {"CONTRACT_ASSET": Decimal("50000.00"), "CONTRACT_LIABILITY": Decimal("-50000.00")}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _usd(amount: str) -> Decimal:
    return Decimal(amount)


def _negated(amounts: dict[str, Decimal]) -> dict[str, Decimal]:
    return {role: -amount for role, amount in amounts.items()}


def _rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _count(tenant_id: UUID, statement: Any) -> int:
    """The single number ``statement`` selects."""
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return int(session.execute(statement).scalar_one())


def _counted(run: dict[str, Any], code: str, lines: list[dict[str, Any]], kind: str) -> None:
    """The step's ``lines`` and ``postings`` are what the ledger holds of that posting kind under
    the run (the count is the ledger's, not a figure of its own)."""
    of_kind = [line for line in lines if line["posting_kind"] == kind]
    counts = runs.step(run, code)["counts"]
    assert counts["lines"] == len(of_kind)
    assert counts["postings"] == len({line["posting_id"] for line in of_kind})


def _dates(lines: list[dict[str, Any]], *, period_key: str, entry_kind: str) -> set[date]:
    return {
        line["effective_date"]
        for line in lines
        if line["period_key"] == period_key and str(line["entry_kind"]) == entry_kind
    }


def _revenue_by_posting_kind(
    world: worlds.ReportWorld, obligation_key: str, period_key: str
) -> dict[str, Decimal]:
    """Σ functional amount of the obligation's ``REVENUE`` lines of the period, per posting kind
    (debit positive: recognised revenue is a credit)."""
    line, posting = subledger_line, subledger_posting
    rows = _rows(
        world.tenant_id,
        select(posting.c.posting_kind, func.sum(line.c.amount_functional).label("amount"))
        .select_from(
            line.join(
                posting,
                and_(
                    posting.c.tenant_id == line.c.tenant_id,
                    posting.c.id == line.c.subledger_posting_id,
                ),
            )
            .join(
                obligation,
                and_(
                    obligation.c.tenant_id == line.c.tenant_id,
                    obligation.c.id == line.c.obligation_id,
                ),
            )
            .join(
                period,
                and_(period.c.tenant_id == line.c.tenant_id, period.c.id == line.c.period_id),
            )
        )
        .where(
            obligation.c.obligation_key == obligation_key,
            line.c.account_role == "REVENUE",
            period.c.period_key == period_key,
        )
        .group_by(posting.c.posting_kind),
    )
    return {str(row["posting_kind"]): Decimal(row["amount"]) for row in rows}


def _failed_items(world: worlds.ReportWorld) -> list[dict[str, Any]]:
    return _rows(
        world.tenant_id,
        select(
            exception_item.c.status,
            exception_item.c.severity,
            exception_item.c.message,
            exception_item.c.close_run_id,
        ).where(exception_item.c.code == FAILED_CODE),
    )


# --- RELEASE_SCHEDULES ----------------------------------------------------------------------------


def test_release_schedules_k01_sep_2026(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-20 (supervisor ruling R-79 (a)): with ``worlds.k01_pellworth`` and Sep 2026
    open, the run's ``RELEASE_SCHEDULES`` step posts nothing for K-01 — O1's Sep 2026 revenue
    9,764.38 (WLD-X-02) is in the ledger as the contract's computation posted it, because the
    revenue of a deterministic schedule is posted when the contract is computed; a second run
    posts nothing either."""
    world = worlds.k01_pellworth(app, keyring, clock, files)
    # WLD-X-02: O1 Sep 2026 revenue 9,764.38, a credit, posted by the computation
    computed = {"ENGINE_COMPUTE": _usd("-9764.38")}
    assert _revenue_by_posting_kind(world, "O1", SEPTEMBER) == computed

    run = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert run["status"] == "SUCCEEDED"
    release = runs.step(run, "RELEASE_SCHEDULES")
    assert (release["status"], release["counts"]) == (
        "SUCCEEDED",
        {"postings": 0, "lines": 0, "groups": 1, "groups_skipped": 0},
    )
    assert runs.summary(run, "RELEASE_SCHEDULES") == "0 postings, 0 lines"
    # K-01 has nothing a period end decides: no pass sealed a line under the run
    assert runs.posted(world.tenant_id, run["id"]) == []
    assert (run["counts"]["postings"], run["counts"]["lines"]) == (0, 0)
    assert _revenue_by_posting_kind(world, "O1", SEPTEMBER) == computed

    second = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert second["id"] != run["id"] and second["status"] == "SUCCEEDED"
    assert runs.step(second, "RELEASE_SCHEDULES")["counts"]["lines"] == 0
    assert runs.posted(world.tenant_id, second["id"]) == []
    assert _revenue_by_posting_kind(world, "O1", SEPTEMBER) == computed


def test_release_schedules_posts_the_loss_provision_of_the_period_end(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supervisor ruling R-79 (a), (d): the release pass posts what only a period end decides.
    WLD-K-03 with an estimate at completion of 1,300,000.00 (``close_run_worlds.k03_loss``) is a
    loss contract — ENGINE_SPEC_B S11-R-14, S11-R-16: expected loss = 1,300,000.00 − 1,200,000.00
    unconstrained consideration = 100,000.00; loss through margin to date = costs 420,000.00 −
    revenue 323,076.92 = 96,923.08; required provision at 30 Sep 2026 = 3,076.92. The computation
    posts no provision; ``RELEASE_SCHEDULES`` posts Dr ``LOSS_EXPENSE`` 3,076.92 / Cr
    ``LOSS_PROVISION`` 3,076.92 (POLICIES JET-12) as the group's ``CLOSE_RELEASE`` posting
    ``release:<close run>:<group>``, dated the period end, with no computation, contract version
    or stored trace behind it (known limitation CLOSE-PASS-TRACE-1).

    Periods close in order (supervisor ruling R-112), so August's run comes first. It posts
    August's period end — the contract asset 50,000.00 at 31 Aug 2026 (revenue 600,000.00,
    WLD-X-09, against invoices 550,000.00) with its reversal on 1 Sep 2026 — and no provision:
    the estimate changes on 10 Sep 2026. September's run then posts the provision and nothing
    else: at 30 Sep 2026 the position is a liability, nothing is reclassified, and the reversal
    is in the ledger already. (What a second run posts for a loss unit is the next test; a run of
    September before August's is the two after it.)"""
    world = worlds.k03_castellan(app, keyring, clock, files)
    close_run_worlds.k03_loss(world, clock)
    report = world.report
    provisions = select(func.count()).where(subledger_line.c.account_role == "LOSS_PROVISION")
    assert _count(report.tenant_id, provisions) == 0

    august = runs.closed(report, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert august["status"] == "SUCCEEDED"
    netted = runs.posted(report.tenant_id, august["id"])
    assert {line["posting_kind"] for line in netted} == {RECLASS}
    assert runs.by_role(netted, period_key=AUGUST, entry_kind=RECLASS) == K03_ASSET
    assert _dates(netted, period_key=AUGUST, entry_kind=RECLASS) == {date(2026, 8, 31)}
    assert runs.by_role(netted, period_key=SEPTEMBER, entry_kind=REVERSAL) == _negated(K03_ASSET)
    assert _dates(netted, period_key=SEPTEMBER, entry_kind=REVERSAL) == {date(2026, 9, 1)}
    assert {(line["period_key"], str(line["entry_kind"])) for line in netted} == {
        (AUGUST, RECLASS),
        (SEPTEMBER, REVERSAL),
    }
    assert _count(report.tenant_id, provisions) == 0

    run = runs.closed(report, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert run["status"] == "SUCCEEDED"
    lines = runs.posted(report.tenant_id, run["id"])
    released = [line for line in lines if line["posting_kind"] == "CLOSE_RELEASE"]
    assert runs.by_role(released, period_key=SEPTEMBER, entry_kind="LOSS_PROVISION") == {
        "LOSS_EXPENSE": _usd("3076.92"),
        "LOSS_PROVISION": _usd("-3076.92"),
    }
    assert {line["period_key"] for line in released} == {SEPTEMBER}
    assert {line["effective_date"] for line in released} == {date(2026, 9, 30)}
    assert {line["idempotency_key"] for line in released} == {
        f"release:{run['id']}:{world.group_id}"
    }
    assert {line["combination_group_id"] for line in released} == {world.group_id}
    # R-79 (d): sealed postings only
    for line in released:
        assert line["contract_computation_id"] is None
        assert (line["contract_version_id"], line["calc_trace_id"]) == (None, None)
        assert line["trace_node_id"]
    _counted(run, "RELEASE_SCHEDULES", lines, "CLOSE_RELEASE")
    assert runs.step(run, "RELEASE_SCHEDULES")["counts"]["postings"] == 1
    # nothing else under September's run: nothing to reclass at 30 Sep 2026, and the reversal of
    # August's reclass is August's run's
    assert {line["posting_kind"] for line in lines} == {"CLOSE_RELEASE"}
    assert runs.step(run, "NETTING_RECLASS")["counts"]["lines"] == 0


def test_a_second_release_of_a_loss_unit_posts_nothing(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 RCP-06, ENGINE_SPEC_B S14-INV-02: every path posts "cumulative target minus posted", so
    a second close run over an unchanged loss contract posts nothing — the database witness of the
    loss-unit family that supervisor ruling R-11 owes once the close passes run on the platform
    (R-44 (b)).

    The ledger stores the subject of every line (04 T-SL-04 ``subject_key`` rev 1.282, Alembic
    revision 0124; ruling R-11 as amended, item ENG-COST-READBACK-1) and the read-back of posted
    amounts (``bundles._posted``) answers it, so the second run finds what the first posted under
    the loss unit's own key. Until then the read-back answered a loss unit's provision under
    ``<contract>@<entity>``, and the engine posted the provision again and reversed the posted
    one (net zero per role and period): this test was red on main by its own statement.

    August is closed first: periods close in order (supervisor ruling R-112)."""
    world = worlds.k03_castellan(app, keyring, clock, files)
    close_run_worlds.k03_loss(world, clock)
    report = world.report
    august = runs.closed(report, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert august["status"] == "SUCCEEDED"
    first = runs.closed(report, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert first["status"] == "SUCCEEDED"
    assert runs.step(first, "RELEASE_SCHEDULES")["counts"]["postings"] == 1

    second = runs.closed(report, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert second["status"] == "SUCCEEDED"
    assert runs.posted(report.tenant_id, second["id"]) == []
    assert (second["counts"]["postings"], second["counts"]["lines"]) == (0, 0)


# --- periods close in order (supervisor ruling R-112) ---------------------------------------------


def test_a_run_is_refused_over_an_earlier_period_end_nobody_posted(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supervisor ruling R-112 (04 T-CLS-01 "Period-end steps"): a close run posts the period-end
    amounts of its own period; when a pass has an amount of an earlier period — a period end no
    close run has posted — the step is refused by name and nothing of it is kept.

    ``close_run_worlds.k03_loss`` with August never closed: at 31 Aug 2026 a contract asset of
    50,000.00 waits for its reclass (revenue 600,000.00, WLD-X-09, against invoices 550,000.00).
    September's run seals September's loss provision in ``RELEASE_SCHEDULES`` — the release pass
    has no amount of August — and is refused at ``NETTING_RECLASS``: 409 ``invalid-transition``
    naming August. The run is ``FAILED`` there; no reclass and no reversal reaches the ledger —
    in particular not September's reversal of a reclass that was never posted — and September's
    ``CLOSE_RUN_FAILED`` item names the period whose close comes first."""
    world = worlds.k03_castellan(app, keyring, clock, files)
    close_run_worlds.k03_loss(world, clock)
    report = world.report
    august = worlds.period_state(report, AVM_US, AUGUST)["period"]["name"]

    run = runs.closed(report, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert (run["status"], run["current_step_code"]) == ("FAILED", "NETTING_RECLASS")
    assert runs.step(run, "FX_REMEASUREMENT")["status"] == "SUCCEEDED"
    assert runs.step(run, "RELEASE_SCHEDULES")["status"] == "SUCCEEDED"
    refused = runs.step(run, "NETTING_RECLASS")
    reason = f"{august} has period-end amounts no close run has posted; run its close first"
    assert august != run["period"]["name"]
    assert refused["status"] == "FAILED"
    assert refused["problem"]["type"].endswith("/invalid-transition")
    assert (refused["problem"]["title"], refused["problem"]["status"]) == (
        "Action not available in this state",
        409,
    )
    assert refused["problem"]["detail"] == f"{reason}."
    assert runs.step(run, "INVARIANTS")["status"] == "PENDING"
    # nothing of the refused step: the run's lines are September's provision, sealed before it
    lines = runs.posted(report.tenant_id, run["id"])
    assert {line["posting_kind"] for line in lines} == {"CLOSE_RELEASE"}
    assert {line["period_key"] for line in lines} == {SEPTEMBER}
    reclassified = select(func.count()).where(subledger_line.c.entry_kind.in_((RECLASS, REVERSAL)))
    assert _count(report.tenant_id, reclassified) == 0
    (item,) = _failed_items(report)
    assert (str(item["status"]), str(item["severity"]), item["close_run_id"]) == (
        "OPEN",
        "BLOCKING",
        UUID(run["id"]),
    )
    assert item["message"] == (
        f"Close run {run['close_run_no']} for {AVM_US} {run['period']['name']} failed at "
        f"Contract balance reclassification: {reason}. Nothing was committed for that step. "
        "Resume the close run once the cause is fixed."
    )


def test_a_refused_run_resumes_after_the_earlier_periods_close(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supervisor ruling R-112, the other half: after August's own run the refused run of
    September resumes to ``SUCCEEDED``, and the pair is in the periods it belongs to — the
    reclass of the contract asset 50,000.00 dated 31 Aug 2026 in August and its reversal dated
    1 Sep 2026 in September, both sealed by August's run. The resumed run restarts at
    ``NETTING_RECLASS``, posts nothing there (at 30 Sep 2026 the position is a liability) and
    settles September's ``CLOSE_RUN_FAILED`` item."""
    world = worlds.k03_castellan(app, keyring, clock, files)
    close_run_worlds.k03_loss(world, clock)
    report = world.report
    refused = runs.closed(report, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert (refused["status"], refused["current_step_code"]) == ("FAILED", "NETTING_RECLASS")
    provision = runs.posted(report.tenant_id, refused["id"])
    assert [str(item["status"]) for item in _failed_items(report)] == ["OPEN"]

    august = runs.closed(report, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert august["status"] == "SUCCEEDED"
    lines = runs.posted(report.tenant_id, august["id"])
    assert {line["posting_kind"] for line in lines} == {RECLASS}
    assert {line["idempotency_key"] for line in lines} == {
        f"reclass:{august['id']}:{report.entity_id}"
    }
    assert runs.by_role(lines, period_key=AUGUST, entry_kind=RECLASS) == K03_ASSET
    assert _dates(lines, period_key=AUGUST, entry_kind=RECLASS) == {date(2026, 8, 31)}
    assert runs.by_role(lines, period_key=SEPTEMBER, entry_kind=REVERSAL) == _negated(K03_ASSET)
    assert _dates(lines, period_key=SEPTEMBER, entry_kind=REVERSAL) == {date(2026, 9, 1)}
    assert {(line["period_key"], str(line["entry_kind"])) for line in lines} == {
        (AUGUST, RECLASS),
        (SEPTEMBER, REVERSAL),
    }

    done = runs.resumed(report, monkeypatch, refused["id"])
    assert (done["status"], done["current_step_code"]) == ("SUCCEEDED", None)
    netting = runs.step(done, "NETTING_RECLASS")
    assert (netting["status"], netting["problem"]) == ("SUCCEEDED", None)
    assert (netting["counts"]["postings"], netting["counts"]["lines"]) == (0, 0)
    # the resumed run sealed nothing more: its lines are the provision of its first attempt
    assert runs.posted(report.tenant_id, done["id"]) == provision
    assert [str(item["status"]) for item in _failed_items(report)] == ["RESOLVED"]


def test_a_net_zero_set_of_an_earlier_period_is_no_unposted_period_end(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supervisor ruling R-114 (a): an earlier period has period-end amounts no close run has
    posted when the pass's ``TIME`` intents for it do not net to zero in some account role and
    currency. A set that nets to zero in every role is none, and the later period closes.

    ``close_run_worlds.k03_loss`` with the estimate effective 20 Aug 2026: the loss emerges at
    31 Aug 2026 — expected loss 100,000.00 less the loss through margin to date 96,923.08
    (costs 420,000.00 less revenue 323,076.92), a provision of 3,076.92 (ENGINE_SPEC_B S11-R-14,
    S11-R-16) — and August's run posts it. While the ledger stored no subject key (supervisor
    ruling R-11) the engine's later passes emitted August's provision again for the loss unit,
    together with the reversal of the posted one: two entries of August that cancel in every
    role, over which September's run was not refused. The ledger now stores the key (04 T-SL-04
    rev 1.282; item ENG-COST-READBACK-1), the later passes find the posted provision and emit
    nothing for August, and this world holds no net-zero set any more: what the test still shows
    is that September's run is not refused and seals no line of August — nothing new is decided
    at 30 Sep 2026, so it seals nothing at all. The rule itself is held by
    ``tests/unit/close/test_period_end_order.py`` and ``test_period_ends.py``."""
    world = worlds.k03_castellan(app, keyring, clock, files)
    close_run_worlds.k03_loss(world, clock, effective_date="2026-08-20")
    report = world.report
    provision = {"LOSS_EXPENSE": _usd("3076.92"), "LOSS_PROVISION": _usd("-3076.92")}

    august = runs.closed(report, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert august["status"] == "SUCCEEDED"
    lines = runs.posted(report.tenant_id, august["id"])
    # the provision, and nothing else: at 31 Aug 2026 the position is a liability (revenue
    # 323,076.92 against invoices 550,000.00), so nothing is reclassified
    assert {line["posting_kind"] for line in lines} == {"CLOSE_RELEASE"}
    assert runs.by_role(lines, period_key=AUGUST, entry_kind="LOSS_PROVISION") == provision
    assert {line["period_key"] for line in lines} == {AUGUST}

    september = runs.closed(report, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert (september["status"], september["current_step_code"]) == ("SUCCEEDED", None)
    assert [runs.step(september, code)["status"] for code in PASS_STEPS] == ["SUCCEEDED"] * 3
    assert runs.posted(report.tenant_id, september["id"]) == []
    assert (september["counts"]["postings"], september["counts"]["lines"]) == (0, 0)
    assert _failed_items(report) == []
    # the ledger holds August's provision once, as August's run sealed it (sums by role: a role
    # delta may post as more than one line)
    held = _rows(
        report.tenant_id,
        select(
            subledger_line.c.account_role,
            func.sum(subledger_line.c.amount_functional).label("amount"),
        )
        .where(subledger_line.c.account_role.in_(sorted(provision)))
        .group_by(subledger_line.c.account_role),
    )
    assert {str(row["account_role"]): Decimal(row["amount"]) for row in held} == provision


# --- NETTING_RECLASS ------------------------------------------------------------------------------


def test_netting_reclass_auto_reversing(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-20: for a contract with unbilled receivable 3,000.00 and contract asset
    2,000.00 at period end, ``NETTING_RECLASS`` posts Dr unbilled receivable 3,000.00, Dr contract
    asset 2,000.00 / Cr contract liability 5,000.00 and its reversal in the next period (POLICIES
    CHK-010; JET-06; D-13): one ``NETTING_RECLASS`` posting of the entity under the run, the
    reclass dated the last day of January and the reversal the first day of February. A second
    run of January posts nothing; February's run posts February's reclass and March's reversal,
    and February keeps the one reversal January's run gave it."""
    world = worlds.chk_010_position(app, keyring, clock, files)
    run = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert run["status"] == "SUCCEEDED"
    lines = runs.posted(world.tenant_id, run["id"])
    assert {line["posting_kind"] for line in lines} == {RECLASS}
    assert {line["idempotency_key"] for line in lines} == {f"reclass:{run['id']}:{world.entity_id}"}
    assert {line["combination_group_id"] for line in lines} == {None}
    reclass = {
        "UNBILLED_RECEIVABLE": _usd("3000.00"),
        "CONTRACT_ASSET": _usd("2000.00"),
        "CONTRACT_LIABILITY": _usd("-5000.00"),
    }
    reversal = {role: -amount for role, amount in reclass.items()}
    assert runs.by_role(lines, period_key=JANUARY, entry_kind=RECLASS) == reclass
    assert _dates(lines, period_key=JANUARY, entry_kind=RECLASS) == {date(2026, 1, 31)}
    assert runs.by_role(lines, period_key=FEBRUARY, entry_kind=REVERSAL) == reversal
    assert _dates(lines, period_key=FEBRUARY, entry_kind=REVERSAL) == {date(2026, 2, 1)}
    # nothing else: every line is January's reclass or February's reversal
    assert {(line["period_key"], str(line["entry_kind"])) for line in lines} == {
        (JANUARY, RECLASS),
        (FEBRUARY, REVERSAL),
    }
    _counted(run, "NETTING_RECLASS", lines, RECLASS)
    assert runs.step(run, "NETTING_RECLASS")["counts"]["postings"] == 1
    assert runs.summary(run, "NETTING_RECLASS") == f"{len(lines)} lines"
    assert (run["counts"]["postings"], run["counts"]["lines"]) == (1, len(lines))

    again = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert again["status"] == "SUCCEEDED"
    assert runs.posted(world.tenant_id, again["id"]) == []

    february = runs.closed(world, monkeypatch, entity_code=US01, period_key=FEBRUARY)
    assert february["status"] == "SUCCEEDED"
    later = runs.posted(world.tenant_id, february["id"])
    assert runs.by_role(later, period_key=FEBRUARY, entry_kind=RECLASS) == reclass
    assert _dates(later, period_key=FEBRUARY, entry_kind=RECLASS) == {date(2026, 2, 28)}
    assert runs.by_role(later, period_key=MARCH, entry_kind=REVERSAL) == reversal
    assert _dates(later, period_key=MARCH, entry_kind=REVERSAL) == {date(2026, 3, 1)}
    assert {(line["period_key"], str(line["entry_kind"])) for line in later} == {
        (FEBRUARY, RECLASS),
        (MARCH, REVERSAL),
    }


# --- FX_REMEASUREMENT -----------------------------------------------------------------------------


def test_fx_remeasurement_step_posts_gain_loss(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-20: a EUR receivable of an entity with functional currency USD is remeasured
    at the Sep 2026 closing rate EUR→USD 1.120000 against the Aug 2026 closing rate 1.105000,
    posting the difference to ``FX_GAIN_LOSS`` (PRD §2.5 AVM-RATES; D-25; POLICIES JET-10a).

    ``close_run_worlds.eur_receivable``: EUR 10,000.00 recognised on 31 Aug 2026 at 1.100000 =
    USD 11,000.00 and not invoiced. August's run remeasures it at 1.105000: 11,050.00, a gain of
    50.00 (Dr ``CONTRACT_LIABILITY`` / Cr ``FX_GAIN_LOSS``); its netting reclass then carries the
    remeasured 11,050.00, because the FX pass runs before it (supervisor ruling R-79 (b); 05
    RCP-08). September's run remeasures at 1.120000: 11,200.00, a gain of 10,000.00 x (1.120000 −
    1.105000) = 150.00. A remeasurement moves the functional carrying only: its transaction
    amounts are zero. One ``FX_REMEASUREMENT`` posting of the entity per run."""
    world = close_run_worlds.eur_receivable(app, keyring, clock, files)
    august = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert august["status"] == "SUCCEEDED"
    lines = runs.posted(world.tenant_id, august["id"])
    remeasured = [line for line in lines if line["posting_kind"] == FX]
    assert {line["idempotency_key"] for line in remeasured} == {
        f"fx:{august['id']}:{world.entity_id}"
    }
    assert runs.by_role(remeasured, period_key=AUGUST, entry_kind=FX) == {
        "CONTRACT_LIABILITY": _usd("50.00"),
        "FX_GAIN_LOSS": _usd("-50.00"),
    }
    assert runs.by_role(remeasured, period_key=AUGUST, entry_kind=FX, amount="amount_txn") == {
        "CONTRACT_LIABILITY": Decimal(0),
        "FX_GAIN_LOSS": Decimal(0),
    }
    assert {line["period_key"] for line in remeasured} == {AUGUST}
    assert {line["effective_date"] for line in remeasured} == {date(2026, 8, 31)}
    _counted(august, "FX_REMEASUREMENT", lines, FX)
    assert runs.step(august, "FX_REMEASUREMENT")["counts"]["postings"] == 1
    assert runs.summary(august, "FX_REMEASUREMENT") == f"{len(remeasured)} lines"
    # the reclass of the same run reads the remeasurement as posted
    netted = [line for line in lines if line["posting_kind"] == RECLASS]
    assert runs.by_role(netted, period_key=AUGUST, entry_kind=RECLASS) == {
        "UNBILLED_RECEIVABLE": _usd("11050.00"),
        "CONTRACT_LIABILITY": _usd("-11050.00"),
    }
    assert runs.by_role(netted, period_key=AUGUST, entry_kind=RECLASS, amount="amount_txn") == {
        "UNBILLED_RECEIVABLE": Decimal("10000.00"),
        "CONTRACT_LIABILITY": Decimal("-10000.00"),
    }

    september = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert september["status"] == "SUCCEEDED"
    lines = runs.posted(world.tenant_id, september["id"])
    remeasured = [line for line in lines if line["posting_kind"] == FX]
    assert {line["idempotency_key"] for line in remeasured} == {
        f"fx:{september['id']}:{world.entity_id}"
    }
    assert runs.by_role(remeasured, period_key=SEPTEMBER, entry_kind=FX) == {
        "CONTRACT_LIABILITY": _usd("150.00"),
        "FX_GAIN_LOSS": _usd("-150.00"),
    }
    assert {line["period_key"] for line in remeasured} == {SEPTEMBER}
    assert {line["effective_date"] for line in remeasured} == {date(2026, 9, 30)}
    netted = [line for line in lines if line["posting_kind"] == RECLASS]
    assert runs.by_role(netted, period_key=SEPTEMBER, entry_kind=RECLASS) == {
        "UNBILLED_RECEIVABLE": _usd("11200.00"),
        "CONTRACT_LIABILITY": _usd("-11200.00"),
    }

    again = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert again["status"] == "SUCCEEDED"
    assert runs.posted(world.tenant_id, again["id"]) == []


# --- INVARIANTS -----------------------------------------------------------------------------------


def _unbalanced_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every posting intent of a pass out of balance by 1.00 on its first line."""
    real = period_end.engine_pass

    def bent(bundle: InputBundle, pass_name: str) -> OutputBundle:
        output = real(bundle, pass_name)
        books = []
        for book in output.books:
            intents = []
            for intent in book.posting_intents:
                first = intent.lines[0]
                moved = dataclasses.replace(
                    first,
                    amount_txn=first.amount_txn + 100,
                    amount_functional=first.amount_functional + 100,
                )
                intents.append(dataclasses.replace(intent, lines=(moved, *intent.lines[1:])))
            books.append(dataclasses.replace(book, posting_intents=tuple(intents)))
        return dataclasses.replace(output, books=tuple(books))

    monkeypatch.setattr(period_end, "engine_pass", bent)


def test_invariants_step_summary(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-20: the ``INVARIANTS`` step summary is "All invariants pass" when debits
    equal credits per entity, book, currency and period; an injected unbalanced posting intent
    makes it ``FAILED`` with "1 invariant failures" and nothing committed for the step.

    The ledger itself cannot hold the imbalance: 04 DB-06 refuses an unbalanced posting at its
    seal. So the injection is witnessed in two places. (1) The step's own reading of January is
    given a sum that is off by 0.01: the step is ``FAILED`` with its problem, the run is
    ``BLOCKED`` (PRD SM-14), the ``CLOSE_RUN_FAILED`` item names the step, and nothing after it
    has run; resumed with a true reading the step passes, the run succeeds and the item is
    settled. (2) Posting intents bent out of balance, in February's run, fail the pass that would
    seal them — ``ledger-unbalanced``, the run ``FAILED``, no line of that step kept."""
    world = worlds.chk_010_position(app, keyring, clock, files)

    # (1) the step reads a period that does not balance
    real_sums = close_runs._ledger_sums

    def off_by_a_cent(session: Any, scope: Any) -> Any:
        found = real_sums(session, scope)
        return dataclasses.replace(
            found, txn={**found.txn, "USD": found.txn["USD"] + Decimal("0.01")}
        )

    monkeypatch.setattr(close_runs, "_ledger_sums", off_by_a_cent)
    blocked = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert (blocked["status"], blocked["current_step_code"]) == ("BLOCKED", "INVARIANTS")
    assert blocked["job"]["state"] == "SUCCEEDED_WITH_EXCEPTIONS"
    failed = runs.step(blocked, "INVARIANTS")
    assert failed["status"] == "FAILED"
    assert (failed["counts"]["invariants_checked"], failed["counts"]["invariant_failures"]) == (
        2,
        1,
    )
    assert runs.summary(blocked, "INVARIANTS") == "1 invariant failures"
    reason = (
        "1 of 2 ledger invariants failed for FY2026-P01 of US01 in book ASC606: the USD lines "
        "sum to 0.01 USD, not to zero"
    )
    assert failed["problem"]["type"].endswith("/ledger-unbalanced")
    assert (failed["problem"]["title"], failed["problem"]["status"]) == (
        "Entries do not balance",
        422,
    )
    assert failed["problem"]["detail"] == reason
    # nothing committed for the step or after it: the passes stay as they sealed, no journal run
    assert runs.step(blocked, "NETTING_RECLASS")["status"] == "SUCCEEDED"
    assert runs.step(blocked, "JOURNAL_SUMMARIZATION")["status"] == "PENDING"
    assert blocked["journal_run_id"] is None
    assert _count(world.tenant_id, select(func.count()).select_from(journal_run)) == 0
    (item,) = _failed_items(world)
    assert (str(item["status"]), str(item["severity"]), item["close_run_id"]) == (
        "OPEN",
        "BLOCKING",
        UUID(blocked["id"]),
    )
    assert item["message"] == (
        f"Close run {blocked['close_run_no']} for US01 {blocked['period']['name']} failed at "
        f"Invariant checks: {reason}. Nothing was committed for that step. Resume the close run "
        "once the cause is fixed."
    )

    # a true reading: the step passes and the run goes on to its end
    monkeypatch.setattr(close_runs, "_ledger_sums", real_sums)
    done = runs.resumed(world, monkeypatch, blocked["id"])
    assert (done["status"], done["current_step_code"]) == ("SUCCEEDED", None)
    passed = runs.step(done, "INVARIANTS")
    assert (passed["status"], passed["problem"]) == ("SUCCEEDED", None)
    assert (passed["counts"]["invariants_checked"], passed["counts"]["invariant_failures"]) == (
        2,
        0,
    )
    assert runs.summary(done, "INVARIANTS") == "All invariants pass"
    assert [str(item["status"]) for item in _failed_items(world)] == ["RESOLVED"]

    # (2) an unbalanced posting intent never reaches the ledger
    _unbalanced_passes(monkeypatch)
    run = runs.closed(world, monkeypatch, entity_code=US01, period_key=FEBRUARY)
    assert (run["status"], run["current_step_code"]) == ("FAILED", "NETTING_RECLASS")
    refused = runs.step(run, "NETTING_RECLASS")
    assert refused["status"] == "FAILED"
    assert refused["problem"]["type"].endswith("/ledger-unbalanced")
    assert refused["problem"]["title"] == "Entries do not balance"
    assert runs.posted(world.tenant_id, run["id"]) == []
    assert runs.step(run, "INVARIANTS")["status"] == "PENDING"
    assert sorted(str(item["status"]) for item in _failed_items(world)) == ["OPEN", "RESOLVED"]


# --- JOURNAL_SUMMARIZATION and the observation steps ----------------------------------------------


def test_journal_summarization_creates_draft_run(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-20: ``JOURNAL_SUMMARIZATION`` creates a ``draft`` journal run with
    ``close_run_id`` set and summary "<n> batches" — calculated by the ``JOURNAL_RUN_CALCULATE``
    handler under the close-run job. A second close run of the period, with nothing new to
    journalise, calculates no second run."""
    world = worlds.k01_pellworth(app, keyring, clock, files)
    run = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert run["status"] == "SUCCEEDED" and run["journal_run_id"] is not None
    shown = get(app, f"{JOURNAL_RUNS}/{run['journal_run_id']}", world.maya)
    assert shown.status_code == 200, shown.text
    journal = shown.json()
    assert (journal["state"], journal["entity"]["code"], journal["period"]["period_key"]) == (
        "draft",
        AVM_US,
        SEPTEMBER,
    )
    (stored,) = _rows(
        world.tenant_id,
        select(
            journal_run.c.close_run_id,
            journal_run.c.job_id,
            journal_run.c.state,
            journal_run.c.line_count,
        ).where(journal_run.c.id == UUID(run["journal_run_id"])),
    )
    assert (stored["close_run_id"], str(stored["state"])) == (UUID(run["id"]), "draft")
    assert str(stored["job_id"]) == run["job"]["id"]
    step = runs.step(run, "JOURNAL_SUMMARIZATION")
    assert (step["status"], step["counts"]) == (
        "SUCCEEDED",
        {"batches": len(journal["batches"]), "journal_lines": stored["line_count"]},
    )
    assert len(journal["batches"]) == 1 and stored["line_count"] > 0
    assert runs.summary(run, "JOURNAL_SUMMARIZATION") == "1 batches"
    assert run["counts"]["batches"] == 1

    second = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert second["status"] == "SUCCEEDED" and second["journal_run_id"] is None
    assert runs.summary(second, "JOURNAL_SUMMARIZATION") == "0 batches"
    assert _count(world.tenant_id, select(func.count()).select_from(journal_run)) == 1


def test_journal_summarization_takes_over_what_an_exported_run_left_out_and_the_period_locks(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item JRN-HELD-AFTER-EXPORT-1 (release blocker; ENGINE_SPEC_B S14-R-17 rev 1.164; 04 T-SL-06
    "Taking over" rev 1.267), the road measured on 2 October with its seventh step turned.

    WLD-K-02 is put under a journal-export hold. September's close run calculates the journal
    run, which holds WLD-K-01's two lines and leaves WLD-K-02's two out; that run is submitted,
    approved, exported and acknowledged; the hold is released. ``JE_COMPLETE`` then names the
    posting as uncovered and the run that left it out is past cancelling. Before the item
    nothing journalised it: a second close run's step calculated nothing — the posting lies
    inside the first run's range, and the step asked only for postings beyond the runs — the lock
    was refused on ``JE_COMPLETE`` and the gate cannot be waived.

    Now the second close run's step calculates the run that takes the two lines over: an empty
    range — it starts where the runs end, DB-16 as before — 9,863.01, the lines named in its
    ``CALCULATE`` event. ``JE_COMPLETE`` passes; the run goes through its life; a third close run
    calculates nothing more, so the lines are taken once; and the period is locked."""
    from erev_api.db.tables import audit_event, contract_hold
    from erev_api.domain.journals import summarise
    from support.close_world import periods_closed_before
    from support.reference import assign

    world = worlds.report_world(app, keyring, clock, files, contracts=(worlds.K01, worlds.K02))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: the journal run is hers to approve
    world = worlds.on_record_clock(world, clock)
    state = worlds.period_state(world, AVM_US, SEPTEMBER)
    entity_id, period_id = UUID(str(state["entity"]["id"])), UUID(str(state["period"]["id"]))
    k02 = UUID(str(world.contracts[worlds.K02].contract["id"]))
    contract_path = f"/api/v1/contracts/{k02}"
    disputed = {
        str(row["id"])
        for row in _rows(
            world.tenant_id,
            select(subledger_line.c.id).where(
                subledger_line.c.period_id == period_id, subledger_line.c.contract_id == k02
            ),
        )
    }
    assert len(disputed) == 2

    def head() -> str:
        shown = get(app, contract_path, world.maya)
        assert shown.status_code == 200, shown.text
        return f'"s{shown.json()["head_stream_version"]}"'

    def complete() -> tuple[str, int]:
        """(status, count) of the checklist row ``JE_COMPLETE`` as the cockpit serves it."""
        shown = get(app, f"{PERIODS}/{state['id']}/cockpit", world.maya)
        assert shown.status_code == 200, shown.text
        (row,) = [item for item in shown.json()["checklist"] if item["code"] == "JE_COMPLETE"]
        return row["status"], row["result"]["count"]

    def taken_over(run_id: str) -> set[str]:
        (event,) = _rows(
            world.tenant_id,
            select(audit_event.c.after).where(
                audit_event.c.action == summarise.CALCULATE_ACTION,
                audit_event.c.object_id == UUID(run_id),
            ),
        )
        return set(event["after"]["taken_over_subledger_line_ids"])

    held = post(
        app,
        f"{contract_path}/apply-hold",
        world.maya,
        {"hold_type": "journal_export", "reason": "Customer dispute on invoice INV-US-2002."},
        if_match=head(),
    )
    assert held.status_code == 200, held.text
    (hold,) = _rows(
        world.tenant_id, select(contract_hold.c.id).where(contract_hold.c.contract_id == k02)
    )
    periods_closed_before(
        world.place, app, world.maya, entity_id=entity_id, before=SEPTEMBER, entity_code=AVM_US
    )
    started = post(
        app,
        f"{PERIODS}/{state['id']}/start-close",
        world.maya,
        {"comment": "September close"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    first = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert first["status"] == "SUCCEEDED" and first["journal_run_id"] is not None, first
    left = get(app, f"{JOURNAL_RUNS}/{first['journal_run_id']}", world.maya).json()
    assert (left["totals"]["line_count"], left["totals"]["debit_functional"]["amount"]) == (
        2,
        "9764.38",
    )
    world = runs.journal_posted(world, clock, first["journal_run_id"])

    released = post(
        app,
        f"{contract_path}/release-hold",
        world.maya,
        {"hold_id": str(hold["id"]), "comment": "Dispute settled; credit memo issued."},
        if_match=head(),
    )
    assert released.status_code == 200, released.text
    assert complete() == ("FAILED", 1)
    refused = post(
        app,
        f"{JOURNAL_RUNS}/{first['journal_run_id']}/cancel",
        world.maya,
        {"reason": "Calculate September again with the released contract."},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == "A journal run can be cancelled only before it is exported."

    # the second close run's step makes the run that takes the posting over
    second = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert second["status"] == "SUCCEEDED", second
    assert second["journal_run_id"] not in (None, first["journal_run_id"])  # before the item: None
    step = runs.step(second, "JOURNAL_SUMMARIZATION")
    assert (step["status"], step["counts"]) == ("SUCCEEDED", {"batches": 1, "journal_lines": 2})
    taking = get(app, f"{JOURNAL_RUNS}/{second['journal_run_id']}", world.maya).json()
    assert (
        taking["state"],
        taking["totals"]["line_count"],
        taking["totals"]["debit_functional"]["amount"],
    ) == ("draft", 2, "9863.01")
    covered = left["coverage"]["to_chain_seq"]
    assert (taking["coverage"]["from_chain_seq"], taking["coverage"]["to_chain_seq"]) == (
        covered,
        covered,
    )
    assert taken_over(second["journal_run_id"]) == disputed
    assert taken_over(first["journal_run_id"]) == set()
    assert complete() == ("PASSED", 0)
    world = runs.journal_posted(world, clock, second["journal_run_id"])

    # taken once: a third close run calculates nothing more
    third = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert third["status"] == "SUCCEEDED" and third["journal_run_id"] is None, third
    assert runs.summary(third, "JOURNAL_SUMMARIZATION") == "0 batches"
    assert _count(world.tenant_id, select(func.count()).select_from(journal_run)) == 2

    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        reviewed_reconciliations_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=entity_id,
            period_id=period_id,
            now=clock.now(),
        )
    state = worlds.period_state(world, AVM_US, SEPTEMBER)
    requested = post(
        app,
        f"{PERIODS}/{state['id']}/request-lock",
        world.maya,
        {"certification_comment": "September 2026 close complete"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text  # before the item: 409 on JE_COMPLETE
    world = worlds.verified(world, clock, "marcus")
    decided = approve(app, str(requested.json()["approval_request_id"]), world.marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert worlds.period_state(world, AVM_US, SEPTEMBER)["state"] == "closed"


def test_observation_steps_succeed_without_export(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-20 (BS4-D-03; PRD J-13.7): with the journal run still ``draft``: ``EXPORT``
    "0 batches exported", ``ACKNOWLEDGEMENT_WAIT`` "0 of 1 batches acknowledged", ``GL_TIE_OUT``
    "No trial balance attached", each ``SUCCEEDED``; ``DATASET_FREEZE`` "12 datasets frozen" with
    12 SHA-256 values in ``counts.datasets``; ``LOCK`` ``PENDING``; run ``SUCCEEDED``.

    BS4-D-04: the twelve datasets are ``SNAPSHOT_DATASET`` files frozen at one instant of the
    step, not earlier than the instant the run began."""
    world = worlds.k01_pellworth(app, keyring, clock, files)
    run = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert (run["status"], run["current_step_code"]) == ("SUCCEEDED", None)
    for code in close_runs.EXECUTED_STEPS:
        assert runs.step(run, code)["status"] == "SUCCEEDED", code
    assert runs.step(run, "LOCK") == {
        "step_code": "LOCK",
        "status": "PENDING",
        "started_at": None,
        "finished_at": None,
        "counts": {},
        "problem": None,
    }
    (draft,) = get(app, f"{JOURNAL_RUNS}/{run['journal_run_id']}", world.maya).json()["batches"]
    assert draft["state"] == "draft"
    assert runs.step(run, "EXPORT")["counts"] == {"batches": 1, "batches_exported": 0}
    assert runs.summary(run, "EXPORT") == "0 batches exported"
    assert runs.step(run, "ACKNOWLEDGEMENT_WAIT")["counts"] == {
        "batches": 1,
        "batches_acknowledged": 0,
    }
    assert runs.summary(run, "ACKNOWLEDGEMENT_WAIT") == "0 of 1 batches acknowledged"
    assert runs.step(run, "GL_TIE_OUT")["counts"] == {"trial_balance_attached": False}
    assert runs.summary(run, "GL_TIE_OUT") == "No trial balance attached"
    assert runs.summary(run, "INVARIANTS") == "All invariants pass"

    freeze = runs.step(run, "DATASET_FREEZE")["counts"]
    assert runs.summary(run, "DATASET_FREEZE") == "12 datasets frozen"
    datasets = freeze["datasets"]
    assert sorted(datasets) == sorted(SNAPSHOT_KINDS) and len(datasets) == 12
    assert all(len(value) == 64 and int(value, 16) >= 0 for value in datasets.values())
    assert run["counts"]["datasets"] == datasets
    assert datetime.fromisoformat(freeze["frozen_known_at"]) >= datetime.fromisoformat(
        run["cutoff_known_at"]
    )
    assert freeze["ledger_chain_seq"] > 0
    stored = _rows(
        world.tenant_id,
        select(file_object.c.sha256, file_object.c.media_type).where(
            file_object.c.purpose == FilePurpose.SNAPSHOT_DATASET.value
        ),
    )
    assert {str(row["sha256"]) for row in stored} == set(datasets.values())
    assert {str(row["media_type"]) for row in stored} == {"application/octet-stream"}


def test_gl_tie_out_states_the_reconciliation_difference(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BS4-D-03, SCREENS_B §1.2 "Difference <currency> <amount>": ``GL_TIE_OUT`` observes the
    period's current subledger-to-GL reconciliation. With a trial balance attached that states
    every controlled account as the subledger holds it and 250.00 more on 2100, the step records
    the difference USD 250.00 and one variance; it generates and attaches nothing itself.

    The ledger is one the ERP keeps (``billing.posting = ERP``): beside the journals it holds the
    two invoices the ERP posts to the contract liability account itself — INV-US-1001 120,000.00
    and INV-US-1044 15,000.00 (PRD WLD-K-01) — which the subledger states in the stored contract
    balance of the role (supervisor rulings R-69 (a), R-74)."""
    world = worlds.k01_pellworth(app, keyring, clock, files)
    line = subledger_line
    balances = _rows(
        world.tenant_id,
        select(gl_account.c.code, func.sum(line.c.amount_functional).label("amount"))
        .select_from(
            line.join(
                gl_account,
                and_(
                    gl_account.c.tenant_id == line.c.tenant_id,
                    gl_account.c.id == line.c.gl_account_id,
                ),
            )
        )
        .group_by(gl_account.c.code)
        .order_by(gl_account.c.code),
    )
    stated = {str(row["code"]): Decimal(row["amount"]) for row in balances}
    assert "2100" in stated
    stated["2100"] -= Decimal("120000.00") + Decimal("15000.00")  # the ERP's own invoices
    stated["2100"] += Decimal("250.00")
    draft = recon.generated(
        app,
        world.maya,
        world.runtime,
        entity_code=AVM_US,
        period_key=SEPTEMBER,
        kind=recon.SUBLEDGER_TO_GL,
    )
    content = recon.trial_balance_csv(
        [
            (code, "USD", format(amount.quantize(Decimal("0.01")), "f"))
            for code, amount in stated.items()
        ]
    )
    file_id = recon.uploaded(app, world.maya, "avm-us-tb-2026-09.csv", content)
    compared = recon.attached(app, world.maya, world.runtime, draft["id"], {"file_id": file_id})
    assert compared["variance_count"] == 1

    run = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert run["status"] == "SUCCEEDED"
    assert runs.step(run, "GL_TIE_OUT")["counts"] == {
        "trial_balance_attached": True,
        "reconciliation_id": draft["id"],
        "currency": "USD",
        "difference": "250.00",
        "variance_count": 1,
    }
    assert runs.summary(run, "GL_TIE_OUT") == "Difference USD 250.00"
    listed = recon.shown(app, world.maya, draft["id"])
    assert (listed["status"], listed["is_current"]) == ("DRAFT", True)


# --- LOCK and the frozen datasets -----------------------------------------------------------------


def test_lock_marks_lock_step(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-20 (BS4-D-03, BS4-D-04): after the lock executes, the latest succeeded run's
    ``LOCK`` step is ``SUCCEEDED`` with the locking user; the lock reuses the frozen dataset files
    whose content did not move between the run and the lock.

    January of ``worlds.chk_010_position`` is closed through the product: soft close, the close
    run, its journal run approved, exported and acknowledged (``runs.journal_posted``), the two
    required reconciliations reviewed (the stand-in of ``worlds.period_locked``), Maya's request
    and Marcus's decision. The lock freezes at its own cutoff (ENGINE_SPEC_B S15-R-18c); a dataset
    whose bytes are what the run froze is the run's file, by the file store's deduplication, and
    ``JE_POPULATION`` — whose run state, approval and acknowledgement members moved in between —
    is a file of its own."""
    world = worlds.on_record_clock(worlds.chk_010_position(app, keyring, clock, files), clock)
    state = worlds.period_state(world, US01, JANUARY)
    started = post(
        app,
        f"{PERIODS}/{state['id']}/start-close",
        world.maya,
        {"comment": "Jan 2026 close"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    run = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert run["status"] == "SUCCEEDED" and runs.step(run, "LOCK")["status"] == "PENDING"
    frozen = run["counts"]["datasets"]
    files_of = {
        str(row["sha256"]): row["id"]
        for row in _rows(
            world.tenant_id,
            select(file_object.c.id, file_object.c.sha256).where(
                file_object.c.purpose == FilePurpose.SNAPSHOT_DATASET.value
            ),
        )
    }
    assert set(files_of) == set(frozen.values())

    world = runs.journal_posted(world, clock, run["journal_run_id"])
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        reviewed_reconciliations_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=UUID(str(state["entity"]["id"])),
            period_id=UUID(str(state["period"]["id"])),
            now=clock.now(),
        )
    state = worlds.period_state(world, US01, JANUARY)
    requested = post(
        app,
        f"{PERIODS}/{state['id']}/request-lock",
        world.maya,
        {"certification_comment": "Jan 2026 close complete"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    world = worlds.verified(world, clock, "marcus")
    decided = approve(app, str(requested.json()["approval_request_id"]), world.marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert worlds.period_state(world, US01, JANUARY)["state"] == "closed"

    (lock,) = _rows(
        world.tenant_id,
        select(period_lock.c.id).where(period_lock.c.period_id == UUID(str(state["period"]["id"]))),
    )
    after = runs.shown(app, world.maya, run["id"])
    assert after["status"] == "SUCCEEDED"
    marked = runs.step(after, "LOCK")
    assert marked["status"] == "SUCCEEDED" and marked["problem"] is None
    assert marked["started_at"] is not None and marked["finished_at"] is not None
    assert marked["counts"]["period_lock_id"] == str(lock["id"])
    locker = marked["counts"]["locked_by"]
    assert (locker["id"], locker["kind"]) == (str(world.marcus.member.user_id), "USER")
    assert runs.summary(after, "LOCK") == f"Locked by {locker['display_name']}"
    assert locker["display_name"] and locker["display_name"] != "System"
    # the mark changes nothing else of the run
    assert [step for step in after["steps"] if step["step_code"] != "LOCK"] == [
        step for step in run["steps"] if step["step_code"] != "LOCK"
    ]
    assert after["counts"] == run["counts"]

    # BS4-D-04: an unchanged dataset is the run's file; a changed one is a file of its own
    snapshots = _rows(
        world.tenant_id,
        select(
            lock_snapshot.c.snapshot_kind, lock_snapshot.c.file_id, lock_snapshot.c.file_sha256
        ).where(lock_snapshot.c.period_lock_id == lock["id"]),
    )
    assert sorted(str(row["snapshot_kind"]) for row in snapshots) == sorted(SNAPSHOT_KINDS)
    moved = {
        str(row["snapshot_kind"])
        for row in snapshots
        if str(row["file_sha256"]) != frozen[str(row["snapshot_kind"])]
    }
    assert moved == {"JE_POPULATION"}
    for row in snapshots:
        kind = str(row["snapshot_kind"])
        if kind in moved:
            assert row["file_id"] not in files_of.values()
        else:
            assert row["file_id"] == files_of[frozen[kind]], kind
    stored = _count(
        world.tenant_id,
        select(func.count())
        .select_from(file_object)
        .where(file_object.c.purpose == FilePurpose.SNAPSHOT_DATASET.value),
    )
    assert stored == 12 + len(moved)


# --- a sandbox ------------------------------------------------------------------------------------


def test_sandbox_close_run_export_step(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """BUILD_SPEC CLO-20: in a sandbox tenant row the ``EXPORT`` step observes CSV-only batches
    and writes no outbox message (05 SBX-08). The step reads the period's batches and records
    what it sees; it exports nothing, in a sandbox as elsewhere (BS4-D-03)."""
    sandbox = insert_sandbox_tenant(keyring)
    context = DbContext(tenant_id=sandbox, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        journal = insert_journal_rows(session, sandbox)
        parts = journal.parts
        values = close_run_values(
            sandbox,
            entity_id=parts.entity_id,
            period_id=parts.period_id,
            status=CloseRunStatus.RUNNING.value,
        )
        session.execute(insert(close_run).values(**values))
        run_id = UUID(str(values["id"]))
    assert str(journal.batch["adapter"]) == GlAdapter.CSV.value
    assert str(journal.batch["state"]) == JournalState.DRAFT.value

    def outbox() -> int:
        return _count(sandbox, select(func.count()).select_from(outbox_message))

    before = outbox()
    runtime = JobRuntime(clock=clock, keyring=keyring, files=files)
    with system_unit_of_work(
        runtime, system_principal(sandbox), request_id="tests-sandbox-export", clock=clock
    ) as uow:
        seen = close_runs._seen(uow.session, run_id)
        observed = close_runs.STEPS[close_runs.EXPORT].once
        assert observed is not None
        result = observed(uow, seen)
        uow.commit()
    assert (result.status, dict(result.counts)) == (
        "SUCCEEDED",
        {"batches": 1, "batches_exported": 0},
    )
    assert outbox() == before
    batches = _rows(sandbox, select(journal_batch.c.adapter, journal_batch.c.state))
    assert [(str(row["adapter"]), str(row["state"])) for row in batches] == [("CSV", "draft")]
    assert _count(sandbox, select(func.count()).select_from(job)) == 0
