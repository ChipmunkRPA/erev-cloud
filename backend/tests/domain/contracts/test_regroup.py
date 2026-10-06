"""CTR-17 regroup — the BUILD_SPEC acceptance tests (BUILD_SPEC CTR-17 "Tests"; REQ-CON-012;
ENGINE_SPEC S06-R-27; D-98 140 Q-4). DB-bound: written for the lane database and recorded **not
run** in the CTR-17 slice. The K-02 world of ``support.factories`` supplies two seat contracts."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
import test_modifications as modification_flows
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    audit_event,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    modification,
    obligation,
    obligation_version,
    subledger_line,
)
from erev_api.domain.contracts import bundles, queries, regroup
from erev_api.enums import ContractEventType
from erev_api.events.payloads import BillingRecordedV1, MoneyIn
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.api_clients import access_approver, issued_client
from support.db import TestDatabase
from support.factories import (
    K02World,
    activated_contract,
    appended,
    booked_contract,
    computed,
    k02_body,
    k02_world,
)
from support.http import HttpResponse, call
from support.principals import sign_in
from support.principals import workspace as signed_in
from support.reference import approve, assign, fields, post, slug

CONTRACTS: Final = "/api/v1/contracts"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def k02(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K02World:
    world = k02_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    return world


def _two_line_body(world: K02World, external_id: str) -> dict[str, Any]:
    body = k02_body(world.customer_id)
    body["external_id"] = external_id
    body["lines"] = [
        {
            "obligation_key": key,
            "product_code": "AVM-SEAT-MO",
            "quantity": str(int(seats) * 24),
            "total_price": {"amount": price, "currency": "USD"},
            "start_date": "2026-01-01",
            "end_date": "2027-12-31",
        }
        for key, seats, price in (("O1", "60", "144000.00"), ("O2", "40", "96000.00"))
    ]
    return body


def _one_line_body(world: K02World, external_id: str) -> dict[str, Any]:
    """A target WITHOUT the moved key O2 (D-98 140-A7 TEST-REGROUP-IDENTITY-1; REGROUP-R2)."""
    body = _two_line_body(world, external_id)
    body["lines"] = [line for line in body["lines"] if line["obligation_key"] == "O1"]
    return body


def _draft(world: K02World, external_id: str, *, lines: str = "two") -> tuple[UUID, UUID]:
    body = (
        _two_line_body(world, external_id) if lines == "two" else _one_line_body(world, external_id)
    )
    booked = booked_contract(world.place, body, activate=False)
    return UUID(str(booked.contract["id"])), UUID(str(booked.combination_group["id"]))


def _computation_ids(world: K02World, contract_ids: list[UUID]) -> dict[UUID, Any]:
    return {
        UUID(str(row["id"])): row["latest_computation_id"]
        for row in world.place.rows(
            select(contract.c.id, contract.c.latest_computation_id).where(
                contract.c.id.in_(contract_ids)
            )
        )
    }


def _events(world: K02World, contract_id: UUID, kind: ContractEventType) -> list[dict[str, Any]]:
    return world.place.rows(
        select(contract_event)
        .where(
            contract_event.c.contract_id == contract_id, contract_event.c.event_type == kind.value
        )
        .order_by(contract_event.c.stream_version)
    )


def _written(world: K02World) -> tuple[int, ...]:
    """What a refused regroup leaves as it was: contracts, events, modifications and lines."""
    return tuple(
        len(world.place.rows(select(table.c.id)))
        for table in (contract, contract_event, modification, subledger_line)
    )


def test_regroup_before_posting_reruns_both(k02: K02World) -> None:
    """BUILD_SPEC CTR-17: ``POST /contracts/{id}/regroup {obligation_keys: ["O2"], comment}`` on a
    draft contract appends a ``REGROUPED`` ``OUT`` and ``IN`` pair sharing ``regroup_id`` and
    recomputes both contracts from inception (REQ-CON-012)."""
    source_id, source_group = _draft(k02, "SF-ORD-10002")
    target_id, target_group = _draft(k02, "SF-ORD-10003", lines="one")  # no O2 on the target
    computed(k02.place, source_group)
    computed(k02.place, target_group)
    prior = _computation_ids(k02, [source_id, target_id])  # TEST-REGROUP-RECOMPUTE-1
    (source_o2,) = k02.place.rows(
        select(obligation.c.id).where(
            obligation.c.contract_id == source_id, obligation.c.obligation_key == "O2"
        )
    )
    moved = post(
        k02.app,
        f"{CONTRACTS}/{source_id}/regroup",
        k02.place.author,
        {"obligation_keys": ["O2"], "target_contract_id": str(target_id), "comment": "Same order."},
    )
    assert moved.status_code == 201, moved.text
    out_id, in_id = (UUID(value) for value in moved.json()["modification_ids"])
    (out_event,) = _events(k02, source_id, ContractEventType.REGROUPED)
    (in_event,) = _events(k02, target_id, ContractEventType.REGROUPED)
    assert out_event["payload"]["direction"] == "OUT" and in_event["payload"]["direction"] == "IN"
    assert out_event["payload"]["regroup_id"] == in_event["payload"]["regroup_id"]
    assert out_event["payload"]["obligation_keys"] == ["O2"]
    assert out_event["payload"]["counterpart_contract_id"] == str(target_id)
    assert UUID(out_event["payload"]["modification_id"]) == out_id
    assert UUID(in_event["payload"]["modification_id"]) == in_id
    rows = {
        UUID(str(row["id"])): row
        for row in k02.place.rows(
            select(modification).where(modification.c.regroup_id.is_not(None))
        )
    }
    assert {str(rows[out_id]["status"]), str(rows[in_id]["status"])} == {"APPLIED"}
    assert rows[out_id]["approval_request_id"] is None  # nothing had posted: no request
    moved_obligation = k02.place.rows(
        select(obligation).where(
            obligation.c.contract_id == target_id, obligation.c.obligation_key == "O2"
        )
    )
    # TEST-REGROUP-IDENTITY-1: the target had no O2; the acquired row links to the exact source row
    assert len(moved_obligation) == 1
    assert moved_obligation[0]["regrouped_from_obligation_id"] == source_o2["id"]
    # TEST-REGROUP-RECOMPUTE-1: both contracts were computed before; each has a NEW computation
    # whose stream heads cover the new head (the paired REGROUPED event)
    latest = _computation_ids(k02, [source_id, target_id])
    assert all(
        latest[cid] is not None and latest[cid] != prior[cid] for cid in (source_id, target_id)
    )
    for cid in (source_id, target_id):
        head = k02.place.rows(select(contract.c.head_stream_version).where(contract.c.id == cid))[0]
        (computation,) = k02.place.rows(
            select(contract_computation.c.stream_heads).where(
                contract_computation.c.id == latest[cid]
            )
        )
        assert int(computation["stream_heads"][str(cid)]) == int(head["head_stream_version"])
    # D-98 140-A6 REGROUP-R1: the two drafts sit in two groups; the target group's bundle
    # reconstructs the move from the IN event's own lines (no source in its bundle) — the target's
    # computation carries an obligation version for O2, the source's no longer does.
    assert in_event["payload"]["lines"][0]["obligation_key"] == "O2"
    target_versions = k02.place.rows(
        select(obligation_version.c.obligation_key)
        .where(obligation_version.c.contract_id == target_id)
        .order_by(obligation_version.c.version_no.desc())
    )
    assert "O2" in {str(v["obligation_key"]) for v in target_versions}


def test_regroup_after_posting_is_refused(k02: K02World) -> None:
    """04 §16.1 ``regroup`` (c), rev 1.234; 03 REQ-CON-012 rev 1.136; item
    REGROUP-AFTER-POSTING-AMOUNT-1. Until the supervisor's ruling of 2026-10-01 this test was
    ``test_regroup_after_posting_creates_two_modifications`` and expected 201 with the DRAFT pair
    for ONE spanning request (D-98 140 Q-4) — a STALE EXPECTATION by that ruling. No test had
    taken such a pair to APPLIED. Measured end to end, the pair moved the remaining allocation of
    O2's latest version — 95,868.49 of 96,000.00 with 35,901.37 posted, not the remainder at the
    regroup's date; its ADD row, classified a separate contract, booked O2 a third time with its
    original service dates; and that contract's activation posted 35,852.19 for service the
    source had recognised already. The road is withdrawn from release 1.0: after a posting the
    command is refused before anything is written, whichever contract has posted."""
    maya = k02.place.author
    # The source is activated and computed so that a subledger line exists (a posting).
    source = booked_contract(k02.place, _two_line_body(k02, "SF-ORD-10002"), activate=False)
    activated = activated_contract(k02.place, source)
    source_id = UUID(str(activated.contract["id"]))
    computed(k02.place, UUID(str(activated.combination_group["id"])))
    assert k02.place.rows(
        select(subledger_line.c.id).where(subledger_line.c.contract_id == source_id)
    ), "the activated K-02 source posts at least one line"
    draft_target, _ = _draft(k02, "SF-ORD-10003", lines="one")  # no O2 on the target (R2)
    posted_target = booked_contract(k02.place, _one_line_body(k02, "SF-ORD-10004"), activate=False)
    activated_contract(k02.place, posted_target)
    posted_target_id = UUID(str(posted_target.contract["id"]))
    draft_source, draft_group = _draft(k02, "SF-ORD-10005")
    computed(k02.place, draft_group)
    before = _written(k02)
    sentence = (
        "{external_id} has posted. After a posting an obligation is moved between contracts by a "
        "modification of each: a removal on the one and an addition on the other, each with its "
        "own approval."
    )

    for moved_from, moved_to, named in (
        (source_id, draft_target, "SF-ORD-10002"),  # the world of this test until rev 1.30
        (source_id, posted_target_id, "SF-ORD-10002"),  # measured: active into active
        (draft_source, posted_target_id, "SF-ORD-10004"),  # measured: a draft into active
        (source_id, None, "SF-ORD-10002"),  # into a new contract
    ):
        body = {"obligation_keys": ["O2"], "comment": "Split order."}
        if moved_to is not None:
            body["target_contract_id"] = str(moved_to)
        refused = post(k02.app, f"{CONTRACTS}/{moved_from}/regroup", maya, body)
        # the status first: until the ruling the command answered 201 with the DRAFT pair
        assert refused.status_code == 409, refused.text
        assert slug(refused) == "invalid-transition"
        assert refused.json()["detail"] == sentence.format(external_id=named)
        assert fields(refused) == [("status", "DB-03")]
        assert _written(k02) == before


def test_regroup_r2_target_key_collision_is_refused_before_any_effect(k02: K02World) -> None:
    """D-98 140-A6 REGROUP-R2: the target already holds O2 (both bodies book O1 and O2), so the
    move is refused by name (REQ-CON-012) before any modification row or event exists."""
    source_id, source_group = _draft(k02, "SF-ORD-10002")
    target_id, target_group = _draft(k02, "SF-ORD-10003")
    computed(k02.place, source_group)
    computed(k02.place, target_group)
    refused = post(
        k02.app,
        f"{CONTRACTS}/{source_id}/regroup",
        k02.place.author,
        {"obligation_keys": ["O2"], "target_contract_id": str(target_id), "comment": "Collide."},
    )
    assert refused.status_code == 422, refused.text
    error = refused.json()["errors"][0]
    assert (error["field"], error["rule_id"]) == ("obligation_keys", "REQ-CON-012")
    assert "already has obligation O2" in error["message"]
    assert k02.place.rows(select(modification).where(modification.c.regroup_id.is_not(None))) == []
    assert _events(k02, source_id, ContractEventType.REGROUPED) == []
    assert _events(k02, target_id, ContractEventType.REGROUPED) == []


def test_a9_regroup_r4_an_acquired_obligation_without_booked_terms_is_refused_first(
    k02: K02World,
) -> None:
    """REGROUP-R4: O2 moved into B before posting exists on B without a booking line; moving it
    again FROM B is refused by name (TERMS_MISSING) before any write — no modification row, no
    event, no new target contract."""
    a_id, a_group = _draft(k02, "SF-ORD-10002")
    b_id, b_group = _draft(k02, "SF-ORD-10003", lines="one")
    computed(k02.place, a_group)
    computed(k02.place, b_group)
    first = post(
        k02.app,
        f"{CONTRACTS}/{a_id}/regroup",
        k02.place.author,
        {"obligation_keys": ["O2"], "target_contract_id": str(b_id), "comment": "Move once."},
    )
    assert first.status_code == 201, first.text
    rows_before = len(k02.place.rows(select(modification)))
    contracts_before = len(k02.place.rows(select(contract.c.id)))
    again = post(
        k02.app,
        f"{CONTRACTS}/{b_id}/regroup",
        k02.place.author,
        {"obligation_keys": ["O2"], "comment": "Move again to a new contract."},
    )
    assert again.status_code == 422, again.text
    error = again.json()["errors"][0]
    assert (error["field"], error["rule_id"]) == ("obligation_keys", "REQ-CON-012")
    assert "books no line O2" in error["message"]
    assert len(k02.place.rows(select(modification))) == rows_before
    assert len(k02.place.rows(select(contract.c.id))) == contracts_before  # no new target
    assert (
        len(_events(k02, b_id, ContractEventType.REGROUPED)) == 1
    )  # the IN of the first move only


def _discounted_partner_body(world: K02World, external_id: str) -> dict[str, Any]:
    """A one-line partner priced BELOW the SSP band — 1,440 increments at 120,000.00 (83.33 against
    the 90.00 low; SSP mid 100.00 → 144,000.00) — so combining it spreads a discount over the
    source's obligations: the joined group's allocation of O2 differs from the singleton's by
    construction (D-98 140-A14 REGROUP-R3 witness setup; Codex 2029 §4)."""
    body = _one_line_body(world, external_id)
    body["lines"][0]["total_price"] = {"amount": "120000.00", "currency": "USD"}
    return body


def _billing(world: K02World, contract_id: UUID, *, invoice: str, day: int) -> None:
    """One ``BILLING_RECORDED`` on O1 — an admitted event that changes the bundle's input hash
    (``InputBundle.sha256`` covers the events; CV-25) without touching the allocation."""
    (head,) = world.place.rows(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    appended(
        world.place,
        contract_id,
        int(head["head_stream_version"]),
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 9, day),
                payload=BillingRecordedV1(
                    invoice_number=invoice,
                    line_external_id="1",
                    obligation_key="O1",
                    amount=MoneyIn(amount="1000.00", currency="USD"),
                    issue_date=date(2026, 9, day),
                ),
                obligation_keys=("O1",),
            )
        ],
    )


def test_a9_regroup_r3_remaining_binds_the_current_group_not_an_old_singleton_version(
    k02: K02World, clock: FrozenClock
) -> None:
    """REGROUP-R3 (old-high vs current-low; D-98 140-A14 witness setup on Codex 2029 §4): the
    source's singleton group is computed three times over DEMONSTRABLY different inputs — booked,
    then activated, then billed: three distinct ``input_sha256`` values, none replayed, versions
    v1 … v3 — then the source joins a discounted partner (the joined group's first version carries
    a different O2 allocation) and is posted; the regroup's REMOVE line carries the joined group's
    remaining allocation, not the singleton's higher-numbered version. The expected rows are read at
    the production record cutoff (``bundles.record_cutoff`` = max(application clock, transaction
    timestamp), the rule ``regroup.py`` applies), not at the frozen application clock, which the
    server-stamped ``known_at`` of every persisted version exceeds."""
    source = booked_contract(k02.place, _two_line_body(k02, "SF-ORD-10002"), activate=False)
    source_id = UUID(str(source.contract["id"]))
    singleton_group = UUID(str(source.combination_group["id"]))
    hashes: list[str] = []
    _, _, first = computed(k02.place, singleton_group)  # v1: as booked
    assert first["replayed"] is False
    hashes.append(str(first["input_sha256"]))
    clock.advance(timedelta(minutes=1))
    activated_contract(
        k02.place, source, compute=False
    )  # CONTRACT_ACTIVATED appended, not computed
    _, _, second = computed(k02.place, singleton_group)  # v2: activated
    assert second["replayed"] is False
    hashes.append(str(second["input_sha256"]))
    clock.advance(timedelta(minutes=1))
    _billing(k02, source_id, invoice="INV-R3-1", day=10)
    _, _, third = computed(k02.place, singleton_group)  # v3: billed
    assert third["replayed"] is False
    hashes.append(str(third["input_sha256"]))
    assert len(set(hashes)) == 3  # hash-changing inputs, not three replays of one bundle
    clock.advance(timedelta(minutes=1))
    partner = booked_contract(
        k02.place, _discounted_partner_body(k02, "SF-ORD-10004"), activate=False
    )
    partner_id = UUID(str(partner.contract["id"]))
    grouped = post(
        k02.app,
        "/api/v1/combination-groups",
        k02.place.author,
        {
            "contract_ids": [str(source_id), str(partner_id)],
            "criterion": "606-10-25-9(a)",
            "rationale": "One deal.",
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
    joined_group = UUID(
        str(
            k02.place.rows(select(contract).where(contract.c.id == source_id))[0][
                "combination_group_id"
            ]
        )
    )
    assert joined_group != singleton_group
    # the approval computed the joined group (the source is ACTIVE, so it posts); an identical
    # bundle replays rather than adding a version
    computed(k02.place, joined_group)
    assert k02.place.rows(
        select(subledger_line.c.id).where(subledger_line.c.contract_id == source_id)
    )
    # the exact eligible current source (REGROUP-R3; A12 (6); A14): the source's CURRENT group,
    # the primary book, a contract version known at the PRODUCTION record cutoff — and the
    # persisted singleton versions carry HIGHER version numbers with a DIFFERENT remaining
    # allocation
    with k02.place.uow() as uow:
        primary = queries.primary_book(uow.session)
        cutoff = bundles.record_cutoff(uow.session, uow.now)
    assert cutoff >= k02.place.clock.now()
    joined_rows = k02.place.rows(
        select(
            obligation_version.c.id,
            obligation_version.c.version_no,
            obligation_version.c.remaining_allocation,
        )
        .select_from(
            obligation_version.join(
                contract_version,
                contract_version.c.id == obligation_version.c.contract_version_id,
            )
        )
        .where(
            obligation_version.c.contract_id == source_id,
            obligation_version.c.combination_group_id == joined_group,
            obligation_version.c.book_code == primary,
            obligation_version.c.obligation_key == "O2",
            contract_version.c.known_at <= cutoff,
        )
        .order_by(obligation_version.c.version_no.desc())
    )
    singleton_rows = k02.place.rows(
        select(
            obligation_version.c.id,
            obligation_version.c.version_no,
            obligation_version.c.remaining_allocation,
        )
        .where(
            obligation_version.c.contract_id == source_id,
            obligation_version.c.combination_group_id == singleton_group,
            obligation_version.c.book_code == primary,
            obligation_version.c.obligation_key == "O2",
        )
        .order_by(obligation_version.c.version_no.desc())
    )
    assert joined_rows and singleton_rows
    assert [row["version_no"] for row in singleton_rows] == [3, 2, 1]  # created, not assumed
    assert singleton_rows[0]["version_no"] > joined_rows[0]["version_no"]  # old-high vs current-low
    assert singleton_rows[0]["id"] != joined_rows[0]["id"]
    assert Decimal(str(singleton_rows[0]["remaining_allocation"])) != Decimal(
        str(joined_rows[0]["remaining_allocation"])
    )
    joined_remaining = joined_rows[0]["remaining_allocation"]
    target_id, _ = _draft(k02, "SF-ORD-10003", lines="one")
    # 04 §16.1 rev 1.234 (item REGROUP-AFTER-POSTING-AMOUNT-1): the after-posting pair is withdrawn
    # from release 1.0. Until the supervisor's ruling of 2026-10-01 the route answered 201 here and
    # this test read the amount from the pair's REMOVE line — a STALE EXPECTATION by that ruling.
    # The route refuses, and the binding REGROUP-R3 states is read where the pair read it.
    refused = post(
        k02.app,
        f"{CONTRACTS}/{source_id}/regroup",
        k02.place.author,
        {"obligation_keys": ["O2"], "target_contract_id": str(target_id), "comment": "Split."},
    )
    assert refused.status_code == 409, refused.text
    assert slug(refused) == "invalid-transition"
    (source_row,) = k02.place.rows(select(contract).where(contract.c.id == source_id))
    with k02.place.uow() as uow:
        bound = regroup._remaining(
            uow.session, source_row, ["O2"], book_code=primary, cutoff=cutoff
        )
    assert bound == {"O2": Decimal(str(joined_remaining))}


def test_mod_discard_1_a_regroup_pair_is_discarded_whole(
    k02: K02World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item MOD-DISCARD-1 (supervisor ruling R-118 (e)): the DRAFT pair of a regroup after posting
    (one ``regroup_id``, ONE spanning request; D-98 140 Q-4) is discarded whole or not at all —
    half a pair can never be submitted. Discarding either row voids both, each with its audit
    event, and no ``REGROUPED`` event is appended.

    04 §16.1 rev 1.234: release 1.0 refuses a regroup after a posting, so no route makes such a
    pair any more. The pair is made here as the route made it before the ruling (its refusal
    switched off for the one request): the discard of a pair stands for the pairs that exist."""
    source = booked_contract(k02.place, _two_line_body(k02, "SF-ORD-10002"), activate=False)
    activated = activated_contract(k02.place, source)
    source_id = UUID(str(activated.contract["id"]))
    target_id, _ = _draft(k02, "SF-ORD-10003", lines="one")
    computed(k02.place, UUID(str(activated.combination_group["id"])))
    with monkeypatch.context() as before_the_ruling:
        before_the_ruling.setattr(regroup, "_refuse_after_posting", lambda session, row: None)
        moved = post(
            k02.app,
            f"{CONTRACTS}/{source_id}/regroup",
            k02.place.author,
            {"obligation_keys": ["O2"], "target_contract_id": str(target_id), "comment": "Split."},
        )
    assert moved.status_code == 201, moved.text
    ids = [UUID(value) for value in moved.json()["modification_ids"]]
    assert len(ids) == 2

    discarded = post(k02.app, f"/api/v1/modifications/{ids[1]}/discard", k02.place.author, {})
    assert discarded.status_code == 200, discarded.text
    assert (discarded.json()["id"], discarded.json()["status"]) == (str(ids[1]), "VOIDED")
    rows = k02.place.rows(select(modification).where(modification.c.id.in_(ids)))
    assert {UUID(str(row["id"])): str(row["status"]) for row in rows} == dict.fromkeys(
        ids, "VOIDED"
    )
    audited = k02.place.rows(
        select(audit_event.c.object_id, audit_event.c.before, audit_event.c.after).where(
            audit_event.c.object_type == "modification",
            audit_event.c.action == "modification.discard",
        )
    )
    assert sorted(
        (str(row["object_id"]), row["before"], row["after"]) for row in audited
    ) == sorted((str(value), {"status": "DRAFT"}, {"status": "VOIDED"}) for value in ids)
    for contract_id in (source_id, target_id):
        assert _events(k02, contract_id, ContractEventType.REGROUPED) == []
    again = post(k02.app, f"/api/v1/modifications/{ids[0]}/discard", k02.place.author, {})
    assert again.status_code == 409, again.text


