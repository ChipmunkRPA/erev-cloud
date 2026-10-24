"""Refuse acquired members silently omitted by an absent persisted balance row."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, select

from erev_api.db.tables import contract, contract_event, contract_version_balance, legal_entity
from erev_api.problems import ProblemError
from erev_api.uow import UnitOfWork

from . import acquisition_evidence, tie_outs
from .builders import ReportParams

KEY = "acquisition_balance_population_v1"


def require_rows(
    uow: UnitOfWork,
    params: ReportParams,
    *,
    entity_ids: Sequence[UUID],
    book: str,
    periods: Mapping[UUID, tie_outs.PeriodRef | None],
    cutoff: datetime,
    contract_id: UUID | None,
    locked_ends: tie_outs.LockedEnds | None,
) -> None:
    if params.binding is not None and not params.binding.evidence.get(KEY):
        return
    tie_outs.record_evidence(params, KEY, True)
    versions = tie_outs.versions_for(uow.session, params, book_code=book, cutoff=cutoff)
    chain = tie_outs.chain_latest(
        book_code=book,
        cutoff=cutoff,
        commit_cutoff=cutoff if params.historical and params.binding is None else None,
        versions=versions if params.binding is not None else None,
        only_contract=contract_id,
    ).subquery()
    balance = contract_version_balance.c
    missing = (
        ~select(balance.id)
        .where(
            balance.contract_id == contract.c.id,
            balance.contract_version_id == chain.c.id,
        )
        .exists()
    )
    candidate = (
        select(contract_event.c.id)
        .where(
            contract_event.c.contract_id == contract.c.id,
            contract_event.c.event_type == "OPENING_BALANCE_ESTABLISHED",
            contract_event.c.payload["reason"].astext == "BUSINESS_COMBINATION",
        )
        .exists()
    )
    rows = uow.session.execute(
        select(
            contract.c.external_id,
            contract.c.contracting_entity_id,
            legal_entity.c.code,
            chain.c.id.label("version_id"),
        )
        .select_from(
            contract.join(chain, chain.c.contract_id == contract.c.id).join(
                legal_entity,
                and_(
                    legal_entity.c.id == contract.c.contracting_entity_id,
                    legal_entity.c.tenant_id == contract.c.tenant_id,
                ),
            )
        )
        .where(
            contract.c.contracting_entity_id.in_(entity_ids),
            chain.c.status_in_book.in_(tie_outs.INCLUDED_STATUSES),
            missing,
            candidate,
        )
        .order_by(contract.c.external_id, legal_entity.c.code)
    ).mappings()
    errors = []
    for row in rows:
        at = periods.get(row["contracting_entity_id"])
        if at is None or (
            locked_ends is not None and locked_ends.at(row["contracting_entity_id"], at) is not None
        ):
            continue
        bundle, _, _ = acquisition_evidence.load(uow, row["version_id"], book)
        voided = {
            event.supersedes_event_key
            for event in bundle.events
            if event.event_type == "EVENT_VOIDED"
        }
        if not any(
            event.contract_key == row["external_id"]
            and event.event_type == "OPENING_BALANCE_ESTABLISHED"
            and event.event_key not in voided
            and event.payload.get("reason") == "BUSINESS_COMBINATION"
            and str(event.payload.get("cutover_date")) <= at.end.isoformat()
            for event in bundle.events
        ):
            continue
        errors.append(
            ProblemError(
                field=f"balances[{row['external_id']}@{row['code']}]",
                rule_id=tie_outs.RULE_PERIOD_BALANCE,
                message=(
                    f"Contract {row['external_id']} in entity {row['code']}: contract version "
                    f"{row['version_id']} has original acquisition evidence but no persisted "
                    f"member balance row for {at.key}. Complete period balances are unavailable; "
                    "the contract cannot be omitted or reported as zero."
                ),
            )
        )
    if errors:
        raise tie_outs.BalanceUnreadable(errors)
