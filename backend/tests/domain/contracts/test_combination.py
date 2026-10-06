"""Contract combination and combination suggestions (04 §15.3 API-R-28, §16.14, T-CON-03, T-CON-04,
table 15.4-C ``COMBINATION_SUGGESTED``, table 3.4-R; ENGINE_SPEC S02-R-09, S02-R-10, S02-R-14;
POLICIES POL-016; PRD BR-CON-03, IMP-89, WLD-C-05, WLD-C-11, WLD-K-05, WLD-K-11; 03 REQ-CON-009,
REQ-CON-010, REQ-CON-019; BUILD_SPEC CTR-8).

Worlds: ``support.factories.k11_world`` (AVM-DE, EUR) for suggestions, with the related-party group
HOLLENBRAND of C-05 and C-11 and the product AVM-KIT of K-05; ``support.factories.seat_world``
(AVM-US, USD) for combinations of two seat contracts of C-09. Maya (Revenue Accountant) books,
proposes and submits; Marcus (Controller; MFA) approves with ``contract.approve``.
"""

from __future__ import annotations

import threading
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals.subjects import COMBINATION_AUTHOR_DETAIL
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import locking
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    audit_event,
    combination_group,
    combination_group_member,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    exception_item,
    obligation_version,
    period,
    subledger_line,
    subledger_posting,
)
from erev_api.domain.contracts import holds, repo
from erev_api.domain.policies.judgements import PROPOSAL_NOT_EDITED
from erev_api.enums import RegistryCategory, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.uow import unit_of_work
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import (
    K11World,
    SeatWorld,
    activated_contract,
    booked_contract,
    computed,
    k11_body,
    k11_world,
    product_with_template,
    seat_body,
    seat_line,
    seat_world,
)
from support.interleave import (
    await_lock_wait,
    await_lock_waits,
    backend_pid,
    observing_checkouts,
)
from support.principals import colleague, enrolled
from support.reference import APPROVALS, approve, assign, fields, get, patch, post, put, slug
from support.rows import publish_registry_version

GROUPS = "/api/v1/combination-groups"
SUGGESTIONS = "/api/v1/combination-suggestions"
EVENTS = "/api/v1/contracts/{contract_id}/events"
RATIONALE = "Separate purchasing entities; negotiated independently."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def k11(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K11World:
    return k11_world(app, keyring, clock, files)


@pytest.fixture
def seats(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files)


# --- suggestions ---------------------------------------------------------------------------------


def _hollenbrand(world: K11World) -> UUID:
    """PRD WLD-C-05 and WLD-C-11 in related-party group HOLLENBRAND, and AVM-KIT; returns C-05."""
    maya = world.place.author
    created = post(
        world.app,
        "/api/v1/related-party-groups",
        maya,
        {"code": "HOLLENBRAND", "name": "Hollenbrand group (Demo)"},
    )
    assert created.status_code == 201, created.text
    group_id = created.json()["id"]
    path = f"/api/v1/customers/{world.customer_id}"
    shown = get(world.app, path, maya)
    assert shown.status_code == 200, shown.text
    joined = patch(
        world.app, path, maya, {"related_party_group_id": group_id}, if_match=shown.headers["ETag"]
    )
    assert joined.status_code == 200, joined.text
    buyer = post(
        world.app,
        "/api/v1/customers",
        maya,
        {
            "code": "C-05",
            "name": "Hollenbrand Klinikbedarf GmbH (Demo)",
            "related_party_group_id": group_id,
        },
    )
    assert buyer.status_code == 201, buyer.text
    product_with_template(
        world.app, maya, code="AVM-KIT", name="Clinic starter kit", revenue_category="PRODUCT"
    )
    return UUID(str(buyer.json()["id"]))


def _k05(customer_id: UUID) -> dict[str, Any]:
    """PRD WLD-K-05 ``NS-SO-DE-5001``: O1 AVM-KIT 100 units × 100.00 = 10,000.00 EUR, 2026-09-03."""
    return {
        "external_id": "NS-SO-DE-5001",
        "customer_id": str(customer_id),
        "contracting_entity_code": "AVM-DE",
        "transaction_currency": "EUR",
        "inception_date": "2026-09-03",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": "AVM-KIT",
                "quantity": "100",
                "total_price": {"amount": "10000.00", "currency": "EUR"},
            }
        ],
    }


def _book_pair(world: K11World) -> tuple[UUID, UUID]:
    """K-11 booked (C-11, 2026-09-01), then K-05 created through ``POST /contracts``."""
    c05 = _hollenbrand(world)
    k11_contract = booked_contract(world.place, k11_body(world.customer_id), activate=False)
    created = post(world.app, "/api/v1/contracts", world.place.author, _k05(c05))
    assert created.status_code == 201, created.text
    return UUID(str(k11_contract.contract["id"])), UUID(str(created.json()["id"]))


def _suggestions(world: K11World) -> list[dict[str, Any]]:
    return world.place.rows(
        select(exception_item).where(exception_item.c.code == "COMBINATION_SUGGESTED")
    )


def test_suggestion_for_related_party_within_window(k11: K11World) -> None:
    k11_id, k05_id = _book_pair(k11)
    items = _suggestions(k11)
    assert len(items) == 1
    item = items[0]
    ids = sorted([k11_id, k05_id], key=str)
    external = {k11_id: "NS-SO-DE-5004", k05_id: "NS-SO-DE-5001"}
    assert (
        str(item["source"]),
        str(item["severity"]),
        str(item["disposition"]),
        str(item["status"]),
        item["dedupe_key"],
        item["contract_id"],
        item["title"],
    ) == (
        "ENGINE",
        "WARNING",
        "remediable",
        "OPEN",
        f"ENGINE:COMBINATION_SUGGESTED:{ids[0]},{ids[1]}",
        k05_id,
        "Combination suggested",
    )
    assert item["message"] == (
        f"{external[ids[0]]} and {external[ids[1]]} belong to the same customer group and started "
        "within 30 days of each other. Combine them or dismiss the suggestion with a rationale."
    )

    listed = get(k11.app, SUGGESTIONS, k11.place.author, {"contract": str(k11_id)})
    assert listed.status_code == 200, listed.text
    (suggestion,) = listed.json()["items"]
    assert suggestion == {
        "id": str(item["id"]),
        "contract_ids": [str(value) for value in ids],
        "contract_external_ids": [external[value] for value in ids],
        "related_party_group": {
            "id": suggestion["related_party_group"]["id"],
            "code": "HOLLENBRAND",
            "name": "Hollenbrand group (Demo)",
        },
        "inception_dates": ["2026-09-01" if value == k11_id else "2026-09-03" for value in ids],
        "detection_window_days": 30,
        "status": "OPEN",
        "created_at": suggestion["created_at"],
    }
    other = get(k11.app, SUGGESTIONS, k11.place.author, {"contract": str(k11.entity_id)})
    assert other.status_code == 200, other.text
    assert other.json()["items"] == []


