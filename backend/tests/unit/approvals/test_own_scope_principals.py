"""Whose ENTITY SCOPE answers the kernel's own-scope question, and who is asked by permission
(04 §16.10 rev 1.321 "Who is not asked"; dev-guide DG-KRN-APR-06 rev 1.297; item
SUPPORT-GRANT-OPERATOR-SCOPE-1, register index 307 — a regression of rev 1.319).

Since rev 1.319 the kernel asks a preparer, a delegate and the reader of a request's content
whether she reads the subject in full BY PERMISSION (``approvals.readers``). A principal that
holds no permission of its own and that no route admitted cannot be asked so: the kernel asks
its entity scope, as before that revision. ``engine.asked_by_entity_scope`` names those
principals, for ``engine.own_scope_covers`` and for its SQL twin
``approval_queries._own_scope_covers`` alike:

* kind SYSTEM — a job, provisioning, an import on behalf of its uploader;
* kind OPERATOR that a command built (``auth_method`` ``"system"``) and that holds no permission
  — the provider's operator at the command line. ``erev support-grant request`` acts as it and
  prepares the ``SUPPORT_GRANT`` request, which any permission of a person's own reads: it holds
  none. Measured on d3a1aa5f6, where rev 1.319 asked every principal but SYSTEM by permission:
  the command was refused 403 as a preparer "outside your roles", and the five cases of
  ``tests/domain/platform/test_support_grants.py`` failed on it.

Everyone else is asked by permission, and each condition of the predicate keeps one of them
there: the operator signed in under a grant, whom a route admitted; a person whose principal a
job built, with her grants or with none; an API client without a scope. This module holds the
predicate over those principals, the question and the twin that read it, and the two places of
the product that build an operator's principal — so that a principal which changes its shape
changes an answer here and not only in a database module.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import engine, readers
from erev_api.approvals.subjects import ALL_ENTITIES, SubjectEntities
from erev_api.auth import operators
from erev_api.auth.principal import Principal, system_principal
from erev_api.domain.platform import approval_queries, support_grants
from erev_api.enums import ApprovalSubjectType, PrincipalKind
from sqlalchemy.dialects import postgresql

TENANT = UUID(int=0x7E)
A = UUID(int=0xA)
B = UUID(int=0xB)
OF_A = SubjectEntities(frozenset({A}))
OF_B = SubjectEntities(frozenset({B}))
SIGNED_IN = {
    "auth_method": "password",
    "session_id": UUID(int=0x5E),
    "mfa_verified_at": datetime(2026, 9, 12, 11, 58, tzinfo=UTC),
}
SUPPORT_GRANT = ApprovalSubjectType.SUPPORT_GRANT
CONTRACT_SUBJECT = ApprovalSubjectType.CONTRACT_ACTIVATION  # read with ``contract.read``


def scopes(**held: Any) -> MappingProxyType[str, Any]:
    """Permission scopes: ``contract_read="*"`` holds ``contract.read`` for all entities."""
    return MappingProxyType({code.replace("_", "."): scope for code, scope in held.items()})


def operator(**changes: Any) -> Principal:
    """The provider's operator at the command line, as ``support_grants.request_as_operator``
    builds it (``test_the_two_writers_build_what_the_predicate_reads`` holds the three facts
    the predicate reads against that function), with ``changes``."""
    built = Principal(
        kind=PrincipalKind.OPERATOR,
        id=UUID(int=0x0B),
        tenant_id=TENANT,
        membership_id=None,
        display_name="Olga Operator",
        roles=(),
        permissions=frozenset(),
        permission_scopes=MappingProxyType({}),
        entity_scope="*",
        auth_method="system",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )
    return replace(built, **changes)


def under_a_grant(**changes: Any) -> Principal:
    """The operator signed in under an approved support grant, as ``auth.operators`` builds it:
    a route admitted it, and it holds the read-only permissions for all entities."""
    stated: dict[str, Any] = {
        "permissions": operators.READ_ONLY_PERMISSIONS,
        "permission_scopes": operators._OPERATOR_PERMISSION_SCOPES,
        "support_grant_id": UUID(int=0x64),
        **SIGNED_IN,
        **changes,
    }
    return operator(**stated)


def person(**changes: Any) -> Principal:
    """A member with ``contract.read`` for entity A, signed in."""
    stated: dict[str, Any] = {
        "kind": PrincipalKind.USER,
        "membership_id": UUID(int=0x3E),
        "display_name": "Rae Reader",
        "roles": ("viewer",),
        "permissions": frozenset({"contract.read"}),
        "permission_scopes": scopes(contract_read=frozenset({A})),
        "entity_scope": (A,),
        **SIGNED_IN,
        **changes,
    }
    return operator(**stated)


# A person as a job builds her to act as its requester (``sandboxes.sandbox_actor``): her
# grants, no session, ``auth_method`` "system". And the same person holding a role that grants
# no permission: an entity in her scope and nothing to be asked by.
BY_A_JOB = {"auth_method": "system", "session_id": None, "mfa_verified_at": None}
NO_PERMISSION = {"permissions": frozenset(), "permission_scopes": scopes()}

ASKED_BY_ENTITY_SCOPE: tuple[tuple[str, Principal], ...] = (
    ("SYSTEM", system_principal(TENANT)),
    ("SYSTEM on behalf of an uploader", system_principal(TENANT, on_behalf_of_id=UUID(int=0x0C))),
    ("the operator at the command line", operator()),
    ("the operator at the command line, unknown as a user", operator(id=None)),
)
ASKED_BY_PERMISSION: tuple[tuple[str, Principal], ...] = (
    ("the operator under a grant", under_a_grant()),
    ("an operator a route admitted, without a permission", operator(**SIGNED_IN)),
    (
        "an operator a command built WITH a permission",
        operator(
            permissions=frozenset({"contract.read"}),
            permission_scopes=scopes(contract_read=frozenset({A})),
        ),
    ),
    ("a person", person()),
    ("a person a job built", person(**BY_A_JOB)),
    ("a person a job built, without a permission", person(**BY_A_JOB, **NO_PERMISSION)),
    ("a person without a permission", person(**NO_PERMISSION)),
    (
        "an API client without a scope",
        person(
            kind=PrincipalKind.API_CLIENT,
            membership_id=None,
            roles=(),
            entity_scope=(),
            auth_method="client_credentials",
            session_id=None,
            mfa_verified_at=None,
            **NO_PERMISSION,
        ),
    ),
)


@pytest.mark.parametrize(("who", "principal"), ASKED_BY_ENTITY_SCOPE)
def test_a_principal_no_route_admitted_and_without_a_permission_is_asked_by_its_entity_scope(
    who: str, principal: Principal
) -> None:
    assert engine.asked_by_entity_scope(principal) is True, who


@pytest.mark.parametrize(("who", "principal"), ASKED_BY_PERMISSION)
def test_everyone_else_is_asked_by_permission(who: str, principal: Principal) -> None:
    assert engine.asked_by_entity_scope(principal) is False, who


def test_the_operator_at_the_command_line_prepares_its_support_grant_request() -> None:
    """The regression. A ``SUPPORT_GRANT`` request names every entity and is read by any
    permission of the person's own; the operator at the command line holds none, so the table of
    readers answers no for it — and the kernel's question answers yes, by its entity scope, as
    it does for SYSTEM."""
    at_the_command_line = operator()
    assert readers.read_in_full(
        at_the_command_line.permission_scopes, SUPPORT_GRANT, ALL_ENTITIES
    ) is (False)
    assert engine.own_scope_covers(at_the_command_line, SUPPORT_GRANT, ALL_ENTITIES) is True
    assert engine.own_scope_covers(system_principal(TENANT), SUPPORT_GRANT, ALL_ENTITIES) is True
    # the entity scope is what answers: narrowed to A it covers A and nothing else
    narrowed = operator(entity_scope=(A,))
    assert engine.own_scope_covers(narrowed, SUPPORT_GRANT, OF_A) is True
    assert engine.own_scope_covers(narrowed, SUPPORT_GRANT, OF_B) is False
    assert engine.own_scope_covers(narrowed, SUPPORT_GRANT, ALL_ENTITIES) is False


def test_an_operator_under_a_grant_and_a_person_are_asked_by_what_they_hold() -> None:
    """Rev 1.319 stands for them: a role or a grant on an entity is not a read of it. Each of
    these principals has an entity scope that covers the subject and is refused, or admitted,
    by its permissions alone."""
    # the grant's own scopes read a contract subject and a support grant of every entity
    assert engine.own_scope_covers(under_a_grant(), CONTRACT_SUBJECT, ALL_ENTITIES) is True
    assert engine.own_scope_covers(under_a_grant(), SUPPORT_GRANT, ALL_ENTITIES) is True
    # ... and it is those scopes that answer: held for A alone they read A alone, whatever
    # the entity scope of the session ("*")
    for_a = scopes(
        **dict.fromkeys(("audit_read", "config_read", "contract_read", "ssp_read"), frozenset({A}))
    )
    narrowed = under_a_grant(permission_scopes=for_a)
    assert narrowed.entity_scope == "*"
    assert engine.own_scope_covers(narrowed, CONTRACT_SUBJECT, OF_A) is True
    assert engine.own_scope_covers(narrowed, CONTRACT_SUBJECT, OF_B) is False
    assert engine.own_scope_covers(narrowed, SUPPORT_GRANT, ALL_ENTITIES) is False
    # an operator a route admitted without any permission reads nothing that names an entity
    assert engine.own_scope_covers(operator(**SIGNED_IN), SUPPORT_GRANT, ALL_ENTITIES) is False
    # a person a job built: entity A is in her scope; with her read she covers it, without a
    # permission she does not — the union of her roles' entities is no read
    assert engine.own_scope_covers(person(**BY_A_JOB), CONTRACT_SUBJECT, OF_A) is True
    without = person(**BY_A_JOB, **NO_PERMISSION)
    assert without.entity_scope == (A,)
    assert engine.own_scope_covers(without, CONTRACT_SUBJECT, OF_A) is False
    assert engine.own_scope_covers(without, SUPPORT_GRANT, OF_A) is False


def _sql(principal: Principal) -> str:
    """The SQL twin for ``principal``, as PostgreSQL text with its parameters unbound."""
    clause = approval_queries._own_scope_covers(principal)
    return str(clause.compile(dialect=postgresql.dialect()))


def test_the_sql_twin_reads_the_same_predicate() -> None:
    """``approval_queries._own_scope_covers`` is the question over the stored columns of a
    request: for a principal asked by its entity scope it holds no word of the subject's type —
    every request for all entities, the request's entities against the scope otherwise; for a
    principal asked by permission it names the types each permission reads."""
    for who, principal in ASKED_BY_ENTITY_SCOPE:
        assert _sql(principal) == "true", who
    narrowed = _sql(operator(entity_scope=(A,)))
    assert narrowed != "true" and "subject_type" not in narrowed
    for who, principal in ASKED_BY_PERMISSION:
        twin = _sql(principal)
        assert twin != "true", who
        # whoever holds a permission is asked by the types it reads
        assert ("subject_type" in twin) is bool(principal.permission_scopes), who


def _built(function: Callable[..., Any]) -> dict[str, str]:
    """The keyword arguments of the one ``Principal(...)`` a function builds, as source text."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    [call] = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Principal"
    ]
    return {str(keyword.arg): ast.unparse(keyword.value) for keyword in call.keywords}


