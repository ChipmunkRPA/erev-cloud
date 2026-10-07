"""Judgement records (04 T-CON-19, §15.3 API-R-33, E-56, E-57, §14.1 DB-10; PRD SM-10, §2.5 routing
row ``JUDGEMENT_RECORD``; 03 REQ-POL-008; ENGINE_SPEC Table 0.4-A, S02-R-01 to S02-R-08;
BUILD_SPEC CTR-7).

A record is prepared as DRAFT (``judgement.create`` for the subject's contracting entity), edited
while DRAFT, and submitted under subject ``JUDGEMENT_RECORD``, whose single step needs
``judgement.review``. The questionnaire is validated per topic at insert, update and submission
(``schemas.db_json.JudgementQuestionnaire``; 422 ``validation-failed``, rule ``T-CON-19``).

The lifecycle callbacks run in the deciding transaction:

- approval moves the record SUBMITTED → REVIEWED with ``reviewer_id`` and ``reviewed_at``; earlier
  REVIEWED records of the same topic, subject and book become SUPERSEDED (SM-10). When the record
  names a contract, the contract's group is computed again, because the engine reads the reviewed
  outcome members (ENGINE_SPEC Table 0.4-A);
- rejection moves it SUBMITTED → REJECTED; the preparer revises it through PATCH, which returns it
  to DRAFT (REJECTED → DRAFT);
- [J] L4-1-Q-12: a voided or withdrawn request also leaves it REJECTED, because E-57 has no
  withdrawn status and SM-10 no SUBMITTED → DRAFT pair.

Every status change writes ``judgement_record.<status lowercase>`` (DG-SM-03).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final
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
from erev_api.auth.dependencies import require_for_entity
from erev_api.db import new_id, transitions
from erev_api.db.tables import (
    combination_group,
    contract,
    estimate,
    estimate_version,
    judgement_record,
    migration_batch,
    modification,
    obligation,
    product,
    registry_version,
)
from erev_api.domain.contracts import holds, repo
from erev_api.domain.contracts.compute_job import (
    ENGINE_BUDGET_SECONDS,
    OBLIGATION_BUDGET,
    compute_group,
    defer_compute,
    obligation_count,
)
from erev_api.domain.platform import approval_queries
from erev_api.enums import (
    ApprovalSubjectType,
    JudgementStatus,
    JudgementTopic,
    ModificationStatus,
    PrincipalKind,
)
from erev_api.events import step1
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.db_json import STEP1_CRITERIA, JudgementQuestionnaire, ValidationError
from erev_api.schemas.judgements import (
    JudgementCreateIn,
    JudgementOut,
    JudgementSubmitIn,
    JudgementUpdateIn,
)

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "CREATE_PERMISSION",
    "create_judgement",
    "get_judgement",
    "judgement_outs",
    "judgements_statement",
    "questionnaire_errors",
    "record_contracts",
    "reject_judgement",
    "review_judgement",
    "step1_criteria_errors",
    "submit_judgement",
    "update_judgement",
]

CREATE_PERMISSION: Final = "judgement.create"
SERIES: Final = "JUDGEMENT"
OBJECT_TYPE: Final = "judgement_record"
CREATE_ACTION: Final = "judgement_record.create"
UPDATE_ACTION: Final = "judgement_record.update"
RULE_SCHEMA: Final = "T-CON-19"
RULE_SUBJECT: Final = "T-CON-19"
NOT_EDITABLE: Final = "Only a draft or rejected judgement record can be edited."
# ERR-01 detail (04 T-CON-19 rev 1.104; supervisor ruling R-64 (7) (a)).
NOT_THE_CREATOR: Final = (
    "Only the person who created this judgement record can change it. Create a new record instead."
)
# Item JDG-REJECTED-EXIT-1: the same refusal where the record can be discarded — a draft or a
# rejected record that is not the proposal of a combination group. Without its second half the
# sentence sent a second preparer to a new record and left the first where it was, and a
# rejected record that stays fails the activation checklist.
NOT_THE_CREATOR_DISCARD: Final = (
    "Only the person who created this judgement record can change it. Create a new record instead "
    "and discard this one."
)
NOT_SUBMITTABLE: Final = "Only a draft judgement record can be submitted."
# The discard of a draft (PRD SM-10 ``DRAFT`` → ``VOIDED``; 04 T-CON-19, E-57 rev 1.242; the
# supervisor's ruling of 2026-10-01 on the lane's question J1 (a)) and, item
# JDG-REJECTED-EXIT-1, of a rejected record.
NOT_DISCARDABLE: Final = "Only a draft or rejected judgement record can be discarded."
DISCARDABLE: Final = (JudgementStatus.DRAFT.value, JudgementStatus.REJECTED.value)
DISCARD_ACTION: Final = "judgement_record.voided"
# The proposal of a combination group is that group's: the submission of a PROPOSED group
# reads the group's draft record — without it the group could not be submitted — and the
# draft is given up with its group, by the group's own discard (rev 1.289).
# Item COMBINATION-PROPOSAL-RECORD-1 (the supervisor's rulings of 2026-10-02 on lane
# F-RPS-REG's probe and line; 04 T-CON-19 rev 1.283): a ``COMBINATION`` record whose subject
# is a combination group is written by the combination commands alone
# (``combination._record_proposal``) and is decided with its group, so it is neither written
# nor sent for review by hand. A ``COMBINATION`` record of another subject — the judgement
# that two orders were booked as one contract — stays a record by hand.
PROPOSAL_OF_A_GROUP: Final = (
    "This record is the proposal of a combination group. It is decided with its group."
)
GROUP_SUBJECT: Final = "combination_group"
COMBINATION_BY_COMMAND: Final = (
    "A combination record of a combination group is written by the combination commands: "
    "propose the combination, or the leave, of its contracts."
)
# Item COMBINATION-PROPOSAL-DISCARD-1 (04 T-CON-19 rev 1.289): the proposal of a group is
# edited by nobody. A correction is the discard of the proposal with its group
# (``combination.discard_group``) and a new proposal: the group row the approver's request
# is made from and the record are written together or not at all.
PROPOSAL_NOT_EDITED: Final = (
    "This record is the proposal of a combination group and is not edited. To change a "
    "proposal that is not submitted, discard it and propose the combination again."
)
CONTRACT_MISMATCH: Final = "The contract differs from the subject's contract."
# Item MOD-DISCARD-1 (supervisor ruling R-118 (e)): no review is requested for a record of a
# voided modification — the mirror of the discard, which is refused while one is pending.
MODIFICATION_VOIDED: Final = "The modification of this record is voided. It takes no review."
# 04 T-CON-19 "Step 1 criteria" (rev 1.150; supervisor rulings R-113 (f), R-115 (f); item
# STEP1-CRITERIA-1): the five answers of a record that serves Step 1.
STEP1_TOPICS: Final = frozenset({JudgementTopic.COLLECTIBILITY, JudgementTopic.NOT_A_CONTRACT})
CRITERIA_REQUIRED: Final = "Answer criteria (a) to (e) of the Step 1 review before it is submitted."
CRITERION_REQUIRED: Final = "Answer this criterion Yes or No before the review is submitted."
CRITERION_E_FOR_TOPIC: Final[Mapping[JudgementTopic, str]] = {
    JudgementTopic.COLLECTIBILITY: (
        "A collectibility record answers Yes to criterion (e). Use topic NOT_A_CONTRACT for a "
        "review that finds collection not probable."
    ),
    JudgementTopic.NOT_A_CONTRACT: (
        "A not-a-contract record answers No to criterion (e). Use topic COLLECTIBILITY for a "
        "review that finds collection probable."
    ),
}
CRITERION_D_HAS_SUBSTANCE: Final = (
    "The contract is recorded with commercial substance; criterion (d) answers No. Correct the "
    "contract or the answer."
)
CRITERION_D_NO_SUBSTANCE: Final = (
    "The contract is recorded without commercial substance; criterion (d) answers Yes. Correct "
    "the contract or the answer."
)
SUBJECT_UNKNOWN: Final = "No {subject_type} has this id."


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def questionnaire_errors(
    topic: JudgementTopic, value: Mapping[str, Any] | None, *, field: str = "questionnaire"
) -> tuple[dict[str, Any] | None, list[ProblemError]]:
    """The validated questionnaire, or the field errors of the topic's schema (T-CON-19)."""
    try:
        validated = JudgementQuestionnaire.validate(topic, value)
    except ValidationError as error:
        errors = []
        for item in error.errors():
            location = ".".join(str(part) for part in item.get("loc", ()))
            errors.append(
                ProblemError(
                    field=field + (f".{location}" if location else ""),
                    rule_id=RULE_SCHEMA,
                    message=str(item.get("msg", "")),
                )
            )
        return None, errors
    return (None if value is None else validated), []


