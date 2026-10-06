"""An SSP book of an entity is read and commanded within that entity (item SSP-ENTITY-SCOPE-1;
supervisor ruling R-28, row N-29; 04 T-REF-28, API-R-26 and §16.4 rev 1.277; 03 REQ-PLT-012).

T-REF-28 to T-REF-31 are RLS-T, so nothing but the SSP reads and commands themselves knows the
entity a book is for. Measured before (lane F-RPS-REG's row 5 and this lane's probe): an SSP
Analyst of one entity listed the book of another with ``entity_code`` null, read its approved
prices, renamed it and created a DRAFT version on it; and ``GET /ssp/resolve`` answered her those
prices — also for her own entity — when that book's code sorted before the workspace's.

Maya is Revenue Accountant and SSP Analyst of all entities; Priya and Marcus approve. She makes
the entities AVM-US and AVM-DE, the book US-LIST of all entities (AVM-PLAT-100 at 85000 / 100000
/ 115000) and the book A-US-ONLY of AVM-US (10000 / 20000 / 30000), each with one approved
version. Ann is SSP Analyst of AVM-DE alone; Uma is SSP Analyst of AVM-US alone. Dana and Rhea
are SSP Analysts of AVM-DE who each hold one more permission for AVM-US through a role of that
permission alone — Dana ``contract.read``, Rhea ``ssp.read`` — so the session of each reads
AVM-US. The frozen clock reads 2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.http import HttpResponse
from support.principals import Actor, colleague, enrolled, member
from support.reference import (
    assign,
    calendar,
    delete,
    entity,
    fields,
    get,
    holding,
    new_product,
    patch,
    post,
    slug,
)
from support.rows import insert_custom_role
from tests.domain.ssp.test_resolution import (
    METHODOLOGY,
    PLATFORM,
    RESOLVE,
    SSP_BOOKS,
    VERSIONS,
    approved,
    new_book,
    observable,
)

WORKSPACE_PRICES = ("85000", "100000", "115000")
US_PRICES = ("10000", "20000", "30000")
NOBODY = "00000000-0000-0000-0000-000000000000"


@dataclass(frozen=True, slots=True)
class World:
    app: FastAPI
    maya: Actor
    ann: Actor  # SSP Analyst of AVM-DE alone
    uma: Actor  # SSP Analyst of AVM-US alone
    dana: Actor  # SSP Analyst of AVM-DE; contract.read alone for AVM-US
    rhea: Actor  # SSP Analyst of AVM-DE; ssp.read alone for AVM-US
    workspace_book: str  # US-LIST, a book of all entities
    workspace_version: str
    us_book: str  # A-US-ONLY, a book of AVM-US
    us_version: str


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> World:
    maya_member = member(keyring, clock)
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers: list[Actor] = []
    for name in ("priya", "marcus"):
        someone = colleague(maya_member.tenant_id, name)
        assign(someone, "ssp_approver")
        approvers.append(enrolled(app, clock, someone))
    new_product(app, maya, code=PLATFORM, name=PLATFORM)
    calendar_id = calendar(app, maya, years=(2026, 2027))
    entities = {
        code: UUID(str(entity(app, maya, code=code, calendar_id=calendar_id)["id"]))
        for code in ("AVM-US", "AVM-DE")
    }

    def version(book_id: str, label: str, prices: tuple[str, str, str]) -> str:
        """An approved version of the book with the product's one entry at ``prices``."""
        made = approved(
            app,
            maya,
            approvers,
            book_id,
            label=label,
            effective_from="2026-01-01",
            entries=[observable(PLATFORM, *prices)],
        )
        return str(made["id"])

    workspace_book = new_book(app, maya, code="US-LIST", name="US list prices", currency="USD")
    us_book = new_book(
        app, maya, code="A-US-ONLY", name="US only", currency="USD", entity_code="AVM-US"
    )
    workspace_version = version(workspace_book, "2026-H1", WORKSPACE_PRICES)
    us_version = version(us_book, "US-2026", US_PRICES)

    tenant_id = maya_member.tenant_id
    everyone = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(everyone) as session:
        for code, permission in (("only_contracts", "contract.read"), ("only_ssp", "ssp.read")):
            insert_custom_role(session, tenant_id=tenant_id, code=code, permissions=[permission])

    def analyst(name: str, entity_code: str, also: str | None = None) -> Actor:
        """An SSP Analyst of the entity; ``also`` is a role she holds for AVM-US beside it."""
        someone = colleague(tenant_id, name)
        assign(someone, "ssp_analyst", entity_ids=[entities[entity_code]])
        if also is not None:
            assign(someone, also, entity_ids=[entities["AVM-US"]])
        return enrolled(app, clock, someone)

    return World(
        app=app,
        maya=maya,
        ann=analyst("ann", "AVM-DE"),
        uma=analyst("uma", "AVM-US"),
        dana=analyst("dana", "AVM-DE", "only_contracts"),
        rhea=analyst("rhea", "AVM-DE", "only_ssp"),
        workspace_book=workspace_book,
        workspace_version=workspace_version,
        us_book=us_book,
        us_version=us_version,
    )


