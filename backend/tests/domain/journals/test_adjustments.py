"""CLO-12 manual adjustments (04 T-SL-05, E-93, E-94, §15.3 API-R-37, §16.14 "API-R-37 shapes";
PRD SM-10, §2.5 routing rows ``MANUAL_ADJUSTMENT``, BR-CLS-04, WLD-B-02, J-13.2; ENGINE_SPEC_B
S09-R-38, S14-R-09a; 03 REQ-JE-019, REQ-REC-023, REQ-CLS-003; CTL-014, CTL-015; BUILD_SPEC CLO-12;
supervisor ruling R-51).

World: ``support.worlds.k01_pellworth`` — AVM-US (USD) with WLD-K-01 ``SF-ORD-10001`` booked,
activated, billed and computed through September 2026 (O1 AVM-PLAT-ENT allocated 118,800.00 over
2026, daily: September 9,764.38, WLD-X-02). Maya (Revenue Accountant) prepares; Priya holds
Revenue Reviewer here beside SSP Approver and approves; Marcus is the Controller. Everything is
built and decided through the product's routes.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    approval_request,
    approval_step,
    contract_event,
    event_submission,
    gl_account,
    job,
    legal_entity,
    manual_adjustment,
    role,
    subledger_line,
    subledger_posting,
)
from erev_api.domain.close import gates
from erev_api.domain.platform import file_evidence
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support import upload_fixtures
from support.close_world import periods_closed_before
from support.db import TestDatabase
from support.factories import computed
from support.http import HttpResponse, call
from support.principals import Actor, colleague, cookie_headers, enrolled
from support.reference import (
    APPROVALS,
    approve,
    assign,
    entity,
    fields,
    get,
    patch,
    post,
    reject,
    slug,
)
from support.shred_in_flight import beside_a_shred
from support.worlds import (
    JOURNAL_RUNS,
    K01,
    SEPTEMBER_2026,
    ReportWorld,
    journal_run,
    k01_pellworth,
    run_now,
)

ADJUSTMENTS: Final = "/api/v1/manual-adjustments"
SCHEDULE_LINES: Final = "/api/v1/schedule-lines"
ATTACHMENTS: Final = "/api/v1/attachments"
FILES: Final = "/api/v1/files"
PERIODS: Final = "/api/v1/periods"
OCTOBER_2026: Final = "FY2026-P10"
BOOK: Final = "ASC606"
# WLD-X-02 / WLD-X-03: O1's allocated 118,800.00 over 365 days; cumulative 79,091.51 at 31 Aug,
# 88,855.89 at 30 Sep and 98,945.75 at 31 Oct 2026.
SEPTEMBER_REVENUE: Final = "9764.38"
OCTOBER_REVENUE: Final = "10089.86"
RELEASE: Final = "2400.00"
REJECTION: Final = "Attach the customer acceptance before resubmitting."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> ReportWorld:
    built = k01_pellworth(app, keyring, clock, files)
    # PRD §5.6: ``adjustment.approve`` is the Revenue Reviewer's and the Controller's.
    assign(built.priya.member, "revenue_reviewer")
    return built


def _usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def _contract_id(world: ReportWorld) -> str:
    return str(world.contracts[K01].contract["id"])


def _group_id(world: ReportWorld) -> UUID:
    return UUID(str(world.contracts[K01].combination_group["id"]))


def _obligation_id(world: ReportWorld, key: str = "O1") -> str:
    (found,) = [item for item in world.contracts[K01].obligations if item["obligation_key"] == key]
    return str(found["id"])


def _body(world: ReportWorld, kind: str, payload: Mapping[str, Any], **over: Any) -> dict[str, Any]:
    return {
        "kind": kind,
        "contract_id": _contract_id(world),
        "effective_date": "2026-09-12",
        "reason_code": "ESTIMATE_CORRECTION",
        "memo": "Customer accepted phase 2 on 12 Sep 2026",
        "payload": dict(payload),
        **over,
    }


def _release(world: ReportWorld, amount: str = RELEASE, **over: Any) -> dict[str, Any]:
    payload = {"obligation_id": _obligation_id(world), "amount": _usd(amount)}
    return _body(world, "MANUAL_RELEASE", payload, **over)


def _created(
    world: ReportWorld, body: Mapping[str, Any], actor: Actor | None = None
) -> dict[str, Any]:
    created = post(world.app, ADJUSTMENTS, actor or world.maya, dict(body))
    assert created.status_code == 201, created.text
    found: dict[str, Any] = created.json()
    assert created.headers["Location"] == f"{ADJUSTMENTS}/{found['id']}"
    assert created.headers["ETag"] == f'"r{found["row_version"]}"'
    return found


def _submitted(
    world: ReportWorld, adjustment_id: str, actor: Actor | None = None
) -> dict[str, Any]:
    submitted = post(world.app, f"{ADJUSTMENTS}/{adjustment_id}/submit", actor or world.maya, {})
    assert submitted.status_code == 200, submitted.text
    found: dict[str, Any] = submitted.json()
    return found


def _shown(world: ReportWorld, adjustment_id: str, actor: Actor | None = None) -> dict[str, Any]:
    shown = get(world.app, f"{ADJUSTMENTS}/{adjustment_id}", actor or world.maya)
    assert shown.status_code == 200, shown.text
    found: dict[str, Any] = shown.json()
    return found


def _request(world: ReportWorld, request_id: str, actor: Actor) -> dict[str, Any]:
    detail = get(world.app, f"{APPROVALS}/{request_id}", actor)
    assert detail.status_code == 200, detail.text
    found: dict[str, Any] = detail.json()
    return found


def _revenue(world: ReportWorld, *periods: str, obligation: str = "O1") -> dict[str, str]:
    """The obligation's revenue by period key in the latest version (``GET /schedule-lines``)."""
    listed = get(
        world.app,
        SCHEDULE_LINES,
        world.maya,
        {
            "contract": _contract_id(world),
            "schedule_kind": "REVENUE",
            "obligation": obligation,
            "from_period": min(periods),
            "to_period": max(periods),
            "limit": "200",
        },
    )
    assert listed.status_code == 200, listed.text
    totals: dict[str, Decimal] = {}
    for item in listed.json()["items"]:
        key = item["period"]["period_key"]
        totals[key] = totals.get(key, Decimal(0)) + Decimal(item["amount"]["amount"])
    return {key: f"{totals.get(key, Decimal(0)):.2f}" for key in periods}


def _events(
    world: ReportWorld, event_type: str = "MANUAL_ADJUSTMENT_APPLIED"
) -> list[dict[str, Any]]:
    return world.place.rows(
        select(contract_event)
        .where(
            contract_event.c.contract_id == UUID(_contract_id(world)),
            contract_event.c.event_type == event_type,
        )
        .order_by(contract_event.c.stream_version)
    )


def _ledger(world: ReportWorld) -> tuple[int, Decimal]:
    """(line count, Σ|functional amount|) of the contract's sealed subledger lines."""
    (row,) = world.place.rows(
        select(
            func.count().label("lines"),
            func.coalesce(func.sum(func.abs(subledger_line.c.amount_functional)), 0).label("total"),
        ).where(subledger_line.c.contract_id == UUID(_contract_id(world)))
    )
    return int(row["lines"]), Decimal(row["total"])


def test_manual_release_one_step_and_survives_recompute(world: ReportWorld) -> None:
    """BUILD_SPEC CLO-12 / REQ-REC-023: a ``MANUAL_RELEASE`` of USD 2,400.00 with reason code and
    memo routes ONE ``adjustment.approve`` step (PRD §2.5, below USD 10,000.00); its approval
    appends ``MANUAL_ADJUSTMENT_APPLIED`` (``applied_event_id`` set, status ``POSTED``); and the
    released amount stays in the period through two recomputations of the group."""
    assert _revenue(world, SEPTEMBER_2026, OCTOBER_2026) == {
        SEPTEMBER_2026: SEPTEMBER_REVENUE,
        OCTOBER_2026: OCTOBER_REVENUE,
    }
    created = _created(world, _release(world))
    assert (created["status"], created["kind"], created["adjustment_no"]) == (
        "DRAFT",
        "MANUAL_RELEASE",
        "ADJ-000001",
    )
    assert created["amount_functional_abs"] == _usd(RELEASE)  # derived by the dry run, never sent
    assert (created["period"]["period_key"], created["entity"]["code"], created["book"]) == (
        SEPTEMBER_2026,
        "AVM-US",
        BOOK,
    )
    assert (created["reason_code"], created["currency"]) == ("ESTIMATE_CORRECTION", "USD")
    assert created["obligation"]["obligation_key"] == "O1"
    # a draft changes nothing: no event, the schedule as it was
    assert _events(world) == [] and _revenue(world, SEPTEMBER_2026)[SEPTEMBER_2026] == "9764.38"

    submitted = _submitted(world, created["id"])
    assert submitted["status"] == "SUBMITTED" and submitted["content_sha256"]
    assert submitted["pending_request"] == {
        "id": submitted["approval_request_id"],
        "purpose": "POSTING",
    }
    request = _request(world, submitted["approval_request_id"], world.priya)
    assert [
        (step["step_no"], step["required_permission"], step["status"]) for step in request["steps"]
    ] == [(1, "adjustment.approve", "ACTIVE")]
    assert (request["amount"], request["flags"], request["entity"]["code"]) == (
        _usd(RELEASE),
        [],
        "AVM-US",
    )
    assert request["subject"]["type"] == "MANUAL_ADJUSTMENT"
    assert request["subject"]["content_sha256"] == submitted["content_sha256"]
    # the approver reads the dry run: September 9,764.38 -> 12,164.38
    preview = request["impact_preview"]["summary"]
    before = {item["period_key"]: item["amount"] for item in preview["revenue_by_period_before"]}
    after = {item["period_key"]: item["amount"] for item in preview["revenue_by_period_after"]}
    assert (before[SEPTEMBER_2026]["amount"], after[SEPTEMBER_2026]["amount"]) == (
        "9764.38",
        "12164.38",
    )
    # pending: no balance moves (REQ-JE-019)
    assert _events(world) == [] and _revenue(world, SEPTEMBER_2026)[SEPTEMBER_2026] == "9764.38"

    decided = approve(world.app, submitted["approval_request_id"], world.priya)
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "APPROVED"
    posted = _shown(world, created["id"])
    assert (posted["status"], posted["subledger_posting_id"], posted["pending_request"]) == (
        "POSTED",
        None,
        None,
    )
    [event] = _events(world)
    assert posted["applied_event_id"] == str(event["id"])
    assert event["payload"] == {"manual_adjustment_id": created["id"]}
    assert str(event["manual_adjustment_id"]) == created["id"]
    assert str(event["approval_request_id"]) == submitted["approval_request_id"]
    assert (str(event["origin"]), event["effective_date"].isoformat()) == ("SYSTEM", "2026-09-12")
    # S09-R-38: min(A, max(C(t), C(P) + m)) — September carries the release, October absorbs it
    released = {SEPTEMBER_2026: "12164.38", OCTOBER_2026: "7689.86"}
    assert _revenue(world, SEPTEMBER_2026, OCTOBER_2026) == released

    ledger = _ledger(world)
    for _ in range(2):
        world.place.clock.advance(timedelta(minutes=1))
        computed(world.place, _group_id(world))
        assert _revenue(world, SEPTEMBER_2026, OCTOBER_2026) == released
    assert _ledger(world) == ledger  # and the recomputations post nothing further
    assert _shown(world, created["id"])["status"] == "POSTED"


