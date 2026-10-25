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
@pytest.mark.parametrize(
    "locked,cross_entity,recomputed,closed_source,untraced",
    [
        (False, False, False, False, False),
        (True, False, False, False, False),
        (False, True, False, False, False),
        (True, True, False, False, False),
        (False, False, True, False, False),
        (True, False, True, False, False),
        (False, False, True, True, False),
        (False, False, True, True, True),
        (False, False, True, True, "complete"),
        (False, False, True, True, "foreign"),
        (False, False, True, True, "group"),
        (False, True, True, True, "foreign"),
    ],
)
def test_acquired_opening_report_retains_original_foreign_currency_sources(
    app,
    keyring,
    clock,
    app_settings,
    monkeypatch,
    locked,
    cross_entity,
    recomputed,
    closed_source,
    untraced,
):
    if cross_entity:
        monkeypatch.setattr(
            close_run_worlds,
            "EUR_CHART",
            (
                *close_run_worlds.EUR_CHART,
                ("1300", "Intercompany due from", "ASSET", "D", "INTERCOMPANY_DUE_FROM"),
                ("2300", "Intercompany due to", "LIABILITY", "C", "INTERCOMPANY_DUE_TO"),
            ),
        )
    world = close_run_worlds.eur_receivable(
        app, keyring, clock, LocalFileStore(app_settings.file_root), reporting_currency="EUR"
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
    selected_entities = [worlds.AVM_US]
    if cross_entity:
        from sqlalchemy import select
        from support.factories import open_periods
        from support.reference import entity

        from erev_api.db.tables import legal_entity

        calendar_id = world.place.scalar(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
        )
        entity(app, world.maya, code="ACQUIRED-PERFORMER", calendar_id=str(calendar_id))
        open_periods(
            app,
            world.maya,
            entity_code="ACQUIRED-PERFORMER",
            keys=[f"FY2026-P{m:02d}" for m in range(1, 10)],
        )
        selected_entities.append("ACQUIRED-PERFORMER")
    acquired_currency = "USD" if recomputed and untraced not in {"foreign", "group"} else "EUR"
    if acquired_currency == "USD":
        close_run_worlds.approved_ssp_version(
            app,
            world.maya,
            [world.priya],
            close_run_worlds.ssp_book(app, world.maya, code="ACQUIRED-USD", currency="USD"),
            label="2026",
            effective_from="2026-01-01",
            entries=[
                close_run_worlds.point_entry(close_run_worlds.EUR_HOURS, "100", currency="USD")
            ],
        )
    acquired_body = {
        "external_id": "ACQUIRED-EUR",
        "customer_id": str(existing.contract["customer_id"]),
        "contracting_entity_code": worlds.AVM_US,
        "transaction_currency": acquired_currency,
        "inception_date": "2026-07-01" if closed_source and not untraced else "2026-08-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": close_run_worlds.EUR_HOURS,
                **({"performing_entity_code": "ACQUIRED-PERFORMER"} if cross_entity else {}),
                "quantity": "200",
                "total_price": {"amount": "20000.00", "currency": acquired_currency},
                "unit_price": "100.00",
                "start_date": "2026-08-01",
                "end_date": "2026-12-31",
            }
        ],
    }
    acquired = booked_contract(world.place, acquired_body, activate=True)

    def money(amount):
        return {"amount": amount, "currency": acquired_currency}

    def append_acquisition(contract_id):
        appended(
            world.place,
            contract_id,
            2,
            [
                EventIn(
                    event_type=ContractEventType.OPENING_BALANCE_ESTABLISHED,
                    effective_date=date(2026, 8, 31),
                    payload=OpeningBalanceEstablishedV3.model_validate(
                        {
                            "reason": "BUSINESS_COMBINATION",
                            "cutover_date": "2026-08-31",
                            "onboarding_method": "RECOMPUTE_FROM_INCEPTION"
                            if recomputed
                            else "OPENING_BALANCES_AT_CUTOVER",
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

    append_acquisition(UUID(str(acquired.contract["id"])))
    second = None
    if untraced == "group":
        second = booked_contract(
            world.place, {**acquired_body, "external_id": "ACQUIRED-SECOND"}, activate=True
        )
        append_acquisition(UUID(str(second.contract["id"])))
    if closed_source:
        # Retained legacy calculation fixture: the native input excludes the cutover
        # from its posting horizon. This is not a test of creating an actual lock.
        from dataclasses import replace

        from erev_api.domain.contracts import bundles as inputs

        build = inputs.build

        def closed_input(*args, **kwargs):
            value = build(*args, **kwargs)
            return replace(
                value,
                evidence_revision=43 if untraced is True else value.evidence_revision,
                entities=tuple(
                    replace(
                        entity,
                        periods=tuple(
                            replace(
                                period,
                                states=tuple(
                                    (
                                        book,
                                        "closed" if period.period_key == "FY2026-P08" else "future",
                                    )
                                    for book, _ in period.states
                                ),
                            )
                            if period.period_key >= "FY2026-P08"
                            else period
                            for period in entity.periods
                        ),
                    )
                    for entity in value.entities
                ),
            )

        with monkeypatch.context() as patch:
            patch.setattr(inputs, "build", closed_input)
            group_id = UUID(str(acquired.combination_group["id"]))
            if second is not None:
                from support.reference import approve

                proposal = post(
                    app,
                    "/api/v1/combination-groups",
                    world.maya,
                    {
                        "contract_ids": [str(acquired.contract["id"]), str(second.contract["id"])],
                        "criterion": "606-10-25-9(b)",
                        "rationale": "One acquired package.",
                    },
                )
                assert proposal.status_code == 201, proposal.text
                group_id = UUID(proposal.json()["id"])
                submitted = post(
                    app, f"/api/v1/combination-groups/{group_id}/submit", world.maya, {}
                )
                assert submitted.status_code == 200, submitted.text
                approved = approve(app, submitted.json()["approval_request_id"], world.marcus)
                assert approved.status_code == 200, approved.text
            _, output, _ = computed(world.place, group_id)
        assert not any(
            node.id == "contract_liability:ACQUIRED-EUR@AVM-US:FY2026-P08"
            for node in output.books[0].trace.nodes
        )
        if untraced:
            from erev_api.domain.reports import tie_outs

            trace = tie_outs.traced_balances(
                (node.id, node.value) for node in output.books[0].trace.nodes
            )
            assert "ACQUIRED-EUR@AVM-US" not in trace.latest
        if untraced in {"complete", "foreign"}:
            assert output.books[0].acquisition_balance_observations
        world = worlds.on_record_clock(world, clock)
        if untraced in {"complete", "foreign"}:
            _, before_acquisition = worlds.report_run(
                world,
                "contract_balances",
                {
                    "entity_codes": [worlds.AVM_US],
                    "book": "ASC606",
                    "period_key": "FY2026-P07",
                    "currency_view": "transaction",
                    "include_zero": True,
                },
            )
            assert not any(
                row.get("contract_external_id") == "ACQUIRED-EUR" for row in before_acquisition
            )
        if untraced is True:
            for code, period_params in (
                ("contract_balances", {"period_key": "FY2026-P08"}),
                (
                    "contract_balance_rollforward",
                    {"from_period_key": "FY2026-P08", "to_period_key": "FY2026-P08"},
                ),
            ):
                started = post(
                    world.app,
                    "/api/v1/report-runs",
                    world.maya,
                    {
                        "report_code": code,
                        "output_format": "JSON",
                        "parameters": {
                            "entity_codes": [worlds.AVM_US],
                            "book": "ASC606",
                            "currency_view": "transaction",
                            **period_params,
                        },
                    },
                )
                assert started.status_code == 202, started.text
                finished = _settled_refusal(world, UUID(started.json()["id"]))
                assert finished["state"] == "FAILED", finished
                assert "no persisted member balance row" in str(finished), finished
                assert "ACQUIRED-EUR" in str(finished), finished
                assert "FY2026-P08" in str(finished), finished
            return
        if second is not None:
            _closed_group_reports(world, output.books[0].acquisition_balance_observations)
            return
        _closed_source_reports(
            world,
            foreign=untraced == "foreign",
            complete=output.books[0].acquisition_balance_observations
            if untraced in {"complete", "foreign"}
            else None,
        )
        return
    computed(world.place, UUID(str(acquired.combination_group["id"])))
    if locked:
        from datetime import timedelta

        from support import close_runs
        from support.close_world import periods_closed_before
        from support.reference import approve

        world = worlds.on_record_clock(world, clock)
        periods_closed_before(
            world.place,
            app,
            world.maya,
            entity_id=world.entity_id,
            before="FY2026-P08",
            entity_code=worlds.AVM_US,
        )
        state = worlds.period_state(world, worlds.AVM_US, "FY2026-P08")
        started = post(
            app,
            f"/api/v1/periods/{state['id']}/start-close",
            world.maya,
            {"comment": "Freeze acquired opening sources"},
            if_match=f'"r{state["row_version"]}"',
        )
        assert started.status_code == 200, started.text
        closed = close_runs.closed(
            world, monkeypatch, entity_code=worlds.AVM_US, period_key="FY2026-P08"
        )
        assert closed["status"] == "SUCCEEDED", str(closed)
        world = close_run_worlds.journal_and_reconciliations(world, clock, closed)
        requested = close_run_worlds.request_lock(world)
        assert requested.status_code == 200, requested.text
        clock.advance(timedelta(minutes=1))
        world = worlds.verified(world, clock, "marcus")
        approved = approve(app, requested.json()["approval_request_id"], world.marcus)
        assert approved.status_code == 200, approved.text
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
    if not locked:
        world = worlds.on_record_clock(world, clock)
    monkeypatch.setattr(policy, "resolve", lambda *a, **k: SimpleNamespace(value="FIFO_WITHIN_POB"))
    views = (
        (
            ("transaction", "USD", "20000.00", "10000.00"),
            ("functional", "USD", "20000.00", "10000.00"),
            ("reporting", "EUR", "18099.55", "9009.01"),
        )
        if recomputed
        else (
            ("transaction", "EUR", "10000.00", "5000.00"),
            ("functional", "USD", "11000.00", "5500.00"),
            ("reporting", "EUR", "9954.75", "4954.95"),
        )
    )
    for view, currency, amount, relief in views:
        acquired_run, acquired_rows = worlds.report_run(
            world,
            "contract_balance_rollforward",
            {
                "entity_codes": selected_entities,
                "book": "ASC606",
                "from_period_key": "FY2026-P08",
                "to_period_key": "FY2026-P08",
                "currency_view": view,
            },
        )
        by_key = {r["row_key"]: r for r in acquired_rows}
        suffix = ":USD" if recomputed and view == "transaction" else ""
        combination_key = "BUSINESS_COMBINATIONS" + suffix
        other_key = "OTHER" + suffix
        increase = "11000.00" if view == "functional" else "10000.00"
        if recomputed:
            increase = "18181.82" if view == "reporting" else "20000.00"
        assert by_key[combination_key]["contract_liability"] == {
            "currency": currency,
            "amount": increase,
        }
        assert by_key[other_key]["contract_liability"]["amount"] == "0.00"
        for row_key, column in (
            (combination_key, "contract_liability"),
            (f"contract:ACQUIRED-EUR:{worlds.AVM_US}", "business_combinations"),
        ):
            explained = get(
                app,
                f"/api/v1/explain/report-runs/{acquired_run['id']}/cell",
                world.maya,
                params={"row_key": row_key, "column_key": column},
            )
            assert explained.status_code == 200, explained.text
            detail = explained.json()
            assert detail["value"] == {"currency": currency, "amount": increase}
            assert len(detail["contributors"]["items"]) == 1
            contribution = detail["contributors"]["items"][0]
            assert contribution["object_type"] == "acquisition_disclosure_contribution"
            assert contribution["value"] == detail["value"]
            assert any("ACQUIRED-EUR/EV-000003" in text for text in contribution["details"])
            assert any(link["href"].startswith("/trace/") for link in contribution["source_links"])
            assert "_entity_id" not in contribution

        repeated = post(app, f"/api/v1/report-runs/{acquired_run['id']}/rerun", world.maya, {})
        assert repeated.status_code == 202, repeated.text
        done = worlds.run_now(world, UUID(repeated.json()["id"]))
        assert done["state"] == "SUCCEEDED", done
        repeat_id = repeated.headers["x-erev-report-run-id"]
        data = get(app, f"/api/v1/report-runs/{repeat_id}/data", world.maya, {"limit": "200"})
        assert data.status_code == 200, data.text
        assert data.json()["items"] == acquired_rows
        run, rows = worlds.report_run(
            world,
            "revenue_from_opening_liability",
            {
                "entity_codes": selected_entities,
                "book": "ASC606",
                "from_period_key": "FY2026-P09",
                "to_period_key": "FY2026-P09",
                "currency_view": view,
            },
        )
        row = next(r for r in rows if r["row_key"] == f"contract:ACQUIRED-EUR:{worlds.AVM_US}")
        expected = {"currency": currency, "amount": amount}
        assert row["opening_contract_liability"] == expected
        # RTI progress is 10,000 realized / 20,000 stated price. Recompute uses the
        # original 20,000 allocation; the cutover method uses the 10,000 remainder.
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


def _closed_source_reports(world, complete=None, foreign=False):
    views = (
        (
            ("transaction", "EUR", "20000.00"),
            ("functional", "USD", "22000.00"),
            ("reporting", "EUR", "19909.50"),
        )
        if foreign
        else (
            ("transaction", "USD", "20000.00"),
            ("functional", "USD", "20000.00"),
            ("reporting", "EUR", "18099.55"),
        )
    )
    for view, currency, expected in views:
        params = {"entity_codes": [worlds.AVM_US], "book": "ASC606", "currency_view": view}
        balance_run, balances = worlds.report_run(
            world,
            "contract_balances",
            {
                **params,
                "period_key": "FY2026-P08",
            },
        )
        own = next(
            row for row in balances if row["row_key"] == f"contract:ACQUIRED-EUR:{worlds.AVM_US}"
        )
        assert own["contract_liability"] == {"currency": currency, "amount": expected}
        assert own["contract_liability_current"] == own["contract_liability"]
        assert own["contract_liability_noncurrent"]["amount"] == "0.00"
        assert own["acquisition_source_period"] == "FY2026-P08"
        explained_balance = get(
            world.app,
            f"/api/v1/explain/report-runs/{balance_run['id']}/cell",
            world.maya,
            params={"row_key": own["row_key"], "column_key": "contract_liability_current"},
        )
        assert explained_balance.status_code == 200, explained_balance.text
        body = explained_balance.json()
        assert body["value"] == own["contract_liability_current"]
        contribution = body["contributors"]["items"][0]
        assert any("/trace/" in link["href"] for link in contribution["source_links"])
        if complete is None:
            assert "maturity horizon" in str(contribution)
        else:
            assert "ORIGINAL_NONPOSTING_CUTOVER_EVALUATION" in str(contribution)
            assert "ERP-managed" in str(contribution)
            if view == "transaction":
                from decimal import Decimal

                (snapshot,) = complete
                for measure, amount in snapshot["amounts"].items():
                    assert Decimal(own[measure]["amount"]) == Decimal(amount) / 100

        if foreign:
            (original,) = complete
            assert original["functional"]["currency"] == "USD"
            assert original["functional"]["amounts"]["contract_liability"] == 2200000
            layers = original["functional"]["liability_layers"]
            assert layers
            assert sum(layer["functional_carrying"] for layer in layers) == 2200000
            assert sum(layer["txn_open"] for layer in layers) == 2000000
            assert "Current liability follows original FIFO layer release" in str(contribution)
            assert "Original liability layer" in str(contribution)
            assert "LIABILITY_LAYER_CREATED" in str(contribution)
            assert "Original functional contract_liability: 22000.00 USD" in str(contribution)
            assert any(
                "contract_liability_functional" in link["href"]
                for link in contribution["source_links"]
            )
        if view == "reporting" or foreign:
            if not foreign:
                assert "Retained closing FX rate" in str(contribution)
            repeated = post(
                world.app, f"/api/v1/report-runs/{balance_run['id']}/rerun", world.maya, {}
            )
            assert repeated.status_code == 202, repeated.text
            done = worlds.run_now(world, UUID(repeated.json()["id"]))
            assert done["state"] == "SUCCEEDED", done
            rerun_id = repeated.headers[worlds.REPORT_RUN_ID_HEADER]
            repeated_explanation = get(
                world.app,
                f"/api/v1/explain/report-runs/{rerun_id}/cell",
                world.maya,
                params={"row_key": own["row_key"], "column_key": "contract_liability_current"},
            )
            assert repeated_explanation.status_code == 200, repeated_explanation.text
            assert repeated_explanation.json()["value"] == body["value"]
            assert repeated_explanation.json()["contributors"] == body["contributors"]
        if view == "transaction":
            _, later = worlds.report_run(
                world,
                "contract_balances",
                {
                    **params,
                    "period_key": "FY2026-P09",
                },
            )
            retained = next(row for row in later if row["row_key"] == own["row_key"])
            assert retained["contract_liability"] == own["contract_liability"]
        run, rows = worlds.report_run(
            world,
            "contract_balance_rollforward",
            {
                **params,
                "from_period_key": "FY2026-P08",
                "to_period_key": "FY2026-P08",
            },
        )
        own = next(
            row for row in rows if row["row_key"] == f"contract:ACQUIRED-EUR:{worlds.AVM_US}"
        )
        assert own["closing"] == {"currency": currency, "amount": expected}
        assert own["business_combinations"] == {
            "currency": currency,
            "amount": ("20000.00" if foreign else "18181.82") if view == "reporting" else expected,
        }
        if view == "reporting":
            assert own["translation"]["amount"] == ("-90.50" if foreign else "-82.27")
        assert own["other"]["amount"] == "0.00"
        checks = {item["code"]: item["result"] for item in run["tie_out_results"]}
        assert checks["TO_BALANCES_EQ_ROLLFORWARD"] == "PASS"
        explained = get(
            world.app,
            f"/api/v1/explain/report-runs/{run['id']}/cell",
            world.maya,
            params={"row_key": own["row_key"], "column_key": "business_combinations"},
        )
        assert explained.status_code == 200, explained.text
        contribution = explained.json()["contributors"]["items"][0]
        assert any("/trace/" in link["href"] for link in contribution["source_links"])
        repeated = post(world.app, f"/api/v1/report-runs/{run['id']}/rerun", world.maya, {})
        assert repeated.status_code == 202, repeated.text
        done = worlds.run_now(world, UUID(repeated.json()["id"]))
        assert done["state"] == "SUCCEEDED", done
        data = get(
            world.app,
            f"/api/v1/report-runs/{repeated.headers['x-erev-report-run-id']}/data",
            world.maya,
            {"limit": "200"},
        )
        assert data.status_code == 200, data.text
        assert data.json()["items"] == rows

    if foreign:
        for view, currency, closing, movement, translation in (
            ("functional", "USD", "22000.00", "22000.00", None),
            ("reporting", "EUR", "19909.50", "20000.00", "-90.50"),
        ):
            run, rows = _settled_report(
                world,
                "contract_balance_rollforward",
                {
                    "entity_codes": [worlds.AVM_US],
                    "book": "ASC606",
                    "currency_view": view,
                    "from_period_key": "FY2026-P08",
                    "to_period_key": "FY2026-P08",
                },
            )
            own = next(
                row for row in rows if row["row_key"] == f"contract:ACQUIRED-EUR:{worlds.AVM_US}"
            )
            assert own["closing"] == {"currency": currency, "amount": closing}
            assert own["business_combinations"] == {"currency": currency, "amount": movement}
            assert own["other"]["amount"] == "0.00"
            if translation is not None:
                assert own["translation"]["amount"] == translation
            checks = {item["code"]: item["result"] for item in run["tie_out_results"]}
            assert checks["TO_BALANCES_EQ_ROLLFORWARD"] == "PASS"
            explained = get(
                world.app,
                f"/api/v1/explain/report-runs/{run['id']}/cell",
                world.maya,
                params={"row_key": own["row_key"], "column_key": "business_combinations"},
            )
            assert explained.status_code == 200, explained.text
            assert "contract_liability_functional" in str(explained.json())
            repeated = post(world.app, f"/api/v1/report-runs/{run['id']}/rerun", world.maya, {})
            assert repeated.status_code == 202, repeated.text
            done = worlds.run_now(world, UUID(repeated.json()["id"]))
            assert done["state"] == "SUCCEEDED", done
            data = get(
                world.app,
                f"/api/v1/report-runs/{repeated.headers['x-erev-report-run-id']}/data",
                world.maya,
                {"limit": "200"},
            )
            assert data.status_code == 200, data.text
            assert data.json()["items"] == rows


def _settled_refusal(world, job_id):
    from sqlalchemy import select

    from erev_api.db.session import DbContext, tenant_session
    from erev_api.db.tables import job
    from erev_api.jobs.registry import run_job

    state = worlds.run_now(world, job_id)
    if state["state"] not in ("SUCCEEDED", "FAILED"):
        context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as session:
            task_id = session.execute(
                select(job.c.procrastinate_job_id).where(job.c.id == job_id)
            ).scalar_one()
            session.execute(worlds._TASK_FETCHED, {"id": task_id})
        run_job(job_id, world.tenant_id, attempt=2, runtime=world.runtime)
        shown = get(world.app, f"/api/v1/jobs/{job_id}", world.maya)
        assert shown.status_code == 200, shown.text
        state = shown.json()
    return state


def _settled_report(world, code, parameters):
    started = post(
        world.app,
        "/api/v1/report-runs",
        world.maya,
        {
            "report_code": code,
            "parameters": parameters,
            "output_format": "JSON",
        },
    )
    assert started.status_code == 202, started.text
    done = _settled_refusal(world, UUID(started.json()["id"]))
    assert done["state"] == "SUCCEEDED", str(done.get("problem"))
    run_id = started.headers[worlds.REPORT_RUN_ID_HEADER]
    shown = get(world.app, f"/api/v1/report-runs/{run_id}", world.maya)
    rows = get(world.app, f"/api/v1/report-runs/{run_id}/data", world.maya, {"limit": "200"})
    assert shown.status_code == rows.status_code == 200
    return shown.json(), rows.json()["items"]


def _closed_group_reports(world, snapshots):
    assert len(snapshots) == 2
    members = {"ACQUIRED-EUR", "ACQUIRED-SECOND"}
    for view, currency, amount in (
        ("transaction", "EUR", "20000.00"),
        ("functional", "USD", "22000.00"),
        ("reporting", "EUR", "19909.50"),
    ):
        params = {"entity_codes": [worlds.AVM_US], "book": "ASC606", "currency_view": view}
        for code, timing in (
            ("contract_balances", {"period_key": "FY2026-P08"}),
            (
                "contract_balance_rollforward",
                {"from_period_key": "FY2026-P08", "to_period_key": "FY2026-P08"},
            ),
        ):
            run, rows = worlds.report_run(world, code, {**params, **timing})
            selected = [
                row
                for row in rows
                if row["row_key"] in {f"contract:{member}:{worlds.AVM_US}" for member in members}
            ]
            assert len(selected) == 2
            column = "contract_liability_current" if code == "contract_balances" else "closing"
            explanations = {}
            for row in selected:
                assert row[column] == {"amount": amount, "currency": currency}
                if code == "contract_balance_rollforward":
                    assert row["other"]["amount"] == "0.00"
                explained = get(
                    world.app,
                    f"/api/v1/explain/report-runs/{run['id']}/cell",
                    world.maya,
                    params={
                        "row_key": row["row_key"],
                        "column_key": column
                        if code == "contract_balances"
                        else "business_combinations",
                    },
                )
                assert explained.status_code == 200, explained.text
                explanations[row["row_key"]] = explained.json()
                if code == "contract_balances":
                    assert "complete acquisition group" in str(explained.json())
            if code == "contract_balance_rollforward":
                assert {check["code"]: check["result"] for check in run["tie_out_results"]}[
                    "TO_BALANCES_EQ_ROLLFORWARD"
                ] == "PASS"
            repeated = post(world.app, f"/api/v1/report-runs/{run['id']}/rerun", world.maya, {})
            assert repeated.status_code == 202, repeated.text
            again = worlds.run_now(world, UUID(repeated.json()["id"]))
            assert again["state"] == "SUCCEEDED", again
            rerun_id = repeated.headers[worlds.REPORT_RUN_ID_HEADER]
            retained = get(world.app, f"/api/v1/report-runs/{rerun_id}", world.maya)
            assert retained.status_code == 200, retained.text
            assert retained.json()["output"]["sha256"] == run["output"]["sha256"]
            for row_key, original in explanations.items():
                explanation = get(
                    world.app,
                    f"/api/v1/explain/report-runs/{rerun_id}/cell",
                    world.maya,
                    params={
                        "row_key": row_key,
                        "column_key": column
                        if code == "contract_balances"
                        else "business_combinations",
                    },
                )
                assert explanation.status_code == 200, explanation.text
                assert explanation.json()["value"] == original["value"]
                assert explanation.json()["contributors"] == original["contributors"]