def test_the_two_writers_build_what_the_predicate_reads() -> None:
    """The predicate reads three facts of a principal — its kind, its ``auth_method`` and whether
    it holds a permission — and the product builds an operator's principal in two places that
    reach the kernel's question or its twin. The command line states all three as the predicate
    names them; the session under a grant states its permissions and an ``auth_method`` that is
    never "system". A writer that changes one of them changes who is asked what."""
    command_line = _built(support_grants.request_as_operator)
    assert (
        command_line["kind"],
        command_line["auth_method"],
        command_line["permission_scopes"],
    ) == ("PrincipalKind.OPERATOR", "'system'", "MappingProxyType({})")
    mine = operator()
    assert (mine.kind, mine.auth_method, dict(mine.permission_scopes)) == (
        PrincipalKind.OPERATOR,
        "system",
        {},
    )
    signed_in = _built(operators._operator_principal)
    assert signed_in["kind"] == "PrincipalKind.OPERATOR"
    assert signed_in["permission_scopes"] == "_OPERATOR_PERMISSION_SCOPES"
    assert "'system'" not in signed_in["auth_method"]
    assert dict(operators._OPERATOR_PERMISSION_SCOPES) == dict.fromkeys(
        sorted(operators.READ_ONLY_PERMISSIONS), "*"
    )
