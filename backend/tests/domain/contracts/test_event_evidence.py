"""The evidence files of a record of events (04 §16 API-S-EventAppend ``evidence_file_ids``;
T-PLT-29 "Binding"; 03 REQ-PLT-012; independent review of the platform security merge, ruling
R-111 (1), item FILE-BIND-READABLE-1).

World: ``support.factories.seat_world`` (AVM-US, AVM-SEAT-MO in US-LIST 2026-H1). Maya records
``BILLING_RECORDED`` on a booked contract through ``POST /contracts/{id}/events``.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import audit_event, contract
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support import upload_fixtures as fx
from support.db import TestDatabase
from support.factories import SeatWorld, booked_contract, seat_body, seat_line, seat_world
from support.http import HttpResponse, call
from support.principals import Actor, colleague, cookie_headers, sign_in, workspace
from support.reference import assign, fields, post, slug

EVENTS = "/api/v1/contracts/{contract_id}/events"
FILES = "/api/v1/files"
BILLING = {
    "event_type": "BILLING_RECORDED",
    "effective_date": "2026-09-01",
    "payload": {
        "invoice_number": "INV-US-4701",
        "line_external_id": "INV-US-4701-1",
        "amount": {"amount": "200.00", "currency": "USD"},
        "issue_date": "2026-09-01",
    },
}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files)


def _uploaded(app: FastAPI, actor: Actor, name: str, content: bytes) -> str:
    """``POST /files`` with purpose ``ATTACHMENT``; the file id."""
    stored = call(
        app,
        "POST",
        FILES,
        data={"purpose": "ATTACHMENT"},
        files={"file": (name, content, "application/pdf")},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert stored.status_code == 201, stored.text
    return str(stored.json()["id"])


def test_req_plt_012_the_evidence_of_an_event_is_a_file_its_recorder_may_read(
    world: SeatWorld,
) -> None:
    """``evidence_file_ids`` took any id: the ids went into the audit event of the record
    unchecked, so a member put a file they could not read — or an id that names nothing — on
    record as the evidence of their own event. Each id is bound as every caller-named file is
    (``file_access.bound``): a file that is missing and a file the recorder may not read are
    refused alike, by their place in the list, and nothing is recorded."""
    app, maya = world.app, world.place.author
    someone = colleague(world.place.tenant_id, "lena")
    assign(someone, "revenue_accountant")
    lena = workspace(app, someone, sign_in(app, someone.email))
    body = seat_body(
        world.customers["C-09"],
        external_id="SF-ORD-10700",
        inception="2026-09-01",
        lines=[seat_line("O001", seats="1", price="2400.00", start="2026-09-01", end="2027-08-31")],
    )
    contract_id = booked_contract(world.place, body, activate=False).contract["id"]
    path = EVENTS.format(contract_id=contract_id)

    def recorded_with(*file_ids: str) -> HttpResponse:
        return post(
            app,
            path,
            maya,
            {"events": [BILLING], "evidence_file_ids": list(file_ids)},
            if_match='"s1"',
        )

    def head() -> int:
        version = world.place.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
        return int(version)

    # Lena's upload, which nothing owns: only she reads it.
    theirs = _uploaded(app, lena, "delivery-note.pdf", fx.PDF + b"% lena\n")
    mine = _uploaded(app, maya, "delivery-note.pdf", fx.PDF + b"% maya\n")
    refused = recorded_with(theirs)
    unknown = recorded_with(str(uuid4()))
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert fields(refused) == [("evidence_file_ids[0]", "T-PLT-29")]
    assert refused.json()["errors"] == unknown.json()["errors"]
    # Each refused id is named by its place; a readable one beside it is not.
    mixed = recorded_with(mine, theirs)
    assert fields(mixed) == [("evidence_file_ids[1]", "T-PLT-29")]
    assert head() == 1

    # Positive control: her own upload is her evidence, and the audit event names it.
    recorded = recorded_with(mine)
    assert recorded.status_code in (200, 201, 202), recorded.text
    assert head() == 2
    details = world.place.rows(
        select(audit_event.c.detail).where(
            audit_event.c.object_id == contract_id,
            audit_event.c.action == "contract.record_events",
            audit_event.c.outcome == "SUCCESS",
        )
    )
    assert [row["detail"]["evidence_file_ids"] for row in details] == [[mine]]
