"""A close run is owed when what it read is no longer what is in force (item CLO-RATE-AFTER-RUN-1;
the supervisor's ruling of 2026-10-02 08:56 on the lane's pre-build line; 04 T-CLS-01 "What a run
read" and §16.8 "The close-run gate", rev 1.291; SCREENS_B §1.1 rev 1.100; BUILD_SPEC CLO-20).

A period-end pass builds one bundle per contract group at the step's record-time cutoff, and a
bundle takes the exchange rates and the period-pinned policy values that are in force at that
cutoff. Publishing either marked no contract group then; since item FX-REPUBLISH-DIRTY-1 the
approval of a rate version marks the groups its changed rates reach, and the measured case
asserts that mark beside the gate. Measured before the item, in the world of this
module: August's run posted the remeasurement at the closing rate 1.105000, a version with
1.115000 for August's closing date was approved afterwards, every gate stayed ``PASSED``, the lock
was approved, and August closed on 50.00 where the rate in force gives 150.00 — a second run
would have posted the 100.00, and nothing asked for it.

World: ``close_run_worlds.eur_receivable`` — AVM-US (USD) with one EUR contract, EUR 10,000.00
delivered on 31 Aug 2026 and never invoiced; the PRD §2.5 rates (August average 1.100000 and
closing 1.105000; September closing 1.120000). January to July are closed (fixture state), August
is in soft close and its close run has succeeded.

Expected amounts are the documents': the unbilled receivable of EUR 10,000.00 stands at USD
11,000.00 (the August average); at the closing rate 1.105000 it is USD 11,050.00 — a
remeasurement of 50.00 — and at 1.115000 USD 11,150.00: 150.00, of which a second run posts the
100.00 the first did not.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import subjects
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import close_run, combination_group, fx_rate_set_version
from erev_api.domain.close import close_runs, gates
from erev_api.enums import ApprovalSubjectType
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.schemas.close_runs import CloseRunCreateIn
from fastapi import FastAPI
from sqlalchemy import func, select
from support import close_run_worlds, worlds
from support import close_runs as runs
from support.db import TestDatabase
from support.reference import PERIODS, approve, get, post, slug

AVM_US = worlds.AVM_US
AUGUST, SEPTEMBER = "FY2026-P08", "FY2026-P09"
FX = "FX_REMEASUREMENT"
RECLASS, REVERSAL = "NETTING_RECLASS", "NETTING_RECLASS_REVERSAL"
GATE = gates.CLOSE_RUN_COMPLETED
CLOSING_SET = "AVM-RATES-CLOSING"
CORRECTED = "1.115000"  # the closing rate of August as corrected; it was 1.105000
PRICE = " A run posts nothing where the change moves nothing for this entity."
RATES_CHANGED = "Close run out of date, run it again: exchange rates changed since it ran." + PRICE
# Item FX-REPUBLISH-DIRTY-1 (04 T-REF-11 "The groups a changed rate reaches", rev 1.297): the
# approval of a version marks the groups its changed rates reach, and the gate of a marked
# contract holds the lock beside the close run's until a run has recomputed it.
DIRTY_GATE = gates.NO_DIRTY_GROUPS
MARKED = "Contracts changed since the last close run: 1"
POLICIES_CHANGED = "Close run out of date, run it again: policies changed since it ran." + PRICE


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _gate(world: worlds.ReportWorld, period_key: str = AUGUST) -> tuple[Any, ...]:
    """(status, count, detail) of ``CLOSE_RUN_COMPLETED`` as the cockpit of the period shows it."""
    return close_run_worlds.gate_shown(world, GATE, period_key)


def _other_gates_failing(world: worlds.ReportWorld) -> dict[str, Any]:
    """The automatic gates of August that are not passed, but for the certification at lock."""
    state = worlds.period_state(world, AVM_US, AUGUST)
    shown = get(world.app, f"{PERIODS}/{state['id']}/cockpit", world.maya)
    assert shown.status_code == 200, shown.text
    return {
        row["code"]: (row["status"], (row.get("result") or {}).get("detail"))
        for row in shown.json()["checklist"]
        if row["status"] not in ("PASSED", "WAIVED") and row["code"] != gates.CONTROLLER_CERTIFIED
    }


def _posted(world: worlds.ReportWorld, run: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """(entry kind, period, account role, functional amount) of the lines a run sealed."""
    return sorted(
        (
            str(line["entry_kind"]),
            str(line["period_key"]),
            str(line["account_role"]),
            f"{Decimal(line['amount_functional']):.2f}",
        )
        for line in runs.posted(world.tenant_id, run["id"])
    )


def _digests(world: worlds.ReportWorld, run: dict[str, Any]) -> tuple[Any, Any]:
    (row,) = close_run_worlds.rows(
        world.tenant_id,
        select(close_run.c.rates_read, close_run.c.registry_read).where(
            close_run.c.id == UUID(str(run["id"]))
        ),
    )
    return row["rates_read"], row["registry_read"]


def test_a_closing_rate_corrected_after_the_run_asks_for_a_second_run(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measured case. August's run posts the remeasurement at 1.105000 and records what it
    read. A version that corrects August's closing rate to 1.115000 is approved afterwards: no
    period-end mark moves, and the gate fails by name — the lock request is refused with the
    gate's sentence. Since item FX-REPUBLISH-DIRTY-1 the approval also marks the group the rate
    reaches — its unbilled receivable is a position at August's end — and the refusal names
    that contract's gate as well. A second run recomputes the group, which posts nothing,
    posts the 100.00 the first did not, with its reclassification and the reversal, and
    records the rates now in force: the gates pass and the lock request is accepted.

    Fail-first (measured before the item, 2026-10-02 02:53): after the corrected rate no
    checklist row changed, the lock request answered 200 and its decision ``APPROVED``; August
    closed on 50.00."""
    world = close_run_worlds.august_in_soft_close(app, keyring, clock, files)
    first = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert (first["status"], first["current_step_code"]) == ("SUCCEEDED", None), first
    assert runs.by_role(
        runs.posted(world.tenant_id, first["id"]), period_key=AUGUST, entry_kind=FX
    ) == {
        "CONTRACT_LIABILITY": Decimal("50.0000"),
        "FX_GAIN_LOSS": Decimal("-50.0000"),
    }
    read_first = _digests(world, first)
    assert all(isinstance(value, str) and len(value) == 64 for value in read_first), read_first
    world = close_run_worlds.journal_and_reconciliations(world, clock, first)
    assert _gate(world) == ("PASSED", 0, None)
    assert _other_gates_failing(world) == {}

    # --- the closing rate of August is corrected after the run ------------------------------
    clock.advance(timedelta(minutes=5))
    world = close_run_worlds.closing_rates(world, clock, {AUGUST: CORRECTED})
    groups = close_run_worlds.rows(
        world.tenant_id,
        select(
            combination_group.c.dirty_since,
            combination_group.c.dirty_trigger,
            combination_group.c.period_ends_open,
        ),
    )
    (corrected,) = close_run_worlds.rows(
        world.tenant_id, select(func.max(fx_rate_set_version.c.published_at).label("at"))
    )
    assert [
        (
            row["dirty_since"],
            str(getattr(row["dirty_trigger"], "value", row["dirty_trigger"])),
            dict(row["period_ends_open"]),
        )
        for row in groups
    ] == [
        (corrected["at"], "FX_REPUBLISH", {"AVM-US|ASC606": "2026-09-01"})
    ]  # the approval marks the group; the period-end mark still says January to August
    assert _gate(world) == ("FAILED", 1, RATES_CHANGED)
    assert _other_gates_failing(world) == {
        GATE: ("FAILED", RATES_CHANGED),
        DIRTY_GATE: ("FAILED", MARKED),
    }
    refused = close_run_worlds.request_lock(world)
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert {error["rule_id"]: error["message"] for error in refused.json()["errors"]} == {
        GATE: RATES_CHANGED,
        DIRTY_GATE: MARKED,
    }

    # --- "Run close again": the second run posts what the first did not ---------------------
    second = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert (second["status"], second["current_step_code"]) == ("SUCCEEDED", None), second
    assert _posted(world, second) == [
        (FX, AUGUST, "CONTRACT_LIABILITY", "100.00"),
        (FX, AUGUST, "FX_GAIN_LOSS", "-100.00"),
        (RECLASS, AUGUST, "CONTRACT_LIABILITY", "-100.00"),
        (RECLASS, AUGUST, "UNBILLED_RECEIVABLE", "100.00"),
        (REVERSAL, SEPTEMBER, "CONTRACT_LIABILITY", "100.00"),
        (REVERSAL, SEPTEMBER, "UNBILLED_RECEIVABLE", "-100.00"),
    ]
    read_second = _digests(world, second)
    assert read_second[0] != read_first[0] and read_second[1] == read_first[1]
    assert _gate(world) == ("PASSED", 0, None)
    world = close_run_worlds.journal_and_reconciliations(world, clock, second)
    assert _other_gates_failing(world) == {}
    accepted = close_run_worlds.request_lock(world)
    assert accepted.status_code == 200, accepted.text


