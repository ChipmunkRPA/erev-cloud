"""Worlds for the period-end steps of a close run (BUILD_SPEC CLO-20), built through the product's
commands.

``eur_receivable``: a EUR receivable in a USD entity under the PRD §2.5 AVM-RATES, for the FX
remeasurement (POLICIES JET-10a; POL-162, POL-164). ``k03_loss``: WLD-K-03 with an estimate at
completion above its unconstrained consideration, for the loss provision a period end decides
(POLICIES JET-12; ENGINE_SPEC_B S11-R-14, S11-R-16).

The close of the EUR receivable's August (item CLO-RATE-AFTER-RUN-1): ``august_in_soft_close``,
``journal_and_reconciliations``, ``request_lock`` and ``august_locked`` take the world to its
lock through the product; ``closing_rates_submitted`` and ``closing_rates`` publish a new
version of the closing rate set; ``gate_shown`` and ``rows`` read what the witnesses assert.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from fastapi import FastAPI
from support import close_runs as runs
from support import worlds
from support.close_world import periods_closed_before, reviewed_reconciliations_for
from support.factories import (
    approved_ssp_version,
    booked_contract,
    customer_id,
    open_periods,
    point_entry,
    product_with_template,
    published_mapping,
    published_template,
    set_default_template,
    ssp_book,
    stamp_test_release,
    workspace,
)
from support.http import HttpResponse
from support.principals import colleague, enrolled, member
from support.reference import (
    PERIODS,
    approve,
    assign,
    calendar,
    entity,
    get,
    holding,
    post,
    put,
)

AVM_US: Final = worlds.AVM_US
EUR_CONTRACT: Final = "SF-ORD-EU-3001"
EUR_HOURS: Final = "AVM-TM-EU"
# A chart of the roles a foreign-currency receivable reaches (PRD §2.6).
EUR_CHART: Final = (
    ("1100", "Accounts receivable", "ASSET", "D", "ACCOUNTS_RECEIVABLE"),
    ("1105", "Unbilled receivable", "ASSET", "D", "UNBILLED_RECEIVABLE"),
    ("1200", "Contract asset", "ASSET", "D", "CONTRACT_ASSET"),
    ("2100", "Contract liability", "LIABILITY", "C", "CONTRACT_LIABILITY"),
    ("4010", "Revenue - services and subscriptions", "REVENUE", "C", "REVENUE"),
    ("7200", "Foreign exchange gain or loss", "EXPENSE", "D", "FX_GAIN_LOSS"),
)
# PRD §2.5 AVM-RATES, EUR to USD (average, closing): Aug 2026, Sep 2026; Jan to Jul 2026 every rate
# equals the Aug 2026 average; the daily spot rate equals the month average.
EUR_AUGUST: Final = ("1.100000", "1.105000")
EUR_SEPTEMBER: Final = ("1.110000", "1.120000")
EUR_HOURS_DELIVERED: Final = Decimal("10000.00")  # 100 hours at EUR 100.00, 31 Aug 2026
AUGUST: Final = "FY2026-P08"
SEPTEMBER: Final = "FY2026-P09"
CLOSING_SET: Final = "AVM-RATES-CLOSING"
FX_RATE_SETS: Final = "/api/v1/fx-rate-sets"
# TPL-RTI: time and materials with a right to invoice, an unconditional right (POL-122).
TPL_RTI: Final = MappingProxyType(
    {
        "distinctness": "distinct",
        "satisfaction_pattern": "OVER_TIME",
        "over_time_criterion": "OT_A",
        "recognition_method": "RIGHT_TO_INVOICE",
        "policy_values": {"balance.right_to_consideration": "UNCONDITIONAL"},
    }
)
K03_LOSS_EAC: Final = "1300000.00"
K03_LOSS_EFFECTIVE: Final = "2026-09-10"
K03_LOSS_RATIONALE: Final = (
    "Ground conditions found before {effective_date}: the cost to complete exceeds the contract "
    "price."
)


def _eur_rates(rate_type: str) -> list[dict[str, str]]:
    """The PRD §2.5 EUR to USD rates of one AVM-RATES set for Jan to Sep 2026."""

    def of_month(number: int) -> tuple[str, str]:
        if number == 9:
            return EUR_SEPTEMBER
        if number == 8:
            return EUR_AUGUST
        return EUR_AUGUST[0], EUR_AUGUST[0]

    pair = {"base_currency": "EUR", "quote_currency": "USD"}
    if rate_type == "spot":
        rows: list[dict[str, str]] = []
        day = date(2026, 1, 1)
        while day <= worlds.THROUGH_SEPTEMBER:
            rows.append({**pair, "rate": of_month(day.month)[0], "effective_date": day.isoformat()})
            day += timedelta(days=1)
        return rows
    return [
        {
            **pair,
            "rate": of_month(number)[0 if rate_type == "average" else 1],
            "period_key": f"FY2026-P{number:02d}",
        }
        for number in range(1, 10)
    ]


def eur_receivable(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> worlds.ReportWorld:
    """A EUR receivable of AVM-US (USD). Maya (Revenue Accountant, SSP Analyst), Priya (Revenue
    Reviewer, SSP Approver; MFA) and Marcus (Controller, SSP Approver, Tenant Admin; MFA) as in
    ``worlds.k03_castellan``; USD and EUR enabled; FY2026-P01 to P09 open; the three AVM-RATES sets
    (spot, closing, average) carry the PRD §2.5 EUR to USD rates, approved by Marcus; AVM-TM-EU
    (TPL-RTI, an unconditional right) at EUR 100.00 an hour under EU-LIST 2026.
    ``SF-ORD-EU-3001`` books 100 hours from 01 Aug 2026, is activated and delivers them on 31 Aug
    2026; the append computes: revenue EUR 10,000.00 at the August rate 1.100000, USD 11,000.00,
    and nothing is invoiced — an unbilled receivable of EUR 10,000.00 at every later period end.
    """
    maya_member = member(keyring, clock, name="maya")
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers = {}
    for name, roles in (
        ("priya", ("revenue_reviewer", "ssp_approver")),
        ("marcus", ("controller", "ssp_approver", "tenant_admin")),
    ):
        someone = colleague(maya_member.tenant_id, name)
        for code in roles:
            assign(someone, code)
        approvers[name] = enrolled(app, clock, someone)
    priya, marcus = approvers["priya"], approvers["marcus"]
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD", "EUR"]})
    assert enabled.status_code == 200, enabled.text
    created = entity(app, maya, code=AVM_US, calendar_id=calendar(app, maya, years=(2026,)))
    open_periods(
        app, maya, entity_code=AVM_US, keys=[f"FY2026-P{month:02d}" for month in range(1, 10)]
    )
    for rate_type in ("spot", "closing", "average"):
        rate_set = post(
            app,
            "/api/v1/fx-rate-sets",
            maya,
            {
                "code": f"AVM-RATES-{rate_type.upper()}",
                "name": f"AVM-RATES {rate_type}",
                "rate_type": rate_type,
            },
        )
        assert rate_set.status_code == 201, rate_set.text
        draft = post(
            app,
            f"/api/v1/fx-rate-sets/{rate_set.json()['id']}/versions",
            maya,
            {
                "coverage_from": "2026-01-01",
                "coverage_to": worlds.THROUGH_SEPTEMBER.isoformat(),
                "rates": _eur_rates(rate_type),
            },
        )
        assert draft.status_code == 201, draft.text
        submitted = post(
            app,
            f"/api/v1/fx-rate-set-versions/{draft.json()['id']}/submit",
            maya,
            {"comment": "AVM-RATES, PRD §2.5"},
            if_match=f'"r{draft.json()["row_version"]}"',
        )
        assert submitted.status_code == 200, submitted.text
        clock.advance(timedelta(minutes=1))
        decided = approve(app, submitted.json()["pending_approval_request_id"], marcus)
        assert decided.status_code == 200, decided.text
    buyer = customer_id(app, maya, code="C-31", name="Example Customer EU (Demo)")
    hours = product_with_template(
        app,
        maya,
        code=EUR_HOURS,
        name="Time and materials hours, EUR (Demo)",
        revenue_category="SERVICES",
    )
    term = {"start_date": "2026-08-01", "end_date": "2026-12-31"}
    template = published_template(
        app,
        maya,
        marcus,
        code="TPL-RTI",
        outputs=TPL_RTI,
        case_line={
            "obligation_key": "POB-01",
            "product_code": EUR_HOURS,
            "quantity": "100",
            "total_price": "0.00",
            **term,
        },
    )
    set_default_template(app, maya, hours, template["template_id"])
    approved_ssp_version(
        app,
        maya,
        [priya],
        ssp_book(app, maya, code="EU-LIST", currency="EUR"),
        label="2026",
        effective_from="2026-01-01",
        entries=[point_entry(EUR_HOURS, "100", currency="EUR")],
    )
    published_mapping(app, maya, marcus, chart=EUR_CHART)
    stamp_test_release()
    place = workspace(app, clock, keyring, files, maya)
    booked = booked_contract(
        place,
        {
            "external_id": EUR_CONTRACT,
            "customer_id": str(buyer),
            "contracting_entity_code": AVM_US,
            "transaction_currency": "EUR",
            "inception_date": "2026-08-01",
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": EUR_HOURS,
                    "quantity": "100",
                    "total_price": {"amount": "0.00", "currency": "EUR"},
                    "unit_price": "100.00",
                    **term,
                }
            ],
        },
        activate=True,
    )
    contract_id = UUID(str(booked.contract["id"]))
    # BUILD_SPEC CTR-6: Maya's delivery waits for another user; Priya approves it, and the
    # approval appends and computes.
    worlds.approved_manual_events(
        place,
        priya,
        contract_id,
        {
            "event_type": "DELIVERY_RECORDED",
            "effective_date": "2026-08-31",
            "payload": {"obligation_key": "O1", "quantity": "100", "trigger": "DELIVERY"},
        },
        evidence_file_ids=[],
    )
    return worlds.ReportWorld(
        place=place,
        priya=priya,
        marcus=marcus,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        entity_id=UUID(str(created["id"])),
        contracts=MappingProxyType({EUR_CONTRACT: booked}),
    )


def k03_loss(
    world: worlds.K03World, clock: FrozenClock, *, effective_date: str = K03_LOSS_EFFECTIVE
) -> dict[str, Any]:
    """WLD-K-03 turned into a loss contract: EAC version 2 of 1,300,000.00, effective 10 Sep 2026
    (or ``effective_date``: with a date in August the loss emerges at 31 Aug 2026) and approved
    by Priya and, in its second step, by Marcus. The unconstrained consideration is 1,200,000.00
    (the price and the bonus of 200,000.00, ENGINE_SPEC_B S11-R-16), so the expected loss is
    100,000.00; the costs stay 420,000.00 — all incurred by 31 Aug 2026 — and the approval
    computes: cumulative revenue 1,000,000.00 x 420,000 / 1,300,000 = 323,076.92. Returns
    API-S-EstimateVersion of version 2.

    The second step (STALE TEST WORLD since lane SECFIX-APR's merge, main f97cd1e6; PRD §2.5
    ``ESTIMATE_VERSION``; supervisor rulings R-41 (7) and R-66 (4)): the version lowers progress
    from 60% to 420,000 / 1,300,000 and cumulative revenue from 600,000.00 to 323,076.92 — a P&L
    impact far above USD 50,000.00 — so the request is PENDING after Priya and APPROVED after
    the Controller, as for the EAC version of ``worlds.k03_castellan``."""
    clock.advance(timedelta(seconds=worlds.K03_STEP_SECONDS))
    report = world.report
    version = worlds.estimate_version_approved(
        world.app,
        report.maya,
        report.priya,
        world.eac_id,
        {
            "effective_date": effective_date,
            "expected_total_amount": K03_LOSS_EAC,
            "rationale": K03_LOSS_RATIONALE.format(effective_date=effective_date),
        },
        controller=report.marcus,
    )
    assert worlds.k03_revenue(report.place, world.group_id) == Decimal("323076.92")
    return version


# --- the close of the EUR receivable's August (item CLO-RATE-AFTER-RUN-1) ------------------------


def rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    """The rows of ``statement`` read under the tenant's scope, in a transaction of their own."""
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def gate_shown(
    world: worlds.ReportWorld, code: str, period_key: str = AUGUST
) -> tuple[Any, Any, Any]:
    """(status, count, detail) of the gate ``code`` as the cockpit of AVM-US's period shows it."""
    state = worlds.period_state(world, AVM_US, period_key)
    shown = get(world.app, f"{PERIODS}/{state['id']}/cockpit", world.maya)
    assert shown.status_code == 200, shown.text
    (item,) = [row for row in shown.json()["checklist"] if row["code"] == code]
    result = item.get("result") or {}
    return item["status"], result.get("count"), result.get("detail")