def test_preview_is_a_dry_run_job_of_the_contract_and_writes_nothing(world: ReportWorld) -> None:
    """04 §16.14 "API-R-37 shapes": ``POST /manual-adjustments/{id}/preview`` answers 202
    API-S-Job (``CONTRACT_COMPUTE``) whose ``result.summary`` is API-S-ImpactSummary of the group
    with the adjustment applied, and writes nothing. The job works on the adjustment's contract:
    T-PLT-27 ``subject_type`` admits a fixed list that does not name the adjustment, and with the
    adjustment as its subject the route answered 500 on ``ck_job__subject_type``."""
    adjustment = _created(world, _release(world))
    untouched = (_events(world), _ledger(world), _revenue(world, SEPTEMBER_2026, OCTOBER_2026))
    started = post(world.app, f"{ADJUSTMENTS}/{adjustment['id']}/preview", world.maya, {})
    assert started.status_code == 202, started.text
    queued = started.json()
    assert (queued["kind"], queued["state"]) == ("CONTRACT_COMPUTE", "QUEUED")
    assert started.headers["Location"] == f"/api/v1/jobs/{queued['id']}"
    [stored] = world.place.rows(
        select(job.c.subject_type, job.c.subject_id, job.c.params).where(
            job.c.id == UUID(queued["id"])
        )
    )
    assert (stored["subject_type"], str(stored["subject_id"])) == ("contract", _contract_id(world))
    # the params name the adjustment (the worker also stamps its release on a compute job)
    assert (stored["params"]["mode"], stored["params"]["manual_adjustment_id"]) == (
        "ADJUSTMENT_PREVIEW",
        adjustment["id"],
    )

    finished = run_now(world, UUID(queued["id"]))
    assert finished["state"] == "SUCCEEDED", finished
    assert finished["result"]["href"] == f"{ADJUSTMENTS}/{adjustment['id']}"
    by_period = {
        item["period_key"]: (
            item["before"]["amount"],
            item["after"]["amount"],
            item["change"]["amount"],
        )
        for item in finished["result"]["summary"]["revenue_by_period"]
    }
    # S09-R-38: September carries the release, October absorbs it
    assert by_period[SEPTEMBER_2026] == (SEPTEMBER_REVENUE, "12164.38", RELEASE)
    assert by_period[OCTOBER_2026] == (OCTOBER_REVENUE, "7689.86", f"-{RELEASE}")
    # a preview is a dry run: no event, no posting, the schedule and the adjustment as they were
    assert (
        _events(world),
        _ledger(world),
        _revenue(world, SEPTEMBER_2026, OCTOBER_2026),
    ) == untouched
    assert _shown(world, adjustment["id"])["status"] == "DRAFT"
    # a posted adjustment has nothing left to preview
    submitted = _submitted(world, adjustment["id"])
    assert approve(world.app, submitted["approval_request_id"], world.priya).status_code == 200
    late = post(world.app, f"{ADJUSTMENTS}/{adjustment['id']}/preview", world.maya, {})
    assert (late.status_code, slug(late)) == (409, "invalid-transition"), late.text


def _person(world: ReportWorld, clock: FrozenClock, name: str, *roles: str) -> Actor:
    """A colleague of the workspace holding ``roles``, signed in with a confirmed TOTP factor."""
    someone = colleague(world.tenant_id, name)
    for code in roles:
        assign(someone, code)
    return enrolled(world.app, clock, someone)


def _attached(world: ReportWorld, actor: Actor, adjustment_id: str) -> dict[str, Any]:
    """``POST /files`` (purpose ATTACHMENT), then ``POST /attachments`` on the adjustment."""
    uploaded = call(
        world.app,
        "POST",
        FILES,
        data={"purpose": "ATTACHMENT"},
        files={"file": ("customer-acceptance.pdf", upload_fixtures.PDF, "application/pdf")},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    attached = post(
        world.app,
        ATTACHMENTS,
        actor,
        {
            "file_object_id": uploaded.json()["id"],
            "subject_type": "manual_adjustment",
            "subject_id": adjustment_id,
            "description": "Customer acceptance",
        },
    )
    assert attached.status_code == 201, attached.text
    found: dict[str, Any] = attached.json()
    return found


def _september(world: ReportWorld, actor: Actor | None = None) -> dict[str, Any]:
    listed = get(world.app, PERIODS, actor or world.maya, {"entity": "AVM-US", "limit": 200})
    assert listed.status_code == 200, listed.text
    (found,) = [
        item for item in listed.json()["items"] if item["period"]["period_key"] == SEPTEMBER_2026
    ]
    return dict(found)


def _override(world: ReportWorld, amount: str, **over: Any) -> dict[str, Any]:
    """A ``SCHEDULE_OVERRIDE`` of O1 that sets September's revenue to ``amount``."""
    payload = {
        "obligation_id": _obligation_id(world),
        "periods": [{"period_id": _september(world)["period"]["id"], "amount": _usd(amount)}],
    }
    return _body(world, "SCHEDULE_OVERRIDE", payload, **over)


def _gates(world: ReportWorld) -> dict[str, gates.GateResult]:
    period_id = UUID(str(_september(world)["period"]["id"]))
    with world.place.uow() as uow:
        results = gates.evaluate_gates(uow, world.entity_id, BOOK, period_id)
        uow.commit()
    return {result.gate_check_code: result for result in results}


def _adjustment_requests(world: ReportWorld) -> list[dict[str, Any]]:
    """Every approval request of subject MANUAL_ADJUSTMENT (the world holds requests of other
    subjects from its set-up)."""
    return world.place.rows(
        select(approval_request).where(approval_request.c.subject_type == "MANUAL_ADJUSTMENT")
    )


def _steps(world: ReportWorld, request_id: str) -> list[tuple[int, str, str, str | None]]:
    """(step no, permission, status, required role code) of a request's steps."""
    rows = world.place.rows(
        select(
            approval_step.c.step_no,
            approval_step.c.required_permission,
            approval_step.c.status,
            role.c.code,
        )
        .select_from(
            approval_step.outerjoin(
                role,
                (role.c.tenant_id == approval_step.c.tenant_id)
                & (role.c.id == approval_step.c.required_role_id),
            )
        )
        .where(approval_step.c.approval_request_id == UUID(request_id))
        .order_by(approval_step.c.step_no)
    )
    return [
        (
            int(row["step_no"]),
            str(row["required_permission"]),
            str(row["status"]),
            None if row["code"] is None else str(row["code"]),
        )
        for row in rows
    ]


def test_threshold_two_steps_and_attachment(world: ReportWorld, clock: FrozenClock) -> None:
    """BUILD_SPEC CLO-12 / PRD §2.5 rows ``MANUAL_ADJUSTMENT``: a ``SCHEDULE_OVERRIDE`` whose
    ``amount_functional_abs`` is USD 10,000.00 is refused at submit without an attachment (422
    ``validation-failed`` naming ``attachments``); with one it routes TWO ``adjustment.approve``
    steps, the second held by a Controller."""
    # September of O1 is 9,764.38: an override to 19,764.38 changes it by exactly 10,000.00
    created = _created(world, _override(world, "19764.38"))
    assert created["amount_functional_abs"] == _usd("10000.00")
    assert created["attachment_count"] == 0
    refused = post(world.app, f"{ADJUSTMENTS}/{created['id']}/submit", world.maya, {})
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("attachments", "PRD-2.5")]
    assert refused.json()["errors"][0]["message"] == (
        "Attach supporting evidence: adjustments of USD 10,000.00 or more need an attachment."
    )
    assert _shown(world, created["id"])["status"] == "DRAFT"
    assert _adjustment_requests(world) == []

    _attached(world, world.maya, created["id"])
    submitted = _submitted(world, created["id"])
    assert (submitted["status"], submitted["attachment_count"]) == ("SUBMITTED", 1)
    request_id = submitted["approval_request_id"]
    request = _request(world, request_id, world.priya)
    assert (request["amount"], request["flags"]) == (_usd("10000.00"), ["ABOVE_THRESHOLD"])
    assert _steps(world, request_id) == [
        (1, "adjustment.approve", "ACTIVE", None),
        (2, "adjustment.approve", "WAITING", "controller"),
    ]
    first = approve(world.app, request_id, world.priya)
    assert first.status_code == 200, first.text
    assert (first.json()["status"], first.json()["current_step_no"]) == ("PENDING", 2)
    assert _shown(world, created["id"])["status"] == "SUBMITTED"
    # the second step is a Controller's: another Revenue Reviewer holds the permission, not the role
    rhea = _person(world, clock, "rhea", "revenue_reviewer")
    not_controller = approve(world.app, request_id, rhea)
    assert (not_controller.status_code, slug(not_controller)) == (403, "forbidden"), (
        not_controller.text
    )
    assert "Controller" in not_controller.json()["detail"]
    second = approve(world.app, request_id, world.marcus)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "APPROVED"
    posted = _shown(world, created["id"])
    assert posted["status"] == "POSTED" and posted["applied_event_id"]
    assert _revenue(world, SEPTEMBER_2026)[SEPTEMBER_2026] == "19764.38"


