"""Policy overrides and SSP overrides (04 T-CON-23, §15.3 API-R-13 and API-R-29, §16.2
``request-ssp-override``, §16.3 ``LINE_ATTRIBUTES_CHANGED``, §16.5 API-S-PolicyOverride;
POLICIES §0.5, §0.6 OVR; dev-guide DG-KRN-REG-01, DG-KRN-REG-06; 05 RCP-17; PRD §2.5 routing
rows ``SSP_OVERRIDE`` and ``POLICY_OVERRIDE``, BR-SSP-03, ACT-21, ACT-55; 03 REQ-SSP-006,
REQ-POL-004; CTL-010; BUILD_SPEC CTR-15, BS3-D-04, BS3-D-06).

``create_override`` stores nothing: policy overrides are not offered in release 1.0 (04
T-CON-23 "Not offered in release 1.0" rev 1.322; PRD ERR-102; POLICIES §0.5 rule 5; item
POLICY-OVERRIDE-WITHDRAW-1, supervisor ruling R-126), because the original release loaded no
override into calculation. The October 7 continuation now loads approved contract-pinned rows;
creation remains withdrawn until the authoring validation and approval controls are completed.
For a visible contract whose contracting entity the preparer holds ``contract.create`` for (404
``not-found`` otherwise, in either case; the 403 is the route's, for a caller without the
permission), every creation is refused by one rule before anything the request names is
validated: 422 ``policy-level-not-allowed`` with one error on ``policy_key`` under rule id
``POLICY_OVERRIDE_NOT_OFFERED``, whose message — the problem's detail as well — is
``NOT_OFFERED`` and ``decided_instead(policy_key)``, the sentence of what decides the parameter
instead. ``DECIDED_BY`` holds that sentence for each of the 23 parameters that list level
CONTRACT or OBLIGATION, each read against the code that takes the parameter; every other
parameter is told the catalogue and no more (DG-KRN-REG-06).

The functions below keep their code and, in a workspace of the release, meet no row: no command
writes one.

``submit_override`` moves DRAFT → SUBMITTED with ``content_sha256`` and requests approval of
subject ``POLICY_OVERRIDE`` (``contract.approve``). Approval supersedes the APPROVED override of
the same scope and key, approves the row with ``approved_at``, the record time from which
resolution answers it, and marks the contract's group dirty (RCP-17). Rejection gives REJECTED; a
withdrawn or voided request WITHDRAWN.

``request_ssp_override`` requests approval of subject ``SSP_OVERRIDE`` (``ssp.approve``) for an
APPROVED SSP book version (422 otherwise) with a justification: the proposal is the preview's
``after``, the obligation's current SSP pins its ``before``. On approval the SYSTEM principal
appends ``LINE_ATTRIBUTES_CHANGED`` with ``changes.ssp_book_version_id``, the justification, the
diff and the request id, effective on the approval date in the contracting entity's time zone.
The next computation prices the obligation from that version (S06-R-26) and stores the request as
``ssp_override_approval_request_id``.

[J] L4-2-Q-2: the commands need ``contract.create`` (PRD ACT-21, ACT-55) rather than the API-R-13
row's ``config.author``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, NoReturn, Protocol
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import Select, and_, func, select, update
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals import preview, subjects
from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.principal import system_principal
from erev_api.clock import to_entity_date
from erev_api.db import transitions
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    combination_group,
    contract,
    legal_entity,
    obligation,
    policy_override,
    ssp_book,
    ssp_book_version,
)
from erev_api.domain.contracts import repo
from erev_api.domain.ssp import scope as ssp_scope
from erev_api.enums import ApprovalSubjectType, ConfigStatus, ContractEventType, RegistryScope
from erev_api.events.payloads import LineAttributeChangesV1, LineAttributesChangedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.problems import Problem, ProblemError
from erev_api.registry import resolve as registry
from erev_api.uow import UnitOfWork

if TYPE_CHECKING:
    from erev_api.auth.principal import RequestContext

__all__ = [
    "create_override",
    "decided_instead",
    "get_override",
    "list_overrides",
    "override_out",
    "request_ssp_override",
    "submit_override",
]

CREATE_PERMISSION: Final = "contract.create"  # PRD ACT-21, ACT-55
OBJECT_TYPE: Final = "policy_override"
SUBMIT_ACTION: Final = "policy_override.submit"
APPROVE_ACTION: Final = "policy_override.approve"
REJECT_ACTION: Final = "policy_override.reject"
WITHDRAW_ACTION: Final = "policy_override.withdraw"
SUPERSEDE_ACTION: Final = "policy_override.supersede"
SSP_OVERRIDE_ACTION: Final = "obligation.ssp_override"
RULE_NOT_OFFERED: Final = "POLICY_OVERRIDE_NOT_OFFERED"  # PRD ERR-102; 04 T-CON-23 rev 1.322
RULE_SSP_OVERRIDE: Final = "REQ-SSP-006"
DRAFT: Final = ConfigStatus.DRAFT.value
SUBMITTED: Final = ConfigStatus.SUBMITTED.value
APPROVED: Final = ConfigStatus.APPROVED.value
SUPERSEDED: Final = ConfigStatus.SUPERSEDED.value
# [J] Copy the documents leave open.
NOT_DRAFT: Final = "Only a draft override can be submitted."
VERSION_NOT_APPROVED: Final = "Choose an approved SSP book version."
# PRD ERR-102: the refusal of every creation says this, then what decides the parameter instead.
NOT_OFFERED: Final = (
    "Policy overrides for a contract or an obligation are not offered in this release."
)
FRAMEWORK_FIXED: Final = "The framework fixes this value."  # as a registry version is refused
KEY_UNKNOWN: Final = "The policy registry holds no parameter of this key."
NO_LEVEL: Final = "It can be set at no level of the policy registry."
SET_ONLY_AT: Final = "It can be set only at {levels} level."  # the form of PRD ERR-47
LEVEL_NAMES: Final[Mapping[RegistryScope, str]] = MappingProxyType(
    {
        RegistryScope.TENANT: "workspace",
        RegistryScope.ENTITY: "legal entity",
        RegistryScope.BOOK: "book",
        RegistryScope.PRODUCT: "product",
    }
)
_WORKSPACE: Final = "It is set in the policy registry for the workspace."
_ENTITY: Final = "It is set in the policy registry for a legal entity."
_PRODUCT: Final = "It is set on the product or on its obligation template."
_DEFAULT: Final = "The framework's default applies to every contract in this release."
# POLICIES §0.5 rule 5, table 0.5-A (rev 1.124): what decides, in release 1.0, each parameter that
# lists level CONTRACT or OBLIGATION, where no override of it is stored. Each sentence was read
# against the code that takes the parameter: a record of the contract decides; or the value is set
# at a level the parameter lists besides and a computation reads it there; or neither, and the
# framework's default applies. ``tests/unit/policies/test_override_not_offered.py`` holds the keys
# to the catalogue and the sentences to the table, word for word, so a parameter that gains or
# loses one of the two levels fails the build until its sentence is read and restated.
DECIDED_BY: Final[Mapping[str, str]] = MappingProxyType(
    {
        "balance.right_to_consideration": _PRODUCT,
        "claims.recognition_gate": (
            "The framework fixes this value, and a claim enters the transaction price with its "
            "estimate version and the reviewed judgement record that attests it enforceable."
        ),
        "concession.allocation_basis": _DEFAULT,
        "cpc.incentive_asset_release_basis": _DEFAULT,
        "cpc.share_based_timing": (
            "The framework fixes this value, and it applies to the consideration payable "
            "recorded on the contract as share-based."
        ),
        "fx.cl_historical_layering": _ENTITY,
        "material_right.ssp_method": "The option terms of the material right decide it.",
        "mod.ssp_basis": (
            "It is set in the policy registry for the workspace, and the SSP basis of a "
            "modification decides it for an obligation."
        ),
        "pob.principal_or_agent": _PRODUCT,
        "recognition.control_trigger": _PRODUCT,
        "recognition.measure_of_progress": _PRODUCT,
        "returns.model": _PRODUCT,
        "returns.returned_units_scope": _PRODUCT,
        "royalty.minimum_guarantee": _DEFAULT,
        "royalty.unreported_sales": _DEFAULT,
        "scope.collaboration_808": "The scope flag of each contract line decides it.",
        "scope.repurchase_classification": (
            "The framework fixes this value, and the reviewed judgement record of the "
            "repurchase terms decides the outcome."
        ),
        # The default states a basis and no rate, and stage 04 takes a rate from an override
        # alone: SFC_RATE_MISSING is an ERROR finding, which stops the group's computation.
        "sfc.discount_rate_basis": (
            "The framework's default basis applies to every contract in this release, and no "
            "discount rate can be given: a contract whose financing needs an adjustment is not "
            "computed (SFC_RATE_MISSING)."
        ),
        "ssp.version_basis": (
            "It is set in the policy registry for the workspace, and an SSP override names the "
            "version that prices an obligation."
        ),
        "step1.term_with_termination_rights": _WORKSPACE,
        # Level P is listed, and the engine reads the parameter for a contract, where the value
        # of a product or a template — given per obligation — is not seen.
        "usage.tier_minimum_method": _DEFAULT,
        "vc.constraint": (
            "The framework fixes this value, and the constrained amount of the element's "
            "estimate version is what it applies."
        ),
        "vc.estimation_method": "The method of the element's estimate version decides it.",
    }
)


class Page(Protocol):
    @property
    def items(self) -> list[Mapping[str, Any]]: ...


def _error(field: str, message: str, rule_id: str) -> ProblemError:
    return ProblemError(field=field, rule_id=rule_id, message=message)


def _modified(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {"updated_by": principal.id, "updated_by_kind": principal.kind.value}


def _row(session: Session, override_id: UUID, *, for_update: bool = False) -> dict[str, Any]:
    statement = select(policy_override).where(policy_override.c.id == override_id)
    if for_update:
        statement = statement.with_for_update()
    found = session.execute(statement).mappings().one_or_none()
    if found is None:
        raise Problem("not-found")
    return dict(found)


def _same_scope(row: Mapping[str, Any]) -> list[Any]:
    """The conditions of the overrides of the row's contract, obligation and key."""
    subject = (
        policy_override.c.obligation_id.is_(None)
        if row["obligation_id"] is None
        else policy_override.c.obligation_id == row["obligation_id"]
    )
    return [
        policy_override.c.contract_id == row["contract_id"],
        subject,
        policy_override.c.policy_key == row["policy_key"],
    ]


