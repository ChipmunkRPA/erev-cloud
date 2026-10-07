"""Contract reads and locks shared by the contract commands (dev-guide §6.1 DG-CMD-02, DG-CMD-14;
04 T-CON-01, T-CON-03, T-CON-04, T-CON-05, T-CON-10; BUILD_SPEC CTR-1).

Every read runs in the caller's session under its tenant context and entity scope, so a row outside
the scope is "not visible" exactly as a missing row is (REQ-PLT-012).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Final
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    FromClause,
    Uuid,
    and_,
    case,
    cast,
    column,
    exists,
    func,
    or_,
    select,
    true,
)
from sqlalchemy.orm import Session

# The one lock order for every path that takes both the group and a contract row (DG-KRN-DB-08 rev
# 1.36; D-98 101a / 101b) lives in the kernel so that approval hooks share it; re-exported here.
from erev_api.db.locking import REGROUPED as REGROUPED
from erev_api.db.locking import lock_group_then_contract as lock_group_then_contract
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import (
    combination_group,
    combination_group_member,
    contract,
    contract_event,
    judgement_record,
    obligation,
)
from erev_api.problems import Problem


def get_contract(
    session: Session, contract_id: UUID, *, for_update: bool = False
) -> dict[str, Any]:
    """The contract row; 404 ``not-found`` when it is not visible."""
    statement = select(contract).where(contract.c.id == contract_id)
    if for_update:
        statement = statement.with_for_update()
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return dict(row)


def contract_by_external_id(session: Session, external_id: str) -> dict[str, Any] | None:
    statement = select(contract).where(contract.c.external_id == external_id)
    row = session.execute(statement).mappings().one_or_none()
    return None if row is None else dict(row)


def lock_group(session: Session, group_id: UUID) -> dict[str, Any]:
    """The combination group row, locked ``FOR UPDATE``; 404 ``not-found`` when not visible."""
    statement = select(combination_group).where(combination_group.c.id == group_id)
    row = session.execute(statement.with_for_update()).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return dict(row)


def get_group(session: Session, group_id: UUID) -> dict[str, Any]:
    statement = select(combination_group).where(combination_group.c.id == group_id)
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return dict(row)


def product_reference_date(session: Session, group_id: UUID) -> date:
    """Current members' minimum inception, the calculation bundle's product reference date.

    Called after visibility/command authorization. This scalar includes other entities of the
    same tenant group, as the calculation does; no contract or entity data is returned.
    """
    member = combination_group_member
    with system_entity_scope(session):
        found = session.execute(
            select(func.min(contract.c.inception_date))
            .select_from(
                member.join(
                    contract,
                    and_(
                        contract.c.tenant_id == member.c.tenant_id,
                        contract.c.id == member.c.contract_id,
                    ),
                )
            )
            .where(member.c.combination_group_id == group_id, member.c.valid_to_known_at.is_(None))
        ).scalar_one()
    if found is None:
        raise Problem("not-found")
    assert isinstance(found, date)
    return found


def current_member(session: Session, contract_id: UUID) -> dict[str, Any] | None:
    """The contract's current membership row (``valid_to_known_at IS NULL``, T-CON-04)."""
    statement = select(combination_group_member).where(
        combination_group_member.c.contract_id == contract_id,
        combination_group_member.c.valid_to_known_at.is_(None),
    )
    row = session.execute(statement).mappings().one_or_none()
    return None if row is None else dict(row)


def obligations(session: Session, contract_id: UUID) -> list[dict[str, Any]]:
    """The contract's obligations in display order."""
    statement = (
        select(obligation)
        .where(obligation.c.contract_id == contract_id)
        .order_by(obligation.c.line_sequence, obligation.c.obligation_key)
    )
    return [dict(row) for row in session.execute(statement).mappings()]


def stream(session: Session, contract_id: UUID) -> list[dict[str, Any]]:
    """The contract's events in stream order."""
    statement = (
        select(contract_event)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )
    return [dict(row) for row in session.execute(statement).mappings()]


# --- what of a combination a session reads --------------------------------------------------------
#
# 03 REQ-PLT-012; supervisor ruling R-28 and the supervisor's ruling of 2026-10-02 on lane
# F-RPS-REG's measurement (head R28-READS). T-CON-03, T-CON-04 and T-CON-19 carry no entity and
# pass the row policy for every member; T-CON-01 is bound to its entity, so a contract the
# session may not read is no row for it. What a group or a judgement record says of a contract is
# therefore read through that contract. Until the head a member whose roles all name one entity
# listed and read the groups and the judgement records of every other entity.

# A contract id as T-CON-19's questionnaire stores it: the text of a uuid. The member is evidence
# (``schemas.db_json.EvidenceQuestionnaire``), so whatever else it holds names no contract.
_UUID_TEXT: Final = "^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$"


