"""API-ACTOR-MEMBERS-1: a response member that names a person is API-S-Actor, read with its row
(04 §16.0 API-S-Actor, §16.5 API-S-Policy, §16.8 API-S-Period, §16.14, API-R-10 — rev 1.139;
dev-guide §6.4 DG-API-11; 05 PRV-07 (a); SCREENS §11.2, §11.6, §13.5; SCREENS_B §6.3; supervisor
ruling R-85 (d)).

One workspace. Tomas is a Tenant Admin and erases a person. Hannah is an Auditor: she holds every
read these routes need and not ``user.manage``, so no name reaches her through ``GET /users``; every
read here is hers. Maya and Lena are two people who acted and ``svc-billing`` is an API client. The
rows that name them are written as the commands leave them, with a chosen author, publisher,
resolver or creator.

Per converted member: a person, the same person after ``POST /users/{id}/anonymise`` (the Actor
then shows what 05 PRV-07 (a) wrote and nothing of her name), an API client, and the system where
the member can hold it. For one page of each list the number of statements is the same for one row
and for fifty.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth import totp
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    account_mapping_version,
    exception_item,
    period_lock,
    period_state,
    period_state_transition,
)
from erev_api.domain.platform.privacy import erased_display_name
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    ConfigStatus,
    PrincipalKind,
    RegistryCategory,
    TenantKind,
)
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.uow import unit_of_work
from fastapi import FastAPI
from sqlalchemy import Engine, event, insert, select, update
from sqlalchemy.orm import Session
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase
from support.factories import world_calendar
from support.http import HttpResponse, call
from support.principals import (
    Actor,
    Member,
    colleague,
    cookie_headers,
    enrolled,
    member,
    sign_in,
    step_up,
    workspace,
)
from support.reference import PERIODS, assign, get, holding, periods, post
from support.rows import (
    CloseParts,
    account_mapping_version_values,
    exception_item_values,
    insert_api_client,
    insert_approval_request,
    insert_registry_version,
    period_lock_values,
    period_state_transition_values,
    publish_registry_version,
)

POLICIES = "/api/v1/policies"
ACCOUNT_MAPPINGS = "/api/v1/account-mappings"
EXCEPTIONS = "/api/v1/exceptions"
AUDIT = "/api/v1/audit-events"
USERS = "/api/v1/users"
CLIENT_NAME = "svc-billing"
REASON = "Data subject request DSR-2026-031 received"
PROBE = "actor_probe"  # the object type of the audit events these tests write
SYSTEM = MappingProxyType({"id": None, "kind": "SYSTEM", "display_name": "System"})
PAGE = 50
PROBE_ID = UUID("01920000-0000-7000-8000-00000000a9a1")


@dataclass(frozen=True, slots=True)
class Cast:
    app: FastAPI
    tenant_id: UUID
    tomas: Actor
    hannah: Actor
    maya: Member
    lena: Member
    client_id: UUID

    def person(self, someone: Member, name: str) -> dict[str, Any]:
        return {"id": str(someone.user_id), "kind": "USER", "display_name": name}

    def erased(self, someone: Member) -> dict[str, Any]:
        """The Actor of an anonymised person: the 05 PRV-07 (a) display name, her id kept."""
        return {
            "id": str(someone.user_id),
            "kind": "USER",
            "display_name": erased_display_name(someone.user_id),
        }

    @property
    def client(self) -> dict[str, Any]:
        return {"id": str(self.client_id), "kind": "API_CLIENT", "display_name": CLIENT_NAME}


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def cast(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Cast:
    tomas = member(keyring, clock, name="tomas")
    assign(tomas, "tenant_admin")
    hannah = colleague(tomas.tenant_id, "hannah")
    assign(hannah, "auditor")
    with tenant_session(_db(tomas.tenant_id)) as session:
        client_id = insert_api_client(session, tenant_id=tomas.tenant_id, name=CLIENT_NAME)
    return Cast(
        app=app,
        tenant_id=tomas.tenant_id,
        tomas=enrolled(app, clock, tomas),
        hannah=workspace(app, hannah, sign_in(app, hannah.email)),
        maya=colleague(tomas.tenant_id, "maya"),
        lena=colleague(tomas.tenant_id, "lena"),
        client_id=client_id,
    )


def _erase(cast: Cast, clock: FrozenClock, someone: Member) -> None:
    """05 PRV-07 (a) through its route: Tomas, with a step-up at a TOTP step he has not used."""
    clock.advance(totp.STEP)
    tomas = step_up(cast.app, clock, cast.tomas)
    erased = call(
        cast.app,
        "POST",
        f"{USERS}/{someone.membership_id}/anonymise",
        json={"reason": REASON},
        headers=cookie_headers(tomas.token, tomas.csrf_token),
    )
    assert erased.status_code == 200, erased.text


def _read(cast: Cast, path: str, **params: Any) -> Any:
    response = get(cast.app, path, cast.hannah, params)
    assert response.status_code == 200, response.text
    return response.json()


def _items(cast: Cast, path: str, **params: Any) -> dict[str, dict[str, Any]]:
    """The items of one page of ``path`` read by Hannah, by id."""
    return {item["id"]: item for item in _read(cast, path, **{"limit": 200, **params})["items"]}


@contextmanager
def _statements() -> Iterator[list[str]]:
    """Every SQL statement the process sends while the block runs."""
    seen: list[str] = []

    def capture(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        seen.append(statement)

    event.listen(Engine, "before_cursor_execute", capture)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", capture)


def _counted(cast: Cast, path: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    """The number of statements of one read of ``path`` by Hannah, after the same read once (the
    first request of a session may do work a later one does not), and the items it answered."""
    _read(cast, path, **params)
    with _statements() as seen:
        body = _read(cast, path, **params)
    return len(seen), body["items"] if isinstance(body, dict) else body


# --- policies (API-S-Policy `created_by`, `published_by`) -----------------------------------------


def test_policy_names_its_author_and_its_publisher(cast: Cast, clock: FrozenClock) -> None:
    tenant_id = cast.tenant_id
    with tenant_session(_db(tenant_id)) as session:
        by_lena = publish_registry_version(
            session,
            tenant_id=tenant_id,
            category=RegistryCategory.AI,
            values={},
            published_by=cast.lena.user_id,
            created_by=cast.lena.user_id,
            created_by_kind=PrincipalKind.USER.value,
        )
        by_client = publish_registry_version(
            session,
            tenant_id=tenant_id,
            category=RegistryCategory.SECURITY,
            values={},
            published_by=cast.client_id,
            created_by=cast.maya.user_id,
            created_by_kind=PrincipalKind.USER.value,
        )
        unattended = publish_registry_version(
            session, tenant_id=tenant_id, category=RegistryCategory.CLOSE, values={}
        )
        draft = insert_registry_version(
            session,
            tenant_id=tenant_id,
            category=RegistryCategory.INTEGRATION,
            created_by=cast.client_id,
            created_by_kind=PrincipalKind.API_CLIENT.value,
        )

    listed = _items(cast, POLICIES)
    lena, maya = cast.person(cast.lena, "Lena"), cast.person(cast.maya, "Maya")
    assert (listed[str(by_lena)]["created_by"], listed[str(by_lena)]["published_by"]) == (
        lena,
        lena,
    )
    # SC-V stores no kind beside `published_by`: the Actor's kind is the identity table's.
    assert (listed[str(by_client)]["created_by"], listed[str(by_client)]["published_by"]) == (
        maya,
        cast.client,
    )
    # Published and nobody published it (an automatic approval): the system did.
    assert (listed[str(unattended)]["created_by"], listed[str(unattended)]["published_by"]) == (
        SYSTEM,
        SYSTEM,
    )
    # A draft has no publisher yet; its author is the API client, by its name.
    assert (listed[str(draft)]["created_by"], listed[str(draft)]["published_by"]) == (
        cast.client,
        None,
    )
    # The provisioned defaults are published versions nobody published.
    provisioned = [
        item
        for item in listed.values()
        if (item["category"], item["version_no"], item["status"]) == ("PLATFORM", 1, "PUBLISHED")
    ]
    assert [item["published_by"] for item in provisioned] == [SYSTEM]
    assert _read(cast, f"{POLICIES}/{by_lena}") == listed[str(by_lena)]

    _erase(cast, clock, cast.lena)
    after = _read(cast, f"{POLICIES}/{by_lena}")
    assert (after["created_by"], after["published_by"]) == (cast.erased(cast.lena),) * 2
    assert "Lena" not in str(_items(cast, POLICIES)[str(by_lena)])


def test_policies_page_costs_the_same_statements_for_one_row_and_for_fifty(cast: Cast) -> None:
    tenant_id = cast.tenant_id
    drafts = {"category": "INTEGRATION", "status": "DRAFT", "limit": PAGE}
    author = {"created_by": cast.maya.user_id, "created_by_kind": PrincipalKind.USER.value}
    with tenant_session(_db(tenant_id)) as session:
        insert_registry_version(
            session, tenant_id=tenant_id, category=RegistryCategory.INTEGRATION, **author
        )
    one, items = _counted(cast, POLICIES, **drafts)
    assert [item["created_by"] for item in items] == [cast.person(cast.maya, "Maya")]

    with tenant_session(_db(tenant_id)) as session:
        for version_no in range(3, PAGE + 2):
            insert_registry_version(
                session,
                tenant_id=tenant_id,
                category=RegistryCategory.INTEGRATION,
                version_no=version_no,
                **author,
            )
    fifty, items = _counted(cast, POLICIES, **drafts)
    assert (len(items), fifty) == (PAGE, one)


# --- account mappings (T-REF-14 `created_by`, `published_by`) -------------------------------------


def _mapping(
    session: Session,
    tenant_id: UUID,
    *,
    version_no: int,
    publish: bool = False,
    published_by: UUID | None = None,
    **author: Any,
) -> UUID:
    """A T-REF-14 version ``AVM-MAP-<n>``; with ``publish`` it supersedes the PUBLISHED version and
    walks DRAFT → TESTED → SUBMITTED → APPROVED → PUBLISHED as the commands do (DB-04), effective
    ``n`` days after the frozen instant."""
    table = account_mapping_version
    at = FROZEN_AT + timedelta(days=version_no)
    row = account_mapping_version_values(
        tenant_id,
        version_no=version_no,
        name=f"AVM-MAP-{version_no}",
        effective_from=at if publish else None,
        **author,
    )
    session.execute(insert(table).values(**row))
    version_id = UUID(str(row["id"]))
    if not publish:
        return version_id
    session.execute(
        update(table)
        .where(table.c.tenant_id == tenant_id, table.c.status == ConfigStatus.PUBLISHED.value)
        .values(status=ConfigStatus.SUPERSEDED.value, effective_to=at)
    )
    where = table.c.id == version_id
    session.execute(
        update(table).where(where).values(status=ConfigStatus.TESTED.value, content_sha256="a" * 64)
    )
    session.execute(update(table).where(where).values(status=ConfigStatus.SUBMITTED.value))
    request_id = insert_approval_request(
        session,
        tenant_id=tenant_id,
        status=ApprovalRequestStatus.APPROVED,
        subject_type=ApprovalSubjectType.ACCOUNT_MAPPING_VERSION.value,
        subject_id=version_id,
    )
    session.execute(
        update(table)
        .where(where)
        .values(status=ConfigStatus.APPROVED.value, approval_request_id=request_id)
    )
    session.execute(
        update(table)
        .where(where)
        .values(status=ConfigStatus.PUBLISHED.value, published_at=at, published_by=published_by)
    )
    return version_id


def test_account_mapping_names_its_author_and_its_publisher(cast: Cast, clock: FrozenClock) -> None:
    tenant_id = cast.tenant_id
    maya = {"created_by": cast.maya.user_id, "created_by_kind": PrincipalKind.USER.value}
    client = {"created_by": cast.client_id, "created_by_kind": PrincipalKind.API_CLIENT.value}
    with tenant_session(_db(tenant_id)) as session:
        by_lena = _mapping(
            session, tenant_id, version_no=1, publish=True, published_by=cast.lena.user_id, **maya
        )
        by_client = _mapping(
            session, tenant_id, version_no=2, publish=True, published_by=cast.client_id, **client
        )
        unattended = _mapping(session, tenant_id, version_no=3, publish=True)
        draft = _mapping(session, tenant_id, version_no=4, **maya)

    listed = _items(cast, ACCOUNT_MAPPINGS)
    shown = {
        version_id: (listed[str(version_id)]["created_by"], listed[str(version_id)]["published_by"])
        for version_id in (by_lena, by_client, unattended, draft)
    }
    person = cast.person(cast.maya, "Maya")
    assert shown == {
        by_lena: (person, cast.person(cast.lena, "Lena")),  # superseded: it was published by her
        by_client: (cast.client, cast.client),
        unattended: (SYSTEM, SYSTEM),  # published, and nobody published it
        draft: (person, None),
    }
    assert _read(cast, f"{ACCOUNT_MAPPINGS}/{by_lena}") == listed[str(by_lena)]

    _erase(cast, clock, cast.lena)
    after = _read(cast, f"{ACCOUNT_MAPPINGS}/{by_lena}")
    assert (after["created_by"], after["published_by"]) == (person, cast.erased(cast.lena))


def test_account_mappings_page_costs_the_same_statements_for_one_row_and_for_fifty(
    cast: Cast,
) -> None:
    tenant_id = cast.tenant_id
    author = {"created_by": cast.maya.user_id, "created_by_kind": PrincipalKind.USER.value}
    with tenant_session(_db(tenant_id)) as session:
        _mapping(session, tenant_id, version_no=1, publish=True, published_by=cast.client_id)
    one, items = _counted(cast, ACCOUNT_MAPPINGS, limit=PAGE)
    assert [item["published_by"] for item in items] == [cast.client]

    with tenant_session(_db(tenant_id)) as session:
        for version_no in range(2, PAGE + 1):
            _mapping(session, tenant_id, version_no=version_no, **author)
    fifty, items = _counted(cast, ACCOUNT_MAPPINGS, limit=PAGE)
    assert (len(items), fifty) == (PAGE, one)


# --- exception items (T-IMP-05 `resolved_by`) -----------------------------------------------------


def _resolved(
    session: Session,
    tenant_id: UUID,
    resolver: UUID | None,
    kind: PrincipalKind,
    *,
    owner_membership_id: UUID | None = None,
) -> str:
    """A RESOLVED item as ``POST /exceptions/{id}/resolve`` leaves it, resolved by ``resolver``."""
    row = exception_item_values(
        tenant_id,
        status="RESOLVED",
        resolution="Corrected at the source and imported again.",
        resolved_at=FROZEN_AT,
        resolved_by=resolver,
        resolved_by_kind=kind.value,
        owner_membership_id=owner_membership_id,
    )
    session.execute(insert(exception_item).values(**row))
    return str(row["id"])


def test_exception_item_names_who_resolved_it(cast: Cast, clock: FrozenClock) -> None:
    tenant_id = cast.tenant_id
    with tenant_session(_db(tenant_id)) as session:
        by_maya = _resolved(session, tenant_id, cast.maya.user_id, PrincipalKind.USER)
        by_lena = _resolved(session, tenant_id, cast.lena.user_id, PrincipalKind.USER)
        by_client = _resolved(session, tenant_id, cast.client_id, PrincipalKind.API_CLIENT)
        by_system = _resolved(session, tenant_id, None, PrincipalKind.SYSTEM)
        still_open = exception_item_values(tenant_id)
        session.execute(insert(exception_item).values(**still_open))

    listed = _items(cast, EXCEPTIONS)
    assert {item_id: item["resolved_by"] for item_id, item in listed.items()} == {
        by_maya: cast.person(cast.maya, "Maya"),
        by_lena: cast.person(cast.lena, "Lena"),
        by_client: cast.client,
        by_system: SYSTEM,
        str(still_open["id"]): None,
    }
    # The Actor carries the kind: the response has no `resolved_by_kind` beside it.
    assert all("resolved_by_kind" not in item for item in listed.values())
    assert _read(cast, f"{EXCEPTIONS}/{by_lena}") == listed[by_lena]

    _erase(cast, clock, cast.lena)
    assert _read(cast, f"{EXCEPTIONS}/{by_lena}")["resolved_by"] == cast.erased(cast.lena)
    assert _items(cast, EXCEPTIONS)[by_maya]["resolved_by"] == cast.person(cast.maya, "Maya")


def test_exception_item_names_its_owner(cast: Cast, clock: FrozenClock) -> None:
    """``owner`` is the API-S-Actor of ``owner_membership_id``, read-only beside it: the id stays,
    being the key ``assign`` takes and answers (04 §16.14; the one sibling the rule admits)."""
    tenant_id = cast.tenant_id
    owned = exception_item_values(
        tenant_id, status="IN_PROGRESS", owner_membership_id=cast.lena.membership_id
    )
    unowned = exception_item_values(tenant_id)
    with tenant_session(_db(tenant_id)) as session:
        session.execute(insert(exception_item).values(**owned))
        session.execute(insert(exception_item).values(**unowned))

    listed = _items(cast, EXCEPTIONS)
    assert {
        item_id: (item["owner_membership_id"], item["owner"]) for item_id, item in listed.items()
    } == {
        str(owned["id"]): (str(cast.lena.membership_id), cast.person(cast.lena, "Lena")),
        str(unowned["id"]): (None, None),
    }

    # The command answers the item with its owner: Maya, who holds `exception.resolve`, takes it.
    maya = holding(cast.app, cast.maya, "revenue_accountant")
    assigned = post(
        cast.app,
        f"{EXCEPTIONS}/{unowned['id']}/assign",
        maya,
        {"owner_membership_id": str(cast.maya.membership_id)},
    )
    assert assigned.status_code == 200, assigned.text
    body = assigned.json()
    assert (body["status"], body["owner_membership_id"], body["owner"]) == (
        "IN_PROGRESS",
        str(cast.maya.membership_id),
        cast.person(cast.maya, "Maya"),
    )

    _erase(cast, clock, cast.lena)  # it also removes her membership; the item still names it
    after = _read(cast, f"{EXCEPTIONS}/{owned['id']}")
    assert (after["owner_membership_id"], after["owner"]) == (
        str(cast.lena.membership_id),
        cast.erased(cast.lena),
    )


def test_exceptions_page_costs_the_same_statements_for_one_row_and_for_fifty(cast: Cast) -> None:
    tenant_id = cast.tenant_id
    maya = cast.person(cast.maya, "Maya")
    owner = cast.lena.membership_id
    with tenant_session(_db(tenant_id)) as session:
        _resolved(
            session, tenant_id, cast.maya.user_id, PrincipalKind.USER, owner_membership_id=owner
        )
    one, items = _counted(cast, EXCEPTIONS, limit=PAGE)
    assert [(item["resolved_by"], item["owner"]) for item in items] == [
        (maya, cast.person(cast.lena, "Lena"))
    ]

    with tenant_session(_db(tenant_id)) as session:
        for _ in range(PAGE - 1):
            _resolved(
                session, tenant_id, cast.maya.user_id, PrincipalKind.USER, owner_membership_id=owner
            )
    fifty, items = _counted(cast, EXCEPTIONS, limit=PAGE)
    assert (len(items), fifty) == (PAGE, one)
    assert {item["owner"]["display_name"] for item in items} == {"Lena"}


# --- audit events (T-PLT-19 `actor`, `on_behalf_of`) ----------------------------------------------


def _client_principal(cast: Cast) -> Principal:
    return Principal(
        kind=PrincipalKind.API_CLIENT,
        id=cast.client_id,
        tenant_id=cast.tenant_id,
        membership_id=None,
        display_name=CLIENT_NAME,
        roles=(),
        permissions=frozenset(),
        permission_scopes=MappingProxyType({}),
        entity_scope="*",
        auth_method="client_credentials",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


def _event(
    cast: Cast, keyring: KeyRing, files: LocalFileStore, *, action: str, principal: Principal
) -> None:
    """One audit event of ``principal`` through the audit writer, as a command or a job step
    writes it."""
    ctx = RequestContext(
        principal=principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="r-actor-members",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=FROZEN_AT,
        format_locale="en-US",
    )
    with unit_of_work(ctx, clock=frozen_clock(FROZEN_AT), keyring=keyring, files=files) as uow:
        uow.audit(action=f"{PROBE}.{action}", object_type=PROBE, object_id=cast.tenant_id)
        uow.commit()


def _probe_events(cast: Cast) -> dict[str, dict[str, Any]]:
    """The probe events by the last part of their action."""
    items = _read(cast, AUDIT, object_type=PROBE, limit=200)["items"]
    return {str(item["action"]).split(".")[1]: item for item in items}


def test_audit_event_names_its_actor_and_on_whose_behalf(
    cast: Cast, keyring: KeyRing, files: LocalFileStore, clock: FrozenClock
) -> None:
    tenant_id = cast.tenant_id
    for action, principal in (
        # a job step: the system, for the person or the API client that started the job
        ("for_maya", system_principal(tenant_id, on_behalf_of_id=cast.maya.user_id)),
        ("for_lena", system_principal(tenant_id, on_behalf_of_id=cast.lena.user_id)),
        ("for_client", system_principal(tenant_id, on_behalf_of_id=cast.client_id)),
        ("for_nobody", system_principal(tenant_id)),
        ("by_client", _client_principal(cast)),
    ):
        _event(cast, keyring, files, action=action, principal=principal)

    events = _probe_events(cast)
    assert {action: (item["actor"], item["on_behalf_of"]) for action, item in events.items()} == {
        "for_maya": (SYSTEM, cast.person(cast.maya, "Maya")),
        "for_lena": (SYSTEM, cast.person(cast.lena, "Lena")),
        # T-PLT-19 stores no kind beside `on_behalf_of_id`: the identity table gives it
        "for_client": (SYSTEM, cast.client),
        "for_nobody": (SYSTEM, None),
        # SCREENS_B §6.3 "Actor": an API client by its name
        "by_client": (cast.client, None),
    }
    # The Actor carries the id: the event has no `on_behalf_of_id` beside it.
    assert all("on_behalf_of_id" not in item for item in events.values())

    _erase(cast, clock, cast.lena)
    assert _probe_events(cast)["for_lena"]["on_behalf_of"] == cast.erased(cast.lena)
    # The event of the erasure keeps her pseudonymous id and shows nothing of her name: the Actor
    # never reads a name out of a payload.
    mine = _read(cast, AUDIT, action="app_user.anonymise", limit=5)["items"]
    assert [item["actor"]["id"] for item in mine] == [str(cast.tomas.member.user_id)]
    assert "Lena" not in str(_probe_events(cast)) and "Lena" not in str(mine)


def test_audit_events_page_costs_the_same_statements_for_one_row_and_for_fifty(
    cast: Cast, keyring: KeyRing, files: LocalFileStore
) -> None:
    for number in range(PAGE):
        principal = system_principal(
            cast.tenant_id, on_behalf_of_id=cast.maya.user_id if number % 2 else cast.client_id
        )
        _event(cast, keyring, files, action="step", principal=principal)
    one, items = _counted(cast, AUDIT, object_type=PROBE, limit=1)
    assert len(items) == 1
    fifty, items = _counted(cast, AUDIT, object_type=PROBE, limit=PAGE)
    assert (len(items), fifty) == (PAGE, one)
    assert {item["on_behalf_of"]["display_name"] for item in items} == {"Maya", CLIENT_NAME}


# --- period locks (T-CLS-04 `created_by`; API-S-Period `current_lock`) ----------------------------


def _lock(
    session: Session,
    tenant_id: UUID,
    state: dict[str, Any],
    *,
    created_by: UUID | None,
    kind: PrincipalKind,
    transition_id: UUID,
    at: datetime = FROZEN_AT,
) -> dict[str, Any]:
    """A T-CLS-04 LOCK row of the period state, created by the principal whose decision executed
    the lock; the row as inserted."""
    parts = CloseParts(
        calendar_id=PROBE_ID,
        entity_id=state["entity_id"],
        period_id=state["period_id"],
        period_state_transition_id=transition_id,
        approval_request_id=insert_approval_request(
            session, tenant_id=tenant_id, entity_id=state["entity_id"]
        ),
        file_id=PROBE_ID,
    )
    lock = period_lock_values(
        tenant_id,
        parts=parts,
        created_by=created_by,
        created_by_kind=kind.value,
        created_at=at,
    )
    session.execute(insert(period_lock).values(**lock))
    return lock


def _closed(
    cast: Cast, maya: Actor, state_id: str, *, created_by: UUID | None, kind: PrincipalKind
) -> None:
    """``open`` → ``closing`` by the command, then ``closing`` → ``closed`` with its lock as the
    period's current lock: the rows the lock decision writes (DB-07)."""
    shown = get(cast.app, f"{PERIODS}/{state_id}", maya).json()
    started = post(
        cast.app,
        f"{PERIODS}/{state_id}/start-close",
        maya,
        {},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    with tenant_session(_db(cast.tenant_id)) as session:
        state = dict(
            session.execute(select(period_state).where(period_state.c.id == UUID(state_id)))
            .mappings()
            .one()
        )
        transition_id = new_id()
        lock = _lock(
            session,
            cast.tenant_id,
            state,
            created_by=created_by,
            kind=kind,
            transition_id=transition_id,
        )
        session.execute(
            insert(period_state_transition).values(
                **period_state_transition_values(
                    cast.tenant_id,
                    period_state_id=state["id"],
                    entity_id=state["entity_id"],
                    period_id=state["period_id"],
                    from_state="closing",
                    to_state="closed",
                    id=transition_id,
                    approval_request_id=lock["approval_request_id"],
                    period_lock_id=lock["id"],
                )
            )
        )
        session.execute(
            update(period_state)
            .where(period_state.c.id == state["id"])
            .values(
                state="closed",
                current_lock_id=lock["id"],
                updated_by_kind=PrincipalKind.SYSTEM.value,
            )
        )


def _period_world(cast: Cast) -> tuple[Actor, dict[str, str]]:
    """Maya as a Revenue Accountant with AVM-US FY2026-P01 to P09 open; the period state ids by
    period key."""
    maya = holding(cast.app, cast.maya, "revenue_accountant")
    world_calendar(cast.app, maya)
    return maya, {
        item["period"]["period_key"]: item["id"]
        for item in periods(cast.app, maya, entity="AVM-US")
    }


def test_period_lock_names_who_created_it(cast: Cast, clock: FrozenClock) -> None:
    maya, states = _period_world(cast)
    creators: dict[str, tuple[UUID | None, PrincipalKind, Any]] = {
        "FY2026-P01": (cast.maya.user_id, PrincipalKind.USER, cast.person(cast.maya, "Maya")),
        "FY2026-P02": (cast.lena.user_id, PrincipalKind.USER, cast.person(cast.lena, "Lena")),
        "FY2026-P03": (cast.client_id, PrincipalKind.API_CLIENT, cast.client),
        "FY2026-P04": (None, PrincipalKind.SYSTEM, SYSTEM),
    }
    for key, (created_by, kind, _) in creators.items():
        _closed(cast, maya, states[key], created_by=created_by, kind=kind)

    def shown() -> dict[str, tuple[Any, Any]]:
        """Per period: the creator of `current_lock` (GET /periods) and of each row of the locks
        list (GET /periods/{id}/locks)."""
        listed = {
            item["period"]["period_key"]: item
            for item in _read(cast, PERIODS, entity="AVM-US", limit=200)["items"]
        }
        return {
            key: (
                listed[key]["current_lock"]["created_by"],
                [
                    row["created_by"]
                    for row in _read(cast, f"{PERIODS}/{states[key]}/locks")["items"]
                ],
            )
            for key in creators
        }

    assert shown() == {key: (actor, [actor]) for key, (_, _, actor) in creators.items()}
    one = _read(cast, f"{PERIODS}/{states['FY2026-P02']}")
    assert one["current_lock"]["created_by"] == cast.person(cast.lena, "Lena")
    assert _read(cast, PERIODS, entity="AVM-US", limit=200)["items"][-1]["current_lock"] is None

    _erase(cast, clock, cast.lena)
    erased = cast.erased(cast.lena)
    assert shown()["FY2026-P02"] == (erased, [erased])


def test_period_locks_cost_the_same_statements_for_one_row_and_for_fifty(cast: Cast) -> None:
    maya, states = _period_world(cast)
    state_id = states["FY2026-P01"]
    _closed(cast, maya, state_id, created_by=cast.maya.user_id, kind=PrincipalKind.USER)
    path = f"{PERIODS}/{state_id}/locks"
    one, items = _counted(cast, path)
    assert [item["created_by"] for item in items] == [cast.person(cast.maya, "Maya")]

    with tenant_session(_db(cast.tenant_id)) as session:
        state = dict(
            session.execute(select(period_state).where(period_state.c.id == UUID(state_id)))
            .mappings()
            .one()
        )
        transition_id = session.execute(
            select(period_state_transition.c.id)
            .where(period_state_transition.c.period_state_id == state["id"])
            .limit(1)
        ).scalar_one()
        for number in range(1, PAGE):
            _lock(
                session,
                cast.tenant_id,
                state,
                created_by=cast.client_id if number % 2 else cast.maya.user_id,
                kind=PrincipalKind.API_CLIENT if number % 2 else PrincipalKind.USER,
                transition_id=UUID(str(transition_id)),
                at=FROZEN_AT + timedelta(seconds=number),
            )
    fifty, items = _counted(cast, path)
    assert (len(items), fifty) == (PAGE, one)
    assert {item["created_by"]["display_name"] for item in items} == {"Maya", CLIENT_NAME}

    # API-S-Period `current_lock`: the lock and its creator are one statement. GET /periods reads
    # the close facts of each row, so its creator must not cost a statement of its own.
    with _statements() as seen:
        shown = _read(cast, f"{PERIODS}/{state_id}")
    assert shown["current_lock"]["created_by"] == cast.person(cast.maya, "Maya")
    of_lock = [statement for statement in seen if "FROM erev.period_lock" in statement]
    assert len(of_lock) == 1 and "erev.app_user" in of_lock[0] and "erev.api_client" in of_lock[0]
    assert not [
        statement
        for statement in seen
        if statement.lstrip().startswith("SELECT erev.app_user.id, erev.app_user.display_name")
    ]


# --- entity scope (ruling R-85 (d)) ---------------------------------------------------------------


def test_reader_scoped_to_one_entity_gets_every_actor_of_a_row_it_may_read(cast: Cast) -> None:
    """A person's name is identity of the workspace, not data of an entity: ``app_user`` has no
    row-level security and ``api_client`` is scoped by tenant alone, so a reader scoped to AVM-UK
    reads the author, the publisher and the lock creator of the rows it may read — and never a 500
    where the person holds nothing in that entity."""
    maya, _ = _period_world(cast)
    calendar_id = _read(cast, "/api/v1/calendars")["items"][0]["id"]
    created = post(
        cast.app,
        "/api/v1/entities",
        maya,
        {
            "code": "AVM-UK",
            "name": "AVM-UK (Demo)",
            "functional_currency": "GBP",
            "time_zone": "Europe/London",
            "calendar_id": calendar_id,
        },
    )
    assert created.status_code == 201, created.text
    uk = UUID(str(created.json()["id"]))
    opened = [
        item for item in periods(cast.app, maya, entity="AVM-UK") if item["state"] == "future"
    ][0]
    assert (
        post(
            cast.app,
            f"{PERIODS}/{opened['id']}/open",
            maya,
            {},
            if_match=f'"r{opened["row_version"]}"',
        ).status_code
        == 200
    )
    _closed(cast, maya, opened["id"], created_by=cast.client_id, kind=PrincipalKind.API_CLIENT)
    with tenant_session(_db(cast.tenant_id)) as session:
        policy = publish_registry_version(
            session,
            tenant_id=cast.tenant_id,
            category=RegistryCategory.AI,
            values={},
            published_by=cast.maya.user_id,
            created_by=cast.client_id,
            created_by_kind=PrincipalKind.API_CLIENT.value,
        )
        item = _resolved(session, cast.tenant_id, cast.maya.user_id, PrincipalKind.USER)
    scoped = holding(cast.app, colleague(cast.tenant_id, "victor"), "viewer", entity_ids=[uk])

    def read(path: str, **params: Any) -> Any:
        response: HttpResponse = get(cast.app, path, scoped, params)
        assert response.status_code == 200, response.text
        return response.json()

    person = cast.person(cast.maya, "Maya")
    assert [entity["code"] for entity in read("/api/v1/entities")["items"]] == ["AVM-UK"]
    shown = read(f"{POLICIES}/{policy}")
    assert (shown["created_by"], shown["published_by"]) == (cast.client, person)
    assert read(f"{EXCEPTIONS}/{item}")["resolved_by"] == person
    assert read(f"{PERIODS}/{opened['id']}")["current_lock"]["created_by"] == cast.client
    assert [row["created_by"] for row in read(f"{PERIODS}/{opened['id']}/locks")["items"]] == [
        cast.client
    ]
