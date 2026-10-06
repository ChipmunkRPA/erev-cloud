"""The workspace's own reference data under a role held for named entities (item
SCOPE-WORKSPACE-LISTS-1, part (d): "the tenant's settings by every road"; supervisor ruling R-28
and the supervisor's ruling of 2026-10-02 on lane F-RPS-REG's measurement; 03 REQ-PLT-012; 04
API-C-03, API-R-17, API-R-18; PRD ACT-44, BR-UX-06).

A legal entity that does not exist yet, a book and a fiscal calendar with its years belong to no
one entity: every entity keeps the book and computes into the year. Their commands ask
``masterdata.maintain`` or ``settings.manage`` for ALL entities. A command on one entity's row
— its name, the books it keeps — asks the permission FOR that entity, and keeping a book the
workspace has not enabled is the workspace's act again.

World (``W2``): ``worlds.ifrs_sw01`` — US01 keeps ASC606 and IFRS15; ``C-IFRS-SW01`` is computed
in both — and a second entity AVM-DE on the same calendar, made by Maya through the product. Maya
is Revenue Accountant of all entities. Dee is Revenue Accountant of AVM-DE alone; Una of US01
alone; Vera is Viewer of all entities and Revenue Accountant of AVM-DE alone; Dual is Auditor of
US01 and Revenue Accountant of AVM-DE; Odile is Auditor alone and holds neither permission. The
members' roles are assignment rows; each signs in with a second factor.

Measured before the head, with the same grants. Dee disabled the workspace's IFRS15 book — the
guard read the entities her session saw keep it: none — after which US01's contract was computed
in ASC606 alone; she generated FY2028, whose period states were written for AVM-DE alone, so that
an invoice of US01 dated 15 Jan 2028 was quarantined on CV-13; and by keeping the Legacy book for
AVM-DE she enabled it for the workspace. Vera created an entity. Dual and Vera renamed US01 and
stopped its IFRS15 book.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    audit_event,
    book,
    contract,
    contract_version,
    entity_book,
    legal_entity,
    period,
    period_state,
)
from erev_api.domain.reference import commands
from erev_api.enums import TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.uow import unit_of_work
from fastapi import FastAPI
from sqlalchemy import func, select
from support import worlds
from support.db import TestDatabase
from support.principals import Actor, colleague, enrolled
from support.reference import assign, calendar, entity, get, patch, post, put
from support.worlds import ReportWorld

API: Final = "/api/v1"
DE: Final = "AVM-DE"
PERMISSIONS: Final = "masterdata.maintain|settings.manage"
RULE: Final = "T-PLT-10"
# The sentences of the refusals, as the product says them (``domain.reference.commands``).
NAMED_ONLY: Final = "Your own access covers named entities only; an administrator of all entities"
NEW_ENTITY: Final = f"A new legal entity is the workspace's. {NAMED_ONLY} must create it."
BOOK: Final = (
    "A book is the workspace's, and every entity that keeps it follows a change. "
    f"{NAMED_ONLY} must make this change."
)
BOOK_NOT_ENABLED: Final = (
    "The Legacy book is not enabled for the workspace, and keeping it would enable it. "
    f"{NAMED_ONLY} must enable the book."
)
CALENDAR: Final = (
    "A fiscal calendar is the workspace's, and every entity on it follows a change. "
    f"{NAMED_ONLY} must make this change."
)
NOT_THIS_ENTITY: Final = (
    "Your access to maintain entities does not cover this entity. An administrator whose access "
    "covers it must make this change."
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@dataclass(frozen=True, slots=True)
class Settled:
    world: ReportWorld
    clock: FrozenClock
    calendar_id: str
    us_id: UUID
    de_id: UUID
    contract_id: UUID
    group_id: UUID

    @property
    def app(self) -> FastAPI:
        return self.world.app

    @property
    def maya(self) -> Actor:
        return self.world.maya

    def member(self, name: str, *grants: tuple[str, UUID | None]) -> Actor:
        """A member with one assignment row per grant — for the named entity, or for all
        entities where none is named — signed in with a second factor."""
        someone = colleague(self.world.tenant_id, name)
        for role_code, entity_id in grants:
            assign(someone, role_code, entity_ids=() if entity_id is None else [entity_id])
        return enrolled(self.app, self.clock, someone)


@pytest.fixture
def settled(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> Settled:
    world = worlds.ifrs_sw01(app, keyring, clock, files)
    calendar_id = str(
        world.place.scalar(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
        )
    )
    created = entity(
        app,
        world.maya,
        code=DE,
        calendar_id=calendar_id,
        functional_currency="USD",
        time_zone="Europe/Berlin",
    )
    booked = world.contracts[worlds.C_IFRS_SW01]
    return Settled(
        world=world,
        clock=clock,
        calendar_id=calendar_id,
        us_id=world.entity_id,
        de_id=UUID(str(created["id"])),
        contract_id=UUID(str(booked.contract["id"])),
        group_id=UUID(str(booked.combination_group["id"])),
    )


def slug(response: Any) -> str:
    body = response.json()
    return str(body.get("type", "")).rsplit("/", 1)[-1] if isinstance(body, dict) else ""


def denials(settled: Settled, actor: Actor) -> list[tuple[str, str, dict[str, Any]]]:
    """(action, object type, detail) of the member's ``DENIED`` events, oldest first."""
    rows = settled.world.place.rows(
        select(audit_event.c.action, audit_event.c.object_type, audit_event.c.detail)
        .where(audit_event.c.actor_id == actor.member.user_id, audit_event.c.outcome == "DENIED")
        .order_by(audit_event.c.chain_seq)
    )
    return [(str(row["action"]), str(row["object_type"]), dict(row["detail"])) for row in rows]