def step1_criteria_errors(
    session: Session,
    topic: JudgementTopic,
    questionnaire: Mapping[str, Any] | None,
    contract_id: UUID | None,
    *,
    whole: bool,
) -> list[ProblemError]:
    """04 T-CON-19 "Step 1 criteria" (supervisor rulings R-113 (f), R-115 (f)): what a record
    that serves Step 1 — topic COLLECTIBILITY or NOT_A_CONTRACT — says of the five criteria of
    606-10-25-1, beyond the member's shape (``schemas.db_json.Step1Criteria``). ``whole`` — at
    submission — asks for all five answers; a draft may hold none, or some. Whenever (e) is
    answered it agrees with the topic (YES with COLLECTIBILITY, NO with NOT_A_CONTRACT), and
    whenever (d) is answered it agrees with ``has_commercial_substance`` of the record's
    contract — at every write and again at submission, because the draft's booking can be
    replaced in between. Each finding names its key (422, rule ``T-CON-19``)."""
    if topic not in STEP1_TOPICS:
        return []
    criteria = (questionnaire or {}).get("criteria")
    if criteria is None:
        if not whole:
            return []
        return [
            ProblemError(
                field="questionnaire.criteria", rule_id=RULE_SCHEMA, message=CRITERIA_REQUIRED
            )
        ]
    errors: list[ProblemError] = []

    def refuse(key: str, message: str) -> None:
        errors.append(
            ProblemError(
                field=f"questionnaire.criteria.{key}", rule_id=RULE_SCHEMA, message=message
            )
        )

    if whole:
        for key in STEP1_CRITERIA:
            if criteria.get(key) is None:
                refuse(key, CRITERION_REQUIRED)
    expected = "YES" if topic is JudgementTopic.COLLECTIBILITY else "NO"
    if criteria.get("e") is not None and criteria["e"] != expected:
        refuse("e", CRITERION_E_FOR_TOPIC[topic])
    answered = criteria.get("d")
    if answered is not None and contract_id is not None:
        substance = bool(
            session.execute(
                select(contract.c.has_commercial_substance).where(contract.c.id == contract_id)
            ).scalar_one()
        )
        if (answered == "YES") != substance:
            refuse("d", CRITERION_D_HAS_SUBSTANCE if substance else CRITERION_D_NO_SUBSTANCE)
    return errors


def _failed(errors: Sequence[ProblemError]) -> Problem:
    detail = errors[0].message if len(errors) == 1 else f"{len(errors)} fields need attention."
    return Problem("validation-failed", detail, errors=errors)


