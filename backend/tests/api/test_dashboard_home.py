"""API-R-50 home dashboard read model and API-R-16 favourites (04 §16.13 API-S-DashboardHome,
API-C-11, API-R-16, T-PLT-37; SCREENS §2.5, §2.6, R-02, SCR-IA-08; PRD WLD-B-01 to WLD-B-03,
WLD-K-01, WLD-K-02, WLD-X-02, WLD-X-03; 03 REQ-RPT-016, REQ-UX-017; BUILD_SPEC RPS-17).

Worlds: ``support.worlds.report_world`` with K-01 ``SF-ORD-10001`` and K-02 ``SF-ORD-10002`` booked,
activated, billed and computed at the frozen clock 2026-09-12T12:00:00Z (AVM-US, FY2026-P01 to P09
open); otherwise Maya's workspace (Revenue Accountant) with AVM-US on a January calendar, and for
the approvals the WLD-B-01 to WLD-B-03 requests written as rows with their active steps, for Priya
(Revenue Reviewer) and Robert (Viewer).

R-RC-1 (L6-3-Q-18): K-02 runs without modification CR-MARROWBY-2026-09 (CTR-17 post-rc), so its
September 2026 revenue is 9,863.01, its contract liability 40,109.59 at 31 Aug 2026 and 30,246.58 at
30 Sep 2026, and its RPO at 30 Sep 2026 150,246.58, of which 120,000.00 within 12 months.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    approval_step,
    combination_group,
    contract,
    customer,
    exception_item,
    judgement_record,
)
from erev_api.enums import RegistryCategory, RegistryScope
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_engine.money import format_exact
from fastapi import FastAPI
from sqlalchemy import insert, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import open_periods, world_calendar
from support.http import HttpResponse, call
from support.principals import (
    Actor,
    colleague,
    cookie_headers,
    enrolled,
    member,
    sign_in,
    workspace,
)
from support.reference import assign, entity, fields, get, holding, periods, put, slug
from support.rows import (
    approval_request_values,
    approval_step_values,
    combination_group_values,
    contract_values,
    customer_values,
    exception_item_values,
    insert_custom_role,
    judgement_record_values,
    publish_registry_version,
)
from support.worlds import AVM_US, K01, K02, SEPTEMBER_2026, report_run, report_world

HOME: Final = "/api/v1/dashboard/home"
SAVED_VIEWS: Final = "/api/v1/saved-views"
BOOK: Final = "ASC606"
AUGUST_2026: Final = "FY2026-P08"
SEPTEMBER: Final = {
    "entity_codes": [AVM_US],
    "book": BOOK,
    "from_period_key": SEPTEMBER_2026,
    "to_period_key": SEPTEMBER_2026,
}
AT_SEPTEMBER: Final = {"entity_codes": [AVM_US], "book": BOOK, "period_key": SEPTEMBER_2026}
TREND_KEYS: Final = [f"FY2026-P{month:02d}" for month in range(4, 10)]
CHART_KEYS: Final = [
    *(f"FY2026-P{month:02d}" for month in range(4, 13)),
    *(f"FY2027-P{month:02d}" for month in range(1, 4)),
]
D = Decimal


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def keyed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(row["row_key"]): row for row in rows}


def home(app: FastAPI, actor: Actor, params: Mapping[str, Any]) -> dict[str, Any]:
    shown = get(app, HOME, actor, params)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


@contextmanager
def system(tenant_id: UUID) -> Iterator[Session]:
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        yield session


@pytest.mark.slow
def test_home_consistency_k01(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = report_world(app, keyring, clock, files, contracts=(K01, K02))
    # POL-201 presents 24-month bands for AVM-US; the home RPO keeps its 12-month bound.
    with system(world.tenant_id) as session:
        publish_registry_version(
            session,
            tenant_id=world.tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            scope=RegistryScope.ENTITY,
            entity_id=world.entity_id,
            values={"rpo.time_bands": [24]},
            at=world.place.clock.now(),
        )
    body = home(world.app, world.maya, {"entity": AVM_US, "period": SEPTEMBER_2026, "book": BOOK})
    context = body["context"]
    assert (
        context["entity"]["id"],
        context["entity"]["code"],
        context["book"],
        context["currency"],
        context["known_at"],
        context["period"]["period_key"],
        context["period"]["end_date"],
    ) == (
        str(world.entity_id),
        AVM_US,
        BOOK,
        "USD",
        "2026-09-12T12:00:00Z",
        SEPTEMBER_2026,
        "2026-09-30",
    )

    # J-16.1: the Revenue figure equals the SF-04 waterfall total of AVM-US Sep 2026.
    run, rows = report_run(world, "revenue_waterfall", SEPTEMBER)
    total = keyed(rows)["TOTAL:USD"]
    revenue = body["revenue"]
    assert revenue["current"] == total[f"period:{SEPTEMBER_2026}"] == total["total"]
    assert revenue["current"] == usd("19627.39")  # K-01 9,764.38 (WLD-X-02) + K-02 9,863.01
    assert run["control_totals"]["recognized_total"] == {"USD": "19627.39"}
    assert [item["period_key"] for item in revenue["trend"]] == TREND_KEYS
    trend = {item["period_key"]: item["recognized"] for item in revenue["trend"]}
    assert trend[SEPTEMBER_2026] == revenue["current"]
    _, august = report_run(
        world,
        "revenue_waterfall",
        {**SEPTEMBER, "from_period_key": AUGUST_2026, "to_period_key": AUGUST_2026},
    )
    assert revenue["prior"] == trend[AUGUST_2026] == keyed(august)["TOTAL:USD"]["total"]
    current, prior = (Fraction(D(revenue[name]["amount"])) for name in ("current", "prior"))
    assert revenue["change_ratio"] == format_exact((current - prior) / abs(prior))

    for period_key, end in ((SEPTEMBER_2026, "closing"), (AUGUST_2026, "opening")):
        _, balances = report_run(
            world, "contract_balances", {**AT_SEPTEMBER, "period_key": period_key}
        )
        assert body["contract_liability"][end] == keyed(balances)["TOTAL:USD"]["contract_liability"]
    # WLD-X-03: K-01 39,708.49 at 31 Aug 2026 and 29,944.11 at 30 Sep 2026.
    assert body["contract_liability"] == {"closing": usd("60190.69"), "opening": usd("79818.08")}

    rpo_run, rpo_rows = report_run(world, "rpo", AT_SEPTEMBER)
    assert [band["key"] for band in rpo_run["control_totals"]["bands"]] == [
        "within_24_months",
        "after_24_months",
    ]
    assert body["rpo"]["total"] == usd(rpo_run["control_totals"]["total"]["USD"])
    assert body["rpo"]["within_12_months"] == keyed(rpo_rows)["TOTAL:USD"]["current"]
    assert body["rpo"] == {"total": usd("180190.69"), "within_12_months": usd("149944.11")}

    # REQ-RPT-016: close status equals API-S-Period of AVM-US Sep 2026 — the single read, which
    # carries the blocker counts (a row of the list answers them null; 04 §16.8 rev 1.199).
    (listed,) = [
        item
        for item in periods(world.app, world.maya, entity=AVM_US)
        if item["period"]["period_key"] == SEPTEMBER_2026
    ]
    shown = get(world.app, f"/api/v1/periods/{listed['id']}", world.maya)
    assert shown.status_code == 200, shown.text
    september = shown.json()
    # 04 §16.13 rev 1.206: ``close`` states the period's ``id`` too — what the row "Exceptions
    # holding the lock" passes to the exception list as ``blocking`` (SCREENS §2.6 rev 1.37).
    assert body["close"] == {
        "id": september["id"],
        "state": september["state"],
        "blockers": september["blockers"],
        "close_run": september["close_run"],
    }
    assert body["close"]["state"] == "open"

    chart_run, chart_rows = report_run(
        world,
        "revenue_waterfall",
        {
            "entity_codes": [AVM_US],
            "book": BOOK,
            "from_period_key": CHART_KEYS[0],
            "to_period_key": CHART_KEYS[-1],
            "as_of": "2026-09-30",
            "measure": "BY_STATE",
        },
    )
    totals = keyed(chart_rows)["TOTAL:USD"]
    chart = body["revenue_chart"]
    assert [item["period_key"] for item in chart["periods"]] == CHART_KEYS
    assert [(item["recognized"], item["scheduled"]) for item in chart["periods"]] == [
        (totals[f"period:{key}:recognized"], totals[f"period:{key}:scheduled"])
        for key in CHART_KEYS
    ]
    assert chart["awaiting_trigger"] == usd(
        chart_run["control_totals"]["awaiting_trigger_total"]["USD"]
    )
    assert (chart["awaiting_trigger"], chart["pending_trigger_count"]) == (usd("0.00"), 0)
    # L7-2-Q-21: the per-period total and the Table view totals row come from the API.
    amount = lambda value: D(value["amount"])  # noqa: E731
    for item in chart["periods"]:
        assert amount(item["total"]) == amount(item["recognized"]) + amount(item["scheduled"])
        assert item["total"]["currency"] == "USD"
    recognized_sum = sum((amount(item["recognized"]) for item in chart["periods"]), D("0"))
    scheduled_sum = sum((amount(item["scheduled"]) for item in chart["periods"]), D("0"))
    assert {name: amount(value) for name, value in chart["totals"].items()} == {
        "recognized": recognized_sum,
        "scheduled": scheduled_sum,
        "awaiting_trigger": D("0.00"),
        "total": recognized_sum + scheduled_sum,
    }
    assert chart["totals"]["total"] == usd(f"{recognized_sum + scheduled_sum:.2f}")


def test_change_ratio_null_without_prior(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    world_calendar(app, maya)
    body = home(app, maya, {"entity": AVM_US, "period": SEPTEMBER_2026})
    revenue = body["revenue"]
    assert (revenue["current"], revenue["prior"], revenue["change_ratio"]) == (
        usd("0.00"),
        usd("0.00"),
        None,
    )
    assert [(item["period_key"], item["recognized"]) for item in revenue["trend"]] == [
        (key, usd("0.00")) for key in TREND_KEYS
    ]
    assert body["contract_liability"] == {"closing": usd("0.00"), "opening": usd("0.00")}
    assert body["rpo"] == {"total": usd("0.00"), "within_12_months": usd("0.00")}
    assert [item["period_key"] for item in body["revenue_chart"]["periods"]] == CHART_KEYS
    assert {item["total"]["amount"] for item in body["revenue_chart"]["periods"]} == {"0.00"}
    assert body["revenue_chart"]["totals"] == {
        "recognized": usd("0.00"),
        "scheduled": usd("0.00"),
        "awaiting_trigger": usd("0.00"),
        "total": usd("0.00"),
    }
    # FY2026-P01 opens the calendar: no prior period, no ratio, one trend period.
    first = home(app, maya, {"entity": AVM_US, "period": "FY2026-P01"})["revenue"]
    assert (first["prior"], first["change_ratio"]) == (None, None)
    assert [item["period_key"] for item in first["trend"]] == ["FY2026-P01"]
    # Defaults: the primary book and the earliest open period of the context entities.
    defaulted = home(app, maya, {"entity": AVM_US})["context"]
    assert (defaulted["book"], defaulted["period"]["period_key"]) == (BOOK, "FY2026-P01")


def _contract(session: Session, tenant_id: UUID, entity_id: UUID) -> UUID:
    buyer = customer_values(tenant_id)
    session.execute(insert(customer).values(**buyer))
    group = combination_group_values(tenant_id)
    session.execute(insert(combination_group).values(**group))
    row = contract_values(
        tenant_id,
        customer_id=buyer["id"],
        contracting_entity_id=entity_id,
        combination_group_id=group["id"],
    )
    session.execute(insert(contract).values(**row))
    return UUID(str(row["id"]))


def _submitted_judgement(session: Session, tenant_id: UUID, contract_id: UUID) -> UUID:
    row = judgement_record_values(
        tenant_id,
        topic="PRINCIPAL_AGENT",
        subject_type="contract",
        subject_id=contract_id,
        contract_id=contract_id,
        book_code=BOOK,
    )
    session.execute(insert(judgement_record).values(**row))
    session.execute(
        update(judgement_record)
        .where(judgement_record.c.id == row["id"])
        .values(status="SUBMITTED", content_sha256="a" * 64, updated_by_kind="SYSTEM")
    )
    return UUID(str(row["id"]))


def test_pending_approvals_decidable_only(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    _, entity_id = world_calendar(app, maya)
    tenant_id = maya_member.tenant_id
    priya = holding(app, colleague(tenant_id, "priya"), "revenue_reviewer")
    robert = holding(app, colleague(tenant_id, "robert"), "viewer")
    with system(tenant_id) as session:
        activation, adjusted, judged, own = (
            _contract(session, tenant_id, entity_id) for _ in range(4)
        )
        judgement_id = _submitted_judgement(session, tenant_id, judged)
        requests: tuple[tuple[dict[str, Any], str], ...] = (
            (  # WLD-B-01
                {
                    "subject_type": "CONTRACT_ACTIVATION",
                    "subject_id": activation,
                    "preparer_id": maya_member.user_id,
                    "amount_functional": D("146000.00"),
                    "amount_currency": "USD",
                    "summary": "Activate BG-AVM-0020",
                    "submitted_at": datetime(2026, 9, 10, 9, tzinfo=UTC),
                },
                "contract.approve",
            ),
            (  # WLD-B-02
                {
                    "subject_type": "MANUAL_ADJUSTMENT",
                    "subject_id": adjusted,
                    "entity_id": entity_id,
                    "preparer_id": maya_member.user_id,
                    "amount_functional": D("2400.00"),
                    "amount_currency": "USD",
                    "summary": "Schedule override on BG-AVM-0022",
                    "submitted_at": datetime(2026, 9, 11, 9, tzinfo=UTC),
                },
                "adjustment.approve",
            ),
            (  # WLD-B-03
                {
                    "subject_type": "JUDGEMENT_RECORD",
                    "subject_id": judgement_id,
                    "preparer_id": maya_member.user_id,
                    "summary": "Review principal and agent judgement",
                    "submitted_at": datetime(2026, 9, 11, 10, tzinfo=UTC),
                },
                "judgement.review",
            ),
            (  # Priya prepared it, so she cannot decide it.
                {
                    "subject_type": "CONTRACT_ACTIVATION",
                    "subject_id": own,
                    "preparer_id": priya.member.user_id,
                    "summary": "Activate BG-AVM-0025",
                    "submitted_at": datetime(2026, 9, 9, 9, tzinfo=UTC),
                },
                "contract.approve",
            ),
            (  # A step permission Priya does not hold.
                {
                    "subject_type": "ROLE_CHANGE",
                    "preparer_id": maya_member.user_id,
                    "summary": "Grant the viewer role",
                    "submitted_at": datetime(2026, 9, 9, 10, tzinfo=UTC),
                },
                "access.approve",
            ),
        )
        for values, permission in requests:
            request = approval_request_values(tenant_id, current_step_no=1, **values)
            session.execute(insert(approval_request).values(**request))
            step = approval_step_values(
                tenant_id, approval_request_id=request["id"], required_permission=permission
            )
            session.execute(insert(approval_step).values(**step))
        for severity in ("BLOCKING", "BLOCKING", "WARNING", "INFO"):
            item = exception_item_values(
                tenant_id,
                source="IMPORT",
                code="PROGRESS_OVER_DELIVERY",
                severity=severity,
                title="Delivery exceeds the contracted quantity",
                entity_id=entity_id,
            )
            session.execute(insert(exception_item).values(**item))
        session.execute(insert(exception_item).values(**exception_item_values(tenant_id)))

    context = {"entity": AVM_US, "period": SEPTEMBER_2026}
    shown = home(app, priya, context)
    assert shown["pending_approvals"] == {"count": 3, "oldest_submitted_at": "2026-09-10T09:00:00Z"}
    # Supervisor ruling R-121 (i), one attribution of an item to an entity (04 T-IMP-05, rev
    # 1.206): the workspace-level item — it names nothing and holds every entity's close — is
    # AVM-US's too. 4/2/1/1 before, by the item's own column: a stale expectation by that ruling.
    assert shown["open_exceptions"] == {"total": 5, "blocking": 3, "warning": 1, "info": 1}
    # The tile counts what the inbox shows for that entity (supervisor ruling R-104, findings
    # Q-43 and Q-48; R-64 (4)): "Waiting for me" filtered by the entity is the same set.
    inbox = get(app, "/api/v1/approvals", priya, {"assigned_to_me": "true", "entity": AVM_US})
    assert inbox.status_code == 200, inbox.text
    assert len(inbox.json()["items"]) == shown["pending_approvals"]["count"] == 3
    across = home(app, priya, {"period": SEPTEMBER_2026})
    assert across["pending_approvals"]["count"] == 3
    assert across["open_exceptions"] == {"total": 5, "blocking": 3, "warning": 1, "info": 1}
    for someone in (robert, maya):
        assert home(app, someone, context)["pending_approvals"] == {
            "count": 0,
            "oldest_submitted_at": None,
        }


def test_a_request_of_a_subject_type_without_a_specification_waits_for_nobody(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Item APR-WAITING-SPECLESS-1 (supervisor ruling R-87 (3); 04 §16.10): a pending request whose
    subject type has no specification yet (``subjects.PENDING_SUBJECTS``; no command submits one)
    is waiting for nobody. Priya holds its step's permission for every entity, and still the
    inbox, its total and the Home tile leave it out — as ``can_decide`` answers false for it
    (R-64 (7) (c)). The request of a specified subject beside it is listed and counted.

    Fail-first: on the stored columns alone the row was listed and counted for Priya."""
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    _, entity_id = world_calendar(app, maya)
    tenant_id = maya_member.tenant_id
    priya = holding(app, colleague(tenant_id, "priya"), "revenue_reviewer")
    with system(tenant_id) as session:
        activation = _contract(session, tenant_id, entity_id)
        rows: tuple[dict[str, Any], ...] = (
            {  # a subject type of a phase that is not built: no specification
                "subject_type": "AI_PROPOSAL_ACCEPTANCE",
                "preparer_id": maya_member.user_id,
                "summary": "Accept the proposed allocation",
                "submitted_at": datetime(2026, 9, 9, 9, tzinfo=UTC),
            },
            {  # positive control: a specified subject Priya can decide
                "subject_type": "CONTRACT_ACTIVATION",
                "subject_id": activation,
                "preparer_id": maya_member.user_id,
                "summary": "Activate BG-AVM-0020",
                "submitted_at": datetime(2026, 9, 10, 9, tzinfo=UTC),
            },
        )
        written: list[str] = []
        for values in rows:
            request = approval_request_values(tenant_id, current_step_no=1, **values)
            session.execute(insert(approval_request).values(**request))
            step = approval_step_values(
                tenant_id, approval_request_id=request["id"], required_permission="contract.approve"
            )
            session.execute(insert(approval_step).values(**step))
            written.append(str(request["id"]))
    specless, specified = written

    waiting = get(app, "/api/v1/approvals", priya, {"assigned_to_me": "true", "count": "true"})
    assert waiting.status_code == 200, waiting.text
    assert [item["id"] for item in waiting.json()["items"]] == [specified]
    assert waiting.headers["X-Erev-Total-Count"] == "1"
    assert home(app, priya, {"period": SEPTEMBER_2026})["pending_approvals"] == {
        "count": 1,
        "oldest_submitted_at": "2026-09-10T09:00:00Z",
    }
    # The request itself is readable and says so: nobody can decide it.
    shown = get(app, f"/api/v1/approvals/{specless}", priya)
    assert shown.status_code == 200, shown.text
    assert shown.json()["can_decide"] is False


