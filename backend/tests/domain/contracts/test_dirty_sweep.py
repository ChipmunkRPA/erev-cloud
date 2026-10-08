"""Durable dirty-group recovery, live-job deduplication and failed-generation bounds."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from erev_api.auth.principal import system_principal
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import combination_group, job
from erev_api.domain.contracts import dirty_sweep
from erev_api.enums import JobKind
from erev_api.jobs.context import system_unit_of_work
from sqlalchemy import select, update
from support.factories import booked_contract, seat_body, seat_line
from tests.domain.contracts import test_compute_job as shared

app = shared.app
files = shared.files
world = shared.world
runtime = shared.runtime


@pytest.mark.parametrize("unpriced", [False, True])
def test_sweep_computes_dirty_groups_and_does_not_repeat_failed_generation(
    world: Any, runtime: Any, unpriced: bool
) -> None:
    line = seat_line("O1", seats="1", price="2400.00", start="2026-09-01", end="2027-08-31")
    if unpriced:
        line["product_code"] = shared.UNPRICED
    booked_contract(
        world.place,
        seat_body(
            world.customers["C-09"], external_id="SWEEP-1", inception="2026-09-01", lines=[line]
        ),
        activate=False,
    )
    tenant_id = world.place.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    runtime.clock.advance(timedelta(seconds=1))
    with tenant_session(context) as session:
        session.execute(
            update(combination_group).values(
                dirty_since=runtime.clock.now(), dirty_trigger="FX_REPUBLISH"
            )
        )
    assert dirty_sweep.run(runtime, only_tenants=[tenant_id]) == 1
    assert dirty_sweep.run(runtime, only_tenants=[tenant_id]) == 0
    with tenant_session(context, read_only=True) as session:
        jobs = (
            session.execute(select(job).where(job.c.params["dirty_generation"].astext.is_not(None)))
            .mappings()
            .all()
        )
        assert len(jobs) == 1
        assert jobs[0]["params"]["trigger"] == "FX_REPUBLISH"
        assert jobs[0]["procrastinate_job_id"] is not None
        queued = jobs[0]["id"]
    shared._work(world, queued, runtime)
    with tenant_session(context, read_only=True) as session:
        group = session.execute(select(combination_group)).mappings().one()
        finished = session.execute(select(job).where(job.c.id == queued)).mappings().one()
        assert finished["state"] == ("SUCCEEDED_WITH_EXCEPTIONS" if unpriced else "SUCCEEDED")
        assert (group["dirty_since"] is not None) == unpriced
    assert dirty_sweep.run(runtime, only_tenants=[tenant_id]) == 0
    # A new mark can share a timestamp; its row version still creates a new generation.
    with tenant_session(context) as session:
        session.execute(
            update(combination_group).values(
                dirty_since=runtime.clock.now(),
                row_version=combination_group.c.row_version + 1,
            )
        )
    assert dirty_sweep.run(runtime, only_tenants=[tenant_id]) == 1


@pytest.mark.parametrize("mode", [None, "PREVIEW", "locked"])
def test_sweep_respects_existing_normal_job_but_not_preview(
    world: Any, runtime: Any, mode: str | None
) -> None:
    booked_contract(
        world.place,
        seat_body(
            world.customers["C-09"],
            external_id="SWEEP-2",
            inception="2026-09-01",
            lines=[
                seat_line("O1", seats="1", price="2400.00", start="2026-09-01", end="2027-08-31")
            ],
        ),
        activate=False,
    )
    tenant_id = world.place.tenant_id
    with system_unit_of_work(runtime, system_principal(tenant_id), request_id="test-dirty") as uow:
        group_id = uow.session.scalar(select(combination_group.c.id))
        uow.session.execute(update(combination_group).values(dirty_since=uow.now))
        if mode != "locked":
            uow.defer(
                JobKind.CONTRACT_COMPUTE,
                {
                    "combination_group_ids": [str(group_id)],
                    **({"mode": mode} if mode else {}),
                },
            )
        uow.commit()
    if mode == "locked":
        with system_unit_of_work(
            runtime, system_principal(tenant_id), request_id="test-lock"
        ) as held:
            held.session.execute(select(combination_group).with_for_update()).all()
            assert dirty_sweep.run(runtime, only_tenants=[tenant_id]) == 0
    assert dirty_sweep.run(runtime, only_tenants=[tenant_id]) == (0 if mode is None else 1)
    assert dirty_sweep.run(runtime, only_tenants=[tenant_id]) == 0


def test_sweep_isolates_enqueue_failure_and_retries_next_tick(
    world: Any, runtime: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from erev_api.uow import UnitOfWork

    for code in ("SWEEP-FAIL", "SWEEP-OK"):
        booked_contract(
            world.place,
            seat_body(
                world.customers["C-09"],
                external_id=code,
                inception="2026-09-01",
                lines=[
                    seat_line(
                        "O1", seats="1", price="2400.00", start="2026-09-01", end="2027-08-31"
                    )
                ],
            ),
            activate=False,
        )
    tenant_id = world.place.tenant_id
    with system_unit_of_work(runtime, system_principal(tenant_id), request_id="test-dirty") as uow:
        groups = list(
            uow.session.scalars(select(combination_group.c.id).order_by(combination_group.c.id))
        )
        uow.session.execute(update(combination_group).values(dirty_since=uow.now))
        uow.commit()
    original = UnitOfWork.defer

    def failed(self: Any, kind: Any, params: Any, **kwargs: Any) -> Any:
        if params["combination_group_ids"] == [str(groups[0])]:
            raise RuntimeError("injected enqueue failure")
        return original(self, kind, params, **kwargs)

    monkeypatch.setattr(UnitOfWork, "defer", failed)
    assert dirty_sweep.run(runtime, only_tenants=[tenant_id]) == 1
    monkeypatch.setattr(UnitOfWork, "defer", original)
    assert dirty_sweep.run(runtime, only_tenants=[tenant_id]) == 1
    assert dirty_sweep.run(runtime, only_tenants=[tenant_id]) == 0