def test_regroup_before_posting_1_a_contract_that_is_not_a_draft_is_refused(k02: K02World) -> None:
    """Item REGROUP-BEFORE-POSTING-1 (04 §16.1 ``regroup``, rev 1.234; ENGINE_SPEC S06-R-27 rev
    1.148; REQ-CON-012 "through an approved command"). While neither contract has a posted line the
    pair is applied at once, without a request — which is right between two drafts, where nothing
    can post. The switch read posted lines alone: measured through the product, O2 (in service
    since 1 January) moved from a draft into an ACTIVE contract that had posted nothing yet was
    recognised at once — 18 lines, 35,901.37 of revenue for January to September — by one holder
    of ``modification.create``, with no activation and no modification approval. A regroup with a
    contract that is not a draft is refused before anything is written, whichever side it is on;
    a new target is not booked either."""
    maya = k02.place.author
    # ACTIVE since 1 January, its one line in service from 1 October: nothing has posted
    body = _one_line_body(k02, "SF-ORD-10003")
    body["lines"][0]["start_date"] = "2026-10-01"
    active = booked_contract(k02.place, body, activate=False)
    activated_contract(k02.place, active)
    active_id = UUID(str(active.contract["id"]))
    draft_id, draft_group = _draft(k02, "SF-ORD-10002")
    computed(k02.place, draft_group)
    assert not k02.place.rows(select(subledger_line.c.id))
    before = _written(k02)
    sentence = (
        "SF-ORD-10003 is active and has posted nothing yet. A regroup is applied at once only "
        "between two drafts: change SF-ORD-10003 with a modification, which is approved."
    )

    for source_id, key, target_id in (
        (draft_id, "O2", active_id),  # the measured road: into the active contract
        (active_id, "O1", draft_id),  # out of the active contract
        (active_id, "O1", None),  # out of the active contract, into a new one
    ):
        moved = {"obligation_keys": [key], "comment": "Same order."}
        if target_id is not None:
            moved["target_contract_id"] = str(target_id)
        refused = post(k02.app, f"{CONTRACTS}/{source_id}/regroup", maya, moved)
        # the status first: without the rule the pair is applied and answered 201
        assert refused.status_code == 409, refused.text
        assert slug(refused) == "invalid-transition"
        assert refused.json()["detail"] == sentence
        assert fields(refused) == [("status", "DB-03")]
        assert _written(k02) == before


