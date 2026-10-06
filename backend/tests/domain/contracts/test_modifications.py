"""CTR-17 Modifications — the BUILD_SPEC acceptance tests (BUILD_SPEC CTR-17 "Tests"; D-98 140).

DB-bound. The K-02 world of ``support.factories`` (PRD WLD-K-02 ``SF-ORD-10002``: O1 AVM-SEAT-MO
100 seats × 24 months, 240,000.00 USD from 01 Jan 2026 to 31 Dec 2027; US-LIST 2026-H1 at 90.00 /
100.00 / 110.00 per seat-month) receives the WLD-X-06 seat add ``CR-MARROWBY-2026-09``: ADD 50
seats from 16 Sep 2026 to 31 Dec 2027 for 60,000.00.

First complete database run: lane FIX-A, 2026-09-29 (the module was written NOT RUN in the CTR-17
slice and stopped at ``/classify`` until then — MAIN DEFECT 3). The run measured the PRD WLD-X-06
split of the pool (O1 143,452.05 / O2 71,726.03, weights 155,000 : 77,500) against the engine's
148,451.55 / 66,726.53 over this world's seat-month entry. Supervisor ruling R-17 (2026-09-29):
the PRD row was wrong, not the engine — POLICIES and ENGINE_SPEC govern accounting numbers over the
PRD (01-DECISIONS §0). O1's remaining increments are counted on the pinned DAILY convention
(2,400 × 472 ÷ 730 × 100.00 = 155,178.08; S06-R-11 series row, D-97 (3)) and the added seats take
the nearest bound of the range their price falls below (775 × 90.00 = 69,750.00; POL-072
``NEAREST_BOUND``, ALG-04 §2.5.4). PRD rev 1.21 states the corrected row and these tests assert
it: the split in ``test_preview_k02_upgrade_figures``, every figure that does not depend on the
split in ``test_preview_k02_boundary_figures`` and the applied schedule's September pair in
``test_wld_x_06_applied_schedule_by_obligation``. The policy question behind the split is AD-41.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from erev_api.approvals import subjects
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    audit_event,
    contract,
    contract_computation,
    contract_event,
    estimate_version,
    file_object,
    job,
    modification,
    obligation,
    obligation_version,
)
from erev_api.domain.contracts import repo
from erev_api.domain.reference import period_auto_open
from erev_api.enums import ContractEventType, ModificationTreatment, RegistryCategory
from erev_api.events.payloads import BillingRecordedV1, ContractAmendedV1, MoneyIn
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore, open_file
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select, text, update
from support.db import TestDatabase
from support.factories import (
    SEAT_MONTH,
    SSP_BOOK_VERSIONS,
    SSP_BOOKS,
    K02World,
    K11World,
    Workspace,
    activated_contract,
    appended,
    approved_ssp_version,
    booked_contract,
    computed,
    customer_id,
    k02_body,
    k02_seat_month_body,
    k02_world,
    k11_body,
    k11_world,
    product_with_template,
    range_entry,
    set_default_template,
    ssp_book,
)
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.principals import Actor, colleague, enrolled, member, sign_in
from support.principals import workspace as signed_workspace
from support.reference import approve, assign, get, patch, periods, post, reject, slug
from support.rows import (
    estimate_version_values,
    insert_contract_rows,
    insert_role_assignment,
    modification_values,
    publish_registry_version,
)
from support.worlds import (
    K03World,
    estimate_version_ready,
    k03_castellan,
    k03_revenue,
    run_now,
)

CONTRACTS: Final = "/api/v1/contracts"
MODIFICATIONS: Final = "/api/v1/modifications"
JOBS: Final = "/api/v1/jobs"
REFERENCE: Final = "CR-MARROWBY-2026-09"
# The E-25 kind of the Marrowby seat add. Its one line — ADD of a new obligation starting on the
# effective date and ending on O1's end date — is the ENGINE_SPEC S06-R-19 shape of ``CO_TERM``
# ("`ADD` line starting on d and ending on the original end date"; 03 REQ-MOD-012 ``co_term``:
# "added quantity ends on the original end date"). Under ``UPGRADE`` — S06-R-19: a ``CHANGE`` line
# on the subscription obligation — the same line is refused by name (422 ``S06-R-19``; PRD §5.5
# ERR-55, 04 §16.14 rev 1.84; ``test_err_55_…`` below), and a CHANGE on O1 could not give the new
# obligation O2 that PRD WLD-X-06 allocates to. The kind reaches nothing but that shape gate
# (``subscriptions.check``) and the renewal rollover, so every figure here is the same under the
# generic ``ADD_OBLIGATION``; which label the PRD J-05.1 journey shows stays the open Technical
# Accounting item TA-K02-MOD-KIND-1.
K02_KIND: Final = "CO_TERM"
_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


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
    assign(world.priya.member, "revenue_reviewer")  # modification.approve (PRD §2.5)
    return world


@pytest.fixture
def k11(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K11World:
    """PRD WLD-K-11: the EUR contract of AVM-DE (functional EUR) — the ROUTING-FX-1 witness."""
    world = k11_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    return world


def _k02_contract(world: K02World) -> UUID:
    """K-02 booked, activated and computed; the contract id. The PER_INCREMENT fixture
    (``k02_seat_month_body``: 2,400 = 100 seats × 24 months) matches the SSP entry's basis
    (D-98 140-A7 TEST-K02-UNITS-1)."""
    booked = booked_contract(world.place, k02_seat_month_body(world.customer_id), activate=False)
    activated = activated_contract(world.place, booked)
    computed(world.place, UUID(str(activated.combination_group["id"])))
    return UUID(str(activated.contract["id"]))


def _upgrade_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "effective_date": "2026-09-16",
        "kind": K02_KIND,
        "reference": REFERENCE,
        "lines": [
            {
                "obligation_key": "O2",
                "action": "ADD",
                "product_code": "AVM-SEAT-MO",
                # PER_INCREMENT (04 E-49; the K-02 SSP entry): 50 seats × 15.5 seat-months
                # (16 Sep 2026 → 31 Dec 2027) = 775 increments, so the SSP extension at 90.00 is
                # the narrated 69,750.00 floor (D-98 140-A7 TEST-K02-UNITS-1).
                "quantity_delta": "775",
                "consideration_delta": {"amount": "60000.00", "currency": "USD"},
                "start_date": "2026-09-16",
                "end_date": "2027-12-31",
            }
        ],
        "rationale": "Marrowby adds 50 seats for the remaining term (PRD WLD-X-06).",
    }
    body.update(overrides)
    return body


def _create(world: K02World, contract_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
    created = post(world.app, f"{CONTRACTS}/{contract_id}/modifications", world.place.author, body)
    assert created.status_code == 201, created.text
    return dict(created.json())


def _classify(world: K02World, modification_id: str) -> dict[str, Any]:
    done = post(world.app, f"{MODIFICATIONS}/{modification_id}/classify", world.place.author, {})
    assert done.status_code == 200, done.text
    return dict(done.json())


def _work(place: Workspace, job_id: UUID, runtime: JobRuntime) -> None:
    """The worker fetches the job's task and runs it."""
    context = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    run_job(job_id, place.tenant_id, attempt=1, runtime=runtime)


def _preview(world: K02World, modification_id: str, runtime: JobRuntime) -> dict[str, Any]:
    """``POST /modifications/{id}/preview`` (202), the worker run, the finished job."""
    queued = post(world.app, f"{MODIFICATIONS}/{modification_id}/preview", world.place.author, {})
    assert queued.status_code == 202, queued.text
    job_id = queued.json()["id"]
    assert queued.headers["Location"] == f"{JOBS}/{job_id}"
    _work(world.place, UUID(job_id), runtime)
    finished = get(world.app, f"{JOBS}/{job_id}", world.place.author).json()
    assert finished["state"] == "SUCCEEDED", finished
    return dict(finished)


def _submit(world: K02World, modification_id: str, actor: Actor | None = None) -> str:
    sent = post(
        world.app,
        f"{MODIFICATIONS}/{modification_id}/submit",
        actor or world.place.author,
        {"comment": "Approve the Marrowby upgrade."},
    )
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert (body["status"], body["approval_request_id"] is not None) == ("SUBMITTED", True), body
    return str(body["approval_request_id"])


