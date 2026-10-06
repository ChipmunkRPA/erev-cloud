"""A guarded transaction is a transaction of the permission that admitted it (item
READ-SCOPE-BY-PERMISSION-1, register index 301; 03 REQ-PLT-012 rev 1.146; 04 API-C-03 and §16.10
"Who reads a subject in full", rev 1.319; dev-guide DG-KRN-AUTH-03 and DG-KRN-APR-06, rev 1.295;
the supervisor's ruling of 2026-10-03 on lane QA-BE's line; supervisor rulings R-28, R-41 (1) and
R-64 (6)).

A role assignment gives each permission of its role the entities of the assignment, so a member
with two roles over different entities holds each permission for its own entities. Until this
item a route asked whether its permission was held for ANY entity and then read and wrote under
the union of the entities of all the member's roles; a second role that did not hold the
permission still opened its entity to it. Now ``auth.dependencies.require`` hands on the context
of a transaction of the route's own permission, and the approvals kernel asks a preparer, a
delegate and the reader of a request's content whether they READ the subject in full — one
permission that reads it, for every entity it is bound to — where it asked the same union.

World: PRD WLD-K-04 (``support.worlds.k04_saltmarsh``) with a combination group of two contracting
entities, ``SF-ORD-UK-2004`` of AVM-UK and ``SF-ORD-US-3001`` of AVM-US, combined through the
routes by people of every entity (``test_reader_independence._two_entities``). Maya is Revenue
Accountant of every entity and Marcus approves for every entity. The members of each test hold
default roles, but for Bea: every default role holds ``contract.read``, so the member whose
second role reads nothing holds a role of the workspace's own with ``import.upload`` alone.

Measured before the item, on the same grants (the line of index 301, 2026-10-03):

- Dana, Viewer of AVM-UK and Service Account of AVM-US, read AVM-US's entity row, its books and
  its 24 period states: ``config.read`` is the Viewer's, for AVM-UK only;
- Rae, Revenue Accountant of AVM-UK and Viewer of AVM-US, added a posting rule that names AVM-US
  to an account mapping: ``config.author`` is the accountant's, for AVM-UK only;
- Bea, Revenue Accountant of AVM-UK with ``import.upload`` for AVM-US, read the AVM-US contract
  (lane F-CTR-WEB's API fact 2), previewed and submitted a modification of the group and read
  the content of her request — the group's price, 73,000.00, for her contract of 68,000.00.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from erev_api.approvals import engine as approvals
from erev_api.approvals.subjects import withheld_summary
from erev_api.auth import entity_scope
from erev_api.auth.permissions import Grants, effective_grants
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import account_mapping_rule, approval_request, gl_account, obligation
from erev_api.domain.reference import commands as reference_commands
from erev_api.enums import ApprovalSubjectType
from fastapi import FastAPI
from sqlalchemy import func, select
from support.factories import Workspace, drafted_override
from support.principals import Actor, colleague
from support.reference import (
    approve,
    assign,
    delete,
    fields,
    get,
    holding,
    mapping_draft,
    mapping_published,
    patch,
    post,
    slug,
)
from support.rows import insert_custom_role, revoke_role_assignments
from support.worlds import AVM_UK, AVM_US, K04_CHART, K04World, run_now
from tests.domain.contracts.test_reader_independence import (  # noqa: F401 - fixtures
    ADJUSTMENTS,
    CONTRACTS,
    FILES,
    GROUP_PRICE,
    JOBS,
    MODIFICATIONS,
    SUBMISSION,
    _adjusted,
    _asked,
    _classified,
    _denied,
    _document,
    _estimated,
    _job_count,
    _preview_routes,
    _previewed,
    _summary,
    _two_entities,
    app,
    files,
    k04,
)

API: Final = "/api/v1"
APPROVALS: Final = f"{API}/approvals"
ENTITIES: Final = f"{API}/entities"
PERIODS: Final = f"{API}/periods"
POLICIES: Final = f"{API}/policies"
POLICY_OVERRIDES: Final = f"{API}/policy-overrides"
ACCOUNT_MAPPINGS: Final = f"{API}/account-mappings"
GL_ACCOUNTS: Final = f"{API}/gl-accounts"
NOTIFICATIONS: Final = f"{API}/me/notifications"
OPENAPI: Final = f"{API}/openapi.json"
CONFIG_READ: Final = "config.read"
UPLOADS_ONLY: Final = "uploads_only"  # a role of the workspace's own: ``import.upload`` alone
Grant = tuple[str, UUID | None]  # (role code, the entity it is held for; None: all entities)


@dataclasses.dataclass(frozen=True)
class Scoped:
    """The world of the module: the group of two contracting entities and its people."""

    k04: K04World
    british: UUID  # SF-ORD-UK-2004, contracted by AVM-UK
    american: UUID  # SF-ORD-US-3001, contracted by AVM-US

    @property
    def app(self) -> FastAPI:
        return self.k04.app

    @property
    def place(self) -> Workspace:
        return self.k04.report.place

    @property
    def maya(self) -> Actor:
        return self.k04.report.maya

    @property
    def marcus(self) -> Actor:
        return self.k04.report.marcus

    @property
    def uk(self) -> UUID:
        return self.k04.uk_entity_id

    @property
    def us(self) -> UUID:
        return self.k04.us_entity_id

    def _assign(self, actor_or_member: Any, grants: Sequence[Grant]) -> None:
        for role_code, entity_id in grants:
            assign(actor_or_member, role_code, entity_ids=() if entity_id is None else [entity_id])

    def member(self, name: str, *grants: Grant) -> Actor:
        """A new member with one assignment per grant, signed in after the last."""
        someone = colleague(self.k04.report.tenant_id, name)
        *first, (role_code, entity_id) = grants
        self._assign(someone, first)
        return holding(
            self.app, someone, role_code, entity_ids=() if entity_id is None else [entity_id]
        )

    def grants(self, actor: Actor) -> Grants:
        """What the member's assignments grant now, as a request reads them: each permission
        with its entities, and the union of the entities of all her roles."""
        tenant_id = self.k04.report.tenant_id
        with tenant_session(
            DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*"), read_only=True
        ) as session:
            return effective_grants(session, actor.member.membership_id, at=self.place.clock.now())

    def regrant(self, actor: Actor, *grants: Grant) -> None:
        """Every assignment of the member revoked and ``grants`` assigned in their place: her
        next request reads the new grants (``effective_grants`` at the request)."""
        tenant_id = self.k04.report.tenant_id
        with tenant_session(
            DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        ) as session:
            revoke_role_assignments(
                session,
                tenant_id=tenant_id,
                membership_id=actor.member.membership_id,
                at=self.place.clock.now(),
            )
        self._assign(actor.member, grants)


@pytest.fixture
def scoped(k04: K04World) -> Scoped:  # noqa: F811 - the fixture of the imported module
    british, american, _ = _two_entities(k04, AVM_US)
    tenant_id = k04.report.tenant_id
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        insert_custom_role(
            session, tenant_id=tenant_id, code=UPLOADS_ONLY, permissions=["import.upload"]
        )
    return Scoped(k04=k04, british=british, american=american)


def _problem(response: Any) -> tuple[int, str]:
    """The status of a response and, for a problem, its kind: an answer that is no problem at
    all fails the comparison, not the read of it."""
    return response.status_code, slug(response) if response.status_code >= 400 else ""


def _codes(response: Any) -> list[str]:
    """The entity codes of a list's rows: a row that is an entity, or that names one."""
    assert response.status_code == 200, response.text
    return sorted(
        str(item["entity"]["code"] if "entity" in item else item["code"])
        for item in response.json()["items"]
    )