def _subject_contract(
    uow: UnitOfWork, subject_type: str, subject_id: UUID, contract_id: UUID | None
) -> tuple[UUID | None, UUID | None]:
    """(contract id, contracting entity id) of a visible subject; 404 when it is not visible."""
    session = uow.session
    found: UUID | None = None
    match subject_type:
        case "contract":
            found = UUID(str(repo.get_contract(session, subject_id)["id"]))
        case "obligation":
            value = session.execute(
                select(obligation.c.contract_id).where(obligation.c.id == subject_id)
            ).scalar_one_or_none()
            if value is None:
                raise Problem("not-found")
            found = UUID(str(repo.get_contract(session, UUID(str(value)))["id"]))
        case "combination_group":
            # head R28-READS: a group the session does not read is no subject for it
            repo.read_group(session, subject_id)
        case "product" | "registry_version":
            table = product if subject_type == "product" else registry_version
            if session.execute(select(table.c.id).where(table.c.id == subject_id)).first() is None:
                raise Problem("not-found")
        case "modification":
            # CTR-17 (D-98 140-A5 JUDGEMENT-1): the record's contract is the modification's, so a
            # MODIFICATION_TREATMENT_OVERRIDE review is bound to one row of one contract.
            value = session.execute(
                select(modification.c.contract_id).where(modification.c.id == subject_id)
            ).scalar_one_or_none()
            if value is None:
                raise Problem("not-found")
            found = UUID(str(repo.get_contract(session, UUID(str(value)))["id"]))
        case "estimate_version":
            # Item JDG-SUBJECT-ESTIMATE-1 (04 T-CON-19 rev 1.210): the record's contract is the
            # estimate's. Without it the record named no contract — the engine reads judgement
            # records by contract, the audit events name the contract, and the review request
            # takes its entity from it. An estimate of a portfolio names no contract.
            owner = session.execute(
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
                .where(estimate_version.c.id == subject_id)
            ).first()
            if owner is None:
                raise Problem("not-found")
            if owner[0] is not None:
                found = UUID(str(repo.get_contract(session, UUID(str(owner[0])))["id"]))
        case "migration_batch":
            # A migration batch is of no single contract: the subject is checked like a product
            # or a registry version, and nothing is defaulted from it.
            if (
                session.execute(
                    select(migration_batch.c.id).where(migration_batch.c.id == subject_id)
                ).first()
                is None
            ):
                raise Problem("not-found")
        case _:  # 04 T-CON-19 ``ck_judgement_record__subject_type`` admits no other literal
            raise Problem("not-found")
    if found is not None and contract_id is not None and contract_id != found:
        raise _failed(
            [ProblemError(field="contract_id", rule_id=RULE_SUBJECT, message=CONTRACT_MISMATCH)]
        )
    chosen = found if found is not None else contract_id
    if chosen is None:
        return None, None
    row = repo.get_contract(session, chosen)
    return chosen, UUID(str(row["contracting_entity_id"]))


def read_by_the_session() -> ColumnElement[bool]:
    """Which T-CON-19 rows are the session's to read (03 REQ-PLT-012; supervisor ruling R-28 and
    the supervisor's ruling of 2026-10-02; head R28-READS). The table carries no entity and its
    rows pass the row policy for every member.

    - A record that names a contract (``contract_id``: its subject's, or the one a record of a
      product or a group names) is read with that contract: a contract the session does not see
      hides the record with it, as ``file_access`` reads the record's files.
    - A record of a combination group that names no contract is read with the group
      (``repo.reads_group``); a ``COMBINATION`` record — the proposal the combination commands
      write, whose conclusion names the contracts it combines or separates — by a session that
      reads every one of them (``repo.reads_proposal``).
    - Any other record that names no contract is the workspace's, as before."""
    record = judgement_record.c
    read = contract.alias("record_contract")
    of_a_group = record.subject_type == "combination_group"
    return or_(
        and_(
            record.contract_id.is_not(None),
            exists().where(read.c.tenant_id == record.tenant_id, read.c.id == record.contract_id),
        ),
        and_(
            record.contract_id.is_(None),
            of_a_group,
            repo.reads_group(record.tenant_id, record.subject_id),
            or_(
                record.topic != JudgementTopic.COMBINATION.value,
                repo.reads_proposal(judgement_record),
            ),
        ),
        and_(record.contract_id.is_(None), ~of_a_group),
    )