def told(response: HttpResponse) -> tuple[int, dict[str, Any]]:
    """What an answer tells its caller: the status and the body without the request's own id."""
    return response.status_code, {**response.json(), "instance": None}


def books_listed(world: World, actor: Actor) -> list[tuple[str, str | None]]:
    """(code, entity_code) of the books ``GET /ssp-books`` answers the actor, in code order."""
    found = get(world.app, SSP_BOOKS, actor, {"limit": "50"})
    assert found.status_code == 200, found.text
    return [(str(item["code"]), item["entity_code"]) for item in found.json()["items"]]


def prices(world: World, actor: Actor, version_id: str) -> list[tuple[Any, ...]]:
    """(low, mid, high) of each band of each entry the actor reads in the version."""
    found = get(world.app, f"{VERSIONS}/{version_id}/entries", actor, {"limit": "50"})
    assert found.status_code == 200, found.text
    return [
        (band["low_value"], band["mid_value"], band["high_value"])
        for item in found.json()["items"]
        for band in item["ranges"]
    ]


def book_reads(world: World, actor: Actor, book: str, version: str) -> dict[str, HttpResponse]:
    """The five reads of API-R-26 that name a book or one of its versions."""
    app = world.app
    return {
        "the book": get(app, f"{SSP_BOOKS}/{book}", actor),
        "its versions": get(app, f"{SSP_BOOKS}/{book}/versions", actor),
        "a version": get(app, f"{VERSIONS}/{version}", actor),
        "its entries": get(app, f"{VERSIONS}/{version}/entries", actor),
        "its diff": get(app, f"{VERSIONS}/{version}/diff", actor, {"against": version}),
    }


def test_ssp_entity_scope_1_a_book_of_an_entity_is_read_within_that_entity(world: World) -> None:
    """The reads. Ann, an SSP Analyst of AVM-DE alone, is listed the workspace's book and not
    the book of AVM-US; that book, its versions, its version, its entries and its diff answer her
    404, exactly as an id that names none. Uma, an SSP Analyst of AVM-US alone, and Maya read
    the book with its entity and its approved prices; all three read the workspace's book.

    Fail-first: Ann was listed the book of AVM-US with ``entity_code`` null and read its
    prices."""
    assert books_listed(world, world.ann) == [("US-LIST", None)]
    unknown = book_reads(world, world.ann, NOBODY, NOBODY)
    hidden = book_reads(world, world.ann, world.us_book, world.us_version)
    for what, answer in unknown.items():
        assert (answer.status_code, slug(answer)) == (404, "not-found"), (what, answer.text)
        assert told(hidden[what]) == told(answer), (what, hidden[what].text)

    # Positive controls: the member of AVM-US and the member of all entities read it whole; and
    # the workspace's book is read by all three.
    for actor in (world.uma, world.maya):
        assert ("A-US-ONLY", "AVM-US") in books_listed(world, actor)
        for what, found in book_reads(world, actor, world.us_book, world.us_version).items():
            assert found.status_code == 200, (what, found.text)
        assert prices(world, actor, world.us_version) == [US_PRICES]
    assert books_listed(world, world.uma) == [("A-US-ONLY", "AVM-US"), ("US-LIST", None)]
    for actor in (world.ann, world.uma, world.maya):
        assert prices(world, actor, world.workspace_version) == [WORKSPACE_PRICES]