def test_regroup_before_posting_1_the_pair_is_dated_the_entitys_current_date(
    k02: K02World, clock: FrozenClock
) -> None:
    """05 TZ-03: a command dates what it writes by the contracting entity's current date. AVM-US
    keeps America/New_York, four hours behind UTC in September: at 03:30 UTC on the 13th it is
    still the 12th there, and at 04:30 UTC the 13th. The pair was dated the UTC date."""
    for number, (now, today) in enumerate(
        (
            (datetime(2026, 9, 13, 3, 30, tzinfo=UTC), date(2026, 9, 12)),
            (datetime(2026, 9, 13, 4, 30, tzinfo=UTC), date(2026, 9, 13)),
        )
    ):
        clock.set(now)
        # the session of 12 September has reached its absolute limit (REQ-PLT-004)
        member = k02.place.author.member
        maya = signed_in(k02.app, member, sign_in(k02.app, member.email))
        source_id, source_group = _draft(k02, f"SF-ORD-1010{number}")
        target_id, target_group = _draft(k02, f"SF-ORD-1020{number}", lines="one")
        computed(k02.place, source_group)
        computed(k02.place, target_group)
        moved = post(
            k02.app,
            f"{CONTRACTS}/{source_id}/regroup",
            maya,
            {
                "obligation_keys": ["O2"],
                "target_contract_id": str(target_id),
                "comment": "Same order.",
            },
        )
        assert moved.status_code == 201, moved.text
        ids = [UUID(value) for value in moved.json()["modification_ids"]]
        rows = k02.place.rows(
            select(modification.c.effective_date).where(modification.c.id.in_(ids))
        )
        assert [row["effective_date"] for row in rows] == [today, today], now
        events = [
            *_events(k02, source_id, ContractEventType.REGROUPED),
            *_events(k02, target_id, ContractEventType.REGROUPED),
        ]
        assert [event["effective_date"] for event in events] == [today, today], now