def _patch(world: K02World, modification_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """PATCH with the row's current ETag as If-Match (API-C-08; D-98 140-A7 TEST-PATCH-1)."""
    shown = get(world.app, f"{MODIFICATIONS}/{modification_id}", world.place.author)
    assert shown.status_code == 200, shown.text
    changed = patch(
        world.app,
        f"{MODIFICATIONS}/{modification_id}",
        world.place.author,
        body,
        if_match=shown.headers["ETag"],
    )
    assert changed.status_code == 200, changed.text
    # the PATCH response carries the resulting row's ETag (API-C-08; D-98 140-A10 (2))
    assert changed.headers["ETag"] == f'"r{changed.json()["row_version"]}"', changed.headers
    return dict(changed.json())


def _approve_with(app: FastAPI, request_id: str, approver: Actor, content_sha256: str) -> Any:
    """``POST /approvals/{id}/approve`` with a hash the client retained earlier (TEST-CTL007-1: the
    PENDING stale-basis case — ``approve`` would fetch the fresh displayed hashes)."""
    detail = get(app, f"/api/v1/approvals/{request_id}", approver).json()
    body: dict[str, Any] = {"subject_content_sha256": content_sha256, "comment": "Stale client"}
    if detail["impact_preview"] is not None:
        body["impact_preview_sha256"] = detail["impact_preview"]["sha256"]
    return post(app, f"/api/v1/approvals/{request_id}/approve", approver, body)


def _row(world: K02World, modification_id: str) -> dict[str, Any]:
    return world.place.rows(select(modification).where(modification.c.id == UUID(modification_id)))[
        0
    ]


def _events(
    world: K02World, contract_id: UUID, event_type: ContractEventType
) -> list[dict[str, Any]]:
    return world.place.rows(
        select(contract_event)
        .where(
            contract_event.c.contract_id == contract_id,
            contract_event.c.event_type == event_type.value,
        )
        .order_by(contract_event.c.stream_version)
    )


def _remaining(summary: dict[str, Any], key: str) -> str:
    (item,) = [row for row in summary["remaining_allocation_after"] if row["obligation_key"] == key]
    return str(item["amount"]["amount"])


@pytest.mark.control("CTL-007")
def test_classify_k02_upgrade(k02: K02World) -> None:
    """BUILD_SPEC CTR-17: K-02 ``CR-MARROWBY-2026-09`` classifies with ``added_goods_distinct``
    true, ``priced_at_ssp`` false (60,000.00 below 69,750.00),
    ``remaining_goods_distinct_from_transferred`` true, ``proposed_treatments`` O1 and O2
    ``PROSPECTIVE`` and ``ssp_basis`` from US-LIST 2026-H1 (REQ-MOD-001, REQ-MOD-002; D-18; PRD
    WLD-X-06).

    Of CTL-007's row ("Modification classification, approval and stale-approval
    voiding") this witnesses the classification: the questionnaire's answers, the
    proposed and chosen treatments and the SSP basis of the K-02 change order. Not
    witnessed here: that another answer gives another treatment
    (``test_br_mod_01_classify_proposes_the_answers_and_stores_none``), the
    approval and the voiding
    (``test_ctl_007_stale_or_self_approved_modification_not_applied``).
    """
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    assert (created["status"], created["kind"], created["reference"]) == (
        "DRAFT",
        K02_KIND,
        REFERENCE,
    )
    assert created["modification_no"].startswith("MOD-")
    classified = _classify(k02, created["id"])
    assert classified["proposed_treatments"] == {"O1": "PROSPECTIVE", "O2": "PROSPECTIVE"}
    assert classified["chosen_treatments"] == {"O1": "PROSPECTIVE", "O2": "PROSPECTIVE"}
    assert classified["treatment_summary"] == "PROSPECTIVE"
    assert classified["proposal_detail"]["class[O1]"] == "D"
    questionnaire = classified["questionnaire"]
    assert questionnaire["O2"]["added_goods_distinct"] is True
    assert questionnaire["O2"]["priced_at_ssp"] is False
    assert questionnaire["O1"]["remaining_goods_distinct_from_transferred"] is True
    assert classified["ssp_basis"]["O2"]["ssp_book_version_id"] == k02.version_id


def test_preview_k02_upgrade_figures(k02: K02World, runtime: JobRuntime) -> None:
    """BUILD_SPEC CTR-17: the preview's ``result.summary`` holds ``transaction_price_before``
    240,000.00, ``transaction_price_after`` 300,000.00, ``catch_up_total`` 0.00 and the remaining
    allocation after — O1 148,451.55 and O2 66,726.53 (REQ-MOD-013; PRD WLD-X-06).

    STALE EXPECTATION by supervisor ruling R-17 (2026-09-29; PRD rev 1.21): the row read
    "143,452.05 / 71,726.03 … weights 155,000 : 77,500 (2 : 1, modification-date SSPs, D-18)" and
    now reads "215,178.08; 148,451.55 / 66,726.53; 0.00; 11,769.80 (9,649.25 / 2,120.55);
    14,132.46; 155,178.08 → 215,178.08 … weights 155,178.08 : 69,750.00". Before the ruling this
    test asserted ``"143452.05"`` and ``"71726.03"``; the two literals are the only change."""
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    finished = _preview(k02, created["id"], runtime)
    summary = finished["result"]["summary"]
    assert summary["transaction_price_before"]["amount"] == "240000.00"
    assert summary["transaction_price_after"]["amount"] == "300000.00"
    assert summary["catch_up_total"]["amount"] == "0.00"
    assert _remaining(summary, "O1") == "148451.55"
    assert _remaining(summary, "O2") == "66726.53"
    row = _row(k02, created["id"])
    assert row["impact_preview_file_id"] is not None
    assert row["impact_preview_sha256"] == finished["result"]["impact_preview_sha256"]
    shown = get(k02.app, f"{MODIFICATIONS}/{created['id']}", k02.place.author).json()
    assert shown["impact_preview"]["transaction_price_after"]["amount"] == "300000.00"
    assert shown["impact_summary"]["catch_up_total"]["amount"] == "0.00"


def _second_half_version(world: K02World, low: str, mid: str, high: str) -> str:
    """US-LIST 2026-H2 from 1 July 2026 with the seat-month range given, approved."""
    return approved_ssp_version(
        world.app,
        world.place.author,
        [world.priya, world.marcus],
        world.book_id,
        label="2026-H2",
        effective_from="2026-07-01",
        entries=[
            range_entry(
                SEAT_MONTH, low, mid, high, value_basis="PER_INCREMENT", quantity_unit="INCREMENTS"
            )
        ],
    )


def test_d_18_a_modification_is_priced_from_the_version_in_force_at_its_date(
    k02: K02World, runtime: JobRuntime
) -> None:
    """01-DECISIONS D-18, POL-080 ``D18_DEFAULT`` (ENGINE_SPEC S06-R-11) beside the SSP read-back
    (item PIN-READBACK-1, S05-R-03): the version recorded for O1 prices O1 itself — its booking,
    at any later computation — and no weight of a modification. US-LIST 2026-H2 (105.00 / 115.00
    / 125.00 a seat-month) is in force from 1 July, so the seat add of 16 September weighs O1's
    remaining increments and the added seats at its lower bound: 2,400 × 472 ÷ 730 × 105.00 =
    162,936.99 and 775 × 105.00 = 81,375.00, and the pool of 215,178.08 splits 143,506.95 /
    71,671.13. Under 2026-H1, O1's recorded version, the split would be 148,451.55 / 66,726.53
    (``test_preview_k02_upgrade_figures``)."""
    contract_id = _k02_contract(k02)
    _second_half_version(k02, "105.00", "115.00", "125.00")
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    finished = _preview(k02, created["id"], runtime)
    summary = finished["result"]["summary"]
    assert summary["transaction_price_after"]["amount"] == "300000.00"
    assert summary["catch_up_total"]["amount"] == "0.00"
    assert (_remaining(summary, "O1"), _remaining(summary, "O2")) == ("143506.95", "71671.13")


def _allocated(world: K02World, contract_id: UUID) -> dict[str, Decimal]:
    """The allocation per obligation key at the contract's latest version."""
    return {
        str(row["obligation_key"]): Decimal(str(row["allocated_amount"]))
        for row in world.place.rows(
            select(obligation_version)
            .where(obligation_version.c.contract_id == contract_id)
            .order_by(obligation_version.c.version_no)  # the latest version wins
        )
    }


def _group_of(world: K02World, contract_id: UUID) -> UUID:
    return UUID(
        str(
            world.place.scalar(
                select(contract.c.combination_group_id).where(contract.c.id == contract_id)
            )
        )
    )


def _applied(world: K02World, modification_id: str, clock: FrozenClock) -> None:
    """The previewed modification submitted and approved by ``priya``: APPLIED."""
    request_id = _submit(world, modification_id)
    clock.advance(timedelta(minutes=1))
    decided = approve(world.app, request_id, world.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text


def test_a_version_approved_afterwards_does_not_weigh_an_applied_modification_again(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """Item PIN-READBACK-1 (ENGINE_SPEC S06-R-11, S05-R-03; 04 T-CON-07
    ``pinned_refs.ssp_weights``). The seat add of 16 September is applied under US-LIST 2026-H1,
    the only version in force on its date then: O1 233,273.47 and O2 66,726.53 (WLD-X-06).
    2026-H2 (105.00 / 115.00 / 125.00 a seat-month), dated 1 July, is approved afterwards. By
    date it covers 16 September, and the next computation weighed O1's remaining increments from
    it a second time and moved posted revenue between the two obligations. The computation that
    applied the modification recorded the version O1's weight was priced from; the next one
    reads it back beside the two own pricings, posts nothing and records it again."""
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    _preview(k02, created["id"], runtime)
    _applied(k02, created["id"], clock)
    under_h1 = {"O1": Decimal("233273.47"), "O2": Decimal("66726.53")}
    assert _allocated(k02, contract_id) == under_h1
    group_id = _group_of(k02, contract_id)

    _second_half_version(k02, "105.00", "115.00", "125.00")
    clock.advance(timedelta(minutes=1))
    bundle, output, stored = computed(k02.place, group_id)

    assert [intent for book in output.books for intent in book.posting_intents] == []
    assert _allocated(k02, contract_id) == under_h1
    (amended,) = _events(k02, contract_id, ContractEventType.CONTRACT_AMENDED)
    event_key = f"SF-ORD-10002/EV-{amended['stream_version']:06d}"
    assert {
        policy.subject_key: dict(policy.value)
        for policy in bundle.books[0].policies
        if (policy.code, policy.scope) == ("ssp.version_basis", "OBLIGATION")
    } == {
        "SF-ORD-10002/O1": {"recorded": "US-LIST@v1", f"recorded@{event_key}": "US-LIST@v1"},
        "SF-ORD-10002/O2": {"recorded": "US-LIST@v1"},
    }
    o1 = k02.place.scalar(
        select(obligation.c.id).where(
            obligation.c.contract_id == contract_id, obligation.c.obligation_key == "O1"
        )
    )
    weights = {"ASC606": {str(amended["id"]): {str(o1): k02.version_id}}}
    records = [
        row["pinned_refs"].get("ssp_weights")
        for row in k02.place.rows(
            select(contract_computation.c.pinned_refs)
            .where(contract_computation.c.combination_group_id == group_id)
            .order_by(contract_computation.c.created_at, contract_computation.c.id)
        )
    ]
    # Nothing before the event; the applying computation records it; the next one keeps it.
    assert records[-2:] == [weights, weights] and set(map(str, records[:-2])) == {"None"}
    assert stored["pinned_refs"]["ssp_weights"] == weights


def test_preview_k02_boundary_figures(k02: K02World, runtime: JobRuntime) -> None:
    """PRD WLD-X-05 / WLD-X-06 and J-05.3 — the figures that do not depend on how the pool is
    split between O1 and O2, measured AT the modification boundary (lane FIX-A; 04 rev 1.92):
    TP 240,000.00 → 300,000.00; catch-up 0.00 for each obligation, each Prospective; O1's
    unrecognised allocation at 16 Sep 2026 155,178.08 (240,000.00 less 84,821.92 recognised through
    15 Sep); the pool 215,178.08 = 155,178.08 + 60,000.00 is the remaining allocation after, O1 +
    O2; RPO at 16 Sep 2026 155,178.08 → 215,178.08; revenue Sep 2026 9,863.01 → 11,769.80 and
    Oct 2026 10,191.79 → 14,132.46. Before: catch-up 84,949.04 (the revenue recognised between
    the stored version's date and the boundary), remaining 239,671.23 → the state after the
    boundary date's own revenue, a second approval step on the false 50,000.00 catch-up flag."""
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    summary = _preview(k02, created["id"], runtime)["result"]["summary"]
    assert (
        summary["transaction_price_before"]["amount"],
        summary["transaction_price_after"]["amount"],
    ) == ("240000.00", "300000.00")
    assert summary["catch_up_total"] == {"amount": "0.00", "currency": "USD"}
    assert [
        (item["obligation_key"], item["treatment"], item["amount"]["amount"])
        for item in summary["catch_up_by_obligation"]
    ] == [("O1", "PROSPECTIVE", "0.00"), ("O2", "PROSPECTIVE", "0.00")]
    assert [
        (item["obligation_key"], item["amount"]["amount"])
        for item in summary["remaining_allocation_before"]
    ] == [("O1", "155178.08")]
    after = {
        item["obligation_key"]: Decimal(item["amount"]["amount"])
        for item in summary["remaining_allocation_after"]
    }
    assert sorted(after) == ["O1", "O2"] and sum(after.values()) == Decimal("215178.08")
    assert (
        summary["rpo_date"],
        summary["rpo_before"]["amount"],
        summary["rpo_after"]["amount"],
    ) == (
        "2026-09-16",
        "155178.08",
        "215178.08",
    )
    revenue = {item["period_key"]: item for item in summary["revenue_by_period"]}
    assert (
        revenue["FY2026-P09"]["before"]["amount"],
        revenue["FY2026-P09"]["after"]["amount"],
        revenue["FY2026-P10"]["before"]["amount"],
        revenue["FY2026-P10"]["after"]["amount"],
    ) == ("9863.01", "11769.80", "10191.79", "14132.46")


def test_k02_figures_do_not_depend_on_the_kind_label(k02: K02World, runtime: JobRuntime) -> None:
    """TA-K02-MOD-KIND-1 evidence: the seat add classifies and previews identically under
    ``CO_TERM`` (the S06-R-19 shape its line has) and the generic ``ADD_OBLIGATION`` — the kind
    reaches the engine's shape gate and the renewal rollover only, never a figure."""
    contract_id = _k02_contract(k02)
    found: dict[str, Any] = {}
    for kind, reference in (("CO_TERM", REFERENCE), ("ADD_OBLIGATION", "CR-MARROWBY-2026-09-G")):
        created = _create(k02, contract_id, _upgrade_body(kind=kind, reference=reference))
        classified = _classify(k02, created["id"])
        finished = _preview(k02, created["id"], runtime)
        found[kind] = (
            classified["proposed_treatments"],
            classified["treatment_summary"],
            classified["questionnaire"],
            classified["ssp_basis"],
            finished["result"]["summary"],
        )
    assert found["CO_TERM"] == found["ADD_OBLIGATION"]


def test_err_55_an_upgrade_carrying_an_add_line_is_refused_by_name(
    k02: K02World, runtime: JobRuntime
) -> None:
    """PRD §5.5 ERR-55 / 04 §16.14 rev 1.84 on the database: kind ``UPGRADE`` — ENGINE_SPEC
    S06-R-19: a ``CHANGE`` line on the subscription obligation — with a line that ADDs an
    obligation is refused by name. ``/classify`` answers the 422 synchronously with the field of
    the offending line and the engine's text; ``/preview`` answers 202 and the worker keeps the
    same Problem in ``job.problem``; nothing is classified or retained (create does not validate
    the shape: MOD-SHAPE-AT-CREATE-1). The same line under the kind whose shape it has
    classifies."""
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body(kind="UPGRADE"))
    refused = post(k02.app, f"{MODIFICATIONS}/{created['id']}/classify", k02.place.author, {})
    assert refused.status_code == 422, refused.text
    problem = refused.json()
    assert problem["type"].rsplit("/", 1)[-1] == "validation-failed"
    (error,) = problem["errors"]
    assert (error["field"], error["rule_id"]) == ("lines[0]", "S06-R-19")
    assert error["message"].endswith("line O2 does not have the UPGRADE shape (S06-R-19)")
    finished = _failed_preview(k02, created["id"], runtime)
    (kept,) = _problem_errors(finished)
    assert kept == (error["field"], error["rule_id"], error["message"])
    row = _row(k02, created["id"])
    assert (
        row["proposed_treatments"],
        row["impact_preview_file_id"],
        row["impact_preview_sha256"],
    ) == ({}, None, None)
    _patch(k02, created["id"], {"kind": K02_KIND})
    assert _classify(k02, created["id"])["proposed_treatments"] == {
        "O1": "PROSPECTIVE",
        "O2": "PROSPECTIVE",
    }


@pytest.mark.control("CTL-007")
def test_br_mod_01_classify_proposes_the_answers_and_stores_none(k02: K02World) -> None:
    """BR-MOD-01 (04 §16.14 rev 1.92; SCREENS §7.5): ``/classify`` returns the answers the system
    can compute with their reasons — the added seats distinct, 60,000.00 below the
    modification-date range 69,750.00 – 85,250.00, O1's remaining increments distinct as a series
    — and stores none of them: the stored questionnaire is the preparer's, because the engine
    reads a stored answer as the preparer's own (S06-R-05). An answer the preparer gives is then
    the engine's input (O1 not distinct → class N → cumulative catch-up proposed) and is no longer
    prefilled.

    Of CTL-007's row this witnesses that the classification follows the answers
    (03 REQ-MOD-002) and whose answers the register's questionnaire holds: what the
    system computes is proposed with its reason and not stored, and the preparer's
    answer that O1's remaining goods are not distinct turns O1's proposal into
    cumulative catch-up. Not witnessed here: the approval and the voiding
    (``test_ctl_007_stale_or_self_approved_modification_not_applied``).
    """
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    reasons = _classify(k02, created["id"])["prefill_reasons"]
    assert reasons["O2"]["priced_at_ssp"] == {
        "value": False,
        "reason_key": "modifications.prefill.priced_at_ssp.below_range",
        "params": {
            "price": "60000",
            "low": "69750",
            "high": "85250",
            "ssp_version_key": "US-LIST@v1",
        },
    }
    assert reasons["O2"]["added_goods_distinct"] == {
        "value": True,
        "reason_key": "modifications.prefill.added_goods_distinct.new_distinct",
        "params": {},
    }
    remaining = reasons["O1"]["remaining_goods_distinct_from_transferred"]
    assert (remaining["value"], remaining["reason_key"]) == (
        True,
        "modifications.prefill.remaining_goods_distinct_from_transferred.series",
    )
    shown = get(k02.app, f"{MODIFICATIONS}/{created['id']}", k02.place.author).json()
    assert shown["questionnaire"] == {} and _row(k02, created["id"])["questionnaire"] == {}
    answered = {"O1": {"remaining_goods_distinct_from_transferred": False}}
    _patch(k02, created["id"], {"questionnaire": answered})
    again = _classify(k02, created["id"])
    assert again["proposed_treatments"] == {"O1": "CUMULATIVE_CATCH_UP", "O2": "PROSPECTIVE"}
    assert again["proposal_detail"]["class[O1]"] == "N"
    assert "O1" not in again["prefill_reasons"]
    assert again["questionnaire"]["O1"] == answered["O1"]
    assert _row(k02, created["id"])["questionnaire"] == answered


@pytest.mark.control("CTL-007")
def test_submit_request_keeps_the_rows_retained_snapshot(
    k02: K02World, runtime: JobRuntime
) -> None:
    """REQ-PLT-015 (04 §16.14 rev 1.92): the ``MODIFICATION`` request's impact preview IS the
    row's retained ``IMPACT_PREVIEW`` file — one ``file_object``, one hash — and the request
    shows its 04 §16.10 summary from that document's ``before`` / ``after`` members.

    Of CTL-007's row this witnesses its evidence, the preview snapshot (03
    REQ-MOD-013 "The preview is snapshotted with the approval"): the request an
    approver is shown carries the one file the preview retained, under the hash the
    preview job answered, and shows that document's figures. Not witnessed here:
    the refusal of a submission without a preview
    (``test_submit_needs_preview_snapshot``) and the decision on the request.
    """
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    finished = _preview(k02, created["id"], runtime)
    request_id = _submit(k02, created["id"])
    row = _row(k02, created["id"])
    request = get(k02.app, f"/api/v1/approvals/{request_id}", k02.priya).json()
    assert request["impact_preview"]["file_id"] == str(row["impact_preview_file_id"])
    assert (
        request["impact_preview"]["sha256"]
        == row["impact_preview_sha256"]
        == finished["result"]["impact_preview_sha256"]
    )
    snapshots = k02.place.rows(
        select(file_object.c.id).where(file_object.c.sha256 == row["impact_preview_sha256"])
    )
    assert [item["id"] for item in snapshots] == [row["impact_preview_file_id"]]
    document = _retained_document(k02, created["id"])
    assert sorted(document) == ["after", "before", "provenance", "summary"]
    shown = request["impact_preview"]["summary"]
    assert shown["revenue_by_period_after"] == document["after"]["revenue_by_period"]
    assert shown["revenue_by_period_before"] == document["before"]["revenue_by_period"]
    assert shown["revenue_by_period_after"][0] == {
        "period_key": "FY2026-P09",
        "amount": {"amount": "11769.80", "currency": "USD"},
    }
    # 04 §16.10 rev 1.126: the summary states the catch-up total the stored preview carries; a
    # modification moves no criteria-met book.
    assert shown["catch_up_total"] == document["after"]["catch_up_total"]
    assert shown["catch_up_total"] == document["summary"]["catch_up_total"]
    assert shown["criteria_met"] is None


@pytest.mark.control("CTL-007")
def test_submit_needs_preview_snapshot(k02: K02World, runtime: JobRuntime) -> None:
    """BUILD_SPEC CTR-17: ``/submit`` without a preview returns 422 with ``rule_id = "REQ-PLT-015"``
    (PRD ERR-53); with the preview it creates a ``MODIFICATION`` request storing an
    ``IMPACT_PREVIEW`` file and its SHA-256 (REQ-PLT-015; DG-KRN-APR-01).

    Of CTL-007's row this witnesses its evidence, "modification register with
    questionnaire and preview snapshot", where it prevents: a submission without a
    preview is refused, and with one the request carries the hash of the row's
    preview and the content hash of the row. Not witnessed here: that the hash is
    the retained file's (``test_submit_request_keeps_the_rows_retained_snapshot``)
    and the decision on the request.
    """
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    refused = post(
        k02.app, f"{MODIFICATIONS}/{created['id']}/submit", k02.place.author, {"comment": "x"}
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["errors"][0]["rule_id"] == "REQ-PLT-015"
    finished = _preview(k02, created["id"], runtime)
    request_id = _submit(k02, created["id"])
    request = get(k02.app, f"/api/v1/approvals/{request_id}", k02.priya).json()
    assert (
        request["subject"]["type"] == "MODIFICATION"
    )  # ApprovalOut.subject (TEST-APPROVAL-SHAPE-1)
    assert request["impact_preview"]["sha256"] == finished["result"]["impact_preview_sha256"]
    row = _row(k02, created["id"])
    assert (str(row["status"]), row["content_sha256"] is not None) == ("SUBMITTED", True)
    assert row["impact_preview_sha256"] == finished["result"]["impact_preview_sha256"]
    assert request["subject"]["content_sha256"] == row["content_sha256"]


def test_treatment_override_needs_judgement(k02: K02World, runtime: JobRuntime) -> None:
    """BUILD_SPEC CTR-17: choosing ``CUMULATIVE_CATCH_UP`` for O1 against the proposal without a
    reviewed ``MODIFICATION_TREATMENT_OVERRIDE`` judgement makes ``/submit`` return 422 with
    ``rule_id = "REQ-MOD-002"`` (PRD ERR-54); with the reviewed record it succeeds (S06-R-01)."""
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    _patch(
        k02,
        created["id"],
        {"chosen_treatments": {"O1": "CUMULATIVE_CATCH_UP", "O2": "PROSPECTIVE"}},
    )
    _classify(k02, created["id"])  # the edit invalidated the classification; re-proposed
    _preview(k02, created["id"], runtime)
    refused = post(
        k02.app, f"{MODIFICATIONS}/{created['id']}/submit", k02.place.author, {"comment": "x"}
    )
    assert refused.status_code == 422, refused.text
    error = refused.json()["errors"][0]
    assert (error["rule_id"], error["field"]) == ("REQ-MOD-002", "chosen_treatments.O1")
    judgement = post(
        k02.app,
        "/api/v1/judgements",
        k02.place.author,
        {
            "topic": "MODIFICATION_TREATMENT_OVERRIDE",
            "subject_type": "modification",
            "subject_id": created["id"],
            "conclusion": "Catch-up: the added seats are not distinct in substance.",
            "questionnaire": {
                "conclusion": "Catch-up: the added seats are not distinct in substance."
            },
            "rationale": "Reviewed with the revenue reviewer.",
        },
    )
    assert judgement.status_code == 201, judgement.text
    judgement_id = judgement.json()["id"]
    submitted = post(k02.app, f"/api/v1/judgements/{judgement_id}/submit", k02.place.author, {})
    assert submitted.status_code == 200, submitted.text
    reviewed = approve(k02.app, submitted.json()["approval_request_id"], k02.priya)
    assert reviewed.status_code == 200, reviewed.text
    _patch(k02, created["id"], {"judgement_record_id": judgement_id})
    _classify(k02, created["id"])
    _preview(k02, created["id"], runtime)
    _submit(k02, created["id"])


def test_step1_hold_release_1_a_record_of_a_modification_places_no_hold(k02: K02World) -> None:
    """Supervisor ruling R-23, second order, and its exception (04 T-CON-20 "Judgement holds"
    rev 1.209; item STEP1-HOLD-RELEASE-1). The REQ-POL-010 hold follows the contract a judgement
    record names — but a record whose subject is a modification places none: the modification
    changes nothing of the contract before its own approval, which the record's review precedes
    (PRD ERR-54), so no revenue is recognised on the unreviewed judgement; and a hold would move
    the contract's head under the draft's preview. K-02 active with a draft change order: its
    treatment-override record is sent for review and reviewed, the contract is never on hold
    and its head does not move."""
    contract_id = _k02_contract(k02)
    maya = k02.place.author
    created = _create(k02, contract_id, _upgrade_body())

    def header() -> tuple[str, bool, int]:
        shown = get(k02.app, f"{CONTRACTS}/{contract_id}", maya).json()
        return str(shown["status"]), bool(shown["on_hold"]), int(shown["head_stream_version"])

    before = header()
    assert before[:2] == ("ACTIVE", False)
    judgement = post(
        k02.app,
        "/api/v1/judgements",
        maya,
        {
            "topic": "MODIFICATION_TREATMENT_OVERRIDE",
            "subject_type": "modification",
            "subject_id": created["id"],
            "conclusion": "Catch-up: the added seats are not distinct in substance.",
            "questionnaire": {
                "conclusion": "Catch-up: the added seats are not distinct in substance."
            },
            "rationale": "Reviewed with the revenue reviewer.",
        },
    )
    assert judgement.status_code == 201, judgement.text
    assert judgement.json()["contract_id"] == str(contract_id)
    sent = post(k02.app, f"/api/v1/judgements/{judgement.json()['id']}/submit", maya, {})
    assert sent.status_code == 200, sent.text
    assert (sent.json()["status"], sent.json()["approval_request_id"] is not None) == (
        "SUBMITTED",
        True,
    )
    assert header() == before
    reviewed = approve(k02.app, sent.json()["approval_request_id"], k02.priya)
    assert reviewed.status_code == 200, reviewed.text
    assert header() == before


@pytest.mark.control("CTL-007")
def test_approval_applies_contract_amended(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """BUILD_SPEC CTR-17: approval by ``priya`` appends ``CONTRACT_AMENDED`` with ``treatments``,
    ``lines`` and ``ssp_basis`` copied from the modification; after the computation the modification
    is ``APPLIED`` with ``applied_event_id`` (SM-03).

    Of CTL-007's row this witnesses the approval that applies: the decision of a
    second person appends one ``CONTRACT_AMENDED`` that names the modification, its
    treatments, its line and the approval request, and the modification is APPLIED
    with that event. Not witnessed here: the refusal of the preparer's own decision
    and the voiding of a stale approval
    (``test_ctl_007_stale_or_self_approved_modification_not_applied``).
    """
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    _preview(k02, created["id"], runtime)
    request_id = _submit(k02, created["id"])
    clock.advance(timedelta(minutes=1))
    decided = approve(k02.app, request_id, k02.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    (amended,) = _events(k02, contract_id, ContractEventType.CONTRACT_AMENDED)
    assert amended["payload"]["modification_id"] == created["id"]
    assert amended["payload"]["treatments"] == {"O1": "PROSPECTIVE", "O2": "PROSPECTIVE"}
    assert [line["obligation_key"] for line in amended["payload"]["lines"]] == ["O2"]
    assert amended["origin"] == "SYSTEM" and amended["modification_id"] == UUID(created["id"])
    assert amended["approval_request_id"] == UUID(request_id)
    row = _row(k02, created["id"])
    assert (str(row["status"]), row["applied_event_id"]) == ("APPLIED", amended["id"])
    versions = k02.place.rows(
        select(obligation_version.c.obligation_key)
        .where(obligation_version.c.contract_id == contract_id)
        .order_by(obligation_version.c.version_no.desc(), obligation_version.c.obligation_key)
    )
    assert {str(v["obligation_key"]) for v in versions} >= {"O1", "O2"}  # REQ-MOD-022


def test_wld_x_06_applied_schedule_by_obligation(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """PRD WLD-X-06 rev 1.21 (supervisor ruling R-17) on the APPLIED contract, through the public
    schedule route: "schedule Sep 2026 (O1 / O2) 11,769.80 (9,649.25 / 2,120.55); schedule Oct
    2026 14,132.46" and the allocation O1 remaining / O2 added seats 148,451.55 / 66,726.53 — O1's
    allocation is what it had recognised through 15 Sep, 84,821.92, plus its share. The
    September pair is O1 round(84,821.92 + 148,451.5470… × 15 ÷ 472) − 79,890.41 and O2
    round(66,726.5329… × 15 ÷ 472); the totals are the ones the preview showed (J-05-AC-1)."""
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    _preview(k02, created["id"], runtime)
    request_id = _submit(k02, created["id"])
    clock.advance(timedelta(minutes=1))
    decided = approve(k02.app, request_id, k02.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    listed = get(k02.app, f"{CONTRACTS}/{contract_id}/schedule", k02.place.author, {"limit": "500"})
    assert listed.status_code == 200, listed.text
    revenue: dict[tuple[str, str], Decimal] = {}
    for item in listed.json()["items"]:
        if item["schedule_kind"] == "REVENUE" and item["obligation_key"] is not None:
            key = (item["period"]["period_key"], item["obligation_key"])
            revenue[key] = revenue.get(key, Decimal(0)) + Decimal(item["amount"]["amount"])
    september = (revenue[("FY2026-P09", "O1")], revenue[("FY2026-P09", "O2")])
    assert september == (Decimal("9649.25"), Decimal("2120.55")), revenue
    assert sum(september) == Decimal("11769.80")
    assert revenue[("FY2026-P10", "O1")] + revenue[("FY2026-P10", "O2")] == Decimal("14132.46")
    assert revenue[("FY2026-P08", "O1")] == Decimal("10191.78")  # untouched history
    assert ("FY2026-P08", "O2") not in revenue
    allocated = {
        str(row["obligation_key"]): Decimal(str(row["allocated_amount"]))
        for row in k02.place.rows(
            select(obligation_version)
            .where(obligation_version.c.contract_id == contract_id)
            .order_by(obligation_version.c.version_no)  # the latest version wins
        )
    }
    assert allocated == {"O1": Decimal("233273.47"), "O2": Decimal("66726.53")}
    assert allocated["O1"] - Decimal("84821.92") == Decimal("148451.55")


def test_separate_contract_books_new_contract(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """BUILD_SPEC CTR-17: K-01 modification ``CR-PELLWORTH-2026-07`` (50 seats × 6 months,
    30,000.00 at SSP 50 × 100.00 × 6) with treatment ``SEPARATE_CONTRACT`` books contract
    ``SF-ORD-10388`` in its own group and appends nothing to the K-01 stream (S06-R-03; PRD
    WLD-K-01b). The K-02 world stands in for K-01's seat product."""
    contract_id = _k02_contract(k02)
    body = _upgrade_body(
        kind="ADD_OBLIGATION",
        reference="CR-PELLWORTH-2026-07",
        lines=[
            {
                "obligation_key": "O2",
                "action": "ADD",
                "product_code": "AVM-SEAT-MO",
                "quantity_delta": "300",
                "consideration_delta": {"amount": "30000.00", "currency": "USD"},
                "start_date": "2026-07-01",
                "end_date": "2026-12-31",
            }
        ],
        effective_date="2026-07-01",
        questionnaire={"separate_contract_external_id": "SF-ORD-10388"},
    )
    created = _create(k02, contract_id, body)
    classified = _classify(k02, created["id"])
    assert classified["proposed_treatments"] == {"O2": "SEPARATE_CONTRACT"}
    _preview(k02, created["id"], runtime)
    request_id = _submit(k02, created["id"])
    clock.advance(timedelta(minutes=1))
    assert approve(k02.app, request_id, k02.priya).status_code == 200
    assert _events(k02, contract_id, ContractEventType.CONTRACT_AMENDED) == []
    (new,) = k02.place.rows(select(contract).where(contract.c.external_id == "SF-ORD-10388"))
    original = k02.place.rows(select(contract).where(contract.c.id == contract_id))[0]
    assert new["combination_group_id"] != original["combination_group_id"]
    row = _row(k02, created["id"])
    (booking,) = _events(k02, UUID(str(new["id"])), ContractEventType.CONTRACT_BOOKED)
    assert (str(row["status"]), row["applied_event_id"]) == ("APPLIED", booking["id"])


def test_repeat_reference_rejected(k02: K02World) -> None:
    """BUILD_SPEC CTR-17: a second modification of K-02 with reference ``CR-MARROWBY-2026-09``
    returns 422 ``validation-failed`` naming ``reference`` (``ux_modification__reference``)."""
    contract_id = _k02_contract(k02)
    _create(k02, contract_id, _upgrade_body())
    repeated = post(
        k02.app, f"{CONTRACTS}/{contract_id}/modifications", k02.place.author, _upgrade_body()
    )
    assert repeated.status_code == 422, repeated.text
    error = repeated.json()["errors"][0]
    assert (error["field"], error["rule_id"]) == ("reference", "ux_modification__reference")


def test_tc_10_new_pob_versions_every_obligation(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """BUILD_SPEC CTR-17 (legacy 03 §7.3 TC-10 fixed; REQ-MOD-022): a modification adding only
    obligation O4 to a contract of three obligations produces a contract version holding obligation
    versions for all four obligations."""
    seats = [("O1", "40", "96000.00"), ("O2", "30", "72000.00"), ("O3", "30", "72000.00")]
    body = k02_body(k02.customer_id)
    body["lines"] = [
        {
            "obligation_key": key,
            "product_code": "AVM-SEAT-MO",
            "quantity": str(int(seats_) * 24),
            "total_price": {"amount": price, "currency": "USD"},
            "start_date": "2026-01-01",
            "end_date": "2027-12-31",
        }
        for key, seats_, price in seats
    ]
    booked = booked_contract(k02.place, body, activate=False)
    activated = activated_contract(k02.place, booked)
    contract_id = UUID(str(activated.contract["id"]))
    computed(k02.place, UUID(str(activated.combination_group["id"])))
    created = _create(
        k02,
        contract_id,
        _upgrade_body(
            kind="ADD_OBLIGATION",
            lines=[
                {
                    "obligation_key": "O4",
                    "action": "ADD",
                    "product_code": "AVM-SEAT-MO",
                    "quantity_delta": "775",  # 50 seats × 15.5 seat-months (PER_INCREMENT)
                    "consideration_delta": {"amount": "60000.00", "currency": "USD"},
                    "start_date": "2026-09-16",
                    "end_date": "2027-12-31",
                }
            ],
        ),
    )
    _classify(k02, created["id"])
    _preview(k02, created["id"], runtime)
    request_id = _submit(k02, created["id"])
    clock.advance(timedelta(minutes=1))
    assert approve(k02.app, request_id, k02.priya).status_code == 200
    latest = k02.place.rows(
        select(obligation_version.c.version_no, obligation_version.c.obligation_key)
        .where(
            obligation_version.c.contract_id == contract_id,
            obligation_version.c.book_code == "ASC606",
        )
        .order_by(obligation_version.c.version_no.desc())
    )
    top = max(int(v["version_no"]) for v in latest)
    keys = sorted(str(v["obligation_key"]) for v in latest if int(v["version_no"]) == top)
    assert keys == ["O1", "O2", "O3", "O4"]


@pytest.mark.skip(
    reason="NOT RUN here by design: TC-REP-01 is the parity suite's LEGACY_PARITY world "
    "(tests/parity); this is the BUILD_SPEC-named entry point (D-98 140-A7)"
)
def test_tc_rep_01_shipped_state_sixteen_obligation_versions(k02: K02World) -> None:
    """BUILD_SPEC CTR-17 (legacy 06 §7.3 TC-REP-01; DG-PAR-06 row-count rule): under the preset,
    Contracts 1 and 2 booked on 2023-01-01 (8 booking lines) and one progress batch dated
    2023-01-31 for both give 16 ``obligation_version`` rows in book ASC606 for the two contracts.
    Exercised by the parity suite's LEGACY_PARITY world (``tests/parity``); recorded here as the
    BUILD_SPEC-named entry point and asserted through that suite's row count when run."""
    raise AssertionError("skipped by the marker above; the parity suite asserts the 16 rows")


@pytest.mark.control("CTL-007")
def test_ctl_007_stale_or_self_approved_modification_not_applied(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """BUILD_SPEC CTR-17 CTL-007 (REQ-PLT-014), reworked per D-98 140-A7 TEST-CTL007-1:
    (1) self-approval is isolated with an otherwise AUTHORIZED, MFA-enrolled preparer (Nadia holds
    revenue_accountant + revenue_reviewer) so no MFA or authority refusal precedes it → 403
    ``self-approval``; (2) editing the SUBMITTED modification voids its request STALE_SUBJECT and a
    decision on it is 409 ``invalid-transition`` (the non-pending refusal precedes any hash
    compare); (3) the PENDING stale-basis case: a hash the client
    retained before a valid event moved a member head is refused 409 ``stale-approval`` while the
    request is still PENDING. The contract version is unchanged throughout.

    Of CTL-007's row this witnesses the approval and the stale-approval voiding of a
    modification. Its classification and its preview are made on the way and not asserted here
    (``test_classify_k02_upgrade``, ``test_submit_request_keeps_the_rows_retained_snapshot``),
    and no modification is applied (``test_approval_applies_contract_amended``)."""
    contract_id = _k02_contract(k02)
    someone = colleague(k02.place.tenant_id, "nadia")
    assign(someone, "revenue_accountant")
    assign(someone, "revenue_reviewer")
    nadia = enrolled(k02.app, clock, someone)
    created = post(k02.app, f"{CONTRACTS}/{contract_id}/modifications", nadia, _upgrade_body())
    assert created.status_code == 201, created.text
    modification_id = str(created.json()["id"])
    assert (
        post(k02.app, f"{MODIFICATIONS}/{modification_id}/classify", nadia, {}).status_code == 200
    )
    _preview(k02, modification_id, runtime)
    request_id = _submit(k02, modification_id, nadia)
    before = k02.place.rows(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )[0]
    # (1) the preparer's own decision — authorized and MFA-fresh, refused only as self-approval
    own = approve(k02.app, request_id, nadia)
    assert (own.status_code, own.json()["type"].rsplit("/", 1)[-1]) == (403, "self-approval"), (
        own.text
    )
    # (2) an edit of the SUBMITTED row returns it to DRAFT and voids the request STALE_SUBJECT
    edited = _patch(
        k02, modification_id, {"rationale": "Marrowby confirmed 50 seats; term unchanged."}
    )
    assert edited["status"] == "DRAFT"
    request = get(k02.app, f"/api/v1/approvals/{request_id}", k02.priya).json()
    assert (request["status"], request["void_reason"]) == ("VOIDED", "STALE_SUBJECT")
    clock.advance(timedelta(minutes=1))
    # a decision on the VOIDED request is refused as the non-pending transition BEFORE any hash
    # compare (approvals engine ``_require_pending``; D-98 140-A10 (1)) — the stale-basis refusal
    # is witnessed on a PENDING request in (3)
    voided = approve(k02.app, request_id, k02.priya)
    assert voided.status_code == 409, voided.text
    assert voided.json()["type"].rsplit("/", 1)[-1] == "invalid-transition"
    # (3) PENDING stale basis: the approver retained the displayed hash, then a valid event moved
    # the contract head (the §16.10 content includes the member heads); the retained hash is refused
    second = _create(k02, contract_id, _upgrade_body(reference="CR-MARROWBY-2026-12"))
    _classify(k02, second["id"])
    _preview(k02, second["id"], runtime)
    pending_id = _submit(k02, second["id"])
    retained = get(k02.app, f"/api/v1/approvals/{pending_id}", k02.priya).json()["subject"][
        "content_sha256"
    ]
    head = k02.place.rows(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )[0]["head_stream_version"]
    appended(
        k02.place,
        contract_id,
        int(head),
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 9, 20),
                payload=BillingRecordedV1(
                    invoice_number="INV-CTL007-1",
                    line_external_id="1",
                    obligation_key="O1",
                    amount=MoneyIn(amount="1000.00", currency="USD"),
                    issue_date=date(2026, 9, 20),
                ),
                obligation_keys=("O1",),
            )
        ],
    )
    clock.advance(timedelta(minutes=1))
    still_pending = get(k02.app, f"/api/v1/approvals/{pending_id}", k02.priya).json()
    assert still_pending["status"] == "PENDING"
    refused = _approve_with(k02.app, pending_id, k02.priya, retained)
    assert refused.status_code == 409, refused.text
    assert refused.json()["type"].rsplit("/", 1)[-1] == "stale-approval"
    after = k02.place.rows(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )[0]
    assert after["head_stream_version"] == before["head_stream_version"] + 1  # the billing only
    assert _events(k02, contract_id, ContractEventType.CONTRACT_AMENDED) == []


# --- D-98 140-A4 / 140-A5 witnesses (Codex production-20260921-1703 §2, 1713 §1–§2) --------------
# DB-bound like the rest of this module: written for the lane database, recorded NOT RUN.


def _audit_versions(world: K02World, modification_id: str) -> list[str | None]:
    rows = world.place.rows(
        select(audit_event.c.object_version)
        .where(
            audit_event.c.object_type == "modification",
            audit_event.c.object_id == UUID(modification_id),
        )
        .order_by(audit_event.c.chain_seq)
    )
    return [None if r["object_version"] is None else str(r["object_version"]) for r in rows]


def test_rowversion_1_commands_advance_the_row_version_and_the_audit_matches(
    k02: K02World, runtime: JobRuntime
) -> None:
    """D-98 140-A5 ROWVERSION-1: T-CON-06 is IM-S without ``tg_touch``, so every command advances
    ``row_version`` in its own UPDATE; the audit ``object_version`` equals the resulting row's; a
    queued preview whose row was edited in between is refused (``PREVIEW_STALE``); ``ETag`` follows
    the version (API-C-08)."""
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    assert created["row_version"] == 1
    shown = get(k02.app, f"{MODIFICATIONS}/{created['id']}", k02.place.author)
    assert shown.headers["ETag"] == '"r1"'
    edited = _patch(k02, created["id"], {"rationale": "Marrowby confirmed 50 seats."})
    assert edited["row_version"] == 2
    shown = get(k02.app, f"{MODIFICATIONS}/{created['id']}", k02.place.author)
    assert shown.headers["ETag"] == '"r2"'
    classified = _classify(k02, created["id"])
    assert classified["row_version"] == 3
    assert _audit_versions(k02, created["id"]) == ["1", "2", "3"]
    assert _row(k02, created["id"])["row_version"] == 3
    # the queued preview names row_version 3; an edit before the worker runs makes it 4
    queued = post(k02.app, f"{MODIFICATIONS}/{created['id']}/preview", k02.place.author, {})
    assert queued.status_code == 202, queued.text
    again = _patch(k02, created["id"], {"rationale": "Edited."})
    assert again["row_version"] == 4
    _work(k02.place, UUID(queued.json()["id"]), runtime)
    finished = get(k02.app, f"{JOBS}/{queued.json()['id']}", k02.place.author).json()
    assert finished["state"] == "FAILED", finished
    row = _row(k02, created["id"])
    assert (row["impact_preview_file_id"], row["row_version"]) == (None, 4)


def test_a4_get_etag_and_list_catch_up_total_from_the_retained_preview(
    k02: K02World, runtime: JobRuntime
) -> None:
    """D-98 140-A4: ``GET /modifications/{id}`` answers ``ETag "r<row_version>"``; the list item's
    ``impact_summary.catch_up_total`` is null before a preview and the retained preview's after."""
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    listed = get(k02.app, f"{CONTRACTS}/{contract_id}/modifications", k02.place.author).json()
    (item,) = listed["items"]
    assert item["impact_summary"] == {"catch_up_total": None}
    finished = _preview(k02, created["id"], runtime)
    listed = get(k02.app, f"{CONTRACTS}/{contract_id}/modifications", k02.place.author).json()
    (item,) = listed["items"]
    assert (
        item["impact_summary"]["catch_up_total"] == finished["result"]["summary"]["catch_up_total"]
    )
    assert item["impact_summary"]["catch_up_total"]["amount"] == "0.00"
    shown = get(k02.app, f"{MODIFICATIONS}/{created['id']}", k02.place.author)
    assert shown.status_code == 200
    assert shown.headers["ETag"] == f'"r{shown.json()["row_version"]}"'
    assert shown.json()["impact_preview"]["catch_up_total"]["amount"] == "0.00"


def _reviewed_override(world: K02World, modification_id: str, conclusion: str) -> str:
    judgement = post(
        world.app,
        "/api/v1/judgements",
        world.place.author,
        {
            "topic": "MODIFICATION_TREATMENT_OVERRIDE",
            "subject_type": "modification",
            "subject_id": modification_id,
            "conclusion": conclusion,
            "questionnaire": {"conclusion": conclusion},
            "rationale": "Reviewed with the revenue reviewer.",
        },
    )
    assert judgement.status_code == 201, judgement.text
    judgement_id = str(judgement.json()["id"])
    submitted = post(world.app, f"/api/v1/judgements/{judgement_id}/submit", world.place.author, {})
    assert submitted.status_code == 200, submitted.text
    reviewed = approve(world.app, submitted.json()["approval_request_id"], world.priya)
    assert reviewed.status_code == 200, reviewed.text
    return judgement_id


def _departing(world: K02World, modification_id: str, judgement_id: str | None) -> None:
    body: dict[str, Any] = {"chosen_treatments": {"O1": "CUMULATIVE_CATCH_UP", "O2": "PROSPECTIVE"}}
    if judgement_id is not None:
        body["judgement_record_id"] = judgement_id
    _patch(world, modification_id, body)
    _classify(world, modification_id)


def test_judgement_1_another_modifications_reviewed_override_is_refused(
    k02: K02World, runtime: JobRuntime
) -> None:
    """D-98 140-A5 JUDGEMENT-1: modifications A and B of one contract; B's reviewed
    MODIFICATION_TREATMENT_OVERRIDE linked to A does not satisfy A's departure (422 REQ-MOD-002);
    A's own record does (04 T-CON-06 ``judgement_record_id``)."""
    contract_id = _k02_contract(k02)
    a = _create(k02, contract_id, _upgrade_body())
    b = _create(k02, contract_id, _upgrade_body(reference="CR-MARROWBY-2026-10"))
    _classify(k02, a["id"])
    _classify(k02, b["id"])
    b_record = _reviewed_override(k02, b["id"], "B: the added seats are not distinct in substance.")
    _departing(k02, a["id"], b_record)
    _preview(k02, a["id"], runtime)
    refused = post(k02.app, f"{MODIFICATIONS}/{a['id']}/submit", k02.place.author, {"comment": "x"})
    assert refused.status_code == 422, refused.text
    error = refused.json()["errors"][0]
    assert (error["rule_id"], error["field"]) == ("REQ-MOD-002", "chosen_treatments.O1")
    a_record = _reviewed_override(k02, a["id"], "A: the added seats are not distinct in substance.")
    _departing(k02, a["id"], a_record)
    _preview(k02, a["id"], runtime)
    _submit(k02, a["id"])


def test_domain_r1_submit_refuses_a_preview_after_another_members_event(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """D-98 140-A5 DOMAIN-R1: contracts A and B combined in one group; A's preview retains the
    group basis (every member's head); a valid B event between A's preview and A's submit — A
    unchanged — makes ``/submit`` refuse 422 REQ-PLT-015 ``PREVIEW_STALE`` instead of relabelling
    the old summary; a fresh preview then submits. The retained candidate and ``input_sha256`` are
    reproducible from the stored document."""
    a_id = _k02_contract(k02)
    b_booked = booked_contract(
        k02.place, {**k02_body(k02.customer_id), "external_id": "SF-ORD-10002-B"}, activate=False
    )
    b_activated = activated_contract(k02.place, b_booked)
    computed(k02.place, UUID(str(b_activated.combination_group["id"])))
    b_id = UUID(str(b_activated.contract["id"]))
    grouped = post(
        k02.app,
        "/api/v1/combination-groups",
        k02.place.author,
        {
            "contract_ids": [str(a_id), str(b_id)],
            "criterion": "606-10-25-9(a)",
            "rationale": "Negotiated as a package with Marrowby.",
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
    created = _create(k02, a_id, _upgrade_body())
    _classify(k02, created["id"])
    finished = _preview(k02, created["id"], runtime)
    stored = _row(k02, created["id"])
    assert stored["impact_preview_sha256"] == finished["result"]["impact_preview_sha256"]
    head_b = k02.place.rows(select(contract.c.head_stream_version).where(contract.c.id == b_id))[0]
    appended(
        k02.place,
        b_id,
        int(head_b["head_stream_version"]),
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 9, 17),
                payload=BillingRecordedV1(
                    invoice_number="INV-B-1",
                    line_external_id="1",
                    obligation_key="O1",
                    amount=MoneyIn(amount="10000.00", currency="USD"),
                    issue_date=date(2026, 9, 17),
                ),
                obligation_keys=("O1",),
            )
        ],
    )
    refused = post(
        k02.app, f"{MODIFICATIONS}/{created['id']}/submit", k02.place.author, {"comment": "x"}
    )
    assert refused.status_code == 422, refused.text
    error = refused.json()["errors"][0]
    assert (error["rule_id"], error["field"]) == ("REQ-PLT-015", "impact_preview")
    assert "not of this modification as it stands" in error["message"]
    _preview(k02, created["id"], runtime)
    _submit(k02, created["id"])


def test_domain_r2_classify_collects_a_pending_add_product_absent_from_every_event(
    k02: K02World,
) -> None:
    """D-98 140-A5 DOMAIN-R2: a mapped product no earlier group event names, introduced only by
    the pending ADD line, reaches the classification's templates through the builder without an
    applying event — the engine proposes a treatment for the new obligation (no PRODUCT_UNMAPPED
    drift of the proposal population)."""
    contract_id = _k02_contract(k02)
    # ``q`` searches code and name; ``code`` is no filter of pob-templates (04 API-R-24: ``status``)
    templates = get(k02.app, "/api/v1/pob-templates", k02.place.author, {"q": "TPL-SUB-DAILY"})
    assert templates.status_code == 200, templates.text
    (daily,) = [t for t in templates.json()["items"] if t["code"] == "TPL-SUB-DAILY"]
    onboarding = product_with_template(
        k02.app,
        k02.place.author,
        code="AVM-ONB-FEE",
        name="Onboarding fee",
        revenue_category="SERVICE",
    )
    set_default_template(k02.app, k02.place.author, onboarding, daily["id"])
    created = _create(
        k02,
        contract_id,
        _upgrade_body(
            kind="ADD_OBLIGATION",
            lines=[
                {
                    "obligation_key": "O3",
                    "action": "ADD",
                    "product_code": "AVM-ONB-FEE",
                    "quantity_delta": "1",
                    "consideration_delta": {"amount": "5000.00", "currency": "USD"},
                    "start_date": "2026-09-16",
                    "end_date": "2026-10-15",
                }
            ],
        ),
    )
    classified = _classify(k02, created["id"])
    assert "O3" in classified["proposed_treatments"], classified
    assert classified["proposed_treatments"]["O3"] in {
        "PROSPECTIVE",
        "SEPARATE_CONTRACT",
        "CUMULATIVE_CATCH_UP",
    }


def _k11_contract(world: K11World) -> UUID:
    booked = booked_contract(world.place, k11_body(world.customer_id), activate=False)
    activated = activated_contract(world.place, booked)
    computed(world.place, UUID(str(activated.combination_group["id"])))
    return UUID(str(activated.contract["id"]))


def test_routing_fx_1_eur_modification_routes_at_the_retained_spot_rate(
    k11: K11World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """D-98 140-A5 ROUTING-FX-1: an EUR modification of the EUR entity (functional EUR) adding
    240,000.00 of transaction price. Without an approved EUR→USD spot rate the preview retains an
    absence and ``/submit`` refuses 422 REQ-PLT-015 naming the pair and the date. With EUR→USD 1.11
    approved and the preview re-run, the request carries amount 240,000.00 EUR (functional, rate
    1) and the TP-change flag (266,400.00 USD ≥ 250,000.00), so a Controller second step routes."""
    contract_id = _k11_contract(k11)
    body = {
        "effective_date": "2026-09-16",
        # a new obligation with a term of its own (it ends a day after O2): no E-25 subscription
        # shape (ENGINE_SPEC S06-R-19), so the generic kind
        "kind": "ADD_OBLIGATION",
        "reference": "CR-DE-5004-2026-09",
        "lines": [
            {
                "obligation_key": "O3",
                "action": "ADD",
                "product_code": "AVM-SUP-12",
                "quantity_delta": "12",
                "consideration_delta": {"amount": "240000.00", "currency": "EUR"},
                "start_date": "2026-09-16",
                "end_date": "2027-09-15",
            }
        ],
        "rationale": "Twelve more support units for the German plant.",
    }
    created = post(k11.app, f"{CONTRACTS}/{contract_id}/modifications", k11.place.author, body)
    assert created.status_code == 201, created.text
    modification_id = str(created.json()["id"])
    assert (
        post(
            k11.app, f"{MODIFICATIONS}/{modification_id}/classify", k11.place.author, {}
        ).status_code
        == 200
    )
    _preview(k11, modification_id, runtime)  # type: ignore[arg-type]
    refused = post(
        k11.app, f"{MODIFICATIONS}/{modification_id}/submit", k11.place.author, {"comment": "x"}
    )
    assert refused.status_code == 422, refused.text
    error = refused.json()["errors"][0]
    assert error["rule_id"] == "REQ-PLT-015"
    assert "no spot rate from EUR to USD on 2026-09-16" in error["message"]
    rate_set = post(
        k11.app,
        "/api/v1/fx-rate-sets",
        k11.place.author,
        {"code": "TREASURY-SPOT", "name": "Treasury spot rates", "rate_type": "spot"},
    )
    assert rate_set.status_code == 201, rate_set.text
    draft = post(
        k11.app,
        f"/api/v1/fx-rate-sets/{rate_set.json()['id']}/versions",
        k11.place.author,
        {
            "coverage_from": "2026-09-01",
            "coverage_to": "2026-12-31",
            "rates": [
                {
                    "base_currency": "EUR",
                    "quote_currency": "USD",
                    "rate": "1.11",
                    "effective_date": "2026-09-15",
                }
            ],
        },
    )
    assert draft.status_code == 201, draft.text
    submitted = post(
        k11.app,
        f"/api/v1/fx-rate-set-versions/{draft.json()['id']}/submit",
        k11.place.author,
        {"comment": "Treasury statement"},
        if_match=f'"r{draft.json()["row_version"]}"',
    )
    assert submitted.status_code == 200, submitted.text
    clock.advance(timedelta(minutes=1))
    approved = approve(k11.app, submitted.json()["pending_approval_request_id"], k11.marcus)
    assert approved.status_code == 200, approved.text
    _preview(k11, modification_id, runtime)  # type: ignore[arg-type]
    sent = post(
        k11.app,
        f"{MODIFICATIONS}/{modification_id}/submit",
        k11.place.author,
        {"comment": "Approve the German upgrade."},
    )
    assert sent.status_code == 200, sent.text
    request = get(
        k11.app, f"/api/v1/approvals/{sent.json()['approval_request_id']}", k11.priya
    ).json()
    assert request["amount"] == {"amount": "240000.00", "currency": "EUR"}
    assert "TP_CHANGE_GE_250K" in request["flags"] and "CATCH_UP_GE_50K" not in request["flags"]
    assert len(request["steps"]) == 2


def test_q3_legacy_template_naming_a_native_row_is_refused(k02: K02World) -> None:
    """D-98 140-A5 Q3: a legacy-template ``CONTRACT_AMENDED`` whose ``modification_id`` names an
    EXISTING native T-CON-06 row is refused by name when the bundle is built (NATIVE_AND_LEGACY),
    instead of projecting the legacy treatment over the row; the builder resolves every named id
    before deciding native versus legacy."""
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    head = k02.place.rows(
        select(contract.c.head_stream_version, contract.c.combination_group_id).where(
            contract.c.id == contract_id
        )
    )[0]
    appended(
        k02.place,
        contract_id,
        int(head["head_stream_version"]),
        [
            EventIn(
                event_type=ContractEventType.CONTRACT_AMENDED,
                effective_date=date(2026, 9, 16),
                payload=ContractAmendedV1(
                    modification_id=UUID(created["id"]),
                    treatments={"O1": ModificationTreatment.LEGACY_PROSPECTIVE},
                    lines=(),
                    ssp_basis={},
                ),
                obligation_keys=(),
                modification_id=UUID(created["id"]),
            )
        ],
    )
    with pytest.raises(ValueError, match="legacy-template CONTRACT_AMENDED names the platform"):
        computed(k02.place, UUID(str(head["combination_group_id"])))


# --- D-98 140-A6 witnesses (Codex production-20260921-1727 / 1733); DB-bound, NOT RUN ------------


def _pellworth_body() -> dict[str, Any]:
    return _upgrade_body(
        kind="ADD_OBLIGATION",
        reference="CR-PELLWORTH-2026-07",
        lines=[
            {
                "obligation_key": "O2",
                "action": "ADD",
                "product_code": "AVM-SEAT-MO",
                "quantity_delta": "300",
                "consideration_delta": {"amount": "30000.00", "currency": "USD"},
                "start_date": "2026-07-01",
                "end_date": "2026-12-31",
            }
        ],
        effective_date="2026-07-01",
        questionnaire={"separate_contract_external_id": "SF-ORD-10388"},
    )


def test_separate_preview_1_is_a_dry_run_booking_in_its_own_group(
    k02: K02World, runtime: JobRuntime
) -> None:
    """SEPARATE-PREVIEW-1: the preview of a SEPARATE_CONTRACT choice books the new contract in its
    own group inside a rolled-back savepoint — the summary is the new contract's (TP before 0.00,
    after 30,000.00), the original stream head is unchanged, no contract SF-ORD-10388 exists
    afterwards, and the retained candidate is the CONTRACT_BOOKED payload."""
    contract_id = _k02_contract(k02)
    head_before = k02.place.rows(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )[0]["head_stream_version"]
    created = _create(k02, contract_id, _pellworth_body())
    classified = _classify(k02, created["id"])
    assert classified["proposed_treatments"] == {"O2": "SEPARATE_CONTRACT"}
    finished = _preview(k02, created["id"], runtime)
    summary = finished["result"]["summary"]
    assert summary["transaction_price_before"]["amount"] == "0.00"
    assert summary["transaction_price_after"]["amount"] == "30000.00"
    assert k02.place.rows(select(contract).where(contract.c.external_id == "SF-ORD-10388")) == []
    head_after = k02.place.rows(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )[0]["head_stream_version"]
    assert head_after == head_before
    shown = get(k02.app, f"{MODIFICATIONS}/{created['id']}", k02.place.author).json()
    assert shown["impact_preview"]["transaction_price_after"]["amount"] == "30000.00"


def test_separate_choice_1_departures_apply_in_both_directions(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """SEPARATE-CHOICE-1: (a) proposal SEPARATE_CONTRACT, chosen PROSPECTIVE with a reviewed
    override → approval appends CONTRACT_AMENDED and books nothing; (b) proposal PROSPECTIVE
    (the Marrowby upgrade), chosen SEPARATE_CONTRACT with a reviewed override → approval books the
    separate contract and appends nothing to the original stream. The mode is the approved
    choice."""
    contract_id = _k02_contract(k02)
    # (a) departure away from the proposal's SEPARATE_CONTRACT
    a = _create(k02, contract_id, _pellworth_body())
    _classify(k02, a["id"])
    a_record = _reviewed_override(k02, a["id"], "Pellworth: priced as part of the original deal.")
    _patch(
        k02, a["id"], {"chosen_treatments": {"O2": "PROSPECTIVE"}, "judgement_record_id": a_record}
    )
    _classify(k02, a["id"])
    _preview(k02, a["id"], runtime)
    request_a = _submit(k02, a["id"])
    clock.advance(timedelta(minutes=1))
    assert approve(k02.app, request_a, k02.priya).status_code == 200
    (amended,) = _events(k02, contract_id, ContractEventType.CONTRACT_AMENDED)
    assert amended["payload"]["modification_id"] == a["id"]
    assert k02.place.rows(select(contract).where(contract.c.external_id == "SF-ORD-10388")) == []
    # (b) departure towards SEPARATE_CONTRACT: a FRESH key O3 (O2 now exists on the contract after
    # (a) applied; re-adding it would trip the duplicate-key guard — TEST-SEPARATE-DIRECTIONS-1)
    b_body = _upgrade_body(reference="CR-MARROWBY-2026-11")
    b_body["lines"][0]["obligation_key"] = "O3"
    b = _create(k02, contract_id, b_body)
    classified_b = _classify(k02, b["id"])
    b_record = _reviewed_override(k02, b["id"], "Marrowby: the added seats are a separate deal.")
    _patch(
        k02,
        b["id"],
        {
            # every proposed key chosen SEPARATE_CONTRACT (the choice is per line; a mix refuses)
            "chosen_treatments": dict.fromkeys(
                classified_b["proposed_treatments"], "SEPARATE_CONTRACT"
            ),
            "judgement_record_id": b_record,
        },
    )
    _classify(k02, b["id"])
    _preview(k02, b["id"], runtime)
    request_b = _submit(k02, b["id"])
    clock.advance(timedelta(minutes=1))
    assert approve(k02.app, request_b, k02.priya).status_code == 200
    assert len(_events(k02, contract_id, ContractEventType.CONTRACT_AMENDED)) == 1  # (a) only
    (new,) = k02.place.rows(
        select(contract).where(contract.c.external_id == f"SF-ORD-10002-{b['modification_no']}")
    )
    assert new["combination_group_id"] is not None
    assert _row(k02, b["id"])["status"] == "APPLIED"
    assert new["external_id"].endswith(b["modification_no"])  # the booking, not a re-ADD of O2


def test_separate_input_1_mixed_choice_refused_at_submit_before_approval(
    k02: K02World, runtime: JobRuntime
) -> None:
    """SEPARATE-INPUT-1 / CHOICE-1 (order per D-98 140-A9): a modification mixing
    SEPARATE_CONTRACT with another treatment is refused at /submit by name (S06-R-03) BEFORE the
    preview prerequisite — no REQ-PLT-015 masks the shape — and never at apply; with a valid
    (non-mixed) choice the preview stays required."""
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    record = _reviewed_override(k02, created["id"], "Mixed on purpose.")
    _patch(
        k02,
        created["id"],
        {
            "chosen_treatments": {"O1": "PROSPECTIVE", "O2": "SEPARATE_CONTRACT"},
            "judgement_record_id": record,
        },
    )
    _classify(k02, created["id"])
    sent = post(
        k02.app, f"{MODIFICATIONS}/{created['id']}/submit", k02.place.author, {"comment": "x"}
    )
    assert sent.status_code == 422, sent.text
    errors = [(error["field"], error["rule_id"]) for error in sent.json()["errors"]]
    assert ("chosen_treatments.O1", "S06-R-03") in errors
    assert all(rule != "REQ-PLT-015" for _, rule in errors)  # the shape, not a missing preview
    # a valid choice without a preview is still the preview prerequisite
    _patch(k02, created["id"], {"chosen_treatments": {"O1": "PROSPECTIVE", "O2": "PROSPECTIVE"}})
    _classify(k02, created["id"])
    sent = post(
        k02.app, f"{MODIFICATIONS}/{created['id']}/submit", k02.place.author, {"comment": "x"}
    )
    assert sent.status_code == 422 and sent.json()["errors"][0]["rule_id"] == "REQ-PLT-015"
    _preview(k02, created["id"], runtime)
    _submit(k02, created["id"])


# --- D-98 140-A8 (Codex production-20260921-1854 §1) witnesses; DB-bound, NOT RUN -----------------


def test_preview_commit_1_worker_commits_the_preview_transaction(
    k02: K02World, runtime: JobRuntime
) -> None:
    """PREVIEW-COMMIT-1: the registered worker runs the preview job and COMMITS the complete
    successful transaction; a fresh transaction then reads the row's pointer and hash, the
    IMPACT_PREVIEW file row, the ``modification.preview_stored`` audit with the resulting row's
    version, and the list / detail routes show the preview."""
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    finished = _preview(k02, created["id"], runtime)
    row = _row(k02, created["id"])  # a fresh transaction
    assert row["impact_preview_file_id"] is not None
    assert row["impact_preview_sha256"] == finished["result"]["impact_preview_sha256"]
    (stored_file,) = k02.place.rows(
        select(file_object).where(file_object.c.id == row["impact_preview_file_id"])
    )
    assert str(stored_file["sha256"]) == row["impact_preview_sha256"]
    audits = k02.place.rows(
        select(audit_event.c.action, audit_event.c.object_version)
        .where(
            audit_event.c.object_type == "modification",
            audit_event.c.object_id == UUID(created["id"]),
            audit_event.c.action == "modification.preview_stored",
        )
        .order_by(audit_event.c.chain_seq)
    )
    assert [str(a["object_version"]) for a in audits] == [str(row["row_version"])]
    shown = get(k02.app, f"{MODIFICATIONS}/{created['id']}", k02.place.author).json()
    assert shown["impact_preview"]["catch_up_total"]["amount"] == "0.00"
    listed = get(k02.app, f"{CONTRACTS}/{contract_id}/modifications", k02.place.author).json()
    assert listed["items"][0]["impact_summary"]["catch_up_total"]["amount"] == "0.00"


def test_domain_r1_capture_preview_job_waits_for_the_group_lock(
    k02: K02World, runtime: JobRuntime
) -> None:
    """DOMAIN-R1 capture (scoped, D-98 140-A11 (4)): the preview job takes the governed lock order
    (group → contract → row) BEFORE it builds the bundle. Witnessed, interleaved and bound to the
    participants (the P5 pattern): a holder locks the group; the worker's backend is observed
    blocked on the combination_group row; after the release the job SUCCEEDS, the preview file row
    is committed and the contract head is unchanged. Not asserted here: a sibling append racing
    the capture (no second member in this world) — the retained-basis comparison at submit is
    ``test_domain_r1_submit_refuses_a_preview_after_another_members_event``."""
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    queued = post(k02.app, f"{MODIFICATIONS}/{created['id']}/preview", k02.place.author, {})
    assert queued.status_code == 202, queued.text
    job_id = UUID(queued.json()["id"])
    ctx = DbContext(tenant_id=k02.place.tenant_id, user_id=None, entity_scope="*")
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            _work(k02.place, job_id, runtime)
        except Exception as exc:  # noqa: BLE001 — surfaced by the assertions below
            outcome["error"] = exc

    worker = threading.Thread(target=run, name="interleaved-preview-worker")
    started = False
    try:
        with observing_checkouts() as backends, tenant_session(ctx) as holder:
            holder_pid = backend_pid(holder)
            current = repo.get_contract(holder, contract_id)
            repo.lock_group(holder, UUID(str(current["combination_group_id"])))
            head_under_lock = int(current["head_stream_version"])
            worker.start()
            started = True
            try:
                blocked_pid, blocked_in = await_lock_wait(
                    holder, holder_pid=holder_pid, backends=backends, timeout=20.0
                )
                assert blocked_pid != holder_pid and worker.is_alive(), (blocked_pid, blocked_in)
                assert "combination_group" in blocked_in.lower(), blocked_in
            finally:
                holder.rollback()  # TEST-PREVIEW-CLEANUP-1: the holder releases on every outcome
    finally:
        if started:
            worker.join(timeout=30)  # bounded; a still-live worker is reported, never hidden
            assert not worker.is_alive(), "the preview worker is still running after the release"
    assert "error" not in outcome, outcome
    finished = get(k02.app, f"{JOBS}/{job_id}", k02.place.author).json()
    assert finished["state"] == "SUCCEEDED", finished
    shown = get(k02.app, f"{MODIFICATIONS}/{created['id']}", k02.place.author).json()
    assert shown["impact_preview"] is not None
    row = _row(k02, created["id"])
    document = k02.place.rows(
        select(file_object.c.id).where(file_object.c.id == row["impact_preview_file_id"])
    )
    assert document, "the committed preview file row"
    assert (
        head_under_lock
        == k02.place.rows(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )[0]["head_stream_version"]
    )


# --- D-98 140-A9 (Codex production-20260921-1925) witnesses; DB-bound, NOT RUN -------------------


def test_a9_input_1_payable_money_reaches_classify_and_the_separate_preview(
    k02: K02World, runtime: JobRuntime
) -> None:
    """INPUT-1 payable (A9) / TEST-NATIVE-CURRENCY-1 (A12): a consideration_payable of USD 500.00
    promised on 15 Jun 2026 — BEFORE the 1 Jul inception, with no distinct good — is authored,
    classifies natively (Money members normalised at the adapter) and previews as the dry-run
    booking whose transaction price is reduced by the payable (606-10-32-25: 30,000.00 − 500.00 =
    29,500.00). A payable in EUR is refused at the input boundary with the exact field and rule
    (T-CON-06) — no row, no approval request, no applying event."""
    contract_id = _k02_contract(k02)
    body = _pellworth_body()
    body["consideration_payable"] = [
        {"amount": {"amount": "500.00", "currency": "USD"}, "promise_date": "2026-06-15"}
    ]
    created = _create(k02, contract_id, body)
    classified = _classify(k02, created["id"])
    assert classified["proposed_treatments"] == {"O2": "SEPARATE_CONTRACT"}
    finished = _preview(k02, created["id"], runtime)
    summary = finished["result"]["summary"]
    assert summary["transaction_price_after"]["amount"] == "29500.00"  # reduced by the payable
    foreign = _pellworth_body()
    foreign["reference"] = "CR-PELLWORTH-2026-08"
    foreign["consideration_payable"] = [
        {"amount": {"amount": "500.00", "currency": "EUR"}, "promise_date": "2026-06-15"}
    ]
    refused = post(k02.app, f"{CONTRACTS}/{contract_id}/modifications", k02.place.author, foreign)
    assert refused.status_code == 422, refused.text
    problem = refused.json()
    assert problem["type"].rsplit("/", 1)[-1] == "validation-failed"
    (error,) = [e for e in problem["errors"] if e["field"].startswith("consideration_payable")]
    assert (error["field"], error["rule_id"]) == (
        "consideration_payable[0].amount.currency",
        "T-CON-06",
    )
    rows = k02.place.rows(
        select(modification).where(modification.c.reference == "CR-PELLWORTH-2026-08")
    )
    assert rows == []  # nothing authored, so no approval request and no applying event
    assert _events(k02, contract_id, ContractEventType.CONTRACT_AMENDED) == []


def test_a12_run_preview_refuses_a_mixed_choice_before_dispatch_and_retains_no_preview(
    k02: K02World, runtime: JobRuntime
) -> None:
    """A12 (2): a mixed chosen map (SEPARATE_CONTRACT beside PROSPECTIVE) is refused by the preview
    job BEFORE dispatch — the job fails with the named S06-R-03 refusal, the row keeps no preview
    pointer / hash, and the ordinary CONTRACT_AMENDED path is never built for it."""
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    record = _reviewed_override(k02, created["id"], "Mixed on purpose.")
    _patch(
        k02,
        created["id"],
        {
            "chosen_treatments": {"O1": "PROSPECTIVE", "O2": "SEPARATE_CONTRACT"},
            "judgement_record_id": record,
        },
    )
    _classify(k02, created["id"])
    queued = post(k02.app, f"{MODIFICATIONS}/{created['id']}/preview", k02.place.author, {})
    assert queued.status_code == 202, queued.text
    _work(k02.place, UUID(queued.json()["id"]), runtime)
    finished = get(k02.app, f"{JOBS}/{queued.json()['id']}", k02.place.author).json()
    assert finished["state"] == "FAILED", finished
    assert "S06-R-03" in str(finished.get("error") or finished.get("problem") or finished)
    row = _row(k02, created["id"])
    assert (row["impact_preview_file_id"], row["impact_preview_sha256"]) == (None, None)


# --- D-98 140-A14 (Codex production-20260921-2029 §2): INPUT-1 preview admission ----------------

NAMED_VERSION_AT: Final = datetime(2026, 9, 1, tzinfo=UTC)
JUSTIFICATION: Final = "Pinned to the study the customer signed against."


def _labelled_k02_contract(world: K02World) -> UUID:
    """K-02 booked with the line's ``ssp_version_label`` (US-LIST ``2026-H1``), activated and
    computed under the default POL-070 basis — so a later tenant ``NAMED_VERSION`` publication still
    resolves the original contract by label when ``/classify`` dry-runs its group."""
    body = k02_seat_month_body(world.customer_id)
    body["lines"][0]["ssp_version_label"] = "2026-H1"
    booked = booked_contract(world.place, body, activate=False)
    activated = activated_contract(world.place, booked)
    computed(world.place, UUID(str(activated.combination_group["id"])))
    return UUID(str(activated.contract["id"]))


def _named_version_policy(world: K02World) -> None:
    """POL-070 ``ssp.version_basis`` = ``NAMED_VERSION`` published for the tenant at 1 Sep 2026
    (before the frozen clock), the only basis under which a separate contract honours an
    ``ssp_basis`` override (A9 INPUT-1)."""
    ctx = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as session:
        publish_registry_version(
            session,
            tenant_id=world.place.tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            values={"ssp.version_basis": "NAMED_VERSION"},
            at=NAMED_VERSION_AT,
        )


def _pellworth_override_body(version_id: str, *, label: str = "2026-H1") -> dict[str, Any]:
    """The Pellworth separate-contract body with the ADD line labelled and an ``ssp_basis``
    override naming ``version_id`` (the shape ``separate_errors`` admits: id WITH label)."""
    body = _pellworth_body()
    body["lines"][0]["ssp_version_label"] = label
    body["ssp_basis"] = {
        "O2": {
            "ssp_book_version_id": version_id,
            "is_override": True,
            "justification": JUSTIFICATION,
        }
    }
    return body


def _seat_entry() -> dict[str, Any]:
    return range_entry(
        SEAT_MONTH,
        "90.00",
        "100.00",
        "110.00",
        value_basis="PER_INCREMENT",
        quantity_unit="INCREMENTS",
    )


def _failed_preview(world: K02World, modification_id: str, runtime: JobRuntime) -> dict[str, Any]:
    """``POST /modifications/{id}/preview`` (202), the worker run, the job FAILED."""
    queued = post(world.app, f"{MODIFICATIONS}/{modification_id}/preview", world.place.author, {})
    assert queued.status_code == 202, queued.text
    _work(world.place, UUID(queued.json()["id"]), runtime)
    finished = get(world.app, f"{JOBS}/{queued.json()['id']}", world.place.author).json()
    assert finished["state"] == "FAILED", finished
    return dict(finished)


def _problem_errors(finished: dict[str, Any]) -> list[tuple[str | None, str | None, str]]:
    """The errors of a FAILED job's API-S-Problem; the slug is the last segment of ``type`` (04
    §15.2 rule 3) — ``code`` is the optional §15.4 code, null for a ``validation-failed``."""
    problem = finished["problem"]
    assert problem is not None, finished
    assert problem["type"].rsplit("/", 1)[-1] == "validation-failed", finished
    return [(item["field"], item["rule_id"], item["message"]) for item in problem["errors"]]


def _retained_document(world: K02World, modification_id: str) -> dict[str, Any]:
    """The stored ``IMPACT_PREVIEW`` document, read back through the file store (plaintext)."""
    row = _row(world, modification_id)
    assert row["impact_preview_file_id"] is not None, row
    with world.place.uow() as uow:
        _, stream = open_file(
            uow.session,
            UUID(str(row["impact_preview_file_id"])),
            files=uow.files,
            keyring=uow.keyring,
        )
        with stream:
            return dict(json.loads(stream.read().decode("utf-8")))


def _nothing_retained(world: K02World, modification_id: str, contract_id: UUID, head: int) -> None:
    row = _row(world, modification_id)
    assert (row["impact_preview_file_id"], row["impact_preview_sha256"]) == (None, None), row
    assert world.place.rows(select(contract).where(contract.c.external_id == "SF-ORD-10388")) == []
    (current,) = world.place.rows(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    assert current["head_stream_version"] == head


def _head(world: K02World, contract_id: UUID) -> int:
    (row,) = world.place.rows(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    return int(row["head_stream_version"])


def test_a14_input_1_preview_refuses_an_unknown_ssp_version_id_and_retains_nothing(
    k02: K02World, runtime: JobRuntime
) -> None:
    """A14 (1): a SEPARATE_CONTRACT choice whose ``ssp_basis`` override names an id that is no SSP
    book version at all — a valid label, a valid all-ADD line — FAILS the preview job by name
    (``S06-R-03``, ``ssp_basis.O2.ssp_book_version_id``, "names no approved SSP book version")
    BEFORE the dry-run booking: no preview pointer / hash, no contract SF-ORD-10388, the K-02 head
    unchanged. Previously the preview computed the labelled SSP and retained SUCCEEDED (Codex 2029
    §2)."""
    contract_id = _k02_contract(k02)
    head = _head(k02, contract_id)
    created = _create(k02, contract_id, _pellworth_override_body(str(uuid4())))
    classified = _classify(k02, created["id"])
    assert classified["proposed_treatments"] == {"O2": "SEPARATE_CONTRACT"}
    finished = _failed_preview(k02, created["id"], runtime)
    errors = _problem_errors(finished)
    assert len(errors) == 1, errors
    field, rule, message = errors[0]
    assert (field, rule) == ("ssp_basis.O2.ssp_book_version_id", "S06-R-03")
    assert "names no approved SSP book version" in message
    _nothing_retained(k02, created["id"], contract_id, head)


def test_a14_input_1_preview_refuses_an_unapproved_ssp_version_id(
    k02: K02World, runtime: JobRuntime
) -> None:
    """A14 (1): an id that names a REAL version of the K-02 book which is not APPROVED (a DRAFT
    ``2027`` version) is refused exactly like an unknown one — approval, not existence, admits an
    override — with nothing retained."""
    contract_id = _k02_contract(k02)
    head = _head(k02, contract_id)
    drafted = post(
        k02.app,
        f"{SSP_BOOKS}/{k02.book_id}/versions",
        k02.place.author,
        {
            "legacy_version_label": "2027",
            "effective_from_date": "2027-01-01",
            "methodology_label": "List-price study",
        },
    )
    assert drafted.status_code == 201, drafted.text
    draft_id = str(drafted.json()["id"])
    shown = get(k02.app, f"{SSP_BOOK_VERSIONS}/{draft_id}", k02.place.author).json()
    assert shown["status"] == "DRAFT", shown
    created = _create(k02, contract_id, _pellworth_override_body(draft_id, label="2027"))
    _classify(k02, created["id"])
    finished = _failed_preview(k02, created["id"], runtime)
    errors = _problem_errors(finished)
    assert [(field, rule) for field, rule, _ in errors] == [
        ("ssp_basis.O2.ssp_book_version_id", "S06-R-03")
    ]
    assert "names no approved SSP book version" in errors[0][2]
    _nothing_retained(k02, created["id"], contract_id, head)


def test_a14_input_1_preview_admits_the_approved_matching_version_and_retains_its_selection(
    k02: K02World, runtime: JobRuntime
) -> None:
    """A14 (1) control: under POL-070 ``NAMED_VERSION`` an override naming the APPROVED US-LIST
    ``2026-H1`` version, on a line labelled ``2026-H1``, previews SUCCEEDED; the stored document
    retains the booking's actual selection ``{"O2": "US-LIST@v1"}`` in
    ``provenance.separate_contract.ssp_selection``, and ``/submit`` (which re-runs the same checks
    over the retained selection) routes the request."""
    contract_id = _labelled_k02_contract(k02)
    _named_version_policy(k02)
    created = _create(k02, contract_id, _pellworth_override_body(k02.version_id))
    classified = _classify(k02, created["id"])
    assert classified["proposed_treatments"] == {"O2": "SEPARATE_CONTRACT"}
    finished = _preview(k02, created["id"], runtime)
    assert finished["result"]["summary"]["transaction_price_after"]["amount"] == "30000.00"
    document = _retained_document(k02, created["id"])
    separate = document["provenance"]["separate_contract"]
    assert separate["dry_run_booking"] is True and separate["own_combination_group"] is True
    assert separate["ssp_selection"] == {"O2": "US-LIST@v1"}
    request_id = _submit(k02, created["id"])
    assert request_id


def test_a14_input_1_preview_refuses_a_same_label_version_of_a_book_the_booking_does_not_select(
    k02: K02World, runtime: JobRuntime
) -> None:
    """A14 (1) same-label mismatch control (the A12 scenario on real books): a second book
    ``US-ALT`` with an APPROVED ``2026-H1`` version and the same seat entry ties with ``US-LIST`` on
    scope, and S05-R-02 breaks the tie by ascending code — the booking selects ``US-ALT``. An
    override naming US-LIST's version FAILS the preview by name (``SSP_SELECTION_MISMATCH`` naming
    both keys) with nothing retained; re-pointed at the US-ALT version it previews SUCCEEDED with
    ``US-ALT@v1`` retained."""
    contract_id = _labelled_k02_contract(k02)
    _named_version_policy(k02)
    alt_book = ssp_book(k02.app, k02.place.author, code="US-ALT")
    alt_version = approved_ssp_version(
        k02.app,
        k02.place.author,
        [k02.priya],
        alt_book,
        label="2026-H1",
        effective_from="2026-01-01",
        entries=[_seat_entry()],
    )
    head = _head(k02, contract_id)
    created = _create(k02, contract_id, _pellworth_override_body(k02.version_id))
    _classify(k02, created["id"])
    finished = _failed_preview(k02, created["id"], runtime)
    errors = _problem_errors(finished)
    assert [(field, rule) for field, rule, _ in errors] == [
        ("ssp_basis.O2.ssp_book_version_id", "S06-R-03")
    ]
    assert "US-ALT@v1" in errors[0][2] and "US-LIST@v1" in errors[0][2]
    _nothing_retained(k02, created["id"], contract_id, head)
    _patch(
        k02,
        created["id"],
        {
            "ssp_basis": {
                "O2": {
                    "ssp_book_version_id": alt_version,
                    "is_override": True,
                    "justification": JUSTIFICATION,
                }
            }
        },
    )
    _classify(k02, created["id"])
    _preview(k02, created["id"], runtime)
    document = _retained_document(k02, created["id"])
    assert document["provenance"]["separate_contract"]["ssp_selection"] == {"O2": "US-ALT@v1"}


# --- item MOD-DISCARD-1 (supervisor ruling R-118 (e)): ``POST /modifications/{id}/discard`` ---

NOT_DISCARDABLE: Final = "Only a draft modification can be discarded."
# PRD ERR-82.
REVIEW_PENDING: Final = (
    "Judgement record {judgement_no} of this modification is waiting for review. Its preparer "
    "withdraws the review request first."
)
MODIFICATION_VOIDED: Final = "The modification of this record is voided. It takes no review."


def _discard(world: K02World, modification_id: str, actor: Actor | None = None) -> Any:
    return post(
        world.app, f"{MODIFICATIONS}/{modification_id}/discard", actor or world.place.author, {}
    )


def _discard_audits(world: K02World, modification_id: str) -> list[tuple[Any, Any, Any]]:
    rows = world.place.rows(
        select(audit_event.c.object_version, audit_event.c.before, audit_event.c.after)
        .where(
            audit_event.c.object_type == "modification",
            audit_event.c.object_id == UUID(modification_id),
            audit_event.c.action == "modification.discard",
        )
        .order_by(audit_event.c.chain_seq)
    )
    return [(row["object_version"], row["before"], row["after"]) for row in rows]


def test_mod_discard_1_any_draft_without_a_pending_request_is_discarded(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """Item MOD-DISCARD-1 (supervisor ruling R-118 (e); PRD SM-03 "Discard draft"; SCREENS §7.3). No
    route moved a DRAFT modification to VOIDED, so a mistaken draft stayed in the preparer's work
    for ever. ``POST /modifications/{id}/discard`` voids ANY draft without a pending request: one
    that was never submitted, and one that was submitted and withdrawn — the request's history
    stays on the row and in the audit trail. Every holder of ``modification.create`` may discard
    (a discard writes no content). Refused: a SUBMITTED row, and a row that is already VOIDED.
    The contract is not touched. The discarded draft frees its reference (04 T-CON-06 rev 1.210,
    revision 0114; the supervisor's ruling on the lane's question — before, the reference of a
    mistyped draft stayed taken for ever): a new draft takes it, and holds it as before."""
    contract_id = _k02_contract(k02)
    head = _head(k02, contract_id)

    # --- a draft that was never submitted ---
    created = _create(k02, contract_id, _upgrade_body())
    discarded = _discard(k02, created["id"])
    assert discarded.status_code == 200, discarded.text
    body = discarded.json()
    assert (body["status"], body["approval_request_id"], body["row_version"]) == ("VOIDED", None, 2)
    assert discarded.headers["ETag"] == '"r2"'
    assert _discard_audits(k02, created["id"]) == [("2", {"status": "DRAFT"}, {"status": "VOIDED"})]
    again = _discard(k02, created["id"])
    assert (again.status_code, again.json()["type"].rsplit("/", 1)[-1]) == (
        409,
        "invalid-transition",
    )
    assert [
        (error["field"], error["rule_id"], error["message"]) for error in again.json()["errors"]
    ] == [(None, "SM-03", NOT_DISCARDABLE)]
    classified = post(k02.app, f"{MODIFICATIONS}/{created['id']}/classify", k02.place.author, {})
    assert classified.status_code == 409, classified.text
    repeated = post(
        k02.app, f"{CONTRACTS}/{contract_id}/modifications", k02.place.author, _upgrade_body()
    )
    assert repeated.status_code == 201, repeated.text  # the discarded draft freed its reference
    assert repeated.json()["reference"] == created["reference"]
    taken = post(
        k02.app, f"{CONTRACTS}/{contract_id}/modifications", k02.place.author, _upgrade_body()
    )
    assert taken.status_code == 422, taken.text  # … which the new draft holds
    assert taken.json()["errors"][0]["rule_id"] == "ux_modification__reference"

    # --- a draft that was submitted and withdrawn, discarded by another holder ---
    second = _create(k02, contract_id, _upgrade_body(reference="CR-MARROWBY-2026-10"))
    _classify(k02, second["id"])
    _preview(k02, second["id"], runtime)
    request_id = _submit(k02, second["id"])
    pending = _discard(k02, second["id"])
    assert (pending.status_code, pending.json()["type"].rsplit("/", 1)[-1]) == (
        409,
        "invalid-transition",
    )
    assert pending.json()["errors"][0]["message"] == NOT_DISCARDABLE
    withdrawn = post(
        k02.app,
        f"{MODIFICATIONS}/{second['id']}/withdraw",
        k02.place.author,
        {"comment": "Wrong order."},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "DRAFT"
    someone = colleague(k02.place.tenant_id, "nadia")
    assign(someone, "revenue_accountant")
    nadia = enrolled(k02.app, clock, someone)
    gone = _discard(k02, second["id"], nadia)
    assert gone.status_code == 200, gone.text
    assert (gone.json()["status"], gone.json()["approval_request_id"]) == ("VOIDED", request_id)
    request = get(k02.app, f"/api/v1/approvals/{request_id}", k02.priya).json()
    assert (request["status"], request["void_reason"]) == ("WITHDRAWN", "WITHDRAWN_BY_PREPARER")
    assert len(_discard_audits(k02, second["id"])) == 1

    # --- nothing reached the contract ---
    assert _head(k02, contract_id) == head
    assert _events(k02, contract_id, ContractEventType.CONTRACT_AMENDED) == []


def test_mod_discard_1_waits_for_a_pending_review_of_the_modifications_own_record(
    k02: K02World,
) -> None:
    """Item MOD-DISCARD-1, Q-D2 of supervisor ruling R-118 (e) (PRD ERR-82). A review of a
    ``MODIFICATION_TREATMENT_OVERRIDE`` record pins the contract's head and group, not the
    modification, so a discard would have left it PENDING — a request to be decided for a voided
    modification. The discard is refused by name while such a review is pending; the review's
    preparer withdraws it (``POST /approvals/{id}/withdraw``), and the draft is then discarded.
    The mirror: no review is requested for a record of a voided modification."""
    maya = k02.place.author
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())

    def record() -> tuple[str, str]:
        made = post(
            k02.app,
            "/api/v1/judgements",
            maya,
            {
                "topic": "MODIFICATION_TREATMENT_OVERRIDE",
                "subject_type": "modification",
                "subject_id": created["id"],
                "conclusion": "Catch-up: the added seats are not distinct in substance.",
                "questionnaire": {
                    "conclusion": "Catch-up: the added seats are not distinct in substance."
                },
                "rationale": "To be reviewed with the revenue reviewer.",
            },
        )
        assert made.status_code == 201, made.text
        return str(made.json()["id"]), str(made.json()["judgement_no"])

    judgement_id, judgement_no = record()
    submitted = post(k02.app, f"/api/v1/judgements/{judgement_id}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    review_id = str(submitted.json()["approval_request_id"])

    refused = _discard(k02, created["id"])
    assert (refused.status_code, refused.json()["type"].rsplit("/", 1)[-1]) == (
        409,
        "invalid-transition",
    )
    assert [
        (error["field"], error["rule_id"], error["message"]) for error in refused.json()["errors"]
    ] == [(None, "SM-03", REVIEW_PENDING.format(judgement_no=judgement_no))]
    assert str(_row(k02, created["id"])["status"]) == "DRAFT"
    assert _discard_audits(k02, created["id"]) == []

    # The review's preparer withdraws it; the record ends REJECTED and the draft is discarded.
    withdrawn = post(
        k02.app, f"/api/v1/approvals/{review_id}/withdraw", maya, {"comment": "No longer needed."}
    )
    assert withdrawn.status_code == 200, withdrawn.text
    shown = get(k02.app, f"/api/v1/judgements/{judgement_id}", maya).json()
    assert shown["status"] == "REJECTED"
    discarded = _discard(k02, created["id"])
    assert discarded.status_code == 200, discarded.text
    assert discarded.json()["status"] == "VOIDED"

    # The mirror: a record of the voided modification is not sent for review.
    late_id, _ = record()
    late = post(k02.app, f"/api/v1/judgements/{late_id}/submit", maya, {})
    assert (late.status_code, late.json()["type"].rsplit("/", 1)[-1]) == (
        409,
        "invalid-transition",
    )
    assert [
        (error["field"], error["rule_id"], error["message"]) for error in late.json()["errors"]
    ] == [("subject_id", "DB-03", MODIFICATION_VOIDED)]
    assert get(k02.app, f"/api/v1/judgements/{late_id}", maya).json()["status"] == "DRAFT"


# --- items MOD-PATCH-CLEAR-1 and MOD-ANSWER-PREVIEW-1 (supervisor ruling R-119 (e)) ---------------


def test_mod_patch_clear_1_a_nullable_member_sent_as_null_is_cleared(k02: K02World) -> None:
    """Item MOD-PATCH-CLEAR-1 (supervisor ruling R-119 (e); 04 §16.14 rev 1.188; a fact of lane
    F-CTR-WEB's CTR-27). ``PATCH`` left a member that was sent as null, so no client could remove
    a price-change amount, a judgement record or a reference from a draft. A member that is LEFT
    OUT leaves the stored value; a nullable authored member SENT AS NULL is cleared, and the
    audit event shows the null; null for a member that cannot be null leaves it, as before. The
    cleared reference is free for the contract again."""
    maya = k02.place.author
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body(price_change_amount="500.00"))
    judgement = post(
        k02.app,
        "/api/v1/judgements",
        maya,
        {
            "topic": "MODIFICATION_TREATMENT_OVERRIDE",
            "subject_type": "modification",
            "subject_id": created["id"],
            "conclusion": "Catch-up: the added seats are not distinct in substance.",
            "questionnaire": {
                "conclusion": "Catch-up: the added seats are not distinct in substance."
            },
            "rationale": "To be reviewed with the revenue reviewer.",
        },
    )
    assert judgement.status_code == 201, judgement.text
    judgement_id = str(judgement.json()["id"])
    linked = _patch(k02, created["id"], {"judgement_record_id": judgement_id})

    def stored(out: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
        amount = out["price_change_amount"]
        return (
            out["reference"],
            None if amount is None else Decimal(amount),
            out["rationale"],
            out["judgement_record_id"],
        )

    authored = (REFERENCE, Decimal("500.00"), _upgrade_body()["rationale"], judgement_id)
    assert stored(linked) == authored

    # A member that is left out stays: an empty PATCH changes none of them.
    assert stored(_patch(k02, created["id"], {})) == authored

    # Sent as null: cleared — in the answer, on the row and in the audit event.
    nulls = {
        "reference": None,
        "price_change_amount": None,
        "rationale": None,
        "judgement_record_id": None,
    }
    cleared = _patch(k02, created["id"], nulls)
    assert stored(cleared) == (None, None, None, None)
    row = _row(k02, created["id"])
    assert {name: row[name] for name in nulls} == nulls
    audited = k02.place.rows(
        select(audit_event.c.after)
        .where(
            audit_event.c.object_type == "modification",
            audit_event.c.object_id == UUID(created["id"]),
            audit_event.c.action == "modification.update",
        )
        .order_by(audit_event.c.chain_seq)
    )
    assert {name: audited[-1]["after"][name] for name in nulls} == nulls
    assert set(nulls).isdisjoint(audited[-2]["after"])  # the empty PATCH named none of them

    # Null for a member that cannot be null leaves it.
    left = _patch(k02, created["id"], {"kind": None, "lines": None})
    assert (left["kind"], len(left["lines"])) == (K02_KIND, 1)

    # The cleared reference is free for the contract again.
    again = _create(k02, contract_id, _upgrade_body())
    assert again["reference"] == REFERENCE


def test_mod_answer_preview_1_commands_answer_the_retained_preview(
    k02: K02World, runtime: JobRuntime
) -> None:
    """Item MOD-ANSWER-PREVIEW-1 (supervisor ruling R-119 (e); 04 §16.14 rev 1.188; a fact of lane
    F-CTR-WEB's CTR-27). The answers of ``/submit`` and ``/withdraw`` carried ``impact_preview:
    null`` and ``impact_summary.catch_up_total: null`` while the row stored a preview; only
    ``GET`` attached it. Every answer whose row stores a preview carries it — ``/submit``,
    ``/withdraw`` and ``/discard`` as ``GET``. ``PATCH`` and ``/classify`` clear the stored
    preview themselves: their answers carry none, and ``GET`` agrees."""
    maya = k02.place.author
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    path = f"{MODIFICATIONS}/{created['id']}"

    def preview_of(out: dict[str, Any]) -> tuple[Any, Any]:
        return out["impact_preview"], out["impact_summary"]

    def retained() -> tuple[Any, Any]:
        shown = get(k02.app, path, maya).json()
        assert shown["impact_preview"] is not None, shown
        assert shown["impact_summary"]["catch_up_total"] is not None, shown
        return preview_of(shown)

    none = (None, {"catch_up_total": None})

    # --- /submit and /withdraw keep the stored preview and answer it ---
    _classify(k02, created["id"])
    _preview(k02, created["id"], runtime)
    kept = retained()
    sent = post(k02.app, f"{path}/submit", maya, {"comment": "Approve the Marrowby upgrade."})
    assert sent.status_code == 200, sent.text
    assert preview_of(sent.json()) == kept
    withdrawn = post(k02.app, f"{path}/withdraw", maya, {"comment": "Wrong order."})
    assert withdrawn.status_code == 200, withdrawn.text
    assert (withdrawn.json()["status"], preview_of(withdrawn.json())) == ("DRAFT", kept)

    # --- PATCH and /classify clear it: null in the answer, and GET agrees ---
    patched = _patch(k02, created["id"], {"rationale": "Marrowby confirmed 50 seats."})
    assert preview_of(patched) == none
    assert preview_of(get(k02.app, path, maya).json()) == none
    _classify(k02, created["id"])
    _preview(k02, created["id"], runtime)
    retained()
    classified = _classify(k02, created["id"])
    assert preview_of(classified) == none
    assert preview_of(get(k02.app, path, maya).json()) == none

    # --- /discard keeps the stored preview and answers it ---
    _preview(k02, created["id"], runtime)
    kept = retained()
    discarded = _discard(k02, created["id"])
    assert discarded.status_code == 200, discarded.text
    assert (discarded.json()["status"], preview_of(discarded.json())) == ("VOIDED", kept)


def test_mod_ssp_override_preview_1_an_authored_override_of_the_added_seats(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """Item MOD-SSP-OVERRIDE-PREVIEW-1 (01-DECISIONS D-18; ENGINE_SPEC S06-R-11; 04 T-CON-06
    ``ssp_basis``). 2026-H2 (105.00 / 115.00 / 125.00) is in force on 16 September; the seat add
    names 2026-H1 for the added seats as an override, which the approval of the modification
    approves. The engine reads an override by version key and was handed the payload as stored,
    which names the version by id: the preview job failed inside the engine ("an ssp_basis
    override names no ssp_version_key"). With the key beside the id the preview computes — O1's
    remaining increments at the version in force, 2,400 x 472 / 730 x 105.00 = 162,936.99, the
    added seats at the named one, 775 x 90.00 = 69,750.00, so the pool of 215,178.08 splits
    150,676.53 / 64,501.55 — the applied contract carries it (O1 84,821.92 + 150,676.53) and the
    next computation posts nothing. An override naming a version that is not approved is refused
    by name before the dry run, and nothing is retained."""
    contract_id = _k02_contract(k02)
    head = _head(k02, contract_id)
    _second_half_version(k02, "105.00", "115.00", "125.00")
    drafted = post(
        k02.app,
        f"{SSP_BOOKS}/{k02.book_id}/versions",
        k02.place.author,
        {
            "legacy_version_label": "2027",
            "effective_from_date": "2027-01-01",
            "methodology_label": "List-price study",
        },
    )
    assert drafted.status_code == 201, drafted.text

    def named(version_id: str) -> dict[str, Any]:
        entry = {
            "ssp_book_version_id": version_id,
            "is_override": True,
            "justification": JUSTIFICATION,
        }
        return {"O2": entry}

    created = _create(k02, contract_id, _upgrade_body(ssp_basis=named(str(drafted.json()["id"]))))
    _classify(k02, created["id"])
    errors = _problem_errors(_failed_preview(k02, created["id"], runtime))
    assert [(field, rule) for field, rule, _ in errors] == [
        ("ssp_basis.O2.ssp_book_version_id", "S06-R-11")
    ]
    assert "names no approved SSP book version" in errors[0][2]
    _nothing_retained(k02, created["id"], contract_id, head)

    _patch(k02, created["id"], {"ssp_basis": named(k02.version_id)})
    _classify(k02, created["id"])
    summary = _preview(k02, created["id"], runtime)["result"]["summary"]
    assert (_remaining(summary, "O1"), _remaining(summary, "O2")) == ("150676.53", "64501.55")

    _applied(k02, created["id"], clock)
    overridden = {"O1": Decimal("235498.45"), "O2": Decimal("64501.55")}
    assert _allocated(k02, contract_id) == overridden
    _, output, _ = computed(k02.place, _group_of(k02, contract_id))
    assert [intent for book in output.books for intent in book.posting_intents] == []
    assert _allocated(k02, contract_id) == overridden


def test_mod_prefill_read_1_a_read_answers_the_classification(
    k02: K02World, runtime: JobRuntime
) -> None:
    """Item MOD-PREFILL-READ-1 (supervisor ruling R-119 (e) and the supervisor's ruling of
    2026-10-01; 04 T-CON-06 ``classification``, §16.14 rev 1.210; a fact of lane F-CTR-WEB's
    CTR-27). No read answered the proposals of a classified draft: ``prefill_reasons`` came only
    with the answer of ``/classify``, which writes an event, moves the row version and clears a
    stored preview. The row now keeps what ``/classify`` answered and every answer of the row
    carries it; a read writes nothing; an edit clears it with the proposal. A question the
    preparer answered is named no more, the price test as the class questions (item
    MOD-PREFILL-STORED-ANSWER-1, which replaced this item's "the price test is reported
    whatever the preparer answered" and its reason ``attested``)."""
    contract_id = _k02_contract(k02)
    maya = k02.place.author
    created = _create(k02, contract_id, _upgrade_body())
    path = f"{MODIFICATIONS}/{created['id']}"
    assert created["prefill_reasons"] == {}
    assert _row(k02, created["id"])["classification"] is None

    classified = _classify(k02, created["id"])
    reasons = classified["prefill_reasons"]
    assert classified["proposal_detail"]["class[O1]"] == "D"
    assert reasons["O2"]["priced_at_ssp"]["reason_key"].endswith(".below_range")
    # the row keeps the proposals, the engine's detail and its price tests, each under a member
    # of its own (item MOD-CLASSIFICATION-KEYS-1, rev 1.286; before it the obligations'
    # entries lay beside ``proposal`` and ``price_tests``)
    assert _row(k02, created["id"])["classification"] == {
        "proposal": classified["proposal_detail"],
        "obligations": reasons,
        "price_tests": classified["price_tests"],
    }

    # --- a read answers it, and writes nothing ---
    audits = len(_audit_versions(k02, created["id"]))
    first = get(k02.app, path, maya)
    again = get(k02.app, path, maya)
    assert first.status_code == 200, first.text
    assert first.json()["prefill_reasons"] == reasons == again.json()["prefill_reasons"]
    assert first.json()["questionnaire"] == {}  # the stored answers alone
    assert (first.headers["ETag"], first.json()["row_version"]) == (
        again.headers["ETag"],
        classified["row_version"],
    )
    assert len(_audit_versions(k02, created["id"])) == audits

    # --- the commands answer it too; it outlives the preview and the submission ---
    _preview(k02, created["id"], runtime)
    assert get(k02.app, path, maya).json()["prefill_reasons"] == reasons
    _submit(k02, created["id"])
    submitted = get(k02.app, path, maya).json()
    assert (submitted["status"], submitted["prefill_reasons"]) == ("SUBMITTED", reasons)
    assert submitted["impact_preview"] is not None

    # --- an edit clears it with the proposal ---
    answered = {"O2": {"priced_at_ssp": True}}
    edited = _patch(k02, created["id"], {"questionnaire": answered})
    assert (edited["status"], edited["proposed_treatments"], edited["prefill_reasons"]) == (
        "DRAFT",
        {},
        {},
    )
    assert _row(k02, created["id"])["classification"] is None
    assert get(k02.app, path, maya).json()["prefill_reasons"] == {}

    # --- answered true: the answer is the preparer's and the price test is named no more (item
    # MOD-PREFILL-STORED-ANSWER-1; rev 1.210 answered it as ``attested`` with the range) ---
    attested = _classify(k02, created["id"])
    assert sorted(attested["prefill_reasons"]["O2"]) == ["added_goods_distinct"]
    assert attested["questionnaire"]["O2"]["priced_at_ssp"] is True
    shown = get(k02.app, path, maya).json()
    assert shown["prefill_reasons"] == attested["prefill_reasons"]
    assert shown["questionnaire"] == answered

    # --- answered false: the same — the engine computes the test, and it is no proposal ---
    _patch(k02, created["id"], {"questionnaire": {"O2": {"priced_at_ssp": False}}})
    denied = _classify(k02, created["id"])
    assert sorted(denied["prefill_reasons"]["O2"]) == ["added_goods_distinct"]
    assert denied["questionnaire"]["O2"]["priced_at_ssp"] is False


def test_mod_prefill_stored_answer_1_a_stored_answer_is_not_named_a_proposal(
    k02: K02World,
) -> None:
    """Item MOD-PREFILL-STORED-ANSWER-1 (the supervisor's ruling of 2026-10-01; 04 §16.14 rev
    1.235; measured on main by lane WEB-QA's K-02 journey). ``prefill_reasons`` names a question
    only while the row holds no answer of the preparer for it — the price test as the two class
    questions. Before, a stored ``priced_at_ssp`` was still named by the next classification: a
    client that takes every named question for a proposal still to confirm left the stored
    answer out of its next save, and the answer was lost. Both answers of O2 stored: the
    classification names neither, a second save built from what no proposal names keeps both,
    and confirming the proposals moves no treatment."""
    contract_id = _k02_contract(k02)
    maya = k02.place.author
    created = _create(k02, contract_id, _upgrade_body())
    path = f"{MODIFICATIONS}/{created['id']}"
    first = _classify(k02, created["id"])
    assert sorted(first["prefill_reasons"]["O2"]) == ["added_goods_distinct", "priced_at_ssp"]

    # --- the preparer confirms O2's two proposals: both are stored ---
    confirmed = {
        question: entry["value"] for question, entry in first["prefill_reasons"]["O2"].items()
    }
    assert confirmed == {"added_goods_distinct": True, "priced_at_ssp": False}
    stored = _patch(k02, created["id"], {"questionnaire": {"O2": confirmed}})
    assert stored["questionnaire"] == {"O2": confirmed}
    assert _row(k02, created["id"])["questionnaire"] == {"O2": confirmed}

    # --- the classification behind it names neither; O1's question is still a proposal ---
    second = _classify(k02, created["id"])
    assert sorted(second["prefill_reasons"]) == ["O1"]
    assert second["questionnaire"]["O2"] == confirmed
    assert get(k02.app, path, maya).json()["prefill_reasons"] == second["prefill_reasons"]

    # --- a second save, built as a client builds it: what no proposal names is the preparer's ---
    kept = {
        key: {
            question: value
            for question, value in section.items()
            if question not in second["prefill_reasons"].get(key, {})
        }
        for key, section in second["questionnaire"].items()
    }
    assert kept == {"O1": {}, "O2": confirmed}
    remaining = "remaining_goods_distinct_from_transferred"
    kept["O1"] = {remaining: second["prefill_reasons"]["O1"][remaining]["value"]}
    saved = _patch(k02, created["id"], {"questionnaire": kept})
    assert saved["questionnaire"] == {"O1": {remaining: True}, "O2": confirmed}

    # --- every answer is the preparer's now: nothing is proposed, and no treatment has moved ---
    third = _classify(k02, created["id"])
    assert third["prefill_reasons"] == {} and "modification_key" in third["proposal_detail"]
    assert third["questionnaire"] == saved["questionnaire"]
    assert third["proposed_treatments"] == first["proposed_treatments"]
    shown = get(k02.app, path, maya).json()
    assert (shown["questionnaire"], shown["prefill_reasons"]) == (
        saved["questionnaire"],
        third["prefill_reasons"],
    )


def test_mod_price_test_fact_1_the_price_test_is_answered_beside_the_proposals(
    k02: K02World,
) -> None:
    """Item MOD-PRICE-TEST-FACT-1 (the supervisor's ruling of 2026-10-01; 04 §16.14 rev 1.250;
    a fact of lane F-CTR-WEB's SCREENS §7.6, which shows the price test's range beside the SSP
    version). Since ``prefill_reasons`` names a question only while it is unanswered, a draft
    whose answers are stored no longer carried the price test at all. ``price_tests``, a member
    of its own beside ``prefill_reasons``: the engine's price test of each added line as the
    classification read it, whatever the preparer answered — the proposal's entry while the
    question is open, the same entry once the answer is stored, and for an answer of true the
    engine's pass on that attestation, with the price and the range complete (60,000.00 against
    69,750.00 to 85,250.00: the row a reviewer must be able to read). A read answers it, an
    edit clears it, and O1, which the engine does not price-test, has no entry."""
    contract_id = _k02_contract(k02)
    maya = k02.place.author
    created = _create(k02, contract_id, _upgrade_body())
    path = f"{MODIFICATIONS}/{created['id']}"
    assert created["price_tests"] == {}
    figures = {"price": "60000", "low": "69750", "high": "85250", "ssp_version_key": "US-LIST@v1"}
    below = {
        "value": False,
        "reason_key": "modifications.prefill.priced_at_ssp.below_range",
        "params": figures,
    }

    # --- unanswered: the fact is the proposal's entry, and it is not among the proposals ---
    first = _classify(k02, created["id"])
    assert first["price_tests"] == {"O2": below}
    assert first["prefill_reasons"]["O2"]["priced_at_ssp"] == below
    assert sorted(first["prefill_reasons"]) == ["O1", "O2"]
    assert get(k02.app, path, maya).json()["price_tests"] == {"O2": below}

    # --- both answers stored: nothing is proposed for O2, and the price test is still stated ---
    stored = _patch(
        k02,
        created["id"],
        {"questionnaire": {"O2": {"added_goods_distinct": True, "priced_at_ssp": False}}},
    )
    assert (stored["price_tests"], stored["prefill_reasons"]) == ({}, {})  # an edit clears both
    assert get(k02.app, path, maya).json()["price_tests"] == {}
    second = _classify(k02, created["id"])
    assert sorted(second["prefill_reasons"]) == ["O1"]
    assert second["price_tests"] == {"O2": below}
    shown = get(k02.app, path, maya).json()
    assert (shown["price_tests"], shown["prefill_reasons"]) == (
        second["price_tests"],
        second["prefill_reasons"],
    )

    # --- answered true: the engine passes on the attestation; both figures are still there ---
    _patch(
        k02,
        created["id"],
        {"questionnaire": {"O2": {"added_goods_distinct": True, "priced_at_ssp": True}}},
    )
    third = _classify(k02, created["id"])
    assert third["price_tests"] == {
        "O2": {
            "value": True,
            "reason_key": "modifications.prefill.priced_at_ssp.attested",
            "params": figures,
        }
    }
    assert "O2" not in third["prefill_reasons"]
    assert get(k02.app, path, maya).json()["price_tests"] == third["price_tests"]


@pytest.mark.parametrize("key", ["proposal", "price_tests", "obligations"])
def test_mod_classification_keys_1_an_obligation_keyed_like_a_member_keeps_its_proposals(
    k02: K02World, key: str
) -> None:
    """Item MOD-CLASSIFICATION-KEYS-1 (the supervisor's ruling of 2026-10-02; 04 T-CON-06
    ``classification``, §16.14 rev 1.286). An obligation key is free text. Measured before, on
    this upgrade with its added line keyed ``proposal``: the line's two proposals were stored
    under ``proposal`` and the engine's detail was gone from the row; keyed ``price_tests``: the
    price tests took the place of the line's proposals, and no answer named the added
    obligation's questions again. The row keeps three members and no other — the obligations
    stand inside ``obligations`` and ``price_tests`` — and the answer carries the proposals of
    the obligations alone, with the engine's detail beside them as ``proposal_detail``. The
    third key is the new member's own name."""
    contract_id = _k02_contract(k02)
    maya = k02.place.author
    body = _upgrade_body()
    body["lines"][0]["obligation_key"] = key
    created = _create(k02, contract_id, body)
    path = f"{MODIFICATIONS}/{created['id']}"
    assert (created["prefill_reasons"], created["proposal_detail"], created["price_tests"]) == (
        {},
        {},
        {},
    )

    classified = _classify(k02, created["id"])
    reasons, detail = classified["prefill_reasons"], classified["proposal_detail"]
    tests = classified["price_tests"]
    assert classified["proposed_treatments"] == {"O1": "PROSPECTIVE", key: "PROSPECTIVE"}
    assert {name: sorted(questions) for name, questions in reasons.items()} == {
        "O1": ["remaining_goods_distinct_from_transferred"],
        key: ["added_goods_distinct", "priced_at_ssp"],
    }
    assert sorted(detail) == sorted(
        ["class[O1]", f"class[{key}]", "modification_key", f"ssp_version[{key}]"]
    )
    assert tests == {key: reasons[key]["priced_at_ssp"]}
    assert sorted(classified["questionnaire"][key]) == ["added_goods_distinct", "priced_at_ssp"]
    assert _row(k02, created["id"])["classification"] == {
        "proposal": detail,
        "obligations": reasons,
        "price_tests": tests,
    }
    shown = get(k02.app, path, maya).json()
    assert (shown["prefill_reasons"], shown["proposal_detail"], shown["price_tests"]) == (
        reasons,
        detail,
        tests,
    )


def test_mod_classification_keys_1_a_classification_stored_flat_reads_as_none(
    k02: K02World,
) -> None:
    """The rows that exist (the supervisor's ruling of 2026-10-02, by D-99 (3)): a row
    classified before the item holds the obligations' entries beside ``proposal`` and
    ``price_tests``. No revision rewrites a tenant's rows and there is no reader of two shapes:
    such a classification reads as none — ``prefill_reasons``, ``proposal_detail`` and
    ``price_tests`` empty — and nothing else of the row is read from it. The next ``/classify``
    writes the three members."""
    contract_id = _k02_contract(k02)
    maya = k02.place.author
    created = _create(k02, contract_id, _upgrade_body())
    path = f"{MODIFICATIONS}/{created['id']}"
    classified = _classify(k02, created["id"])
    reasons, detail = classified["prefill_reasons"], classified["proposal_detail"]
    tests = classified["price_tests"]
    assert sorted(reasons) == ["O1", "O2"] and list(tests) == ["O2"] and detail

    # The row as it was stored before the item, written past the commands.
    flat = {"proposal": detail, **reasons, "price_tests": tests}
    context = DbContext(tenant_id=k02.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(
            update(modification)
            .where(modification.c.id == UUID(created["id"]))
            .values(classification=flat)
        )
    assert _row(k02, created["id"])["classification"] == flat

    shown = get(k02.app, path, maya).json()
    assert (shown["prefill_reasons"], shown["proposal_detail"], shown["price_tests"]) == (
        {},
        {},
        {},
    )
    # the row's own columns are not read from the classification
    assert (shown["proposed_treatments"], shown["treatment_summary"], shown["ssp_basis"]) == (
        classified["proposed_treatments"],
        classified["treatment_summary"],
        classified["ssp_basis"],
    )

    again = _classify(k02, created["id"])
    assert (again["prefill_reasons"], again["proposal_detail"], again["price_tests"]) == (
        reasons,
        detail,
        tests,
    )
    assert _row(k02, created["id"])["classification"] == {
        "proposal": detail,
        "obligations": reasons,
        "price_tests": tests,
    }


def _net_revenue(summary: dict[str, Any]) -> Decimal:
    """Credit less debit of the summary's revenue journal lines."""
    return sum(
        (
            Decimal(line["credit"]["amount"]) - Decimal(line["debit"]["amount"])
            for line in summary["journal_lines"]
            if line["account_role"] == "REVENUE"
        ),
        Decimal(0),
    )


def test_mod_preview_journal_rule_1_the_lines_are_those_of_the_asking_day(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """Item MOD-PREVIEW-JOURNAL-RULE-1 (supervisor ruling R-119 (e) and the supervisor's ruling
    of 2026-10-01, way (A); 04 API-S-ImpactSummary rev 1.210; a fact of lane F-CTR-WEB's CTR-27).
    A preview's journal lines are the entries the approval would post if it computed at the
    preview's instant: the change's effect together with every period amount not posted yet. One
    K-02 draft, asked twice. In September the lines are September's change, 1,906.79. The clock
    passes into October and the period tick opens FY2026-P10: asked again, the SAME draft answers
    16,039.25 — October's whole 14,132.46 beside it, which any computation would post. The
    summary says when and for which period it was computed. The retained September preview does
    not go stale when the period opens, and the submission takes it: a stated property (04:
    recorded, not built otherwise). The warning's condition is the one a client evaluates — the
    entity's latest postable period is no longer the preview's."""
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    path = f"{MODIFICATIONS}/{created['id']}"
    _classify(k02, created["id"])
    asked = clock.now()
    september = _preview(k02, created["id"], runtime)["result"]["summary"]
    assert datetime.fromisoformat(september["computed_at"]) == asked
    assert september["computed_period_key"] == "FY2026-P09"
    assert _net_revenue(september) == Decimal("1906.79")
    kept = get(k02.app, path, k02.place.author).json()
    assert kept["impact_preview"]["computed_period_key"] == "FY2026-P09"
    retained = kept["impact_preview_sha256"]

    # --- the clock passes into October; the period tick opens the next period (05 SCH-05) ---
    clock.set(datetime(2026, 10, 1, 5, 0, tzinfo=UTC))  # 1 October, 01:00 in New York
    opened = period_auto_open.run(runtime, only_tenants=[k02.place.tenant_id])
    assert (opened.opened, opened.failed) == (1, 0)
    author = k02.place.author
    maya = signed_workspace(
        k02.app, author.member, sign_in(k02.app, author.member.email), author.secret
    )
    postable = [
        item["period"]["period_key"]
        for item in periods(k02.app, maya, entity="AVM-US")
        if item["state"] in ("open", "closing", "reopened")
    ]
    assert max(postable) == "FY2026-P10" != september["computed_period_key"]  # the warning

    # --- the retained preview is still the row's: nothing voided, and the submission takes it ---
    shown = get(k02.app, path, maya).json()
    assert shown["impact_preview_sha256"] == retained
    assert _net_revenue(shown["impact_preview"]) == Decimal("1906.79")
    submitted = post(k02.app, f"{path}/submit", maya, {"comment": None})
    assert submitted.status_code == 200, submitted.text
    assert (submitted.json()["status"], submitted.json()["impact_preview_sha256"]) == (
        "SUBMITTED",
        retained,
    )
    withdrawn = post(k02.app, f"{path}/withdraw", maya, {"comment": "Asked again in October."})
    assert withdrawn.status_code == 200, withdrawn.text

    # --- asked again, the same draft answers the lines of the new day ---
    queued = post(k02.app, f"{path}/preview", maya, {})
    assert queued.status_code == 202, queued.text
    _work(k02.place, UUID(queued.json()["id"]), runtime)
    october = get(k02.app, path, maya).json()["impact_preview"]
    assert october["computed_period_key"] == "FY2026-P10"
    assert datetime.fromisoformat(october["computed_at"]) == clock.now()
    whole_october = next(
        Decimal(row["after"]["amount"])
        for row in october["revenue_by_period"]
        if row["period_key"] == "FY2026-P10"
    )
    assert whole_october == Decimal("14132.46")
    assert _net_revenue(october) == Decimal("1906.79") + whole_october == Decimal("16039.25")
    assert (october["transaction_price_after"], october["catch_up_total"]) == (
        september["transaction_price_after"],
        september["catch_up_total"],
    )


# --- Item MOD-LINKED-ESTIMATES-1 (supervisor rulings R-118 (e), R-119 (e); 04 T-CON-13
# ``modification_id``, §16.10, §16.14 rev 1.210; PRD BR-MOD-02, ERR-83, ERR-87, ERR-88) -----------

ESTIMATES: Final = "/api/v1/estimates"
VERSIONS: Final = "/api/v1/estimate-versions"
REBATE: Final = "REBATE-MH-01"
BONUS: Final = "BONUS-MH-01"
NOT_APPROVED: Final = (
    "Estimate version REBATE-MH-01 v{n} of this modification is not approved. "
    "It is approved before the modification is submitted."
)


def _rebate(world: K02World, contract_id: UUID, code: str = REBATE) -> str:
    """A variable consideration element of the contract (most likely amount) — the rebate, or
    the bonus for ``BONUS``; its id. No test here holds two open versions of one element."""
    made = post(
        world.app,
        f"{CONTRACTS}/{contract_id}/estimates",
        world.place.author,
        {
            "estimate_kind": "VARIABLE_CONSIDERATION",
            "element_code": code,
            "vc_element_type": "BONUS" if code == BONUS else "REBATE",
            "method": "MOST_LIKELY_AMOUNT",
        },
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def _rebate_version(world: K02World, estimate_id: str, modification_id: str | None = None) -> Any:
    """``POST /estimates/{id}/versions``: nothing expected from the day of the change, created
    inside ``modification_id`` when one is given."""
    body: dict[str, Any] = {
        "effective_date": "2026-09-16",
        "scenarios": [{"outcome": "Threshold not expected", "amount": "0.00"}],
        "unconstrained_amount": "0.00",
        "most_conservative_amount": "0.00",
        "constrained_amount": "0.00",
        "rationale": "Nothing is expected at the seat count of the change.",
    }
    if modification_id is not None:
        body["modification_id"] = modification_id
    return post(world.app, f"{ESTIMATES}/{estimate_id}/versions", world.place.author, body)


def _version_submitted(world: K02World, version_id: str) -> str:
    """Submit a version of the rebate; the request id. The version is first given what its
    submission asks (04 §16.14 rev 1.241): its evidence and the reviewed ``CONSTRAINT`` record of
    ``REBATE-MH-01`` — a record of the version itself, whose review appends nothing to the
    contract (``worlds.estimate_version_ready``)."""
    estimate_version_ready(
        world.app, world.place.author, version_id, constraint_of=REBATE, reviewer=world.priya
    )
    sent = post(world.app, f"{VERSIONS}/{version_id}/submit", world.place.author, {"comment": "OK"})
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "SUBMITTED", sent.text
    return str(sent.json()["approval_request_id"])


def _named(response: Any) -> list[tuple[Any, Any, Any]]:
    """A 409 ``invalid-transition`` as its entries (field, rule id, message)."""
    assert (response.status_code, slug(response)) == (409, "invalid-transition"), response.text
    return [
        (error["field"], error["rule_id"], error["message"]) for error in response.json()["errors"]
    ]


def _linked(world: K02World, modification_id: str) -> list[tuple[Any, Any, Any]]:
    shown = get(world.app, f"{MODIFICATIONS}/{modification_id}", world.place.author)
    assert shown.status_code == 200, shown.text
    return [
        (item["element_code"], item["version_no"], item["status"])
        for item in shown.json()["linked_estimate_versions"]
    ]


def _version_statuses(world: K02World, estimate_id: str) -> dict[int, str]:
    rows = world.place.rows(
        select(estimate_version.c.version_no, estimate_version.c.status).where(
            estimate_version.c.estimate_id == UUID(estimate_id)
        )
    )
    return {int(row["version_no"]): str(row["status"]) for row in rows}


def test_mod_linked_estimates_1_a_version_is_created_inside_a_draft_modification(
    k02: K02World,
) -> None:
    """PRD BR-MOD-02 said "estimate versions created inside a modification are linked to it" and
    no column, member or route carried the link. ``POST /estimates/{id}/versions`` takes
    ``modification_id``: a DRAFT modification of the estimate's own contract, 422 otherwise.
    The version answers it, the modification lists it (``linked_estimate_versions``), the
    version list filters by it, and no command changes it. Both approvals certify the link: the
    version's content names its modification and the modification's content lists the ids — a
    subject without a link hashes as it did."""
    maya = k02.place.author
    contract_id = _k02_contract(k02)
    estimate_id = _rebate(k02, contract_id)
    created = _create(k02, contract_id, _upgrade_body())
    assert created["linked_estimate_versions"] == []

    made = _rebate_version(k02, estimate_id, created["id"])
    assert made.status_code == 201, made.text
    inside = made.json()
    assert (inside["modification_id"], inside["version_no"], inside["status"]) == (
        created["id"],
        1,
        "DRAFT",
    )
    plain = _rebate_version(k02, _rebate(k02, contract_id, BONUS))
    assert (plain.status_code, plain.json()["modification_id"]) == (201, None), plain.text
    outside = plain.json()

    shown = get(k02.app, f"{MODIFICATIONS}/{created['id']}", maya).json()
    assert shown["linked_estimate_versions"] == [
        {
            "id": inside["id"],
            "estimate_id": estimate_id,
            "element_code": REBATE,
            "estimate_kind": "VARIABLE_CONSIDERATION",
            "version_no": 1,
            "status": "DRAFT",
            "effective_date": "2026-09-16",
        }
    ]
    versions = f"{ESTIMATES}/{estimate_id}/versions"
    of_change = get(k02.app, versions, maya, {"modification_id": created["id"]})
    assert [item["id"] for item in of_change.json()["items"]] == [inside["id"]]
    assert get(k02.app, versions, maya, {"modification_id": str(uuid4())}).json()["items"] == []
    of_other = get(
        k02.app,
        f"{ESTIMATES}/{outside['estimate_id']}/versions",
        maya,
        {"modification_id": created["id"]},
    )
    assert of_other.json()["items"] == []  # the bonus version is not of the modification

    # no command changes the link
    moved = patch(
        k02.app,
        f"{VERSIONS}/{outside['id']}",
        maya,
        {"modification_id": created["id"]},
        if_match=None,
    )
    assert (moved.status_code, slug(moved)) == (422, "validation-failed"), moved.text
    assert [error["field"] for error in moved.json()["errors"]] == ["modification_id"]

    # what the two approvals certify (04 §16.10)
    context = DbContext(tenant_id=k02.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        linked = subjects.estimate_version_content(session, UUID(inside["id"]))
        unlinked = subjects.estimate_version_content(session, UUID(outside["id"]))
        (change,) = subjects.modification_content(session, UUID(created["id"]))["modifications"]
    assert linked["modification_id"] == created["id"]
    assert "modification_id" not in unlinked
    assert change["linked_estimate_version_ids"] == [inside["id"]]

    # refused: a modification that does not exist, one of another contract, one that is no draft
    def not_a_draft(modification_id: str) -> None:
        refused = _rebate_version(k02, estimate_id, modification_id)
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
        assert [
            (error["field"], error["rule_id"], error["message"])
            for error in refused.json()["errors"]
        ] == [("modification_id", "T-CON-13", "Choose a draft modification of this contract.")]

    not_a_draft(str(uuid4()))
    other_customer = customer_id(k02.app, maya, code="C-77", name="Pellworth Clinics LLC (Demo)")
    booked = booked_contract(
        k02.place,
        {**k02_seat_month_body(other_customer), "external_id": "SF-ORD-10777"},
        activate=False,
    )
    other_contract = UUID(str(activated_contract(k02.place, booked).contract["id"]))
    elsewhere = _create(k02, other_contract, _upgrade_body(reference="CR-PELLWORTH-2026-09"))
    assert "linked_estimate_version_ids" not in _content(k02, elsewhere["id"])
    not_a_draft(elsewhere["id"])
    dropped = _create(k02, contract_id, _upgrade_body(reference="CR-MARROWBY-2026-10"))
    assert _discard(k02, dropped["id"]).status_code == 200
    not_a_draft(dropped["id"])
    assert _version_statuses(k02, estimate_id) == {1: "DRAFT"}  # nothing was written


def _content(world: K02World, modification_id: str) -> dict[str, Any]:
    """The one row of a modification's §16.10 content."""
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        (item,) = subjects.modification_content(session, UUID(modification_id))["modifications"]
    return dict(item)


def test_mod_linked_estimates_1_the_versions_are_approved_before_the_modification(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """PRD SM-03 said "linked estimate versions and judgements approved in the same session". The
    kernel admits one order only. (1) The reason: the approval of an estimate version appends
    ``ESTIMATE_CHANGED``, which moves the head a modification's request pins — a modification
    that waits for its approval is stale by it. (2) So the versions created inside a
    modification are approved FIRST: ``/submit`` names each one that is not (PRD ERR-87) before
    it asks for anything else, and once they are approved the modification is previewed again —
    the basis of the stored preview moved with the head — submitted and approved. (3) A link
    written after the submission changes the content the request pins: the decision is stale. A
    discarded version does not count, in the check or in the content."""
    maya = k02.place.author
    contract_id = _k02_contract(k02)
    estimate_id = _rebate(k02, contract_id)
    created = _create(k02, contract_id, _upgrade_body())
    change = f"{MODIFICATIONS}/{created['id']}"

    # (1) a version outside the modification, approved while the modification waits
    first = _rebate_version(k02, estimate_id).json()
    first_request = _version_submitted(k02, first["id"])
    _classify(k02, created["id"])
    _preview(k02, created["id"], runtime)
    waiting = _submit(k02, created["id"])
    head = _head(k02, contract_id)
    clock.advance(timedelta(minutes=1))
    decided = approve(k02.app, first_request, k02.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert _head(k02, contract_id) == head + 1  # ESTIMATE_CHANGED
    late = approve(k02.app, waiting, k02.priya)
    assert (late.status_code, slug(late)) == (409, "stale-approval"), late.text
    request = get(k02.app, f"/api/v1/approvals/{waiting}", k02.priya).json()
    assert (request["status"], request["void_reason"]) == ("VOIDED", "STALE_SUBJECT")
    assert str(_row(k02, created["id"])["status"]) == "DRAFT"

    # (2) a version created inside the draft: named by the submission until it is approved
    made = _rebate_version(k02, estimate_id, created["id"])
    assert made.status_code == 201, made.text
    second = made.json()
    assert _linked(k02, created["id"]) == [(REBATE, 2, "DRAFT")]
    refused = post(k02.app, f"{change}/submit", maya, {"comment": "Too early."})
    assert _named(refused) == [(None, "SM-03", NOT_APPROVED.format(n=2))]
    second_request = _version_submitted(k02, second["id"])
    refused = post(k02.app, f"{change}/submit", maya, {"comment": "Still too early."})
    assert _named(refused) == [(None, "SM-03", NOT_APPROVED.format(n=2))]
    assert str(_row(k02, created["id"])["status"]) == "DRAFT"
    clock.advance(timedelta(minutes=1))
    decided = approve(k02.app, second_request, k02.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert _linked(k02, created["id"]) == [(REBATE, 2, "APPROVED")]
    # the stored preview was taken before the version's event: it is not of the row as it stands
    outdated = post(k02.app, f"{change}/submit", maya, {"comment": "Preview first."})
    assert (outdated.status_code, slug(outdated)) == (422, "validation-failed"), outdated.text
    assert [error["rule_id"] for error in outdated.json()["errors"]] == ["REQ-PLT-015"]
    _preview(k02, created["id"], runtime)
    request_id = _submit(k02, created["id"])
    assert _content(k02, created["id"])["linked_estimate_version_ids"] == [second["id"]]

    # (3) a link written past the commands after the submission: the request's content moved
    stray = estimate_version_values(
        k02.place.tenant_id,
        estimate_id=UUID(estimate_id),
        version_no=3,
        modification_id=UUID(created["id"]),
    )
    context = DbContext(tenant_id=k02.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(insert(estimate_version).values(**stray))
    clock.advance(timedelta(minutes=1))
    late = approve(k02.app, request_id, k02.priya)
    assert (late.status_code, slug(late)) == (409, "stale-approval"), late.text
    assert str(_row(k02, created["id"])["status"]) == "DRAFT"
    refused = post(k02.app, f"{change}/submit", maya, {"comment": "A stray draft."})
    assert _named(refused) == [(None, "SM-03", NOT_APPROVED.format(n=3))]
    gone = post(k02.app, f"{VERSIONS}/{stray['id']}/discard", maya, {})
    assert (gone.status_code, gone.json()["status"]) == (200, "VOIDED"), gone.text
    assert _linked(k02, created["id"]) == [(REBATE, 2, "APPROVED"), (REBATE, 3, "VOIDED")]

    # every linked version that counts is approved, and the content — which is the preview's
    # basis too — lists what it listed: the retained preview stands and the submission takes it
    assert _content(k02, created["id"])["linked_estimate_version_ids"] == [second["id"]]
    request_id = _submit(k02, created["id"])
    clock.advance(timedelta(minutes=1))
    decided = approve(k02.app, request_id, k02.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert str(_row(k02, created["id"])["status"]) == "APPLIED"
    assert _version_statuses(k02, estimate_id) == {1: "SUPERSEDED", 2: "APPROVED", 3: "VOIDED"}


def test_mod_linked_estimates_1_a_discard_waits_for_a_submitted_version(k02: K02World) -> None:
    """The discard of a draft modification leaves no request to be decided for a voided
    modification: it answers 409 naming a linked estimate version that is waiting for approval
    (PRD ERR-83) and nothing is written. Linked versions that are DRAFT or WITHDRAWN go with the
    modification — they stay as they are — and their own submission then answers 409 naming the
    modification (PRD ERR-88). Such a draft is discarded like any other, and the element is
    changed by a version outside the modification."""
    maya = k02.place.author
    contract_id = _k02_contract(k02)
    estimate_id = _rebate(k02, contract_id)
    created = _create(k02, contract_id, _upgrade_body())
    first = _rebate_version(k02, estimate_id, created["id"]).json()
    request_id = _version_submitted(k02, first["id"])

    held = _discard(k02, created["id"])
    assert _named(held) == [
        (
            None,
            "SM-03",
            "Estimate version REBATE-MH-01 v1 of this modification is waiting for approval. "
            "Its preparer withdraws it first.",
        )
    ]
    assert str(_row(k02, created["id"])["status"]) == "DRAFT"
    assert _discard_audits(k02, created["id"]) == []
    pending = get(k02.app, f"/api/v1/approvals/{request_id}", k02.priya).json()
    assert pending["status"] == "PENDING"

    withdrawn = post(k02.app, f"{VERSIONS}/{first['id']}/withdraw", maya, {"comment": "Not yet."})
    assert (withdrawn.status_code, withdrawn.json()["status"]) == (200, "WITHDRAWN"), withdrawn.text
    bonus_id = _rebate(k02, contract_id, BONUS)
    second = _rebate_version(k02, bonus_id, created["id"]).json()
    gone = _discard(k02, created["id"])
    assert (gone.status_code, gone.json()["status"]) == (200, "VOIDED"), gone.text
    # the linked versions are not rewritten
    assert _version_statuses(k02, estimate_id) == {1: "WITHDRAWN"}
    assert _version_statuses(k02, bonus_id) == {1: "DRAFT"}
    assert _linked(k02, created["id"]) == [(BONUS, 1, "DRAFT"), (REBATE, 1, "WITHDRAWN")]

    discarded = (
        None,
        "SM-04",
        f"Modification {created['modification_no']} of this estimate version was discarded. "
        "The version cannot be submitted.",
    )
    sent = post(k02.app, f"{VERSIONS}/{second['id']}/submit", maya, {"comment": "OK"})
    assert _named(sent) == [discarded]
    # the withdrawn one is a draft again by an edit, and then answers the same
    revised = patch(
        k02.app,
        f"{VERSIONS}/{first['id']}",
        maya,
        {"rationale": "Revised after the withdrawal."},
        if_match=None,
    )
    assert (revised.status_code, revised.json()["status"]) == (200, "DRAFT"), revised.text
    sent = post(k02.app, f"{VERSIONS}/{first['id']}/submit", maya, {"comment": "OK"})
    assert _named(sent) == [discarded]
    assert _version_statuses(k02, estimate_id) == {1: "DRAFT"}

    # such a draft is discarded like any other; the element goes on outside the modification
    for version in (first, second):
        dropped = post(k02.app, f"{VERSIONS}/{version['id']}/discard", maya, {})
        assert (dropped.status_code, dropped.json()["status"]) == (200, "VOIDED"), dropped.text
    later = _rebate_version(k02, estimate_id).json()
    assert (later["version_no"], later["modification_id"]) == (2, None)
    _version_submitted(k02, later["id"])


# --- PRD J-06 in the built order (PRD rev 1.158; the supervisor's word of 2026-10-01) ------------

J06_REVENUE_ACCOUNT: Final = "4010"
J06_LIABILITY_ACCOUNT: Final = "2100"


def _j06_money(value: Any) -> str:
    return str(value["amount"])


def _j06_september(summary: dict[str, Any]) -> tuple[str, str]:
    (row,) = [item for item in summary["revenue_by_period"] if item["period_key"] == "FY2026-P09"]
    return _j06_money(row["before"]), _j06_money(row["after"])


def _j06_lines(summary: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Account code → (debit, credit) of the summary's journal lines."""
    return {
        str(line["gl_account"]["code"]): (_j06_money(line["debit"]), _j06_money(line["credit"]))
        for line in summary["journal_lines"]
    }


def _j06_version_preview(world: K03World, version_id: str) -> dict[str, Any]:
    queued = post(world.app, f"{VERSIONS}/{version_id}/preview", world.report.maya, {})
    assert queued.status_code == 202, queued.text
    finished = run_now(world.report, UUID(str(queued.json()["id"])))
    assert finished["state"] == "SUCCEEDED", finished
    return dict(finished["result"]["summary"])


def _j06_approved(world: K03World, version_id: str, clock: FrozenClock) -> None:
    """Maya submits the version and its request is approved: by Priya and — where the request is
    routed the Controller's second step, for a P&L impact of USD 50,000.00 or more (PRD §2.5
    routing row ``ESTIMATE_VERSION``; the request then carries the flag ``PL_IMPACT_GE_50K``) —
    by Marcus. The steps of the request are exactly those its flags route. Before the submission
    Maya attaches the version's evidence (04 §16.14 rev 1.241); the bonus version names the
    journey's own ``CONSTRAINT`` record, which is reviewed before it is submitted."""
    estimate_version_ready(world.app, world.report.maya, version_id)
    sent = post(world.app, f"{VERSIONS}/{version_id}/submit", world.report.maya, {"comment": "OK"})
    assert sent.status_code == 200, sent.text
    request_id = str(sent.json()["approval_request_id"])
    clock.advance(timedelta(seconds=20))
    decided = approve(world.app, request_id, world.report.priya)
    assert decided.status_code == 200, decided.text
    second_step = "PL_IMPACT_GE_50K" in decided.json()["flags"]
    assert len(decided.json()["steps"]) == (2 if second_step else 1), decided.text
    if second_step:
        assert decided.json()["status"] == "PENDING", decided.text
        clock.advance(timedelta(seconds=20))
        decided = approve(world.app, request_id, world.report.marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text


def test_j_06_the_change_order_and_its_linked_versions_in_the_built_order(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """PRD J-06.1 to J-06.6 (rev 1.158) on WLD-K-03 through the product's commands. The journey
    said: one preview of 91,463.41 for the change order with its two estimate versions, one
    submission routing four requests, one bulk approval. The kernel admits another order
    (04 §16.10, §16.14 rev 1.210): the versions created inside the draft modification are
    approved first, each posting at its own approval — the estimate of total costs reverses
    87,804.88, the bonus adds 102,439.03 — and the modification's preview then states the
    catch-up of its date, 91,463.41, with entries of 76,829.26 for what the two versions have
    not posted. The end is WLD-X-10: 691,463.41."""
    world = k03_castellan(app, keyring, clock, files)
    maya, priya, marcus = world.report.maya, world.report.priya, world.report.marcus
    step = timedelta(seconds=20)  # inside the approvers' MFA window (BR-PLT-06)
    assert k03_revenue(world.report.place, world.group_id) == Decimal("600000.00")  # WLD-X-09

    # J-06.1 — the draft modification with two linked draft versions and one draft record
    clock.advance(step)
    created = post(
        app,
        f"{CONTRACTS}/{world.contract_id}/modifications",
        maya,
        {
            "effective_date": "2026-09-10",
            "kind": "PRICE_CHANGE",
            "reference": "CR-CASTELLAN-2026-09",
            "lines": [
                {
                    "obligation_key": "O1",
                    "action": "CHANGE",
                    "consideration_delta": {"amount": "150000.00", "currency": "USD"},
                }
            ],
            "rationale": "Floor plan change (change order CO-07)",
        },
    )
    assert created.status_code == 201, created.text
    change_id = str(created.json()["id"])
    change = f"{MODIFICATIONS}/{change_id}"
    eac = post(
        app,
        f"{ESTIMATES}/{world.eac_id}/versions",
        maya,
        {
            "effective_date": "2026-09-10",
            "expected_total_amount": "820000.00",
            "rationale": "Change order CO-07 adds 120,000.00 of cost",
            "modification_id": change_id,
        },
    )
    assert eac.status_code == 201, eac.text
    record = post(
        app,
        "/api/v1/judgements",
        maya,
        {
            "topic": "CONSTRAINT",
            "subject_type": "modification",
            "subject_id": change_id,
            "conclusion": (
                "Completion within the extended 30-month window is highly likely; no "
                "significant reversal expected."
            ),
            "rationale": "Schedule review of change order CO-07.",
            "codification_refs": ["606-10-32-11", "606-10-32-12"],
            "questionnaire": {"estimate_key": "BONUS-CB-01", "remote": True},
        },
    )
    assert record.status_code == 201, record.text
    bonus = post(
        app,
        f"{ESTIMATES}/{world.bonus_id}/versions",
        maya,
        {
            "effective_date": "2026-09-10",
            "scenarios": [
                {"outcome": "Completion bonus earned", "amount": "200000.00"},
                {"outcome": "Not earned", "amount": "0.00"},
            ],
            "unconstrained_amount": "200000.00",
            "most_conservative_amount": "0.00",
            "constrained_amount": "200000.00",
            "rationale": "Completion within the extended window is highly likely.",
            "judgement_record_id": record.json()["id"],
            "modification_id": change_id,
        },
    )
    assert bonus.status_code == 201, bonus.text
    eac_v2, bonus_v2 = str(eac.json()["id"]), str(bonus.json()["id"])
    shown = get(app, change, maya).json()
    assert [
        (item["element_code"], item["version_no"], item["status"])
        for item in shown["linked_estimate_versions"]
    ] == [("BONUS-CB-01", 2, "DRAFT"), ("EAC", 2, "DRAFT")]
    early = post(app, f"{change}/submit", maya, {"comment": "Too early."})
    assert [message for _, _, message in _named(early)] == [
        "Estimate version BONUS-CB-01 v2 of this modification is not approved. "
        "It is approved before the modification is submitted.",
        "Estimate version EAC v2 of this modification is not approved. "
        "It is approved before the modification is submitted.",
    ]

    # J-06.2 — the one question of a change without an added line
    classified = post(app, f"{change}/classify", maya, {})
    assert classified.status_code == 200, classified.text
    assert classified.json()["treatment_summary"] == "CUMULATIVE_CATCH_UP"
    assert classified.json()["questionnaire"] == {
        "O1": {"remaining_goods_distinct_from_transferred": False}
    }
    reason = classified.json()["prefill_reasons"]["O1"]["remaining_goods_distinct_from_transferred"]
    assert reason["params"] == {"progress": "0.6", "progress_measure": "COST_TO_COST"}

    # J-06.3 — EAC version 2: its preview is what its approval posts
    read = get(app, f"{VERSIONS}/{eac_v2}", maya).json()
    assert _j06_money(read["costs_incurred_to_date"]) == "420000.00"
    assert Decimal(read["progress_ratio"]).quantize(Decimal("0.001")) == Decimal("0.512")
    clock.advance(step)
    preview = _j06_version_preview(world, eac_v2)
    assert (
        _j06_money(preview["transaction_price_before"]),
        _j06_money(preview["transaction_price_after"]),
        _j06_money(preview["catch_up_total"]),
        _j06_september(preview),
    ) == ("1000000.00", "1000000.00", "-87804.88", ("0.00", "-87804.88"))
    assert _j06_lines(preview) == {
        J06_REVENUE_ACCOUNT: ("87804.88", "0.00"),
        J06_LIABILITY_ACCOUNT: ("0.00", "87804.88"),
    }
    _j06_approved(world, eac_v2, clock)
    assert k03_revenue(world.report.place, world.group_id) == Decimal("512195.12")

    # J-06.4 — the record reviewed, then bonus version 2
    clock.advance(step)
    sent = post(app, f"/api/v1/judgements/{record.json()['id']}/submit", maya, {"comment": "OK"})
    assert sent.status_code == 200, sent.text
    reviewed = approve(app, str(sent.json()["approval_request_id"]), priya)
    assert (reviewed.status_code, reviewed.json()["status"]) == (200, "APPROVED"), reviewed.text
    clock.advance(step)
    preview = _j06_version_preview(world, bonus_v2)
    assert (
        _j06_money(preview["transaction_price_before"]),
        _j06_money(preview["transaction_price_after"]),
        _j06_money(preview["catch_up_total"]),
        _j06_september(preview),
    ) == ("1000000.00", "1200000.00", "102439.03", ("-87804.88", "14634.15"))
    assert _j06_lines(preview) == {
        J06_LIABILITY_ACCOUNT: ("102439.03", "0.00"),
        J06_REVENUE_ACCOUNT: ("0.00", "102439.03"),
    }
    _j06_approved(world, bonus_v2, clock)
    assert k03_revenue(world.report.place, world.group_id) == Decimal("614634.15")

    # J-06.5 — the modification: the catch-up of its date, and the entries for what is left
    clock.advance(step)
    queued = post(app, f"{change}/preview", maya, {})
    assert queued.status_code == 202, queued.text
    finished = run_now(world.report, UUID(str(queued.json()["id"])))
    assert finished["state"] == "SUCCEEDED", finished
    preview = dict(finished["result"]["summary"])
    assert (
        _j06_money(preview["transaction_price_before"]),
        _j06_money(preview["transaction_price_after"]),
        _j06_money(preview["catch_up_total"]),
        _j06_september(preview),
    ) == ("1200000.00", "1350000.00", "91463.41", ("14634.15", "91463.41"))
    assert _j06_lines(preview) == {
        J06_LIABILITY_ACCOUNT: ("76829.26", "0.00"),
        J06_REVENUE_ACCOUNT: ("0.00", "76829.26"),
    }
    submitted = post(app, f"{change}/submit", maya, {"comment": "Approve change order CO-07."})
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    clock.advance(step)
    first = approve(app, request_id, priya)
    assert (first.status_code, first.json()["status"], first.json()["current_step_no"]) == (
        200,
        "PENDING",
        2,
    ), first.text
    assert len(first.json()["steps"]) == 2  # the catch-up is at least USD 50,000.00

    # J-06.6 — step 2: applied, WLD-X-10
    clock.advance(step)
    second = approve(app, request_id, marcus)
    assert (second.status_code, second.json()["status"]) == (200, "APPROVED"), second.text
    assert k03_revenue(world.report.place, world.group_id) == Decimal("691463.41")
    applied = get(app, change, maya).json()
    assert applied["status"] == "APPLIED"
    assert [
        (item["element_code"], item["version_no"], item["status"])
        for item in applied["linked_estimate_versions"]
    ] == [("BONUS-CB-01", 2, "APPROVED"), ("EAC", 2, "APPROVED")]


# --- Item MOD-REJECTED-REVISE-1 (the supervisor's ruling of 2026-10-01; PRD SM-03 "Revise";
# 04 §16.14 rev 1.236) ------------------------------------------------------------------------


def _rejected(
    world: K02World, contract_id: UUID, runtime: JobRuntime, clock: FrozenClock
) -> tuple[dict[str, Any], str]:
    """The Marrowby seat add of K-02, submitted and rejected by Priya: the row as created and
    the id of its request."""
    created = _create(world, contract_id, _upgrade_body())
    _classify(world, created["id"])
    _preview(world, created["id"], runtime)
    request_id = _submit(world, created["id"])
    clock.advance(timedelta(minutes=1))
    rejected = reject(world.app, request_id, world.priya, "The order form names 40 seats.")
    assert rejected.status_code == 200, rejected.text
    assert str(_row(world, created["id"])["status"]) == "REJECTED"
    return created, request_id


def _update_audits(world: K02World, modification_id: str) -> list[tuple[Any, Any]]:
    rows = world.place.rows(
        select(audit_event.c.before, audit_event.c.after)
        .where(
            audit_event.c.object_type == "modification",
            audit_event.c.object_id == UUID(modification_id),
            audit_event.c.action == "modification.update",
        )
        .order_by(audit_event.c.chain_seq)
    )
    return [(row["before"], row["after"]) for row in rows]


def test_mod_rejected_revise_1_a_rejected_modification_is_revised_and_approved(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """Item MOD-REJECTED-REVISE-1 (the supervisor's ruling of 2026-10-01; PRD SM-03 REJECTED →
    DRAFT "Revise"; 04 §16.14 rev 1.236). Measured before: a rejected change order was a dead
    end — ``PATCH`` answered 409, the discard answered 409, and its reference stayed taken, so
    the order could not be entered again either. ``PATCH /modifications/{id}`` now admits a
    REJECTED row: the edit returns it to DRAFT, resets what every edit resets and says so in
    its audit event; the rejected request stays closed. Classified and previewed again, the
    revision is submitted — a new request, the same reference — approved and applied."""
    maya = k02.place.author
    contract_id = _k02_contract(k02)
    created, first_request = _rejected(k02, contract_id, runtime, clock)
    change = f"{MODIFICATIONS}/{created['id']}"

    revised = _patch(
        k02, created["id"], {"rationale": "Marrowby adds 50 seats: the order form of 12 September."}
    )
    assert (revised["status"], revised["reference"]) == ("DRAFT", REFERENCE)
    row = _row(k02, created["id"])
    assert (
        row["proposed_treatments"],
        row["classification"],
        row["impact_preview_sha256"],
        row["content_sha256"],
    ) == ({}, None, None, None)
    assert str(row["approval_request_id"]) == first_request  # the request's history stays
    assert _update_audits(k02, created["id"]) == [
        (
            {"status": "REJECTED"},
            {
                "status": "DRAFT",
                "rationale": "Marrowby adds 50 seats: the order form of 12 September.",
            },
        )
    ]
    closed = get(k02.app, f"/api/v1/approvals/{first_request}", maya).json()
    assert closed["status"] == "REJECTED"
    early = post(k02.app, f"{change}/submit", maya, {"comment": "Again."})
    assert early.status_code == 422, early.text  # an edit asks for a new classification

    _classify(k02, created["id"])
    _preview(k02, created["id"], runtime)
    second_request = _submit(k02, created["id"])
    assert second_request != first_request
    assert get(k02.app, f"/api/v1/approvals/{first_request}", maya).json()["status"] == "REJECTED"
    clock.advance(timedelta(minutes=1))
    decided = approve(k02.app, second_request, k02.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    applied = _row(k02, created["id"])
    assert (str(applied["status"]), applied["reference"]) == ("APPLIED", REFERENCE)
    (amended,) = _events(k02, contract_id, ContractEventType.CONTRACT_AMENDED)
    assert amended["payload"]["modification_id"] == created["id"]
    assert amended["approval_request_id"] == UUID(second_request)


def test_mod_rejected_revise_1_a_revised_draft_that_is_given_up_frees_its_reference(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """Item MOD-REJECTED-REVISE-1, the other way out. A REJECTED modification holds its reference
    and is not discarded as it stands — only a draft is. Revised, it is a draft: discarded, it
    frees the reference, and the change order is entered again under it. The contract is not
    touched by any of it."""
    maya = k02.place.author
    contract_id = _k02_contract(k02)
    head = _head(k02, contract_id)
    created, _ = _rejected(k02, contract_id, runtime, clock)

    taken = post(k02.app, f"{CONTRACTS}/{contract_id}/modifications", maya, _upgrade_body())
    assert taken.status_code == 422, taken.text
    assert taken.json()["errors"][0]["rule_id"] == "ux_modification__reference"
    as_rejected = _discard(k02, created["id"])
    assert (as_rejected.status_code, slug(as_rejected)) == (409, "invalid-transition")
    assert as_rejected.json()["errors"][0]["message"] == NOT_DISCARDABLE

    revised = _patch(k02, created["id"], {"rationale": "Entered with the wrong seat count."})
    assert revised["status"] == "DRAFT"
    discarded = _discard(k02, created["id"])
    assert (discarded.status_code, discarded.json()["status"]) == (200, "VOIDED"), discarded.text
    again = post(k02.app, f"{CONTRACTS}/{contract_id}/modifications", maya, _upgrade_body())
    assert again.status_code == 201, again.text
    assert again.json()["reference"] == REFERENCE
    assert _head(k02, contract_id) == head


def test_mod_rejected_revise_1_the_rows_of_a_rejected_pair_return_to_draft_together(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Item MOD-REJECTED-REVISE-1 for the pair of a regroup after posting (one ``regroup_id``,
    ONE spanning request; D-98 140 Q-4): it was submitted and rejected as one, and half a pair
    can be neither submitted nor discarded. Release 1.0 makes no such pair any more (04 §16.1
    rev 1.234), so the two REJECTED rows are placed here as rows — the revision stands for the
    pairs that exist. The edit of either row returns both to DRAFT, each with its own audit
    event, and the pair is then discarded whole."""
    owner = member(keyring, clock, name="tomas")
    tenant_id = owner.tenant_id
    regroup_id = uuid4()
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        insert_role_assignment(
            session,
            tenant_id=tenant_id,
            membership_id=owner.membership_id,
            role_code="revenue_accountant",
        )
        chains = [insert_contract_rows(session, tenant_id) for _ in range(2)]
        rows = [
            modification_values(
                tenant_id,
                contract_id=chain.contract_id,
                contracting_entity_id=chain.entity_id,
                regroup_id=regroup_id,
                status="REJECTED",
            )
            for chain in chains
        ]
        session.execute(insert(modification), rows)
    tomas = enrolled(app, clock, owner)
    first, second = (str(row["id"]) for row in rows)

    shown = get(app, f"{MODIFICATIONS}/{first}", tomas)
    assert (shown.status_code, shown.json()["status"]) == (200, "REJECTED"), shown.text
    revised = patch(
        app,
        f"{MODIFICATIONS}/{first}",
        tomas,
        {"rationale": "The split is entered again."},
        if_match=shown.headers["ETag"],
    )
    assert (revised.status_code, revised.json()["status"]) == (200, "DRAFT"), revised.text

    def stored(*columns: Any) -> dict[str, tuple[Any, ...]]:
        with tenant_session(context) as session:
            found = session.execute(
                select(modification.c.id, *columns).where(modification.c.regroup_id == regroup_id)
            ).all()
        return {str(row[0]): tuple(row[1:]) for row in found}

    assert stored(modification.c.status) == {first: ("DRAFT",), second: ("DRAFT",)}
    with tenant_session(context) as session:
        audited = session.execute(
            select(audit_event.c.object_id, audit_event.c.before, audit_event.c.after).where(
                audit_event.c.object_type == "modification",
                audit_event.c.action == "modification.update",
                audit_event.c.object_id.in_([UUID(first), UUID(second)]),
            )
        ).all()
    assert sorted((str(row[0]), row[1], row[2]) for row in audited) == sorted(
        [
            (
                first,
                {"status": "REJECTED"},
                {"status": "DRAFT", "rationale": "The split is entered again."},
            ),
            (second, {"status": "REJECTED"}, {"status": "DRAFT"}),
        ]
    )

    discarded = post(app, f"{MODIFICATIONS}/{second}/discard", tomas, {})
    assert (discarded.status_code, discarded.json()["status"]) == (200, "VOIDED"), discarded.text
    assert stored(modification.c.status) == {first: ("VOIDED",), second: ("VOIDED",)}


# --- the judgement records of a modification (item MOD-LINKED-JUDGEMENTS-1) ----------------------

RECORD_NOT_REVIEWED: Final = (
    "Judgement record {no} of this modification is not reviewed. It is reviewed, or discarded, "
    "before the modification is submitted."
)
RECORD_NOT_REVIEWED_AT_APPROVAL: Final = (
    "Judgement record {no} of this modification is not reviewed. The modification is approved "
    "after it."
)
JUDGEMENTS: Final = "/api/v1/judgements"


def _mod_record(world: K02World, modification_id: str) -> dict[str, Any]:
    """A DRAFT judgement record Maya prepares whose subject is the modification."""
    created = post(
        world.app,
        JUDGEMENTS,
        world.place.author,
        {
            "topic": "OTHER",
            "subject_type": "modification",
            "subject_id": modification_id,
            "conclusion": "The added seats are priced within the range of the list.",
            "rationale": "Compared with the approved list of 2026-H1.",
        },
    )
    assert created.status_code == 201, created.text
    return dict(created.json())


def _record_sent(world: K02World, record_id: str) -> str:
    """The record sent for review; its request id."""
    sent = post(world.app, f"{JUDGEMENTS}/{record_id}/submit", world.place.author, {})
    assert (sent.status_code, sent.json()["status"]) == (200, "SUBMITTED"), sent.text
    return str(sent.json()["approval_request_id"])


def test_mod_linked_judgements_1_the_records_are_reviewed_before_the_modification(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """Item MOD-LINKED-JUDGEMENTS-1 (the supervisor's ruling of 2026-10-01; PRD SM-03, ERR-95; 04
    §16.14 rev 1.242). Measured before: a modification was submitted, approved and applied
    beside a judgement record of its own that waited for review, and the record's review then
    answered 409 ``stale-approval`` — the applied event had moved the head its request pins, so
    a record that waits can never be reviewed once its modification is applied. A record whose
    subject is the modification is therefore reviewed, or discarded, FIRST: ``/submit`` names
    each one that is DRAFT or SUBMITTED, in number order, and the approval asks the same of a
    record added since. A rejected record holds nothing, and neither does a discarded one; a
    record that is reviewed while the modification waits leaves the modification's request
    fresh."""
    maya = k02.place.author
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    change = f"{MODIFICATIONS}/{created['id']}"
    _classify(k02, created["id"])
    _preview(k02, created["id"], runtime)

    def held(response: Any, template: str, *records: dict[str, Any]) -> None:
        assert _named(response) == [
            (None, "SM-03", template.format(no=record["judgement_no"])) for record in records
        ]

    # --- a draft record of the modification: named by the submission ---
    first = _mod_record(k02, created["id"])
    held(
        post(k02.app, f"{change}/submit", maya, {"comment": "Too early."}),
        RECORD_NOT_REVIEWED,
        first,
    )

    # --- sent for review it is still named, beside a second draft: one entry a record ---
    first_request = _record_sent(k02, first["id"])
    second = _mod_record(k02, created["id"])
    held(
        post(k02.app, f"{change}/submit", maya, {"comment": "Still too early."}),
        RECORD_NOT_REVIEWED,
        first,
        second,
    )
    assert str(_row(k02, created["id"])["status"]) == "DRAFT"

    # --- the first is reviewed; a third, rejected, holds nothing; the second is discarded ---
    clock.advance(timedelta(minutes=1))
    reviewed = approve(k02.app, first_request, k02.priya)
    assert (reviewed.status_code, reviewed.json()["status"]) == (200, "APPROVED"), reviewed.text
    third = _mod_record(k02, created["id"])
    rejected = reject(k02.app, _record_sent(k02, third["id"]), k02.priya, "Not needed.")
    assert rejected.status_code == 200, rejected.text
    held(
        post(k02.app, f"{change}/submit", maya, {"comment": "One left."}),
        RECORD_NOT_REVIEWED,
        second,
    )
    gone = post(k02.app, f"{JUDGEMENTS}/{second['id']}/discard", maya, {})
    assert (gone.status_code, gone.json()["status"]) == (200, "VOIDED"), gone.text
    request_id = _submit(k02, created["id"])

    # --- a record added after the submission: the approval is the backstop ---
    late = _mod_record(k02, created["id"])
    clock.advance(timedelta(minutes=1))
    held(approve(k02.app, request_id, k02.priya), RECORD_NOT_REVIEWED_AT_APPROVAL, late)
    late_request = _record_sent(k02, late["id"])
    held(approve(k02.app, request_id, k02.priya), RECORD_NOT_REVIEWED_AT_APPROVAL, late)
    assert str(_row(k02, created["id"])["status"]) == "SUBMITTED"

    # --- reviewed beside the waiting modification, it leaves the request fresh: applied ---
    done = approve(k02.app, late_request, k02.priya)
    assert (done.status_code, done.json()["status"]) == (200, "APPROVED"), done.text
    decided = approve(k02.app, request_id, k02.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert str(_row(k02, created["id"])["status"]) == "APPLIED"


def test_mod_linked_judgements_1_a_departure_without_its_reviewed_record_still_answers_err_54(
    k02: K02World, runtime: JobRuntime
) -> None:
    """The records of a modification are asked BEHIND the row's own findings (04 §16.14 rev
    1.242). A departure from the proposed treatment whose ``MODIFICATION_TREATMENT_OVERRIDE``
    record is still a draft answers 422 ``REQ-MOD-002`` (PRD ERR-54), which names the treatment
    and what it needs — not the 409 of PRD ERR-95, which the same draft would otherwise meet."""
    maya = k02.place.author
    contract_id = _k02_contract(k02)
    created = _create(k02, contract_id, _upgrade_body())
    _classify(k02, created["id"])
    _patch(
        k02,
        created["id"],
        {"chosen_treatments": {"O1": "CUMULATIVE_CATCH_UP", "O2": "PROSPECTIVE"}},
    )
    _classify(k02, created["id"])  # the edit invalidated the classification; re-proposed
    _preview(k02, created["id"], runtime)
    conclusion = "Catch-up: the added seats are not distinct in substance."
    drafted = post(
        k02.app,
        JUDGEMENTS,
        maya,
        {
            "topic": "MODIFICATION_TREATMENT_OVERRIDE",
            "subject_type": "modification",
            "subject_id": created["id"],
            "conclusion": conclusion,
            "questionnaire": {"conclusion": conclusion},
            "rationale": "To be reviewed with the revenue reviewer.",
        },
    )
    assert (drafted.status_code, drafted.json()["status"]) == (201, "DRAFT"), drafted.text
    refused = post(k02.app, f"{MODIFICATIONS}/{created['id']}/submit", maya, {"comment": "x"})
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert [(error["rule_id"], error["field"]) for error in refused.json()["errors"]] == [
        ("REQ-MOD-002", "chosen_treatments.O1")
    ]
    assert str(_row(k02, created["id"])["status"]) == "DRAFT"
