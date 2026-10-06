"""The usage period of a report, at every door (04 §16.3 "The usage period of a report", table
15.4-B ``USAGE_PERIOD_NOT_ENDED`` and T-CON-24, rev 1.320; PRD BR-REC-01, IMP-148; dev-guide
DG-KRN-EVT-02 rev 1.296; item USAGE-REPORT-PERIOD-ENDED-1; the supervisor's rulings of 2026-10-03).

A usage report states usage that has occurred: its usage period ends on or before the report's
date, the event's effective date. World: WLD-K-08 (``support.worlds.k08_ulvane``), one usage
obligation of 80,000.00 over 2026, the clock at 12 September 2026. The refused report is the one
measured on main 2498e096a: 50,000 calls rated 5,000.00 for 1 to 31 August, dated 24 August. It was
taken, its version was dated 24 August with the fee on a schedule line and in no remainder, and
every report at 31 August stated 21,739.73 where 26,739.73 stands
(``tests/domain/reports/test_usage_report_figures_db.py`` holds the figures). Here: each channel
that can send the report answers 422 by name and stores nothing; a report whose period has ended
is taken; a request stored below the route is stale at its approval. The pure rule is in
``tests/unit/events/test_usage_period.py``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    contract,
    contract_computation,
    contract_event,
    event_submission,
    job,
    subledger_line,
)
from erev_api.domain.contracts import events as contract_events
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.api_clients import access_approver, issued_client
from support.db import TestDatabase
from support.factories import Workspace
from support.http import HttpResponse, call
from support.reference import approve, assign, post, slug
from support.worlds import K08, ReportWorld, k08_ulvane

EVENTS = "/api/v1/contracts/{contract_id}/events"
RULE = "USAGE_PERIOD_NOT_ENDED"
SENTENCE = (
    "The usage period 01 Aug 2026 to 31 Aug 2026 ends after the report's date, 24 Aug 2026. A "
    "usage report states usage that has occurred: end the period on or before 24 Aug 2026."
)
FINDING = [("events.0.payload.usage_period_end", RULE, SENTENCE)]
FEE = Decimal("5000.00")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def k08(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> ReportWorld:
    world = k08_ulvane(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: `event.approve`
    return world


def _usage(start: str, end: str, *, day: str, royalty: bool | None = None) -> dict[str, Any]:
    """A usage report of 50,000 calls rated 5,000.00 for ``start`` to ``end``, dated ``day``."""
    payload: dict[str, Any] = {
        "obligation_key": "O1",
        "usage_period_start": start,
        "usage_period_end": end,
        "metric": "API_CALL",
        "quantity": "50000",
        "rated_amount": {"amount": "5000.00", "currency": "USD"},
    }
    if royalty is not None:
        payload["is_royalty_statement"] = royalty
    return {"event_type": "USAGE_REPORTED", "effective_date": day, "payload": payload}


# the report of the measurement: dated inside its usage period
INSIDE = _usage("2026-08-01", "2026-08-31", day="2026-08-24")


def _head(place: Workspace, contract_id: UUID) -> int:
    return int(
        place.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
    )


def _revenue(place: Workspace, contract_id: UUID) -> Decimal:
    """Revenue posted for the contract, as a positive figure (credits are stored negative)."""
    total = place.scalar(
        select(func.coalesce(func.sum(subledger_line.c.amount_txn), 0)).where(
            subledger_line.c.contract_id == contract_id,
            subledger_line.c.account_role == "REVENUE",
        )
    )
    return -Decimal(total)


def _stored(place: Workspace, contract_id: UUID) -> tuple[int | Decimal, ...]:
    """What a refused report must leave as it was: the contract's head and posted revenue, and
    the workspace's events, computations, event submissions, approval requests and jobs."""
    tables = (contract_event, contract_computation, event_submission, approval_request, job)
    counts = [int(place.scalar(select(func.count()).select_from(table))) for table in tables]
    return (_head(place, contract_id), _revenue(place, contract_id), *counts)


def _sent(world: ReportWorld, contract_id: UUID, item: dict[str, Any]) -> HttpResponse:
    """The request of a signed-in person, Maya."""
    return post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        world.maya,
        {"events": [item]},
        if_match=f'"s{_head(world.place, contract_id)}"',
    )


def _metered(world: ReportWorld, token: str, contract_id: UUID, item: dict[str, Any]) -> Any:
    """The request of the metering client."""
    return call(
        world.app,
        "POST",
        EVENTS.format(contract_id=contract_id),
        json={"events": [item]},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": f"k-{uuid4()}",
            "If-Match": f'"s{_head(world.place, contract_id)}"',
        },
    )


def _metering_token(world: ReportWorld) -> str:
    """API client ``svc-metering`` (PRD §2.5 integrations) with ``event.record`` and its token:
    Marcus requests the grant, Ada — a second Tenant Admin — approves it, Marcus issues the
    secret (supervisor ruling R-38 (iii))."""
    ada = access_approver(world.app, world.place.clock, world.marcus.member, "ada")
    client = issued_client(
        world.app,
        world.marcus,
        {"name": "svc-metering", "scopes": ["event.record", "contract.read"]},
        approver=ada,
    )
    issued = call(
        world.app,
        "POST",
        "/api/v1/oauth/token",
        data={"grant_type": "client_credentials"},
        auth=(client["client_id"], client["client_secret"]),
    )
    assert issued.status_code == 200, issued.text
    return str(issued.json()["access_token"])


def _findings(response: Any) -> list[tuple[str, str, str]]:
    return [
        (str(error["field"]), str(error["rule_id"]), str(error["message"]))
        for error in response.json()["errors"]
    ]


