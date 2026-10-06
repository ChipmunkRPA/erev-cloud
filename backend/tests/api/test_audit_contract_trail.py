"""The events of one contract across object types (04 T-PLT-19 "Contract key", rev 1.154; dev-guide
DG-KRN-AUD-09; supervisor ruling R-108; item AUD-API-GAPS-1; PRD J-17.5).

World: ``support.factories.k02_world`` — contract A (K-02, ``SF-ORD-10002``) is booked, activated
and computed, then held and released, given an estimate with a version, a modification and a
policy override — a DRAFT row of the fixture's, submitted through the product, since release 1.0
creates none (04 T-CON-23 rev 1.322); contract B is a draft of the same customer, so booking it
raises a combination suggestion that names both, and a combination proposal names both as well.

The events are stored with the key (the first test), and ``GET /audit-events?contract_id=`` reads
them back across object types (the second): the modification, estimate and hold events of PRD
J-17.5 that ``object_type=contract&object_id=`` never answered. Owed with item
APR-REQUEST-REASON-1: the approval requests of the contract, a rejected and resubmitted one among
them (ruling R-108 (a) point 4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.audit import contract_key
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import audit_event, audit_event_contract
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import (
    K02World,
    activated_contract,
    booked_contract,
    computed,
    drafted_override,
    k02_seat_month_body,
    k02_world,
)
from support.reference import get, patch, post, slug

API = "/api/v1"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@dataclass(frozen=True, slots=True)
class Trail:
    world: K02World
    a: str  # the contract everything is done to
    b: str  # a draft of the same customer
    hold_id: str
    estimate_id: str
    estimate_version_id: str
    modification_id: str
    override_id: str
    group_id: str  # the proposed combination of a and b

    def events(self) -> list[dict[str, Any]]:
        """Every audit event of the workspace, oldest first."""
        return self.world.place.rows(
            select(
                audit_event.c.id,
                audit_event.c.action,
                audit_event.c.object_type,
                audit_event.c.object_id,
                audit_event.c.outcome,
                audit_event.c.detail,
            ).order_by(audit_event.c.chain_seq)
        )


def _names(event: dict[str, Any]) -> set[str]:
    """The contracts an event's key names."""
    detail = event["detail"]
    one = detail.get(contract_key.CONTRACT_ID)
    return {*([] if one is None else [one]), *detail.get(contract_key.CONTRACT_IDS, [])}


