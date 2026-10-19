"""Real billing and sealed-revenue inputs for the BBR report under construction."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract, legal_entity, subledger_line
from erev_api.domain.reports.builders import (
    ReportParams,
    SourceBinding,
    SourceCollector,
    bbr_bookings,
    bbr_sources,
)
from erev_api.enums import ContractEventType
from erev_api.events.payloads import BillingRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.money import MoneyIn
from erev_api.problems import Problem
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import appended
from support.worlds import AVM_US, K01, k01_pellworth


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_bbr_source_cutoff_scope_and_retained_inputs(
    app: FastAPI, app_settings: Settings, clock: FrozenClock, keyring: KeyRing
) -> None:
    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    cid = UUID(str(world.contracts[K01].contract["id"]))
    entity = world.place.scalar(select(legal_entity.c.id).where(legal_entity.c.code == AVM_US))
    periods = world.place.rows(select(subledger_line.c.period_id).distinct())
    period_ids = [r["period_id"] for r in periods]
    cutoff = world.place.scalar(select(func.clock_timestamp()))
    params = ReportParams(
        "bookings_billings_revenue",
        1,
        {},
        (entity,),
        cutoff,
        book_code="ASC606",
        sources=SourceCollector(),
        historical=True,
    )
    with world.place.uow() as uow:
        original = bbr_sources.read(uow, params, period_ids=period_ids)
    bookings = bbr_bookings.new_contracts(original)
    assert len(bookings) == 1
    assert bookings[0].amount == Decimal("135000.00")
    assert bookings[0].contract_id == cid
    assert len(bookings[0].basis_ids) == 2
    bills = bbr_sources.billings(original)
    revenues = bbr_sources.revenue(original)
    assert bills and revenues
    assert all(r.entity_id == entity for r in (*bills, *revenues))
    assert all(r.period_id in period_ids for r in revenues)
    assert sum((r.amount for r in revenues), Decimal(0)) > 0
    assert all(r.functional_amount is not None for r in revenues)
    assert params.sources is not None
    assert params.sources.evidence[bbr_sources.EVIDENCE] == original
    head = world.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == cid))
    appended(
        world.place,
        cid,
        head,
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 9, 16),
                payload=BillingRecordedV1(
                    invoice_number="BBR-NEW",
                    line_external_id="BBR-NEW-1",
                    obligation_key="O1",
                    amount=MoneyIn(amount="5000.00", currency="USD"),
                    issue_date=date(2026, 9, 16),
                ),
            )
        ],
    )
    with world.place.uow() as uow:
        historic = bbr_sources.read(uow, replace(params, sources=None), period_ids=period_ids)
        current = bbr_sources.read(
            uow,
            replace(
                params, sources=None, known_at=world.place.scalar(select(func.clock_timestamp()))
            ),
            period_ids=period_ids,
        )
    assert historic == original
    assert bbr_bookings.new_contracts(current) == bookings
    assert sum((r.amount for r in bbr_sources.billings(current)), Decimal(0)) == (
        sum((r.amount for r in bills), Decimal(0)) + Decimal("5000.00")
    )
    binding = SourceBinding(
        cutoff=cutoff,
        versions={},
        labels={},
        members={},
        row_keys=frozenset(),
        strategy="retained_inputs",
        evidence={bbr_sources.EVIDENCE: original},
    )
    bound = replace(params, sources=None, binding=binding)
    with world.place.uow() as uow:
        assert bbr_sources.read(uow, bound, period_ids=period_ids) == original
        empty = bbr_sources.read(
            uow, replace(params, entity_ids=(), sources=None), period_ids=period_ids
        )
        assert not bbr_sources.billings(empty) and not bbr_sources.revenue(empty)
        with pytest.raises(Problem, match="entity scope"):
            bbr_sources.read(uow, replace(bound, entity_ids=()), period_ids=period_ids)
        with pytest.raises(Problem, match="another book or range"):
            bbr_sources.read(uow, replace(bound, book_code="IFRS15"), period_ids=period_ids)


def test_bbr_report_delivery_and_retained_reproduction(
    app: FastAPI, app_settings: Settings, clock: FrozenClock, keyring: KeyRing
) -> None:
    import hashlib

    from support.reference import get, post
    from support.worlds import REPORT_RUNS, journal_run, report_run, resigned, run_now

    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    journal_run(world)
    clock.set(world.place.scalar(select(func.clock_timestamp())))
    world = resigned(world)
    params = {
        "entity_codes": [AVM_US],
        "book": "ASC606",
        "from_period_key": "FY2026-P09",
        "to_period_key": "FY2026-P09",
        "known_at": clock.now().isoformat(),
    }
    original, rows = report_run(world, "bookings_billings_revenue", params)
    assert len(rows) == 1 and rows[0]["revenue"]["amount"] != "0.00"
    data = get(app, f"{REPORT_RUNS}/{original['id']}/output", world.maya).json()
    assert data["tie_out_results"][0]["result"] == "PASS"
    csv_run, _ = report_run(world, "bookings_billings_revenue", params, output_format="CSV")
    base = f"{REPORT_RUNS}/{csv_run['id']}/output"
    content = get(app, base, world.maya).content
    manifest = get(app, base, world.maya, {"part": "manifest"}).json()
    assert manifest["sha256"] == hashlib.sha256(content).hexdigest()
    rerun = post(app, f"{REPORT_RUNS}/{original['id']}/rerun", world.maya, {})
    assert rerun.status_code == 202, rerun.text
    assert run_now(world, UUID(rerun.json()["id"]))["state"] == "SUCCEEDED"
    assert (
        get(app, f"{REPORT_RUNS}/{rerun.headers['x-erev-report-run-id']}/output", world.maya).json()
        == data
    )
