"""Read-only prospective split allocation from authenticated original computation evidence."""

from datetime import date
from uuid import UUID

from erev_engine.combination_split import prepare
from erev_engine.errors import EngineError
from sqlalchemy import select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import combination_group, contract
from erev_api.domain.contracts import queries
from erev_api.domain.reports.computation_sources import read_for_report
from erev_api.problems import Problem
from erev_api.schemas.combinations import (
    CombinationSplitBalanceRowOut,
    CombinationSplitBalancesOut,
    CombinationSplitMemberOut,
    CombinationSplitObligationOut,
    CombinationSplitPreviewOut,
)
from erev_api.uow import UnitOfWork


def preview(
    uow: UnitOfWork,
    group_id: UUID,
    effective_date: date,
    leave_contract_ids: list[UUID],
    book_code: str | None,
    balance_as_of: date | None = None,
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
    from erev_engine import ENGINE_VERSION
    from erev_engine.combination_membership import membership_at
    from erev_engine.stages import s01_canonicalize
    from erev_engine.trace import TraceBuilder

    canonical = s01_canonicalize.run(original.bundle, TraceBuilder(engine_version=ENGINE_VERSION))
    current = membership_at(
        original.bundle.group.group_key,
        canonical.contracts,
        canonical.events,
        effective_date=effective_date,
    )
    source_groups = {current[m["external_id"]] for m in members if m["id"] in leaving}
    if len(source_groups) != 1:
        raise Problem("validation-failed", "Select leaving members from one effective combination.")
    source_group = next(iter(source_groups))
    selected = [m for m in members if current[m["external_id"]] == source_group]
    if len(selected) < 2:
        raise Problem("validation-failed", "A singleton cannot be split again.")
    destinations = {
        m["external_id"]: f"SINGLETON:{m['external_id']}" if m["id"] in leaving else source_group
        for m in selected
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
    balance_preview = None
    if balance_as_of is not None:
        from erev_engine.combination_split_balances import calculate, preview_input

        if balance_as_of < effective_date:
            raise Problem("validation-failed", "Balance date must be on or after the split date.")
        try:
            candidate = preview_input(
                original.bundle, effective_date=effective_date, destinations=destinations
            )
            calculated = calculate(candidate, book_code=plan.book_code, as_of=balance_as_of)
        except (ValueError, EngineError) as error:
            raise Problem("validation-failed", str(error)) from error
        rows = []
        for destination in calculated:
            for entity in sorted({target.entity for target in destination.presentation}):
                amounts = {
                    target.measure: target.value
                    for target in destination.presentation
                    if target.entity == entity
                }
                rows.append(
                    CombinationSplitBalanceRowOut(
                        destination=destination.destination,
                        entity=entity,
                        member_contract_keys=list(destination.member_contract_keys),
                        contract_liability_minor=amounts["contract_liability"],
                        contract_asset_minor=amounts["contract_asset"],
                        unbilled_receivable_minor=amounts["unbilled_receivable"],
                        trace_sha256=destination.trace.sha256(),
                    )
                )
        balance_preview = CombinationSplitBalancesOut(
            as_of=balance_as_of, preview_input_sha256=candidate.sha256(), rows=rows
        )
    ids = {m["external_id"]: m["id"] for m in members}
    return CombinationSplitPreviewOut(
        balance_preview=balance_preview,
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
                        recognized_minor=r.recognized_total_minor
                        if r.recognized_total_minor is not None
                        else r.recognized_minor,
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