def _row(session: Session, judgement_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    """The record a read or a command starts from; 404 ``not-found`` when it is not the session's
    to read (``read_by_the_session``)."""
    statement = select(judgement_record).where(
        judgement_record.c.id == judgement_id, read_by_the_session()
    )
    if lock:
        statement = statement.with_for_update()
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _locked_record(session: Session, judgement_id: UUID) -> dict[str, Any]:
    """The record ``FOR UPDATE`` on the DG-KRN-DB-08 order (rev 1.36; D-98 candidate 101c): a record
    that names a contract locks that contract's combination group first, the record between, then
    the contract row (``repo.lock_group_then_contract`` with ``between``), so the hold and the
    recompute that follow find every row already held and no pair is taken in the inverse order.
    A record without a contract locks itself only."""
    preview = _row(session, judgement_id)  # unlocked: which contract, so which group, to lock first
    if preview["contract_id"] is None:
        return _row(session, judgement_id, lock=True)
    locked: list[dict[str, Any]] = []
    repo.lock_group_then_contract(
        session,
        UUID(str(preview["contract_id"])),
        between=lambda _group_id: locked.append(_row(session, judgement_id, lock=True)),
    )
    return locked[0]


def _require_prepare(uow: UnitOfWork, row: Mapping[str, Any]) -> None:
    entity_id: UUID | None = None
    if row["contract_id"] is not None:
        found = repo.get_contract(uow.session, UUID(str(row["contract_id"])))
        entity_id = UUID(str(found["contracting_entity_id"]))
    require_for_entity(uow.ctx, CREATE_PERMISSION, entity_id)


def _require_creator(uow: UnitOfWork, row: Mapping[str, Any]) -> None:
    """A DRAFT or REJECTED record is changed only by its creator (04 T-CON-19 rev 1.104; supervisor
    ruling R-64 (7) (a)). The record's author is the one person who may not review it — the
    excluded decider of its ``JUDGEMENT_RECORD`` request, and of the ``COMBINATION_GROUP`` request
    that reviews a combination proposal (R-41 (3)) — and the author is read from ``created_by``:
    content a second editor wrote would be content the author rule does not see. Whoever may
    prepare the record may still submit it; the submitter is the request's preparer."""
    principal = uow.principal
    kind = str(getattr(row["created_by_kind"], "value", row["created_by_kind"]))
    creator = (row["created_by"], kind)
    if row["created_by"] is None or creator != (principal.id, principal.kind.value):
        raise Problem(
            "forbidden",
            NOT_THE_CREATOR_DISCARD if _discard_refusal(row) is None else NOT_THE_CREATOR,
        )


def _discard_refusal(row: Mapping[str, Any], *, with_its_group: bool = False) -> str | None:
    """Why the record is not discarded, or None for one that is: a DRAFT or a REJECTED record
    that is not the proposal of a combination group, which is decided with its group — and
    given up with it: ``with_its_group`` is the discard of that group
    (``combination.discard_group``; item COMBINATION-PROPOSAL-DISCARD-1), the one caller that
    voids a group's proposal. ``discard_judgement`` hands its mark ``proposal_of_group`` on
    under this name: the census of that mark counts the callers of the two commands and
    nothing else (``tests/unit/test_combination_proposal_writer.py``)."""
    if _text(row["status"]) not in DISCARDABLE:
        return NOT_DISCARDABLE
    if _proposal_of_a_group(row) and not with_its_group:
        return PROPOSAL_OF_A_GROUP
    return None


def _proposal_of_a_group(record: Mapping[str, Any]) -> bool:
    """Whether ``record`` (``topic``, ``subject_type``) is the proposal of a combination group:
    the ``COMBINATION`` record the combination commands write for the group (item
    COMBINATION-PROPOSAL-RECORD-1)."""
    return (
        _text(record["topic"]) == JudgementTopic.COMBINATION.value
        and str(record["subject_type"]) == GROUP_SUBJECT
    )


def record_contracts(record: Mapping[str, Any]) -> list[UUID]:
    """The contracts an audit event of a record names (04 T-PLT-19 ``detail.contract_id`` /
    ``detail.contract_ids``, rev 1.154): the record's contract (T-CON-19 ``contract_id``); the
    proposal of a combination group names the contracts of the proposal
    (``questionnaire.contract_ids``, which the combination commands write). A ``COMBINATION``
    record of another subject is a record by hand: its questionnaire is evidence and names
    nothing (rev 1.283, item COMBINATION-PROPOSAL-RECORD-1) — before, the list of ANY such
    record was read, so a record on the caller's own contract named other contracts in the
    trail and not its own, and a list that named no contract failed the write. A record about
    no contract names none. ``record`` carries ``topic``, ``subject_type``, ``contract_id`` and
    ``questionnaire``."""
    if _proposal_of_a_group(record):
        named = (record["questionnaire"] or {}).get("contract_ids") or ()
        if named:
            return [UUID(str(value)) for value in named]
    return [] if record["contract_id"] is None else [UUID(str(record["contract_id"]))]


def _status_audit(
    uow: UnitOfWork, record: Mapping[str, Any], before: str, after: str, **extra: Any
) -> None:
    uow.audit(
        action=f"{OBJECT_TYPE}.{after.lower()}",
        object_type=OBJECT_TYPE,
        object_id=UUID(str(record["id"])),
        before={"status": before},
        after={"status": after, **extra},
        contract_ids=record_contracts(record),
    )


def create_judgement(
    uow: UnitOfWork, *, body: JudgementCreateIn, proposal_of_group: bool = False
) -> JudgementOut:
    """``POST /judgements``: a DRAFT record numbered from series ``JUDGEMENT``.

    By hand a ``COMBINATION`` record of a combination group is refused, 422 on ``topic``
    (item COMBINATION-PROPOSAL-RECORD-1): that record is the group's proposal, and a record
    somebody wrote beside it stood in for it — the group's commands and its approval read
    the latest record of the topic. ``proposal_of_group``: the caller is the combination
    command writing its group's proposal (``combination._record_proposal``, the one caller
    that passes it; ``tests/unit/test_combination_proposal_writer.py``)."""
    contract_id, entity_id = _subject_contract(
        uow, body.subject_type, body.subject_id, body.contract_id
    )
    require_for_entity(uow.ctx, CREATE_PERMISSION, entity_id)
    session = uow.session
    if (
        body.topic is JudgementTopic.COMBINATION
        and body.subject_type == GROUP_SUBJECT
        and not proposal_of_group
    ):
        raise _failed(
            [ProblemError(field="topic", rule_id=RULE_SCHEMA, message=COMBINATION_BY_COMMAND)]
        )
    questionnaire, errors = questionnaire_errors(body.topic, body.questionnaire)
    errors = errors or step1_criteria_errors(
        session, body.topic, questionnaire, contract_id, whole=False
    )
    if errors:
        raise _failed(errors)
    if body.supersedes_id is not None:
        _row(session, body.supersedes_id)
    principal = uow.principal
    judgement_id = new_id()
    number = numbering.next_number(uow, SERIES)
    values: dict[str, Any] = {
        "judgement_no": number,
        "topic": body.topic.value,
        "subject_type": body.subject_type,
        "subject_id": body.subject_id,
        "contract_id": contract_id,
        "book_code": None if body.book is None else body.book.value,
        "conclusion": body.conclusion,
        "rationale": body.rationale,
        "alternatives_considered": body.alternatives_considered,
        "codification_refs": list(body.codification_refs),
        "questionnaire": questionnaire,
        "status": JudgementStatus.DRAFT.value,
        "supersedes_id": body.supersedes_id,
    }
    session.execute(
        insert(judgement_record).values(
            tenant_id=principal.tenant_id,
            id=judgement_id,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            **values,
            **_stamps(uow),
        )
    )
    uow.audit(
        action=CREATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=judgement_id,
        object_version="1",
        after={
            **values,
            "subject_id": str(body.subject_id),
            "contract_id": None if contract_id is None else str(contract_id),
            "supersedes_id": None if body.supersedes_id is None else str(body.supersedes_id),
        },
        contract_ids=record_contracts(values),
    )
    return get_judgement(session, judgement_id)


def update_judgement(
    uow: UnitOfWork, *, judgement_id: UUID, body: JudgementUpdateIn
) -> JudgementOut:
    """``PATCH /judgements/{id}``: edit a DRAFT record; a REJECTED record returns to DRAFT first
    (SM-10 REJECTED → DRAFT). Only the record's creator (403 ``forbidden`` for anyone else).
    The proposal of a combination group is edited by nobody, its creator included: 409
    ``invalid-transition`` with the sentence that names the road (rev 1.289, item
    COMBINATION-PROPOSAL-DISCARD-1) — until then its author's edit rewrote the record
    and not the group row the approver's request is made from."""
    session = uow.session
    row = _row(session, judgement_id, lock=True)
    _require_prepare(uow, row)
    if _proposal_of_a_group(row):
        raise Problem(
            "invalid-transition",
            PROPOSAL_NOT_EDITED,
            errors=[
                ProblemError(
                    field="status", rule_id=transitions.RULE_ID, message=PROPOSAL_NOT_EDITED
                )
            ],
        )
    _require_creator(uow, row)
    status = _text(row["status"])
    if status not in (JudgementStatus.DRAFT.value, JudgementStatus.REJECTED.value):
        raise Problem(
            "invalid-transition",
            NOT_EDITABLE,
            errors=[
                ProblemError(field="status", rule_id=transitions.RULE_ID, message=NOT_EDITABLE)
            ],
        )
    changes: dict[str, Any] = {}
    for name in sorted(body.model_fields_set):
        value = getattr(body, name)
        if name == "book":
            changes["book_code"] = None if value is None else value.value
        elif name == "codification_refs":
            changes[name] = list(value or [])
        else:
            changes[name] = value
    topic = JudgementTopic(_text(row["topic"]))
    if "questionnaire" in changes:
        questionnaire, errors = questionnaire_errors(topic, changes["questionnaire"])
        errors = errors or step1_criteria_errors(
            session, topic, questionnaire, row["contract_id"], whole=False
        )
        if errors:
            raise _failed(errors)
        changes["questionnaire"] = questionnaire
    if status == JudgementStatus.REJECTED.value:
        transitions.apply(
            session,
            OBJECT_TYPE,
            judgement_id,
            to_status=JudgementStatus.DRAFT.value,
            expected_status=status,
            set_values=_stamps(uow),
        )
        _status_audit(uow, row, status, JudgementStatus.DRAFT.value)
    if changes:
        transitions.apply(
            session,
            OBJECT_TYPE,
            judgement_id,
            to_status=None,
            expected_status=JudgementStatus.DRAFT.value,
            set_values={**changes, **_stamps(uow)},
        )
        uow.audit(
            action=UPDATE_ACTION,
            object_type=OBJECT_TYPE,
            object_id=judgement_id,
            after={name: value for name, value in changes.items() if name != "questionnaire"}
            | ({"questionnaire": changes["questionnaire"]} if "questionnaire" in changes else {}),
            # the contracts the record named before the edit and names after it
            contract_ids=[*record_contracts(row), *record_contracts({**row, **changes})],
        )
    return get_judgement(session, judgement_id)


def discard_judgement(
    uow: UnitOfWork, *, judgement_id: UUID, proposal_of_group: bool = False
) -> JudgementOut:
    """``POST /judgements/{id}/discard`` (PRD SM-10 ``DRAFT`` → ``VOIDED``; 04 T-CON-19, E-57 rev
    1.242; the supervisor's ruling of 2026-10-01 on the lane's question J1 (a)): a draft that
    will not be submitted leaves the preparer's work. A draft had one exit, its submission, so a
    record made by mistake waited for a reviewer's rejection — and a modification is not
    submitted while a record whose subject it is stands DRAFT or SUBMITTED (PRD ERR-95). ANY
    draft is discarded, also one that was submitted, rejected and edited again: the request's
    history stays on the row (``approval_request_id``) and in the audit trail. Every holder of
    ``judgement.create`` for the record's entity may discard — a discard writes no content, so
    it is not the creator's alone, as an edit is. Refused, 409 ``invalid-transition``: a record
    in any other status, and the proposal of a combination group, which is decided with its
    group. Nothing else is written: a DRAFT record has no pending request, and the discard is
    the record's alone. A draft that was sent for review before may still hold its contract —
    the REQ-POL-010 hold placed at its submission stays after a rejection — and that hold stays
    after the discard too, to be released by hand (``release-hold``), as after the rejection.
    The record keeps its number, which is not given out again, and takes no further edit,
    submission or discard.

    Item JDG-REJECTED-EXIT-1 (measured on main with index 174): a REJECTED record is
    discarded as a draft is. It fails the activation checklist (``JUDGEMENT_RECORDS``) and
    had ONE exit, its creator's edit, which makes it a draft again — an edit no screen sends,
    while the screens write a NEW record after a rejection; so a contract whose review was
    once rejected was never activated from a screen. SM-10 holds REJECTED → DRAFT and DRAFT →
    VOIDED and no pair REJECTED → VOIDED (DB-03): the record goes both ways in this one unit
    of work, two updates under the row's lock, without an edit — so it is not the creator's
    alone. It is a draft only inside this transaction: no reader sees it there, a refusal
    after the first step leaves it REJECTED, and one audit event states the discard, from
    REJECTED to VOIDED.

    ``proposal_of_group``: the caller is the discard of a PROPOSED group
    (``combination.discard_group``, the one caller that passes it; rev 1.289, item
    COMBINATION-PROPOSAL-DISCARD-1), which voids the group and its proposal in one
    transaction. By hand the proposal of a group is refused as before."""
    session = uow.session
    row = _row(session, judgement_id, lock=True)
    _require_prepare(uow, row)
    status = _text(row["status"])
    refusal = _discard_refusal(row, with_its_group=proposal_of_group)
    if refusal is not None:
        raise Problem(
            "invalid-transition",
            refusal,
            errors=[ProblemError(field="status", rule_id=transitions.RULE_ID, message=refusal)],
        )
    if status == JudgementStatus.REJECTED.value:
        transitions.apply(
            session,
            OBJECT_TYPE,
            judgement_id,
            to_status=JudgementStatus.DRAFT.value,
            expected_status=status,
            set_values=_stamps(uow),
        )
    transitions.apply(
        session,
        OBJECT_TYPE,
        judgement_id,
        to_status=JudgementStatus.VOIDED.value,
        expected_status=JudgementStatus.DRAFT.value,
        set_values=_stamps(uow),
    )
    uow.audit(
        action=DISCARD_ACTION,
        object_type=OBJECT_TYPE,
        object_id=judgement_id,
        before={"status": status},
        after={"status": JudgementStatus.VOIDED.value},
        contract_ids=record_contracts(row),
    )
    return get_judgement(session, judgement_id)


def submit_judgement(
    uow: UnitOfWork, *, judgement_id: UUID, body: JudgementSubmitIn
) -> JudgementOut:
    """``POST /judgements/{id}/submit``: validate, hash and route the record for review."""
    session = uow.session
    row = _locked_record(session, judgement_id)  # DG-KRN-DB-08: group, record, contract
    _require_prepare(uow, row)
    if _text(row["status"]) != JudgementStatus.DRAFT.value:
        raise Problem(
            "invalid-transition",
            NOT_SUBMITTABLE,
            errors=[
                ProblemError(field="status", rule_id=transitions.RULE_ID, message=NOT_SUBMITTABLE)
            ],
        )
    if _proposal_of_a_group(row):
        # Item COMBINATION-PROPOSAL-RECORD-1: the draft a combination command wrote is
        # submitted by its group's submission (``combination.submit_group``), which routes
        # ``COMBINATION_GROUP``. Sent for a review of its own it was reviewed there, and
        # the group could then no longer be submitted.
        raise Problem(
            "invalid-transition",
            PROPOSAL_OF_A_GROUP,
            errors=[
                ProblemError(
                    field="status", rule_id=transitions.RULE_ID, message=PROPOSAL_OF_A_GROUP
                )
            ],
        )
    if _text(row["subject_type"]) == "modification":
        # The record's locks hold the modification's contract, which a discard takes first.
        subject = session.execute(
            select(modification.c.status).where(modification.c.id == row["subject_id"])
        ).scalar_one_or_none()
        if subject is not None and _text(subject) == ModificationStatus.VOIDED.value:
            raise Problem(
                "invalid-transition",
                MODIFICATION_VOIDED,
                errors=[
                    ProblemError(
                        field="subject_id",
                        rule_id=transitions.RULE_ID,
                        message=MODIFICATION_VOIDED,
                    )
                ],
            )
    topic = JudgementTopic(_text(row["topic"]))
    _, errors = questionnaire_errors(topic, row["questionnaire"])
    # 04 T-CON-19 "Step 1 criteria": a record that serves Step 1 answers all five when it is
    # sent for review (supervisor ruling R-113 (f)).
    errors = errors or step1_criteria_errors(
        session, topic, row["questionnaire"], row["contract_id"], whole=True
    )
    if errors:
        raise _failed(errors)
    # DG-KRN-APR-05 rev 1.40 (D-98 candidate 101d): the approved basis is captured AFTER every
    # system-side mutation of the subject in this unit of work — the REQ-POL-010 hold appends
    # HOLD_APPLIED (head + 1) to an ACTIVE contract, so it is applied BEFORE approvals.submit hashes
    # the subject content, exactly when the request will wait for a person (the same auto-approval
    # evaluation submit makes); an auto-approved record of another topic than NOT_A_CONTRACT
    # never holds (the review releases at once). Before this slice the hold followed the hash
    # and the first unchanged approval was refused STALE_SUBJECT.
    # Codex ROUTING-R1 (rev 1.40): the published routing state is read ONCE, under the record's
    # locks, and the same reading decides the hold AND routes the request (approvals.submit does
    # not read it again), so a concurrent publication can never split them.
    decision = approvals.route_submission(uow, ApprovalSubjectType.JUDGEMENT_RECORD, judgement_id)
    if (
        row["contract_id"] is not None
        and str(row["subject_type"]) not in UNHELD_SUBJECTS
        # Item STEP1-HOLD-RELEASE-1 (04 T-CON-20 "Judgement holds" rev 1.209; the supervisor's
        # ruling on Q-H3): a NOT_A_CONTRACT record holds whatever the routing — its hold is
        # released by the assessment that cites it, not by the review, so an auto-approved
        # record would otherwise leave the book recognising until that assessment.
        and (decision.auto_rule is None or topic is JudgementTopic.NOT_A_CONTRACT)
    ):
        # REQ-POL-010 (BUILD_SPEC CTR-10): an unreviewed judgement holds an active contract.
        holds.apply_system_hold(uow, UUID(str(row["contract_id"])), reason=_hold_reason(row, topic))
    content = judgement_record_content(session, judgement_id)
    transitions.apply(
        session,
        OBJECT_TYPE,
        judgement_id,
        to_status=JudgementStatus.SUBMITTED.value,
        expected_status=JudgementStatus.DRAFT.value,
        set_values={"content_sha256": sha256_hex(content), **_stamps(uow)},
    )
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.JUDGEMENT_RECORD,
        subject_id=judgement_id,
        summary=f"Review {row['judgement_no']} ({topic.value})",
        comment=body.comment,
        routing_decision=decision,
    )
    request_id = UUID(str(request["id"]))
    if _text(request["status"]) == "PENDING":
        transitions.apply(
            session,
            OBJECT_TYPE,
            judgement_id,
            to_status=None,
            expected_status=None,
            set_values={"approval_request_id": request_id, **_stamps(uow)},
        )
    _status_audit(
        uow,
        row,
        JudgementStatus.DRAFT.value,
        JudgementStatus.SUBMITTED.value,
        approval_request_id=str(request_id),
        **(
            {"constraint_estimate_basis": content["constraint_estimate_basis"]}
            if "constraint_estimate_basis" in content
            else {}
        ),
    )
    return get_judgement(session, judgement_id)


