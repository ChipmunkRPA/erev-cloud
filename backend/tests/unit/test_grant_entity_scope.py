"""The entity scope of a grant (supervisor ruling R-63 (e); 03 REQ-PLT-012; 04 T-PLT-10, DB-12;
PRD J-22.1): ``erev_api.auth.entity_scope`` — the shape of a request, codes that name legal
entities, and a grantor who never grants beyond their own access. CPU: ``decided`` over the known
entities (DG-TST-18); the routes are witnessed in ``tests/api``."""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth import entity_scope, operators
from erev_api.auth.entity_scope import (
    ALL_AND_NAMED,
    ALL_ENTITIES,
    BEYOND_OWN_SCOPE,
    ENTITIES_EMPTY,
    ENTITY_UNKNOWN,
    EntityScope,
    HeldScope,
)
from erev_api.auth.principal import Principal, system_principal
from erev_api.enums import PrincipalKind

TENANT = UUID("0a1b2c3d-0000-4000-8000-0000000000aa")
DE = UUID("0a1b2c3d-0000-4000-8000-0000000000d1")
UK = UUID("0a1b2c3d-0000-4000-8000-0000000000d2")
US = UUID("0a1b2c3d-0000-4000-8000-0000000000d3")
KNOWN = {"AVM-DE": DE, "AVM-UK": UK, "AVM-US": US}
FIELD = "roles[0].entity_codes"
FLAG = "roles[0].is_all_entities"


def decided(
    held: HeldScope, *, is_all: bool, codes: tuple[str, ...] = ()
) -> tuple[EntityScope | None, list[tuple[str | None, str | None, str]]]:
    scope, findings = entity_scope.decided(
        held=held,
        is_all_entities=is_all,
        entity_codes=codes,
        known=KNOWN,
        field=FIELD,
        shape_field=FLAG,
    )
    return scope, [(item.field, item.rule_id, item.message) for item in findings]


def test_all_entities_is_granted_by_a_grantor_of_every_entity() -> None:
    assert decided("*", is_all=True) == (ALL_ENTITIES, [])
    assert ALL_ENTITIES.entity_ids == () and ALL_ENTITIES.label == "all entities"


def test_named_entities_are_stored_in_code_order_once_each() -> None:
    scope, findings = decided("*", is_all=False, codes=("AVM-US", "AVM-DE", "AVM-US"))
    assert findings == []
    assert scope == EntityScope(False, (DE, US), ("AVM-DE", "AVM-US"))
    assert scope is not None and scope.label == "AVM-DE, AVM-US"


def test_the_request_states_one_shape() -> None:
    # T-PLT-10: is_all_entities = (cardinality(entity_ids) = 0)
    assert decided("*", is_all=True, codes=("AVM-DE",)) == (
        None,
        [(FIELD, "T-PLT-10", ALL_AND_NAMED)],
    )
    assert decided("*", is_all=False) == (None, [(FIELD, "T-PLT-10", ENTITIES_EMPTY)])


def test_a_code_that_names_no_legal_entity_is_refused() -> None:
    # DB-12: one finding for the member, whichever code it is — the answer names none of them
    for codes in (("AVM-FR",), ("AVM-DE", "AVM-FR")):
        assert decided("*", is_all=False, codes=codes) == (
            None,
            [(FIELD, "EREV-REF-002", ENTITY_UNKNOWN)],
        )


def test_a_grantor_of_named_entities_grants_those_and_no_more() -> None:
    held = frozenset({DE, UK})
    scope, findings = decided(held, is_all=False, codes=("AVM-UK", "AVM-DE"))
    assert (scope, findings) == (EntityScope(False, (DE, UK), ("AVM-DE", "AVM-UK")), [])
    # REQ-PLT-012: an entity outside the grantor's own scope answers exactly as an unknown code
    outside = decided(held, is_all=False, codes=("AVM-DE", "AVM-US"))
    unknown = decided(held, is_all=False, codes=("AVM-DE", "AVM-FR"))
    assert outside == unknown == (None, [(FIELD, "EREV-REF-002", ENTITY_UNKNOWN)])
    # — and all entities is more than the grantor holds
    assert decided(held, is_all=True) == (None, [(FLAG, "T-PLT-10", BEYOND_OWN_SCOPE)])


