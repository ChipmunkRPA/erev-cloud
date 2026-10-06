"""The author's authority over a registry version, without a database (PRD BR-UX-06 rev 1.203;
04 §15.3 API-R-13 rev 1.309; item POLICY-TENANT-SCOPE-ALL-ENTITIES-1).

``registry_versions.require_authority`` asks ``config.author`` FOR THE VERSION'S SCOPE: for all
entities when the version is a TENANT or BOOK version — a TENANT version answers for every
entity that states no value of its own, a BOOK version for every entity that keeps the book,
ahead of the entity's own — and for the version's entity when it is an ENTITY version. This
module pins, as pure functions:

* the matrix of holders and scopes: who passes, and what a refused caller is told and leaves on
  record — 403 by name under rule ``T-PLT-10`` after ONE ``DENIED`` event of the command, which
  states the scope asked for the workspace's version and never an entity;
* the check fails closed: a scope that is not ENTITY, and an ENTITY scope that names no entity,
  ask the permission for all entities; holding it for every entity the workspace has today is
  not holding it for all;
* SYSTEM — provisioning, a seed, a job — passes: it acts for the tenant;
* the answer and the event's detail are those of the access commands
  (``platform.users.beyond_scope``, ``platform.users.scope_denial``), which the registry module
  cannot import (DG-ARC-17) and builds itself: the two shapes are held equal here;
* the words of the refusal for an ENTITY version. Since 04 API-C-03 rev 1.319 (item
  READ-SCOPE-BY-PERMISSION-1) a route's transaction runs under the scope of ``config.author``,
  so a command on the version of an entity the caller's permission does not name answers 404,
  or 422 at a create, before the command asks: no route delivers the sentence, it stays the
  command's own statement, and it is spelled out here and not read from the product.

The routes and the audit rows are witnessed in
``tests/domain/policies/test_registry_scope_authority.py``.
"""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.principal import Principal, system_principal
from erev_api.domain.platform import users
from erev_api.domain.policies import registry_versions
from erev_api.enums import PrincipalKind, RegistryScope
from erev_api.problems import Problem

TENANT = UUID(int=0x7E)
E1 = UUID(int=0xE1)
E2 = UUID(int=0xE2)
VERSION = UUID(int=0x5E)
ACTION = "registry_version.update"
PERMISSION = "config.author"
Scope = Any  # "*" or a frozenset of entity ids


