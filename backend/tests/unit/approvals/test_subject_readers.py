"""Who reads an approval subject in full, and under which scope a guarded route runs (04 §16.10
rev 1.319 "Who reads a subject in full", API-C-03; 03 REQ-PLT-012 rev 1.146; dev-guide
DG-KRN-AUTH-03 and DG-KRN-APR-06 rev 1.295; item READ-SCOPE-BY-PERMISSION-1, register index 301).

Pure functions over principals built here (DG-TST-18). The two rules through the routes, each
red first on the base of the item, are in ``tests/api/test_read_scope_by_permission.py``.

- ``approvals.readers.READERS`` is held against the registry of subjects — every registered
  type states who reads it, a type the table does not know is read by nobody — and against the
  read registry of files, so that a stored preview, the summary of a dry run and the kernel ask
  ONE set of permissions.
- ``readers.read_in_full`` and ``engine.own_scope_covers``: one permission for every entity;
  scopes of several permissions are never added up; a role on an entity is not a read of it.
- ``engine.find_authority``: a principal's own grants ask nothing further; a delegation is taken
  only by a principal who reads the subject in full.
- ``auth.dependencies.admitted_by``: the context a guard hands on carries the scope of the
  guard's own permission.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Final, Literal
from uuid import UUID

import pytest
from erev_api.approvals import engine, readers, subjects
from erev_api.approvals.subjects import ALL_ENTITIES, TENANT_LEVEL, SubjectEntities
from erev_api.auth import dependencies
from erev_api.auth.permissions import CATALOGUE, DEFAULT_ROLES
from erev_api.auth.principal import Principal, RequestContext, system_principal
from erev_api.domain.platform import file_access
from erev_api.enums import ApprovalSubjectType, PrincipalKind, TenantKind

TENANT: Final = UUID("0a1b2c3d-0000-4000-8000-0000000000aa")
UK: Final = UUID("0a1b2c3d-0000-4000-8000-0000000000d2")
US: Final = UUID("0a1b2c3d-0000-4000-8000-0000000000d3")
BOTH: Final = SubjectEntities(frozenset({UK, US}))
OF_UK: Final = SubjectEntities(frozenset({UK}))
NOW: Final = datetime(2026, 9, 12, 12, tzinfo=UTC)
NO_SESSION: Any = None  # nothing below reads the database
Held = Literal["*"] | frozenset[UUID]
_S = ApprovalSubjectType
CODES: Final = frozenset(permission.code for permission in CATALOGUE)
# The subjects no read permission of the catalogue names (04 §16.10 rev 1.319): they keep what
# every subject had before — a permission of the person's own, whatever it is, for every entity.
ANY_PERMISSION: Final = frozenset(
    {
        _S.ROLE_ASSIGNMENT,
        _S.ROLE_CHANGE,
        _S.SOD_EXCEPTION,
        _S.SUPPORT_GRANT,
        _S.EVIDENCE_SHRED,
        _S.MIGRATION_SSP_REPLAY,
    }
)


def _member(scopes: dict[str, Held], *entity_scope: UUID, membership: bool = False) -> Principal:
    """A person who holds each permission of ``scopes`` for its entities and whose roles name
    ``entity_scope`` (all entities when none is given)."""
    return Principal(
        kind=PrincipalKind.USER,
        id=UUID(int=7),
        tenant_id=TENANT,
        membership_id=UUID(int=8) if membership else None,
        display_name="Rae",
        roles=("revenue_accountant", "viewer"),
        permissions=frozenset(scopes),
        permission_scopes=MappingProxyType(scopes),
        entity_scope=entity_scope or "*",
        auth_method="password",
        mfa_verified_at=NOW,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


def _roles(*grants: tuple[str, UUID]) -> Principal:
    """A member of default roles: one assignment per (role code, entity), as
    ``effective_grants`` adds them up — each permission with the entities of the roles that
    hold it, and the union of the entities of all of them."""
    scopes: dict[str, set[UUID]] = {}
    for role_code, entity_id in grants:
        for code in DEFAULT_ROLES[role_code]:
            scopes.setdefault(code, set()).add(entity_id)
    held: dict[str, Held] = {code: frozenset(ids) for code, ids in scopes.items()}
    return _member(held, *sorted({entity_id for _, entity_id in grants}))


# --- the table --------------------------------------------------------------------------------


def test_every_subject_states_who_reads_it() -> None:
    registered = {subject_type.value for subject_type in subjects.SUBJECTS}
    assert set(readers.READERS) == registered | {readers.CONTRACT}
    assert readers.CONTRACT == engine.CONTRACT_SUBJECT
    for subject_type, stated in readers.READERS.items():
        if subject_type != readers.CONTRACT and _S(subject_type) in ANY_PERMISSION:
            assert stated == readers.ANY_PERMISSION, subject_type
            continue
        assert isinstance(stated, frozenset) and stated, subject_type
        assert stated <= CODES, subject_type
    # the statement over ``approval_request`` names the types of a request, never the pending
    # events of a preview, which are no request
    for code in sorted(CODES):
        assert set(readers.read_with(code)) <= registered, code
    assert {_S(value) for value in readers.read_with_any()} == ANY_PERMISSION
    assert readers.CONTRACT not in readers.read_with("contract.read")
    assert _S.MODIFICATION.value in readers.read_with("contract.read")


def test_a_type_the_table_does_not_know_is_read_by_nobody() -> None:
    """Fail closed: the subject types without a specification (``PENDING_SUBJECTS``) state no
    reader, so no permission reads one that names an entity; one that names none asks nothing."""
    everything = _member(dict.fromkeys(sorted(CODES), "*"))
    for subject_type, _phase in subjects.PENDING_SUBJECTS:
        assert readers.of(subject_type) == frozenset()
        assert not engine.own_scope_covers(everything, subject_type, OF_UK)
        assert not engine.own_scope_covers(everything, subject_type, ALL_ENTITIES)
        assert engine.own_scope_covers(everything, subject_type, TENANT_LEVEL)


def test_a_dry_run_and_the_kernel_ask_one_set_of_readers() -> None:
    """04 §16.10 "Who reads a stored preview" (rev 1.300, rev 1.314) and "Who reads a subject in
    full" (rev 1.319) are one question: the readers of a stored preview and of the summary of a
    dry run are the kernel's readers of the same subject."""
    for subject_type, stated in file_access.STORED_PREVIEW_READERS.items():
        assert readers.of(subject_type) == stated, subject_type
    for subject_type in (_S.ESTIMATE_VERSION, file_access.PENDING_EVENTS):
        assert readers.of(subject_type) == file_access.UNSTORED_PREVIEW_READERS, subject_type


