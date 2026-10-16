"""Tenant-wide release-validation population from one database statement (RCP-29)."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, distinct, func, or_, select

from erev_api.db.tables import (
    book,
    combination_group,
    combination_group_member,
    contract,
    contract_event,
    contract_version,
    obligation_version,
    period,
    period_state,
    subledger_line,
    subledger_posting,
    subledger_posting_seal,
)
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

from .release_validation import GroupFacts


@dataclass(frozen=True, slots=True)
class PopulationFacts:
    groups: tuple[GroupFacts, ...]
    required_entity_ids: tuple[UUID, ...]


def read(uow: UnitOfWork) -> PopulationFacts:
    """Read complete tenant facts; never widen a restricted caller's entity scope.

    All correlated observations share a single statement snapshot, including source heads.
    The eventual attempt writer must persist these facts before dispatching any child job.
    """
    if uow.principal.db_context.entity_scope != "*":
        raise Problem("forbidden", "Release validation requires the complete tenant population.")
    tenant_id = uow.principal.tenant_id
    group = combination_group.c
    member = combination_group_member.c
    current_member = and_(
        member.tenant_id == tenant_id,
        member.combination_group_id == group.id,
        member.valid_to_known_at.is_(None),
    )
    open_state = period_state.c.state.in_(("open", "closing", "reopened"))
    event_activity = (
        select(contract_event.c.id)
        .select_from(
            combination_group_member.join(
                contract_event,
                and_(
                    contract_event.c.tenant_id == member.tenant_id,
                    contract_event.c.contract_id == member.contract_id,
                ),
            )
            .join(
                period_state,
                and_(
                    period_state.c.tenant_id == contract_event.c.tenant_id,
                    period_state.c.entity_id == contract_event.c.contracting_entity_id,
                ),
            )
            .join(
                period,
                and_(
                    period.c.tenant_id == period_state.c.tenant_id,
                    period.c.id == period_state.c.period_id,
                ),
            )
        )
        .where(
            current_member,
            open_state,
            contract_event.c.effective_date >= period.c.start_date,
            contract_event.c.effective_date <= period.c.end_date,
        )
        .correlate(combination_group)
        .exists()
    )
    ledger_activity = (
        select(subledger_line.c.id)
        .select_from(
            subledger_posting.join(
                subledger_posting_seal,
                and_(
                    subledger_posting_seal.c.tenant_id == subledger_posting.c.tenant_id,
                    subledger_posting_seal.c.subledger_posting_id == subledger_posting.c.id,
                ),
            )
            .join(
                subledger_line,
                and_(
                    subledger_line.c.tenant_id == subledger_posting.c.tenant_id,
                    subledger_line.c.subledger_posting_id == subledger_posting.c.id,
                ),
            )
            .join(
                contract,
                and_(
                    contract.c.tenant_id == subledger_line.c.tenant_id,
                    contract.c.id == subledger_line.c.contract_id,
                ),
            )
            .join(
                period_state,
                and_(
                    period_state.c.tenant_id == subledger_line.c.tenant_id,
                    period_state.c.entity_id == contract.c.contracting_entity_id,
                    period_state.c.period_id == subledger_line.c.period_id,
                    period_state.c.book_code == subledger_line.c.book_code,
                ),
            )
        )
        .where(
            subledger_posting.c.tenant_id == tenant_id,
            subledger_posting.c.combination_group_id == group.id,
            open_state,
        )
        .correlate(combination_group)
        .exists()
    )
    strata = (
        select(
            func.jsonb_agg(
                distinct(
                    func.jsonb_build_array(
                        obligation_version.c.book_code, obligation_version.c.recognition_method
                    )
                )
            )
        )
        .select_from(
            contract_version.join(
                obligation_version,
                and_(
                    obligation_version.c.tenant_id == contract_version.c.tenant_id,
                    obligation_version.c.contract_version_id == contract_version.c.id,
                ),
            ).join(
                book,
                and_(
                    book.c.tenant_id == contract_version.c.tenant_id,
                    book.c.code == contract_version.c.book_code,
                ),
            )
        )
        .where(
            contract_version.c.tenant_id == tenant_id,
            contract_version.c.contract_computation_id == group.head_computation_id,
            book.c.is_enabled.is_(True),
        )
        .correlate(combination_group)
        .scalar_subquery()
    )
    entities = (
        select(func.array_agg(distinct(contract.c.contracting_entity_id)))
        .select_from(
            combination_group_member.join(
                contract,
                and_(contract.c.tenant_id == member.tenant_id, contract.c.id == member.contract_id),
            )
        )
        .where(current_member)
        .correlate(combination_group)
        .scalar_subquery()
    )
    rows = (
        uow.session.execute(
            select(
                group.id,
                group.head_computation_id,
                or_(event_activity, ledger_activity).label("open_activity"),
                strata.label("strata"),
                entities.label("entities"),
            )
            .where(group.tenant_id == tenant_id)
            .order_by(group.id)
        )
        .mappings()
        .all()
    )
    return PopulationFacts(
        groups=tuple(
            GroupFacts(
                row["id"],
                row["head_computation_id"],
                row["open_activity"],
                frozenset(tuple(pair) for pair in row["strata"] or ()),
            )
            for row in rows
        ),
        required_entity_ids=tuple(
            sorted({entity for row in rows for entity in row["entities"] or ()}, key=str)
        ),
    )
