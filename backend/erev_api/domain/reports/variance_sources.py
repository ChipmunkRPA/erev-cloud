"""Load frozen close endpoints and authorized retained computation candidates.

This is the read phase, before any DRY_RUN. A selected candidate must subsequently
reproduce the frozen endpoints; selection alone is not a reproduction claim. No
input is rebuilt from live configuration. Every source group must remain readable,
including its performing entities, even when the report displays a single entity.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import (
    contract,
    contract_computation,
    contract_version,
    legal_entity,
    obligation_version,
)
from erev_api.domain.reports import (
    computation_sources,
    evidence_close,
    locked,
    tie_outs,
    variance_measures,
)
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


@dataclass(frozen=True)
class Side:
    frozen: evidence_close.FrozenClose
    computations: Mapping[UUID, computation_sources.VerifiedComputation]
    contract_computations: Mapping[str, UUID]


@dataclass(frozen=True)
class Pair:
    earlier: Side
    later: Side
    required_entity_ids: tuple[UUID, ...]


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Close variance sources: {detail}")


def _side(uow: UnitOfWork, frozen: evidence_close.FrozenClose) -> Side:
    scope = frozen.scope
    cutoff = frozen.record["cutoff_known_at"]
    if not isinstance(cutoff, datetime):
        raise _refuse("the lock has no recorded input cutoff.")
    # Include zero/exempt rows too; their contract may change disclosure eligibility.
    wanted = {
        str(row["contract_external_id"])
        for report in frozen.reports
        if report.report_code in {"revenue_waterfall", "contract_balances", "rpo"}
        for row in locked.report_data(report.dataset).rows
    }
    if "" in wanted:
        raise _refuse("a frozen monetary row has no contract identity.")
    # A recompute with no new event can retain an old version.known_at. Filter
    # actual computation availability BEFORE choosing the latest chain member.
    eligible = (
        tuple(
            uow.session.execute(
                select(contract_version.c.id)
                .join(
                    contract_computation,
                    (contract_computation.c.id == contract_version.c.contract_computation_id)
                    & (contract_computation.c.tenant_id == contract_version.c.tenant_id),
                )
                .where(
                    contract_version.c.tenant_id == uow.principal.tenant_id,
                    contract_version.c.book_code == scope.book_code,
                    contract_version.c.created_at <= cutoff,
                    contract_computation.c.created_at <= cutoff,
                    contract_computation.c.cutoff_at <= cutoff,
                    contract_computation.c.status == "SUCCEEDED",
                    contract_version.c.id.in_(
                        select(obligation_version.c.contract_version_id)
                        .join(
                            contract,
                            (contract.c.id == obligation_version.c.contract_id)
                            & (contract.c.tenant_id == obligation_version.c.tenant_id),
                        )
                        .where(contract.c.external_id.in_(wanted))
                    ),
                )
            ).scalars()
        )
        if wanted
        else ()
    )
    selected = (
        (
            uow.session.execute(
                select(contract.c.external_id, contract_version.c.contract_computation_id)
                .select_from(obligation_version)
                .join(
                    contract,
                    (contract.c.id == obligation_version.c.contract_id)
                    & (contract.c.tenant_id == obligation_version.c.tenant_id),
                )
                .join(
                    contract_version,
                    (contract_version.c.id == obligation_version.c.contract_version_id)
                    & (contract_version.c.tenant_id == obligation_version.c.tenant_id),
                )
                .where(
                    contract.c.tenant_id == uow.principal.tenant_id,
                    contract.c.external_id.in_(wanted),
                    contract_version.c.book_code == scope.book_code,
                    tie_outs.read_from(
                        contract.c.id,
                        contract_version.c.id,
                        book_code=scope.book_code,
                        cutoff=cutoff,
                        created_cutoff=cutoff,
                        statuses=None,
                        versions=eligible,
                    ),
                )
                .distinct()
            ).all()
        )
        if wanted
        else []
    )
    by_contract: dict[str, UUID] = {}
    for name, computation_id in selected:
        if computation_id is None or (name in by_contract and by_contract[name] != computation_id):
            raise _refuse("a frozen contract has no unique retained computation candidate.")
        by_contract[name] = computation_id
    if set(by_contract) != wanted:
        raise _refuse("a frozen contract has no readable computation at the lock cutoff.")
    computations = {}
    for computation_id in sorted(set(by_contract.values()), key=str):
        source = computation_sources.read_for_report(uow, computation_id)
        created_at = uow.session.execute(
            select(contract_computation.c.created_at).where(
                contract_computation.c.tenant_id == uow.principal.tenant_id,
                contract_computation.c.id == computation_id,
            )
        ).scalar_one()
        if source.bundle.known_at > cutoff or created_at > cutoff:
            raise _refuse("a computation was not available at the lock cutoff.")
        if scope.book_code not in {book.book_code for book in source.bundle.books}:
            raise _refuse("a computation does not contain the lock's book.")
        computations[computation_id] = source
    return Side(frozen, MappingProxyType(computations), MappingProxyType(by_contract))


def read_pair(
    uow: UnitOfWork,
    *,
    from_period_lock_id: UUID,
    to_period_lock_id: UUID,
    entity_ids: Sequence[UUID],
) -> Pair:
    """Read both complete frozen sources and all required original computation files."""
    if "report.run" not in uow.principal.permissions or not uow.principal.permission_scopes.get(
        "report.run"
    ):
        raise Problem("forbidden")
    scopes = [
        locked.lock_scope(uow.session, key) for key in (from_period_lock_id, to_period_lock_id)
    ]
    if any(scope is None or scope.entity_id not in entity_ids for scope in scopes):
        raise Problem("not-found")
    earlier = evidence_close.read_for_report(uow, from_period_lock_id)
    later = evidence_close.read_for_report(uow, to_period_lock_id)
    # Scope/order and monetary shape checks run before computation evidence access.
    variance_measures.compare(earlier, later)
    sides = (_side(uow, earlier), _side(uow, later))
    required_codes = {
        entity.code
        for side in sides
        for source in side.computations.values()
        for entity in source.bundle.entities
    }
    rows = uow.session.execute(
        select(legal_entity.c.id, legal_entity.c.code).where(
            legal_entity.c.tenant_id == uow.principal.tenant_id,
            legal_entity.c.code.in_(required_codes),
        )
    ).all()
    if {row.code for row in rows} != required_codes:
        raise Problem("not-found")
    required = {earlier.scope.entity_id, *(row.id for row in rows)}
    return Pair(*sides, tuple(sorted(required, key=str)))
