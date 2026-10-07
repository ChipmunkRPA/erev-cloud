"""Approval subjects (dev-guide §5.6 KRN-APR, DG-KRN-APR-05; 04 E-08, §14.1 DB-10; PHASES §5.3,
BS-D-07).

``SUBJECTS`` maps an E-08 subject type to its ``SubjectSpec``: the subject table, the default step
permission, whether an impact preview is required, the functions ``submit`` hashes and routes on,
and the callbacks ``decide`` runs in the deciding transaction. ``PENDING_SUBJECTS`` names the
subject types whose specs later items build, each with its PHASES §5.3 phase code. An item that
registers a spec removes its entry in the same commit (BUILD_SPEC XR-13), and GATE-SOP requires the
tuple to be empty. A subject type without a spec cannot be submitted (XR-12).

A subject without a pending row of its own (``ROLE_ASSIGNMENT`` before the assignment exists;
``ROLE_CHANGE`` before the permissions change) sets ``proposal_content``. Its request stores the
proposal as the ``after`` member of the impact preview and the current state as ``before``;
``subject_id`` is the id the new row will take, or the role id. The engine hashes the proposal with
the base state it changes, and ``on_approved`` applies the verified proposal (BUILD_SPEC BS1-D-24,
BS1-D-31; 04 SMAP-14).

``SOD_EXCEPTION`` follows the same pattern, because ``sod_exception.approval_request_id`` refers to
the request and cannot change once written: the command submits the proposal, then inserts the
REQUESTED row. SoD rule versions route through ``ROLE_CHANGE`` (BS1-D-29); their proposal names
``object_type`` ``sod_rule`` and approval publishes the SUBMITTED version. ``SUPPORT_GRANT`` follows
the grant pattern of ``SOD_EXCEPTION`` for operator support access (BUILD_SPEC PLF-26).

``FX_RATE_SET_VERSION`` hashes the pending row it approves: the version's set, coverage and every
rate, derived inverses included. Approval moves the SUBMITTED version to APPROVED, its effective
state, with ``published_at`` and ``published_by``; rejection and withdrawal return it to DRAFT
through REJECTED or WITHDRAWN (04 E-12; PRD SM-04; BUILD_SPEC RFD-3).

``RULE_SET_VERSION`` hashes the version's rules (``rule_set_version_content``). Its callbacks run
the configuration lifecycle of ``erev_api.domain.policies.lifecycle``, which this kernel module
may not import (DG-LAY-03): the domain module registers them through ``register_lifecycle`` when it
is imported, and a subject whose lifecycle is not registered fails closed (XR-12; BUILD_SPEC RFD-5).

``ACCOUNT_MAPPING_VERSION`` hashes the version's name, number, effective date and rules
(``account_mapping_version_content``). ``erev_api.domain.reference.mapping`` registers its lifecycle
the same way: approval publishes the version (04 T-REF-14; BUILD_SPEC RFD-7).

``POB_TEMPLATE_VERSION`` hashes the version's template code, number, effective date and outputs
(``pob_template_version_content``). ``erev_api.domain.policies.templates`` registers its lifecycle:
approval publishes the version and supersedes the template's PUBLISHED version (04 T-REF-23;
BUILD_SPEC RFD-10).

``PRINCIPAL_AGENT_CHANGE`` follows the ``ROLE_CHANGE`` proposal pattern: the product has no pending
row, so the request stores the proposed conclusion as the preview's ``after`` and hashes it with
the product's current conclusion. Approval sets ``product.principal_agent``; rejection and voiding
change nothing (04 T-REF-20; PRD §2.5; REQ-REF-012; BUILD_SPEC RFD-9). The same subject carries a
change of the product's level-P ``policy_values`` (04 API-R-23 and §16.10 rev 1.110; security
ruling R-21): that proposal holds the whole proposed map, is hashed with the stored map as well,
and its approval sets ``product.policy_values``.

``SSP_BOOK_VERSION`` hashes the version's book, number, label, effective dates, methodology and
entries with their bands, and the book's scope — the entity, currency, channel, segment and
resolution mode its approval puts the prices in force for (``ssp_book_version_content``; 04 §16.10
rev 1.110; REQ-PLT-014). ``erev_api.domain.ssp.publication``
registers its lifecycle and its routing flags. ``METHODOLOGY_CHANGE`` and ``ABOVE_THRESHOLD`` are
its ``second_step_flags``, so the fallback routing gives such a request a second ``ssp.approve``
step (PRD §2.5; REQ-SSP-007; BUILD_SPEC RFD-13).

``REGISTRY_VERSION`` hashes the version's category, scope key, number, effective date, preset
and WHOLE value set with the predecessor it stands on and the difference to it
(``registry_version_content``; 04 T-PLT-32 rev 1.183).
``erev_api.domain.policies.registry_versions`` registers its lifecycle: approval re-checks that
basis under the row locks of the version and of its predecessor, publishes the version and
supersedes the PUBLISHED version of its scope key (04 T-PLT-32, §16.5; PRD BR-POL-02; BUILD_SPEC
RFD-11). An entity-scope version's request names that entity, and a tenant- or book-scope
version's request spans every entity (``registry_version_entities``; D-100 supersedes [J]
L3-1-Q-7; item POLICY-TENANT-SCOPE-ALL-ENTITIES-1).

``POLICY_OVERRIDE`` hashes the T-CON-23 row it approves (``policy_override_content``): scope, key,
value, rationale and judgement record. ``erev_api.domain.policies.overrides`` registers its
lifecycle: approval supersedes the APPROVED override of the same scope and key, approves the row and
marks the contract's group dirty (05 RCP-17; PRD §2.5 ``contract.approve``; BUILD_SPEC CTR-15).

``SSP_OVERRIDE`` follows the ``PRINCIPAL_AGENT_CHANGE`` proposal pattern: the obligation has no
pending row, so the request stores the proposed version and justification as the preview's
``after`` and hashes them with the obligation's current SSP pins and the proposed version's status
(``ssp_override_content``). ``erev_api.domain.policies.overrides`` registers its lifecycle: approval
appends ``LINE_ATTRIBUTES_CHANGED`` as the SYSTEM principal (04 §16.2; PRD §2.5 ``ssp.approve``;
REQ-SSP-006; BUILD_SPEC CTR-15). [J] L4-2-Q-4: neither subject is revenue-affecting for the
preview rule. Both requests name the contracting entity of their contract (D-100 supersedes [J]
L4-2-Q-5).

``ESTIMATE_VERSION`` hashes the T-CON-13 version it approves with its element
(``estimate_version_content``): the element's identity, method and allocation target, and the
version's number, effective date, scenarios, parameters, amounts, rationale, judgement record and
predecessor. It is revenue-affecting: the submission's dry run with the version applied is the
impact preview (REQ-PLT-015). ``erev_api.domain.contracts.estimates`` registers its lifecycle:
approval supersedes the element's APPROVED version, approves the version and appends
``ESTIMATE_CHANGED`` as SYSTEM, then computes the group; rejection gives REJECTED and a withdrawn or
voided request WITHDRAWN (05 §3.6.8 EMOD-24; PRD SM-04, §2.5 routing row ``ESTIMATE_VERSION``;
CTL-013; BUILD_SPEC CTR-12). [J] L5-2-Q-4: the request names no functional amount, so the second
Controller step of the routing row waits for a published routing rule set. The request names the
contracting entity of the element's contract (D-100 supersedes the entity part of L5-2-Q-4).

``JOURNAL_RUN`` hashes the run's identity, coverage, state and totals with each batch's external id,
totals and detail file hash (``journal_run_content``). ``erev_api.domain.journals.commands``
registers its lifecycle: approval moves the run and every batch to ``approved`` (04 T-SL-06,
T-SL-07, DB-16; PRD SM-08, §2.5 routing row ``JOURNAL_RUN``; BUILD_SPEC CLO-11). The request
names the run's entity (D-100 supersedes [J] L6-3-Q-9); the submit command checks ``journal.run``
for the same entity.

``MANUAL_ADJUSTMENT`` hashes the authored members of the T-SL-05 row with the contract's group and
stream head and the hashes of its live attachments (``manual_adjustment_content``), so an event
appended to the contract, or an attachment added or voided, after the submission makes the
decision stale. The request names the contracting entities of every current member of the
contract's combination group — the adjustment's own entity for a contract alone in its group
(rulings R-25, R-51 (d) and R-64 (1): the approval recomputes the group) — and its absolute
functional amount; flag ``ABOVE_THRESHOLD`` gives the fallback routing the second step held by a
Controller (PRD §2.5), and flag ``DEFER_PAST_LOCK`` marks the request whose approval defers the
adjustment past the lock instead of posting it (REQ-JE-019; ruling R-51 (c)). The person who
prepared the adjustment is excluded from deciding it besides the submitter
(``manual_adjustment_creator``): in a ``closing`` period the two differ (BR-CLS-04).
``erev_api.domain.journals.adjustments`` registers its lifecycle (BUILD_SPEC CLO-12).

**Entity scope (R-25; 04 T-PLT-17 rev 1.104; dev-guide DG-KRN-APR-06; REQ-PLT-012; D-100).** Every
subject bound to legal entities states them and the request freezes them at submission: one entity
through ``SubjectSpec.entity_id`` (the contracting entity of a contract-bound subject, the run's or
the period's entity, the entity of an entity-scope version or book), several through
``SubjectSpec.entities`` (``SubjectEntities``: a combination or a regroup pair across entities, an
import). A decision needs the step permission for EVERY entity; a request is listed and readable
for a scope that covers at least one. ``_tenant_level`` marks the subjects that belong to no
entity — access administration and tenant configuration — which any holder of the step permission
decides. A subject row the caller cannot read answers 404, never a tenant-level request.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from erev_engine.stages.s01_canonicalize import obligation_subject_key
from sqlalchemy import RowMapping, Table, and_, delete, func, insert, or_, select, update
from sqlalchemy.orm import Session

from erev_api.approvals import delegations, preview
from erev_api.approvals.authorship import AUTHOR_DETAIL, draft_authors
from erev_api.auth import sod
from erev_api.auth.permissions import role_content_sha256
from erev_api.auth.principal import system_principal
from erev_api.db import transitions
from erev_api.db.locking import hold_fx_publication, lock_group_then_contract
from erev_api.db.session import of_session_tenant
from erev_api.db.tables import (
    account_mapping_rule,
    account_mapping_version,
    api_client,
    app_user,
    approval_request,
    close_checklist_item,
    close_checklist_template,
    combination_group,
    combination_group_member,
    contract,
    contract_event,
    contract_version,
    estimate,
    estimate_version,
    event_submission,
    exception_item,
    file_attachment,
    file_object,
    fx_rate,
    fx_rate_set,
    fx_rate_set_version,
    gl_account,
    import_mapping_profile,
    import_row,
    import_template,
    import_upload,
    job,
    journal_batch,
    journal_run,
    judgement_record,
    legal_entity,
    manual_adjustment,
    migration_batch,
    modification,
    obligation,
    obligation_version,
    period_state,
    pob_template,
    pob_template_version,
    policy_override,
    product,
    registry_version,
    role,
    role_assignment,
    role_permission,
    rule,
    rule_set,
    rule_set_version,
    sod_exception,
    sod_rule,
    ssp_book,
    ssp_book_version,
    ssp_entry,
    ssp_range,
    subledger_line,
    subledger_posting_seal,
    support_grant,
    tenant_membership,
)
from erev_api.enums import (
    ApiClientStatus,
    ApprovalRequestStatus,
    ApprovalSubjectType,
    ConfigStatus,
    ContractEventType,
    GrantStatus,
    MembershipStatus,
    PrincipalKind,
    RegistryScope,
    UserStatus,
)
from erev_api.events import step1
from erev_api.events.payloads import LATEST_SCHEMA_VERSION, parse_payload
from erev_api.events.stream import EventIn, append_events
from erev_api.problems import Problem
from erev_api.registry import versions as registry_versions

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork


class SubjectNotVisible(LookupError):
    """A content function found no subject row the session may read. The row exists for nobody the
    caller could be told about: ``engine.decide`` answers 404 ``not-found`` for it (REQ-PLT-012;
    R-25), while every other ``LookupError`` of a content function stays the defect it is."""


@dataclass(frozen=True, slots=True)
class SubjectEntities:
    """The legal entities an approval subject is bound to (04 T-PLT-17 rev 1.104; dev-guide
    DG-KRN-APR-06; REQ-PLT-012; D-100): ``ids`` when the subject names them, ``all_entities`` when
    it spans every entity of the tenant, neither for a tenant-level subject. A decision needs ONE
    authority whose scope covers every entity (``covered_by``); a request is listed and readable for
    a scope that covers at least one of them (``touched_by``). A subject that spans every entity is
    covered, and listed, only by scope ``"*"``: what the engine cannot name it does not show."""

    ids: frozenset[UUID] = frozenset()
    all_entities: bool = False

    def __post_init__(self) -> None:
        if self.all_entities and self.ids:
            raise ValueError("a subject that spans every entity names none")

    def covered_by(self, scope: Literal["*"] | frozenset[UUID]) -> bool:
        """Every entity of the subject is in ``scope``; a tenant-level subject always is."""
        return scope == "*" or (not self.all_entities and self.ids <= scope)

    def touched_by(self, scope: Literal["*"] | frozenset[UUID]) -> bool:
        """At least one entity of the subject is in ``scope``; a tenant-level subject always is."""
        if scope == "*":
            return True
        if self.all_entities:
            return False
        return not self.ids or not self.ids.isdisjoint(scope)


TENANT_LEVEL: Final = SubjectEntities()
ALL_ENTITIES: Final = SubjectEntities(all_entities=True)


@dataclass(frozen=True, slots=True)
class FloorStep:
    """One further approval the content of a subject demands, stated by ``SubjectSpec.floor`` (R-38
    (ii), R-41, R-92): a step permission, its approver count and, when set, the role code every
    approver of it holds. ``engine.route_submission`` adds it to the subject's own steps, so
    routing output is raised to it like to the rest of the floor."""

    name: str
    permission: str
    min_approvers: int = 1
    role: str | None = None


@dataclass(frozen=True, slots=True)
class DeciderRefusal:
    """Why a person may not give one approval of a request, stated by ``SubjectSpec.deciders``
    (supervisor ruling R-92): the answer — 403 ``forbidden`` by name — with the permission the
    person lacks and the facts of the refusal, as its ``DENIED`` audit event records them (R-98;
    DG-KRN-AUTH-05)."""

    problem: Problem
    permission: str
    detail: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SubjectSpec:
    subject_type: ApprovalSubjectType  # E-08
    table: str  # 04 table name
    required_permission: str  # default step permission
    revenue_affecting: bool  # impact preview required (REQ-PLT-015)
    min_approvers: int  # 1; PERIOD_REOPEN 2, one a controller (REQ-CLS-011)
    content: Callable[[Session, UUID], Mapping[str, Any]]
    entity_id: Callable[[Session, UUID], UUID | None]
    amount_functional: Callable[[Session, UUID], tuple[Decimal, str] | None]
    flags: Callable[[Session, UUID], frozenset[str]]
    on_approved: Callable[[UnitOfWork, UUID, UUID], None]  # (uow, subject_id, approval_request_id)
    on_rejected: Callable[[UnitOfWork, UUID, UUID], None]
    on_voided: Callable[[UnitOfWork, UUID, UUID], None]
    # SCREENS SCR-IA-06: the subject route NTF-02 to NTF-04 link to; None links to the request.
    link_path: Callable[[UUID], str] | None = None
    # BS1-D-24: the content hashed for a subject without a pending row, from its proposal (the
    # preview's ``after``); None hashes ``content(session, subject_id)``.
    proposal_content: Callable[[Session, Mapping[str, Any]], Mapping[str, Any]] | None = None
    # RFD-13 (REQ-SSP-007): flags that give the fallback routing a second step with the same
    # permission and approvers.
    second_step_flags: frozenset[str] = frozenset()
    # CTR-9 (PRD §2.5 CONTRACT_ACTIVATION): the role code that narrows that second step (04 T-PLT-18
    # ``required_role_id``); None leaves it open to every holder of the permission.
    second_step_role: str | None = None
    # DIN-11 (PRD §2.5 EXCEPTION_WAIVER): the user ids who may not decide the subject besides the
    # preparer, for example the owner of the exception item a waiver clears; None excludes nobody.
    excluded_deciders: Callable[[Session, UUID], frozenset[UUID]] | None = None
    # PRD §5.5 copy of the ERR-02 refusal of an excluded decider; None takes the engine's
    # ``EXCLUDED_DETAIL`` ("You own this item …").
    excluded_detail: str | None = None
    # R-25 (04 T-PLT-17 rev 1.104): the entities of a subject that can span several — a combination
    # across entities, an import, a regroup pair; None reads the one entity of ``entity_id`` (None
    # there is a tenant-level subject). The request freezes the answer at submission.
    entities: Callable[[Session, UUID], SubjectEntities] | None = None
    # R-41 (4): the entities a subject WITHOUT a row names in its proposal (the preview's
    # ``after``) — a role assignment states the entities of the grant it proposes. Read at
    # submission and again, from the stored proposal, at the decision.
    proposal_entities: Callable[[Session, Mapping[str, Any]], SubjectEntities] | None = None
    # R-41 (7) (PRD §2.5 ``PERIOD_LOCK``: "1: period.lock (Controller)"): the role code every
    # approver of the subject's own first step holds (04 T-PLT-18 ``required_role_id``); None
    # leaves the step open to every holder of the permission.
    step_role: str | None = None
    # R-64 (6), R-106 (b): the entities the PREPARER is held to at submission, where they are
    # fewer than the entities of the request — those of what the request would put in force. An
    # import in quarantine mode commits its usable rows only, while its request names every
    # entity any row names. Only a named, non-empty set inside the request's entities narrows
    # the check (``engine._preparer_entities`` fails closed on any other statement). Three
    # subjects state one (``tests/architecture/test_preparer_entities_seam.py``):
    # ``IMPORT_COMMIT``, and ``MANUAL_EVENT`` and ``ATTRIBUTE_CHANGE``, whose preparer records
    # the facts of ONE contract of a group the request names whole (04 §16.10 rev 1.269).
    # None: the entities of the request.
    preparer_entities: Callable[[Session, UUID], SubjectEntities] | None = None
    # R-38 (ii), R-92: further approvals the subject's CONTENT demands besides its own steps — an
    # import whose commit performs an approval answers one step per further approver that
    # approval takes (``import_commit_floor``). Called with the entities of the request and the
    # instant of the routing. None: none.
    floor: Callable[[Session, UUID, SubjectEntities, datetime], Sequence[FloorStep]] | None = None
    # R-92: the subject's own check of the people who decide. (session, subject id, the entities
    # of the request, the ordinal of the approval — 1 for the first approval of the request — the
    # people asked about, the instant) → the refusal of each person who may not give that
    # approval. ``engine.decide`` asks it at every decision; ``engine.can_decide``, the queue and
    # the notifications ask the same, so nobody takes a step the subject would not let them
    # finish and "waiting for me" stays exact. None: the step's permission and role decide alone.
    deciders: (
        Callable[
            [Session, UUID, SubjectEntities, int, Collection[UUID], datetime],
            Mapping[UUID, DeciderRefusal],
        ]
        | None
    ) = None


ROLE_ASSIGNMENT_OBJECT: Final = "role_assignment"
ROLE_ASSIGNMENT_CREATE: Final = "role_assignment.create"


def role_assignment_proposal(
    *,
    membership_id: UUID,
    role_id: UUID,
    role_code: str,
    is_all_entities: bool,
    entity_ids: Sequence[UUID],
    sod_exception_id: UUID | None,
    entity_codes: Sequence[str] = (),
) -> dict[str, Any]:
    """The ``after`` member of a ``ROLE_ASSIGNMENT`` request: the T-PLT-10 row it proposes, with
    the codes of its entities beside their ids (the approver reads the scope by name; supervisor
    ruling R-63 (e)). The ids are what the approval inserts."""
    return {
        "membership_id": str(membership_id),
        "role_id": str(role_id),
        "role_code": role_code,
        "is_all_entities": is_all_entities,
        "entity_ids": sorted(str(value) for value in entity_ids),
        "entity_codes": sorted(str(code) for code in entity_codes),
        "sod_exception_id": None if sod_exception_id is None else str(sod_exception_id),
    }


API_CLIENT_OBJECT: Final = "api_client"
API_CLIENT_ACTIVATE: Final = "api_client.activate"
API_CLIENT_REJECT: Final = "api_client.reject"
# The T-PLT-15 members a grant request proposes: its content hashes them as proposed and as stored.
_API_CLIENT_GRANT: Final = (
    "name",
    "client_id",
    "scopes",
    "is_all_entities",
    "entity_ids",
    "expires_at",
    "rate_limit_per_minute",
)


def api_client_grant_proposal(
    *,
    api_client_id: UUID,
    name: str,
    client_id: str,
    scopes: Sequence[str],
    is_all_entities: bool,
    entity_ids: Sequence[UUID],
    expires_at: datetime,
    rate_limit_per_minute: int,
    entity_codes: Sequence[str] = (),
) -> dict[str, Any]:
    """The ``after`` member of a ``ROLE_ASSIGNMENT`` request that grants an API client its scopes
    (supervisor ruling R-38 (iii); 04 T-PLT-15 and §16.10 rev 1.168; REQ-PLT-033): the members of
    the ``PENDING_APPROVAL`` row its approval makes ``ACTIVE``. ``object_type`` tells it from the
    proposal of a role assignment; ``is_all_entities`` and ``entity_ids`` are read by
    ``role_assignment_entities`` exactly as a role grant's, so an all-entities client takes
    ``access.approve`` for all entities."""
    return {
        "object_type": API_CLIENT_OBJECT,
        "api_client_id": str(api_client_id),
        "name": name,
        "client_id": client_id,
        "scopes": sorted(scopes),
        "is_all_entities": is_all_entities,
        "entity_ids": sorted(str(value) for value in entity_ids),
        "entity_codes": sorted(str(code) for code in entity_codes),
        "expires_at": expires_at.isoformat(),
        "rate_limit_per_minute": rate_limit_per_minute,
    }


def is_api_client_grant(proposal: Mapping[str, Any]) -> bool:
    """Whether a ``ROLE_ASSIGNMENT`` proposal grants an API client its scopes."""
    return proposal.get("object_type") == API_CLIENT_OBJECT


def _api_client_grant_content(session: Session, proposal: Mapping[str, Any]) -> dict[str, Any]:
    """The proposal with the state it changes: the client's status and the granted members as the
    row stores them. A client that is no longer pending, or no longer what the request proposes,
    makes the decision stale (REQ-PLT-014)."""
    row = (
        session.execute(
            select(api_client.c.status, *(api_client.c[name] for name in _API_CLIENT_GRANT)).where(
                api_client.c.id == UUID(str(proposal["api_client_id"]))
            )
        )
        .mappings()
        .one_or_none()
    )
    base: dict[str, Any] | None = None
    if row is not None:
        base = {
            "status": _text(row["status"]),
            "name": str(row["name"]),
            "client_id": str(row["client_id"]),
            "scopes": sorted(str(code) for code in row["scopes"]),
            "is_all_entities": bool(row["is_all_entities"]),
            "entity_ids": sorted(str(value) for value in row["entity_ids"]),
            "expires_at": row["expires_at"].isoformat(),
            "rate_limit_per_minute": int(row["rate_limit_per_minute"]),
        }
    return {"proposal": dict(proposal), "base": base}


def role_assignment_content(session: Session, proposal: Mapping[str, Any]) -> dict[str, Any]:
    """The proposal with the state it changes: whether the membership is removed, the role's
    permission hash and state, and whether the membership already holds the role. The grant of an
    API client's scopes rides on the same subject (``api_client_grant_proposal``) and hashes the
    client row instead."""
    if is_api_client_grant(proposal):
        return _api_client_grant_content(session, proposal)
    membership_id = UUID(str(proposal["membership_id"]))
    role_id = UUID(str(proposal["role_id"]))
    status = session.execute(
        select(tenant_membership.c.status).where(
            of_session_tenant(tenant_membership), tenant_membership.c.id == membership_id
        )
    ).scalar_one_or_none()
    granted = session.execute(
        select(role.c.content_sha256, role.c.is_active).where(role.c.id == role_id)
    ).one_or_none()
    assigned = session.execute(
        select(role_assignment.c.id)
        .where(
            role_assignment.c.membership_id == membership_id,
            role_assignment.c.role_id == role_id,
            role_assignment.c.revoked_at.is_(None),
        )
        .limit(1)
    ).first()
    return {
        "proposal": dict(proposal),
        "base": {
            "membership_removed": status is None or status == MembershipStatus.REMOVED.value,
            "role_content_sha256": None if granted is None else str(granted.content_sha256),
            "role_is_active": granted is not None and bool(granted.is_active),
            "role_assigned": assigned is not None,
        },
    }


def role_assignment_entities(_: Session, proposal: Mapping[str, Any]) -> SubjectEntities:
    """The legal entities a ``ROLE_ASSIGNMENT`` request is bound to (R-41 (4); 04 §16.10 rev
    1.104): the entities of the grant it proposes (T-PLT-10 ``entity_ids``), and every entity for
    an all-entities grant — deciding that one takes ``access.approve`` for all entities, so an
    approver for one entity cannot hand out a role over another. A proposal that names neither is
    malformed and spans every entity (fail closed)."""
    if bool(proposal.get("is_all_entities")):
        return ALL_ENTITIES
    ids = frozenset(UUID(str(value)) for value in proposal.get("entity_ids") or ())
    return SubjectEntities(ids) if ids else ALL_ENTITIES


def _stated_by_proposal(_: Session, subject_id: UUID) -> UUID | None:
    raise LookupError(
        f"subject {subject_id} states its entities in its proposal (SubjectSpec.proposal_entities)"
    )


def support_grant_entities(_: Session, __: UUID) -> SubjectEntities:
    """The entities of a ``SUPPORT_GRANT`` request: every entity (04 §16.10 rev 1.219; supervisor
    ruling R-115 (c); item SCOPE-WORKSPACE-LISTS-1). Provider access under a grant reaches the
    whole workspace, so the request is listed for, read and decided by a holder of
    ``support_grant.approve`` for all entities — an administrator of one entity does not open the
    workspace to the provider (measured before: a Tenant Admin of one entity approved it)."""
    return ALL_ENTITIES


def _tenant_level(_: Session, __: UUID) -> UUID | None:
    """``SubjectSpec.entity_id`` of a genuinely tenant-level subject (R-25): it belongs to no legal
    entity, so its request names none and any holder of the step permission decides it."""
    return None


def _hashes_its_proposal(_: Session, subject_id: UUID) -> Mapping[str, Any]:
    raise LookupError(f"subject {subject_id} has no row; its request hashes the proposal")


def _lock_memberships(session: Session, membership_ids: Iterable[UUID]) -> None:
    """Lock the membership rows ``FOR UPDATE`` in ascending id order before a SoD check reads their
    assignments (DG-CMD-02; precedent ``users._lock_membership``)."""
    ids = sorted(set(membership_ids))
    if ids:
        session.execute(
            select(tenant_membership.c.id)
            .where(tenant_membership.c.id.in_(ids))
            .order_by(tenant_membership.c.id)
            .with_for_update()
        ).all()


def _apply_role_assignment(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    """Insert the approved assignment after the SoD check at approval (PRD SM-13; REQ-PLT-010).

    A conflict without a covering exception raises 409 ``sod-conflict``, which rolls the decision
    back. The covering exception, when there is one, is stored on the row. The membership row is
    locked before the check, so concurrent approvals for one member run one after the other and
    the later one sees the earlier grant (DG-CMD-02; CTL-034).
    """
    proposal = preview.request_proposal(uow, approval_request_id)
    if is_api_client_grant(proposal):
        _activate_api_client(uow, subject_id, approval_request_id)
        return
    membership_id = UUID(str(proposal["membership_id"]))
    role_id = UUID(str(proposal["role_id"]))
    _lock_memberships(uow.session, [membership_id])
    # PRD BR-PLT-07: a delegation that lost its support has ended before a grant could revive it.
    delegations.end_unsupported(uow, cause=delegations.ROLE_ASSIGNMENT_GRANTED)
    covering = sod.assert_assignment_allowed(uow.session, membership_id, role_id, at=uow.now)
    principal = uow.principal
    uow.session.execute(
        insert(role_assignment).values(
            tenant_id=principal.tenant_id,
            id=subject_id,
            membership_id=membership_id,
            role_id=role_id,
            is_all_entities=bool(proposal["is_all_entities"]),
            entity_ids=[UUID(str(value)) for value in proposal["entity_ids"]],
            valid_from=uow.now,
            approval_request_id=approval_request_id,
            sod_exception_id=covering,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
        )
    )
    uow.audit(
        action=ROLE_ASSIGNMENT_CREATE,
        object_type=ROLE_ASSIGNMENT_OBJECT,
        object_id=subject_id,
        after={**proposal, "sod_exception_id": None if covering is None else str(covering)},
        approval_request_id=approval_request_id,
    )


def _activate_api_client(uow: UnitOfWork, api_client_id: UUID, approval_request_id: UUID) -> None:
    """``on_approved`` of an API client's grant (supervisor ruling R-38 (iii); 04 T-PLT-15 rev
    1.168): ``PENDING_APPROVAL`` → ``ACTIVE``. The approval issues no secret and the approver
    sees none: the row keeps the hash of a secret nobody holds until a holder of
    ``api_client.manage`` issues the first one (``auth.api_clients.rotate_secret``) — unless the
    request was approved at its submission, where the creating command returns it."""
    session = uow.session
    current = session.execute(
        select(api_client.c.status).where(api_client.c.id == api_client_id).with_for_update()
    ).scalar_one_or_none()
    if _text(current) != ApiClientStatus.PENDING_APPROVAL.value:
        raise LookupError(
            f"API client {api_client_id} of approval request {approval_request_id} is not pending"
        )
    principal = uow.principal
    version = session.execute(
        update(api_client)
        .where(api_client.c.id == api_client_id)
        .values(
            status=ApiClientStatus.ACTIVE.value,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
        .returning(api_client.c.row_version)
    ).scalar_one()
    uow.audit(
        action=API_CLIENT_ACTIVATE,
        object_type=API_CLIENT_OBJECT,
        object_id=api_client_id,
        object_version=str(version),
        before={"status": ApiClientStatus.PENDING_APPROVAL.value},
        after={"status": ApiClientStatus.ACTIVE.value},
        approval_request_id=approval_request_id,
    )


def _close_role_assignment(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    """``on_rejected`` and ``on_voided`` of ``ROLE_ASSIGNMENT``. The proposal of a role assignment
    wrote no row, so nothing is undone. The grant of an API client leaves its row ``REJECTED``:
    it never took effect, and another request needs another client (ruling R-38 (iii)). The
    subject id of a role assignment names no client, so the update finds a row only for a
    client's grant."""
    principal = uow.principal
    version = uow.session.execute(
        update(api_client)
        .where(
            api_client.c.id == subject_id,
            api_client.c.status == ApiClientStatus.PENDING_APPROVAL.value,
        )
        .values(
            status=ApiClientStatus.REJECTED.value,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
        .returning(api_client.c.row_version)
    ).scalar_one_or_none()
    if version is None:
        return
    uow.audit(
        action=API_CLIENT_REJECT,
        object_type=API_CLIENT_OBJECT,
        object_id=subject_id,
        object_version=str(version),
        before={"status": ApiClientStatus.PENDING_APPROVAL.value},
        after={"status": ApiClientStatus.REJECTED.value},
        approval_request_id=approval_request_id,
    )


ROLE_OBJECT: Final = "role"
ROLE_CHANGE_ACTION: Final = "role.change"
SYSTEM_ROLE_DETAIL: Final = "System roles cannot change."  # BUILD_SPEC BS1-D-31


def role_change_proposal(
    *, role_id: UUID, role_code: str, permissions: Iterable[str]
) -> dict[str, Any]:
    """The ``after`` member of a ``ROLE_CHANGE`` request: the role's proposed permission codes."""
    return {
        "object_type": ROLE_OBJECT,
        "role_id": str(role_id),
        "role_code": role_code,
        "permissions": sorted(set(permissions)),
    }


def role_change_content(session: Session, proposal: Mapping[str, Any]) -> dict[str, Any]:
    """The proposal with the role state it changes: whether the role exists, is a system role or
    active, and the hash of its current permissions. A proposal of ``object_type`` ``sod_rule``
    hashes the version and published state instead (BS1-D-29)."""
    if proposal.get("object_type") == SOD_RULE_OBJECT:
        return _sod_rule_version_content(session, proposal)
    found = session.execute(
        select(role.c.is_system, role.c.is_active, role.c.content_sha256).where(
            role.c.id == UUID(str(proposal["role_id"]))
        )
    ).one_or_none()
    return {
        "proposal": dict(proposal),
        "base": {
            "role_exists": found is not None,
            "is_system": found is not None and bool(found.is_system),
            "is_active": found is not None and bool(found.is_active),
            "role_content_sha256": None if found is None else str(found.content_sha256),
        },
    }


def _void_stale_assignment_requests(uow: UnitOfWork, role_id: UUID) -> None:
    """DG-KRN-APR-05: a changed role voids the pending ``ROLE_ASSIGNMENT`` requests granting it,
    because their content hash covers the role's permissions."""
    # The engine imports this module, so it is imported where it is used.
    from erev_api.approvals import engine  # noqa: PLC0415

    session = uow.session
    pending = session.execute(
        select(approval_request.c.subject_id, approval_request.c.impact_preview_file_id)
        .where(
            approval_request.c.subject_type == ApprovalSubjectType.ROLE_ASSIGNMENT.value,
            approval_request.c.status == ApprovalRequestStatus.PENDING.value,
            approval_request.c.impact_preview_file_id.is_not(None),
        )
        .order_by(approval_request.c.submitted_at, approval_request.c.id)
    ).all()
    for subject_id, file_id in pending:
        document = preview.read_preview(session, file_id, files=uow.files, keyring=uow.keyring)
        if str(document["after"].get("role_id")) == str(role_id):
            engine.void_if_stale(
                uow, subject_type=ApprovalSubjectType.ROLE_ASSIGNMENT, subject_id=subject_id
            )


def _apply_role_change(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    """Replace the role's permissions with the approved list and activate it (BS1-D-31).

    A system role raises 409 ``invalid-transition``; a combination the role's holders would meet
    without an exception raises 409 ``sod-conflict``. Either rolls the decision back. A proposal of
    ``object_type`` ``sod_rule`` publishes the SoD rule version instead (BS1-D-29).
    """
    proposal = preview.request_proposal(uow, approval_request_id)
    if proposal.get("object_type") == SOD_RULE_OBJECT:
        _publish_sod_rule_version(uow, subject_id, approval_request_id)
        return
    session = uow.session
    principal = uow.principal
    current = (
        session.execute(select(role).where(role.c.id == subject_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if current is None:
        raise LookupError(f"role {subject_id} of approval request {approval_request_id} is gone")
    if current["is_system"]:
        raise Problem("invalid-transition", SYSTEM_ROLE_DETAIL)
    proposed = sorted(str(code) for code in proposal["permissions"])
    # DG-CMD-02: every holder's membership is locked, so a concurrent grant to a holder waits.
    holders = session.scalars(
        select(role_assignment.c.membership_id).where(
            role_assignment.c.role_id == subject_id, role_assignment.c.revoked_at.is_(None)
        )
    ).all()
    _lock_memberships(session, [UUID(str(value)) for value in holders])
    # PRD BR-PLT-07: what is unsupported ends before the role can give a permission back ...
    delegations.end_unsupported(uow, cause=delegations.ROLE_CHANGED)
    sod.assert_role_change_allowed(session, subject_id, proposed, at=uow.now)
    held = sorted(
        str(code)
        for code in session.scalars(
            select(role_permission.c.permission_code).where(role_permission.c.role_id == subject_id)
        )
    )
    removed = sorted(set(held) - set(proposed))
    added = sorted(set(proposed) - set(held))
    if removed:
        session.execute(
            delete(role_permission).where(
                role_permission.c.role_id == subject_id,
                role_permission.c.permission_code.in_(removed),
            )
        )
    if added:
        session.execute(
            insert(role_permission),
            [
                {
                    "tenant_id": principal.tenant_id,
                    "role_id": subject_id,
                    "permission_code": code,
                    "created_at": uow.now,
                    "created_by": principal.id,
                    "created_by_kind": principal.kind.value,
                }
                for code in added
            ],
        )
    content_sha256 = role_content_sha256(proposed)
    session.execute(
        update(role)
        .where(role.c.id == subject_id)
        .values(
            is_active=True,
            content_sha256=content_sha256,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    uow.audit(
        action=ROLE_CHANGE_ACTION,
        object_type=ROLE_OBJECT,
        object_id=subject_id,
        before={
            "permissions": held,
            "is_active": bool(current["is_active"]),
            "content_sha256": str(current["content_sha256"]),
        },
        after={"permissions": proposed, "is_active": True, "content_sha256": content_sha256},
        approval_request_id=approval_request_id,
        detail={"permissions_added": added, "permissions_removed": removed},
    )
    # ... and a delegation of a permission the role no longer carries ends with the change.
    delegations.end_unsupported(uow, cause=delegations.ROLE_CHANGED)
    if added or removed:
        _void_stale_assignment_requests(uow, subject_id)


SOD_RULE_OBJECT: Final = "sod_rule"
SOD_RULE_PUBLISH: Final = "sod_rule.publish"
SOD_RULE_SUPERSEDE: Final = "sod_rule.supersede"
SOD_RULE_REJECT: Final = "sod_rule.reject"
SOD_RULE_WITHDRAW: Final = "sod_rule.withdraw"
SOD_RULE_NOT_SUBMITTED: Final = "Only a submitted version of an SoD rule can be published."


def sod_rule_proposal(
    *,
    version_id: UUID,
    code: str,
    version_no: int,
    name: str,
    function_a_permissions: Iterable[str],
    function_b_permissions: Iterable[str],
    rationale: str,
) -> dict[str, Any]:
    """The ``after`` member of a ``ROLE_CHANGE`` request for an SoD rule version (BS1-D-29)."""
    return {
        "object_type": SOD_RULE_OBJECT,
        "sod_rule_id": str(version_id),
        "code": code,
        "version_no": version_no,
        "name": name,
        "function_a_permissions": sorted(set(function_a_permissions)),
        "function_b_permissions": sorted(set(function_b_permissions)),
        "rationale": rationale,
    }


def _sod_rule_version_content(session: Session, proposal: Mapping[str, Any]) -> dict[str, Any]:
    """The proposal with the state it changes: the version's status and content hash, and the
    rule's published version."""
    version = session.execute(
        select(sod_rule.c.status, sod_rule.c.content_sha256).where(
            sod_rule.c.id == UUID(str(proposal["sod_rule_id"]))
        )
    ).one_or_none()
    published = session.execute(
        select(sod_rule.c.id, sod_rule.c.content_sha256).where(
            sod_rule.c.code == str(proposal["code"]),
            sod_rule.c.status == ConfigStatus.PUBLISHED.value,
        )
    ).one_or_none()
    return {
        "proposal": dict(proposal),
        "base": {
            "version_status": None if version is None else str(version.status),
            "version_content_sha256": None if version is None else _text(version.content_sha256),
            "published_version_id": None if published is None else str(published.id),
            "published_content_sha256": None
            if published is None
            else _text(published.content_sha256),
        },
    }


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _void_stale_exception_requests(uow: UnitOfWork, code: str) -> None:
    """DG-KRN-APR-05: a newly published rule version voids the pending ``SOD_EXCEPTION`` requests
    of the rule, because their content hash covers the published rule."""
    # The engine imports this module, so it is imported where it is used.
    from erev_api.approvals import engine  # noqa: PLC0415

    requested = uow.session.scalars(
        select(sod_exception.c.id)
        .where(
            sod_exception.c.sod_rule_code == code,
            sod_exception.c.status == GrantStatus.REQUESTED.value,
        )
        .order_by(sod_exception.c.id)
    ).all()
    for exception_id in requested:
        engine.void_if_stale(
            uow,
            subject_type=ApprovalSubjectType.SOD_EXCEPTION,
            subject_id=UUID(str(exception_id)),
        )


def _publish_sod_rule_version(uow: UnitOfWork, version_id: UUID, approval_request_id: UUID) -> None:
    """SUBMITTED → APPROVED → PUBLISHED for the approved version (PRD SM-04; BS1-D-29).

    The rule's PUBLISHED version becomes SUPERSEDED from now first, because one version of a code
    is PUBLISHED at a time (DB-04). A version that is no longer SUBMITTED raises 409
    ``invalid-transition``, which rolls the decision back.
    """
    session = uow.session
    principal = uow.principal
    version = (
        session.execute(select(sod_rule).where(sod_rule.c.id == version_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if version is None:
        raise LookupError(
            f"sod_rule {version_id} of approval request {approval_request_id} is gone"
        )
    if version["status"] != ConfigStatus.SUBMITTED.value:
        raise Problem("invalid-transition", SOD_RULE_NOT_SUBMITTED)
    stamp = {"updated_by": principal.id, "updated_by_kind": principal.kind.value}
    session.execute(
        update(sod_rule)
        .where(sod_rule.c.id == version_id)
        .values(
            status=ConfigStatus.APPROVED.value, approval_request_id=approval_request_id, **stamp
        )
    )
    current = session.execute(
        select(sod_rule.c.id)
        .where(
            sod_rule.c.code == version["code"],
            sod_rule.c.status == ConfigStatus.PUBLISHED.value,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if current is not None:
        session.execute(
            update(sod_rule)
            .where(sod_rule.c.id == current)
            .values(status=ConfigStatus.SUPERSEDED.value, effective_to=uow.now, **stamp)
        )
        uow.audit(
            action=SOD_RULE_SUPERSEDE,
            object_type=SOD_RULE_OBJECT,
            object_id=current,
            before={"status": ConfigStatus.PUBLISHED.value, "effective_to": None},
            after={"status": ConfigStatus.SUPERSEDED.value, "effective_to": uow.now},
            approval_request_id=approval_request_id,
        )
    session.execute(
        update(sod_rule)
        .where(sod_rule.c.id == version_id)
        .values(
            status=ConfigStatus.PUBLISHED.value,
            published_at=uow.now,
            published_by=principal.id,
            **stamp,
        )
    )
    uow.audit(
        action=SOD_RULE_PUBLISH,
        object_type=SOD_RULE_OBJECT,
        object_id=version_id,
        before={
            "status": ConfigStatus.SUBMITTED.value,
            "approval_request_id": None,
            "published_at": None,
            "published_by": None,
        },
        after={
            "status": ConfigStatus.PUBLISHED.value,
            "approval_request_id": approval_request_id,
            "published_at": uow.now,
            "published_by": principal.id,
        },
        approval_request_id=approval_request_id,
    )
    _void_stale_exception_requests(uow, str(version["code"]))


def _close_role_change(
    status: ConfigStatus, action: str
) -> Callable[[UnitOfWork, UUID, UUID], None]:
    """``on_rejected`` or ``on_voided`` of ``ROLE_CHANGE``: a SUBMITTED SoD rule version takes
    ``status``; a role proposal wrote no row, so nothing changes."""

    def close(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
        found = uow.session.execute(
            select(sod_rule.c.status).where(sod_rule.c.id == subject_id).with_for_update()
        ).scalar_one_or_none()
        if found != ConfigStatus.SUBMITTED.value:
            return
        principal = uow.principal
        uow.session.execute(
            update(sod_rule)
            .where(sod_rule.c.id == subject_id)
            .values(
                status=status.value, updated_by=principal.id, updated_by_kind=principal.kind.value
            )
        )
        uow.audit(
            action=action,
            object_type=SOD_RULE_OBJECT,
            object_id=subject_id,
            before={"status": ConfigStatus.SUBMITTED.value},
            after={"status": status.value},
            approval_request_id=approval_request_id,
        )

    return close


SOD_EXCEPTION_OBJECT: Final = "sod_exception"
SOD_EXCEPTION_APPROVE: Final = "sod_exception.approve"
SOD_EXCEPTION_REJECT: Final = "sod_exception.reject"
SOD_EXCEPTION_VOID: Final = "sod_exception.void"
# [J] SPEC-Q-184: no rule approves an exception without a person (XR-12).
SOD_EXCEPTION_NEEDS_PERSON: Final = "An SoD exception needs the approval of another administrator."


def sod_exception_proposal(
    *,
    exception_id: UUID,
    sod_rule_code: str,
    membership_id: UUID,
    compensating_control: str,
    valid_from: datetime,
    valid_to: datetime,
) -> dict[str, Any]:
    """The ``after`` member of a ``SOD_EXCEPTION`` request: the T-PLT-14 row it proposes."""
    return {
        "object_type": SOD_EXCEPTION_OBJECT,
        "sod_exception_id": str(exception_id),
        "sod_rule_code": sod_rule_code,
        "membership_id": str(membership_id),
        "compensating_control": compensating_control,
        "valid_from": valid_from.isoformat(),
        "valid_to": valid_to.isoformat(),
    }


def sod_exception_content(session: Session, proposal: Mapping[str, Any]) -> dict[str, Any]:
    """The proposal with the state it changes: whether the membership is removed and the content
    hash of the rule's published version."""
    status = session.execute(
        select(tenant_membership.c.status).where(
            of_session_tenant(tenant_membership),
            tenant_membership.c.id == UUID(str(proposal["membership_id"])),
        )
    ).scalar_one_or_none()
    published = session.execute(
        select(sod_rule.c.content_sha256).where(
            sod_rule.c.code == str(proposal["sod_rule_code"]),
            sod_rule.c.status == ConfigStatus.PUBLISHED.value,
        )
    ).scalar_one_or_none()
    return {
        "proposal": dict(proposal),
        "base": {
            "membership_removed": status is None or status == MembershipStatus.REMOVED.value,
            "rule_content_sha256": _text(published),
        },
    }


SUPPORT_GRANT_OBJECT: Final = "support_grant"
SUPPORT_GRANT_APPROVE: Final = "support_grant.approve"
SUPPORT_GRANT_REJECT: Final = "support_grant.reject"
SUPPORT_GRANT_VOID: Final = "support_grant.void"
SUPPORT_GRANT_LINK: Final = "/settings/support-access"  # SCREENS RT-92
# [J] SPEC-Q-191: no rule approves support access without a person (XR-12).
SUPPORT_GRANT_NEEDS_PERSON: Final = (
    "Support access needs the approval of a workspace administrator."
)


def support_grant_proposal(
    *,
    grant_id: UUID,
    operator_user_id: UUID,
    reason: str,
    ticket_ref: str | None,
    valid_from: datetime,
    valid_to: datetime,
) -> dict[str, Any]:
    """The ``after`` member of a ``SUPPORT_GRANT`` request: the T-PLT-33 row it proposes."""
    return {
        "object_type": SUPPORT_GRANT_OBJECT,
        "support_grant_id": str(grant_id),
        "operator_user_id": str(operator_user_id),
        "scope": "READ_ONLY",
        "reason": reason,
        "ticket_ref": ticket_ref,
        "valid_from": valid_from.isoformat(),
        "valid_to": valid_to.isoformat(),
    }


def support_grant_content(session: Session, proposal: Mapping[str, Any]) -> dict[str, Any]:
    """The proposal with the state it changes: whether the operator is still an ACTIVE operator."""
    operator = session.execute(
        select(app_user.c.is_operator, app_user.c.status).where(
            app_user.c.id == UUID(str(proposal["operator_user_id"]))
        )
    ).one_or_none()
    return {
        "proposal": dict(proposal),
        "base": {
            "operator_active": operator is not None
            and bool(operator.is_operator)
            and operator.status == UserStatus.ACTIVE.value
        },
    }


def _approve_grant(
    table: Table, action: str, needs_person: str
) -> Callable[[UnitOfWork, UUID, UUID], None]:
    """``on_approved`` of a grant subject: REQUESTED → APPROVED with ``approved_at`` (E-96; PRD
    SM-13).

    ``submit`` runs this before the command inserts the row only when an ``AUTO_APPROVAL`` rule
    matches; that raises 409 ``invalid-transition`` and rolls the request back (XR-12).
    """

    def approve(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
        found = uow.session.execute(
            select(table.c.status).where(table.c.id == subject_id)
        ).scalar_one_or_none()
        if found is None:
            raise Problem("invalid-transition", needs_person)
        transitions.apply(
            uow.session,
            table.name,
            subject_id,
            to_status=GrantStatus.APPROVED.value,
            expected_status=GrantStatus.REQUESTED.value,
            set_values={"approved_at": uow.now},
        )
        uow.audit(
            action=action,
            object_type=table.name,
            object_id=subject_id,
            before={"status": GrantStatus.REQUESTED.value, "approved_at": None},
            after={"status": GrantStatus.APPROVED.value, "approved_at": uow.now},
            approval_request_id=approval_request_id,
        )

    return approve


def _close_grant(table: Table, action: str) -> Callable[[UnitOfWork, UUID, UUID], None]:
    """``on_rejected`` or ``on_voided`` of a grant subject: REQUESTED → REJECTED, the only way out
    of REQUESTED besides approval (PRD SM-13; E-96)."""

    def close(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
        found = uow.session.execute(
            select(table.c.status).where(table.c.id == subject_id)
        ).scalar_one_or_none()
        if found != GrantStatus.REQUESTED.value:
            return
        transitions.apply(
            uow.session,
            table.name,
            subject_id,
            to_status=GrantStatus.REJECTED.value,
            expected_status=GrantStatus.REQUESTED.value,
            set_values={},
        )
        uow.audit(
            action=action,
            object_type=table.name,
            object_id=subject_id,
            before={"status": GrantStatus.REQUESTED.value},
            after={"status": GrantStatus.REJECTED.value},
            approval_request_id=approval_request_id,
        )

    return close


def _nothing_to_undo(_: UnitOfWork, __: UUID, ___: UUID) -> None:
    """A pending proposal writes no subject row, so a rejection or void changes nothing."""


# --- MANUAL_EVENT (04 T-CON-24; dev-guide DG-KRN-EVT-02; BUILD_SPEC CTR-5, L4-1-Q-1) ------------

SUBMISSION_TABLE: Final = "event_submission"


def event_submission_content(session: Session, subject_id: UUID) -> Mapping[str, Any]:
    """The contract and the stored events of a submission (T-CON-24 ``events``)."""
    row = session.execute(
        select(event_submission.c.contract_id, event_submission.c.events).where(
            event_submission.c.id == subject_id
        )
    ).one_or_none()
    if row is None:
        raise SubjectNotVisible(f"event submission {subject_id} is not visible")
    return {
        "object_type": SUBMISSION_TABLE,
        "contract_id": str(row.contract_id),
        "events": list(row.events),
    }


def _visible_entity(found: Any) -> UUID:
    """The one entity a bound subject names (R-25; 04 T-PLT-17 rev 1.104). A subject row the caller
    cannot read answers 404 ``not-found`` (REQ-PLT-012): a bound subject never falls back to a
    tenant-level request."""
    if found is None:
        raise Problem("not-found")
    return UUID(str(found))


def _resolved_by_entities(_: Session, subject_id: UUID) -> UUID | None:
    raise LookupError(f"subject {subject_id} states its entities through SubjectSpec.entities")


def contracting_entity(session: Session, contract_id: UUID) -> UUID:
    """The contracting entity of a contract the caller reads; 404 ``not-found`` otherwise."""
    return _visible_entity(
        session.execute(
            select(contract.c.contracting_entity_id).where(contract.c.id == contract_id)
        ).scalar_one_or_none()
    )


def contract_group_entities(session: Session, contract_ids: Iterable[UUID]) -> SubjectEntities:
    """The legal entities a contract subject is bound to (R-25; supervisor rulings R-64 (1) and
    R-70 (b); 04 §16.10 rev 1.104): the contracting entities of the named contracts and of every
    current member of their combination groups. The approval of a contract subject recomputes or
    reverses the whole group — in its hook, or by the events it appends and the next computation
    — so every member's figures move on it; a contract alone in its group names its own entity.
    A contract subject belongs to the entity that CONTRACTS: the performing entities of its
    obligations are not added. Memberships are read from T-CON-04, which no entity scope hides.
    A named contract the session cannot read answers 404 (REQ-PLT-012); a member it cannot read
    makes the subject span every entity (``ALL_ENTITIES``) rather than drop the entity it cannot
    name. ``engine`` reads under the tenant's SYSTEM scope, where neither happens for a row that
    exists."""
    wanted = sorted({UUID(str(value)) for value in contract_ids})
    rows = session.execute(
        select(
            contract.c.id, contract.c.contracting_entity_id, contract.c.combination_group_id
        ).where(contract.c.id.in_(wanted))
    ).all()
    if not wanted or len(rows) != len(wanted):
        raise Problem("not-found")
    entities = {UUID(str(row.contracting_entity_id)) for row in rows}
    groups = sorted(
        {
            UUID(str(row.combination_group_id))
            for row in rows
            if row.combination_group_id is not None
        }
    )
    members = (
        {
            UUID(str(value))
            for value in session.scalars(
                select(combination_group_member.c.contract_id).where(
                    combination_group_member.c.combination_group_id.in_(groups),
                    combination_group_member.c.valid_to_known_at.is_(None),
                )
            )
        }
        if groups
        else set()
    ) - set(wanted)
    if not members:
        return SubjectEntities(frozenset(entities))
    owners = session.execute(
        select(contract.c.id, contract.c.contracting_entity_id).where(
            contract.c.id.in_(sorted(members))
        )
    ).all()
    if len(owners) != len(members):
        return ALL_ENTITIES
    return SubjectEntities(frozenset(entities | {UUID(str(entity_id)) for _, entity_id in owners}))


def contract_subject_entities(session: Session, subject_id: UUID) -> SubjectEntities:
    """The entities of a ``CONTRACT_ACTIVATION`` or ``CONTRACT_VOID`` request: the subject is the
    contract (``contract_group_entities``)."""
    return contract_group_entities(session, [subject_id])


def event_submission_entities(session: Session, subject_id: UUID) -> SubjectEntities:
    """The entities of a ``MANUAL_EVENT`` or ``ATTRIBUTE_CHANGE`` request: the group of the
    submission's contract (T-CON-24 ``contract_id``; ``contract_group_entities`` — the approved
    events mark the group dirty and the next computation includes them)."""
    found = session.execute(
        select(event_submission.c.contract_id).where(event_submission.c.id == subject_id)
    ).scalar_one_or_none()
    return contract_group_entities(session, [_visible_entity(found)])


# 04 §16.10 (P5-SUBJ-1): the templates whose rows key on a contract — a contract template, and the
# contract-event / modification templates of both families (LEGACY_V1 `legacy_progress_tracking` /
# `legacy_contract_modification`; CSV_V2 `invoices`, `progress_events`, `usage`, `cost_events`,
# `pre_standard_revenue`, `modifications`, whose `key_column` is the contract). `estimates` keys on
# a contract too but targets an estimate version whose own approval revalidates — excluded (D-98
# candidate 135: a contract-head binding there would double-bind one change to two approvals).
CONTRACT_KEYED_TARGETS: Final = frozenset({"contract", "contract_event", "modification"})
# The normalized-row column that holds the CONTRACT of each contract-keyed template, by template
# code — REGISTERED by the domain templates when they load (`legacy_v1`, `csv_v2`; the
# `register_lifecycle` pattern): the kernel never names a domain column (DG-ARC-01) and never parses
# the display `business_key` (D-98 candidate 135 amendment 1). An unregistered code names nothing.
_IMPORT_CONTRACT_COLUMNS: Final[dict[str, str]] = {}


def register_import_contract_column(template_code: str, column: str) -> None:
    """Register the normalized-row column that holds the contract of ``template_code``'s rows."""
    _IMPORT_CONTRACT_COLUMNS[str(template_code)] = str(column)


def import_contract_column(template_code: str) -> str | None:
    """The registered contract column of ``template_code``; None when none is registered."""
    return _IMPORT_CONTRACT_COLUMNS.get(str(template_code))


def import_contract_keys(session: Session, subject_id: UUID) -> list[str]:
    """The external ids of the contracts an import's VALID / WARNING rows name — a contract
    template's keys, and for the contract-event / modification templates the contract of each row
    (04 §16.10 rev 1.65; D-98 candidate 135): the keys `import_commit_content` pins the heads of,
    and the keys an import's consumed basis covers (`engine.consume_fresh_basis`; DG-KRN-APR-05
    rev 1.51). Each contract is read from the row's AUTHORITATIVE normalized data — the legacy v1
    `Contract Unique Name` column, or a CSV v2 template's registered `key_column` — never parsed
    out of the display `business_key` (T-IMP-03 joins its columns with " / ", a sequence that is
    admissible inside a contract identifier: D-98 candidate 135 amendment 1, Codex
    production-20260921-1521 §1). Sorted, deduplicated, exact text."""
    row = session.execute(
        select(import_upload.c.template_code, import_upload.c.template_version).where(
            import_upload.c.id == subject_id
        )
    ).one_or_none()
    if row is None:
        raise SubjectNotVisible(f"import upload {subject_id} is not visible")
    template = session.execute(
        select(import_template.c.target_object, import_template.c.family).where(
            import_template.c.code == row.template_code,
            import_template.c.version == row.template_version,
        )
    ).one_or_none()
    if template is None or template.target_object not in CONTRACT_KEYED_TARGETS:
        return []
    column = import_contract_column(str(row.template_code))
    if column is None:  # a seeded template whose emitter registered no contract column
        return []
    keys: set[str] = set()
    for normalized in session.scalars(
        select(import_row.c.normalized).where(
            import_row.c.import_upload_id == subject_id,
            import_row.c.normalized.is_not(None),
            import_row.c.status.in_(("VALID", "WARNING")),
        )
    ):
        value = (normalized or {}).get(column)
        if value is not None and str(value) != "":
            keys.add(str(value))
    return sorted(keys)


def import_commit_content(session: Session, subject_id: UUID) -> Mapping[str, Any]:
    """05 IPL-08: the file hash, template version, parameters and diff file hash of an import.

    [J] L5-1-Q-6; 04 §16.10 rev 1.65 (D-98 candidate 135): the content also holds the stream head of
    every contract the upload's rows name — a contract template's keys and the contract of each
    contract-event / modification row (`import_contract_keys`) — so an event appended to one of
    them before the decision voids the request with ``STALE_SUBJECT`` (05 IPL-10; REQ-PLT-014).
    """
    row = session.execute(
        select(
            import_upload.c.file_sha256,
            import_upload.c.template_code,
            import_upload.c.template_version,
            import_upload.c.parameters,
            import_upload.c.diff_file_id,
        ).where(import_upload.c.id == subject_id)
    ).one_or_none()
    if row is None:
        raise SubjectNotVisible(f"import upload {subject_id} is not visible")
    diff_sha256 = (
        None
        if row.diff_file_id is None
        else session.execute(
            select(file_object.c.sha256).where(file_object.c.id == row.diff_file_id)
        ).scalar_one_or_none()
    )
    keys = import_contract_keys(session, subject_id)
    heads: list[list[Any]] = []
    if keys:
        found = {
            str(external_id): int(head)
            for external_id, head in session.execute(
                select(contract.c.external_id, contract.c.head_stream_version).where(
                    contract.c.external_id.in_(keys)
                )
            )
        }
        heads = [[key, found.get(key)] for key in keys]
    return {
        "object_type": "import_upload",
        "file_sha256": str(row.file_sha256).strip(),
        "template_code": str(row.template_code),
        "template_version": int(row.template_version),
        "parameters": dict(row.parameters or {}),
        "diff_file_sha256": None if diff_sha256 is None else str(diff_sha256).strip(),
        "contracts": heads,
    }


def import_commit_entities(session: Session, subject_id: UUID) -> SubjectEntities:
    """The legal entities an ``IMPORT_COMMIT`` request is bound to (R-25; 04 §16.10 rev 1.104;
    supervisor rulings R-29, R-41 (5) and R-87 (1)): the entities the upload's rows name, as the
    imports domain resolved and stored them at validation (``imports.scope.named_entity_ids``,
    stated through the registered lifecycle — the kernel names no column of a template,
    DG-ARC-01). A tenant-level upload names none; an unresolved one spans every entity. The set
    is joined, whenever it is read, with the contracting entities of every current member of the
    combination groups of the contracts the rows name (``import_contract_keys``,
    ``contract_group_entities``; R-64 (1), R-87 (1)): the commit appends to those contracts and
    computes their groups. ``LookupError`` while the imports domain registered no entity source:
    the kernel never guesses the entities of an import (XR-12)."""
    lifecycle = LIFECYCLES.get(ApprovalSubjectType.IMPORT_COMMIT)
    if lifecycle is None or lifecycle.entities is None:
        raise LookupError("approval subject IMPORT_COMMIT has no registered entity source")
    named = lifecycle.entities(session, subject_id)
    if named.all_entities:
        return named
    keys = import_contract_keys(session, subject_id)
    contract_ids = (
        [
            UUID(str(value))
            for value in session.scalars(
                select(contract.c.id).where(contract.c.external_id.in_(keys))
            )
        ]
        if keys
        else []
    )
    if not contract_ids:  # no row names a contract that exists yet
        return named
    grouped = contract_group_entities(session, contract_ids)
    if grouped.all_entities:
        return ALL_ENTITIES
    return SubjectEntities(named.ids | grouped.ids)


def import_commit_preparer_entities(session: Session, subject_id: UUID) -> SubjectEntities:
    """The entities the uploader of an import is held to when the ``IMPORT_COMMIT`` request is
    submitted (supervisor ruling R-64 (6) with R-29; 04 §16.10 rev 1.104 part 9, §16.6; 05
    IPL-08): those named by the rows that will COMMIT, as the imports domain states them
    (``imports.scope.preparer_entities``, through the registered lifecycle) — every data row, or
    in quarantine mode the usable rows, the refused rows staying behind (REQ-DAT-008). The
    request itself stays bound to every entity any row names (``import_commit_entities``).
    Without a registered source the uploader is held to the entities of the request."""
    lifecycle = LIFECYCLES.get(ApprovalSubjectType.IMPORT_COMMIT)
    if lifecycle is None or lifecycle.preparer_entities is None:
        return import_commit_entities(session, subject_id)
    return lifecycle.preparer_entities(session, subject_id)


def _event_submission_preparer_entities(
    subject_type: ApprovalSubjectType,
) -> Callable[[Session, UUID], SubjectEntities]:
    """``SubjectSpec.preparer_entities`` of ``MANUAL_EVENT`` and ``ATTRIBUTE_CHANGE`` (item
    MANUAL-EVENT-PREPARER-SCOPE-1; the supervisor's ruling of 2026-10-01; 04 §16.10 rev 1.269):
    the entity the contracts domain states (``contracts.events.preparer_entities``, through the
    registered lifecycle) — the contracting entity of the ONE contract the events are recorded
    on. The preparer records the facts of that contract, her entity's. The request itself stays
    bound to the contracting entities of the contract's whole group
    (``event_submission_entities``): its approval computes the group, which its deciders answer
    for with the permission for every entity, and which the preparer neither authors nor reads.
    Without a registered source the preparer is held to the entities of the request."""

    def stated(session: Session, subject_id: UUID) -> SubjectEntities:
        lifecycle = LIFECYCLES.get(subject_type)
        if lifecycle is None or lifecycle.preparer_entities is None:
            return event_submission_entities(session, subject_id)
        return lifecycle.preparer_entities(session, subject_id)

    return stated


def import_commit_floor(
    session: Session, subject_id: UUID, entities: SubjectEntities, at: datetime
) -> Sequence[FloorStep]:
    """The further steps of an ``IMPORT_COMMIT`` request whose commit performs an approval by
    itself (R-38 (ii); supervisor rulings R-87 (1) and R-92; 04 §16.10 rev 1.104, §16.6): the
    request keeps its own step, whose approver also answers for the first approver of every
    approval the commit performs (``import_commit_deciders``), and gains one step per further
    approver any of those approvals takes — the underlying subject's second step with its role,
    a step a routing rule of the workspace adds to that subject. The imports domain states them
    (``imports.scope.floor_steps``, through the registered lifecycle — the kernel names no
    template, DG-ARC-01); ``LookupError`` while it registered none (XR-12)."""
    lifecycle = LIFECYCLES.get(ApprovalSubjectType.IMPORT_COMMIT)
    if lifecycle is None or lifecycle.floor is None:
        raise LookupError("approval subject IMPORT_COMMIT has no registered floor")
    return lifecycle.floor(session, subject_id, entities, at)


def import_commit_deciders(
    session: Session,
    subject_id: UUID,
    entities: SubjectEntities,
    ordinal: int,
    user_ids: Collection[UUID],
    at: datetime,
) -> Mapping[UUID, DeciderRefusal]:
    """``SubjectSpec.deciders`` of ``IMPORT_COMMIT`` (supervisor ruling R-92): who of ``user_ids``
    may not give approval number ``ordinal`` of the request, because they do not hold what the
    approvals its commit performs ask of that approver (``imports.scope.decider_refusals``,
    through the registered lifecycle); ``LookupError`` while the imports domain registered no
    such check (XR-12: an import is never decided on the step's permission alone by default)."""
    lifecycle = LIFECYCLES.get(ApprovalSubjectType.IMPORT_COMMIT)
    if lifecycle is None or lifecycle.deciders is None:
        raise LookupError("approval subject IMPORT_COMMIT has no registered check of its deciders")
    return lifecycle.deciders(session, subject_id, entities, ordinal, user_ids, at)


def _submission_events(
    items: Sequence[Mapping[str, Any]], approval_request_id: UUID
) -> list[EventIn]:
    events: list[EventIn] = []
    for item in items:
        event_type = ContractEventType(str(item["event_type"]))
        key = item.get("obligation_key")
        supersedes = item.get("supersedes_event_id")
        events.append(
            EventIn(
                event_type=event_type,
                effective_date=date.fromisoformat(str(item["effective_date"])),
                payload=parse_payload(
                    event_type, LATEST_SCHEMA_VERSION[event_type], item["payload"]
                ),
                obligation_keys=() if key is None else (str(key),),
                is_manual=True,
                supersedes_event_id=None if supersedes is None else UUID(str(supersedes)),
                approval_request_id=approval_request_id,
            )
        )
    return events


def _submission_stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


# The contracts domain's check of a stored batch (``_apply_event_submission``): the unit of work,
# the locked contract row and the events the stored items parse to.
type EventSubmissionCheck = Callable[[UnitOfWork, Mapping[str, Any], Sequence[EventIn]], None]
# The contracts domain's writes that belong to the append: the unit of work of the SYSTEM principal
# that appended, acting for the preparer, and the stored rows of the appended events.
type EventSubmissionApplied = Callable[[UnitOfWork, Sequence[Mapping[str, Any]]], None]


def _apply_event_submission(
    uow: UnitOfWork,
    subject_id: UUID,
    approval_request_id: UUID,
    *,
    check: EventSubmissionCheck | None = None,
    before_basis: Callable[[UnitOfWork], None] | None = None,
    applied: EventSubmissionApplied | None = None,
) -> None:
    """DG-KRN-EVT-02: the SYSTEM principal appends the approved events on behalf of the preparer at
    the contract's head, and the submission becomes APPLIED with their ids (T-CON-24). The events
    mark the group dirty; the lifecycle of the contracts domain computes it after this call (04
    T-CON-24 rev 1.194 — until then the next computation included them, [J] L4-1-Q-1).

    ``check`` (BUILD_SPEC CTR-6; 04 T-CON-24 "Checked again where it is appended"): the domain's
    validation of the stored batch against the stream as it stands, called under the submission,
    group and contract locks, after the basis and the Step 1 refusals and before the append, with
    the locked contract row and the events. It raises ``engine.StaleBasis`` on a finding, which
    ``decide`` answers by voiding the request as stale.

    ``before_basis`` and ``applied`` (item EVT-EVIDENCE-1; 04 T-CON-24 rev 1.268): the domain's
    locks that belong under the submission, group and contract locks and before the basis is read
    again — the files of the request's evidence — and the domain's writes that belong to the
    append, made by the SYSTEM unit of work that appended, with the stored rows of the events."""
    session = uow.session
    row = (
        session.execute(
            select(event_submission).where(event_submission.c.id == subject_id).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise LookupError(f"event submission {subject_id} of request {approval_request_id} is gone")
    preparer = session.execute(
        select(approval_request.c.preparer_id).where(approval_request.c.id == approval_request_id)
    ).scalar_one_or_none()
    # DG-KRN-DB-08 rev 1.36 (D-98 101b): the group row first, then the contract row — the appended
    # events update the contract (_raise_head) and mark the group dirty under held locks.
    _, locked_contract = lock_group_then_contract(session, UUID(str(row["contract_id"])))
    if before_basis is not None:
        before_basis(uow)
    # DG-KRN-APR-05 rev 1.40 (D-98 candidate 101d, R3d-b): under the submission, group and contract
    # locks, before the first write, the submission must still hash to the basis the approver
    # reviewed (its contract id and stored events — immutable after submission, so this is the
    # uniform check, not a race the content could expose).
    from erev_api.approvals import engine  # noqa: PLC0415

    engine.assert_fresh_basis(uow, approval_request_id)
    events = _submission_events(row["events"], approval_request_id)
    # Supervisor ruling R-77 (9): what a submission may hold is decided again where it is
    # appended — no activation event, no Step 1 assessment or flag, no void of an assessment or of
    # an activation event (rulings R-20, R-61 (b)) — so a submission stored before a refusal
    # existed, or built below the routes, never reaches the stream.
    step1.refuse_stored(session, events)
    if check is not None:
        check(uow, locked_contract, events)
    head = int(locked_contract["head_stream_version"])
    system_ctx = dataclasses.replace(
        uow.ctx,
        principal=system_principal(uow.principal.tenant_id, on_behalf_of_id=preparer),
    )
    system = type(uow)(
        ctx=system_ctx, session=session, clock=uow.clock, keyring=uow.keyring, files=uow.files
    )
    system.now = uow.now
    appended = append_events(
        system,
        contract_id=row["contract_id"],
        expected_stream_version=int(head),
        events=events,
        origin="SYSTEM",
    )
    if applied is not None:
        applied(system, appended)
    for event in system.drain_audit_events():
        uow.buffer_audit_event(event)
    stamps = _submission_stamps(uow)
    transitions.apply(
        session,
        SUBMISSION_TABLE,
        subject_id,
        to_status="APPROVED",
        expected_status="SUBMITTED",
        set_values=stamps,
    )
    transitions.apply(
        session,
        SUBMISSION_TABLE,
        subject_id,
        to_status="APPLIED",
        expected_status="APPROVED",
        set_values={"applied_event_ids": [item["id"] for item in appended], **stamps},
    )


def _close_event_submission(status: str) -> Callable[[UnitOfWork, UUID, UUID], None]:
    def close(uow: UnitOfWork, subject_id: UUID, _approval_request_id: UUID) -> None:
        transitions.apply(
            uow.session,
            SUBMISSION_TABLE,
            subject_id,
            to_status=status,
            expected_status="SUBMITTED",
            set_values=_submission_stamps(uow),
        )

    return close


_reject_event_submission = _close_event_submission("REJECTED")
_void_event_submission = _close_event_submission("VOIDED")
# BUILD_SPEC CTR-6 (dev-guide DG-KRN-EVT-02 rev 1.177): the contracts domain registers the lifecycle
# of the two event-submission subjects and composes it from these — the check of a stored batch
# against the stream as it stands, and the computation after the append, are the domain's.
apply_event_submission: Final = _apply_event_submission
reject_event_submission: Final = _reject_event_submission
void_event_submission: Final = _void_event_submission


# --- JUDGEMENT_RECORD (04 T-CON-19; PRD SM-10, §2.5; BUILD_SPEC CTR-7) ----------------------------


def _constraint_estimate_basis(
    session: Session, record: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Bind a constraint review to a specific version and its financial inputs.

    Version subjects resolve directly. Other contract-bound subjects resolve the named
    element's latest version (or its explicitly named version key). The binding is part of
    the existing immutable submitted-content hash, not a caller-supplied questionnaire value.
    Linking the record, adding evidence, or advancing lifecycle status does not change it.
    """
    if str(getattr(record["topic"], "value", record["topic"])) != "CONSTRAINT":
        return None
    if record["contract_id"] is None:
        return None
    named = (record["questionnaire"] or {}).get("estimate_key")
    statement = (
        select(
            estimate_version,
            estimate.c.element_code,
            estimate.c.method,
            estimate.c.direction,
            estimate.c.vc_element_type,
            estimate.c.allocation_target,
            estimate.c.target_obligation_ids,
            estimate.c.obligation_id,
            contract.c.external_id,
        )
        .select_from(
            estimate_version.join(
                estimate,
                and_(
                    estimate.c.tenant_id == estimate_version.c.tenant_id,
                    estimate.c.id == estimate_version.c.estimate_id,
                ),
            ).join(
                contract,
                and_(
                    contract.c.tenant_id == estimate.c.tenant_id,
                    contract.c.id == estimate.c.contract_id,
                ),
            )
        )
        .where(
            estimate.c.contract_id == record["contract_id"],
            estimate.c.estimate_kind == "VARIABLE_CONSIDERATION",
        )
        .order_by(estimate_version.c.version_no.desc(), estimate_version.c.id)
    )
    if str(record["subject_type"]) == "estimate_version":
        statement = statement.where(estimate_version.c.id == record["subject_id"])
    for row in session.execute(statement).mappings():
        key = obligation_subject_key(str(row["external_id"]), str(row["element_code"]))
        if named not in (str(row["element_code"]), key, f"{key}@v{int(row['version_no'])}"):
            continue
        return {
            "version_id": str(row["id"]),
            "estimate_id": str(row["estimate_id"]),
            "version_no": int(row["version_no"]),
            "effective_date": row["effective_date"].isoformat(),
            **{
                name: None if row[name] is None else str(getattr(row[name], "value", row[name]))
                for name in (
                    "method",
                    "direction",
                    "vc_element_type",
                    "allocation_target",
                    "obligation_id",
                )
            },
            "target_obligation_ids": sorted(
                str(value) for value in row["target_obligation_ids"] or ()
            ),
            **{
                name: _decimal_text(row[name])
                for name in (
                    "unconstrained_amount",
                    "most_conservative_amount",
                    "constrained_amount",
                    "expected_total_amount",
                    "rate",
                    "expected_quantity",
                )
            },
            **{
                name: row[name]
                for name in (
                    "scenarios",
                    "parameters",
                    "amortization_months",
                    "constraint_checklist",
                )
            },
            "currency": None if row["currency"] is None else str(row["currency"]).strip(),
        }
    return None


def judgement_record_content(session: Session, subject_id: UUID) -> Mapping[str, Any]:
    """The reviewed conclusion and questionnaire, including a constraint's estimate basis.

    The stored hash binds the current version and figures at submission. Subsequent figure
    changes make a pending review stale and invalidate its use at estimate approval.
    """
    row = (
        session.execute(select(judgement_record).where(judgement_record.c.id == subject_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise SubjectNotVisible(f"judgement record {subject_id} is not visible")
    book = row["book_code"]
    basis = _constraint_estimate_basis(session, dict(row))
    return {
        **({"constraint_estimate_basis": basis} if basis is not None else {}),
        "object_type": "judgement_record",
        "judgement_no": str(row["judgement_no"]),
        "topic": str(getattr(row["topic"], "value", row["topic"])),
        "subject_type": str(row["subject_type"]),
        "subject_id": str(row["subject_id"]),
        "contract_id": None if row["contract_id"] is None else str(row["contract_id"]),
        "book_code": None if book is None else str(getattr(book, "value", book)),
        "conclusion": str(row["conclusion"]),
        "rationale": str(row["rationale"]),
        "alternatives_considered": row["alternatives_considered"],
        "codification_refs": [str(value) for value in row["codification_refs"] or ()],
        "questionnaire": row["questionnaire"],
    }


def judgement_record_subject_content(session: Session, subject_id: UUID) -> Mapping[str, Any]:
    """The approval subject content of a ``JUDGEMENT_RECORD`` request (04 §16.10 rev 1.49; D-98
    candidate 101c): the record's reviewed content and, when the record names a contract, that
    contract's current group and stream head — so a contract moved or appended between the request
    and the decision makes the decision stale (STALE_SUBJECT) and the review's recompute never runs
    against rows the approver did not review. The record's own ``content_sha256`` (T-CON-19) stays
    ``judgement_record_content``."""
    content = dict(judgement_record_content(session, subject_id))
    contract_id = content["contract_id"]
    if contract_id is None:
        content["contract"] = None
        return content
    (state,) = _member_states(session, [UUID(str(contract_id))])
    content["contract"] = {
        "combination_group_id": state["combination_group_id"],
        "head_stream_version": state["head_stream_version"],
    }
    return content


def judgement_record_entities(session: Session, subject_id: UUID) -> SubjectEntities:
    """The entities of a ``JUDGEMENT_RECORD`` request (R-25; R-64 (1)): the group of the contract
    the record names (T-CON-19 ``contract_id`` — a contract, obligation or modification subject;
    ``contract_group_entities``: the review releases the hold and computes the group again). A
    record that names no contract (a product, a registry version, a migration batch) is a
    tenant-level subject."""
    row = session.execute(
        select(judgement_record.c.contract_id).where(judgement_record.c.id == subject_id)
    ).one_or_none()
    if row is None:
        raise Problem("not-found")
    if row.contract_id is None:
        return TENANT_LEVEL
    return contract_group_entities(session, [UUID(str(row.contract_id))])


# ERR-02 copy for the author of a judgement record, in person or through a delegate.
JUDGEMENT_AUTHOR_DETAIL: Final = "You wrote this judgement record, so another user must review it."


def judgement_record_author(session: Session, subject_id: UUID) -> frozenset[UUID]:
    """T-CON-19 ``reviewer_id`` "must differ from ``created_by``" (DB-10
    ``tg_judgement_record__review``): the record's author may not review it, whoever submitted it.
    The database guard sees the deciding person only; as an excluded decider the author is also
    refused as the DELEGATOR of whoever decides on the author's behalf (R-25; REQ-PLT-011 "across
    UI, API, delegation and role switching")."""
    row = session.execute(
        select(judgement_record.c.created_by, judgement_record.c.created_by_kind).where(
            judgement_record.c.id == subject_id
        )
    ).one_or_none()
    if row is None or row.created_by is None:
        return frozenset()
    kind = str(getattr(row.created_by_kind, "value", row.created_by_kind))
    return frozenset({UUID(str(row.created_by))}) if kind == "USER" else frozenset()


# --- COMBINATION_GROUP (04 T-CON-03; PRD §2.5; BUILD_SPEC CTR-8, L4-1-Q-16) -----------------------


def _combination_proposal(session: Session, group: RowMapping) -> RowMapping | None:
    """The submitted proposal a ``COMBINATION_GROUP`` request is about: the record the
    combination command wrote (item COMBINATION-PROPOSAL-RECORD-1; 04 §16.10 "Subject
    content" and T-CON-19, rev 1.283). For a combination it is the record the group names
    (T-CON-03 ``judgement_record_id``) while the group is PROPOSED or SUBMITTED; for a leave
    from an APPLIED group, the group's ``SUBMITTED`` record of action ``LEAVE`` that carries
    no approval request of its own — the command submits it without one, and one request is
    pending per subject. Never "the latest record of the topic": a record somebody else
    wrote for the group changed the content a pending request hashes, so its approval voided
    it as stale, and made its writer an author of the proposal
    (``domain.contracts.combination._proposal`` reads by the same rule)."""
    record = judgement_record.c
    status = str(getattr(group["status"], "value", group["status"]))
    conditions = [
        record.subject_type == "combination_group",
        record.subject_id == group["id"],
        record.topic == "COMBINATION",
        record.status == "SUBMITTED",
    ]
    if status in ("PROPOSED", "SUBMITTED"):
        if group["judgement_record_id"] is None:
            return None
        conditions.append(record.id == group["judgement_record_id"])
    elif status == "APPLIED" and not group["is_singleton"]:
        conditions += [
            record.questionnaire.contains({"action": "LEAVE"}),
            record.approval_request_id.is_(None),
        ]
    else:
        return None
    return (
        session.execute(
            select(
                record.judgement_no,
                record.questionnaire,
                record.created_by,
                record.created_by_kind,
            )
            .where(*conditions)
            .order_by(record.judgement_no.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )


def combination_group_content(session: Session, subject_id: UUID) -> Mapping[str, Any]:
    """The group and its submitted ``COMBINATION`` proposal (action and contracts): the
    record the command wrote (``_combination_proposal``)."""
    group = (
        session.execute(select(combination_group).where(combination_group.c.id == subject_id))
        .mappings()
        .one_or_none()
    )
    if group is None:
        raise SubjectNotVisible(f"combination group {subject_id} is not visible")
    proposal = _combination_proposal(session, group)
    questionnaire: dict[str, Any] = (
        {} if proposal is None else dict(proposal["questionnaire"] or {})
    )
    member_ids = sorted(UUID(str(value)) for value in questionnaire.get("contract_ids", ()))
    return {
        "object_type": "combination_group",
        "code": str(group["code"]),
        "is_singleton": bool(group["is_singleton"]),
        "status": str(getattr(group["status"], "value", group["status"])),
        "transaction_currency": str(group["transaction_currency"]).strip(),
        "criterion": group["criterion"],
        "rationale": group["rationale"],
        "proposal": None
        if proposal is None
        else {
            "judgement_no": str(proposal["judgement_no"]),
            "questionnaire": proposal["questionnaire"],
        },
        # 04 §16.10 rev 1.49 (D-98 candidate 101c): each proposal member's current group and
        # stream head at the request — a member moved or appended before the decision makes it
        # stale (STALE_SUBJECT), never applied against rows the approver did not review.
        "members": _member_states(session, member_ids),
    }


# ERR-02 copy for the author of a combination proposal, in person or through a delegate.
COMBINATION_AUTHOR_DETAIL: Final = (
    "You wrote this combination proposal, so another user must approve it."
)


def combination_group_author(session: Session, subject_id: UUID) -> frozenset[UUID]:
    """The author of the combination proposal a ``COMBINATION_GROUP`` request approves — the
    creator of the group's SUBMITTED ``COMBINATION`` judgement record, who need not be the person
    who submitted it (R-41 (3); the judgement-author rule of 04 T-CON-19). The approval reviews
    that record (``reviewer_id``), and DB-10 sees only the deciding person; as an excluded decider
    the author is refused in person, through a delegate and in bulk approval. The record is
    the one the command wrote (``_combination_proposal``; item COMBINATION-PROPOSAL-RECORD-1):
    the creator of another record of the group is no author of the proposal."""
    group = (
        session.execute(select(combination_group).where(combination_group.c.id == subject_id))
        .mappings()
        .one_or_none()
    )
    proposal = None if group is None else _combination_proposal(session, group)
    if proposal is None or proposal["created_by"] is None:
        return frozenset()
    kind = str(getattr(proposal["created_by_kind"], "value", proposal["created_by_kind"]))
    return frozenset({UUID(str(proposal["created_by"]))}) if kind == "USER" else frozenset()


def _member_states(session: Session, contract_ids: Sequence[UUID]) -> list[dict[str, Any]]:
    """``{contract_id, combination_group_id, head_stream_version}`` per contract, ascending id."""
    if not contract_ids:
        return []
    found = {
        UUID(str(row.id)): row
        for row in session.execute(
            select(
                contract.c.id, contract.c.combination_group_id, contract.c.head_stream_version
            ).where(contract.c.id.in_(list(contract_ids)))
        )
    }
    states: list[dict[str, Any]] = []
    for contract_id in sorted(contract_ids):
        row = found.get(contract_id)
        states.append(
            {
                "contract_id": str(contract_id),
                "combination_group_id": None if row is None else str(row.combination_group_id),
                "head_stream_version": None if row is None else int(row.head_stream_version),
            }
        )
    return states


def combination_group_entities(session: Session, subject_id: UUID) -> SubjectEntities:
    """The legal entities a ``COMBINATION_GROUP`` request is bound to (R-25; 04 T-PLT-17 rev 1.104):
    the contracting entities of every contract the decision re-allocates — the contracts of the
    submitted proposal, the current members of the group and the current members of each group a
    proposal contract is in now (the group it would leave). Memberships are read from T-CON-04,
    which no entity scope hides; a member contract the caller cannot read makes the subject span
    every entity (``ALL_ENTITIES``) rather than drop the entity it cannot name."""
    members = combination_group_content(session, subject_id)["members"]
    wanted = {UUID(str(member["contract_id"])) for member in members}
    groups = {subject_id} | {
        UUID(str(member["combination_group_id"]))
        for member in members
        if member["combination_group_id"] is not None
    }
    wanted |= {
        UUID(str(value))
        for value in session.scalars(
            select(combination_group_member.c.contract_id).where(
                combination_group_member.c.combination_group_id.in_(sorted(groups)),
                combination_group_member.c.valid_to_known_at.is_(None),
            )
        )
    }
    if not wanted:
        return ALL_ENTITIES
    owners = session.execute(
        select(contract.c.id, contract.c.contracting_entity_id).where(
            contract.c.id.in_(sorted(wanted))
        )
    ).all()
    if len(owners) != len(wanted):
        return ALL_ENTITIES
    return SubjectEntities(frozenset(UUID(str(entity_id)) for _, entity_id in owners))


# --- CONTRACT_ACTIVATION (04 T-CON-01, §16.1; PRD SM-02, §2.5; BUILD_SPEC CTR-9) -----------------

ACTIVATION_THRESHOLD: Final = Decimal("100000.00")  # PRD §2.5: TP ≥ USD 100,000.00 is routed
CONTROLLER_THRESHOLD: Final = Decimal("1000000.00")  # PRD §2.5: a second step held by a Controller
# Item ACT-FLAGS-1 (the supervisor's ruling of 2026-10-02; PRD §2.5 rev 1.194; 04 §16.10 rev
# 1.287): the currency the routing thresholds of PRD §2.5 are amounts of — the two above, the P&L
# impact of an estimate version, the two of a modification and the amount of a manual adjustment.
# Stated HERE and nowhere else: the readers (``domain.contracts.activation``, ``.estimates``,
# ``.modifications``, ``domain.journals.adjustments``) import it, so a workspace's own threshold
# currency, the day there is one, is this one change.
THRESHOLD_CURRENCY: Final = "USD"
ABOVE_THRESHOLD: Final = "ABOVE_THRESHOLD"  # 04 T-PLT-17 flag
ABOVE_CONTROLLER_THRESHOLD: Final = "ABOVE_CONTROLLER_THRESHOLD"  # [J] L4-1-Q-20
# Item ACT-FLAGS-1 (04 §16.10 rev 1.287; the supervisor's ruling of 2026-10-02): an activation
# whose amount cannot be stated for want of a spot rate — to the threshold currency, or to the
# entity's functional currency. A second-step flag of the subject BY ITSELF: a request without a
# functional amount is one no tenant's amount rule can read, so it never passes such a rule
# unseen — a Controller decides it.
RATE_NOT_PUBLISHED: Final = "RATE_NOT_PUBLISHED"
CONTROLLER_ROLE: Final = "controller"
CONTRACT_LINK: Final = "/contracts/{contract_id}"  # SCREENS SF-03
# PRD §2.5 CONTRACT_VOID rows; 04 T-PLT-17 flag examples; demo ROUTE-VOID-02 (BUILD_SPEC CTR-11).
POSTED_LINES: Final = "POSTED_LINES"


def contract_activation_content(session: Session, subject_id: UUID) -> Mapping[str, Any]:
    """The contract an activation request approves: its identity, head and reference; an appended
    event raises the head, so the request becomes stale (DG-KRN-APR-05). The activation of a
    NOT_A_CONTRACT contract also states the ``CONTRACT_CRITERIA_MET`` events its approval appends
    — book, effective date and judgement record (04 §16.10 rev 1.105; supervisor ruling R-20 (c);
    REQ-PLT-014): a book enabled or disabled, or a record no longer reviewed, changes them without
    an event. Every other activation keeps the members it had."""
    row = session.execute(
        select(
            contract.c.contract_no,
            contract.c.external_id,
            contract.c.head_stream_version,
            contract.c.document_ref,
            contract.c.combination_group_id,
            contract.c.status,
            contract.c.contracting_entity_id,
        ).where(contract.c.id == subject_id)
    ).one_or_none()
    if row is None:
        raise SubjectNotVisible(f"contract {subject_id} is not visible")
    content: dict[str, Any] = {
        "object_type": "contract",
        "contract_no": str(row.contract_no),
        "external_id": str(row.external_id),
        "head_stream_version": int(row.head_stream_version),
        "document_ref": row.document_ref,
        "combination_group_id": str(row.combination_group_id),
    }
    criteria = step1.criteria_met(
        session,
        contract_id=subject_id,
        status=row.status,
        entity_id=UUID(str(row.contracting_entity_id)),
    )
    if criteria:
        content["criteria_met"] = [item.members() for item in criteria]
    return content


@dataclass(frozen=True, slots=True)
class PostedBasis:
    """The contract's posted-state basis a void reverses (D-98 92 / 99a / 99b): its subledger line
    count, the latest posting time (``recorded_at``; readable) and, per book, the T-SL-02
    ``chain_seq`` of its last posting — the strictly ordered position the reversed set is derived
    from (04 T-SL-01), never the timestamp (two postings sealed in one clock instant would fall on
    both sides of a time cutoff)."""

    line_count: int
    posted_through: datetime | None
    positions: Mapping[str, int]

    def members(self) -> dict[str, Any]:
        """The cutoff members of the ``CONTRACT_VOIDED`` payload, the stored preview, the execution
        audit event and the request content (04 §16.1, §16.3)."""
        return {
            "posted_line_count": self.line_count,
            "posted_through": None
            if self.posted_through is None
            else self.posted_through.isoformat(),
            "posted_through_seq": dict(sorted(self.positions.items())),
        }


def _book(value: Any) -> str:
    return str(getattr(value, "value", value)).strip()


def posted_basis(session: Session, contract_id: UUID) -> PostedBasis:
    """The contract's posted-state basis (``PostedBasis``), read in the caller's transaction."""
    row = session.execute(
        select(func.count(), func.max(subledger_line.c.recorded_at)).where(
            subledger_line.c.contract_id == contract_id
        )
    ).one()
    seal = subledger_posting_seal
    positions = session.execute(
        select(seal.c.book_code, func.max(seal.c.chain_seq))
        .select_from(
            seal.join(
                subledger_line, subledger_line.c.subledger_posting_id == seal.c.subledger_posting_id
            )
        )
        .where(subledger_line.c.contract_id == contract_id)
        .group_by(seal.c.book_code)
    ).all()
    return PostedBasis(
        line_count=int(row[0]),
        posted_through=row[1],
        positions={_book(book): int(seq) for book, seq in positions},
    )


def reversed_population(
    session: Session, contract_id: UUID, positions: Mapping[str, int]
) -> tuple[dict[str, tuple[UUID, ...]], int]:
    """The reversed set derived from a stored cutoff position (04 T-SL-01; D-98 99b): per book, the
    postings of the contract whose seal ``chain_seq`` is at or below ``positions[book]`` in chain
    order, and the count of the contract's lines in them. Empty without a position."""
    if not positions:
        return {}, 0
    seal = subledger_posting_seal
    rows = session.execute(
        select(seal.c.book_code, seal.c.subledger_posting_id, seal.c.chain_seq, func.count())
        .select_from(
            seal.join(
                subledger_line, subledger_line.c.subledger_posting_id == seal.c.subledger_posting_id
            )
        )
        .where(
            subledger_line.c.contract_id == contract_id,
            or_(
                *(
                    and_(seal.c.book_code == book, seal.c.chain_seq <= int(position))
                    for book, position in sorted(positions.items())
                )
            ),
        )
        .group_by(seal.c.book_code, seal.c.subledger_posting_id, seal.c.chain_seq)
        .order_by(seal.c.book_code, seal.c.chain_seq)
    ).all()
    found: dict[str, list[UUID]] = {}
    lines = 0
    for book, posting_id, _seq, count in rows:
        found.setdefault(_book(book), []).append(UUID(str(posting_id)))
        lines += int(count)
    return {book: tuple(ids) for book, ids in found.items()}, lines


def contract_void_content(session: Session, subject_id: UUID) -> Mapping[str, Any]:
    """The contract a void request approves (BUILD_SPEC CTR-11): the activation content members
    plus the command, so the two subjects of one contract never share a content hash; an appended
    event raises the head and makes the request stale (DG-KRN-APR-05; REQ-PLT-014).

    D-98 92 / 99b: the content also carries the posted-state basis the void reverses — the
    contract's subledger line count, latest posting time and per-book chain position
    (``PostedBasis.members``) — so a computation that posts between submission and decision
    changes the hash and ``decide`` voids the pending request as ``STALE_SUBJECT`` (409
    ``stale-approval``); the void is resubmitted under the route its posted state now needs.
    """
    return {
        **contract_activation_content(session, subject_id),
        "command": "request-void",
        **posted_basis(session, subject_id).members(),
    }


def contract_activation_total(session: Session, subject_id: UUID) -> tuple[Decimal, str, str]:
    """The absolute consideration of the latest booking that no void names, the transaction currency
    and the contracting entity's functional currency."""
    row = session.execute(
        select(contract.c.transaction_currency, legal_entity.c.functional_currency)
        .select_from(
            contract.join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == contract.c.tenant_id,
                    legal_entity.c.id == contract.c.contracting_entity_id,
                ),
            )
        )
        .where(contract.c.id == subject_id)
    ).one_or_none()
    if row is None:
        raise SubjectNotVisible(f"contract {subject_id} is not visible")
    events = session.execute(
        select(
            contract_event.c.id,
            contract_event.c.event_type,
            contract_event.c.payload,
            contract_event.c.supersedes_event_id,
        )
        .where(contract_event.c.contract_id == subject_id)
        .order_by(contract_event.c.stream_version)
    ).all()
    voided = {item.supersedes_event_id for item in events if item.supersedes_event_id is not None}
    bookings = [
        item
        for item in events
        if str(getattr(item.event_type, "value", item.event_type))
        == ContractEventType.CONTRACT_BOOKED.value
        and item.id not in voided
    ]
    total = Decimal(0)
    for line in (bookings[-1].payload or {}).get("lines") or () if bookings else ():
        price = line.get("total_price") or {}
        total += Decimal(str(price.get("amount", "0")))
    return (
        abs(total),
        str(row.transaction_currency).strip(),
        str(row.functional_currency).strip(),
    )


# Item ACT-FLAGS-1 (04 T-PLT-17, §16.10 rev 1.287): the ``amount_functional`` of an activation or
# a void request is the consideration CONVERTED to the entity's functional currency, so it is
# stated by the domain module that reads the rates in force and registered with the subject's
# lifecycle (``SubjectLifecycle.amount``; ``domain.contracts.activation.activation_amount`` and
# ``booked_amount``). Until rev 1.287 a function here answered None whenever the two currencies
# differed.


PRODUCT_OBJECT: Final = "product"
PRINCIPAL_AGENT_CHANGE_ACTION: Final = "product.principal_agent_change"
POLICY_VALUES_CHANGE_ACTION: Final = "product.policy_values_change"
POLICY_VALUES: Final = "policy_values"  # the member that makes a proposal a policy-values proposal
PRODUCT_LINK: Final = "/settings/products/{product_id}"  # SCREENS RT-83


def principal_agent_proposal(
    *, product_id: UUID, product_code: str, principal_agent: str, rationale: str
) -> dict[str, Any]:
    """The ``after`` member of a ``PRINCIPAL_AGENT_CHANGE`` request: the proposed conclusion."""
    return {
        "object_type": PRODUCT_OBJECT,
        "product_id": str(product_id),
        "product_code": product_code,
        "principal_agent": principal_agent,
        "rationale": rationale,
    }


def policy_values_proposal(
    *, product_id: UUID, product_code: str, policy_values: Mapping[str, Any], rationale: str
) -> dict[str, Any]:
    """The ``after`` member of a ``PRINCIPAL_AGENT_CHANGE`` request that proposes the product's
    level-P values: the whole proposed map (04 API-R-23 rev 1.110)."""
    return {
        "object_type": PRODUCT_OBJECT,
        "product_id": str(product_id),
        "product_code": product_code,
        POLICY_VALUES: dict(sorted(policy_values.items())),
        "rationale": rationale,
    }


def principal_agent_content(session: Session, proposal: Mapping[str, Any]) -> dict[str, Any]:
    """The proposal with the state it changes: whether the product exists and its current
    conclusion — and, for a policy-values proposal, its current level-P values — so an approval
    after another change is stale (DG-KRN-APR-05; 04 §16.10 rev 1.110)."""
    current = session.execute(
        select(product.c.principal_agent, product.c.policy_values).where(
            product.c.id == UUID(str(proposal["product_id"]))
        )
    ).one_or_none()
    base: dict[str, Any] = {
        "product_exists": current is not None,
        "principal_agent": None if current is None else _text(current.principal_agent),
    }
    if POLICY_VALUES in proposal:
        stored = None if current is None else current.policy_values
        base[POLICY_VALUES] = None if stored is None else dict(sorted(stored.items()))
    return {"proposal": dict(proposal), "base": base}


def _apply_policy_values_change(
    uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID, proposal: Mapping[str, Any]
) -> None:
    """Store the approved level-P values on the product (REQ-POL-003; CTL-031). Prospective by
    construction: a contract past DRAFT reads its pinned product (04 T-CON-07
    ``pinned_refs.products``), so only contracts that leave DRAFT later take the new values."""
    session = uow.session
    current = session.execute(
        select(product.c.policy_values, product.c.row_version)
        .where(product.c.id == subject_id)
        .with_for_update()
    ).one_or_none()
    if current is None:
        raise LookupError(f"product {subject_id} of approval request {approval_request_id} is gone")
    proposed = dict(proposal[POLICY_VALUES])
    stored = dict(current.policy_values or {})
    if proposed == stored:
        return
    principal = uow.principal
    session.execute(
        update(product)
        .where(product.c.id == subject_id)
        .values(
            policy_values=proposed,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    uow.audit(
        action=POLICY_VALUES_CHANGE_ACTION,
        object_type=PRODUCT_OBJECT,
        object_id=subject_id,
        object_version=str(int(current.row_version) + 1),
        before={POLICY_VALUES: stored},
        after={POLICY_VALUES: proposed},
        approval_request_id=approval_request_id,
        detail={"rationale": proposal.get("rationale")},
    )


def _apply_principal_agent_change(
    uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID
) -> None:
    """Set the approved conclusion on the product, prospectively (REQ-REF-012; CTL-031); a
    policy-values proposal stores its map instead (``_apply_policy_values_change``)."""
    proposal = preview.request_proposal(uow, approval_request_id)
    if POLICY_VALUES in proposal:
        _apply_policy_values_change(uow, subject_id, approval_request_id, proposal)
        return
    session = uow.session
    current = session.execute(
        select(product.c.principal_agent, product.c.row_version)
        .where(product.c.id == subject_id)
        .with_for_update()
    ).one_or_none()
    if current is None:
        raise LookupError(f"product {subject_id} of approval request {approval_request_id} is gone")
    proposed = str(proposal["principal_agent"])
    if proposed == str(current.principal_agent):
        return
    principal = uow.principal
    session.execute(
        update(product)
        .where(product.c.id == subject_id)
        .values(
            principal_agent=proposed,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    uow.audit(
        action=PRINCIPAL_AGENT_CHANGE_ACTION,
        object_type=PRODUCT_OBJECT,
        object_id=subject_id,
        object_version=str(int(current.row_version) + 1),
        before={"principal_agent": str(current.principal_agent)},
        after={"principal_agent": proposed},
        approval_request_id=approval_request_id,
        detail={"rationale": proposal.get("rationale")},
    )


FX_RATE_SET_VERSION_OBJECT: Final = "fx_rate_set_version"
FX_RATE_SET_VERSION_APPROVE: Final = "fx_rate_set_version.approve"
FX_RATE_SET_VERSION_REJECT: Final = "fx_rate_set_version.reject"
FX_RATE_SET_VERSION_WITHDRAW: Final = "fx_rate_set_version.withdraw"
FX_RATE_SET_VERSION_NOT_SUBMITTED: Final = (
    "Only a submitted version of an FX rate set can be approved."
)
FX_RATE_PLACES: Final = 12  # TY-03 erev.fx_rate_value NUMERIC(28,12)


def fx_rate_set_version_content(session: Session, subject_id: UUID) -> dict[str, Any]:
    """The hashed content of an FX rate set version: its set, number, coverage and every rate in
    key order, derived inverses included (04 T-REF-10 to T-REF-12). Lifecycle columns and
    ``rate_count`` are left out, so the hash of a SUBMITTED version is the hash ``decide``
    recomputes."""
    version = (
        session.execute(
            select(
                fx_rate_set_version.c.version_no,
                fx_rate_set_version.c.coverage_from,
                fx_rate_set_version.c.coverage_to,
                fx_rate_set.c.code,
                fx_rate_set.c.rate_type,
                fx_rate_set.c.source,
            )
            .select_from(
                fx_rate_set_version.join(
                    fx_rate_set,
                    and_(
                        fx_rate_set.c.tenant_id == fx_rate_set_version.c.tenant_id,
                        fx_rate_set.c.id == fx_rate_set_version.c.fx_rate_set_id,
                    ),
                )
            )
            .where(fx_rate_set_version.c.id == subject_id)
        )
        .mappings()
        .one_or_none()
    )
    if version is None:
        raise SubjectNotVisible(f"fx_rate_set_version {subject_id} is not visible")
    rates = session.execute(
        select(
            fx_rate.c.base_currency,
            fx_rate.c.quote_currency,
            fx_rate.c.effective_date,
            fx_rate.c.period_id,
            fx_rate.c.rate,
            fx_rate.c.is_derived,
        )
        .where(fx_rate.c.fx_rate_set_version_id == subject_id)
        .order_by(fx_rate.c.effective_date, fx_rate.c.base_currency, fx_rate.c.quote_currency)
    ).mappings()
    quantum = Decimal(1).scaleb(-FX_RATE_PLACES)
    return {
        "fx_rate_set": {
            "code": str(version["code"]),
            "rate_type": str(version["rate_type"]),
            "source": str(version["source"]),
        },
        "version_no": int(version["version_no"]),
        "coverage_from": version["coverage_from"].isoformat(),
        "coverage_to": version["coverage_to"].isoformat(),
        "rates": [
            {
                "base_currency": str(row["base_currency"]),
                "quote_currency": str(row["quote_currency"]),
                "effective_date": row["effective_date"].isoformat(),
                "period_id": _text(row["period_id"]),
                "rate": format(Decimal(row["rate"]).quantize(quantum), "f"),
                "is_derived": bool(row["is_derived"]),
            }
            for row in rates
        ],
    }


def rule_set_version_content(session: Session, version_id: UUID) -> dict[str, Any]:
    """The hashed content of a rule set version: its set code, kind, number, effective date and
    rules in ``rule_key`` order (04 T-REF-24 to T-REF-26; BUILD_SPEC RFD-5)."""
    version = session.execute(
        select(
            rule_set_version.c.rule_set_id,
            rule_set_version.c.kind,
            rule_set_version.c.version_no,
            rule_set_version.c.effective_from,
        ).where(rule_set_version.c.id == version_id)
    ).one_or_none()
    if version is None:
        raise SubjectNotVisible(f"rule set version {version_id} is not visible")
    code = session.execute(
        select(rule_set.c.code).where(rule_set.c.id == version.rule_set_id)
    ).scalar_one()
    rules = session.execute(
        select(
            rule.c.rule_key,
            rule.c.priority,
            rule.c.specificity,
            rule.c.conditions,
            rule.c.outputs,
            rule.c.description,
        )
        .where(rule.c.rule_set_version_id == version_id)
        .order_by(rule.c.rule_key)
    ).all()
    return {
        "rule_set_code": str(code),
        "kind": str(version.kind),
        "version_no": int(version.version_no),
        "effective_from": version.effective_from,
        "rules": [
            {
                "rule_key": str(row.rule_key),
                "priority": int(row.priority),
                "specificity": int(row.specificity),
                "conditions": row.conditions,
                "outputs": row.outputs,
                "description": row.description,
            }
            for row in rules
        ],
    }


POB_TEMPLATE_OUTPUT_COLUMNS: Final = (
    "obligation_kind",
    "distinctness",
    "series_increment_unit",
    "satisfaction_pattern",
    "over_time_criterion",
    "recognition_method",
    "ratable_convention",
    "start_date_rule",
    "end_date_rule",
    "term_months",
    "principal_agent",
    "warranty_type",
    "licence_nature",
    "sfc_assessment_required",
    "revenue_category",
    "disaggregation",
    "account_role_overrides",
    "stratification_label",
    "is_excluded_from_netting_attribution",
    "policy_values",
)


def pob_template_version_content(session: Session, version_id: UUID) -> dict[str, Any]:
    """The hashed content of an obligation template version: its template code, number, effective
    date and every T-REF-23 output (04 T-REF-22, T-REF-23; BUILD_SPEC RFD-10). Test cases and
    lifecycle columns are left out, so the hash of a SUBMITTED version is the hash ``decide``
    recomputes."""
    version = (
        session.execute(
            select(
                pob_template.c.code,
                pob_template_version.c.version_no,
                pob_template_version.c.effective_from,
                *(pob_template_version.c[name] for name in POB_TEMPLATE_OUTPUT_COLUMNS),
            )
            .select_from(
                pob_template_version.join(
                    pob_template,
                    and_(
                        pob_template.c.tenant_id == pob_template_version.c.tenant_id,
                        pob_template.c.id == pob_template_version.c.pob_template_id,
                    ),
                )
            )
            .where(pob_template_version.c.id == version_id)
        )
        .mappings()
        .one_or_none()
    )
    if version is None:
        raise SubjectNotVisible(f"obligation template version {version_id} is not visible")
    outputs: dict[str, Any] = {}
    for name in POB_TEMPLATE_OUTPUT_COLUMNS:
        value = version[name]
        outputs[name] = dict(sorted(value.items())) if isinstance(value, Mapping) else value
    return {
        "template_code": str(version["code"]),
        "version_no": int(version["version_no"]),
        "effective_from": version["effective_from"],
        "outputs": outputs,
    }


def registry_version_content(session: Session, version_id: UUID) -> dict[str, Any]:
    """The hashed content of a registry version (04 T-PLT-32 "Whole value set", rev 1.183;
    supervisor ruling R-117 (b); BUILD_SPEC RFD-11): its category, scope key, number, effective
    date and preset, the WHOLE value set in code order, the predecessor it stands on and the
    difference to it by code — ``registry.versions.whole_content``. The test evidence, the
    simulation report and the lifecycle columns are left out, and a DRAFT or TESTED version
    answers the set the server stores at the submit, so the hash its tests recorded is the hash of
    the SUBMITTED version and the hash ``decide`` recomputes; a predecessor that changes after
    the submit changes the content, which makes the request stale."""
    content = registry_versions.whole_content(session, version_id)
    if content is None:
        raise SubjectNotVisible(f"registry version {version_id} is not visible")
    return content


def registry_version_entities(session: Session, version_id: UUID) -> SubjectEntities:
    """The entities a ``REGISTRY_VERSION`` request is bound to (04 §16.10 rev 1.309; PRD
    BR-UX-06 rev 1.203; R-25; item POLICY-TENANT-SCOPE-ALL-ENTITIES-1): the entity of an
    entity-scope version (T-PLT-32 ``entity_id``), and EVERY entity for a tenant- or book-scope
    version. Such a version is the workspace's: a tenant version's values answer for every
    entity that states none of its own, and a book version's for every entity that keeps the
    book, ahead of the entity's own (``registry.resolve`` reads B before E), so its request
    is listed for, read and decided by a holder of ``config.approve`` for all entities, and
    submitted by a preparer whose own scope covers them all. Until rev 1.309 it was a
    tenant-level subject that any holder decided — measured: an accountant and a Controller
    of one entity published a version for the workspace. A version that names no entity is
    never taken for one of a single entity: what is not an entity version spans every
    entity."""
    row = session.execute(
        select(registry_version.c.scope, registry_version.c.entity_id).where(
            registry_version.c.id == version_id
        )
    ).one_or_none()
    if row is None:
        raise Problem("not-found")
    if str(row.scope) == RegistryScope.ENTITY.value and row.entity_id is not None:
        return SubjectEntities(frozenset({UUID(str(row.entity_id))}))
    return ALL_ENTITIES


def account_mapping_version_entities(session: Session, version_id: UUID) -> SubjectEntities:
    """The legal entities an ``ACCOUNT_MAPPING_VERSION`` request is bound to (R-41 (4); supervisor
    ruling R-64 (2); 04 §16.10 rev 1.104): the entities its rules name (T-REF-15 ``entity_id``)
    AND the entities named by the rules of the version its approval ends — the PUBLISHED version
    in force at its ``effective_from``, which publication supersedes or closes at that instant
    (``reference.mapping.publish``). A superseding version binds what it ends: dropping an
    entity's rules is that entity's change, not tenant configuration. A rule without an entity is
    tenant configuration; a version that names none and ends none that does is a tenant-level
    subject. A version without an effective date ends nothing: publication refuses it, so its
    approval puts nothing in force. The rules are part of the hashed content, so a rule added
    after submission voids the request as stale, and another version published in between
    changes the set the decision compares (``engine.current_entities``)."""
    version = account_mapping_version
    found = session.execute(
        select(version.c.id, version.c.effective_from).where(version.c.id == version_id)
    ).one_or_none()
    if found is None:
        raise Problem("not-found")
    at = found.effective_from
    named = account_mapping_rule.c.account_mapping_version_id == version_id
    if at is not None:
        # PUBLISHED ranges never overlap (DB-04): at most one version is in force at that instant.
        ended = select(version.c.id).where(
            version.c.id != version_id,
            version.c.status == "PUBLISHED",
            or_(version.c.effective_from.is_(None), version.c.effective_from <= at),
            or_(version.c.effective_to.is_(None), version.c.effective_to > at),
        )
        named = or_(named, account_mapping_rule.c.account_mapping_version_id.in_(ended))
    ids = session.scalars(
        select(account_mapping_rule.c.entity_id)
        .where(named, account_mapping_rule.c.entity_id.is_not(None))
        .distinct()
    ).all()
    return SubjectEntities(frozenset(UUID(str(value)) for value in ids))


def mapping_profile_version_content(session: Session, version_id: UUID) -> dict[str, Any]:
    """The hashed content of an import mapping profile version: its code, name, template, number,
    effective date and mappings (04 T-IMP-06; BUILD_SPEC DIN-10). Lifecycle columns are left out,
    so the hash of a SUBMITTED version is the hash ``decide`` recomputes."""
    row = session.execute(
        select(
            import_mapping_profile.c.code,
            import_mapping_profile.c.name,
            import_mapping_profile.c.template_code,
            import_mapping_profile.c.version_no,
            import_mapping_profile.c.effective_from,
            import_mapping_profile.c.mappings,
        ).where(import_mapping_profile.c.id == version_id)
    ).one_or_none()
    if row is None:
        raise SubjectNotVisible(f"mapping profile version {version_id} is not visible")
    effective_from: datetime | None = row.effective_from
    return {
        "code": str(row.code),
        "name": str(row.name),
        "template_code": str(row.template_code),
        "version_no": int(row.version_no),
        "effective_from": None if effective_from is None else effective_from.isoformat(),
        "mappings": dict(row.mappings or {}),
    }


EXCEPTION_LINK: Final = "/data/exceptions/{item_id}"  # SCREENS SCR-IA-06 NTF-11
EXCEPTION_OPEN: Final = ("OPEN", "IN_PROGRESS")  # E-44 statuses a waiver can clear


def _literal(value: Any) -> str | None:
    return None if value is None else str(getattr(value, "value", value))


def _exception_row(session: Session, item_id: UUID) -> Mapping[str, Any]:
    row = (
        session.execute(select(exception_item).where(exception_item.c.id == item_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return dict(row)


CHECKLIST_ITEM_TABLE: Final = "close_checklist_item"  # BS4-D-07: EXCEPTION_WAIVER covers it
CHECKLIST_WAIVER_BASIS: Final = "waiver_basis"
CHECKLIST_WAIVABLE: Final = ("NOT_STARTED", "IN_PROGRESS", "FAILED")  # E-60 not cleared


def checklist_waiver_row(session: Session, item_id: UUID) -> Mapping[str, Any] | None:
    """The T-CLS-03 item a checklist waiver names with its template, or None when ``item_id`` is
    not a checklist item (BUILD_SPEC BS4-D-07, CLO-4)."""
    row = (
        session.execute(
            select(
                close_checklist_item.c.tenant_id,
                close_checklist_item.c.id,
                close_checklist_item.c.entity_id,
                close_checklist_item.c.book_code,
                close_checklist_item.c.period_id,
                close_checklist_item.c.status,
                close_checklist_item.c.result,
                close_checklist_item.c.owner_membership_id,
                close_checklist_template.c.code,
                close_checklist_template.c.gate_kind,
                close_checklist_template.c.gate_check_code,
            )
            .join(
                close_checklist_template,
                and_(
                    close_checklist_template.c.tenant_id == close_checklist_item.c.tenant_id,
                    close_checklist_template.c.id
                    == close_checklist_item.c.close_checklist_template_id,
                ),
            )
            .where(close_checklist_item.c.id == item_id)
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else dict(row)


def is_checklist_item(session: Session, item_id: UUID) -> bool:
    """Whether an ``EXCEPTION_WAIVER`` subject is a checklist item (BS4-D-07)."""
    return checklist_waiver_row(session, item_id) is not None


def _membership_user(session: Session, tenant_id: Any, membership_id: Any) -> frozenset[UUID]:
    if membership_id is None:
        return frozenset()
    user_id = session.execute(
        select(tenant_membership.c.user_id).where(
            tenant_membership.c.tenant_id == tenant_id,
            tenant_membership.c.id == membership_id,
        )
    ).scalar_one_or_none()
    return frozenset() if user_id is None else frozenset({UUID(str(user_id))})


def checklist_waiver_basis(result: Mapping[str, Any], gate_check_code: Any) -> Mapping[str, Any]:
    """The submitted approvals-gate scope; other gates retain their current-result basis.

    The close approval hook verifies that the current pending population is a subset before
    applying this frozen basis. Completed requests need not invalidate the original review.
    """
    if gate_check_code == "APPROVALS_CLEARED" and CHECKLIST_WAIVER_BASIS in result:
        return dict(result[CHECKLIST_WAIVER_BASIS])
    return result


def exception_waiver_content(session: Session, item_id: UUID) -> dict[str, Any]:
    """``EXCEPTION_WAIVER`` hashes what a waiver accepts: the item's number, source, code, severity,
    disposition, message, key and whether it is still open. A resolution or dismissal therefore
    voids a pending waiver, while an owner change does not (BUILD_SPEC DIN-11). A checklist item
    hashes its template code and kind, gate check code, entity, book, period and whether it is
    still not cleared, so a gate that passes voids a pending waiver (BS4-D-07) — and the count
    and the sentence its gate stored (04 T-CLS-03 rev 1.305; item CLO-WAIVER-COVERS-LATER-1): a
    waiver also binds the stored member identities, so a replacement at the same count makes
    the request stale. The close hook refreshes this basis at the decision. For the approvals
    gate alone, completed requests may leave the submitted population; new pending requests
    still require a fresh review. A manual task stores no result and hashes neither."""
    checklist = checklist_waiver_row(session, item_id)
    if checklist is not None:
        stored = checklist_waiver_basis(checklist["result"] or {}, checklist["gate_check_code"])
        return {
            "subject_table": CHECKLIST_ITEM_TABLE,
            "code": str(checklist["code"]),
            "gate_kind": _literal(checklist["gate_kind"]),
            "gate_check_code": checklist["gate_check_code"],
            "entity_id": str(checklist["entity_id"]),
            "book_code": _literal(checklist["book_code"]),
            "period_id": str(checklist["period_id"]),
            "open": _literal(checklist["status"]) in CHECKLIST_WAIVABLE,
            "count": stored.get("count"),
            "detail": stored.get("detail"),
            **(
                {"members": stored.get("members")}
                if _literal(checklist["gate_kind"]) == "AUTOMATIC"
                else {}
            ),
        }
    row = _exception_row(session, item_id)
    return {
        "exception_no": str(row["exception_no"]),
        "source": _literal(row["source"]),
        "code": str(row["code"]),
        "severity": _literal(row["severity"]),
        "disposition": _literal(row["disposition"]),
        "message": str(row["message"]),
        "business_key": row["business_key"],
        "open": _literal(row["status"]) in EXCEPTION_OPEN,
    }


def exception_waiver_entities(session: Session, item_id: UUID) -> SubjectEntities:
    """The legal entities an ``EXCEPTION_WAIVER`` request is bound to, which scope who reads the
    request and who decides its step (R-25; D-100 supersedes [J] L7-2-Q-7; 04 §16.10 rev 1.218,
    item EXC-IMPORT-SCOPE-1): a checklist item's entity (T-CLS-03 ``entity_id``); for an
    exception item, what the queue's own module states through the registered lifecycle
    (``imports.exceptions.waiver_entities``; the kernel names no column of an upload,
    DG-ARC-01) — the item's entity, or for an item that names none the entities of everything
    it is about: the contract it names, the members of its group, the entities its upload names
    (every entity for an upload that names none or is not resolved).

    Until this item an exception item that named no entity and no contract was a tenant-level
    subject: any holder of ``exception.waive`` read and decided the waiver of a finding of an
    import he could not read, or of the quarantine of a group of another entity's contracts.
    ``LookupError`` while the queue's module registered no entity source: the kernel never
    guesses the entities of an item (XR-12)."""
    checklist = checklist_waiver_row(session, item_id)
    if checklist is not None:
        return SubjectEntities(frozenset({UUID(str(checklist["entity_id"]))}))
    lifecycle = LIFECYCLES.get(ApprovalSubjectType.EXCEPTION_WAIVER)
    if lifecycle is None or lifecycle.entities is None:
        raise LookupError("approval subject EXCEPTION_WAIVER has no registered entity source")
    return lifecycle.entities(session, item_id)


def exception_waiver_owner(session: Session, item_id: UUID) -> frozenset[UUID]:
    """PRD §2.5 routing row ``EXCEPTION_WAIVER``: the item owner may not approve its waiver."""
    checklist = checklist_waiver_row(session, item_id)
    if checklist is not None:
        return _membership_user(session, checklist["tenant_id"], checklist["owner_membership_id"])
    row = _exception_row(session, item_id)
    return _membership_user(session, row["tenant_id"], row["owner_membership_id"])


def account_mapping_version_content(session: Session, version_id: UUID) -> dict[str, Any]:
    """The hashed content of an account mapping version: its name, number, effective date and every
    rule with its GL account code, in key order (04 T-REF-14, T-REF-15; BUILD_SPEC RFD-7). Lifecycle
    columns are left out, so the hash of a SUBMITTED version is the hash ``decide`` recomputes."""
    version = session.execute(
        select(
            account_mapping_version.c.name,
            account_mapping_version.c.version_no,
            account_mapping_version.c.effective_from,
        ).where(account_mapping_version.c.id == version_id)
    ).one_or_none()
    if version is None:
        raise SubjectNotVisible(f"account mapping version {version_id} is not visible")
    rows = session.execute(
        select(
            account_mapping_rule.c.account_role,
            account_mapping_rule.c.clearing_purpose,
            account_mapping_rule.c.entity_id,
            account_mapping_rule.c.book_code,
            account_mapping_rule.c.product_id,
            account_mapping_rule.c.revenue_category,
            account_mapping_rule.c.gl_account_id,
            gl_account.c.code.label("gl_account_code"),
            account_mapping_rule.c.default_dimensions,
            account_mapping_rule.c.priority,
            account_mapping_rule.c.specificity,
        )
        .select_from(
            account_mapping_rule.join(
                gl_account,
                and_(
                    gl_account.c.tenant_id == account_mapping_rule.c.tenant_id,
                    gl_account.c.id == account_mapping_rule.c.gl_account_id,
                ),
            )
        )
        .where(account_mapping_rule.c.account_mapping_version_id == version_id)
    ).mappings()

    def text_of(value: Any) -> str | None:
        return None if value is None else str(value)

    rules = [
        {
            "account_role": str(row["account_role"]),
            "clearing_purpose": text_of(row["clearing_purpose"]),
            "entity_id": text_of(row["entity_id"]),
            "book_code": text_of(row["book_code"]),
            "product_id": text_of(row["product_id"]),
            "revenue_category": row["revenue_category"],
            "gl_account_id": str(row["gl_account_id"]),
            "gl_account_code": str(row["gl_account_code"]),
            "default_dimensions": dict(row["default_dimensions"]),
            "priority": int(row["priority"]),
            "specificity": int(row["specificity"]),
        }
        for row in rows
    ]
    rules.sort(
        key=lambda item: (
            tuple(
                "" if item[name] is None else str(item[name])
                for name in (
                    "account_role",
                    "clearing_purpose",
                    "entity_id",
                    "book_code",
                    "product_id",
                    "revenue_category",
                    "priority",
                    "gl_account_code",
                )
            )
            + (json.dumps(item["default_dimensions"], sort_keys=True),)
        )
    )
    return {
        "name": str(version.name),
        "version_no": int(version.version_no),
        "effective_from": version.effective_from,
        "rules": rules,
    }


def fx_rate_set_version_uploader(session: Session, subject_id: UUID) -> frozenset[UUID]:
    """The person whose file a rate set version came from (04 T-REF-11 ``import_upload_id``;
    supervisor ruling R-98; REQ-PLT-011). The commit of an ``fx_rates`` import creates the version
    and submits it as SYSTEM on behalf of its uploader, so the request names no preparer; the
    uploader wrote its rates all the same and may not decide it, in person or as the delegator of
    whoever decides. Direct-entry creators and successful editors are excluded as well. API clients
    are not human deciders."""
    row = session.execute(
        select(import_upload.c.created_by, import_upload.c.created_by_kind)
        .select_from(
            fx_rate_set_version.join(
                import_upload,
                and_(
                    import_upload.c.tenant_id == fx_rate_set_version.c.tenant_id,
                    import_upload.c.id == fx_rate_set_version.c.import_upload_id,
                ),
            )
        )
        .where(fx_rate_set_version.c.id == subject_id)
    ).one_or_none()
    authors = draft_authors(fx_rate_set_version, edit_actions=("fx_rate_set_version.update",))(
        session, subject_id
    )
    if row is None or row.created_by is None:
        return authors
    kind = str(getattr(row.created_by_kind, "value", row.created_by_kind))
    return authors | (frozenset({UUID(str(row.created_by))}) if kind == "USER" else frozenset())


# What the approval of a rate set version means for the periods already closed is the close
# domain's to say (item CLO-RATE-AFTER-RUN-1; 04 T-REF-11 "A rate changed after a lock", rev
# 1.291; ``domain.close.rate_changes``). The reference commands register it when they load — the
# module every submission of a version goes through (DG-LAY-03: the kernel imports no domain) —
# and it runs once the version is APPROVED, in the decision's transaction.
type FxRateVersionApproved = Callable[[UnitOfWork, UUID, UUID], object]
FX_RATE_VERSION_APPROVED: Final[list[FxRateVersionApproved]] = []


def register_fx_rate_version_approved(hook: FxRateVersionApproved) -> None:
    """Register what follows the approval of an FX rate set version; registering a hook again
    changes nothing."""
    if hook not in FX_RATE_VERSION_APPROVED:
        FX_RATE_VERSION_APPROVED.append(hook)


def _approve_fx_rate_set_version(
    uow: UnitOfWork, version_id: UUID, approval_request_id: UUID
) -> None:
    """SUBMITTED → APPROVED, the effective state of an FX rate set version (04 E-12, T-REF-11).

    Nothing is superseded: a rate resolves from the highest APPROVED version whose coverage contains
    its date. A version that is no longer SUBMITTED raises 409 ``invalid-transition``, which rolls
    the decision back. The hooks of ``FX_RATE_VERSION_APPROVED`` then run on the approved version;
    ``LookupError`` rolls the decision back while no domain module registered one (XR-12): a
    version that changes a rate of a closed period is never in force without its finding.
    """
    session = uow.session
    principal = uow.principal
    hold_fx_publication(session, principal.tenant_id, exclusive=True)
    status = session.execute(
        select(fx_rate_set_version.c.status)
        .where(fx_rate_set_version.c.id == version_id)
        .with_for_update()
    ).scalar_one_or_none()
    if status is None:
        raise LookupError(
            f"fx_rate_set_version {version_id} of approval request {approval_request_id} is gone"
        )
    if status != ConfigStatus.SUBMITTED.value:
        raise Problem("invalid-transition", FX_RATE_SET_VERSION_NOT_SUBMITTED)
    session.execute(
        update(fx_rate_set_version)
        .where(fx_rate_set_version.c.id == version_id)
        .values(
            status=ConfigStatus.APPROVED.value,
            approval_request_id=approval_request_id,
            published_at=uow.now,
            published_by=principal.id,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    uow.audit(
        action=FX_RATE_SET_VERSION_APPROVE,
        object_type=FX_RATE_SET_VERSION_OBJECT,
        object_id=version_id,
        before={
            "status": ConfigStatus.SUBMITTED.value,
            "approval_request_id": None,
            "published_at": None,
            "published_by": None,
        },
        after={
            "status": ConfigStatus.APPROVED.value,
            "approval_request_id": approval_request_id,
            "published_at": uow.now,
            "published_by": principal.id,
        },
        approval_request_id=approval_request_id,
    )
    if not FX_RATE_VERSION_APPROVED:
        raise LookupError("the approval of an FX rate set version has no registered hook")
    for hook in FX_RATE_VERSION_APPROVED:
        hook(uow, version_id, approval_request_id)


def _close_fx_rate_set_version(
    status: ConfigStatus, action: str
) -> Callable[[UnitOfWork, UUID, UUID], None]:
    """``on_rejected`` or ``on_voided`` of ``FX_RATE_SET_VERSION``: a SUBMITTED version takes
    ``status``, then returns to DRAFT for a new edit round (04 E-12; PRD SM-04)."""

    def close(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
        session = uow.session
        found = session.execute(
            select(fx_rate_set_version.c.status)
            .where(fx_rate_set_version.c.id == subject_id)
            .with_for_update()
        ).scalar_one_or_none()
        if found != ConfigStatus.SUBMITTED.value:
            return
        principal = uow.principal
        stamp = {"updated_by": principal.id, "updated_by_kind": principal.kind.value}
        where = fx_rate_set_version.c.id == subject_id
        session.execute(
            update(fx_rate_set_version).where(where).values(status=status.value, **stamp)
        )
        session.execute(
            update(fx_rate_set_version).where(where).values(status=ConfigStatus.DRAFT.value)
        )
        uow.audit(
            action=action,
            object_type=FX_RATE_SET_VERSION_OBJECT,
            object_id=subject_id,
            before={"status": ConfigStatus.SUBMITTED.value},
            after={"status": ConfigStatus.DRAFT.value},
            approval_request_id=approval_request_id,
            detail={
                "lifecycle": [ConfigStatus.SUBMITTED.value, status.value, ConfigStatus.DRAFT.value]
            },
        )

    return close


SSP_METHODOLOGY_CHANGE: Final = "METHODOLOGY_CHANGE"  # 04 T-PLT-17 routing flags
SSP_ABOVE_THRESHOLD: Final = "ABOVE_THRESHOLD"
SSP_SECOND_APPROVER_FLAGS: Final = frozenset({SSP_METHODOLOGY_CHANGE, SSP_ABOVE_THRESHOLD})
_SSP_ENTRY_KEY: Final = (
    "product_code",
    "stratification",
    "region",
    "channel",
    "segment",
    "deal_size_band",
    "term_band",
    "currency",
)
_SSP_ENTRY_ATTRIBUTES: Final = (
    "method",
    "value_basis",
    "unit_list_price",
    "midpoint_discount_ratio",
    "range_ratio",
    "cost_basis",
    "margin_ratio",
    "observable_point",
    "distinctness",
)
_SSP_BAND_VALUES: Final = (
    "band_from",
    "band_to",
    "point_value",
    "low_value",
    "mid_value",
    "high_value",
)
# T-REF-28 scope columns of the book (``domain.ssp.books.SCOPE_MEMBERS``): what an approved
# version's prices are in force for.
_SSP_SCOPE: Final = ("entity_id", "currency", "channel", "segment", "resolution_mode")
_SSP_VERSION_JOIN: Final = ssp_book_version.join(
    ssp_book,
    and_(
        ssp_book.c.tenant_id == ssp_book_version.c.tenant_id,
        ssp_book.c.id == ssp_book_version.c.ssp_book_id,
    ),
)


def _ssp_band_order(band: Mapping[str, Any]) -> tuple[str, bool, Decimal]:
    start = band["band_from"]
    return (str(band["band_dimension"]), start is not None, Decimal(0) if start is None else start)


def _ssp_entry_order(entry: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple("" if entry[name] is None else str(entry[name]) for name in _SSP_ENTRY_KEY)


def ssp_book_version_content(session: Session, version_id: UUID) -> dict[str, Any]:
    """The hashed content of an SSP book version (04 T-REF-28 to T-REF-31, §16.10 rev 1.110;
    REQ-SSP-007; REQ-PLT-014): the book, number, label, effective dates and methodology, every
    entry with its bands in key order, and the book's scope. The approval puts the prices in force
    for that scope, so a scope other than the submitted one makes the request stale."""
    found = (
        session.execute(
            select(
                ssp_book.c.code.label("book_code"),
                ssp_book_version.c.ssp_book_id,
                ssp_book_version.c.version_no,
                ssp_book_version.c.legacy_version_label,
                ssp_book_version.c.effective_from_date,
                ssp_book_version.c.effective_to_date,
                ssp_book_version.c.methodology_label,
                ssp_book_version.c.is_methodology_change,
                *(ssp_book.c[name].label(f"scope_{name}") for name in _SSP_SCOPE),
            )
            .select_from(_SSP_VERSION_JOIN)
            .where(ssp_book_version.c.id == version_id)
        )
        .mappings()
        .one_or_none()
    )
    if found is None:
        raise SubjectNotVisible(f"ssp_book_version {version_id} is not visible")
    version = {str(name): value for name, value in found.items() if not name.startswith("scope_")}
    scope = {name: _text(found[f"scope_{name}"]) for name in _SSP_SCOPE}
    joined = ssp_entry.join(
        product,
        and_(product.c.tenant_id == ssp_entry.c.tenant_id, product.c.id == ssp_entry.c.product_id),
    ).outerjoin(
        gl_account,
        and_(
            gl_account.c.tenant_id == ssp_entry.c.tenant_id,
            gl_account.c.id == ssp_entry.c.revenue_gl_account_id,
        ),
    )
    rows = (
        session.execute(
            select(
                ssp_entry.c.id,
                product.c.code.label("product_code"),
                *(ssp_entry.c[name] for name in _SSP_ENTRY_KEY[1:]),
                *(ssp_entry.c[name] for name in _SSP_ENTRY_ATTRIBUTES),
                gl_account.c.code.label("revenue_account_code"),
            )
            .select_from(joined)
            .where(ssp_entry.c.ssp_book_version_id == version_id)
        )
        .mappings()
        .all()
    )
    bands: dict[UUID, list[dict[str, Any]]] = {}
    if rows:
        statement = select(
            ssp_range.c.ssp_entry_id,
            ssp_range.c.band_dimension,
            *(ssp_range.c[name] for name in _SSP_BAND_VALUES),
        ).where(ssp_range.c.ssp_entry_id.in_([row["id"] for row in rows]))
        for band in session.execute(statement).mappings():
            bands.setdefault(UUID(str(band["ssp_entry_id"])), []).append(
                {
                    "band_dimension": str(band["band_dimension"]),
                    **{name: band[name] for name in _SSP_BAND_VALUES},
                }
            )
    entries = []
    for row in rows:
        entry = {str(name): value for name, value in row.items() if name != "id"}
        entry["ranges"] = sorted(bands.get(UUID(str(row["id"])), []), key=_ssp_band_order)
        entries.append(entry)
    entries.sort(key=_ssp_entry_order)
    return {**version, "scope": scope, "entries": entries}


def ssp_book_version_entity(session: Session, version_id: UUID) -> UUID | None:
    """The scope entity of the version's book, which scopes the request; None for a book of all
    entities, which is tenant configuration. A version the caller cannot read is 404."""
    row = session.execute(
        select(ssp_book.c.entity_id)
        .select_from(_SSP_VERSION_JOIN)
        .where(ssp_book_version.c.id == version_id)
    ).one_or_none()
    if row is None:
        raise Problem("not-found")
    return None if row.entity_id is None else UUID(str(row.entity_id))


@dataclass(frozen=True, slots=True)
class SubjectLifecycle:
    """The callbacks of a subject whose lifecycle a domain module implements, and optionally
    what only that module can state about the subject: its routing flags, the legal entities it
    names, the entities its preparer is held to, the steps its content demands and its own
    check of the people who decide (``IMPORT_COMMIT``: rulings R-29, R-38 (ii), R-41 (5), R-64
    (6), R-87 (1), R-92)."""

    on_approved: Callable[[UnitOfWork, UUID, UUID], None]
    on_rejected: Callable[[UnitOfWork, UUID, UUID], None]
    on_voided: Callable[[UnitOfWork, UUID, UUID], None]
    flags: Callable[[Session, UUID], frozenset[str]] | None = None
    # Item ACT-FLAGS-1: T-PLT-17 ``amount_functional`` with its currency, for a subject whose
    # amount only the domain module can state (a conversion at the rates in force); None states
    # no amount.
    amount: Callable[[Session, UUID], tuple[Decimal, str] | None] | None = None
    entities: Callable[[Session, UUID], SubjectEntities] | None = None
    preparer_entities: Callable[[Session, UUID], SubjectEntities] | None = None
    floor: Callable[[Session, UUID, SubjectEntities, datetime], Sequence[FloorStep]] | None = None
    deciders: (
        Callable[
            [Session, UUID, SubjectEntities, int, Collection[UUID], datetime],
            Mapping[UUID, DeciderRefusal],
        ]
        | None
    ) = None


POLICY_OVERRIDE_OBJECT: Final = "policy_override"
SSP_OVERRIDE_OBJECT: Final = "obligation"


def policy_override_content(session: Session, override_id: UUID) -> dict[str, Any]:
    """What a ``POLICY_OVERRIDE`` approval certifies: the override's scope, key, value, rationale
    and judgement record (04 T-CON-23; BUILD_SPEC CTR-15)."""
    row = (
        session.execute(select(policy_override).where(policy_override.c.id == override_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise SubjectNotVisible(f"policy override {override_id} is not visible")
    return {
        "contract_id": str(row["contract_id"]),
        "obligation_id": _text(row["obligation_id"]),
        "level": _text(row["level"]),
        "policy_key": str(row["policy_key"]),
        "value": row["value"],
        "rationale": str(row["rationale"]),
        "judgement_record_id": _text(row["judgement_record_id"]),
    }


def ssp_override_proposal(
    *,
    obligation_id: UUID,
    contract_id: UUID,
    obligation_key: str,
    ssp_book_version_id: UUID,
    version_label: str | None,
    justification: str,
) -> dict[str, Any]:
    """The ``after`` member of an ``SSP_OVERRIDE`` request: the version the obligation is to be
    priced from and the preparer's justification (04 §16.2 ``request-ssp-override``)."""
    return {
        "object_type": SSP_OVERRIDE_OBJECT,
        "obligation_id": str(obligation_id),
        "contract_id": str(contract_id),
        "obligation_key": obligation_key,
        "ssp_book_version_id": str(ssp_book_version_id),
        "version_label": version_label,
        "justification": justification,
    }


def _versions_of_obligation() -> Any:
    """T-CON-11 joined to the T-CON-08 version each row belongs to."""
    return obligation_version.join(
        contract_version,
        and_(
            contract_version.c.tenant_id == obligation_version.c.tenant_id,
            contract_version.c.id == obligation_version.c.contract_version_id,
        ),
    )


def obligation_latest_computation(session: Session, obligation_id: UUID) -> UUID | None:
    """The computation (T-CON-07) that last held the obligation; None before its first.

    Item MOD-SSP-PIN-CHAIN-1 (supervisor ruling of 2026-10-01 on lane F-RPS-REG's finding S-3):
    ``version_no`` counts within one combination group (04 T-CON-08), so the highest number
    across every group the contract has been in is not the latest version. It is found in two
    steps. (1) The GROUP: that of the obligation's version with the latest ``known_at``. A
    version's ``known_at`` is the record time of the latest event its computation read
    (``computation.persist``), and a computation that holds the obligation read the event that
    began its contract's membership in the group — the booking, or the contract's
    ``COMBINATION_CHANGED`` — and none recorded after that membership ended, so the versions of
    a later membership are all later than those of an earlier one. (2) Within that group, the
    highest number: ``known_at`` alone does not order one group's versions — a group computes
    the events of its present members (``bundles.build``), so once another member has left, the
    next computation reads fewer events and carries an earlier ``known_at`` than the one
    before it."""
    held = obligation_version.c.obligation_id == obligation_id
    group = (
        select(obligation_version.c.combination_group_id)
        .select_from(_versions_of_obligation())
        .where(held)
        .order_by(contract_version.c.known_at.desc(), contract_version.c.version_no.desc())
        .limit(1)
        .scalar_subquery()
    )
    found = session.execute(
        select(contract_version.c.contract_computation_id)
        .select_from(_versions_of_obligation())
        .where(held, obligation_version.c.combination_group_id == group)
        .order_by(contract_version.c.version_no.desc())
        .limit(1)
    ).scalar_one_or_none()
    return None if found is None else UUID(str(found))


def obligation_ssp_pins(session: Session, obligation_id: UUID) -> list[str]:
    """The SSP book versions the obligation is priced from: those of its versions in the latest
    computation that held it (``obligation_latest_computation``) — every book of that
    computation.

    Measured before item MOD-SSP-PIN-CHAIN-1, when the highest ``version_no`` decided: a
    contract computed four times on its own and then combined read the pin of the group it had
    left — an SSP override request showed and stored that pin as its ``before``, the appended
    event recorded it in its ``diff``, and a recomputation of the combined group that changed
    the pin left a pending request fresh. No allocation reads this function: the engine takes
    the pin from the override's event."""
    latest = obligation_latest_computation(session, obligation_id)
    if latest is None:
        return []
    pins = session.execute(
        select(obligation_version.c.ssp_book_version_id)
        .select_from(_versions_of_obligation())
        .where(
            obligation_version.c.obligation_id == obligation_id,
            contract_version.c.contract_computation_id == latest,
        )
    ).scalars()
    return sorted({str(value) for value in pins if value is not None})


def ssp_override_content(session: Session, proposal: Mapping[str, Any]) -> dict[str, Any]:
    """The proposal with the state it changes: whether the obligation exists, the versions it is
    priced from and the proposed version's status, so an approval after a recomputation, or after
    the version left APPROVED, is stale (DG-KRN-APR-05)."""
    obligation_id = UUID(str(proposal["obligation_id"]))
    exists = session.execute(
        select(obligation.c.id).where(obligation.c.id == obligation_id)
    ).first()
    status = session.execute(
        select(ssp_book_version.c.status).where(
            ssp_book_version.c.id == UUID(str(proposal["ssp_book_version_id"]))
        )
    ).scalar_one_or_none()
    return {
        "proposal": dict(proposal),
        "base": {
            "obligation_exists": exists is not None,
            "ssp_book_version_ids": obligation_ssp_pins(session, obligation_id),
            "proposed_version_status": _text(status),
        },
    }


def policy_override_entities(session: Session, override_id: UUID) -> SubjectEntities:
    """The entities of a ``POLICY_OVERRIDE`` request (R-25; D-100 supersedes [J] L4-2-Q-5): the
    group of the override's contract (T-CON-23 ``contract_id``; ``contract_group_entities`` — the
    approval marks the group dirty, RCP-17)."""
    found = session.execute(
        select(policy_override.c.contract_id).where(policy_override.c.id == override_id)
    ).scalar_one_or_none()
    return contract_group_entities(session, [_visible_entity(found)])


def ssp_override_entities(session: Session, obligation_id: UUID) -> SubjectEntities:
    """The entities of an ``SSP_OVERRIDE`` request (R-25; D-100 supersedes [J] L4-2-Q-5): the group
    of the obligation's contract (the subject id is the obligation, T-CON-10;
    ``contract_group_entities`` — the override re-allocates the group)."""
    found = session.execute(
        select(obligation.c.contract_id).where(obligation.c.id == obligation_id)
    ).scalar_one_or_none()
    return contract_group_entities(session, [_visible_entity(found)])


# Lifecycles registered by domain modules at import (DG-LAY-03: the kernel imports no domain).
LIFECYCLES: Final[dict[ApprovalSubjectType, SubjectLifecycle]] = {}


ESTIMATE_VERSION_OBJECT: Final = "estimate_version"
# PRD §2.5 ``ESTIMATE_VERSION`` second-step flag: the absolute P&L impact of the version — the
# catch-up of the submission's dry run — is USD 50,000.00 or more (R-41 (7)).
ESTIMATE_PL_IMPACT_FLAG: Final = "PL_IMPACT_GE_50K"


def _decimal_text(value: Any) -> str | None:
    return None if value is None else format(Decimal(value).normalize(), "f")


def estimate_version_content(session: Session, version_id: UUID) -> dict[str, Any]:
    """What an ``ESTIMATE_VERSION`` approval certifies: the version and its element (04 T-CON-12,
    T-CON-13; BUILD_SPEC CTR-12) and — item EST-PREVIEW-HEAD-PIN-1 (04 §16.10 rev 1.233) — for
    a version of a contract's element the contract's ``{combination_group_id,
    head_stream_version}`` and every member of its group in ascending id order, as a
    ``MODIFICATION``'s content carries them. The request's impact preview is a dry run over the
    stream as it stood at the submission; before, an append or a regroup between the request and
    the decision left the approver deciding on figures the approval no longer posted (measured:
    two versions of one contract pending together, the second approved on a preview of
    120,000.00 while it posted 102,439.03). Now such a decision is stale (STALE_SUBJECT) and the
    version is submitted again with a fresh preview. A portfolio element names no contract and
    pins none."""
    row = (
        session.execute(
            select(estimate_version, estimate.c.contract_id, estimate.c.portfolio_id)
            .add_columns(
                estimate.c.obligation_id.label("element_obligation_id"),
                estimate.c.estimate_kind,
                estimate.c.element_code,
                estimate.c.vc_element_type,
                estimate.c.direction,
                estimate.c.method,
                estimate.c.allocation_target,
                estimate.c.target_obligation_ids,
            )
            .select_from(
                estimate_version.join(
                    estimate,
                    and_(
                        estimate.c.tenant_id == estimate_version.c.tenant_id,
                        estimate.c.id == estimate_version.c.estimate_id,
                    ),
                )
            )
            .where(estimate_version.c.id == version_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise SubjectNotVisible(f"estimate version {version_id} is not visible")

    def text_of(value: Any) -> str | None:
        return None if value is None else str(getattr(value, "value", value))

    pinned: dict[str, Any] = {}
    if row["contract_id"] is not None:
        contract_id = UUID(str(row["contract_id"]))
        (state,) = _member_states(session, [contract_id])
        pinned = {
            "contract": {
                "combination_group_id": state["combination_group_id"],
                "head_stream_version": state["head_stream_version"],
            },
            "members": _member_states(session, _group_member_ids(session, contract_id)),
        }
    return {
        "object_type": ESTIMATE_VERSION_OBJECT,
        "estimate_id": str(row["estimate_id"]),
        "contract_id": text_of(row["contract_id"]),
        "portfolio_id": text_of(row["portfolio_id"]),
        "obligation_id": text_of(row["element_obligation_id"]),
        "estimate_kind": text_of(row["estimate_kind"]),
        "element_code": str(row["element_code"]),
        "vc_element_type": text_of(row["vc_element_type"]),
        "direction": str(row["direction"]),
        "method": text_of(row["method"]),
        "allocation_target": str(row["allocation_target"]),
        "target_obligation_ids": sorted(str(value) for value in row["target_obligation_ids"] or ()),
        "version_no": int(row["version_no"]),
        "effective_date": row["effective_date"].isoformat(),
        "scenarios": row["scenarios"],
        "parameters": row["parameters"],
        "unconstrained_amount": _decimal_text(row["unconstrained_amount"]),
        "most_conservative_amount": _decimal_text(row["most_conservative_amount"]),
        "constrained_amount": _decimal_text(row["constrained_amount"]),
        "rate": _decimal_text(row["rate"]),
        "expected_total_amount": _decimal_text(row["expected_total_amount"]),
        "expected_quantity": _decimal_text(row["expected_quantity"]),
        "amortization_months": row["amortization_months"],
        "currency": None if row["currency"] is None else str(row["currency"]).strip(),
        "constraint_checklist": row["constraint_checklist"],
        "rationale": str(row["rationale"]),
        "judgement_record_id": text_of(row["judgement_record_id"]),
        "supersedes_version_id": text_of(row["supersedes_version_id"]),
        # 04 §16.10 rev 1.210 (item MOD-LINKED-ESTIMATES-1): the modification the version was
        # created inside, when it names one — a version without a link hashes as before.
        **(
            {}
            if row["modification_id"] is None
            else {"modification_id": str(row["modification_id"])}
        ),
        **pinned,
    }


def estimate_version_entities(session: Session, version_id: UUID) -> SubjectEntities:
    """The legal entities an ``ESTIMATE_VERSION`` request is bound to (R-25; D-100 supersedes [J]
    L5-2-Q-4): the group of the element's contract (T-CON-12 ``contract_id``;
    ``contract_group_entities`` — the approval recomputes it). A portfolio-scoped element
    (``portfolio_id``; its versions are built by CTR-13) names contracts of any entity, so it
    spans every entity until that item states its members."""
    row = session.execute(
        select(estimate.c.contract_id)
        .select_from(
            estimate_version.join(
                estimate,
                and_(
                    estimate.c.tenant_id == estimate_version.c.tenant_id,
                    estimate.c.id == estimate_version.c.estimate_id,
                ),
            )
        )
        .where(estimate_version.c.id == version_id)
    ).one_or_none()
    if row is None:
        raise Problem("not-found")
    if row.contract_id is None:
        return ALL_ENTITIES
    return contract_group_entities(session, [UUID(str(row.contract_id))])


JOURNAL_RUN_OBJECT: Final = "journal_run"
JOURNAL_RUN_LINK: Final = "/journals/runs/{run_id}"  # SCREENS_B RT-29


def _run_literal(value: Any) -> str | None:
    return None if value is None else str(getattr(value, "value", value)).strip()


PERIOD_LOCK_OBJECT: Final = "period_state"
PERIOD_LINK: Final = "/close/periods/{state_id}"  # SCREENS_B SF-05 cockpit
LOCK_FROM_STATE: Final[Mapping[str, str]] = {"closing": "LOCK", "closed": "PERMANENT_LOCK"}


def period_lock_content(session: Session, state_id: UUID) -> dict[str, Any]:
    """What a ``PERIOD_LOCK`` approval certifies: the period state's identity, state, version and
    current lock, and the lock kind the state implies (``closing`` → ``LOCK``, ``closed`` →
    ``PERMANENT_LOCK``; BUILD_SPEC CLO-6; 04 T-CLS-04, E-63)."""
    row = (
        session.execute(
            select(
                period_state.c.entity_id,
                period_state.c.book_code,
                period_state.c.period_id,
                period_state.c.state,
                period_state.c.row_version,
                period_state.c.current_lock_id,
            ).where(period_state.c.id == state_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise SubjectNotVisible(f"period state {state_id} is not visible")
    state = str(getattr(row["state"], "value", row["state"]))
    return {
        "object_type": PERIOD_LOCK_OBJECT,
        "period_state_id": str(state_id),
        "entity_id": str(row["entity_id"]),
        "book_code": str(getattr(row["book_code"], "value", row["book_code"])),
        "period_id": str(row["period_id"]),
        "state": state,
        "row_version": int(row["row_version"]),
        "current_lock_id": None if row["current_lock_id"] is None else str(row["current_lock_id"]),
        "lock_kind": LOCK_FROM_STATE.get(state, "LOCK"),
    }


def period_reopen_content(session: Session, state_id: UUID) -> dict[str, Any]:
    """What a ``PERIOD_REOPEN`` approval decides on: the period state's identity, its ``closed``
    state, version and the lock the reopen names as ``previous_lock_id`` (BUILD_SPEC CLO-7; 04
    T-CLS-04 ``REOPEN``; SM-07 ``closed → reopened``)."""
    return {**period_lock_content(session, state_id), "lock_kind": "REOPEN"}


def period_lock_entity(session: Session, state_id: UUID) -> UUID | None:
    """T-PLT-17 ``entity_id`` of a ``PERIOD_LOCK`` or ``PERIOD_REOPEN`` request: the entity of the
    period state (T-REF-06 ``entity_id``)."""
    return _visible_entity(
        session.execute(
            select(period_state.c.entity_id).where(period_state.c.id == state_id)
        ).scalar_one_or_none()
    )


def journal_run_content(session: Session, run_id: UUID) -> dict[str, Any]:
    """What a ``JOURNAL_RUN`` approval certifies: the run's identity, coverage, state and totals,
    and each batch's external id, totals and detail file hash (04 T-SL-06, T-SL-07; BUILD_SPEC
    CLO-11)."""
    row = (
        session.execute(select(journal_run).where(journal_run.c.id == run_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise SubjectNotVisible(f"journal run {run_id} is not visible")
    batches = session.execute(
        select(journal_batch)
        .where(journal_batch.c.journal_run_id == run_id)
        .order_by(journal_batch.c.batch_no, journal_batch.c.chunk_no)
    ).mappings()
    return {
        "object_type": JOURNAL_RUN_OBJECT,
        "run_no": str(row["run_no"]),
        "entity_id": str(row["entity_id"]),
        "book_code": _run_literal(row["book_code"]),
        "period_id": str(row["period_id"]),
        "mode": _run_literal(row["mode"]),
        "delta_book_code": _run_literal(row["delta_book_code"]),
        "grain": _run_literal(row["grain"]),
        "state": _run_literal(row["state"]),
        "cutoff_known_at": row["cutoff_known_at"].isoformat(),
        "coverage": [
            row["from_chain_seq"],
            row["to_chain_seq"],
            row["delta_from_chain_seq"],
            row["delta_to_chain_seq"],
        ],
        "line_count": int(row["line_count"]),
        "total_debit_functional": _decimal_text(row["total_debit_functional"]),
        "total_credit_functional": _decimal_text(row["total_credit_functional"]),
        "batches": [
            {
                "external_id": str(batch["external_id"]),
                "state": _run_literal(batch["state"]),
                "txn_currency": _run_literal(batch["txn_currency"]),
                "line_count": int(batch["line_count"]),
                "total_debit_txn": _decimal_text(batch["total_debit_txn"]),
                "total_credit_txn": _decimal_text(batch["total_credit_txn"]),
                "total_debit_functional": _decimal_text(batch["total_debit_functional"]),
                "total_credit_functional": _decimal_text(batch["total_credit_functional"]),
                "detail_sha256": _run_literal(batch["detail_sha256"]),
            }
            for batch in batches
        ],
    }


def journal_run_entity(session: Session, run_id: UUID) -> UUID | None:
    """T-PLT-17 ``entity_id`` of a ``JOURNAL_RUN`` request (R-25; D-100 supersedes [J] L6-3-Q-9):
    the run's entity (T-SL-06 ``entity_id``)."""
    return _visible_entity(
        session.execute(
            select(journal_run.c.entity_id).where(journal_run.c.id == run_id)
        ).scalar_one_or_none()
    )


# PRD BR-JE-01 copy (ERR-02): the refusal of the run's runner, in person or through a delegate.
JOURNAL_RUNNER_DETAIL: Final = "You calculated this journal run, so another user must approve it."


def journal_run_runner(session: Session, run_id: UUID) -> frozenset[UUID]:
    """PRD BR-JE-01: the user who ran the calculation — the creator of the run's
    ``JOURNAL_RUN_CALCULATE`` job — may not approve the run. ``SubjectSpec.excluded_deciders``
    compares the acting persons of a decision, so the runner is refused in person AND as the
    delegator of whoever decides on the runner's behalf (R-25; REQ-PLT-011 "across UI, API,
    delegation and role switching"), at every step."""
    runner = session.execute(
        select(job.c.created_by)
        .select_from(
            journal_run.join(
                job,
                and_(job.c.tenant_id == journal_run.c.tenant_id, job.c.id == journal_run.c.job_id),
            )
        )
        .where(journal_run.c.id == run_id)
    ).scalar_one_or_none()
    return frozenset() if runner is None else frozenset({UUID(str(runner))})


def register_lifecycle(subject_type: ApprovalSubjectType, lifecycle: SubjectLifecycle) -> None:
    """Register the domain callbacks of ``subject_type``."""
    LIFECYCLES[ApprovalSubjectType(subject_type)] = lifecycle


@dataclass(frozen=True, slots=True)
class CoveredLifecycle:
    """The callbacks of a further table a subject type covers, chosen when ``owns`` answers true for
    the subject id (BUILD_SPEC BS4-D-07: ``EXCEPTION_WAIVER`` covers ``close_checklist_item``)."""

    table: str
    owns: Callable[[Session, UUID], bool]
    lifecycle: SubjectLifecycle
    # [J] D-88 L7-2-Q-7: the subject route of NTF-02 to NTF-04 and API-S-Approval ``subject.href``
    # when the table holds the subject; None when it does not.
    link: Callable[[Session, UUID], str | None]


COVERED_LIFECYCLES: Final[dict[ApprovalSubjectType, dict[str, CoveredLifecycle]]] = {}


def register_covered_lifecycle(
    subject_type: ApprovalSubjectType, covered: CoveredLifecycle
) -> None:
    """Register the callbacks of a further table ``subject_type`` covers."""
    COVERED_LIFECYCLES.setdefault(ApprovalSubjectType(subject_type), {})[covered.table] = covered


def covered_link(
    session: Session, subject_type: ApprovalSubjectType | str, subject_id: UUID
) -> str | None:
    """The link of the covered table that holds the subject, or None when none does; callers then
    use ``SubjectSpec.link_path`` ([J] D-88 L7-2-Q-7)."""
    for covered in COVERED_LIFECYCLES.get(ApprovalSubjectType(subject_type), {}).values():
        link = covered.link(session, subject_id)
        if link is not None:
            return link
    return None


def _registered(
    subject_type: ApprovalSubjectType, callback: Literal["on_approved", "on_rejected", "on_voided"]
) -> Callable[[UnitOfWork, UUID, UUID], None]:
    """A spec callback that runs the registered lifecycle, or the covered table's when that table
    holds the subject; ``LookupError`` rolls the decision back while no domain module registered
    one (XR-12)."""

    def call(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
        for covered in COVERED_LIFECYCLES.get(subject_type, {}).values():
            if covered.owns(uow.session, subject_id):
                chosen: Callable[[UnitOfWork, UUID, UUID], None] = getattr(
                    covered.lifecycle, callback
                )
                chosen(uow, subject_id, approval_request_id)
                return
        lifecycle = LIFECYCLES.get(subject_type)
        if lifecycle is None:
            raise LookupError(f"approval subject {subject_type} has no registered lifecycle")
        handler: Callable[[UnitOfWork, UUID, UUID], None] = getattr(lifecycle, callback)
        handler(uow, subject_id, approval_request_id)

    return call


def _registered_flags(
    subject_type: ApprovalSubjectType,
) -> Callable[[Session, UUID], frozenset[str]]:
    """A spec ``flags`` function that runs the registered lifecycle's; ``LookupError`` while no
    domain module registered one (XR-12)."""

    def call(session: Session, subject_id: UUID) -> frozenset[str]:
        lifecycle = LIFECYCLES.get(subject_type)
        if lifecycle is None:
            raise LookupError(f"approval subject {subject_type} has no registered lifecycle")
        return frozenset() if lifecycle.flags is None else lifecycle.flags(session, subject_id)

    return call


def _registered_amount(
    subject_type: ApprovalSubjectType,
) -> Callable[[Session, UUID], tuple[Decimal, str] | None]:
    """A spec ``amount_functional`` function that runs the registered lifecycle's (item
    ACT-FLAGS-1); no amount where the lifecycle states none, and ``LookupError`` while no domain
    module registered one (XR-12)."""

    def call(session: Session, subject_id: UUID) -> tuple[Decimal, str] | None:
        lifecycle = LIFECYCLES.get(subject_type)
        if lifecycle is None:
            raise LookupError(f"approval subject {subject_type} has no registered lifecycle")
        return None if lifecycle.amount is None else lifecycle.amount(session, subject_id)

    return call


# One entry per built E-08 value; later items register their subjects here.
# --- MODIFICATION (04 T-CON-06, §16.10 rev 1.70; PRD §2.5 routing row MODIFICATION; BUILD_SPEC
# CTR-17; D-98 140) -------------------------------------------------------------------------------

MODIFICATION_OBJECT: Final = "modification"
MODIFICATION_LINK: Final = "/modifications/{modification_id}"  # SCREENS SF-07:detail
# The PRD §2.5 second-step conditions, evaluated by the command at submit from the STORED impact
# preview (D-98 140 Q-5): |catch-up| ≥ USD 50,000.00; |transaction price change| ≥ USD 250,000.00.
MODIFICATION_CATCH_UP_FLAG: Final = "CATCH_UP_GE_50K"
MODIFICATION_TP_CHANGE_FLAG: Final = "TP_CHANGE_GE_250K"
# The authored T-CON-06 members an approver reviews (§16.10 rev 1.70): decision-derived fields
# (status, approval linkage, applied event) are excluded (D-98 101d note).
MODIFICATION_CONTENT_MEMBERS: Final = (
    "modification_no",
    "contract_id",
    "effective_date",
    "kind",
    "template_mode",
    "reference",
    "lines",
    "questionnaire",
    "price_change_amount",
    "price_change_settlement",
    "noncash_consideration",
    "consideration_payable",
    "scope_605_35",
    "currency",
    "proposed_treatments",
    "chosen_treatments",
    "treatment_summary",
    "ssp_basis",
    "rationale",
    "judgement_record_id",
    "impact_preview_sha256",
    "regroup_id",
)


def modification_rows(session: Session, subject_id: UUID) -> list[dict[str, Any]]:
    """The subject row and, for a regroup after posting, the row sharing its ``regroup_id`` — the
    ONE spanning request's pair (D-98 140 Q-4), ordered by contract id; ``LookupError`` when the
    subject is not visible."""
    row = session.execute(select(modification).where(modification.c.id == subject_id)).mappings()
    found = row.one_or_none()
    if found is None:
        raise SubjectNotVisible(f"modification {subject_id} is not visible")
    if found["regroup_id"] is None:
        return [dict(found)]
    pair = (
        session.execute(
            select(modification)
            .where(modification.c.regroup_id == found["regroup_id"])
            .order_by(modification.c.contract_id, modification.c.id)
        )
        .mappings()
        .all()
    )
    return [dict(item) for item in pair]


def _judgement_sha(session: Session, judgement_id: Any) -> str | None:
    if judgement_id is None:
        return None
    found = session.execute(
        select(judgement_record.c.content_sha256).where(judgement_record.c.id == judgement_id)
    ).scalar_one_or_none()
    return None if found is None else str(found)


def _group_member_ids(session: Session, contract_id: UUID) -> list[UUID]:
    group_id = session.execute(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    ).scalar_one_or_none()
    if group_id is None:
        return [contract_id]
    return [
        UUID(str(value))
        for value in session.scalars(
            select(contract.c.id).where(contract.c.combination_group_id == group_id)
        )
    ]


def modification_content(session: Session, subject_id: UUID) -> dict[str, Any]:
    """What a ``MODIFICATION`` approval certifies (04 §16.10 rev 1.70; D-98 140): per row of the
    subject (one, or the regroup pair) the authored T-CON-06 members with the judgement record's
    ``content_sha256`` and the preview hash, the contract's ``{combination_group_id,
    head_stream_version}`` and every member of its group in ascending id order — so an append or a
    regroup between the request and the decision makes the decision stale (STALE_SUBJECT)."""
    items: list[dict[str, Any]] = []
    regroup_id: str | None = None
    for row in modification_rows(session, subject_id):
        contract_id = UUID(str(row["contract_id"]))
        regroup_id = None if row["regroup_id"] is None else str(row["regroup_id"])
        members = _member_states(session, _group_member_ids(session, contract_id))
        (state,) = _member_states(session, [contract_id])
        authored = {name: canonical_value(row.get(name)) for name in MODIFICATION_CONTENT_MEMBERS}
        authored["judgement_content_sha256"] = _judgement_sha(session, row["judgement_record_id"])
        # 04 §16.10 rev 1.210 (item MOD-LINKED-ESTIMATES-1): the ids of the estimate versions
        # created inside the row, ascending — ids, not statuses: the hook reads the statuses when
        # it decides, and an approved version's event already moves the head pinned below. A
        # discarded (VOIDED) version is not listed: it does not count, and this content is the
        # preview's basis too — a stray draft that is discarded restores the preview it made
        # stale. A row without a link hashes as before.
        linked = [
            str(found)
            for found in session.scalars(
                select(estimate_version.c.id)
                .where(
                    estimate_version.c.modification_id == row["id"],
                    estimate_version.c.status != ConfigStatus.VOIDED.value,
                )
                .order_by(estimate_version.c.id)
            )
        ]
        if linked:
            authored["linked_estimate_version_ids"] = linked
        items.append(
            {
                "modification_id": str(row["id"]),
                **authored,
                "contract": {
                    "combination_group_id": state["combination_group_id"],
                    "head_stream_version": state["head_stream_version"],
                },
                "members": members,
            }
        )
    return {"object_type": MODIFICATION_OBJECT, "regroup_id": regroup_id, "modifications": items}


def modification_entities(session: Session, subject_id: UUID) -> SubjectEntities:
    """The legal entities a ``MODIFICATION`` request is bound to (R-25; R-41 (1), (4)): the
    contracting entity of the subject row and, for a regroup after posting, of the row sharing its
    ``regroup_id`` — the ONE spanning request amends both contracts (04 §16.10 rev 1.70) — and the
    contracting entities of every current member of those contracts' combination groups. The
    approval recomputes the whole group and its content hashes every member's state
    (``modification_content``), so the approver reads, and holds the permission for, each of
    them; an approver for the contracting entity alone would hash a group it sees in part and
    void the request. Memberships are read from T-CON-04, which no entity scope hides; a member
    contract the caller cannot read makes the subject span every entity (``ALL_ENTITIES``) rather
    than drop the entity it cannot name. A contract alone in its group names its own entity."""
    try:
        rows = modification_rows(session, subject_id)
    except SubjectNotVisible as error:
        raise Problem("not-found") from error
    return contract_group_entities(session, [UUID(str(row["contract_id"])) for row in rows])


def canonical_value(value: Any) -> Any:
    """JSON-safe copy of a stored member for the content hash (dates, decimals, uuids as text)."""
    if isinstance(value, dict):
        return {str(key): canonical_value(item) for key, item in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [canonical_value(item) for item in value]
    if isinstance(value, str | bool | int | float) or value is None:
        return value
    return str(value)


# --- MANUAL_ADJUSTMENT (04 T-SL-05, T-PLT-17; PRD §2.5 routing rows MANUAL_ADJUSTMENT; BUILD_SPEC
# CLO-12; rulings R-25, R-51) ----------------------------------------------------------------------

MANUAL_ADJUSTMENT_OBJECT: Final = "manual_adjustment"
# 04 T-PLT-17 flag: the request asks to defer a pending adjustment past the period lock; its
# approval sets ``is_deferred_past_lock`` and posts nothing (REQ-JE-019; ruling R-51 (c)).
DEFER_PAST_LOCK: Final = "DEFER_PAST_LOCK"
# The authored T-SL-05 members an approver reviews: decision-derived columns (status, the request,
# the applied event, the posting, the stored preview and hash) are excluded.
MANUAL_ADJUSTMENT_CONTENT_MEMBERS: Final = (
    "adjustment_no",
    "kind",
    "contract_id",
    "obligation_id",
    "entity_id",
    "book_code",
    "period_id",
    "effective_date",
    "payload",
    "amount_functional_abs",
    "currency",
    "reason_code",
    "memo",
    "is_deferred_past_lock",
)


def _manual_adjustment_row(session: Session, adjustment_id: UUID) -> Mapping[str, Any]:
    row = (
        session.execute(select(manual_adjustment).where(manual_adjustment.c.id == adjustment_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise SubjectNotVisible(f"manual adjustment {adjustment_id} is not visible")
    return dict(row)


def manual_adjustment_content(session: Session, adjustment_id: UUID) -> dict[str, Any]:
    """What a ``MANUAL_ADJUSTMENT`` approval certifies (04 T-SL-05; REQ-PLT-014): the authored
    members of the adjustment, the contract's ``{combination_group_id, head_stream_version}`` —
    an append or a regroup between the request and the decision makes the decision stale — and the
    content hashes of its live attachments whose file can still be read, the evidence the
    threshold rule requires (PRD §2.5). An approved shred of such a document therefore makes the
    decision of a pending request stale (ruling R-120 (g); 04 T-PLT-29 "A document a rule asks
    for")."""
    row = _manual_adjustment_row(session, adjustment_id)
    (state,) = _member_states(session, [UUID(str(row["contract_id"]))])
    attachments = session.scalars(
        select(file_object.c.sha256)
        .select_from(
            file_attachment.join(
                file_object,
                and_(
                    file_object.c.tenant_id == file_attachment.c.tenant_id,
                    file_object.c.id == file_attachment.c.file_object_id,
                ),
            )
        )
        .where(
            file_attachment.c.subject_type == MANUAL_ADJUSTMENT_OBJECT,
            file_attachment.c.subject_id == adjustment_id,
            file_attachment.c.voided_at.is_(None),
            file_object.c.shredded_at.is_(None),
        )
    )
    authored = {name: canonical_value(row[name]) for name in MANUAL_ADJUSTMENT_CONTENT_MEMBERS}
    authored["amount_functional_abs"] = _decimal_text(row["amount_functional_abs"])
    return {
        "object_type": MANUAL_ADJUSTMENT_OBJECT,
        "manual_adjustment_id": str(adjustment_id),
        **authored,
        "contract": {
            "combination_group_id": state["combination_group_id"],
            "head_stream_version": state["head_stream_version"],
        },
        "attachments": sorted(str(value).strip() for value in attachments),
    }


def manual_adjustment_entities(session: Session, adjustment_id: UUID) -> SubjectEntities:
    """The entities of a ``MANUAL_ADJUSTMENT`` request (R-25; supervisor rulings R-51 (d) and
    R-64 (1); 04 §16.10 rev 1.104 part 11): the contracting entities of every current member of
    the combination group of the adjustment's contract (T-SL-05 ``contract_id``;
    ``contract_group_entities`` — the approval of the posting request appends
    ``MANUAL_ADJUSTMENT_APPLIED`` and recomputes the group). A contract alone in its group names
    its own entity, which is the adjustment's (T-SL-05 ``entity_id``). An adjustment the session
    cannot read answers 404, never a tenant-level request."""
    found = session.execute(
        select(manual_adjustment.c.contract_id).where(manual_adjustment.c.id == adjustment_id)
    ).scalar_one_or_none()
    return contract_group_entities(session, [_visible_entity(found)])


def manual_adjustment_amount(session: Session, adjustment_id: UUID) -> tuple[Decimal, str] | None:
    """T-PLT-17 ``amount_functional``: the adjustment's absolute impact in the entity's functional
    currency (04 T-SL-05 ``amount_functional_abs``; PRD §2.5 threshold routing)."""
    found = session.execute(
        select(manual_adjustment.c.amount_functional_abs, legal_entity.c.functional_currency)
        .select_from(
            manual_adjustment.join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == manual_adjustment.c.tenant_id,
                    legal_entity.c.id == manual_adjustment.c.entity_id,
                ),
            )
        )
        .where(manual_adjustment.c.id == adjustment_id)
    ).one_or_none()
    if found is None:
        return None
    return Decimal(found[0]), str(found[1]).strip()


def manual_adjustment_creator(session: Session, adjustment_id: UUID) -> frozenset[UUID]:
    """PRD §2.5 (approver ≠ preparer; CTL-014): the person who prepared the adjustment may not
    decide a request about it, whoever submitted it — in a ``closing`` period a holder of
    ``period.lock`` submits what an accountant prepared (BR-CLS-04), and the request's preparer
    is then the submitter."""
    found = session.execute(
        select(manual_adjustment.c.created_by, manual_adjustment.c.created_by_kind).where(
            manual_adjustment.c.id == adjustment_id
        )
    ).one_or_none()
    if found is None or found[0] is None or str(found[1]) != PrincipalKind.USER.value:
        return frozenset()
    return frozenset({UUID(str(found[0]))})


MIGRATION_SSP_REPLAY_OBJECT: Final = "migration_batch"


def migration_ssp_replay_content(session: Session, batch_id: UUID) -> dict[str, Any]:
    """What a ``MIGRATION_SSP_REPLAY`` approval certifies (04 §16.10 rev 1.72; D-98 133 AMENDMENT
    4): the legacy database's ``SKU_SSP`` table as the batch PROFILE records it — the source digest,
    the
    ``SKU_SSP`` digest, the distinct version labels, the row count and the (label, SKU,
    stratification)
    keys — the file is the evidence; nothing is read from the spooled source here."""
    row = (
        session.execute(
            select(migration_batch.c.source_sha256, migration_batch.c.profile).where(
                migration_batch.c.id == batch_id
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise SubjectNotVisible(f"migration batch {batch_id} is not visible")
    profile = dict(row["profile"] or {})
    return {
        "source_sha256": str(row["source_sha256"]),
        "sku_ssp_sha256": profile.get("sku_ssp_sha256"),
        "ssp_versions": sorted(str(label) for label in profile.get("ssp_versions") or ()),
        "sku_ssp_rows": int(profile.get("sku_ssp_rows") or 0),
        "sku_ssp_keys": sorted(
            [str(k[0]), str(k[1]), str(k[2])] for k in profile.get("sku_ssp_keys") or ()
        ),
    }


SUBJECTS: Final[dict[ApprovalSubjectType, SubjectSpec]] = {
    ApprovalSubjectType.ROLE_ASSIGNMENT: SubjectSpec(
        subject_type=ApprovalSubjectType.ROLE_ASSIGNMENT,
        table="role_assignment",
        required_permission="access.approve",  # PRD §2.5 routing row ROLE_ASSIGNMENT
        revenue_affecting=False,
        min_approvers=1,
        content=_hashes_its_proposal,
        entity_id=_stated_by_proposal,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_apply_role_assignment,
        on_rejected=_close_role_assignment,
        on_voided=_close_role_assignment,
        proposal_content=role_assignment_content,
        proposal_entities=role_assignment_entities,
    ),
    ApprovalSubjectType.ROLE_CHANGE: SubjectSpec(
        subject_type=ApprovalSubjectType.ROLE_CHANGE,
        table="role",
        required_permission="access.approve",  # PRD §2.5 routing row ROLE_CHANGE
        revenue_affecting=False,
        min_approvers=1,
        content=_hashes_its_proposal,
        entity_id=_tenant_level,  # a role or an SoD rule of the tenant
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_apply_role_change,
        on_rejected=_close_role_change(ConfigStatus.REJECTED, SOD_RULE_REJECT),
        on_voided=_close_role_change(ConfigStatus.WITHDRAWN, SOD_RULE_WITHDRAW),
        proposal_content=role_change_content,
    ),
    ApprovalSubjectType.SOD_EXCEPTION: SubjectSpec(
        subject_type=ApprovalSubjectType.SOD_EXCEPTION,
        table="sod_exception",
        required_permission="access.approve",  # PRD §2.5 routing row SOD_EXCEPTION
        revenue_affecting=False,
        min_approvers=1,
        content=_hashes_its_proposal,
        entity_id=_tenant_level,  # access administration (T-PLT-14)
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_approve_grant(
            sod_exception, SOD_EXCEPTION_APPROVE, SOD_EXCEPTION_NEEDS_PERSON
        ),
        on_rejected=_close_grant(sod_exception, SOD_EXCEPTION_REJECT),
        on_voided=_close_grant(sod_exception, SOD_EXCEPTION_VOID),
        proposal_content=sod_exception_content,
    ),
    ApprovalSubjectType.SUPPORT_GRANT: SubjectSpec(
        subject_type=ApprovalSubjectType.SUPPORT_GRANT,
        table="support_grant",
        required_permission="support_grant.approve",  # PRD §2.5 routing row SUPPORT_GRANT
        revenue_affecting=False,
        min_approvers=1,
        content=_hashes_its_proposal,
        entity_id=_resolved_by_entities,
        entities=support_grant_entities,  # provider access to every entity
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_approve_grant(
            support_grant, SUPPORT_GRANT_APPROVE, SUPPORT_GRANT_NEEDS_PERSON
        ),
        on_rejected=_close_grant(support_grant, SUPPORT_GRANT_REJECT),
        on_voided=_close_grant(support_grant, SUPPORT_GRANT_VOID),
        link_path=lambda _subject_id: SUPPORT_GRANT_LINK,
        proposal_content=support_grant_content,
    ),
    ApprovalSubjectType.FX_RATE_SET_VERSION: SubjectSpec(
        subject_type=ApprovalSubjectType.FX_RATE_SET_VERSION,
        table="fx_rate_set_version",
        required_permission="config.approve",  # PRD §2.5 routing row FX_RATE_SET_VERSION
        revenue_affecting=False,
        min_approvers=1,
        content=fx_rate_set_version_content,
        entity_id=_tenant_level,  # tenant reference data
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_approve_fx_rate_set_version,
        on_rejected=_close_fx_rate_set_version(ConfigStatus.REJECTED, FX_RATE_SET_VERSION_REJECT),
        on_voided=_close_fx_rate_set_version(ConfigStatus.WITHDRAWN, FX_RATE_SET_VERSION_WITHDRAW),
        # R-98: the uploader of the import that created the version (SYSTEM submits for them).
        excluded_deciders=fx_rate_set_version_uploader,
    ),
    ApprovalSubjectType.ACCOUNT_MAPPING_VERSION: SubjectSpec(
        subject_type=ApprovalSubjectType.ACCOUNT_MAPPING_VERSION,
        table="account_mapping_version",
        required_permission="config.approve",  # PRD §2.5 routing row ACCOUNT_MAPPING_VERSION
        revenue_affecting=False,
        min_approvers=1,
        content=account_mapping_version_content,
        entity_id=_resolved_by_entities,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_registered(ApprovalSubjectType.ACCOUNT_MAPPING_VERSION, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.ACCOUNT_MAPPING_VERSION, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.ACCOUNT_MAPPING_VERSION, "on_voided"),
        entities=account_mapping_version_entities,
    ),
    ApprovalSubjectType.RULE_SET_VERSION: SubjectSpec(
        subject_type=ApprovalSubjectType.RULE_SET_VERSION,
        table="rule_set_version",
        required_permission="config.approve",  # PRD §2.5 routing row RULE_SET_VERSION
        revenue_affecting=False,
        min_approvers=1,
        content=rule_set_version_content,
        entity_id=_tenant_level,  # tenant configuration (T-REF-25)
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_registered(ApprovalSubjectType.RULE_SET_VERSION, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.RULE_SET_VERSION, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.RULE_SET_VERSION, "on_voided"),
    ),
    ApprovalSubjectType.POB_TEMPLATE_VERSION: SubjectSpec(
        subject_type=ApprovalSubjectType.POB_TEMPLATE_VERSION,
        table="pob_template_version",
        required_permission="config.approve",  # PRD §2.5 configuration subjects → config.approve
        revenue_affecting=False,
        min_approvers=1,
        content=pob_template_version_content,
        entity_id=_tenant_level,  # tenant configuration (T-REF-23)
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_registered(ApprovalSubjectType.POB_TEMPLATE_VERSION, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.POB_TEMPLATE_VERSION, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.POB_TEMPLATE_VERSION, "on_voided"),
    ),
    ApprovalSubjectType.PRINCIPAL_AGENT_CHANGE: SubjectSpec(
        subject_type=ApprovalSubjectType.PRINCIPAL_AGENT_CHANGE,
        table="product",
        required_permission="config.approve",  # PRD §2.5 routing row PRINCIPAL_AGENT_CHANGE
        revenue_affecting=False,
        min_approvers=1,
        content=_hashes_its_proposal,
        entity_id=_tenant_level,  # a product of the tenant
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_apply_principal_agent_change,
        on_rejected=_nothing_to_undo,
        on_voided=_nothing_to_undo,
        link_path=lambda subject_id: PRODUCT_LINK.format(product_id=subject_id),
        proposal_content=principal_agent_content,
    ),
    ApprovalSubjectType.SSP_BOOK_VERSION: SubjectSpec(
        subject_type=ApprovalSubjectType.SSP_BOOK_VERSION,
        table="ssp_book_version",
        required_permission="ssp.approve",  # PRD §2.5 routing row SSP_BOOK_VERSION
        revenue_affecting=False,
        min_approvers=1,
        content=ssp_book_version_content,
        entity_id=ssp_book_version_entity,
        amount_functional=lambda _session, _subject_id: None,
        flags=_registered_flags(ApprovalSubjectType.SSP_BOOK_VERSION),
        on_approved=_registered(ApprovalSubjectType.SSP_BOOK_VERSION, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.SSP_BOOK_VERSION, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.SSP_BOOK_VERSION, "on_voided"),
        second_step_flags=SSP_SECOND_APPROVER_FLAGS,
    ),
    ApprovalSubjectType.REGISTRY_VERSION: SubjectSpec(
        subject_type=ApprovalSubjectType.REGISTRY_VERSION,
        table="registry_version",
        required_permission="config.approve",  # PRD §2.5 configuration subjects → config.approve
        revenue_affecting=False,
        min_approvers=1,
        content=registry_version_content,
        entity_id=_resolved_by_entities,
        entities=registry_version_entities,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_registered(ApprovalSubjectType.REGISTRY_VERSION, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.REGISTRY_VERSION, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.REGISTRY_VERSION, "on_voided"),
        link_path=lambda subject_id: f"/policies/accounting/{subject_id}",  # SCREENS RT-64
    ),
    ApprovalSubjectType.MANUAL_EVENT: SubjectSpec(
        subject_type=ApprovalSubjectType.MANUAL_EVENT,
        excluded_deciders=draft_authors(event_submission, edit_actions=()),
        excluded_detail=AUTHOR_DETAIL,
        table="event_submission",
        required_permission="event.approve",  # PRD §2.5 routing row MANUAL_EVENT
        revenue_affecting=False,
        min_approvers=1,
        content=event_submission_content,
        entity_id=_resolved_by_entities,
        entities=event_submission_entities,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        preparer_entities=_event_submission_preparer_entities(ApprovalSubjectType.MANUAL_EVENT),
        # erev_api.domain.contracts.events registers the lifecycle (BUILD_SPEC CTR-6): the stored
        # batch is checked again where it is appended, and the approval computes the group.
        on_approved=_registered(ApprovalSubjectType.MANUAL_EVENT, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.MANUAL_EVENT, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.MANUAL_EVENT, "on_voided"),
    ),
    ApprovalSubjectType.IMPORT_COMMIT: SubjectSpec(
        subject_type=ApprovalSubjectType.IMPORT_COMMIT,
        table="import_upload",
        required_permission="import.approve",  # PRD §2.5 routing row IMPORT_COMMIT
        revenue_affecting=True,
        min_approvers=1,
        content=import_commit_content,
        entity_id=_resolved_by_entities,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        # erev_api.domain.imports.commit registers the lifecycle (BUILD_SPEC DIN-3).
        on_approved=_registered(ApprovalSubjectType.IMPORT_COMMIT, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.IMPORT_COMMIT, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.IMPORT_COMMIT, "on_voided"),
        entities=import_commit_entities,
        preparer_entities=import_commit_preparer_entities,
        floor=import_commit_floor,
        deciders=import_commit_deciders,
    ),
    ApprovalSubjectType.JUDGEMENT_RECORD: SubjectSpec(
        subject_type=ApprovalSubjectType.JUDGEMENT_RECORD,
        table="judgement_record",
        required_permission="judgement.review",  # PRD §2.5 routing row JUDGEMENT_RECORD
        revenue_affecting=False,
        min_approvers=1,
        content=judgement_record_subject_content,
        entity_id=_resolved_by_entities,
        entities=judgement_record_entities,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_registered(ApprovalSubjectType.JUDGEMENT_RECORD, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.JUDGEMENT_RECORD, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.JUDGEMENT_RECORD, "on_voided"),
        excluded_deciders=judgement_record_author,
        excluded_detail=JUDGEMENT_AUTHOR_DETAIL,
    ),
    ApprovalSubjectType.COMBINATION_GROUP: SubjectSpec(
        subject_type=ApprovalSubjectType.COMBINATION_GROUP,
        table="combination_group",
        required_permission="contract.approve",  # PRD §2.5 routing row COMBINATION_GROUP
        revenue_affecting=False,  # [J] L4-1-Q-16: no dry-run preview of a combination yet
        min_approvers=1,
        content=combination_group_content,
        entity_id=_resolved_by_entities,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_registered(ApprovalSubjectType.COMBINATION_GROUP, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.COMBINATION_GROUP, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.COMBINATION_GROUP, "on_voided"),
        entities=combination_group_entities,
        excluded_deciders=combination_group_author,
        excluded_detail=COMBINATION_AUTHOR_DETAIL,
    ),
    ApprovalSubjectType.CONTRACT_ACTIVATION: SubjectSpec(
        subject_type=ApprovalSubjectType.CONTRACT_ACTIVATION,
        table="contract",
        required_permission="contract.approve",  # PRD §2.5 routing rows CONTRACT_ACTIVATION
        revenue_affecting=True,  # the activation dry run is the impact preview (REQ-PLT-015)
        min_approvers=1,
        content=contract_activation_content,
        entity_id=_resolved_by_entities,
        entities=contract_subject_entities,
        # Item ACT-FLAGS-1: the consideration in the entity's functional currency, converted by
        # the domain module; ``activation.submit_activation`` supplies amount and flags itself,
        # from its dry run (``engine.submit(amount=…, flags=…)``).
        amount_functional=_registered_amount(ApprovalSubjectType.CONTRACT_ACTIVATION),
        flags=_registered_flags(ApprovalSubjectType.CONTRACT_ACTIVATION),
        on_approved=_registered(ApprovalSubjectType.CONTRACT_ACTIVATION, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.CONTRACT_ACTIVATION, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.CONTRACT_ACTIVATION, "on_voided"),
        link_path=lambda subject_id: CONTRACT_LINK.format(contract_id=subject_id),
        # PRD §2.5 rev 1.194: the Controller's step from USD 1,000,000.00, and for an amount
        # that cannot be stated (``RATE_NOT_PUBLISHED``).
        second_step_flags=frozenset({ABOVE_CONTROLLER_THRESHOLD, RATE_NOT_PUBLISHED}),
        second_step_role=CONTROLLER_ROLE,
    ),
    ApprovalSubjectType.MODIFICATION: SubjectSpec(
        subject_type=ApprovalSubjectType.MODIFICATION,
        excluded_deciders=draft_authors(
            modification, edit_actions=("modification.update", "modification.classify")
        ),
        excluded_detail=AUTHOR_DETAIL,
        table=MODIFICATION_OBJECT,
        required_permission="modification.approve",  # PRD §2.5 routing row MODIFICATION
        revenue_affecting=True,  # the stored impact preview is the request's preview (REQ-PLT-015)
        min_approvers=1,
        content=modification_content,
        entity_id=_resolved_by_entities,
        # D-98 140 Q-5: |transaction price change| and the two flags come from the STORED preview,
        # which a Session cannot read; ``modifications.submit`` supplies them through
        # ``engine.route_submission(amount=…, flags=…)`` and the request row keeps them.
        amount_functional=lambda _session, _subject_id: None,
        flags=_registered_flags(ApprovalSubjectType.MODIFICATION),
        on_approved=_registered(ApprovalSubjectType.MODIFICATION, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.MODIFICATION, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.MODIFICATION, "on_voided"),
        link_path=lambda subject_id: MODIFICATION_LINK.format(modification_id=subject_id),
        second_step_flags=frozenset({MODIFICATION_CATCH_UP_FLAG, MODIFICATION_TP_CHANGE_FLAG}),
        second_step_role=CONTROLLER_ROLE,
        entities=modification_entities,
    ),
    ApprovalSubjectType.CONTRACT_VOID: SubjectSpec(
        subject_type=ApprovalSubjectType.CONTRACT_VOID,
        table="contract",
        required_permission="contract.approve",  # PRD §2.5 routing rows CONTRACT_VOID
        revenue_affecting=True,  # the void dry run is the impact preview (REQ-PLT-015; CTL-046)
        min_approvers=1,
        content=contract_void_content,
        entity_id=_resolved_by_entities,
        entities=contract_subject_entities,
        # Item ACT-FLAGS-1: the booked consideration in the entity's functional currency.
        amount_functional=_registered_amount(ApprovalSubjectType.CONTRACT_VOID),
        flags=_registered_flags(ApprovalSubjectType.CONTRACT_VOID),
        on_approved=_registered(ApprovalSubjectType.CONTRACT_VOID, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.CONTRACT_VOID, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.CONTRACT_VOID, "on_voided"),
        link_path=lambda subject_id: CONTRACT_LINK.format(contract_id=subject_id),
        second_step_flags=frozenset({POSTED_LINES}),
        second_step_role=CONTROLLER_ROLE,
    ),
    ApprovalSubjectType.ATTRIBUTE_CHANGE: SubjectSpec(
        subject_type=ApprovalSubjectType.ATTRIBUTE_CHANGE,
        excluded_deciders=draft_authors(event_submission, edit_actions=()),
        excluded_detail=AUTHOR_DETAIL,
        table="event_submission",
        required_permission="event.approve",  # PRD §2.5 routing row ATTRIBUTE_CHANGE
        revenue_affecting=False,  # [J] L4-1-Q-23: no dry-run preview of an attribute change yet
        min_approvers=1,
        content=event_submission_content,
        entity_id=_resolved_by_entities,
        entities=event_submission_entities,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        preparer_entities=_event_submission_preparer_entities(ApprovalSubjectType.ATTRIBUTE_CHANGE),
        on_approved=_registered(ApprovalSubjectType.ATTRIBUTE_CHANGE, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.ATTRIBUTE_CHANGE, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.ATTRIBUTE_CHANGE, "on_voided"),
    ),
    ApprovalSubjectType.POLICY_OVERRIDE: SubjectSpec(
        subject_type=ApprovalSubjectType.POLICY_OVERRIDE,
        excluded_deciders=draft_authors(policy_override, edit_actions=()),
        excluded_detail=AUTHOR_DETAIL,
        table="policy_override",
        required_permission="contract.approve",  # PRD §2.5 routing row POLICY_OVERRIDE
        revenue_affecting=False,  # L4-2-Q-4
        min_approvers=1,
        content=policy_override_content,
        entity_id=_resolved_by_entities,
        entities=policy_override_entities,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_registered(ApprovalSubjectType.POLICY_OVERRIDE, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.POLICY_OVERRIDE, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.POLICY_OVERRIDE, "on_voided"),
    ),
    ApprovalSubjectType.SSP_OVERRIDE: SubjectSpec(
        subject_type=ApprovalSubjectType.SSP_OVERRIDE,
        table="obligation",
        required_permission="ssp.approve",  # PRD §2.5 routing row SSP_OVERRIDE
        revenue_affecting=False,  # L4-2-Q-4
        min_approvers=1,
        content=_hashes_its_proposal,
        entity_id=_resolved_by_entities,
        entities=ssp_override_entities,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_registered(ApprovalSubjectType.SSP_OVERRIDE, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.SSP_OVERRIDE, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.SSP_OVERRIDE, "on_voided"),
        proposal_content=ssp_override_content,
    ),
    ApprovalSubjectType.ESTIMATE_VERSION: SubjectSpec(
        subject_type=ApprovalSubjectType.ESTIMATE_VERSION,
        excluded_deciders=draft_authors(
            estimate_version, edit_actions=("estimate_version.update",)
        ),
        excluded_detail=AUTHOR_DETAIL,
        table="estimate_version",
        required_permission="estimate.approve",  # PRD §2.5 routing row ESTIMATE_VERSION
        revenue_affecting=True,  # the submission's dry run is the impact preview (REQ-PLT-015)
        min_approvers=1,
        content=estimate_version_content,
        entity_id=_resolved_by_entities,
        # R-41 (7): the absolute P&L impact and its flag come from the submission's dry run, which
        # a Session cannot read; ``estimates.submit_version`` supplies them through
        # ``engine.route_submission(amount=…, flags=…)`` and the request row keeps them.
        amount_functional=lambda _session, _subject_id: None,
        flags=_registered_flags(ApprovalSubjectType.ESTIMATE_VERSION),
        on_approved=_registered(ApprovalSubjectType.ESTIMATE_VERSION, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.ESTIMATE_VERSION, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.ESTIMATE_VERSION, "on_voided"),
        entities=estimate_version_entities,
        # PRD §2.5 ``ESTIMATE_VERSION``: "If absolute P&L impact ≥ USD 50,000.00: 2: Controller".
        second_step_flags=frozenset({ESTIMATE_PL_IMPACT_FLAG}),
        second_step_role=CONTROLLER_ROLE,
    ),
    ApprovalSubjectType.MAPPING_PROFILE_VERSION: SubjectSpec(
        subject_type=ApprovalSubjectType.MAPPING_PROFILE_VERSION,
        table="import_mapping_profile",
        required_permission="config.approve",  # PRD §2.5 routing row MAPPING_PROFILE_VERSION
        revenue_affecting=False,
        min_approvers=1,
        content=mapping_profile_version_content,
        entity_id=_tenant_level,  # tenant configuration (T-IMP-06)
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_registered(ApprovalSubjectType.MAPPING_PROFILE_VERSION, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.MAPPING_PROFILE_VERSION, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.MAPPING_PROFILE_VERSION, "on_voided"),
    ),
    ApprovalSubjectType.EXCEPTION_WAIVER: SubjectSpec(
        subject_type=ApprovalSubjectType.EXCEPTION_WAIVER,
        table="exception_item",
        required_permission="exception.waive",  # PRD §2.5 routing row EXCEPTION_WAIVER
        revenue_affecting=False,  # [J] L6-1-Q-10: a waiver changes no figure, so no preview
        min_approvers=1,
        content=exception_waiver_content,
        entity_id=_resolved_by_entities,
        entities=exception_waiver_entities,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_registered(ApprovalSubjectType.EXCEPTION_WAIVER, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.EXCEPTION_WAIVER, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.EXCEPTION_WAIVER, "on_voided"),
        link_path=lambda subject_id: EXCEPTION_LINK.format(item_id=subject_id),
        excluded_deciders=exception_waiver_owner,
    ),
    ApprovalSubjectType.JOURNAL_RUN: SubjectSpec(
        subject_type=ApprovalSubjectType.JOURNAL_RUN,
        table="journal_run",
        required_permission="journal.approve",  # PRD §2.5 routing row JOURNAL_RUN
        revenue_affecting=False,  # a run summarises posted lines; it changes no revenue
        min_approvers=1,
        content=journal_run_content,
        entity_id=journal_run_entity,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_registered(ApprovalSubjectType.JOURNAL_RUN, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.JOURNAL_RUN, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.JOURNAL_RUN, "on_voided"),
        link_path=lambda subject_id: JOURNAL_RUN_LINK.format(run_id=subject_id),
        excluded_deciders=journal_run_runner,
        excluded_detail=JOURNAL_RUNNER_DETAIL,
    ),
    # F-CLO CLO-6 (appended after JOURNAL_RUN by agreement with F-CTR): PRD §2.5 row PERIOD_LOCK.
    ApprovalSubjectType.PERIOD_LOCK: SubjectSpec(
        subject_type=ApprovalSubjectType.PERIOD_LOCK,
        table=PERIOD_LOCK_OBJECT,
        required_permission="period.lock",  # held by the Controller role only (PRD §5.6)
        revenue_affecting=False,  # a lock freezes; it changes no revenue
        min_approvers=1,
        content=period_lock_content,
        entity_id=period_lock_entity,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_registered(ApprovalSubjectType.PERIOD_LOCK, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.PERIOD_LOCK, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.PERIOD_LOCK, "on_voided"),
        link_path=lambda subject_id: PERIOD_LINK.format(state_id=subject_id),
        # PRD §2.5 ``PERIOD_LOCK``: "1: period.lock (Controller)" — the role is part of the step,
        # so a custom role that carries period.lock does not lock a period (R-41 (7)).
        step_role=CONTROLLER_ROLE,
    ),
    # F-CLO CLO-7: PRD §2.5 row PERIOD_REOPEN — one step, two approvers holding
    # ``period.reopen_approve`` (Controller or Revenue Reviewer), at least one a Controller
    # (``quorum.REOPEN_QUORUM``; engine ``_advance``), neither the requester (REQ-CLS-011;
    # D-75 Q12).
    ApprovalSubjectType.PERIOD_REOPEN: SubjectSpec(
        subject_type=ApprovalSubjectType.PERIOD_REOPEN,
        table=PERIOD_LOCK_OBJECT,
        required_permission="period.reopen_approve",
        revenue_affecting=False,  # the reopen itself moves no revenue; the postings that follow do
        min_approvers=2,
        content=period_reopen_content,
        entity_id=period_lock_entity,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_registered(ApprovalSubjectType.PERIOD_REOPEN, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.PERIOD_REOPEN, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.PERIOD_REOPEN, "on_voided"),
        link_path=lambda subject_id: PERIOD_LINK.format(state_id=subject_id),
    ),
    ApprovalSubjectType.MIGRATION_SSP_REPLAY: SubjectSpec(
        subject_type=ApprovalSubjectType.MIGRATION_SSP_REPLAY,
        table=MIGRATION_SSP_REPLAY_OBJECT,
        required_permission="migration.approve",  # 02-PRD §2.5 rev 1.15 (AUTO-MIG-01 auto-approves)
        revenue_affecting=False,
        min_approvers=1,
        content=migration_ssp_replay_content,
        entity_id=_tenant_level,  # the all-entity LEGACY-SKU-SSP book
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        # erev_api.domain.migration.commands registers the (no-op) lifecycle: the replayed versions
        # are
        # written by the import job that reads the approved request; nothing runs at the decision.
        on_approved=_registered(ApprovalSubjectType.MIGRATION_SSP_REPLAY, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.MIGRATION_SSP_REPLAY, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.MIGRATION_SSP_REPLAY, "on_voided"),
    ),
    # F-CLO-A CLO-12: PRD §2.5 rows MANUAL_ADJUSTMENT — one ``adjustment.approve`` step; from USD
    # 10,000.00 (flag ``ABOVE_THRESHOLD``, set by the command) a second one held by a Controller.
    # The request names the adjustment's entity (ruling R-25) and never auto-approves (R-26).
    ApprovalSubjectType.MANUAL_ADJUSTMENT: SubjectSpec(
        subject_type=ApprovalSubjectType.MANUAL_ADJUSTMENT,
        table=MANUAL_ADJUSTMENT_OBJECT,
        required_permission="adjustment.approve",
        revenue_affecting=True,  # the submission's dry run is the impact preview (REQ-PLT-015)
        min_approvers=1,
        content=manual_adjustment_content,
        entity_id=_resolved_by_entities,
        entities=manual_adjustment_entities,
        amount_functional=manual_adjustment_amount,
        flags=lambda _session, _subject_id: frozenset(),  # the command supplies them
        on_approved=_registered(ApprovalSubjectType.MANUAL_ADJUSTMENT, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.MANUAL_ADJUSTMENT, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.MANUAL_ADJUSTMENT, "on_voided"),
        second_step_flags=frozenset({ABOVE_THRESHOLD}),
        second_step_role=CONTROLLER_ROLE,
        excluded_deciders=manual_adjustment_creator,
    ),
    # Lane SECFIX-IMP (supervisor rulings R-49 (a), R-86 (b), (c); 04 rev 1.142 E-08; PRD §2.5
    # rev 1.71): the shred of a file that a record holds as its evidence — requested by the
    # privacy-side administrator, decided by a Controller. The subject is the file_object
    # row; the hashed content is the proposal with the state of the file
    # (``evidence_shred_content`` below the table). The request is bound to the legal entities
    # of the records that hold the file, which its proposal states (R-25, R-41 (4);
    # ``evidence_shred_entities``), and its one step carries the Controller role (R-49 (a):
    # "one step, the Controller role"; R-41 (7)).
    # ``erev_api.domain.platform.evidence_shred`` registers the lifecycle; the subject is never
    # auto-approved.
    ApprovalSubjectType.EVIDENCE_SHRED: SubjectSpec(
        subject_type=ApprovalSubjectType.EVIDENCE_SHRED,
        table="file_object",  # EVIDENCE_SHRED_OBJECT
        required_permission="config.approve",  # EVIDENCE_SHRED_PERMISSION; a Controller's
        revenue_affecting=False,  # a shred moves no revenue; the proposal is its preview
        min_approvers=1,
        content=_hashes_its_proposal,
        entity_id=_stated_by_proposal,
        amount_functional=lambda _session, _subject_id: None,
        flags=lambda _session, _subject_id: frozenset(),
        on_approved=_registered(ApprovalSubjectType.EVIDENCE_SHRED, "on_approved"),
        on_rejected=_registered(ApprovalSubjectType.EVIDENCE_SHRED, "on_rejected"),
        on_voided=_registered(ApprovalSubjectType.EVIDENCE_SHRED, "on_voided"),
        proposal_content=lambda session, proposal: evidence_shred_content(session, proposal),
        proposal_entities=lambda session, proposal: evidence_shred_entities(session, proposal),
        step_role=CONTROLLER_ROLE,
    ),
}

# --- EVIDENCE_SHRED (the block of the table's last entry; rulings R-49 (a), R-86) ------------

EVIDENCE_SHRED_OBJECT: Final = "file_object"
# R-49 (a) as ruled: one step, ``config.approve`` held by a Controller (no catalogue change).
EVIDENCE_SHRED_PERMISSION: Final = "config.approve"


def evidence_shred_proposal(
    file_row: Mapping[str, Any],
    holds: Sequence[Mapping[str, Any]],
    *,
    reason: str,
    entity_ids: Collection[UUID] | None,
    pending_requests: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """The ``after`` member of an ``EVIDENCE_SHRED`` request: the file, its SHA-256, the records
    that hold it as their evidence — each by the column that references the file, the row and
    the name a person reads — the legal entities of those records (``entity_ids``; None when one
    of them has none, which is every entity) and the reason that names the data-subject request.
    The approval lifts exactly these holds. ``pending_requests`` names the approval requests
    that were pending on those records when the shred was requested — the decision of each is
    refused once the file is gone (ruling R-120 (g)): what the approver of the shred stops."""
    return {
        "file_id": str(file_row["id"]),
        "sha256": str(file_row["sha256"]).strip(),
        "purpose": str(getattr(file_row["purpose"], "value", file_row["purpose"])),
        "holds": sorted(
            (
                {
                    "table": str(hold["table"]),
                    "column": str(hold["column"]),
                    "record_id": str(hold["record_id"]),
                    "record": str(hold["record"]),
                }
                for hold in holds
            ),
            key=lambda item: (item["table"], item["column"], item["record_id"]),
        ),
        "entity_ids": sorted(str(entity_id) for entity_id in entity_ids or ()),
        "is_all_entities": not entity_ids,
        "pending_requests": sorted(
            (
                {
                    "request_no": str(request["request_no"]),
                    "subject_type": str(request["subject_type"]),
                    "record": str(request["record"]),
                }
                for request in pending_requests
            ),
            key=lambda item: item["request_no"],
        ),
        "reason": reason,
    }


def evidence_shred_entities(session: Session, proposal: Mapping[str, Any]) -> SubjectEntities:
    """The legal entities an ``EVIDENCE_SHRED`` request is bound to (R-25, R-41 (4); 04 §16.10
    "Entity scope of a request"): the entities of the records that hold the file, as its
    proposal states them — every entity when one of those records has none. The proposal names
    them as a role assignment's does, so a proposal that names neither spans every entity (fail
    closed)."""
    return role_assignment_entities(session, proposal)


def evidence_shred_content(session: Session, proposal: Mapping[str, Any]) -> dict[str, Any]:
    """What an ``EVIDENCE_SHRED`` approval certifies: the proposal with the state of the file it
    changes — already shredded, under a legal hold, under retention. ``file_object`` is RLS-T,
    so the content does not depend on who reads it (R-64 (1)). A file shredded or put on hold
    between the request and the decision makes the decision stale (REQ-PLT-014); that the
    records of the proposal are still exactly the ones that hold the file is established by
    the approval hook, which reads them over every entity
    (``domain.platform.evidence_shred``)."""
    file_id = UUID(str(proposal["file_id"]))
    stored = session.execute(
        select(
            file_object.c.sha256,
            file_object.c.shredded_at,
            file_object.c.legal_hold,
            file_object.c.retention_until,
        ).where(file_object.c.id == file_id)
    ).one_or_none()
    return {
        "proposal": dict(proposal),
        "base": {
            "file_sha256": None if stored is None else str(stored.sha256).strip(),
            "shredded": stored is None or stored.shredded_at is not None,
            "legal_hold": stored is not None and bool(stored.legal_hold),
            "retention_until": None
            if stored is None or stored.retention_until is None
            else stored.retention_until.isoformat(),
        },
    }


PENDING_SUBJECTS: Final[tuple[tuple[str, str], ...]] = (
    ("AI_PROPOSAL_ACCEPTANCE", "AIX"),
    ("MIGRATION_PROMOTION", "LMG"),
)


def spec_for(subject_type: ApprovalSubjectType) -> SubjectSpec:
    """The registered spec; ``LookupError`` for a subject type whose spec is not built yet."""
    spec = SUBJECTS.get(ApprovalSubjectType(subject_type))
    if spec is None:
        raise LookupError(f"approval subject {subject_type} has no SubjectSpec yet")
    return spec


# The name of each subject type as a reader is shown it (E-08; SCREENS §15.3 "Subject type
# labels", the words of the web's ``approvals.subjectType.<literal>`` messages). It stands, with
# the request's number, for the summary of a request whose content the reader is not shown
# (``withheld_summary``): a summary names the record the request is about.
SUBJECT_LABELS: Final[Mapping[ApprovalSubjectType, str]] = MappingProxyType(
    {
        ApprovalSubjectType.SSP_BOOK_VERSION: "SSP book version",
        ApprovalSubjectType.SSP_OVERRIDE: "SSP override",
        ApprovalSubjectType.CONTRACT_ACTIVATION: "Contract activation",
        ApprovalSubjectType.MODIFICATION: "Modification",
        ApprovalSubjectType.MANUAL_EVENT: "Manual event",
        ApprovalSubjectType.ESTIMATE_VERSION: "Estimate version",
        ApprovalSubjectType.MANUAL_ADJUSTMENT: "Manual adjustment",
        ApprovalSubjectType.REGISTRY_VERSION: "Policy version",
        ApprovalSubjectType.RULE_SET_VERSION: "Rule set version",
        ApprovalSubjectType.POB_TEMPLATE_VERSION: "Obligation template version",
        ApprovalSubjectType.ACCOUNT_MAPPING_VERSION: "Account mapping version",
        ApprovalSubjectType.FX_RATE_SET_VERSION: "FX rate set version",
        ApprovalSubjectType.ROLE_CHANGE: "Role change",
        ApprovalSubjectType.ROLE_ASSIGNMENT: "Role assignment",
        ApprovalSubjectType.SOD_EXCEPTION: "Separation of duties exception",
        ApprovalSubjectType.PERIOD_LOCK: "Period lock",
        ApprovalSubjectType.PERIOD_REOPEN: "Period reopen",
        ApprovalSubjectType.IMPORT_COMMIT: "Import commit",
        ApprovalSubjectType.CONTRACT_VOID: "Contract void",
        ApprovalSubjectType.COMBINATION_GROUP: "Contract combination",
        ApprovalSubjectType.JUDGEMENT_RECORD: "Judgement record",
        ApprovalSubjectType.JOURNAL_RUN: "Journal run",
        ApprovalSubjectType.SUPPORT_GRANT: "Support access",
        ApprovalSubjectType.AI_PROPOSAL_ACCEPTANCE: "AI proposal acceptance",
        ApprovalSubjectType.PRINCIPAL_AGENT_CHANGE: "Principal or agent change",
        ApprovalSubjectType.ATTRIBUTE_CHANGE: "Obligation attribute change",
        ApprovalSubjectType.EXCEPTION_WAIVER: "Exception waiver",
        ApprovalSubjectType.MIGRATION_PROMOTION: "Migration promotion",
        ApprovalSubjectType.MAPPING_PROFILE_VERSION: "Mapping profile version",
        ApprovalSubjectType.POLICY_OVERRIDE: "Policy override",
        ApprovalSubjectType.MIGRATION_SSP_REPLAY: "Migration SSP replay",
        ApprovalSubjectType.EVIDENCE_SHRED: "Evidence file shredding",
    }
)


def withheld_summary(subject_type: ApprovalSubjectType | str, request_no: str) -> str:
    """What a reader who is not shown a request's content reads for its summary: the name of the
    subject type and the request's number, and nothing of the record (04 §16.10 rev 1.208; item
    APR-CONTENT-SCOPE-1). Every summary names the record the request is about — a contract by its
    external id, a grant by its entities' codes — and the row does not say which of the request's
    entities that record belongs to, so no summary is kept for such a reader."""
    return f"{SUBJECT_LABELS[ApprovalSubjectType(subject_type)]} {request_no}"
