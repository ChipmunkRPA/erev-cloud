"""API-R-32 estimates and estimate versions (04 T-CON-12, T-CON-13, E-12, §16.14 estimates, table
15.4-D; PRD SM-04, §2.5 routing row ``ESTIMATE_VERSION``, WLD-K-03, WLD-K-06, WLD-X-16, ERR-13,
IMP-71, IMP-74; 05 §3.6.8; 03 REQ-TP-004, REQ-TP-005; CTL-013; BUILD_SPEC CTR-12).

World K-06 (PRD §2.6, WLD-K-06, AK:S3-EX24): Maya (Revenue Accountant, SSP Analyst) prepares; Priya
(Revenue Reviewer, SSP Approver; MFA) approves the estimate versions and ``DE-LIST 2026``; Marcus
(Controller, Tenant Admin; MFA) enables EUR and approves the template and the mapping. AVM-DE (EUR,
Europe/Berlin) has FY2026-P01 to P09 open. ``NS-SO-DE-5002`` books O1 AVM-PART, 575 units × 100.00 =
57,500.00 EUR from 2026-07-01. [J] L5-2-Q-8: the framework order books the 575 units shipped in the
framework year, as AK:S3-EX24 books the units of its assumption. Element ``REBATE-DR-01`` (rebate,
most likely amount): version 1 "threshold not expected" (0.00, effective 2026-07-01), approved by
Priya; then 75 units shipped 2026-07-15 with INV-DE-4201 7,500.00 and 500 units shipped 2026-09-20
with INV-DE-4470 50,000.00, computed.

World K-03 (WLD-K-03): AVM-US (USD) of ``support.factories.k02_world``; ``PRJ-CB-2026-01`` O1
AVM-ENG-BUILD 1,000,000.00 from 2026-02-01, booked as a draft, with the progress costs of February
to August 2026 (420,000.00).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from erev_api.approvals.engine import ROLE_REQUIRED_DETAIL
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    approval_step,
    audit_event,
    contract_event,
    estimate,
    estimate_version,
    job,
    role,
)
from erev_api.domain.contracts.commands import BookedContract
from erev_api.enums import ContractEventType
from erev_api.events.payloads import BillingRecordedV1, CostIncurredV1, DeliveryRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from erev_api.money import MoneyIn
from erev_engine.trace import reevaluate
from fastapi import FastAPI
from sqlalchemy import and_, select, text, update
from support.db import TestDatabase
from support.factories import (
    K11_CHART,
    TPL_PROD_UNITS,
    Workspace,
    activated_contract,
    appended,
    approved_ssp_version,
    booked_contract,
    computed,
    customer_id,
    k02_world,
    product_with_template,
    published_mapping,
    published_template,
    range_entry,
    set_default_template,
    ssp_book,
    stamp_test_release,
    workspace,
    world_calendar,
)
from support.http import call
from support.principals import Actor, colleague, cookie_headers, enrolled, member
from support.reference import approve, assign, fields, get, holding, patch, post, put, reject, slug
from support.worlds import (
    BONUS_CB_01,
    estimate_version_ready,
    evidence_file,
    judgement_submitted,
    k03_castellan,
    k03_revenue,
)

CONTRACTS: Final = "/api/v1/contracts"
ESTIMATES: Final = "/api/v1/estimates"
VERSIONS: Final = "/api/v1/estimate-versions"
PART: Final = "AVM-PART"
REBATE: Final = "REBATE-DR-01"
ENGINEERING: Final = "AVM-ENG-BUILD"
# PRD §2.6 accounts of the roles a K-06 computation reaches, with the refund liability of JET-04b.
K06_CHART: Final = (
    *K11_CHART,
    ("2110", "Refund liability", "LIABILITY", "C", "REFUND_LIABILITY"),
)
PART_CASE: Final = {
    "obligation_key": "POB-01",
    "product_code": PART,
    "quantity": "575",
    "total_price": "57500.00",
}
_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
EUR_USD_SPOT: Final = "1.0850"
V1_RATIONALE: Final = "Threshold of 1,000 units not expected in the framework year."
V2_OUTCOME: Final = "Threshold expected: all units re-priced to 90.00"
V2_RATIONALE: Final = "Customer acquired Tessen Werke; forecast 1,450 units in the framework year."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


@dataclass(frozen=True, slots=True)
class K06World:
    place: Workspace
    priya: Actor
    marcus: Actor
    customer_id: UUID

    @property
    def app(self) -> FastAPI:
        return self.place.app


def k06_world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> K06World:
    maya_member = member(keyring, clock)
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers: dict[str, Actor] = {}
    for name, roles in (
        ("priya", ("revenue_reviewer", "ssp_approver")),
        ("marcus", ("controller", "tenant_admin")),
    ):
        someone = colleague(maya_member.tenant_id, name)
        for code in roles:
            assign(someone, code)
        approvers[name] = enrolled(app, clock, someone)
    marcus = approvers["marcus"]
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD", "EUR"]})
    assert enabled.status_code == 200, enabled.text
    _eur_usd_spot(app, maya, marcus)
    world_calendar(
        app, maya, entity_code="AVM-DE", functional_currency="EUR", time_zone="Europe/Berlin"
    )
    buyer = customer_id(app, maya, code="C-06", name="Drossel Fahrzeugtechnik GmbH (Demo)")
    part = product_with_template(
        app, maya, code=PART, name="Drive part, per unit", revenue_category="PRODUCT"
    )
    units = published_template(
        app, maya, marcus, code="TPL-PROD-UNITS", outputs=TPL_PROD_UNITS, case_line=PART_CASE
    )
    set_default_template(app, maya, part, units["template_id"])
    book_id = ssp_book(app, maya, code="DE-LIST", currency="EUR")
    approved_ssp_version(
        app,
        maya,
        [approvers["priya"]],
        book_id,
        label="2026",
        effective_from="2026-01-01",
        entries=[range_entry(PART, "90.00", "100.00", "110.00", currency="EUR")],
    )
    published_mapping(app, maya, marcus, chart=K06_CHART)
    stamp_test_release()
    return K06World(
        place=workspace(app, clock, keyring, files, maya),
        priya=approvers["priya"],
        marcus=marcus,
        customer_id=buyer,
    )


def _eur_usd_spot(app: FastAPI, author: Actor, approver: Actor) -> None:
    """The PRD §2.5 threshold of an estimate version is in USD (row ``ESTIMATE_VERSION``; J-07.3
    "One approval step (impact below USD 50,000.00)"), so a EUR version is measured at the EUR to
    USD ``spot`` rate on its effective date — and takes the Controller's second step when no rate
    is in force (04 T-PLT-17 ``flags`` ``PL_IMPACT_GE_50K``, rev 1.104; supervisor ruling R-41
    (7)). One rate from 2026-01-01 makes every version of this world measurable."""
    rate_set = post(
        app,
        "/api/v1/fx-rate-sets",
        author,
        {"code": "AVM-RATES-SPOT", "name": "AVM-RATES spot", "rate_type": "spot"},
    )
    assert rate_set.status_code == 201, rate_set.text
    draft = post(
        app,
        f"/api/v1/fx-rate-sets/{rate_set.json()['id']}/versions",
        author,
        {
            "coverage_from": "2026-01-01",
            "coverage_to": "2026-12-31",
            "rates": [
                {
                    "base_currency": "EUR",
                    "quote_currency": "USD",
                    "rate": EUR_USD_SPOT,
                    "effective_date": "2026-01-01",
                }
            ],
        },
    )
    assert draft.status_code == 201, draft.text
    submitted = post(
        app,
        f"/api/v1/fx-rate-set-versions/{draft.json()['id']}/submit",
        author,
        {"comment": "EUR to USD spot rate"},
        if_match=f'"r{draft.json()["row_version"]}"',
    )
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, submitted.json()["pending_approval_request_id"], approver)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text


def k06_body(customer: UUID) -> dict[str, Any]:
    return {
        "external_id": "NS-SO-DE-5002",
        "customer_id": str(customer),
        "contracting_entity_code": "AVM-DE",
        "transaction_currency": "EUR",
        "inception_date": "2026-07-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": PART,
                "quantity": "575",
                "total_price": {"amount": "57500.00", "currency": "EUR"},
            }
        ],
    }


def _rebate_version(
    effective_date: str, amount: str, outcome: str, rationale: str, **extra: Any
) -> dict[str, Any]:
    return {
        "effective_date": effective_date,
        "scenarios": [{"outcome": outcome, "amount": amount}],
        "unconstrained_amount": amount,
        "most_conservative_amount": amount,
        "constrained_amount": amount,
        "rationale": rationale,
        **extra,
    }


def _v2_body(**extra: Any) -> dict[str, Any]:
    """K-06 version 2 (J-07.2): threshold expected, effective 2026-09-30, refund target 5,750.00."""
    return _rebate_version(
        "2026-09-30",
        "5750.00",
        V2_OUTCOME,
        V2_RATIONALE,
        parameters={"refund_liability_target": "5750.00"},
        **extra,
    )


def _ready(world: K06World, version_id: str) -> None:
    """What the submission asks of a version beyond its values (04 §16.14 rev 1.241; items
    EST-EVIDENCE-AT-SUBMIT-1 and the constraint's judgement record), given by Maya: its evidence
    and, for a variable-consideration version that names no record yet, the ``CONSTRAINT``
    record of its element, which Priya reviews (``worlds.estimate_version_ready``)."""
    (found,) = world.place.rows(
        select(
            estimate.c.estimate_kind,
            estimate.c.element_code,
            estimate_version.c.judgement_record_id,
        )
        .select_from(
            estimate_version.join(
                estimate,
                and_(
                    estimate.c.tenant_id == estimate_version.c.tenant_id,
                    estimate.c.id == estimate_version.c.estimate_id,
                ),
            )
        )
        .where(estimate_version.c.id == UUID(version_id))
    )
    kind = str(getattr(found["estimate_kind"], "value", found["estimate_kind"]))
    owes_record = kind == "VARIABLE_CONSIDERATION" and found["judgement_record_id"] is None
    estimate_version_ready(
        world.app,
        world.place.author,
        version_id,
        constraint_of=str(found["element_code"]) if owes_record else None,
        reviewer=world.priya,
    )


def _submitted(
    world: K06World, version_id: str, actor: Actor | None = None, *, ready: bool = True
) -> str:
    """Submit a version as ``actor`` (Maya by default); the request id. Unless ``ready`` is
    false the version is first given what the submission asks (``_ready``)."""
    if ready:
        _ready(world, version_id)
    sent = post(
        world.app, f"{VERSIONS}/{version_id}/submit", actor or world.place.author, {"comment": "OK"}
    )
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert (body["status"], body["approval_request_id"] is not None) == ("SUBMITTED", True), body
    return str(body["approval_request_id"])


@dataclass(frozen=True, slots=True)
class K06Contract:
    booked: BookedContract
    estimate_id: str
    v1_id: str

    @property
    def contract_id(self) -> UUID:
        return UUID(str(self.booked.contract["id"]))

    @property
    def group_id(self) -> UUID:
        return UUID(str(self.booked.combination_group["id"]))


def _k06_with_v1(world: K06World, *, approved: bool = True, shipped: bool = True) -> K06Contract:
    """K-06 activated, ``REBATE-DR-01`` version 1 submitted (and approved by Priya), then the two
    shipments and invoices recorded and computed."""
    maya = world.place.author
    booked = booked_contract(world.place, k06_body(world.customer_id), activate=False)
    booked = activated_contract(world.place, booked, compute=False)
    contract_id = booked.contract["id"]
    element = post(
        world.app,
        f"{CONTRACTS}/{contract_id}/estimates",
        maya,
        {
            "estimate_kind": "VARIABLE_CONSIDERATION",
            "element_code": REBATE,
            "vc_element_type": "REBATE",
            "method": "MOST_LIKELY_AMOUNT",
        },
    )
    assert element.status_code == 201, element.text
    created = element.json()
    assert (created["direction"], created["allocation_target"], created["latest_version"]) == (
        "DECREASE",
        "CONTRACT",
        None,
    )
    assert element.headers["Location"] == f"{ESTIMATES}/{created['id']}/versions"
    v1 = post(
        world.app,
        f"{ESTIMATES}/{created['id']}/versions",
        maya,
        _rebate_version("2026-07-01", "0.00", "Threshold not expected", V1_RATIONALE),
    )
    assert v1.status_code == 201, v1.text
    assert (v1.json()["version_no"], v1.json()["status"]) == (1, "DRAFT")
    request_id = _submitted(world, v1.json()["id"])
    if approved:
        decided = approve(world.app, request_id, world.priya)
        assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    if shipped:
        head = 3 if approved else 2
        appended(world.place, contract_id, head, _shipments())
        computed(world.place, booked.combination_group["id"])
    return K06Contract(booked=booked, estimate_id=str(created["id"]), v1_id=str(v1.json()["id"]))


def _shipments() -> list[EventIn]:
    events = []
    for units, amount, invoice, day in (
        ("75", "7500.00", "INV-DE-4201", date(2026, 7, 15)),
        ("500", "50000.00", "INV-DE-4470", date(2026, 9, 20)),
    ):
        events.append(
            EventIn(
                event_type=ContractEventType.DELIVERY_RECORDED,
                effective_date=day,
                payload=DeliveryRecordedV1(obligation_key="O1", quantity=units, trigger="DELIVERY"),
            )
        )
        events.append(
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=day,
                payload=BillingRecordedV1(
                    invoice_number=invoice,
                    line_external_id=f"{invoice}-1",
                    obligation_key="O1",
                    amount=MoneyIn(amount=amount, currency="EUR"),
                    issue_date=day,
                ),
            )
        )
    return events


def _estimate_events(world: K06World, contract_id: UUID) -> list[dict[str, Any]]:
    return world.place.rows(
        select(contract_event)
        .where(
            contract_event.c.contract_id == contract_id,
            contract_event.c.event_type == ContractEventType.ESTIMATE_CHANGED.value,
        )
        .order_by(contract_event.c.stream_version)
    )


def _work(place: Workspace, job_id: UUID, runtime: JobRuntime) -> None:
    """The worker fetches the job's task and runs it."""
    context = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    run_job(job_id, place.tenant_id, attempt=1, runtime=runtime)


def _period(summary: dict[str, Any], period_key: str) -> tuple[str, str]:
    (row,) = [item for item in summary["revenue_by_period"] if item["period_key"] == period_key]
    return row["before"]["amount"], row["after"]["amount"]


def _balance(rows: list[dict[str, Any]], name: str) -> str | None:
    found = [item["amount"]["amount"] for item in rows if item["balance"] == name]
    return found[0] if found else None


def test_version_immutable_after_submission(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k06_world(app, keyring, clock, files)
    k06 = _k06_with_v1(world, approved=False, shipped=False)
    path = f"{VERSIONS}/{k06.v1_id}"
    refused = patch(
        app, path, world.place.author, {"rationale": "Changed after submission."}, if_match=None
    )
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert fields(refused) == [("status", "DB-03")]
    shown = get(app, path, world.place.author).json()
    assert (shown["status"], shown["rationale"]) == ("SUBMITTED", V1_RATIONALE)


def test_method_locked_after_first_approved(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k06_world(app, keyring, clock, files)
    k06 = _k06_with_v1(world, shipped=False)
    refused = post(
        app,
        f"{ESTIMATES}/{k06.estimate_id}/versions",
        world.place.author,
        _v2_body(method="EXPECTED_VALUE"),
    )
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("method", "ESTIMATE_METHOD_LOCKED")]
    assert refused.json()["errors"][0]["message"] == (
        "The estimation method is fixed after the first version (POL-040). Use Most likely amount."
    )
    versions = world.place.rows(
        select(estimate_version.c.version_no).where(
            estimate_version.c.estimate_id == UUID(k06.estimate_id)
        )
    )
    assert [row["version_no"] for row in versions] == [1]


def test_constraint_range_check(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k06_world(app, keyring, clock, files)
    k06 = _k06_with_v1(world, shipped=False)
    body = {
        **_v2_body(),
        "unconstrained_amount": "5750.00",
        "most_conservative_amount": "0.00",
        "constrained_amount": "6000.00",
    }
    refused = post(app, f"{ESTIMATES}/{k06.estimate_id}/versions", world.place.author, body)
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("constrained_amount", "ESTIMATE_CONSTRAINT_RANGE")]
    assert refused.json()["errors"][0]["message"] == (
        "The constrained estimate (6,000.00) is outside the allowed range 0.00 – 5,750.00."
    )


def test_approval_appends_estimate_changed_k06(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    runtime: JobRuntime,
) -> None:
    world = k06_world(app, keyring, clock, files)
    maya = world.place.author
    k06 = _k06_with_v1(world)
    (v1_event,) = _estimate_events(world, k06.contract_id)
    assert v1_event["payload"] == {
        "estimate_version_id": k06.v1_id,
        "previous_estimate_version_id": None,
    }

    v2 = post(app, f"{ESTIMATES}/{k06.estimate_id}/versions", maya, _v2_body())
    assert v2.status_code == 201, v2.text
    v2_id = str(v2.json()["id"])
    assert (v2.json()["version_no"], v2.json()["supersedes_version_id"]) == (2, k06.v1_id)
    preview = post(app, f"{VERSIONS}/{v2_id}/preview", maya, {})
    assert preview.status_code == 202, preview.text
    queued = preview.json()
    assert (queued["kind"], queued["state"]) == ("CONTRACT_COMPUTE", "QUEUED")
    assert preview.headers["Location"] == f"/api/v1/jobs/{queued['id']}"
    _work(world.place, UUID(queued["id"]), runtime)
    finished = get(app, f"/api/v1/jobs/{queued['id']}", maya).json()
    assert finished["state"] == "SUCCEEDED", finished
    summary = finished["result"]["summary"]
    # PRD WLD-X-16, J-07.2: Sep 2026 revenue 50,000.00 → 44,250.00; refund liability 5,750.00.
    assert _period(summary, "FY2026-P09") == ("50000.00", "44250.00")
    assert (
        summary["transaction_price_before"]["amount"],
        summary["transaction_price_after"]["amount"],
    ) == ("57500.00", "51750.00")
    assert _balance(summary["balances_after"], "refund_liability") == "5750.00"
    assert _balance(summary["balances_before"], "refund_liability") == "0.00"
    assert _balance(summary["balances_after"], "contract_liability") == "0.00"
    assert len(_estimate_events(world, k06.contract_id)) == 1

    request_id = _submitted(world, v2_id)
    # 04 §16.10 rev 1.126: the request's summary states the catch-up total its stored preview
    # carries; an estimate version moves no criteria-met book.
    stated = get(app, f"/api/v1/approvals/{request_id}", world.priya).json()
    assert stated["impact_preview"]["summary"]["catch_up_total"] == summary["catch_up_total"]
    assert stated["impact_preview"]["summary"]["criteria_met"] is None
    decided = approve(app, request_id, world.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    v1_event, v2_event = _estimate_events(world, k06.contract_id)
    assert v2_event["payload"] == {
        "estimate_version_id": v2_id,
        "previous_estimate_version_id": k06.v1_id,
    }
    assert (
        v2_event["origin"],
        v2_event["effective_date"],
        v2_event["estimate_version_id"],
        v2_event["approval_request_id"],
    ) == ("SYSTEM", date(2026, 9, 30), UUID(v2_id), UUID(request_id))
    shown = get(app, f"{VERSIONS}/{v2_id}", maya).json()
    assert (shown["status"], shown["applied_event_ids"], shown["approver"]["id"]) == (
        "APPROVED",
        [str(v2_event["id"])],
        str(world.priya.member.user_id),
    )
    assert shown["approved_at"] == "2026-09-12T12:00:00Z"
    assert get(app, f"{VERSIONS}/{k06.v1_id}", maya).json()["status"] == "SUPERSEDED"


def test_eac_below_costs_incurred_rejected(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k02_world(app, keyring, clock, files)
    maya = world.place.author
    contract_id, estimate_id = _k03_eac(world.place, world.customer_id)
    refused = post(
        app,
        f"{ESTIMATES}/{estimate_id}/versions",
        maya,
        {
            "effective_date": "2026-08-31",
            "expected_total_amount": "400000.00",
            "rationale": "Remaining costs re-estimated after the August site review.",
        },
    )
    assert (refused.status_code, slug(refused)) == (422, "eac-below-costs-incurred"), refused.text
    assert refused.json()["detail"] == (
        "Estimated total costs (400,000.00) cannot be lower than costs incurred to date "
        "(420,000.00)."
    )
    assert fields(refused) == [("expected_total_amount", "ERR-13")]
    assert world.place.rows(select(estimate_version.c.id)) == []
    assert contract_id is not None


def _k03_eac(place: Workspace, customer: UUID) -> tuple[UUID, str]:
    """K-03 booked as a draft with the February to August progress costs and element ``EAC``
    (cost build-up); (contract id, element id)."""
    app = place.app
    maya = place.author
    product_with_template(
        app, maya, code=ENGINEERING, name="Engineering and build", revenue_category="SERVICES"
    )
    booked = booked_contract(
        place,
        {
            "external_id": "PRJ-CB-2026-01",
            "customer_id": str(customer),
            "contracting_entity_code": "AVM-US",
            "transaction_currency": "USD",
            "inception_date": "2026-02-01",
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": ENGINEERING,
                    "quantity": "1",
                    "total_price": {"amount": "1000000.00", "currency": "USD"},
                    "start_date": "2026-02-01",
                    "end_date": "2027-07-31",
                }
            ],
        },
        activate=False,
    )
    contract_id = UUID(str(booked.contract["id"]))
    costs = []
    for day, amount in (
        (date(2026, 2, 28), "30000.00"),
        (date(2026, 3, 31), "50000.00"),
        (date(2026, 4, 30), "60000.00"),
        (date(2026, 5, 31), "70000.00"),
        (date(2026, 6, 30), "70000.00"),
        (date(2026, 7, 31), "70000.00"),
        (date(2026, 8, 31), "70000.00"),
    ):
        costs.append(
            EventIn(
                event_type=ContractEventType.COST_INCURRED,
                effective_date=day,
                payload=CostIncurredV1(
                    purpose="PROGRESS_INPUT",
                    obligation_key="O1",
                    amount=MoneyIn(amount=amount, currency="USD"),
                ),
            )
        )
    appended(place, contract_id, 1, costs)
    element = post(
        app,
        f"{CONTRACTS}/{contract_id}/estimates",
        maya,
        {"estimate_kind": "EAC", "element_code": "EAC", "method": "COST_BUILDUP"},
    )
    assert element.status_code == 201, element.text
    assert element.json()["direction"] == "INCREASE"
    return contract_id, str(element.json()["id"])


def test_list_version_summaries(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k06_world(app, keyring, clock, files)
    maya = world.place.author
    k06 = _k06_with_v1(world, shipped=False)
    v2 = post(app, f"{ESTIMATES}/{k06.estimate_id}/versions", maya, _v2_body())
    assert v2.status_code == 201, v2.text
    listed = get(app, f"{CONTRACTS}/{k06.contract_id}/estimates", maya)
    assert listed.status_code == 200, listed.text
    (item,) = listed.json()["items"]
    current, latest = item["current_version"], item["latest_version"]
    assert (current["id"], current["version_no"], current["status"]) == (k06.v1_id, 1, "APPROVED")
    assert (current["effective_date"], current["approved_at"]) == (
        "2026-07-01",
        "2026-09-12T12:00:00Z",
    )
    assert current["approver"]["id"] == str(world.priya.member.user_id)
    assert (latest["id"], latest["version_no"], latest["status"]) == (v2.json()["id"], 2, "DRAFT")
    assert (latest["approver"], latest["approved_at"]) == (None, None)
    filtered = get(
        app, f"{CONTRACTS}/{k06.contract_id}/estimates", maya, {"status": "APPROVED"}
    ).json()
    assert filtered["items"] == []
    versions = get(app, f"{ESTIMATES}/{k06.estimate_id}/versions", maya, {"sort": "version_no"})
    assert [row["version_no"] for row in versions.json()["items"]] == [1, 2]
    assert versions.json()["items"][1]["excluded_amount"] == {"amount": "0.00", "currency": "EUR"}
    assert versions.json()["items"][1]["costs_incurred_to_date"] is None

    k02 = k02_world(app, keyring, clock, files)
    _, eac_id = _k03_eac(k02.place, k02.customer_id)
    eac = post(
        app,
        f"{ESTIMATES}/{eac_id}/versions",
        k02.place.author,
        {
            "effective_date": "2026-08-31",
            "expected_total_amount": "700000.00",
            "rationale": "Estimate at completion from the project plan.",
        },
    )
    assert eac.status_code == 201, eac.text
    shown = eac.json()
    assert (shown["costs_incurred_to_date"], shown["progress_ratio"], shown["excluded_amount"]) == (
        {"amount": "420000.00", "currency": "USD"},
        "0.6",
        None,
    )


@pytest.mark.control("CTL-013")
@pytest.mark.parametrize("different_submitter", [False, True])
def test_ctl_013_estimate_preparer_cannot_approve(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    different_submitter: bool,
) -> None:
    world = k06_world(app, keyring, clock, files)
    k06 = _k06_with_v1(world)
    rosa_member = colleague(world.place.tenant_id, "rosa")
    assign(rosa_member, "revenue_accountant")
    assign(rosa_member, "revenue_reviewer")
    rosa = enrolled(app, clock, rosa_member)
    v2 = post(app, f"{ESTIMATES}/{k06.estimate_id}/versions", rosa, _v2_body())
    assert v2.status_code == 201, v2.text
    request_id = _submitted(
        world, str(v2.json()["id"]), world.place.author if different_submitter else rosa
    )

    refused = approve(app, request_id, rosa)
    assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text
    assert get(app, f"{VERSIONS}/{v2.json()['id']}", rosa).json()["status"] == "SUBMITTED"
    assert len(_estimate_events(world, k06.contract_id)) == 1


def _routed(world: K06World, request_id: str) -> tuple[list[str], tuple[Decimal, str], list[Any]]:
    """The request's flags, its amount and its steps as (number, permission, role id, status)."""
    (request,) = world.place.rows(
        select(
            approval_request.c.flags,
            approval_request.c.amount_functional,
            approval_request.c.amount_currency,
            approval_request.c.routing_rule_id,
        ).where(approval_request.c.id == UUID(request_id))
    )
    assert request["routing_rule_id"] is None  # no routing rule: the subject's own steps
    steps = world.place.rows(
        select(
            approval_step.c.step_no,
            approval_step.c.required_permission,
            approval_step.c.required_role_id,
            approval_step.c.status,
        )
        .where(approval_step.c.approval_request_id == UUID(request_id))
        .order_by(approval_step.c.step_no)
    )
    return (
        list(request["flags"]),
        (Decimal(request["amount_functional"]), str(request["amount_currency"]).strip()),
        [tuple(str(v) if i == 3 else v for i, v in enumerate(step.values())) for step in steps],
    )


def test_r41_controller_second_step_from_usd_50k_of_pl_impact(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Supervisor ruling R-41 (7); PRD §2.5 ``ESTIMATE_VERSION`` "If absolute P&L impact ≥ USD
    50,000.00: 2: Controller"; 04 T-PLT-17 ``flags`` ``PL_IMPACT_GE_50K`` (rev 1.104). The P&L
    impact of a version is the catch-up of its submission's dry run. K-06 is a EUR contract of a
    EUR entity, EUR to USD spot 1.0850. Version 2 of J-07.2 re-prices 5,750.00 EUR — USD 6,238.75
    — and takes one step (J-07.3). A re-pricing of 47,000.00 EUR is below 50,000 in its own
    currency and USD 50,995.00 at the spot rate: the request carries the flag and a second step
    that only a Controller decides. The world publishes no routing rule, so these are the
    subject's own steps; before the ruling the second step stood only in the sample world's
    rules, and a Revenue Reviewer alone approved any estimate version here. Priya decides step 1;
    a second Revenue Reviewer is refused step 2 by the role; Marcus, a Controller, decides it and
    the version applies."""
    world = k06_world(app, keyring, clock, files)
    maya = world.place.author
    k06 = _k06_with_v1(world)
    (controller,) = world.place.rows(select(role.c.id).where(role.c.code == "controller"))

    small = post(app, f"{ESTIMATES}/{k06.estimate_id}/versions", maya, _v2_body())
    assert small.status_code == 201, small.text
    small_request = _submitted(world, str(small.json()["id"]))
    assert _routed(world, small_request) == (
        [],
        (Decimal("5750.00"), "EUR"),
        [(1, "estimate.approve", None, "ACTIVE")],
    )
    withdrawn = post(app, f"{VERSIONS}/{small.json()['id']}/withdraw", maya, {})
    assert withdrawn.status_code == 200, withdrawn.text

    deep = post(
        app,
        f"{ESTIMATES}/{k06.estimate_id}/versions",
        maya,
        _rebate_version(
            "2026-09-30",
            "47000.00",
            "Threshold expected: all units re-priced under the framework floor",
            "Customer acquired Tessen Werke and renegotiated the framework price.",
            parameters={"refund_liability_target": "47000.00"},
        ),
    )
    assert deep.status_code == 201, deep.text
    deep_id = str(deep.json()["id"])
    request_id = _submitted(world, deep_id)
    assert _routed(world, request_id) == (
        ["PL_IMPACT_GE_50K"],
        (Decimal("47000.00"), "EUR"),
        [
            (1, "estimate.approve", None, "ACTIVE"),
            (2, "estimate.approve", controller["id"], "WAITING"),
        ],
    )

    first = approve(app, request_id, world.priya)
    assert (first.status_code, first.json()["status"]) == (200, "PENDING"), first.text
    assert get(app, f"{VERSIONS}/{deep_id}", maya).json()["status"] == "SUBMITTED"
    assert len(_estimate_events(world, k06.contract_id)) == 1  # nothing applied yet
    rosa_member = colleague(world.place.tenant_id, "rosa")
    assign(rosa_member, "revenue_reviewer")
    rosa = enrolled(app, clock, rosa_member)
    refused = approve(app, request_id, rosa)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == ROLE_REQUIRED_DETAIL.format(role="Controller")

    second = approve(app, request_id, world.marcus)
    assert (second.status_code, second.json()["status"]) == (200, "APPROVED"), second.text
    assert get(app, f"{VERSIONS}/{deep_id}", maya).json()["status"] == "APPROVED"
    _, applied = _estimate_events(world, k06.contract_id)
    assert (applied["estimate_version_id"], applied["approval_request_id"]) == (
        UUID(deep_id),
        UUID(request_id),
    )


# --- ENC-VC-direction: the T-CON-12 direction through API, bundle, engine and journals -----------

K06_CONTRACT: Final = "NS-SO-DE-5002"


def _element(
    world: K06World, contract_id: UUID, code: str, vc_type: str, direction: str | None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "estimate_kind": "VARIABLE_CONSIDERATION",
        "element_code": code,
        "vc_element_type": vc_type,
        "method": "MOST_LIKELY_AMOUNT",
    }
    if direction is not None:
        body["direction"] = direction
    created = post(world.app, f"{CONTRACTS}/{contract_id}/estimates", world.place.author, body)
    assert created.status_code == 201, created.text
    return dict(created.json())


def _approved_v1(
    world: K06World, estimate_id: str, amount: str, rationale: str, **extra: Any
) -> str:
    v1 = post(
        world.app,
        f"{ESTIMATES}/{estimate_id}/versions",
        world.place.author,
        _rebate_version("2026-07-01", amount, f"most likely {amount}", rationale, **extra),
    )
    assert v1.status_code == 201, v1.text
    decided = approve(world.app, _submitted(world, v1.json()["id"]), world.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    return str(v1.json()["id"])


def test_enc_vc_direction_round_trip_api_bundle_engine_journals(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """K-06 with three more approved elements beside ``REBATE-DR-01`` v1 (0.00): a VOLUME_TIER
    overage with explicit INCREASE (1,000.00), a VOLUME_TIER without a direction (the B3-DG-17
    default DECREASE, 1,000.00) and a BONUS with explicit DECREASE (500.00; the case the L5
    ``_vc_sign`` workaround signed). The API persists each direction, the production bundle
    carries it with magnitude amounts, stage 04 signs the price (57,500.00 + 1,000.00 − 1,000.00 −
    500.00 = 57,000.00), stage 10 creates a refund component only for the reducing VOLUME_TIER
    element (billed 57,500.00 − revenue 57,000.00 = 500.00, capped by K 1,000.00), and the trace
    re-evaluates exactly (DG-ENG-04). Two more REBATE elements at 0.00 carry explicit targets
    (ENC-VC-direction ruling, VC-R03/R04/R13): INCREASE with ``"0.00"`` (a zero component, not an
    absent target) and DECREASE with ``"25.01"`` (2,501 minor units), both surviving API
    normalisation into the bundle's version parameters."""
    world = k06_world(app, keyring, clock, files)
    k06 = _k06_with_v1(world, shipped=False)
    contract_id = k06.contract_id
    increase = _element(world, contract_id, "OVG-INC", "VOLUME_TIER", "INCREASE")
    default = _element(world, contract_id, "OVG-DEF", "VOLUME_TIER", None)
    bonus = _element(world, contract_id, "BONUS-DEC", "BONUS", "DECREASE")
    target_inc = _element(world, contract_id, "TGT-INC", "REBATE", "INCREASE")
    target_dec = _element(world, contract_id, "TGT-DEC", "REBATE", "DECREASE")
    assert (increase["direction"], default["direction"], bonus["direction"]) == (
        "INCREASE",
        "DECREASE",
        "DECREASE",
    )
    listed = get(app, f"{CONTRACTS}/{contract_id}/estimates", world.place.author).json()
    stored = {item["id"]: item["direction"] for item in listed["items"]}
    for created in (increase, default, bonus, target_inc, target_dec):
        assert stored[created["id"]] == created["direction"]  # persisted on T-CON-12
    _approved_v1(world, increase["id"], "1000.00", "Annual tier overage expected (positive).")
    _approved_v1(world, default["id"], "1000.00", "Volume tier credit expected (reducing).")
    _approved_v1(world, bonus["id"], "500.00", "Bonus clawback expected (reducing bonus).")
    _approved_v1(
        world,
        target_inc["id"],
        "0.00",
        "Rebate element with an explicit zero refund target.",
        parameters={"refund_liability_target": "0.00"},
    )
    _approved_v1(
        world,
        target_dec["id"],
        "0.00",
        "Rebate element with an explicit 25.01 refund target.",
        parameters={"refund_liability_target": "25.01"},
    )
    appended(world.place, contract_id, 8, _shipments())  # booked, activated, six approvals
    bundle, output, _ = computed(world.place, k06.group_id)

    # The price first: on 9467de0 the INCREASE overage was measured as a decrease (55,000.00).
    (book,) = [item for item in output.books if item.book_code == "ASC606"]
    assert book.contract_version is not None
    assert book.contract_version.columns["transaction_price"] == 5_700_000

    by_code = {item.element_code: item for item in bundle.estimate_versions}
    assert {code: item.direction for code, item in by_code.items()} == {
        REBATE: "DECREASE",
        "OVG-INC": "INCREASE",
        "OVG-DEF": "DECREASE",
        "BONUS-DEC": "DECREASE",
        "TGT-INC": "INCREASE",
        "TGT-DEC": "DECREASE",
    }
    assert {code: item.constrained_amount for code, item in by_code.items()} == {
        REBATE: Decimal("0.00"),
        "OVG-INC": Decimal("1000.00"),
        "OVG-DEF": Decimal("1000.00"),
        "BONUS-DEC": Decimal("500.00"),
        "TGT-INC": Decimal("0.00"),
        "TGT-DEC": Decimal("0.00"),
    }  # magnitudes (B3-D16); the sign is the engine's
    targets = {
        code: item.parameters.get("refund_liability_target") for code, item in by_code.items()
    }
    assert targets[REBATE] is None and targets["OVG-INC"] is None  # absent stays absent
    assert Decimal(str(targets["TGT-INC"])) == 0 and targets["TGT-INC"] is not None
    assert Decimal(str(targets["TGT-DEC"])) == Decimal("25.01")
    assert output.input_sha256 == bundle.sha256()
    # CV-25 hash view: default-equal directions do not enter the hash, so the bundle hashes as it
    # did before the member existed; the non-default ones (OVG-INC, BONUS-DEC, TGT-INC) do.
    stripped = dataclasses.replace(
        bundle,
        estimate_versions=tuple(
            dataclasses.replace(item, direction=None) for item in bundle.estimate_versions
        ),
    )
    assert stripped.sha256() != bundle.sha256()
    kept = dataclasses.replace(
        bundle,
        estimate_versions=tuple(
            dataclasses.replace(item, direction=None)
            if item.element_code in (REBATE, "OVG-DEF", "TGT-DEC")
            else item
            for item in bundle.estimate_versions
        ),
    )
    assert kept.sha256() == bundle.sha256()

    nodes = {node.id: node for node in book.trace.nodes}
    assert {
        code: (
            nodes[f"vc_constrained:{K06_CONTRACT}/{code}:-"].value,
            nodes[f"vc_constrained:{K06_CONTRACT}/{code}:-"].params["direction"],
        )
        for code in ("OVG-INC", "OVG-DEF", "BONUS-DEC")
    } == {
        "OVG-INC": ("1000.00", "INCREASE"),
        "OVG-DEF": ("-1000.00", "DECREASE"),
        "BONUS-DEC": ("-500.00", "DECREASE"),
    }
    # Every ``refund_liability`` node is EITHER a VC component (one refund-settled candidate's
    # component under ``/VARIABLE_CONSIDERATION/``) OR the exact member total of a period (the stage
    # 10 member sum ``bal.member_sum.v1``, role ``member_sum``, citing that period's components;
    # DG-KRN-EXP-01, D-97 (8)); any other kind is unexpected (Codex T1F chain triage 917f7bd).
    refund_all = [node for node in book.trace.nodes if node.id.startswith("refund_liability:")]
    refund_nodes = {
        node.id: node.value for node in refund_all if "/VARIABLE_CONSIDERATION/" in node.id
    }
    totals = [node for node in refund_all if node.params.get("role") == "member_sum"]
    assert refund_nodes and totals
    assert len(refund_nodes) + len(totals) == len(refund_all)  # no unexpected kind
    assert all("/VARIABLE_CONSIDERATION/" not in node.id for node in totals)
    # Components exist for the reducing derived candidates (REBATE-DR-01 at K 0.00 and OVG-DEF)
    # and for the explicit targets (TGT-INC 0.00, TGT-DEC 25.01); the INCREASE overage and the
    # DECREASE bonus (no target, not a refund-settled type) create none.
    assert not [
        node_id for node_id in refund_nodes if "OVG-INC" in node_id or "BONUS-DEC" in node_id
    ]
    components_p09 = {
        node_id: value for node_id, value in refund_nodes.items() if node_id.endswith(":FY2026-P09")
    }
    assert len(components_p09) == 4
    assert {
        node_id.rsplit(":", 1)[0].rsplit("/", 1)[1]: value
        for node_id, value in components_p09.items()
    } == {"OVG-DEF": "500.00", REBATE: "0.00", "TGT-INC": "0.00", "TGT-DEC": "25.01"}
    (balance,) = [
        item
        for item in book.balances
        if item.subject_key.startswith(f"{K06_CONTRACT}@") and item.period_key == "FY2026-P09"
    ]
    assert balance.columns["refund_liability_txn"] == 52_501
    # The member total of FY2026-P09 is the exact sum of the four components, citing exactly their
    # sorted ids, with the member-sum role, formula and period; the balance column links it.
    (total_p09,) = [
        node for node in totals if node.id == f"refund_liability:{balance.subject_key}:FY2026-P09"
    ]
    assert total_p09.value == "525.01"
    assert total_p09.formula_id == "bal.member_sum.v1"
    assert (total_p09.params["role"], total_p09.params["as_of"]) == ("member_sum", "FY2026-P09")
    assert list(total_p09.inputs) == sorted(components_p09)
    assert balance.trace_nodes["refund_liability"] == total_p09.id  # the ``_txn`` column's link key
    assert reevaluate(book.trace) == {node.id: node.value for node in book.trace.nodes}


def test_jdg_subject_estimate_1_a_record_of_an_estimate_version_takes_its_contract(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Item JDG-SUBJECT-ESTIMATE-1 (the supervisor's ruling of 2026-10-01; 04 T-CON-19
    ``contract_id`` rev 1.210; a fact of lane F-CTR-WEB's CTR-25). ``POST /judgements`` did not
    look at an ``estimate_version`` subject at all: any uuid passed, and the record named no
    contract — so the engine, which reads judgement records by contract, never saw it, its audit
    events named no contract and its review request no entity. The route now reads the subject:
    the record takes the contract of the version's estimate, a ``contract_id`` that differs is
    refused, and an unknown subject — an estimate version or a migration batch — is 404."""
    world = k06_world(app, keyring, clock, files)
    maya = world.place.author
    k06 = _k06_with_v1(world, approved=False, shipped=False)
    other = booked_contract(
        world.place,
        {**k06_body(world.customer_id), "external_id": "NS-SO-DE-5003"},
        activate=False,
    )

    def record(subject_type: str, subject_id: str, **extra: Any) -> Any:
        return post(
            world.app,
            "/api/v1/judgements",
            maya,
            {
                "topic": "CONSTRAINT",
                "subject_type": subject_type,
                "subject_id": subject_id,
                "conclusion": "The rebate is constrained to zero until the threshold is likely.",
                "rationale": "Volumes to date are below the first tier.",
                "questionnaire": {"estimate_key": REBATE, "remote": False},
                **extra,
            },
        )

    defaulted = record("estimate_version", k06.v1_id)
    assert defaulted.status_code == 201, defaulted.text
    assert defaulted.json()["contract_id"] == str(k06.contract_id)
    [created] = world.place.rows(
        select(audit_event.c.after).where(
            audit_event.c.object_type == "judgement_record",
            audit_event.c.object_id == UUID(str(defaulted.json()["id"])),
            audit_event.c.action == "judgement_record.create",
        )
    )
    assert created["after"]["contract_id"] == str(k06.contract_id)

    same = record("estimate_version", k06.v1_id, contract_id=str(k06.contract_id))
    assert same.status_code == 201, same.text
    assert same.json()["contract_id"] == str(k06.contract_id)

    differing = record("estimate_version", k06.v1_id, contract_id=str(other.contract["id"]))
    assert differing.status_code == 422, differing.text
    assert [
        (error["field"], error["rule_id"], error["message"]) for error in differing.json()["errors"]
    ] == [("contract_id", "T-CON-19", "The contract differs from the subject's contract.")]

    unknown = str(uuid4())
    for subject_type in ("estimate_version", "migration_batch"):
        missing = record(subject_type, unknown)
        assert missing.status_code == 404, (subject_type, missing.text)


def test_step1_hold_release_1_a_record_of_an_estimate_version_places_no_hold(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Supervisor ruling R-23, second order, and its exception (04 T-CON-20 "Judgement holds"
    rev 1.209; item STEP1-HOLD-RELEASE-1). The REQ-POL-010 hold follows the contract a judgement
    record names — but a record whose subject is an estimate version places none: the version
    changes nothing of the contract before its own approval, so no revenue is recognised on the
    unreviewed judgement, and a hold would move the contract's head under the version that waits.
    K-06 active, version 1 waiting for its approval: the record is sent for review and reviewed,
    the contract is never on hold and its head does not move."""
    world = k06_world(app, keyring, clock, files)
    maya = world.place.author
    k06 = _k06_with_v1(world, approved=False, shipped=False)

    def header() -> tuple[str, bool, int]:
        shown = get(world.app, f"{CONTRACTS}/{k06.contract_id}", maya).json()
        return str(shown["status"]), bool(shown["on_hold"]), int(shown["head_stream_version"])

    before = header()
    assert before[:2] == ("ACTIVE", False)
    created = post(
        world.app,
        "/api/v1/judgements",
        maya,
        {
            "topic": "CONSTRAINT",
            "subject_type": "estimate_version",
            "subject_id": k06.v1_id,
            "conclusion": "The rebate is constrained to zero until the threshold is likely.",
            "rationale": "Volumes to date are below the first tier.",
            "questionnaire": {"estimate_key": REBATE, "remote": False},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["contract_id"] == str(k06.contract_id)
    sent = post(world.app, f"/api/v1/judgements/{created.json()['id']}/submit", maya, {})
    assert sent.status_code == 200, sent.text
    assert (sent.json()["status"], sent.json()["approval_request_id"] is not None) == (
        "SUBMITTED",
        True,
    )
    assert header() == before
    reviewed = approve(world.app, sent.json()["approval_request_id"], world.priya)
    assert reviewed.status_code == 200, reviewed.text
    assert header() == before


def test_est_discard_1_a_draft_estimate_version_is_discarded(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Item EST-DISCARD-1 (supervisor ruling R-119 (e); PRD SM-04; 04 E-12 ``VOIDED``, API-R-32
    rev 1.210; SCREENS §8.4 "Discard draft"). PRD SM-04 gave a DRAFT estimate version one exit,
    its submission, and the screen offered a command no route served: a mistaken draft stayed.
    ``POST /estimate-versions/{id}/discard`` moves ANY draft to VOIDED — one that was never
    submitted, and one that was submitted, withdrawn and edited again (the request's history
    stays on the row) — for every holder of ``estimate.create``. A version in another status is
    refused; a discarded version takes no command, keeps its number, and is no longer the
    element's latest version. Nothing reaches the contract."""
    world = k06_world(app, keyring, clock, files)
    maya = world.place.author
    k06 = _k06_with_v1(world, shipped=False)  # version 1 APPROVED
    versions = f"{ESTIMATES}/{k06.estimate_id}/versions"
    events_before = len(_estimate_events(world, k06.contract_id))

    def discard(version_id: str, actor: Actor | None = None) -> Any:
        return post(world.app, f"{VERSIONS}/{version_id}/discard", actor or maya, {})

    def refused(response: Any) -> None:
        assert (response.status_code, slug(response)) == (409, "invalid-transition"), response.text
        assert [
            (error["field"], error["rule_id"], error["message"])
            for error in response.json()["errors"]
        ] == [("status", "DB-03", "Only a draft estimate version can be discarded.")]

    def element() -> dict[str, Any]:
        listed = get(world.app, f"{CONTRACTS}/{k06.contract_id}/estimates", maya)
        assert listed.status_code == 200, listed.text
        (item,) = listed.json()["items"]
        return dict(item)

    refused(discard(k06.v1_id))  # APPROVED

    # --- a draft that was never submitted, discarded by another holder ---
    drafted = post(world.app, versions, maya, _v2_body())
    assert drafted.status_code == 201, drafted.text
    second = str(drafted.json()["id"])
    assert element()["latest_version"]["version_no"] == 2
    someone = colleague(world.place.tenant_id, "nadia")
    assign(someone, "revenue_accountant")
    gone = discard(second, enrolled(world.app, clock, someone))
    assert gone.status_code == 200, gone.text
    found = gone.json()
    assert (found["status"], found["version_no"]) == ("VOIDED", 2)
    assert found["approval_request_id"] is None
    assert world.place.rows(
        select(audit_event.c.before, audit_event.c.after).where(
            audit_event.c.object_type == "estimate_version",
            audit_event.c.object_id == UUID(second),
            audit_event.c.action == "estimate_version.voided",
        )
    ) == [{"before": {"status": "DRAFT"}, "after": {"status": "VOIDED"}}]
    summary = element()
    assert (summary["latest_version"]["version_no"], summary["current_version"]["version_no"]) == (
        1,
        1,
    )
    voided = get(world.app, versions, maya, {"status": "VOIDED"})
    assert [item["id"] for item in voided.json()["items"]] == [second]
    # the elements list filters by the status of the latest version that is not discarded
    elements = f"{CONTRACTS}/{k06.contract_id}/estimates"
    by_status = {
        status: len(get(world.app, elements, maya, {"status": status}).json()["items"])
        for status in ("APPROVED", "VOIDED", "DRAFT")
    }
    assert by_status == {"APPROVED": 1, "VOIDED": 0, "DRAFT": 0}

    # --- a discarded version takes no command ---
    refused(discard(second))
    edited = patch(
        world.app, f"{VERSIONS}/{second}", maya, {"rationale": "Too late."}, if_match=None
    )
    assert (edited.status_code, slug(edited)) == (409, "invalid-transition")
    sent = post(world.app, f"{VERSIONS}/{second}/submit", maya, {"comment": "OK"})
    assert (sent.status_code, slug(sent)) == (409, "invalid-transition")

    # --- submitted, withdrawn, a draft again by an edit: discarded with its request's history ---
    again = post(world.app, versions, maya, _v2_body())
    assert (again.status_code, again.json()["version_no"]) == (201, 3), again.text
    third = str(again.json()["id"])
    request_id = _submitted(world, third)
    refused(discard(third))  # SUBMITTED
    withdrawn = post(world.app, f"{VERSIONS}/{third}/withdraw", maya, {"comment": "Not yet."})
    assert (withdrawn.status_code, withdrawn.json()["status"]) == (200, "WITHDRAWN"), withdrawn.text
    refused(discard(third))  # WITHDRAWN is not a draft until it is edited
    revised = patch(
        world.app,
        f"{VERSIONS}/{third}",
        maya,
        {"rationale": "Revised after the withdrawal."},
        if_match=None,
    )
    assert (revised.status_code, revised.json()["status"]) == (200, "DRAFT"), revised.text
    dropped = discard(third)
    assert dropped.status_code == 200, dropped.text
    assert (dropped.json()["status"], dropped.json()["approval_request_id"]) == (
        "VOIDED",
        request_id,
    )

    # --- the number is not given out again, and nothing reached the contract ---
    next_one = post(world.app, versions, maya, _v2_body())
    assert (next_one.status_code, next_one.json()["version_no"]) == (201, 4), next_one.text
    assert len(_estimate_events(world, k06.contract_id)) == events_before


# 04 T-CON-13 ``constraint_checklist`` (rev 1.210): the five factors of ASC 606-10-32-12.
CHECKLIST: Final = {
    "susceptible_to_outside_factors": True,
    "long_resolution_period": False,
    "limited_experience": False,
    "price_concession_practice": False,
    "broad_range_of_amounts": True,
}


def test_est_constraint_keys_1_a_checklist_holds_the_five_factors_or_nothing(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Item EST-CONSTRAINT-KEYS-1 (supervisor ruling R-120 (e); 04 T-CON-13
    ``constraint_checklist``, §16.14 rev 1.210). The checklist was any JSON object: no document
    named its keys, so the screen and a client could each write their own. It is the five named
    factors of 606-10-32-12, each a boolean — true: present; false: considered and not present
    — or no checklist at all. Another key, a missing key and a value that is not a boolean are
    refused by their path, on create and on PATCH. A version stored before the keys were named
    answers what it stored, is edited without the member and is submitted as it stands."""
    world = k06_world(app, keyring, clock, files)
    maya = world.place.author
    k06 = _k06_with_v1(world, shipped=False)  # version 1 APPROVED, without a checklist
    versions = f"{ESTIMATES}/{k06.estimate_id}/versions"

    def refused(response: Any, *paths: str) -> None:
        assert (response.status_code, slug(response)) == (422, "validation-failed"), response.text
        assert sorted(error["field"] for error in response.json()["errors"]) == sorted(paths)

    made = post(world.app, versions, maya, _v2_body(constraint_checklist=CHECKLIST))
    assert made.status_code == 201, made.text
    second = str(made.json()["id"])
    assert made.json()["constraint_checklist"] == CHECKLIST

    path = "constraint_checklist"
    cases: list[tuple[dict[str, Any], tuple[str, ...]]] = [
        ({**CHECKLIST, "weather": True}, (f"{path}.weather",)),
        (
            {key: value for key, value in CHECKLIST.items() if key != "limited_experience"},
            (f"{path}.limited_experience",),
        ),
        ({**CHECKLIST, "long_resolution_period": "no"}, (f"{path}.long_resolution_period",)),
        ({**CHECKLIST, "broad_range_of_amounts": 1}, (f"{path}.broad_range_of_amounts",)),
        ({}, tuple(f"{path}.{key}" for key in CHECKLIST)),
    ]
    for sent, paths in cases:
        refused(post(world.app, versions, maya, _v2_body(constraint_checklist=sent)), *paths)
        refused(
            patch(
                world.app,
                f"{VERSIONS}/{second}",
                maya,
                {"constraint_checklist": sent},
                if_match=None,
            ),
            *paths,
        )

    # PATCH replaces the checklist whole, and null takes it away
    changed = {**CHECKLIST, "limited_experience": True}
    for sent in (changed, None):
        edited = patch(
            world.app,
            f"{VERSIONS}/{second}",
            maya,
            {"constraint_checklist": sent},
            if_match=None,
        )
        assert (edited.status_code, edited.json()["constraint_checklist"]) == (200, sent)

    # a version written before the keys were named: read as stored, edited beside, submitted
    earlier = {"susceptibility": "high", "notes": ["weather"]}
    with tenant_session(
        DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    ) as session:
        session.execute(
            update(estimate_version)
            .where(estimate_version.c.id == UUID(second))
            .values(constraint_checklist=earlier)
        )
    assert get(world.app, f"{VERSIONS}/{second}", maya).json()["constraint_checklist"] == earlier
    beside = patch(
        world.app,
        f"{VERSIONS}/{second}",
        maya,
        {"rationale": "Edited beside the earlier checklist."},
        if_match=None,
    )
    assert (beside.status_code, beside.json()["constraint_checklist"]) == (200, earlier)
    _ready(world, second)  # its evidence and its CONSTRAINT record (04 §16.14 rev 1.241)
    sent_in = post(world.app, f"{VERSIONS}/{second}/submit", maya, {"comment": "OK"})
    assert (sent_in.status_code, sent_in.json()["status"]) == (200, "SUBMITTED"), sent_in.text
    assert sent_in.json()["constraint_checklist"] == earlier


# --- one open version, the evidence, the constraint's record, the head pin -----------------------
# Items EST-ONE-OPEN-VERSION-1, EST-EVIDENCE-AT-SUBMIT-1, the constraint's judgement record and
# EST-PREVIEW-HEAD-PIN-1 (the supervisor's rulings of 2026-10-01; 04 §16.10 rev 1.233, T-CON-13
# and §16.14 rev 1.241; PRD rev 1.165 SM-04, rev 1.168 ERR-93, ERR-94, IMP-138 to IMP-141).

VERSION_OPEN: Final = (
    "Estimate version {code} v{no} is open. One version of an element is prepared at a time: "
    "approve or discard it first."
)
EVIDENCE_MISSING: Final = "Attach the evidence of this estimate version before it is submitted."
EVIDENCE_WITHDRAWN: Final = (
    "The evidence of this estimate version is no longer attached. Attach it before the version "
    "is approved."
)
ATTESTATION_REASON: Final = (
    "The values equal the approved version: this is an attestation of no change. State its "
    "reason in at least 10 characters."
)
ATTESTATION_VALUES: Final = (
    "The values differ from the approved version: this is not an attestation of no change."
)
CONSTRAINT_RECORD: Final = (
    "Name the CONSTRAINT judgement record of this element: a record of this contract for "
    "{code}, sent for review or reviewed."
)
RECORD_NOT_REVIEWED: Final = (
    "Judgement record {no} of this estimate version is not reviewed. It is reviewed before the "
    "version is approved."
)
NO_EVIDENCE: Final = (None, "ESTIMATE_EVIDENCE_REQUIRED", EVIDENCE_MISSING)
NO_RECORD: Final = (
    "judgement_record_id",
    "ESTIMATE_CONSTRAINT_RECORD",
    CONSTRAINT_RECORD.format(code=REBATE),
)
V1_BODY: Final = ("2026-07-01", "0.00", "Threshold not expected", V1_RATIONALE)


def _k06_rebate(world: K06World) -> tuple[UUID, str]:
    """K-06 booked and activated with the element ``REBATE-DR-01`` and no version yet: (contract
    id, element id)."""
    booked = booked_contract(world.place, k06_body(world.customer_id), activate=False)
    booked = activated_contract(world.place, booked, compute=False)
    contract_id = UUID(str(booked.contract["id"]))
    return contract_id, str(_element(world, contract_id, REBATE, "REBATE", None)["id"])


def _draft(app: FastAPI, author: Actor, element_id: str, body: dict[str, Any]) -> str:
    created = post(app, f"{ESTIMATES}/{element_id}/versions", author, body)
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _version(app: FastAPI, reader: Actor, version_id: str) -> dict[str, Any]:
    shown = get(app, f"{VERSIONS}/{version_id}", reader)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _findings(response: Any) -> list[tuple[Any, str, str]]:
    assert (response.status_code, slug(response)) == (422, "validation-failed"), response.text
    return [(item["field"], item["rule_id"], item["message"]) for item in response.json()["errors"]]


def _lifecycle_refusal(response: Any, message: str) -> None:
    """409 ``invalid-transition`` with one finding under the rule id of SM-04."""
    assert (response.status_code, slug(response)) == (409, "invalid-transition"), response.text
    assert [(item["rule_id"], item["message"]) for item in response.json()["errors"]] == [
        ("SM-04", message)
    ]


def _stale(app: FastAPI, reader: Actor, response: Any, request_id: str) -> None:
    """409 ``stale-approval``: the request is VOIDED ``STALE_SUBJECT`` (04 §16.10)."""
    assert (response.status_code, slug(response)) == (409, "stale-approval"), response.text
    closed = get(app, f"/api/v1/approvals/{request_id}", reader).json()
    assert (closed["status"], closed["void_reason"]) == ("VOIDED", "STALE_SUBJECT"), closed


def _attached(app: FastAPI, author: Actor, version_id: str) -> str:
    """One file ``author`` uploads and attaches to the version; the attachment id."""
    attached = post(
        app,
        "/api/v1/attachments",
        author,
        {
            "file_object_id": evidence_file(app, author),
            "subject_type": "estimate_version",
            "subject_id": version_id,
        },
    )
    assert attached.status_code == 201, attached.text
    return str(attached.json()["id"])


def _record(
    app: FastAPI,
    author: Actor,
    subject: tuple[str, str],
    *,
    topic: str = "CONSTRAINT",
    key: str = REBATE,
    submit: bool = True,
) -> dict[str, Any]:
    """A judgement record ``author`` prepares for ``subject`` (type, id) and, with ``submit``,
    sends for review. It names the element by ``key`` — a ``CONSTRAINT`` record, and a record
    of topic ``OTHER`` as well (04 T-CON-19 lets it name an estimate): the topic alone tells the
    two apart."""
    body: dict[str, Any] = {
        "topic": topic,
        "subject_type": subject[0],
        "subject_id": subject[1],
        "conclusion": "The constraint as this estimate version states it.",
        "rationale": "The factors of ASC 606-10-32-12 were considered.",
        "questionnaire": {"estimate_key": key},
    }
    if topic == "CONSTRAINT":
        body["questionnaire"]["remote"] = False
    if submit:
        return judgement_submitted(app, author, body)
    created = post(app, "/api/v1/judgements", author, body)
    assert created.status_code == 201, created.text
    return dict(created.json())


def _named(app: FastAPI, author: Actor, version_id: str, record_id: str) -> None:
    named = patch(
        app, f"{VERSIONS}/{version_id}", author, {"judgement_record_id": record_id}, if_match=None
    )
    assert named.status_code == 200, named.text


def _impact(place: Workspace, request_id: str) -> Decimal:
    """The request's amount: the absolute P&L impact of the dry run its submission made."""
    (request,) = place.rows(
        select(approval_request.c.amount_functional).where(
            approval_request.c.id == UUID(request_id)
        )
    )
    return Decimal(request["amount_functional"])


def test_est_one_open_version_1_one_version_of_an_element_is_open(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Item EST-ONE-OPEN-VERSION-1 (04 T-CON-13, §16.14 rev 1.241; PRD SM-04, ERR-93). At most
    one version of an element is DRAFT or SUBMITTED. Before, a second version could be prepared
    and sent for approval beside one that was waiting, each on the same predecessor. A second
    one is refused by name where it would become open: at its creation, and at the edit that
    returns a REJECTED or WITHDRAWN version to DRAFT. REJECTED and WITHDRAWN are not open — such
    a version stays as history beside a new one and is revised once no other is open — and
    neither is a discarded draft; a version of another element of the contract is not counted."""
    world = k06_world(app, keyring, clock, files)
    maya = world.place.author
    contract_id, element_id = _k06_rebate(world)
    versions = f"{ESTIMATES}/{element_id}/versions"

    def second(response: Any, open_no: int) -> None:
        _lifecycle_refusal(response, VERSION_OPEN.format(code=REBATE, no=open_no))

    def revise(version_id: str) -> Any:
        return patch(
            world.app, f"{VERSIONS}/{version_id}", maya, {"rationale": "Revised."}, if_match=None
        )

    # --- a draft is open, and so is a version that waits for its approval ---
    v1 = _draft(world.app, maya, element_id, _rebate_version(*V1_BODY))
    second(post(world.app, versions, maya, _v2_body()), 1)
    request_1 = _submitted(world, v1)
    second(post(world.app, versions, maya, _v2_body()), 1)
    assert approve(world.app, request_1, world.priya).status_code == 200

    # --- a rejected version is not open: a new one is prepared beside it ... ---
    v2 = _draft(world.app, maya, element_id, _v2_body())
    assert _version(world.app, maya, v2)["version_no"] == 2
    rejected = reject(world.app, _submitted(world, v2), world.priya, "The forecast is not shown.")
    assert rejected.status_code == 200, rejected.text
    assert _version(world.app, maya, v2)["status"] == "REJECTED"
    v3 = _draft(
        world.app, maya, element_id, {**_v2_body(), "rationale": "Forecast of 30 September."}
    )
    # --- ... and the rejected one does not come back to a draft while that one is open ---
    second(revise(v2), 3)
    assert _version(world.app, maya, v2)["status"] == "REJECTED"

    # --- a withdrawn version likewise; once the open one is gone, the other is revised ---
    _submitted(world, v3)
    second(revise(v2), 3)
    withdrawn = post(world.app, f"{VERSIONS}/{v3}/withdraw", maya, {"comment": "Not yet."})
    assert (withdrawn.status_code, withdrawn.json()["status"]) == (200, "WITHDRAWN"), withdrawn.text
    revised = revise(v2)
    assert (revised.status_code, revised.json()["status"]) == (200, "DRAFT"), revised.text
    second(revise(v3), 2)
    assert _version(world.app, maya, v3)["status"] == "WITHDRAWN"
    second(post(world.app, versions, maya, _v2_body()), 2)

    # --- a version of another element of the same contract is not counted ---
    other = _element(world, contract_id, "REBATE-DR-02", "REBATE", None)
    _draft(world.app, maya, str(other["id"]), _rebate_version(*V1_BODY))

    # --- a discarded draft is not open ---
    discarded = post(world.app, f"{VERSIONS}/{v2}/discard", maya, {})
    assert (discarded.status_code, discarded.json()["status"]) == (200, "VOIDED"), discarded.text
    fourth = post(world.app, versions, maya, _v2_body())
    assert (fourth.status_code, fourth.json()["version_no"]) == (201, 4), fourth.text


def test_est_evidence_at_submit_1_a_version_is_submitted_with_its_evidence_and_its_record(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Items EST-EVIDENCE-AT-SUBMIT-1 and the constraint's judgement record (04 §16.14 rev
    1.241, table 15.4-D; PRD IMP-138, IMP-140, ERR-94; 03 REQ-TP-004, REQ-POL-008, CTL-049).
    Before, a variable-consideration version was submitted and approved with no file and with
    any record or none: the constrained amount — the constraint conclusion REQ-POL-008 makes a
    reviewed judgement — posted its catch-up on nobody's review. Now the submission asks for the
    evidence and for the CONSTRAINT record of the element, sent for review or reviewed; the
    approval asks that the record is REVIEWED and that the evidence is still attached. The
    record's subject is the version, so its review moves no head: the version's request, which
    pins the head (item EST-PREVIEW-HEAD-PIN-1), is decided after it."""
    world = k06_world(app, keyring, clock, files)
    maya, priya = world.place.author, world.priya
    _, element_id = _k06_rebate(world)
    v1 = _draft(world.app, maya, element_id, _rebate_version(*V1_BODY))

    def submit() -> Any:
        return post(world.app, f"{VERSIONS}/{v1}/submit", maya, {"comment": "OK"})

    # --- nothing attached and no record named: both are asked, by name; nothing moved ---
    assert _findings(submit()) == [NO_EVIDENCE, NO_RECORD]
    assert _version(world.app, maya, v1)["status"] == "DRAFT"

    # --- with the evidence, the record is still asked — and not any record serves ---
    first_file = _attached(world.app, maya, v1)
    assert _findings(submit()) == [NO_RECORD]
    on_version = ("estimate_version", v1)
    elsewhere = booked_contract(
        world.place,
        {**k06_body(world.customer_id), "external_id": "NS-SO-DE-5003"},
        activate=False,
    )
    wrong = {
        "not a CONSTRAINT record": _record(world.app, maya, on_version, topic="OTHER"),
        "of another element": _record(world.app, maya, on_version, key="REBATE-DR-99"),
        "of another contract": _record(
            world.app, maya, ("contract", str(elsewhere.contract["id"]))
        ),
        "not sent for review": _record(world.app, maya, on_version, submit=False),
    }
    for why, record in wrong.items():
        _named(world.app, maya, v1, str(record["id"]))
        assert _findings(submit()) == [NO_RECORD], why

    # --- the element's CONSTRAINT record, sent for review: the version is submitted ---
    record = _record(world.app, maya, on_version)
    _named(world.app, maya, v1, str(record["id"]))
    sent = submit()
    assert (sent.status_code, sent.json()["status"]) == (200, "SUBMITTED"), sent.text
    request_id = str(sent.json()["approval_request_id"])

    # --- the approval waits for the record's review (PRD ERR-94) ---
    _lifecycle_refusal(
        approve(world.app, request_id, priya),
        RECORD_NOT_REVIEWED.format(no=record["judgement_no"]),
    )
    assert _version(world.app, maya, v1)["status"] == "SUBMITTED"
    reviewed = approve(world.app, str(record["approval_request_id"]), priya)
    assert (reviewed.status_code, reviewed.json()["status"]) == (200, "APPROVED"), reviewed.text

    # --- ... and for the evidence: its uploader may void it while the version waits ---
    voided = post(
        world.app, f"/api/v1/attachments/{first_file}/void", maya, {"reason": "The wrong file."}
    )
    assert voided.status_code == 200, voided.text
    _lifecycle_refusal(approve(world.app, request_id, priya), EVIDENCE_WITHDRAWN)
    assert _version(world.app, maya, v1)["status"] == "SUBMITTED"
    _attached(world.app, maya, v1)
    # neither the review of the record nor the attachments moved what the request pins
    decided = approve(world.app, request_id, priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert _version(world.app, maya, v1)["status"] == "APPROVED"


def test_est_evidence_at_submit_1_an_attestation_of_no_change_is_told_by_its_values(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Item EST-EVIDENCE-AT-SUBMIT-1, the attestation (04 §16.14 rev 1.241; PRD IMP-139,
    IMP-141; 03 REQ-TP-005). A variable-consideration version whose values equal those of the
    element's approved version is an attestation of no change: it owes no file and names no
    record of its own, and it states its reason in at least ten characters. It is told by its
    VALUES — the checklist by its marked factors — not by the flag the caller sends: a version
    that sends ``no_change_attestation`` with other values is refused on the flag, which the
    estimate change listing prints, and owes what a changed version owes."""
    world = k06_world(app, keyring, clock, files)
    maya, priya = world.place.author, world.priya
    k06 = _k06_with_v1(world, approved=True, shipped=False)
    unmarked = dict.fromkeys(CHECKLIST, False)

    def submit(version_id: str) -> Any:
        return post(world.app, f"{VERSIONS}/{version_id}/submit", maya, {"comment": "OK"})

    # --- the approved values again, with five unmarked factors where version 1 stored none ---
    attested = _draft(
        world.app,
        maya,
        k06.estimate_id,
        _rebate_version(
            "2026-09-30",
            "0.00",
            "Threshold not expected",
            "No change",
            constraint_checklist=unmarked,
            parameters={"no_change_attestation": True},
        ),
    )
    assert _findings(submit(attested)) == [
        ("rationale", "ESTIMATE_ATTESTATION_REASON", ATTESTATION_REASON)
    ]
    reasoned = patch(
        world.app,
        f"{VERSIONS}/{attested}",
        maya,
        {"rationale": "Reassessed at 30 September: the forecast stands at 925 units."},
        if_match=None,
    )
    assert reasoned.status_code == 200, reasoned.text
    sent = submit(attested)  # no file, no record of its own
    assert (sent.status_code, sent.json()["status"]) == (200, "SUBMITTED"), sent.text
    assert sent.json()["judgement_record_id"] is None
    decided = approve(world.app, str(sent.json()["approval_request_id"]), priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text

    # --- other values under the flag: refused on the flag, with what a changed version owes ---
    flagged = {"no_change_attestation": True, "refund_liability_target": "5750.00"}
    changed = _draft(world.app, maya, k06.estimate_id, {**_v2_body(), "parameters": flagged})
    assert _findings(submit(changed)) == [
        ("parameters.no_change_attestation", "ESTIMATE_ATTESTATION_VALUES", ATTESTATION_VALUES),
        NO_EVIDENCE,
        NO_RECORD,
    ]


def test_est_preview_head_pin_1_a_version_is_approved_on_the_head_it_was_previewed_on(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Item EST-PREVIEW-HEAD-PIN-1 (04 §16.10 rev 1.233; PRD SM-04 rev 1.165). Measured before:
    EAC version 2 (820,000.00) and bonus version 2 (200,000.00, no longer constrained) of K-03
    waited together; the bonus request showed a catch-up of 120,000.00 — 60.0% progress on the
    EAC of 700,000.00 — and once EAC version 2 was approved the approver decided the bonus on
    that preview while the approval posted 102,439.03 (51.2%). Now the request's content pins
    the contract's group and head: the EAC approval moves the head, the decision on the bonus
    request answers 409 ``stale-approval``, the request is voided and the version WITHDRAWN;
    revised and submitted again, its request shows 102,439.03 and its approval posts that.
    Beside it: an EAC version with the approved figures is no attestation — it owes its file."""
    world = k03_castellan(app, keyring, clock, files)
    report = world.report
    maya, priya, marcus = report.maya, report.priya, report.marcus
    step = timedelta(seconds=20)  # inside the approvers' MFA window (BR-PLT-06)

    def submitted(version_id: str) -> str:
        sent = post(world.app, f"{VERSIONS}/{version_id}/submit", maya, {"comment": "Review"})
        assert (sent.status_code, sent.json()["status"]) == (200, "SUBMITTED"), sent.text
        return str(sent.json()["approval_request_id"])

    def two_steps(request_id: str) -> None:
        first = approve(world.app, request_id, priya)
        assert (first.status_code, first.json()["status"]) == (200, "PENDING"), first.text
        second = approve(world.app, request_id, marcus)
        assert (second.status_code, second.json()["status"]) == (200, "APPROVED"), second.text

    # --- EAC version 2 and bonus version 2 wait together, each previewed on the same head ---
    clock.advance(step)
    eac_v2 = _draft(
        world.app,
        maya,
        world.eac_id,
        {
            "effective_date": "2026-09-10",
            "expected_total_amount": "820000.00",
            "rationale": "Change order CO-07 adds 120,000.00 of cost",
        },
    )
    estimate_version_ready(world.app, maya, eac_v2)
    eac_request = submitted(eac_v2)
    bonus_v2 = _draft(
        world.app,
        maya,
        world.bonus_id,
        {
            "effective_date": "2026-09-10",
            "scenarios": [
                {"outcome": "Completion bonus earned", "amount": "200000.00"},
                {"outcome": "Not earned", "amount": "0.00"},
            ],
            "unconstrained_amount": "200000.00",
            "most_conservative_amount": "0.00",
            "constrained_amount": "200000.00",
            "rationale": "Completion within the extended window is highly likely.",
        },
    )
    estimate_version_ready(world.app, maya, bonus_v2, constraint_of=BONUS_CB_01, reviewer=priya)
    bonus_request = submitted(bonus_v2)
    assert _impact(report.place, bonus_request) == Decimal("120000.00")

    # --- the EAC version is approved: the head moves under the bonus request ---
    clock.advance(step)
    two_steps(eac_request)
    assert k03_revenue(report.place, world.group_id) == Decimal("512195.12")
    clock.advance(step)
    _stale(world.app, priya, approve(world.app, bonus_request, priya), bonus_request)
    assert _version(world.app, maya, bonus_v2)["status"] == "WITHDRAWN"
    assert k03_revenue(report.place, world.group_id) == Decimal("512195.12")  # nothing posted

    # --- revised and submitted again: a fresh preview on the head as it stands ---
    revised = patch(
        world.app,
        f"{VERSIONS}/{bonus_v2}",
        maya,
        {"rationale": "Completion within the extended window is highly likely (after CO-07)."},
        if_match=None,
    )
    assert (revised.status_code, revised.json()["status"]) == (200, "DRAFT"), revised.text
    again = submitted(bonus_v2)
    assert _impact(report.place, again) == Decimal("102439.03")
    clock.advance(step)
    two_steps(again)
    # 1,200,000.00 at 420,000.00 of 820,000.00: what the two approvals posted
    assert k03_revenue(report.place, world.group_id) == Decimal("614634.15")

    # --- an EAC version with the approved figures owes its file: only a VC version attests ---
    unchanged = _draft(
        world.app,
        maya,
        world.eac_id,
        {
            "effective_date": "2026-09-30",
            "expected_total_amount": "820000.00",
            "rationale": "Reassessed at 30 September: no change.",
        },
    )
    owed = post(world.app, f"{VERSIONS}/{unchanged}/submit", maya, {"comment": "Review"})
    assert _findings(owed) == [NO_EVIDENCE]


def test_est_preview_head_pin_1_an_append_beside_a_pending_version_makes_its_request_stale(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Item EST-PREVIEW-HEAD-PIN-1: every append to the contract moves the head a pending
    version's request pins — a shipment and its invoice here, as an integration records them.
    The kernel compares the content before ANY decision, so a REJECTION of the stale request
    answers 409 ``stale-approval`` as an approval does, and the version ends WITHDRAWN, not
    REJECTED: it is revised and submitted again with a preview on the new head. Control: with
    nothing appended in between, the decision is taken."""
    world = k06_world(app, keyring, clock, files)
    maya, priya = world.place.author, world.priya
    k06 = _k06_with_v1(world, approved=True, shipped=False)
    v2 = _draft(world.app, maya, k06.estimate_id, _v2_body())
    request_id = _submitted(world, v2)
    appended(world.place, k06.contract_id, 3, _shipments())

    refused = reject(world.app, request_id, priya, "Not on this forecast.")
    _stale(world.app, priya, refused, request_id)
    assert _version(world.app, maya, v2)["status"] == "WITHDRAWN"

    revised = patch(world.app, f"{VERSIONS}/{v2}", maya, {"rationale": V2_RATIONALE}, if_match=None)
    assert (revised.status_code, revised.json()["status"]) == (200, "DRAFT"), revised.text
    decided = approve(world.app, _submitted(world, v2), priya)  # nothing appended in between
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text


def test_est_evidence_at_submit_1_a_record_that_changed_after_the_submission_holds_the_approval(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The constraint's judgement record at the approval (04 §16.14 rev 1.241; PRD ERR-94): the
    record is asked again when the version is decided, because it can change after the
    submission. A record its reviewer REJECTED is not reviewed: the approval is refused by name
    and the request stays pending. Revised into the record of another element and reviewed, it
    is no longer the CONSTRAINT record of this element: the approval asks for one in the words
    of the submission. The way out is the preparer's — she withdraws the version, names a
    record of the element and submits again."""
    world = k06_world(app, keyring, clock, files)
    maya, priya = world.place.author, world.priya
    _, element_id = _k06_rebate(world)
    v1 = _draft(world.app, maya, element_id, _rebate_version(*V1_BODY))
    _attached(world.app, maya, v1)
    record = _record(world.app, maya, ("estimate_version", v1))
    _named(world.app, maya, v1, str(record["id"]))

    def submit() -> str:
        sent = post(world.app, f"{VERSIONS}/{v1}/submit", maya, {"comment": "OK"})
        assert (sent.status_code, sent.json()["status"]) == (200, "SUBMITTED"), sent.text
        return str(sent.json()["approval_request_id"])

    request_id = submit()

    # --- the reviewer rejects the record: it is not reviewed ---
    rejected = reject(
        world.app, str(record["approval_request_id"]), priya, "The factors are not weighed."
    )
    assert rejected.status_code == 200, rejected.text
    not_reviewed = RECORD_NOT_REVIEWED.format(no=record["judgement_no"])
    _lifecycle_refusal(approve(world.app, request_id, priya), not_reviewed)

    # --- revised into the record of another element, sent again and reviewed ---
    edited = patch(
        world.app,
        f"/api/v1/judgements/{record['id']}",
        maya,
        {"questionnaire": {"estimate_key": "REBATE-DR-99", "remote": False}},
        if_match=None,
    )
    assert (edited.status_code, edited.json()["status"]) == (200, "DRAFT"), edited.text
    again = post(
        world.app, f"/api/v1/judgements/{record['id']}/submit", maya, {"comment": "Review"}
    )
    assert (again.status_code, again.json()["status"]) == (200, "SUBMITTED"), again.text
    reviewed = approve(world.app, str(again.json()["approval_request_id"]), priya)
    assert (reviewed.status_code, reviewed.json()["status"]) == (200, "APPROVED"), reviewed.text
    _lifecycle_refusal(approve(world.app, request_id, priya), CONSTRAINT_RECORD.format(code=REBATE))
    assert _version(world.app, maya, v1)["status"] == "SUBMITTED"

    # --- the way out: withdrawn, a record of the element named, submitted again ---
    withdrawn = post(world.app, f"{VERSIONS}/{v1}/withdraw", maya, {"comment": "Another record."})
    assert (withdrawn.status_code, withdrawn.json()["status"]) == (200, "WITHDRAWN"), withdrawn.text
    fresh = _record(world.app, maya, ("estimate_version", v1))
    _named(world.app, maya, v1, str(fresh["id"]))
    reviewed = approve(world.app, str(fresh["approval_request_id"]), priya)
    assert (reviewed.status_code, reviewed.json()["status"]) == (200, "APPROVED"), reviewed.text
    decided = approve(world.app, submit(), priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert _version(world.app, maya, v1)["status"] == "APPROVED"


SHRED_REASON: Final = "DSR-2026-0917: erase the person's data in this document"


def _document(app: FastAPI, actor: Actor, name: str, content: bytes) -> str:
    """``POST /files`` (purpose ``ATTACHMENT``) of ``content``; the stored file's id. The bytes
    differ from one document to the next: an upload of bytes the workspace holds answers the
    stored file (04 T-PLT-29 "Uploads of the same bytes")."""
    stored = call(
        app,
        "POST",
        "/api/v1/files",
        data={"purpose": "ATTACHMENT"},
        files={"file": (name, content, "text/csv")},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert stored.status_code == 201, stored.text
    return str(stored.json()["id"])


def test_est_evidence_at_submit_1_a_shredded_file_is_no_evidence(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Item EST-EVIDENCE-AT-SUBMIT-1 with 04 T-PLT-29 "A document a rule asks for" (rulings
    R-119 (g), R-120 (g); rev 1.241): the evidence of a version is a file that can still be
    read. A shred leaves the attachment row in place, live — and it is no evidence: the
    submission is refused as one without a file, and the approval of a version whose document
    was shredded while it waited is refused by name until one is attached again. Each file is
    shredded here by one administrator, without an approval: the evidence of an estimate
    version is not an evidence reference (the stated limit of T-PLT-29)."""
    world = k06_world(app, keyring, clock, files)
    maya, priya, marcus = world.place.author, world.priya, world.marcus
    k06 = _k06_with_v1(world, approved=True, shipped=False)
    v2 = _draft(world.app, maya, k06.estimate_id, _v2_body())

    def supported(name: str, content: bytes) -> str:
        file_id = _document(world.app, maya, name, content)
        attached = post(
            world.app,
            "/api/v1/attachments",
            maya,
            {"file_object_id": file_id, "subject_type": "estimate_version", "subject_id": v2},
        )
        assert attached.status_code == 201, attached.text
        return file_id

    def shred(file_id: str) -> None:
        erased = post(world.app, f"/api/v1/files/{file_id}/shred", marcus, {"reason": SHRED_REASON})
        assert erased.status_code == 200 and erased.json()["shredded_at"] is not None, erased.text

    def submit() -> Any:
        return post(world.app, f"{VERSIONS}/{v2}/submit", maya, {"comment": "OK"})

    record = _record(world.app, maya, ("estimate_version", v2))
    _named(world.app, maya, v2, str(record["id"]))

    # --- at the submission: the attachment of a shredded file is no evidence ---
    shred(supported("forecast-1.csv", b"forecast,units\nframework year,1450\n"))
    assert _findings(submit()) == [NO_EVIDENCE]
    held = supported("forecast-2.csv", b"forecast,units\nframework year,1451\n")
    sent = submit()
    assert (sent.status_code, sent.json()["status"]) == (200, "SUBMITTED"), sent.text
    request_id = str(sent.json()["approval_request_id"])
    reviewed = approve(world.app, str(record["approval_request_id"]), priya)
    assert (reviewed.status_code, reviewed.json()["status"]) == (200, "APPROVED"), reviewed.text

    # --- at the approval: the document was shredded while the version waited ---
    shred(held)
    _lifecycle_refusal(approve(world.app, request_id, priya), EVIDENCE_WITHDRAWN)
    assert _version(world.app, maya, v2)["status"] == "SUBMITTED"
    supported("forecast-3.csv", b"forecast,units\nframework year,1452\n")
    decided = approve(world.app, request_id, priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