def test_window_zero_disables_detection(k11: K11World) -> None:
    context = DbContext(tenant_id=k11.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        publish_registry_version(
            session,
            tenant_id=k11.place.tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            values={"combination.detection_window_days": 0},
        )
    _book_pair(k11)
    assert _suggestions(k11) == []


def test_dismiss_requires_rationale(k11: K11World) -> None:
    k11_id, _ = _book_pair(k11)
    (item,) = _suggestions(k11)
    path = f"{SUGGESTIONS}/{item['id']}/dismiss"
    short = post(k11.app, path, k11.place.author, {"rationale": "Too short"})
    assert short.status_code == 422, short.text
    assert slug(short) == "validation-failed"
    dismissed = post(k11.app, path, k11.place.author, {"rationale": RATIONALE})
    assert dismissed.status_code == 200, dismissed.text
    assert (dismissed.json()["id"], dismissed.json()["status"]) == (str(item["id"]), "DISMISSED")
    stored = k11.place.rows(select(exception_item).where(exception_item.c.id == item["id"]))[0]
    assert (str(stored["status"]), stored["resolution"], stored["resolved_by"]) == (
        "DISMISSED",
        RATIONALE,
        k11.place.author.member.user_id,
    )
    audits = k11.place.rows(
        select(audit_event.c.action, audit_event.c.before, audit_event.c.after).where(
            audit_event.c.object_id == item["id"], audit_event.c.action == "exception_item.dismiss"
        )
    )
    assert [(row["before"]["status"], row["after"]["status"]) for row in audits] == [
        ("OPEN", "DISMISSED")
    ]
    listed = get(k11.app, SUGGESTIONS, k11.place.author, {"contract": str(k11_id)})
    assert listed.json()["items"] == []
    again = post(k11.app, path, k11.place.author, {"rationale": RATIONALE})
    assert again.status_code in (200, 409), again.text


# --- combination ---------------------------------------------------------------------------------


def _active(world: SeatWorld, external_id: str, seats: str, price: str, end: str) -> UUID:
    """A C-09 seat contract from 2026-09-01, activated as SYSTEM (BS3-D-19) and computed."""
    line = seat_line("O1", seats=seats, price=price, start="2026-09-01", end=end)
    body = seat_body(
        world.customers["C-09"], external_id=external_id, inception="2026-09-01", lines=[line]
    )
    booked = activated_contract(world.place, booked_contract(world.place, body, activate=False))
    computed(world.place, UUID(str(booked.combination_group["id"])))
    return UUID(str(booked.contract["id"]))


def _allocated(world: SeatWorld, group_id: UUID) -> dict[UUID, Decimal]:
    """Per contract, the allocated amount of the group's latest SUCCEEDED computation."""
    latest = world.place.rows(
        select(contract_computation.c.id)
        .where(
            contract_computation.c.combination_group_id == group_id,
            contract_computation.c.status == "SUCCEEDED",
        )
        .order_by(contract_computation.c.created_at.desc(), contract_computation.c.id.desc())
        .limit(1)
    )
    assert latest, "no successful computation"
    rows = world.place.rows(
        select(obligation_version.c.contract_id, obligation_version.c.allocated_amount)
        .join(contract_version, contract_version.c.id == obligation_version.c.contract_version_id)
        .where(contract_version.c.contract_computation_id == latest[0]["id"])
    )
    found: dict[UUID, Decimal] = {}
    for row in rows:
        key = UUID(str(row["contract_id"]))
        found[key] = found.get(key, Decimal(0)) + Decimal(row["allocated_amount"])
    return found


def _combine(world: SeatWorld) -> tuple[UUID, UUID, UUID]:
    first = _active(world, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    second = _active(world, "SF-ORD-10418", "10", "48000.00", "2027-08-31")
    proposed = post(
        world.app,
        GROUPS,
        world.place.author,
        {
            "contract_ids": [str(first), str(second)],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group = proposed.json()
    assert (
        group["status"],
        group["is_singleton"],
        group["criterion"],
        group["member_contract_ids"],
        group["proposal"]["action"],
        group["proposal"]["status"],
        sorted(group["proposal"]["contract_ids"]),
    ) == ("PROPOSED", False, "25_9_B", [], "JOIN", "DRAFT", sorted([str(first), str(second)]))
    group_id = UUID(group["id"])
    submitted = post(world.app, f"{GROUPS}/{group_id}/submit", world.place.author, {})
    assert submitted.status_code == 200, submitted.text
    shown = submitted.json()
    assert shown["status"] == "SUBMITTED"
    request = get(world.app, f"{APPROVALS}/{shown['approval_request_id']}", world.marcus).json()
    assert (
        request["subject"]["type"],
        [step["required_permission"] for step in request["steps"]],
    ) == (
        "COMBINATION_GROUP",
        ["contract.approve"],
    )
    approved = approve(world.app, shown["approval_request_id"], world.marcus)
    assert approved.status_code == 200, approved.text
    return first, second, group_id


def _last_event(world: SeatWorld, contract_id: UUID) -> dict[str, Any]:
    rows = world.place.rows(
        select(contract_event)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version.desc())
        .limit(1)
    )
    return rows[0]


def _current_group(world: SeatWorld, contract_id: UUID) -> UUID:
    rows = world.place.rows(
        select(combination_group_member.c.combination_group_id).where(
            combination_group_member.c.contract_id == contract_id,
            combination_group_member.c.valid_to_known_at.is_(None),
        )
    )
    (row,) = rows
    return UUID(str(row["combination_group_id"]))


def test_combination_by_approved_command_reruns_group(seats: SeatWorld) -> None:
    first, second, group_id = _combine(seats)
    for contract_id in (first, second):
        event = _last_event(seats, contract_id)
        assert (str(event["event_type"]), event["origin"], event["payload"]) == (
            "COMBINATION_CHANGED",
            "SYSTEM",
            {"combination_group_id": str(group_id), "action": "JOIN", "criterion": "25_9_B"},
        )
        assert _current_group(seats, contract_id) == group_id
        header = seats.place.rows(
            select(contract.c.combination_group_id).where(contract.c.id == contract_id)
        )
        assert UUID(str(header[0]["combination_group_id"])) == group_id
    shown = get(seats.app, f"{GROUPS}/{group_id}", seats.place.author).json()
    assert (shown["status"], sorted(shown["member_contract_ids"]), shown["proposal"]) == (
        "APPLIED",
        sorted([str(first), str(second)]),
        None,
    )
    # S02-R-09: the group is computed from its inception with both members in the fold. Relative
    # SSP of AVM-SEAT-MO at 2,400.00 per seat: 30 × 2,400 : 10 × 2,400 = 3 : 1 of the combined
    # 156,000.00, so 117,000.00 and 39,000.00 against the stated 108,000.00 and 48,000.00.
    allocated = _allocated(seats, group_id)
    assert allocated == {first: Decimal("117000.00"), second: Decimal("39000.00")}
    # The differences post in FY2026-P09. September revenue before: 108,000.00 × 30 ÷ 1,096 =
    # 2,956.20 and 48,000.00 × 30 ÷ 365 = 3,945.21; after: 117,000.00 × 30 ÷ 1,096 = 3,202.55 and
    # 39,000.00 × 30 ÷ 365 = 3,205.48. Credits are negative.
    latest = seats.place.rows(
        select(contract_computation.c.id)
        .where(
            contract_computation.c.combination_group_id == group_id,
            contract_computation.c.status == "SUCCEEDED",
        )
        .order_by(contract_computation.c.created_at.desc(), contract_computation.c.id.desc())
        .limit(1)
    )[0]["id"]
    joined = subledger_line.join(
        subledger_posting, subledger_posting.c.id == subledger_line.c.subledger_posting_id
    ).join(period, period.c.id == subledger_line.c.period_id)
    periods = seats.place.rows(
        select(period.c.period_key)
        .select_from(joined)
        .where(subledger_posting.c.contract_computation_id == latest)
        .distinct()
    )
    assert [row["period_key"] for row in periods] == ["FY2026-P09"]
    expected = {
        first: (Decimal("-246.35"), Decimal("-3202.55")),
        second: (Decimal("739.73"), Decimal("-3205.48")),
    }
    for contract_id, (difference, total) in expected.items():
        revenue = (
            subledger_line.c.contract_id == contract_id,
            subledger_line.c.account_role == "REVENUE",
        )
        posted_now = seats.place.scalar(
            select(func.coalesce(func.sum(subledger_line.c.amount_txn), 0))
            .select_from(joined)
            .where(subledger_posting.c.contract_computation_id == latest, *revenue)
        )
        posted_total = seats.place.scalar(
            select(func.coalesce(func.sum(subledger_line.c.amount_txn), 0)).where(*revenue)
        )
        assert (Decimal(posted_now), Decimal(posted_total)) == (difference, total), contract_id


def test_proposal_author_cannot_approve_through_a_delegate(
    seats: SeatWorld, clock: FrozenClock
) -> None:
    """Supervisor ruling R-41 (3) (04 §16.10 rev 1.104 "Deciders a subject excludes"; the
    judgement-author rule of T-CON-19; REQ-PLT-011 "across UI, API, delegation and role
    switching"). Ana writes a combination proposal and Tomas submits it, so Ana is not the
    request's preparer. Ana also holds ``contract.approve`` and delegates it to Dora, who holds no
    approval permission of her own: Dora's approval would be the author's, taken on her behalf —
    403 ``self-approval``, as for Ana in person and for both in a bulk approval — and the group
    stays SUBMITTED with no decision. The Controller, who did not write it, approves it."""
    app, tenant_id = seats.app, seats.place.tenant_id
    first = _active(seats, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    second = _active(seats, "SF-ORD-10418", "10", "48000.00", "2027-08-31")
    ana_member = colleague(tenant_id, "ana")
    for code in ("revenue_accountant", "revenue_reviewer"):
        assign(ana_member, code)
    ana = enrolled(app, clock, ana_member)
    tomas_member = colleague(tenant_id, "tomas")
    assign(tomas_member, "revenue_accountant")
    tomas = enrolled(app, clock, tomas_member)
    dora_member = colleague(tenant_id, "dora")
    assign(dora_member, "viewer")
    dora = enrolled(app, clock, dora_member)

    proposed = post(
        app,
        GROUPS,
        ana,
        {
            "contract_ids": [str(first), str(second)],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(proposed.json()["id"])
    submitted = post(app, f"{GROUPS}/{group_id}/submit", tomas, {})
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])

    now = clock.now()
    delegated = post(
        app,
        "/api/v1/approval-delegations",
        ana,
        {
            "delegate_membership_id": str(dora.member.membership_id),
            "permissions": ["contract.approve"],
            "valid_from": now.isoformat(),
            "valid_to": (now + timedelta(days=30)).isoformat(),
            "reason": "Out of office",
        },
    )
    assert delegated.status_code == 201, delegated.text
    detail = get(app, f"{APPROVALS}/{request_id}", dora)
    assert detail.status_code == 200 and detail.json()["can_decide"] is False, detail.text
    assert detail.json()["impact_preview"] is None  # a combination request carries no preview
    hashes = {"subject_content_sha256": detail.json()["subject"]["content_sha256"]}
    for approver in (dora, ana):
        refused = approve(app, request_id, approver)
        assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text
        assert refused.json()["detail"] == COMBINATION_AUTHOR_DETAIL
        bulk = post(
            app,
            f"{APPROVALS}/bulk-approve",
            approver,
            {"items": [{"approval_request_id": request_id, **hashes}]},
        )
        assert bulk.status_code == 200, bulk.text
        (result,) = bulk.json()["results"]
        # The item is refused and the request it names — readable to both — is still pending.
        assert (result["status"], result["problem"]["type"].rsplit("/", 1)[-1]) == (
            "PENDING",
            "self-approval",
        ), result
        assert result["problem"]["detail"] == COMBINATION_AUTHOR_DETAIL
    shown = get(app, f"{GROUPS}/{group_id}", ana).json()
    assert (shown["status"], shown["member_contract_ids"]) == ("SUBMITTED", [])
    pending = get(app, f"{APPROVALS}/{request_id}", tomas).json()
    assert [step["decisions"] for step in pending["steps"]] == [[]]
    # "Waiting for me" is ``can_decide`` (R-64 (4)): the request does not wait for the author,
    # who holds the step permission, nor for her delegate, and the list's total says the same;
    # it waits for the Controller.

    def waiting(actor: Any) -> tuple[list[str], str]:
        listed = get(app, APPROVALS, actor, {"assigned_to_me": "true", "count": "true"})
        assert listed.status_code == 200, listed.text
        return (
            [item["id"] for item in listed.json()["items"]],
            listed.headers["X-Erev-Total-Count"],
        )

    for approver in (dora, ana):
        assert waiting(approver) == ([], "0")
    assert waiting(seats.marcus) == ([request_id], "1")
    for contract_id in (first, second):
        assert str(_last_event(seats, contract_id)["event_type"]) != "COMBINATION_CHANGED"

    approved = approve(app, request_id, seats.marcus)
    assert approved.status_code == 200, approved.text
    applied = get(app, f"{GROUPS}/{group_id}", ana).json()
    assert (applied["status"], sorted(applied["member_contract_ids"])) == (
        "APPLIED",
        sorted([str(first), str(second)]),
    )


def test_cross_currency_combination_rejected(seats: SeatWorld) -> None:
    enabled = put(
        seats.app, "/api/v1/tenant-currencies", seats.marcus, {"currency_codes": ["USD", "EUR"]}
    )
    assert enabled.status_code == 200, enabled.text
    usd = booked_contract(
        seats.place,
        seat_body(
            seats.customers["C-09"],
            external_id="SF-ORD-10417",
            inception="2026-09-01",
            lines=[
                seat_line("O1", seats="30", price="108000.00", start="2026-09-01", end="2029-08-31")
            ],
        ),
        activate=False,
    )
    eur_line = {
        **seat_line("O1", seats="10", price="33000.00", start="2026-09-01", end="2027-08-31"),
        "total_price": {"amount": "33000.00", "currency": "EUR"},
    }
    eur = booked_contract(
        seats.place,
        {
            **seat_body(
                seats.customers["C-09"],
                external_id="SF-ORD-10419",
                inception="2026-09-01",
                lines=[eur_line],
            ),
            "transaction_currency": "EUR",
        },
        activate=False,
    )
    refused = post(
        seats.app,
        GROUPS,
        seats.place.author,
        {
            "contract_ids": [str(usd.contract["id"]), str(eur.contract["id"])],
            "criterion": "606-10-25-9(a)",
            "rationale": "Negotiated together.",
        },
    )
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert fields(refused) == [("contract_ids", "REQ-CON-019")]
    assert (
        seats.place.rows(
            select(combination_group.c.id).where(combination_group.c.is_singleton.is_(False))
        )
        == []
    )


def test_uncombine_only_as_approved_error_correction(seats: SeatWorld) -> None:
    first, second, group_id = _combine(seats)
    head = int(
        seats.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == second))
    )
    direct = post(
        seats.app,
        EVENTS.format(contract_id=second),
        seats.place.author,
        {
            "events": [
                {
                    "event_type": "COMBINATION_CHANGED",
                    "effective_date": "2026-09-10",
                    "payload": {"combination_group_id": str(group_id), "action": "LEAVE"},
                }
            ]
        },
        if_match=f'"s{head}"',
    )
    assert direct.status_code == 422, direct.text
    assert fields(direct) == [("events.0.event_type", "API-R-30")]

    path = f"{GROUPS}/{group_id}/submit"
    wrong = post(
        seats.app,
        path,
        seats.place.author,
        {"leave_contract_ids": [str(second)], "reason_code": "ERROR_CORRECTION"},
    )
    assert wrong.status_code == 422, wrong.text
    assert fields(wrong) == [("reason_code", "REASON_CODE_NOT_ALLOWED")]

    requested = post(
        seats.app,
        path,
        seats.place.author,
        {
            "leave_contract_ids": [str(second)],
            "reason_code": "DATA_CORRECTION",
            "comment": "SF-ORD-10418 was combined with the wrong order.",
        },
    )
    assert requested.status_code == 200, requested.text
    shown = requested.json()
    assert (shown["status"], shown["proposal"]["action"], shown["proposal"]["contract_ids"]) == (
        "APPLIED",
        "LEAVE",
        [str(second)],
    )
    approved = approve(seats.app, shown["approval_request_id"], seats.marcus)
    assert approved.status_code == 200, approved.text

    event = _last_event(seats, second)
    assert (str(event["event_type"]), event["payload"]) == (
        "COMBINATION_CHANGED",
        {"combination_group_id": str(group_id), "action": "LEAVE", "criterion": None},
    )
    singleton = _current_group(seats, second)
    code = seats.place.scalar(
        select(combination_group.c.code).where(combination_group.c.id == singleton)
    )
    contract_no = seats.place.scalar(select(contract.c.contract_no).where(contract.c.id == second))
    assert code == f"CG-{contract_no}"
    assert _current_group(seats, first) == group_id
    # S02-R-09: the member is computed in its own singleton group from its own inception.
    assert _allocated(seats, singleton) == {second: Decimal("48000.00")}
    assert date.fromisoformat(str(event["effective_date"])) >= date(2026, 9, 1)


def _dirty_groups(world: SeatWorld) -> dict[str, bool]:
    """Group code → whether ``dirty_since`` is set, for every group of the world."""
    rows = world.place.rows(select(combination_group.c.code, combination_group.c.dirty_since))
    return {str(row["code"]): row["dirty_since"] is not None for row in rows}


def test_combine_empty_group_dirty_1_a_group_left_without_a_member_is_not_left_dirty(
    seats: SeatWorld,
) -> None:
    """Item COMBINE-EMPTY-GROUP-DIRTY-1 (supervisor ruling of 2026-10-01; seen by lane F-CLO-B).
    A combination stamps ``dirty_since`` on the group a member comes from, and a group is cleared
    only by its next computation — which a group without members never has. Before the fix the
    two singleton groups stayed dirty for good after the join, and the combined group after
    every member had left it. A group the combination empties is cleared; a group that holds a
    contract is computed, and clean, as before."""
    first, second, group_id = _combine(seats)
    numbers = {
        contract_id: seats.place.scalar(
            select(contract.c.contract_no).where(contract.c.id == contract_id)
        )
        for contract_id in (first, second)
    }
    combined = str(
        seats.place.scalar(
            select(combination_group.c.code).where(combination_group.c.id == group_id)
        )
    )
    own = [f"CG-{numbers[first]}", f"CG-{numbers[second]}"]
    # The join: both singleton groups are left without a member, the combined group is computed.
    assert _dirty_groups(seats) == {own[0]: False, own[1]: False, combined: False}
    assert (
        seats.place.scalar(
            select(func.count())
            .select_from(combination_group_member)
            .where(
                combination_group_member.c.combination_group_id != group_id,
                combination_group_member.c.valid_to_known_at.is_(None),
            )
        )
        == 0
    )

    # Every member leaves: the combined group is the one left without a member.
    requested = post(
        seats.app,
        f"{GROUPS}/{group_id}/submit",
        seats.place.author,
        {
            "leave_contract_ids": [str(first), str(second)],
            "reason_code": "DATA_CORRECTION",
            "comment": "The two orders were combined by mistake.",
        },
    )
    assert requested.status_code == 200, requested.text
    approved = approve(seats.app, requested.json()["approval_request_id"], seats.marcus)
    assert approved.status_code == 200, approved.text
    assert (_current_group(seats, first), _current_group(seats, second)) != (group_id, group_id)
    assert _dirty_groups(seats) == {own[0]: False, own[1]: False, combined: False}
    # ... and each contract is computed in its own group again, from its own inception.
    assert _allocated(seats, _current_group(seats, first)) == {first: Decimal("108000.00")}
    assert _allocated(seats, _current_group(seats, second)) == {second: Decimal("48000.00")}


# D-98 candidate 101c (c): a BILLING event a member receives between the request and the decision.
BILLING = {
    "event_type": "BILLING_RECORDED",
    "effective_date": "2026-09-01",
    "payload": {
        "invoice_number": "INV-US-4101",
        "line_external_id": "INV-US-4101-1",
        "amount": {"amount": "1000.00", "currency": "USD"},
        "issue_date": "2026-09-01",
    },
}


def _append_billing(world: SeatWorld, contract_id: UUID) -> None:
    head = int(
        world.place.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
    )
    appended = post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        world.place.author,
        {"events": [BILLING]},
        if_match=f'"s{head}"',
    )
    # 201 appended, 202 API-S-Job when the compute is deferred (04 §16.3 API-S-EventAppend).
    assert appended.status_code in (201, 202), appended.text


def test_join_approval_is_stale_after_a_member_event(seats: SeatWorld) -> None:
    """04 §16.10 rev 1.49 (D-98 candidate 101c): the COMBINATION_GROUP subject content carries each
    proposal member's current group id and stream head, so an event appended to a member between
    the request and the decision voids the request STALE_SUBJECT (409 ``stale-approval``) — the
    join is never applied against rows the approver did not review. DB-bound, NOT RUN on l12."""
    first = _active(seats, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    second = _active(seats, "SF-ORD-10418", "10", "48000.00", "2027-08-31")
    proposed = post(
        seats.app,
        GROUPS,
        seats.place.author,
        {
            "contract_ids": [str(first), str(second)],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(proposed.json()["id"])
    submitted = post(seats.app, f"{GROUPS}/{group_id}/submit", seats.place.author, {})
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.json()["approval_request_id"]
    before = get(seats.app, f"{APPROVALS}/{request_id}", seats.marcus).json()
    head_before = int(
        seats.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == first))
    )
    _append_billing(seats, first)
    stale = approve(seats.app, request_id, seats.marcus)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval"), stale.text
    after = get(seats.app, f"{APPROVALS}/{request_id}", seats.marcus).json()
    assert (after["status"], after["void_reason"]) == ("VOIDED", "STALE_SUBJECT")
    # Batch #5 (main 020e5fd3) measured the former oracle wrong: the request KEEPS the hash the
    # approver reviewed (REQ-PLT-014; api/v1/approvals.py shows the stored `subject_content_sha256`)
    # — the void does not rewrite it. What changed is the member: its head advanced by the append,
    # and the void audit names the CURRENT content hash, which differs from the reviewed one.
    assert after["subject"]["content_sha256"] == before["subject"]["content_sha256"]
    assert (
        int(
            seats.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == first))
        )
        == head_before + 1
    )
    voids = seats.place.rows(
        select(audit_event.c.after).where(
            audit_event.c.object_id == UUID(str(request_id)),
            audit_event.c.action == "approval_request.void",
        )
    )
    assert [row["after"]["void_reason"] for row in voids] == ["STALE_SUBJECT"]
    assert voids[0]["after"]["subject_content_sha256"] != before["subject"]["content_sha256"]
    # on_voided closes the submitted group; neither member moved.
    shown = get(seats.app, f"{GROUPS}/{group_id}", seats.place.author).json()
    assert (shown["status"], shown["member_contract_ids"]) == ("REJECTED", [])
    assert _current_group(seats, first) != group_id and _current_group(seats, second) != group_id