# --- the question -----------------------------------------------------------------------------


def test_a_subject_is_read_in_full_with_one_permission_for_every_entity() -> None:
    modification = _S.MODIFICATION  # read with ``contract.read``
    assert readers.read_in_full({"contract.read": frozenset({UK, US})}, modification, BOTH)
    assert readers.read_in_full({"contract.read": "*"}, modification, BOTH)
    assert readers.read_in_full({"contract.read": "*"}, modification, ALL_ENTITIES)
    assert not readers.read_in_full({"contract.read": frozenset({UK})}, modification, BOTH)
    assert not readers.read_in_full(
        {"contract.read": frozenset({UK, US})}, modification, ALL_ENTITIES
    )
    # another read permission is not this subject's
    assert not readers.read_in_full({"config.read": "*", "ssp.read": "*"}, modification, OF_UK)
    # a tenant-level subject names no entity: nothing to read, whoever asks
    assert readers.read_in_full({}, modification, TENANT_LEVEL)
    # the four of a manual adjustment: ONE of them for every entity, their scopes never added up
    adjustment = _S.MANUAL_ADJUSTMENT
    assert readers.read_in_full({"report.run": frozenset({UK, US})}, adjustment, BOTH)
    assert not readers.read_in_full(
        {"contract.read": frozenset({UK}), "adjustment.create": frozenset({US})}, adjustment, BOTH
    )
    # a subject no read permission names: any permission, the entities added up
    grant = _S.ROLE_ASSIGNMENT
    assert readers.read_in_full(
        {"contract.read": frozenset({UK}), "import.upload": frozenset({US})}, grant, BOTH
    )
    assert not readers.read_in_full({"contract.read": frozenset({UK})}, grant, BOTH)
    assert not readers.read_in_full({}, grant, OF_UK)
    assert readers.read_in_full({"audit.read": "*"}, grant, ALL_ENTITIES)


def test_a_role_on_an_entity_is_not_a_read_of_it() -> None:
    """The two members of the item, as their roles add up. Rae — Revenue Accountant of AVM-UK,
    Viewer of AVM-US — reads a contract subject of both entities. Bea — Revenue Accountant of
    AVM-UK with ``import.upload`` alone for AVM-US — does not, though her roles name both: until
    rev 1.319 the question was the roles' union, and it answered her yes."""
    rae = _roles(("revenue_accountant", UK), ("viewer", US))
    bea = _member(
        {
            **{code: frozenset({UK}) for code in DEFAULT_ROLES["revenue_accountant"]},
            "import.upload": frozenset({UK, US}),
        },
        UK,
        US,
    )
    for subject_type in (
        _S.MODIFICATION,
        _S.ESTIMATE_VERSION,
        _S.MANUAL_ADJUSTMENT,
        readers.CONTRACT,
    ):
        assert engine.own_scope_covers(rae, subject_type, BOTH), subject_type
        assert not engine.own_scope_covers(bea, subject_type, BOTH), subject_type
        assert engine.own_scope_covers(bea, subject_type, OF_UK), subject_type
    assert set(bea.entity_scope) == {UK, US}  # the union still names both
    # the Service Account role reads contracts and no configuration: the Viewer's ``config.read``
    # is for AVM-UK alone
    dana = _roles(("viewer", UK), ("service_account", US))
    assert engine.own_scope_covers(dana, _S.CONTRACT_ACTIVATION, BOTH)
    assert not engine.own_scope_covers(dana, _S.ACCOUNT_MAPPING_VERSION, BOTH)
    assert not engine.own_scope_covers(dana, _S.SSP_BOOK_VERSION, BOTH)
    # the question does not read the scope of the route: a context a guard narrowed answers alike
    narrowed = dependencies.admitted_by(_context(rae), "modification.create").principal
    assert narrowed.entity_scope == (UK,)
    assert engine.own_scope_covers(narrowed, _S.MODIFICATION, BOTH)