def holder(scope: Scope | None) -> Principal:
    """A person who holds ``config.author`` for ``scope``; None: who does not hold it at all."""
    held = {} if scope is None else {PERMISSION: scope}
    return Principal(
        kind=PrincipalKind.USER,
        id=UUID(int=0xA1),
        tenant_id=TENANT,
        membership_id=UUID(int=0xA2),
        display_name="Ella",
        roles=("revenue_accountant",),
        permissions=frozenset(held),
        permission_scopes=MappingProxyType(held),
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """The ``DENIED`` events ``require_authority`` hands the audit writer."""
    calls: list[dict[str, Any]] = []

    def record_denied(ctx: Any, **event: Any) -> None:
        calls.append(event)

    monkeypatch.setattr(registry_versions.audit_writer, "record_denied", record_denied)
    return calls


def asked(
    principal: Principal, scope: RegistryScope | str, entity_id: UUID | None
) -> Problem | None:
    """The refusal ``require_authority`` raises for the caller, or None when it passes."""
    uow = SimpleNamespace(principal=principal, ctx=object(), keyring=object())
    try:
        registry_versions.require_authority(
            uow,  # type: ignore[arg-type]
            scope=scope,
            entity_id=entity_id,
            action=ACTION,
            version_id=VERSION,
        )
    except Problem as refused:
        return refused
    return None


def shape(problem: Problem) -> tuple[str, int, str | None, list[tuple[str | None, str | None]]]:
    return (
        problem.slug,
        problem.status,
        problem.detail,
        [(error.field, error.rule_id) for error in problem.errors],
    )


WORKSPACE = (
    "forbidden",
    403,
    registry_versions.WORKSPACE_BEYOND_SCOPE,
    [(None, "T-PLT-10")],
)
ENTITY = ("forbidden", 403, registry_versions.ENTITY_BEYOND_SCOPE, [(None, "T-PLT-10")])


@pytest.mark.parametrize(
    ("held", "scope", "entity_id"),
    [
        ("*", RegistryScope.TENANT, None),
        ("*", RegistryScope.BOOK, None),
        ("*", RegistryScope.ENTITY, E1),
        ("*", "TENANT", None),  # the stored column is the enum's value
        (frozenset({E1}), RegistryScope.ENTITY, E1),
        (frozenset({E1, E2}), "ENTITY", E2),
    ],
)
def test_a_holder_for_the_versions_scope_passes(
    recorded: list[dict[str, Any]], held: Scope, scope: RegistryScope | str, entity_id: UUID | None
) -> None:
    assert asked(holder(held), scope, entity_id) is None
    assert recorded == []


@pytest.mark.parametrize(
    ("held", "scope", "entity_id", "told", "detail"),
    [
        # the workspace's version: all entities, and no named set is all of them
        (frozenset({E1}), RegistryScope.TENANT, None, WORKSPACE, {"scope": "*"}),
        (frozenset({E1}), RegistryScope.BOOK, None, WORKSPACE, {"scope": "*"}),
        (frozenset({E1, E2}), RegistryScope.TENANT, None, WORKSPACE, {"scope": "*"}),
        (frozenset(), RegistryScope.TENANT, None, WORKSPACE, {"scope": "*"}),
        (None, RegistryScope.BOOK, None, WORKSPACE, {"scope": "*"}),
        # an entity's version: that entity, not another one
        (frozenset({E1}), RegistryScope.ENTITY, E2, ENTITY, {}),
        (frozenset(), "ENTITY", E1, ENTITY, {}),
        (None, RegistryScope.ENTITY, E1, ENTITY, {}),
        # fails closed: an entity scope that names no entity is asked as the workspace's
        (frozenset({E1}), RegistryScope.ENTITY, None, WORKSPACE, {"scope": "*"}),
    ],
)
def test_a_caller_the_scope_does_not_cover_is_refused_by_name_and_on_record(
    recorded: list[dict[str, Any]],
    held: Scope | None,
    scope: RegistryScope | str,
    entity_id: UUID | None,
    told: tuple[Any, ...],
    detail: dict[str, str],
) -> None:
    refused = asked(holder(held), scope, entity_id)
    assert refused is not None and shape(refused) == told
    [event] = recorded
    keyring = event.pop("keyring")
    assert keyring is not None
    assert event == {
        "action": ACTION,
        "object_type": "registry_version",
        "object_id": VERSION,
        "permission": PERMISSION,
        "detail": {"rule_id": "T-PLT-10", **detail},
    }


def test_system_acts_for_the_tenant(recorded: list[dict[str, Any]]) -> None:
    for scope, entity_id in (
        (RegistryScope.TENANT, None),
        (RegistryScope.BOOK, None),
        (RegistryScope.ENTITY, E1),
    ):
        assert asked(system_principal(TENANT), scope, entity_id) is None
    assert recorded == []


def test_the_words_of_the_refusal_for_an_entity_version(recorded: list[dict[str, Any]]) -> None:
    """What the command tells a caller whose ``config.author`` does not cover the entity of an
    ENTITY version — the words a member would read, spelled out. The sentence of a workspace's
    version is spelled out beside its routes (``test_registry_scope_authority.py``)."""
    sentence = (
        "Your access to author policies does not cover the entity of this version. A member whose "
        "access covers it must author it."
    )
    refused = asked(holder(frozenset({E1})), RegistryScope.ENTITY, E2)
    assert refused is not None
    assert (refused.status, refused.slug, refused.detail) == (403, "forbidden", sentence)
    assert [(error.rule_id, error.message) for error in refused.errors] == [("T-PLT-10", sentence)]
    assert len(recorded) == 1


def test_the_refusal_and_its_record_are_those_of_the_access_commands() -> None:
    """``platform.users`` holds the answer by name and the detail of its ``DENIED`` event for the
    commands on access; the registry module is imported on the way to that one and builds the two
    itself. They must not drift."""
    for message in (
        registry_versions.WORKSPACE_BEYOND_SCOPE,
        registry_versions.ENTITY_BEYOND_SCOPE,
    ):
        assert shape(registry_versions.beyond_scope(message)) == shape(users.beyond_scope(message))
    for all_entities in (True, False):
        assert registry_versions.scope_denial(all_entities=all_entities) == users.scope_denial(
            all_entities=all_entities
        )
