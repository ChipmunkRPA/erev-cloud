"""FCS-6 Tamsin acceptance against approved SSP and real product templates."""

import json
from uuid import uuid4

from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.domain.forecast import deal_bundle, deal_compute, deal_results
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.schemas.deal_previews import DealInputIn
from erev_engine.canonical import canonical_bytes
from support.db import TestDatabase
from support.factories import (
    IMPLEMENTATION_PLUS,
    PLATFORM_100,
    approved_ssp_version,
    j03_world,
    range_entry,
)


def test_tamsin_row_preview(
    committed_db: TestDatabase, app_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    app = create_app(app_settings, clock=clock)
    world = j03_world(app, keyring, clock, LocalFileStore(app_settings.file_root))
    approved_ssp_version(
        app,
        world.place.author,
        [world.priya, world.marcus],
        world.book_id,
        label="2026-H2",
        effective_from="2026-10-01",
        copy_from_version_id=world.version_id,
        entries=[
            range_entry(PLATFORM_100, "95200.00", "112000.00", "128800.00", value_basis="AMOUNT"),
            range_entry(
                IMPLEMENTATION_PLUS, "18000.00", "20000.00", "22000.00", "cost_plus_margin"
            ),
        ],
    )
    proposal = DealInputIn.model_validate(
        {
            "customer_name": "Tamsin Row Hotels Inc. (Demo)",
            "entity_code": "AVM-US",
            "start_date": "2026-11-01",
            "lines": [
                {
                    "product_code": PLATFORM_100,
                    "quantity": "1",
                    "term_months": 12,
                    "price": {"amount": "90000.00", "currency": "USD"},
                },
                {
                    "product_code": IMPLEMENTATION_PLUS,
                    "quantity": "1",
                    "price": {"amount": "26000.00", "currency": "USD"},
                },
            ],
        }
    )
    with world.place.uow() as uow:
        bundle = deal_bundle.build(uow, proposal, uuid4())
        computed = deal_compute.compute(bundle)
    assert len(bundle.events) == 1
    assert [event.event_type for event in computed.input.events] == [
        "CONTRACT_BOOKED",
        "CONTRACT_ACTIVATED",
    ]
    assert deal_compute.compute(bundle).input_sha256 == computed.input_sha256
    inputs = json.loads(canonical_bytes({"engine_bundle": computed.input}))
    output = json.loads(canonical_bytes(computed.output))
    book = next(book for book in deal_results.project(inputs, output) if book.book_code == "ASC606")
    rows = {row.product_code: row for row in book.allocations}
    assert rows[PLATFORM_100].selected_ssp == "95200"
    assert rows[PLATFORM_100].range_position == "BELOW"
    assert rows[IMPLEMENTATION_PLUS].selected_ssp == "22000"
    assert rows[IMPLEMENTATION_PLUS].range_position == "ABOVE"
    assert book.transaction_price.amount == "116000.00"
    assert rows[PLATFORM_100].allocated_amount.amount == "94225.26"
    assert rows[IMPLEMENTATION_PLUS].allocated_amount.amount == "21774.74"
    assert not book.has_material_right and not book.has_variable_consideration
    assert min(row.period_key for row in book.revenue_by_period) == "FY2026-P11"