def _entity_of(current: Mapping[str, Any]) -> UUID:
    return UUID(str(current["contracting_entity_id"]))


# --- policy overrides ----------------------------------------------------------------------------


def decided_instead(policy_key: str) -> str:
    """What decides ``policy_key`` where no override of it is offered — the second sentence of
    the refusal. One of the 23 parameters that list level CONTRACT or OBLIGATION is told what
    ``DECIDED_BY`` holds for it (POLICIES §0.5 table 0.5-A). Any other is told the catalogue and
    no more: that the framework fixes a value forced in both books, else the levels it can be set
    at; a key the catalogue does not hold, that the registry holds no such parameter."""
    spec = registry.PARAMETERS.get(policy_key)
    if spec is None:
        return KEY_UNKNOWN
    decided = DECIDED_BY.get(policy_key)
    if decided is not None:
        return decided
    if spec.is_forced_asc606 and spec.is_forced_ifrs15:
        return FRAMEWORK_FIXED
    names = [name for level, name in LEVEL_NAMES.items() if level in spec.allowed_levels]
    if not names:
        return NO_LEVEL
    listed = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} or {names[-1]}"
    return SET_ONLY_AT.format(levels=listed)


def create_override(uow: UnitOfWork, *, contract_id: UUID, policy_key: str) -> NoReturn:
    """``POST /policy-overrides``: refused by name, whatever the request names (the module
    docstring; 04 T-CON-23 "Not offered in release 1.0"). The contract's 404 comes first, as it
    did — for an id that names none and for an entity the permission does not cover; nothing
    is validated, stored or audited."""
    current = repo.get_contract(uow.session, contract_id)
    require_for_entity(uow.ctx, CREATE_PERMISSION, _entity_of(current))
    message = f"{NOT_OFFERED} {decided_instead(policy_key)}"
    raise Problem(
        "policy-level-not-allowed",
        message,
        errors=[_error("policy_key", message, RULE_NOT_OFFERED)],
    )