def test_ssp_entity_scope_1_a_book_of_an_entity_is_commanded_within_that_entity(
    world: World,
) -> None:
    """The commands. Every command of API-R-26 that names the book of AVM-US, its version or an
    entry of it answers Ann 404, as it answers for an id that names none, and changes nothing;
    she makes no book for AVM-US. Uma, whose ``ssp.create`` covers AVM-US, renames the book and
    prepares a version on it; Maya does too. A book of all entities stays every preparer's.

    Fail-first: Ann renamed the book of AVM-US and created a DRAFT version on it."""
    app = world.app
    before = get(app, f"{SSP_BOOKS}/{world.us_book}", world.maya)
    etag = before.headers["ETag"]
    version_etag = get(app, f"{VERSIONS}/{world.us_version}", world.maya).headers["ETag"]
    version_body = {
        "legacy_version_label": "ANN-2027",
        "effective_from_date": "2027-01-01",
        "methodology_label": METHODOLOGY,
    }

    def commands(actor: Actor, book: str, version: str) -> Mapping[str, HttpResponse]:
        return {
            "PATCH book": patch(
                app, f"{SSP_BOOKS}/{book}", actor, {"name": "Renamed"}, if_match=etag
            ),
            "POST version": post(app, f"{SSP_BOOKS}/{book}/versions", actor, version_body),
            "PATCH version": patch(
                app,
                f"{VERSIONS}/{version}",
                actor,
                {"methodology_label": "Changed"},
                if_match=version_etag,
            ),
            "POST entries": post(
                app,
                f"{VERSIONS}/{version}/entries",
                actor,
                {"entries": [observable(PLATFORM, "1", "2", "3")]},
            ),
            "DELETE entry": delete(app, f"{VERSIONS}/{version}/entries/{NOBODY}", actor),
            "POST submit": post(
                app, f"{VERSIONS}/{version}/submit", actor, {"comment": None}, if_match=version_etag
            ),
            "POST withdraw": post(app, f"{VERSIONS}/{version}/withdraw", actor, {"comment": None}),
        }

    unknown = commands(world.ann, NOBODY, NOBODY)
    hidden = commands(world.ann, world.us_book, world.us_version)
    for what, answer in unknown.items():
        assert (answer.status_code, slug(answer)) == (404, "not-found"), (what, answer.text)
        assert told(hidden[what]) == told(unknown[what]), (what, hidden[what].text)
    # Nothing moved: the book, its one version and that version's prices.
    after = get(app, f"{SSP_BOOKS}/{world.us_book}", world.maya)
    assert (after.json()["name"], after.headers["ETag"]) == (before.json()["name"], etag)
    versions = get(app, f"{SSP_BOOKS}/{world.us_book}/versions", world.maya, {"limit": "50"})
    assert [item["legacy_version_label"] for item in versions.json()["items"]] == ["US-2026"]
    assert prices(world, world.maya, world.us_version) == [US_PRICES]
    # A book for an entity her permission does not cover: as an entity that does not exist.
    for code in ("AVM-US", "AVM-XX"):
        refused = post(
            app, SSP_BOOKS, world.ann, {"code": f"ANN-{code}", "name": "Hers", "entity_code": code}
        )
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
        assert fields(refused) == [("entity_code", "T-REF-28")]

    # Positive controls: the member of AVM-US renames the book and prepares a version on it ...
    renamed = patch(
        app, f"{SSP_BOOKS}/{world.us_book}", world.uma, {"name": "US prices"}, if_match=etag
    )
    assert (renamed.status_code, renamed.json()["name"]) == (200, "US prices"), renamed.text
    drafted = post(app, f"{SSP_BOOKS}/{world.us_book}/versions", world.uma, version_body)
    assert drafted.status_code == 201, drafted.text
    stored = post(
        app,
        f"{VERSIONS}/{drafted.json()['id']}/entries",
        world.uma,
        {"entries": [observable(PLATFORM, "11000", "21000", "31000")]},
    )
    assert stored.status_code == 200, stored.text
    # ... and Ann, whose entity the workspace's book also serves, prepares a version on that one,
    # and makes a book for her own entity.
    hers = post(app, f"{SSP_BOOKS}/{world.workspace_book}/versions", world.ann, version_body)
    assert hers.status_code == 201, hers.text
    own = post(
        app, SSP_BOOKS, world.ann, {"code": "DE-LIST", "name": "DE prices", "entity_code": "AVM-DE"}
    )
    assert (own.status_code, own.json()["entity_code"]) == (201, "AVM-DE"), own.text


def resolved(world: World, actor: Actor, entity_code: str | None) -> tuple[Any, ...]:
    """(status, book code, low, mid, high) of ``GET /ssp/resolve`` for AVM-PLAT-100 on
    2026-09-01 in USD at 96000.00, for the entity named or none."""
    params = {
        "product": PLATFORM,
        "date": "2026-09-01",
        "currency": "USD",
        "quantity": "1",
        "stated_price": "96000.00",
    }
    if entity_code is not None:
        params["entity"] = entity_code
    found = get(world.app, RESOLVE, actor, params)
    if found.status_code != 200:
        return (found.status_code, slug(found), *[field for field, _ in fields(found)])
    body = found.json()
    return (200, body["ssp_book_version"]["book_code"], body["low"], body["mid"], body["high"])


