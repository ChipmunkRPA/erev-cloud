"""Contract combination and combination suggestions (04 §15.3 API-R-28, §16.14, T-CON-03, T-CON-04,
T-CON-19, table 15.4-C ``COMBINATION_SUGGESTED``, E-95, table 3.4-R; ENGINE_SPEC S02-R-09, S02-R-10,
S02-R-14; POLICIES POL-016; PRD BR-CON-03, IMP-89, §2.5 routing row ``COMBINATION_GROUP``; 03
REQ-CON-009, REQ-CON-010, REQ-CON-019; BUILD_SPEC CTR-8).

Suggestions (S02-R-14). ``raise_suggestions`` runs for a booked contract c: every other contract d
of the same customer or related-party group whose inception is within
``combination.detection_window_days`` of c's, or whose external id appears in c's ``document_ref``
or custom attributes, and that is not in c's group, raises one ``COMBINATION_SUGGESTED`` item
(source ``ENGINE``, severity ``WARNING``, disposition ``remediable``, ``dedupe_key``
``ENGINE:COMBINATION_SUGGESTED:<ascending contract ids joined by ,>``). Window 0 disables detection.
A suggestion is dismissed with a rationale of at least 10 characters (``DISMISSED``, ``resolution``,
audit ``exception_item.dismiss``).

Combination (S02-R-09, S02-R-10). ``POST /combination-groups`` proposes a group in one currency
(422 ``REQ-CON-019`` otherwise). [J] L4-1-Q-16: T-CON-03 has no member column for a proposal, so
the proposal is recorded as a ``COMBINATION`` judgement record of the group whose questionnaire
names ``action`` and ``contract_ids`` (T-CON-19 allows evidence members); the group points at it
through ``judgement_record_id``. ``/submit`` moves the group PROPOSED → SUBMITTED and the record
DRAFT → SUBMITTED, and routes ``COMBINATION_GROUP`` (``contract.approve``). On approval the SYSTEM
principal, on behalf of the preparer, appends ``COMBINATION_CHANGED`` ``JOIN`` on every member,
ends each current membership at the event's ``recorded_at`` and opens one in the group, the group
becomes APPROVED → APPLIED, the record REVIEWED, and the group is computed from its inception,
posting the differences in the first open period.

A proposal that was not submitted is given up by ``/discard`` (04 rev 1.289; item
COMBINATION-PROPOSAL-DISCARD-1): the group PROPOSED → VOIDED and its record DRAFT → VOIDED in
one transaction, for a holder of what the proposal's ``POST`` asked. The record of a group is
edited by nobody, so a correction is a discard and a new proposal.

Uncombining is an approved error correction: ``/submit`` of an APPLIED group with
``leave_contract_ids`` needs ``reason_code`` ``DATA_CORRECTION`` (422 ``REASON_CODE_NOT_ALLOWED``
otherwise). On approval each leaving contract receives ``COMBINATION_CHANGED`` ``LEAVE``, rejoins
its own singleton group ``CG-<contract_no>`` and is computed from its own inception; the remaining
members are computed again. Rejection and void close the proposal (L4-1-Q-16).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Final, Literal
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import ColumnElement, Select, and_, exists, func, insert, or_, select, update
from sqlalchemy.orm import Session

from erev_api import numbering
from erev_api.approvals import engine as approvals
from erev_api.approvals.subjects import (
    SubjectLifecycle,
    judgement_record_content,
    register_lifecycle,
)
from erev_api.audit import writer as audit_writer
from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.principal import Principal, system_principal
from erev_api.clock import to_entity_date
from erev_api.db import new_id, transitions
from erev_api.db.tables import (
    approval_request,
    combination_group,
    combination_group_member,
    contract,
    customer,
    exception_item,
    judgement_record,
    legal_entity,
    related_party_group,
)
from erev_api.domain.contracts import bundles, period_ends, repo
from erev_api.domain.contracts.compute_job import (
    ENGINE_BUDGET_SECONDS,
    OBLIGATION_BUDGET,
    compute_group,
    defer_compute,
    obligation_count,
)
from erev_api.domain.imports.exceptions import (
    OPEN_STATUSES,
    RaisedItem,
    dedupe_key,
    item_contracts,
    raise_exception_item,
    readable,
    severity_of,
)
from erev_api.domain.policies import judgements
from erev_api.enums import (
    ApprovalSubjectType,
    CombinationStatus,
    ContractEventType,
    ContractStatus,
    ExceptionSource,
    ExceptionStatus,
    JudgementStatus,
    JudgementTopic,
)
from erev_api.events import step1
from erev_api.events.payloads import CombinationChangedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.problems import Problem, ProblemError
from erev_api.registry import resolve as registry
from erev_api.schemas.combinations import (
    CODIFICATION_CRITERIA,
    CombinationGroupCreateIn,
    CombinationGroupDetailOut,
    CombinationGroupSubmitIn,
    CombinationProposalOut,
    CombinationSuggestionOut,
    SuggestionDismissIn,
)
from erev_api.schemas.common import RefOut
from erev_api.schemas.judgements import JudgementCreateIn
from erev_api.uow import UnitOfWork

__all__ = [
    "CREATE_PERMISSION",
    "SUGGESTED",
    "create_group",
    "discard_group",
    "dismiss_suggestion",
    "get_group",
    "group_outs",
    "groups_statement",
    "raise_suggestions",
    "submit_group",
    "suggestion_outs",
    "suggestions_read_by",
    "suggestions_statement",
]

CREATE_PERMISSION: Final = "contract.create"
SUGGESTED: Final = "COMBINATION_SUGGESTED"
WINDOW_SETTING: Final = "combination.detection_window_days"
CONTRACT_SERIES: Final = "CONTRACT"
GROUP_PREFIX: Final = "CG-"
GROUP_OBJECT: Final = "combination_group"
MEMBER_OBJECT: Final = "combination_group_member"
ITEM_OBJECT: Final = "exception_item"
DISMISS_ACTION: Final = "exception_item.dismiss"
GROUP_CREATE_ACTION: Final = "combination_group.create"
MEMBER_CREATE_ACTION: Final = "combination_group_member.create"
LEAVE_REASON: Final = "DATA_CORRECTION"
RULE_CURRENCY: Final = "REQ-CON-019"
RULE_COMBINATION: Final = "REQ-CON-009"
RULE_MEMBER: Final = "T-CON-04"
RULE_REASON: Final = "REASON_CODE_NOT_ALLOWED"
# PRD IMP-89.
SUGGESTION_MESSAGE: Final = (
    "{first} and {second} belong to the same customer group and started within {days} days of "
    "each other. Combine them or dismiss the suggestion with a rationale."
)
SUGGESTION_HINT: Final = (
    "Combine the contracts through a combination group request, or dismiss the suggestion with a "
    "rationale."
)
ONE_CURRENCY: Final = "Contracts in one combination group share one transaction currency."
REPEATED: Final = "Name each contract once."
VOIDED_MEMBER: Final = "A voided contract cannot be combined."
ALREADY_COMBINED: Final = "The contract already belongs to a combination group."
NOT_OPEN: Final = "Only an open suggestion can be dismissed."
NOT_PROPOSED: Final = "Only a proposed group or an applied group with leaving members is submitted."
NOT_MEMBER: Final = "The contract is not a member of this group."
PROPOSAL_CHANGED: Final = (
    "The group's proposal changed while the request was being checked. Reload to see the "
    "latest version, then try again."
)
LEAVE_ONLY_CORRECTION: Final = "A contract leaves a combination only as a data correction."
# Item COMBINATION-PROPOSAL-DISCARD-1 (04 T-CON-03, E-95 rev 1.289): the two refusals of a
# discard, each with what the operator does in that state.
AWAITS_APPROVAL: Final = (
    "This combination waits for approval. Withdraw its request, or have it rejected."
)
NOT_DISCARDABLE: Final = "Only a proposed combination that is not submitted can be discarded."
# Supervisor ruling R-77 (5) (item STEP1-BOOK-ADOPTION-1): a contract behind the not-a-contract
# gate is assessed in the books its own entity keeps and in no other.
RULE_STEP1: Final = "REQ-POL-008"
GATED_MEMBER: Final = (
    "{contract} is assessed as not a contract. In this group it would also be computed in book "
    "{books}, which {entity} does not keep and where it has no assessment. Combine it after it "
    "is activated."
)


@dataclass(frozen=True, slots=True)
class _Proposal:
    record_id: UUID
    action: Literal["JOIN", "LEAVE"]
    contract_ids: tuple[UUID, ...]
    status: JudgementStatus


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _created(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _failed(errors: Sequence[ProblemError]) -> Problem:
    detail = errors[0].message if len(errors) == 1 else f"{len(errors)} fields need attention."
    return Problem("validation-failed", detail, errors=errors)


def _ordered(ids: Sequence[UUID]) -> list[UUID]:
    """04 B3-D14: ascending contract ids."""
    return sorted(ids, key=str)


# --- suggestions (S02-R-14) ----------------------------------------------------------------------


def _references(row: Mapping[str, Any]) -> list[str]:
    texts = [str(row["document_ref"] or "")]
    for value in dict(row["custom_attributes"] or {}).values():
        if isinstance(value, str):
            texts.append(value)
    return texts


def raise_suggestions(uow: UnitOfWork, contract_id: UUID) -> list[RaisedItem]:
    """S02-R-14 for a booked contract: raise one ``COMBINATION_SUGGESTED`` item per candidate."""
    session = uow.session
    window = int(registry.setting(session, WINDOW_SETTING, known_at=uow.now))
    if window <= 0:
        return []
    booked = repo.get_contract(session, contract_id)
    party_group = session.execute(
        select(customer.c.related_party_group_id).where(customer.c.id == booked["customer_id"])
    ).scalar_one_or_none()
    same_party: ColumnElement[bool] = contract.c.customer_id == booked["customer_id"]
    if party_group is not None:
        members = select(customer.c.id).where(customer.c.related_party_group_id == party_group)
        same_party = same_party | contract.c.customer_id.in_(members)
    candidates = session.execute(
        select(contract).where(
            contract.c.id != contract_id,
            contract.c.status != ContractStatus.VOIDED.value,
            contract.c.combination_group_id != booked["combination_group_id"],
            same_party,
        )
    ).mappings()
    references = _references(booked)
    inception: date = booked["inception_date"]
    raised: list[RaisedItem] = []
    for other in sorted(candidates, key=lambda row: str(row["external_id"])):
        within = abs((other["inception_date"] - inception).days) <= window
        cited = any(str(other["external_id"]) in text for text in references)
        if not (within or cited):
            continue
        pair: dict[UUID, Mapping[str, Any]] = {
            UUID(str(booked["id"])): booked,
            UUID(str(other["id"])): dict(other),
        }
        ids = _ordered(list(pair))
        external_ids = [str(pair[value]["external_id"]) for value in ids]
        entities = {pair[value]["contracting_entity_id"] for value in ids}
        raised.append(
            raise_exception_item(
                uow,
                source=ExceptionSource.ENGINE,
                code=SUGGESTED,
                severity=severity_of("WARNING"),
                message=SUGGESTION_MESSAGE.format(
                    first=external_ids[0], second=external_ids[1], days=window
                ),
                dedupe=dedupe_key(ExceptionSource.ENGINE, SUGGESTED, ",".join(map(str, ids))),
                suggestion=SUGGESTION_HINT,
                business_key=",".join(external_ids),
                source_payload={
                    "contract_ids": [str(value) for value in ids],
                    "contract_external_ids": external_ids,
                    "inception_dates": [pair[value]["inception_date"].isoformat() for value in ids],
                    "related_party_group_id": None if party_group is None else str(party_group),
                    "detection_window_days": window,
                    "cross_reference": cited,
                },
                contract_id=contract_id,
                entity_id=UUID(str(next(iter(entities)))) if len(entities) == 1 else None,
            )
        )
    return raised


def suggestions_statement(contract_id: UUID | None) -> Select[Any]:
    """The open ``COMBINATION_SUGGESTED`` items naming a contract, whoever asks."""
    statement = select(exception_item).where(
        exception_item.c.code == SUGGESTED, exception_item.c.status.in_(OPEN_STATUSES)
    )
    if contract_id is not None:
        statement = statement.where(
            exception_item.c.source_payload.contains({"contract_ids": [str(contract_id)]})
        )
    return statement


def suggestions_read_by(principal: Principal, contract_id: UUID | None) -> Select[Any]:
    """``GET /combination-suggestions``: ``suggestions_statement`` for a member who reads the
    items by the queue's rule (``exceptions.readable``; 04 T-IMP-05 "An item that names no
    entity: who reads it", rev 1.218). A suggestion to combine contracts of two entities names
    neither entity and is read by a member whose ``contract.read`` covers both; until item
    EXC-IMPORT-SCOPE-1 a reader of one of them was told the other's contract."""
    return suggestions_statement(contract_id).where(readable(principal))


