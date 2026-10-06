"""RPS-8 register witnesses — the ``modification_register`` producer over the K-02 world (BUILD_SPEC
RPS-8 ``test_modification_register_k02``; ENGINE_SPEC_B S15-R-20c rev 1.38; SCREENS_B RPT-14 rev
1.23; D-98 140-A1 and 140-A8 REGISTER-CATCHUP-1 / EVENT-1 / CUTOFF-1; lane F-CTR).

DB-bound: written for the lane database and recorded NOT RUN in the CTR-17 slice. The other RPS-8
registers (je_population, out_of_period_register, late_entry_report, manual_adjustment_register)
are their owners' witnesses and are not written here.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract, contract_version, modification, obligation_version
from erev_api.domain.contracts import queries
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import modification_register as register
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.problems import Problem
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import K02World, k02_world
from support.reference import approve, assign, get, post
from tests.domain.contracts import test_modifications as flows

MODIFICATIONS: Final = "/api/v1/modifications"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


@pytest.fixture
def k02(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K02World:
    world = k02_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    return world


def _run(world: K02World, *, known_at: Any, historical: bool = False, **parameters: Any) -> Any:
    """The register built through the framework's parameters as a live (or explicit as-of) run."""
    with world.place.uow() as uow:
        params = ReportParams(
            report_code=register.CODE,
            report_version=1,
            parameters={"from_date": "2026-01-01", "to_date": "2027-12-31", **parameters},
            entity_ids=(world.entity_id,),
            known_at=known_at,
            historical=historical,
        )
        return register.build(uow, params)


ANSWERS: Final = {
    "added_goods_distinct": True,
    "priced_at_ssp": False,
    "remaining_goods_distinct_from_transferred": True,
}


def _applied_upgrade(world: K02World, runtime: JobRuntime, clock: FrozenClock) -> tuple[UUID, str]:
    """The K-02 upgrade with the narrated questionnaire answers supplied through the admitted
    create body (TEST-REGISTER-ANSWERS-1: never synthesized from the classification)."""
    contract_id = flows._k02_contract(world)
    created = flows._create(world, contract_id, flows._upgrade_body(questionnaire=dict(ANSWERS)))
    flows._classify(world, created["id"])
    flows._preview(world, created["id"], runtime)
    request_id = flows._submit(world, created["id"])
    clock.advance(timedelta(minutes=1))
    assert approve(world.app, request_id, world.priya).status_code == 200
    return contract_id, str(created["id"])


def test_modification_register_k02(k02: K02World, runtime: JobRuntime, clock: FrozenClock) -> None:
    """BUILD_SPEC RPS-8: row reference ``CR-MARROWBY-2026-09``; effective 16 Sep 2026; entered UTC
    timestamp; answers Yes / No / Yes; proposed and chosen treatment Prospective; approver
    ``priya``; TP change 60,000.00; catch-up 0.00 for the added line (PRD J-05.6; REQ-MOD-014).
    REGISTER-CATCHUP-1: the zero catch-up is read from the caused version's obligation row, not
    substituted. REGISTER-EVENT-1: the applied event's owner is the original contract."""
    contract_id, modification_id = _applied_upgrade(k02, runtime, clock)
    clock.advance(timedelta(minutes=1))
    data = _run(k02, known_at=clock.now())
    (row,) = data.rows
    head = k02.place.rows(
        select(contract.c.head_stream_version, contract.c.external_id).where(
            contract.c.id == contract_id
        )
    )[0]
    assert row["reference"] == "CR-MARROWBY-2026-09"
    assert (str(row["effective_date"]), row["obligation_key"], row["status"]) == (
        "2026-09-16",
        "O2",
        "APPLIED",
    )
    assert row["created_at"].tzinfo is not None
    assert (
        row["added_goods_distinct"],
        row["priced_at_ssp"],
        row["remaining_goods_distinct_from_transferred"],
    ) == (True, False, True)
    assert (row["proposed_treatment"], row["chosen_treatment"]) == ("PROSPECTIVE", "PROSPECTIVE")
    assert row["approvers"] and "priya" in row["approvers"].lower()
    assert row["tp_change"] == {"amount": "60000.00", "currency": "USD"}
    assert row["catch_up_amount"] == {"amount": "0.00", "currency": "USD"}
    assert row["applied_event_key"] == f"event:{head['external_id']}:{head['head_stream_version']}"
    assert row["contract_external_id"] == head["external_id"]
    assert data.control_totals["modification_count"] == 1
    assert data.control_totals["tp_change_total"] == {"USD": "60000.00"}
    shown = get(k02.app, f"{MODIFICATIONS}/{modification_id}", k02.place.author).json()
    assert shown["status"] == "APPLIED"