def test_leave_approval_is_stale_after_a_member_event(seats: SeatWorld) -> None:
    """The LEAVE proposal's member appended between the request and the decision: 409
    ``stale-approval``, the request VOIDED STALE_SUBJECT, the member still in the group (the leave
    was not applied). DB-bound, NOT RUN on l12."""
    first, second, group_id = _combine(seats)
    requested = post(
        seats.app,
        f"{GROUPS}/{group_id}/submit",
        seats.place.author,
        {
            "leave_contract_ids": [str(second)],
            "reason_code": "DATA_CORRECTION",
            "comment": "SF-ORD-10418 was combined with the wrong order.",
        },
    )
    assert requested.status_code == 200, requested.text
    request_id = requested.json()["approval_request_id"]
    _append_billing(seats, second)
    stale = approve(seats.app, request_id, seats.marcus)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval"), stale.text
    after = get(seats.app, f"{APPROVALS}/{request_id}", seats.marcus).json()
    assert (after["status"], after["void_reason"]) == ("VOIDED", "STALE_SUBJECT")
    assert _current_group(seats, second) == group_id and _current_group(seats, first) == group_id
    shown = get(seats.app, f"{GROUPS}/{group_id}", seats.place.author).json()
    assert (shown["status"], shown["proposal"]) == ("APPLIED", None)