# Supervisor ruling R-23, second order (04 T-CON-20 "Judgement holds" rev 1.209; item
# STEP1-HOLD-RELEASE-1): REQ-POL-010 holds a contract for an "unreviewed judgement on the
# contract", and the record's contract is ``contract_id`` — whatever its subject. Before, only a
# record whose SUBJECT was a contract or an obligation held: a record of a product or of a
# combination group that names a contract placed nothing, and its review recomputed that
# contract all the same (measured). THE EXCEPTION, ruled with it: the two subjects below take
# their contract from the subject and change nothing of it before their OWN approval, which the
# record's review precedes — PRD ERR-54 for a treatment override; item MOD-LINKED-JUDGEMENTS-1
# and the CONSTRAINT rule of the estimate items for the rest. So no revenue is recognised on the
# unreviewed judgement, which is all the hold is for; and a hold would move the contract's head
# twice and make stale the very preview or pending version the record belongs to.
UNHELD_SUBJECTS: Final = frozenset({"modification", "estimate_version"})


def _hold_reason(row: Mapping[str, Any], topic: JudgementTopic) -> str:
    """The reason the record's hold is stored with and found by (``holds`` module docstring)."""
    return holds.judgement_hold_reason(row["judgement_no"], topic.value)


def _supersede(uow: UnitOfWork, row: Mapping[str, Any]) -> list[UUID]:
    """SM-10: earlier REVIEWED records of the same topic, subject and book become SUPERSEDED.
    Item STEP1-HOLD-RELEASE-1 (04 T-CON-20 "Judgement holds" (c), rev 1.209): the hold a
    superseded record still has is released with it — only a NOT_A_CONTRACT record keeps its
    hold past its review, and the record that supersedes it carries a hold of its own until
    ITS assessment is recorded. The caller (``review_judgement``) holds the contract's locks and
    computes the group once, behind every release."""
    session = uow.session
    book = row["book_code"]
    earlier = session.execute(
        select(
            judgement_record.c.id,
            judgement_record.c.judgement_no,
            judgement_record.c.topic,
            judgement_record.c.contract_id,
        )
        .where(
            judgement_record.c.id != row["id"],
            judgement_record.c.topic == row["topic"],
            judgement_record.c.subject_type == row["subject_type"],
            judgement_record.c.subject_id == row["subject_id"],
            judgement_record.c.status == JudgementStatus.REVIEWED.value,
            judgement_record.c.book_code.is_(None)
            if book is None
            else judgement_record.c.book_code == book,
        )
        .order_by(judgement_record.c.judgement_no)
    ).all()
    superseded = []
    for item in earlier:
        earlier_id = UUID(str(item.id))
        record = transitions.apply(
            session,
            OBJECT_TYPE,
            earlier_id,
            to_status=JudgementStatus.SUPERSEDED.value,
            expected_status=JudgementStatus.REVIEWED.value,
            set_values=_stamps(uow),
        )
        _status_audit(
            uow,
            record,
            JudgementStatus.REVIEWED.value,
            JudgementStatus.SUPERSEDED.value,
            superseded_by=str(row["id"]),
        )
        if item.contract_id is not None and item.contract_id == row["contract_id"]:
            holds.release_system_holds(
                uow,
                UUID(str(item.contract_id)),
                reason=holds.judgement_hold_reason(item.judgement_no, _text(item.topic)),
                comment=holds.SUPERSEDED_RELEASE_COMMENT.format(
                    judgement_no=item.judgement_no, superseded_by=row["judgement_no"]
                ),
            )
        superseded.append(earlier_id)
    return superseded