def test_a_rate_after_the_period_and_a_version_that_repeats_the_rates_ask_for_nothing(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rates are read by VALUE and through the period's last day. A version that changes
    September's closing rate — a rate dated after 31 August — and a version that repeats every
    rate as it stands each leave the gate passed; and a second run, started all the same, posts
    nothing: no amount of August depends on a rate dated after its last day.

    By the version a rate comes from, each of the two publications would have asked August for
    a run that posts nothing — as every month's publication of the next rates would."""
    world = close_run_worlds.august_in_soft_close(app, keyring, clock, files)
    first = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert (first["status"], first["current_step_code"]) == ("SUCCEEDED", None), first
    assert _gate(world) == ("PASSED", 0, None)

    clock.advance(timedelta(minutes=5))
    world = close_run_worlds.closing_rates(world, clock, {SEPTEMBER: "1.130000"})  # it was 1.120000
    assert _gate(world) == ("PASSED", 0, None)
    clock.advance(timedelta(minutes=5))
    world = close_run_worlds.closing_rates(
        world, clock, {}
    )  # every rate as the version before states it
    assert _gate(world) == ("PASSED", 0, None)

    second = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert (second["status"], second["current_step_code"]) == ("SUCCEEDED", None), second
    assert _posted(world, second) == []
    assert _digests(world, second) == _digests(world, first)
    assert _gate(world) == ("PASSED", 0, None)


def test_an_approval_begun_before_the_step_and_committed_after_the_run_is_not_read(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never a time. The corrected version is approved by a decision whose transaction begins
    BEFORE the close run and commits after it: its ``published_at`` — the application instant of
    the decision's unit of work — is earlier than the run's cutoff, so by every clock stored the
    version was "in force" when the run read. It was not committed, the run did not read it, and
    August's run posted 50.00. What the run recorded is what its own transaction could read: the
    gate finds the read different now and asks for a run.

    The run is started and worked to its end INSIDE the decision — from the subject's own
    approval hook, before the decision commits — as the preparer, in units of work of its own.
    It runs BEFORE the hook approves the version: since item FX-REPUBLISH-DIRTY-1 the approval
    holds the rows of the groups it marks from that point to its commit, and a run that meets
    them waits for it (dev-guide DG-KRN-DB-08 rev 1.281) — worked after the approval, this
    run's FX step ended FAILED at the lock timeout. The decision's transaction begins before
    the run and commits after it all the same, and ``published_at`` is the decision's instant."""
    world = close_run_worlds.august_in_soft_close(app, keyring, clock, files)
    listed = get(app, "/api/v1/fx-rate-sets", world.maya, {"limit": 50})
    (closing,) = [item for item in listed.json()["items"] if item["code"] == CLOSING_SET]
    rates = close_run_worlds._eur_rates("closing")
    for row in rates:
        row["rate"] = CORRECTED if row["period_key"] == AUGUST else row["rate"]
    draft = post(
        app,
        f"/api/v1/fx-rate-sets/{closing['id']}/versions",
        world.maya,
        {
            "coverage_from": "2026-01-01",
            "coverage_to": worlds.THROUGH_SEPTEMBER.isoformat(),
            "rates": rates,
        },
    )
    assert draft.status_code == 201, draft.text
    submitted = post(
        app,
        f"/api/v1/fx-rate-set-versions/{draft.json()['id']}/submit",
        world.maya,
        {"comment": "August closing rate corrected"},
        if_match=f'"r{draft.json()["row_version"]}"',
    )
    assert submitted.status_code == 200, submitted.text
    version_id = UUID(str(draft.json()["id"]))

    kind = ApprovalSubjectType.FX_RATE_SET_VERSION
    spec = subjects.SUBJECTS[kind]
    ran: list[UUID] = []

    def the_run_then_approved(uow: Any, subject_id: UUID, request_id: UUID) -> None:
        clock.advance(timedelta(minutes=1))  # the run begins after the decision began
        with world.place.uow() as mayas:
            started = close_runs.start(
                mayas, CloseRunCreateIn(entity_code=AVM_US, period_key=AUGUST)
            )
            mayas.commit()
        assert started.job is not None
        runs.unattended(monkeypatch)
        runs.work(world.tenant_id, world.runtime, started.job.id)
        ran.append(started.run_id)
        spec.on_approved(uow, subject_id, request_id)  # APPROVED, published — and not committed

    monkeypatch.setitem(
        subjects.SUBJECTS, kind, dataclasses.replace(spec, on_approved=the_run_then_approved)
    )
    clock.advance(timedelta(minutes=1))
    world = worlds.verified(world, clock, "marcus")
    decided_at = clock.now()
    decided = approve(app, submitted.json()["pending_approval_request_id"], world.marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text

    (run_id,) = ran
    run = runs.shown(app, world.maya, str(run_id))
    assert (run["status"], run["current_step_code"]) == ("SUCCEEDED", None), run
    (version,) = close_run_worlds.rows(
        world.tenant_id,
        select(fx_rate_set_version.c.status, fx_rate_set_version.c.published_at).where(
            fx_rate_set_version.c.id == version_id
        ),
    )
    (stored,) = close_run_worlds.rows(
        world.tenant_id, select(close_run.c.cutoff_known_at).where(close_run.c.id == run_id)
    )
    assert (str(version["status"]), version["published_at"]) == ("APPROVED", decided_at)
    assert version["published_at"] < stored["cutoff_known_at"]  # "published before the run"
    assert runs.by_role(
        runs.posted(world.tenant_id, run["id"]), period_key=AUGUST, entry_kind=FX
    ) == {"CONTRACT_LIABILITY": Decimal("50.0000"), "FX_GAIN_LOSS": Decimal("-50.0000")}
    assert _gate(world) == ("FAILED", 1, RATES_CHANGED)


POLICIES = "/api/v1/policies"
ATTRIBUTION = "position.reclass_attribution_key"  # POL-121, pinned per period (pin P)
LOSS_UNIT = "loss.unit"  # POL-150, pinned on the contract (pin K)
CONCURRENCY = "platform.job_concurrency"  # a workspace setting, no accounting policy
# The first day of October in New York: a period that has not started by this world's
# application clock (12 Sep 2026), as 04 §16.5 asks of a version that holds a period-pinned
# parameter — and a day the SERVER's clock has passed on every day this suite runs.
OCTOBER = "2026-10-01T04:00:00Z"
LATE_SEPTEMBER = "2026-09-20T04:00:00Z"


def _policy_version(
    world: worlds.ReportWorld,
    clock: FrozenClock,
    category: str,
    values: dict[str, Any],
    effective_from: str | None = None,
) -> worlds.ReportWorld:
    """A tenant version of a registry category — created, tested and submitted by Maya, approved
    and so published by Marcus (04 §16.5)."""
    app = world.app
    body: dict[str, Any] = {"category": category, "scope": "TENANT", "values": values}
    if effective_from is not None:
        body["effective_from"] = effective_from
    made = post(app, POLICIES, world.maya, body)
    assert made.status_code == 201, made.text
    version_id = str(made.json()["id"])
    tested = post(app, f"{POLICIES}/{version_id}/test", world.maya, {"run_simulation": False})
    assert tested.status_code == 202, tested.text
    job = runs.work(world.tenant_id, world.runtime, UUID(str(tested.json()["id"])))
    assert str(job["state"]) == "SUCCEEDED", job
    sent = post(app, f"{POLICIES}/{version_id}/submit", world.maya, {"comment": "Ready"})
    assert sent.status_code == 200, sent.text
    clock.advance(timedelta(minutes=1))
    world = worlds.verified(world, clock, "marcus")
    decided = approve(app, str(sent.json()["approval_request_id"]), world.marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    shown = get(app, f"{POLICIES}/{version_id}", world.maya)
    assert (shown.status_code, shown.json()["status"]) == (200, "PUBLISHED"), shown.text
    return world


def test_a_period_pinned_policy_value_that_comes_into_force_after_the_period_asks_for_nothing(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The registry is read by VALUE and for the RUN'S PERIOD (third row of rev 1.291, with item
    PINP-PERIOD-VALUE-1): only the parameters a bundle hands to every period — pin ``P`` — and
    of those the value in force at the earlier of the cutoff and the period's last instant. A
    workspace setting (another category), a contract-pinned accounting policy (the same category
    as the period-pinned ones, published as one whole set) and a period-pinned value that comes
    into force AFTER August's last instant — the key the netting reclassification is attributed
    by, effective 1 October — each leave August's gate passed. No pass of August reads that
    value: a second run records the two digests of the first and posts nothing, and the lock
    request is not refused by the close run.

    STALE EXPECTATION by the join with item PINP-PERIOD-VALUE-1 (the supervisor's word of
    2026-10-02 16:27). Before it a bundle handed EVERY period the value in force at its cutoff,
    so the version effective 1 October failed August's gate by name and a second run read it.
    Since the join a period keeps the value in force at its own end, and the digest that was
    read at the cutoff would have asked for a run that reads and posts nothing.

    The clocks. A version that holds a period-pinned parameter takes effect on the first day of
    a period that has not started (04 §16.5), by the application clock; a bundle, and this gate,
    read at the record-time cutoff — the later of the application instant and the transaction
    timestamp. This world's application clock stands at 12 September 2026 and the server's is
    past 1 October 2026 on every day the suite runs, so a version effective 1 October is
    accepted as a future period's and is in force for a record-time read from its publication:
    the cutoff lies behind August's last instant, the read is made at that instant, and the
    version is not in force there. No version takes effect at a past instant, so the value of a
    period that has started does not change afterwards; the digest differs only for a run made
    before its period's values were settled (``tests/unit/close/test_run_inputs.py``)."""
    world = close_run_worlds.august_in_soft_close(app, keyring, clock, files)
    first = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert (first["status"], first["current_step_code"]) == ("SUCCEEDED", None), first
    assert _gate(world) == ("PASSED", 0, None)

    clock.advance(timedelta(minutes=5))
    world = _policy_version(world, clock, "PLATFORM", {CONCURRENCY: 8})
    assert _gate(world) == ("PASSED", 0, None)
    world = _policy_version(world, clock, "ACCOUNTING_POLICY", {LOSS_UNIT: "POB"}, LATE_SEPTEMBER)
    assert _gate(world) == ("PASSED", 0, None)

    world = _policy_version(
        world, clock, "ACCOUNTING_POLICY", {ATTRIBUTION: "CUMULATIVE_SSP_DELIVERED"}, OCTOBER
    )
    assert _gate(world) == ("PASSED", 0, None)
    refused = close_run_worlds.request_lock(world)  # the journal and the reconciliations are owed
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert GATE not in [error["rule_id"] for error in refused.json()["errors"]]
    assert POLICIES_CHANGED not in [error["message"] for error in refused.json()["errors"]]

    second = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert (second["status"], second["current_step_code"]) == ("SUCCEEDED", None), second
    assert _digests(world, second) == _digests(world, first)
    assert None not in _digests(world, first)
    assert _posted(world, second) == []
    assert _gate(world) == ("PASSED", 0, None)