def test_a_principal_without_the_permission_grants_nothing() -> None:
    nobody: HeldScope = frozenset()
    assert decided(nobody, is_all=False, codes=("AVM-DE",)) == (
        None,
        [(FIELD, "EREV-REF-002", ENTITY_UNKNOWN)],
    )
    assert decided(nobody, is_all=True) == (None, [(FLAG, "T-PLT-10", BEYOND_OWN_SCOPE)])


def _user(scopes: dict[str, HeldScope]) -> Principal:
    return Principal(
        kind=PrincipalKind.USER,
        id=UUID(int=7),
        tenant_id=TENANT,
        membership_id=UUID(int=8),
        display_name="Tomas",
        roles=("tenant_admin",),
        permissions=frozenset(scopes),
        permission_scopes=MappingProxyType(scopes),
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


def test_the_held_scope_is_the_permissions_own() -> None:
    admin = _user({"role.manage": "*", "user.manage": frozenset({DE})})
    assert entity_scope.held_scope(admin, "role.manage") == "*"
    assert entity_scope.held_scope(admin, "user.manage") == frozenset({DE})
    assert entity_scope.held_scope(admin, "access.approve") == frozenset()
    # provisioning and jobs act for the tenant
    assert entity_scope.held_scope(system_principal(TENANT), "role.manage") == "*"


def _principal(kind: PrincipalKind, scopes: dict[str, HeldScope], **members: Any) -> Principal:
    return replace(_user(scopes), kind=kind, membership_id=None, roles=(), **members)


def test_what_a_principal_that_is_no_member_holds() -> None:
    """The scope rules ask ``held_scope``, and four kinds of principal reach a workspace besides a
    signed-in member. SYSTEM — a job, an approval's hook — acts for the tenant and covers every
    entity. An API client holds its scopes for the entities of the client. The platform operator
    holds no permission to change anything: under a support grant its four read permissions, in
    its own command of 04 §14.3 none at all — so no scope rule lets it through, and the command
    that issues the first Tenant Admin's invitation again does not ask one
    (``users.issue_invitation_again``; ``tests/domain/platform/test_operator_reinvite.py``)."""
    everything = [(True, ())]  # the first Tenant Admin's role: for all entities
    for acting in (system_principal(TENANT), system_principal(TENANT, on_behalf_of_id=DE)):
        assert entity_scope.held_scope(acting, "user.manage") == "*"
        assert entity_scope.covers(entity_scope.held_scope(acting, "role.manage"), everything)
        assert entity_scope.holds_all(acting, "role.manage")
        assert entity_scope.holds_for(acting, ["period.close"], US)

    client = _principal(
        PrincipalKind.API_CLIENT,
        dict.fromkeys(["period.close", "user.manage"], frozenset({DE})),
    )
    assert entity_scope.held_scope(client, "user.manage") == frozenset({DE})
    assert entity_scope.covers(entity_scope.held_scope(client, "user.manage"), [(False, (DE,))])
    assert not entity_scope.covers(entity_scope.held_scope(client, "user.manage"), everything)
    assert not entity_scope.holds_all(client, "role.manage")
    assert entity_scope.holds_for(client, ["period.close"], DE)
    assert not entity_scope.holds_for(client, ["period.close"], US)

    support = _principal(
        PrincipalKind.OPERATOR,
        dict.fromkeys(sorted(operators.READ_ONLY_PERMISSIONS), "*"),
        support_grant_id=UK,
    )
    own_command = _principal(PrincipalKind.OPERATOR, {})
    for operator in (support, own_command):
        for permission in ("user.manage", "role.manage", "period.close", "settings.manage"):
            assert entity_scope.held_scope(operator, permission) == frozenset()
        assert not entity_scope.covers(entity_scope.held_scope(operator, "user.manage"), everything)
        assert not entity_scope.holds_all(operator, "role.manage")
        assert not entity_scope.holds_for(operator, ["period.close", "settings.manage"], DE)
    assert entity_scope.held_scope(support, "audit.read") == "*"


@pytest.mark.parametrize(
    ("stored", "shown", "stated"),
    [
        ((), [], []),
        ((US, DE), ["AVM-DE", "AVM-US"], ["AVM-DE", "AVM-US"]),
        # an entity the reader's session does not cover: left out of the references, stated by
        # its id in evidence
        ((UK, DE), ["AVM-DE"], ["AVM-DE", str(UK)]),
    ],
)
def test_a_stored_scope_is_read_by_code(
    stored: tuple[UUID, ...], shown: list[str], stated: list[str]
) -> None:
    found = {
        DE: {"id": DE, "code": "AVM-DE", "name": "Avenmoor GmbH (Demo)"},
        US: {"id": US, "code": "AVM-US", "name": "Avenmoor Systems Inc. (Demo)"},
    }
    assert [ref["code"] for ref in entity_scope.refs(found, stored)] == shown
    assert entity_scope.codes(found, stored) == sorted(stated)


def test_a_scope_covers_what_it_names_and_nothing_wider() -> None:
    """The command side (ruling R-63 (e) as refined by R-115 (c)): a command on an assignment or
    a membership needs the actor's permission for every entity the grants name; an all-entities
    grant needs the permission for all entities."""
    de = frozenset({DE})
    assert entity_scope.covers("*", [(True, ()), (False, (DE, UK))])
    assert entity_scope.covers(de, [(False, (DE,))])
    assert entity_scope.covers(de, [])  # a member without a role is covered by every administrator
    assert not entity_scope.covers(de, [(False, (DE, UK))])  # one entity beyond
    assert not entity_scope.covers(de, [(False, (DE,)), (True, ())])  # one all-entities grant
    assert not entity_scope.covers(frozenset(), [(False, (DE,))])
    # ids arrive as stored: uuid or text
    assert entity_scope.covers(de, [(False, (str(DE),))])


def test_a_tenant_wide_act_needs_the_permission_for_all_entities() -> None:
    """Supervisor rulings R-28 and R-115 (c): the definition of a role is held, or may be held,
    for every entity; an administrator of named entities does not change it."""
    assert entity_scope.holds_all(_user({"role.manage": "*"}), "role.manage")
    assert not entity_scope.holds_all(_user({"role.manage": frozenset({DE})}), "role.manage")
    assert not entity_scope.holds_all(_user({"user.manage": "*"}), "role.manage")
    assert entity_scope.holds_all(system_principal(TENANT), "role.manage")


def test_a_command_on_an_entitys_row_needs_its_permission_for_that_entity() -> None:
    """Security finding S18 (ruling R-28): ``period.close`` held for AVM-UK and a role of another
    kind on AVM-US do not open a period of AVM-US; one of several permissions that authorise the
    command is enough when it is held for the entity."""
    pat = _user({"period.close": frozenset({UK}), "contract.read": frozenset({UK, US})})
    assert entity_scope.holds_for(pat, ["period.close"], UK)
    assert not entity_scope.holds_for(pat, ["period.close"], US)
    assert not entity_scope.holds_for(pat, ["period.close", "settings.manage"], US)
    admin = _user({"settings.manage": "*"})
    assert entity_scope.holds_for(admin, ["period.close", "settings.manage"], US)
    assert entity_scope.holds_for(system_principal(TENANT), ["period.close"], US)


def test_a_request_that_reaches_beyond_the_grantor_is_told_from_a_mistake() -> None:
    """``reaches_beyond``: a grantor of named entities asked for all entities, or named a code it
    does not cover — whether or not the code names an entity, so that the record of the attempt
    tells no more than the answer. A grantor of all entities reaches beyond nothing, a granted
    request reached nothing, and a request that states both shapes or neither is malformed."""
    named = frozenset({DE})
    granted = entity_scope.EntityScope(
        is_all_entities=False, entity_ids=(DE,), entity_codes=("AVM-DE",)
    )

    def reached(held: entity_scope.HeldScope, all_entities: bool, *codes: str) -> bool:
        return entity_scope.reaches_beyond(
            held, is_all_entities=all_entities, entity_codes=codes, scope=None
        )

    assert reached(named, True)
    assert reached(named, False, "AVM-US")
    assert reached(named, False, "AVM-FR") is reached(named, False, "AVM-US")
    assert not reached(named, True, "AVM-DE")  # both shapes
    assert not reached(named, False)  # neither
    assert not reached("*", False, "AVM-FR")  # a grantor of all entities: a mistake
    assert not entity_scope.reaches_beyond(
        named, is_all_entities=False, entity_codes=("AVM-DE",), scope=granted
    )