def _overtake(uow: UnitOfWork, row: Mapping[str, Any]) -> list[UUID]:
    """Item STEP1-HOLD-RELEASE-1 (04 T-CON-20 "Judgement holds" (c'), rev 1.209; the supervisor's
    ruling of 2026-10-01 on the lane's question 2). The hold of a reviewed NOT_A_CONTRACT record
    ends at the not-probable assessment that cites the record, or at its supersession — so a
    record that is never assessed with would hold the contract for good: the significant-change
    flag it answered is voided, or the facts change before the assessment and the next review
    finds collection probable. The review of a COLLECTIBILITY record therefore also releases the
    open hold of every REVIEWED NOT_A_CONTRACT record of the same subject and the same book
    (SM-10's reading: equal ``book_code``, or none on both). A second person has since concluded
    the opposite: nothing false is recorded, and the overtaken record keeps its status. A record
    that is still SUBMITTED is not touched — its hold follows its own review. Answers the holds
    released; the caller (``review_judgement``) holds the contract's locks and computes the
    group once, behind every release."""
    if _text(row["topic"]) != JudgementTopic.COLLECTIBILITY.value or row["contract_id"] is None:
        return []
    book = row["book_code"]
    overtaken = uow.session.execute(
        select(judgement_record.c.judgement_no)
        .where(
            judgement_record.c.id != row["id"],
            judgement_record.c.topic == JudgementTopic.NOT_A_CONTRACT.value,
            judgement_record.c.subject_type == row["subject_type"],
            judgement_record.c.subject_id == row["subject_id"],
            judgement_record.c.contract_id == row["contract_id"],
            judgement_record.c.status == JudgementStatus.REVIEWED.value,
            judgement_record.c.book_code.is_(None)
            if book is None
            else judgement_record.c.book_code == book,
        )
        .order_by(judgement_record.c.judgement_no)
    ).scalars()
    released: list[UUID] = []
    for judgement_no in overtaken:
        released += holds.release_system_holds(
            uow,
            UUID(str(row["contract_id"])),
            reason=holds.judgement_hold_reason(judgement_no, JudgementTopic.NOT_A_CONTRACT.value),
            comment=holds.OVERTAKEN_RELEASE_COMMENT.format(
                judgement_no=judgement_no, overtaken_by=row["judgement_no"]
            ),
        )
    return released