# --- M1: a read answers under the scope of the read's own permission -----------------------------


def test_a_role_without_the_permission_opens_none_of_its_entitys_rows_to_a_read(
    scoped: Scoped,
) -> None:
    """Default roles alone. Dana is Viewer of AVM-UK and holds the Service Account role for
    AVM-US; that role holds ``contract.read`` and not ``config.read``. The three reads of
    configuration answer her what they answer Vera, a Viewer of AVM-UK alone: AVM-UK's entity
    row, 404 for AVM-US's, the period states of AVM-UK. What her second role does hold still
    reaches its entity: she reads the contract of AVM-US, with ``contract.read``.

    As built (measured, 2026-10-03): the list answered her both entities, ``GET
    /entities/<AVM-US>`` 200, and the periods of FY2026 12 rows of each entity."""
    app_, uk, us = scoped.app, scoped.uk, scoped.us
    dana = scoped.member("dana", ("service_account", us), ("viewer", uk))
    vera = scoped.member("vera", ("viewer", uk))
    sam = scoped.member("sam", ("service_account", us))
    year = {"fiscal_year": 2026, "limit": 200}
    # her grants: the union of her roles names both entities, ``config.read`` one
    held = scoped.grants(dana)
    assert set(held.entity_scope) == {uk, us}
    assert held.permission_scopes[CONFIG_READ] == frozenset({uk})
    assert held.permission_scopes["contract.read"] == frozenset({uk, us})

    for reader in (dana, vera):
        assert _codes(get(app_, ENTITIES, reader)) == [AVM_UK]
        assert get(app_, f"{ENTITIES}/{uk}", reader).status_code == 200
        assert get(app_, f"{ENTITIES}/{us}", reader).status_code == 404
        assert _codes(get(app_, PERIODS, reader, year)) == [AVM_UK] * 12
    # the controls: a reader of every entity; a member whose only role does not hold the read
    assert _codes(get(app_, ENTITIES, scoped.maya)) == [AVM_UK, AVM_US]
    assert _codes(get(app_, PERIODS, scoped.maya, year)) == [AVM_UK] * 12 + [AVM_US] * 12
    for path in (ENTITIES, f"{ENTITIES}/{us}", PERIODS):
        assert get(app_, path, sam).status_code == 403, path

    # what the second role holds is hers for its entity, by its own permission
    for contract_id in (scoped.british, scoped.american):
        assert get(app_, f"{CONTRACTS}/{contract_id}", dana).status_code == 200
    assert get(app_, f"{CONTRACTS}/{scoped.american}", vera).status_code == 404


# The reads of ``config.read`` (04 §15.3), each with the requests asked of it: a function of
# what Maya — who reads every entity — is answered by the lists. Every template of the OpenAPI
# document is here (``test_no_read_of_configuration_…`` holds the two equal).
Asked = list[tuple[str, Mapping[str, Any]]]
ALL: Final[Mapping[str, Any]] = {"limit": 200}


def _ids(app_: FastAPI, maya: Actor, path: str, **params: Any) -> list[dict[str, Any]]:
    listed = get(app_, path, maya, {**ALL, **params})
    assert listed.status_code == 200, (path, listed.text)
    items: list[dict[str, Any]] = listed.json()["items"]
    return items


def _each(path: str, template: str, key: str = "id") -> Callable[[FastAPI, Actor], Asked]:
    """``template`` once for every row of the list at ``path``."""

    def asked(app_: FastAPI, maya: Actor) -> Asked:
        return [(template.format(item[key]), {}) for item in _ids(app_, maya, path)]

    return asked


def _nested(parent: str, versions: str, template: str) -> Callable[[FastAPI, Actor], Asked]:
    """``template`` once for every version of every row of the list at ``parent``."""

    def asked(app_: FastAPI, maya: Actor) -> Asked:
        found: Asked = []
        for item in _ids(app_, maya, parent):
            for version in _ids(app_, maya, versions.format(item["id"])):
                found.append((template.format(version["id"]), {}))
        return found

    return asked


def _plain(path: str, **params: Any) -> Callable[[FastAPI, Actor], Asked]:
    return lambda _app, _maya: [(path, {**ALL, **params})]