def refused_by_name(
    settled: Settled,
    actor: Actor,
    send: Any,
    *,
    sentence: str,
    action: str,
    object_type: str,
    all_entities: bool,
) -> None:
    """``send()`` is answered 403 ``forbidden`` with ``sentence`` under rule ``T-PLT-10``, after
    exactly one ``DENIED`` event under the command's action — its detail states the rule, the
    two permissions and, for an act on the workspace, the scope ``*``."""
    before = denials(settled, actor)
    answer = send()
    assert (answer.status_code, slug(answer)) == (403, "forbidden"), answer.text
    body = answer.json()
    assert body["detail"] == sentence, body
    assert [(error["rule_id"], error["message"]) for error in body["errors"]] == [(RULE, sentence)]
    added = denials(settled, actor)[len(before) :]
    scope = {"scope": "*"} if all_entities else {}
    assert added == [(action, object_type, {"rule_id": RULE, **scope, "permission": PERMISSIONS})]


def tenant_books(settled: Settled) -> dict[str, bool]:
    rows = settled.world.place.rows(select(book.c.code, book.c.is_enabled))
    return {str(row["code"]): bool(row["is_enabled"]) for row in rows}


def kept_books(settled: Settled) -> list[tuple[str, str, bool]]:
    rows = settled.world.place.rows(
        select(legal_entity.c.code, entity_book.c.book_code, entity_book.c.is_enabled).select_from(
            entity_book.join(legal_entity, legal_entity.c.id == entity_book.c.entity_id)
        )
    )
    return sorted(
        (str(row["code"]), str(row["book_code"]), bool(row["is_enabled"])) for row in rows
    )


def book_version(settled: Settled, code: str) -> str:
    version = settled.world.place.scalar(select(book.c.row_version).where(book.c.code == code))
    return f'"r{int(version)}"'


def entity_version(settled: Settled, entity_id: UUID) -> str:
    version = settled.world.place.scalar(
        select(legal_entity.c.row_version).where(legal_entity.c.id == entity_id)
    )
    return f'"r{int(version)}"'


