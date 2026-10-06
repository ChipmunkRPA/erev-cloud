"""Product pins, and the approved change of a product's policy values (security finding SN-7,
supervisor ruling R-21; 04 T-CON-07 ``pinned_refs.products``, T-REF-20, API-R-23 and §16.10 rev
1.110; dev-guide DG-KRN-REG-02 rev 1.93; 05 RCP-15 rev 1.49; POLICIES §0.5 rule 3 pin K, §0.6; 03
REQ-POL-003, REQ-POL-007, REQ-REF-012, REQ-REF-014; CTL-031).

The finding. ``PATCH /products/{id}`` stored ``policy_values`` for a ``masterdata.maintain`` holder
with no approval, and the bundle builder read the product row on every computation. The reviewer
set ``recognition.time_convention`` to ``MONTHLY_EVEN`` on the seat product of K-02 (100 seats × 24
months, 240,000.00 USD, ACTIVE with posted lines): the next recompute re-timed the contract from
10,191.78 / 9,205.48 / 10,191.78 to 10,000.00 a month and doubled its ledger lines.

The repair has two halves, both witnessed here on the database through the public routes:

- maker-checker: the direct edit is refused by name; the change goes through
  ``propose-policy-values-change`` and the approval of another ``config.approve`` holder;
- pin: a contract past DRAFT keeps the product state its computation recorded
  (``contract_computation.pinned_refs.products``), so the approved change reaches only contracts
  that leave DRAFT after it. A contract still DRAFT reads the product row — nothing of it posts,
  and a repaired product must reach it (REQ-REF-014) — and a group formed by an approved
  combination reads the pins of its members' former groups.

Pin K of a combined group (item PIN-K-COMBINATION-1, supervisor ruling R-112 (i); DG-KRN-REG-02
rev 1.143). The registry values a contract was first computed with are recorded on its version
(``contract_version.pinned_policies``) and read back from the group's previous version, but a group
formed by an approved combination has none: its first computation resolved every pin-K parameter
at the instant of the combination. SF-ORD-10417 (30 seats, 108,000.00), posted under
``ssp.outside_range_point`` ``NEAREST_BOUND``, was combined with an order activated after a tenant
version had taken that parameter to ``MIDPOINT``, and the group allocated 96,000.00 / 32,000.00
where the combination alone gives 100,571.43 / 27,428.57. The first version of a group now takes
the recorded values of a member's former group, in the order of the product pins.

Maya (Revenue Accountant, SSP Analyst) prepares; Marcus (Controller, SSP Approver, Tenant Admin;
MFA) approves. The CPU half is ``tests/unit/test_product_pin_members.py``.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    audit_event,
    combination_group,
    contract,
    contract_computation,
    contract_version,
    obligation_version,
    subledger_line,
)
from erev_api.enums import RegistryCategory
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import (
    K02World,
    SeatWorld,
    Workspace,
    activated_contract,
    booked_contract,
    computed,
    k02_body,
    k02_world,
    seat_body,
    seat_line,
    seat_world,
)
from support.principals import Actor
from support.reference import APPROVALS, approve, fields, get, patch, post, slug
from support.rows import publish_registry_version

PRODUCTS = "/api/v1/products"
CONTRACTS = "/api/v1/contracts"
GROUPS = "/api/v1/combination-groups"
SEAT = "AVM-SEAT-MO"
CONVENTION = "recognition.time_convention"  # POL-090: T, P; pin K; CFG
MONTHLY = {CONVENTION: "MONTHLY_EVEN"}
MID_MONTH = {CONVENTION: "MID_MONTH"}
POINT = "ssp.outside_range_point"  # POL-072: T, E, P; pin K
NEAREST_BOUND = {"level": "DEFAULT", "value": "NEAREST_BOUND", "source_id": "POL-072"}
RATIONALE = "Seat plans are sold and earned by whole months."
FIRST_QUARTER = ("FY2026-P01", "FY2026-P02", "FY2026-P03")
DAILY_AMOUNTS = ["10191.78", "9205.48", "10191.78"]  # 240,000.00 × days ÷ 730
MONTHLY_AMOUNTS = ["10000.00", "10000.00", "10000.00"]  # 240,000.00 ÷ 24


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def k02(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K02World:
    return k02_world(app, keyring, clock, files)


@pytest.fixture
def seats(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files)


def product_of(app: FastAPI, actor: Actor, code: str = SEAT) -> tuple[dict[str, Any], str]:
    """The product ``code`` as ``GET /products/{id}`` shows it, and its ETag."""
    listed = get(app, PRODUCTS, actor, {"q": code})
    assert listed.status_code == 200, listed.text
    (found,) = [item for item in listed.json()["items"] if item["code"] == code]
    shown = get(app, f"{PRODUCTS}/{found['id']}", actor)
    assert shown.status_code == 200, shown.text
    body: dict[str, Any] = shown.json()
    return body, shown.headers["ETag"]


def changed_by_request(
    app: FastAPI, proposer: Actor, approver: Actor, policy_values: dict[str, Any]
) -> str:
    """The seat product's policy values changed the approved way; returns the request id."""
    product, _ = product_of(app, proposer)
    proposed = post(
        app,
        f"{PRODUCTS}/{product['id']}/propose-policy-values-change",
        proposer,
        {"policy_values": policy_values, "rationale": RATIONALE},
    )
    assert proposed.status_code == 200, proposed.text
    request_id = str(proposed.json()["approval_request_id"])
    decided = approve(app, request_id, approver)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert product_of(app, proposer)[0]["policy_values"] == policy_values
    return request_id