CONFIG_READS: Final[Mapping[str, Callable[[FastAPI, Actor], Asked]]] = {
    f"{API}/account-mappings": _plain(ACCOUNT_MAPPINGS),
    f"{API}/account-mappings/resolve": lambda _app, _maya: [
        (f"{ACCOUNT_MAPPINGS}/resolve", {"role": "REVENUE", "entity": code, "book": "ASC606"})
        for code in (AVM_UK, AVM_US)
    ],
    f"{API}/account-mappings/{{version_id}}": _each(ACCOUNT_MAPPINGS, ACCOUNT_MAPPINGS + "/{}"),
    f"{API}/account-mappings/{{version_id}}/rules": _each(
        ACCOUNT_MAPPINGS, ACCOUNT_MAPPINGS + "/{}/rules"
    ),
    f"{API}/books": _plain(f"{API}/books"),
    f"{API}/calendars": _plain(f"{API}/calendars"),
    f"{API}/close-checklist-templates": _plain(f"{API}/close-checklist-templates"),
    f"{API}/config-test-cases": _plain(f"{API}/config-test-cases"),
    f"{API}/currencies": _plain(f"{API}/currencies"),
    f"{API}/dimensions": _plain(f"{API}/dimensions"),
    f"{API}/dimensions/{{code}}/values": _each(
        f"{API}/dimensions", API + "/dimensions/{}/values", key="code"
    ),
    f"{API}/entities": _plain(ENTITIES),
    f"{API}/entities/{{entity_id}}": _each(ENTITIES, ENTITIES + "/{}"),
    f"{API}/fx-rate-set-versions/{{version_id}}": _nested(
        f"{API}/fx-rate-sets", API + "/fx-rate-sets/{}/versions", API + "/fx-rate-set-versions/{}"
    ),
    f"{API}/fx-rate-sets": _plain(f"{API}/fx-rate-sets"),
    f"{API}/fx-rate-sets/{{set_id}}/versions": _each(
        f"{API}/fx-rate-sets", API + "/fx-rate-sets/{}/versions"
    ),
    f"{API}/fx-rates": _plain(f"{API}/fx-rates"),
    f"{API}/gl-accounts": _plain(GL_ACCOUNTS),
    f"{API}/gl-accounts/{{account_id}}": _each(GL_ACCOUNTS, GL_ACCOUNTS + "/{}"),
    f"{API}/periods": _plain(PERIODS, fiscal_year=2026),
    f"{API}/periods/{{period_id}}": _each(PERIODS, PERIODS + "/{}"),
    f"{API}/periods/{{period_id}}/checklist": _each(PERIODS, PERIODS + "/{}/checklist"),
    f"{API}/periods/{{period_id}}/cockpit": _each(PERIODS, PERIODS + "/{}/cockpit"),
    f"{API}/periods/{{period_id}}/locks": _each(PERIODS, PERIODS + "/{}/locks"),
    f"{API}/periods/{{period_id}}/transitions": _each(PERIODS, PERIODS + "/{}/transitions"),
    f"{API}/pob-template-versions/{{version_id}}": _nested(
        f"{API}/pob-templates",
        API + "/pob-templates/{}/versions",
        API + "/pob-template-versions/{}",
    ),
    f"{API}/pob-templates": _plain(f"{API}/pob-templates"),
    f"{API}/pob-templates/{{template_id}}": _each(
        f"{API}/pob-templates", API + "/pob-templates/{}"
    ),
    f"{API}/pob-templates/{{template_id}}/versions": _each(
        f"{API}/pob-templates", API + "/pob-templates/{}/versions"
    ),
    f"{API}/policies": _plain(POLICIES),
    f"{API}/policies/resolve": lambda _app, _maya: [
        (f"{POLICIES}/resolve", {"key": "entity.reporting_type", "entity": code})
        for code in (AVM_UK, AVM_US)
    ],
    f"{API}/policies/{{policy_id}}": _each(POLICIES, POLICIES + "/{}"),
    f"{API}/policy-overrides": _plain(POLICY_OVERRIDES),
    f"{API}/policy-overrides/{{override_id}}": _each(POLICY_OVERRIDES, POLICY_OVERRIDES + "/{}"),
    f"{API}/registry/parameters": _plain(f"{API}/registry/parameters"),
    f"{API}/rule-set-versions/{{version_id}}": _nested(
        f"{API}/rule-sets", API + "/rule-sets/{}/versions", API + "/rule-set-versions/{}"
    ),
    f"{API}/rule-set-versions/{{version_id}}/rules": _nested(
        f"{API}/rule-sets", API + "/rule-sets/{}/versions", API + "/rule-set-versions/{}/rules"
    ),
    f"{API}/rule-set-versions/{{version_id}}/test-cases": _nested(
        f"{API}/rule-sets",
        API + "/rule-sets/{}/versions",
        API + "/rule-set-versions/{}/test-cases",
    ),
    f"{API}/rule-sets": _plain(f"{API}/rule-sets"),
    f"{API}/rule-sets/{{rule_set_id}}": _each(f"{API}/rule-sets", API + "/rule-sets/{}"),
    f"{API}/rule-sets/{{rule_set_id}}/versions": _each(
        f"{API}/rule-sets", API + "/rule-sets/{}/versions"
    ),
    f"{API}/tenant-currencies": _plain(f"{API}/tenant-currencies"),
}
# The templates whose rows the entity policy of the database hides (04 §3 RLS-TE: a legal
# entity, the books it keeps, its period states, an entity's policy version) or that read through
# such a row (an override through its contract; a resolution for a named entity): a reader of
# AVM-UK alone is answered less than a reader of every entity there, and these are the reads a
# second role opened. Every other template reads the workspace's own tables (RLS-T) — a GL
# account and a posting rule among them, which name entities and are every reader's.
OF_AN_ENTITY: Final = frozenset(
    {
        f"{API}/entities",
        f"{API}/entities/{{entity_id}}",
        f"{API}/periods",
        f"{API}/periods/{{period_id}}",
        f"{API}/periods/{{period_id}}/checklist",
        f"{API}/periods/{{period_id}}/cockpit",
        f"{API}/periods/{{period_id}}/locks",
        f"{API}/periods/{{period_id}}/transitions",
        f"{API}/policies",
        f"{API}/policies/{{policy_id}}",
        f"{API}/policies/resolve",
        f"{API}/policy-overrides",
        f"{API}/policy-overrides/{{override_id}}",
        f"{API}/account-mappings/resolve",
    }
)


def _answer(response: Any) -> tuple[int, Any]:
    """A response as two readers are compared: the body of a 200, the kind of a problem."""
    if response.status_code == 200:
        return 200, response.json()
    return response.status_code, slug(response)


