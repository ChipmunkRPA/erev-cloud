"""Contract references for AI proposal lifecycle events, captured in their transaction."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import calc_trace, obligation_version
from erev_api.uow import UnitOfWork


def proposal_contract_ids(
    uow: UnitOfWork, *, kind: str, subject_id: UUID | None
) -> tuple[UUID, ...]:
    if kind == "CONTRACT_EXTRACTION":
        # An unaccepted extraction has no created contract, even if its source is shared.
        return ()
    if kind != "NUMBER_EXPLANATION" or subject_id is None:
        raise ValueError("AI_AUDIT_SOURCE_INVALID")
    contracts = tuple(
        uow.session.scalars(
            select(obligation_version.c.contract_id)
            .join(
                calc_trace,
                (calc_trace.c.tenant_id == obligation_version.c.tenant_id)
                & (calc_trace.c.contract_version_id == obligation_version.c.contract_version_id),
            )
            .where(
                calc_trace.c.tenant_id == uow.principal.tenant_id,
                calc_trace.c.id == subject_id,
            )
            .distinct()
            .order_by(obligation_version.c.contract_id)
        )
    )
    if not contracts:
        raise ValueError("AI_AUDIT_CONTRACTS_UNAVAILABLE")
    return contracts