def schedule(app: FastAPI, actor: Actor, contract_id: UUID) -> dict[str, str]:
    """The contract's revenue schedule: period key → amount."""
    listed = get(app, f"{CONTRACTS}/{contract_id}/schedule", actor, {"limit": 500})
    assert listed.status_code == 200, listed.text
    return {
        item["period"]["period_key"]: item["amount"]["amount"]
        for item in listed.json()["items"]
        if item["schedule_kind"] == "REVENUE"
    }


def first_quarter(app: FastAPI, actor: Actor, contract_id: UUID) -> list[str]:
    amounts = schedule(app, actor, contract_id)
    return [amounts[period_key] for period_key in FIRST_QUARTER]


def line_count(place: Workspace, contract_id: UUID) -> int:
    return int(
        place.scalar(
            select(func.count())
            .select_from(subledger_line)
            .where(subledger_line.c.contract_id == contract_id)
        )
    )


def pins(place: Workspace, group_id: UUID) -> dict[str, Any]:
    """``pinned_refs.products`` of the group's latest SUCCEEDED computation."""
    rows = place.rows(
        select(contract_computation.c.pinned_refs)
        .where(
            contract_computation.c.combination_group_id == group_id,
            contract_computation.c.status == "SUCCEEDED",
        )
        .order_by(contract_computation.c.created_at.desc(), contract_computation.c.id.desc())
        .limit(1)
    )
    found: dict[str, Any] = rows[0]["pinned_refs"]["products"]
    return found


def memo_edited(app: FastAPI, actor: Actor, contract_id: UUID) -> None:
    """The reviewer's trigger: a non-accounting command whose computation rebuilds the bundle."""
    shown = get(app, f"{CONTRACTS}/{contract_id}", actor)
    assert shown.status_code == 200, shown.text
    touched = post(
        app,
        f"{CONTRACTS}/{contract_id}/update-memos",
        actor,
        {"memo_1": "Renewal call booked", "comment": "Non-accounting memo edit"},
        if_match=shown.headers["ETag"],
    )
    assert touched.status_code == 200, touched.text