def test_no_read_of_configuration_answers_a_second_role_more(scoped: Scoped) -> None:
    """M1 over every read of ``config.read``: the 42 GET routes the OpenAPI document declares
    with that permission, each asked for every row Maya lists — AVM-US's entity, its period
    states, a policy version of entity scope for it and a policy override of its contract among
    them. Dana (Viewer of AVM-UK, Service Account of AVM-US) is answered exactly what Vera
    (Viewer of AVM-UK alone) is, request by request: her second role holds no ``config.read``.

    The routes divide (``OF_AN_ENTITY``). Fourteen read rows the entity policy hides, read
    through one or resolve for a named entity: there Vera is answered less than Maya, and
    there the second role opened AVM-US's rows before the item. The other twenty-eight read the
    workspace's own tables — the account mappings with their rules and the GL accounts among
    them, whose rows name entities and are every reader's — and answer every reader of
    configuration alike, before and after.

    As built (measured on 6e04bc69d): Dana was answered more than Vera by requests of every one
    of the fourteen."""
    app_, maya = scoped.app, scoped.maya
    uk, us = scoped.uk, scoped.us
    version = post(
        app_,
        POLICIES,
        maya,
        {
            "category": "DISCLOSURE_ELECTION",
            "scope": "ENTITY",
            "entity_code": AVM_US,
            "values": {"entity.reporting_type": "NONPUBLIC"},
        },
    )
    assert version.status_code == 201, version.text
    # The row the two override reads answer: a DRAFT of the fixture's, since release 1.0 creates
    # no policy override (04 T-CON-23 "Not offered in release 1.0", rev 1.322).
    drafted_override(
        scoped.place,
        scoped.american,
        "returns.model",
        "EXPECTED_RETURNS",
        obligation_key="O1",
        rationale="Returns of this order are estimated from the customer's history.",
    )
    dana = scoped.member("dana", ("service_account", us), ("viewer", uk))
    vera = scoped.member("vera", ("viewer", uk))

    document = get(app_, OPENAPI, maya)
    assert document.status_code == 200, document.text
    declared = {
        path
        for path, operations in document.json()["paths"].items()
        if operations.get("get", {}).get("x-erev-permission") == CONFIG_READ
    }
    assert declared == set(CONFIG_READS)
    assert len(declared) == 42 and OF_AN_ENTITY <= declared

    opened: list[tuple[str, str]] = []  # (template, request) where the second role adds
    narrower: set[str] = set()  # templates where a reader of AVM-UK is answered less than Maya
    asked = 0
    for template in sorted(CONFIG_READS):
        requests = CONFIG_READS[template](app_, maya)
        assert requests, template  # the world holds a row for every read
        for path, params in requests:
            asked += 1
            whole = _answer(get(app_, path, maya, params))
            assert whole[0] not in (403, 404), (template, path, whole)
            hers, alone = (_answer(get(app_, path, reader, params)) for reader in (dana, vera))
            if hers != alone:
                opened.append((template, path))
            if alone != whole:
                narrower.add(template)
    assert sorted({template for template, _ in opened}) == []
    assert narrower == OF_AN_ENTITY
    assert asked > 150  # 48 period states by five reads alone


# --- M2: a command writes under the scope of the command's own permission -------------------------

RULE_OF_REVENUE: Final = "REVENUE"


def _rule(account_id: str, entity_id: UUID | None) -> dict[str, Any]:
    return {
        "account_role": RULE_OF_REVENUE,
        "entity_id": None if entity_id is None else str(entity_id),
        "gl_account_id": account_id,
    }


def _rules(place: Workspace, version_id: str) -> int:
    return int(
        place.scalar(
            select(func.count())
            .select_from(account_mapping_rule)
            .where(account_mapping_rule.c.account_mapping_version_id == UUID(version_id))
        )
    )


def test_a_command_names_no_entity_its_own_permission_does_not_cover(scoped: Scoped) -> None:
    """Default roles alone. Rae is Revenue Accountant of AVM-UK and Viewer of AVM-US:
    ``config.author`` is the accountant's, for AVM-UK. A posting rule that names AVM-US is
    refused to her as to Una, a Revenue Accountant of AVM-UK alone — 422 on ``entity_id``, rule
    T-REF-15, "Choose an existing entity.": the command's transaction reads under the scope of
    ``config.author``, where AVM-US does not exist. Her rule for AVM-UK, and Maya's for AVM-US,
    are taken.

    As built (measured, 2026-10-03): Rae's rule for AVM-US was stored, 201 — the posting rule
    of an entity she views."""
    app_, place = scoped.app, scoped.place
    rae = scoped.member("rae", ("viewer", scoped.us), ("revenue_accountant", scoped.uk))
    una = scoped.member("una", ("revenue_accountant", scoped.uk))
    account_id = str(get(app_, GL_ACCOUNTS, scoped.maya).json()["items"][0]["id"])
    created = post(app_, ACCOUNT_MAPPINGS, una, {"name": "AVM-MAP-2026-07", "effective_from": None})
    assert created.status_code == 201, created.text
    version_id = str(created.json()["id"])
    rules = f"{ACCOUNT_MAPPINGS}/{version_id}/rules"

    for author in (una, rae):
        refused = post(app_, rules, author, _rule(account_id, scoped.us))
        assert _problem(refused) == (422, "validation-failed"), refused.text
        assert fields(refused) == [("entity_id", "T-REF-15")]
        assert refused.json()["errors"][0]["message"] == reference_commands.MAPPING_ENTITY_UNKNOWN
    assert _rules(place, version_id) == 0
    # the controls: her own entity; an author of every entity
    assert post(app_, rules, rae, _rule(account_id, scoped.uk)).status_code == 201
    assert post(app_, rules, scoped.maya, _rule(account_id, scoped.us)).status_code == 201
    assert _rules(place, version_id) == 2