def _ok(response: Any, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    return body


def _etag(app: FastAPI, path: str, actor: Any) -> str:
    shown = get(app, path, actor)
    assert shown.status_code == 200, shown.text
    return str(shown.headers["etag"])


def _trail(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> Trail:
    world = k02_world(app, keyring, clock, files)
    place, maya = world.place, world.place.author
    booked = booked_contract(place, k02_seat_month_body(world.customer_id), activate=False)
    activated = activated_contract(place, booked)
    computed(place, UUID(str(activated.combination_group["id"])))
    a = str(activated.contract["id"])
    contract_path = f"{API}/contracts/{a}"

    draft = {
        **k02_seat_month_body(world.customer_id),
        "external_id": "TRAIL-B",
        "document_ref": "SO-TRAIL-B",
    }
    b = str(_ok(post(app, f"{API}/contracts", maya, draft), 201)["id"])

    hold = {"hold_type": "recognition", "reason": "Pending credit review."}
    _ok(
        post(
            app, f"{contract_path}/apply-hold", maya, hold, if_match=_etag(app, contract_path, maya)
        )
    )
    listed = _ok(get(app, f"{contract_path}/events", maya, {"limit": 200}))
    hold_id = str([i for i in listed["items"] if i["event_type"] == "HOLD_APPLIED"][-1]["id"])
    _ok(
        post(
            app,
            f"{contract_path}/release-hold",
            maya,
            {"hold_id": hold_id, "comment": "Credit review passed."},
            if_match=_etag(app, contract_path, maya),
        )
    )

    estimate = {
        "estimate_kind": "VARIABLE_CONSIDERATION",
        "element_code": "REBATE-1",
        "vc_element_type": "REBATE",
        "method": "MOST_LIKELY_AMOUNT",
    }
    estimate_id = str(_ok(post(app, f"{contract_path}/estimates", maya, estimate), 201)["id"])
    version = {
        "effective_date": "2026-09-30",
        "scenarios": [{"outcome": "Expected rebate", "amount": "1000.00"}],
        "unconstrained_amount": "1000.00",
        "most_conservative_amount": "1000.00",
        "constrained_amount": "1000.00",
        "rationale": "Rebate expected at the current run rate.",
    }
    created = post(app, f"{API}/estimates/{estimate_id}/versions", maya, version)
    estimate_version_id = str(_ok(created, 201)["id"])
    _ok(
        patch(
            app,
            f"{API}/estimate-versions/{estimate_version_id}",
            maya,
            {"rationale": "Rebate expected at the current run rate (revised)."},
            if_match=created.headers.get("ETag", '"r1"'),  # a created version is row version 1
        )
    )

    modification = {
        "effective_date": "2026-09-16",
        "kind": "CO_TERM",
        "reference": "SO-UPG-1",
        "lines": [
            {
                "obligation_key": "O2",
                "action": "ADD",
                "product_code": "AVM-SEAT-MO",
                "quantity_delta": "775",
                "consideration_delta": {"amount": "60000.00", "currency": "USD"},
                "start_date": "2026-09-16",
                "end_date": "2027-12-31",
            }
        ],
        "rationale": "Marrowby adds 50 seats for the remaining term.",
    }
    modification_id = str(
        _ok(post(app, f"{contract_path}/modifications", maya, modification), 201)["id"]
    )

    # Release 1.0 creates no policy override (04 T-CON-23 "Not offered in release 1.0", rev
    # 1.322): the DRAFT row is the fixture's, and the event that puts the object on the contract's
    # trail is the product's own submit.
    override_id = str(
        drafted_override(
            place,
            UUID(a),
            "step1.term_with_termination_rights",
            "STATED_TERM",
            rationale="The stated term governs; termination rights are not substantive.",
        )
    )
    _ok(post(app, f"{API}/policy-overrides/{override_id}/submit", maya, {"comment": "Ready"}))

    proposal = {
        "contract_ids": [a, b],
        "criterion": "606-10-25-9(a)",
        "rationale": "Negotiated as a package.",
    }
    group_id = str(_ok(post(app, f"{API}/combination-groups", maya, proposal), 201)["id"])
    return Trail(
        world=world,
        a=a,
        b=b,
        hold_id=hold_id,
        estimate_id=estimate_id,
        estimate_version_id=estimate_version_id,
        modification_id=modification_id,
        override_id=override_id,
        group_id=group_id,
    )


def test_every_event_of_a_contract_object_names_its_contract(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    trail = _trail(app, keyring, clock, files)
    events = trail.events()
    both = sorted([trail.a, trail.b])

    # No event of a contract's object is without a contract, and none names a stranger.
    for event in events:
        if event["object_type"] in contract_key.ALWAYS:
            assert _names(event), event
        assert _names(event) <= {trail.a, trail.b}, event
        several = event["detail"].get(contract_key.CONTRACT_IDS)
        assert several is None or (several == both and "contract_id" not in event["detail"]), event

    # What was done to A names A — whichever table the object is a row of.
    of_a = [event for event in events if trail.a in _names(event)]
    by_object = {(event["object_type"], str(event["object_id"])) for event in of_a}
    assert {
        ("contract_hold", trail.hold_id),
        ("estimate", trail.estimate_id),
        ("estimate_version", trail.estimate_version_id),
        ("modification", trail.modification_id),
        ("policy_override", trail.override_id),
        ("combination_group", trail.group_id),
    } <= by_object
    # ... and so do the facts, which store no object id: the booking, the obligations, the
    # stream appends, the computation and what it wrote, the postings.
    assert {
        "contract",
        "obligation",
        "contract_event",
        "combination_group_member",
        "contract_computation",
        "contract_version",
        "obligation_version",
        "schedule",
        "schedule_line",
        "subledger_posting",
        "subledger_line",
        "subledger_posting_seal",
    } <= {event["object_type"] for event in of_a if event["object_id"] is None}

    # One contract is stated as contract_id; B's own booking does not name A.
    assert {event["action"] for event in events if _names(event) == {trail.b}} >= {
        "contract.book",
        "contract_event.append",
    }
    for event in of_a:
        if event["object_type"] in ("contract_hold", "modification", "policy_override", "estimate"):
            assert event["detail"]["contract_id"] == trail.a, event

    # 04 T-PLT-48: the append wrote the key of every event a second time, as the rows the read
    # by contract goes through — one a contract, with the event's own sequence and id.
    links = trail.world.place.rows(
        select(
            audit_event_contract.c.contract_id,
            audit_event_contract.c.chain_seq,
            audit_event_contract.c.audit_event_id,
        )
    )
    assert sorted((str(link["contract_id"]), str(link["audit_event_id"])) for link in links) == (
        sorted((named, str(event["id"])) for event in events for named in _names(event))
    )
    assert len({(link["contract_id"], link["chain_seq"]) for link in links}) == len(links)

    # Events of several contracts: the combination proposal with its judgement record, and the
    # suggestion booking B raised (it names the two contracts it would combine).
    of_both = {event["action"] for event in events if _names(event) == {trail.a, trail.b}}
    assert {
        "combination_group.create",
        "judgement_record.create",
        "exception_item.create",
    } <= of_both


def _listed(trail: Trail, **params: str) -> list[dict[str, Any]]:
    """Every item of ``GET /audit-events`` under ``params``, page after page."""
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        query = {**params, "limit": "40", **({} if cursor is None else {"cursor": cursor})}
        page = _ok(get(trail.world.app, f"{API}/audit-events", trail.world.place.author, query))
        items += page["items"]
        cursor = page["next_cursor"]
        if cursor is None:
            return items


def test_the_contract_filter_answers_the_trail_across_object_types(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    trail = _trail(app, keyring, clock, files)
    stored = trail.events()
    naming_a = [str(event["id"]) for event in reversed(stored) if trail.a in _names(event)]
    naming_b = [str(event["id"]) for event in reversed(stored) if trail.b in _names(event)]
    assert len(naming_a) > 40 > 3 < len(naming_b) < len(naming_a)  # more than a page; B is a draft

    # Exactly the stored events that name the contract, newest first, whatever their object type.
    of_a = _listed(trail, contract_id=trail.a)
    assert [item["id"] for item in of_a] == naming_a
    assert [item["id"] for item in _listed(trail, contract_id=trail.b)] == naming_b
    # PRD J-17.5: the modification, the estimate version and the hold are on the trail, each
    # under its own object — and labelled with what a person calls it (04 §16.14 (d)).
    by_object = {(item["object_type"], item["object_id"]): item for item in of_a}
    assert {
        ("modification", trail.modification_id),
        ("estimate_version", trail.estimate_version_id),
        ("contract_hold", trail.hold_id),
        ("policy_override", trail.override_id),
        ("combination_group", trail.group_id),
    } <= set(by_object)
    modification = by_object[("modification", trail.modification_id)]
    assert modification["object_label"].startswith("MOD-"), modification["object_label"]
    assert by_object[("estimate_version", trail.estimate_version_id)]["object_label"] == (
        "REBATE-1 v1"
    )
    assert by_object[("contract_hold", trail.hold_id)]["object_label"] is None
    # The old way answers the events recorded on the contract row alone — none of those.
    on_the_row = _listed(trail, object_type="contract", object_id=trail.a)
    assert {item["object_type"] for item in on_the_row} == {"contract"}
    assert len(on_the_row) < len(of_a)

    # The other filters narrow the trail.
    holds = _listed(trail, contract_id=trail.a, object_type="contract_hold")
    assert {item["object_id"] for item in holds} == {trail.hold_id} and len(holds) == 2
    # An event of both contracts is on both trails; an event of B alone is not on A's.
    shared = {item["id"] for item in of_a} & set(naming_b)
    assert {by_id["action"] for by_id in of_a if by_id["id"] in shared} >= {
        "combination_group.create",
        "exception_item.create",
    }
    assert set(naming_b) - {item["id"] for item in of_a}
    counted = get(
        app,
        f"{API}/audit-events",
        trail.world.place.author,
        {"contract_id": trail.a, "count": "true"},
    )
    assert counted.headers["x-erev-total-count"] == str(len(naming_a))


def test_a_refused_attachment_on_a_contract_is_recorded_not_an_error(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """DG-KRN-AUTH-05 with DG-KRN-AUD-09: the attachment guard refuses a permission before it reads
    the subject, so its DENIED event names the subject it was asked for and no contract; the
    refusal is a 403 with its event, never an error for want of a key."""
    world = k02_world(app, keyring, clock, files)
    booked = booked_contract(world.place, k02_seat_month_body(world.customer_id), activate=False)
    contract_id = str(booked.contract["id"])
    body = {"file_object_id": str(uuid4()), "subject_type": "contract", "subject_id": contract_id}
    refused = post(
        app, f"{API}/attachments", world.priya, body
    )  # an SSP Approver: no contract.create
    assert refused.status_code == 403, refused.text
    assert slug(refused) == "forbidden"
    (denied,) = world.place.rows(
        select(
            audit_event.c.action,
            audit_event.c.object_type,
            audit_event.c.object_id,
            audit_event.c.detail,
        ).where(audit_event.c.outcome == "DENIED")
    )
    assert (denied["action"], denied["object_type"], str(denied["object_id"])) == (
        "file_attachment.create",
        "contract",
        contract_id,
    )
    assert denied["detail"]["permission"] == "contract.create"
    assert not _names(denied)