def entity_names(settled: Settled) -> dict[str, str]:
    rows = settled.world.place.rows(select(legal_entity.c.code, legal_entity.c.name))
    return {str(row["code"]): str(row["name"]) for row in rows}


def versions(settled: Settled) -> dict[str, int]:
    """Contract versions of ``C-IFRS-SW01``'s group per book."""
    rows = settled.world.place.rows(
        select(contract_version.c.book_code, func.count().label("n"))
        .where(contract_version.c.combination_group_id == settled.group_id)
        .group_by(contract_version.c.book_code)
    )
    return {str(row["book_code"]): int(row["n"]) for row in rows}


def invoiced(settled: Settled, day: str, number: str) -> dict[str, Any]:
    """``POST /contracts/{id}/events`` as Maya: one invoice of 1,000.00 dated ``day``."""
    head = settled.world.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == settled.contract_id)
    )
    sent = post(
        settled.app,
        f"{API}/contracts/{settled.contract_id}/events",
        settled.maya,
        {
            "events": [
                {
                    "event_type": "BILLING_RECORDED",
                    "effective_date": day,
                    "payload": {
                        "invoice_number": number,
                        "line_external_id": f"{number}-1",
                        "amount": {"amount": "1000.00", "currency": "USD"},
                        "issue_date": day,
                    },
                }
            ]
        },
        if_match=f'"s{int(head)}"',
    )
    assert sent.status_code == 201, sent.text
    answer: dict[str, Any] = sent.json()
    return answer


def year_states(settled: Settled, year: int) -> list[tuple[str, str, int]]:
    """(entity, book, number of period states) of the fiscal year, of every entity."""
    rows = settled.world.place.rows(
        select(legal_entity.c.code, period_state.c.book_code, func.count().label("n"))
        .select_from(
            period_state.join(legal_entity, legal_entity.c.id == period_state.c.entity_id).join(
                period, period.c.id == period_state.c.period_id
            )
        )
        .where(period.c.fiscal_year == year)
        .group_by(legal_entity.c.code, period_state.c.book_code)
    )
    return sorted((str(row["code"]), str(row["book_code"]), int(row["n"])) for row in rows)


def periods_of(settled: Settled, year: int) -> int:
    return int(
        settled.world.place.scalar(
            select(func.count())
            .select_from(period)
            .where(period.c.calendar_id == UUID(settled.calendar_id), period.c.fiscal_year == year)
        )
    )


EVERY_BOOK_2028: Final = [(DE, "ASC606", 12), ("US01", "ASC606", 12), ("US01", "IFRS15", 12)]


def test_a_new_entity_asks_the_permission_for_all_entities(settled: Settled) -> None:
    """``POST /entities``. Dee, whose permission names AVM-DE, and Vera, whose permission names
    AVM-DE while another role shows her every entity, are refused 403 by name with a ``DENIED``
    event before the body is read; Odile, who holds neither permission, is refused as before;
    Maya creates the entity, and the check of the code sees every entity. Before: Vera created
    AVM-F3; Dee was answered 422 for a bad body and 403 without a ``DENIED`` event for a good
    one."""
    app = settled.app
    dee = settled.member("dee", ("revenue_accountant", settled.de_id))
    vera = settled.member("vera", ("viewer", None), ("revenue_accountant", settled.de_id))
    odile = settled.member("odile", ("auditor", settled.de_id))

    def body(code: str, **over: Any) -> dict[str, Any]:
        return {
            "code": code,
            "name": f"{code} (Demo)",
            "functional_currency": "USD",
            "time_zone": "Europe/Paris",
            "calendar_id": settled.calendar_id,
            **over,
        }

    for actor, payload in (
        (vera, body("AVM-F3")),  # before: 201 — the entity was created
        (dee, body("AVM-F2")),
        (dee, body("bad code!", time_zone="Mars/Olympus")),
        (dee, body("US01")),
    ):
        refused_by_name(
            settled,
            actor,
            lambda actor=actor, payload=payload: post(app, f"{API}/entities", actor, payload),
            sentence=NEW_ENTITY,
            action="legal_entity.create",
            object_type="legal_entity",
            all_entities=True,
        )
    without = post(app, f"{API}/entities", odile, body("AVM-F1"))
    assert (without.status_code, slug(without)) == (403, "forbidden"), without.text
    assert without.json().get("errors") in (None, [])  # no sentence of a scope: no permission
    assert sorted(entity_names(settled)) == [DE, "US01"]

    taken = post(app, f"{API}/entities", settled.maya, body("US01"))
    assert taken.status_code == 422, taken.text
    assert [(error["field"], error["message"]) for error in taken.json()["errors"]] == [
        ("code", "Another entity already uses this code.")
    ]
    made = post(app, f"{API}/entities", settled.maya, body("AVM-F4"))
    assert made.status_code == 201, made.text
    assert sorted(entity_names(settled)) == [DE, "AVM-F4", "US01"]