def test_a_row_that_names_entities_is_changed_by_an_author_for_those_entities(
    scoped: Scoped,
) -> None:
    """The checks of their own (the ruling's part 3; 04 T-REF-13 and T-REF-15 rev 1.319). A GL
    account and a posting rule are rows of the workspace's tables: every author reads them, and
    the entity policy hides none. One that NAMES entities is changed by an author who holds
    ``config.author`` for them. Una, of AVM-UK alone: the delete of a rule that names AVM-US,
    and a change of an account available to AVM-US alone, answer her 404 as for an id that names
    nothing, and nothing is written; an entity her permission does not cover is not added to an
    account's ``entity_ids`` — 422 on the member, as for an id that names no entity, which Maya
    is refused too. Her own entity's rows, and the workspace's — a rule that names no entity,
    an account available to all — are hers to change, as before.

    As built (read by lane SECFIX-APR, measured here on the base): ``entity_ids`` was checked
    for repetition alone, so any id was stored; Una deactivated the account of AVM-US and
    deleted its rule."""
    app_, place, maya = scoped.app, scoped.place, scoped.maya
    uk, us = scoped.uk, scoped.us
    una = scoped.member("una", ("revenue_accountant", uk))
    account_id = str(get(app_, GL_ACCOUNTS, maya).json()["items"][0]["id"])

    # --- the posting rules of a draft: one for each entity, one for the workspace
    created = post(
        app_, ACCOUNT_MAPPINGS, maya, {"name": "AVM-MAP-2026-07", "effective_from": None}
    )
    assert created.status_code == 201, created.text
    rules = f"{ACCOUNT_MAPPINGS}/{created.json()['id']}/rules"
    ids: dict[str, str] = {}
    for name, entity_id in (("us", us), ("uk", uk), ("workspace", None)):
        added = post(app_, rules, maya, _rule(account_id, entity_id))
        assert added.status_code == 201, added.text
        ids[name] = str(added.json()["id"])

    hidden = delete(app_, f"{rules}/{ids['us']}", una)
    assert _problem(hidden) == (404, "not-found"), hidden.text
    assert _denied(place, hidden) == []
    assert _rules(place, str(created.json()["id"])) == 3
    for name in ("uk", "workspace"):
        assert delete(app_, f"{rules}/{ids[name]}", una).status_code == 204, name
    assert delete(app_, f"{rules}/{ids['us']}", maya).status_code == 204
    assert _rules(place, str(created.json()["id"])) == 0

    # --- a GL account: the entities it is available to
    def account(author: Actor, code: str, entity_ids: Sequence[UUID]) -> Any:
        body = {
            "code": code,
            "name": f"Receivables {code}",
            "account_type": "ASSET",
            "normal_balance": "D",
            "entity_ids": [str(value) for value in entity_ids],
        }
        return post(app_, GL_ACCOUNTS, author, body)

    def stored(found_id: str) -> tuple[bool, list[UUID], int]:
        (row,) = place.rows(
            select(gl_account.c.is_active, gl_account.c.entity_ids, gl_account.c.row_version).where(
                gl_account.c.id == UUID(found_id)
            )
        )
        return bool(row["is_active"]), sorted(row["entity_ids"]), int(row["row_version"])

    for author, named in ((una, us), (maya, uuid4())):
        refused = account(author, "9410", [named])
        assert _problem(refused) == (422, "validation-failed"), refused.text
        assert fields(refused) == [("entity_ids", "T-REF-13")]
        assert refused.json()["errors"][0]["message"] == entity_scope.ENTITY_UNKNOWN
    american = account(maya, "9410", [us])
    british = account(una, "9420", [uk])
    shared = account(una, "9430", [])
    for made in (american, british, shared):
        assert made.status_code == 201, made.text
    american_id, british_id, shared_id = (
        str(made.json()["id"]) for made in (american, british, shared)
    )

    # every author reads the account of AVM-US; Una does not change it
    assert get(app_, f"{GL_ACCOUNTS}/{american_id}", una).status_code == 200
    for change in ({"is_active": False}, {"entity_ids": [str(uk)]}, {"entity_ids": []}):
        hidden = patch(app_, f"{GL_ACCOUNTS}/{american_id}", una, change, if_match='"r1"')
        assert _problem(hidden) == (404, "not-found"), (change, hidden.text)
        assert _denied(place, hidden) == []
    assert stored(american_id) == (True, [us], 1)
    # her own entity's account: changed, and not given to an entity she does not author for
    widened = patch(
        app_,
        f"{GL_ACCOUNTS}/{british_id}",
        una,
        {"entity_ids": [str(uk), str(us)]},
        if_match='"r1"',
    )
    assert _problem(widened) == (422, "validation-failed"), widened.text
    assert fields(widened) == [("entity_ids", "T-REF-13")]
    renamed = patch(app_, f"{GL_ACCOUNTS}/{british_id}", una, {"is_active": False}, if_match='"r1"')
    assert renamed.status_code == 200, renamed.text
    assert stored(british_id) == (False, [uk], 2)
    # the workspace's account stays any author's, and Maya changes AVM-US's
    assert (
        patch(
            app_, f"{GL_ACCOUNTS}/{shared_id}", una, {"name": "Receivables"}, if_match='"r1"'
        ).status_code
        == 200
    )
    assert (
        patch(
            app_, f"{GL_ACCOUNTS}/{american_id}", maya, {"is_active": False}, if_match='"r1"'
        ).status_code
        == 200
    )
    assert stored(american_id) == (False, [us], 2)


def test_a_version_that_ends_another_entitys_rules_is_submitted_by_who_reads_them(
    scoped: Scoped,
) -> None:
    """The second shape of 04 §16.10 rev 1.319 "The request's row is the kernel's" (lane
    SECFIX-APR's reading; supervisor ruling R-64 (2): a superseding version binds what it ends).
    From October the mapping in force holds a posting rule of AVM-US. A version that takes
    effect later and names no entity ends that rule, so its request names AVM-US — alone. Rae
    authors configuration for AVM-UK and reads AVM-US: her command runs under ``config.author``,
    where AVM-US does not exist, and her request of AVM-US is stored, PENDING, because the
    kernel's question admitted her — she reads the rules her version ends. Una, of AVM-UK
    alone, drafts and tests the version (one version is open at a time, SM-04) and is refused
    by name at its submission, on record; the version stays TESTED, and Rae submits it.

    Measured before the kernel's statements moved under the tenant's scope: Rae's submission
    answered 403 ``forbidden`` without a detail, from the row policy's check on the insert."""
    app_, place, maya, marcus = scoped.app, scoped.place, scoped.maya, scoped.marcus
    uk, us = scoped.uk, scoped.us
    accounts = {
        str(item["code"]): str(item["id"])
        for item in get(app_, GL_ACCOUNTS, maya, ALL).json()["items"]
    }
    general = [
        {"account_role": role, "gl_account_id": accounts[code]} for code, _, _, _, role in K04_CHART
    ]
    mapping_published(
        app_,
        maya,
        marcus,
        name="AVM-MAP-2026-10",
        effective_from="2026-10-01T00:00:00Z",
        rules=[*general, _rule(accounts["4010"], us)],
    )
    rae = scoped.member("rae", ("viewer", us), ("revenue_accountant", uk))
    una = scoped.member("una", ("revenue_accountant", uk))
    draft = mapping_draft(
        app_, una, name="AVM-MAP-2026-11", effective_from="2026-11-01T00:00:00Z", rules=general
    )
    version_id = str(draft["id"])
    path = f"{ACCOUNT_MAPPINGS}/{version_id}"
    ran = post(app_, f"{path}/test", una, {})
    assert ran.status_code == 200, ran.text

    refused = post(app_, f"{path}/submit", una, {"comment": "Review"})
    _refused_by_name(
        place,
        refused,
        sentence=approvals.OUTSIDE_SCOPE_DETAIL,
        expected={
            "action": approvals.SUBMIT_ACTION,
            "detail": {
                "subject_type": "ACCOUNT_MAPPING_VERSION",
                "subject_id": version_id,
                "reason": approvals.DENIED_PREPARER_SCOPE,
                "permission": "",
            },
        },
    )
    assert get(app_, path, una).json()["status"] == "TESTED"

    sent = post(app_, f"{path}/submit", rae, {"comment": "Review"})
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "SUBMITTED"
    assert _denied(place, sent) == []
    shown = get(app_, path, rae)
    assert shown.status_code == 200, shown.text
    request_id = shown.json()["pending_approval_request_id"]
    assert request_id is not None
    (stored,) = place.rows(
        select(
            approval_request.c.entity_id, approval_request.c.status, approval_request.c.preparer_id
        ).where(approval_request.c.id == UUID(str(request_id)))
    )
    assert (stored["entity_id"], str(stored["status"])) == (us, "PENDING")
    assert stored["preparer_id"] == rae.member.user_id
    request = get(app_, f"{APPROVALS}/{request_id}", marcus)
    assert [ref["code"] for ref in request.json()["entities"]] == [AVM_US]