def august_in_soft_close(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> worlds.ReportWorld:
    """``eur_receivable`` with January to July closed (fixture state) and August in soft close."""
    world = eur_receivable(app, keyring, clock, files)
    state = worlds.period_state(world, AVM_US, AUGUST)
    periods_closed_before(
        world.place,
        app,
        world.maya,
        entity_id=UUID(str(state["entity"]["id"])),
        before=AUGUST,
        entity_code=AVM_US,
    )
    state = worlds.period_state(world, AVM_US, AUGUST)
    started = post(
        app,
        f"{PERIODS}/{state['id']}/start-close",
        world.maya,
        {"comment": "August close"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    return world


def journal_and_reconciliations(
    world: worlds.ReportWorld, clock: FrozenClock, run: Mapping[str, Any]
) -> worlds.ReportWorld:
    """The rest of what August's lock asks beside its close run: the journal run the close run
    calculated through its life, and the two reconciliations reviewed (fixture rows, as the lock
    tests state them)."""
    world = runs.journal_posted(world, clock, str(run["journal_run_id"]))
    state = worlds.period_state(world, AVM_US, AUGUST)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        reviewed_reconciliations_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=UUID(str(state["entity"]["id"])),
            period_id=UUID(str(state["period"]["id"])),
            now=clock.now(),
        )
    return world


def request_lock(world: worlds.ReportWorld, period_key: str = AUGUST) -> HttpResponse:
    """Maya's ``request-lock`` of AVM-US's period, as the route answers it."""
    state = worlds.period_state(world, AVM_US, period_key)
    return post(
        world.app,
        f"{PERIODS}/{state['id']}/request-lock",
        world.maya,
        {"certification_comment": f"{state['period']['name']} close complete"},
        if_match=f'"r{state["row_version"]}"',
    )


def august_locked(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[worlds.ReportWorld, dict[str, Any]]:
    """August closed through the product on its own close run: the run posts the remeasurement
    at the closing rate in force, its journal run is acknowledged, the reconciliations are
    reviewed, Maya requests the lock and Marcus approves it. (the world, API-S-CloseRun)."""
    world = august_in_soft_close(app, keyring, clock, files)
    run = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert (run["status"], run["current_step_code"]) == ("SUCCEEDED", None), run
    world = journal_and_reconciliations(world, clock, run)
    requested = request_lock(world)
    assert requested.status_code == 200, requested.text
    clock.advance(timedelta(minutes=1))
    world = worlds.verified(world, clock, "marcus")
    decided = approve(app, str(requested.json()["approval_request_id"]), world.marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert worlds.period_state(world, AVM_US, AUGUST)["state"] == "closed"
    return world, run


def closing_rates_submitted(
    world: worlds.ReportWorld,
    changed: Mapping[str, str | None],
    *,
    comment: str = "Closing rates republished",
) -> dict[str, str]:
    """A new version of the closing rate set over the same coverage, submitted by Maya — every
    rate as ``_eur_rates`` states it but those of ``changed`` (period key to rate; None leaves
    the period's rate out of the version). ``{"version_id", "approval_request_id"}``."""
    app = world.app
    listed = get(app, FX_RATE_SETS, world.maya, {"limit": 50})
    assert listed.status_code == 200, listed.text
    (closing,) = [item for item in listed.json()["items"] if item["code"] == CLOSING_SET]
    rates = []
    for row in _eur_rates("closing"):
        rate = changed.get(row["period_key"], row["rate"])
        if rate is not None:
            rates.append({**row, "rate": rate})
    draft = post(
        app,
        f"{FX_RATE_SETS}/{closing['id']}/versions",
        world.maya,
        {
            "coverage_from": "2026-01-01",
            "coverage_to": worlds.THROUGH_SEPTEMBER.isoformat(),
            "rates": rates,
        },
    )
    assert draft.status_code == 201, draft.text
    submitted = post(
        app,
        f"/api/v1/fx-rate-set-versions/{draft.json()['id']}/submit",
        world.maya,
        {"comment": comment},
        if_match=f'"r{draft.json()["row_version"]}"',
    )
    assert submitted.status_code == 200, submitted.text
    return {
        "version_id": str(draft.json()["id"]),
        "approval_request_id": str(submitted.json()["pending_approval_request_id"]),
    }


def closing_rates(
    world: worlds.ReportWorld, clock: FrozenClock, changed: Mapping[str, str | None]
) -> worlds.ReportWorld:
    """``closing_rates_submitted``, approved by Marcus with a fresh TOTP."""
    sent = closing_rates_submitted(world, changed)
    clock.advance(timedelta(minutes=1))
    world = worlds.verified(world, clock, "marcus")
    decided = approve(world.app, sent["approval_request_id"], world.marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    return world