def test_the_home_counts_what_the_inbox_lists_for_an_approver_who_reads_less(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Supervisor ruling R-64 (4) under item READ-SCOPE-BY-PERMISSION-1 (register index 301; 04
    §16.13 rev 1.319; the supervisor's ruling of 2026-10-03): the Home's count asks what the
    inbox asks, under the scope the inbox has. The Home is a read of ``contract.read`` and its
    transaction runs under that permission's scope; the inbox carries no permission guard. Ada
    approves contracts for AVM-UK — a role of the workspace's own with ``contract.approve``
    alone — and is a Viewer of AVM-US: her approval permission reaches an entity her
    ``contract.read`` does not. A request of AVM-UK waits for her in her own right; the inbox
    lists it and the Home counts it, and neither counts the request of AVM-US, which is not
    hers to decide.

    Fail-first (the count moved back under the route's scope): the Home answered 0 beside an
    inbox of 1 — the row policy of ``contract.read`` hid the request of AVM-UK."""
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    calendar_id, us = world_calendar(app, maya)
    uk = UUID(str(entity(app, maya, code="AVM-UK", calendar_id=calendar_id)["id"]))
    open_periods(
        app, maya, entity_code="AVM-UK", keys=[f"FY2026-P{month:02d}" for month in range(1, 10)]
    )
    tenant_id = maya_member.tenant_id
    someone = colleague(tenant_id, "ada")
    with system(tenant_id) as session:
        insert_custom_role(
            session, tenant_id=tenant_id, code="approves_only", permissions=["contract.approve"]
        )
        written: dict[str, str] = {}
        for name, entity_id, day in (("uk", uk, 10), ("us", us, 11)):
            request = approval_request_values(
                tenant_id,
                current_step_no=1,
                subject_type="CONTRACT_ACTIVATION",
                subject_id=_contract(session, tenant_id, entity_id),
                entity_id=entity_id,
                preparer_id=maya_member.user_id,
                summary=f"Activate a contract of {name.upper()}",
                submitted_at=datetime(2026, 9, day, 9, tzinfo=UTC),
            )
            session.execute(insert(approval_request).values(**request))
            step = approval_step_values(
                tenant_id, approval_request_id=request["id"], required_permission="contract.approve"
            )
            session.execute(insert(approval_step).values(**step))
            written[name] = str(request["id"])
    assign(someone, "approves_only", entity_ids=[uk])
    ada = holding(app, someone, "viewer", entity_ids=[us])

    waiting = get(app, "/api/v1/approvals", ada, {"assigned_to_me": "true", "count": "true"})
    assert waiting.status_code == 200, waiting.text
    assert [item["id"] for item in waiting.json()["items"]] == [written["uk"]]
    assert waiting.headers["X-Erev-Total-Count"] == "1"
    assert home(app, ada, {"period": SEPTEMBER_2026})["pending_approvals"] == {
        "count": 1,
        "oldest_submitted_at": "2026-09-10T09:00:00Z",
    }
    # the control: an approver for every entity counts both, on the Home as in the inbox
    priya = holding(app, colleague(tenant_id, "priya"), "revenue_reviewer")
    assert home(app, priya, {"period": SEPTEMBER_2026})["pending_approvals"]["count"] == 2
    listed = get(app, "/api/v1/approvals", priya, {"assigned_to_me": "true"})
    assert sorted(item["id"] for item in listed.json()["items"]) == sorted(written.values())


def test_reporting_currency_across_entities(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    marcus_member = colleague(maya_member.tenant_id, "marcus")
    assign(marcus_member, "tenant_admin")
    marcus = enrolled(app, clock, marcus_member)
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD", "GBP"]})
    assert enabled.status_code == 200, enabled.text
    calendar_id, _ = world_calendar(app, maya)
    entity(
        app,
        maya,
        code="AVM-UK",
        calendar_id=calendar_id,
        functional_currency="GBP",
        time_zone="Europe/London",
    )
    open_periods(
        app, maya, entity_code="AVM-UK", keys=[f"FY2026-P{month:02d}" for month in range(1, 10)]
    )

    across = home(app, maya, {"period": SEPTEMBER_2026})
    assert (across["context"]["entity"], across["context"]["currency"]) == (None, "USD")
    assert (across["revenue"]["current"], across["rpo"]["total"]) == (usd("0.00"), usd("0.00"))
    assert across["close"] is None
    both = home(app, maya, {"entity": [AVM_US, "AVM-UK"], "period": SEPTEMBER_2026})
    assert (both["context"]["entity"], both["context"]["currency"]) == (None, "USD")
    uk = home(app, maya, {"entity": "AVM-UK", "period": SEPTEMBER_2026})
    assert (uk["context"]["entity"]["code"], uk["context"]["currency"]) == ("AVM-UK", "GBP")
    assert uk["revenue"]["current"] == {"amount": "0.00", "currency": "GBP"}
    assert uk["close"] is not None and uk["close"]["state"] == "open"

    unknown = get(app, HOME, maya, {"entity": "AVM-XX"})
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text
    assert fields(unknown) == [("entity", "API-C-11")]
    outside = get(app, HOME, maya, {"entity": AVM_US, "period": "FY2031-P01"})
    assert (outside.status_code, fields(outside)) == (422, [("period", "API-C-11")]), outside.text


def send(
    app: FastAPI, method: str, path: str, actor: Actor, json: Mapping[str, Any]
) -> HttpResponse:
    headers = cookie_headers(actor.token, actor.csrf_token)
    return call(app, method, path, json=dict(json), headers=headers)


def favourites(app: FastAPI, actor: Actor) -> list[tuple[str, str, str, str]]:
    listed = get(app, SAVED_VIEWS, actor, {"is_favourite": "true"})
    assert listed.status_code == 200, listed.text
    return [
        (item["name"], item["config"]["target"], item["config"]["path"], item["config"]["label"])
        for item in listed.json()["items"]
    ]


def test_favourites_round_trip(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya_member = member(keyring, clock)
    maya = workspace(app, maya_member, sign_in(app, maya_member.email))
    omar_member = colleague(maya_member.tenant_id, "omar")
    omar = workspace(app, omar_member, sign_in(app, omar_member.email))

    created = send(
        app,
        "POST",
        SAVED_VIEWS,
        maya,
        {
            "screen_code": "SF-01",
            "name": "RPO",
            "is_favourite": True,
            "config": {"target": "report", "path": "/reports/rpo", "label": "RPO"},
        },
    )
    assert created.status_code == 201, created.text
    favourite = created.json()
    assert (favourite["screen_code"], favourite["is_favourite"]) == ("SF-01", True)
    assert favourites(app, maya) == [("RPO", "report", "/reports/rpo", "RPO")]
    assert favourites(app, omar) == []

    unpinned = send(app, "PATCH", f"{SAVED_VIEWS}/{favourite['id']}", maya, {"is_favourite": False})
    assert unpinned.status_code == 200, unpinned.text
    assert unpinned.json()["is_favourite"] is False
    assert favourites(app, maya) == []
    listed = get(app, SAVED_VIEWS, maya, {"screen_code": "SF-01"})
    assert listed.status_code == 200, listed.text
    assert [(item["name"], item["is_favourite"]) for item in listed.json()["items"]] == [
        ("RPO", False)
    ]