def _summary(session: Session, row: Mapping[str, Any], current: Mapping[str, Any]) -> str:
    where = f"contract {current['contract_no']}"
    if row["obligation_id"] is not None:
        key = session.execute(
            select(obligation.c.obligation_key).where(obligation.c.id == row["obligation_id"])
        ).scalar_one()
        where = f"{where} obligation {key}"
    return f"Override {row['policy_key']} for {where}"


def submit_override(uow: UnitOfWork, override_id: UUID, *, comment: str | None) -> None:
    """``POST /policy-overrides/{id}/submit``: DRAFT → SUBMITTED and one ``POLICY_OVERRIDE``
    request; 409 ``invalid-transition`` unless the override is DRAFT."""
    session = uow.session
    row = _row(session, override_id, for_update=True)
    current = repo.get_contract(session, UUID(str(row["contract_id"])))
    require_for_entity(uow.ctx, CREATE_PERMISSION, _entity_of(current))
    if str(row["status"]) != DRAFT:
        raise Problem(
            "invalid-transition", errors=[_error("status", NOT_DRAFT, transitions.RULE_ID)]
        )
    digest = sha256_hex(subjects.policy_override_content(session, override_id))
    transitions.apply(
        session,
        OBJECT_TYPE,
        override_id,
        to_status=SUBMITTED,
        set_values={"content_sha256": digest, **_modified(uow)},
        expected_status=DRAFT,
    )
    uow.audit(
        action=SUBMIT_ACTION,
        object_type=OBJECT_TYPE,
        object_id=override_id,
        before={"status": DRAFT},
        after={"status": SUBMITTED, "content_sha256": digest},
        comment=comment,
        contract_id=UUID(str(row["contract_id"])),
    )
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.POLICY_OVERRIDE,
        subject_id=override_id,
        summary=_summary(session, row, current),
        comment=comment,
    )
    status = session.execute(
        select(policy_override.c.status).where(policy_override.c.id == override_id)
    ).scalar_one()
    if str(status) == SUBMITTED:
        transitions.apply(
            session,
            OBJECT_TYPE,
            override_id,
            to_status=None,
            set_values={"approval_request_id": request["id"], **_modified(uow)},
        )