def _proposed(record: FromClause) -> Any:
    """The contracts the ``COMBINATION`` record ``record`` names (``questionnaire.contract_ids``)
    as rows of one uuid column, so that each is one lookup of T-CON-01 by its key. A member that
    is no list names none, and an element that is no uuid is a null row."""
    ids = record.c.questionnaire["contract_ids"]
    listed = case((func.jsonb_typeof(ids) == "array", ids), else_=func.jsonb_build_array())
    element = func.jsonb_array_elements_text(listed).column_valued("value")
    named = case((element.op("~")(_UUID_TEXT), cast(element, Uuid())), else_=None)
    return (
        func.unnest(select(func.array_agg(named)).scalar_subquery())
        .table_valued(column("id", Uuid()), name="proposed_contract")
        .render_derived()
    )


def _within(read: FromClause, within: Sequence[UUID] | None) -> ColumnElement[bool]:
    """``read`` — an alias of T-CON-01 — is a contract of one of the entities ``within``. With
    no list the row policy alone decides: any contract the session reads."""
    return true() if within is None else read.c.contracting_entity_id.in_(sorted(within, key=str))


def reads_group(
    tenant_id: ColumnElement[Any],
    group_id: ColumnElement[Any],
    *,
    within: Sequence[UUID] | None = None,
) -> ColumnElement[bool]:
    """Whether the session reads the combination group the two columns name: through a contract
    it reads that is, or was, a member of the group, or that a ``COMBINATION`` record of the
    group names — a proposed group has no member until its proposal is approved, and a group a
    leave emptied is still the group of the contracts that were in it. A group that names no
    contract at all — no membership, past or present, and no such record: the row a proposal is
    about to be written for — is the workspace's, as a judgement record that names none is.

    ``within``: the entities of a report run, which stand for its readers — a run is read by
    every member whose scope covers its entities, so what it states is decided by them and not
    by who runs it (``reports.builders.register_support.requests_in_scope``). The contracts are
    then those of these entities."""
    member = combination_group_member.alias("group_member")
    record = judgement_record.alias("group_proposal")
    read = contract.alias("member_contract")
    named_contract = contract.alias("proposed_contract_row")
    members = and_(member.c.tenant_id == tenant_id, member.c.combination_group_id == group_id)
    proposals = and_(
        record.c.tenant_id == tenant_id,
        record.c.subject_type == "combination_group",
        record.c.subject_id == group_id,
        record.c.topic == "COMBINATION",
    )
    named = _proposed(record)
    through_member = exists().where(
        members,
        read.c.tenant_id == member.c.tenant_id,
        read.c.id == member.c.contract_id,
        _within(read, within),
    )
    through_proposal = exists().where(
        proposals,
        exists()
        .select_from(named)
        .where(
            exists()
            .where(
                named_contract.c.tenant_id == record.c.tenant_id,
                named_contract.c.id == named.c.id,
                _within(named_contract, within),
            )
            .correlate(named, record)
        )
        .correlate(record),
    )
    names_none = and_(~exists().where(members), ~exists().where(proposals))
    return or_(through_member, through_proposal, names_none)


def reads_proposal(
    record: FromClause, *, within: Sequence[UUID] | None = None
) -> ColumnElement[bool]:
    """Whether the session reads EVERY contract the ``COMBINATION`` record ``record`` names. The
    record states which contracts are combined or separated — its conclusion names them — so it
    is read by a session that reads all of them, as an exception item that names no entity is
    read by whoever may read everything it is about (04 T-IMP-05, rev 1.218). A member of one
    entity of a combination across entities reads the group (``reads_group``) and not the
    record. An id of no contract — or of one the session does not read: the two are one answer —
    refuses; an element that is no uuid names nothing. ``within`` as in ``reads_group``."""
    named = _proposed(record)
    read = contract.alias("named_contract")
    unread = and_(
        named.c.id.is_not(None),
        ~exists()
        .where(
            read.c.tenant_id == record.c.tenant_id,
            read.c.id == named.c.id,
            _within(read, within),
        )
        .correlate(named, record),
    )
    return ~exists().select_from(named).where(unread).correlate(record)


def names_within(record: FromClause, within: Sequence[UUID]) -> ColumnElement[bool]:
    """Whether the ``COMBINATION`` record ``record`` names at least one contract of the entities
    ``within``: the record belongs to a report run of those entities, which states it when it
    holds every contract the record names (``reads_proposal``) and counts it otherwise."""
    named = _proposed(record)
    read = contract.alias("named_contract")
    return (
        exists()
        .select_from(named)
        .where(
            exists()
            .where(
                read.c.tenant_id == record.c.tenant_id,
                read.c.id == named.c.id,
                _within(read, within),
            )
            .correlate(named, record)
        )
        .correlate(record)
    )


def read_group(session: Session, group_id: UUID) -> dict[str, Any]:
    """The group row for a read, or for a command's first read of its subject; 404 ``not-found``
    when the session does not read the group (``reads_group``). ``get_group`` reads the row
    whoever asks, for the steps that follow an authorisation."""
    statement = select(combination_group).where(
        combination_group.c.id == group_id,
        reads_group(combination_group.c.tenant_id, combination_group.c.id),
    )
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return dict(row)