@pytest.mark.control("CTL-031")
def test_sn7_an_approved_product_change_does_not_reach_a_posted_contract(k02: K02World) -> None:
    """The inverted proof of concept, the approval witness and the positive control. K-02 is ACTIVE
    and posted under the daily convention. (1) The reviewer's direct edit is refused and writes
    nothing. (2) The same change by request needs Marcus's approval. (3) K-02 then recomputes — by
    the reviewer's memo edit and by a plain recompute — on its pin: same schedule, same ledger, no
    intent. (4) A contract booked after the approved change takes the monthly convention."""
    app, maya, marcus = k02.app, k02.place.author, k02.marcus
    active = activated_contract(
        k02.place, booked_contract(k02.place, k02_body(k02.customer_id), activate=False)
    )
    contract_id = UUID(str(active.contract["id"]))
    group_id = UUID(str(active.combination_group["id"]))
    before = schedule(app, maya, contract_id)
    assert [before[period_key] for period_key in FIRST_QUARTER] == DAILY_AMOUNTS
    posted = line_count(k02.place, contract_id)
    assert posted > 0
    pinned = pins(k02.place, group_id)
    assert set(pinned) == {SEAT}
    assert (
        pinned[SEAT]["policy_values"],
        pinned[SEAT]["default_template_code"],
        pinned[SEAT]["obligation_policies"][CONVENTION]["value"],
    ) == ({}, "TPL-SUB-DAILY", "DAILY")

    # (1) the direct edit of the proof of concept
    product, etag = product_of(app, maya)
    refused = patch(
        app, f"{PRODUCTS}/{product['id']}", maya, {"policy_values": MONTHLY}, if_match=etag
    )
    assert (refused.status_code, slug(refused), fields(refused)) == (
        422,
        "validation-failed",
        [(f"policy_values.{CONVENTION}", "REQ-POL-003")],
    )
    assert product_of(app, maya) == (product, etag)

    # (2) the change by request: proposed by Maya, pending until Marcus approves
    proposed = post(
        app,
        f"{PRODUCTS}/{product['id']}/propose-policy-values-change",
        maya,
        {"policy_values": MONTHLY, "rationale": RATIONALE},
    )
    assert proposed.status_code == 200, proposed.text
    request_id = str(proposed.json()["approval_request_id"])
    request = get(app, f"{APPROVALS}/{request_id}", marcus).json()
    assert (
        request["subject"]["type"],
        request["subject"]["id"],
        request["status"],
        request["summary"],
        [step["required_permission"] for step in request["steps"]],
    ) == (
        "PRINCIPAL_AGENT_CHANGE",
        product["id"],
        "PENDING",
        f"Policy values change for {SEAT}",
        ["config.approve"],
    )
    pending, _ = product_of(app, maya)
    assert (pending["policy_values"], pending["pending_approval_request_id"]) == ({}, request_id)
    # Maya holds no config.approve: her own proposal is not hers to decide.
    own = approve(app, request_id, maya)
    assert own.status_code == 403, own.text
    assert product_of(app, maya)[0]["policy_values"] == {}
    decided = approve(app, request_id, marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    changed, _ = product_of(app, maya)
    assert (
        changed["policy_values"],
        changed["pending_approval_request_id"],
        changed["row_version"],
    ) == (MONTHLY, None, product["row_version"] + 1)
    (event,) = k02.place.rows(
        select(audit_event.c.before, audit_event.c.after, audit_event.c.approval_request_id).where(
            audit_event.c.action == "product.policy_values_change"
        )
    )
    assert (event["before"], event["after"], str(event["approval_request_id"])) == (
        {"policy_values": {}},
        {"policy_values": MONTHLY},
        request_id,
    )

    # (3) the posted contract recomputes on its pin
    memo_edited(app, maya, contract_id)
    assert schedule(app, maya, contract_id) == before
    assert line_count(k02.place, contract_id) == posted
    bundle, output, _ = computed(k02.place, group_id)
    (seat,) = [item for item in bundle.group.products if item.code == SEAT]
    assert seat.policy_values == {}
    assert [intent for book in output.books for intent in book.posting_intents] == []
    assert schedule(app, maya, contract_id) == before
    assert line_count(k02.place, contract_id) == posted
    assert pins(k02.place, group_id) == pinned

    # (4) positive control: the next contract takes the approved value
    later_body = {
        **k02_body(k02.customer_id),
        "external_id": "SF-ORD-10003",
        "document_ref": "SF-ORD-10003",
    }
    later = activated_contract(k02.place, booked_contract(k02.place, later_body, activate=False))
    later_id = UUID(str(later.contract["id"]))
    assert first_quarter(app, maya, later_id) == MONTHLY_AMOUNTS
    later_pin = pins(k02.place, UUID(str(later.combination_group["id"])))[SEAT]
    assert (later_pin["policy_values"], later_pin["obligation_policies"][CONVENTION]["value"]) == (
        MONTHLY,
        "MONTHLY_EVEN",
    )
    assert first_quarter(app, maya, contract_id) == DAILY_AMOUNTS


def test_sn7_a_draft_contract_reads_the_product_until_it_is_activated(k02: K02World) -> None:
    """The pin starts where posting starts. While K-02 is DRAFT a computation pins nothing and the
    approved change of its product reaches it — the repair of a product must reach a draft
    (REQ-REF-014). The activation pins the product as it then is; a later approved change no
    longer reaches the contract."""
    app, maya, marcus = k02.app, k02.place.author, k02.marcus
    booked = booked_contract(k02.place, k02_body(k02.customer_id), activate=False)
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))
    bundle, _, _ = computed(k02.place, group_id)
    assert [item.policy_values for item in bundle.group.products] == [{}]
    assert pins(k02.place, group_id) == {}
    assert line_count(k02.place, contract_id) == 0

    changed_by_request(app, maya, marcus, MONTHLY)
    bundle, _, _ = computed(k02.place, group_id)
    assert [item.policy_values for item in bundle.group.products] == [MONTHLY]
    assert pins(k02.place, group_id) == {}

    activated_contract(k02.place, booked)
    assert first_quarter(app, maya, contract_id) == MONTHLY_AMOUNTS
    pinned = pins(k02.place, group_id)
    assert pinned[SEAT]["policy_values"] == MONTHLY
    posted = line_count(k02.place, contract_id)
    assert posted > 0

    changed_by_request(app, maya, marcus, {})
    bundle, output, _ = computed(k02.place, group_id)
    assert [item.policy_values for item in bundle.group.products] == [MONTHLY]
    assert [intent for book in output.books for intent in book.posting_intents] == []
    assert first_quarter(app, maya, contract_id) == MONTHLY_AMOUNTS
    assert line_count(k02.place, contract_id) == posted
    assert pins(k02.place, group_id) == pinned