def test_a_system_principal_covers_what_its_entity_scope_covers() -> None:
    """A job, provisioning and an import on behalf of its uploader hold no permission of their
    own and no route admits them: they are asked their entity scope, as before."""
    system = system_principal(TENANT)
    assert engine.own_scope_covers(system, _S.MODIFICATION, ALL_ENTITIES)
    narrowed = Principal(
        **{
            **{name: getattr(system, name) for name in system.__dataclass_fields__},
            "permissions": frozenset({"contract.create"}),
            "permission_scopes": MappingProxyType({"contract.create": frozenset({UK})}),
            "entity_scope": (UK,),
        }
    )
    assert engine.own_scope_covers(narrowed, _S.IMPORT_COMMIT, OF_UK)
    assert not engine.own_scope_covers(narrowed, _S.IMPORT_COMMIT, BOTH)


def test_own_grants_ask_nothing_further_and_a_delegation_asks_the_read() -> None:
    """``find_authority``: who holds the step's permission for every entity decides in her own
    right — also with a role that approves and does not read, and whatever permission a routing
    rule gave the step. Without such a grant the principal must read the subject in full before
    a delegation is looked for: a principal who does not is answered None before any read."""

    def authority(principal: Principal, permission: str = "contract.approve") -> Any:
        return engine.find_authority(
            NO_SESSION, principal, permission, BOTH, at=NOW, subject_type=_S.CONTRACT_VOID
        )

    approves_only = _member({"contract.approve": frozenset({UK, US})}, UK, US)
    found = authority(approves_only)
    assert found is not None and found.on_behalf_of_id is None
    assert authority(_member({"config.approve": "*"}), "config.approve") is not None
    # no grant of her own for both entities, and no read of both: nothing is looked up — a
    # member with a membership would otherwise read her delegations from ``NO_SESSION``
    for scopes in (
        {"contract.approve": frozenset({UK})},
        {"contract.approve": frozenset({UK}), "contract.read": frozenset({UK})},
        {"contract.read": frozenset({UK}), "import.upload": frozenset({UK, US})},
    ):
        assert authority(_member(scopes, UK, US, membership=True)) is None, scopes
    # she reads both and holds no membership here: no delegation to take
    assert authority(_member({"contract.read": frozenset({UK, US})}, UK, US)) is None


# --- the guard --------------------------------------------------------------------------------


def _context(principal: Principal) -> RequestContext:
    return RequestContext(
        principal=principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-subject-readers",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=NOW,
        format_locale="en-US",
    )


def test_a_guard_hands_on_the_scope_of_its_own_permission() -> None:
    rae = _roles(("revenue_accountant", UK), ("viewer", US))
    ctx = _context(rae)
    assert rae.entity_scope == (UK, US)
    # the accountant's permission: her command's transaction is AVM-UK's
    admitted = dependencies.admitted_by(ctx, "config.author")
    assert admitted.principal.entity_scope == (UK,)
    assert admitted.principal.db_context.entity_scope == (UK,)
    # nothing else of the principal or of the context moves
    assert admitted.principal.permission_scopes is rae.permission_scopes
    assert admitted.principal.role_scopes is rae.role_scopes
    assert admitted.principal.permissions == rae.permissions
    assert (admitted.request_id, admitted.now) == (ctx.request_id, ctx.now)
    # a read both roles hold keeps both entities, and the context is handed back as it is
    assert dependencies.admitted_by(ctx, "contract.read") is ctx
    # a permission she does not hold names no entity
    assert dependencies.admitted_by(ctx, "period.lock").principal.entity_scope == ()
    # all entities stays all entities; named entities under a wider union are named
    everywhere = _member({"audit.read": "*", "contract.read": frozenset({UK})})
    wide = _context(everywhere)
    assert dependencies.admitted_by(wide, "audit.read") is wide
    assert dependencies.admitted_by(wide, "contract.read").principal.entity_scope == (UK,)


@pytest.mark.parametrize("code", sorted(CODES))
def test_require_hands_on_the_context_of_a_transaction_of_its_permission(code: str) -> None:
    """Every permission of the catalogue: the guard built for it answers the context of a
    transaction of that permission — held here for AVM-UK by a member whose roles name both
    entities. ``require_all_entities`` and ``api.deps.command`` build on this guard."""
    member = _member(dict.fromkeys(sorted(CODES), frozenset({UK})), UK, US)
    admitted = dependencies.require(code)(NO_SESSION, _context(member))
    assert admitted.principal.entity_scope == (UK,)
    assert admitted.principal.permission_scopes[code] == frozenset({UK})