def suggestion_outs(
    session: Session, rows: Sequence[Mapping[str, Any]]
) -> list[CombinationSuggestionOut]:
    group_ids = {
        UUID(str(payload["related_party_group_id"]))
        for row in rows
        if (payload := row["source_payload"] or {}).get("related_party_group_id")
    }
    groups = (
        {
            UUID(str(found.id)): RefOut(id=found.id, code=found.code, name=found.name)
            for found in session.execute(
                select(
                    related_party_group.c.id, related_party_group.c.code, related_party_group.c.name
                ).where(related_party_group.c.id.in_(sorted(group_ids)))
            )
        }
        if group_ids
        else {}
    )
    found: list[CombinationSuggestionOut] = []
    for row in rows:
        payload = dict(row["source_payload"] or {})
        group_id = payload.get("related_party_group_id")
        found.append(
            CombinationSuggestionOut(
                id=row["id"],
                contract_ids=[UUID(str(value)) for value in payload.get("contract_ids", ())],
                contract_external_ids=[
                    str(value) for value in payload.get("contract_external_ids", ())
                ],
                related_party_group=None if group_id is None else groups.get(UUID(str(group_id))),
                inception_dates=[
                    date.fromisoformat(str(value)) for value in payload.get("inception_dates", ())
                ],
                detection_window_days=int(payload.get("detection_window_days", 0)),
                status=ExceptionStatus(_text(row["status"])),
                created_at=row["created_at"],
            )
        )
    return found