def test_create_submit_join_and_leave_apply_on_the_ruled_order(seats: SeatWorld) -> None:
    """D-98 candidate 101c (e): the real sequence under the reordered locks — create (201), submit
    (200), the JOIN applied on approval, then the LEAVE submitted (200) and applied on approval —
    every group row ascending, the proposal record between, the contracts last, the membership
    re-verified for equality. DB-bound, NOT RUN on l12."""
    first, second, group_id = _combine(seats)
    assert _current_group(seats, first) == group_id and _current_group(seats, second) == group_id
    joined = get(seats.app, f"{GROUPS}/{group_id}", seats.place.author).json()
    assert (joined["status"], sorted(joined["member_contract_ids"]), joined["proposal"]) == (
        "APPLIED",
        sorted([str(first), str(second)]),
        None,
    )
    requested = post(
        seats.app,
        f"{GROUPS}/{group_id}/submit",
        seats.place.author,
        {
            "leave_contract_ids": [str(second)],
            "reason_code": "DATA_CORRECTION",
            "comment": "SF-ORD-10418 was combined with the wrong order.",
        },
    )
    assert requested.status_code == 200, requested.text
    approved = approve(seats.app, requested.json()["approval_request_id"], seats.marcus)
    assert approved.status_code == 200, approved.text
    assert _current_group(seats, first) == group_id and _current_group(seats, second) != group_id
    remaining = get(seats.app, f"{GROUPS}/{group_id}", seats.place.author).json()
    assert (remaining["status"], remaining["member_contract_ids"], remaining["proposal"]) == (
        "APPLIED",
        [str(first)],
        None,
    )