@pytest.mark.control("CTL-014")
def test_ctl_014_self_approval_blocked(world: ReportWorld, clock: FrozenClock) -> None:
    """CTL-014 (REQ-JE-019, REQ-PLT-011): the preparer of a manual adjustment cannot decide it, even
    holding ``adjustment.approve`` — 403 ``self-approval``, no decision recorded, nothing posted;
    another approver's decision posts it, and the request keeps preparer and approver apart."""
    dana = _person(world, clock, "dana", "revenue_accountant", "revenue_reviewer")
    created = _created(world, _release(world), dana)
    submitted = _submitted(world, created["id"], dana)
    request_id = submitted["approval_request_id"]
    own = approve(world.app, request_id, dana)
    assert (own.status_code, slug(own)) == (403, "self-approval"), own.text
    assert own.json()["detail"] == "You prepared this item, so another user must approve it."
    rejected = reject(world.app, request_id, dana, "Not needed after all.")
    assert (rejected.status_code, slug(rejected)) == (403, "self-approval"), rejected.text
    request = _request(world, request_id, world.priya)
    assert (request["status"], request["steps"][0]["decisions"]) == ("PENDING", [])
    assert _shown(world, created["id"])["status"] == "SUBMITTED" and _events(world) == []
    assert _revenue(world, SEPTEMBER_2026)[SEPTEMBER_2026] == SEPTEMBER_REVENUE

    decided = approve(world.app, request_id, world.priya)
    assert decided.status_code == 200, decided.text
    request = _request(world, request_id, world.priya)
    [decision] = request["steps"][0]["decisions"]
    assert request["preparer"]["id"] == str(dana.member.user_id)
    assert decision["approver"]["id"] == str(world.priya.member.user_id)
    assert _shown(world, created["id"])["status"] == "POSTED"


