"""The calculator observes an obligation in the version of the computation that last held it
(item SSP-CALC-LATEST-VERSION-1, the rider of SSP-ENTITY-SCOPE-1; the supervisor's ruling of
2026-10-02; 04 T-CON-08 and T-REF-34; ``approvals.subjects.obligation_latest_computation``, item
MOD-SSP-PIN-CHAIN-1).

``version_no`` counts within one combination group. The provider of committed contract lines
ordered an obligation's versions by that number across every group its contract has been in and
took the last — for a contract computed on its own and then combined, a version of the group it
had left. Measured before, in this world: the order computed twice on its own and then combined
was observed in version 2 of its former group, where the joint group holds its version 1.

World: ``two_orders`` of ``tests/domain/reports/test_combined_group_versions_db.py`` — K-02, K-09
(``SF-ORD-10417``, 30 seats at 108,000.00) and the customer's second order (``SF-ORD-10418``, 10
seats at 48,000.00), each computed in its own group. The second order is then computed once more
on its own (a second invoice, INV-US-3103), and Maya combines the two orders and Marcus approves:
the joint group computes from its inception. The frozen clock reads 2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    contract,
    contract_version,
    job,
    obligation,
    obligation_version,
    ssp_calculator_run,
)
from erev_api.domain.ssp import calculator
from erev_api.enums import ContractEventType
from erev_api.events.payloads import BillingRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from erev_api.money import MoneyIn
from fastapi import FastAPI
from sqlalchemy import and_, select, text
from support.db import TestDatabase
from support.factories import appended, computed
from support.reference import post
from support.worlds import K02, K09, ReportWorld
from tests.domain.reports.test_combined_group_versions_db import SECOND, combine, two_orders

RUNS = "/api/v1/ssp-calculator-runs"
RUN_ID_HEADER = "X-Erev-Ssp-Calculator-Run-Id"
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _everyone(world: ReportWorld) -> DbContext:
    return DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")


def versions(world: ReportWorld) -> dict[str, list[tuple[UUID, int, UUID]]]:
    """Per order, (combination group, version number, obligation version) of its obligation's
    versions in the order they became known."""
    held = obligation_version.join(
        contract,
        and_(
            contract.c.tenant_id == obligation_version.c.tenant_id,
            contract.c.id == obligation_version.c.contract_id,
        ),
    ).join(
        contract_version,
        and_(
            contract_version.c.tenant_id == obligation_version.c.tenant_id,
            contract_version.c.id == obligation_version.c.contract_version_id,
        ),
    )
    with tenant_session(_everyone(world), read_only=True) as session:
        rows = session.execute(
            select(
                contract.c.external_id,
                obligation_version.c.combination_group_id,
                obligation_version.c.version_no,
                obligation_version.c.id,
            )
            .select_from(held)
            .where(
                contract.c.external_id.in_([K02, K09, SECOND]),
                obligation_version.c.book_code == "ASC606",
            )
            .order_by(contract_version.c.known_at, contract_version.c.version_no)
        ).all()
    found: dict[str, list[tuple[UUID, int, UUID]]] = {}
    for external_id, group_id, number, version_id in rows:
        found.setdefault(str(external_id), []).append(
            (UUID(str(group_id)), int(number), UUID(str(version_id)))
        )
    return found


def observed(
    world: ReportWorld, keyring: KeyRing, files: LocalFileStore
) -> dict[str, tuple[UUID, str, str]]:
    """Maya's run over the committed lines of the three orders' product, worked: per source
    reference, the obligation version the observation names, its quantity and its unit price."""
    app, maya = world.app, world.maya
    with tenant_session(_everyone(world), read_only=True) as session:
        products = sorted(
            {
                str(value)
                for value in session.scalars(
                    select(obligation.c.product_id)
                    .join(
                        contract,
                        and_(
                            contract.c.tenant_id == obligation.c.tenant_id,
                            contract.c.id == obligation.c.contract_id,
                        ),
                    )
                    .where(contract.c.external_id.in_([K09, SECOND]))
                )
            }
        )
    book = post(
        app, "/api/v1/ssp-books", maya, {"code": "SEATS", "name": "Seats", "currency": "USD"}
    )
    assert book.status_code == 201, book.text
    body = {
        "name": "Seats, committed lines",
        "parameters": {
            "source": "committed_obligations",
            "product_ids": products,
            "dimensions": {},
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "band_ratio": "0.15",
            "currency": "USD",
            "ssp_book_id": book.json()["id"],
            "pool_file_id": None,
        },
    }
    started = post(app, RUNS, maya, body)
    assert started.status_code == 202, started.text
    job_id = UUID(started.json()["id"])
    with tenant_session(_everyone(world)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    run_job(job_id, world.tenant_id, attempt=1, runtime=world.runtime)
    run_id = UUID(str(started.headers[RUN_ID_HEADER]))
    with tenant_session(_everyone(world), read_only=True) as session:
        run: dict[str, Any] = dict(
            session.execute(select(ssp_calculator_run).where(ssp_calculator_run.c.id == run_id))
            .mappings()
            .one()
        )
        assert run["status"] == "SUCCEEDED", run
        found = calculator.observations_of(session, run, files=files, keyring=keyring)
    return {
        item.source_reference: (
            UUID(str(item.source_ref_id)),
            format(item.quantity.normalize(), "f"),
            format(item.unit_price.normalize(), "f"),
        )
        for item in found
    }


def test_ssp_calc_latest_version_1_a_combined_contract_is_observed_in_its_joint_group(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """The second order has two versions in the group it left (numbers 1 and 2) and one in the
    joint group (number 1): the calculator observes it in the joint group's version — the one of
    the computation that last held the obligation — and K-09 beside it. K-02, never combined, is
    observed in the latest version of its one group: the positive control.

    Fail-first: the observation of ``SF-ORD-10418 O1`` named version 2 of the order's former
    group."""
    files = LocalFileStore(app_settings.file_root)
    world = two_orders(app, keyring, clock, files)
    place = world.place
    second = world.contracts[SECOND]
    invoice = EventIn(
        event_type=ContractEventType.BILLING_RECORDED,
        effective_date=date(2026, 9, 2),
        payload=BillingRecordedV1(
            invoice_number="INV-US-3103",
            line_external_id="INV-US-3103-1",
            obligation_key="O1",
            amount=MoneyIn(amount="1000.00", currency="USD"),
            issue_date=date(2026, 9, 2),
        ),
    )
    appended(place, UUID(str(second.contract["id"])), 3, [invoice])
    computed(place, UUID(str(second.combination_group["id"])))
    joint = combine(world)

    held = versions(world)
    # The premise, read from the rows: the group the second order left holds a higher number
    # than the joint group does.
    assert [(group == joint, number) for group, number, _ in held[SECOND]] == [
        (False, 1),
        (False, 2),
        (True, 1),
    ]
    assert [(group == joint, number) for group, number, _ in held[K09]] == [(False, 1), (True, 1)]
    assert len({group for group, _, _ in held[K02]}) == 1  # K-02 has been in one group only

    named = observed(world, keyring, files)

    assert named == {
        f"{K02} O1": (held[K02][-1][2], "100", "2400"),
        f"{K09} O1": (held[K09][-1][2], "30", "3600"),
        f"{SECOND} O1": (held[SECOND][-1][2], "10", "4800"),
    }
