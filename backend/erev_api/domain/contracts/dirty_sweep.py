"""Recover dirty booked groups not reached by command/import computation dispatch."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import or_, select

from erev_api.auth.principal import system_principal
from erev_api.db.tables import combination_group, combination_group_member, contract_event, job
from erev_api.domain.platform.tenant_directory import active_tenants
from erev_api.enums import ComputationTrigger, JobKind
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from erev_api.jobs.registry import isolated

REQUEST_ID = "dirty-contract-sweep"


def run(runtime: JobRuntime, *, only_tenants: Sequence[UUID] | None = None) -> int:
    """Queue one computation per dirty generation, isolating each group transaction.

    The group lock serializes concurrent sweepers with fact writers. An existing live job
    already covers the group. A terminal sweep job for this mark is left to job retry or
    exception remediation, so a persistent calculation refusal does not create a minute loop.
    """
    requested = 0
    for tenant_id in active_tenants(runtime, request_id=REQUEST_ID, only=only_tenants):
        principal = system_principal(tenant_id)
        group_ids: list[UUID] = []
        with isolated("dirty_contract_sweep.tenant_failed", tenant_id=str(tenant_id)):
            with system_unit_of_work(runtime, principal, request_id=REQUEST_ID) as uow:
                booked = (
                    select(combination_group_member.c.combination_group_id)
                    .join(
                        contract_event,
                        (contract_event.c.contract_id == combination_group_member.c.contract_id)
                        & (contract_event.c.tenant_id == combination_group_member.c.tenant_id),
                    )
                    .where(
                        combination_group_member.c.valid_to_known_at.is_(None),
                        contract_event.c.event_type == "CONTRACT_BOOKED",
                    )
                )
                group_ids = list(
                    uow.session.scalars(
                        select(combination_group.c.id)
                        .where(
                            combination_group.c.dirty_since.is_not(None),
                            combination_group.c.status == "APPLIED",
                            combination_group.c.id.in_(booked),
                        )
                        .order_by(combination_group.c.dirty_since, combination_group.c.id)
                    )
                )
        for group_id in group_ids:
            with isolated(
                "dirty_contract_sweep.failed", tenant_id=str(tenant_id), group_id=str(group_id)
            ):
                with system_unit_of_work(runtime, principal, request_id=REQUEST_ID) as uow:
                    group = (
                        uow.session.execute(
                            select(combination_group)
                            .where(
                                combination_group.c.id == group_id,
                                combination_group.c.status == "APPLIED",
                                combination_group.c.dirty_since.is_not(None),
                            )
                            .with_for_update(skip_locked=True)
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if group is None:
                        continue
                    generation = f"{group['dirty_since'].isoformat()}:{group['row_version']}"
                    covered = uow.session.execute(
                        select(job.c.id)
                        .where(
                            job.c.kind == JobKind.CONTRACT_COMPUTE.value,
                            job.c.params["combination_group_ids"].contains([str(group_id)]),
                            job.c.params["mode"].astext.is_(None),
                            or_(
                                job.c.state.in_(["QUEUED", "RUNNING"]),
                                job.c.params["dirty_generation"].astext == generation,
                            ),
                        )
                        .limit(1)
                    ).first()
                    if covered is not None:
                        continue
                    uow.defer(
                        JobKind.CONTRACT_COMPUTE,
                        {
                            "combination_group_ids": [str(group_id)],
                            "trigger": group["dirty_trigger"] or ComputationTrigger.COMMAND.value,
                            "dirty_generation": generation,
                        },
                        subject_type="combination_group",
                        subject_id=group_id,
                    )
                    uow.commit()
                    requested += 1
    return requested