def _start_close(world: ReportWorld, actor: Actor) -> dict[str, Any]:
    september = _september(world, actor)
    started = post(
        world.app,
        f"{PERIODS}/{september['id']}/start-close",
        actor,
        {"comment": "September close in progress"},
        if_match=f'"r{september["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    moved: dict[str, Any] = started.json()
    assert moved["state"] == "closing"
    return moved


def _lock_refusal(world: ReportWorld) -> list[str]:
    """The gate codes that refuse ``POST /periods/{id}/request-lock`` now."""
    september = _september(world, world.marcus)
    refused = post(
        world.app,
        f"{PERIODS}/{september['id']}/request-lock",
        world.marcus,
        {"certification_comment": "September 2026 close complete"},
        if_match=f'"r{september["row_version"]}"',
    )
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    return [str(error["rule_id"]) for error in refused.json()["errors"]]


def test_pending_adjustment_blocks_lock_until_deferred(world: ReportWorld) -> None:
    """BUILD_SPEC CLO-12 / REQ-JE-019: a ``SUBMITTED`` adjustment of the period makes
    ``MANUAL_ADJUSTMENTS_CLEARED`` ``FAILED`` (count 1) and changes no balance; an approved
    ``request-defer-past-lock`` sets ``is_deferred_past_lock = true`` and the gate ``PASSED`` — the
    adjustment then holds neither that gate nor ``APPROVALS_CLEARED`` (ruling R-51 (c))."""
    clear = _gates(world)
    assert (
        clear["MANUAL_ADJUSTMENTS_CLEARED"].status.value,
        clear["MANUAL_ADJUSTMENTS_CLEARED"].count,
    ) == (
        "PASSED",
        0,
    )
    ledger = _ledger(world)
    created = _created(world, _release(world))
    drafted = _gates(world)["MANUAL_ADJUSTMENTS_CLEARED"]  # a draft is pending too
    assert (drafted.status.value, drafted.count) == ("FAILED", 1)
    submitted = _submitted(world, created["id"])
    posting_request = submitted["approval_request_id"]
    pending = _gates(world)
    failed = pending["MANUAL_ADJUSTMENTS_CLEARED"]
    assert (failed.status.value, failed.count, failed.detail) == (
        "FAILED",
        1,
        "Manual adjustments pending: 1",
    )
    assert (pending["APPROVALS_CLEARED"].status.value, pending["APPROVALS_CLEARED"].count) == (
        "FAILED",
        1,
    )
    assert _ledger(world) == ledger and _events(world) == []
    assert _revenue(world, SEPTEMBER_2026)[SEPTEMBER_2026] == SEPTEMBER_REVENUE

    # PRD BR-CLS-08 (supervisor ruling R-6): the lock is chronological and its order answers
    # before the gates, so January to August are closed first — fixture state of the order
    # rule, nothing of the subject.
    periods_closed_before(
        world.place, world.app, world.maya, entity_id=world.entity_id, before=SEPTEMBER_2026
    )
    _start_close(world, world.marcus)
    blocking = _lock_refusal(world)
    assert "MANUAL_ADJUSTMENTS_CLEARED" in blocking and "APPROVALS_CLEARED" in blocking

    # the deferral is asked by a holder of ``adjustment.create`` or of ``period.lock`` for the
    # entity: Priya (Revenue Reviewer) holds neither, Marcus (Controller) the second
    not_priya = post(
        world.app,
        f"{ADJUSTMENTS}/{created['id']}/request-defer-past-lock",
        world.priya,
        {"comment": "Customer acceptance arrives in October"},
    )
    assert (not_priya.status_code, slug(not_priya)) == (403, "forbidden"), not_priya.text
    unexplained = post(
        world.app, f"{ADJUSTMENTS}/{created['id']}/request-defer-past-lock", world.marcus, {}
    )
    assert (unexplained.status_code, slug(unexplained)) == (422, "validation-failed")
    assert fields(unexplained) == [("comment", None)]  # the reason of a deferral is required
    asked = post(
        world.app,
        f"{ADJUSTMENTS}/{created['id']}/request-defer-past-lock",
        world.marcus,
        {"comment": "Customer acceptance arrives in October"},
    )
    assert asked.status_code == 200, asked.text
    deferral = asked.json()
    assert (deferral["status"], deferral["is_deferred_past_lock"]) == ("SUBMITTED", False)
    assert deferral["approval_request_id"] != posting_request
    assert deferral["pending_request"] == {
        "id": deferral["approval_request_id"],
        "purpose": "DEFER_PAST_LOCK",
    }
    replaced = _request(world, posting_request, world.priya)
    assert (replaced["status"], replaced["void_reason"]) == ("VOIDED", "SUBJECT_VOIDED")
    request = _request(world, deferral["approval_request_id"], world.priya)
    assert (request["flags"], request["status"], request["summary"]) == (
        ["DEFER_PAST_LOCK"],
        "PENDING",
        "Defer past lock: manual release ADJ-000001 of SF-ORD-10001",
    )
    assert [step["required_permission"] for step in request["steps"]] == ["adjustment.approve"]
    waiting = _gates(world)  # a requested deferral defers nothing yet
    assert waiting["MANUAL_ADJUSTMENTS_CLEARED"].count == 1
    assert waiting["APPROVALS_CLEARED"].count == 1

    decided = approve(world.app, deferral["approval_request_id"], world.priya)
    assert decided.status_code == 200, decided.text
    deferred = _shown(world, created["id"])
    assert (deferred["status"], deferred["is_deferred_past_lock"], deferred["pending_request"]) == (
        "SUBMITTED",
        True,
        None,
    )
    assert deferred["applied_event_id"] is None
    passed = _gates(world)
    cleared = passed["MANUAL_ADJUSTMENTS_CLEARED"]
    assert (cleared.status.value, cleared.count, cleared.detail) == ("PASSED", 0, None)
    assert (passed["APPROVALS_CLEARED"].status.value, passed["APPROVALS_CLEARED"].count) == (
        "PASSED",
        0,
    )
    remaining = _lock_refusal(world)
    assert "MANUAL_ADJUSTMENTS_CLEARED" not in remaining and "APPROVALS_CLEARED" not in remaining
    # deferred, not posted: still no balance moved
    assert _ledger(world) == ledger and _events(world) == []
    assert _revenue(world, SEPTEMBER_2026)[SEPTEMBER_2026] == SEPTEMBER_REVENUE

    # a deferred adjustment is not deferred twice
    twice = post(
        world.app,
        f"{ADJUSTMENTS}/{created['id']}/request-defer-past-lock",
        world.marcus,
        {"comment": "Again"},
    )
    assert (twice.status_code, slug(twice)) == (409, "invalid-transition"), twice.text
    # a later submit routes it for posting (ruling R-51 (c)); in soft close by a lock holder. The
    # deferral stands: the adjustment does not count, its pending request does
    routed = _submitted(world, created["id"], world.marcus)
    assert (routed["status"], routed["is_deferred_past_lock"]) == ("SUBMITTED", True)
    assert routed["pending_request"] == {"id": routed["approval_request_id"], "purpose": "POSTING"}
    assert routed["approval_request_id"] not in (posting_request, deferral["approval_request_id"])
    assert routed["content_sha256"] != submitted["content_sha256"]  # hashed as it is now
    holding = _gates(world)
    assert holding["MANUAL_ADJUSTMENTS_CLEARED"].count == 0
    assert holding["APPROVALS_CLEARED"].count == 1
    final = approve(world.app, routed["approval_request_id"], world.priya)
    assert final.status_code == 200, final.text
    posted = _shown(world, created["id"])
    assert posted["status"] == "POSTED" and posted["applied_event_id"]
    assert _revenue(world, SEPTEMBER_2026)[SEPTEMBER_2026] == "12164.38"


def test_rejection_changes_nothing(world: ReportWorld) -> None:
    """BUILD_SPEC CLO-12 / PRD WLD-B-02, J-13.2: a schedule override of USD 2,400.00 prepared by
    ``maya`` without an attachment is rejected by ``priya`` with "Attach the customer acceptance
    before resubmitting." — status ``REJECTED``; schedules and subledger are unchanged."""
    ledger = _ledger(world)
    schedule = _revenue(world, SEPTEMBER_2026, OCTOBER_2026)
    created = _created(world, _override(world, "12164.38", reason_code="DATA_CORRECTION"))
    assert created["amount_functional_abs"] == _usd("2400.00")
    submitted = _submitted(world, created["id"])
    refused = reject(world.app, submitted["approval_request_id"], world.priya, REJECTION)
    assert refused.status_code == 200, refused.text
    assert refused.json()["status"] == "REJECTED"
    rejected = _shown(world, created["id"])
    assert (rejected["status"], rejected["applied_event_id"], rejected["subledger_posting_id"]) == (
        "REJECTED",
        None,
        None,
    )
    request = _request(world, submitted["approval_request_id"], world.maya)
    [decision] = request["steps"][0]["decisions"]
    assert (decision["decision"], decision["comment"]) == ("REJECT", REJECTION)
    assert _events(world) == [] and _ledger(world) == ledger
    assert _revenue(world, SEPTEMBER_2026, OCTOBER_2026) == schedule
    gate = _gates(world)["MANUAL_ADJUSTMENTS_CLEARED"]
    assert (gate.status.value, gate.count) == ("PASSED", 0)  # a rejected adjustment is not pending

    # PRD SM-10 (rev 1.49; ruling R-51 (b)): revise and resubmit — a PATCH returns it to DRAFT
    revised = patch(
        world.app,
        f"{ADJUSTMENTS}/{created['id']}",
        world.maya,
        {"memo": "Customer acceptance attached"},
        if_match=f'"r{rejected["row_version"]}"',
    )
    assert revised.status_code == 200, revised.text
    assert (revised.json()["status"], revised.json()["memo"]) == (
        "DRAFT",
        "Customer acceptance attached",
    )
    again = _submitted(world, created["id"])
    assert again["approval_request_id"] != submitted["approval_request_id"]


def _account_ids(world: ReportWorld) -> dict[str, str]:
    return {str(row["code"]): str(row["id"]) for row in world.place.rows(select(gl_account))}


def _journal(world: ReportWorld, debit: str, credit: str) -> dict[str, Any]:
    """A ``MANUAL_JOURNAL`` on O1: Dr deferred revenue 2100 / Cr revenue 4010 (the AVM-US chart)."""
    accounts = _account_ids(world)
    payload = {
        "obligation_id": _obligation_id(world),
        "lines": [
            {
                "account_role": "CONTRACT_LIABILITY",
                "gl_account_id": accounts["2100"],
                "amount_txn": _usd(debit),
            },
            {
                "account_role": "REVENUE",
                "gl_account_id": accounts["4010"],
                "amount_txn": _usd(f"-{credit}"),
            },
        ],
    }
    return _body(world, "MANUAL_JOURNAL", payload, reason_code="DATA_CORRECTION")


def _manual_lines(world: ReportWorld) -> list[tuple[str, str, Decimal, str]]:
    """(role, account code, signed functional amount, posting kind) of the contract's sealed lines
    of entry kind ``MANUAL_ADJUSTMENT``."""
    rows = world.place.rows(
        select(
            subledger_line.c.account_role,
            gl_account.c.code,
            subledger_line.c.amount_functional,
            subledger_posting.c.posting_kind,
        )
        .select_from(
            subledger_line.join(
                gl_account,
                (gl_account.c.tenant_id == subledger_line.c.tenant_id)
                & (gl_account.c.id == subledger_line.c.gl_account_id),
            ).join(
                subledger_posting,
                (subledger_posting.c.tenant_id == subledger_line.c.tenant_id)
                & (subledger_posting.c.id == subledger_line.c.subledger_posting_id),
            )
        )
        .where(
            subledger_line.c.contract_id == UUID(_contract_id(world)),
            subledger_line.c.entry_kind == "MANUAL_ADJUSTMENT",
        )
    )
    return sorted(
        (
            str(row["account_role"]),
            str(row["code"]),
            Decimal(row["amount_functional"]),
            str(row["posting_kind"]),
        )
        for row in rows
    )


def _manual_subjects(world: ReportWorld) -> set[str | None]:
    """The stored subject keys of the contract's sealed lines of entry kind
    ``MANUAL_ADJUSTMENT`` (04 T-SL-04 ``subject_key`` rev 1.282)."""
    rows = world.place.rows(
        select(subledger_line.c.subject_key)
        .where(
            subledger_line.c.contract_id == UUID(_contract_id(world)),
            subledger_line.c.entry_kind == "MANUAL_ADJUSTMENT",
        )
        .distinct()
    )
    return {row["subject_key"] for row in rows}


def test_manual_journal_lines_must_balance(world: ReportWorld) -> None:
    """BUILD_SPEC CLO-12: ``MANUAL_JOURNAL`` lines Dr 2,400.00 / Cr 2,399.99 return 422
    ``ledger-unbalanced``; balanced lines post a ``subledger_posting`` whose journal entries carry
    ``je_type = manual``. Ruling R-51 (a): a recomputation over the posted adjustment emits
    nothing — the approved lines are stage 14 role targets (ENGINE_SPEC_B S14-R-09a)."""
    unbalanced = post(world.app, ADJUSTMENTS, world.maya, _journal(world, "2400.00", "2399.99"))
    assert (unbalanced.status_code, slug(unbalanced)) == (422, "ledger-unbalanced"), unbalanced.text
    assert unbalanced.json()["detail"] == (
        "The lines do not balance: debits 2400.00 and credits 2399.99 differ by 0.01 USD."
    )
    assert world.place.rows(select(manual_adjustment)) == []

    created = _created(world, _journal(world, "2400.00", "2400.00"))
    assert created["amount_functional_abs"] == _usd("2400.00")  # the debit total
    submitted = _submitted(world, created["id"])
    request = _request(world, submitted["approval_request_id"], world.priya)
    lines = request["impact_preview"]["summary"]["journal_lines"]
    assert [
        (
            line["account_role"],
            line["gl_account"]["code"],
            line["debit"]["amount"],
            line["credit"]["amount"],
        )
        for line in lines
    ] == [
        ("CONTRACT_LIABILITY", "2100", "2400.00", "0.00"),
        ("REVENUE", "4010", "0.00", "2400.00"),
    ]
    assert _manual_lines(world) == []  # pending: nothing posted
    before = _ledger(world)
    decided = approve(world.app, submitted["approval_request_id"], world.priya)
    assert decided.status_code == 200, decided.text
    posted = _shown(world, created["id"])
    assert posted["status"] == "POSTED" and posted["applied_event_id"]
    [posting] = world.place.rows(
        select(subledger_posting).where(
            subledger_posting.c.id == UUID(posted["subledger_posting_id"])
        )
    )
    assert (str(posting["posting_kind"]), str(posting["manual_adjustment_id"])) == (
        "MANUAL_ADJUSTMENT",
        created["id"],
    )
    assert posting["idempotency_key"] == f"adjustment:{created['id']}"
    approved_lines = [
        ("CONTRACT_LIABILITY", "2100", Decimal("2400.00"), "MANUAL_ADJUSTMENT"),
        ("REVENUE", "4010", Decimal("-2400.00"), "MANUAL_ADJUSTMENT"),
    ]
    assert _manual_lines(world) == approved_lines
    # 04 T-SL-04 ``subject_key`` (rev 1.282): the lines store the obligation's subject, the key
    # of the adjustment's role target (S14-R-09a)
    assert _manual_subjects(world) == {f"{K01}/O1"}
    # exactly the two approved lines were added: the approval's own computation emitted nothing
    assert _ledger(world) == (before[0] + 2, before[1] + Decimal("4800.00"))

    # R-51 (a): recomputations over the posted adjustment neither reverse nor repeat it
    after = _ledger(world)
    for _ in range(2):
        world.place.clock.advance(timedelta(minutes=1))
        computed(world.place, _group_id(world))
    assert _ledger(world) == after and _manual_lines(world) == approved_lines

    # the journal of September carries the lines as MANUAL entries (E-30 ``manual``)
    run = journal_run(world)
    entries = get(world.app, f"{JOURNAL_RUNS}/{run['id']}/entries", world.maya, {"limit": "200"})
    assert entries.status_code == 200, entries.text
    manual = [item for item in entries.json()["items"] if item["je_type"] == "manual"]
    assert manual and {item["entry_kind"] for item in manual} == {"MANUAL_ADJUSTMENT"}
    assert {item["manual_adjustment_id"] for item in manual} == {created["id"]}
    assert all(
        item["je_type"] == "automated" for item in entries.json()["items"] if item not in manual
    )


def test_contract_level_reclass_posts_once(world: ReportWorld) -> None:
    """An ``ACCOUNT_RECLASS`` without an obligation belongs to the contract: its approved lines
    post on the accounts approved, under the contract's subject, and recomputations of the group
    emit nothing for them (ENGINE_SPEC_B S14-R-09a; ruling R-51 (a))."""
    accounts = _account_ids(world)
    payload = {
        "lines": [
            {
                "account_role": "UNBILLED_RECEIVABLE",
                "gl_account_id": accounts["1210"],
                "amount_txn": _usd("500.00"),
            },
            {
                "account_role": "ACCOUNTS_RECEIVABLE",
                "gl_account_id": accounts["1200"],
                "amount_txn": _usd("-500.00"),
            },
        ]
    }
    body = _body(world, "ACCOUNT_RECLASS", payload, reason_code="DATA_CORRECTION")
    created = _created(world, body)
    assert (created["obligation"], created["amount_functional_abs"]) == (None, _usd("500.00"))
    submitted = _submitted(world, created["id"])
    before = _ledger(world)
    decided = approve(world.app, submitted["approval_request_id"], world.priya)
    assert decided.status_code == 200, decided.text
    approved_lines = [
        ("ACCOUNTS_RECEIVABLE", "1200", Decimal("-500.00"), "MANUAL_ADJUSTMENT"),
        ("UNBILLED_RECEIVABLE", "1210", Decimal("500.00"), "MANUAL_ADJUSTMENT"),
    ]
    assert _manual_lines(world) == approved_lines
    # 04 T-SL-04 ``subject_key`` (rev 1.282; ruling R-11 as amended): the subject stage 14 gives
    # the adjustment's role target — the contract's in the adjustment's entity (S14-R-09a) — so
    # the read-back answers the key the engine has a target for.
    assert _manual_subjects(world) == {f"{K01}@AVM-US"}
    assert _ledger(world) == (before[0] + 2, before[1] + Decimal("1000.00"))
    after = _ledger(world)
    for _ in range(2):
        world.place.clock.advance(timedelta(minutes=1))
        computed(world.place, _group_id(world))
    assert _ledger(world) == after and _manual_lines(world) == approved_lines
    assert _revenue(world, SEPTEMBER_2026)[SEPTEMBER_2026] == SEPTEMBER_REVENUE


@pytest.mark.control("CTL-015")
def test_ctl_015_soft_close_restricts_submitters(world: ReportWorld) -> None:
    """CTL-015 (REQ-CLS-003; PRD BR-CLS-04): in a ``closing`` period ``maya`` — Revenue Accountant,
    without ``period.lock`` — receives 403 ``forbidden`` on submit, and ``marcus`` (Controller)
    succeeds; the refusal is audited, nothing is routed for Maya."""
    created = _created(world, _release(world))  # preparing stays the accountant's
    _start_close(world, world.marcus)
    refused = post(world.app, f"{ADJUSTMENTS}/{created['id']}/submit", world.maya, {})
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert _shown(world, created["id"])["status"] == "DRAFT"
    assert _adjustment_requests(world) == []

    submitted = post(world.app, f"{ADJUSTMENTS}/{created['id']}/submit", world.marcus, {})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"
    request = _request(world, submitted.json()["approval_request_id"], world.priya)
    assert request["preparer"]["id"] == str(world.marcus.member.user_id)
    # the Controller who submitted cannot approve it himself (CTL-014); the reviewer can
    own = approve(world.app, request["id"], world.marcus)
    assert (own.status_code, slug(own)) == (403, "self-approval"), own.text
    decided = approve(world.app, request["id"], world.priya)
    assert decided.status_code == 200, decided.text
    assert _shown(world, created["id"])["status"] == "POSTED"


def test_preparer_is_excluded_when_a_lock_holder_submits(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """PRD §2.5 (approver ≠ preparer) with BR-CLS-04: in a ``closing`` period a lock holder submits
    what an accountant prepared, so the request's preparer is the submitter. The person who
    prepared the adjustment is excluded from deciding it all the same, even holding
    ``adjustment.approve`` with a fresh second factor."""
    dana = _person(world, clock, "dana", "revenue_accountant", "revenue_reviewer")
    created = _created(world, _release(world), dana)
    assert created["created_by"]["id"] == str(dana.member.user_id)
    _start_close(world, world.marcus)
    submitted = _submitted(world, created["id"], world.marcus)
    request_id = submitted["approval_request_id"]
    request = _request(world, request_id, world.priya)
    assert request["preparer"]["id"] == str(world.marcus.member.user_id)

    own = approve(world.app, request_id, dana)
    assert (own.status_code, slug(own)) == (403, "self-approval"), own.text
    assert own.json()["detail"] == "You own this item, so another user must approve it."
    assert _request(world, request_id, world.priya)["steps"][0]["decisions"] == []
    assert _shown(world, created["id"])["status"] == "SUBMITTED" and _events(world) == []

    decided = approve(world.app, request_id, world.priya)
    assert decided.status_code == 200, decided.text
    assert _shown(world, created["id"])["status"] == "POSTED"


def test_withdraw_returns_to_draft_and_discard_voids(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """PRD SM-10 (rev 1.49; ruling R-51 (b)): ``SUBMITTED`` → ``DRAFT`` when the preparer withdraws
    the request, and ``DRAFT`` → ``VOIDED`` when the draft is discarded with a reason — a mistaken
    draft stops counting as pending. Neither changes a balance."""
    ledger = _ledger(world)
    created = _created(world, _release(world))
    submitted = _submitted(world, created["id"])
    request_id = submitted["approval_request_id"]
    # only the preparer of the request takes it back: Rhea holds the permission, not the request;
    # Priya (Revenue Reviewer) holds neither permission of the command
    rhea = _person(world, clock, "rhea", "revenue_accountant")
    not_rhea = post(world.app, f"{ADJUSTMENTS}/{created['id']}/withdraw", rhea, {})
    assert (not_rhea.status_code, slug(not_rhea)) == (403, "forbidden"), not_rhea.text
    assert not_rhea.json()["detail"] == "Only the preparer can withdraw this approval request."
    not_priya = post(world.app, f"{ADJUSTMENTS}/{created['id']}/withdraw", world.priya, {})
    assert (not_priya.status_code, slug(not_priya)) == (403, "forbidden"), not_priya.text
    assert _shown(world, created["id"])["status"] == "SUBMITTED"

    withdrawn = post(
        world.app,
        f"{ADJUSTMENTS}/{created['id']}/withdraw",
        world.maya,
        {"comment": "Wrong amount"},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    draft = withdrawn.json()
    assert (draft["status"], draft["pending_request"]) == ("DRAFT", None)
    request = _request(world, request_id, world.priya)
    assert (request["status"], request["void_reason"]) == ("WITHDRAWN", "WITHDRAWN_BY_PREPARER")
    gate = _gates(world)["MANUAL_ADJUSTMENTS_CLEARED"]
    assert (gate.status.value, gate.count) == ("FAILED", 1)  # a draft is pending
    again = post(world.app, f"{ADJUSTMENTS}/{created['id']}/withdraw", world.maya, {})
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text

    # the draft is editable again, under If-Match; the amount follows the payload
    unversioned = patch(
        world.app, f"{ADJUSTMENTS}/{created['id']}", world.maya, {"memo": "x"}, if_match=None
    )
    assert (unversioned.status_code, slug(unversioned)) == (428, "precondition-required")
    payload = {"obligation_id": _obligation_id(world), "amount": _usd("1200.00")}
    edited = patch(
        world.app,
        f"{ADJUSTMENTS}/{created['id']}",
        world.maya,
        {"payload": payload},
        if_match=f'"r{draft["row_version"]}"',
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["amount_functional_abs"] == _usd("1200.00")
    stale = patch(
        world.app,
        f"{ADJUSTMENTS}/{created['id']}",
        world.maya,
        {"memo": "Second thoughts"},
        if_match=f'"r{draft["row_version"]}"',
    )
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed"), stale.text

    unexplained = post(world.app, f"{ADJUSTMENTS}/{created['id']}/discard", world.maya, {})
    assert (unexplained.status_code, slug(unexplained)) == (422, "validation-failed")
    discarded = post(
        world.app,
        f"{ADJUSTMENTS}/{created['id']}/discard",
        world.maya,
        {"reason": "Entered against the wrong obligation"},
    )
    assert discarded.status_code == 200, discarded.text
    assert discarded.json()["status"] == "VOIDED"
    gate = _gates(world)["MANUAL_ADJUSTMENTS_CLEARED"]
    assert (gate.status.value, gate.count) == ("PASSED", 0)
    # VOIDED is terminal
    for action, body in (
        ("submit", {}),
        ("withdraw", {}),
        ("discard", {"reason": "Again"}),
        ("request-defer-past-lock", {"comment": "Later"}),
        ("preview", {}),
    ):
        refused = post(world.app, f"{ADJUSTMENTS}/{created['id']}/{action}", world.maya, body)
        assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), (
            action,
            refused.text,
        )
    frozen = patch(
        world.app,
        f"{ADJUSTMENTS}/{created['id']}",
        world.maya,
        {"memo": "Too late"},
        if_match=f'"r{discarded.json()["row_version"]}"',
    )
    assert (frozen.status_code, slug(frozen)) == (409, "invalid-transition"), frozen.text
    assert _events(world) == [] and _ledger(world) == ledger
    assert _revenue(world, SEPTEMBER_2026)[SEPTEMBER_2026] == SEPTEMBER_REVENUE


NOT_CREATOR: Final = "Only {creator} can change this adjustment."
ADJUSTMENT_NOT_VOIDABLE: Final = (
    "A posted manual adjustment cannot be voided. Correct it with a further adjustment."
)
OWN_ITEM: Final = "You own this item, so another user must approve it."
PREPARED_ITEM: Final = "You prepared this item, so another user must approve it."


def _refusal(response: Any) -> tuple[int, str, str, list[tuple[str, str, str]]]:
    """(status, slug, detail, [(field, rule id, message)]) of a problem response."""
    body = response.json()
    errors = [(item["field"], item["rule_id"], item["message"]) for item in body["errors"]]
    return response.status_code, slug(response), body["detail"], errors


def test_an_adjustment_is_edited_only_by_its_creator(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """Item ADJ-VOID-REFUSE-1, the creator-only rule (supervisor ruling R-112 (b) (2); PRD ERR-71;
    as R-64 (7) (a) for a judgement record): T-SL-05 keeps no list of editors and the
    self-approval rule excludes the creator and the submitter, so a second editor could approve
    what they wrote. ``PATCH`` is the creator's alone — for a draft and for a rejected adjustment
    being revised — and the refusal names the creator; ``submit`` and ``discard`` add nothing to
    the content and stay with whoever holds the permission."""
    created = _created(world, _release(world))
    etag = f'"r{created["row_version"]}"'
    not_maya = NOT_CREATOR.format(creator=created["created_by"]["display_name"])
    refusal = (403, "forbidden", not_maya, [("created_by", "SM-10", not_maya)])
    # Dana prepares and reviews adjustments: she could edit Maya's draft and then approve it
    dana = _person(world, clock, "dana", "revenue_accountant", "revenue_reviewer")
    payload = {"obligation_id": _obligation_id(world), "amount": _usd("9000.00")}
    for body in ({"payload": payload}, {"memo": "Reviewed by Dana"}):
        refused = patch(world.app, f"{ADJUSTMENTS}/{created['id']}", dana, body, if_match=etag)
        assert _refusal(refused) == refusal, refused.text
    # a stale version does not answer first: the refusal names the person, not the version
    stale = patch(
        world.app, f"{ADJUSTMENTS}/{created['id']}", dana, {"memo": "x"}, if_match='"r99"'
    )
    assert _refusal(stale) == refusal, stale.text
    unchanged = _shown(world, created["id"])
    assert (unchanged["row_version"], unchanged["memo"], unchanged["amount_functional_abs"]) == (
        created["row_version"],
        created["memo"],
        _usd(RELEASE),
    )

    # so what Dana decides is Maya's content alone: she rejects it as any reviewer does
    submitted = _submitted(world, created["id"])
    rejected = reject(world.app, submitted["approval_request_id"], dana, REJECTION)
    assert rejected.status_code == 200, rejected.text
    # a rejected adjustment is revised by its creator only
    revised_by_dana = patch(
        world.app,
        f"{ADJUSTMENTS}/{created['id']}",
        dana,
        {"memo": "Acceptance attached"},
        if_match=f'"r{_shown(world, created["id"])["row_version"]}"',
    )
    assert _refusal(revised_by_dana) == refusal, revised_by_dana.text
    assert _shown(world, created["id"])["status"] == "REJECTED"
    revised = patch(
        world.app,
        f"{ADJUSTMENTS}/{created['id']}",
        world.maya,
        {"memo": "Acceptance attached"},
        if_match=f'"r{_shown(world, created["id"])["row_version"]}"',
    )
    assert revised.status_code == 200, revised.text
    assert (revised.json()["status"], revised.json()["memo"]) == ("DRAFT", "Acceptance attached")

    # submit and discard are not edits: another accountant submits Maya's draft, or discards a
    # mistaken one, so an absent creator's draft never stands in a close's way
    rhea = _person(world, clock, "rhea", "revenue_accountant")
    by_rhea = _submitted(world, created["id"], rhea)
    request = _request(world, by_rhea["approval_request_id"], world.priya)
    assert request["preparer"]["id"] == str(rhea.member.user_id)
    decided = approve(world.app, by_rhea["approval_request_id"], dana)
    assert decided.status_code == 200, decided.text
    assert _shown(world, created["id"])["status"] == "POSTED"
    other = _created(world, _release(world, "100.00"))
    discarded = post(
        world.app,
        f"{ADJUSTMENTS}/{other['id']}/discard",
        rhea,
        {"reason": "Entered twice"},
    )
    assert discarded.status_code == 200, discarded.text
    assert discarded.json()["status"] == "VOIDED"


def test_neither_the_creator_nor_the_submitter_approves(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """04 §16.14 (rev 1.158; supervisor ruling R-112 (b) (2)): B submits A's draft, and neither A
    nor B can approve it — the creator is excluded as the owner of the item, the submitter as the
    request's preparer — although both hold ``adjustment.approve`` with a fresh second factor. It
    is what makes the open ``submit`` safe beside the creator-only edit."""
    dana = _person(world, clock, "dana", "revenue_accountant", "revenue_reviewer")
    erin = _person(world, clock, "erin", "revenue_accountant", "revenue_reviewer")
    created = _created(world, _release(world), dana)
    assert created["created_by"]["id"] == str(dana.member.user_id)
    submitted = _submitted(world, created["id"], erin)
    request_id = submitted["approval_request_id"]
    request = _request(world, request_id, world.priya)
    assert request["preparer"]["id"] == str(erin.member.user_id)

    for person, detail in ((dana, OWN_ITEM), (erin, PREPARED_ITEM)):
        own = approve(world.app, request_id, person)
        assert (own.status_code, slug(own), own.json()["detail"]) == (
            403,
            "self-approval",
            detail,
        ), own.text
    assert _request(world, request_id, world.priya)["steps"][0]["decisions"] == []
    assert _shown(world, created["id"])["status"] == "SUBMITTED" and _events(world) == []

    decided = approve(world.app, request_id, world.priya)
    assert decided.status_code == 200, decided.text
    assert _shown(world, created["id"])["status"] == "POSTED"


def test_the_event_of_a_posted_adjustment_is_not_voided(world: ReportWorld) -> None:
    """Item ADJ-VOID-REFUSE-1 (supervisor ruling R-112 (b) (1); PRD ERR-70):
    ``POST /events/{id}/request-void`` refuses a ``MANUAL_ADJUSTMENT_APPLIED`` event by name.
    Approved, that void would take the adjustment back at the next computation while its T-SL-05
    row, the register and the close gate still read it as posted. A posted adjustment is
    corrected by a further adjustment; the reversal of PRD SM-10 is not built in 1.0."""
    created = _created(world, _release(world))
    submitted = _submitted(world, created["id"])
    decided = approve(world.app, submitted["approval_request_id"], world.priya)
    assert decided.status_code == 200, decided.text
    [event] = _events(world)
    ledger, revenue = _ledger(world), _revenue(world, SEPTEMBER_2026, OCTOBER_2026)
    stored = _void_records(world)

    refused = post(
        world.app,
        f"/api/v1/events/{event['id']}/request-void",
        world.maya,
        {"reason_code": "DATA_CORRECTION", "comment": "Entered against the wrong period"},
    )
    assert _refusal(refused) == (
        409,
        "invalid-transition",
        ADJUSTMENT_NOT_VOIDABLE,
        [("event_type", "SM-10", ADJUSTMENT_NOT_VOIDABLE)],
    ), refused.text
    # nothing was stored or routed, and the adjustment stands as posted
    assert _void_records(world) == stored
    assert _events(world, "EVENT_VOIDED") == []
    posted = _shown(world, created["id"])
    assert (posted["status"], posted["applied_event_id"]) == ("POSTED", str(event["id"]))
    assert (_ledger(world), _revenue(world, SEPTEMBER_2026, OCTOBER_2026)) == (ledger, revenue)

    # the route still voids what it voided before: the refusal is of this event type alone
    [billing, *_] = _events(world, "BILLING_RECORDED")
    accepted = post(
        world.app,
        f"/api/v1/events/{billing['id']}/request-void",
        world.maya,
        {"reason_code": "DATA_CORRECTION", "comment": "Invoice entered twice"},
    )
    assert accepted.status_code == 201, accepted.text
    assert _void_records(world) == (stored[0] + 1, stored[1] + 1)


def _void_records(world: ReportWorld) -> tuple[int, int]:
    """(event submissions, approval requests of subject MANUAL_EVENT) of the workspace."""
    return (
        int(world.place.scalar(select(func.count()).select_from(event_submission))),
        int(
            world.place.scalar(
                select(func.count())
                .select_from(approval_request)
                .where(approval_request.c.subject_type == "MANUAL_EVENT")
            )
        ),
    )


def test_rejected_deferral_keeps_the_adjustment_pending(world: ReportWorld) -> None:
    """Ruling R-51 (c): a rejected deferral leaves the adjustment ``SUBMITTED``, not deferred and
    still counted; a later submit routes it for posting. [J] BR-CLS-04 restricts submitting in a
    ``closing`` period: the accountant who prepared the adjustment still asks for its deferral."""
    created = _created(world, _release(world))
    submitted = _submitted(world, created["id"])
    _start_close(world, world.marcus)
    asked = post(
        world.app,
        f"{ADJUSTMENTS}/{created['id']}/request-defer-past-lock",
        world.maya,
        {"comment": "Customer acceptance arrives in October"},
    )
    assert asked.status_code == 200, asked.text
    deferral = asked.json()
    assert deferral["pending_request"]["purpose"] == "DEFER_PAST_LOCK"
    repeated = post(
        world.app,
        f"{ADJUSTMENTS}/{created['id']}/request-defer-past-lock",
        world.maya,
        {"comment": "Customer acceptance arrives in October"},
    )
    assert (repeated.status_code, slug(repeated)) == (409, "invalid-transition"), repeated.text
    assert repeated.json()["detail"] == (
        "A request to defer this adjustment past lock is already pending."
    )

    refused = reject(
        world.app, deferral["approval_request_id"], world.priya, "Book it in September."
    )
    assert refused.status_code == 200, refused.text
    kept = _shown(world, created["id"])
    assert (kept["status"], kept["is_deferred_past_lock"], kept["pending_request"]) == (
        "SUBMITTED",
        False,
        None,
    )
    counted = _gates(world)
    assert counted["MANUAL_ADJUSTMENTS_CLEARED"].count == 1
    assert counted["APPROVALS_CLEARED"].count == 0  # no request is pending
    assert _events(world) == []

    # soft close: the posting is submitted again by a lock holder (BR-CLS-04)
    not_maya = post(world.app, f"{ADJUSTMENTS}/{created['id']}/submit", world.maya, {})
    assert (not_maya.status_code, slug(not_maya)) == (403, "forbidden"), not_maya.text
    routed = _submitted(world, created["id"], world.marcus)
    assert routed["pending_request"] == {"id": routed["approval_request_id"], "purpose": "POSTING"}
    assert routed["approval_request_id"] not in (
        submitted["approval_request_id"],
        deferral["approval_request_id"],
    )
    decided = approve(world.app, routed["approval_request_id"], world.priya)
    assert decided.status_code == 200, decided.text
    posted = _shown(world, created["id"])
    assert (posted["status"], posted["is_deferred_past_lock"]) == ("POSTED", False)
    assert _revenue(world, SEPTEMBER_2026)[SEPTEMBER_2026] == "12164.38"
    assert _gates(world)["MANUAL_ADJUSTMENTS_CLEARED"].count == 0


def test_withdrawing_a_deferred_adjustment_ends_the_deferral(world: ReportWorld) -> None:
    """A deferred adjustment has no pending request; withdrawing it returns it to ``DRAFT``, which
    is editable and therefore pending again: the deferral does not outlive it (REQ-JE-019)."""
    created = _created(world, _release(world))
    _submitted(world, created["id"])
    asked = post(
        world.app,
        f"{ADJUSTMENTS}/{created['id']}/request-defer-past-lock",
        world.maya,
        {"comment": "Customer acceptance arrives in October"},
    )
    assert asked.status_code == 200, asked.text
    decided = approve(world.app, asked.json()["approval_request_id"], world.priya)
    assert decided.status_code == 200, decided.text
    assert _shown(world, created["id"])["is_deferred_past_lock"] is True
    assert _gates(world)["MANUAL_ADJUSTMENTS_CLEARED"].count == 0

    withdrawn = post(world.app, f"{ADJUSTMENTS}/{created['id']}/withdraw", world.maya, {})
    assert withdrawn.status_code == 200, withdrawn.text
    draft = withdrawn.json()
    assert (draft["status"], draft["is_deferred_past_lock"]) == ("DRAFT", False)
    gate = _gates(world)["MANUAL_ADJUSTMENTS_CLEARED"]
    assert (gate.status.value, gate.count) == ("FAILED", 1)


def test_adjustments_of_another_entity_are_not_found(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """Ruling R-28: a row of entity E needs the permission FOR E. Uma prepares and approves for
    AVM-UK only; every route of an AVM-US adjustment answers her 404, the list shows her none,
    and she cannot attach to it or decide its request."""
    (calendar_id,) = {
        str(row["calendar_id"])
        for row in world.place.rows(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
        )
    }
    uk = entity(world.app, world.maya, code="AVM-UK", calendar_id=calendar_id)
    uma_member = colleague(world.tenant_id, "uma")
    for code in ("revenue_accountant", "revenue_reviewer"):
        assign(uma_member, code, entity_ids=[UUID(str(uk["id"]))])
    uma = enrolled(world.app, clock, uma_member)

    outside = post(world.app, ADJUSTMENTS, uma, _release(world))
    assert (outside.status_code, slug(outside)) == (404, "not-found"), outside.text
    created = _created(world, _release(world))
    submitted = _submitted(world, created["id"])
    path = f"{ADJUSTMENTS}/{created['id']}"

    shown = get(world.app, path, uma)
    assert (shown.status_code, slug(shown)) == (404, "not-found"), shown.text
    listed = get(world.app, ADJUSTMENTS, uma)
    assert (listed.status_code, listed.json()["items"]) == (200, []), listed.text
    edited = patch(world.app, path, uma, {"memo": "Mine now"}, if_match='"r1"')
    assert (edited.status_code, slug(edited)) == (404, "not-found"), edited.text
    for action, body in (
        ("preview", {}),
        ("submit", {}),
        ("withdraw", {}),
        ("discard", {"reason": "Not mine"}),
        ("request-defer-past-lock", {"comment": "Later"}),
    ):
        refused = post(world.app, f"{path}/{action}", uma, body)
        assert (refused.status_code, slug(refused)) == (404, "not-found"), (action, refused.text)
    uploaded = call(
        world.app,
        "POST",
        FILES,
        data={"purpose": "ATTACHMENT"},
        files={"file": ("note.pdf", upload_fixtures.PDF, "application/pdf")},
        headers=cookie_headers(uma.token, uma.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    attached = post(
        world.app,
        ATTACHMENTS,
        uma,
        {
            "file_object_id": uploaded.json()["id"],
            "subject_type": "manual_adjustment",
            "subject_id": created["id"],
            "description": "Not hers",
        },
    )
    assert (attached.status_code, slug(attached)) == (404, "not-found"), attached.text
    request_path = f"{APPROVALS}/{submitted['approval_request_id']}"
    unseen = get(world.app, request_path, uma)
    assert (unseen.status_code, slug(unseen)) == (404, "not-found"), unseen.text
    request = _request(world, submitted["approval_request_id"], world.priya)
    decision = post(
        world.app,
        f"{request_path}/approve",
        uma,
        {
            "subject_content_sha256": request["subject"]["content_sha256"],
            "impact_preview_sha256": request["impact_preview"]["sha256"],
            "comment": "OK",
        },
    )
    assert (decision.status_code, slug(decision)) == (404, "not-found"), decision.text

    # nothing moved, and the people of AVM-US still read and decide it
    current = _shown(world, created["id"])
    assert (current["status"], current["attachment_count"], current["row_version"]) == (
        "SUBMITTED",
        0,
        submitted["row_version"],
    )
    found = get(world.app, ADJUSTMENTS, world.maya, {"entity": "AVM-US", "status": "SUBMITTED"})
    assert [item["id"] for item in found.json()["items"]] == [created["id"]]
    none = get(world.app, ADJUSTMENTS, world.maya, {"entity": "AVM-UK"})
    assert (none.status_code, none.json()["items"]) == (200, [])


def test_an_attachment_of_another_entity_s_adjustment_is_not_found_on_void(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """REQ-PLT-012 with ruling R-28 on ``POST /attachments/{id}/void``: the supporting document
    of an AVM-US adjustment answers Uma — who prepares for AVM-UK only — 404, as a missing one
    does. A second AVM-US preparer, who may attach to the adjustment and did not attach this
    file, gets the same 404 since ruling R-111 (5) (04 T-PLT-30 Subjects rev 1.189: an attachment
    the caller did not attach is answered as one that does not exist — the 403 "Only the person
    who attached this file can void it." told it from a missing one); the person who attached
    it voids it."""
    (calendar_id,) = {
        str(row["calendar_id"])
        for row in world.place.rows(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
        )
    }
    uk = entity(world.app, world.maya, code="AVM-UK", calendar_id=calendar_id)
    uma_member = colleague(world.tenant_id, "uma")
    assign(uma_member, "revenue_accountant", entity_ids=[UUID(str(uk["id"]))])
    uma = enrolled(world.app, clock, uma_member)
    rhea = _person(world, clock, "rhea", "revenue_accountant")

    created = _created(world, _release(world))
    attachment = _attached(world, world.maya, created["id"])
    path = f"{ATTACHMENTS}/{attachment['id']}/void"

    unseen = post(world.app, path, uma, {"reason": "Not hers"})
    assert (unseen.status_code, slug(unseen)) == (404, "not-found"), unseen.text
    not_the_uploader = post(world.app, path, rhea, {"reason": "Not hers either"})
    assert (not_the_uploader.status_code, slug(not_the_uploader)) == (404, "not-found")
    assert {**not_the_uploader.json(), "instance": None} == {**unseen.json(), "instance": None}
    assert _shown(world, created["id"])["attachment_count"] == 1

    voided = post(world.app, path, world.maya, {"reason": "Wrong document"})
    assert voided.status_code == 200, voided.text
    assert _shown(world, created["id"])["attachment_count"] == 0


def test_list_filters_and_idempotent_create(world: ReportWorld) -> None:
    """04 API-R-37: the list filters ``entity``, ``book``, ``period``, ``status`` and ``kind``; a
    create repeated under its ``Idempotency-Key`` answers the first response and stores one
    adjustment (API-C-04)."""
    body = _release(world)
    headers = cookie_headers(world.maya.token, world.maya.csrf_token)
    first = call(world.app, "POST", ADJUSTMENTS, json=body, headers=headers)
    assert first.status_code == 201, first.text
    replayed = call(world.app, "POST", ADJUSTMENTS, json=body, headers=headers)
    assert (replayed.status_code, replayed.json()["id"]) == (201, first.json()["id"])
    assert replayed.headers["Idempotent-Replay"] == "true"
    override = _created(world, _override(world, "12164.38"))
    assert len(world.place.rows(select(manual_adjustment))) == 2  # the replay stored nothing
    _submitted(world, override["id"])

    def listed(**params: str) -> list[str]:
        found = get(world.app, ADJUSTMENTS, world.maya, {"sort": "adjustment_no", **params})
        assert found.status_code == 200, found.text
        return [str(item["adjustment_no"]) for item in found.json()["items"]]

    assert listed() == ["ADJ-000001", "ADJ-000002"]
    assert listed(status="SUBMITTED") == ["ADJ-000002"]
    assert listed(kind="MANUAL_RELEASE") == ["ADJ-000001"]
    assert listed(entity="AVM-US", book=BOOK, period=SEPTEMBER_2026) == [
        "ADJ-000001",
        "ADJ-000002",
    ]
    assert listed(period=OCTOBER_2026) == [] and listed(book="IFRS15") == []
    unknown = get(world.app, ADJUSTMENTS, world.maya, {"status": "PENDING"})
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text


def test_r86_the_attachment_a_threshold_adjustment_needed_is_evidence(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """Supervisor ruling R-86 (c) on the manual adjustment (04 T-PLT-29 evidence references rev
    1.142; 05 PRV-07 b): from USD 10,000.00 the request needs an attachment and carries
    ``ABOVE_THRESHOLD``, so that document is evidence while the adjustment is submitted — one
    administrator does not shred it, and ``file.shred`` names the adjustment and the approved
    path. The attachment of a submitted adjustment below the threshold, and the same document
    before the submission and after a withdrawal, are erased by ``file.shred`` alone."""
    tess = _person(world, clock, "tess", "tenant_admin")

    def supported(adjustment_id: str, name: str) -> str:
        """A document of its own bytes attached to the adjustment; the stored file's id."""
        uploaded = call(
            world.app,
            "POST",
            FILES,
            data={"purpose": "ATTACHMENT"},
            files={"file": (name, upload_fixtures.PDF + f"% {name}\n".encode(), "application/pdf")},
            headers=cookie_headers(world.maya.token, world.maya.csrf_token),
        )
        assert uploaded.status_code == 201, uploaded.text
        body = {
            "file_object_id": uploaded.json()["id"],
            "subject_type": "manual_adjustment",
            "subject_id": adjustment_id,
        }
        attached = post(world.app, ATTACHMENTS, world.maya, body)
        assert attached.status_code == 201, attached.text
        return str(uploaded.json()["id"])

    def holds(file_id: str) -> list[str]:
        return [hold.record for hold in file_evidence.holds(world.tenant_id, UUID(file_id))]

    def shred(file_id: str) -> Any:
        reason = {"reason": "DSR-2026-0917: erase the person's data in this document"}
        return post(world.app, f"{FILES}/{file_id}/shred", tess, reason)

    def flags(adjustment: Mapping[str, Any]) -> list[str]:
        request = _request(world, str(adjustment["approval_request_id"]), world.priya)
        return list(request["flags"])

    # An override that changes September by exactly 10,000.00: the request needs the document,
    # and once it is submitted one administrator does not shred it.
    large = _created(world, _override(world, "19764.38"))
    support = supported(large["id"], "customer-acceptance.pdf")
    assert flags(_submitted(world, large["id"])) == ["ABOVE_THRESHOLD"]
    record = (
        f"the supporting attachment of manual adjustment {large['adjustment_no']}, which has "
        "been submitted"
    )
    refused = shred(support)
    assert refused.status_code == 409, refused.text
    assert slug(refused) == "invalid-transition"
    (error,) = refused.json()["errors"]
    assert (error["rule_id"], error["message"]) == (
        "FILE_SHRED_APPROVAL_REQUIRED",
        file_evidence.APPROVAL_MESSAGE.format(record=record),
    )
    assert holds(support) == [record]

    # Withdrawn: the adjustment is a draft again and its document is erasable as before.
    withdrawn = post(
        world.app, f"{ADJUSTMENTS}/{large['id']}/withdraw", world.maya, {"comment": "Wrong amount"}
    )
    assert withdrawn.status_code == 200 and withdrawn.json()["status"] == "DRAFT", withdrawn.text
    assert holds(support) == []
    done = shred(support)
    assert done.status_code == 200 and done.json()["shredded_at"] is not None, done.text

    # Below the threshold the request needs no attachment: one added anyway is no evidence.
    small = _created(world, _release(world))
    extra = supported(small["id"], "note.pdf")
    assert flags(_submitted(world, small["id"])) == []
    assert holds(extra) == []
    erased = shred(extra)
    assert erased.status_code == 200 and erased.json()["shredded_at"] is not None, erased.text


# --- a document a rule asks for is one whose file can still be read ------------------------------
# Item EVIDENCE-COUNT-SHREDDED-1 (supervisor rulings R-119 (g), R-120 (g), R-121 (l); 04 rev 1.216
# T-PLT-29 "A document a rule asks for", §16.10; PRD rev 1.145 §2.5; 03 rev 1.131 REQ-PLT-035).

SHRED_REASON: Final = "DSR-2026-0917: erase the person's data in this document"


def _document(world: ReportWorld, adjustment_id: str, name: str) -> str:
    """A document of its own bytes that Maya uploads and attaches to the adjustment; the stored
    file's id."""
    uploaded = call(
        world.app,
        "POST",
        FILES,
        data={"purpose": "ATTACHMENT"},
        files={"file": (name, upload_fixtures.PDF + f"% {name}\n".encode(), "application/pdf")},
        headers=cookie_headers(world.maya.token, world.maya.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    body = {
        "file_object_id": uploaded.json()["id"],
        "subject_type": "manual_adjustment",
        "subject_id": adjustment_id,
    }
    attached = post(world.app, ATTACHMENTS, world.maya, body)
    assert attached.status_code == 201, attached.text
    return str(uploaded.json()["id"])


def _answer(response: HttpResponse) -> tuple[int, str | None]:
    """(status, problem) — no problem for an answer that is none."""
    return (response.status_code, slug(response) if response.status_code >= 400 else None)


def _submit(world: ReportWorld, adjustment_id: str) -> HttpResponse:
    return post(world.app, f"{ADJUSTMENTS}/{adjustment_id}/submit", world.maya, {})


def test_evidence_count_shredded_1_a_shredded_document_supports_no_adjustment(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """From USD 10,000.00 a manual adjustment needs an attachment (PRD §2.5). The document of a
    DRAFT is no evidence yet and ``file.shred`` erases it; its attachment row stays, live. That
    row counted for the rule: the draft was submitted on a document that no longer exists. The
    submission is refused as one without an attachment, and goes through once a document that
    can be read stands beside the shredded one."""
    tess = _person(world, clock, "tess", "tenant_admin")
    large = _created(world, _override(world, "19764.38"))
    support = _document(world, large["id"], "customer-acceptance.pdf")
    erased = post(world.app, f"{FILES}/{support}/shred", tess, {"reason": SHRED_REASON})
    assert erased.status_code == 200 and erased.json()["shredded_at"] is not None, erased.text
    assert _shown(world, large["id"])["attachment_count"] == 1  # the row stays

    refused = _submit(world, large["id"])
    assert _answer(refused) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("attachments", "PRD-2.5")]
    assert _shown(world, large["id"])["status"] == "DRAFT"
    assert _adjustment_requests(world) == []

    # Positive control: a document that can be read supports the adjustment.
    _document(world, large["id"], "customer-acceptance-signed.pdf")
    submitted = _submitted(world, large["id"])
    request = _request(world, submitted["approval_request_id"], world.priya)
    assert (submitted["status"], request["flags"]) == ("SUBMITTED", ["ABOVE_THRESHOLD"])


def test_evidence_count_shredded_1_an_approved_shred_makes_the_pending_request_stale(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """Ruling R-120 (g). Once the adjustment is submitted its document is evidence, and only an
    approved ``EVIDENCE_SHRED`` request erases it. The request's preview names the pending
    request that rests on the document; and when the Controller has approved the shred, the
    decision of that pending request is refused as stale — the request is voided and the
    adjustment is a draft again, to be supported by a document that can be read."""
    tess = _person(world, clock, "tess", "tenant_admin")
    large = _created(world, _override(world, "19764.38"))
    support = _document(world, large["id"], "customer-acceptance.pdf")
    request_id = _submitted(world, large["id"])["approval_request_id"]
    pending = _request(world, request_id, world.priya)

    asked = post(world.app, f"{FILES}/{support}/request-shred", tess, {"reason": SHRED_REASON})
    assert asked.status_code == 200, asked.text
    shred_request = _request(world, asked.json()["approval_request_id"], world.marcus)
    preview = get(
        world.app, f"{FILES}/{shred_request['impact_preview']['file_id']}/content", world.marcus
    )
    assert preview.status_code == 200, preview.text
    named = preview.json()["after"].get("pending_requests")
    shredded = approve(world.app, asked.json()["approval_request_id"], world.marcus)
    assert shredded.status_code == 200, shredded.text
    gone = get(world.app, f"{FILES}/{support}/content", world.maya)
    assert [error["rule_id"] for error in gone.json()["errors"]] == ["FILE_SHREDDED"], gone.text

    decided = approve(world.app, request_id, world.priya)
    assert {"the preview names": named, "the pending request's decision": _answer(decided)} == {
        "the preview names": [
            {
                "request_no": pending["request_no"],
                "subject_type": "MANUAL_ADJUSTMENT",
                "record": (
                    f"the supporting attachment of manual adjustment {large['adjustment_no']}, "
                    "which has been submitted"
                ),
            }
        ],
        "the pending request's decision": (409, "stale-approval"),
    }
    (voided,) = [row for row in _adjustment_requests(world) if str(row["id"]) == request_id]
    assert (voided["status"], voided["void_reason"]) == ("VOIDED", "STALE_SUBJECT")
    assert _shown(world, large["id"])["status"] == "DRAFT"

    # The way on: the shredded document supports nothing, a readable one does.
    assert _answer(_submit(world, large["id"])) == (422, "validation-failed")
    _document(world, large["id"], "customer-acceptance-signed.pdf")
    assert _submitted(world, large["id"])["status"] == "SUBMITTED"


def test_evidence_count_shredded_1_the_submission_and_the_attachment_wait_for_a_shred(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """The file row is locked by the commands that count the file, as by the shred, so the later
    of the two sees what the earlier committed (the import commit did that already). A shred in
    flight — the row locked and marked, not committed — holds back the attaching of the file
    and the submission of the adjustment it supports; when it commits, the attachment finds no
    such file and the submission no document."""
    large = _created(world, _override(world, "19764.38"))
    first = UUID(_document(world, large["id"], "customer-acceptance.pdf"))
    again = {
        "file_object_id": str(first),
        "subject_type": "manual_adjustment",
        "subject_id": large["id"],
    }
    # Maya attaches her upload once more while its shred is in flight ...
    attached = beside_a_shred(
        world.tenant_id,
        first,
        lambda: post(world.app, ATTACHMENTS, world.maya, again),
        at=clock.now(),
    )
    # ... and submits the adjustment while the shred of its other document is.
    second = UUID(_document(world, large["id"], "customer-acceptance-signed.pdf"))
    submitted = beside_a_shred(
        world.tenant_id, second, lambda: _submit(world, large["id"]), at=clock.now()
    )
    assert {
        "attach": (attached.waited, *_answer(attached.response)),
        "submit": (submitted.waited, *_answer(submitted.response)),
    } == {
        "attach": (True, 422, "validation-failed"),
        "submit": (True, 422, "validation-failed"),
    }
    assert fields(attached.response)[0][0] == "file_object_id"
    assert fields(submitted.response) == [("attachments", "PRD-2.5")]
    assert _shown(world, large["id"])["status"] == "DRAFT"


def test_evidence_count_shredded_1_the_approval_waits_for_a_shred(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """The approval of the posting request reads its basis again under the adjustment's locks,
    and the files of its documents are locked before that reading. A shred in flight holds the
    last decision back; when it commits, the decision is refused as stale and the adjustment is
    a draft again — it is not approved on a document destroyed beside it.

    Why the approval is a caller of the lock beside the three transitions and the attachment
    (judgement J25): measured without it, on the head that locked at those four only, the last
    decision did not wait and answered 200 beside the shred in flight — ``(False, 200, None)``
    here. The approval and an approved shred of its document, running at once, each completed
    without seeing the other."""
    large = _created(world, _override(world, "19764.38"))
    document = UUID(_document(world, large["id"], "customer-acceptance.pdf"))
    request_id = _submitted(world, large["id"])["approval_request_id"]
    first = approve(world.app, request_id, world.priya)
    assert first.status_code == 200 and first.json()["status"] == "PENDING", first.text
    decided = beside_a_shred(
        world.tenant_id,
        document,
        lambda: approve(world.app, request_id, world.marcus),
        at=clock.now(),
    )
    assert (decided.waited, *_answer(decided.response)) == (True, 409, "stale-approval")
    assert _shown(world, large["id"])["status"] == "DRAFT"