def _recompute_contract(uow: UnitOfWork, contract_id: UUID) -> None:
    """The engine reads reviewed outcome members, so the contract's group is computed again; a large
    group defers ``CONTRACT_COMPUTE`` (RCP-18). The caller (``review_judgement``) already holds the
    group row, the record and the contract row on the DG-KRN-DB-08 order, so the group ``UPDATE``
    and ``compute_group``'s own locks below re-lock held rows (D-98 candidate 101c)."""
    session = uow.session
    group_id = session.execute(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    ).scalar_one_or_none()
    if group_id is None:
        return
    group = UUID(str(group_id))
    session.execute(
        update(combination_group)
        .where(
            combination_group.c.tenant_id == uow.principal.tenant_id,
            combination_group.c.id == group,
        )
        .values(
            # 05 RCP-17 rev 1.207 (item COMPUTE-BEHIND-GROUP-1): a mark is never moved back
            dirty_since=func.greatest(combination_group.c.dirty_since, uow.now),
            **_stamps(uow),
            row_version=combination_group.c.row_version + 1,
        )
    )
    outcome = None
    if obligation_count(session, group) <= OBLIGATION_BUDGET:
        outcome = compute_group(uow, group, budget_seconds=ENGINE_BUDGET_SECONDS)
    if outcome is None or outcome.deferred:
        defer_compute(uow, group, contract_id=contract_id)