def test_a_book_of_the_workspace_asks_the_permission_for_all_entities(settled: Settled) -> None:
    """``PATCH /books/{code}``, and the second road to the same row: ``PUT
    /entities/{id}/books/{code}`` for a book the workspace has not enabled. Dee's ``PATCH`` that
    would disable IFRS15 is refused 403 by name; the book stays enabled and US01's contract goes
    on being computed in it. Maya's is refused by the keep-guard, which reads every entity that
    keeps the book. Dee keeps no Legacy book for AVM-DE while the workspace has not enabled it;
    once Maya has, Dee's own permission suffices. Before: Dee's ``PATCH`` answered 200 and the
    next computation wrote an ASC606 version and no IFRS15 version; her ``PUT`` enabled the
    Legacy book for the workspace."""
    app = settled.app
    dee = settled.member("dee", ("revenue_accountant", settled.de_id))
    vera = settled.member("vera", ("viewer", None), ("revenue_accountant", settled.de_id))
    assert tenant_books(settled) == {"ASC606": True, "IFRS15": True, "LEGACY": False}
    kept = kept_books(settled)
    assert kept == [(DE, "ASC606", True), ("US01", "ASC606", True), ("US01", "IFRS15", True)]

    for actor in (dee, vera):
        refused_by_name(
            settled,
            actor,
            lambda actor=actor: patch(
                app,
                f"{API}/books/IFRS15",
                actor,
                {"is_enabled": False},
                if_match=book_version(settled, "IFRS15"),
            ),
            sentence=BOOK,
            action="book.update",
            object_type="book",
            all_entities=True,
        )
    guarded = patch(
        app,
        f"{API}/books/IFRS15",
        settled.maya,
        {"is_enabled": False},
        if_match=book_version(settled, "IFRS15"),
    )
    assert guarded.status_code == 422, guarded.text
    assert [(error["field"], error["message"]) for error in guarded.json()["errors"]] == [
        ("is_enabled", "Entities keep this book: US01. Disable it for them first.")
    ]
    assert tenant_books(settled)["IFRS15"] is True

    # the damage measured, closed: the next computation of US01's contract writes both books
    before = versions(settled)
    answer = invoiced(settled, "2026-04-01", "INV-SW01-4")
    assert answer["computation"]["status"] == "SUCCEEDED", answer["computation"]
    assert versions(settled) == {name: count + 1 for name, count in before.items()}
    assert set(before) == {"ASC606", "IFRS15"}

    # the second road: keeping a book the workspace has not enabled is the workspace's act
    legacy = f"{API}/entities/{settled.de_id}/books/LEGACY"
    refused_by_name(
        settled,
        dee,
        lambda: put(app, legacy, dee, {"is_enabled": True}),
        sentence=BOOK_NOT_ENABLED,
        action="entity_book.update",
        object_type="book",
        all_entities=True,
    )
    assert (tenant_books(settled)["LEGACY"], kept_books(settled)) == (False, kept)
    enabled = patch(
        app,
        f"{API}/books/LEGACY",
        settled.maya,
        {"is_enabled": True},
        if_match=book_version(settled, "LEGACY"),
    )
    assert enabled.status_code == 200, enabled.text
    own = put(app, legacy, dee, {"is_enabled": True})
    assert own.status_code == 200, own.text
    assert (own.json()["book_code"], own.json()["is_enabled"]) == ("LEGACY", True)
    assert kept_books(settled) == sorted([*kept, (DE, "LEGACY", True)])