def _seat_contract(
    world: SeatWorld,
    external_id: str,
    seat_count: str,
    price: str,
    end: str,
    start: str = "2026-09-01",
) -> UUID:
    """A C-09 seat contract from ``start``, activated and computed (its own group)."""
    line = seat_line("O1", seats=seat_count, price=price, start=start, end=end)
    body = seat_body(
        world.customers["C-09"], external_id=external_id, inception=start, lines=[line]
    )
    booked = activated_contract(world.place, booked_contract(world.place, body, activate=False))
    return UUID(str(booked.contract["id"]))


def _combined(world: SeatWorld, *contract_ids: UUID) -> UUID:
    """The contracts combined by the approved command (REQ-CON-009): Maya proposes and submits,
    Marcus approves, and the approval computes the group. Returns the group id."""
    app, maya = world.app, world.place.author
    proposed = post(
        app,
        GROUPS,
        maya,
        {
            "contract_ids": [str(contract_id) for contract_id in contract_ids],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(proposed.json()["id"])
    submitted = post(app, f"{GROUPS}/{group_id}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, submitted.json()["approval_request_id"], world.marcus)
    assert decided.status_code == 200, decided.text
    status = world.place.scalar(
        select(combination_group.c.status).where(combination_group.c.id == group_id)
    )
    assert str(status) == "APPLIED"
    return group_id


def _revenue(world: SeatWorld, contract_id: UUID) -> Decimal:
    return Decimal(
        world.place.scalar(
            select(func.coalesce(func.sum(subledger_line.c.amount_txn), 0)).where(
                subledger_line.c.contract_id == contract_id,
                subledger_line.c.account_role == "REVENUE",
            )
        )
    )


def test_sn7_a_combination_reads_the_pins_of_its_members_former_groups(seats: SeatWorld) -> None:
    """Two posted seat contracts, each pinned in its own group under the daily convention. The
    product is then changed by approval, and the contracts are combined by the approved command
    (REQ-CON-009). The combined group has no computation of its own yet: it reads the pins of its
    members' former groups, so the combination posts exactly the differences of the combination —
    September revenue 3,202.55 and 3,205.48, the figures of
    ``test_combination.py::test_combination_by_approved_command_reruns_group`` — and none of the
    monthly convention the product row holds by then."""
    app, maya, marcus = seats.app, seats.place.author, seats.marcus
    first = _seat_contract(seats, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    second = _seat_contract(seats, "SF-ORD-10418", "10", "48000.00", "2027-08-31")
    assert (_revenue(seats, first), _revenue(seats, second)) == (
        Decimal("-2956.20"),
        Decimal("-3945.21"),
    )
    changed_by_request(app, maya, marcus, MONTHLY)

    group_id = _combined(seats, first, second)
    assert (_revenue(seats, first), _revenue(seats, second)) == (
        Decimal("-3202.55"),
        Decimal("-3205.48"),
    )
    pinned = pins(seats.place, group_id)
    assert (
        pinned[SEAT]["policy_values"],
        pinned[SEAT]["obligation_policies"][CONVENTION]["value"],
    ) == ({}, "DAILY")
    bundle, output, _ = computed(seats.place, group_id)
    assert [item.policy_values for item in bundle.group.products] == [{}]
    assert [intent for book in output.books for intent in book.posting_intents] == []


@pytest.mark.parametrize(
    ("second_start", "second_end", "governing"),
    [("2026-09-01", "2027-08-31", {}), ("2026-08-01", "2027-07-31", MONTHLY)],
    ids=["same inception: the smaller external id", "the earlier inception"],
)
def test_sn7_a_pin_conflict_in_a_combination_goes_to_the_earliest_member(
    seats: SeatWorld, second_start: str, second_end: str, governing: dict[str, Any]
) -> None:
    """The conflict case. SF-ORD-10417 is posted and pinned under the daily convention; the
    product is changed by approval; SF-ORD-10418 is then activated and pinned under the monthly
    one. A group holds one state per product, so the combination takes the pin of the member with
    the earliest inception date, then the smallest external id: the first order's when both start
    on 1 September — the combination then posts the figures it posts without any product change —
    and the second order's when that one started on 1 August. Before the combination the product
    is changed once more, to a state neither member is pinned on, so that the governing state is
    a member's pin in both cases and never the product row. The approver of the combination is
    shown neither state: the request carries no impact preview (L4-1-Q-16), reported as a gap."""
    app, maya, marcus = seats.app, seats.place.author, seats.marcus
    first = _seat_contract(seats, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    changed_by_request(app, maya, marcus, MONTHLY)
    second = _seat_contract(seats, "SF-ORD-10418", "10", "48000.00", second_end, second_start)
    changed_by_request(app, maya, marcus, MID_MONTH)

    group_id = _combined(seats, first, second)
    pinned = pins(seats.place, group_id)
    assert set(pinned) == {SEAT}
    assert pinned[SEAT]["policy_values"] == governing
    bundle, output, _ = computed(seats.place, group_id)
    assert [item.policy_values for item in bundle.group.products] == [governing]
    assert [intent for book in output.books for intent in book.posting_intents] == []
    if not governing:
        assert (_revenue(seats, first), _revenue(seats, second)) == (
            Decimal("-3202.55"),
            Decimal("-3205.48"),
        )
    request = seats.place.rows(
        select(approval_request.c.impact_preview_file_id).where(
            approval_request.c.subject_type == "COMBINATION_GROUP",
            approval_request.c.subject_id == group_id,
        )
    )
    assert [row["impact_preview_file_id"] for row in request] == [None]


def test_sn7_an_uncombined_contract_computes_on_its_own_pin_again(seats: SeatWorld) -> None:
    """The way back. The two orders are combined, the product is changed by approval, and the
    second order is taken out of the group again as an approved data correction (REQ-CON-009).
    It returns to its own group, whose computations recorded the product under the daily
    convention, and the first order stays alone in the combined group: both compute on those
    pins — the stand-alone September revenue of 3,945.21 and 2,956.20 — and neither takes the
    monthly convention the product row holds by then."""
    app, maya, marcus = seats.app, seats.place.author, seats.marcus
    first = _seat_contract(seats, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    second = _seat_contract(seats, "SF-ORD-10418", "10", "48000.00", "2027-08-31")
    group_id = _combined(seats, first, second)
    changed_by_request(app, maya, marcus, MONTHLY)

    requested = post(
        app,
        f"{GROUPS}/{group_id}/submit",
        maya,
        {
            "leave_contract_ids": [str(second)],
            "reason_code": "DATA_CORRECTION",
            "comment": "SF-ORD-10418 was combined with the wrong order.",
        },
    )
    assert requested.status_code == 200, requested.text
    decided = approve(app, requested.json()["approval_request_id"], marcus)
    assert decided.status_code == 200, decided.text
    own_group = UUID(
        str(
            seats.place.scalar(
                select(contract.c.combination_group_id).where(contract.c.id == second)
            )
        )
    )
    assert own_group != group_id

    assert (_revenue(seats, first), _revenue(seats, second)) == (
        Decimal("-2956.20"),
        Decimal("-3945.21"),
    )
    for group in (group_id, own_group):
        pinned = pins(seats.place, group)
        assert (
            pinned[SEAT]["policy_values"],
            pinned[SEAT]["obligation_policies"][CONVENTION]["value"],
        ) == ({}, "DAILY")
        bundle, output, _ = computed(seats.place, group)
        assert [item.policy_values for item in bundle.group.products] == [{}]
        assert [intent for book in output.books for intent in book.posting_intents] == []


def _own_group(world: SeatWorld, contract_id: UUID) -> UUID:
    return UUID(
        str(
            world.place.scalar(
                select(contract.c.combination_group_id).where(contract.c.id == contract_id)
            )
        )
    )


def _policy_pin(world: SeatWorld, group_id: UUID) -> Any:
    """``pinned_policies`` of the group's latest contract version for POL-072."""
    rows = world.place.rows(
        select(contract_version.c.pinned_policies)
        .where(contract_version.c.combination_group_id == group_id)
        .order_by(contract_version.c.version_no.desc())
        .limit(1)
    )
    return rows[0]["pinned_policies"][POINT]


def _allocated(world: SeatWorld, group_id: UUID) -> dict[UUID, Decimal]:
    """The allocated amount per member contract on the group's latest version."""
    rows = world.place.rows(
        select(obligation_version.c.contract_id, obligation_version.c.allocated_amount)
        .join(contract_version, contract_version.c.id == obligation_version.c.contract_version_id)
        .where(contract_version.c.combination_group_id == group_id)
        .order_by(contract_version.c.version_no)
    )
    return {UUID(str(row["contract_id"])): Decimal(row["allocated_amount"]) for row in rows}


def _point_published(world: SeatWorld, value: str) -> dict[str, Any]:
    """A TENANT registry version takes POL-072 to ``value``, a minute after what was computed so
    far (``support.rows``, as the registry tests publish one). Returns the pin it gives."""
    world.place.clock.advance(timedelta(minutes=1))
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        version_id = publish_registry_version(
            session,
            tenant_id=world.place.tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            values={POINT: value},
            at=world.place.clock.now(),
        )
    return {"level": "T", "value": value, "source_id": str(version_id)}


@pytest.mark.parametrize("registry_changes", [False, True], ids=["no change", "MIDPOINT between"])
def test_pin_k_a_combined_group_keeps_the_values_of_its_earliest_member(
    seats: SeatWorld, registry_changes: bool
) -> None:
    """SF-ORD-10417 is posted and pinned under ``NEAREST_BOUND``. With or without a tenant
    version that takes the parameter to ``MIDPOINT`` before SF-ORD-10418 is activated, the
    combination allocates what the combination alone gives: both orders start on 1 September, so
    the first order's recorded values govern. A recompute of the group stays on them."""
    first = _seat_contract(seats, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    later = _point_published(seats, "MIDPOINT") if registry_changes else NEAREST_BOUND
    second = _seat_contract(seats, "SF-ORD-10418", "10", "20000.00", "2027-08-31")
    assert _policy_pin(seats, _own_group(seats, first)) == NEAREST_BOUND
    assert _policy_pin(seats, _own_group(seats, second)) == later

    group_id = _combined(seats, first, second)
    assert _policy_pin(seats, group_id) == NEAREST_BOUND
    assert _allocated(seats, group_id) == {
        first: Decimal("100571.43"),
        second: Decimal("27428.57"),
    }
    bundle, output, _ = computed(seats.place, group_id)
    assert [
        item.value
        for item in bundle.books[0].policies
        if (item.code, item.scope) == (POINT, "GROUP")
    ] == ["NEAREST_BOUND"]
    assert [intent for book in output.books for intent in book.posting_intents] == []
    assert _policy_pin(seats, group_id) == NEAREST_BOUND


def test_pin_k_the_earliest_inception_decides_before_the_external_id(seats: SeatWorld) -> None:
    """The other side of the order. SF-ORD-10418 starts on 1 August and is activated after the
    tenant version: its recorded ``MIDPOINT`` governs the combination with SF-ORD-10417, which
    started on 1 September under ``NEAREST_BOUND`` — 96,000.00 / 32,000.00, the midpoint
    allocation of 128,000.00 over 72,000.00 and 24,000.00. Before the combination the parameter
    changes once more, to a value neither order is pinned on, so the governing value is a
    member's recorded one and never what the registry answers at the combination."""
    first = _seat_contract(seats, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    midpoint = _point_published(seats, "MIDPOINT")
    second = _seat_contract(seats, "SF-ORD-10418", "10", "20000.00", "2027-07-31", "2026-08-01")
    assert _policy_pin(seats, _own_group(seats, first)) == NEAREST_BOUND
    assert _policy_pin(seats, _own_group(seats, second)) == midpoint
    _point_published(seats, "LOW_POINT")

    group_id = _combined(seats, first, second)
    assert _policy_pin(seats, group_id) == midpoint
    assert _allocated(seats, group_id) == {
        first: Decimal("96000.00"),
        second: Decimal("32000.00"),
    }