def test_ssp_entity_scope_1_the_resolve_read_answers_what_a_computation_takes(
    world: World,
) -> None:
    """``GET /ssp/resolve`` reads the approved versions under the tenant's scope, as the
    computation's bundle does, so a book's scope entity is the stored one whoever asks. The book
    of AVM-US is coded to sort before the workspace's — the order in which the engine's rule
    (S05-R-02: equal scope count, ascending code) took it for Ann, in whose session its entity
    read NULL. Ann is answered the workspace's book without an entity and for her own entity, as
    Maya is; AVM-US is no entity she can name, as an entity that does not exist is none. Uma and
    Maya are answered the book of AVM-US for AVM-US.

    Fail-first: Ann was answered 10000 / 20000 / 30000 — the approved prices of the book of
    AVM-US — without an entity and for AVM-DE."""
    workspace = (200, "US-LIST", *WORKSPACE_PRICES)
    us_only = (200, "A-US-ONLY", *US_PRICES)
    no_such_entity = (422, "validation-failed", "entity")
    for actor in (world.ann, world.maya):
        assert resolved(world, actor, None) == workspace
        assert resolved(world, actor, "AVM-DE") == workspace
    assert resolved(world, world.ann, "AVM-US") == no_such_entity
    assert resolved(world, world.ann, "AVM-XX") == no_such_entity
    # Positive controls: who may name AVM-US is answered its book; no one else's entity is hers.
    assert resolved(world, world.maya, "AVM-US") == us_only
    assert resolved(world, world.uma, "AVM-US") == us_only
    assert resolved(world, world.uma, None) == workspace
    assert resolved(world, world.uma, "AVM-DE") == no_such_entity


def test_ssp_entity_scope_1_reach_is_the_permissions_and_not_the_sessions(world: World) -> None:
    """The rule asks the permission, entity by entity — ``ssp.read`` for a read, ``ssp.create``
    for a command — and not what the caller's session reads. Dana is SSP Analyst of AVM-DE and
    holds ``contract.read`` alone for AVM-US: the row policy shows her that entity, and the book
    of AVM-US is still absent for her — not listed, 404, not hers to make a book for, and no
    entity she may name to the resolve read. Rhea is SSP Analyst of AVM-DE and holds
    ``ssp.read`` alone for AVM-US: she reads the book of AVM-US and is answered it by the
    resolve read, and a command on it answers her 404 and changes nothing — her ``ssp.create``
    covers AVM-DE.

    Fail-first: Dana was listed the book of AVM-US with its entity and read its prices, and the
    resolve read answered her that book for AVM-US; Rhea renamed it."""
    app = world.app
    workspace = (200, "US-LIST", *WORKSPACE_PRICES)
    us_only = (200, "A-US-ONLY", *US_PRICES)
    before = get(app, f"{SSP_BOOKS}/{world.us_book}", world.maya)
    etag = before.headers["ETag"]
    version_body = {
        "legacy_version_label": "RHEA-2027",
        "effective_from_date": "2027-01-01",
        "methodology_label": METHODOLOGY,
    }

    # Dana: her session reads AVM-US; no SSP permission of hers covers it.
    assert books_listed(world, world.dana) == [("US-LIST", None)]
    unknown = book_reads(world, world.dana, NOBODY, NOBODY)
    for what, answer in book_reads(world, world.dana, world.us_book, world.us_version).items():
        assert (answer.status_code, slug(answer)) == (404, "not-found"), (what, answer.text)
        assert told(answer) == told(unknown[what]), (what, answer.text)
    refused = post(
        app, SSP_BOOKS, world.dana, {"code": "DANA-US", "name": "Hers", "entity_code": "AVM-US"}
    )
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("entity_code", "T-REF-28")]
    assert resolved(world, world.dana, "AVM-US") == (422, "validation-failed", "entity")
    assert resolved(world, world.dana, "AVM-DE") == workspace

    # Rhea: her ``ssp.read`` covers AVM-US, her ``ssp.create`` does not.
    assert books_listed(world, world.rhea) == [("A-US-ONLY", "AVM-US"), ("US-LIST", None)]
    for what, found in book_reads(world, world.rhea, world.us_book, world.us_version).items():
        assert found.status_code == 200, (what, found.text)
    assert prices(world, world.rhea, world.us_version) == [US_PRICES]
    assert resolved(world, world.rhea, "AVM-US") == us_only
    answers = {
        "PATCH book": patch(
            app, f"{SSP_BOOKS}/{world.us_book}", world.rhea, {"name": "Renamed"}, if_match=etag
        ),
        "POST version": post(
            app, f"{SSP_BOOKS}/{world.us_book}/versions", world.rhea, version_body
        ),
    }
    for what, answer in answers.items():
        assert (answer.status_code, slug(answer)) == (404, "not-found"), (what, answer.text)
    after = get(app, f"{SSP_BOOKS}/{world.us_book}", world.maya)
    assert (after.json()["name"], after.headers["ETag"]) == (before.json()["name"], etag)
    versions = get(app, f"{SSP_BOOKS}/{world.us_book}/versions", world.maya, {"limit": "50"})
    assert [item["legacy_version_label"] for item in versions.json()["items"]] == ["US-2026"]
