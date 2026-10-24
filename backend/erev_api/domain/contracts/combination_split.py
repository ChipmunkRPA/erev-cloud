"""Read-only prospective split allocation from authenticated original computation evidence."""

from datetime import date
from uuid import UUID

from sqlalchemy import select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import combination_group, contract
from erev_api.domain.contracts import queries
from erev_api.domain.reports.computation_sources import read_for_report
from erev_api.problems import Problem
from erev_api.schemas.combinations import (
    CombinationSplitMemberOut,
    CombinationSplitObligationOut,
    CombinationSplitPreviewOut,
)
from erev_api.uow import UnitOfWork
from erev_engine.combination_split import prepare
from erev_engine.errors import EngineError


def preview(
    uow: UnitOfWork,
    group_id: UUID,
    effective_date: date,
    leave_contract_ids: list[UUID],
    book_code: str | None,
) -> CombinationSplitPreviewOut:
    group = (
        uow.session.execute(select(combination_group).where(combination_group.c.id == group_id))
        .mappings()
        .one_or_none()
    )
    if group is None:
        raise Problem("not-found")
    members = (
        uow.session.execute(select(contract).where(contract.c.combination_group_id == group_id))
        .mappings()
        .all()
    )
    if not members:
        raise Problem("not-found")
    for member in members:
        require_for_entity(uow.ctx, "contract.read", member["contracting_entity_id"])
    if group["dirty_since"] is not None or group["head_computation_id"] is None:
        raise Problem("validation-failed", "Recompute the entire combination before split preview.")
    leaving = set(leave_contract_ids)
    if (
        not leaving
        or len(leaving) != len(leave_contract_ids)
        or not leaving <= {m["id"] for m in members}
    ):
        raise Problem(
            "validation-failed", "Select unique original members leaving this combination."
        )
    original = read_for_report(uow, group["head_computation_id"], permission="contract.read")
    if original.group_id != group_id or set(original.bundle.group.member_contract_keys) != {
        m["external_id"] for m in members
    }:
        raise Problem(
            "validation-failed", "The source computation differs from the current population."
        )
    destinations = {
        m["external_id"]: f"SINGLETON:{m['external_id']}"
        if m["id"] in leaving
        else str(group["code"])
        for m in members
    }
    try:
        plan = prepare(
            original.bundle,
            book_code=book_code or queries.primary_book(uow.session),
            destinations=destinations,
            effective_date=effective_date,
        )
    except (ValueError, EngineError) as error:
        raise Problem("validation-failed", str(error)) from error
    ids = {m["external_id"]: m["id"] for m in members}
    return CombinationSplitPreviewOut(
        group_id=group_id,
        source_computation_id=original.computation_id,
        input_sha256=plan.input_sha256,
        output_sha256=original.output_sha256,
        book_code=plan.book_code,
        currency=plan.currency,
        effective_date=plan.effective_date,
        boundary_position=plan.boundary_position,
        recognized_minor=plan.recognized_minor,
        unrecognized_minor=plan.unrecognized_minor,
        currency_minor_unit=original.bundle.currencies[plan.currency].minor_unit,
        members=[
            CombinationSplitMemberOut(
                contract_id=ids[m.contract_key],
                contract_key=m.contract_key,
                destination=m.destination,
                recognized_minor=m.recognized_minor,
                remaining_before_minor=m.remaining_before_minor,
                remaining_after_minor=m.remaining_after_minor,
                remaining_ssp=str(m.remaining_ssp),
                obligations=[
                    CombinationSplitObligationOut(
                        obligation_key=r.obligation_key,
                        recognized_minor=r.recognized_minor,
                        remaining_before_minor=r.remaining_minor,
                        remaining_after_minor=dict(m.obligation_shares)[r.obligation_key],
                        remaining_ssp=str(r.remaining_ssp),
                        ssp_sources=[
                            {"ref_type": s.ref_type, "ref_id": s.ref_id, "detail": dict(s.detail)}
                            for s in r.remaining_ssp_sources
                        ],
                    )
                    for r in m.original
                ],
            )
            for m in plan.members
        ],
    )