def review_judgement(uow: UnitOfWork, judgement_id: UUID, approval_request_id: UUID) -> None:
    """``on_approved`` of ``JUDGEMENT_RECORD``: REVIEWED by the deciding person (DB-10)."""
    session = uow.session
    row = _locked_record(session, judgement_id)  # DG-KRN-DB-08: group, record, contract
    # DG-KRN-APR-05 rev 1.40 (D-98 candidate 101d): the approved basis re-validated under the locks.
    approvals.assert_fresh_basis(uow, approval_request_id)
    principal = uow.principal
    reviewer = principal.id if principal.kind is PrincipalKind.USER else None
    transitions.apply(
        session,
        OBJECT_TYPE,
        judgement_id,
        to_status=JudgementStatus.REVIEWED.value,
        expected_status=JudgementStatus.SUBMITTED.value,
        set_values={
            "reviewer_id": reviewer,
            "reviewed_at": uow.now,
            "approval_request_id": approval_request_id,
            **_stamps(uow),
        },
    )
    _status_audit(
        uow,
        row,
        JudgementStatus.SUBMITTED.value,
        JudgementStatus.REVIEWED.value,
        approval_request_id=str(approval_request_id),
    )
    _supersede(uow, row)
    _overtake(uow, row)
    if row["contract_id"] is not None:
        contract_id = UUID(str(row["contract_id"]))
        topic = JudgementTopic(_text(row["topic"]))
        if topic is not JudgementTopic.NOT_A_CONTRACT:
            # Item STEP1-HOLD-RELEASE-1 (04 T-CON-20 "Judgement holds" (a), rev 1.209): the
            # review of a NOT_A_CONTRACT record releases nothing — from the review to the
            # assessment that cites the record the book would recognise revenue under a
            # reviewed "not a contract". ``events.record_events`` releases it with that
            # assessment.
            holds.release_system_holds(
                uow,
                contract_id,
                reason=_hold_reason(row, topic),
                comment=holds.JUDGEMENT_RELEASE_COMMENT.format(judgement_no=row["judgement_no"]),
            )
        _recompute_contract(uow, contract_id)


def reject_judgement(uow: UnitOfWork, judgement_id: UUID, approval_request_id: UUID) -> None:
    """``on_rejected`` and ``on_voided`` of ``JUDGEMENT_RECORD`` (L4-1-Q-12)."""
    record = transitions.apply(
        uow.session,
        OBJECT_TYPE,
        judgement_id,
        to_status=JudgementStatus.REJECTED.value,
        expected_status=JudgementStatus.SUBMITTED.value,
        set_values=_stamps(uow),
    )
    _status_audit(
        uow,
        record,
        JudgementStatus.SUBMITTED.value,
        JudgementStatus.REJECTED.value,
        approval_request_id=str(approval_request_id),
    )


register_lifecycle(
    ApprovalSubjectType.JUDGEMENT_RECORD,
    SubjectLifecycle(
        on_approved=review_judgement, on_rejected=reject_judgement, on_voided=reject_judgement
    ),
)


# --- reads ---------------------------------------------------------------------------------------


def judgements_statement(
    *,
    topics: Sequence[JudgementTopic] = (),
    statuses: Sequence[JudgementStatus] = (),
    subject_type: str | None = None,
    subject_id: UUID | None = None,
) -> Select[Any]:
    """``GET /judgements`` filtered by the API-R-33 parameters: the records the session reads
    (``read_by_the_session``)."""
    conditions: list[ColumnElement[bool]] = [read_by_the_session()]
    if topics:
        conditions.append(judgement_record.c.topic.in_([value.value for value in topics]))
    if statuses:
        conditions.append(judgement_record.c.status.in_([value.value for value in statuses]))
    if subject_type is not None:
        conditions.append(judgement_record.c.subject_type == subject_type)
    if subject_id is not None:
        conditions.append(judgement_record.c.subject_id == subject_id)
    return select(judgement_record).where(and_(*conditions))


def _overtaken(session: Session, rows: Sequence[Mapping[str, Any]]) -> dict[UUID, step1.Record]:
    """``overtaken_by`` of the rows (item STEP1-CITE-LATEST-1): the reader the events route asks
    (``step1.overtaken``), so a record reads as overtaken exactly where an assessment that
    cites it is refused. Only a REVIEWED record of a Step 1 topic can be overtaken; a page
    without one costs no query."""
    step1_topics = step1.PROBABLE_TOPICS | step1.NOT_PROBABLE_TOPICS
    ids = [
        row["id"]
        for row in rows
        if _text(row["topic"]) in step1_topics
        and _text(row["status"]) == JudgementStatus.REVIEWED.value
    ]
    if not ids:
        return {}
    return step1.overtaken(session, step1.records(session, ids).values())


def judgement_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[JudgementOut]:
    names = approval_queries.display_names(
        session, [row["created_by"] for row in rows] + [row["reviewer_id"] for row in rows]
    )
    overtaken = _overtaken(session, rows)
    found = []
    for row in rows:
        reviewer = row["reviewer_id"]
        book = row["book_code"]
        by = overtaken.get(UUID(str(row["id"])))
        found.append(
            JudgementOut.model_validate(
                {
                    "id": row["id"],
                    "judgement_no": row["judgement_no"],
                    "topic": _text(row["topic"]),
                    "subject_type": row["subject_type"],
                    "subject_id": row["subject_id"],
                    "contract_id": row["contract_id"],
                    "book": None if book is None else _text(book),
                    "conclusion": row["conclusion"],
                    "rationale": row["rationale"],
                    "alternatives_considered": row["alternatives_considered"],
                    "codification_refs": list(row["codification_refs"] or ()),
                    "questionnaire": row["questionnaire"],
                    "status": _text(row["status"]),
                    "reviewer": None
                    if reviewer is None
                    else approval_queries.actor(
                        UUID(str(reviewer)), PrincipalKind.USER.value, names
                    ),
                    "reviewed_at": row["reviewed_at"],
                    "approval_request_id": row["approval_request_id"],
                    "content_sha256": None
                    if row["content_sha256"] is None
                    else str(row["content_sha256"]).strip(),
                    "supersedes_id": row["supersedes_id"],
                    "overtaken_by": None
                    if by is None
                    else {"id": by.id, "judgement_no": by.judgement_no},
                    "created_by": approval_queries.actor(
                        row["created_by"], _text(row["created_by_kind"]), names
                    ),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        )
    return found


def get_judgement(session: Session, judgement_id: UUID) -> JudgementOut:
    (item,) = judgement_outs(session, [_row(session, judgement_id)])
    return item