def test_a_fiscal_year_is_generated_for_every_entity_on_the_calendar(settled: Settled) -> None:
    """``POST /calendars`` and ``POST /calendars/{id}/generate-year``. Dee — of one entity on
    the calendar — and Nina — of an entity on another calendar — are refused 403 by name, and no
    period of FY2028 exists. Maya's command writes the periods and the period states of every
    book kept on the calendar and says how many of each; an invoice of US01 dated 15 Jan 2028
    then computes. A repeat writes nothing and says so. Before: Dee's command answered 200 with
    ``inserted_count`` 12 and wrote the states of AVM-DE alone; the invoice was quarantined on
    CV-13; the repeat by a member who read US01 answered ``inserted_count`` 0 and wrote 24
    states."""
    app = settled.app
    dee = settled.member("dee", ("revenue_accountant", settled.de_id))
    other_calendar = calendar(app, settled.maya, code="FISCAL-JP", years=(2026,))
    japan = entity(
        app,
        settled.maya,
        code="AVM-JP",
        calendar_id=other_calendar,
        functional_currency="USD",
        time_zone="Asia/Tokyo",
    )
    nina = settled.member("nina", ("revenue_accountant", UUID(str(japan["id"]))))
    generate = f"{API}/calendars/{settled.calendar_id}/generate-year"
    assert (periods_of(settled, 2028), year_states(settled, 2028)) == (0, [])

    for actor in (dee, nina):
        refused_by_name(
            settled,
            actor,
            lambda actor=actor: post(app, generate, actor, {"fiscal_year": 2028}),
            sentence=CALENDAR,
            action="period.generate",
            object_type="fiscal_calendar",
            all_entities=True,
        )
    refused_by_name(
        settled,
        dee,
        lambda: post(app, f"{API}/calendars", dee, {"code": "DEE-CAL", "name": "Dee's calendar"}),
        sentence=CALENDAR,
        action="fiscal_calendar.create",
        object_type="fiscal_calendar",
        all_entities=True,
    )
    assert (periods_of(settled, 2028), year_states(settled, 2028)) == (0, [])

    made = post(app, generate, settled.maya, {"fiscal_year": 2028})
    assert made.status_code == 200, made.text
    assert (made.json()["inserted_count"], made.json()["inserted_state_count"]) == (12, 36)
    assert year_states(settled, 2028) == EVERY_BOOK_2028
    before = versions(settled)
    answer = invoiced(settled, "2028-01-15", "INV-SW01-2028")
    assert answer["computation"]["status"] == "SUCCEEDED", answer["computation"]
    assert versions(settled) == {name: count + 1 for name, count in before.items()}

    again = post(app, generate, settled.maya, {"fiscal_year": 2028})
    assert again.status_code == 200, again.text
    assert (again.json()["inserted_count"], again.json()["inserted_state_count"]) == (0, 0)