def dismiss_suggestion(
    uow: UnitOfWork, *, item_id: UUID, body: SuggestionDismissIn
) -> CombinationSuggestionOut:
    """``POST /combination-suggestions/{id}/dismiss``: DISMISSED with the rationale (B3-D14)."""
    session = uow.session
    row = (
        session.execute(
            select(exception_item)
            .where(
                exception_item.c.id == item_id,
                exception_item.c.code == SUGGESTED,
                # who cannot read a suggestion does not dismiss it: 404, as an unknown id
                readable(uow.principal),
            )
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    require_for_entity(uow.ctx, CREATE_PERMISSION, row["entity_id"])
    if row["entity_id"] is None:
        # a suggestion across two entities: the permission for the entity of each contract it
        # names, not for any entity (04 API-R-28 rev 1.218; item EXC-IMPORT-SCOPE-1)
        for entity_id in session.scalars(
            select(contract.c.contracting_entity_id)
            .where(contract.c.id.in_(item_contracts(session, dict(row))))
            .distinct()
        ):
            require_for_entity(uow.ctx, CREATE_PERMISSION, UUID(str(entity_id)))
    status = _text(row["status"])
    if status not in OPEN_STATUSES:
        raise Problem(
            "invalid-transition",
            NOT_OPEN,
            errors=[ProblemError(field="status", rule_id=transitions.RULE_ID, message=NOT_OPEN)],
        )
    principal = uow.principal
    session.execute(
        update(exception_item)
        .where(exception_item.c.tenant_id == principal.tenant_id, exception_item.c.id == item_id)
        .values(
            status=ExceptionStatus.DISMISSED.value,
            resolution=body.rationale,
            resolved_at=uow.now,
            resolved_by=principal.id,
            resolved_by_kind=principal.kind.value,
            row_version=exception_item.c.row_version + 1,
            **_stamps(uow),
        )
    )
    uow.audit(
        action=DISMISS_ACTION,
        object_type=ITEM_OBJECT,
        object_id=item_id,
        before={"status": status},
        after={"status": ExceptionStatus.DISMISSED.value, "resolution": body.rationale},
        contract_ids=item_contracts(session, dict(row)),
    )
    updated = (
        session.execute(select(exception_item).where(exception_item.c.id == item_id))
        .mappings()
        .one()
    )
    (item,) = suggestion_outs(session, [dict(updated)])
    return item


# --- groups --------------------------------------------------------------------------------------


GroupRows = dict[UUID, dict[str, Any]]
Between = Callable[[GroupRows], object]


def _observe(session: Session, contract_ids: Iterable[UUID]) -> list[dict[str, Any]]:
    """The contracts read without locks: which groups to lock, and the group each contract must
    still belong to under the locks (equality; D-98 candidate 101c)."""
    return [repo.get_contract(session, contract_id) for contract_id in contract_ids]


def _expected(rows: Iterable[Mapping[str, Any]]) -> dict[UUID, UUID]:
    return {UUID(str(row["id"])): UUID(str(row["combination_group_id"])) for row in rows}


def _lock_groups_then_contracts(
    session: Session,
    *,
    group_ids: Iterable[UUID],
    expected: Mapping[UUID, UUID],
    between: Between | None = None,
) -> tuple[GroupRows, list[dict[str, Any]]]:
    """DG-KRN-DB-08 rev 1.36 (D-98 candidates 101b, 101c): every ``combination_group`` row this
    unit of work will lock or update — ``group_ids`` (the target, the leave singletons) and each
    contract's observed group (``expected``) — ``FOR UPDATE`` in ONE ascending id order, the target
    included (never taken first); then ``between`` (the proposal record); then the contracts
    ``FOR UPDATE`` in ascending id order, each contract's group under the lock EQUAL to the one
    observed at the unlocked read (a difference is refused ``precondition-failed``, never processed
    on a group that was not locked). Re-locking a row this transaction holds is a no-op. Returns
    ``({group id: row}, [contract rows by id])``."""
    groups = {
        gid: repo.lock_group(session, gid) for gid in sorted({*group_ids, *expected.values()})
    }
    if between is not None:
        between(groups)
    rows = [repo.get_contract(session, cid, for_update=True) for cid in sorted(expected)]
    for row in rows:
        if UUID(str(row["combination_group_id"])) != expected[UUID(str(row["id"]))]:
            raise Problem("precondition-failed", repo.REGROUPED)
    return groups, rows


def _visible_contracts(
    uow: UnitOfWork,
    contract_ids: Sequence[UUID],
    *,
    target: UUID | None = None,
    between: Between | None = None,
) -> tuple[GroupRows, list[dict[str, Any]]]:
    """The proposal's contracts, each visible to the caller, locked on the one order (DG-KRN-DB-08
    rev 1.36): their current groups — read without locks — and the submit ``target`` in one
    ascending id order, ``between`` (the proposal record), then the contracts in ascending id order
    with their groups re-verified for equality. Returns the locked group rows and contract rows."""
    session = uow.session
    expected = _expected(_observe(session, contract_ids))
    groups, rows = _lock_groups_then_contracts(
        session,
        group_ids=() if target is None else (target,),
        expected=expected,
        between=between,
    )
    for row in rows:
        require_for_entity(uow.ctx, CREATE_PERMISSION, UUID(str(row["contracting_entity_id"])))
    return groups, rows


def _gated_member_errors(uow: UnitOfWork, rows: Sequence[Mapping[str, Any]]) -> list[ProblemError]:
    """Ruling R-77 (5): a contract behind the not-a-contract gate (header NOT_A_CONTRACT) does not
    join a group in which it would be computed in a book its own entity does not keep. The
    combined group is computed in every book any member's group is computed in today (the books
    of the members' contracting entities and of the performing entities of their lines:
    ``bundles.build``); in a book the contract's own entity does not keep there is no assessment,
    so the replayed gate would find the book not assessed and Table 2.2-A would ACTIVATE the
    contract there — recognition with no approval of an activation. The books are read under the
    shared ``book`` lock (ruling R-80), after the group and contract locks the caller holds."""
    gated = [
        (index, row)
        for index, row in enumerate(rows)
        if _text(row["status"]) == ContractStatus.NOT_A_CONTRACT.value
    ]
    if not gated:
        return []
    session = uow.session
    step1.lock_books(session)
    computed: set[str] = set()
    for row in rows:
        bundle = bundles.build(session, UUID(str(row["combination_group_id"])), uow.now)
        computed |= {str(book.book_code) for book in bundle.books}
    errors: list[ProblemError] = []
    for index, row in gated:
        entity_id = UUID(str(row["contracting_entity_id"]))
        other = sorted(computed - set(step1.enabled_books(session, entity_id)))
        if other:
            entity_code = session.execute(
                select(legal_entity.c.code).where(legal_entity.c.id == entity_id)
            ).scalar_one()
            errors.append(
                ProblemError(
                    field=f"contract_ids.{index}",
                    rule_id=RULE_STEP1,
                    message=GATED_MEMBER.format(
                        contract=row["external_id"], books=", ".join(other), entity=entity_code
                    ),
                )
            )
    return errors


def _member_errors(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[ProblemError]:
    errors: list[ProblemError] = []
    currencies = {str(row["transaction_currency"]).strip() for row in rows}
    if len(currencies) > 1:
        errors.append(
            ProblemError(field="contract_ids", rule_id=RULE_CURRENCY, message=ONE_CURRENCY)
        )
    for index, row in enumerate(rows):
        if _text(row["status"]) == ContractStatus.VOIDED.value:
            errors.append(
                ProblemError(
                    field=f"contract_ids.{index}", rule_id="T-CON-01", message=VOIDED_MEMBER
                )
            )
        singleton = session.execute(
            select(combination_group.c.is_singleton).where(
                combination_group.c.id == row["combination_group_id"]
            )
        ).scalar_one()
        if not singleton:
            errors.append(
                ProblemError(
                    field=f"contract_ids.{index}", rule_id=RULE_MEMBER, message=ALREADY_COMBINED
                )
            )
    return errors


def _proposal(session: Session, group_id: UUID, *, lock: bool = False) -> _Proposal | None:
    """The pending proposal of the group: the record its command wrote (item
    COMBINATION-PROPOSAL-RECORD-1; 04 T-CON-19 rev 1.283).

    - A combination: the record the group names (T-CON-03 ``judgement_record_id``, set by
      ``create_group``), while the group is PROPOSED or SUBMITTED and the record DRAFT or
      SUBMITTED.
    - A leave from an APPLIED group: the group's SUBMITTED record of action ``LEAVE`` that
      carries no approval request of its own — ``submit_group`` writes and submits it in
      the transaction that routes the group's request (``_submit_record`` sets none), and
      one request is pending per subject, so there is at most one.

    Never "the latest record of the topic": until the item a record somebody else wrote
    for the group — by hand, which ``POST /judgements`` no longer takes — stood in for the
    proposal here and in the content the approval hashes
    (``approvals.subjects.combination_group_content`` reads by the same rule)."""
    record = judgement_record.c
    named = (
        select(combination_group.c.judgement_record_id)
        .where(
            combination_group.c.id == group_id,
            combination_group.c.status.in_(
                [CombinationStatus.PROPOSED.value, CombinationStatus.SUBMITTED.value]
            ),
        )
        .scalar_subquery()
    )
    applied = exists().where(
        combination_group.c.id == group_id,
        combination_group.c.status == CombinationStatus.APPLIED.value,
        combination_group.c.is_singleton.is_(False),
    )
    statement = (
        select(record.id, record.questionnaire, record.status)
        .where(
            record.subject_type == GROUP_OBJECT,
            record.subject_id == group_id,
            record.topic == JudgementTopic.COMBINATION.value,
            or_(
                and_(
                    record.id == named,
                    record.status.in_(
                        [JudgementStatus.DRAFT.value, JudgementStatus.SUBMITTED.value]
                    ),
                ),
                and_(
                    record.status == JudgementStatus.SUBMITTED.value,
                    record.questionnaire.contains({"action": "LEAVE"}),
                    record.approval_request_id.is_(None),
                    applied,
                ),
            ),
        )
        .order_by(record.judgement_no.desc())
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update()
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        return None
    questionnaire = dict(row["questionnaire"] or {})
    action: Literal["JOIN", "LEAVE"] = "LEAVE" if questionnaire.get("action") == "LEAVE" else "JOIN"
    return _Proposal(
        record_id=UUID(str(row["id"])),
        action=action,
        contract_ids=tuple(UUID(str(value)) for value in questionnaire.get("contract_ids", ())),
        status=JudgementStatus(_text(row["status"])),
    )


def _record_proposal(
    uow: UnitOfWork,
    group_id: UUID,
    *,
    action: Literal["JOIN", "LEAVE"],
    contract_rows: Sequence[Mapping[str, Any]],
    criterion: str | None,
    rationale: str,
) -> UUID:
    ids = _ordered([UUID(str(row["id"])) for row in contract_rows])
    external_ids = sorted(str(row["external_id"]) for row in contract_rows)
    codification = next(
        (name for name, literal in CODIFICATION_CRITERIA.items() if literal == criterion), None
    )
    verb = "Combine" if action == "JOIN" else "Separate"
    created = judgements.create_judgement(
        uow,
        body=JudgementCreateIn(
            topic=JudgementTopic.COMBINATION,
            subject_type="combination_group",
            subject_id=group_id,
            conclusion=f"{verb} {', '.join(external_ids)}.",
            rationale=rationale,
            codification_refs=[] if codification is None else [codification],
            questionnaire={
                "action": action,
                "contract_ids": [str(value) for value in ids],
                **({} if criterion is None else {"criterion": criterion}),
            },
        ),
        proposal_of_group=True,  # the one writer of a group's COMBINATION record
    )
    return created.id


def create_group(uow: UnitOfWork, *, body: CombinationGroupCreateIn) -> CombinationGroupDetailOut:
    """``POST /combination-groups``: a PROPOSED group and its ``COMBINATION`` record."""
    if len(set(body.contract_ids)) != len(body.contract_ids):
        raise _failed(
            [ProblemError(field="contract_ids", rule_id=RULE_COMBINATION, message=REPEATED)]
        )
    session = uow.session
    _, rows = _visible_contracts(uow, body.contract_ids)
    errors = _member_errors(session, rows) or _gated_member_errors(uow, rows)
    if errors:
        raise _failed(errors)
    criterion = CODIFICATION_CRITERIA[body.criterion]
    group_id = new_id()
    values = {
        "code": f"{GROUP_PREFIX}{numbering.next_number(uow, CONTRACT_SERIES)}",
        "is_singleton": False,
        "status": CombinationStatus.PROPOSED.value,
        "transaction_currency": str(rows[0]["transaction_currency"]).strip(),
        "criterion": criterion,
        "rationale": body.rationale,
        "inception_date": min(row["inception_date"] for row in rows),
    }
    session.execute(
        insert(combination_group).values(
            tenant_id=uow.principal.tenant_id,
            id=group_id,
            **values,
            **_created(uow),
            **_stamps(uow),
        )
    )
    record_id = _record_proposal(
        uow,
        group_id,
        action="JOIN",
        contract_rows=rows,
        criterion=criterion,
        rationale=body.rationale,
    )
    transitions.apply(
        session,
        GROUP_OBJECT,
        group_id,
        to_status=None,
        set_values={"judgement_record_id": record_id, **_stamps(uow)},
    )
    uow.audit(
        action=GROUP_CREATE_ACTION,
        object_type=GROUP_OBJECT,
        object_id=group_id,
        object_version="1",
        after={
            **values,
            "inception_date": values["inception_date"].isoformat(),
            "contract_ids": [str(value) for value in _ordered(body.contract_ids)],
            "judgement_record_id": str(record_id),
        },
        contract_ids=body.contract_ids,
    )
    return get_group(session, group_id)


def _group_audit(
    uow: UnitOfWork, group_id: UUID, before: str, after: str, *, contract_ids: Sequence[UUID]
) -> None:
    """A status event of a group; it names the contracts of the proposal being decided (04
    T-PLT-19 ``detail.contract_ids``)."""
    uow.audit(
        action=f"{GROUP_OBJECT}.{after.lower()}",
        object_type=GROUP_OBJECT,
        object_id=group_id,
        before={"status": before},
        after={"status": after},
        contract_ids=contract_ids,
    )


def _submit_record(uow: UnitOfWork, record_id: UUID) -> None:
    session = uow.session
    content = judgement_record_content(session, record_id)
    record = transitions.apply(
        session,
        "judgement_record",
        record_id,
        to_status=JudgementStatus.SUBMITTED.value,
        expected_status=JudgementStatus.DRAFT.value,
        set_values={"content_sha256": sha256_hex(content), **_stamps(uow)},
    )
    uow.audit(
        action="judgement_record.submitted",
        object_type="judgement_record",
        object_id=record_id,
        before={"status": JudgementStatus.DRAFT.value},
        after={"status": JudgementStatus.SUBMITTED.value},
        contract_ids=judgements.record_contracts(record),
    )


def submit_group(
    uow: UnitOfWork, *, group_id: UUID, body: CombinationGroupSubmitIn
) -> CombinationGroupDetailOut:
    """``POST /combination-groups/{id}/submit``: route a combination or a leave (L4-1-Q-16).

    DG-KRN-DB-08 rev 1.36 (D-98 candidate 101c): the group is read without a lock to choose the
    branch; the branch then locks every group it touches in one ascending id order (the target
    included), the proposal record between, then the contracts — and re-checks the status, the
    proposal and the membership under the locks."""
    session = uow.session
    preview = repo.read_group(session, group_id)  # 404 for a group the session does not read
    status = _text(preview["status"])
    group: dict[str, Any] = preview
    if status == CombinationStatus.PROPOSED.value and body.leave_contract_ids is None:
        proposal = _proposal(session, group_id)
        if proposal is None or proposal.action != "JOIN":
            raise Problem("invalid-transition", NOT_PROPOSED)

        def lock_proposal(groups: GroupRows) -> None:
            nonlocal group
            group = groups[group_id]
            if _text(group["status"]) != status:
                raise Problem("invalid-transition", NOT_PROPOSED)
            if _proposal(session, group_id, lock=True) != proposal:
                raise Problem("precondition-failed", PROPOSAL_CHANGED)

        _, rows = _visible_contracts(
            uow, proposal.contract_ids, target=group_id, between=lock_proposal
        )
        errors = _member_errors(session, rows) or _gated_member_errors(uow, rows)
        if errors:
            raise _failed(errors)
        transitions.apply(
            session,
            GROUP_OBJECT,
            group_id,
            to_status=CombinationStatus.SUBMITTED.value,
            expected_status=status,
            set_values=_stamps(uow),
        )
        _group_audit(
            uow,
            group_id,
            status,
            CombinationStatus.SUBMITTED.value,
            contract_ids=proposal.contract_ids,
        )
        _submit_record(uow, proposal.record_id)
        summary = f"Combine {len(rows)} contracts in {group['code']}"
    elif (
        status == CombinationStatus.APPLIED.value
        and not preview["is_singleton"]
        and body.leave_contract_ids is not None
    ):
        if body.reason_code is None or body.reason_code.value != LEAVE_REASON:
            raise _failed(
                [
                    ProblemError(
                        field="reason_code", rule_id=RULE_REASON, message=LEAVE_ONLY_CORRECTION
                    )
                ]
            )
        leaving = list(body.leave_contract_ids)

        def check_members(groups: GroupRows) -> None:
            nonlocal group
            group = groups[group_id]
            if _text(group["status"]) != status or group["is_singleton"]:
                raise Problem("invalid-transition", NOT_PROPOSED)
            current = _current_members(session, [group_id]).get(group_id, [])
            errors = [
                ProblemError(
                    field=f"leave_contract_ids.{index}", rule_id=RULE_MEMBER, message=NOT_MEMBER
                )
                for index, value in enumerate(leaving)
                if value not in current
            ]
            if errors:
                raise _failed(errors)

        _, rows = _visible_contracts(uow, leaving, target=group_id, between=check_members)
        record_id = _record_proposal(
            uow,
            group_id,
            action="LEAVE",
            contract_rows=rows,
            criterion=None,
            rationale=body.comment or "Uncombine as a data correction.",
        )
        _submit_record(uow, record_id)
        summary = f"Separate {len(rows)} contracts from {group['code']}"
    else:
        raise Problem("invalid-transition", NOT_PROPOSED)
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.COMBINATION_GROUP,
        subject_id=group_id,
        summary=summary,
        comment=body.comment,
        reason_code=None if body.reason_code is None else body.reason_code.value,
    )
    if _text(request["status"]) == "PENDING":
        request_id = UUID(str(request["id"]))
        transitions.apply(
            session,
            GROUP_OBJECT,
            group_id,
            to_status=None,
            set_values={"approval_request_id": request_id, **_stamps(uow)},
        )
    return get_group(session, group_id)


# --- the discard of a proposal -------------------------------------------------------------------


def _refuse_discard(status: str) -> None:
    """409 ``invalid-transition`` unless the group is PROPOSED: a SUBMITTED group is given up
    through its request, and every other state has no proposal to give up."""
    if status == CombinationStatus.PROPOSED.value:
        return
    message = AWAITS_APPROVAL if status == CombinationStatus.SUBMITTED.value else NOT_DISCARDABLE
    raise Problem(
        "invalid-transition",
        message,
        errors=[ProblemError(field="status", rule_id=transitions.RULE_ID, message=message)],
    )


def _named_contracts(session: Session, group: Mapping[str, Any]) -> tuple[UUID, ...]:
    """The contracts the record the group names lists, whatever that record's status: the
    contracts ``create_group`` asked its permission for."""
    if group["judgement_record_id"] is None:
        return ()
    questionnaire = session.execute(
        select(judgement_record.c.questionnaire).where(
            judgement_record.c.id == group["judgement_record_id"]
        )
    ).scalar_one_or_none()
    return tuple(UUID(str(value)) for value in (questionnaire or {}).get("contract_ids", ()))


def discard_group(uow: UnitOfWork, *, group_id: UUID) -> CombinationGroupDetailOut:
    """``POST /combination-groups/{id}/discard`` (item COMBINATION-PROPOSAL-DISCARD-1; 04
    T-CON-03, E-95 and API-R-28 rev 1.289; PRD SM-10, ACT-04): a proposal that was not
    submitted is given up — the group PROPOSED → VOIDED and its record DRAFT → VOIDED in
    this transaction. A correction is a discard and a new proposal.

    WHO: what the proposal's ``POST`` asked, and not its author alone — a proposal whose
    author has left must not stand for good: ``contract.create`` for the contracting entity
    of every contract the proposal names, each read by the caller (404 otherwise), and
    ``judgement.create`` held for any entity, the guard of the record's own writer and of
    its discard (``judgements.discard_judgement``).

    None of the members' checks of a submission runs: a proposal that names a contract
    since voided, or since combined elsewhere, could be neither submitted nor given up
    and is discarded here. The group's row is locked first, then its record
    (DG-KRN-DB-08), and the status and the proposal are read again under the locks: no
    ``If-Match``, as the group's other commands have none. Refused, 409
    ``invalid-transition`` on ``status``: a SUBMITTED group — its request is withdrawn
    or rejected — and every other state, a repeat on a VOIDED group included. A record
    the group names that is no longer a draft is left as it is."""
    session = uow.session
    preview = repo.read_group(session, group_id)  # 404 for a group the session does not read
    _refuse_discard(_text(preview["status"]))
    proposal = _proposal(session, group_id)
    for row in _observe(session, _named_contracts(session, preview)):
        require_for_entity(uow.ctx, CREATE_PERMISSION, UUID(str(row["contracting_entity_id"])))
    require_for_entity(uow.ctx, judgements.CREATE_PERMISSION, None)
    group = repo.lock_group(session, group_id)
    _refuse_discard(_text(group["status"]))
    if _proposal(session, group_id, lock=True) != proposal:
        raise Problem("precondition-failed", PROPOSAL_CHANGED)
    transitions.apply(
        session,
        GROUP_OBJECT,
        group_id,
        to_status=CombinationStatus.VOIDED.value,
        expected_status=CombinationStatus.PROPOSED.value,
        set_values=_stamps(uow),
    )
    _group_audit(
        uow,
        group_id,
        CombinationStatus.PROPOSED.value,
        CombinationStatus.VOIDED.value,
        contract_ids=_named_contracts(session, group),
    )
    if proposal is not None and proposal.status is JudgementStatus.DRAFT:
        judgements.discard_judgement(
            uow,
            judgement_id=proposal.record_id,
            proposal_of_group=True,  # the one caller that voids a group's proposal
        )
    return get_group(session, group_id)


# --- approval lifecycle --------------------------------------------------------------------------


def _system_unit(uow: UnitOfWork, preparer: UUID | None) -> UnitOfWork:
    ctx = dataclasses.replace(
        uow.ctx, principal=system_principal(uow.principal.tenant_id, on_behalf_of_id=preparer)
    )
    system = UnitOfWork(
        ctx=ctx, session=uow.session, clock=uow.clock, keyring=uow.keyring, files=uow.files
    )
    system.now = uow.now
    return system


def _change(
    system: UnitOfWork, contract_row: Mapping[str, Any], payload: CombinationChangedV1
) -> Mapping[str, Any]:
    session = system.session
    zone = session.execute(
        select(legal_entity.c.time_zone).where(
            legal_entity.c.id == contract_row["contracting_entity_id"]
        )
    ).scalar_one()
    (event,) = append_events(
        system,
        contract_id=UUID(str(contract_row["id"])),
        expected_stream_version=int(contract_row["head_stream_version"]),
        events=[
            EventIn(
                event_type=ContractEventType.COMBINATION_CHANGED,
                effective_date=to_entity_date(system.now, str(zone)),
                payload=payload,
            )
        ],
        origin="SYSTEM",
    )
    return event


def _move(
    uow: UnitOfWork, contract_id: UUID, target_group_id: UUID, event: Mapping[str, Any]
) -> None:
    """End the current membership at the event's ``recorded_at`` and open one in the target."""
    session = uow.session
    current = repo.current_member(session, contract_id)
    if current is not None:
        transitions.apply(
            session,
            MEMBER_OBJECT,
            UUID(str(current["id"])),
            to_status=None,
            set_values={"valid_to_known_at": event["recorded_at"], "leave_event_id": event["id"]},
        )
    member_id = new_id()
    session.execute(
        insert(combination_group_member).values(
            tenant_id=uow.principal.tenant_id,
            id=member_id,
            combination_group_id=target_group_id,
            contract_id=contract_id,
            valid_from_known_at=event["recorded_at"],
            join_event_id=event["id"],
            **_created(uow),
        )
    )
    principal = uow.principal
    session.execute(
        update(contract)
        .where(contract.c.tenant_id == principal.tenant_id, contract.c.id == contract_id)
        .values(
            combination_group_id=target_group_id,
            row_version=contract.c.row_version + 1,
            **_stamps(uow),
        )
    )
    audit_writer.record_facts(
        uow,
        action=MEMBER_CREATE_ACTION,
        object_type=MEMBER_OBJECT,
        ids=[member_id],
        detail={"combination_group_id": str(target_group_id)},
        contract_id=contract_id,
    )


def _dirty(uow: UnitOfWork, group_id: UUID) -> None:
    uow.session.execute(
        update(combination_group)
        .where(
            combination_group.c.tenant_id == uow.principal.tenant_id,
            combination_group.c.id == group_id,
        )
        .values(
            # 05 RCP-17 rev 1.207 (item COMPUTE-BEHIND-GROUP-1): a mark is never moved back
            dirty_since=func.greatest(combination_group.c.dirty_since, uow.now),
            row_version=combination_group.c.row_version + 1,
            **_stamps(uow),
        )
    )


def _settle_emptied(uow: UnitOfWork, group_ids: Iterable[UUID]) -> None:
    """Item COMBINE-EMPTY-GROUP-DIRTY-1 (supervisor ruling of 2026-10-01; seen by lane F-CLO-B):
    clear ``dirty_since`` of every group of ``group_ids`` the combination left without a member.
    The last member's ``COMBINATION_CHANGED`` stamped it (``stream._mark_dirty``; ``_dirty``),
    and nothing clears it again: a group is cleared by its next computation, and a group without
    members is never computed (``_compute``; ``bundles.build`` refuses it) — a singleton group
    whose contract joined a combined group, and a combined group every member left, stayed dirty
    for good. Such a group keeps its versions as history; it is stamped and computed again when
    a contract returns to it (a leave moves the contract back into its singleton group). The
    caller holds the row of every group it names (``_lock_members``)."""
    wanted = sorted(set(group_ids))
    held = _current_members(uow.session, wanted)
    emptied = [group_id for group_id in wanted if not held.get(group_id)]
    if not emptied:
        return
    uow.session.execute(
        update(combination_group)
        .where(
            combination_group.c.tenant_id == uow.principal.tenant_id,
            combination_group.c.id.in_(emptied),
            combination_group.c.dirty_since.is_not(None),
        )
        .values(
            dirty_since=None,
            dirty_trigger=None,  # 04 T-CON-03 rev 1.297: a trigger is carried by a mark only
            row_version=combination_group.c.row_version + 1,
            **_stamps(uow),
        )
    )


def _compute(uow: UnitOfWork, group_id: UUID, contract_id: UUID) -> None:
    session = uow.session
    if not _current_members(session, [group_id]).get(group_id):
        return
    outcome = None
    if obligation_count(session, group_id) <= OBLIGATION_BUDGET:
        outcome = compute_group(uow, group_id, budget_seconds=ENGINE_BUDGET_SECONDS)
    if outcome is None or outcome.deferred:
        defer_compute(uow, group_id, contract_id=contract_id)


def _review(uow: UnitOfWork, record_id: UUID, approval_request_id: UUID) -> None:
    record = transitions.apply(
        uow.session,
        "judgement_record",
        record_id,
        to_status=JudgementStatus.REVIEWED.value,
        expected_status=JudgementStatus.SUBMITTED.value,
        set_values={
            "reviewer_id": uow.principal.id,
            "reviewed_at": uow.now,
            "approval_request_id": approval_request_id,
            **_stamps(uow),
        },
    )
    uow.audit(
        action="judgement_record.reviewed",
        object_type="judgement_record",
        object_id=record_id,
        before={"status": JudgementStatus.SUBMITTED.value},
        after={"status": JudgementStatus.REVIEWED.value},
        contract_ids=judgements.record_contracts(record),
    )


def _lock_members(
    session: Session, *, group_id: UUID, proposal: _Proposal, between: Between | None = None
) -> tuple[GroupRows, list[dict[str, Any]], dict[UUID, UUID]]:
    """``apply_combination``'s lock step (DG-KRN-DB-08 rev 1.36; D-98 candidates 101b, 101c). The
    appended CombinationChanged events mark each member's CURRENT group dirty (``_change`` →
    ``_mark_dirty``; ``_dirty``) and a leave moves members into their singleton groups, so every one
    of those group rows and the target are locked in one ascending id order before ``between`` (the
    proposal record) and the member contracts; unlocked reads supply the ids and each member's group
    is re-verified for equality under the locks. Returns the locked group rows, the member rows by
    external id and, for a leave, each member's singleton group id."""
    members = _observe(session, proposal.contract_ids)
    singletons_by_contract: dict[UUID, UUID] = {}
    if proposal.action != "JOIN":
        for row in members:
            singleton = session.execute(
                select(combination_group.c.id).where(
                    combination_group.c.code == f"{GROUP_PREFIX}{row['contract_no']}",
                    combination_group.c.is_singleton.is_(True),
                )
            ).scalar_one()
            singletons_by_contract[UUID(str(row["id"]))] = UUID(str(singleton))
    groups, rows = _lock_groups_then_contracts(
        session,
        group_ids={group_id, *singletons_by_contract.values()},
        expected=_expected(members),
        between=between,
    )
    return groups, sorted(rows, key=lambda row: str(row["external_id"])), singletons_by_contract


def apply_combination(uow: UnitOfWork, group_id: UUID, approval_request_id: UUID) -> None:
    """``on_approved`` of ``COMBINATION_GROUP`` (S02-R-09)."""
    session = uow.session
    proposal = _proposal(session, group_id)  # unlocked: which contracts, so which groups, to lock
    if proposal is None or proposal.status is not JudgementStatus.SUBMITTED:
        raise LookupError(f"combination group {group_id} has no submitted proposal")
    request = session.execute(
        select(approval_request.c.preparer_id, approval_request.c.reason_code).where(
            approval_request.c.id == approval_request_id
        )
    ).one()
    group: dict[str, Any] = {}

    def lock_proposal(groups: GroupRows) -> None:
        # DG-KRN-DB-08 rev 1.36: the proposal record after every group row, before the contracts.
        nonlocal group
        group = groups[group_id]
        if _proposal(session, group_id, lock=True) != proposal:
            raise Problem("precondition-failed", PROPOSAL_CHANGED)

    _, rows, singletons_by_contract = _lock_members(
        session, group_id=group_id, proposal=proposal, between=lock_proposal
    )
    # DG-KRN-APR-05 rev 1.40 (D-98 candidate 101d): under every lock, before anything is applied,
    # the members must still hash to the basis the approver reviewed (an append committed after
    # decide's pre-lock check would otherwise be applied against).
    approvals.assert_fresh_basis(uow, approval_request_id)
    if proposal.action == "JOIN":
        # Ruling R-77 (5): a member gated after the request is a changed head and so a stale
        # basis; a book kept by another member's entity since then changes no head, so the guard
        # is asked again under the locks, before the first write.
        refused = _gated_member_errors(uow, rows)
        if refused:
            raise Problem("invalid-transition", refused[0].message, errors=refused)
    _review(uow, proposal.record_id, approval_request_id)
    system = _system_unit(uow, request.preparer_id)
    if proposal.action == "JOIN":
        for row in rows:
            event = _change(
                system,
                row,
                CombinationChangedV1(
                    combination_group_id=group_id, action="JOIN", criterion=group["criterion"]
                ),
            )
            _dirty(system, UUID(str(row["combination_group_id"])))
            _move(system, UUID(str(row["id"])), group_id, event)
        # The groups the members came from: one that holds no contract now is not left dirty.
        _settle_emptied(uow, (UUID(str(row["combination_group_id"])) for row in rows))
        for status_from, status_to in (
            (CombinationStatus.SUBMITTED, CombinationStatus.APPROVED),
            (CombinationStatus.APPROVED, CombinationStatus.APPLIED),
        ):
            transitions.apply(
                session,
                GROUP_OBJECT,
                group_id,
                to_status=status_to.value,
                expected_status=status_from.value,
                set_values={"approval_request_id": approval_request_id, **_stamps(uow)},
            )
            _group_audit(
                uow,
                group_id,
                status_from.value,
                status_to.value,
                contract_ids=proposal.contract_ids,
            )
        _dirty(uow, group_id)
        for event in system.drain_audit_events():
            uow.buffer_audit_event(event)
        _compute(uow, group_id, UUID(str(rows[0]["id"])))
        return
    if request.reason_code != LEAVE_REASON:
        raise LookupError(f"a leave from {group_id} needs reason code {LEAVE_REASON}")
    singletons: list[tuple[UUID, UUID]] = []
    for row in rows:
        contract_id = UUID(str(row["id"]))
        event = _change(
            system, row, CombinationChangedV1(combination_group_id=group_id, action="LEAVE")
        )
        singleton = singletons_by_contract[contract_id]  # locked above, before the contracts
        _move(system, contract_id, singleton, event)
        _dirty(system, singleton)
        singletons.append((singleton, contract_id))
    _dirty(uow, group_id)
    for event in system.drain_audit_events():
        uow.buffer_audit_event(event)
    # DG-KRN-DB-08 (1c) rev 1.218 (finding F4): a leave computes each singleton and then the
    # remainder; the first computation that posts takes the book's chain head, so the windows of
    # all of them are held before the first.
    period_ends.hold_windows(uow, [*(singleton_id for singleton_id, _ in singletons), group_id])
    for singleton_id, contract_id in singletons:
        _compute(uow, singleton_id, contract_id)
    remaining = _current_members(session, [group_id]).get(group_id, [])
    if remaining:
        _compute(uow, group_id, remaining[0])
    else:
        _settle_emptied(uow, [group_id])  # every member left: nothing is left to compute


def close_combination(uow: UnitOfWork, group_id: UUID, approval_request_id: UUID) -> None:
    """``on_rejected`` and ``on_voided`` of ``COMBINATION_GROUP`` (L4-1-Q-16)."""
    session = uow.session
    group = repo.lock_group(session, group_id)
    proposal = _proposal(session, group_id, lock=True)
    if proposal is not None and proposal.status is JudgementStatus.SUBMITTED:
        judgements.reject_judgement(uow, proposal.record_id, approval_request_id)
    status = _text(group["status"])
    if status == CombinationStatus.SUBMITTED.value:
        transitions.apply(
            session,
            GROUP_OBJECT,
            group_id,
            to_status=CombinationStatus.REJECTED.value,
            expected_status=status,
            set_values=_stamps(uow),
        )
        _group_audit(
            uow,
            group_id,
            status,
            CombinationStatus.REJECTED.value,
            contract_ids=() if proposal is None else proposal.contract_ids,
        )


register_lifecycle(
    ApprovalSubjectType.COMBINATION_GROUP,
    SubjectLifecycle(
        on_approved=apply_combination, on_rejected=close_combination, on_voided=close_combination
    ),
)


# --- reads ---------------------------------------------------------------------------------------


def _current_members(session: Session, group_ids: Sequence[UUID]) -> dict[UUID, list[UUID]]:
    found: dict[UUID, list[UUID]] = {}
    for group_id, contract_id in session.execute(
        select(
            combination_group_member.c.combination_group_id, combination_group_member.c.contract_id
        )
        .where(
            combination_group_member.c.combination_group_id.in_(list(group_ids)),
            combination_group_member.c.valid_to_known_at.is_(None),
        )
        .order_by(combination_group_member.c.contract_id)
    ):
        found.setdefault(UUID(str(group_id)), []).append(UUID(str(contract_id)))
    return found


def _members_read(
    session: Session, group_ids: Sequence[UUID]
) -> dict[UUID, tuple[list[UUID], int]]:
    """Per group, the current members the session reads (by contract id) and how many current
    members the group has in all (head R28-READS: an answer lists the members its reader reads
    and counts all of them, as ``entity_count`` does for the entities of a request). The
    commands read every member (``_current_members``): T-CON-04 carries no entity."""
    read = contract.alias("member_contract")
    shown: dict[UUID, list[UUID]] = {}
    counted: dict[UUID, int] = {}
    for group_id, contract_id, visible in session.execute(
        select(
            combination_group_member.c.combination_group_id,
            combination_group_member.c.contract_id,
            read.c.id,
        )
        .select_from(
            combination_group_member.outerjoin(
                read,
                and_(
                    read.c.tenant_id == combination_group_member.c.tenant_id,
                    read.c.id == combination_group_member.c.contract_id,
                ),
            )
        )
        .where(
            combination_group_member.c.combination_group_id.in_(list(group_ids)),
            combination_group_member.c.valid_to_known_at.is_(None),
        )
        .order_by(combination_group_member.c.contract_id)
    ):
        key = UUID(str(group_id))
        counted[key] = counted.get(key, 0) + 1
        if visible is not None:
            shown.setdefault(key, []).append(UUID(str(contract_id)))
    return {key: (shown.get(key, []), count) for key, count in counted.items()}


def _read_contracts(session: Session, contract_ids: Sequence[UUID]) -> set[UUID]:
    """Those of ``contract_ids`` the session reads."""
    wanted = sorted(set(contract_ids), key=str)
    if not wanted:
        return set()
    statement = select(contract.c.id).where(contract.c.id.in_(wanted))
    return {UUID(str(value)) for value in session.execute(statement).scalars()}


def groups_statement(
    *, statuses: Sequence[CombinationStatus] = (), contract_id: UUID | None = None
) -> Select[Any]:
    """``GET /combination-groups`` filtered by status and current member: the groups the
    session reads (``repo.reads_group``). ``contract_id`` matches a member the session reads —
    an id it does not read finds nothing, whatever groups that contract is in."""
    conditions: list[ColumnElement[bool]] = [
        repo.reads_group(combination_group.c.tenant_id, combination_group.c.id)
    ]
    if statuses:
        conditions.append(combination_group.c.status.in_([value.value for value in statuses]))
    if contract_id is not None:
        conditions.append(
            combination_group.c.id.in_(
                select(combination_group_member.c.combination_group_id).where(
                    combination_group_member.c.contract_id == contract_id,
                    combination_group_member.c.valid_to_known_at.is_(None),
                    combination_group_member.c.contract_id.in_(
                        select(contract.c.id).where(contract.c.id == contract_id)
                    ),
                )
            )
        )
    return select(combination_group).where(and_(*conditions))


def group_outs(
    session: Session, rows: Sequence[Mapping[str, Any]]
) -> list[CombinationGroupDetailOut]:
    members = _members_read(session, [UUID(str(row["id"])) for row in rows])
    found: list[CombinationGroupDetailOut] = []
    for row in rows:
        group_id = UUID(str(row["id"]))
        proposal = _proposal(session, group_id)
        shown, member_count = members.get(group_id, ([], 0))
        # a pending proposal names its contracts the same way: those the session reads, and
        # how many it names in all
        proposed = (
            set() if proposal is None else _read_contracts(session, list(proposal.contract_ids))
        )
        found.append(
            CombinationGroupDetailOut(
                id=group_id,
                code=str(row["code"]),
                is_singleton=bool(row["is_singleton"]),
                status=CombinationStatus(_text(row["status"])),
                transaction_currency=str(row["transaction_currency"]).strip(),
                criterion=row["criterion"],
                rationale=row["rationale"],
                judgement_record_id=row["judgement_record_id"],
                approval_request_id=row["approval_request_id"],
                inception_date=row["inception_date"],
                head_computation_id=row["head_computation_id"],
                dirty_since=row["dirty_since"],
                member_contract_ids=shown,
                member_count=member_count,
                proposal=None
                if proposal is None
                else CombinationProposalOut(
                    action=proposal.action,
                    contract_ids=[value for value in proposal.contract_ids if value in proposed],
                    contract_count=len(proposal.contract_ids),
                    judgement_record_id=proposal.record_id,
                    status=proposal.status,
                ),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )
    return found


def get_group(session: Session, group_id: UUID) -> CombinationGroupDetailOut:
    """``GET /combination-groups/{id}``, and the answer of the commands that make or submit a
    group; 404 for a group the session does not read (``repo.read_group``)."""
    (item,) = group_outs(session, [repo.read_group(session, group_id)])
    return item