# --- API fact 2: a role that does not read contracts opens no contract ----------------------------


def test_a_role_that_reads_no_contract_opens_no_contract_of_its_entity(scoped: Scoped) -> None:
    """Lane F-CTR-WEB's API fact 2. Bea is Revenue Accountant of AVM-UK and holds, for AVM-US,
    a role with ``import.upload`` alone: no role of hers reads a contract of AVM-US. The
    contract of AVM-US answers her 404 by id, as it answers Una of AVM-UK alone, with every
    read under it; the list holds her entity's contracts. Her own entity's member of the same
    group is hers to read.

    As built (measured by that lane on 94241243c and here on 9798a7806): ``GET
    /contracts/<SF-ORD-US-3001>`` answered her 200."""
    app_ = scoped.app
    bea = scoped.member("bea", (UPLOADS_ONLY, scoped.us), ("revenue_accountant", scoped.uk))
    una = scoped.member("una", ("revenue_accountant", scoped.uk))
    path = f"{CONTRACTS}/{scoped.american}"
    for reader in (bea, una):
        assert get(app_, path, reader).status_code == 404
        for part in ("obligations", "events", "schedule", "balances", "modifications"):
            assert get(app_, f"{path}/{part}", reader).status_code == 404, part
        listed = get(app_, CONTRACTS, reader, {"limit": 200})
        assert listed.status_code == 200, listed.text
        ids = {str(item["id"]) for item in listed.json()["items"]}
        assert str(scoped.british) in ids and str(scoped.american) not in ids
        assert get(app_, f"{CONTRACTS}/{scoped.british}", reader).status_code == 200
    assert get(app_, path, scoped.maya).status_code == 200
    # her grants: the union of her roles names both entities, ``contract.read`` one
    held = scoped.grants(bea)
    assert set(held.entity_scope) == {scoped.uk, scoped.us}
    assert held.permission_scopes["import.upload"] == frozenset({scoped.uk, scoped.us})
    assert held.permission_scopes["contract.read"] == frozenset({scoped.uk})


# --- the preparer: asked whether she reads the group, not which roles she holds -------------------


def _refused_by_name(
    place: Workspace, refused: Any, *, sentence: str, expected: Mapping[str, Any]
) -> None:
    """403 ``forbidden`` with ``sentence``, and the one ``DENIED`` event of the kernel."""
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"] == sentence
    assert _denied(place, refused) == [
        {"action": expected["action"], "object_type": approvals.OBJECT_TYPE, "object_id": None}
        | {"detail": dict(expected["detail"])}
    ]


def test_a_preparer_previews_and_submits_what_she_reads_in_full(scoped: Scoped) -> None:
    """The member of the ruling's part 2, through the routes. Rae is Revenue Accountant of
    AVM-UK and Viewer of AVM-US — default roles: she prepares for AVM-UK and READS both
    entities of the group. The four preview routes take her, her jobs answer her the group's
    summary, her modification is submitted and the content of her request is answered to her:
    the kernel asks a preparer whether she reads every entity the subject is bound to (R-64
    (6): she asks others to approve only what she can read in full), and ``contract.read`` is
    hers for both.

    Bea prepares for AVM-UK too, and her second role, for AVM-US, holds ``import.upload``
    alone. Each of the four routes refuses her by name, 403, defers nothing and leaves one
    ``DENIED`` event; so does the submission of her modification, which stays a draft.

    As built: Bea's four previews were taken and her submission accepted — her roles' union
    covered the group (measured, 2026-10-03). Under the transaction's scope alone (rule 1
    without the kernel's question) Rae would be refused as Bea is: the command runs under
    ``modification.create``, which is hers for AVM-UK only."""
    app_, place, british = scoped.app, scoped.place, scoped.british
    rae = scoped.member("rae", ("viewer", scoped.us), ("revenue_accountant", scoped.uk))
    bea = scoped.member("bea", (UPLOADS_ONLY, scoped.us), ("revenue_accountant", scoped.uk))

    # --- Rae: kept
    modification_id = _classified(app_, rae, british, "CR-UK-2004-2026-07")
    kept = _preview_routes(
        british,
        modification_id,
        _estimated(app_, rae, british, "REBATE-2004"),
        _adjusted(app_, place, rae, british),
    )
    for route in kept:
        taken = _asked(app_, rae, british, route)
        assert taken.status_code == 202, (route.path, taken.text)
        assert _denied(place, taken) == [], route.path
        job_id = str(taken.json()["id"])
        finished = run_now(scoped.k04.report, UUID(job_id))
        assert finished["state"] == "SUCCEEDED", (route.path, finished.get("problem"))
        own = get(app_, f"{JOBS}/{job_id}", rae)
        assert own.status_code == 200, (route.path, own.text)
        assert _summary(own.json()["result"]) == (GROUP_PRICE, None), route.path
    submitted = post(app_, f"{MODIFICATIONS}/{modification_id}/submit", rae, dict(SUBMISSION))
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"
    assert _denied(place, submitted) == []
    request_id = str(submitted.json()["approval_request_id"])
    shown = get(app_, f"{APPROVALS}/{request_id}", rae)
    assert shown.status_code == 200, shown.text
    request = shown.json()
    assert request["content_withheld"] is False
    assert sorted(ref["code"] for ref in request["entities"]) == [AVM_UK, AVM_US]
    # the hash her row keeps is the hash the kernel stored: one content, read under one scope
    assert submitted.json()["content_sha256"] == request["subject"]["content_sha256"]
    assert request["impact_preview"] is not None
    assert _document(app_, rae, request["impact_preview"]["file_id"]) == (200, 200)

    # --- Bea: refused at each command, by name
    hers = _classified(app_, bea, british, "CR-UK-2004-2026-08")
    refused_routes = _preview_routes(
        british,
        hers,
        _estimated(app_, bea, british, "REBATE-2004-B"),
        _adjusted(app_, place, bea, british),
    )
    for route in refused_routes:
        jobs = _job_count(place)
        refused = _asked(app_, bea, british, route)
        _refused_by_name(
            place,
            refused,
            sentence=approvals.OUTSIDE_PREVIEW_DETAIL,
            expected={
                "action": route.action,
                "detail": {
                    "subject_type": route.subject_type,
                    "subject_id": route.subject_id,
                    "reason": approvals.DENIED_PREPARER_SCOPE,
                    "permission": route.permission,
                },
            },
        )
        assert _job_count(place) == jobs, route.path
    _previewed(scoped.k04, scoped.maya, hers)  # the preview her submission would stand on
    refused = post(app_, f"{MODIFICATIONS}/{hers}/submit", bea, dict(SUBMISSION))
    _refused_by_name(
        place,
        refused,
        sentence=approvals.OUTSIDE_SCOPE_DETAIL,
        expected={
            "action": approvals.SUBMIT_ACTION,
            "detail": {
                "subject_type": "MODIFICATION",
                "subject_id": hers,
                "reason": approvals.DENIED_PREPARER_SCOPE,
                "permission": "",
            },
        },
    )
    assert get(app_, f"{MODIFICATIONS}/{hers}", bea).json()["status"] == "DRAFT"