def test_the_period_states_of_a_year_are_written_whoever_asks(
    settled: Settled, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """``commands.ensure_fiscal_year`` carries no authorisation, so that a command which creates
    periods on its caller's behalf can use it: its write is complete by its own statement. Run in
    a unit of work whose session reads AVM-DE alone, it writes the states of US01's two books
    as well and answers the count of all; a second call finds nothing to write and says so.
    Before: 12 states, AVM-DE's."""
    scoped = replace(system_principal(settled.world.tenant_id), entity_scope=(settled.de_id,))
    ctx = RequestContext(
        principal=scoped,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-reference-settings-scope",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    calendar_id = UUID(settled.calendar_id)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        out = commands.ensure_fiscal_year(uow, calendar_id=calendar_id, fiscal_year=2028)
        uow.commit()
    assert out.inserted_count == 12
    assert year_states(settled, 2028) == EVERY_BOOK_2028
    assert out.inserted_state_count == 36

    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        again = commands.ensure_fiscal_year(uow, calendar_id=calendar_id, fiscal_year=2028)
        uow.commit()
    assert (again.inserted_count, again.inserted_state_count) == (0, 0)
    assert year_states(settled, 2028) == EVERY_BOOK_2028


def test_an_entity_is_changed_with_the_permission_for_that_entity(settled: Settled) -> None:
    """``PATCH /entities/{id}`` and ``PUT /entities/{id}/books/{code}``. Dual reads US01 as its
    Auditor and holds ``masterdata.maintain`` for AVM-DE; Vera reads every entity as a Viewer and
    holds it for AVM-DE: both are refused 403 by name on US01, with a ``DENIED`` event, and US01
    is as it was. On AVM-DE their permission suffices, as Una's does on US01. Dee, who does not
    read US01, is answered 404; Odile, who reads it and holds neither permission, 403 as before.
    Before: Dual and Vera renamed US01 and stopped its IFRS15 book; Dual kept the Legacy book
    for it."""
    app = settled.app
    us, de = f"{API}/entities/{settled.us_id}", f"{API}/entities/{settled.de_id}"
    dee = settled.member("dee", ("revenue_accountant", settled.de_id))
    una = settled.member("una", ("revenue_accountant", settled.us_id))
    vera = settled.member("vera", ("viewer", None), ("revenue_accountant", settled.de_id))
    dual = settled.member("dual", ("auditor", settled.us_id), ("revenue_accountant", settled.de_id))
    odile = settled.member("odile", ("auditor", settled.us_id))
    names, kept = entity_names(settled), kept_books(settled)

    for actor in (dual, vera):
        assert get(app, us, actor).status_code == 200  # the precondition: she reads US01
        refused_by_name(
            settled,
            actor,
            lambda actor=actor: patch(
                app,
                us,
                actor,
                {"name": "US01 renamed"},
                if_match=entity_version(settled, settled.us_id),
            ),
            sentence=NOT_THIS_ENTITY,
            action="legal_entity.update",
            object_type="legal_entity",
            all_entities=False,
        )
        for code, wanted in (("IFRS15", False), ("LEGACY", True)):
            refused_by_name(
                settled,
                actor,
                lambda actor=actor, code=code, wanted=wanted: put(
                    app, f"{us}/books/{code}", actor, {"is_enabled": wanted}
                ),
                sentence=NOT_THIS_ENTITY,
                action="entity_book.update",
                object_type="entity_book",
                all_entities=False,
            )
    unseen = patch(
        app, us, dee, {"name": "US01 renamed"}, if_match=entity_version(settled, settled.us_id)
    )
    assert unseen.status_code == 404, unseen.text
    without = patch(
        app, us, odile, {"name": "US01 renamed"}, if_match=entity_version(settled, settled.us_id)
    )
    assert (without.status_code, slug(without)) == (403, "forbidden"), without.text
    assert without.json().get("errors") in (None, [])
    assert (entity_names(settled), kept_books(settled), tenant_books(settled)["LEGACY"]) == (
        names,
        kept,
        False,
    )

    for actor, path, entity_id, name in (
        (dual, de, settled.de_id, "AVM-DE renamed by Dual"),
        (una, us, settled.us_id, "US01 renamed by Una"),
    ):
        changed = patch(
            app, path, actor, {"name": name}, if_match=entity_version(settled, entity_id)
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["name"] == name
    stopped = put(app, f"{us}/books/IFRS15", una, {"is_enabled": False})
    assert stopped.status_code == 200, stopped.text
    assert ("US01", "IFRS15", False) in kept_books(settled)
