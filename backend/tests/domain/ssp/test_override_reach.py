"""An SSP override names a version its requester may read (item SSP-ENTITY-SCOPE-1, the override;
the supervisor's ruling of 2026-10-02 on this lane's sibling finding, reading (1); 04 §16.2
``request-ssp-override`` and T-REF-28 "Reach" rev 1.277; 03 REQ-SSP-006, REQ-PLT-012).

``POST /obligations/{id}/request-ssp-override`` asks ``contract.create`` for the contract's entity
and took any APPROVED version by its id. With the books scoped, a version of another entity's book
is one its requester can no longer list or read, and a command that accepted its id confirmed it:
the request's summary stated that book's code and the version's label.

The world is that of ``test_calculator_reach.py`` — AVM-US and AVM-DE, one ACTIVE contract of
each for AVM-PLAT-100, the workspace's book US-LIST with its approved version 2026-H1 — with the
book A-US-ONLY of AVM-US and its approved version US-2026. Dora is Revenue Accountant of AVM-DE
alone: ``contract.create`` and ``ssp.read`` for AVM-DE. The frozen clock reads
2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import approval_request, audit_event, contract, obligation
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import and_, func, select
from support.db import TestDatabase
from support.http import HttpResponse
from support.principals import Actor, colleague, enrolled
from support.reference import approve, assign, fields, post
from tests.domain.ssp.test_calculator import ENTERPRISE, SSP_BOOKS, VERSIONS, attach, submit
from tests.domain.ssp.test_calculator_reach import World as ReachWorld
from tests.domain.ssp.test_calculator_reach import built

OBLIGATIONS = "/api/v1/obligations"
APPROVALS = "/api/v1/approvals"
NOBODY = "00000000-0000-0000-0000-000000000000"
JUSTIFICATION = "Negotiated under another list; the order form cites it."
NOT_A_VERSION = (422, [("ssp_book_version_id", "REQ-SSP-006")])


@dataclass(frozen=True, slots=True)
class World:
    app: FastAPI
    reach: ReachWorld
    dora: Actor  # Revenue Accountant of AVM-DE alone
    de_obligation: UUID  # O1 of SF-ORD-30101, the contract of AVM-DE
    us_version: str  # US-2026, the approved version of A-US-ONLY, the book of AVM-US


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _everyone(world: ReachWorld) -> DbContext:
    return DbContext(tenant_id=world.base.tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> World:
    reach = built(app, keyring, clock, app_settings)
    maya = reach.maya
    book = post(
        app,
        SSP_BOOKS,
        maya,
        {"code": "A-US-ONLY", "name": "US only", "currency": "USD", "entity_code": "AVM-US"},
    )
    assert book.status_code == 201, book.text
    created = post(
        app,
        f"{SSP_BOOKS}/{book.json()['id']}/versions",
        maya,
        {
            "legacy_version_label": "US-2026",
            "effective_from_date": "2026-01-01",
            "methodology_label": "List-price study 2025",
        },
    )
    assert created.status_code == 201, created.text
    us_version = str(created.json()["id"])
    entry = {
        "product_code": ENTERPRISE,
        "currency": "USD",
        "method": "observable",
        "distinctness": "distinct",
        "ranges": [{"point_value": "132000.00"}],
    }
    stored = post(app, f"{VERSIONS}/{us_version}/entries", maya, {"entries": [entry]})
    assert stored.status_code == 200, stored.text
    attach(app, maya, us_version)
    submitted = submit(app, maya, us_version)
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, submitted.json()["approval_request_id"], reach.base.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    someone = colleague(reach.base.tenant_id, "dora")
    assign(someone, "revenue_accountant", entity_ids=[reach.entities["AVM-DE"]])
    with tenant_session(_everyone(reach), read_only=True) as session:
        de_obligation = session.execute(
            select(obligation.c.id)
            .select_from(
                obligation.join(
                    contract,
                    and_(
                        contract.c.tenant_id == obligation.c.tenant_id,
                        contract.c.id == obligation.c.contract_id,
                    ),
                )
            )
            .where(contract.c.external_id == "SF-ORD-30101")
        ).scalar_one()
    return World(
        app=app,
        reach=reach,
        dora=enrolled(app, clock, someone),
        de_obligation=UUID(str(de_obligation)),
        us_version=us_version,
    )


def told(response: HttpResponse) -> tuple[int, dict[str, Any]]:
    """What an answer tells its caller: the status and the body without the request's own id."""
    return response.status_code, {**response.json(), "instance": None}


def written(world: World) -> tuple[int, int]:
    """(``SSP_OVERRIDE`` requests, audit events of the obligation or of a request's submission)
    in the workspace: what a refused override must leave as it was."""
    with tenant_session(_everyone(world.reach), read_only=True) as session:
        requests = session.execute(
            select(func.count())
            .select_from(approval_request)
            .where(approval_request.c.subject_type == "SSP_OVERRIDE")
        ).scalar_one()
        events = session.execute(
            select(func.count())
            .select_from(audit_event)
            .where(
                (audit_event.c.object_id == world.de_obligation)
                | (audit_event.c.action == "approval_request.submit")
            )
        ).scalar_one()
    return int(requests), int(events)


def test_ssp_entity_scope_1_an_override_names_a_version_its_requester_may_read(
    world: World,
) -> None:
    """Dora, who holds ``contract.create`` and ``ssp.read`` for AVM-DE, names the approved version
    of AVM-US's book for her obligation: 422 on ``ssp_book_version_id``, member for member the
    answer to an id that names no version, and nothing is written — no request, no audit event
    of a submission. She names the approved version of the workspace's book and is answered her
    request; Maya, who reads every entity, names the version of AVM-US's book and is answered
    hers, as before.

    Fail-first: Dora was answered 200, and her request's summary stated ``A-US-ONLY US-2026``."""
    app = world.app
    path = f"{OBLIGATIONS}/{world.de_obligation}/request-ssp-override"

    def asked(actor: Actor, version_id: str) -> HttpResponse:
        body = {"ssp_book_version_id": version_id, "justification": JUSTIFICATION}
        return post(app, path, actor, body)

    before = written(world)
    unknown = asked(world.dora, NOBODY)
    assert (unknown.status_code, fields(unknown)) == NOT_A_VERSION, unknown.text
    hidden = asked(world.dora, world.us_version)
    assert told(hidden) == told(unknown), hidden.text
    assert written(world) == before

    # Positive controls. A version of a book of all entities is hers to name ...
    hers = asked(world.dora, world.reach.base.h1_id)
    assert hers.status_code == 200, hers.text
    assert set(hers.json()) == {"approval_request_id"}
    withdrawn = post(
        app,
        f"{APPROVALS}/{hers.json()['approval_request_id']}/withdraw",
        world.dora,
        {"comment": "Asked for the wrong half."},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    # ... and the member of every entity names the version of AVM-US's book, as before.
    whole = asked(world.reach.maya, world.us_version)
    assert whole.status_code == 200, whole.text
    assert written(world)[0] == before[0] + 2