def test_stale_basis_is_refused_under_the_locks_after_a_concurrent_append(seats: SeatWorld) -> None:
    """DG-KRN-APR-05 rev 1.40 (D-98 candidate 101d; Codex WAIT-FRESH-R2). T1 holds a member's
    group and contract on the ruled order and has appended HOLD_APPLIED (head H → H+1),
    uncommitted. T2 (the approval) passes ``decide``'s pre-lock basis check — under READ COMMITTED
    it sees the committed H — records the decision and enters ``apply_combination``, where it is
    observed waiting for T1's group row (participant-bound: T2's backend blocked by T1's backend).
    T1 commits. T2 acquires every lock, re-validates the basis under them, finds H+1 and is refused:
    409 ``stale-approval``, the request VOIDED STALE_SUBJECT, nothing applied. Before this slice T2
    applied the JOIN against H+1. DB-bound, NOT RUN on l12."""
    first = _active(seats, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    second = _active(seats, "SF-ORD-10418", "10", "48000.00", "2027-08-31")
    proposed = post(
        seats.app,
        GROUPS,
        seats.place.author,
        {
            "contract_ids": [str(first), str(second)],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(proposed.json()["id"])
    submitted = post(seats.app, f"{GROUPS}/{group_id}/submit", seats.place.author, {})
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    head_before = int(
        seats.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == first))
    )
    ctx = RequestContext(
        principal=system_principal(seats.place.tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="r-p5-lock-r3d",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=seats.place.clock.now(),
        format_locale="en-US",
    )
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["result"] = approve(seats.app, request_id, seats.marcus)
        except Exception as exc:  # noqa: BLE001 — surfaced by the assertions below
            outcome["error"] = exc

    place = seats.place
    with observing_checkouts() as backends:
        with unit_of_work(ctx, clock=place.clock, keyring=place.keyring, files=place.files) as t1:
            holder_pid = backend_pid(t1.session)
            # T1: the member's group, then its contract (DG-KRN-DB-08), HOLD_APPLIED appended.
            assert holds.apply_system_hold(t1, first, reason="R3d concurrent append") is not None
            request = threading.Thread(target=run, name="stale-approve")
            request.start()
            # T2 passed the pre-lock basis check on the committed H and now waits for a group row
            # T1 holds — witnessed on T2's own backend, blocked by T1's backend.
            # Integrated batch #6 (main 9e7d1031) saw T2's backend blocked by T1 in the approval
            # detail's attachments SELECT (approval_queries) instead of the group row. Cause found
            # (lane FIX-A; support/interleave.py): that text was T1's stale pg_stat_activity
            # snapshot — T2 was on the group row. The wait names the statement it expects and,
            # when it never comes, carries the pg_locks dump that names the lock natively.
            blocked_pid, blocked_in = await_lock_wait(
                t1.session,
                holder_pid=holder_pid,
                backends=backends,
                timeout=20.0,
                expect="combination_group",
            )
            assert blocked_pid != holder_pid and request.is_alive(), (blocked_pid, blocked_in)
            assert "combination_group" in blocked_in.lower(), blocked_in
            t1.commit()  # H+1 is now committed; T2 proceeds into its locks
        request.join(timeout=30)
    assert not request.is_alive() and "error" not in outcome, outcome
    response = outcome["result"]
    assert (response.status_code, slug(response)) == (409, "stale-approval"), response.text
    after = get(seats.app, f"{APPROVALS}/{request_id}", seats.marcus).json()
    assert (after["status"], after["void_reason"]) == ("VOIDED", "STALE_SUBJECT")
    assert (
        int(
            seats.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == first))
        )
        == head_before + 1
    )
    # Nothing applied: both members still in their singletons; on_voided closed the group.
    assert _current_group(seats, first) != group_id and _current_group(seats, second) != group_id
    shown = get(seats.app, f"{GROUPS}/{group_id}", seats.place.author).json()
    assert (shown["status"], shown["member_contract_ids"]) == ("REJECTED", [])