def test_the_content_of_a_request_is_answered_to_a_preparer_who_reads_it_in_full(
    scoped: Scoped,
) -> None:
    """The preparer's clause of 04 §16.10 rev 1.208, as rev 1.319 asks it. Bea prepares, previews
    and submits a modification of the group while she is a Viewer of AVM-US: she reads both
    entities, and the content of her request is hers. Then her Viewer role is withdrawn and she
    is given, for AVM-US, the role with ``import.upload`` alone — the member lane F-CTR-WEB
    measured, whose roles' union still covers the group. Her request answers her its header
    with ``content_withheld``: the subject type's name and the request's number for the
    summary, no amount, no impact preview, no flag — and what she wrote herself. Its document
    answers her as a file that does not exist, and the approval is told to her without the
    record's name. Marcus, who approves for every entity, reads the content and decides.

    As built (measured, 2026-10-03): the request answered such a member its content — the
    impact preview and its document, 73,000.00 and 78,000.00."""
    app_, place, british = scoped.app, scoped.place, scoped.british
    bea = scoped.member("bea", ("viewer", scoped.us), ("revenue_accountant", scoped.uk))
    modification_id = _classified(app_, bea, british, "CR-UK-2004-2026-07")
    _previewed(scoped.k04, bea, modification_id)
    submitted = post(app_, f"{MODIFICATIONS}/{modification_id}/submit", bea, dict(SUBMISSION))
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    path = f"{APPROVALS}/{request_id}"
    whole = get(app_, path, bea).json()
    assert whole["content_withheld"] is False
    file_id = whole["impact_preview"]["file_id"]
    assert _document(app_, bea, file_id) == (200, 200)
    assert "SF-ORD-UK-2004" in whole["summary"]

    scoped.regrant(bea, (UPLOADS_ONLY, scoped.us), ("revenue_accountant", scoped.uk))
    held = scoped.grants(bea)
    assert set(held.entity_scope) == {scoped.uk, scoped.us}
    assert held.permission_scopes["contract.read"] == frozenset({scoped.uk})

    shown = get(app_, path, bea)
    assert shown.status_code == 200, shown.text
    header = shown.json()
    (request_no,) = [
        str(row["request_no"])
        for row in place.rows(
            select(approval_request.c.request_no).where(approval_request.c.id == UUID(request_id))
        )
    ]
    label = withheld_summary(ApprovalSubjectType.MODIFICATION, request_no)
    assert header["content_withheld"] is True
    assert (header["summary"], header["subject"]["display"]) == (label, label)
    assert (header["amount"], header["impact_preview"], header["flags"]) == (None, None, [])
    assert header["attachments"] == []
    assert header["comment"] == SUBMISSION["comment"]  # her own words (rev 1.252)
    assert (header["status"], header["preparer"]["id"]) == ("PENDING", str(bea.member.user_id))
    assert "SF-ORD-UK-2004" not in shown.text and "73000.00" not in shown.text
    assert _document(app_, bea, file_id) == (404, 404)
    listed = get(app_, APPROVALS, bea, {"preparer": "me"}).json()["items"]
    assert [(item["id"], item["content_withheld"]) for item in listed] == [(request_id, True)]
    # the control: the approver for every entity reads the content; so the request is decided
    assert get(app_, path, scoped.marcus).json()["content_withheld"] is False
    approved = approve(app_, request_id, scoped.marcus)
    assert approved.status_code == 200, approved.text
    told = get(app_, NOTIFICATIONS, bea, {"limit": 50})
    assert told.status_code == 200, told.text
    about = [item for item in told.json()["items"] if item["kind"] == "ITEM_APPROVED"]
    assert [item["title"] for item in about] == [f"Approved: {label}"]
    assert "SF-ORD-UK-2004" not in told.text
    assert get(app_, path, bea).json()["content_withheld"] is True


# --- item PREVIEW-INLINE-SCOPE-1: what a request states does not depend on who submits ------------

GBP: Final = "GBP"
VOID_REQUEST: Final = {
    "reason_code": "DUPLICATE",
    "comment": "Duplicate of an order created by a repeated CRM sync.",
}


def _stored(app_: FastAPI, reader: Actor, request_id: str) -> tuple[Any, ...]:
    """What a request states, as an approver for every entity reads it: its amount, its flags,
    the hash of its content, the hash of its impact preview and the stored document."""
    shown = get(app_, f"{APPROVALS}/{request_id}", reader)
    assert shown.status_code == 200, shown.text
    request = shown.json()
    preview = request["impact_preview"]
    document = get(app_, f"{FILES}/{preview['file_id']}/content", reader)
    assert document.status_code == 200, document.text
    return (
        request["amount"],
        request["flags"],
        request["subject"]["content_sha256"],
        preview["sha256"],
        document.json(),
    )