def test_register_catchup_1_nonzero_catch_up_reads_the_caused_version(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """TEST-REGISTER-CATCHUP-LINE-1: a genuine supported line — CHANGE on the existing O1 with a
    consideration delta — chosen CUMULATIVE_CATCH_UP under a reviewed override applies with a
    nonzero catch-up on O1; the register reads that obligation row of the bound application version
    (exact version / book / contract / key) — nonzero, never synthesized. Explicit negative: a DRAFT
    modification in the same run carries empty measures (no application version)."""
    contract_id = flows._k02_contract(k02)
    body = flows._upgrade_body(
        # the ENGINE_SPEC S06-R-19 shape of UPGRADE: a CHANGE line on the subscription obligation
        # for the remaining term with ΔC > 0 (the helper's own kind is the seat add's)
        kind="UPGRADE",
        reference="CR-MARROWBY-2026-13",
        lines=[
            {
                "obligation_key": "O1",
                "action": "CHANGE",
                "quantity_delta": "0",
                "consideration_delta": {"amount": "12000.00", "currency": "USD"},
                "start_date": "2026-09-16",
                "end_date": "2027-12-31",
            }
        ],
    )
    created = flows._create(k02, contract_id, body)
    flows._classify(k02, created["id"])
    record = flows._reviewed_override(
        k02, created["id"], "Catch-up: the price change is retroactive."
    )
    flows._patch(
        k02,
        created["id"],
        {"chosen_treatments": {"O1": "CUMULATIVE_CATCH_UP"}, "judgement_record_id": record},
    )
    flows._classify(k02, created["id"])
    flows._preview(k02, created["id"], runtime)
    request_id = flows._submit(k02, created["id"])
    clock.advance(timedelta(minutes=1))
    # PRD §2.5: an absolute catch-up of USD 50,000.00 or more routes a second step held by a
    # Controller. The preview carries the engine's catch-up of this boundary — the INCEPTION
    # segment re-based on the line's dates reverses the 84,821.92 recognised — so the Revenue
    # Reviewer's approval leaves the request PENDING (lane FIX-A: the preview used to report the
    # change in cumulative revenue between two versions, 205.13 here, and routed one step).
    first = approve(k02.app, request_id, k02.priya)
    assert (first.status_code, first.json()["status"], first.json()["flags"]) == (
        200,
        "PENDING",
        ["CATCH_UP_GE_50K"],
    )
    clock.advance(timedelta(minutes=1))
    second = approve(k02.app, request_id, k02.marcus)
    assert (second.status_code, second.json()["status"]) == (200, "APPROVED"), second.text
    draft = flows._create(k02, contract_id, flows._upgrade_body(reference="CR-MARROWBY-2026-14"))
    clock.advance(timedelta(minutes=1))
    data = _run(k02, known_at=clock.now(), status=["APPLIED", "DRAFT"])
    by_key = {row["row_key"]: row for row in data.rows}  # the full row key proves multiplicity
    assert len(by_key) == len(data.rows) == 2
    applied = by_key[f"modification:{created['modification_no']}:O1"]
    assert (applied["obligation_key"], applied["chosen_treatment"]) == ("O1", "CUMULATIVE_CATCH_UP")
    assert applied["treatment_override"] is True
    assert applied["catch_up_amount"] is not None
    assert Decimal(applied["catch_up_amount"]["amount"]) != 0
    # the exact persisted amount the docstring claims: the application version (the primary-book
    # contract version of the contract's group whose cause_event_ids hold the applied event), this
    # contract, obligation O1
    stored = flows._row(k02, created["id"])
    group_id = k02.place.rows(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    )[0]["combination_group_id"]
    with k02.place.uow() as uow:
        primary = queries.primary_book(uow.session)
    (persisted,) = k02.place.rows(
        select(obligation_version.c.catch_up_amount)
        .select_from(
            obligation_version.join(
                contract_version, contract_version.c.id == obligation_version.c.contract_version_id
            )
        )
        .where(
            contract_version.c.book_code == primary,
            contract_version.c.combination_group_id == group_id,
            contract_version.c.cause_event_ids.overlap([stored["applied_event_id"]]),
            obligation_version.c.contract_id == contract_id,
            obligation_version.c.obligation_key == "O1",
        )
    )
    assert Decimal(applied["catch_up_amount"]["amount"]) == Decimal(
        str(persisted["catch_up_amount"])
    )
    negative = by_key[f"modification:{draft['modification_no']}:O2"]
    assert (negative["status"], negative["tp_change"], negative["catch_up_amount"]) == (
        "DRAFT",
        None,
        None,
    )


def test_register_event_1_separate_contract_key_names_the_new_contract(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """The separate-contract booking's applied event belongs to the NEW contract SF-ORD-10388:
    ``applied_event_key`` names it (stream version 1) while the row key keeps the original."""
    contract_id = flows._k02_contract(k02)
    created = flows._create(k02, contract_id, flows._pellworth_body())
    flows._classify(k02, created["id"])
    flows._preview(k02, created["id"], runtime)
    request_id = flows._submit(k02, created["id"])
    clock.advance(timedelta(minutes=1))
    assert approve(k02.app, request_id, k02.priya).status_code == 200
    clock.advance(timedelta(minutes=1))
    data = _run(k02, known_at=clock.now())
    (row,) = data.rows
    original = k02.place.rows(select(contract.c.external_id).where(contract.c.id == contract_id))[0]
    assert row["contract_external_id"] == original["external_id"]
    assert row["applied_event_key"] == "event:SF-ORD-10388:1"
    assert row["row_key"] == f"modification:{row['modification_no']}:O2"


def test_register_cutoff_1_two_cutoffs_around_a_later_application(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """REGISTER-CUTOFF-1: at a cutoff after the application the row is APPLIED with the version
    measures; an explicit historical read at a cutoff BEFORE the application (the row last changed
    later) is refused by name — T-CON-06 keeps no row history; a live run never refuses."""
    contract_id = flows._k02_contract(k02)
    created = flows._create(k02, contract_id, flows._upgrade_body())
    flows._classify(k02, created["id"])
    flows._preview(k02, created["id"], runtime)
    request_id = flows._submit(k02, created["id"])
    before_apply = clock.now()
    clock.advance(timedelta(minutes=2))
    assert approve(k02.app, request_id, k02.priya).status_code == 200
    clock.advance(timedelta(minutes=1))
    served = _run(k02, known_at=clock.now())
    (row,) = served.rows
    assert row["status"] == "APPLIED" and row["tp_change"] is not None
    with pytest.raises(Problem) as refused:
        _run(
            k02, known_at=before_apply, historical=True, status=["SUBMITTED", "APPROVED", "APPLIED"]
        )
    (error,) = refused.value.errors
    assert error.field == "parameters.known_at" and "no row history" in error.message
    live = _run(k02, known_at=before_apply)  # a record-basis run never refuses here
    assert live.control_totals["row_count"] >= 0


def test_register_cutoff_1_submitted_then_rejected_is_refused_not_dropped(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """D-98 140-A10 / A11 REGISTER-CUTOFF-1: a modification SUBMITTED at the cutoff and later
    REJECTED must not vanish from a historical ``status = [SUBMITTED]`` run — the historical
    population is inspected before the current-status filter, so the run refuses by name."""
    contract_id = flows._k02_contract(k02)
    created = flows._create(k02, contract_id, flows._upgrade_body())
    flows._classify(k02, created["id"])
    flows._preview(k02, created["id"], runtime)
    request_id = flows._submit(k02, created["id"])
    at_submission = clock.now()
    clock.advance(timedelta(minutes=2))
    from support.reference import reject

    assert reject(k02.app, request_id, k02.priya, "Not this quarter.").status_code == 200
    assert flows._row(k02, created["id"])["status"] == "REJECTED"
    with pytest.raises(Problem) as refused:
        _run(k02, known_at=at_submission, historical=True, status=["SUBMITTED"])
    (error,) = refused.value.errors
    assert error.field == "parameters.known_at" and "no row history" in error.message
    clock.advance(timedelta(minutes=1))
    current = _run(k02, known_at=clock.now(), status=["REJECTED"])
    assert [row["status"] for row in current.rows] == ["REJECTED"]


def test_register_catchup_1_later_join_binds_the_application_group_not_the_first_match(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """D-98 140-A11 REGISTER-CATCHUP-1 (distinct from REGROUP-R3): after the upgrade is applied in
    the singleton group, an approved combination JOIN with another contract re-includes the
    modification event in the joined group's first version, so two versions hold the event; the
    register binds the version of the group the owner belonged to at application (the singleton's)
    and its measures stay the applied ones — never an arbitrary first match."""
    contract_id, modification_id = _applied_upgrade(k02, runtime, clock)
    clock.advance(timedelta(minutes=1))
    before_join = _run(k02, known_at=clock.now())
    (row_before,) = before_join.rows
    partner = flows.booked_contract(
        k02.place,
        {**flows.k02_body(k02.customer_id), "external_id": "SF-ORD-10002-J"},
        activate=False,
    )
    grouped = post(
        k02.app,
        "/api/v1/combination-groups",
        k02.place.author,
        {
            "contract_ids": [str(contract_id), str(partner.contract["id"])],
            "criterion": "606-10-25-9(a)",
            "rationale": "Combined after the upgrade.",
        },
    )
    assert grouped.status_code == 201, grouped.text
    routed = post(
        k02.app,
        f"/api/v1/combination-groups/{grouped.json()['id']}/submit",
        k02.place.author,
        {"comment": "Combine."},
    )
    assert routed.status_code == 200, routed.text
    clock.advance(timedelta(minutes=1))
    assert approve(k02.app, routed.json()["approval_request_id"], k02.priya).status_code == 200
    clock.advance(timedelta(minutes=1))
    # two ACTUAL eligible candidates with DIFFERING values: the singleton application version and
    # the joined group's first version both hold the applied event; the joined version has no
    # predecessor, so its (transaction_price − 0) is the whole group's price, not 60,000.00
    stored = flows._row(k02, modification_id)
    with k02.place.uow() as uow:
        primary = queries.primary_book(uow.session)
    candidates = k02.place.rows(
        select(
            contract_version.c.id,
            contract_version.c.combination_group_id,
            contract_version.c.transaction_price,
            contract_version.c.previous_version_id,
        ).where(
            contract_version.c.book_code == primary,
            contract_version.c.cause_event_ids.overlap([stored["applied_event_id"]]),
        )
    )
    assert len(candidates) == 2 and len({str(c["combination_group_id"]) for c in candidates}) == 2
    joined = next(c for c in candidates if c["previous_version_id"] is None)
    assert Decimal(str(joined["transaction_price"])) != Decimal(
        "60000.00"
    )  # the wrong candidate differs
    after_join = _run(k02, known_at=clock.now())
    (row_after,) = after_join.rows
    assert (
        row_after["tp_change"]
        == row_before["tp_change"]
        == {"amount": "60000.00", "currency": "USD"}
    )  # equality now discriminates: the joined candidate would have given the group's price
    assert row_after["catch_up_amount"] == row_before["catch_up_amount"]
    assert row_after["applied_event_key"] == row_before["applied_event_key"]


def test_register_cutoff_1_mutable_effective_date_is_refused_not_dropped(
    k02: K02World, clock: FrozenClock
) -> None:
    """D-98 140-A13 REGISTER-CUTOFF-1 follow-through: a DRAFT dated 15 Jul 2026 at cutoff K is
    PATCHed to 1 Aug 2026 after K. A historical July register at K must refuse by name (the row
    changed after K; T-CON-06 keeps no history of its effective date) — never vanish because the
    CURRENT date is August. Control: a live July run excludes it by its current date and a live
    August run includes it."""
    contract_id = flows._k02_contract(k02)
    body = flows._upgrade_body(effective_date="2026-07-15", reference="CR-MARROWBY-2026-15")
    body["lines"][0]["start_date"] = "2026-07-15"
    created = flows._create(k02, contract_id, body)
    at_k = clock.now()
    clock.advance(timedelta(minutes=2))
    moved = flows._patch(k02, created["id"], {"effective_date": "2026-08-01"})
    assert str(moved["effective_date"]) == "2026-08-01"
    with pytest.raises(Problem) as refused:
        _run(
            k02,
            known_at=at_k,
            historical=True,
            from_date="2026-07-01",
            to_date="2026-07-31",
            status=["DRAFT"],
        )
    (error,) = refused.value.errors
    assert error.field == "parameters.known_at" and created["modification_no"] in error.message
    clock.advance(timedelta(minutes=1))
    july = _run(
        k02, known_at=clock.now(), from_date="2026-07-01", to_date="2026-07-31", status=["DRAFT"]
    )
    assert created["modification_no"] not in {row["modification_no"] for row in july.rows}
    august = _run(
        k02, known_at=clock.now(), from_date="2026-08-01", to_date="2026-08-31", status=["DRAFT"]
    )
    assert created["modification_no"] in {row["modification_no"] for row in august.rows}
    assert k02.place.rows(select(modification.c.id).where(modification.c.id == UUID(created["id"])))


def test_manual_adjustment_register(k02: K02World, runtime: JobRuntime, clock: FrozenClock) -> None:
    """BUILD_SPEC RPS-8 (RPT-18; S15-R-20d): WLD-B-02 — a rejected ``SCHEDULE_OVERRIDE`` of USD
    2,400.00 on the K-02 contract, prepared by ``maya``, no attachment — appears once with
    adjustment number, kind, amount, reason code, preparer, the approver's decision comment
    ("Attach the customer acceptance before resubmitting."), no approvers, preparer_differs No,
    attachment_count 0; a POSTED manual release in the same period feeds the POSTED footer; the
    control totals count both rows. Built through the CLO-12 commands (re-pointed from seeded rows
    when the writer landed, lane F-CLO-A): the override sets September's revenue of O1 USD
    2,400.00 above what the schedule holds and Priya rejects it with the comment; a release of USD
    100.00 is approved and posts."""
    from erev_api.db.tables import obligation
    from erev_api.domain.reports.builders import manual_adjustment_register as manual_register
    from support.reference import periods, reject

    adjustments = "/api/v1/manual-adjustments"
    contract_id = flows._k02_contract(k02)
    maya = k02.place.author
    (september,) = [
        item
        for item in periods(k02.app, maya, entity="AVM-US")
        if item["period"]["period_key"] == "FY2026-P09"
    ]
    (o1,) = k02.place.rows(
        select(obligation.c.id).where(
            obligation.c.contract_id == contract_id, obligation.c.obligation_key == "O1"
        )
    )
    listed = get(
        k02.app,
        "/api/v1/schedule-lines",
        maya,
        {
            "contract": str(contract_id),
            "schedule_kind": "REVENUE",
            "obligation": "O1",
            "from_period": "FY2026-P09",
            "to_period": "FY2026-P09",
            "limit": "200",
        },
    )
    assert listed.status_code == 200, listed.text
    held = sum((Decimal(item["amount"]["amount"]) for item in listed.json()["items"]), Decimal(0))

    def usd(amount: Decimal) -> dict[str, str]:
        return {"amount": f"{amount:.2f}", "currency": "USD"}

    def prepared(kind: str, reason_code: str, memo: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {
            "kind": kind,
            "contract_id": str(contract_id),
            "effective_date": "2026-09-12",
            "reason_code": reason_code,
            "memo": memo,
            "payload": {"obligation_id": str(o1["id"]), **payload},
        }
        created = post(k02.app, adjustments, maya, body)
        assert created.status_code == 201, created.text
        submitted = post(k02.app, f"{adjustments}/{created.json()['id']}/submit", maya, {})
        assert submitted.status_code == 200, submitted.text
        found: dict[str, Any] = submitted.json()
        return found

    override = [
        {"period_id": str(september["period"]["id"]), "amount": usd(held + Decimal("2400.00"))}
    ]
    rejected = prepared(
        "SCHEDULE_OVERRIDE", "DATA_CORRECTION", "Customer acceptance pending", {"periods": override}
    )
    assert rejected["amount_functional_abs"] == {"amount": "2400.00", "currency": "USD"}
    refused = reject(
        k02.app,
        rejected["approval_request_id"],
        k02.priya,
        "Attach the customer acceptance before resubmitting.",
    )
    assert refused.status_code == 200, refused.text
    released = prepared(
        "MANUAL_RELEASE",
        "ESTIMATE_CORRECTION",
        "Release on acceptance",
        {"amount": usd(Decimal("100.00"))},
    )
    assert released["amount_functional_abs"] == {"amount": "100.00", "currency": "USD"}
    decided = approve(k02.app, released["approval_request_id"], k02.priya)
    assert decided.status_code == 200, decided.text
    shown = get(k02.app, f"{adjustments}/{released['id']}", maya)
    assert shown.json()["status"] == "POSTED", shown.text
    clock.advance(timedelta(minutes=1))
    with k02.place.uow() as uow:
        data = manual_register.build(
            uow,
            ReportParams(
                report_code=manual_register.CODE,
                report_version=1,
                parameters={"from_period_key": "FY2026-P09", "to_period_key": "FY2026-P09"},
                entity_ids=(k02.entity_id,),
                known_at=clock.now(),
                historical=False,
            ),
        )
    by_no = {row["adjustment_no"]: row for row in data.rows}
    row = by_no[str(rejected["adjustment_no"])]
    assert (row["kind"], row["status"], row["reason_code"]) == (
        "SCHEDULE_OVERRIDE",
        "REJECTED",
        "DATA_CORRECTION",
    )
    assert row["amount_functional_abs"] == {"amount": "2400.00", "currency": "USD"}
    assert row["contract_external_id"] and row["entity_code"] == "AVM-US"
    assert row["period_key"] == "FY2026-P09"
    assert row["preparer"] and row["approvers"] is None and row["preparer_differs"] is False
    assert row["decision_comment"] == "Attach the customer acceptance before resubmitting."
    assert row["attachment_count"] == 0 and row["is_deferred_past_lock"] is False
    assert data.control_totals["row_count"] == 2
    assert data.control_totals["amount_functional_abs_total"] == {"USD": "2500.00"}
    assert data.control_totals["posted_total"] == {"USD": "100.00"}


# --- BUILD_SPEC RPS-8: je_population, out_of_period_register, late_entry_report (F-RPS-REG) ---
# Every world below is built through the product's commands (``support.worlds``) and every report
# runs through ``POST /report-runs`` and its ``REPORT_RUN`` job.


def _instant(value: Any) -> Any:
    """A DS-FMT-17 machine value (ISO 8601 UTC) as an aware datetime."""
    from datetime import datetime

    assert isinstance(value, str) and value.endswith("Z"), value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.mark.slow
def test_je_population_ties_and_flags_post_close(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """BUILD_SPEC RPS-8 (RPT-15; 03 REQ-JE-018; PRD J-14-AC-4): every row carries the creator (the
    run's preparer), the approver, created and posted UTC timestamps, the manual or automated
    flag, the post-close flag, the description and its source links; the totals equal the
    period's journal runs (``TO_JE_POPULATION_EQ_RUNS`` ``PASS``); the lines of a post-reopen run
    show post-close Yes.

    ``worlds.k01_pellworth`` through 26 Feb 2026 (PRD WLD-K-01): O1 allocated 118,800.00 and O2
    16,200.00 of 135,000.00 over standalone prices 132,000.00 and 18,000.00. Feb 2026 of AVM-US is
    closed through the product (``period_locked``): run 1 journalises the February revenue of O1,
    118,800.00 × 59 ÷ 365 less 118,800.00 × 31 ÷ 365 = 19,203.29 − 10,089.86 = 9,113.43. The
    period is reopened for an error correction (J-14.1 to J-14.3) and Maya records what was
    missing — O2 complete on 27 Feb 2026 and INV-US-1044 (WLD-K-01) — which posts 16,200.00 ×
    (1 − 0.40) = 9,720.00 into the reopened period; run 2 journalises it. A person's progress
    event waits for another user (BUILD_SPEC CTR-6; 04 §16.3 "Manual events"): Maya submits the
    two events with their evidence and Priya approves, which appends and computes."""
    from datetime import date

    from support import worlds
    from support.worlds import AVM_US, FEBRUARY_2026, K01

    world = worlds.k01_pellworth(app, keyring, clock, files, through=date(2026, 2, 26))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: a journal run is hers to approve
    world = worlds.on_record_clock(world, clock)
    first, world = worlds.period_locked(world, clock, entity_code=AVM_US, period_key=FEBRUARY_2026)
    world = worlds.period_reopened(
        world,
        clock,
        entity_code=AVM_US,
        period_key=FEBRUARY_2026,
        comment="Implementation completed on 27 Feb 2026 was not recorded.",
    )
    contract_id = UUID(str(world.contracts[K01].contract["id"]))
    corrected = worlds.approved_manual_events(
        world.place,
        world.priya,
        contract_id,
        {
            "event_type": "PROGRESS_RECORDED",
            "effective_date": "2026-02-27",
            "payload": {
                "obligation_key": "O2",
                "cumulative_progress_ratio": "1",
                "measure": "OUTPUT_PERCENT",
            },
        },
        {
            "event_type": "BILLING_RECORDED",
            "effective_date": "2026-02-27",
            "payload": {
                "invoice_number": "INV-US-1044",
                "line_external_id": "INV-US-1044-1",
                "obligation_key": "O2",
                "amount": {"amount": "15000.00", "currency": "USD"},
                "issue_date": "2026-02-27",
            },
        },
    )
    assert corrected["computation"]["status"] == "SUCCEEDED", corrected["computation"]
    second, world = worlds.posted_journal(
        world, clock, entity_code=AVM_US, period_key=FEBRUARY_2026
    )
    assert (first["run_no"], second["run_no"]) == ("JR-000001", "JR-000002")

    run, rows = worlds.report_run(
        world,
        "je_population",
        {
            "entity_codes": [AVM_US],
            "from_period_key": FEBRUARY_2026,
            "to_period_key": FEBRUARY_2026,
        },
    )
    by_key = {row["row_key"]: row for row in rows}
    assert list(by_key) == [
        "line:JE-AVM-US-000001:1",
        "line:JE-AVM-US-000001:2",
        "line:JE-AVM-US-000002:1",
        "line:JE-AVM-US-000002:2",
    ]

    def usd(amount: str) -> dict[str, str]:
        return {"amount": amount, "currency": "USD"}

    expected = {
        "line:JE-AVM-US-000001:1": ("JR-000001", "CONTRACT_LIABILITY", "9113.43", "0.00", False),
        "line:JE-AVM-US-000001:2": ("JR-000001", "REVENUE", "0.00", "9113.43", False),
        "line:JE-AVM-US-000002:1": ("JR-000002", "CONTRACT_LIABILITY", "9720.00", "0.00", True),
        "line:JE-AVM-US-000002:2": ("JR-000002", "REVENUE", "0.00", "9720.00", True),
    }
    batches = {str(item["run_no"]): item["batches"][0] for item in (first, second)}
    for key, (run_no, role, debit, credit, post_close) in expected.items():
        row = by_key[key]
        assert (row["run_no"], row["account_role"]) == (run_no, role), key
        assert (row["debit_txn"], row["credit_txn"]) == (usd(debit), usd(credit)), key
        assert (row["debit_functional"], row["credit_functional"]) == (usd(debit), usd(credit))
        # J-14-AC-4: the lines of the run after the reopen are flagged; the others are not
        assert row["is_post_close"] is post_close, key
        # REQ-JE-018: manual or automated; description; period; state
        assert (row["je_type"], row["is_manual"]) == ("automated", False), key
        assert row["description"] == "AVM-US Feb 2026 revenue recognition", key
        assert (row["entity_code"], row["book"], row["period_key"]) == (
            AVM_US,
            "ASC606",
            FEBRUARY_2026,
        )
        assert (row["run_state"], row["origin_period_key"]) == ("acknowledged", None), key
        # creator and approver: Maya ran the calculation, Priya approved the run (BR-JE-01)
        assert (row["created_by"]["kind"], row["created_by"]["id"]) == (
            "USER",
            str(world.maya.member.user_id),
        ), row["created_by"]
        assert (row["approved_by"]["kind"], row["approved_by"]["id"]) == (
            "USER",
            str(world.priya.member.user_id),
        ), row["approved_by"]
        # created, approved and posted instants, in UTC and in that order
        created, approved, posted = (
            _instant(row[name]) for name in ("created_at", "approved_at", "acknowledged_at")
        )
        assert created <= approved <= posted, key
        # source links: the run's batch, the ledger's document and the lines summarised
        batch = batches[run_no]
        assert row["batch_external_id"] == batch["external_id"], key
        assert row["gl_document_id"] == "GL-" + str(batch["external_id"]).split(":", 2)[-1]
        assert row["source_line_count"] == 1, key
    first_posted = _instant(by_key["line:JE-AVM-US-000001:1"]["acknowledged_at"])
    second_created = _instant(by_key["line:JE-AVM-US-000002:1"]["created_at"])
    assert first_posted < second_created  # run 2 was calculated after the lock and the reopen

    # the totals equal the period's journal runs
    totals = run["control_totals"]
    assert (totals["row_count"], totals["entry_count"]) == (4, 2)
    assert totals["debit_functional_total"] == {"USD": "18833.43"}
    assert totals["credit_functional_total"] == {"USD": "18833.43"}
    assert totals["debit_txn_total"] == totals["credit_txn_total"] == {"USD": "18833.43"}
    run_debits = [item["totals"]["debit_functional"] for item in (first, second)]
    assert run_debits == [usd("9113.43"), usd("9720.00")]
    assert sum(Decimal(item["amount"]) for item in run_debits) == Decimal("18833.43")
    (tie_out,) = run["tie_out_results"]
    assert (tie_out["code"], tie_out["result"]) == ("TO_JE_POPULATION_EQ_RUNS", "PASS")
    assert tie_out["expected"] == tie_out["actual"] == [usd("18833.43")]


@pytest.mark.slow
def test_out_of_period_register_k07(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """BUILD_SPEC RPS-8 (RPT-16; PRD J-04.5, WLD-X-18; 03 REQ-CLS-006): ``worlds.k07_fenwright`` —
    invoice INV-DE-4390 effective 31 Aug 2026, entered after the Aug 2026 lock of AVM-DE — gives
    one row with origin period Aug 2026, posting period Sep 2026, revenue effect 0.00, the user
    and the approval.

    BLOCKED at full strength (lane F-RPS-REG, 2026-09-30; reported to the supervisor): the
    register holds no row. (1) Avenmoor keeps ``billing.posting`` ``ERP`` (PRD §2.5; POL-004), so
    an invoice posts no subledger line, and the register lists the lines that carry an origin
    period (ENGINE_SPEC_B S15-R-18b): the late event's own fact (ENGINE_SPEC S08-R-11; the
    ``LATE_EVENT`` finding) has no row, and the JET-06 reclass that would carry its balance effect
    is posted only by the close run (CLO-19, CLO-20). (2) The commit of an import computes nothing
    (05 IPL-11 is not built), so even the ``LATE_EVENT`` item waits for the next command on the
    contract. (3) An imported event is appended by the system on the uploader's behalf and carries
    no approval of its own (04 §3.3 ``BILLING_RECORDED``: none), so neither the user nor the
    import's approval is on the event the register reads."""
    from support import worlds
    from support.worlds import AUGUST_2026, AVM_DE, K07, SEPTEMBER_2026

    world = worlds.k07_fenwright(app, keyring, clock, files)
    report = world.report
    assert world.late_invoice is not None
    run, rows = worlds.report_run(
        report,
        "out_of_period_register",
        {
            "entity_codes": [AVM_DE],
            "from_period_key": SEPTEMBER_2026,
            "to_period_key": SEPTEMBER_2026,
        },
    )
    assert len(rows) == 1, (rows, run["control_totals"])
    (row,) = rows
    assert (row["origin_period_key"], row["posting_period_key"]) == (AUGUST_2026, SEPTEMBER_2026)
    assert (row["contract_external_id"], row["event_type"], row["effective_date"]) == (
        K07,
        "BILLING_RECORDED",
        "2026-08-31",
    )
    assert row["revenue_effect"] == {"amount": "0.00", "currency": "EUR"}
    # the user who entered the invoice and the approval that released it (PRD J-04.2, J-04.3)
    assert (row["recorded_by"]["kind"], row["recorded_by"]["id"]) == (
        "USER",
        str(report.maya.member.user_id),
    )
    assert row["approval_request_no"] == world.late_invoice["approval_request_no"]
    assert run["control_totals"]["row_count"] == 1
    assert run["control_totals"]["revenue_effect_total"] == {"EUR": "0.00"}


@pytest.mark.slow
def test_late_entry_window(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """BUILD_SPEC RPS-8 (RPT-17; 03 REQ-CLS-007): an event entered after the Aug 2026 lock with
    an effective date in Aug 2026 is listed with its effective date and ``recorded_at``; an event
    effective 3 days before the period end is listed under the ±5-day window
    (``close.late_entry_window_days`` 5); one effective 6 days before is not.

    ``worlds.k07_august_locked`` (PRD WLD-K-07; Aug 2026 of AVM-DE locked through the product).
    Maya then records two notes on the contract effective 27 Sep and 24 Sep 2026 — 3 and 6 days
    before 30 Sep — and the late invoice INV-DE-4390 of 31 Aug 2026 arrives through the import
    (``worlds.k07_late_invoice``; PRD J-04.2, J-04.3)."""
    from erev_api.db.tables import period_lock
    from erev_api.domain.reports.builders import late_entry_report
    from support import worlds
    from support.worlds import AUGUST_2026, AVM_DE, K07, REPORT_RUNS, SEPTEMBER_2026

    world = worlds.k07_august_locked(app, keyring, clock, files)
    for day, note in (("2026-09-27", "Cutoff review"), ("2026-09-24", "Carrier confirmation")):
        noted = worlds._appended_through_api(
            world.report.place,
            world.contract_id,
            {"event_type": "MEMO_UPDATED", "effective_date": day, "payload": {"memo_1": note}},
        )
        assert noted["computation"]["status"] == "SUCCEEDED", noted["computation"]
    world = worlds.k07_late_invoice(world, clock)
    report = world.report
    # The lock of Aug 2026 itself: the earlier periods of AVM-DE are closed first as fixture state
    # (PRD BR-CLS-08, supervisor ruling R-6; ``worlds.period_locked``), each with a lock row.
    august_state = worlds.period_state(report, AVM_DE, AUGUST_2026)
    (lock,) = report.place.rows(
        select(period_lock.c.kind, period_lock.c.created_at).where(
            period_lock.c.entity_id == UUID(str(august_state["entity"]["id"])),
            period_lock.c.period_id == UUID(str(august_state["period"]["id"])),
        )
    )
    assert lock["kind"] == "LOCK"

    def sections(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        assert {row["section"] for row in rows} <= {1, 2}
        return (
            [row for row in rows if row["section"] == 1],
            [row for row in rows if row["section"] == 2],
        )

    # --- Aug 2026: the invoice entered after the lock -------------------------------------------
    august, rows = worlds.report_run(
        report, "late_entry_report", {"entity_codes": [AVM_DE], "period_key": AUGUST_2026}
    )
    entered, near = sections(rows)
    (late,) = entered
    assert (late["contract_external_id"], late["event_type"], late["event_type_label"]) == (
        K07,
        "BILLING_RECORDED",
        "Billing recorded",
    )
    assert (late["entity_code"], late["origin"]) == (AVM_DE, "IMPORT")
    # booked, activated, delivered, two notes, then the invoice: stream version 6
    assert late["row_key"] == late["event_key"] == f"event:{K07}:6"
    assert (late["effective_date"], late["days_from_period_end"]) == ("2026-08-31", 0)
    assert _instant(late["lock_recorded_at"]) == lock["created_at"]
    assert _instant(late["recorded_at"]) > lock["created_at"]
    # within 5 days of 31 Aug: the invoice again, on the period end itself; the delivery of
    # 14 Aug is 17 days before it, and the events before the lock are in neither section
    (same,) = near
    assert (same["row_key"], same["days_from_period_end"]) == (late["row_key"], 0)
    assert same["lock_recorded_at"] is None  # filled in section 1 only
    assert august["control_totals"] == {
        "section_1_count": 1,
        "section_2_count": 1,
        "window_days": 5,
    }
    # the run stores the default it applied: the registry value (D-87 L6-3-Q-29)
    assert august["parameters"]["window_days"] == 5

    # --- Sep 2026, not locked: 3 days before the period end is listed, 6 days is not -------------
    september, rows = worlds.report_run(
        report, "late_entry_report", {"entity_codes": [AVM_DE], "period_key": SEPTEMBER_2026}
    )
    entered, near = sections(rows)
    assert entered == []  # Sep 2026 has no lock
    assert [
        (row["event_type"], row["effective_date"], row["days_from_period_end"]) for row in near
    ] == [("MEMO_UPDATED", "2026-09-27", -3)]
    (listed,) = near
    assert (listed["recorded_by"]["kind"], listed["recorded_by"]["id"]) == (
        "USER",
        str(report.maya.member.user_id),
    )
    assert _instant(listed["recorded_at"]) > lock["created_at"]
    assert september["control_totals"] == {
        "section_1_count": 0,
        "section_2_count": 1,
        "window_days": 5,
    }
    # a 6-day window reaches the note of 24 Sep; rows in effective-date order
    wider, rows = worlds.report_run(
        report,
        "late_entry_report",
        {"entity_codes": [AVM_DE], "period_key": SEPTEMBER_2026, "window_days": 6},
    )
    assert [(row["section"], row["days_from_period_end"]) for row in rows] == [(2, -6), (2, -3)]
    assert wider["parameters"]["window_days"] == 6
    # a window outside 0 to 31 is refused with the SCREENS_B copy
    refused = post(
        report.app,
        REPORT_RUNS,
        report.maya,
        {
            "report_code": "late_entry_report",
            "parameters": {
                "entity_codes": [AVM_DE],
                "period_key": SEPTEMBER_2026,
                "window_days": 32,
            },
            "output_format": "JSON",
        },
    )
    assert refused.status_code == 422, refused.text
    (error,) = refused.json()["errors"]
    assert (error["field"], error["message"]) == (
        "parameters.window_days",
        late_entry_report.WINDOW_COPY,
    )


@pytest.mark.slow
def test_imported_late_event_names_uploader_and_approval(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Supervisor ruling R-63 (c) (SCREENS_B RPT-16 and RPT-17 "Recorded by", "Approval"; PRD
    J-04.5 "with its user and approval"): an event an import commit wrote as the ``SYSTEM``
    principal is shown in both registers with its upload's uploader and the upload's
    ``IMPORT_COMMIT`` request; an event a person recorded keeps its own fields.

    ``worlds.k01_pellworth`` with INV-US-1001 only (PRD WLD-K-01: O2 allocated 16,200.00 of
    135,000.00); Jan 2026 of AVM-US is locked through the product. ``worlds.k01_late_progress``:
    Maya uploads the O2 progress of 40% at 31 Jan 2026 with the template ``progress_events``,
    Priya approves the commit, and Maya's note of 10 Feb 2026 is the command whose computation
    posts the late revenue, 16,200.00 × 0.40 = 6,480.00, in Feb 2026 with origin FY2026-P01."""
    from datetime import date

    from erev_api.db.tables import contract_event
    from support import worlds
    from support.worlds import AVM_US, FEBRUARY_2026, JANUARY_2026, K01

    world = worlds.k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 1))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: journal runs and imports are hers
    world = worlds.on_record_clock(world, clock)
    _, world = worlds.period_locked(world, clock, entity_code=AVM_US, period_key=JANUARY_2026)
    world, upload, noted = worlds.k01_late_progress(world, clock)
    assert noted["computation"]["status"] == "SUCCEEDED", noted["computation"]
    maya = ("USER", str(world.maya.member.user_id))

    # what the rule rests on: the commit wrote the event as SYSTEM, with the upload and no
    # approval request of its own (04 §3.3); the note is Maya's own event
    imported, note = world.place.rows(
        select(
            contract_event.c.event_type,
            contract_event.c.origin,
            contract_event.c.created_by,
            contract_event.c.created_by_kind,
            contract_event.c.import_upload_id,
            contract_event.c.approval_request_id,
        )
        .where(contract_event.c.stream_version >= 4)
        .order_by(contract_event.c.stream_version)
    )
    assert (imported["event_type"], imported["origin"]) == ("PROGRESS_RECORDED", "IMPORT")
    assert (imported["created_by"], imported["created_by_kind"]) == (None, "SYSTEM")
    assert str(imported["import_upload_id"]) == str(upload["id"])
    assert imported["approval_request_id"] is None
    assert (note["event_type"], note["created_by_kind"]) == ("MEMO_UPDATED", "USER")

    def recorder(row: dict[str, Any]) -> tuple[str, str]:
        return row["recorded_by"]["kind"], str(row["recorded_by"]["id"])

    # --- RPT-17, Jan 2026: the imported event entered after the lock -----------------------------
    january, rows = worlds.report_run(
        world, "late_entry_report", {"entity_codes": [AVM_US], "period_key": JANUARY_2026}
    )
    assert [(row["section"], row["row_key"]) for row in rows] == [
        (1, f"event:{K01}:4"),
        (2, f"event:{K01}:4"),
    ]
    for row in rows:
        assert (row["event_type"], row["origin"]) == ("PROGRESS_RECORDED", "IMPORT")
        assert recorder(row) == maya  # the uploader, not the system principal
        assert row["approval_request_no"] == upload["approval_request_no"]  # the upload's request
    assert january["control_totals"] == {
        "section_1_count": 1,
        "section_2_count": 1,
        "window_days": 5,
    }
    # an event a person recorded keeps its own fields: Maya's note of 10 Feb, 18 days before
    # the end of Feb 2026, has no approval request
    _, rows = worlds.report_run(
        world,
        "late_entry_report",
        {"entity_codes": [AVM_US], "period_key": FEBRUARY_2026, "window_days": 20},
    )
    (own,) = rows
    assert (own["section"], own["event_type"], own["days_from_period_end"]) == (
        2,
        "MEMO_UPDATED",
        -18,
    )
    assert (recorder(own), own["origin"], own["approval_request_no"]) == (maya, "UI", None)

    # --- RPT-16, Feb 2026: the late revenue, attributed to the import and the note --------------
    february, rows = worlds.report_run(
        world,
        "out_of_period_register",
        {
            "entity_codes": [AVM_US],
            "from_period_key": FEBRUARY_2026,
            "to_period_key": FEBRUARY_2026,
        },
    )
    (late,) = rows
    assert (late["origin_period_key"], late["posting_period_key"], late["reason_code"]) == (
        JANUARY_2026,
        FEBRUARY_2026,
        "LATE_EVENT",
    )
    # the first-included events of the delta: the imported progress and the note that computed it
    assert late["event_key"] == f"event:{K01}:4|event:{K01}:5:SUBJECT"
    # S15-R-18a rev 1.110: the row key is the whole key — origin, posting, event key
    assert late["row_key"] == f"{JANUARY_2026}:{FEBRUARY_2026}:{late['event_key']}"
    assert (late["event_type"], late["origin"]) == ("PROGRESS_RECORDED|MEMO_UPDATED", "IMPORT|UI")
    assert late["revenue_effect"] == {"amount": "6480.00", "currency": "USD"}
    assert late["balance_effect"] == {"amount": "-6480.00", "currency": "USD"}
    # both members name Maya — the uploader of the import and the author of the note — so the
    # row states its recorder; the approval is the upload's (the note has none)
    assert recorder(late) == maya
    assert late["approval_request_no"] == upload["approval_request_no"]
    assert february["control_totals"] == {
        "row_count": 1,
        "line_count": 2,
        "revenue_effect_total": {"USD": "6480.00"},
        "balance_effect_total": {"USD": "-6480.00"},
    }


@pytest.mark.slow
def test_a_contract_booked_after_seven_closed_periods_is_seven_rows_and_the_lock_freezes_them(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Item RPT-OOP-ROWKEY-1 (supervisor ruling R-112 (j); ENGINE_SPEC_B S15-R-18a rev 1.110;
    SCREENS_B RPT-16 rev 1.46): WLD-K-01 through 31 Aug 2026 with January to July closed
    (BR-CLS-08). A second contract of the customer, one PLATFORM line of 120,000.00 for 2026 dated
    1 Jan 2026, is booked and computed in August: each closed month's revenue is posted into
    August with its own origin period, 69,698.63 = 120,000.00 × 212 / 365 in all. The register
    holds one row per (origin period, posting period, event set) — seven rows of ONE event set —
    and each row's ``row_key`` is that whole key; the lock of August freezes them, and a run
    "as locked" serves them.

    Fail-first (measured on d11ca733): the seven rows shared the row key
    ``event:LATE-ARRIVAL-01:1|event:LATE-ARRIVAL-01:2:SUBJECT`` and the lock decision answered
    409 ``invalid-transition`` — "the OUT_OF_PERIOD_REGISTER dataset cannot be frozen (the rows
    do not form a dataset: duplicate row_key …)", rule ``S15-R-18`` — with August left in soft
    close."""
    from datetime import date

    from erev_api.db.tables import period_lock
    from erev_api.domain.reports import locked
    from support import worlds
    from support.close_world import periods_closed_before
    from support.factories import booked_contract, computed
    from support.worlds import AUGUST_2026, AVM_US, K01

    late = "LATE-ARRIVAL-01"
    world = worlds.k01_pellworth(app, keyring, clock, files, through=date(2026, 8, 31))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: the journal run is hers to approve
    world = worlds.on_record_clock(world, clock)
    periods_closed_before(
        world.place, app, world.maya, entity_id=world.entity_id, before=AUGUST_2026
    )
    body = worlds.k01_body(UUID(str(world.contracts[K01].contract["customer_id"])))
    body["external_id"] = late
    body["lines"] = [body["lines"][0]]
    booked = booked_contract(world.place, body, activate=True)
    computed(world.place, UUID(str(booked.combination_group["id"])))

    august = {
        "entity_codes": [AVM_US],
        "from_period_key": AUGUST_2026,
        "to_period_key": AUGUST_2026,
    }
    months = [f"FY2026-P{number:02d}" for number in range(1, 8)]
    event_key = f"event:{late}:1|event:{late}:2:SUBJECT"
    row_keys = [f"{origin}:{AUGUST_2026}:{event_key}" for origin in months]
    revenue = ["10191.78", "9205.48", "10191.78", "9863.01", "10191.79", "9863.01", "10191.78"]
    totals = {
        "row_count": 7,
        "line_count": 14,
        "revenue_effect_total": {"USD": "69698.63"},
        "balance_effect_total": {"USD": "-69698.63"},
    }

    run, rows = worlds.report_run(world, "out_of_period_register", august)
    assert [
        (row["origin_period_key"], row["posting_period_key"], row["event_key"]) for row in rows
    ] == [(origin, AUGUST_2026, event_key) for origin in months]
    assert [row["row_key"] for row in rows] == row_keys  # the whole key: no two rows share one
    assert [row["revenue_effect"]["amount"] for row in rows] == revenue
    assert {row["reason_code"] for row in rows} == {"LATE_EVENT"}
    assert run["control_totals"] == totals

    # the lock of August: the register is a dataset again, so the decision freezes it
    _, world = worlds.period_locked(world, clock, entity_code=AVM_US, period_key=AUGUST_2026)
    period_id = UUID(str(worlds.period_state(world, AVM_US, AUGUST_2026)["period"]["id"]))
    lock_id = world.place.scalar(
        select(period_lock.c.id).where(
            period_lock.c.period_id == period_id, period_lock.c.kind == "LOCK"
        )
    )
    with world.place.uow() as uow:
        dataset = locked.locked_dataset(uow, report_code="out_of_period_register", lock_id=lock_id)
    frozen = locked.report_data(dataset)
    assert (dataset.kind, dataset.row_count) == ("OUT_OF_PERIOD_REGISTER", 7)
    assert [
        (
            row["row_key"],
            row["origin_period_key"],
            row["posting_period_key"],
            row["event_key"],
            row["revenue_effect"],
        )
        for row in frozen.rows
    ] == [
        (key, origin, AUGUST_2026, event_key, amount)
        for key, origin, amount in zip(row_keys, months, revenue, strict=True)
    ]
    assert dict(dataset.control_totals) == totals
    as_locked, locked_rows = worlds.report_run(
        world, "out_of_period_register", {**august, "period_lock_id": str(lock_id)}
    )
    assert as_locked["period_lock_id"] == str(lock_id)
    assert [row["row_key"] for row in locked_rows] == row_keys