def test_two_approvals_over_the_same_singletons_take_the_groups_on_one_order(
    seats: SeatWorld,
) -> None:
    """P5-LOCK-R4 (Codex's OPEN residual of 101c — the cross-group schedule; DG-KRN-DB-08 rev
    1.36). Two units of work share TWO group rows only as two proposals over the same singletons:
    T1 and T2 both over [X, Y] (singletons SX, SY), both submitted. A holder locks the FIRST shared
    row on the ruled order, ``min(SX, SY)``; both approvals start and are each observed waiting for
    it on their OWN backends, blocked by the holder's backend, in a statement against
    ``combination_group`` (participant-bound, two distinct pids); the holder releases; both
    complete. Exactly one is 200 — its group APPLIED with X and Y current in it — and the other is
    412 ``precondition-failed`` REGROUPED: its ``_lock_groups_then_contracts`` revalidation, under
    every lock and before its own basis check, found X's group ≠ the singleton it observed; its
    request stays PENDING and its group SUBMITTED (the command rolled back). No 40P01 / 409
    ``lock-conflict`` in either. Which request wins is PostgreSQL's choice — the assertions are
    symmetric. Under UUIDv7 both targets are newer than the singletons; the target-lowest /
    -between positions are the CPU proof's (``tests/unit/test_activation_lock_order.py``,
    P5-LOCK-R4 section). DB-bound, NOT RUN on l12."""
    first = _active(seats, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    second = _active(seats, "SF-ORD-10418", "10", "48000.00", "2027-08-31")
    sx, sy = _current_group(seats, first), _current_group(seats, second)
    requests: dict[UUID, str] = {}
    for _ in range(2):
        proposed = post(
            seats.app,
            GROUPS,
            seats.place.author,
            {
                "contract_ids": [str(first), str(second)],
                "criterion": "606-10-25-9(b)",
                "rationale": "One package: both orders serve a single commercial objective.",
            },
        )
        assert proposed.status_code == 201, proposed.text
        group_id = UUID(proposed.json()["id"])
        submitted = post(seats.app, f"{GROUPS}/{group_id}/submit", seats.place.author, {})
        assert submitted.status_code == 200, submitted.text
        requests[group_id] = str(submitted.json()["approval_request_id"])
    t1, t2 = sorted(requests)
    assert len({sx, sy, t1, t2}) == 4

    def steps_of(request_id: str) -> list[tuple[int, str, list[Any]]]:
        shown = get(seats.app, f"{APPROVALS}/{request_id}", seats.marcus).json()
        return [(int(s["step_no"]), str(s["status"]), list(s["decisions"])) for s in shown["steps"]]

    # Codex production-20260921-1216 §1 R1: the governed step projection of a PENDING request is
    # the FIRST step ACTIVE and every later step WAITING (engine._insert_request; E-06) — captured
    # before any approval so the loser's exact projection can be compared afterwards.
    before_steps = {group_id: steps_of(requests[group_id]) for group_id in (t1, t2)}
    for projection in before_steps.values():
        assert [status for _, status, _ in projection] == ["ACTIVE"] + ["WAITING"] * (
            len(projection) - 1
        ), projection
        assert all(decisions == [] for _, _, decisions in projection), projection
    first_shared = min(sx, sy)  # the first row every one of the two lock sequences takes
    ctx = DbContext(tenant_id=seats.place.tenant_id, user_id=None, entity_scope="*")
    outcomes: dict[UUID, Any] = {}

    def run(group_id: UUID) -> None:
        try:
            outcomes[group_id] = approve(seats.app, requests[group_id], seats.marcus)
        except Exception as exc:  # noqa: BLE001 — surfaced by the assertions below
            outcomes[group_id] = exc

    threads = [
        threading.Thread(target=run, args=(group_id,), name=f"approve-{group_id}")
        for group_id in (t1, t2)
    ]
    started: list[threading.Thread] = []
    try:
        with observing_checkouts() as backends:
            with tenant_session(ctx) as holder:
                holder_pid = backend_pid(holder)
                repo.lock_group(holder, first_shared)
                for thread in threads:
                    thread.start()
                    started.append(
                        thread
                    )  # registered first: the cleanup joins it whatever follows
                # Integrated batch #6 (main 9e7d1031): PostgreSQL queues the second approval on
                # the TUPLE lock held by the first waiter, so it is blocked by that waiter, not by
                # the holder; the wait accepts the chain. The app's lock_timeout is 10 s
                # (db/session.py): a waiter held longer answers 55P03 (unmapped: 500) — the
                # release below comes well within it.
                # Integrated batch #7 (main 104a954c): the count had admitted a captured backend
                # reported blocked in a GET-side `SET TRANSACTION READ ONLY`; only waiters blocked
                # in the group-row statement count now. Cause found (lane FIX-A): no read-side
                # wait — the holder's stale pg_stat_activity snapshot (support/interleave.py).
                blocked = await_lock_waits(
                    holder,
                    holder_pid=holder_pid,
                    backends=backends,
                    count=2,
                    timeout=20.0,
                    expect="combination_group",
                )
                assert holder_pid not in blocked and all(t.is_alive() for t in started), blocked
                assert all("combination_group" in q.lower() for q in blocked.values()), blocked
                holder.rollback()  # both proceed: one takes the shared rows, the other waits
    finally:
        # Codex production-20260921-1155 §3 R1: the cleanup runs AFTER the holder has released or
        # unwound (the `with` blocks above exit first) and ATTEMPTS to join every approval that was
        # started (a timed join is an attempt, not a guarantee — Codex 1216) so that a timeout, a
        # query error or a failed assertion above does not by itself leave an API transaction
        # running into the fixture teardown; the original failure is preserved (no assertion here;
        # an unfinished thread is reported by the assertions below when nothing else failed).
        for thread in started:
            thread.join(timeout=60)
    assert len(started) == 2 and not any(thread.is_alive() for thread in started)
    assert not any(isinstance(outcome, Exception) for outcome in outcomes.values()), outcomes
    codes = {group_id: outcomes[group_id].status_code for group_id in (t1, t2)}
    assert sorted(codes.values()) == [200, 412], {k: outcomes[k].text for k in outcomes}
    winner = next(group_id for group_id, code in codes.items() if code == 200)
    loser = next(group_id for group_id, code in codes.items() if code == 412)
    assert slug(outcomes[loser]) == "precondition-failed", outcomes[loser].text
    assert locking.REGROUPED in outcomes[loser].text
    applied = get(seats.app, f"{GROUPS}/{winner}", seats.place.author).json()
    assert (applied["status"], sorted(applied["member_contract_ids"])) == (
        "APPLIED",
        sorted([str(first), str(second)]),
    )
    assert _current_group(seats, first) == winner == _current_group(seats, second)
    stale = get(seats.app, f"{GROUPS}/{loser}", seats.place.author).json()
    request = get(seats.app, f"{APPROVALS}/{requests[loser]}", seats.marcus).json()
    assert (stale["status"], stale["member_contract_ids"], request["status"]) == (
        "SUBMITTED",
        [],
        "PENDING",
    )
    # Codex 1155 §3 / 1216 §1 R1: the loser's pre-hook decision write was rolled back with its
    # command — its step projection is EXACTLY the pre-approval one (first step ACTIVE, later
    # steps WAITING, no decisions), step 1 current, and no decision row exists for its request.
    assert steps_of(requests[loser]) == before_steps[loser], (
        steps_of(requests[loser]),
        before_steps[loser],
    )
    assert request["current_step_no"] == 1, request
    assert (
        seats.place.scalar(
            select(func.count())
            .select_from(approval_decision)
            .where(approval_decision.c.approval_request_id == UUID(requests[loser]))
        )
        == 0
    )


def test_r64_a_draft_combination_proposal_is_changed_by_nobody(
    seats: SeatWorld, clock: FrozenClock
) -> None:
    """Supervisor ruling R-64 (7) (a) on the ``COMBINATION`` record (R-41 (3)): the author of a
    combination proposal — the creator of its judgement record — may not approve it. The record
    of a PROPOSED group names no contract, so every holder of ``judgement.create`` could rewrite
    it by ``PATCH /judgements/{id}`` and then approve their own text: Tomas holds both. R-64
    left the edit to Ana, who proposed it. Since item COMBINATION-PROPOSAL-DISCARD-1 (the
    supervisor's rulings of 2026-10-02; 04 T-CON-19 rev 1.289) the proposal of a group is
    edited by nobody — a correction is a discard and a new proposal, so that the group row
    the approver's request is made from and the record never part: Tomas's edit AND Ana's
    answer 409 with the sentence that names the road, and the proposal keeps her rationale,
    which he may then submit and another approver decides."""
    app, tenant_id = seats.app, seats.place.tenant_id
    first = _active(seats, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    second = _active(seats, "SF-ORD-10418", "10", "48000.00", "2027-08-31")
    ana_member = colleague(tenant_id, "ana")
    assign(ana_member, "revenue_accountant")
    ana = enrolled(app, clock, ana_member)
    tomas_member = colleague(tenant_id, "tomas")
    for code in ("revenue_accountant", "revenue_reviewer"):
        assign(tomas_member, code)
    tomas = enrolled(app, clock, tomas_member)

    rationale = "One package: both orders serve a single commercial objective."
    proposed = post(
        app,
        GROUPS,
        ana,
        {
            "contract_ids": [str(first), str(second)],
            "criterion": "606-10-25-9(b)",
            "rationale": rationale,
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = proposed.json()["id"]
    record_path = f"/api/v1/judgements/{proposed.json()['judgement_record_id']}"
    before = get(app, record_path, ana).json()
    assert before["status"] == "DRAFT"

    rewritten = patch(
        app,
        record_path,
        tomas,
        {"rationale": "Combine: the prices depend on each other."},
        if_match=None,
    )
    assert (rewritten.status_code, slug(rewritten)) == (409, "invalid-transition"), rewritten.text
    assert rewritten.json()["detail"] == PROPOSAL_NOT_EDITED
    own = patch(
        app, record_path, ana, {"rationale": rationale + " Negotiated together."}, if_match=None
    )
    assert (own.status_code, slug(own)) == (409, "invalid-transition"), own.text
    assert own.json()["detail"] == PROPOSAL_NOT_EDITED
    assert get(app, record_path, ana).json()["rationale"] == before["rationale"]

    # Positive controls: submission by another preparer; and the submitter, who holds the
    # approval permission, is the request's preparer and cannot decide.
    submitted = post(app, f"{GROUPS}/{group_id}/submit", tomas, {})
    assert submitted.status_code == 200, submitted.text
    refused = approve(app, str(submitted.json()["approval_request_id"]), tomas)
    assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text


def test_jdg_discard_1_the_proposal_of_a_combination_group_is_decided_with_its_group(
    seats: SeatWorld,
) -> None:
    """The discard of a judgement record (04 T-CON-19 rev 1.242; PRD SM-10) leaves the proposal
    of a combination group alone. The submission of a PROPOSED group reads the group's draft
    ``COMBINATION`` record: without it the group could not be submitted, and the draft is given
    up with its group, by the group's own discard (item COMBINATION-PROPOSAL-DISCARD-1). The
    record's discard answers 409 by name, the record stays a draft and the group is submitted."""
    first = _active(seats, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    second = _active(seats, "SF-ORD-10418", "10", "48000.00", "2027-08-31")
    author = seats.place.author
    proposed = post(
        seats.app,
        GROUPS,
        author,
        {
            "contract_ids": [str(first), str(second)],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    record_path = f"/api/v1/judgements/{proposed.json()['judgement_record_id']}"
    refused = post(seats.app, f"{record_path}/discard", author, {})
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert [
        (error["field"], error["rule_id"], error["message"]) for error in refused.json()["errors"]
    ] == [
        (
            "status",
            "DB-03",
            "This record is the proposal of a combination group. It is decided with its group.",
        )
    ]
    assert get(seats.app, record_path, author).json()["status"] == "DRAFT"
    submitted = post(seats.app, f"{GROUPS}/{proposed.json()['id']}/submit", author, {})
    assert (submitted.status_code, submitted.json()["status"]) == (200, "SUBMITTED"), submitted.text