def _revenue_before(document: Mapping[str, Any]) -> list[tuple[str, str]]:
    return [
        (str(row["period_key"]), str(row["amount"]["amount"]))
        for row in document["before"]["revenue_by_period"]
    ]


def test_what_a_request_states_of_its_contract_does_not_depend_on_who_submits(
    k04: K04World,  # noqa: F811 - the fixture of the imported module
) -> None:
    """Item PREVIEW-INLINE-SCOPE-1, found by the census of index 301 (04 API-S-ImpactSummary rev
    1.319; supervisor rulings R-64 (1) and R-87 (1); REQ-PLT-015). ``SF-ORD-UK-2001`` is
    contracted by AVM-UK and its O1 is performed by AVM-US: the schedule lines and the posted
    lines of O1 are rows of AVM-US. Una is a Revenue Accountant of AVM-UK alone — the contract is
    hers to prepare for — and Rae is one who also views AVM-US. Two commands summarise their dry
    run in the caller's transaction and store the summary with their request.

    The void: Una's request states what Rae's and Maya's state — one amount, one flag, one
    content, one preview hash, one document: 28 posted lines, and the revenue the void takes
    away in each of the next six periods. Her answer is the request's id and no figure; the
    stored preview is hers to read through her request, as her preview jobs' summaries are.

    The manual adjustment: a release of 100.00 on O1 is measured, stored and routed as 100.00
    whoever prepares it, at its creation and at its submission.

    The same summary serves an activation and an estimate version's submission
    (``events.impact_summary``; ``tests/architecture/test_scope_questions.py`` holds each read
    inside the tenant's scope). The activation of a draft has no stored revenue before it: its
    preview was the same for Una and for Maya (measured, 78 members). An estimate version of
    this contract is submitted by nobody in this world, which maps no account for it.

    As built (measured on 6e04bc69d, 2026-10-03): Una's void stored a preview with 16 posted
    lines of 28 and revenue before 0.00 in the six periods — the preview its approver
    certifies by its hash; her release of 100.00 was stored and routed as 4,890.61, the whole
    period's revenue, read as an impact against a stored revenue of nothing. A guarded
    transaction of the permission that admitted it (index 301) put Rae where Una was."""
    app_, place = k04.app, k04.report.place
    tenant_id, uk, us = k04.report.tenant_id, k04.uk_entity_id, k04.us_entity_id
    contract_id = k04.contract_id
    maya, marcus = k04.report.maya, k04.report.marcus
    una = holding(app_, colleague(tenant_id, "una"), "revenue_accountant", entity_ids=[uk])
    viewer = colleague(tenant_id, "rae")
    assign(viewer, "viewer", entity_ids=[us])
    rae = holding(app_, viewer, "revenue_accountant", entity_ids=[uk])

    # --- the void: asked by each, read by the approver, withdrawn
    voided: dict[str, tuple[Any, ...]] = {}
    for name, actor in (("una", una), ("rae", rae), ("maya", maya)):
        head = get(app_, f"{CONTRACTS}/{contract_id}", actor).json()["head_stream_version"]
        asked = post(
            app_,
            f"{CONTRACTS}/{contract_id}/request-void",
            actor,
            dict(VOID_REQUEST),
            if_match=f'"s{head}"',
        )
        assert asked.status_code == 200, (name, asked.text)
        assert set(asked.json()) == {"approval_request_id"}  # the answer carries no figure
        request_id = str(asked.json()["approval_request_id"])
        voided[name] = _stored(app_, marcus, request_id)
        own = get(app_, f"{APPROVALS}/{request_id}", actor)
        assert own.status_code == 200 and own.json()["content_withheld"] is False, name
        withdrawn = post(app_, f"{APPROVALS}/{request_id}/withdraw", actor, {"comment": "Kept."})
        assert withdrawn.status_code == 200, (name, withdrawn.text)
    assert voided["una"] == voided["maya"]
    assert voided["rae"] == voided["maya"]
    amount, flags, _, _, document = voided["maya"]
    assert (amount, flags) == ({"amount": "68000.00", "currency": GBP}, ["POSTED_LINES"])
    assert document["before"]["posted_basis"]["posted_line_count"] == 28
    assert _revenue_before(document) == [
        ("FY2026-P09", "4790.61"),
        ("FY2026-P10", "4950.29"),
        ("FY2026-P11", "4790.61"),
        ("FY2026-P12", "4950.29"),
        ("FY2027-P01", "4950.30"),
        ("FY2027-P02", "4471.23"),
    ]

    # --- the manual adjustment: a release of 100.00 on the obligation AVM-US performs
    (first,) = place.rows(
        select(obligation.c.id).where(
            obligation.c.contract_id == contract_id, obligation.c.obligation_key == "O1"
        )
    )
    release = {"amount": "100.00", "currency": GBP}
    measured: dict[str, tuple[Any, ...]] = {}
    for name, actor in (("una", una), ("maya", maya)):
        created = post(
            app_,
            ADJUSTMENTS,
            actor,
            {
                "kind": "MANUAL_RELEASE",
                "contract_id": str(contract_id),
                "effective_date": "2026-06-30",
                "reason_code": "ESTIMATE_CORRECTION",
                "memo": "Service accepted on 30 June 2026",
                "payload": {"obligation_id": str(first["id"]), "amount": dict(release)},
            },
        )
        assert created.status_code == 201, (name, created.text)
        assert created.json()["amount_functional_abs"] == release, name
        adjustment_id = str(created.json()["id"])
        sent = post(app_, f"{ADJUSTMENTS}/{adjustment_id}/submit", actor, {"comment": "OK"})
        assert sent.status_code == 200, (name, sent.text)
        request_id = str(sent.json()["approval_request_id"])
        amount, flags, _, preview, document = _stored(app_, marcus, request_id)
        measured[name] = (sent.json()["amount_functional_abs"], amount, flags, preview, document)
        back = post(app_, f"{ADJUSTMENTS}/{adjustment_id}/withdraw", actor, {"comment": "Kept."})
        assert back.status_code == 200, (name, back.text)
    assert measured["una"] == measured["maya"]
    assert measured["maya"][:3] == (release, release, [])
    assert _revenue_before(measured["maya"][4]) == [
        ("FY2026-P06", "4790.61"),
        ("FY2026-P07", "4950.29"),
        ("FY2026-P08", "4950.29"),
        ("FY2026-P09", "4790.61"),
        ("FY2026-P10", "4950.29"),
        ("FY2026-P11", "4790.61"),
    ]
