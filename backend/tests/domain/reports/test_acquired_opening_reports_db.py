"""Period-end acquisition sources through stored computation, public reports and bound reruns.

Opening facts are fixture-appended: this does not claim a public acquisition-entry workflow.
"""

from datetime import date
from types import SimpleNamespace
from uuid import UUID

import pytest
from support import close_run_worlds, worlds
from support.factories import appended, booked_contract, computed
from support.reference import get, post

from erev_api.domain.reports import opening_consumption_policy as policy
from erev_api.enums import ContractEventType
from erev_api.events.payloads import OpeningBalanceEstablishedV3
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app


@pytest.fixture
def app(committed_db, app_settings, clock):
    return create_app(app_settings, clock=clock)


@pytest.mark.slow
def test_acquired_opening_report_retains_original_foreign_currency_sources(
    app, keyring, clock, app_settings, monkeypatch
):
    world = close_run_worlds.eur_receivable(
        app, keyring, clock, LocalFileStore(app_settings.file_root)
    )
    existing = world.contracts[close_run_worlds.EUR_CONTRACT]
    # Settle the setup contract's unbilled balance, so this scenario does not
    # depend on a separate period-close FX pass for that unrelated receivable.
    settled = post(
        app,
        f"/api/v1/contracts/{existing.contract['id']}/events",
        world.maya,
        {
            "events": [
                {
                    "event_type": "BILLING_RECORDED",
                    "effective_date": "2026-08-31",
                    "payload": {
                        "invoice_number": "SETUP-INVOICE",
                        "line_external_id": "SETUP-1",
                        "obligation_key": "O1",
                        "issue_date": "2026-08-31",
                        "amount": {"amount": "10000.00", "currency": "EUR"},
                    },
                }
            ]
        },
        if_match='"s3"',
    )
    assert settled.status_code == 201, settled.text
    acquired = booked_contract(
        world.place,
        {
            "external_id": "ACQUIRED-EUR",
            "customer_id": str(existing.contract["customer_id"]),
            "contracting_entity_code": worlds.AVM_US,
            "transaction_currency": "EUR",
            "inception_date": "2026-08-01",
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": close_run_worlds.EUR_HOURS,
                    "quantity": "200",
                    "total_price": {"amount": "20000.00", "currency": "EUR"},
                    "unit_price": "100.00",
                    "start_date": "2026-08-01",
                    "end_date": "2026-12-31",
                }
            ],
        },
        activate=True,
    )

    def money(amount):
        return {"amount": amount, "currency": "EUR"}

    appended(
        world.place,
        UUID(str(acquired.contract["id"])),
        2,
        [
            EventIn(
                event_type=ContractEventType.OPENING_BALANCE_ESTABLISHED,
                effective_date=date(2026, 8, 31),
                payload=OpeningBalanceEstablishedV3.model_validate(
                    {
                        "reason": "BUSINESS_COMBINATION",
                        "cutover_date": "2026-08-31",
                        "onboarding_method": "OPENING_BALANCES_AT_CUTOVER",
                        "fair_value_contract_liability": money("10000"),
                        "obligations": [
                            {
                                "obligation_key": "O1",
                                "delivered_quantity_cum": "100",
                                "ssp_delivered_cum": "10000",
                                "remaining_quantity": "100",
                                "remaining_ssp": "10000",
                                "revenue_cum": money("10000"),
                                "billed_cum": money("20000"),
                                "catch_up_cum": money("0"),
                                "pre_standard_revenue_cum": money("0"),
                                "remaining_allocation": money("10000"),
                                "remaining_billing": money("0"),
                                "position_obligation": money("10000"),
                                "netting_reclass_amount": money("0"),
                            }
                        ],
                    }
                ),
            )
        ],
    )
    computed(world.place, UUID(str(acquired.combination_group["id"])))
    worlds.approved_manual_events(
        world.place,
        world.priya,
        UUID(str(acquired.contract["id"])),
        {
            "event_type": "DELIVERY_RECORDED",
            "effective_date": "2026-09-10",
            "payload": {"obligation_key": "O1", "quantity": "100", "trigger": "DELIVERY"},
        },
        evidence_file_ids=[],
    )
    world = worlds.on_record_clock(world, clock)
    monkeypatch.setattr(policy, "resolve", lambda *a, **k: SimpleNamespace(value="FIFO_WITHIN_POB"))
    for view, currency, amount, relief in (
        ("transaction", "EUR", "10000.00", "5000.00"),
        ("functional", "USD", "11000.00", "5500.00"),
    ):
        run, rows = worlds.report_run(
            world,
            "revenue_from_opening_liability",
            {
                "entity_codes": [worlds.AVM_US],
                "book": "ASC606",
                "from_period_key": "FY2026-P09",
                "to_period_key": "FY2026-P09",
                "currency_view": view,
            },
        )
        row = next(r for r in rows if r["row_key"] == f"contract:ACQUIRED-EUR:{worlds.AVM_US}")
        expected = {"currency": currency, "amount": amount}
        assert row["opening_contract_liability"] == expected
        # Fixed-price RTI progress is 10,000 realized / 20,000 stated price.
        # Half of the 10,000 remaining allocation is recognized (S09-R-18).
        expected_relief = {"currency": currency, "amount": relief}
        assert row["revenue_from_opening"] == expected_relief
        assert row["revenue_recognized"] == expected_relief
        restarted = post(app, f"/api/v1/report-runs/{run['id']}/rerun", world.maya, {})
        assert restarted.status_code == 202, restarted.text
        finished = worlds.run_now(world, UUID(restarted.json()["id"]))
        assert finished["state"] == "SUCCEEDED", finished
        run_id = restarted.headers["x-erev-report-run-id"]
        rebuilt = get(app, f"/api/v1/report-runs/{run_id}/data", world.maya, {"limit": "200"})
        assert rebuilt.status_code == 200, rebuilt.text
        assert rebuilt.json()["items"] == rows
