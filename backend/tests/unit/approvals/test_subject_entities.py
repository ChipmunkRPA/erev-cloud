"""The legal entities of an approval subject as pure functions (04 T-PLT-17 rev 1.104, §16.10
"Entity scope of a request"; dev-guide DG-KRN-APR-06, DG-KRN-APR-07; REQ-PLT-012; supervisor ruling
R-25 on the security review's findings SN-4, SC-5 and SC-N5).

``SubjectEntities`` is the rule in one place: a decision needs a scope that covers EVERY entity, a
listing a scope that covers at least one, and a subject that spans every entity only scope ``*``.
``test_every_subject_states_its_entities`` pins the classification of the registry, so a new E-08
subject — or a subject that falls back to "no entity" — is a knowing edit of this list and of 04
§16.10, never a default.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.approvals import engine, subjects
from erev_api.approvals.subjects import ALL_ENTITIES, TENANT_LEVEL, SubjectEntities
from erev_api.auth.principal import Principal, system_principal
from erev_api.enums import ApprovalSubjectType, PrincipalKind

A: Final = UUID("00000000-0000-0000-0000-00000000000a")
B: Final = UUID("00000000-0000-0000-0000-00000000000b")
C: Final = UUID("00000000-0000-0000-0000-00000000000c")
TENANT: Final = UUID("00000000-0000-0000-0000-0000000000f0")
USER: Final = UUID("00000000-0000-0000-0000-0000000000f1")

_S = ApprovalSubjectType
# 04 §16.10 rev 1.104, last row of "Entity scope of a request": the subjects that belong to no legal
# entity. Every other registered subject names a resolver.
TENANT_LEVEL_SUBJECTS: Final = frozenset(
    {
        _S.ROLE_CHANGE,
        _S.SOD_EXCEPTION,
        _S.FX_RATE_SET_VERSION,
        _S.RULE_SET_VERSION,
        _S.POB_TEMPLATE_VERSION,
        _S.PRINCIPAL_AGENT_CHANGE,
        _S.MAPPING_PROFILE_VERSION,
        _S.MIGRATION_SSP_REPLAY,
    }
)
# The subjects that can name several entities or span all of them (``SubjectSpec.entities``).
SEVERAL_ENTITY_SUBJECTS: Final = frozenset(
    {
        _S.IMPORT_COMMIT,
        _S.COMBINATION_GROUP,
        # R-41 (4), R-64 (2): the entities its rules name and those of the version it ends.
        _S.ACCOUNT_MAPPING_VERSION,
        # R-64 (1), R-70 (b): a contract subject names the contracting entities of every current
        # member of the contract's combination group (``subjects.contract_group_entities``).
        _S.CONTRACT_ACTIVATION,
        _S.CONTRACT_VOID,
        _S.MODIFICATION,
        _S.MANUAL_EVENT,
        _S.ATTRIBUTE_CHANGE,
        _S.POLICY_OVERRIDE,
        _S.SSP_OVERRIDE,
        _S.ESTIMATE_VERSION,
        _S.JUDGEMENT_RECORD,
        # 04 §16.10 rev 1.104 part 11 (R-64 (1) where it meets CLO-12): the approval of an
        # adjustment recomputes the group of its contract (``manual_adjustment_entities``).
        _S.MANUAL_ADJUSTMENT,
        # 04 §16.10 rev 1.219 (item SCOPE-WORKSPACE-LISTS-1; ruling R-115 (c)): an operator's
        # access reaches the whole workspace, so the request spans every entity
        # (``support_grant_entities``) — until then a tenant-level subject any holder decided.
        _S.SUPPORT_GRANT,
        # 04 §16.10 rev 1.218 (item EXC-IMPORT-SCOPE-1; supervisor ruling R-121 (k)): the waiver
        # of an import's item that names no entity states the entities its upload names, as the
        # upload's ``IMPORT_COMMIT`` request reads them (``exception_waiver_entities``).
        _S.EXCEPTION_WAIVER,
        # 04 §16.10 rev 1.309 (item POLICY-TENANT-SCOPE-ALL-ENTITIES-1; PRD BR-UX-06 rev 1.203):
        # a tenant- or book-scope version is the workspace's, so its request spans every
        # entity, and an entity-scope version names its entity (``registry_version_entities``)
        # — until then one resolver that answered None for the first two, a tenant-level
        # request any holder decided, and was listed in neither set of this module.
        _S.REGISTRY_VERSION,
    }
)
# The subjects without a row that state their entities in the proposal they hash
# (``SubjectSpec.proposal_entities``; R-41 (4)): the entities of the proposed grant; the entities
# of the records that hold the file an ``EVIDENCE_SHRED`` request would shred (04 §16.10 rev
# 1.142; supervisor rulings R-49 (a), R-86, R-119 (g)).
PROPOSAL_ENTITY_SUBJECTS: Final = frozenset({_S.ROLE_ASSIGNMENT, _S.EVIDENCE_SHRED})


def test_covered_by_needs_every_entity() -> None:
    both = SubjectEntities(frozenset({A, B}))
    assert both.covered_by("*")
    assert both.covered_by(frozenset({A, B}))
    assert both.covered_by(frozenset({A, B, C}))
    assert not both.covered_by(frozenset({A}))
    assert not both.covered_by(frozenset({C}))
    assert not both.covered_by(frozenset())


def test_touched_by_needs_one_entity() -> None:
    both = SubjectEntities(frozenset({A, B}))
    assert both.touched_by("*")
    assert both.touched_by(frozenset({A}))
    assert both.touched_by(frozenset({B, C}))
    assert not both.touched_by(frozenset({C}))
    assert not both.touched_by(frozenset())


def test_tenant_level_subject_is_covered_by_any_holder() -> None:
    for scope in ("*", frozenset({A}), frozenset()):
        assert TENANT_LEVEL.covered_by(scope)  # type: ignore[arg-type]
        assert TENANT_LEVEL.touched_by(scope)  # type: ignore[arg-type]


def test_subject_of_every_entity_needs_scope_star() -> None:
    assert ALL_ENTITIES.covered_by("*") and ALL_ENTITIES.touched_by("*")
    for scope in (frozenset({A}), frozenset({A, B, C}), frozenset()):
        # What the engine cannot name it neither lets a scoped holder decide nor shows it.
        assert not ALL_ENTITIES.covered_by(scope)
        assert not ALL_ENTITIES.touched_by(scope)
    with pytest.raises(ValueError, match="names none"):
        SubjectEntities(frozenset({A}), all_entities=True)


@pytest.mark.parametrize(
    ("entities", "columns"),
    [
        (TENANT_LEVEL, {"entity_id": None, "entity_ids": [], "is_all_entities": False}),
        (
            SubjectEntities(frozenset({A})),
            {"entity_id": A, "entity_ids": [], "is_all_entities": False},
        ),
        (
            SubjectEntities(frozenset({B, A})),
            {"entity_id": None, "entity_ids": [A, B], "is_all_entities": False},
        ),
        (ALL_ENTITIES, {"entity_id": None, "entity_ids": [], "is_all_entities": True}),
    ],
)
def test_request_columns_round_trip(entities: SubjectEntities, columns: dict[str, Any]) -> None:
    """One entity is stored in ``entity_id`` (the RLS-TE key), several in ``entity_ids``, every
    entity as the flag — the three forms ``ck_approval_request__entity_scope`` keeps apart — and a
    request reads back exactly the set it froze."""
    assert engine.entity_columns(entities) == columns
    assert engine.request_entities(columns) == entities


def test_request_entities_reads_a_set_a_snapshot_cut_left_with_one_member() -> None:
    """A partial snapshot cut may leave one member in ``entity_ids`` (04 T-PLT-17 rev 1.104): it
    still names that entity."""
    row = {"entity_id": None, "entity_ids": [A], "is_all_entities": False}
    assert engine.request_entities(row) == SubjectEntities(frozenset({A}))


def test_request_entities_needs_the_three_columns() -> None:
    """A row without the columns is an error, never a tenant-level request."""
    with pytest.raises(KeyError):
        engine.request_entities({"entity_id": None})


def test_every_subject_states_its_entities() -> None:
    registered = set(subjects.SUBJECTS)
    assert TENANT_LEVEL_SUBJECTS <= registered
    assert SEVERAL_ENTITY_SUBJECTS <= registered
    assert PROPOSAL_ENTITY_SUBJECTS <= registered
    for subject_type, spec in subjects.SUBJECTS.items():
        tenant_level = spec.entity_id is subjects._tenant_level
        several = spec.entities is not None
        proposed = spec.proposal_entities is not None
        assert tenant_level == (subject_type in TENANT_LEVEL_SUBJECTS), subject_type
        assert several == (subject_type in SEVERAL_ENTITY_SUBJECTS), subject_type
        assert proposed == (subject_type in PROPOSAL_ENTITY_SUBJECTS), subject_type
        if several:
            # One source only: a subject that states a set never also answers ``entity_id``.
            assert spec.entity_id is subjects._resolved_by_entities, subject_type
        if proposed:
            assert spec.entity_id is subjects._stated_by_proposal, subject_type
            assert spec.proposal_content is not None and not several, subject_type
        assert getattr(spec.entity_id, "__name__", "") != "<lambda>", subject_type


def test_api_client_grant_rides_on_role_assignment_and_states_its_entities() -> None:
    """Supervisor ruling R-38 (iii) (04 T-PLT-15 and §16.10 rev 1.168): an API client's scopes are
    an access grant decided under the routing of ``ROLE_ASSIGNMENT``. Its proposal names itself by
    ``object_type`` and states its entities exactly as a role grant does, so an all-entities
    client takes ``access.approve`` for all entities and a proposal that names neither fails
    closed."""
    proposal = subjects.api_client_grant_proposal(
        api_client_id=C,
        name="svc-salesforce",
        client_id="erevc_probe",
        scopes=["import.upload", "contract.create"],
        is_all_entities=True,
        entity_ids=(),
        expires_at=datetime(2027, 9, 12, 12, tzinfo=UTC),
        rate_limit_per_minute=600,
    )
    assert subjects.is_api_client_grant(proposal)
    assert not subjects.is_api_client_grant(
        subjects.role_assignment_proposal(
            membership_id=A,
            role_id=B,
            role_code="viewer",
            is_all_entities=True,
            entity_ids=(),
            sod_exception_id=None,
        )
    )
    assert (proposal["object_type"], proposal["api_client_id"], proposal["scopes"]) == (
        "api_client",
        str(C),
        ["contract.create", "import.upload"],
    )
    assert subjects.role_assignment_entities(None, proposal) == ALL_ENTITIES  # type: ignore[arg-type]
    named = {**proposal, "is_all_entities": False, "entity_ids": [str(B), str(A)]}
    assert subjects.role_assignment_entities(None, named) == SubjectEntities(frozenset({A, B}))  # type: ignore[arg-type]
    neither = {**proposal, "is_all_entities": False, "entity_ids": []}
    assert subjects.role_assignment_entities(None, neither) == ALL_ENTITIES  # type: ignore[arg-type]
    spec = subjects.SUBJECTS[ApprovalSubjectType.ROLE_ASSIGNMENT]
    assert spec.on_rejected is spec.on_voided is subjects._close_role_assignment


def test_role_assignment_states_the_entities_of_the_proposed_grant() -> None:
    """R-41 (4): a ``ROLE_ASSIGNMENT`` request is bound to the entities of the grant it proposes;
    an all-entities grant spans every entity, so deciding it takes ``access.approve`` for all
    entities. A proposal that names neither is malformed and fails closed."""

    def proposed(**members: Any) -> SubjectEntities:
        return subjects.role_assignment_entities(None, members)  # type: ignore[arg-type]

    assert proposed(is_all_entities=True, entity_ids=[]) == ALL_ENTITIES
    assert proposed(is_all_entities=False, entity_ids=[str(A)]) == SubjectEntities(frozenset({A}))
    assert proposed(is_all_entities=False, entity_ids=[str(B), str(A)]) == SubjectEntities(
        frozenset({A, B})
    )
    assert proposed(is_all_entities=False, entity_ids=[]) == ALL_ENTITIES
    assert proposed() == ALL_ENTITIES
    built = subjects.role_assignment_proposal(
        membership_id=USER,
        role_id=TENANT,
        role_code="controller",
        is_all_entities=False,
        entity_ids=[B],
        sod_exception_id=None,
    )
    assert subjects.role_assignment_entities(None, built) == SubjectEntities(  # type: ignore[arg-type]
        frozenset({B})
    )


def _reading(scopes: dict[str, Any], *entity_scope: UUID) -> Principal:
    """A person who holds ``scopes`` and whose roles name ``entity_scope`` (all entities when
    none is given)."""
    person = _person({})
    return Principal(
        **{
            **{name: getattr(person, name) for name in person.__dataclass_fields__},
            "permissions": frozenset(scopes),
            "permission_scopes": MappingProxyType(scopes),
            "entity_scope": entity_scope or "*",
        }
    )


def test_own_entity_scope_must_cover_every_entity() -> None:
    """R-41 (1): a delegation conveys the permission, not the view — the decider reads every
    entity of the subject in its OWN right, whoever's authority it decides with. Since 04 rev
    1.319 (register index 301) that view is a permission that reads the subject, held for every
    entity of it; until then it was the union of the entities of the decider's roles, which this
    test asserted. A role on an entity that reads nothing of the subject does not cover it
    (``tests/unit/approvals/test_subject_readers.py`` holds the table and the rule)."""
    void = _S.CONTRACT_VOID  # read with ``contract.read``
    everywhere = _reading({"contract.read": "*"})
    scoped = _reading({"contract.read": frozenset({A})}, A)
    both = SubjectEntities(frozenset({A, B}))
    assert engine.own_scope_covers(everywhere, void, both)
    assert engine.own_scope_covers(everywhere, void, ALL_ENTITIES)
    assert engine.own_scope_covers(scoped, void, SubjectEntities(frozenset({A})))
    assert engine.own_scope_covers(scoped, void, TENANT_LEVEL)
    assert not engine.own_scope_covers(scoped, void, both)
    assert not engine.own_scope_covers(scoped, void, ALL_ENTITIES)
    # The roles' union covers both entities; the read covers one: not covered.
    elsewhere = _reading({"contract.read": frozenset({A}), "import.upload": frozenset({B})}, A, B)
    assert not engine.own_scope_covers(elsewhere, void, both)
    # Listing still needs one entity only.
    assert engine.in_entity_scope(scoped, both)


def test_union_of_authorities_is_for_listing_only() -> None:
    a_only: dict[str, Any] = {"contract.approve": frozenset({A})}
    b_only: dict[str, Any] = {"contract.approve": frozenset({B}), "event.approve": "*"}
    union = engine.union_scopes([a_only, b_only])
    assert union == {"contract.approve": frozenset({A, B}), "event.approve": "*"}
    assert engine.union_scopes([a_only, {"contract.approve": "*"}]) == {"contract.approve": "*"}
    assert engine.union_scopes([]) == {}


def test_entities_in_the_audit_event_of_a_submission() -> None:
    """R-41 (8): the submit audit event states the entity set the request froze, and each step
    the role it is narrowed to."""
    assert engine.entities_audit(SubjectEntities(frozenset({B, A}))) == {
        "entity_ids": sorted([str(A), str(B)]),
        "all_entities": False,
    }
    assert engine.entities_audit(ALL_ENTITIES) == {"entity_ids": [], "all_entities": True}
    from erev_api.approvals import routing

    role_id = C
    routed = routing.Routing(
        steps=(
            routing.StepPlan(name="Approval", permission="contract.approve", min_approvers=1),
            routing.StepPlan(
                name="Second approval",
                permission="contract.approve",
                min_approvers=1,
                role_id=role_id,
            ),
        ),
        rule=None,
    )
    after = engine.submit_audit_after(
        request_no="APR-000001",
        subject_type=_S.CONTRACT_VOID,
        subject_id=USER,
        subject_content_sha256="a" * 64,
        impact_preview_sha256=None,
        routed=routed,
        entities=SubjectEntities(frozenset({A})),
        role_codes={role_id: "controller"},
    )
    assert after["entities"] == {"entity_ids": [str(A)], "all_entities": False}
    assert after["steps"] == [
        {"name": "Approval", "permission": "contract.approve", "min_approvers": 1},
        {
            "name": "Second approval",
            "permission": "contract.approve",
            "min_approvers": 1,
            "role": "controller",
        },
    ]


def _person(role_scopes: dict[str, Any]) -> Principal:
    scopes: dict[str, Any] = {"contract.approve": "*"}
    return Principal(
        kind=PrincipalKind.USER,
        id=USER,
        tenant_id=TENANT,
        membership_id=None,
        display_name="Probe person",
        roles=tuple(sorted(role_scopes)),
        permissions=frozenset(scopes),
        permission_scopes=MappingProxyType(scopes),
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
        role_scopes=MappingProxyType(role_scopes),
    )


def test_step_role_counts_only_for_the_subjects_entities() -> None:
    """SC-N5 (04 T-PLT-18 rev 1.104): a role held for entity B does not meet a step's role
    requirement for a subject of entity A."""
    step_role = {"code": "controller", "name": "Controller"}
    of_a = SubjectEntities(frozenset({A}))
    assert engine._holds_step_role(_person({"controller": frozenset({A})}), step_role, of_a)
    assert engine._holds_step_role(_person({"controller": "*"}), step_role, of_a)
    assert not engine._holds_step_role(_person({"controller": frozenset({B})}), step_role, of_a)
    assert not engine._holds_step_role(_person({"revenue_reviewer": "*"}), step_role, of_a)
    # A subject of two entities needs the role for both; one that spans every entity for all.
    both = SubjectEntities(frozenset({A, B}))
    assert not engine._holds_step_role(_person({"controller": frozenset({A})}), step_role, both)
    assert engine._holds_step_role(_person({"controller": frozenset({A, B})}), step_role, both)
    assert not engine._holds_step_role(
        _person({"controller": frozenset({A, B})}), step_role, ALL_ENTITIES
    )
    # A step without a role asks for none; a tenant-level subject is met by any assignment.
    assert engine._holds_step_role(_person({}), None, of_a)
    assert engine._holds_step_role(_person({"controller": frozenset({B})}), step_role, TENANT_LEVEL)


def test_principal_without_role_scopes_holds_no_role() -> None:
    """``Principal.role_scopes`` defaults to empty: a principal built without it fails closed."""
    bare = system_principal(TENANT)
    assert dict(bare.role_scopes) == {}
    assert not engine._holds_step_role(
        bare, {"code": "controller", "name": "Controller"}, TENANT_LEVEL
    )


def test_in_entity_scope_mirrors_row_level_security() -> None:
    """``engine.in_entity_scope``: the union entity scope reaches one entity of the request — the
    rule RLS-TE applies to a request of one entity, which the engine applies to a request of
    several."""
    person = _person({})
    scoped = Principal(
        **{
            **{name: getattr(person, name) for name in person.__dataclass_fields__},
            "entity_scope": (A,),
        }
    )
    assert engine.in_entity_scope(scoped, SubjectEntities(frozenset({A, B})))
    assert not engine.in_entity_scope(scoped, SubjectEntities(frozenset({B, C})))
    assert engine.in_entity_scope(scoped, TENANT_LEVEL)
    assert engine.in_entity_scope(person, SubjectEntities(frozenset({B, C})))
