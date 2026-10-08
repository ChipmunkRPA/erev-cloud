"""Resolve RPS-16 request selectors before creating a pack or dispatching its job.

All four packs contain audit/access evidence, so their source population intersects
``report.run`` and ``audit.read`` scope (API-R-42; report framework R-13/R-28/R-63).
This reads identities only. Collectors must still enforce their content permissions,
read the selected immutable/as-of sources, and verify completeness. Download also
requires ``evidence.export`` and fresh authorization of the complete stored population.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import contract, legal_entity, period_lock
from erev_api.domain.reports import locked
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.evidence_packs import (
    ClosePackCreateIn,
    ContractSamplePackCreateIn,
    EvidencePackCreateIn,
)
from erev_api.uow import UnitOfWork

SOURCE_PERMISSIONS: Final = ("report.run", "audit.read")


@dataclass(frozen=True, slots=True)
class SourceSelection:
    """Bound identities, never a claim that their evidence has been collected.

    ``known_at`` is the generation request's cutoff. A CLOSE pack's frozen datasets
    use ``lock_known_at`` instead; auxiliary evidence must identify its own basis.
    Contract IDs retain the submitted order. Entity IDs are sorted and deduplicated.
    """

    tenant_id: UUID
    known_at: datetime
    entity_ids: tuple[UUID, ...]
    contract_ids: tuple[UUID, ...] = ()
    lock: locked.LockScope | None = None
    lock_known_at: datetime | None = None


def _entities(uow: UnitOfWork) -> frozenset[UUID]:
    principal = uow.principal
    scopes = []
    for permission in SOURCE_PERMISSIONS:
        scope = principal.permission_scopes.get(permission)
        if permission not in principal.permissions or scope is None or scope == frozenset():
            raise Problem("forbidden")
        if scope != "*":
            scopes.append(scope)
    # RLS applies the transaction's entity scope too; never widen it to a permission wildcard.
    rows = uow.session.execute(
        select(legal_entity.c.id).where(legal_entity.c.tenant_id == principal.tenant_id)
    ).scalars()
    return frozenset(entity_id for entity_id in rows if all(entity_id in scope for scope in scopes))


def resolve(uow: UnitOfWork, request: EvidencePackCreateIn) -> SourceSelection:
    """Resolve the entire request or refuse it; no writes, partial sample, or scope fallback.

    Invoke inside the caller's unit of work, following the route's audited permission
    guards. SYSTEM jobs have no implicit permission to resolve a fresh population.
    Missing and unauthorized source identities both produce an unlabelled 404.
    """
    entities = _entities(uow)
    if isinstance(request, ClosePackCreateIn):
        scope = locked.lock_scope(uow.session, request.period_lock_id)
        if scope is None or scope.entity_id not in entities:
            raise Problem("not-found")
        errors = []
        for field, supplied, actual in (
            ("entity_code", request.entity_code, scope.entity_code),
            ("book", request.book, scope.book_code),
            ("period_key", request.period_key, scope.period_key),
        ):
            if supplied != actual:
                errors.append(
                    ProblemError(
                        field=field,
                        rule_id="S15-R-19",
                        message=f"{field} must be {actual}, the value of the selected lock.",
                    )
                )
        refusal = locked.froze_nothing(uow.session, scope)
        if refusal is not None:
            errors.append(ProblemError(field="period_lock_id", rule_id="S15-R-19", message=refusal))
        if errors:
            raise Problem("validation-failed", errors=errors)
        cutoff = uow.session.execute(
            select(period_lock.c.cutoff_known_at).where(
                period_lock.c.tenant_id == uow.principal.tenant_id,
                period_lock.c.id == scope.lock_id,
            )
        ).scalar_one()
        # The database requires this on LOCK. Never replace a corrupt/missing basis with now.
        if cutoff is None:
            raise Problem("validation-failed", "The selected lock has no freeze cutoff.")
        return SourceSelection(
            uow.principal.tenant_id, uow.now, (scope.entity_id,), lock=scope, lock_known_at=cutoff
        )
    if isinstance(request, ContractSamplePackCreateIn):
        rows = uow.session.execute(
            select(contract.c.external_id, contract.c.id, contract.c.contracting_entity_id).where(
                contract.c.tenant_id == uow.principal.tenant_id,
                contract.c.external_id.in_(request.contract_external_ids),
                contract.c.contracting_entity_id.in_(entities),
            )
        ).tuples()
        found = {external_id: (identity, entity) for external_id, identity, entity in rows}
        if len(found) != len(request.contract_external_ids):
            raise Problem("not-found")
        selected = [found[key] for key in request.contract_external_ids]
        return SourceSelection(
            uow.principal.tenant_id,
            uow.now,
            tuple(sorted({entity for _, entity in selected})),
            tuple(identity for identity, _ in selected),
        )
    return SourceSelection(uow.principal.tenant_id, uow.now, tuple(sorted(entities)))