# --- item REGROUP-PERMISSION-PRD-1 (04 §16.1 rev 1.263; PRD ACT-04 rev 1.179) ---------------------


def _client(k02: K02World, name: str, scopes: list[str]) -> str:
    """An API client whose scopes are scopes — its permissions (PRD PRS-08) — and its token.
    The scopes are an access grant (supervisor ruling R-38 (iii)): Marcus requests the client,
    a second Tenant Admin approves the grant, and Marcus issues its secret."""
    ada = access_approver(k02.app, k02.place.clock, k02.marcus.member, "ada")
    made = issued_client(k02.app, k02.marcus, {"name": name, "scopes": scopes}, approver=ada)
    issued = call(
        k02.app,
        "POST",
        "/api/v1/oauth/token",
        data={"grant_type": "client_credentials"},
        auth=(made["client_id"], made["client_secret"]),
    )
    assert issued.status_code == 200, issued.text
    return str(issued.json()["access_token"])


def _regrouped_by(k02: K02World, token: str, source_id: UUID, body: dict[str, Any]) -> HttpResponse:
    return call(
        k02.app,
        "POST",
        f"{CONTRACTS}/{source_id}/regroup",
        json=body,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"k-{uuid4()}"},
    )


def test_regroup_permission_prd_1_a_holder_of_contract_create_regroups_two_drafts(
    k02: K02World,
) -> None:
    """Item REGROUP-PERMISSION-PRD-1 (04 §16.1 regroup, rev 1.263; PRD ACT-04 rev 1.179; 04
    API-R-28). In release 1.0 the command moves obligations between two drafts, which is draft
    editing: whoever books and replaces drafts regroups two of them. The command asked
    modification.create instead — since CTR-17, against the PRD and against 04's own route
    row — so an integration client, which holds contract.create and no
    modification.create, booked two drafts and could not move a line between them. The two
    T-CON-06 rows are written all the same, by a caller who may not create a modification."""
    token = _client(k02, "svc-salesforce", ["contract.read", "contract.create"])
    source_id, source_group = _draft(k02, "SF-ORD-10002")
    target_id, target_group = _draft(k02, "SF-ORD-10003", lines="one")
    computed(k02.place, source_group)
    computed(k02.place, target_group)

    moved = _regrouped_by(
        k02,
        token,
        source_id,
        {"obligation_keys": ["O2"], "target_contract_id": str(target_id), "comment": "One order."},
    )

    # the status first: without the rule the client is answered 403
    assert moved.status_code == 201, moved.text
    ids = [UUID(value) for value in moved.json()["modification_ids"]]
    rows = k02.place.rows(
        select(modification.c.status, modification.c.created_by_kind).where(
            modification.c.id.in_(ids)
        )
    )
    assert [(str(row["status"]), str(row["created_by_kind"])) for row in rows] == [
        ("APPLIED", "API_CLIENT"),
        ("APPLIED", "API_CLIENT"),
    ]
    (moved_out,) = _events(k02, source_id, ContractEventType.REGROUPED)
    (moved_in,) = _events(k02, target_id, ContractEventType.REGROUPED)
    assert (str(moved_out["origin"]), str(moved_in["origin"])) == ("API", "API")
    # into a new contract as well: the booking of the new draft asks the same permission
    third_id, third_group = _draft(k02, "SF-ORD-10004")
    computed(k02.place, third_group)
    contracts = len(k02.place.rows(select(contract.c.id)))
    booked = _regrouped_by(
        k02, token, third_id, {"obligation_keys": ["O2"], "comment": "Its own order."}
    )
    assert booked.status_code == 201, booked.text
    assert len(k02.place.rows(select(contract.c.id))) == contracts + 1
    # the client is no preparer of modifications: the route of T-CON-06 still refuses it
    refused = call(
        k02.app,
        "POST",
        f"{CONTRACTS}/{target_id}/modifications",
        json=modification_flows._upgrade_body(),
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"k-{uuid4()}"},
    )
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text


def test_regroup_permission_prd_1_modification_create_alone_does_not_regroup(
    k02: K02World,
) -> None:
    """The other side of the same rule: a caller who may prepare modifications and may not create
    contracts does not regroup two drafts — 403, with nothing written. Until the rule this
    caller moved a line between two drafts it could neither book nor replace."""
    token = _client(k02, "svc-changes", ["contract.read", "modification.create"])
    source_id, source_group = _draft(k02, "SF-ORD-10002")
    target_id, target_group = _draft(k02, "SF-ORD-10003", lines="one")
    computed(k02.place, source_group)
    computed(k02.place, target_group)
    before = _written(k02)

    refused = _regrouped_by(
        k02,
        token,
        source_id,
        {"obligation_keys": ["O2"], "target_contract_id": str(target_id), "comment": "One order."},
    )

    # the status first: without the rule the pair is applied and answered 201
    assert refused.status_code == 403, refused.text
    assert slug(refused) == "forbidden"
    assert _written(k02) == before