def test_the_metering_client_is_refused_by_name_and_nothing_is_appended(k08: ReportWorld) -> None:
    """An API client's report is appended at once (PRD ACT-10), so the door is the only place
    that can hold it: the report for 1 to 31 August dated 24 August answers 422 with the finding
    of table 15.4-B at its ``usage_period_end``, and the contract's head, revenue, events and
    computations are as they were. The same usage up to the report's date — 1 to 24 August — is
    taken and posts its fee.

    Measured before the rule: the first report answered 201 and posted 5,000.00."""
    place = k08.place
    contract_id = UUID(str(k08.contracts[K08].contract["id"]))
    token = _metering_token(k08)
    before = _stored(place, contract_id)

    refused = _metered(k08, token, contract_id, INSIDE)

    # the status first: without the rule this is an append's 201
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert _findings(refused) == FINDING
    assert _stored(place, contract_id) == before

    taken = _metered(k08, token, contract_id, _usage("2026-08-01", "2026-08-24", day="2026-08-24"))

    assert taken.status_code == 201, taken.text
    assert taken.json()["computation"]["status"] == "SUCCEEDED"
    assert _head(place, contract_id) == before[0] + 1
    assert _revenue(place, contract_id) == before[1] + FEE


@pytest.mark.parametrize("royalty", [None, True], ids=["usage report", "royalty statement"])
def test_a_person_is_refused_and_no_submission_is_stored(
    k08: ReportWorld, royalty: bool | None
) -> None:
    """A person's usage report waits for a second person (04 §16.3 "Manual events"); one whose
    period ends after its date does not get that far — 422 by name, no event submission, no
    approval request. The royalty statement is the same payload and is held alike."""
    place = k08.place
    contract_id = UUID(str(k08.contracts[K08].contract["id"]))
    before = _stored(place, contract_id)
    report = _usage("2026-08-01", "2026-08-31", day="2026-08-24", royalty=royalty)

    refused = _sent(k08, contract_id, report)

    # the status first: without the rule this is a submission's 201
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert _findings(refused) == FINDING
    assert _stored(place, contract_id) == before


def test_the_preview_is_refused_alike(k08: ReportWorld) -> None:
    """``POST /contracts/{id}/events/preview`` validates what the append would: the same 422,
    and no job is started for a report the route would refuse."""
    place = k08.place
    contract_id = UUID(str(k08.contracts[K08].contract["id"]))
    before = _stored(place, contract_id)

    refused = post(
        k08.app,
        EVENTS.format(contract_id=contract_id) + "/preview",
        k08.maya,
        {"events": [INSIDE]},
        if_match=f'"s{_head(place, contract_id)}"',
    )

    # the status first: without the rule this is the 202 of a dry run
    assert refused.status_code == 422, refused.text
    assert _findings(refused) == FINDING
    assert _stored(place, contract_id) == before


@pytest.mark.parametrize(
    ("start", "end", "day"),
    [
        ("2026-08-01", "2026-08-31", "2026-08-31"),
        ("2026-08-01", "2026-08-31", "2026-09-05"),
    ],
    ids=["dated at its period's end", "dated after it"],
)
def test_a_report_whose_period_has_ended_is_taken(
    k08: ReportWorld, start: str, end: str, day: str
) -> None:
    """Equal dates are accepted, and a report dated after its period's end is accepted as before
    the rule: the request waits, the second person approves, the fee is posted."""
    place = k08.place
    contract_id = UUID(str(k08.contracts[K08].contract["id"]))
    head, revenue = _head(place, contract_id), _revenue(place, contract_id)

    sent = _sent(k08, contract_id, _usage(start, end, day=day))

    assert sent.status_code == 201, sent.text
    approved = approve(k08.app, sent.json()["approval_request_id"], k08.priya)
    assert approved.status_code == 200, approved.text
    assert _head(place, contract_id) == head + 1
    assert _revenue(place, contract_id) == revenue + FEE


def test_a_request_stored_below_the_route_is_stale_at_its_approval(
    k08: ReportWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """04 T-CON-24 "Checked again where it is appended": the approval passes ``check_bounds``
    again, and with it the rule. A request stored without it — here with the rule switched off
    while the request is sent, as one stored before the rule — is voided as stale at its
    approval (409 ``stale-approval``, ``STALE_SUBJECT``): nothing is appended and no decision
    stands."""
    place = k08.place
    contract_id = UUID(str(k08.contracts[K08].contract["id"]))
    head, revenue = _head(place, contract_id), _revenue(place, contract_id)
    with monkeypatch.context() as without_the_rule:
        without_the_rule.setattr(
            contract_events, "usage_period_refusal", lambda start, end, effective: None
        )
        sent = _sent(k08, contract_id, INSIDE)
    assert sent.status_code == 201, sent.text
    stored = sent.json()

    stale = approve(k08.app, stored["approval_request_id"], k08.priya)

    # the status first: without the second check this approval answers 200 and posts the fee
    assert stale.status_code == 409, stale.text
    assert slug(stale) == "stale-approval"
    request_id = UUID(stored["approval_request_id"])
    (request,) = place.rows(select(approval_request).where(approval_request.c.id == request_id))
    assert (str(request["status"]), str(request["void_reason"])) == ("VOIDED", "STALE_SUBJECT")
    (submission,) = place.rows(
        select(event_submission).where(event_submission.c.id == UUID(stored["event_submission_id"]))
    )
    assert str(submission["status"]) == "VOIDED"
    assert not place.rows(
        select(approval_decision.c.id).where(approval_decision.c.approval_request_id == request_id)
    )
    assert (_head(place, contract_id), _revenue(place, contract_id)) == (head, revenue)
