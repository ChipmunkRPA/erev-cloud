"""Who a seeded rule set is read for — the part of ``engine._seeded_admitted`` that needs no row
(04 §14.3 item 2 rev 1.254; dev-guide DG-KRN-APR-08 rev 1.242; item SBX-EMPTY-BOOTSTRAP-1).

The bootstrap Tenant Admin is known by a ``ROLE_ASSIGNMENT`` request "prepared by SYSTEM with no
preparer" that rule ``AUTO-BOOTSTRAP`` approved (``routing.is_bootstrap_admin``). That names the
request of the seed of a workspace, and no other, only while the approvals engine never lets the
rule approve a request that carries no preparer — which ``engine.submit`` writes for a job, whose
principal has no id. It does not: a seeded rule set is read for a signed-in member and for no
other principal, and that is decided before a row is read, so the session here is one that fails
when it is touched. Both halves of the guard are held — the kind and the membership — although
no principal of the product has one without the other; and the basis of a bootstrap approval is
stated for a member only, which stops a reading handed to ``submit`` from outside.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.approvals import engine, routing
from erev_api.approvals.subjects import ALL_ENTITIES
from erev_api.auth.principal import Principal, system_principal
from erev_api.enums import ApprovalSubjectType, PrincipalKind

TENANT: Final = UUID("00000000-0000-0000-0000-0000000000e0")
USER: Final = UUID("00000000-0000-0000-0000-0000000000e1")
MEMBERSHIP: Final = UUID("00000000-0000-0000-0000-0000000000e2")
NOW: Final = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
ROLE_ASSIGNMENT: Final = ApprovalSubjectType.ROLE_ASSIGNMENT
SEEDED: Final = (ROLE_ASSIGNMENT, ApprovalSubjectType.MIGRATION_SSP_REPLAY)


class _Untouched:
    """A session no statement may reach."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the session was read ({name}) before the principal was judged")


@dataclass(frozen=True, slots=True)
class _Uow:
    principal: Principal
    session: Any
    now: datetime = NOW


def _admin(kind: PrincipalKind, *, membership_id: UUID | None) -> Principal:
    """A principal of ``kind`` that states the Tenant Admin role, as a session would."""
    return Principal(
        kind=kind,
        id=USER,
        tenant_id=TENANT,
        membership_id=membership_id,
        display_name="Seeded admission probe",
        roles=(routing.BOOTSTRAP_ROLE,),
        permissions=frozenset({"access.approve"}),
        permission_scopes=MappingProxyType({"access.approve": "*"}),
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=NOW,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


NOT_A_MEMBER: Final = {
    "a job for no user": system_principal(TENANT),
    "a job on behalf of a user": system_principal(TENANT, on_behalf_of_id=USER),
    "a job that states the role": replace(
        system_principal(TENANT, on_behalf_of_id=USER), roles=(routing.BOOTSTRAP_ROLE,)
    ),
    "an API client": _admin(PrincipalKind.API_CLIENT, membership_id=None),
    "an operator": _admin(PrincipalKind.OPERATOR, membership_id=None),
    "a user without a membership": _admin(PrincipalKind.USER, membership_id=None),
    # No principal of the product is one of these three: the kind decides by itself.
    "a job that names a membership": replace(
        system_principal(TENANT, on_behalf_of_id=USER),
        roles=(routing.BOOTSTRAP_ROLE,),
        membership_id=MEMBERSHIP,
    ),
    "an API client that names a membership": _admin(
        PrincipalKind.API_CLIENT, membership_id=MEMBERSHIP
    ),
    "an operator that names a membership": _admin(PrincipalKind.OPERATOR, membership_id=MEMBERSHIP),
}


@pytest.mark.parametrize("who", sorted(NOT_A_MEMBER))
@pytest.mark.parametrize("subject_type", SEEDED)
def test_a_seeded_rule_set_is_read_for_a_signed_in_member_only(
    who: str, subject_type: ApprovalSubjectType
) -> None:
    uow: Any = _Uow(principal=NOT_A_MEMBER[who], session=_Untouched())
    assert engine._seeded_admitted(uow, subject_type, setup_completed=False) is False


def test_the_seeded_subjects_are_the_two_the_documents_name() -> None:
    """04 §14.3 item 2 and §16.10: the subjects only their provisioning-seeded rule set
    approves. A third one would need its own answer to who prepares it."""
    assert set(routing.SEEDED_RULE_SETS) == set(SEEDED)
    assert routing.SEEDED_RULE_SETS[ROLE_ASSIGNMENT] == routing.AUTO_BOOTSTRAP


def test_a_member_who_is_no_tenant_admin_is_refused_before_a_row_is_read() -> None:
    """The second fact of the bootstrap exception — the preparer still holds the role — is the
    principal's, so a member without it never reaches ``routing.is_bootstrap_admin``; a Tenant
    Admin does, once setup is known to be incomplete."""
    member = replace(_admin(PrincipalKind.USER, membership_id=MEMBERSHIP), roles=("viewer",))
    uow: Any = _Uow(principal=member, session=_Untouched())
    assert engine._seeded_admitted(uow, ROLE_ASSIGNMENT, setup_completed=False) is False
    admin = _admin(PrincipalKind.USER, membership_id=MEMBERSHIP)
    done: Any = _Uow(principal=admin, session=_Untouched())
    assert engine._seeded_admitted(done, ROLE_ASSIGNMENT, setup_completed=True) is False
    with pytest.raises(AssertionError, match="the session was read"):
        engine._seeded_admitted(done, ROLE_ASSIGNMENT, setup_completed=False)


@pytest.mark.parametrize("who", ["a job for no user", "a job on behalf of a user", "an API client"])
def test_the_basis_of_a_bootstrap_approval_is_stated_for_a_member_only(who: str) -> None:
    """``engine._auto_basis`` is what ``submit`` asks when it audits an approval by rule
    ``AUTO-BOOTSTRAP``. It refuses a principal without a membership: a reading handed to
    ``submit`` that names the rule for the request of a job — the one request ``submit`` writes
    without a preparer — ends in this error, inside the transaction, and not in an approval."""
    rule = routing.RuleRef(
        rule_set_version_id=UUID("00000000-0000-0000-0000-0000000000e3"),
        rule_id=UUID("00000000-0000-0000-0000-0000000000e4"),
        rule_set_code=routing.AUTO_BOOTSTRAP,
        rule_key=routing.AUTO_BOOTSTRAP,
    )
    uow: Any = _Uow(principal=NOT_A_MEMBER[who], session=_Untouched())
    with pytest.raises(ValueError, match="approves the request of a member only"):
        engine._auto_basis(uow, ROLE_ASSIGNMENT, rule, ALL_ENTITIES)