def _mark_dirty(uow: UnitOfWork, group_id: UUID) -> None:
    """RCP-17: approval of a policy override marks the member's group dirty."""
    principal = uow.principal
    uow.session.execute(
        update(combination_group)
        .where(
            combination_group.c.tenant_id == principal.tenant_id,
            combination_group.c.id == group_id,
        )
        .values(
            # 05 RCP-17 rev 1.207 (item COMPUTE-BEHIND-GROUP-1): a mark is never moved back
            dirty_since=func.greatest(combination_group.c.dirty_since, uow.now),
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
            row_version=combination_group.c.row_version + 1,
        )
    )


def _approve_override(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    session = uow.session
    row = _row(session, subject_id, for_update=True)
    if str(row["status"]) != SUBMITTED:
        raise LookupError(f"policy override {subject_id} is not submitted")
    previous = session.execute(
        select(policy_override.c.id)
        .where(*_same_scope(row), policy_override.c.status == APPROVED)
        .with_for_update()
    ).scalars()
    for previous_id in [UUID(str(value)) for value in previous]:
        transitions.apply(
            session,
            OBJECT_TYPE,
            previous_id,
            to_status=SUPERSEDED,
            set_values=_modified(uow),
            expected_status=APPROVED,
        )
        uow.audit(
            action=SUPERSEDE_ACTION,
            object_type=OBJECT_TYPE,
            object_id=previous_id,
            before={"status": APPROVED},
            after={"status": SUPERSEDED, "superseded_by": str(subject_id)},
            approval_request_id=approval_request_id,
            contract_id=UUID(str(row["contract_id"])),
        )
    transitions.apply(
        session,
        OBJECT_TYPE,
        subject_id,
        to_status=APPROVED,
        set_values={
            "approved_at": uow.now,
            "approval_request_id": approval_request_id,
            **_modified(uow),
        },
        expected_status=SUBMITTED,
    )
    current = repo.get_contract(session, UUID(str(row["contract_id"])))
    _mark_dirty(uow, UUID(str(current["combination_group_id"])))
    uow.audit(
        action=APPROVE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=subject_id,
        before={"status": SUBMITTED},
        after={"status": APPROVED, "approved_at": uow.now.isoformat()},
        approval_request_id=approval_request_id,
        contract_id=UUID(str(row["contract_id"])),
    )


def _closer(to_status: ConfigStatus, action: str) -> Callable[[UnitOfWork, UUID, UUID], None]:
    """``on_rejected`` (REJECTED) or ``on_voided`` (WITHDRAWN) of a SUBMITTED override."""

    def close(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
        session = uow.session
        row = _row(session, subject_id, for_update=True)
        if str(row["status"]) != SUBMITTED:
            return
        transitions.apply(
            session,
            OBJECT_TYPE,
            subject_id,
            to_status=to_status.value,
            set_values=_modified(uow),
            expected_status=SUBMITTED,
        )
        uow.audit(
            action=action,
            object_type=OBJECT_TYPE,
            object_id=subject_id,
            before={"status": SUBMITTED},
            after={"status": to_status.value},
            approval_request_id=approval_request_id,
            contract_id=UUID(str(row["contract_id"])),
        )

    return close


def override_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """API-S-PolicyOverride of each row (``schemas.obligations.PolicyOverrideOut``)."""
    ids = sorted(
        {UUID(str(row["obligation_id"])) for row in rows if row["obligation_id"] is not None}
    )
    keys: dict[UUID, str] = {}
    if ids:
        keys = {
            UUID(str(found_id)): str(key)
            for found_id, key in session.execute(
                select(obligation.c.id, obligation.c.obligation_key).where(obligation.c.id.in_(ids))
            )
        }
    return [
        {
            "id": row["id"],
            "contract_id": row["contract_id"],
            "obligation_id": row["obligation_id"],
            "obligation_key": None
            if row["obligation_id"] is None
            else keys.get(UUID(str(row["obligation_id"]))),
            "level": row["level"],
            "policy_key": row["policy_key"],
            "value": row["value"],
            "rationale": row["rationale"],
            "judgement_record_id": row["judgement_record_id"],
            "status": row["status"],
            "content_sha256": row["content_sha256"],
            "approval_request_id": row["approval_request_id"],
            "approved_at": row["approved_at"],
            "supersedes_id": row["supersedes_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "row_version": row["row_version"],
        }
        for row in rows
    ]


def override_out(session: Session, override_id: UUID) -> dict[str, Any]:
    """One override of a visible contract; 404 ``not-found`` otherwise."""
    row = _row(session, override_id)
    repo.get_contract(session, UUID(str(row["contract_id"])))
    return override_outs(session, [row])[0]


def get_override(ctx: RequestContext, override_id: UUID) -> dict[str, Any]:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return override_out(session, override_id)


def list_overrides[P: Page](
    ctx: RequestContext,
    *,
    contract_id: UUID | None,
    page: Callable[[Session, Select[Any]], P],
) -> tuple[P, list[dict[str, Any]]]:
    """One page of the overrides of visible contracts; ``contract`` keeps one contract's."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        visible = policy_override.join(
            contract,
            and_(
                contract.c.tenant_id == policy_override.c.tenant_id,
                contract.c.id == policy_override.c.contract_id,
            ),
        )
        statement = select(policy_override).select_from(visible)
        if contract_id is not None:
            statement = statement.where(policy_override.c.contract_id == contract_id)
        result = page(session, statement)
        return result, override_outs(session, result.items)


# --- SSP overrides -------------------------------------------------------------------------------


def request_ssp_override(
    uow: UnitOfWork, obligation_id: UUID, *, ssp_book_version_id: UUID, justification: str
) -> UUID:
    """``POST /obligations/{id}/request-ssp-override``: the ``SSP_OVERRIDE`` request id; 422
    ``validation-failed`` unless the version is APPROVED and one its requester may read — a
    version of a book of all entities, or of a book of an entity her ``ssp.read`` covers
    (``ssp.scope``; item SSP-ENTITY-SCOPE-1). A version of another entity's book answers as an
    id that names no approved version: the command confirms no id the SSP reads deny, and the
    request's summary would state that book's code and the version's label."""
    session = uow.session
    found = session.execute(
        select(obligation.c.contract_id, obligation.c.obligation_key).where(
            obligation.c.id == obligation_id
        )
    ).one_or_none()
    if found is None:
        raise Problem("not-found")
    current = repo.get_contract(session, UUID(str(found.contract_id)))
    require_for_entity(uow.ctx, CREATE_PERMISSION, _entity_of(current))
    target = session.execute(
        select(
            ssp_book_version.c.status,
            ssp_book_version.c.legacy_version_label,
            ssp_book.c.code,
            ssp_book.c.entity_id,
        )
        .select_from(
            ssp_book_version.join(
                ssp_book,
                and_(
                    ssp_book.c.tenant_id == ssp_book_version.c.tenant_id,
                    ssp_book.c.id == ssp_book_version.c.ssp_book_id,
                ),
            )
        )
        .where(ssp_book_version.c.id == ssp_book_version_id)
    ).one_or_none()
    if (
        target is None
        or str(target.status) != APPROVED
        or not ssp_scope.reaches(uow.principal, ssp_scope.READ, target.entity_id)
    ):
        raise Problem(
            "validation-failed",
            errors=[_error("ssp_book_version_id", VERSION_NOT_APPROVED, RULE_SSP_OVERRIDE)],
        )
    key = str(found.obligation_key)
    label = None if target.legacy_version_label is None else str(target.legacy_version_label)
    proposal = subjects.ssp_override_proposal(
        obligation_id=obligation_id,
        contract_id=UUID(str(current["id"])),
        obligation_key=key,
        ssp_book_version_id=ssp_book_version_id,
        version_label=label,
        justification=justification,
    )
    before = {"ssp_book_version_ids": subjects.obligation_ssp_pins(session, obligation_id)}
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.SSP_OVERRIDE,
        subject_id=obligation_id,
        summary=f"Price {current['contract_no']} {key} from {target.code} {label or ''}".rstrip(),
        impact_preview=approvals.ImpactPreview(before=before, after=proposal),
        comment=justification,
    )
    return UUID(str(request["id"]))


def _system_unit(uow: UnitOfWork) -> UnitOfWork:
    """The SYSTEM principal in the caller's transaction, stamped with the caller's instant."""
    ctx = dataclasses.replace(uow.ctx, principal=system_principal(uow.principal.tenant_id))
    system = UnitOfWork(
        ctx=ctx, session=uow.session, clock=uow.clock, keyring=uow.keyring, files=uow.files
    )
    system.now = uow.now
    return system


def _apply_ssp_override(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    """Append ``LINE_ATTRIBUTES_CHANGED`` as SYSTEM with the approved version (04 §16.2, §16.3)."""
    proposal = preview.request_proposal(uow, approval_request_id)
    session = uow.session
    contract_id = UUID(str(proposal["contract_id"]))
    # DG-KRN-DB-08 rev 1.36 (D-98 101b): the group row first, then the contract row, before the
    # appended event updates the contract (_raise_head) and marks the group dirty (_mark_dirty).
    _, locked_contract = repo.lock_group_then_contract(session, contract_id)
    # DG-KRN-APR-05 rev 1.40 (D-98 candidate 101d, R3d-b): under the group and contract locks,
    # before the first write, the proposal's base state (the obligation, its SSP pins, the proposed
    # version's status) must still hash to the basis the approver reviewed.
    approvals.assert_fresh_basis(uow, approval_request_id)
    current = session.execute(
        select(contract.c.head_stream_version, legal_entity.c.time_zone)
        .select_from(
            contract.join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == contract.c.tenant_id,
                    legal_entity.c.id == contract.c.contracting_entity_id,
                ),
            )
        )
        .where(contract.c.id == contract_id)
    ).one_or_none()
    if current is None:
        raise LookupError(
            f"contract {contract_id} of approval request {approval_request_id} is gone"
        )
    version_id = UUID(str(proposal["ssp_book_version_id"]))
    key = str(proposal["obligation_key"])
    justification = str(proposal["justification"])
    before = subjects.obligation_ssp_pins(session, subject_id)
    event = EventIn(
        event_type=ContractEventType.LINE_ATTRIBUTES_CHANGED,
        effective_date=to_entity_date(uow.now, str(current.time_zone)),
        payload=LineAttributesChangedV1(
            obligation_key=key,
            changes=LineAttributeChangesV1(
                ssp_book_version_id=version_id, justification=justification
            ),
            diff={"ssp_book_version_id": {"before": before, "after": str(version_id)}},
        ),
        obligation_keys=(key,),
        approval_request_id=approval_request_id,
    )
    system = _system_unit(uow)
    (appended,) = append_events(
        system,
        contract_id=contract_id,
        expected_stream_version=int(locked_contract["head_stream_version"]),
        events=[event],
        origin="SYSTEM",
    )
    for audit_event in system.drain_audit_events():
        uow.buffer_audit_event(audit_event)
    # The hook computes nothing: the group is left to a later computation, which records nothing
    # and is not judged. The period pin is asked for the event recorded here (PRD ERR-72;
    # supervisor ruling R-122 (j); item PIN-WINDOW-APPENDER-1); inside a decision the engine
    # answers it in its decision form.
    # Imported here: period_ends imports the approvals engine and modules of this package.
    from erev_api.domain.contracts import period_ends

    period_ends.refuse_appends_a_lock_met(uow, [UUID(str(locked_contract["combination_group_id"]))])
    uow.audit(
        action=SSP_OVERRIDE_ACTION,
        object_type=subjects.SSP_OVERRIDE_OBJECT,
        object_id=subject_id,
        before={"ssp_book_version_ids": before},
        after={"ssp_book_version_id": str(version_id)},
        approval_request_id=approval_request_id,
        detail={"event_id": str(appended["id"]), "justification": justification},
        contract_id=contract_id,
    )


def _nothing_to_undo(_uow: UnitOfWork, _subject_id: UUID, _approval_request_id: UUID) -> None:
    """A rejected or voided ``SSP_OVERRIDE`` request changed nothing."""


subjects.register_lifecycle(
    ApprovalSubjectType.POLICY_OVERRIDE,
    subjects.SubjectLifecycle(
        on_approved=_approve_override,
        on_rejected=_closer(ConfigStatus.REJECTED, REJECT_ACTION),
        on_voided=_closer(ConfigStatus.WITHDRAWN, WITHDRAW_ACTION),
    ),
)
subjects.register_lifecycle(
    ApprovalSubjectType.SSP_OVERRIDE,
    subjects.SubjectLifecycle(
        on_approved=_apply_ssp_override, on_rejected=_nothing_to_undo, on_voided=_nothing_to_undo
    ),
)
